"""add torrent error reason

【可回滚】为 torrent_info 增加可空的 error_reason 文本列，历史记录保持
NULL；downgrade 直接删除该列，不影响其它表或索引。

Revision ID: de898cb28172
Revises: f5e6d7c8b9a0
Create Date: 2026-08-11 22:49:43.969165

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "de898cb28172"
down_revision: Union[str, Sequence[str], None] = "f5e6d7c8b9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {col["name"] for col in inspector.get_columns("torrent_info")}
    if "error_reason" not in existing_columns:
        op.add_column(
            "torrent_info",
            sa.Column(
                "error_reason",
                sa.Text(),
                nullable=True,
                comment="下载器返回的种子错误原因",
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {col["name"] for col in inspector.get_columns("torrent_info")}
    if "error_reason" in existing_columns:
        op.drop_column("torrent_info", "error_reason")
