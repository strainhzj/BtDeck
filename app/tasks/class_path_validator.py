"""
类路径验证工具 - REQ-003实现
用于Python内部类数据完整性修复的验证工具

功能:
1. 验证类路径格式正确性
2. 检查模块是否可导入
3. 验证类是否存在
4. 检查类是否有execute方法
5. 批量验证数据库中的类路径
6. 生成修复报告和修复建议
"""

import importlib
import inspect
import logging
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path
import sys
import traceback

logger = logging.getLogger(__name__)


class ClassPathValidationError:
    """类路径验证错误类"""

    def __init__(self, error_type: str, message: str, details: str = ""):
        self.error_type = error_type
        self.message = message
        self.details = details

    def to_dict(self) -> Dict[str, str]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "details": self.details
        }


class ClassPathValidator:
    """类路径验证器"""

    # 错误类型常量
    ERROR_INVALID_FORMAT = "INVALID_FORMAT"
    ERROR_MODULE_NOT_FOUND = "MODULE_NOT_FOUND"
    ERROR_CLASS_NOT_FOUND = "CLASS_NOT_FOUND"
    ERROR_NO_EXECUTE_METHOD = "NO_EXECUTE_METHOD"
    ERROR_IMPORT_FAILED = "IMPORT_FAILED"
    ERROR_INVALID_SYNTAX = "INVALID_SYNTAX"

    def __init__(self):
        self.validation_results = []
        self.system_paths = sys.path.copy()

    def validate_class_path_format(self, class_path: str) -> Tuple[bool, Optional[ClassPathValidationError]]:
        """
        验证类路径格式

        Args:
            class_path: 类路径字符串，如 "app.tasks.my_task.MyTaskClass"

        Returns:
            Tuple[bool, Optional[ClassPathValidationError]]: (是否有效, 错误信息)
        """
        if not class_path or not class_path.strip():
            return False, ClassPathValidationError(
                self.ERROR_INVALID_FORMAT,
                "类路径不能为空",
                f"提供的类路径: '{class_path}'"
            )

        class_path = class_path.strip()

        # 检查基本格式：应该包含至少一个点号
        if '.' not in class_path:
            return False, ClassPathValidationError(
                self.ERROR_INVALID_FORMAT,
                "类路径格式无效，应包含模块路径和类名，用点号分隔",
                f"类路径: '{class_path}'"
            )

        # 检查是否以Python关键字开头
        python_keywords = {
            'import', 'def', 'print', 'await', 'async', 'class', 'if', 'for',
            'while', 'try', 'except', 'with', 'lambda', 'yield', 'return',
            'pass', 'break', 'continue', 'global', 'nonlocal'
        }

        first_part = class_path.split('.')[0].strip()
        if first_part in python_keywords:
            return False, ClassPathValidationError(
                self.ERROR_INVALID_FORMAT,
                f"类路径不能以Python关键字开头: {first_part}",
                f"类路径: '{class_path}'"
            )

        # 检查是否包含非法字符
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in invalid_chars:
            if char in class_path:
                return False, ClassPathValidationError(
                    self.ERROR_INVALID_FORMAT,
                    f"类路径包含非法字符: {char}",
                    f"类路径: '{class_path}'"
                )

        # 检查各部分是否都有效
        parts = class_path.split('.')
        for i, part in enumerate(parts):
            if not part.strip():
                return False, ClassPathValidationError(
                    self.ERROR_INVALID_FORMAT,
                    f"类路径第{i+1}部分为空",
                    f"类路径: '{class_path}'"
                )

            # 检查是否是有效的Python标识符
            if not part.isidentifier():
                return False, ClassPathValidationError(
                    self.ERROR_INVALID_FORMAT,
                    f"类路径第{i+1}部分 '{part}' 不是有效的Python标识符",
                    f"类路径: '{class_path}'"
                )

        return True, None

    def validate_module_import(self, module_path: str) -> Tuple[bool, Optional[ClassPathValidationError]]:
        """
        验证模块是否可以导入

        Args:
            module_path: 模块路径，如 "app.tasks.my_task"

        Returns:
            Tuple[bool, Optional[ClassPathValidationError]]: (是否可导入, 错误信息)
        """
        try:
            # 尝试导入模块
            module = importlib.import_module(module_path)
            logger.debug(f"模块 {module_path} 导入成功")
            return True, None

        except ImportError as e:
            return False, ClassPathValidationError(
                self.ERROR_MODULE_NOT_FOUND,
                f"无法导入模块: {module_path}",
                f"导入错误: {str(e)}"
            )

        except SyntaxError as e:
            return False, ClassPathValidationError(
                self.ERROR_INVALID_SYNTAX,
                f"模块 {module_path} 存在语法错误",
                f"语法错误: {str(e)}"
            )

        except Exception as e:
            return False, ClassPathValidationError(
                self.ERROR_IMPORT_FAILED,
                f"导入模块 {module_path} 时发生未知错误",
                f"错误类型: {type(e).__name__}, 错误信息: {str(e)}"
            )

    def validate_class_exists(self, module_path: str, class_name: str) -> Tuple[bool, Optional[object], Optional[ClassPathValidationError]]:
        """
        验证类是否存在

        Args:
            module_path: 模块路径
            class_name: 类名

        Returns:
            Tuple[bool, Optional[object], Optional[ClassPathValidationError]]: (是否存在, 类对象, 错误信息)
        """
        try:
            # 导入模块
            module = importlib.import_module(module_path)

            # 检查类是否存在
            if not hasattr(module, class_name):
                return False, None, ClassPathValidationError(
                    self.ERROR_CLASS_NOT_FOUND,
                    f"模块 {module_path} 中不存在类 {class_name}",
                    f"模块内容: {dir(module)}"
                )

            # 获取类对象
            cls = getattr(module, class_name)

            # 检查是否是类
            if not inspect.isclass(cls):
                return False, None, ClassPathValidationError(
                    self.ERROR_CLASS_NOT_FOUND,
                    f"{module_path}.{class_name} 不是一个类，而是 {type(cls).__name__}",
                    f"对象类型: {type(cls)}"
                )

            logger.debug(f"类 {module_path}.{class_name} 验证成功")
            return True, cls, None

        except ImportError as e:
            return False, None, ClassPathValidationError(
                self.ERROR_MODULE_NOT_FOUND,
                f"无法导入模块: {module_path}",
                f"导入错误: {str(e)}"
            )

        except Exception as e:
            return False, None, ClassPathValidationError(
                self.ERROR_IMPORT_FAILED,
                f"验证类 {module_path}.{class_name} 时发生错误",
                f"错误类型: {type(e).__name__}, 错误信息: {str(e)}"
            )

    def validate_execute_method(self, cls: object) -> Tuple[bool, Optional[ClassPathValidationError]]:
        """
        验证类是否有execute方法

        Args:
            cls: 类对象

        Returns:
            Tuple[bool, Optional[ClassPathValidationError]]: (是否有execute方法, 错误信息)
        """
        if not hasattr(cls, 'execute'):
            return False, ClassPathValidationError(
                self.ERROR_NO_EXECUTE_METHOD,
                f"类 {cls.__name__} 没有 execute 方法",
                f"可用方法: {[method for method in dir(cls) if not method.startswith('_')]}"
            )

        execute_method = getattr(cls, 'execute')

        # 检查是否是方法或函数
        if not callable(execute_method):
            return False, ClassPathValidationError(
                self.ERROR_NO_EXECUTE_METHOD,
                f"类 {cls.__name__} 的 execute 属性不是可调用的方法",
                f"execute 类型: {type(execute_method)}"
            )

        logger.debug(f"类 {cls.__name__} 的 execute 方法验证成功")
        return True, None

    def validate_class_path_comprehensive(self, class_path: str) -> Dict[str, Any]:
        """
        综合验证类路径

        Args:
            class_path: 完整的类路径

        Returns:
            Dict[str, Any]: 验证结果
        """
        result = {
            "class_path": class_path,
            "is_valid": False,
            "errors": [],
            "module_path": None,
            "class_name": None,
            "class_object": None
        }

        try:
            # 1. 验证格式
            format_valid, format_error = self.validate_class_path_format(class_path)
            if not format_valid:
                result["errors"].append(format_error.to_dict())
                return result

            # 解析模块路径和类名
            module_path, class_name = class_path.rsplit('.', 1)
            result["module_path"] = module_path
            result["class_name"] = class_name

            # 2. 验证模块导入
            module_valid, module_error = self.validate_module_import(module_path)
            if not module_valid:
                result["errors"].append(module_error.to_dict())
                return result

            # 3. 验证类存在
            class_exists, class_obj, class_error = self.validate_class_exists(module_path, class_name)
            if not class_exists:
                result["errors"].append(class_error.to_dict())
                return result

            result["class_object"] = class_obj

            # 4. 验证execute方法
            execute_valid, execute_error = self.validate_execute_method(class_obj)
            if not execute_valid:
                result["errors"].append(execute_error.to_dict())
                return result

            # 全部验证通过
            result["is_valid"] = True
            logger.info(f"类路径 {class_path} 验证通过")

        except Exception as e:
            result["errors"].append({
                "error_type": "VALIDATION_EXCEPTION",
                "message": f"验证过程中发生未预期的错误: {str(e)}",
                "details": traceback.format_exc()
            })

        return result

    def suggest_fix_for_error(self, error: Dict[str, str]) -> List[str]:
        """
        根据错误类型提供修复建议

        Args:
            error: 错误信息字典

        Returns:
            List[str]: 修复建议列表
        """
        suggestions = []
        error_type = error.get("error_type", "")

        if error_type == self.ERROR_INVALID_FORMAT:
            suggestions.extend([
                "检查类路径格式，应为 'module.submodule.ClassName' 格式",
                "确保类路径不包含非法字符（/, \\, :, *, ?, \", <, >, |）",
                "避免使用Python关键字作为路径开头"
            ])

        elif error_type == self.ERROR_MODULE_NOT_FOUND:
            suggestions.extend([
                "检查模块路径是否正确，确保模块存在于Python路径中",
                "确认模块文件名和目录结构是否匹配路径",
                "检查是否有语法错误或导入依赖问题"
            ])

        elif error_type == self.ERROR_CLASS_NOT_FOUND:
            suggestions.extend([
                "检查类名拼写是否正确",
                "确认类确实存在于指定模块中",
                "检查类的导入和导出是否正确"
            ])

        elif error_type == self.ERROR_NO_EXECUTE_METHOD:
            suggestions.extend([
                "在类中添加 execute 方法",
                "确保 execute 方法是可调用的",
                "检查方法名是否拼写正确"
            ])

        elif error_type == self.ERROR_IMPORT_FAILED:
            suggestions.extend([
                "检查模块的依赖是否已安装",
                "查看详细的错误信息以定位问题",
                "尝试单独导入模块进行测试"
            ])

        elif error_type == self.ERROR_INVALID_SYNTAX:
            suggestions.extend([
                "修复模块中的语法错误",
                "使用Python语法检查工具验证代码",
                "检查缩进、引号、括号等语法元素"
            ])

        return suggestions

    def generate_validation_report(self, validation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成验证报告

        Args:
            validation_results: 验证结果列表

        Returns:
            Dict[str, Any]: 验证报告
        """
        total_count = len(validation_results)
        valid_count = sum(1 for result in validation_results if result.get("is_valid", False))
        invalid_count = total_count - valid_count

        # 统计错误类型
        error_stats = {}
        for result in validation_results:
            for error in result.get("errors", []):
                error_type = error.get("error_type", "UNKNOWN")
                error_stats[error_type] = error_stats.get(error_type, 0) + 1

        # 生成修复建议
        all_suggestions = []
        for result in validation_results:
            if not result.get("is_valid", False):
                for error in result.get("errors", []):
                    all_suggestions.extend(self.suggest_fix_for_error(error))

        # 去重建议
        unique_suggestions = list(set(all_suggestions))

        return {
            "summary": {
                "total_count": total_count,
                "valid_count": valid_count,
                "invalid_count": invalid_count,
                "success_rate": f"{(valid_count / total_count * 100):.1f}%" if total_count > 0 else "0%"
            },
            "error_statistics": error_stats,
            "repair_suggestions": unique_suggestions,
            "detailed_results": validation_results
        }


# 全局验证器实例
class_path_validator = ClassPathValidator()


def validate_single_class_path(class_path: str) -> Dict[str, Any]:
    """
    验证单个类路径的便捷函数

    Args:
        class_path: 类路径字符串

    Returns:
        Dict[str, Any]: 验证结果
    """
    return class_path_validator.validate_class_path_comprehensive(class_path)


def validate_class_paths_batch(class_paths: List[str]) -> Dict[str, Any]:
    """
    批量验证类路径的便捷函数

    Args:
        class_paths: 类路径列表

    Returns:
        Dict[str, Any]: 验证报告
    """
    results = []
    for class_path in class_paths:
        result = validate_single_class_path(class_path)
        results.append(result)

    return class_path_validator.generate_validation_report(results)


if __name__ == "__main__":
    # 测试代码
    test_paths = [
        "app.tasks.cron_executor.CronTaskExecutor",  # 应该有效
        "nonexistent.module.ClassName",              # 应该失败 - 模块不存在
        "sys.invalid.Class",                         # 应该失败 - 类不存在
        "invalid-format",                           # 应该失败 - 格式无效
        "app.tasks.cron_executor.NonExistentClass"   # 应该失败 - 类不存在
    ]

    print("=== 类路径验证测试 ===")
    report = validate_class_paths_batch(test_paths)

    print(f"\n验证结果汇总:")
    print(f"总计: {report['summary']['total_count']}")
    print(f"有效: {report['summary']['valid_count']}")
    print(f"无效: {report['summary']['invalid_count']}")
    print(f"成功率: {report['summary']['success_rate']}")

    print(f"\n错误统计:")
    for error_type, count in report['error_statistics'].items():
        print(f"  {error_type}: {count}")

    print(f"\n修复建议:")
    for suggestion in report['repair_suggestions']:
        print(f"  - {suggestion}")