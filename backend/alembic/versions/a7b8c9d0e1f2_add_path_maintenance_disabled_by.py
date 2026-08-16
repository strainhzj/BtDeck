"""downloader_path_maintenance disabled_by 来源字段

【可回滚】给 ``downloader_path_maintenance`` 新增 ``disabled_by`` 列，区分禁用来源：
- NULL：从未禁用（或已被重新启用）
- 'auto'：路径扫描清理自动禁用（种子回归后由 ``_sync_active_path`` 自动恢复）
- 'user'：用户通过路径管理手动禁用（扫描永不恢复，防止每小时任务推翻用户意图）

存量数据处理（保守策略，不推翻任何现存禁用状态）：
1. ``is_enabled=0`` 的记录统一标 'user' —— 历史自动禁用的路径保持禁用，
   由用户手动启用一次后进入新语义（后续自动禁用标 'auto' 可自愈）。
2. 当前仍有种子（``torrent_info`` 中 dr=0 且 save_path 匹配）的路径记录把
   ``last_updated_time`` 刷新为 now，避免宽限期（PATH_CLEANUP_GRACE_DAYS）
   上线后首轮扫描把存量老记录批量禁用。

Revision ID: a7b8c9d0e1f2
Revises: d4e5f6a7b8c9
Create Date: 2026-08-16 15:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {str(column["name"]) for column in inspector.get_columns("downloader_path_maintenance")}
    if "disabled_by" not in columns:
        op.add_column(
            "downloader_path_maintenance",
            sa.Column("disabled_by", sa.String(10), nullable=True, comment="禁用来源：auto=扫描自动，user=用户手动"),
        )

    # 存量禁用记录保守标 'user'（幂等：只补 NULL 的禁用记录）
    bind.execute(
        sa.text(
            "UPDATE downloader_path_maintenance SET disabled_by = 'user' "
            "WHERE is_enabled = 0 AND disabled_by IS NULL"
        )
    )

    # 当前启用且无最后更新时间的路径补 now（宽限期 coalesce 兜底；幂等）
    bind.execute(
        sa.text(
            "UPDATE downloader_path_maintenance SET last_updated_time = datetime('now') "
            "WHERE is_enabled = 1 AND last_updated_time IS NULL"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {str(column["name"]) for column in inspector.get_columns("downloader_path_maintenance")}
    if "disabled_by" in columns:
        with op.batch_alter_table("downloader_path_maintenance", recreate="always") as batch_op:
            batch_op.drop_column("disabled_by")
