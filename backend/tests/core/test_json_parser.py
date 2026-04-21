"""
JSON安全解析工具模块单元测试

测试 safe_json_parse、safe_json_parse_with_validator、safe_json_dumps 三个函数，
覆盖有效/无效输入、边界情况和异常处理。所有测试均为纯函数测试，无外部依赖。
"""

import json
import pytest
from app.core.json_parser import (
    safe_json_parse,
    safe_json_parse_with_validator,
    safe_json_dumps,
)


# ============================================================
# safe_json_parse 测试
# ============================================================

class TestSafeJsonParse:
    """safe_json_parse 函数测试"""

    # --- 有效 JSON 解析 ---

    def test_有效JSON对象(self):
        """解析标准 JSON 对象"""
        result = safe_json_parse('{"name": "test", "age": 30}')
        assert result == {"name": "test", "age": 30}

    def test_有效JSON数组(self):
        """解析 JSON 数组"""
        result = safe_json_parse('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_有效JSON字符串(self):
        """解析 JSON 字符串"""
        result = safe_json_parse('"hello"')
        assert result == "hello"

    def test_有效JSON数字(self):
        """解析 JSON 数字"""
        result = safe_json_parse('42')
        assert result == 42

    def test_有效JSON布尔(self):
        """解析 JSON 布尔值"""
        assert safe_json_parse('true') is True
        assert safe_json_parse('false') is False

    def test_有效JSONnull(self):
        """解析 JSON null"""
        result = safe_json_parse('null')
        assert result is None

    def test_嵌套JSON(self):
        """解析嵌套 JSON 结构"""
        json_str = '{"users": [{"id": 1, "name": "Alice"}], "total": 1}'
        result = safe_json_parse(json_str)
        assert result == {"users": [{"id": 1, "name": "Alice"}], "total": 1}

    def test_含中文JSON(self):
        """解析包含中文的 JSON"""
        result = safe_json_parse('{"名称": "测试"}')
        assert result == {"名称": "测试"}

    def test_含转义字符JSON(self):
        """解析包含转义字符的 JSON"""
        result = safe_json_parse('{"path": "C:\\\\Users\\\\test"}')
        assert result == {"path": "C:\\Users\\test"}

    # --- 无效 JSON 输入 ---

    def test_无效JSON返回默认值(self):
        """无效 JSON 字符串应返回默认值"""
        result = safe_json_parse('invalid json', default={})
        assert result == {}

    def test_截断的JSON(self):
        """截断的 JSON 字符串返回默认值"""
        result = safe_json_parse('{"key": "value"', default=None)
        assert result is None

    def test_默认值为空列表(self):
        """默认值为空列表"""
        result = safe_json_parse('not json', default=[])
        assert result == []

    def test_默认值为指定对象(self):
        """自定义默认值对象"""
        default_obj = {"error": True}
        result = safe_json_parse('bad json', default=default_obj)
        assert result == default_obj

    # --- 特殊输入 ---

    def test_None输入返回默认值(self):
        """None 输入应返回默认值"""
        result = safe_json_parse(None, default={})
        assert result == {}

    def test_空字符串返回默认值(self):
        """空字符串输入应返回默认值"""
        result = safe_json_parse('', default="fallback")
        assert result == "fallback"

    def test_默认值默认为None(self):
        """不指定默认值时返回 None"""
        result = safe_json_parse(None)
        assert result is None

    def test_log_errors为False时不抛异常(self):
        """log_errors=False 时静默处理错误"""
        result = safe_json_parse('invalid', default={}, log_errors=False)
        assert result == {}

    def test_error_context不影响解析结果(self):
        """error_context 参数不影响返回值"""
        result = safe_json_parse('{"a": 1}', error_context="[测试]")
        assert result == {"a": 1}

    def test_error_context不影响错误时的返回值(self):
        """error_context 参数不影响错误时的默认返回值"""
        result = safe_json_parse('bad', default=0, error_context="[上下文]")
        assert result == 0


# ============================================================
# safe_json_parse_with_validator 测试
# ============================================================

class TestSafeJsonParseWithValidator:
    """safe_json_parse_with_validator 函数测试"""

    def test_验证通过的列表(self):
        """验证器通过 - 返回解析结果"""
        result = safe_json_parse_with_validator(
            '["a", "b", "c"]',
            validator=lambda x: isinstance(x, list),
            default=[]
        )
        assert result == ["a", "b", "c"]

    def test_验证通过的对象(self):
        """验证器通过 - 对象类型验证"""
        def is_dict_with_name(obj):
            return isinstance(obj, dict) and "name" in obj

        result = safe_json_parse_with_validator(
            '{"name": "test"}',
            validator=is_dict_with_name,
            default={}
        )
        assert result == {"name": "test"}

    def test_验证失败返回默认值(self):
        """验证器不通过 - 返回默认值"""
        result = safe_json_parse_with_validator(
            '{"name": "test"}',
            validator=lambda x: isinstance(x, list),
            default=[]
        )
        assert result == []

    def test_无效JSON验证器返回默认值(self):
        """无效 JSON - 验证器不会被调用，直接返回默认值"""
        result = safe_json_parse_with_validator(
            'invalid',
            validator=lambda x: True,
            default={"error": True}
        )
        assert result == {"error": True}

    def test_None输入验证器返回默认值(self):
        """None 输入 - 返回默认值"""
        result = safe_json_parse_with_validator(
            None,
            validator=lambda x: True,
            default="fallback"
        )
        assert result == "fallback"

    def test_验证器抛出异常返回默认值(self):
        """验证器内部抛出异常 - 返回默认值"""
        def bad_validator(x):
            raise ValueError("验证器出错")

        result = safe_json_parse_with_validator(
            '{"key": "value"}',
            validator=bad_validator,
            default={}
        )
        assert result == {}

    def test_解析为None时验证器返回默认值(self):
        """解析结果为 None (JSON null) - 验证失败，返回默认值"""
        result = safe_json_parse_with_validator(
            'null',
            validator=lambda x: x is not None,
            default="was_null"
        )
        assert result == "was_null"

    def test_验证器检查数值范围(self):
        """验证器检查数值范围"""
        result = safe_json_parse_with_validator(
            '42',
            validator=lambda x: isinstance(x, int) and x > 0,
            default=0
        )
        assert result == 42

    def test_验证器检查数值范围失败(self):
        """验证器检查数值范围 - 不满足"""
        result = safe_json_parse_with_validator(
            '-5',
            validator=lambda x: isinstance(x, int) and x > 0,
            default=0
        )
        assert result == 0

    def test_log_errors为False验证失败静默(self):
        """log_errors=False 时验证失败静默处理"""
        result = safe_json_parse_with_validator(
            'not json',
            validator=lambda x: True,
            default={},
            log_errors=False
        )
        assert result == {}


# ============================================================
# safe_json_dumps 测试
# ============================================================

class TestSafeJsonDumps:
    """safe_json_dumps 函数测试"""

    def test_序列化字典(self):
        """序列化字典对象"""
        result = safe_json_dumps({"key": "value"})
        assert result == '{"key": "value"}'

    def test_序列化列表(self):
        """序列化列表"""
        result = safe_json_dumps([1, 2, 3])
        assert result == '[1, 2, 3]'

    def test_序列化字符串(self):
        """序列化字符串"""
        result = safe_json_dumps("hello")
        assert result == '"hello"'

    def test_序列化数字(self):
        """序列化数字"""
        result = safe_json_dumps(42)
        assert result == '42'

    def test_序列化布尔值(self):
        """序列化布尔值"""
        assert safe_json_dumps(True) == 'true'
        assert safe_json_dumps(False) == 'false'

    def test_序列化None(self):
        """序列化 None"""
        result = safe_json_dumps(None)
        assert result == 'null'

    def test_序列化中文不转义(self):
        """ensure_ascii=False 时中文不转义"""
        result = safe_json_dumps({"名称": "测试"})
        assert "名称" in result
        assert "测试" in result

    def test_序列化中文转义(self):
        """ensure_ascii=True 时中文被转义"""
        result = safe_json_dumps({"名称": "测试"}, ensure_ascii=True)
        assert "\\u" in result
        assert "名称" not in result

    def test_不可序列化对象返回默认值(self):
        """不可序列化对象返回默认值"""
        result = safe_json_dumps({1, 2, 3}, default="{}")
        assert result == "{}"

    def test_自定义默认返回值(self):
        """自定义序列化失败时的默认返回值"""
        result = safe_json_dumps(
            {1, 2, 3},
            default='{"error": true}'
        )
        assert result == '{"error": true}'

    def test_log_errors为False静默错误(self):
        """log_errors=False 时静默处理错误"""
        result = safe_json_dumps(
            float('inf'),
            default="err",
            log_errors=False
        )
        # float('inf') 在某些环境下可序列化，某些不可
        # 如果序列化成功则验证格式正确
        try:
            json.loads(result)
        except (json.JSONDecodeError, ValueError):
            assert result == "err"

    def test_嵌套对象序列化(self):
        """序列化嵌套对象"""
        obj = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"}
            ],
            "total": 2
        }
        result = safe_json_dumps(obj)
        parsed = json.loads(result)
        assert parsed == obj

    def test_空字典序列化(self):
        """序列化空字典"""
        result = safe_json_dumps({})
        assert result == '{}'

    def test_空列表序列化(self):
        """序列化空列表"""
        result = safe_json_dumps([])
        assert result == '[]'
