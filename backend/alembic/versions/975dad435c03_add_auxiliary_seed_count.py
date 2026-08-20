"""【可回滚】add auxiliary seed count

Revision ID: 975dad435c03
Revises: ab68fe061d5b
Create Date: 2026-08-20 16:23:25.194208

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "975dad435c03"
down_revision: Union[str, Sequence[str], None] = "ab68fe061d5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增辅种数量字段；历史数据先以 1 作为安全默认值。"""
    op.add_column(
        "torrent_info",
        sa.Column(
            "auxiliary_seed_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="辅种数量",
        ),
    )


def downgrade() -> None:
    """回滚辅种数量字段。"""
    op.drop_column("torrent_info", "auxiliary_seed_count")
