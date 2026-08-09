"""orphan purge hardlink notes

【可回滚】为 orphan_purge_job 增加 hardlink_notes_json 列，承载"成功删除但存在
其它硬链接副本"的诊断信息（路径 + is_seed）。纯 ADD COLUMN，downgrade 直接删列，
不影响既有业务数据。

Revision ID: f9a1b2c3d4e5
Revises: 3a4b5c6d7e8f
Create Date: 2026-08-09 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f9a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "3a4b5c6d7e8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "orphan_purge_job"
_COLUMN = "hardlink_notes_json"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Text(),
                nullable=True,
                comment="成功删除但存在其它硬链接副本的诊断 JSON 数组（路径+is_seed）",
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_columns:
        op.drop_column(_TABLE, _COLUMN)
