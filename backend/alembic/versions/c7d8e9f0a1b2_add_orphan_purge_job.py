"""add orphan purge job

【可回滚】纯新增任务表与索引，downgrade 删除该表不会影响孤儿候选和文件数据。

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "orphan_purge_job"
_INDEX_STATUS = "ix_orphan_purge_job_status"
_INDEX_CREATED_AT = "ix_orphan_purge_job_created_at"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("task_id", sa.String(length=36), nullable=False, comment="任务 UUID"),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                comment="pending/running/completed/partial/failed",
            ),
            sa.Column("canonical_paths_json", sa.Text(), nullable=False, comment="待删除规范化路径 JSON 数组"),
            sa.Column("operator", sa.String(length=100), nullable=False, comment="任务提交人"),
            sa.Column("total_count", sa.Integer(), nullable=False, server_default="0", comment="待处理数量"),
            sa.Column("purged_count", sa.Integer(), nullable=False, server_default="0", comment="成功删除数量"),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0", comment="失败数量"),
            sa.Column("failed_list_json", sa.Text(), nullable=True, comment="失败项 JSON 数组"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="任务级异常"),
            sa.Column(
                "notification_sent_at",
                sa.DateTime(),
                nullable=True,
                comment="结果通知成功写入时间",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("started_at", sa.DateTime(), nullable=True, comment="首次开始时间"),
            sa.Column("completed_at", sa.DateTime(), nullable=True, comment="完成时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.PrimaryKeyConstraint("task_id"),
        )

    existing_indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(_TABLE)}
    if _INDEX_STATUS not in existing_indexes:
        op.create_index(_INDEX_STATUS, _TABLE, ["status"], unique=False)
    if _INDEX_CREATED_AT not in existing_indexes:
        op.create_index(_INDEX_CREATED_AT, _TABLE, ["created_at"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing_indexes = {item["name"] for item in inspector.get_indexes(_TABLE)}
    if _INDEX_CREATED_AT in existing_indexes:
        op.drop_index(_INDEX_CREATED_AT, table_name=_TABLE)
    if _INDEX_STATUS in existing_indexes:
        op.drop_index(_INDEX_STATUS, table_name=_TABLE)
    op.drop_table(_TABLE)
