"""按稳定 task_code 触发内置定时任务（协议无关入口）。

PLANS/mcp-service-capabilities.md §4.7/§10.1-5 的服务层前置：
HTTP 手动触发按 task_id；MCP 侧（未来）要求稳定 task_code + 内置白名单 +
类型策略前检。本模块净新增，不改变现有 HTTP 触发路径。

安全口径：
- 仅允许 ``task_code`` 出现在内置注册表（``default_scheduled_tasks``）中的任务；
- ``task_type`` 0-3（Shell/CMD/PowerShell/Python 脚本）永不开放，即便
  ``BTDECK_ALLOW_CUSTOM_SCRIPTS=True``（类型不作为放行依据，白名单才是）；
- enabled/运行中前检由 ``start_task_immediately`` 既有逻辑承担，本层只透传拒绝原因；
- 返回 ``accepted`` 语义（异步触发，不伪报完成）；run_id 由 ``_execute_task``
  在执行期写入 ``CronTask.last_run_id``，触发时点不可同步取得，调用方需事后读取。
"""

import logging
from typing import Any, Dict

from app.data.default_scheduled_tasks import get_task_by_code
from app.database import SessionLocal
from app.tasks.cron_crud import CronTaskCRUD
from app.tasks.cron_executor import cron_executor

logger = logging.getLogger(__name__)

# 内置非脚本任务类型：4=Python内部类、5=清理回收站、6=审计日志导出。
# 脚本类型 0-3 一律拒绝（见模块 docstring 安全口径）。
_ALLOWED_TASK_TYPES = (4, 5, 6)

REASON_TASK_NOT_FOUND = "TASK_NOT_FOUND"
REASON_TASK_TYPE_NOT_ALLOWED = "TASK_TYPE_NOT_ALLOWED"
REASON_TASK_NOT_BUILTIN = "TASK_NOT_BUILTIN"
REASON_TRIGGER_REJECTED = "TRIGGER_REJECTED"
REASON_TRIGGER_ERROR = "TRIGGER_ERROR"


def _reject(task_code: str, reason: str, message: str) -> Dict[str, Any]:
    return {
        "accepted": False,
        "task_id": None,
        "task_code": task_code,
        "task_name": None,
        "reason": reason,
        "message": message,
    }


async def trigger_task_by_code(task_code: str) -> Dict[str, Any]:
    """按稳定 task_code 触发内置定时任务。

    Returns:
        ``{"accepted": bool, "task_id": int|None, "task_code": str,
        "task_name": str|None, "reason": str, "message": str}``；
        ``reason`` 为稳定拒绝码，``message`` 为人类可读原因。
    """
    if not task_code or not isinstance(task_code, str):
        return _reject(str(task_code), REASON_TASK_NOT_FOUND, "task_code 不能为空")

    # 前检1：必须是内置注册表中的任务（自定义 task_code 不开放）
    builtin = get_task_by_code(task_code)
    if builtin is None:
        return _reject(task_code, REASON_TASK_NOT_BUILTIN, f"task_code 不在内置任务白名单: {task_code}")

    task_name = builtin.get("task_name")

    db = SessionLocal()
    try:
        # 前检2：数据库中存在且未删除
        task_result = CronTaskCRUD.get_cron_task_by_code(db, task_code)
        if not task_result.success or not task_result.data:
            return _reject(task_code, REASON_TASK_NOT_FOUND, f"任务不存在或已删除: {task_code}")

        task = task_result.data
        task_id = task.id
        task_type = task.task_type

        # 前检3：类型策略（0-3 脚本类永不开放；类型不是放行依据，仅是额外护栏）
        if task_type not in _ALLOWED_TASK_TYPES:
            return _reject(
                task_code,
                REASON_TASK_TYPE_NOT_ALLOWED,
                f"任务类型不允许触发 [task_type={task_type}]，仅开放内置非脚本任务",
            )

        # 触发：enabled/运行中前检由 start_task_immediately 内建（ValueError 携带原因）
        await cron_executor.start_task_immediately(task_id)
        return {
            "accepted": True,
            "task_id": task_id,
            "task_code": task_code,
            "task_name": task_name,
            "reason": "",
            "message": "已接受触发请求，异步执行（run_id 见 CronTask.last_run_id）",
        }
    except ValueError as e:
        # start_task_immediately 的业务拒绝（禁用/运行中/不存在）
        return _reject(task_code, REASON_TRIGGER_REJECTED, str(e))
    except Exception as e:  # noqa: BLE001 - 触发异常以稳定拒绝码返回，不向调用方暴露堆栈
        logger.error(f"按 task_code 触发任务异常: {task_code}, {e}", exc_info=True)
        return _reject(task_code, REASON_TRIGGER_ERROR, f"触发异常: {type(e).__name__}")
    finally:
        db.close()
