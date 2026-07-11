"""orphan lifecycle: current candidate + operation lease + notification dedupe_key

语义重做（v1.0.6+）：
1. 新增 orphan_current_candidate 表（当前候选，按「连续成为孤儿的时间」管理生命周期，
   取代把历史 OrphanFile 明细当当前状态的做法）
2. 新增 orphan_operation_lease 表（跨进程 lease，保护扫描/预览/清理互斥）
3. notification 表新增可空唯一 dedupe_key 列（幂等通知去重，如 orphan_scan:{scan_id}）

【可回滚】upgrade 增 2 表 + 1 列 + 索引，downgrade 全部 drop/移除。
回滚说明：新增表/列为纯增量，drop 不影响业务数据（历史 OrphanFile 保留为审计明细）。

Revision ID: b075727f7182
Revises: c3f1a8b7d902
Create Date: 2026-07-11 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b075727f7182"
down_revision: Union[str, Sequence[str], None] = "c3f1a8b7d902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 增 orphan_current_candidate + orphan_operation_lease + notification.dedupe_key.

    使用 inspect 守卫：对已有该表/列的库（异常重跑），upgrade 不报错。
    与 c3f1a8b7d902 orphan_file_tables 迁移风格一致。
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ==================== orphan_current_candidate 表 ====================
    if not insp.has_table("orphan_current_candidate"):
        op.create_table(
            "orphan_current_candidate",
            sa.Column(
                "canonical_path", sa.String(length=600), nullable=False, comment="规范化路径（normcase+normpath）"
            ),
            sa.Column("downloader_id", sa.String(length=36), nullable=False, comment="关联下载器ID"),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False, comment="首次发现时间"),
            sa.Column(
                "last_seen_at", sa.DateTime(), nullable=False, comment="最后一次在完整成功扫描中确认为孤儿的时间"
            ),
            sa.Column("last_seen_scan_id", sa.String(length=36), nullable=True, comment="最后一次确认的扫描批次ID"),
            sa.Column(
                "consecutive_scan_count",
                sa.Integer(),
                nullable=False,
                server_default="1",
                comment="连续确认为孤儿的完整成功扫描次数",
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="candidate",
                comment="状态：candidate/resolved/quarantined/purged",
            ),
            sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0", comment="文件大小（字节）"),
            sa.Column("mtime_ns", sa.BigInteger(), nullable=True, comment="文件修改时间（纳秒）"),
            sa.Column("device_id", sa.BigInteger(), nullable=True, comment="设备ID（st_dev）"),
            sa.Column("inode", sa.BigInteger(), nullable=True, comment="inode（st_ino）"),
            sa.Column("quarantine_path", sa.String(length=600), nullable=True, comment="隔离区路径"),
            sa.Column("quarantined_at", sa.DateTime(), nullable=True, comment="移入隔离区时间"),
            sa.Column(
                "purge_after", sa.DateTime(), nullable=True, comment="允许物理删除时间（quarantined_at + 保留期）"
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.PrimaryKeyConstraint("canonical_path"),
            sa.UniqueConstraint("downloader_id", "canonical_path", name="uq_orphan_candidate_dl_path"),
        )
        op.create_index(
            op.f("ix_orphan_current_candidate_status"),
            "orphan_current_candidate",
            ["status"],
            unique=False,
        )
        op.create_index(
            op.f("ix_orphan_current_candidate_purge_after"),
            "orphan_current_candidate",
            ["purge_after"],
            unique=False,
        )

    # ==================== orphan_operation_lease 表 ====================
    if not insp.has_table("orphan_operation_lease"):
        op.create_table(
            "orphan_operation_lease",
            sa.Column(
                "lease_key", sa.String(length=60), nullable=False, comment="租约键（如 orphan_scan/orphan_cleanup）"
            ),
            sa.Column("owner", sa.String(length=100), nullable=False, comment="持有者标识（进程ID+UUID）"),
            sa.Column("acquired_at", sa.DateTime(), nullable=False, comment="获取时间"),
            sa.Column("expires_at", sa.DateTime(), nullable=False, comment="过期时间"),
            sa.PrimaryKeyConstraint("lease_key"),
        )

    # ==================== notification.dedupe_key 列 + 部分唯一索引 ====================
    existing_columns = {col["name"] for col in insp.get_columns("notification")}
    if "dedupe_key" not in existing_columns:
        op.add_column(
            "notification",
            sa.Column("dedupe_key", sa.String(length=100), nullable=True, comment="去重键（如 orphan_scan:{scan_id}）"),
        )

    existing_indexes = {idx["name"] for idx in insp.get_indexes("notification")}
    if "uq_notification_dedupe_key" not in existing_indexes:
        # SQLite 支持部分唯一索引（WHERE dedupe_key IS NOT NULL），允许多个 NULL 值
        op.create_index(
            "uq_notification_dedupe_key",
            "notification",
            ["dedupe_key"],
            unique=True,
            sqlite_where=sa.text("dedupe_key IS NOT NULL"),
        )


def downgrade() -> None:
    """Downgrade schema: drop orphan_current_candidate + orphan_operation_lease + notification.dedupe_key."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # notification.dedupe_key
    existing_indexes = {idx["name"] for idx in insp.get_indexes("notification")}
    if "uq_notification_dedupe_key" in existing_indexes:
        op.drop_index("uq_notification_dedupe_key", table_name="notification")
    existing_columns = {col["name"] for col in insp.get_columns("notification")}
    if "dedupe_key" in existing_columns:
        op.drop_column("notification", "dedupe_key")

    # orphan_operation_lease
    if insp.has_table("orphan_operation_lease"):
        op.drop_table("orphan_operation_lease")

    # orphan_current_candidate
    if insp.has_table("orphan_current_candidate"):
        op.drop_index(op.f("ix_orphan_current_candidate_purge_after"), table_name="orphan_current_candidate")
        op.drop_index(op.f("ix_orphan_current_candidate_status"), table_name="orphan_current_candidate")
        op.drop_table("orphan_current_candidate")
