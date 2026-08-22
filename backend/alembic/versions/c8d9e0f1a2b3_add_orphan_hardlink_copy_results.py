"""add orphan hardlink copy results

【可回滚】新增 ``orphan_hardlink_copy_result``（按 ``(device_id, inode_id)``
唯一存储定时任务预扫描的副本路径）与单行 keyset 游标表
``orphan_hardlink_scan_state``。downgrade 直接删表，无数据迁移。

Revision ID: c8d9e0f1a2b3
Revises: b6e1c4d9a2f7
Create Date: 2026-08-15 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b6e1c4d9a2f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("orphan_hardlink_copy_result"):
        op.create_table(
            "orphan_hardlink_copy_result",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("device_id", sa.String(length=32), nullable=False),
            sa.Column("inode_id", sa.Integer(), nullable=False),
            sa.Column("copy_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("found_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("copies_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("truncated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("scan_note", sa.String(length=200), nullable=True),
            sa.Column("scanned_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("device_id", "inode_id", name="uq_orphan_hardlink_identity"),
        )
        op.create_index(
            "ix_orphan_hardlink_copy_result_scanned_at",
            "orphan_hardlink_copy_result",
            ["scanned_at"],
        )
    if not sa.inspect(bind).has_table("orphan_hardlink_scan_state"):
        op.create_table(
            "orphan_hardlink_scan_state",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("last_detail_id", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("orphan_hardlink_scan_state"):
        op.drop_table("orphan_hardlink_scan_state")
    if sa.inspect(bind).has_table("orphan_hardlink_copy_result"):
        op.drop_index("ix_orphan_hardlink_copy_result_scanned_at", table_name="orphan_hardlink_copy_result")
        op.drop_table("orphan_hardlink_copy_result")
