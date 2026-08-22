"""orphan purge delay count

【可回滚】为 orphan_current_candidate 增加 purge_delay_count 列，记录"到期删除
遇硬链接副本跳过时 purge_after 延后"的次数（每次进入隔离态由业务侧重置为 0）。
纯 ADD COLUMN（NOT NULL + server_default=0 满足 SQLite 约束），downgrade 直接
删列，不影响既有业务数据。

Revision ID: f0e1d2c3b4a5
Revises: f9a1b2c3d4e5
Create Date: 2026-08-09 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f0e1d2c3b4a5"
down_revision: Union[str, Sequence[str], None] = "f9a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "orphan_current_candidate"
_COLUMN = "purge_delay_count"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment="硬链接副本跳过导致 purge_after 延后的次数（每次进入隔离态重置）",
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_columns:
        op.drop_column(_TABLE, _COLUMN)
