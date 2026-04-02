"""
DatabaseResult 模块单元测试

测试数据库操作标准化返回格式，包括成功/失败结果创建、
错误码映射、序列化等功能。所有测试均为纯函数测试，无外部依赖。
"""

import pytest
from app.core.database_result import DatabaseError, DatabaseResult


# ============================================================
# DatabaseError 枚举测试
# ============================================================

class TestDatabaseError:
    """DatabaseError 枚举值测试"""

    def test_枚举所有值存在(self):
        """验证所有枚举成员都已定义"""
        expected_members = [
            "SUCCESS", "NOT_FOUND", "DUPLICATE_KEY",
            "VALIDATION_ERROR", "DATABASE_ERROR",
            "FOREIGN_KEY_CONSTRAINT", "UNKNOWN_ERROR"
        ]
        for name in expected_members:
            assert hasattr(DatabaseError, name), f"缺少枚举成员: {name}"

    def test_枚举值等于自身名称(self):
        """验证枚举值与名称字符串一致"""
        assert DatabaseError.SUCCESS.value == "SUCCESS"
        assert DatabaseError.NOT_FOUND.value == "NOT_FOUND"
        assert DatabaseError.DUPLICATE_KEY.value == "DUPLICATE_KEY"
        assert DatabaseError.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert DatabaseError.DATABASE_ERROR.value == "DATABASE_ERROR"
        assert DatabaseError.FOREIGN_KEY_CONSTRAINT.value == "FOREIGN_KEY_CONSTRAINT"
        assert DatabaseError.UNKNOWN_ERROR.value == "UNKNOWN_ERROR"

    def test_枚举成员总数(self):
        """验证枚举成员数量"""
        assert len(DatabaseError) == 7


# ============================================================
# DatabaseResult 默认值测试
# ============================================================

class TestDatabaseResultDefaults:
    """DatabaseResult 默认值测试"""

    def test_直接构造的默认值(self):
        """直接构造时未提供的字段应使用默认值"""
        result = DatabaseResult(success=True)
        assert result.data is None
        assert result.message == ""
        assert result.error_code is None
        assert result.affected_rows == 0
        assert result.total_count is None

    def test_直接构造指定所有字段(self):
        """直接构造时显式指定所有字段"""
        result = DatabaseResult(
            success=True,
            data={"id": 1},
            message="测试消息",
            error_code="SUCCESS",
            affected_rows=3,
            total_count=100
        )
        assert result.success is True
        assert result.data == {"id": 1}
        assert result.message == "测试消息"
        assert result.error_code == "SUCCESS"
        assert result.affected_rows == 3
        assert result.total_count == 100


# ============================================================
# success_result 工厂方法测试
# ============================================================

class TestSuccessResult:
    """success_result 工厂方法测试"""

    def test_基本成功结果(self):
        """创建基本成功结果"""
        result = DatabaseResult.success_result()
        assert result.success is True
        assert result.data is None
        assert result.message == "Operation completed successfully"
        assert result.error_code == DatabaseError.SUCCESS.value
        assert result.affected_rows == 0
        assert result.total_count is None

    def test_带数据的成功结果(self):
        """创建带数据的成功结果"""
        data = {"name": "test", "value": 42}
        result = DatabaseResult.success_result(data=data)
        assert result.success is True
        assert result.data == data

    def test_自定义消息(self):
        """自定义成功消息"""
        result = DatabaseResult.success_result(message="创建成功")
        assert result.message == "创建成功"

    def test_指定affected_rows(self):
        """指定影响行数"""
        result = DatabaseResult.success_result(affected_rows=5)
        assert result.affected_rows == 5

    def test_指定total_count(self):
        """指定总计数"""
        result = DatabaseResult.success_result(total_count=1000)
        assert result.total_count == 1000

    def test_全部参数(self):
        """同时指定所有参数"""
        result = DatabaseResult.success_result(
            data={"items": [1, 2, 3]},
            message="查询完成",
            affected_rows=3,
            total_count=50
        )
        assert result.success is True
        assert result.data == {"items": [1, 2, 3]}
        assert result.message == "查询完成"
        assert result.affected_rows == 3
        assert result.total_count == 50
        assert result.error_code == DatabaseError.SUCCESS.value


# ============================================================
# 泛型支持测试 - 不同类型数据
# ============================================================

class TestSuccessResultGenericTypes:
    """success_result 泛型支持测试"""

    def test_字典类型数据(self):
        """成功结果携带字典数据"""
        data = {"key": "value"}
        result = DatabaseResult.success_result(data=data)
        assert result.data == data
        assert isinstance(result.data, dict)

    def test_列表类型数据(self):
        """成功结果携带列表数据"""
        data = [1, 2, 3, "four"]
        result = DatabaseResult.success_result(data=data)
        assert result.data == data
        assert isinstance(result.data, list)

    def test_字符串类型数据(self):
        """成功结果携带字符串数据"""
        data = "hello world"
        result = DatabaseResult.success_result(data=data)
        assert result.data == data
        assert isinstance(result.data, str)

    def test_整数类型数据(self):
        """成功结果携带整数数据"""
        data = 42
        result = DatabaseResult.success_result(data=data)
        assert result.data == data
        assert isinstance(result.data, int)

    def test_None数据(self):
        """成功结果携带None数据"""
        result = DatabaseResult.success_result(data=None)
        assert result.data is None

    def test_布尔类型数据(self):
        """成功结果携带布尔数据"""
        result = DatabaseResult.success_result(data=True)
        assert result.data is True

    def test_嵌套复杂数据(self):
        """成功结果携带嵌套复杂数据结构"""
        data = {
            "users": [
                {"id": 1, "name": "Alice", "tags": ["admin", "active"]},
                {"id": 2, "name": "Bob", "tags": []}
            ],
            "total": 2,
            "meta": None
        }
        result = DatabaseResult.success_result(data=data)
        assert result.data == data
        assert result.data["users"][0]["tags"] == ["admin", "active"]


# ============================================================
# failure_result 工厂方法测试
# ============================================================

class TestFailureResult:
    """failure_result 工厂方法测试"""

    def test_基本失败结果(self):
        """创建基本失败结果"""
        result = DatabaseResult.failure_result(message="操作失败")
        assert result.success is False
        assert result.message == "操作失败"
        assert result.error_code == DatabaseError.UNKNOWN_ERROR.value
        assert result.data is None
        assert result.affected_rows == 0

    def test_指定错误码(self):
        """指定特定错误码"""
        result = DatabaseResult.failure_result(
            message="重复键",
            error_code=DatabaseError.DUPLICATE_KEY
        )
        assert result.error_code == DatabaseError.DUPLICATE_KEY.value

    def test_失败结果带部分数据(self):
        """失败结果可以携带部分数据"""
        result = DatabaseResult.failure_result(
            message="部分失败",
            data={"processed": 5, "failed": 2}
        )
        assert result.data == {"processed": 5, "failed": 2}

    def test_所有错误码映射(self):
        """验证所有错误码都能正确映射到 value"""
        error_mappings = [
            (DatabaseError.NOT_FOUND, "NOT_FOUND"),
            (DatabaseError.DUPLICATE_KEY, "DUPLICATE_KEY"),
            (DatabaseError.VALIDATION_ERROR, "VALIDATION_ERROR"),
            (DatabaseError.DATABASE_ERROR, "DATABASE_ERROR"),
            (DatabaseError.FOREIGN_KEY_CONSTRAINT, "FOREIGN_KEY_CONSTRAINT"),
            (DatabaseError.UNKNOWN_ERROR, "UNKNOWN_ERROR"),
        ]
        for error_enum, expected_value in error_mappings:
            result = DatabaseResult.failure_result(message="测试", error_code=error_enum)
            assert result.error_code == expected_value


# ============================================================
# not_found_result 工厂方法测试
# ============================================================

class TestNotFoundResult:
    """not_found_result 工厂方法测试"""

    def test_默认消息(self):
        """默认 not found 消息"""
        result = DatabaseResult.not_found_result()
        assert result.success is False
        assert result.message == "Record not found"
        assert result.error_code == DatabaseError.NOT_FOUND.value

    def test_自定义消息(self):
        """自定义 not found 消息"""
        result = DatabaseResult.not_found_result(message="用户不存在")
        assert result.message == "用户不存在"
        assert result.error_code == DatabaseError.NOT_FOUND.value

    def test_error_code为NOT_FOUND(self):
        """error_code 必须为 NOT_FOUND"""
        result = DatabaseResult.not_found_result()
        assert result.error_code == "NOT_FOUND"


# ============================================================
# validation_error_result 工厂方法测试
# ============================================================

class TestValidationErrorResult:
    """validation_error_result 工厂方法测试"""

    def test_创建验证错误结果(self):
        """创建验证错误结果"""
        result = DatabaseResult.validation_error_result(message="字段验证失败")
        assert result.success is False
        assert result.message == "字段验证失败"
        assert result.error_code == DatabaseError.VALIDATION_ERROR.value

    def test_error_code为VALIDATION_ERROR(self):
        """error_code 必须为 VALIDATION_ERROR"""
        result = DatabaseResult.validation_error_result(message="测试")
        assert result.error_code == "VALIDATION_ERROR"


# ============================================================
# database_error_result 工厂方法测试
# ============================================================

class TestDatabaseErrorResult:
    """database_error_result 工厂方法测试"""

    def test_创建数据库错误结果(self):
        """创建数据库错误结果"""
        result = DatabaseResult.database_error_result(message="连接超时")
        assert result.success is False
        assert result.message == "连接超时"
        assert result.error_code == DatabaseError.DATABASE_ERROR.value

    def test_error_code为DATABASE_ERROR(self):
        """error_code 必须为 DATABASE_ERROR"""
        result = DatabaseResult.database_error_result(message="测试")
        assert result.error_code == "DATABASE_ERROR"


# ============================================================
# to_dict 序列化测试
# ============================================================

class TestToDict:
    """to_dict 序列化方法测试"""

    def test_成功结果转字典(self):
        """成功结果序列化为字典"""
        result = DatabaseResult.success_result(
            data={"id": 1, "name": "test"},
            message="操作成功",
            affected_rows=1
        )
        d = result.to_dict()
        assert d == {
            "success": True,
            "data": {"id": 1, "name": "test"},
            "message": "操作成功",
            "error_code": "SUCCESS",
            "affected_rows": 1,
            "total_count": None
        }

    def test_失败结果转字典(self):
        """失败结果序列化为字典"""
        result = DatabaseResult.failure_result(
            message="记录不存在",
            error_code=DatabaseError.NOT_FOUND
        )
        d = result.to_dict()
        assert d == {
            "success": False,
            "data": None,
            "message": "记录不存在",
            "error_code": "NOT_FOUND",
            "affected_rows": 0,
            "total_count": None
        }

    def test_完整结果转字典(self):
        """包含所有字段的完整结果序列化"""
        result = DatabaseResult(
            success=True,
            data=[1, 2, 3],
            message="查询成功",
            error_code="SUCCESS",
            affected_rows=3,
            total_count=100
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["data"] == [1, 2, 3]
        assert d["message"] == "查询成功"
        assert d["error_code"] == "SUCCESS"
        assert d["affected_rows"] == 3
        assert d["total_count"] == 100

    def test_默认值转字典(self):
        """默认值结果序列化"""
        result = DatabaseResult(success=True)
        d = result.to_dict()
        assert d["data"] is None
        assert d["message"] == ""
        assert d["error_code"] is None
        assert d["affected_rows"] == 0
        assert d["total_count"] is None

    def test_to_dict返回新字典(self):
        """to_dict 应返回新字典，修改不影响原对象"""
        result = DatabaseResult.success_result(data={"a": 1})
        d = result.to_dict()
        d["success"] = False
        d["data"]["a"] = 999
        # 原对象不受影响（data是引用，但success是值类型）
        assert result.success is True
        # 注意：data 是引用类型，修改 d["data"] 会影响 result.data
        # 这是正常的 Python 行为
