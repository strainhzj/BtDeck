#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级搜索API模型 - 任务1.1.2
支持13字段全字段搜索和多选排除功能
"""

import json
import math
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import datetime
import re

from app.contracts.advanced_search import (
    FRONTEND_TO_BACKEND_OPERATOR,
    MAX_REGEX_CONDITIONS,
    MAX_REGEX_PATTERN_LENGTH,
    NEGATED_SEARCH_OPERATORS,
    SEARCH_FIELD_CONTRACT,
    SUPPORTED_SEARCH_OPERATORS,
    allowed_operators_for_field,
    field_kind,
)
from app.services.sqlite_search_runtime import validate_regex_pattern

_SCALAR_TEXT_OPERATORS = {
    "eq",
    "ne",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "not_starts_with",
    "not_ends_with",
}
_LIST_OPERATORS = {
    "in",
    "not_in",
    "contains_any",
    "contains_all",
    "not_contains_any",
    "not_contains_all",
}
_SCALAR_COMPARISON_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte"}
_DATE_FIELDS = {"added_date", "added_time", "completed_date"}


def _finite_non_negative_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} requires a number, not bool")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} requires a finite number") from exc
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field} requires a finite non-negative number")
    return numeric


def _parse_size_value(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("size requires a number with an optional unit")
    if isinstance(value, (int, float)):
        numeric = _finite_non_negative_number(value, field="size")
        return int(numeric)
    if not isinstance(value, str):
        raise ValueError("size requires a number with an optional unit")
    parsed = validate_size_string(value)
    if parsed is None:
        raise ValueError(f"invalid size value: {value!r}")
    return parsed


def _parse_date_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            raise ValueError("timezone-aware dates are not supported")
        return value
    if not isinstance(value, str):
        raise ValueError("date value must be a string")
    parsed = validate_date_string(value)
    if parsed is None:
        raise ValueError(f"invalid date value: {value!r}")
    return parsed


def _object_value(value: Any, *, operator: str) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{operator} requires a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{operator} requires an object value")
    return dict(value)


def _normalize_range_value(field: str, value: Any) -> Dict[str, Any]:
    value_dict = _object_value(value, operator="between")
    allowed_keys = {"min", "max", "start", "end", "minUnit", "maxUnit"}
    unknown = set(value_dict) - allowed_keys
    if unknown:
        raise ValueError(f"between contains unknown keys: {sorted(unknown)}")

    lower: datetime | int | float | None
    upper: datetime | int | float | None
    if field in _DATE_FIELDS:
        lower_raw = value_dict.get("start", value_dict.get("min"))
        upper_raw = value_dict.get("end", value_dict.get("max"))
        lower = _parse_date_value(lower_raw) if lower_raw is not None else None
        upper = _parse_date_value(upper_raw) if upper_raw is not None else None
        normalized = {
            "start": lower_raw if lower is not None else None,
            "end": upper_raw if upper is not None else None,
        }
    else:
        lower_raw = value_dict.get("min")
        upper_raw = value_dict.get("max")
        if field == "size":
            lower = _parse_size_value(lower_raw) if lower_raw is not None else None
            upper = _parse_size_value(upper_raw) if upper_raw is not None else None
        else:
            lower = _finite_non_negative_number(lower_raw, field=field) if lower_raw is not None else None
            upper = _finite_non_negative_number(upper_raw, field=field) if upper_raw is not None else None
        normalized = {"min": lower, "max": upper}

    if lower is None and upper is None:
        raise ValueError("between requires at least one boundary")
    if lower is not None and upper is not None:
        if field in _DATE_FIELDS:
            assert isinstance(lower, datetime)
            assert isinstance(upper, datetime)
            reversed_boundaries = lower > upper
        else:
            assert isinstance(lower, (int, float))
            assert isinstance(upper, (int, float))
            reversed_boundaries = lower > upper
        if reversed_boundaries:
            raise ValueError("between lower boundary must not exceed upper boundary")
    return normalized


def _normalize_condition_value(field: str, operator: str, value: Any) -> Any:
    kind = field_kind(field)
    if operator in {"is_null", "is_not_null"}:
        return None
    if operator == "between":
        return _normalize_range_value(field, value)
    if operator == "regex":
        pattern: Any
        case_sensitive: Any
        if isinstance(value, str):
            pattern = value
            case_sensitive = True
        else:
            value_dict = _object_value(value, operator="regex")
            unknown = set(value_dict) - {"pattern", "caseSensitive"}
            if unknown:
                raise ValueError(f"regex contains unknown keys: {sorted(unknown)}")
            pattern = value_dict.get("pattern")
            case_sensitive = value_dict.get("caseSensitive", False)
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("regex pattern must be a non-empty string")
        if len(pattern) > MAX_REGEX_PATTERN_LENGTH:
            raise ValueError(f"regex pattern exceeds {MAX_REGEX_PATTERN_LENGTH} characters")
        if not isinstance(case_sensitive, bool):
            raise ValueError("regex caseSensitive must be boolean")
        validate_regex_pattern(pattern, case_sensitive=case_sensitive)
        return {"pattern": pattern, "caseSensitive": case_sensitive}
    if operator == "last_days":
        value_dict = _object_value(value, operator="last_days")
        if set(value_dict) != {"days"}:
            raise ValueError("last_days requires exactly the days field")
        days = value_dict["days"]
        if isinstance(days, bool):
            raise ValueError("last_days days must be an integer")
        try:
            days_int = int(days)
        except (TypeError, ValueError) as exc:
            raise ValueError("last_days days must be an integer") from exc
        if days_int < 1 or days_int > 36500:
            raise ValueError("last_days days must be between 1 and 36500")
        return {"days": days_int}
    if operator == "date_range":
        value_dict = _object_value(value, operator="date_range")
        unknown = set(value_dict) - {"start", "end"}
        if unknown:
            raise ValueError(f"date_range contains unknown keys: {sorted(unknown)}")
        start_raw = value_dict.get("start")
        end_raw = value_dict.get("end")
        start = _parse_date_value(start_raw) if start_raw is not None else None
        end = _parse_date_value(end_raw) if end_raw is not None else None
        if start is None and end is None:
            raise ValueError("date_range requires at least one boundary")
        if start is not None and end is not None and start > end:
            raise ValueError("date_range start must not exceed end")
        return {"start": start_raw, "end": end_raw}
    if operator in _LIST_OPERATORS:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, (list, tuple)):
            items = [
                str(item).strip() for item in value if not isinstance(item, (dict, list, tuple)) and str(item).strip()
            ]
        else:
            raise ValueError(f"{operator} requires a list or comma-separated string")
        if not items:
            raise ValueError(f"{operator} requires at least one value")
        return items
    if field == "super_seeding":
        normalized = str(value).strip().lower()
        if normalized in {"1", "true"}:
            return "1"
        if normalized in {"0", "false"}:
            return "0"
        if normalized in {"unsupported", "unknown"}:
            return "unsupported"
        raise ValueError("super_seeding requires true, false or unsupported")
    if kind == "number" and operator in _SCALAR_COMPARISON_OPERATORS:
        return _parse_size_value(value) if field == "size" else _finite_non_negative_number(value, field=field)
    if kind == "date" and operator in _SCALAR_COMPARISON_OPERATORS:
        _parse_date_value(value)
        return value
    if kind == "boolean":
        if isinstance(value, bool):
            return "1" if value else "0"
        if value in (0, "0", "false", "False"):
            return "0"
        if value in (1, "1", "true", "True"):
            return "1"
        raise ValueError(f"{field} requires a boolean value")
    if operator in _SCALAR_TEXT_OPERATORS:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{operator} requires a non-empty string")
        return value
    raise ValueError(f"unsupported value shape for {field} {operator}")


class SearchCondition(BaseModel):
    """搜索条件基类"""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(..., description="搜索字段", examples=["name"])
    operator: str = Field(..., description="操作符", examples=["contains"])
    value: Any = Field(..., description="搜索值", examples=["电影"])
    mode: Literal["include", "exclude"] = Field(
        "include",
        description="条件模式；exclude 表示对当前操作符的完整结果取严格补集",
    )

    @model_validator(mode="after")
    def validate_field_operator_and_value(self):
        if self.field not in SEARCH_FIELD_CONTRACT:
            raise ValueError(f"unknown search field: {self.field}")
        if self.operator not in SUPPORTED_SEARCH_OPERATORS:
            raise ValueError(f"unknown search operator: {self.operator}")
        if self.field == "tags":
            self.operator = {
                "eq": "contains_any",
                "contains": "contains_any",
                "in": "contains_any",
                "ne": "not_contains_any",
                "not_contains": "not_contains_any",
                "not_in": "not_contains_any",
            }.get(self.operator, self.operator)
        allowed = allowed_operators_for_field(self.field)
        if self.operator not in allowed:
            raise ValueError(f"operator {self.operator!r} is not allowed for field {self.field!r}")
        if self.mode == "exclude" and self.operator not in NEGATED_SEARCH_OPERATORS:
            raise ValueError(f"operator {self.operator!r} does not support exclude mode")
        self.value = _normalize_condition_value(self.field, self.operator, self.value)
        return self


class SearchTemplate(BaseModel):
    """搜索模板"""

    id: Optional[str] = None
    user_id: str = Field(..., description="用户ID")
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    description: Optional[str] = Field(default=None, max_length=500, description="模板描述")
    conditions: List[Dict[str, Any]] = Field(..., description="搜索条件JSON")
    is_default: bool = Field(default=False, description="是否默认模板")
    is_public: bool = Field(default=False, description="是否公开模板")
    usage_count: int = Field(default=0, description="使用次数")
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class SearchGroup(BaseModel):
    """搜索条件组"""

    model_config = ConfigDict(extra="forbid")

    logic: Literal["AND", "OR"] = Field("AND", description="组内逻辑关系")
    conditions: List[SearchCondition] = Field(..., min_length=1, max_length=50, description="组内条件列表")

    @field_validator("logic", mode="before")
    @classmethod
    def normalize_logic(cls, value):
        return value.upper() if isinstance(value, str) else value


class EnhancedAdvancedSearchRequest(BaseModel):
    """增强高级搜索请求"""

    model_config = ConfigDict(extra="forbid")

    # 基础分页参数
    page: int = Field(default=1, ge=1, le=1000, description="页码", examples=[1])
    limit: int = Field(default=20, ge=1, le=100000, description="每页数量", examples=[20])
    sort_by: str = Field("added_time", description="排序字段", examples=["added_time"])
    sort_order: Literal["asc", "desc"] = Field("desc", description="排序方向", examples=["desc"])

    # 基础过滤条件
    downloader_id: Optional[str] = Field(default=None, description="下载器ID", examples=[""])
    downloader_name: Optional[str] = Field(default=None, description="下载器名称", examples=[""])
    name: Optional[str] = Field(default=None, description="种子名称", examples=[""])
    tags: Optional[str] = Field(default=None, description="标签", examples=[""])
    category: Optional[str] = Field(default=None, description="分类", examples=[""])
    status: Optional[str] = Field(default=None, description="状态", examples=[""])

    # 数值范围过滤
    size_min: Optional[str] = Field(default=None, description="种子大小最小值", examples=["1GB"])
    size_max: Optional[str] = Field(default=None, description="种子大小最大值", examples=["10GB"])
    ratio_min: Optional[float] = Field(default=None, ge=0, description="分享比率最小值", examples=[0.5])
    ratio_max: Optional[float] = Field(default=None, ge=0, description="分享比率最大值", examples=[2.0])

    # 日期范围过滤
    added_date_min: Optional[str] = Field(default=None, description="添加时间最小值", examples=["2025-01-01"])
    added_date_max: Optional[str] = Field(default=None, description="添加时间最大值", examples=["2025-12-31"])
    completed_date_min: Optional[str] = Field(default=None, description="完成时间最小值", examples=["2025-01-01"])
    completed_date_max: Optional[str] = Field(default=None, description="完成时间最大值", examples=["2025-12-31"])

    # 高级搜索条件组
    condition_groups: Optional[List[SearchGroup]] = Field(default=None, description="条件组列表")
    between_group_logics: Optional[List[Literal["AND", "OR"]]] = Field(
        default=None, description="条件组之间的逻辑关系列表"
    )

    @field_validator("between_group_logics", mode="before")
    @classmethod
    def normalize_between_group_logics(cls, value):
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("between_group_logics must be a list")
        return [item.upper() if isinstance(item, str) else item for item in value]

    @model_validator(mode="after")
    def validate_request_semantics(self):
        allowed_sort_fields = {
            "info_id",
            "downloader_id",
            "downloader_name",
            "torrent_id",
            "hash",
            "name",
            "save_path",
            "size",
            "status",
            "torrent_file",
            "added_date",
            "added_time",
            "completed_date",
            "ratio",
            "ratio_limit",
            "tags",
            "category",
            "super_seeding",
            "enabled",
        }
        if self.sort_by not in allowed_sort_fields:
            raise ValueError(f"unknown sort field: {self.sort_by}")

        size_min = _parse_size_value(self.size_min) if self.size_min is not None else None
        size_max = _parse_size_value(self.size_max) if self.size_max is not None else None
        if size_min is not None and size_max is not None and size_min > size_max:
            raise ValueError("size_min must not exceed size_max")

        for field_name in (
            "added_date_min",
            "added_date_max",
            "completed_date_min",
            "completed_date_max",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _parse_date_value(value)
        for lower_name, upper_name in (
            ("added_date_min", "added_date_max"),
            ("completed_date_min", "completed_date_max"),
        ):
            lower_raw = getattr(self, lower_name)
            upper_raw = getattr(self, upper_name)
            if (
                lower_raw is not None
                and upper_raw is not None
                and _parse_date_value(lower_raw) > _parse_date_value(upper_raw)
            ):
                raise ValueError(f"{lower_name} must not exceed {upper_name}")

        for field_name in ("ratio_min", "ratio_max"):
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, bool) or not math.isfinite(float(value))):
                raise ValueError(f"{field_name} must be finite")
        if self.ratio_min is not None and self.ratio_max is not None and self.ratio_min > self.ratio_max:
            raise ValueError("ratio_min must not exceed ratio_max")

        groups = self.condition_groups or []
        expected_logic_count = max(0, len(groups) - 1)
        actual_logic_count = len(self.between_group_logics or [])
        if actual_logic_count != expected_logic_count:
            raise ValueError("between_group_logics length must equal condition_groups length - 1")
        regex_count = sum(condition.operator == "regex" for group in groups for condition in group.conditions)
        if regex_count > MAX_REGEX_CONDITIONS:
            raise ValueError(f"at most {MAX_REGEX_CONDITIONS} regex conditions are allowed")
        return self


def _template_condition_for_validation(raw: Any) -> SearchCondition:
    if not isinstance(raw, dict):
        raise ValueError("template condition must be an object")
    allowed_keys = {"id", "field", "operator", "value", "mode", "index"}
    unknown = set(raw) - allowed_keys
    if unknown:
        raise ValueError(f"template condition contains unknown keys: {sorted(unknown)}")
    if not {"field", "operator", "value"} <= set(raw):
        raise ValueError("template condition requires field, operator and value")
    field = raw["field"]
    frontend_operator = raw["operator"]
    if not isinstance(field, str):
        raise ValueError("template condition field must be a string")
    if not isinstance(frontend_operator, str):
        raise ValueError("template condition operator must be a string")
    operator = FRONTEND_TO_BACKEND_OPERATOR.get(frontend_operator, frontend_operator)
    mode = raw.get("mode", "include")
    if mode not in {"include", "exclude"}:
        raise ValueError("template condition mode must be include or exclude")
    if mode == "exclude" and operator not in NEGATED_SEARCH_OPERATORS:
        raise ValueError(f"operator {frontend_operator!r} does not support exclude mode")
    value = raw.get("value")
    if field == "size" and operator != "between" and isinstance(value, dict):
        numeric = value.get("value", value.get("min"))
        unit = value.get("unit", value.get("minUnit", "GB"))
        value = f"{numeric} {unit}" if numeric is not None else None
    elif field == "size" and operator == "between" and isinstance(value, dict):
        value = {
            "min": (f"{value.get('min')} {value.get('minUnit', 'GB')}" if value.get("min") is not None else None),
            "max": (f"{value.get('max')} {value.get('maxUnit', 'GB')}" if value.get("max") is not None else None),
        }
    return SearchCondition.model_validate({"field": field, "operator": operator, "value": value, "mode": mode})


def validate_template_conditions_payload(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("template conditions must be an object")
    source = value.get("source")
    if source == "simple":
        if not isinstance(value.get("listQuery"), dict):
            raise ValueError("simple template requires a listQuery object")
        return value
    if source != "advanced":
        raise ValueError("template source must be simple or advanced")
    allowed_top_level = {
        "source",
        "version",
        "condition_groups",
        "sort_by",
        "sort_order",
    }
    unknown_top_level = set(value) - allowed_top_level
    if unknown_top_level:
        raise ValueError(f"advanced template contains unknown keys: {sorted(unknown_top_level)}")
    groups = value.get("condition_groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("advanced template requires condition_groups")
    validated_groups = []
    between_group_logics = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError("template condition group must be an object")
        allowed_group_keys = {
            "id",
            "name",
            "logic",
            "betweenGroupLogic",
            "editing",
            "conditions",
        }
        unknown_group_keys = set(group) - allowed_group_keys
        if unknown_group_keys:
            raise ValueError("template condition group contains unknown keys: " f"{sorted(unknown_group_keys)}")
        if "logic" not in group:
            raise ValueError("template condition group requires explicit logic")
        logic = group["logic"]
        conditions = group.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise ValueError("template condition group requires conditions")
        validated_groups.append(
            SearchGroup.model_validate(
                {
                    "logic": logic,
                    "conditions": [
                        _template_condition_for_validation(condition).model_dump() for condition in conditions
                    ],
                }
            )
        )
        if group_index < len(groups) - 1:
            between_logic = group.get("betweenGroupLogic")
            if not isinstance(between_logic, str):
                raise ValueError("non-final template condition groups require " "betweenGroupLogic")
            between_group_logics.append(between_logic.upper())

    EnhancedAdvancedSearchRequest.model_validate(
        {
            "condition_groups": [group.model_dump() for group in validated_groups],
            "between_group_logics": between_group_logics,
            "sort_by": value.get("sort_by", "added_time"),
            "sort_order": value.get("sort_order", "desc"),
        }
    )
    return value


class SearchTemplateCreate(BaseModel):
    """创建搜索模板请求"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    description: Optional[str] = Field(default=None, max_length=500, description="模板描述")
    conditions: Dict[str, Any] = Field(..., description="搜索条件")
    is_public: bool = Field(default=False, description="是否公开模板")

    @field_validator("conditions")
    @classmethod
    def validate_conditions(cls, value):
        return validate_template_conditions_payload(value)


class SearchTemplateUpdate(BaseModel):
    """更新搜索模板请求"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="模板ID")
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="模板名称")
    description: Optional[str] = Field(default=None, max_length=500, description="模板描述")
    conditions: Optional[Dict[str, Any]] = Field(default=None, description="搜索条件")
    is_public: Optional[bool] = Field(default=None, description="是否公开模板")

    @field_validator("conditions")
    @classmethod
    def validate_conditions(cls, value):
        if value is None:
            return value
        return validate_template_conditions_payload(value)


class SearchTemplateResponse(BaseModel):
    """搜索模板响应"""

    id: str = Field(..., description="模板ID")
    user_id: str = Field(..., description="用户ID")
    name: str = Field(..., description="模板名称")
    description: Optional[str] = Field(default=None, description="模板描述")
    conditions: Dict[str, Any] = Field(..., description="搜索条件")
    is_default: bool = Field(..., description="是否默认模板")
    is_public: bool = Field(..., description="是否公开模板")
    usage_count: int = Field(..., description="使用次数")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: Optional[datetime] = Field(default=None, description="更新时间")


class SearchTemplateDelete(BaseModel):
    """删除搜索模板请求"""

    template_id: str = Field(..., description="模板ID")


class AdvancedSearchResponse(BaseModel):
    """高级搜索响应"""

    total: int = Field(..., description="总记录数", examples=[1000])
    page: int = Field(..., description="当前页码", examples=[1])
    limit: int = Field(..., description="每页数量", examples=[20])
    total_pages: int = Field(..., description="总页数", examples=[50])
    data: List[Dict[str, Any]] = Field(..., description="搜索结果列表")


class TorrentDeleteRequest(BaseModel):
    """批量删除种子请求"""

    torrent_ids: List[str] = Field(..., min_length=1, max_length=100, description="种子ID列表")
    delete_data: bool = Field(default=True, description="是否删除数据文件", examples=[True])
    id_recycle: bool = Field(default=False, description="是否进入回收箱", examples=[False])


class SearchStatisticsResponse(BaseModel):
    """搜索统计响应"""

    field_distribution: Dict[str, int] = Field(..., description="字段分布统计")
    operator_usage: Dict[str, int] = Field(..., description="操作符使用统计")
    search_performance: Dict[str, float] = Field(..., description="搜索性能统计")


# 字段映射定义
SEARCH_FIELDS = {
    "info_id": {"name": "种子ID", "type": "string", "searchable": True},
    "downloader_id": {"name": "下载器ID", "type": "string", "searchable": True},
    "downloader_name": {"name": "下载器名称", "type": "string", "searchable": True},
    "torrent_id": {"name": "种子内部ID", "type": "string", "searchable": True},
    "hash": {"name": "哈希值", "type": "string", "searchable": True},
    "name": {"name": "种子名称", "type": "string", "searchable": True},
    "save_path": {"name": "保存路径", "type": "string", "searchable": True},
    "size": {"name": "种子大小", "type": "float", "searchable": True, "range_filter": True},
    "status": {"name": "状态", "type": "string", "searchable": True, "multi_select": True},
    "torrent_file": {"name": "种子文件", "type": "string", "searchable": False},
    "added_date": {"name": "添加时间", "type": "datetime", "searchable": True, "range_filter": True},
    "completed_date": {"name": "完成时间", "type": "datetime", "searchable": True, "range_filter": True},
    "ratio": {"name": "分享比率", "type": "float", "searchable": True, "range_filter": True},
    "ratio_limit": {"name": "比率限制", "type": "float", "searchable": True, "range_filter": True},
    "tags": {"name": "标签", "type": "string", "searchable": True, "multi_select": True},
    "category": {"name": "分类", "type": "string", "searchable": True, "multi_select": True},
    "super_seeding": {"name": "超级做种", "type": "string", "searchable": True},
    "enabled": {"name": "启用状态", "type": "boolean", "searchable": True},
    "dr": {"name": "删除状态", "type": "integer", "searchable": False},
}

# 操作符映射定义
SEARCH_OPERATORS = {
    # 字符串操作符
    "eq": "=",
    "ne": "!=",
    "contains": "LIKE",
    "not_contains": "NOT LIKE",
    "starts_with": "LIKE",
    "ends_with": "LIKE",
    "not_starts_with": "NOT LIKE",
    "not_ends_with": "NOT LIKE",
    "in": "IN",
    "not_in": "NOT IN",
    "is_null": "IS NULL",
    "is_not_null": "IS NOT NULL",
    # 数值操作符
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

# 状态映射
STATUS_MAPPING = {
    "downloading": "下载中",
    "stalled": "暂停",
    "completed": "已完成",
    "seeding": "做种中",
    "paused": "已暂停",
    "error": "错误",
    "checking": "检查中",
    "moving": "移动中",
    "unknown": "未知",
}

# 分类映射
CATEGORY_MAPPING = {
    "movies": "电影",
    "tv": "电视剧",
    "music": "音乐",
    "games": "游戏",
    "software": "软件",
    "anime": "动漫",
    " documentaries": "纪录片",
    "other": "其他",
}


def validate_size_string(size_str: Optional[str]) -> Optional[int]:
    """验证大小字符串并转换为字节"""
    if not size_str:
        return None

    # 匹配数字和单位
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGT]?B?)$", size_str.strip(), re.IGNORECASE)
    if not match:
        return None

    number = float(match.group(1))
    unit = match.group(2).upper() if match.group(2) else "B"

    # 转换为字节
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(number * multipliers.get(unit, 1))


def validate_date_string(date_str: Optional[str]) -> Optional[datetime]:
    """验证日期字符串"""
    if not date_str:
        return None

    # 尝试多种日期格式
    formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y/%m/%d %H:%M:%S"]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None
