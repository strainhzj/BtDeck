"""users.must_change_password 强制改密标志列（安全修复 W8/W9）

【可回滚】加列（带 server_default '0'），downgrade 直接删列。
注：autogenerate 产生的孤儿硬链接表/索引漂移操作与本次变更无关，
已手工剔除——该漂移属存量治理项，不在本迁移处理。

Revision ID: ff42d3402df5
Revises: a8b9c0d1e2f3
Create Date: 2026-08-16 21:22:11.455960

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ff42d3402df5"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """users 加 must_change_password 列（布尔，默认 0）。

    幂等保护：stamp 回退后重放（测试/救援场景）时列已存在，检查后跳过，
    避免 SQLite duplicate column 报错。
    """
    bind = op.get_bind()
    columns = [c["name"] for c in sa.inspect(bind).get_columns("users")]
    if "must_change_password" not in columns:
        op.add_column("users", sa.Column("must_change_password", sa.Boolean(), server_default="0", nullable=False))


def downgrade() -> None:
    """删除 must_change_password 列（幂等：列不存在时跳过）。"""
    bind = op.get_bind()
    columns = [c["name"] for c in sa.inspect(bind).get_columns("users")]
    if "must_change_password" in columns:
        op.drop_column("users", "must_change_password")
