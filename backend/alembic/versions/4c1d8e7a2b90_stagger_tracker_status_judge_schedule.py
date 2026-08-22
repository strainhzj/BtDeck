"""stagger tracker status judge schedule

【受限回滚】将系统内置的种子 Tracker 状态判断任务从已知旧计划
``0 */5 * * *`` 调整为 ``20,50 * * * *``，使其在 Tracker 状态同步任务
（``10,40 * * * *``）之后 10 分钟独立运行。仅 task_code、未删除标记、旧计划
和系统旧描述全部命中的记录会被迁移，其它自定义 Cron/描述不受影响；downgrade
也仅恢复仍保持新计划与系统新描述的记录，不恢复升级前的 ``update_time``。

Revision ID: 4c1d8e7a2b90
Revises: de898cb28172
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "4c1d8e7a2b90"
down_revision: Union[str, Sequence[str], None] = "de898cb28172"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TASK_CODE = "TORRENT_TRACKER_STATUS_JUDGE"
_OLD_CRON = "0 */5 * * *"
_NEW_CRON = "20,50 * * * *"
_OLD_DESCRIPTION = (
    "定期检查所有种子的tracker状态，根据关键词池（失败池、成功池、忽略池）"
    "智能判断tracker是否失败，自动更新has_tracker_error字段"
    "（间隔: 5分钟，批量处理20,000+种子）"
)
_NEW_DESCRIPTION = (
    "定期检查所有种子的tracker状态，根据状态码与关键词池（失败池、成功池、忽略池）"
    "共同判断tracker是否失败，自动更新has_tracker_error字段"
    "（每30分钟，在Tracker状态同步任务后10分钟执行，批量处理20,000+种子）"
)


def _has_cron_task_table(bind: sa.engine.Connection) -> bool:
    return sa.inspect(bind).has_table("cron_task")


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_cron_task_table(bind):
        return

    bind.execute(
        sa.text("""
            UPDATE cron_task
               SET cron_plan = :new_cron,
                   description = :new_description,
                   update_time = CURRENT_TIMESTAMP
             WHERE task_code = :task_code
               AND dr = 0
               AND cron_plan = :old_cron
               AND description = :old_description
            """),
        {
            "task_code": _TASK_CODE,
            "old_cron": _OLD_CRON,
            "new_cron": _NEW_CRON,
            "old_description": _OLD_DESCRIPTION,
            "new_description": _NEW_DESCRIPTION,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_cron_task_table(bind):
        return

    bind.execute(
        sa.text("""
            UPDATE cron_task
               SET cron_plan = :old_cron,
                   description = :old_description,
                   update_time = CURRENT_TIMESTAMP
             WHERE task_code = :task_code
               AND dr = 0
               AND cron_plan = :new_cron
               AND description = :new_description
            """),
        {
            "task_code": _TASK_CODE,
            "old_cron": _OLD_CRON,
            "new_cron": _NEW_CRON,
            "old_description": _OLD_DESCRIPTION,
            "new_description": _NEW_DESCRIPTION,
        },
    )
