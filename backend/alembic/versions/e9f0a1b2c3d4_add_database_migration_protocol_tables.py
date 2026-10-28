"""add_database_migration_protocol_tables

【受限可回滚】数据库迁移 UI 协议元数据三表（database-migration-ui W1-1，
PLANS/database-migration-ui.md §3.2/§3.3）：

- ``bt_database_identity``：库身份单例（id=1 CHECK + 随机 UUID database_id）；
  本 revision 为存量库**生成**身份（幂等：已有行不重生成，database_id 保持稳定）。
- ``bt_database_migration_receipt``：迁移完成凭据（ownership receipt）——
  首表导入前即持久 IMPORTING，finalize 同事务更新 VERIFIED 并清未完成标记；
  origin_epoch 不可变 / eligible_epoch 可撤销。
- ``bt_database_migration_events``：本地审计回放去重行（与正式审计同事务归档）。

downgrade 边界（受限）：receipt/events 存在任何行时**拒绝**降级（禁止静默丢
活跃/未完成凭据，PLANS §12 W1 复核意见 6）；仅"从未发生过迁移"的库（协议表
为空、identity 为 seed 产物）允许 drop——identity 会随再次 upgrade 以新 UUID
重建，引用旧 database_id 的配置将 fail-closed（这是显式后果，非静默行为）。

双方言：DDL 取 SQLite/PG 通用子集（op.create_table + sa.JSON + 命名索引/
CHECK），无 ALTER、无方言专属函数；identity seed 经 sa.table() 类型化绑定
（datetime 绑定为 timestamp，PG 严格类型安全）。

Revision ID: e9f0a1b2c3d4
Revises: c9e0f1a2b3c4
Create Date: 2026-10-28

"""

import uuid
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.database_protocol import (
    EVENTS_TABLE,
    IDENTITY_TABLE,
    PROTOCOL_SCHEMA_VERSION,
    RECEIPT_TABLE,
)


# revision identifiers, used by Alembic.
revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "c9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _identity_insert() -> sa.Table:
    """类型化插入替身（datetime 以 timestamp 绑定，双方言安全）。"""
    return sa.table(
        IDENTITY_TABLE,
        sa.column("id", sa.Integer),
        sa.column("database_id", sa.String(36)),
        sa.column("schema_version", sa.String(16)),
        sa.column("created_at", sa.DateTime),
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table(IDENTITY_TABLE):
        op.create_table(
            IDENTITY_TABLE,
            sa.Column("id", sa.Integer(), autoincrement=False, nullable=False, comment="单例主键，恒为 1"),
            sa.Column(
                "database_id", sa.String(36), nullable=False, comment="库自身随机 UUID（uuid4；导入不可从源复制）"
            ),
            sa.Column("schema_version", sa.String(16), nullable=False, comment="协议表结构版本"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="身份创建时间（UTC）"),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("id = 1", name="ck_bt_database_identity_singleton"),
        )

    if not inspector.has_table(RECEIPT_TABLE):
        op.create_table(
            RECEIPT_TABLE,
            sa.Column(
                "attempt_id",
                sa.String(96),
                nullable=False,
                comment="sqlite-to-pg/<uuid> | pg-to-sqlite/<uuid> | handoff/<uuid>",
            ),
            sa.Column("operation_kind", sa.String(32), nullable=False, comment="MIGRATE | HANDOFF_SAME_DB"),
            sa.Column(
                "source_database_id", sa.String(36), nullable=True, comment="源库 database_id（源无身份时为 NULL）"
            ),
            sa.Column(
                "target_database_id", sa.String(36), nullable=False, comment="目标库 database_id（目标自身身份）"
            ),
            sa.Column(
                "deployment_id",
                sa.String(64),
                nullable=True,
                comment="配置卷部署标识（首次使用管理功能时持久创建；早期可为 NULL）",
            ),
            sa.Column(
                "ownership_nonce", sa.String(64), nullable=False, comment="随机 ownership nonce（清理/切换授权核对）"
            ),
            sa.Column("revision_at_import", sa.String(64), nullable=False, comment="导入时迁移链 revision"),
            sa.Column("digest_version", sa.String(32), nullable=False, comment="内容摘要算法版本"),
            sa.Column(
                "table_counts", sa.JSON(), nullable=True, comment="全业务表行数清单 {表名: 行数}（verify 通过后写入）"
            ),
            sa.Column(
                "table_digests",
                sa.JSON(),
                nullable=True,
                comment="全业务表内容摘要清单 {表名: sha256}（verify 通过后写入）",
            ),
            sa.Column("schema_fingerprint", sa.String(128), nullable=False, comment="schema 指纹（表/列清单排序摘要）"),
            sa.Column("origin_epoch", sa.String(64), nullable=False, comment="创建本次导入的冻结代次（不可变）"),
            sa.Column(
                "eligible_epoch", sa.String(64), nullable=False, comment="当前切换资格代次（可撤销；重绑协议 CAS 目标）"
            ),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                comment="IMPORTING | VERIFIED | ACTIVATED | STALE | ABANDONED",
            ),
            sa.Column(
                "activation_generation",
                sa.String(64),
                nullable=True,
                comment="激活时的配置 generation（ACTIVATED 后写入）",
            ),
            sa.Column("activated_at", sa.DateTime(), nullable=True, comment="首次激活时间（UTC）"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="receipt 创建时间（UTC）"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="最近更新时间（UTC）"),
            sa.PrimaryKeyConstraint("attempt_id"),
        )

    if not inspector.has_table(EVENTS_TABLE):
        op.create_table(
            EVENTS_TABLE,
            sa.Column("event_id", sa.String(64), nullable=False, comment="事件唯一 ID（uuid4）"),
            sa.Column(
                "attempt_id",
                sa.String(96),
                nullable=False,
                comment="所属 attempt（逻辑引用 receipt.attempt_id）",
            ),
            sa.Column("seq", sa.Integer(), nullable=False, comment="attempt 内单调序号"),
            sa.Column("summary", sa.String(512), nullable=False, comment="事件摘要（脱敏）"),
            sa.Column("archived_at", sa.DateTime(), nullable=True, comment="归档到正式审计日志的时间；NULL=未归档"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="事件时间（UTC）"),
            sa.PrimaryKeyConstraint("event_id"),
        )
        op.create_index(
            op.f("ix_bt_database_migration_events_attempt_id"),
            EVENTS_TABLE,
            ["attempt_id"],
            unique=False,
        )

    # 存量库身份 seed（幂等）：已有行不重生成——database_id 一经生成保持稳定
    bind = op.get_bind()
    existing = bind.execute(sa.text(f"SELECT COUNT(*) FROM {IDENTITY_TABLE}")).scalar()
    if not existing:
        bind.execute(
            _identity_insert()
            .insert()
            .values(
                id=1,
                database_id=str(uuid.uuid4()),
                schema_version=PROTOCOL_SCHEMA_VERSION,
                created_at=datetime.utcnow(),
            )
        )


def downgrade() -> None:
    """受限降级：存在任何 receipt/event 行即拒绝（禁止静默丢活跃/未完成凭据）。"""
    bind = op.get_bind()
    receipts = bind.execute(sa.text(f"SELECT COUNT(*) FROM {RECEIPT_TABLE}")).scalar()
    events = bind.execute(sa.text(f"SELECT COUNT(*) FROM {EVENTS_TABLE}")).scalar()
    if receipts or events:
        raise RuntimeError(
            f"bt_database_migration_receipt/events 存在 {receipts + events} 行迁移凭据/事件，"
            "拒绝降级丢弃（活跃/未完成/历史凭据均不可静默删除；如确需清理请先走显式 ABANDONED 流程）"
        )
    op.drop_index(op.f("ix_bt_database_migration_events_attempt_id"), table_name=EVENTS_TABLE)
    op.drop_table(EVENTS_TABLE)
    op.drop_table(RECEIPT_TABLE)
    op.drop_table(IDENTITY_TABLE)
