"""A 轨同库交接（database-migration-ui W3-7，PLANS §7.3；T10）。

clear = **受控交接到 env**，不是直接删记录：
- 常规 clear 仅允许 env 指向**同一当前服务库**（把 B 管理交还 A）；
- 异库目标拒绝（引导新迁移；历史旧库灾难回退走明确离线流程，不伪装 clear）；
- 交接创建独立 ``HANDOFF_SAME_DB`` attempt：维护态下核 env 候选与当前身份，
  二次确认；**不复用异库导入条件**（不核历史导入内容摘要/旧导入 revision），
  因此业务变化与合法升级后仍可交接；
- 旧进程：排空+持源 fence 后仅操作本地候选/manifest/control，**不修改同库
  receipt**（manifest 钉住既有 ACTIVATED receipt 的 attempt 与旧 generation）；
- 新进程：部署单实例锁+普通准入关闭，核当前库与既有 receipt；**单连接**
  fence/ACK 事务完成"核旧 generation → CAS 新 generation → 提交"
  （SQLite 同一 BEGIN IMMEDIATE 连接；PG 同连接所持锁内——禁跨连接自锁）。
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional

from app.core import database_bootstrap as bootstrap
from app.services.db_migration.journal import Journal, make_manifest_payload
from app.services.db_migration.pipeline import DIGEST_VERSION_CANONICAL_V1, TOOL_VERSION

__all__ = ["HandoffError", "plan_handoff_same_db", "handoff_same_db_ack_sqlite"]


class HandoffError(RuntimeError):
    """同库交接拒绝（异库/身份不符/状态不符）。"""


def _current_effective(config_path: str) -> bootstrap.EffectiveDatabaseConfig:
    return bootstrap.resolve_effective_database_config(config_path)


def plan_handoff_same_db(config_dir: str, confirm_attempt: Optional[str] = None) -> Dict[str, Any]:
    """生成同库交接计划（端点数据源；不执行任何写）。

    校验：
    - 当前存在受管 active（B 管理）——无 active 无需交接（引导新迁移）；
    - env 候选（若已提供 DB_TYPE/DATABASE_PATH/PG env）必须解析为**同一库**
      （同 dialect；SQLite 同绝对路径/同 inode；PG 同 host:port/database）；
      env 未提供候选时返回"待填期望配置"步骤（§7.3：用户页面填非密码字段）；
    - 既有 receipt 指向当前库（receipt_attempt_id 与 active 一致）。
    """
    from app.core.config import settings

    config_path = str(settings.YAML_PATH)
    effective = _current_effective(config_path)
    if effective.source != "active":
        raise HandoffError("当前无受管 active（无需 clear 交接；如需更换数据库请发起新迁移）")
    journal = Journal(config_dir)
    control = journal.read_control() or {}
    # env 候选核验（同库三态：match | mismatch | unspecified）
    env_candidate = _env_candidate_state(effective)
    if env_candidate["state"] == "mismatch":
        raise HandoffError(
            f"env 候选指向不同数据库（{env_candidate['detail']}）；clear 仅允许同库交接，"
            "异库请发起新迁移或走离线恢复"
        )
    handoff_attempt = f"handoff/{uuid.uuid4()}"
    plan = {
        "kind": "HANDOFF_SAME_DB",
        "handoffAttemptId": handoff_attempt,
        "currentActive": effective.masked_summary(),
        "pinnedReceiptAttempt": effective.receipt_attempt_id,
        "pinnedGeneration": control.get("generation"),
        "envCandidate": env_candidate,
        "steps": [
            "1. 用户在宿主环境将 A 的 env 指向同一当前服务库（页面生成专属步骤）",
            "2. 二次确认后创建 HANDOFF_SAME_DB attempt（维护态；无导入/无 staging）",
            "3. 旧进程排空+持 fence，仅持久本地候选/manifest/control（不动同库 receipt）",
            "4. 重启后新进程单连接核旧 generation → CAS 新 generation → 提交 ACK",
            "5. 本地 ACTIVATED_ACK 持久后释放业务准入（B 管理交还 A）",
        ],
        "confirmToken": f"handoff:{handoff_attempt}:{(effective.expected_database_id or '')[:8]}",
    }
    return plan


def _env_candidate_state(effective: bootstrap.EffectiveDatabaseConfig) -> Dict[str, Any]:
    """env 候选三态：unspecified（待填）/ match / mismatch（含细节）。"""
    environ = os.environ
    db_type = (environ.get("DB_TYPE") or "").strip().lower()
    if not db_type:
        return {"state": "unspecified", "detail": "宿主 env 未声明 DB_TYPE（待用户填写期望配置）"}
    env_dialect = "postgresql" if db_type in ("postgres", "pg") else db_type
    if env_dialect != effective.dialect:
        return {"state": "mismatch", "detail": f"env 方言 {env_dialect} ≠ active {effective.dialect}"}
    if env_dialect == "sqlite":
        env_path = environ.get("DATABASE_PATH", "")
        if env_path and effective.sqlite_path and os.path.exists(env_path) and os.path.exists(effective.sqlite_path):
            if os.path.samefile(env_path, effective.sqlite_path):
                return {"state": "match", "detail": f"同库文件 {effective.sqlite_path}"}
            return {"state": "mismatch", "detail": f"env 路径 {env_path} 与 active {effective.sqlite_path} 非 samefile"}
        if env_path == effective.sqlite_path:
            return {"state": "match", "detail": "路径一致"}
        return {"state": "mismatch", "detail": f"env DATABASE_PATH={env_path!r} ≠ active {effective.sqlite_path!r}"}
    env_key = (
        f"{environ.get('DB_HOST', 'localhost')}:{environ.get('DB_PORT', '5432')}/{environ.get('DB_NAME', 'btdeck')}"
    )
    pg = effective.pg
    active_key = f"{pg.host}:{pg.port}/{pg.database}" if pg else "?"
    if env_key == active_key:
        return {"state": "match", "detail": env_key}
    return {"state": "mismatch", "detail": f"env {env_key} ≠ active {active_key}"}


def make_handoff_manifest(
    config_dir: str, handoff_attempt: str, *, effective: bootstrap.EffectiveDatabaseConfig
) -> Dict[str, Any]:
    """HANDOFF_SAME_DB attempt 的 manifest（§7.3：钉住既有 receipt/旧 generation）。"""
    journal = Journal(config_dir)
    control = journal.read_control() or {}
    return make_manifest_payload(
        attempt_id=handoff_attempt,
        direction="handoff-same-db",
        operation_kind="HANDOFF_SAME_DB",
        epoch=f"epoch-{uuid.uuid4().hex[:16]}",
        source={"dialect": effective.dialect, "database_id": effective.expected_database_id},
        target={"dialect": effective.dialect, "database_id": effective.expected_database_id},
        tool_version=TOOL_VERSION,
        digest_version=DIGEST_VERSION_CANONICAL_V1,
        objects=[],
        source_snapshot={
            "pinned_receipt_attempt": effective.receipt_attempt_id,
            "pinned_generation": control.get("generation"),
        },
    )


def handoff_same_db_ack_sqlite(
    db_path: str,
    *,
    expected_old_generation: str,
    new_generation: str,
) -> bool:
    """单连接 fence/ACK（SQLite）：同一 BEGIN IMMEDIATE 连接核旧→CAS 新→提交。

    目标列 = ``bt_database_migration_receipts.activation_generation``（既有
    ACTIVATED receipt 的代次，§3.3）；核旧不符/表缺失 → False（保持维护，
    不跨连接等待自己持有的写锁）。幂等：已是新代次直接成功。
    """
    import sqlite3

    conn = sqlite3.connect(db_path, isolation_level=None, timeout=15)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if not sqlite_has_table(conn, "bt_database_migration_receipts"):
            conn.execute("ROLLBACK")
            return False
        row = conn.execute(
            "SELECT activation_generation FROM bt_database_migration_receipts " "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return False
        if row[0] == new_generation:  # 幂等补齐（重启重放）
            conn.execute("COMMIT")
            return True
        if row[0] != expected_old_generation:
            conn.execute("ROLLBACK")
            return False
        conn.execute(
            "UPDATE bt_database_migration_receipts SET activation_generation = ? " "WHERE activation_generation = ?",
            (new_generation, expected_old_generation),
        )
        conn.execute("COMMIT")
        return True
    finally:
        conn.close()


def sqlite_has_table(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None
