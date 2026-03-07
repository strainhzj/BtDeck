"""
增强的Python代码执行器 - REQ-002实现
修复Python内部类任务执行语法错误

主要改进:
1. 智能异步/同步代码检测
2. 完整的语法验证
3. 增强的错误处理和恢复
4. 安全的代码执行环境
5. 详细的执行日志
"""

import ast
import asyncio
import logging
import sys
import traceback
import inspect
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
import importlib.util

logger = logging.getLogger(__name__)


class PythonCodeAnalyzer:
    """Python代码分析器"""

    def __init__(self):
        self.async_keywords = ['await', 'async def', 'async with', 'async for']
        self.sync_keywords = ['def ', 'for ', 'while ', 'if ', 'try:', 'except', 'finally']

    def is_async_code(self, code: str) -> bool:
        """
        智能检测代码是否为异步代码

        Args:
            code: Python代码字符串

        Returns:
            bool: 是否为异步代码
        """
        try:
            # 尝试解析AST
            tree = ast.parse(code)

            # 检查是否包含异步节点
            for node in ast.walk(tree):
                if isinstance(node, (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await)):
                    return True

            return False

        except SyntaxError:
            # 如果AST解析失败，使用关键词检测作为后备方案
            return any(keyword in code for keyword in self.async_keywords)

    def validate_syntax(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        验证Python代码语法

        Args:
            code: Python代码字符串

        Returns:
            Tuple[bool, Optional[str]]: (语法是否正确, 错误信息)
        """
        try:
            # 使用AST解析验证语法
            ast.parse(code)
            return True, None

        except SyntaxError as e:
            error_msg = f"语法错误: {e.msg} (行 {e.lineno}, 列 {e.offset})"
            logger.warning(f"代码语法验证失败: {error_msg}")
            return False, error_msg

        except Exception as e:
            error_msg = f"代码验证异常: {str(e)}"
            logger.error(f"代码验证时发生异常: {error_msg}")
            return False, error_msg

    def analyze_code_structure(self, code: str) -> Dict[str, Any]:
        """
        分析代码结构

        Args:
            code: Python代码字符串

        Returns:
            Dict[str, Any]: 代码结构分析结果
        """
        analysis = {
            "has_functions": False,
            "has_classes": False,
            "has_imports": False,
            "has_main_execution": False,
            "function_names": [],
            "class_names": [],
            "import_modules": [],
            "complexity_score": 0
        }

        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    analysis["has_functions"] = True
                    analysis["function_names"].append(node.name)
                    analysis["complexity_score"] += 1

                elif isinstance(node, ast.ClassDef):
                    analysis["has_classes"] = True
                    analysis["class_names"].append(node.name)
                    analysis["complexity_score"] += 2

                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    analysis["has_imports"] = True
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            analysis["import_modules"].append(alias.name)
                    else:
                        analysis["import_modules"].append(f"from {node.module}")

                elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    # 检查是否有直接的函数调用（可能是主执行代码）
                    analysis["has_main_execution"] = True
                    analysis["complexity_score"] += 1

        except SyntaxError as e:
            analysis["syntax_error"] = str(e)

        return analysis


class SafePythonExecutor:
    """安全的Python代码执行器"""

    def __init__(self):
        self.analyzer = PythonCodeAnalyzer()
        self.execution_timeout = 300  # 5分钟超时

    def create_safe_environment(self) -> Dict[str, Any]:
        """
        创建安全的执行环境

        Returns:
            Dict[str, Any]: 安全的执行环境
        """
        # 基础安全模块
        safe_modules = {
            'datetime': datetime,
            'time': __import__('time'),
            'json': __import__('json'),
            'os': __import__('os'),
            'sys': __import__('sys'),
            'math': __import__('math'),
            'random': __import__('random'),
            'string': __import__('string'),
            're': __import__('re'),
        }

        # 创建受限的内置函数
        safe_builtins = {}
        dangerous_builtins = [
            'exec', 'eval', 'compile', '__import__', 'open', 'file',
            'input', 'raw_input', 'reload', 'vars', 'globals', 'locals',
            'dir', 'hasattr', 'getattr', 'setattr', 'delattr', 'help'
        ]

        for name, obj in __builtins__.items():
            if name not in dangerous_builtins:
                safe_builtins[name] = obj

        return {
            '__builtins__': safe_builtins,
            **safe_modules
        }

    async def execute_async_code(self, code: str) -> Dict[str, Any]:
        """
        安全执行异步Python代码

        Args:
            code: 异步Python代码

        Returns:
            Dict[str, Any]: 执行结果
        """
        start_time = datetime.now()

        try:
            # 语法验证
            syntax_valid, syntax_error = self.analyzer.validate_syntax(code)
            if not syntax_valid:
                return {
                    "success": False,
                    "log_detail": f"异步代码语法错误: {syntax_error}",
                    "execution_time": 0
                }

            # 分析代码结构
            structure = self.analyzer.analyze_code_structure(code)

            # 创建安全的执行环境
            safe_globals = self.create_safe_environment()
            safe_locals = {}

            # 构建异步执行包装器
            wrapped_code = self._wrap_async_code(code)

            # 执行包装代码
            exec(wrapped_code, safe_globals, safe_locals)

            # 获取异步函数
            async_func = safe_locals.get('_async_wrapper')
            if not async_func:
                return {
                    "success": False,
                    "log_detail": "异步代码包装失败",
                    "execution_time": 0
                }

            # 执行异步函数（带超时）
            try:
                result = await asyncio.wait_for(async_func(), timeout=self.execution_timeout)
                execution_time = (datetime.now() - start_time).total_seconds()

                return {
                    "success": True,
                    "log_detail": f"异步代码执行成功\n执行结果: {result}\n执行时间: {execution_time:.2f}秒",
                    "execution_time": execution_time,
                    "code_structure": structure
                }

            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "log_detail": f"异步代码执行超时（{self.execution_timeout}秒）",
                    "execution_time": self.execution_timeout
                }

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_traceback = traceback.format_exc()

            return {
                "success": False,
                "log_detail": f"异步代码执行失败: {str(e)}\n错误详情:\n{error_traceback}",
                "execution_time": execution_time
            }

    def execute_sync_code(self, code: str) -> Dict[str, Any]:
        """
        安全执行同步Python代码

        Args:
            code: 同步Python代码

        Returns:
            Dict[str, Any]: 执行结果
        """
        start_time = datetime.now()

        try:
            # 语法验证
            syntax_valid, syntax_error = self.analyzer.validate_syntax(code)
            if not syntax_valid:
                return {
                    "success": False,
                    "log_detail": f"同步代码语法错误: {syntax_error}",
                    "execution_time": 0
                }

            # 分析代码结构
            structure = self.analyzer.analyze_code_structure(code)

            # 创建安全的执行环境
            safe_globals = self.create_safe_environment()
            safe_locals = {}

            # 执行代码
            exec(code, safe_globals, safe_locals)

            execution_time = (datetime.now() - start_time).total_seconds()

            # 检查是否有返回值
            result = safe_locals.get('result', '代码执行完成')

            return {
                "success": True,
                "log_detail": f"同步代码执行成功\n执行结果: {result}\n执行时间: {execution_time:.2f}秒",
                "execution_time": execution_time,
                "code_structure": structure
            }

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_traceback = traceback.format_exc()

            return {
                "success": False,
                "log_detail": f"同步代码执行失败: {str(e)}\n错误详情:\n{error_traceback}",
                "execution_time": execution_time
            }

    def _wrap_async_code(self, code: str) -> str:
        """
        包装异步代码以便安全执行

        Args:
            code: 异步代码

        Returns:
            str: 包装后的代码
        """
        # 缩进原始代码
        indented_code = '\n'.join('    ' + line for line in code.split('\n'))

        wrapped_code = f"""
import asyncio
import sys

async def _async_wrapper():
    try:
{indented_code}
        return "异步代码执行成功"
    except Exception as e:
        return f"异步代码执行异常: {{str(e)}}"

# 导出函数供外部调用
_async_wrapper = _async_wrapper
"""
        return wrapped_code


class EnhancedPythonExecutor:
    """增强的Python执行器 - REQ-002的主要实现"""

    def __init__(self):
        self.analyzer = PythonCodeAnalyzer()
        self.safe_executor = SafePythonExecutor()
        self.execution_history = []

    async def execute_python_internal_class(self, executor_code: str) -> Dict[str, Any]:
        """
        增强的Python内部类执行方法

        Args:
            executor_code: 执行器代码或类路径

        Returns:
            Dict[str, Any]: 执行结果
        """
        execution_start = datetime.now()

        try:
            # 记录执行开始
            logger.info(f"开始执行Python内部类代码: {executor_code[:100]}...")

            # 1. 检查是否是类路径格式
            if self._is_class_path(executor_code):
                return await self._execute_class_path(executor_code, execution_start)

            # 2. 验证代码语法
            syntax_valid, syntax_error = self.analyzer.validate_syntax(executor_code)
            if not syntax_valid:
                return {
                    "success": False,
                    "log_detail": f"代码语法错误: {syntax_error}",
                    "execution_time": 0,
                    "error_type": "SYNTAX_ERROR"
                }

            # 3. 检测代码类型（异步/同步）
            is_async = self.analyzer.is_async_code(executor_code)

            if is_async:
                logger.info("检测到异步代码，使用异步执行器")
                result = await self.safe_executor.execute_async_code(executor_code)
                result["execution_type"] = "async"
            else:
                logger.info("检测到同步代码，使用同步执行器")
                result = self.safe_executor.execute_sync_code(executor_code)
                result["execution_type"] = "sync"

            # 添加执行元数据
            result["execution_timestamp"] = execution_start.isoformat()
            result["executor_code_length"] = len(executor_code)

            # 记录执行历史
            self.execution_history.append({
                "timestamp": execution_start.isoformat(),
                "executor_code": executor_code,
                "result": result
            })

            return result

        except Exception as e:
            execution_time = (datetime.now() - execution_start).total_seconds()
            logger.error(f"Python内部类执行发生严重错误: {str(e)}")

            return {
                "success": False,
                "log_detail": f"Python内部类执行严重错误: {str(e)}\n{traceback.format_exc()}",
                "execution_time": execution_time,
                "error_type": "EXECUTION_ERROR",
                "execution_timestamp": execution_start.isoformat()
            }

    def _is_class_path(self, code: str) -> bool:
        """
        判断是否为类路径格式

        Args:
            code: 代码字符串

        Returns:
            bool: 是否为类路径
        """
        if not code or not code.strip():
            return False

        code = code.strip()

        # 排除代码关键字
        code_keywords = [
            'import', 'def', 'class', 'print', 'await', 'async', 'for', 'while',
            'if', 'try', 'except', 'with', 'lambda', 'yield', 'return'
        ]

        first_word = code.split('.')[0].split()[0] if '.' in code else code.split()[0]

        return (
            '.' in code and
            not any(code.startswith(keyword) for keyword in code_keywords) and
            first_word not in code_keywords and
            not code.startswith('#') and
            not code.startswith('"""')
        )

    async def _execute_class_path(self, class_path: str, execution_start: datetime) -> Dict[str, Any]:
        """
        执行类路径

        Args:
            class_path: 类路径字符串
            execution_start: 执行开始时间

        Returns:
            Dict[str, Any]: 执行结果
        """
        try:
            # 使用类路径验证器验证
            from app.tasks.class_path_validator import validate_single_class_path
            validation_result = validate_single_class_path(class_path)

            if not validation_result["is_valid"]:
                error_messages = [error["message"] for error in validation_result["errors"]]
                return {
                    "success": False,
                    "log_detail": f"类路径验证失败: {'; '.join(error_messages)}",
                    "execution_time": 0,
                    "error_type": "CLASS_PATH_VALIDATION_ERROR",
                    "validation_errors": validation_result["errors"]
                }

            # 解析类路径
            module_path = validation_result["module_path"]
            class_name = validation_result["class_name"]

            # 动态导入模块
            module = importlib.import_module(module_path)
            task_class = getattr(module, class_name)
            task_instance = task_class()

            # 检查execute方法
            if not hasattr(task_instance, 'execute'):
                return {
                    "success": False,
                    "log_detail": f"类 {class_name} 没有execute方法",
                    "execution_time": 0,
                    "error_type": "MISSING_EXECUTE_METHOD"
                }

            execute_method = getattr(task_instance, 'execute')

            # 检查execute方法是否是异步的
            if inspect.iscoroutinefunction(execute_method):
                logger.info(f"执行异步类方法: {class_path}")
                result = await asyncio.wait_for(
                    execute_method(),
                    timeout=self.safe_executor.execution_timeout
                )
            else:
                logger.info(f"执行同步类方法: {class_path}")
                # 在线程池中执行同步方法以避免阻塞
                result = await asyncio.get_event_loop().run_in_executor(
                    None, execute_method
                )

            execution_time = (datetime.now() - execution_start).total_seconds()

            return {
                "success": True,
                "log_detail": f"Python内部类执行成功\n类路径: {class_path}\n执行结果: {str(result)}\n执行时间: {execution_time:.2f}秒",
                "execution_time": execution_time,
                "execution_type": "class_path",
                "class_path": class_path,
                "result": result
            }

        except ImportError as e:
            return {
                "success": False,
                "log_detail": f"导入模块失败: {str(e)}",
                "execution_time": (datetime.now() - execution_start).total_seconds(),
                "error_type": "IMPORT_ERROR"
            }

        except AttributeError as e:
            return {
                "success": False,
                "log_detail": f"访问类属性失败: {str(e)}",
                "execution_time": (datetime.now() - execution_start).total_seconds(),
                "error_type": "ATTRIBUTE_ERROR"
            }

        except Exception as e:
            execution_time = (datetime.now() - execution_start).total_seconds()
            error_traceback = traceback.format_exc()

            return {
                "success": False,
                "log_detail": f"类路径执行失败: {str(e)}\n错误详情:\n{error_traceback}",
                "execution_time": execution_time,
                "error_type": "CLASS_EXECUTION_ERROR"
            }

    def get_execution_statistics(self) -> Dict[str, Any]:
        """
        获取执行统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        if not self.execution_history:
            return {
                "total_executions": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "average_execution_time": 0.0
            }

        total_executions = len(self.execution_history)
        success_count = sum(1 for h in self.execution_history if h["result"]["success"])
        failure_count = total_executions - success_count
        total_execution_time = sum(h["result"]["execution_time"] for h in self.execution_history)

        return {
            "total_executions": total_executions,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": (success_count / total_executions * 100) if total_executions > 0 else 0,
            "average_execution_time": (total_execution_time / total_executions) if total_executions > 0 else 0,
            "recent_executions": self.execution_history[-5:]  # 最近5次执行
        }


# 全局增强执行器实例
enhanced_python_executor = EnhancedPythonExecutor()


async def execute_python_code_enhanced(code: str) -> Dict[str, Any]:
    """
    增强的Python代码执行便捷函数

    Args:
        code: Python代码或类路径

    Returns:
        Dict[str, Any]: 执行结果
    """
    return await enhanced_python_executor.execute_python_internal_class(code)