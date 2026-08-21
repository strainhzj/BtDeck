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
    # inspect 守卫：版本回拨重放（如 db_governance 测试 stamp 回拨后重新
    # upgrade）时列已存在，直接跳过保持幂等（对齐 ab68fe061d5b 守卫风格）。
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {str(column["name"]) for column in inspector.get_columns("torrent_info")}
    if "auxiliary_seed_count" in existing:
        return
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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {str(column["name"]) for column in inspector.get_columns("torrent_info")}
    if "auxiliary_seed_count" not in existing:
        return
    with op.batch_alter_table("torrent_info", recreate="always") as batch_op:
        batch_op.drop_column("auxiliary_seed_count")
