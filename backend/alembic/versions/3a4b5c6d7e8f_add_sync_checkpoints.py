"""add sync checkpoints

【可回滚】纯新增表与索引（W3-2，PLANS/sync-database-blocking-remediation.md）：
sync_checkpoints 按 (downloader_id, sync_type) 持久化同步进度，供中断/重启
后从最后 durable checkpoint 续跑（P1-03）。downgrade 删除该表不影响既有
业务数据；唯一约束与查询索引随表一并回退。

Revision ID: 3a4b5c6d7e8f
Revises: d8e9f0a1b2c3
Create Date: 2026-08-09 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "3a4b5c6d7e8f"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "sync_checkpoints"
_UNIQUE_NAME = "uq_sync_checkpoints_downloader_sync_type"
_INDEX_DOWNLOADER = "ix_sync_checkpoints_downloader_id"
_INDEX_SYNC_TYPE = "ix_sync_checkpoints_sync_type"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="主键"),
            sa.Column("downloader_id", sa.String(length=100), nullable=False, comment="下载器标识"),
            sa.Column("sync_type", sa.String(length=20), nullable=False, comment="同步类型：info/tracker/full"),
            sa.Column("cursor_value", sa.Text(), nullable=True, comment="透明游标字符串/JSON 文本（W3-1 起真正使用）"),
            sa.Column("cycle_started_at", sa.DateTime(), nullable=False, comment="当前周期开始时间"),
            sa.Column("last_full_sync_at", sa.DateTime(), nullable=True, comment="最近完整覆盖时间"),
            sa.Column("last_success_at", sa.DateTime(), nullable=True, comment="最近成功提交时间"),
            sa.Column("last_attempt_at", sa.DateTime(), nullable=False, comment="最近尝试时间"),
            sa.Column(
                "outcome",
                sa.String(length=20),
                nullable=True,
                comment="success/partial/skipped/failed/no_action/cancelled（None=尚无完成记录）",
            ),
            sa.Column("detail_json", sa.Text(), nullable=True, comment="聚合统计 JSON（白名单 key，不含敏感数据）"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="0", comment="乐观锁版本"),
            sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.UniqueConstraint("downloader_id", "sync_type", name=_UNIQUE_NAME),
        )

    existing_indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(_TABLE)}
    if _INDEX_DOWNLOADER not in existing_indexes:
        op.create_index(_INDEX_DOWNLOADER, _TABLE, ["downloader_id"], unique=False)
    if _INDEX_SYNC_TYPE not in existing_indexes:
        op.create_index(_INDEX_SYNC_TYPE, _TABLE, ["sync_type"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    existing_indexes = {item["name"] for item in inspector.get_indexes(_TABLE)}
    for index_name in (_INDEX_DOWNLOADER, _INDEX_SYNC_TYPE):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=_TABLE)
    op.drop_table(_TABLE)
