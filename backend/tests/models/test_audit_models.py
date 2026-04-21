"""
TorrentAuditLog 模型单元测试

测试 TorrentAuditLog 的实例方法：
- to_dict: 转换为字典
- id 属性: 返回 log_id
- get_operation_detail_dict: 获取操作详情字典
- get_old_value_dict: 获取旧值字典
- get_new_value_dict: 获取新值字典
- set_operation_detail: 设置操作详情
- set_old_value: 设置旧值
- set_new_value: 设置新值
- _parse_json_field: 解析JSON字段（内部）
- _serialize_json_field: 序列化JSON字段（内部）

所有测试使用 __new__ + 手动属性设置绕过 ORM 初始化。
导入前需 mock app.database.SessionLocal 以避免数据库连接。
"""

from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest

# 必须在导入 audit_models 前 mock SessionLocal
with patch("app.database.SessionLocal"):
    from app.torrents.audit_models import TorrentAuditLog


# ============================================================
# 辅助工具
# ============================================================

def _make_audit_log(**kwargs):
    """创建 TorrentAuditLog 轻量级对象，绕过 ORM 初始化"""
    from unittest.mock import MagicMock

    defaults = {
        "log_id": "test-log-001",
        "torrent_info_id": "torrent-001",
        "operation_type": "add",
        "operation_detail": None,
        "old_value": None,
        "new_value": None,
        "operator": "admin",
        "operation_time": datetime(2026, 4, 3, 14, 30, 0),
        "operation_result": "success",
        "error_message": None,
        "downloader_id": "dl-001",
        "create_time": datetime(2026, 4, 3, 14, 30, 0),
        "torrent_name": "测试种子",
        "downloader_name": "测试下载器",
        "ip_address": "127.0.0.1",
        "user_agent": "Mozilla/5.0",
        "request_id": "req-001",
        "session_id": "sess-001",
    }
    defaults.update(kwargs)

    # 创建 mock 对象并设置属性
    log = MagicMock(spec=TorrentAuditLog)
    for key, value in defaults.items():
        setattr(log, key, value)

    # 绑定方法
    log.to_dict = TorrentAuditLog.to_dict.__get__(log, TorrentAuditLog)
    log.get_operation_detail_dict = TorrentAuditLog.get_operation_detail_dict.__get__(log, TorrentAuditLog)
    log.get_old_value_dict = TorrentAuditLog.get_old_value_dict.__get__(log, TorrentAuditLog)
    log.get_new_value_dict = TorrentAuditLog.get_new_value_dict.__get__(log, TorrentAuditLog)
    log.set_operation_detail = TorrentAuditLog.set_operation_detail.__get__(log, TorrentAuditLog)
    log.set_old_value = TorrentAuditLog.set_old_value.__get__(log, TorrentAuditLog)
    log.set_new_value = TorrentAuditLog.set_new_value.__get__(log, TorrentAuditLog)
    log._parse_json_field = TorrentAuditLog._parse_json_field.__get__(log, TorrentAuditLog)
    log._serialize_json_field = TorrentAuditLog._serialize_json_field.__get__(log, TorrentAuditLog)

    # id 属性
    type(log).id = property(lambda self: self.log_id)

    return log


# ============================================================
# to_dict 测试
# ============================================================

class TestAuditLogToDict:
    """to_dict 方法测试"""

    def test_返回包含所有字段(self):
        """to_dict 应返回包含所有字段的字典"""
        log = _make_audit_log()
        result = log.to_dict()

        expected_keys = {
            "log_id", "torrent_info_id", "operation_type", "operation_detail",
            "old_value", "new_value", "operator", "operation_time",
            "operation_result", "error_message", "downloader_id", "create_time",
            "torrent_name", "downloader_name", "ip_address", "user_agent",
            "request_id", "session_id",
        }
        assert set(result.keys()) == expected_keys

    def test_值正确映射(self):
        """所有字段值应正确映射"""
        log = _make_audit_log(
            operation_type="delete",
            operator="test_user",
        )
        result = log.to_dict()

        assert result["operation_type"] == "delete"
        assert result["operator"] == "test_user"


# ============================================================
# id 属性测试
# ============================================================

class TestAuditLogIdProperty:
    """id 属性测试"""

    def test_id返回log_id(self):
        """id 属性应返回 log_id"""
        log = _make_audit_log(log_id="custom-log-id")
        assert log.id == "custom-log-id"


# ============================================================
# get_operation_detail_dict 测试
# ============================================================

class TestGetOperationDetailDict:
    """get_operation_detail_dict 方法测试"""

    def test_valid_json返回字典(self):
        """有效 JSON 应返回解析后的字典"""
        log = _make_audit_log(operation_detail='{"action": "pause", "reason": "user"}')
        result = log.get_operation_detail_dict()
        assert result == {"action": "pause", "reason": "user"}

    def test_invalid_json返回空字典(self):
        """无效 JSON 应返回空字典"""
        log = _make_audit_log(operation_detail="invalid-json")
        result = log.get_operation_detail_dict()
        assert result == {}

    def test_none返回空字典(self):
        """None 应返回空字典"""
        log = _make_audit_log(operation_detail=None)
        result = log.get_operation_detail_dict()
        assert result == {}

    def test_json_array返回空字典(self):
        """JSON 数组应返回空字典（验证函数要求字典）"""
        log = _make_audit_log(operation_detail='["item1", "item2"]')
        result = log.get_operation_detail_dict()
        assert result == {}


# ============================================================
# get_old_value_dict 测试
# ============================================================

class TestGetOldValueDict:
    """get_old_value_dict 方法测试"""

    def test_valid_json返回字典(self):
        """有效 JSON 应返回解析后的字典"""
        log = _make_audit_log(old_value='{"name": "old", "size": 100}')
        result = log.get_old_value_dict()
        assert result == {"name": "old", "size": 100}

    def test_invalid_json返回空字典(self):
        """无效 JSON 应返回空字典"""
        log = _make_audit_log(old_value="invalid")
        result = log.get_old_value_dict()
        assert result == {}


# ============================================================
# get_new_value_dict 测试
# ============================================================

class TestGetNewValueDict:
    """get_new_value_dict 方法测试"""

    def test_valid_json返回字典(self):
        """有效 JSON 应返回解析后的字典"""
        log = _make_audit_log(new_value='{"name": "new", "size": 200}')
        result = log.get_new_value_dict()
        assert result == {"name": "new", "size": 200}

    def test_invalid_json返回空字典(self):
        """无效 JSON 应返回空字典"""
        log = _make_audit_log(new_value="invalid")
        result = log.get_new_value_dict()
        assert result == {}


# ============================================================
# set_operation_detail 测试
# ============================================================

class TestSetOperationDetail:
    """set_operation_detail 方法测试"""

    def test_有效字典设置成功(self):
        """有效字典应设置成功并返回 True"""
        log = _make_audit_log()
        result = log.set_operation_detail({"action": "resume"})

        assert result is True
        assert log.operation_detail == '{"action": "resume"}'

    def test_嵌套字典设置成功(self):
        """嵌套字典应正确序列化"""
        log = _make_audit_log()
        detail = {
            "action": "update",
            "changes": {"field1": "value1", "field2": "value2"}
        }
        result = log.set_operation_detail(detail)

        assert result is True
        assert '"action": "update"' in log.operation_detail

    def test_空字典设置成功(self):
        """空字典应设置成功"""
        log = _make_audit_log()
        result = log.set_operation_detail({})

        assert result is True
        assert log.operation_detail == '{}'


# ============================================================
# set_old_value 测试
# ============================================================

class TestSetOldValue:
    """set_old_value 方法测试"""

    def test_字典设置成功(self):
        """字典应正确序列化"""
        log = _make_audit_log()
        result = log.set_old_value({"status": "paused"})

        assert result is True
        assert log.old_value == '{"status": "paused"}'

    def test_列表设置成功(self):
        """列表应正确序列化"""
        log = _make_audit_log()
        result = log.set_old_value([1, 2, 3])

        assert result is True
        assert log.old_value == '[1, 2, 3]'

    def test_字符串设置成功(self):
        """字符串应正确序列化"""
        log = _make_audit_log()
        result = log.set_old_value("old_value")

        assert result is True
        assert log.old_value == '"old_value"'


# ============================================================
# set_new_value 测试
# ============================================================

class TestSetNewValue:
    """set_new_value 方法测试"""

    def test_字典设置成功(self):
        """字典应正确序列化"""
        log = _make_audit_log()
        result = log.set_new_value({"status": "seeding"})

        assert result is True
        assert log.new_value == '{"status": "seeding"}'

    def test_数字设置成功(self):
        """数字应正确序列化"""
        log = _make_audit_log()
        result = log.set_new_value(12345)

        assert result is True
        assert log.new_value == '12345'


# ============================================================
# _parse_json_field 测试（内部方法）
# ============================================================

class TestParseJsonField:
    """_parse_json_field 内部方法测试"""

    def test_有效JSON字符串(self):
        """有效 JSON 字符串应解析成功"""
        log = _make_audit_log()
        result = log._parse_json_field('{"key": "value"}', "test_field")
        assert result == {"key": "value"}

    def test_无效JSON字符串(self):
        """无效 JSON 应返回空字典"""
        log = _make_audit_log()
        result = log._parse_json_field("invalid", "test_field")
        assert result == {}

    def test_空字符串(self):
        """空字符串应返回空字典"""
        log = _make_audit_log()
        result = log._parse_json_field("", "test_field")
        assert result == {}

    def test_null输入(self):
        """None 应返回空字典"""
        log = _make_audit_log()
        result = log._parse_json_field(None, "test_field")
        assert result == {}


# ============================================================
# _serialize_json_field 测试（内部方法）
# ============================================================

class TestSerializeJsonField:
    """_serialize_json_field 内部方法测试"""

    def test_字典序列化(self):
        """字典应正确序列化"""
        log = _make_audit_log()
        result = log._serialize_json_field({"key": "value"}, "test_field")
        assert result == '{"key": "value"}'

    def test_列表序列化(self):
        """列表应正确序列化"""
        log = _make_audit_log()
        result = log._serialize_json_field([1, 2, 3], "test_field")
        assert result == '[1, 2, 3]'

    def test_none返回None(self):
        """None 应返回 None"""
        log = _make_audit_log()
        result = log._serialize_json_field(None, "test_field")
        assert result is None

    def test_不可序列化对象转为字符串(self):
        """不可序列化对象因 default=str 而转为字符串"""
        class UnserializableClass:
            pass

        log = _make_audit_log()
        obj = UnserializableClass()
        result = log._serialize_json_field(obj, "test_field")
        # default=str 会将对象转为字符串表示
        assert result is not None
        assert "UnserializableClass" in result
