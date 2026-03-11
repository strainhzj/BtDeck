import asyncio
import subprocess
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import text

from app.tasks.cron_crud import CronTaskCRUD, TaskLogsCRUD
from app.tasks.cron_crud_async import AsyncCronTaskCRUD, AsyncTaskLogsCRUD
from app.tasks.cron_models import CronTask
from app.tasks.cleanup_executor import CleanupTaskExecutor
from app.database import get_db, AsyncSessionLocal, SessionLocal
from app.services.speed_schedule_service import SpeedScheduleService
import json

logger = logging.getLogger(__name__)


class CronTaskExecutor:
    """定时任务执行器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone='Asia/Shanghai')
        self.running_tasks: Dict[int, bool] = {}  # 跟踪正在运行的任务
        self.app = None  # ✅ 新增：存储 FastAPI 应用实例

    def set_app(self, app):
        """设置 FastAPI 应用实例

        Args:
            app: FastAPI 应用实例
        """
        self.app = app

    async def start(self):
        """启动调度器"""
        try:
            self.scheduler.start()
            logger.info("定时任务调度器启动成功")
            self._ensure_speed_schedule_job()
            await self.load_all_tasks()
        except Exception as e:
            logger.error(f"定时任务调度器启动失败: {str(e)}")

    async def stop(self):
        """停止调度器"""
        try:
            self.scheduler.shutdown(wait=False)
            logger.info("定时任务调度器已停止")
        except Exception as e:
            logger.error(f"定时任务调度器停止失败: {str(e)}")

    def _ensure_speed_schedule_job(self):
        """注册分时段限速同步任务（每分钟执行）"""
        job_id = "speed_schedule_sync"
        if self.scheduler.get_job(job_id):
            return

        self.scheduler.add_job(
            func=self._sync_speed_schedule,
            trigger=IntervalTrigger(minutes=1),
            id=job_id,
            name="speed_schedule_sync",
            replace_existing=True,
            misfire_grace_time=30
        )

    def _sync_speed_schedule(self):
        """Sync speed schedule rules."""
        if not self.app or not hasattr(self.app.state, 'store') or self.app.state.store is None:
            logger.warning("Downloader cache not initialized, skip speed schedule sync")
            return

        cached_downloaders = self.app.state.store.get_snapshot_sync()
        if not cached_downloaders:
            logger.warning("Downloader cache is empty, skip speed schedule sync")
            return

        db = SessionLocal()
        try:
            downloader_ids = [
                downloader.downloader_id
                for downloader in cached_downloaders
                if getattr(downloader, "fail_time", 0) == 0
            ]
            if not downloader_ids:
                return

            placeholders = ", ".join([f":id_{idx}" for idx in range(len(downloader_ids))])
            params = {f"id_{idx}": downloader_id for idx, downloader_id in enumerate(downloader_ids)}

            sql = f"""
                SELECT ds.id, ds.downloader_id
                FROM downloader_settings ds
                WHERE ds.enable_schedule = 1
                  AND ds.downloader_id IN ({placeholders})
            """
            downloaders = db.execute(text(sql), params).fetchall()

            for row in downloaders:
                SpeedScheduleService.apply_to_downloader(
                    db, row.downloader_id, row.id
                )

        except Exception as e:
            logger.error(f"同步分时段限速失败: {e}")
        finally:
            db.close()

    async def load_all_tasks(self):
        """加载所有启用的定时任务 - 使用异步数据库操作"""
        try:
            async with AsyncSessionLocal() as db:
                result = await AsyncCronTaskCRUD.get_enabled_tasks(db)

                if result.success:
                    tasks = result.data
                    for task in tasks:
                        await self.add_task_to_scheduler(task)
                    logger.info(f"成功加载 {len(tasks)} 个定时任务")
                else:
                    logger.error(f"加载定时任务失败: {result.message}")

        except Exception as e:
            logger.error(f"加载定时任务时发生错误: {str(e)}")

    async def add_task_to_scheduler(self, task: Dict[str, Any]) -> bool:
        """添加任务到调度器"""
        try:
            job_id = f"cron_task_{task['task_id']}"

            # 如果任务已存在，先移除
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            # 解析cron表达式
            trigger = self._parse_cron_plan(task['cron_plan'])
            if not trigger:
                logger.error(f"任务 {task['task_name']} 的cron表达式解析失败: {task['cron_plan']}")
                return False

            # 添加任务到调度器
            self.scheduler.add_job(
                func=self._execute_task,
                trigger=trigger,
                args=[task['task_id']],
                id=job_id,
                name=task['task_name'],
                replace_existing=True,
                misfire_grace_time=300  # 允许5分钟的延迟执行
            )

            logger.info(f"成功添加定时任务到调度器: {task['task_name']}")
            return True

        except Exception as e:
            logger.error(f"添加任务到调度器失败: {str(e)}")
            return False

    def _parse_cron_plan(self, cron_plan: str):
        """解析cron表达式"""
        try:
            # 支持的cron格式: "分 时 日 月 周"
            parts = cron_plan.split()
            if len(parts) != 5:
                logger.error(f"cron表达式格式错误: {cron_plan}")
                return None

            minute, hour, day, month, day_of_week = parts

            return CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone='Asia/Shanghai'
            )

        except Exception as e:
            logger.error(f"解析cron表达式失败: {str(e)}")
            return None

    async def _execute_task(self, task_id: int):
        """执行定时任务 - 使用异步数据库操作"""
        if self.running_tasks.get(task_id, False):
            logger.warning(f"任务 {task_id} 正在运行中，跳过本次执行")
            return

        try:
            # 标记任务为运行中
            self.running_tasks[task_id] = True

            # 更新任务状态为运行中
            await self._update_task_status(task_id, 1)

            # 异步获取任务信息
            async with AsyncSessionLocal() as db:
                task_result = await AsyncCronTaskCRUD.get_cron_task_by_id(db, task_id)

                if not task_result.success:
                    logger.error(f"获取任务信息失败: {task_result.message}")
                    return

                task = task_result.data
                start_time = datetime.now()
                success = False
                log_detail = ""

                try:
                    logger.info(f"开始执行定时任务: {task['task_name']} (ID: {task_id})")

                    # 异步更新任务的开始执行时间
                    await AsyncCronTaskCRUD.update_task_start_time(db, task_id, start_time)

                    # 执行任务
                    result = await self._run_task_script(task)
                    success = result['success']
                    log_detail = result['log_detail']

                    logger.info(f"定时任务执行完成: {task['task_name']}, 成功: {success}")

                except Exception as e:
                    success = False
                    log_detail = f"任务执行异常: {str(e)}"
                    logger.error(f"定时任务执行异常: {task['task_name']}, 错误: {str(e)}")

                finally:
                    end_time = datetime.now()
                    duration = int((end_time - start_time).total_seconds())

                    # 异步更新任务的执行持续时间
                    await AsyncCronTaskCRUD.update_task_execution_duration(db, task_id, duration)

                    # 异步创建任务日志
                    log_data = {
                        "task_id": task_id,
                        "task_name": task['task_name'],
                        "task_type": task['task_type'],
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": duration,
                        "success": success,
                        "log_detail": log_detail
                    }

                    await AsyncTaskLogsCRUD.create_task_log(db, log_data)

                # 更新任务状态为空闲（在事务外）
                await self._update_task_status(task_id, 2)

        except Exception as e:
            logger.error(f"执行定时任务时发生严重错误: {str(e)}")
        finally:
            # 清除运行标记
            self.running_tasks[task_id] = False

    async def _run_task_script(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """运行任务脚本"""
        task_type = task['task_type']
        executor = task['executor']

        try:
            if task_type == 0:  # Shell脚本
                return await self._run_shell_script(executor)
            elif task_type == 1:  # CMD脚本
                return await self._run_cmd_script(executor)
            elif task_type == 2:  # PowerShell脚本
                return await self._run_powershell_script(executor)
            elif task_type == 3:  # Python脚本
                return await self._run_python_script(executor)
            elif task_type == 4:  # Python内部类
                return await self._run_python_internal_class(executor)
            elif task_type == 5:  # 清理回收站任务
                return await self._run_cleanup_task(executor)
            elif task_type == 6:  # 审计日志导出任务
                return await self._run_audit_log_export_task(executor)
            else:
                return {"success": False, "log_detail": f"不支持的任务类型: {task_type}"}

        except Exception as e:
            return {"success": False, "log_detail": f"脚本执行失败: {str(e)}"}

    async def _run_shell_script(self, script: str) -> Dict[str, Any]:
        """运行Shell脚本"""
        try:
            process = await asyncio.create_subprocess_shell(
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return {
                    "success": True,
                    "log_detail": f"Shell脚本执行成功\n输出: {stdout.decode('utf-8', errors='ignore')}"
                }
            else:
                return {
                    "success": False,
                    "log_detail": f"Shell脚本执行失败，返回码: {process.returncode}\n错误: {stderr.decode('utf-8', errors='ignore')}"
                }

        except Exception as e:
            return {"success": False, "log_detail": f"Shell脚本执行异常: {str(e)}"}

    async def _run_cmd_script(self, script: str) -> Dict[str, Any]:
        """运行CMD脚本"""
        try:
            process = await asyncio.create_subprocess_shell(
                f'cmd /c "{script}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return {
                    "success": True,
                    "log_detail": f"CMD脚本执行成功\n输出: {stdout.decode('utf-8', errors='ignore')}"
                }
            else:
                return {
                    "success": False,
                    "log_detail": f"CMD脚本执行失败，返回码: {process.returncode}\n错误: {stderr.decode('utf-8', errors='ignore')}"
                }

        except Exception as e:
            return {"success": False, "log_detail": f"CMD脚本执行异常: {str(e)}"}

    async def _run_powershell_script(self, script: str) -> Dict[str, Any]:
        """运行PowerShell脚本"""
        try:
            process = await asyncio.create_subprocess_shell(
                f'powershell -Command "{script}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return {
                    "success": True,
                    "log_detail": f"PowerShell脚本执行成功\n输出: {stdout.decode('utf-8', errors='ignore')}"
                }
            else:
                return {
                    "success": False,
                    "log_detail": f"PowerShell脚本执行失败，返回码: {process.returncode}\n错误: {stderr.decode('utf-8', errors='ignore')}"
                }

        except Exception as e:
            return {"success": False, "log_detail": f"PowerShell脚本执行异常: {str(e)}"}

    async def _run_python_script(self, script: str) -> Dict[str, Any]:
        """运行Python脚本"""
        try:
            process = await asyncio.create_subprocess_shell(
                f'python -c "{script}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return {
                    "success": True,
                    "log_detail": f"Python脚本执行成功\n输出: {stdout.decode('utf-8', errors='ignore')}"
                }
            else:
                return {
                    "success": False,
                    "log_detail": f"Python脚本执行失败，返回码: {process.returncode}\n错误: {stderr.decode('utf-8', errors='ignore')}"
                }

        except Exception as e:
            return {"success": False, "log_detail": f"Python脚本执行异常: {str(e)}"}

    async def _run_python_internal_class(self, executor_code: str) -> Dict[str, Any]:
        """运行Python内部类或代码"""
        try:
            # 检查是否是类路径格式（包含点号）
            if '.' in executor_code and not executor_code.strip().startswith(('import', 'def', 'print', 'await', 'time', 'async')):
                # 尝试作为类路径执行
                try:
                    module_path, class_name = executor_code.rsplit('.', 1)
                    module = __import__(module_path, fromlist=[class_name])
                    task_class = getattr(module, class_name)

                    # ✅ 修复：尝试在初始化时传递 app 实例
                    task_instance = None
                    try:
                        # 尝试通过 __init__ 参数传递 app
                        task_instance = task_class(app=self.app)
                    except TypeError:
                        # 如果 __init__ 不接受 app 参数，使用 set_app 方法
                        task_instance = task_class()
                        if hasattr(task_instance, 'set_app'):
                            task_instance.set_app(self.app)

                    # 检查是否有execute方法
                    if hasattr(task_instance, 'execute'):
                        execute_method = task_instance.execute

                        # ✅ 修复：检查方法是否为协函数，避免await同步方法导致RuntimeError
                        if asyncio.iscoroutinefunction(execute_method):
                            # ✅ 修复：传递 app 参数到 execute 方法
                            result = await execute_method(app=self.app)
                        else:
                            # 同步调用
                            result = execute_method(app=self.app)

                        return {
                            "success": True,
                            "log_detail": f"Python内部类执行成功\n结果: {str(result)}"
                        }
                    else:
                        return {
                            "success": False,
                            "log_detail": f"类 {class_name} 没有execute方法"
                        }

                except (ImportError, AttributeError) as e:
                    # 如果不是有效的类路径，则作为代码执行
                    logger.debug(f"无法作为类路径执行，转为代码执行: {str(e)}")

            # 检查代码是否包含异步语法
            has_await = 'await' in executor_code
            has_async_def = 'async def' in executor_code

            if has_await or has_async_def:
                # 处理异步代码
                return await self._execute_async_python_code(executor_code)
            else:
                # 处理同步代码 - ✅ 现在是异步函数
                return await self._execute_sync_python_code(executor_code)

        except Exception as e:
            return {"success": False, "log_detail": f"Python内部类执行异常: {str(e)}"}

    async def _execute_async_python_code(self, code: str) -> Dict[str, Any]:
        """执行异步Python代码"""
        try:
            # 创建一个包装的异步函数
            wrapped_code = f"""
import asyncio
async def _async_exec_func():
    try:
{chr(10).join('        ' + line for line in code.split(chr(10)))}
        return {{"success": True, "message": "异步代码执行成功"}}
    except Exception as e:
        return {{"success": False, "message": str(e)}}
"""

            # 创建执行环境
            exec_globals = {
                '__builtins__': __builtins__,
                'datetime': datetime,
                'asyncio': asyncio,
                'time': __import__('time'),
            }

            # 执行包装代码
            exec(wrapped_code, exec_globals)

            # 获取并执行异步函数
            async_func = exec_globals['_async_exec_func']
            result = await async_func()

            if result['success']:
                return {
                    "success": True,
                    "log_detail": f"异步Python代码执行成功\n执行代码: {code}"
                }
            else:
                return {
                    "success": False,
                    "log_detail": f"异步代码执行失败: {result['message']}"
                }

        except Exception as e:
            return {"success": False, "log_detail": f"异步Python代码执行异常: {str(e)}"}

    async def _execute_sync_python_code(self, code: str) -> Dict[str, Any]:
        """
        执行同步Python代码 - 使用线程池避免阻塞事件循环

        ✅ 修复：在线程池中执行同步代码，避免阻塞事件循环
        """
        try:
            loop = asyncio.get_event_loop()

            # 定义在线程池中执行的函数
            def exec_sync_code():
                exec_globals = {
                    '__builtins__': __builtins__,
                    'datetime': datetime,
                    'asyncio': asyncio,
                    'time': __import__('time'),
                }
                exec(code, exec_globals)

            # ✅ 在线程池中执行同步代码，避免阻塞事件循环
            await loop.run_in_executor(None, exec_sync_code)

            return {
                "success": True,
                "log_detail": f"同步Python代码执行成功\n执行代码: {code}"
            }

        except Exception as e:
            return {"success": False, "log_detail": f"同步Python代码执行异常: {str(e)}"}

    async def _update_task_status(self, task_id: int, status: int):
        """更新任务状态 - 使用异步数据库操作"""
        try:
            async with AsyncSessionLocal() as db:
                await AsyncCronTaskCRUD.update_task_status(db, task_id, status)
        except Exception as e:
            logger.error(f"更新任务状态失败: {str(e)}")

    # 任务控制功能
    async def start_task_immediately(self, task_id: int) -> bool:
        """立即启动任务 - 使用异步数据库操作"""
        try:
            async with AsyncSessionLocal() as db:
                task_result = await AsyncCronTaskCRUD.get_cron_task_by_id(db, task_id)

                if task_result.success:
                    task = task_result.data
                    # 检查任务是否启用
                    if not task.get('enabled'):
                        error_msg = f"任务 '{task.get('task_name', task_id)}' 处于禁用状态，无法启动。请先启用该任务。"
                        logger.warning(f"启动任务失败: {error_msg} (任务ID: {task_id}, 状态: enabled={task.get('enabled')})")
                        raise ValueError(error_msg)

                    # 检查任务是否已在运行中
                    if self.running_tasks.get(task_id, False):
                        error_msg = f"任务 '{task.get('task_name', task_id)}' 正在运行中，请勿重复启动。"
                        logger.warning(f"启动任务失败: {error_msg} (任务ID: {task_id})")
                        raise ValueError(error_msg)

                    # 立即执行任务
                    logger.info(f"准备立即启动任务: {task.get('task_name', task_id)} (任务ID: {task_id})")

                    # ✅ 修复：保存task引用并添加异常处理，避免异常被忽略
                    task = asyncio.create_task(self._execute_task(task_id))

                    # 添加回调处理任务异常
                    def handle_task_exception(t: asyncio.Task):
                        try:
                            exception = t.exception()
                            if exception:
                                logger.error(f"立即执行任务异常: {task.get('task_name', task_id)} (任务ID: {task_id}), 错误: {str(exception)}")
                        except asyncio.CancelledError:
                            logger.warning(f"任务被取消: {task.get('task_name', task_id)} (任务ID: {task_id})")

                    task.add_done_callback(handle_task_exception)

                    return True
                else:
                    # 任务不存在
                    error_msg = task_result.message or f"任务ID {task_id} 不存在"
                    logger.error(f"启动任务失败: {error_msg}")
                    raise ValueError(error_msg)

        except ValueError:
            # 重新抛出业务逻辑异常，让上层处理
            raise
        except Exception as e:
            logger.error(f"立即启动任务异常: {str(e)} (任务ID: {task_id})", exc_info=True)
            raise

    async def pause_task(self, task_id: int) -> bool:
        """暂停任务"""
        try:
            job_id = f"cron_task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.pause_job(job_id)
                await self._update_task_status(task_id, 2)  # 设置为空闲状态
                return True
            return False

        except Exception as e:
            logger.error(f"暂停任务失败: {str(e)}")
            return False

    async def resume_task(self, task_id: int) -> bool:
        """恢复任务"""
        try:
            job_id = f"cron_task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.resume_job(job_id)
                return True
            return False

        except Exception as e:
            logger.error(f"恢复任务失败: {str(e)}")
            return False

    async def interrupt_task(self, task_id: int) -> bool:
        """中断任务"""
        try:
            # 设置任务为不运行状态
            self.running_tasks[task_id] = False

            # 从调度器中移除任务
            job_id = f"cron_task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            # 更新任务状态
            await self._update_task_status(task_id, 2)

            return True

        except Exception as e:
            logger.error(f"中断任务失败: {str(e)}")
            return False

    async def refresh_task(self, task_id: int) -> bool:
        """刷新任务配置 - 使用异步数据库操作"""
        try:
            async with AsyncSessionLocal() as db:
                task_result = await AsyncCronTaskCRUD.get_cron_task_by_id(db, task_id)

                if task_result.success:
                    task = task_result.data
                    return await self.add_task_to_scheduler(task)

                return False

        except Exception as e:
            logger.error(f"刷新任务失败: {str(e)}")
            return False

    async def remove_task_from_scheduler(self, task_id: int) -> bool:
        """从调度器中移除任务"""
        try:
            job_id = f"cron_task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"任务 {task_id} 已从调度器中移除")
                return True
            else:
                logger.warning(f"任务 {task_id} 在调度器中不存在")
                return True  # 不存在也算成功

        except Exception as e:
            logger.error(f"从调度器移除任务失败: {str(e)}")
            return False

    async def _run_cleanup_task(self, executor: str) -> Dict[str, Any]:
        """
        执行清理回收站任务
        
        Args:
            executor: JSON格式的清理任务配置
                {
                    "cleanup_level_3": bool,
                    "cleanup_level_4": bool,
                    "days_threshold": int
                }
        
        Returns:
            执行结果字典
        """
        try:
            # 解析任务配置
            task_config = json.loads(executor)
            
            # 验证配置
            if not isinstance(task_config, dict):
                return {"success": False, "log_detail": "任务配置格式错误，必须是JSON对象"}

            # 定义必需字段及其类型
            required_fields = {
                "cleanup_level_3": bool,
                "cleanup_level_4": bool,
                "days_threshold": int
            }

            # 验证字段存在性和类型
            for field, expected_type in required_fields.items():
                if field not in task_config:
                    return {"success": False, "log_detail": f"缺少必需字段: {field}"}
                if not isinstance(task_config[field], expected_type):
                    return {"success": False, "log_detail": f"字段 {field} 类型错误，期望 {expected_type.__name__}"}

            # 验证 days_threshold 范围
            if not (1 <= task_config["days_threshold"] <= 365):
                return {"success": False, "log_detail": "days_threshold 必须在 1-365 之间"}
            
            # 获取数据库会话（使用同步Session，因为CleanupTaskExecutor是同步实现）
            with next(get_db()) as db:
                # 创建清理执行器
                cleanup_executor = CleanupTaskExecutor(db)

                # 执行清理任务
                result = await cleanup_executor.execute_cleanup_task(
                    task_config=task_config,
                    operator="system",
                    audit_service=None  # 可选：传入审计服务实例
                )
                
                # 生成日志详情
                log_detail = (
                    f"清理任务完成\n"
                    f"等级3清理: {result['level3_cleaned']} 个\n"
                    f"等级4清理: {result['level4_cleaned']} 个\n"
                    f"释放空间: {result['total_size_freed'] / (1024**3):.2f} GB"
                )

                if result['errors']:
                    log_detail += f"\n错误: {len(result['errors'])} 个错误\n"
                    log_detail += "\n".join(result['errors'][:5])  # 最多显示5个错误
                    if len(result['errors']) > 5:
                        log_detail += f"\n... 还有 {len(result['errors']) - 5} 个错误"
                
                logger.info(log_detail)
                
                return {"success": True, "log_detail": log_detail}
        
        except json.JSONDecodeError as e:
            error_msg = f"任务配置JSON解析失败: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "log_detail": error_msg}
        
        except Exception as e:
            error_msg = f"清理任务执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "log_detail": error_msg}


    async def _run_audit_log_export_task(self, executor: str) -> Dict[str, Any]:
        """运行审计日志导出任务"""
        try:
            from app.tasks.scheduler.audit_log_exporter import AuditLogExportTask

            # 解析执行配置
            import json
            config = json.loads(executor) if isinstance(executor, str) else {}

            # 创建任务实例
            task = AuditLogExportTask()

            # 执行导出
            async with AsyncSessionLocal() as db:
                exported_count = await task.execute_manual_export(
                    db_session=db,
                    days=config.get('days', 7),
                    operation_type=config.get('operation_type')
                )

            return {
                "success": True,
                "log_detail": f"成功导出{exported_count}条审计日志"
            }

        except Exception as e:
            logger.error(f"审计日志导出任务执行失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "log_detail": f"导出失败: {str(e)}"
            }


# 全局定时任务执行器实例
cron_executor = CronTaskExecutor()
