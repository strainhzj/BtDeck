# -*- coding: utf-8 -*-
"""数据库迁移协议常量（database-migration-ui W1-1）。

⚠️ 本模块必须保持**纯标准库**：不得 import app.* 下任何模块（尤其
``app.database`` / ``app.core.config``——它们在模块加载期创建引擎/加载
settings）。早期只读引导（``app.core.database_bootstrap``）、维护恢复与
CLI 需要在引擎可用之前消费这些常量做平台分流与状态判定。

与 ORM 模型（``app.models.database_migration``）的关系：模型模块 import
本模块取表名与状态常量，保证单一事实源；对拍门禁
（tests/core/test_database_migration_protocol.py）校验两侧一致。

契约来源：PLANS/database-migration-ui.md §3（身份、schema 与业务数据范围）。
"""

from __future__ import annotations

import re

# =============================================================================
# 协议元数据表（受 Alembic 管理的三张表；不参与业务数据导入/摘要）
# =============================================================================

IDENTITY_TABLE = "bt_database_identity"
RECEIPT_TABLE = "bt_database_migration_receipt"
EVENTS_TABLE = "bt_database_migration_events"

PROTOCOL_TABLE_NAMES: frozenset[str] = frozenset({IDENTITY_TABLE, RECEIPT_TABLE, EVENTS_TABLE})

# =============================================================================
# 身份/协议版本
# =============================================================================

# bt_database_identity.schema_version：协议表结构版本（表结构变化时递增）
PROTOCOL_SCHEMA_VERSION = "1"

# bt_database_migration_receipt.digest_version：行内容摘要算法版本
# （btdeck-canonical-v1：全列类型归一、JSON SQL NULL 与 JSON null 区分、
# UTC 时间、字符串 PK 固定 C 排序；见 services/db_migration/canonical.py）
DIGEST_VERSION_CANONICAL_V1 = "btdeck-canonical-v1"

# =============================================================================
# receipt 状态机（IMPORTING → VERIFIED → ACTIVATED；STALE/ABANDONED 为失效态）
# =============================================================================

RECEIPT_STATUS_IMPORTING = "IMPORTING"
RECEIPT_STATUS_VERIFIED = "VERIFIED"
RECEIPT_STATUS_ACTIVATED = "ACTIVATED"
RECEIPT_STATUS_STALE = "STALE"
RECEIPT_STATUS_ABANDONED = "ABANDONED"

RECEIPT_STATUSES: frozenset[str] = frozenset(
    {
        RECEIPT_STATUS_IMPORTING,
        RECEIPT_STATUS_VERIFIED,
        RECEIPT_STATUS_ACTIVATED,
        RECEIPT_STATUS_STALE,
        RECEIPT_STATUS_ABANDONED,
    }
)

# 活跃/未完成状态：存在即阻止协议表 downgrade（禁止静默丢活跃 receipt）
RECEIPT_ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        RECEIPT_STATUS_IMPORTING,
        RECEIPT_STATUS_VERIFIED,
        RECEIPT_STATUS_ACTIVATED,
    }
)

# =============================================================================
# 操作类型与 attempt 前缀（§3.1 标识不变量）
# =============================================================================

OPERATION_MIGRATE = "MIGRATE"
OPERATION_HANDOFF_SAME_DB = "HANDOFF_SAME_DB"

OPERATION_KINDS: frozenset[str] = frozenset({OPERATION_MIGRATE, OPERATION_HANDOFF_SAME_DB})

ATTEMPT_PREFIX_SQLITE_TO_PG = "sqlite-to-pg/"
ATTEMPT_PREFIX_PG_TO_SQLITE = "pg-to-sqlite/"
ATTEMPT_PREFIX_HANDOFF = "handoff/"

# 既有临时导入标记表（v1.0.8 P4 起存在；保留为兼容边界，§3.2）。
# 会随 finalize 被 DROP——所以完成凭据另存 receipt，不再只靠它
IMPORT_MARKER_TABLE = "_btdeck_import_state"

# 受管协议文件布局（§4.2：不是新的可选连接配置源）
DB_MIGRATION_DIR = "db-migration"
CONTROL_FILE = "control.json"
ATTEMPTS_DIRNAME = "attempts"
MANIFEST_FILENAME = "manifest.json"

# attempt_id 形如 "<prefix><uuid>"，禁止携带 "/" 之外的路径分隔符
_ATTEMPT_RE = re.compile(r"^(sqlite-to-pg|pg-to-sqlite|handoff)/[0-9a-fA-F-]{36}$")


def is_valid_attempt_id(attempt_id: str) -> bool:
    """校验 attempt_id 形态（前缀 + UUID4）；用于路径/目录映射前的防穿越检查。"""
    return bool(_ATTEMPT_RE.fullmatch(attempt_id))


def is_protocol_table(table_name: str) -> bool:
    """判定表名是否属于协议元数据表（业务导入/摘要/计数范围排除之）。

    注意：这不是"忽略所有 ``_btdeck_*``"——未知对象（不在业务 metadata、
    也不是协议表/alembic_version/导入标记）在预检与基线判定中仍然拒绝
    （PLANS §3.2）。
    """
    return table_name in PROTOCOL_TABLE_NAMES
