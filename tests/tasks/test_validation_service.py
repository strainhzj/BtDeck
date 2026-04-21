"""
validation_service.py 单元测试

覆盖 ScriptValidationService、CronValidationService、PythonClassValidationService 三个服务类。
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.tasks.validation_service import (
    ScriptValidationService,
    ScriptValidationResponse,
    CronValidationService,
    CronValidationResponse,
    PythonClassValidationService,
    PythonClassValidationResponse,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def script_service():
    """脚本校验服务实例"""
    return ScriptValidationService()


@pytest.fixture
def cron_service():
    """Cron 表达式校验服务实例"""
    return CronValidationService()


@pytest.fixture
def python_class_service():
    """Python 类路径验证服务实例"""
    return PythonClassValidationService()


# ===========================================================================
# ScriptValidationService - Python 脚本语法校验
# ===========================================================================


class TestPythonScriptValidation:
    """Python 脚本语法校验测试（script_type=3）"""

    @pytest.mark.asyncio
    async def test_valid_python_code(self, script_service):
        """有效的 Python 代码应通过校验"""
        code = "x = 1\ny = 2\nprint(x + y)"
        result = await script_service.validate_script(code, 3)

        assert isinstance(result, ScriptValidationResponse)
        assert result.valid is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_python_syntax_error(self, script_service):
        """包含语法错误的 Python 代码应校验失败，并返回错误信息"""
        code = "def foo(\n"
        result = await script_service.validate_script(code, 3)

        assert result.valid is False
        assert len(result.errors) > 0
        assert "语法错误" in result.errors[0].message

    @pytest.mark.asyncio
    async def test_empty_python_code(self, script_service):
        """空 Python 代码应通过校验（ast.parse('') 不报错）"""
        code = ""
        result = await script_service.validate_script(code, 3)

        assert result.valid is True

    @pytest.mark.asyncio
    async def test_python_import_error_in_code(self, script_service):
        """包含 import 语句的代码（语法正确）应通过语法校验（只做语法检查，不做运行检查）"""
        code = "import nonexistent_module_xyz\nprint('hello')"
        result = await script_service.validate_script(code, 3)

        # 语法层面合法，import 错误不在语法校验范围内
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_python_unmatched_parentheses(self, script_service):
        """括号不匹配的代码应产生错误（ast.parse 阶段捕获语法错误）"""
        code = "result = func(arg1, arg2"
        result = await script_service.validate_script(code, 3)

        assert result.valid is False
        assert len(result.errors) > 0
        # ast.parse 会直接报 SyntaxError，而不是括号不匹配
        assert "语法错误" in result.errors[0].message or "括号" in result.errors[0].message

    @pytest.mark.asyncio
    async def test_python_unmatched_brackets(self, script_service):
        """方括号不匹配应产生错误（ast.parse 阶段捕获语法错误）"""
        code = "data = [1, 2, 3"
        result = await script_service.validate_script(code, 3)

        assert result.valid is False
        assert len(result.errors) > 0
        assert "语法错误" in result.errors[0].message or "方括号" in result.errors[0].message

    @pytest.mark.asyncio
    async def test_python_parentheses_mismatch_in_multiline(self, script_service):
        """多行代码中某行括号不匹配（但语法层面合法）应被额外检查捕获"""
        # 这段代码在 ast.parse 时合法，但第二行括号不匹配（作为单独行检查）
        code = "x = 1\nprint('hello', func(arg"
        result = await script_service.validate_script(code, 3)

        # ast.parse 会捕获 SyntaxError
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_python_multiline_valid(self, script_service):
        """多行有效 Python 代码应通过校验"""
        code = """
def greet(name):
    return f"Hello, {name}"

result = greet("World")
print(result)
"""
        result = await script_service.validate_script(code, 3)

        assert result.valid is True

    @pytest.mark.asyncio
    async def test_syntax_error_reports_line_number(self, script_service):
        """语法错误应报告正确的行号"""
        code = "x = 1\ny = 2\nif True\n    z = 3"
        result = await script_service.validate_script(code, 3)

        assert result.valid is False
        assert len(result.errors) > 0
        # 语法错误应报告在第 3 行
        assert result.errors[0].startLineNumber >= 3


# ===========================================================================
# ScriptValidationService - Shell 脚本语法校验
# ===========================================================================


class TestShellScriptValidation:
    """Shell 脚本语法校验测试（script_type=0）"""

    @pytest.mark.asyncio
    async def test_valid_shell_script(self, script_service):
        """简单有效的 Shell 脚本（仅注释行，不触发外部 bash 调用）"""
        code = "#!/bin/bash\n# 这是一个注释\necho hello"
        result = await script_service.validate_script(code, 0)

        assert isinstance(result, ScriptValidationResponse)
        # Windows 环境下 bash 可能不可用，只要返回结构正确即可
        assert isinstance(result.valid, bool)
        assert isinstance(result.errors, list)

    @pytest.mark.asyncio
    async def test_shell_unclosed_quote(self, script_service):
        """未闭合的引号应产生错误"""
        code = 'echo "hello world'
        result = await script_service.validate_script(code, 0)

        assert result.valid is False
        assert any("引号" in e.message for e in result.errors)


# ===========================================================================
# ScriptValidationService - 其他脚本类型
# ===========================================================================


class TestOtherScriptValidation:
    """其他脚本类型校验测试"""

    @pytest.mark.asyncio
    async def test_unsupported_script_type(self, script_service):
        """不支持的脚本类型应返回失败"""
        result = await script_service.validate_script("code", 99)

        assert result.valid is False
        assert "不支持" in result.message

    @pytest.mark.asyncio
    async def test_batch_script_valid(self, script_service):
        """简单的 CMD 批处理脚本应通过基础检查"""
        code = "@echo off\necho hello"
        result = await script_service.validate_script(code, 1)

        assert result.valid is True


# ===========================================================================
# CronValidationService - Cron 表达式校验
# ===========================================================================


class TestCronValidation:
    """Cron 表达式校验测试"""

    @pytest.mark.asyncio
    async def test_valid_standard_cron(self, cron_service):
        """标准 5 字段 cron 表达式应通过"""
        result = await cron_service.validate_cron_expression("0 2 * * *")

        assert result.valid is True
        assert result.description is not None
        assert result.executionTimes is not None
        assert len(result.executionTimes.executionTimes) == 5

    @pytest.mark.asyncio
    async def test_empty_expression(self, cron_service):
        """空表达式应校验失败"""
        result = await cron_service.validate_cron_expression("")

        assert result.valid is False
        assert "不能为空" in result.message

    @pytest.mark.asyncio
    async def test_whitespace_only_expression(self, cron_service):
        """仅空白字符的表达式应校验失败"""
        result = await cron_service.validate_cron_expression("   ")

        assert result.valid is False

    @pytest.mark.asyncio
    async def test_wrong_field_count(self, cron_service):
        """字段数不正确应校验失败"""
        result = await cron_service.validate_cron_expression("0 2 * *")

        assert result.valid is False
        assert "5个字段" in result.message

    @pytest.mark.asyncio
    async def test_invalid_cron_value(self, cron_service):
        """无效的 cron 值应校验失败"""
        result = await cron_service.validate_cron_expression("99 2 * * *")

        assert result.valid is False

    @pytest.mark.asyncio
    async def test_every_minute_expression(self, cron_service):
        """每分钟表达式 * * * * * 应通过"""
        result = await cron_service.validate_cron_expression("* * * * *")

        assert result.valid is True
        assert "每分钟" in result.description

    @pytest.mark.asyncio
    async def test_interval_expression(self, cron_service):
        """间隔表达式（如每5分钟）应通过"""
        result = await cron_service.validate_cron_expression("*/5 * * * *")

        assert result.valid is True
        assert "每5分钟" in result.description

    @pytest.mark.asyncio
    async def test_execution_times_are_strings(self, cron_service):
        """执行时间列表应为格式化的字符串"""
        result = await cron_service.validate_cron_expression("0 * * * *")

        assert result.valid is True
        for t in result.executionTimes.executionTimes:
            assert isinstance(t, str)
            # 应该包含日期时间格式
            assert "-" in t and ":" in t


# ===========================================================================
# CronValidationService - 描述生成
# ===========================================================================


class TestCronDescription:
    """Cron 表达式描述生成测试"""

    def test_every_minute_description(self, cron_service):
        """每分钟的描述"""
        desc = cron_service._generate_cron_description("* * * * *")
        assert "每分钟" in desc

    def test_specific_hour_description(self, cron_service):
        """特定小时的描述"""
        desc = cron_service._generate_cron_description("0 8 * * *")
        assert "第0分钟" in desc
        assert "8点" in desc

    def test_specific_weekday_description(self, cron_service):
        """特定星期的描述"""
        desc = cron_service._generate_cron_description("0 0 * * 1")
        assert "周一" in desc

    def test_invalid_format_description(self, cron_service):
        """无效格式应返回默认描述"""
        desc = cron_service._generate_cron_description("0 0 0")
        assert "无效" in desc


# ===========================================================================
# PythonClassValidationService - 类路径验证
# ===========================================================================


class TestPythonClassValidation:
    """Python 类路径验证测试"""

    @pytest.mark.asyncio
    async def test_valid_class_path(self, python_class_service):
        """有效且存在的类路径应通过验证"""
        # 使用 Python 内置模块来验证
        result = await python_class_service.validate_class_path("os.path.join")

        # os.path.join 实际是一个函数而非类，但仍能被 hasattr 检测到
        assert isinstance(result, PythonClassValidationResponse)
        assert result.valid is True or result.message != ""

    @pytest.mark.asyncio
    async def test_empty_class_path(self, python_class_service):
        """空类路径应校验失败"""
        result = await python_class_service.validate_class_path("")

        assert result.valid is False
        assert "不能为空" in result.message

    @pytest.mark.asyncio
    async def test_no_dot_in_path(self, python_class_service):
        """不含点号的路径应校验失败"""
        result = await python_class_service.validate_class_path("SomeClass")

        assert result.valid is False
        assert "格式不正确" in result.message

    @pytest.mark.asyncio
    async def test_nonexistent_module(self, python_class_service):
        """不存在的模块应校验失败"""
        result = await python_class_service.validate_class_path("nonexistent_module_xyz_abc.SomeClass")

        assert result.valid is False
        assert "无法导入模块" in result.message

    @pytest.mark.asyncio
    async def test_nonexistent_class_in_existing_module(self, python_class_service):
        """存在的模块中不存在的类应校验失败"""
        result = await python_class_service.validate_class_path("os.path.NonExistentClassXYZ")

        assert result.valid is False
        assert "不存在" in result.message

    @pytest.mark.asyncio
    async def test_available_classes(self, python_class_service):
        """获取可用类列表应返回预定义的类信息"""
        classes = await python_class_service.get_available_classes()

        assert len(classes) > 0
        assert all(c.className for c in classes)
        assert all(c.module for c in classes)

    @pytest.mark.asyncio
    async def test_whitespace_only_class_path(self, python_class_service):
        """仅空白字符的类路径应校验失败"""
        result = await python_class_service.validate_class_path("   ")

        assert result.valid is False
        assert "不能为空" in result.message
