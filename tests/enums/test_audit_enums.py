"""
审计日志操作类型枚举测试

测试目标模块: app.torrents.audit_enums
覆盖 AuditOperationType / AuditOperationResult 的所有枚举值和方法。
"""
import pytest

from app.torrents.audit_enums import AuditOperationType, AuditOperationResult


# ===========================================================================
# AuditOperationType 测试数据
# ===========================================================================

# (枚举值, 显示名, 分类)
AUDIT_OPERATION_TYPE_PARAMS = [
    # ---- 种子管理操作 ----
    ("add", "新增种子", "torrent"),
    ("pause", "暂停种子", "torrent"),
    ("resume", "开始种子", "torrent"),
    ("recheck", "重新检查种子", "torrent"),
    ("delete_l4", "等级4删除（待删除标签）", "torrent"),
    ("delete_l3", "等级3删除（回收站）", "torrent"),
    ("delete_l2", "等级2删除（保留数据）", "torrent"),
    ("delete_l1", "等级1删除（完全删除）", "torrent"),
    # ---- 回收站操作 ----
    ("restore", "还原种子", "recycle_bin"),
    ("cleanup_l3", "清理等级3数据", "recycle_bin"),
    ("cleanup_l4", "清理等级4数据", "recycle_bin"),
    # ---- Tracker操作 ----
    ("update_tracker", "修改Tracker", "tracker"),
    ("add_tracker", "添加Tracker", "tracker"),
    ("remove_tracker", "删除Tracker", "tracker"),
    # ---- 标签操作 ----
    ("update_tag", "修改标签", "tag"),
    ("add_tag", "添加标签", "tag"),
    ("remove_tag", "删除标签", "tag"),
    # ---- 分类操作 ----
    ("update_category", "修改分类", "tag"),
    # ---- 下载器操作 ----
    ("downloader_add", "添加下载器", "downloader"),
    ("downloader_delete", "删除下载器", "downloader"),
    ("downloader_update", "修改下载器配置", "downloader"),
    ("downloader_test", "测试下载器连接", "downloader"),
    ("sync", "同步下载器种子", "downloader"),
    # ---- 定时任务操作 ----
    ("scheduled_task_add", "添加定时任务", "scheduled_task"),
    ("scheduled_task_delete", "删除定时任务", "scheduled_task"),
    ("scheduled_task_update", "修改定时任务", "scheduled_task"),
    ("scheduled_task_enable", "启用定时任务", "scheduled_task"),
    ("scheduled_task_disable", "禁用定时任务", "scheduled_task"),
    ("scheduled_task_execute", "手动执行定时任务", "scheduled_task"),
    # ---- 关键词规则操作 ----
    ("keyword_rule_add", "添加关键词规则", "keyword_rule"),
    ("keyword_rule_delete", "删除关键词规则", "keyword_rule"),
    ("keyword_rule_update", "修改关键词规则", "keyword_rule"),
    ("keyword_rule_enable", "启用关键词规则", "keyword_rule"),
    ("keyword_rule_disable", "禁用关键词规则", "keyword_rule"),
    # ---- 系统操作 ----
    ("sync_status", "同步状态", "system"),
    ("cleanup_zombie", "清理僵尸种子", "system"),
    ("batch_operation", "批量操作", "system"),
    # ---- 归档操作 ----
    ("archive_logs", "归档审计日志", "archive"),
]

INVALID_OPERATION_TYPE_VALUES = [
    "unknown",
    "ADD",           # 大写不应匹配（枚举值是小写）
    "delete_l5",
    "",
    "pause_seed",    # 部分匹配但不存在的值
    "sync_downloader",
]


# ===========================================================================
# AuditOperationResult 测试数据
# ===========================================================================

AUDIT_OPERATION_RESULT_PARAMS = [
    ("success", "成功"),
    ("failed", "失败"),
    ("partial", "部分成功"),
]

INVALID_OPERATION_RESULT_VALUES = [
    "unknown",
    "SUCCESS",   # 大写不应匹配
    "error",
    "",
    "pending",
]


# ===========================================================================
# 测试类
# ===========================================================================


class TestAuditOperationTypeMemberCount:
    """验证 AuditOperationType 枚举成员总数正确"""

    def test_member_count(self):
        assert len(AuditOperationType) == 38


class TestAuditOperationTypeIsValid:
    """验证 AuditOperationType.is_valid 对所有合法值返回 True，对无效值返回 False"""

    @pytest.mark.parametrize("value", [p[0] for p in AUDIT_OPERATION_TYPE_PARAMS])
    def test_valid_values_return_true(self, value):
        assert AuditOperationType.is_valid(value) is True

    @pytest.mark.parametrize("value", INVALID_OPERATION_TYPE_VALUES)
    def test_invalid_values_return_false(self, value):
        assert AuditOperationType.is_valid(value) is False


class TestAuditOperationTypeGetDisplayName:
    """验证 AuditOperationType.get_display_name 返回正确的中文名称，无效值返回原值"""

    @pytest.mark.parametrize("value,expected_name", [(p[0], p[1]) for p in AUDIT_OPERATION_TYPE_PARAMS])
    def test_valid_values_return_display_name(self, value, expected_name):
        assert AuditOperationType.get_display_name(value) == expected_name

    @pytest.mark.parametrize("value", INVALID_OPERATION_TYPE_VALUES)
    def test_invalid_values_return_original_value(self, value):
        assert AuditOperationType.get_display_name(value) == value


class TestAuditOperationTypeGetCategory:
    """验证 AuditOperationType.get_category 返回正确的分类，无效值返回 None"""

    @pytest.mark.parametrize("value,expected_category", [(p[0], p[2]) for p in AUDIT_OPERATION_TYPE_PARAMS])
    def test_valid_values_return_category(self, value, expected_category):
        assert AuditOperationType.get_category(value) == expected_category

    @pytest.mark.parametrize("value", INVALID_OPERATION_TYPE_VALUES)
    def test_invalid_values_return_none(self, value):
        assert AuditOperationType.get_category(value) is None


class TestAuditOperationTypeEnumConstruction:
    """验证 AuditOperationType 枚举值可以通过字符串构造"""

    @pytest.mark.parametrize("value", [p[0] for p in AUDIT_OPERATION_TYPE_PARAMS])
    def test_construct_from_value(self, value):
        member = AuditOperationType(value)
        assert member.value == value

    @pytest.mark.parametrize("value", INVALID_OPERATION_TYPE_VALUES)
    def test_construct_invalid_raises_value_error(self, value):
        with pytest.raises(ValueError):
            AuditOperationType(value)


class TestAuditOperationTypeStrEnum:
    """验证 AuditOperationType 作为 str, Enum 的行为"""

    @pytest.mark.parametrize("value", [p[0] for p in AUDIT_OPERATION_TYPE_PARAMS])
    def test_string_comparison(self, value):
        member = AuditOperationType(value)
        assert member == value
        assert isinstance(member, str)


class TestAuditOperationResultMemberCount:
    """验证 AuditOperationResult 枚举成员总数正确"""

    def test_member_count(self):
        assert len(AuditOperationResult) == 3


class TestAuditOperationResultIsValid:
    """验证 AuditOperationResult.is_valid 对所有合法值返回 True，对无效值返回 False"""

    @pytest.mark.parametrize("value", [p[0] for p in AUDIT_OPERATION_RESULT_PARAMS])
    def test_valid_values_return_true(self, value):
        assert AuditOperationResult.is_valid(value) is True

    @pytest.mark.parametrize("value", INVALID_OPERATION_RESULT_VALUES)
    def test_invalid_values_return_false(self, value):
        assert AuditOperationResult.is_valid(value) is False


class TestAuditOperationResultGetDisplayName:
    """验证 AuditOperationResult.get_display_name 返回正确的中文名称，无效值返回原值"""

    @pytest.mark.parametrize("value,expected_name", AUDIT_OPERATION_RESULT_PARAMS)
    def test_valid_values_return_display_name(self, value, expected_name):
        assert AuditOperationResult.get_display_name(value) == expected_name

    @pytest.mark.parametrize("value", INVALID_OPERATION_RESULT_VALUES)
    def test_invalid_values_return_original_value(self, value):
        assert AuditOperationResult.get_display_name(value) == value


class TestAuditOperationResultEnumConstruction:
    """验证 AuditOperationResult 枚举值可以通过字符串构造"""

    @pytest.mark.parametrize("value", [p[0] for p in AUDIT_OPERATION_RESULT_PARAMS])
    def test_construct_from_value(self, value):
        member = AuditOperationResult(value)
        assert member.value == value

    @pytest.mark.parametrize("value", INVALID_OPERATION_RESULT_VALUES)
    def test_construct_invalid_raises_value_error(self, value):
        with pytest.raises(ValueError):
            AuditOperationResult(value)


class TestAuditOperationResultStrEnum:
    """验证 AuditOperationResult 作为 str, Enum 的行为"""

    @pytest.mark.parametrize("value", [p[0] for p in AUDIT_OPERATION_RESULT_PARAMS])
    def test_string_comparison(self, value):
        member = AuditOperationResult(value)
        assert member == value
        assert isinstance(member, str)
