"""orphan_purge_job submit-time ip address column

【可回滚】给 ``orphan_purge_job`` 新增 ``ip_address``（nullable String(64)）。
孤儿文件主动清理 / 隔离区彻底删除为后台异步任务（execute_job 独立会话执行），
审计日志在后台写入时已无 HTTP 请求上下文，需在任务提交时把提交端 IP 持久化
到 job 行、后台执行时透传给 ``cleanup_orphans`` / ``purge_quarantine_now`` 的
审计调用。纯加列无数据回填，历史任务行保持 NULL（显示为空）。

Revision ID: ab68fe061d5b
Revises: ff42d3402df5
Create Date: 2026-08-16 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ab68fe061d5b"
down_revision: Union[str, Sequence[str], None] = "ff42d3402df5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    job_columns = {str(column["name"]) for column in inspector.get_columns("orphan_purge_job")}
    if "ip_address" not in job_columns:
        op.add_column(
            "orphan_purge_job",
            sa.Column("ip_address", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    job_columns = {str(column["name"]) for column in inspector.get_columns("orphan_purge_job")}
    if "ip_address" in job_columns:
        with op.batch_alter_table("orphan_purge_job", recreate="always") as batch_op:
            batch_op.drop_column("ip_address")
