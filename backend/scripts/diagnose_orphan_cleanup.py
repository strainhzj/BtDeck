# -*- coding: utf-8 -*-
"""孤儿文件清理诊断脚本（只读）。

当 cleanup-preview 对一批 orphan_id 返回 total_count=0/items=[] 时，本脚本在
后端实际连接的数据库上逐项核查这些 id 为何「查不到」，定位根因。

使用示例（在 backend/ 目录）：
    python scripts/diagnose_orphan_cleanup.py --scan-id b9606bb0-... --orphan-ids 203494 203495 203496
    python scripts/diagnose_orphan_cleanup.py --orphan-ids 203494          # 不传 scan-id 只看明细

默认 DB 路径取 app.core.config.settings.DATABASE_PATH（与运行时一致）；
可用 --db 显式覆盖。脚本只读，不改任何数据。
"""
from __future__ import annotations

import argparse
import io
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional

# 保证中文输出在 Windows 控制台不乱码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def resolve_db_path(override: Optional[str]) -> str:
    """解析 DB 路径：--db > 环境变量 DATABASE_PATH > app settings.DATABASE_PATH > config/app.db。"""
    if override:
        return override
    env = os.getenv("DATABASE_PATH")
    if env:
        return env
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app.core.config import settings

        return str(settings.DATABASE_PATH)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 无法导入 app settings，回退 config/app.db：{exc}")
        return os.path.join("config", "app.db")


def columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def main() -> int:
    parser = argparse.ArgumentParser(description="诊断 cleanup-preview 为何对指定 orphan_id 返回空")
    parser.add_argument("--orphan-ids", nargs="+", type=int, required=True, help="要核查的 orphan_file.id 列表")
    parser.add_argument("--scan-id", default=None, help="请求里传入的 scan_id（可选，用于比对一致性）")
    parser.add_argument("--db", default=None, help="显式指定 app.db 路径（默认取运行时配置）")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    print("=" * 72)
    print(f"DB 路径: {db_path}")
    if not os.path.exists(db_path):
        print(f"[错误] DB 文件不存在：{db_path}")
        print("       后端实际连的库可能不在这里；可用 --db 显式指定。")
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print("\n========== 1. 迁移版本与列结构 ==========")
    try:
        versions = [r[0] for r in conn.execute("SELECT version_num FROM alembic_version").fetchall()]
        print(f"当前 alembic 版本: {versions}")
    except sqlite3.OperationalError:
        print("[警告] 无 alembic_version 表")
        versions = []

    # 代码迁移头（a1b2c3d4e5f6）正是加 canonical_path 的迁移；若 DB 版本早于它，列可能缺失。
    head = "a1b2c3d4e5f6"
    if versions and versions[0] != head:
        print(f"  ⚠️  DB 版本 {versions[0]} 早于代码迁移头 {head}，迁移可能未应用！")
        print("      a1b2c3d4e5f6 正是给 orphan_file 加 canonical_path、给候选加 is_ignored 的迁移。")
        print("      若列缺失，preview 的 SQL 会报错（500），而非返回空。")

    of_cols = columns(conn, "orphan_file")
    cand_cols = columns(conn, "orphan_current_candidate")
    print(f"\norphan_file 列: {of_cols}")
    print(f"  canonical_path 存在? {'是' if 'canonical_path' in of_cols else '否 ❌'}")
    print(f"  confidence 存在?   {'是' if 'confidence' in of_cols else '否 ❌'}")
    print(f"\norphan_current_candidate 列: {cand_cols}")
    print(f"  is_ignored 存在?   {'是' if 'is_ignored' in cand_cols else '否 ❌'}")

    has_canonical = "canonical_path" in of_cols
    has_confidence = "confidence" in of_cols

    print("\n========== 2. orphan_id 明细核查 ==========")
    ids = args.orphan_ids
    qmarks = ",".join("?" * len(ids))

    detail_cols = [c for c in ("id", "scan_id", "file_path", "file_size", "downloader_id") if c in of_cols]
    if has_confidence:
        detail_cols.append("confidence")
    if has_canonical:
        detail_cols.append("canonical_path")
    detail_cols += [c for c in ("is_deleted", "deleted_at") if c in of_cols]

    select_clause = ", ".join(detail_cols)
    rows = conn.execute(f"SELECT {select_clause} FROM orphan_file WHERE id IN ({qmarks})", ids).fetchall()

    found_ids = {r["id"] for r in rows}
    missing_ids = [i for i in ids if i not in found_ids]

    print(f"请求 orphan_ids: {ids}")
    print(f"库中找到: {len(rows)} 条")
    if missing_ids:
        print(f"  ⚠️  以下 id 在 orphan_file 中【不存在】（可能 scan_id 属于别的库/批次）: {missing_ids}")

    # 每条诊断「为何 preview 查不到」
    print("\n--- 逐项根因判定（preview 过滤条件）---")
    for r in rows:
        d = row_to_dict(r)
        reasons: List[str] = []
        if args.scan_id and d.get("scan_id") != args.scan_id:
            reasons.append(f"scan_id 不匹配（明细={d.get('scan_id')} ≠ 请求={args.scan_id}）")
        if d.get("is_deleted"):
            reasons.append("已清理（is_deleted=1）")
        if has_confidence and d.get("confidence") != "high":
            reasons.append(f"低置信度（confidence={d.get('confidence')}，被 preview 的 ==high 过滤）")
        verdict = "；".join(reasons) if reasons else "✅ 明细层面未被过滤，可进入 preview（根因可能在候选忽视态或 SQL 报错）"
        print(f"\n  id={d.get('id')}: {d.get('file_path')}")
        print(f"    scan_id={d.get('scan_id')}, confidence={d.get('confidence')}, is_deleted={d.get('is_deleted')}")
        print(f"    => {verdict}")

    # 候选忽视态核查（preview 还会过滤 canonical_path NOT IN 候选 is_ignored 集合）
    if has_canonical and rows:
        print("\n========== 3. 候选忽视态核查（preview 的 NOT IN 过滤）==========")
        cps = [r["canonical_path"] for r in rows if r["canonical_path"]]
        if cps:
            cp_qmarks = ",".join("?" * len(cps))
            ignore_check = conn.execute(
                f"SELECT canonical_path, is_ignored, status, operation_state FROM orphan_current_candidate "
                f"WHERE canonical_path IN ({cp_qmarks})",
                cps,
            ).fetchall()
            cand_map = {r["canonical_path"]: row_to_dict(r) for r in ignore_check}
            for r in rows:
                cp = r["canonical_path"]
                cand = cand_map.get(cp)
                if not cand:
                    print(f"  id={r['id']}: 无候选记录（preview 仍会放行，因 NOT IN 空集为真）")
                elif cand.get("is_ignored"):
                    print(f"  id={r['id']}: ⚠️ 候选 is_ignored=1，被 preview 的 NOT IN 过滤（忽视态保护）")
                else:
                    print(f"  id={r['id']}: 候选 is_ignored=0, status={cand.get('status')}, op={cand.get('operation_state')}（未因忽视被过滤）")
        else:
            print("  明细无 canonical_path 值（全为 NULL）")

    print("\n========== 4. 结论汇总 ==========")
    if missing_ids:
        print(f"  → 主因倾向：{len(missing_ids)} 个 id 在此库不存在。检查 DB 是否是后端实际连接的库，")
        print("    或 scan_id 是否属于历史批次（cleanup_preview 要求 scan_id == 明细 scan_id）。")
    elif has_confidence and all(r["confidence"] != "high" for r in rows if has_confidence):
        print("  → 主因倾向：所选文件均为低置信度（low），preview 的 ==high 过滤是预期行为（low 不可清理）。")
        print("    前端应提示用户「需等下载器上线精筛后清理」，而非静默空。")
    elif has_canonical and any(
        conn.execute(
            "SELECT is_ignored FROM orphan_current_candidate WHERE canonical_path=?", (r["canonical_path"],)
        ).fetchone()
        and conn.execute(
            "SELECT is_ignored FROM orphan_current_candidate WHERE canonical_path=?", (r["canonical_path"],)
        ).fetchone()[0]
        for r in rows
        if r["canonical_path"]
    ):
        print("  → 主因倾向：所选文件已被忽视，preview 的 NOT IN 过滤是预期行为（忽视态保护）。")
        print("    前端应提示用户「先取消忽视才能清理」。")
    elif versions and versions[0] != head:
        print(f"  → 主因倾向：DB 迁移未应用（{versions[0]} → {head}），列结构可能不完整。")
        print("    请在远端重启后端（触发自动迁移）或手动 `alembic upgrade head`。")
    else:
        print("  → 未发现明显根因，建议：检查后端日志中 cleanup_preview 的实际异常堆栈。")

    conn.close()
    print("\n" + "=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
