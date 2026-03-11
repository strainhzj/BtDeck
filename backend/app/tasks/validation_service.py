"""
任务验证服务
提供脚本语法校验、Cron表达式验证、Python类验证等功能
"""

import asyncio
import re
import ast
import subprocess
import tempfile
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from croniter import croniter
from pydantic import BaseModel

import logging

logger = logging.getLogger(__name__)


class ValidationError(BaseModel):
    """语法错误信息模型"""
    startLineNumber: int
    startColumn: int
    endLineNumber: int
    endColumn: int
    severity: int
    message: str


class ScriptValidationResponse(BaseModel):
    """脚本语法校验响应模型"""
    valid: bool
    errors: List[ValidationError]
    message: str


class CronExecutionTime(BaseModel):
    """Cron执行时间信息"""
    nextExecutionTime: str
    previousExecutionTime: Optional[str] = None
    executionTimes: List[str] = []


class CronValidationResponse(BaseModel):
    """Cron表达式校验响应模型"""
    valid: bool
    message: str
    description: Optional[str] = None
    executionTimes: Optional[CronExecutionTime] = None


class PythonClassInfo(BaseModel):
    """Python类信息模型"""
    className: str
    module: str
    description: Optional[str] = None
    methods: List[str] = []
    parameters: Dict[str, Any] = {}


class PythonClassValidationResponse(BaseModel):
    """Python类路径验证响应模型"""
    valid: bool
    exists: bool
    classInfo: Optional[PythonClassInfo] = None
    message: str


class ScriptValidationService:
    """脚本语法校验服务"""

    def __init__(self):
        self.script_type_map = {
            0: "shell",
            1: "batch",
            2: "powershell",
            3: "python"
        }

    async def validate_script(self, content: str, script_type: int) -> ScriptValidationResponse:
        """
        校验脚本语法

        Args:
            content: 脚本内容
            script_type: 脚本类型 (0-shell, 1-cmd, 2-powershell, 3-python)

        Returns:
            校验结果
        """
        try:
            script_type_name = self.script_type_map.get(script_type, "unknown")
            logger.info(f"开始校验{script_type_name}脚本语法")

            if script_type == 0:  # Shell脚本
                return await self._validate_shell_script(content)
            elif script_type == 1:  # CMD批处理
                return await self._validate_batch_script(content)
            elif script_type == 2:  # PowerShell
                return await self._validate_powershell_script(content)
            elif script_type == 3:  # Python脚本
                return await self._validate_python_script(content)
            else:
                return ScriptValidationResponse(
                    valid=False,
                    errors=[],
                    message=f"不支持的脚本类型: {script_type}"
                )

        except Exception as e:
            logger.error(f"脚本语法校验失败: {str(e)}")
            return ScriptValidationResponse(
                valid=False,
                errors=[],
                message=f"校验过程中发生错误: {str(e)}"
            )

    async def _validate_shell_script(self, content: str) -> ScriptValidationResponse:
        """校验Shell脚本语法"""
        errors = []

        try:
            # 基础语法检查
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # 检查常见的语法错误
                if 'if ' in line and not line.endswith('then') and 'fi' not in line:
                    errors.append(ValidationError(
                        startLineNumber=i,
                        startColumn=0,
                        endLineNumber=i,
                        endColumn=len(line),
                        severity=1,
                        message="if语句缺少then或fi"
                    ))

                # 检查未闭合的引号
                if line.count('"') % 2 != 0 or line.count("'") % 2 != 0:
                    errors.append(ValidationError(
                        startLineNumber=i,
                        startColumn=0,
                        endLineNumber=i,
                        endColumn=len(line),
                        severity=1,
                        message="未闭合的引号"
                    ))

            # 尝试使用bash -n进行语法检查
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                    f.write(content)
                    temp_file = f.name

                # 使用bash -n进行语法检查
                result = await asyncio.create_subprocess_exec(
                    'bash', '-n', temp_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()

                if result.returncode != 0 and stderr:
                    error_lines = stderr.decode('utf-8').split('\n')
                    for error_line in error_lines:
                        if error_line.strip():
                            # 解析bash错误信息
                            match = re.search(r'line (\d+):', error_line)
                            line_num = int(match.group(1)) if match else i
                            errors.append(ValidationError(
                                startLineNumber=line_num,
                                startColumn=0,
                                endLineNumber=line_num,
                                endColumn=0,
                                severity=1,
                                message=error_line.strip()
                            ))

            finally:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

            return ScriptValidationResponse(
                valid=len(errors) == 0,
                errors=errors,
                message="语法检查完成" if len(errors) == 0 else f"发现 {len(errors)} 个语法错误"
            )

        except Exception as e:
            return ScriptValidationResponse(
                valid=False,
                errors=[],
                message=f"Shell脚本校验失败: {str(e)}"
            )

    async def _validate_batch_script(self, content: str) -> ScriptValidationResponse:
        """校验CMD批处理脚本语法"""
        errors = []

        try:
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('REM') or line.startswith('@'):
                    continue

                # 基础语法检查
                if line.startswith('if ') and not line.endswith(')'):
                    errors.append(ValidationError(
                        startLineNumber=i,
                        startColumn=0,
                        endLineNumber=i,
                        endColumn=len(line),
                        severity=1,
                        message="if语句可能不完整"
                    ))

                # 检查常见的语法错误
                if 'set' in line and '=' in line and not line.startswith('set '):
                    errors.append(ValidationError(
                        startLineNumber=i,
                        startColumn=0,
                        endLineNumber=i,
                        endColumn=len(line),
                        severity=1,
                        message="变量设置语法错误"
                    ))

            return ScriptValidationResponse(
                valid=len(errors) == 0,
                errors=errors,
                message="语法检查完成" if len(errors) == 0 else f"发现 {len(errors)} 个语法错误"
            )

        except Exception as e:
            return ScriptValidationResponse(
                valid=False,
                errors=[],
                message=f"CMD脚本校验失败: {str(e)}"
            )

    async def _validate_powershell_script(self, content: str) -> ScriptValidationResponse:
        """校验PowerShell脚本语法"""
        errors = []

        try:
            # 尝试使用PowerShell语法检查
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False, encoding='utf-8') as f:
                f.write(content)
                temp_file = f.name

            try:
                # 使用PowerShell语法检查
                result = await asyncio.create_subprocess_exec(
                    'powershell', '-NoProfile', '-Command', f"Get-Command -Syntax (Get-Content '{temp_file}' -Raw)",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()

                if result.returncode != 0 and stderr:
                    error_lines = stderr.decode('utf-8').split('\n')
                    for error_line in error_lines:
                        if error_line.strip():
                            errors.append(ValidationError(
                                startLineNumber=1,
                                startColumn=0,
                                endLineNumber=1,
                                endColumn=0,
                                severity=1,
                                message=error_line.strip()
                            ))

            finally:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

            return ScriptValidationResponse(
                valid=len(errors) == 0,
                errors=errors,
                message="语法检查完成" if len(errors) == 0 else f"发现 {len(errors)} 个语法错误"
            )

        except Exception as e:
            # 如果PowerShell不可用，进行基础检查
            logger.warning(f"PowerShell语法检查不可用，进行基础检查: {str(e)}")

            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # 基础语法检查
                if line.startswith('function ') and not line.endswith('{'):
                    errors.append(ValidationError(
                        startLineNumber=i,
                        startColumn=0,
                        endLineNumber=i,
                        endColumn=len(line),
                        severity=1,
                        message="函数定义可能不完整"
                    ))

            return ScriptValidationResponse(
                valid=len(errors) == 0,
                errors=errors,
                message="基础语法检查完成" if len(errors) == 0 else f"发现 {len(errors)} 个语法错误"
            )

    async def _validate_python_script(self, content: str) -> ScriptValidationResponse:
        """校验Python脚本语法"""
        errors = []

        try:
            # 使用AST进行语法检查
            ast.parse(content)

            # 进行更详细的语法检查
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # 检查常见的语法问题
                if line.count('(') != line.count(')'):
                    errors.append(ValidationError(
                        startLineNumber=i,
                        startColumn=0,
                        endLineNumber=i,
                        endColumn=len(line),
                        severity=1,
                        message="括号不匹配"
                    ))

                if line.count('[') != line.count(']'):
                    errors.append(ValidationError(
                        startLineNumber=i,
                        startColumn=0,
                        endLineNumber=i,
                        endColumn=len(line),
                        severity=1,
                        message="方括号不匹配"
                    ))

            return ScriptValidationResponse(
                valid=len(errors) == 0,
                errors=errors,
                message="语法检查完成" if len(errors) == 0 else f"发现 {len(errors)} 个语法错误"
            )

        except SyntaxError as e:
            errors.append(ValidationError(
                startLineNumber=e.lineno or 1,
                startColumn=e.offset or 0,
                endLineNumber=e.lineno or 1,
                endColumn=e.offset or 0,
                severity=1,
                message=f"语法错误: {str(e)}"
            ))

            return ScriptValidationResponse(
                valid=False,
                errors=errors,
                message="Python语法错误"
            )

        except Exception as e:
            return ScriptValidationResponse(
                valid=False,
                errors=[],
                message=f"Python脚本校验失败: {str(e)}"
            )


class CronValidationService:
    """Cron表达式校验服务"""

    async def validate_cron_expression(self, expression: str) -> CronValidationResponse:
        """
        校验Cron表达式

        Args:
            expression: Cron表达式

        Returns:
            校验结果
        """
        try:
            logger.info(f"开始校验Cron表达式: {expression}")

            # 基础格式检查
            if not expression or not expression.strip():
                return CronValidationResponse(
                    valid=False,
                    message="Cron表达式不能为空"
                )

            parts = expression.strip().split()
            if len(parts) != 5:
                return CronValidationResponse(
                    valid=False,
                    message="Cron表达式必须包含5个字段: 分 时 日 月 周"
                )

            # 使用croniter进行验证
            try:
                cron = croniter(expression)

                # 获取执行时间
                now = datetime.now()
                next_time = cron.get_next(datetime)
                prev_time = cron.get_prev(datetime)

                # 计算未来5次执行时间
                execution_times = []
                temp_cron = croniter(expression, now)
                for _ in range(5):
                    execution_times.append(temp_cron.get_next(datetime).strftime('%Y-%m-%d %H:%M:%S'))

                execution_time_info = CronExecutionTime(
                    nextExecutionTime=next_time.strftime('%Y-%m-%d %H:%M:%S'),
                    previousExecutionTime=prev_time.strftime('%Y-%m-%d %H:%M:%S'),
                    executionTimes=execution_times
                )

                # 生成描述
                description = self._generate_cron_description(expression)

                return CronValidationResponse(
                    valid=True,
                    message="Cron表达式有效",
                    description=description,
                    executionTimes=execution_time_info
                )

            except ValueError as e:
                return CronValidationResponse(
                    valid=False,
                    message=f"无效的Cron表达式: {str(e)}"
                )

        except Exception as e:
            logger.error(f"Cron表达式校验失败: {str(e)}")
            return CronValidationResponse(
                valid=False,
                message=f"校验过程中发生错误: {str(e)}"
            )

    def _generate_cron_description(self, expression: str) -> str:
        """生成Cron表达式描述"""
        parts = expression.strip().split()

        if len(parts) != 5:
            return "无效的Cron表达式"

        minute, hour, day, month, weekday = parts

        descriptions = []

        # 解析分钟
        if minute == '*':
            descriptions.append("每分钟")
        elif minute.isdigit():
            descriptions.append(f"第{minute}分钟")
        elif '/' in minute:
            interval = minute.split('/')[1]
            descriptions.append(f"每{interval}分钟")
        else:
            descriptions.append(f"在{minute}分钟")

        # 解析小时
        if hour == '*':
            if minute != '*':
                descriptions.append("每小时")
        elif hour.isdigit():
            descriptions.append(f"{hour}点")
        elif '/' in hour:
            interval = hour.split('/')[1]
            descriptions.append(f"每{interval}小时")
        else:
            descriptions.append(f"在{hour}时")

        # 解析日期
        if day == '*':
            if hour != '*' or minute != '*':
                descriptions.append("每天")
        elif day.isdigit():
            descriptions.append(f"每月{day}日")
        elif '/' in day:
            interval = day.split('/')[1]
            descriptions.append(f"每{interval}天")

        # 解析月份
        if month != '*':
            if month.isdigit():
                descriptions.append(f"{month}月")

        # 解析星期
        if weekday != '*':
            weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
            if weekday.isdigit():
                descriptions.append(weekdays[int(weekday) % 7])

        return ' '.join(descriptions) if descriptions else "自定义时间"


class PythonClassValidationService:
    """Python类验证服务"""

    def __init__(self):
        self.available_classes = [
            PythonClassInfo(
                className="SystemTask",
                module="app.tasks.system_tasks",
                description="系统任务基类",
                methods=["execute", "validate", "cleanup"],
                parameters={"timeout": "int", "retry_count": "int"}
            ),
            PythonClassInfo(
                className="DownloaderTask",
                module="app.tasks.downloader_tasks",
                description="下载器任务基类",
                methods=["sync_status", "check_health", "restart_downloader"],
                parameters={"downloader_id": "int", "action": "str"}
            ),
            PythonClassInfo(
                className="TorrentTask",
                module="app.tasks.torrent_tasks",
                description="种子管理任务",
                methods=["add_torrent", "remove_torrent", "check_torrent_status"],
                parameters={"torrent_hash": "str", "action": "str"}
            )
        ]

    async def validate_class_path(self, class_path: str) -> PythonClassValidationResponse:
        """
        验证Python类路径

        Args:
            class_path: 类路径，格式：module.submodule.ClassName

        Returns:
            验证结果
        """
        try:
            logger.info(f"开始验证Python类路径: {class_path}")

            if not class_path or not class_path.strip():
                return PythonClassValidationResponse(
                    valid=False,
                    exists=False,
                    message="类路径不能为空"
                )

            # 检查格式
            if '.' not in class_path:
                return PythonClassValidationResponse(
                    valid=False,
                    exists=False,
                    message="类路径格式不正确，应为 module.submodule.ClassName"
                )

            parts = class_path.split('.')
            if len(parts) < 2:
                return PythonClassValidationResponse(
                    valid=False,
                    exists=False,
                    message="类路径格式不正确"
                )

            class_name = parts[-1]
            module_path = '.'.join(parts[:-1])

            # 尝试导入模块
            try:
                import importlib
                module = importlib.import_module(module_path)

                # 检查类是否存在
                if hasattr(module, class_name):
                    cls = getattr(module, class_name)

                    # 获取类信息
                    methods = [method for method in dir(cls) if not method.startswith('_')]

                    class_info = PythonClassInfo(
                        className=class_name,
                        module=module_path,
                        description=f"从 {module_path} 导入的类",
                        methods=methods,
                        parameters={}
                    )

                    return PythonClassValidationResponse(
                        valid=True,
                        exists=True,
                        classInfo=class_info,
                        message="类路径验证成功"
                    )
                else:
                    return PythonClassValidationResponse(
                        valid=False,
                        exists=False,
                        message=f"模块 {module_path} 中不存在类 {class_name}"
                    )

            except ImportError as e:
                return PythonClassValidationResponse(
                    valid=False,
                    exists=False,
                    message=f"无法导入模块 {module_path}: {str(e)}"
                )

        except Exception as e:
            logger.error(f"Python类路径验证失败: {str(e)}")
            return PythonClassValidationResponse(
                valid=False,
                exists=False,
                message=f"验证过程中发生错误: {str(e)}"
            )

    async def get_available_classes(self) -> List[PythonClassInfo]:
        """获取可用的Python类列表"""
        return self.available_classes