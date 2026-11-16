# -*- coding: utf-8 -*-
"""业务引擎加载前的早期启动决议（复核修复批 W3 / R4 深水区，§7.2.6-8）。

背景（冷启动实测，2026-11-15 审查缺陷 3/8）：``app.database`` 在**导入期**
用当时的有效配置建好同步/异步引擎池与 URL 工厂；激活 redo 原挂在 lifespan
gate——此时引擎已按旧配置实例化，redo 补发布只改磁盘文件，业务 Session 照写
旧源（W1 只能以"调度托管退出 / 回维护分支"兜底）。本模块把 redo 提到
**任何引擎模块导入之前**执行：

    app/main.py 顶部（仅 stdlib/config 导入之后）::

        resolve_and_prepare_startup(settings.YAML_PATH)

    → 幂等补配置发布 + 目标 ACK（显式候选目标，严格事务核验）→ 审计归档 →
      本地 ACTIVATED_ACK → 清 RESTART_PENDING

之后 ``app.factory`` / ``app.database`` 才被导入：解析到的有效配置已是新
目标，引擎/URL 工厂天然指向新库——无漂移、无需托管退出。

依赖纪律（与 database_bootstrap 同一 fail-closed 链路）：本模块**禁止
import** ``app.database`` / ``app.core.migration`` / ``app.factory``（引擎
与路由副作用模块）；目标连接一律从**已发布配置**（bootstrap 纯解析）现建。
lifespan gate 的 redo 兜底保留并复用同一实现（幂等：COMMITTED 未 ACK 时
重复执行安全；已完成/无 pending 则 nothing_pending）。

失败语义：redo 任一步失败 → 打印 WARN 并返回 ``REDO_FAILED``，**导入继续**
——lifespan gate 仍见 COMMITTED → 进维护分支重试同一幂等实现。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.core.database_bootstrap import (
    DIALECT_POSTGRESQL,
    DIALECT_SQLITE,
    ManagedStateError,
    pg_sync_url,
    resolve_effective_database_config,
)

__all__ = [
    "REDO_COMPLETED",
    "REDO_FAILED",
    "REDO_NOTHING_PENDING",
    "run_pending_activation_redo",
    "resolve_and_prepare_startup",
]

REDO_COMPLETED = "completed"
REDO_NOTHING_PENDING = "nothing_pending"
REDO_FAILED = "failed"


def _published_sync_engine(yaml_path: str):
    """从**已发布**有效配置现建同步引擎（绝不 import app.database 走导入期缓存）。

    发布后的 config.yaml 即目标配置：sqlite → sqlite:/// 路径；postgresql →
    psycopg2 + sslmode 查询参数（契约 §2.3，与 verify_active_database_binding
    同源构造）。NullPool：一次性归档连接，不复用。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    effective = resolve_effective_database_config(yaml_path)
    if effective.dialect == DIALECT_SQLITE:
        path = effective.sqlite_path or ""
        if not path or not Path(path).is_absolute():
            raise ManagedStateError(f"已发布 sqlite_path 缺失/非绝对: {path!r}")
        return create_engine(f"sqlite:///{path}", poolclass=NullPool)
    if effective.dialect == DIALECT_POSTGRESQL:
        pg = effective.pg
        if pg is None:
            raise ManagedStateError("已发布配置指向 postgresql 但参数缺失")
        return create_engine(pg_sync_url(pg), poolclass=NullPool, connect_args={"connect_timeout": 8})
    raise ManagedStateError(f"已发布配置方言非法: {effective.dialect!r}")


def run_pending_activation_redo(
    config_dir: str,
    *,
    yaml_path: Optional[str] = None,
    service_factory: Optional[Callable[[str], Any]] = None,
) -> str:
    """COMMITTED 待 ACK 的幂等 redo（§7.2.6-8）→ REDO_COMPLETED / *_FAILED。

    顺序：journal 权威判定 → 幂等补配置发布 → **目标 ACK 先**（activated_at/
    generation，显式候选目标单连接事务）→ 审计归档（同事件去重回放）→ 本地
    ACTIVATED_ACK → 清 RESTART_PENDING。ACTIVATED_ACK 已本地 ACK 的 attempt
    返回 REDO_NOTHING_PENDING（归档兜底归维护面/正常启动 gate，语义与
    evaluate_startup_disposition 一致）。
    """
    from app.services.db_migration.activation import ActivationService
    from app.services.db_migration.journal import Journal

    journal = Journal(config_dir)
    try:
        authority = journal.evaluate_intent_authority()
    except Exception as exc:  # noqa: BLE001 - 损坏交 lifespan fail-closed
        print(f"[WARN] 早期启动决议：journal 权威判定失败: {exc}")
        return REDO_FAILED
    if not authority.committed_pending_restart:
        return REDO_NOTHING_PENDING

    if service_factory is not None:
        service = service_factory(config_dir)
    else:
        service = ActivationService(
            config_dir,
            yaml_path=yaml_path,
            restart_scheduler=lambda _info: False,  # 导入前完成即无漂移，绝不调度退出
        )
    redo: Optional[Dict[str, Any]]
    try:
        redo = service.redo_pending_activation()
    except Exception as exc:  # noqa: BLE001 - 候选损坏/发布失败同样保持 COMMITTED
        print(f"[WARN] 早期启动决议：幂等补发布失败（保持 COMMITTED）: {exc}")
        return REDO_FAILED
    if redo is None or not redo.get("awaitingTargetAck"):
        return REDO_NOTHING_PENDING
    attempt_id = str(redo["attemptId"])

    def _archive(attempt: str) -> int:
        """spool → bt_database_migration_events（event_id 幂等去重）。

        连接目标 = 已发布配置（关键：不能走 app.database 导入期缓存——本函数
        在引擎模块导入**之前**或兜底位运行，均以磁盘上已发布的新配置为准）。
        """
        from app.services.db_migration.local_audit import MaintenanceLocalAudit
        from sqlalchemy import text

        audit = MaintenanceLocalAudit(config_dir)
        rows, token = audit.snapshot_for_archive()
        engine = _published_sync_engine(yaml_path or _default_yaml_path(config_dir))
        archived = 0
        try:
            with engine.begin() as conn:
                for row in rows:
                    if row.get("attempt_id") not in (None, attempt):
                        continue
                    result = conn.execute(
                        text(
                            "INSERT INTO bt_database_migration_events "
                            "(event_id, attempt_id, seq, summary, created_at) "
                            "VALUES (:eid, :aid, :seq, :summary, :created) "
                            "ON CONFLICT (event_id) DO NOTHING"
                        ),
                        {
                            "eid": row.get("event_id"),
                            "aid": attempt,
                            "seq": row.get("seq", 0),
                            "summary": str(row.get("summary", row.get("kind", "event")))[:512],
                            "created": _archive_created(row.get("ts")),
                        },
                    )
                    archived += max(result.rowcount or 0, 0)
        finally:
            engine.dispose()
        if rows:
            service.advance_archive_cursor(str(rows[-1].get("event_id", "")))
            audit.clear_if_unchanged(token)
        return archived

    try:
        service.complete_activation(attempt_id, archive_audit=_archive)
    except Exception as exc:  # noqa: BLE001 - 失败保持 COMMITTED 交维护分支
        print(f"[WARN] 早期启动决议：激活 redo 失败（保持 COMMITTED）: {exc}")
        return REDO_FAILED
    print(f"[OK] 早期启动决议：激活 redo 完成（目标 ACK→归档→本地 ACK）: {attempt_id}")
    return REDO_COMPLETED


def _archive_created(value: Any) -> Any:
    """spool ts 归一 naive UTC（epoch 数值 → datetime；否则原样）。"""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
    return value


def _default_yaml_path(config_dir: str) -> str:
    """config_dir → config.yaml（与 settings.YAML_PATH 同布局；测试/显式入口用）。"""
    return str(Path(config_dir) / "config.yaml")


def resolve_and_prepare_startup(yaml_path: Optional[str] = None) -> None:
    """``app.main`` 顶部导入前入口；**绝不抛出**（导入必须继续）。

    成功完成 redo → 打印 OK（随后的引擎导入解析到新配置）；任何失败/异常 →
    打印 WARN 后返回，lifespan gate 见 COMMITTED 照常进维护分支兜底。
    """
    try:
        if yaml_path is None:
            from app.core.config import settings

            yaml_path = str(settings.YAML_PATH)
        config_dir = str(Path(yaml_path).parent)
        outcome = run_pending_activation_redo(config_dir, yaml_path=yaml_path)
        if outcome == REDO_COMPLETED:
            print("[OK] 启动前激活决议完成：本进程将以新配置建引擎（无漂移、无需托管重启）")
    except Exception as exc:  # noqa: BLE001 - 决议绝不阻塞导入
        print(f"[WARN] 早期启动决议不可用（交 lifespan 分流兜底）: {exc}")
