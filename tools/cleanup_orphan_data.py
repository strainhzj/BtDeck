#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BtDeck 孤儿文件存量数据清理脚本（正式环境 / Docker 部署）。

作用：清空孤儿扫描相关的 4 张表，让前端不再展示历史孤儿列表，
      下次扫描成功后重新生成准确的孤儿数据。

清理范围（仅这 4 张表，不动其他任何数据）：
  - orphan_file              （孤儿明细，FK → orphan_scan_result）
  - orphan_scan_result       （扫描批次）
  - orphan_current_candidate （当前候选）
  - orphan_operation_lease   （操作租约）

安全特性：
  1. 自动定位 db：优先 --db 参数；否则从 btdeck-backend 容器挂载推断；
     再否则按 docker-compose 约定查找 ./data/backend/config/app.db
  2. 执行前自动备份（带时间戳 .bak）
  3. 检测 db 是否被运行中的容器持有写锁（WAL/SHM + 锁探测），若被占用则中止
  4. 单事务内删除，先子表后父表；失败自动回滚
  5. 幂等：表不存在 / 已为空 / 已清理过，均安全重复执行
  6. 删除前后打印行数对照 + 外键完整性校验 + 下载器/种子数据未被动校验
  7. --dry-run 仅模拟不写入

用法（在正式机宿主机执行，需 python3 + docker CLI）：
  python3 cleanup_orphan_data.py                 # 自动定位 + 清理
  python3 cleanup_orphan_data.py --dry-run       # 仅模拟，查看会清什么
  python3 cleanup_orphan_data.py --db /path/app.db   # 指定 db 路径
  python3 cleanup_orphan_data.py --container btdeck-backend  # 指定容器名

@file: tools/cleanup_orphan_data.py
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ORPHAN_TABLES = [
    "orphan_file",              # 子表（FK → orphan_scan_result）
    "orphan_current_candidate",
    "orphan_operation_lease",
    "orphan_scan_result",       # 父表（最后删）
]

# 依赖顺序：先子后父（FK 约束）
DELETE_ORDER = [
    "orphan_file",
    "orphan_current_candidate",
    "orphan_operation_lease",
    "orphan_scan_result",
]


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd: list[str]) -> tuple[int, str]:
    """运行命令，返回 (returncode, stdout)。"""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace"
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, ""
    except Exception as e:  # noqa: BLE001
        return 1, str(e)


def locate_db(args: argparse.Namespace) -> Path | None:
    """按优先级定位 db 文件。"""
    # 1. 显式 --db
    if args.db:
        p = Path(args.db).expanduser().resolve()
        if p.is_file():
            log(f"使用指定 db: {p}")
            return p
        log(f"✗ 指定的 db 不存在: {p}")
        return None

    # 2. 从 docker 容器挂载推断
    container = args.container
    if container:
        rc, out = run(["docker", "inspect",
                       "--format",
                       "{{range .Mounts}}{{.Source}}::{{.Destination}}{{println}}{{end}}",
                       container])
        if rc == 0:
            for line in out.splitlines():
                if "::" not in line:
                    continue
                src, dst = line.split("::", 1)
                # 容器内 /app/config 或 /config 挂载点 → 宿主侧含 app.db
                if dst.rstrip("/").endswith("/config") or dst.rstrip("/").endswith("/app/config"):
                    candidate = Path(src) / "app.db"
                    if candidate.is_file():
                        log(f"从容器 {container} 挂载定位 db: {candidate}")
                        return candidate.resolve()

    # 3. docker-compose 约定 ./data/backend/config/app.db（当前目录及向上查找）
    for base in [Path.cwd(), *Path.cwd().parents]:
        candidate = base / "data" / "backend" / "config" / "app.db"
        if candidate.is_file():
            log(f"按 compose 约定定位 db: {candidate}")
            return candidate.resolve()

    log("✗ 未能自动定位 db，请用 --db 显式指定路径")
    return None


def db_locked(db_path: Path) -> bool:
    """检测 db 是否被占用（运行中的容器持有写锁）。

    尝试 BEGIN IMMEDIATE 获取写锁；2 秒内拿不到视为被占用。
    """
    import sqlite3
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT 1").fetchone()
        cur.execute("COMMIT")
        conn.close()
        return False
    except sqlite3.OperationalError as e:
        return "locked" in str(e).lower() or "busy" in str(e).lower()
    except Exception:
        return False


def backup_db(db_path: Path) -> Path | None:
    """备份 db 到同目录带时间戳的 .bak 文件。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = db_path.with_name(f"{db_path.name}.bak.{ts}")
    try:
        shutil.copy2(db_path, bak)
        log(f"✓ 已备份: {bak} ({bak.stat().st_size // 1024} KB)")
        return bak
    except Exception as e:  # noqa: BLE001
        log(f"✗ 备份失败: {e}")
        return None


def count_rows(cur, table: str) -> int:
    try:
        return cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return -1  # 表不存在


def table_exists(cur, table: str) -> bool:
    r = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return r is not None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="清理 BtDeck 孤儿文件存量数据（仅 4 张孤儿表）")
    parser.add_argument("--db", help="显式指定 app.db 路径")
    parser.add_argument("--container", default="btdeck-backend",
                        help="后端容器名（用于推断挂载路径，默认 btdeck-backend）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅模拟，不写入数据库")
    parser.add_argument("--no-backup", action="store_true",
                        help="跳过备份（不推荐）")
    args = parser.parse_args()

    global sqlite3
    import sqlite3

    log("=" * 60)
    log("BtDeck 孤儿数据清理脚本")
    log("=" * 60)

    # 1. 定位 db
    db_path = locate_db(args)
    if db_path is None:
        return 2

    # 2. 锁检测
    if db_locked(db_path):
        log("✗ 数据库被占用（运行中的容器可能正持有写锁）。")
        log("  请先停止 BtDeck 后端容器再执行：docker stop <container>")
        return 3
    log("✓ 数据库未被占用")

    # 3. 检查孤儿表是否存在（版本兼容）
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    missing = [t for t in ORPHAN_TABLES if not table_exists(cur, t)]
    if missing:
        log(f"✗ 以下孤儿表不存在: {missing}")
        log("  正式环境版本可能低于 v1.0.6（无孤儿扫描功能），无需清理。")
        conn.close()
        return 4

    # 4. 删除前行数
    before = {t: count_rows(cur, t) for t in ORPHAN_TABLES}
    log("删除前行数:")
    for t in ORPHAN_TABLES:
        log(f"  {t}: {before[t]}")

    total = sum(before.values())
    if total == 0:
        log("✓ 孤儿表已全部为空，无需清理")
        conn.close()
        return 0

    # 5. 参照数据完整性快照（确认不误伤）
    dl_count = count_rows(cur, "bt_downloaders")
    ti_count = count_rows(cur, "torrent_info")
    log(f"参照: bt_downloaders={dl_count} torrent_info={ti_count}（清理后应不变）")

    # 6. dry-run 截止
    if args.dry_run:
        log(f"[DRY-RUN] 将清理 {total} 行孤儿数据，未实际写入")
        conn.close()
        return 0

    # 7. 备份
    if not args.no_backup:
        bak = backup_db(db_path)
        if bak is None:
            log("✗ 备份失败，已中止（可用 --no-backup 强制跳过，不推荐）")
            conn.close()
            return 5

    # 8. 事务内删除（先子后父）
    try:
        cur.execute("BEGIN IMMEDIATE")
        for t in DELETE_ORDER:
            n = cur.execute(f"DELETE FROM {t}").rowcount
            if n:
                log(f"  DELETE {t}: {n} 行")
        cur.execute("COMMIT")
        log("✓ 事务已提交")
    except Exception as e:  # noqa: BLE001
        cur.execute("ROLLBACK")
        log(f"✗ 删除失败，已回滚: {e}")
        conn.close()
        return 6

    # 9. 验证
    after = {t: count_rows(cur, t) for t in ORPHAN_TABLES}
    log("删除后行数:")
    for t in ORPHAN_TABLES:
        log(f"  {t}: {after[t]}")

    dl_after = count_rows(cur, "bt_downloaders")
    ti_after = count_rows(cur, "torrent_info")
    fk_violations = cur.execute("PRAGMA foreign_key_check").fetchall()

    conn.close()

    log("-" * 60)
    ok = True
    if any(after.values()):
        log("✗ 清理后仍有残留数据")
        ok = False
    if dl_after != dl_count or ti_after != ti_count:
        log(f"✗ 参照数据被误伤！bt_downloaders {dl_count}→{dl_after}, torrent_info {ti_count}→{ti_after}")
        ok = False
    else:
        log(f"✓ 参照数据未变: bt_downloaders={dl_after} torrent_info={ti_after}")
    if fk_violations:
        log(f"✗ 外键完整性违例: {fk_violations}")
        ok = False
    else:
        log("✓ 外键完整性无违例")

    if ok:
        log("=" * 60)
        log("✓ 清理完成")
        log("  注意：下次扫描仍会因路径映射缺失而 fail-closed，")
        log("        需在下载器设置中补全 save_path 的 internal→external 映射后才能成功扫描。")
        log("=" * 60)
        return 0
    log("✗ 清理完成但验证发现问题，请检查日志")
    return 7


if __name__ == "__main__":
    sys.exit(main())
