"""add task outcome and freshness columns

【可回滚】纯 ADD COLUMN（全部可空，历史行兼容，W3-4 / P1-05）：
- task_logs 增加 outcome / skip_reason：把“调度成功但业务数据没更新”从 success
  布尔中分离（六态：success/partial/skipped/failed/no_action/cancelled）。
- cron_task 增加 last_success_at / last_attempt_at / last_outcome /
  last_skip_reason / last_run_id：任务数据新鲜度与最近结果溯源。
  last_success_at 仅当 outcome ∈ {success, partial, no_action} 时推进，
  skipped/failed/cancelled 不推进（stale 判断依据）。
downgrade 直接删列，不影响既有业务数据。

Revision ID: f5e6d7c8b9a0
Revises: f0e1d2c3b4a5
Create Date: 2026-08-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f5e6d7c8b9a0"
down_revision: Union[str, Sequence[str], None] = "f0e1d2c3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (表名, [(列名, 类型, 注释)]) —— 全部可空，历史行默认 NULL 兼容
_COLUMNS = {
    "task_logs": [
        (
            "outcome",
            sa.String(length=20),
            "业务结果六态：success/partial/skipped/failed/no_action/cancelled（NULL=历史记录无此字段）",
        ),
        (
            "skip_reason",
            sa.String(length=50),
            "跳过原因机器码：resource_busy/already_running/outside_budget/downloader_offline（未跳过错失为 NULL）",
        ),
    ],
    "cron_task": [
        (
            "last_success_at",
            sa.DateTime(),
            "最近一次数据成功时间（success/partial/no_action 更新；skipped/failed/cancelled 不推进）",
        ),
        ("last_attempt_at", sa.DateTime(), "最近一次执行尝试时间（所有执行更新）"),
        ("last_outcome", sa.String(length=20), "最近一次业务结果（六态）"),
        ("last_skip_reason", sa.String(length=50), "最近一次跳过原因机器码"),
        ("last_run_id", sa.String(length=64), "最近一次运行 ID（日志溯源）"),
    ],
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, columns in _COLUMNS.items():
        existing_columns = {col["name"] for col in inspector.get_columns(table)}
        for name, type_, comment in columns:
            if name not in existing_columns:
                op.add_column(table, sa.Column(name, type_, nullable=True, comment=comment))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, columns in _COLUMNS.items():
        existing_columns = {col["name"] for col in inspector.get_columns(table)}
        for name, _, _ in columns:
            if name in existing_columns:
                op.drop_column(table, name)
