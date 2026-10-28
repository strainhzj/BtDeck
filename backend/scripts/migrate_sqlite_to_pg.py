#!/usr/bin/env python3
"""SQLite → PostgreSQL 迁移工具 CLI 薄壳（database-migration-ui W1-6）。

逻辑已抽取至服务层 ``app/services/db_migration/sqlite_to_pg.py``（工具 2.0.0，
新协议：ownership receipt/epoch/nonce 绑定）；本文件只保留 CLI 参数、attempt
绑定持久化与退出码翻译：

退出码：0 成功；1 预检未通过（默认拒绝）；2 目标库状态非法；3 导入中断
（可 --resume 恢复，attempt/nonce 由本地绑定文件回填，不进命令行历史）。

兼容性（PLANS §6.3）：
- 无 database.active 的旧 env 用法（DB_TYPE=postgresql + DB_*）保持；
- 存在受管 active 且隐式目标有歧义 → fail-closed 提示 --connection-profile
  （受保护连接档案由 W3 配置仓储提供，本版本明确拒绝而不偷换 --target-config）；
- 旧 1.1.0 checkpoint（无 ownership 绑定）明确拒绝恢复，不伪装兼容。

用法：
  python scripts/migrate_sqlite_to_pg.py --source /path/app.db --precheck
  python scripts/migrate_sqlite_to_pg.py --source /path/app.db
  python scripts/migrate_sqlite_to_pg.py --source /path/app.db --resume
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# 允许脚本从 backend/ 或仓库根运行（backend/scripts/ 下的既有惯例）
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core import database_bootstrap as bootstrap  # noqa: E402
from app.core.database_bootstrap import PostgresParams  # noqa: E402
from app.services.db_migration import pipeline  # noqa: E402
from app.services.db_migration.pg_to_sqlite import _atomic_write_private  # noqa: E402
from app.services.db_migration.pipeline import PipelineContext  # noqa: E402
from app.services.db_migration.sqlite_to_pg import (  # noqa: E402
    MigrationInterrupted,
    PrecheckFailed,
    TargetInvalid,
    precheck,
    run_sqlite_to_pg,
)
from app.services.db_migration.target_params import pg_engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_sqlite_to_pg")


# ==================== attempt 绑定持久化（§4.2 journal 的 W1 最小切片） ====================


def _config_dir() -> Path:
    config_dir = os.getenv("CONFIG_DIR")
    if config_dir:
        return Path(config_dir)
    return BACKEND_ROOT / "config"


def _attempt_binding_dir(attempt_id: str) -> Path:
    uuid_tail = attempt_id.rsplit("/", 1)[1]
    return _config_dir() / "db-migration" / "attempts" / uuid_tail


def persist_attempt_binding(ctx: PipelineContext) -> Path:
    """持久 attempt 绑定（attempt_id/nonce/epoch；0600 原子写）——resume 凭据来源。

    W3 journal（manifest/control 仓储锁）交付前的最小实现：仅本机绑定，
    不含连接参数或密码。
    """
    directory = _attempt_binding_dir(ctx.attempt_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "attempt.json"
    _atomic_write_private(
        path,
        {
            "attempt_id": ctx.attempt_id,
            "ownership_nonce": ctx.ownership_nonce,
            "origin_epoch": ctx.origin_epoch,
            "eligible_epoch": ctx.eligible_epoch,
            "tool_version": pipeline.TOOL_VERSION,
        },
    )
    return path


def load_latest_attempt_binding() -> Optional[Dict[str, Any]]:
    """读取最近的 attempt 绑定（mtime 最新）；无/损坏返回 None（--resume 无法回填凭据）。"""
    attempts_root = _config_dir() / "db-migration" / "attempts"
    if not attempts_root.is_dir():
        return None
    candidates = sorted(
        (p for p in attempts_root.iterdir() if p.is_dir() and (p / "attempt.json").exists()),
        key=lambda p: (p / "attempt.json").stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    try:
        data = json.loads((candidates[0] / "attempt.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("attempt_id") or not data.get("ownership_nonce"):
        return None
    return data


# ==================== 目标解析（env 保持 / active fail-closed） ====================


def _resolve_target_params() -> PostgresParams:
    """目标解析：受管 active 存在 → fail-closed（TargetInvalid→exit 2，不偷换 --target-config）。"""
    active = bootstrap.load_active_config(_config_dir() / "config.yaml")
    if active is not None:
        raise TargetInvalid(
            "检测到受管有效配置 database.active：隐式 env 目标有歧义，"
            "需受保护 --connection-profile 显式指定目标（W3 配置仓储提供；本版本拒绝执行）"
        )
    environ = os.environ
    if (environ.get("DB_TYPE") or "").strip().lower() not in ("postgresql", "postgres", "pg"):
        raise TargetInvalid("必须以 DB_TYPE=postgresql 运行本工具（目标库配置与应用同源，契约 §2.1）")
    effective = bootstrap.resolve_effective_database_config(_config_dir() / "config.yaml")
    assert effective.pg is not None  # env 分支已保证 postgresql 方言
    return effective.pg


def main(argv: Optional[list] = None) -> int:
    # force：应用链路导入可能已给 root 装默认 WARNING 级 handler（basicConfig 幂等不覆盖）
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    parser = argparse.ArgumentParser(description="BtDeck SQLite → PostgreSQL 迁移工具（协议 2.0.0）")
    parser.add_argument("--source", default=None, help="源 SQLite 路径（默认 settings.DATABASE_PATH）")
    parser.add_argument("--precheck", action="store_true", help="仅预检（不连 PG，退出码 0/1）")
    parser.add_argument(
        "--auto-wrap-scalar", action="store_true", help="JSON 裸标量包裹为数组（仅匹配字段元素类型；出报告）"
    )
    parser.add_argument("--resume", action="store_true", help="从检查点恢复未完成导入（attempt 绑定自本地文件回填）")
    parser.add_argument("--source-config", help="原部署 config.yaml（含加密下载器时必需）")
    parser.add_argument("--target-config", help="目标部署 config.yaml（须与源 SM4 密钥同源）")
    parser.add_argument("--backup-root", default=str(BACKEND_ROOT), help="目标部署后端根目录，用于相对备份路径核验")
    parser.add_argument(
        "--connection-profile",
        default=None,
        help="受保护连接档案名（受管 active 存在时必需；由 W3 配置仓储提供，本版本不可用即拒绝）",
    )
    args = parser.parse_args(argv)

    if args.connection_profile is not None:
        logger.error("--connection-profile 需要受保护连接档案支持（W3 配置仓储交付）；当前版本不可用")
        return 2

    from app.core.config import settings

    source = args.source or str(settings.DATABASE_PATH)
    if not Path(source).exists():
        logger.error("源库不存在: %s", source)
        return 1

    asset_paths = {
        "source_config": args.source_config or str(Path(source).parent / "config.yaml"),
        "target_config": args.target_config or str(settings.YAML_PATH),
        "backup_root": args.backup_root,
    }

    # 仅预检：不连目标、不落 attempt
    if args.precheck:
        errors, warnings, version = precheck(source, auto_wrap=args.auto_wrap_scalar, asset_paths=asset_paths)
        for w in warnings:
            logger.warning("[预检] %s", w)
        for e in errors:
            logger.error("[预检] %s", e)
        logger.info("[预检] 源版本=%s；错误=%d 警告=%d", version, len(errors), len(warnings))
        return 1 if errors else 0

    try:
        params = _resolve_target_params()
    except TargetInvalid as exc:
        logger.error("目标解析失败：%s", exc)
        return 2

    # attempt 上下文：新开 or --resume 回填本地绑定（凭据不进命令行）
    if args.resume:
        binding = load_latest_attempt_binding()
        if binding is None:
            logger.error("--resume 需要本地 attempt 绑定（db-migration/attempts/*/attempt.json）；未找到——拒绝")
            return 2
        ctx = PipelineContext(
            attempt_id=str(binding["attempt_id"]),
            ownership_nonce=str(binding["ownership_nonce"]),
            origin_epoch=str(binding.get("origin_epoch") or ""),
            eligible_epoch=str(binding.get("eligible_epoch") or ""),
        )
        logger.info("[恢复] attempt=%s（本地绑定回填）", ctx.attempt_id)
    else:
        ctx = PipelineContext(attempt_id=pipeline.make_attempt_id("sqlite-to-pg"))
        binding_path = persist_attempt_binding(ctx)
        logger.info("[attempt] %s（绑定已持久 %s）", ctx.attempt_id, binding_path)

    engine = pg_engine(params)
    try:
        result = run_sqlite_to_pg(
            source,
            pg_engine=engine,
            ctx=ctx,
            resume=args.resume,
            auto_wrap=args.auto_wrap_scalar,
            asset_paths=asset_paths,
        )
    except PrecheckFailed as exc:
        logger.error("[预检] 未通过：%s（共 %d 项）", exc, len(exc.errors))
        return 1
    except TargetInvalid as exc:
        logger.error("目标库状态非法：%s", exc)
        return 2
    except MigrationInterrupted as exc:
        logger.error("导入中断：%s；修复原因后 --resume（attempt 绑定已保留）", exc)
        return 3
    finally:
        engine.dispose()

    logger.info("[完成] %d 表 %d 行；receipt=VERIFIED", result["tables"], result["rows"])
    _print_switch_guide(source, ctx.attempt_id)
    return 0


def _print_switch_guide(source_path: str, attempt_id: str) -> None:
    logger.info("=" * 60)
    logger.info("切换指引（契约 §3：无损回退窗口 = 首次正常启动前的离线核对）")
    logger.info("1. 保持源库停写；目标 PG 已就绪（receipt=%s VERIFIED，应用尚未启动过）", attempt_id)
    logger.info("2. 离线核对：psql 抽查关键表/行数（或重跑本工具 --precheck 对照源库）")
    logger.info("3. 切换/激活：database-migration-ui 的 A 指引或 B 一键切换（W3 交付）")
    logger.info("   —— 直接改 env 启动会被 VERIFIED receipt 拒启（首次激活核验）")
    logger.info("4. 回退边界：激活后首次业务写入结束无损回退窗口；源库 %s 请归档保留", source_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
