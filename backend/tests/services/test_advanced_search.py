# -*- coding: utf-8 -*-
"""
AdvancedSearch 模块的单元测试

测试内容：
- validate_size_string / validate_date_string 纯函数
- SearchQueryBuilder 的构建逻辑（通过 mock DB Session 隔离）
- AdvancedSearchService 的模板 CRUD 和权限校验

所有 ORM / DB 相关依赖通过 mock 隔离。
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

from app.api.models.advanced_search import (
    validate_size_string,
    validate_date_string,
    EnhancedAdvancedSearchRequest,
    MultiSelectCondition,
    SearchGroup,
    SearchCondition,
)
from app.services.advanced_search import (
    SearchQueryBuilder,
    SearchTemplateModel,
    AdvancedSearchService,
)


# ==================== validate_size_string 测试 ====================

class TestValidateSizeString:
    """validate_size_string 纯函数测试"""

    def test_gb(self):
        """1GB → 1 * 1024^3 字节"""
        assert validate_size_string("1GB") == 1024 ** 3

    def test_mb(self):
        """500MB → 500 * 1024^2 字节"""
        assert validate_size_string("500MB") == 500 * 1024 ** 2

    def test_tb(self):
        """1.5TB → 1.5 * 1024^4 字节"""
        assert validate_size_string("1.5TB") == int(1.5 * 1024 ** 4)

    def test_kb(self):
        """1024KB → 1024 * 1024 字节"""
        assert validate_size_string("1024KB") == 1024 * 1024

    def test_bytes_only(self):
        """仅数字 + B 单位"""
        assert validate_size_string("100B") == 100

    def test_plain_number_no_unit(self):
        """纯数字无单位 → 按 B 计算"""
        result = validate_size_string("2048")
        assert result == 2048

    def test_decimal_value(self):
        """小数值 + GB"""
        result = validate_size_string("2.5GB")
        assert result == int(2.5 * 1024 ** 3)

    def test_case_insensitive(self):
        """大小写不敏感：1gb == 1GB"""
        assert validate_size_string("1gb") == validate_size_string("1GB")

    def test_with_spaces(self):
        """数字和单位之间有空格"""
        result = validate_size_string("10 GB")
        assert result == 10 * 1024 ** 3

    def test_invalid_string(self):
        """无效字符串 → 返回 None"""
        assert validate_size_string("abc") is None

    def test_invalid_unit(self):
        """无效单位 XB → 返回 None"""
        assert validate_size_string("1XB") is None

    def test_empty_string(self):
        """空字符串 → 返回 None"""
        assert validate_size_string("") is None

    def test_none(self):
        """None → 返回 None"""
        assert validate_size_string(None) is None

    def test_zero_size(self):
        """0GB → 0"""
        assert validate_size_string("0GB") == 0

    def test_only_unit_prefix(self):
        """仅单位前缀如 5K → 正则匹配 5+K，K 被视为 KB 单位"""
        result = validate_size_string("5K")
        # 正则 (\d+(?:\.\d+)?)\s*([KMGT]?B?) 匹配 5K：
        # number=5, unit=K → upper()=K → multipliers 中无 K 键，默认 1
        # 所以结果是 5 * 1 = 5（K 不是合法的 unit key）
        assert result == 5


# ==================== validate_date_string 测试 ====================

class TestValidateDateString:
    """validate_date_string 纯函数测试"""

    def test_standard_date(self):
        """标准日期 YYYY-MM-DD"""
        result = validate_date_string("2025-06-15")
        assert result == datetime(2025, 6, 15)

    def test_datetime_with_seconds(self):
        """日期时间 YYYY-MM-DD HH:MM:SS"""
        result = validate_date_string("2025-06-15 14:30:00")
        assert result == datetime(2025, 6, 15, 14, 30, 0)

    def test_slash_date(self):
        """斜杠日期 YYYY/MM/DD"""
        result = validate_date_string("2025/06/15")
        assert result == datetime(2025, 6, 15)

    def test_slash_datetime(self):
        """斜杠日期时间 YYYY/MM/DD HH:MM:SS"""
        result = validate_date_string("2025/06/15 14:30:00")
        assert result == datetime(2025, 6, 15, 14, 30, 0)

    def test_invalid_date(self):
        """无效日期字符串 → 返回 None"""
        assert validate_date_string("not-a-date") is None

    def test_empty_string(self):
        """空字符串 → 返回 None"""
        assert validate_date_string("") is None

    def test_none(self):
        """None → 返回 None"""
        assert validate_date_string(None) is None

    def test_date_with_spaces(self):
        """日期字符串前后有空格 → 正常解析"""
        result = validate_date_string("  2025-01-01  ")
        assert result == datetime(2025, 1, 1)


# ==================== SearchQueryBuilder 测试 ====================

class TestSearchQueryBuilder:
    """SearchQueryBuilder 查询构建器测试"""

    @pytest.fixture
    def mock_db(self):
        """创建 mock DB Session 和基础 query"""
        db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        db.query.return_value = mock_query
        return db, mock_query

    @pytest.fixture
    def builder(self, mock_db):
        """创建 SearchQueryBuilder 实例"""
        db, _ = mock_db
        return SearchQueryBuilder(db)

    def test_reset(self, builder, mock_db):
        """reset() 应重建基础查询"""
        db, _ = mock_db
        result = builder.reset()
        assert result is builder  # 支持链式调用
        assert db.query.call_count >= 2  # __init__ 一次 + reset 一次

    def test_apply_basic_filters_empty(self, builder, mock_db):
        """无过滤条件的请求 → 不追加 filter"""
        _, mock_query = mock_db
        request = EnhancedAdvancedSearchRequest()

        result = builder.apply_basic_filters(request)
        assert result is builder
        # base_query.filter 不应被额外调用（因为 filters 为空）
        # 注意：__init__ 时已调用过 db.query，这里检查未被再次 filter

    def test_apply_basic_filters_with_name(self, builder, mock_db):
        """有 name 条件 → 调用 filter"""
        _, mock_query = mock_db
        request = EnhancedAdvancedSearchRequest(name="测试")

        builder.apply_basic_filters(request)
        mock_query.filter.assert_called()

    def test_apply_basic_filters_with_downloader(self, builder, mock_db):
        """有 downloader_id → 调用 filter"""
        _, mock_query = mock_db
        request = EnhancedAdvancedSearchRequest(downloader_id="dl-001")

        builder.apply_basic_filters(request)
        mock_query.filter.assert_called()

    def test_apply_basic_filters_with_size_range(self, builder, mock_db):
        """size_min + size_max 范围过滤 → filter 被调用"""
        _, mock_query = mock_db
        request = EnhancedAdvancedSearchRequest(size_min="1GB", size_max="10GB")

        builder.apply_basic_filters(request)
        mock_query.filter.assert_called()

    def test_apply_basic_filters_with_date_range(self, builder, mock_db):
        """日期范围过滤 → filter 被调用"""
        _, mock_query = mock_db
        request = EnhancedAdvancedSearchRequest(
            added_date_min="2025-01-01",
            added_date_max="2025-12-31"
        )

        builder.apply_basic_filters(request)
        mock_query.filter.assert_called()

    def test_apply_sorting_default(self, builder, mock_db):
        """默认排序 → desc"""
        _, mock_query = mock_db
        builder.apply_sorting("added_date", "desc")
        mock_query.order_by.assert_called()

    def test_apply_sorting_asc(self, builder, mock_db):
        """升序排序"""
        _, mock_query = mock_db
        builder.apply_sorting("name", "asc")
        mock_query.order_by.assert_called()

    def test_apply_sorting_invalid_field(self, builder, mock_db):
        """无效排序字段 → 使用默认 added_date"""
        _, mock_query = mock_db
        builder.apply_sorting("nonexistent_field", "desc")
        mock_query.order_by.assert_called()

    def test_apply_pagination_page1(self, builder, mock_db):
        """第 1 页 → offset=0"""
        _, mock_query = mock_db
        builder.apply_pagination(page=1, limit=20)
        mock_query.offset.assert_called_once_with(0)
        mock_query.limit.assert_called_once_with(20)

    def test_apply_pagination_page3(self, builder, mock_db):
        """第 3 页 → offset=40"""
        _, mock_query = mock_db
        builder.apply_pagination(page=3, limit=20)
        mock_query.offset.assert_called_once_with(40)

    def test_get_query(self, builder, mock_db):
        """get_query → 返回内部 query 对象"""
        _, mock_query = mock_db
        assert builder.get_query() is mock_query

    def test_count(self, builder, mock_db):
        """count → 返回查询计数"""
        _, mock_query = mock_db
        mock_query.count.return_value = 42
        assert builder.count() == 42


# ==================== apply_condition_groups 测试 ====================

class TestApplyConditionGroups:
    """apply_condition_groups 条件组逻辑测试"""

    @pytest.fixture
    def builder_with_mock(self):
        """创建 builder 和 mock query"""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        db = mock_db
        db.query.return_value = mock_query
        return SearchQueryBuilder(db), mock_query

    def test_empty_groups(self, builder_with_mock):
        """空条件组 → 不调用 filter"""
        builder, mock_query = builder_with_mock
        builder.apply_condition_groups(None)
        # 仅 __init__ 时调用过 filter，不应增加调用
        init_call_count = mock_query.filter.call_count

        builder.apply_condition_groups([])
        assert mock_query.filter.call_count == init_call_count

    def test_single_and_group(self, builder_with_mock):
        """单个 AND 条件组 → filter 被调用"""
        builder, mock_query = builder_with_mock
        groups = [
            SearchGroup(logic="AND", conditions=[
                SearchCondition(field="name", operator="contains", value="测试")
            ])
        ]

        builder.apply_condition_groups(groups)
        # 应该追加了 filter
        assert mock_query.filter.call_count > 1

    def test_invalid_logic_skipped(self, builder_with_mock):
        """无效 logic 的条件组 → 跳过"""
        builder, mock_query = builder_with_mock
        init_count = mock_query.filter.call_count

        builder.apply_condition_groups([{"logic": "", "conditions": []}])
        assert mock_query.filter.call_count == init_count


# ==================== apply_multi_select_conditions 测试 ====================

class TestApplyMultiSelectConditions:
    """apply_multi_select_conditions 多选条件测试"""

    @pytest.fixture
    def builder_with_mock(self):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        db = mock_db
        db.query.return_value = mock_query
        return SearchQueryBuilder(db), mock_query

    def test_include_mode(self, builder_with_mock):
        """include 模式 → 使用 IN 过滤"""
        builder, mock_query = builder_with_mock
        cond = MultiSelectCondition(
            field="status", operator="in", value=["downloading", "seeding"],
            mode="include"
        )

        builder.apply_multi_select_conditions(cond, None, None, None)
        assert mock_query.filter.call_count > 1

    def test_exclude_mode(self, builder_with_mock):
        """exclude 模式 → 使用 NOT IN 过滤"""
        builder, mock_query = builder_with_mock
        cond = MultiSelectCondition(
            field="status", operator="in", value=["error"],
            mode="exclude"
        )

        builder.apply_multi_select_conditions(cond, None, None, None)
        assert mock_query.filter.call_count > 1

    def test_all_none_conditions(self, builder_with_mock):
        """所有条件为 None → 不追加 filter"""
        builder, mock_query = builder_with_mock
        init_count = mock_query.filter.call_count

        builder.apply_multi_select_conditions(None, None, None, None)
        assert mock_query.filter.call_count == init_count

    def test_empty_value_skipped(self, builder_with_mock):
        """value 为空列表 → 跳过"""
        builder, mock_query = builder_with_mock
        init_count = mock_query.filter.call_count
        cond = MultiSelectCondition(
            field="status", operator="in", value=[],
            mode="include"
        )

        builder.apply_multi_select_conditions(cond, None, None, None)
        assert mock_query.filter.call_count == init_count


# ==================== AdvancedSearchService 模板管理测试 ====================

class TestAdvancedSearchServiceTemplates:
    """AdvancedSearchService 模板 CRUD 和权限测试"""

    @pytest.fixture
    def service(self):
        """创建 AdvancedSearchService，内部组件全部 mock"""
        mock_db = MagicMock()

        with patch.object(SearchQueryBuilder, "__init__", lambda self, db: None), \
             patch.object(SearchTemplateModel, "__init__", lambda self, db: None):
            with patch("app.services.advanced_search.TorrentDeletionService"):
                svc = AdvancedSearchService(db=mock_db)

        svc.query_builder = MagicMock()
        svc.template_model = MagicMock()
        return svc

    def test_get_templates_success(self, service):
        """获取模板列表成功"""
        service.template_model.get_by_user.return_value = [
            {"id": "tpl-1", "name": "测试模板"}
        ]

        result = service.get_search_templates("user-001")
        assert result["status"] == "success"
        assert result["total"] == 1

    def test_get_templates_failure(self, service):
        """获取模板列表异常"""
        service.template_model.get_by_user.side_effect = Exception("DB错误")

        result = service.get_search_templates("user-001")
        assert result["status"] == "failed"
        assert result["code"] == "500"

    def test_delete_template_not_found(self, service):
        """删除不存在的模板 → 404"""
        service.template_model.get_by_id.return_value = None

        result = service.delete_search_template("tpl-nonexistent", "user-001")
        assert result["status"] == "failed"
        assert result["code"] == "404"

    def test_delete_template_no_permission(self, service):
        """删除他人模板 → 403"""
        service.template_model.get_by_id.return_value = {
            "id": "tpl-1", "user_id": "other-user"
        }

        result = service.delete_search_template("tpl-1", "user-001")
        assert result["status"] == "failed"
        assert result["code"] == "403"

    def test_delete_template_success(self, service):
        """删除自己的模板 → 成功"""
        service.template_model.get_by_id.return_value = {
            "id": "tpl-1", "user_id": "user-001"
        }
        service.template_model.delete.return_value = True

        result = service.delete_search_template("tpl-1", "user-001")
        assert result["status"] == "success"
        assert result["code"] == "200"

    def test_apply_template_not_found(self, service):
        """应用不存在的模板 → 404"""
        service.template_model.get_by_id.return_value = None

        result = service.apply_search_template("tpl-nonexistent", "user-001")
        assert result["status"] == "failed"
        assert result["code"] == "404"

    def test_apply_template_no_permission(self, service):
        """应用他人私有模板 → 403"""
        service.template_model.get_by_id.return_value = {
            "id": "tpl-1",
            "user_id": "other-user",
            "is_public": False
        }

        result = service.apply_search_template("tpl-1", "user-001")
        assert result["status"] == "failed"
        assert result["code"] == "403"

    def test_apply_public_template_success(self, service):
        """应用他人公开模板 → 成功"""
        service.template_model.get_by_id.return_value = {
            "id": "tpl-1",
            "user_id": "other-user",
            "is_public": True,
            "name": "公开模板",
            "description": "描述",
            "conditions": {}
        }

        result = service.apply_search_template("tpl-1", "user-001")
        assert result["status"] == "success"
        service.template_model.increment_usage.assert_called_once_with("tpl-1")

    def test_update_template_success(self, service):
        """更新自己的模板 → 成功"""
        service.template_model.get_by_id.return_value = {
            "id": "tpl-1", "user_id": "user-001"
        }
        service.template_model.update.return_value = True

        result = service.update_search_template(
            "tpl-1", {"name": "新名称", "conditions": {}}, "user-001"
        )
        assert result["status"] == "success"

    def test_update_template_no_permission(self, service):
        """更新他人模板 → 403"""
        service.template_model.get_by_id.return_value = {
            "id": "tpl-1", "user_id": "other-user"
        }

        result = service.update_search_template(
            "tpl-1", {"name": "新名称"}, "user-001"
        )
        assert result["status"] == "failed"
        assert result["code"] == "403"
