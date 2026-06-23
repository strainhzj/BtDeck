from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, asc, func
from app.core.database_result import DatabaseResult
from app.tasks.cron_models import CronTask
from app.tasks.models import TaskLogs


class CronTaskCRUD:
    """定时任务CRUD操作"""

    @staticmethod
    def convert_task_type_to_chinese(task_type: int) -> str:
        """任务类型转换为中文"""
        type_mapping = {0: "shell脚本", 1: "cmd脚本", 2: "powershell脚本", 3: "python脚本", 4: "python内部类"}
        return type_mapping.get(task_type, "未知类型")

    @staticmethod
    def convert_task_status_to_chinese(task_status: int) -> str:
        """任务状态转换为中文"""
        status_mapping = {0: "等待运行", 1: "运行中", 2: "空闲"}
        return status_mapping.get(task_status, "未知状态")

    @staticmethod
    def create_cron_task(db: Session, task_data: Dict[str, Any]) -> DatabaseResult:
        """创建定时任务"""
        try:
            # 检查任务编码是否已存在
            existing_task = (
                db.query(CronTask)
                .filter(and_(CronTask.task_code == task_data.get("task_code"), CronTask.dr == 0))
                .first()
            )

            if existing_task:
                return DatabaseResult.failure_result(f"任务编码 '{task_data.get('task_code')}' 已存在，请使用其他编码")

            # 检查任务名称是否已存在
            existing_task_name = (
                db.query(CronTask)
                .filter(and_(CronTask.task_name == task_data.get("task_name"), CronTask.dr == 0))
                .first()
            )

            if existing_task_name:
                return DatabaseResult.failure_result(f"任务名称 '{task_data.get('task_name')}' 已存在，请使用其他名称")

            cron_task = CronTask(
                task_name=task_data.get("task_name"),
                task_code=task_data.get("task_code"),
                task_type=task_data.get("task_type"),
                executor=task_data.get("executor"),
                cron_plan=task_data.get("cron_plan"),
                enabled=task_data.get("enabled", True),
                create_by=task_data.get("create_by", "admin"),
            )

            db.add(cron_task)
            db.commit()
            db.refresh(cron_task)

            return DatabaseResult.success_result(cron_task.to_dict())

        except Exception as e:
            db.rollback()
            return DatabaseResult.failure_result(f"创建定时任务失败: {str(e)}")

    @staticmethod
    def get_cron_task_by_id(db: Session, task_id: int) -> DatabaseResult:
        """根据ID获取定时任务"""
        try:
            task = db.query(CronTask).filter(and_(CronTask.task_id == task_id, CronTask.dr == 0)).first()

            if not task:
                return DatabaseResult.not_found("定时任务不存在")

            return DatabaseResult.success_result(task.to_dict())

        except Exception as e:
            return DatabaseResult.failure_result(f"获取定时任务失败: {str(e)}")

    @staticmethod
    def get_cron_task_by_code(db: Session, task_code: str) -> DatabaseResult:
        """根据任务编码获取定时任务"""
        try:
            task = db.query(CronTask).filter(and_(CronTask.task_code == task_code, CronTask.dr == 0)).first()

            if not task:
                return DatabaseResult.success_result({"total": 0, "list": []})

            return DatabaseResult.success_result({"total": 1, "list": [task.to_dict()]})

        except Exception as e:
            return DatabaseResult.failure_result(f"根据编码获取定时任务失败: {str(e)}")

    @staticmethod
    def get_cron_tasks(
        db: Session,
        skip: int = 0,
        limit: int = 20,
        task_name: Optional[str] = None,
        task_code: Optional[str] = None,
        enabled: Optional[bool] = None,
        task_type: Optional[int] = None,
        task_status: Optional[int] = None,
    ) -> DatabaseResult:
        """获取定时任务列表"""
        try:
            query = db.query(CronTask).filter(CronTask.dr == 0)

            if task_name:
                query = query.filter(CronTask.task_name.like(f"%{task_name}%"))
            if task_code:
                query = query.filter(CronTask.task_code.like(f"%{task_code}%"))
            if enabled is not None:
                query = query.filter(CronTask.enabled == enabled)
            if task_type is not None:
                query = query.filter(CronTask.task_type == task_type)
            if task_status is not None:
                query = query.filter(CronTask.task_status == task_status)

            total = query.count()
            tasks = query.order_by(desc(CronTask.create_time)).offset(skip).limit(limit).all()

            # 数据转换
            task_list = []
            for task in tasks:
                task_data = task.to_dict()
                task_data.update(
                    {
                        "task_type_name": CronTaskCRUD.convert_task_type_to_chinese(task.task_type),
                        "task_status_name": CronTaskCRUD.convert_task_status_to_chinese(task.task_status),
                    }
                )
                task_list.append(task_data)

            return DatabaseResult.success_result({"total": total, "list": task_list})

        except Exception as e:
            return DatabaseResult.failure_result(f"获取定时任务列表失败: {str(e)}")

    @staticmethod
    def update_cron_task(db: Session, task_id: int, task_data: Dict[str, Any]) -> DatabaseResult:
        """更新定时任务"""
        try:
            task = db.query(CronTask).filter(and_(CronTask.task_id == task_id, CronTask.dr == 0)).first()

            if not task:
                return DatabaseResult.not_found("定时任务不存在")

            # 检查任务编码是否被其他任务使用
            if "task_code" in task_data:
                existing_task = (
                    db.query(CronTask)
                    .filter(
                        and_(
                            CronTask.task_code == task_data.get("task_code"),
                            CronTask.task_id != task_id,
                            CronTask.dr == 0,
                        )
                    )
                    .first()
                )

                if existing_task:
                    return DatabaseResult.failure_result(
                        f"任务编码 '{task_data.get('task_code')}' 已被其他任务使用，请使用其他编码"
                    )

            # 检查任务名称是否被其他任务使用
            if "task_name" in task_data:
                existing_task_name = (
                    db.query(CronTask)
                    .filter(
                        and_(
                            CronTask.task_name == task_data.get("task_name"),
                            CronTask.task_id != task_id,
                            CronTask.dr == 0,
                        )
                    )
                    .first()
                )

                if existing_task_name:
                    return DatabaseResult.failure_result(
                        f"任务名称 '{task_data.get('task_name')}' 已被其他任务使用，请使用其他名称"
                    )

            # 更新字段
            update_fields = ["task_name", "task_code", "task_type", "executor", "enabled", "cron_plan"]

            for field in update_fields:
                if field in task_data:
                    setattr(task, field, task_data[field])

            task.update_time = datetime.now()
            task.update_by = task_data.get("update_by", "admin")

            db.commit()
            db.refresh(task)

            return DatabaseResult.success_result(task.to_dict())

        except Exception as e:
            db.rollback()
            return DatabaseResult.failure_result(f"更新定时任务失败: {str(e)}")

    @staticmethod
    def delete_cron_task(db: Session, task_id: int, delete_by: str = "admin") -> DatabaseResult:
        """删除定时任务（逻辑删除）"""
        try:
            task = db.query(CronTask).filter(and_(CronTask.task_id == task_id, CronTask.dr == 0)).first()

            if not task:
                return DatabaseResult.not_found("定时任务不存在")

            task.dr = 1
            task.update_time = datetime.now()
            task.update_by = delete_by

            db.commit()

            return DatabaseResult.success_result({"task_id": task_id})

        except Exception as e:
            db.rollback()
            return DatabaseResult.failure_result(f"删除定时任务失败: {str(e)}")

    @staticmethod
    def update_task_status(db: Session, task_id: int, status: int) -> DatabaseResult:
        """更新任务状态"""
        try:
            task = db.query(CronTask).filter(and_(CronTask.task_id == task_id, CronTask.dr == 0)).first()

            if not task:
                return DatabaseResult.not_found("定时任务不存在")

            task.task_status = status
            task.update_time = datetime.now()

            db.commit()

            return DatabaseResult.success_result(task.to_dict())

        except Exception as e:
            db.rollback()
            return DatabaseResult.failure_result(f"更新任务状态失败: {str(e)}")

    @staticmethod
    def get_enabled_tasks(db: Session) -> DatabaseResult:
        """获取所有启用的定时任务"""
        try:
            tasks = db.query(CronTask).filter(and_(CronTask.enabled == True, CronTask.dr == 0)).all()

            return DatabaseResult.success_result([task.to_dict() for task in tasks])

        except Exception as e:
            return DatabaseResult.failure_result(f"获取启用任务失败: {str(e)}")


class TaskLogsCRUD:
    """任务日志CRUD操作"""

    @staticmethod
    def create_task_log(db: Session, log_data: Dict[str, Any]) -> DatabaseResult:
        """创建任务日志"""
        try:
            task_log = TaskLogs(
                task_id=log_data.get("task_id"),
                task_name=log_data.get("task_name"),
                task_type=log_data.get("task_type"),
                start_time=log_data.get("start_time"),
                end_time=log_data.get("end_time"),
                duration=log_data.get("duration"),
                success=log_data.get("success"),
                log_detail=log_data.get("log_detail"),
            )

            db.add(task_log)
            db.commit()
            db.refresh(task_log)

            return DatabaseResult.success_result(task_log.to_dict())

        except Exception as e:
            db.rollback()
            return DatabaseResult.failure_result(f"创建任务日志失败: {str(e)}")

    @staticmethod
    def get_task_logs(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        task_name: Optional[str] = None,
        task_id: Optional[int] = None,
        success: Optional[bool] = None,
    ) -> DatabaseResult:
        """获取任务日志列表"""
        try:
            query = db.query(TaskLogs).filter(TaskLogs.dr == 0)

            if task_name:
                query = query.filter(TaskLogs.task_name.like(f"%{task_name}%"))
            if task_id:
                query = query.filter(TaskLogs.task_id == task_id)
            if success is not None:
                query = query.filter(TaskLogs.success == success)

            total = query.count()
            logs = query.order_by(desc(TaskLogs.start_time)).offset(skip).limit(limit).all()

            return DatabaseResult.success_result({"total": total, "list": [log.to_dict() for log in logs]})

        except Exception as e:
            return DatabaseResult.failure_result(f"获取任务日志失败: {str(e)}")

    @staticmethod
    def get_task_logs_statistics(db: Session) -> DatabaseResult:
        """获取任务日志统计信息"""
        try:
            # 基础查询：只查询未删除的记录
            base_query = db.query(TaskLogs).filter(TaskLogs.dr == 0)

            # 总日志数
            total_logs = base_query.count()

            # 成功日志数
            success_logs = base_query.filter(TaskLogs.success == True).count()

            # 失败日志数
            failed_logs = base_query.filter(TaskLogs.success == False).count()

            # 今日日志数
            today = date.today()
            today_logs = base_query.filter(func.date(TaskLogs.start_time) == today).count()

            statistics = {
                "total_logs": total_logs,
                "success_logs": success_logs,
                "failed_logs": failed_logs,
                "today_logs": today_logs,
            }

            return DatabaseResult.success_result(statistics)

        except Exception as e:
            return DatabaseResult.failure_result(f"获取任务日志统计失败: {str(e)}")

    @staticmethod
    def delete_task_logs(
        db: Session,
        log_ids: Optional[List[int]] = None,
        task_id: Optional[int] = None,
        before_date: Optional[str] = None,
    ) -> DatabaseResult:
        """
        删除任务日志（软删除，dr=1）。

        支持按 log_id 列表、task_id 或指定日期之前三种维度，组合使用。
        至少要有一个过滤条件，避免误删全部。

        Args:
            log_ids: 指定日志ID列表
            task_id: 指定任务ID（删除该任务所有日志）
            before_date: 删除此日期(YYYY-MM-DD)之前的日志
        """
        try:
            if not log_ids and task_id is None and not before_date:
                return DatabaseResult.failure_result("必须提供 log_ids / task_id / before_date 中的至少一个条件")

            query = db.query(TaskLogs).filter(TaskLogs.dr == 0)
            if log_ids:
                query = query.filter(TaskLogs.log_id.in_(log_ids))
            if task_id is not None:
                query = query.filter(TaskLogs.task_id == task_id)
            if before_date:
                try:
                    cutoff = datetime.strptime(before_date, "%Y-%m-%d")
                except ValueError:
                    return DatabaseResult.failure_result("before_date 格式应为 YYYY-MM-DD")
                query = query.filter(TaskLogs.start_time < cutoff)

            count = query.update({TaskLogs.dr: 1}, synchronize_session=False)
            db.commit()

            return DatabaseResult.success_result({"deleted": count})

        except Exception as e:
            db.rollback()
            return DatabaseResult.failure_result(f"删除任务日志失败: {str(e)}")

    @staticmethod
    def cleanup_task_logs(
        db: Session, days: Optional[int] = None, keep_success: bool = False, keep_error: bool = False
    ) -> DatabaseResult:
        """
        清理过期任务日志（软删除，dr=1）。

        Args:
            days: 清理 N 天前的日志（按 start_time）；不传则不按时间过滤
            keep_success: 为 True 时保留成功日志（success=True 不删）
            keep_error: 为 True 时保留失败日志（success=False 不删）
        """
        try:
            if days is None and not keep_success and not keep_error:
                return DatabaseResult.failure_result("请至少指定一个清理条件")
            if days is not None and days < 0:
                return DatabaseResult.failure_result("days 必须大于等于 0")

            query = db.query(TaskLogs).filter(TaskLogs.dr == 0)

            if days is not None:
                cutoff = datetime.now() - timedelta(days=days)
                query = query.filter(TaskLogs.start_time < cutoff)

            if keep_success:
                query = query.filter(TaskLogs.success == False)  # noqa: E712
            if keep_error:
                query = query.filter(TaskLogs.success == True)  # noqa: E712

            count = query.update({TaskLogs.dr: 1}, synchronize_session=False)
            db.commit()

            return DatabaseResult.success_result({"cleaned": count})

        except Exception as e:
            db.rollback()
            return DatabaseResult.failure_result(f"清理任务日志失败: {str(e)}")
