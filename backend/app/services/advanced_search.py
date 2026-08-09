#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级搜索服务 - 任务2.2.1 FTS5查询引擎实现
支持13字段全字段搜索和多选排除功能
采用ORM查询策略，预留FTS5扩展接口
"""

import logging
import json
import uuid
from contextlib import nullcontext
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, not_, desc, asc, func, exists
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import expression

from app.core.json_parser import safe_json_parse

from app.torrents.models import TorrentInfo, TrackerInfo
from app.models.search_template import SearchTemplate
from app.services.torrent_deletion_service import TorrentDeletionService, DeleteRequest, DeleteOption, SafetyCheckLevel
from app.api.models.advanced_search import (
    EnhancedAdvancedSearchRequest,
    validate_template_conditions_payload,
    validate_size_string,
    validate_date_string,
)

# 导入种子信息转换函数（包含tracker信息）
from app.api.endpoints.torrent_helpers import convert_to_vos_with_trackers
from app.services.sqlite_search_runtime import (
    RegexSearchTimeout,
    consume_regex_runtime_error,
    ensure_search_runtime,
    regex_query_budget,
)
from app.services.deletion_task_manager import build_active_deletion_exclusion

logger = logging.getLogger(__name__)


def _normalize_multi_value(value: Any) -> List[str]:
    """
    将多值搜索条件归一化为字符串列表。

    用于 contains_any / contains_all 等多值子串匹配操作符：
    - list/tuple → 元素转 str 后返回（过滤空值）
    - str        → 按逗号拆分（兼容历史逗号串 value）
    - 其它       → 包装成单元素列表

    空值统一返回空列表，使上层 lambda 生成空参数的 or_()/and_()
    （SQLAlchemy 对空列表 or_() 会返回 False 字面量，安全）。
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        items = [str(value)]
    return [item for item in items if item]


class SearchQueryBuilder:
    """搜索查询构建器 - 负责构建复杂的SQLAlchemy查询"""

    # 字段到数据库列的映射
    FIELD_MAPPING = {
        "info_id": TorrentInfo.info_id,
        "downloader_id": TorrentInfo.downloader_id,
        "downloader_name": TorrentInfo.downloader_name,
        "torrent_id": TorrentInfo.torrent_id,
        "hash": TorrentInfo.hash,
        "name": TorrentInfo.name,
        "save_path": TorrentInfo.save_path,
        "size": TorrentInfo.size,
        "status": TorrentInfo.status,
        "torrent_file": TorrentInfo.torrent_file,
        "added_date": TorrentInfo.added_date,
        "added_time": TorrentInfo.added_date,  # 别名
        "completed_date": TorrentInfo.completed_date,
        "ratio": TorrentInfo.ratio,
        "ratio_limit": TorrentInfo.ratio_limit,
        "tags": TorrentInfo.tags,
        "category": TorrentInfo.category,
        "super_seeding": TorrentInfo.super_seeding,
        "enabled": TorrentInfo.enabled,
    }

    # 操作符到SQLAlchemy的映射
    OPERATOR_MAPPING = {
        "eq": lambda column, value: column == value,
        "ne": lambda column, value: column != value,
        "gt": lambda column, value: column > value,
        "gte": lambda column, value: column >= value,
        "lt": lambda column, value: column < value,
        "lte": lambda column, value: column <= value,
        "contains": lambda column, value: column.contains(value) if isinstance(value, str) else column == value,
        "not_contains": lambda column, value: ~column.contains(value) if isinstance(value, str) else column != value,
        "starts_with": lambda column, value: column.startswith(value) if isinstance(value, str) else column == value,
        "ends_with": lambda column, value: column.endswith(value) if isinstance(value, str) else column == value,
        "not_starts_with": lambda column, value: (
            ~column.startswith(value) if isinstance(value, str) else column != value
        ),
        "not_ends_with": lambda column, value: ~column.endswith(value) if isinstance(value, str) else column != value,
        "in": lambda column, value: column.in_(value if isinstance(value, (list, tuple)) else [value]),
        "not_in": lambda column, value: ~column.in_(value if isinstance(value, (list, tuple)) else [value]),
        "is_null": lambda column, value: column.is_(None),
        "is_not_null": lambda column, value: column.isnot(None),
        # 多值子串匹配：针对逗号分隔字符串列（如 tags="movie,4k"）
        # value 经 _normalize_multi_value 归一化为字符串列表后，逐个做 LIKE 子串匹配
        "contains_any": lambda column, value: or_(*[column.contains(v) for v in _normalize_multi_value(value)]),
        "contains_all": lambda column, value: and_(*[column.contains(v) for v in _normalize_multi_value(value)]),
        "not_contains_any": lambda column, value: not_(
            or_(*[column.contains(v) for v in _normalize_multi_value(value)])
        ),
        "not_contains_all": lambda column, value: not_(
            and_(*[column.contains(v) for v in _normalize_multi_value(value)])
        ),
    }

    # 数值语义列：ORM 列已是 Float（v1.0.6.1 迁移后），常量保留供未来扩展守卫。
    # 不含 size（size 走 validate_size_string 单位解析独立路径）。
    NUMERIC_FIELDS = {"ratio", "ratio_limit"}

    def __init__(self, db: Session):
        """
        初始化查询构建器

        Args:
            db: 数据库会话
        """
        self.db = db
        ensure_search_runtime(db)
        self.base_query = self._new_base_query()

    def _new_base_query(self):
        query = self.db.query(TorrentInfo).filter(TorrentInfo.dr == 0)
        active_deletion_exclusion = build_active_deletion_exclusion(TorrentInfo.info_id)
        if active_deletion_exclusion is not None:
            query = query.filter(active_deletion_exclusion)
        return query

    def reset(self) -> "SearchQueryBuilder":
        """重置查询到初始状态"""
        self.base_query = self._new_base_query()
        return self

    def apply_basic_filters(self, request: EnhancedAdvancedSearchRequest) -> "SearchQueryBuilder":
        """
        应用基础过滤条件

        Args:
            request: 搜索请求对象

        Returns:
            self 支持链式调用
        """
        filters = []

        # 下载器ID过滤
        if request.downloader_id:
            filters.append(TorrentInfo.downloader_id == request.downloader_id)

        # 下载器名称过滤
        if request.downloader_name:
            filters.append(TorrentInfo.downloader_name.contains(request.downloader_name))

        # 种子名称过滤
        if request.name:
            filters.append(TorrentInfo.name.contains(request.name))

        # 标签过滤
        if request.tags:
            filters.append(TorrentInfo.tags.contains(request.tags))

        # 分类过滤
        if request.category:
            filters.append(TorrentInfo.category == request.category)

        # 状态过滤
        if request.status:
            filters.append(TorrentInfo.status == request.status)

        # 种子大小范围过滤
        if request.size_min:
            size_min_bytes = validate_size_string(request.size_min)
            if size_min_bytes is not None:
                filters.append(TorrentInfo.size >= size_min_bytes)

        if request.size_max:
            size_max_bytes = validate_size_string(request.size_max)
            if size_max_bytes is not None:
                filters.append(TorrentInfo.size <= size_max_bytes)

        # 分享比率范围过滤（ratio 列已是 Float，天然数值比较）
        if request.ratio_min is not None:
            filters.append(TorrentInfo.ratio >= request.ratio_min)

        if request.ratio_max is not None:
            filters.append(TorrentInfo.ratio <= request.ratio_max)

        # 添加日期范围过滤
        if request.added_date_min:
            added_min = validate_date_string(request.added_date_min)
            if added_min is not None:
                filters.append(TorrentInfo.added_date >= added_min)

        if request.added_date_max:
            added_max = validate_date_string(request.added_date_max)
            if added_max is not None:
                # 包含当天的23:59:59（用户传 '2026-01-15' 应包含当天所有种子）
                added_max = added_max.replace(hour=23, minute=59, second=59)
                filters.append(TorrentInfo.added_date <= added_max)

        # 完成日期范围过滤
        if request.completed_date_min:
            completed_min = validate_date_string(request.completed_date_min)
            if completed_min is not None:
                filters.append(TorrentInfo.completed_date >= completed_min)

        if request.completed_date_max:
            completed_max = validate_date_string(request.completed_date_max)
            if completed_max is not None:
                completed_max = completed_max.replace(hour=23, minute=59, second=59)
                filters.append(TorrentInfo.completed_date <= completed_max)

        if filters:
            self.base_query = self.base_query.filter(and_(*filters))

        return self

    def apply_condition_groups(
        self, condition_groups: Optional[List], between_group_logics: Optional[List[str]] = None
    ) -> "SearchQueryBuilder":
        """
        应用高级条件组

        Args:
            condition_groups: 条件组列表（SearchGroup对象或字典）
            between_group_logics: 条件组之间的逻辑关系列表（AND/OR）

        Returns:
            self 支持链式调用
        """
        if not condition_groups:
            return self

        group_filters = []

        for group in condition_groups:
            if hasattr(group, "logic"):
                logic = group.logic
                conditions = group.conditions
            elif isinstance(group, dict):
                from app.api.models.advanced_search import SearchGroup

                validated_group = SearchGroup.model_validate(group)
                logic = validated_group.logic
                conditions = validated_group.conditions
            else:
                raise ValueError("condition group must be a validated object")

            condition_filters = [self._build_condition_filter(condition) for condition in conditions]
            if logic == "AND":
                group_filters.append(and_(*condition_filters))
            else:
                group_filters.append(or_(*condition_filters))

        if group_filters:
            logics = between_group_logics or []
            if len(logics) != len(group_filters) - 1:
                raise ValueError("between_group_logics length must equal group count - 1")
            result_filter = group_filters[0]
            for logic, group_filter in zip(logics, group_filters[1:]):
                if logic.upper() == "AND":
                    result_filter = and_(result_filter, group_filter)
                else:
                    result_filter = or_(result_filter, group_filter)
            self.base_query = self.base_query.filter(result_filter)

        return self

    def _build_condition_filter(self, condition):
        """
        构建单个条件的过滤

        Args:
            condition: 条件对象（SearchCondition Pydantic对象或字典）

        Returns:
            SQLAlchemy 过滤表达式
        """
        if not hasattr(condition, "field"):
            from app.api.models.advanced_search import SearchCondition

            condition = SearchCondition.model_validate(condition)
        field = condition.field
        operator = condition.operator
        value = condition.value

        if field == "tracker_url":
            return self._build_tracker_url_filter(operator, value)
        if field == "tracker_msg":
            return self._build_tracker_msg_filter(operator, value)
        if field not in self.FIELD_MAPPING:
            raise ValueError(f"search field has no query mapping: {field}")
        column = self.FIELD_MAPPING[field]

        # 处理特殊字段类型
        if field == "size" and operator in ["eq", "ne", "gt", "gte", "lt", "lte"]:
            # 大小字段可能包含单位
            if isinstance(value, str):
                value = validate_size_string(value)
                if value is None:
                    raise ValueError(f"invalid size value for {operator}")

        if field in ["added_date", "completed_date", "added_time"] and operator in [
            "eq",
            "ne",
            "gt",
            "gte",
            "lt",
            "lte",
        ]:
            # 日期字段处理
            if isinstance(value, str):
                parsed_date = validate_date_string(value)
                if parsed_date is None:
                    raise ValueError(f"invalid date value for {operator}")
                if operator in {"eq", "ne"} and len(value.strip()) == 10:
                    day_end = parsed_date.replace(hour=23, minute=59, second=59)
                    day_filter = and_(column >= parsed_date, column <= day_end)
                    return day_filter if operator == "eq" else not_(day_filter)
                value = parsed_date

        if field in self.NUMERIC_FIELDS and operator in ["gt", "gte", "lt", "lte"]:
            # Float 列天然数值比较；value 显式转 float 兜底
            # （SearchCondition.value 是 Union[str,...,int,float]，Pydantic smart-union 下
            # JSON 字符串 "2.5" 会匹配 str 而非 float，故需显式转换）
            try:
                value = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"numeric field {field} cannot be converted to float") from exc

        # between / regex / last_days / date_range 需要先解构 value，单独 dispatch
        if operator == "between":
            return self._build_between_filter(column, field, value)
        if operator == "regex":
            return self._build_regex_filter(column, value)
        if operator in ("last_days", "date_range"):
            return self._build_date_window_filter(column, operator, value)

        try:
            operator_factory = self.OPERATOR_MAPPING[operator]
        except KeyError as exc:
            raise ValueError(f"operator has no query implementation: {operator}") from exc
        return operator_factory(column, value)

    def _build_between_filter(self, column, field: str, value: Any) -> expression.ClauseElement:
        """between 操作符：value = {min, max}（size 带 minUnit/maxUnit；date 带 start/end）。

        前端实测 value 形态：
          - size: {"min": "1 GB", "max": "10 GB", "minUnit": "GB", "maxUnit": "GB"}
          - 数值字段（ratio/ratio_limit）: {"min": 1, "max": 10}
          - 日期字段（added_date/completed_date）: {"start": "...", "end": "..."}
        """
        if not isinstance(value, dict):
            raise ValueError("between requires an object value")

        if field in ["added_date", "completed_date", "added_time"]:
            # 日期区间：min/max 或 start/end 任一命名都接受
            start_raw = value.get("start", value.get("min"))
            end_raw = value.get("end", value.get("max"))
            conditions = []
            if start_raw is not None:
                start = validate_date_string(start_raw) if isinstance(start_raw, str) else start_raw
                if start is None:
                    raise ValueError("invalid between start date")
                conditions.append(column >= start)
            if end_raw is not None:
                end = validate_date_string(end_raw) if isinstance(end_raw, str) else end_raw
                if end is None:
                    raise ValueError("invalid between end date")
                if isinstance(end_raw, str) and len(end_raw.strip()) == 10:
                    end = end.replace(hour=23, minute=59, second=59)
                conditions.append(column <= end)
            if not conditions:
                raise ValueError("between requires at least one date boundary")
            return and_(*conditions)

        if field == "size":
            # size 带 "1 GB" 单位串
            min_raw = value.get("min")
            max_raw = value.get("max")
            conditions = []
            if min_raw is not None:
                min_bytes = validate_size_string(min_raw) if isinstance(min_raw, str) else min_raw
                if min_bytes is None:
                    raise ValueError("invalid between minimum size")
                conditions.append(column >= min_bytes)
            if max_raw is not None:
                max_bytes = validate_size_string(max_raw) if isinstance(max_raw, str) else max_raw
                if max_bytes is None:
                    raise ValueError("invalid between maximum size")
                conditions.append(column <= max_bytes)
            if not conditions:
                raise ValueError("between requires at least one size boundary")
            return and_(*conditions)

        # 默认数值字段（ratio/ratio_limit 等）
        min_raw = value.get("min")
        max_raw = value.get("max")
        conditions = []
        try:
            if min_raw is not None:
                conditions.append(column >= float(min_raw))
            if max_raw is not None:
                conditions.append(column <= float(max_raw))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"between numeric boundaries are invalid for {field}") from exc
        if not conditions:
            raise ValueError("between requires at least one numeric boundary")
        return and_(*conditions)

    def _build_regex_filter(self, column, value: Any) -> expression.ClauseElement:
        """regex 操作符：value = {pattern, caseSensitive}。

        ``bt_regexp`` is installed on every SQLite connection and uses a
        timeout-capable regex engine. Request validation compiles the pattern
        before any query is executed.
        """
        if isinstance(value, dict):
            pattern = value.get("pattern")
            case_sensitive = value.get("caseSensitive", False)
        elif isinstance(value, str):
            pattern = value
            case_sensitive = True
        else:
            raise ValueError("regex requires an object or string value")

        if not pattern:
            raise ValueError("regex pattern must not be empty")
        return and_(
            column.is_not(None),
            func.bt_regexp(pattern, column, int(bool(case_sensitive))) == 1,
        )

    def _build_date_window_filter(self, column, operator: str, value: Any) -> expression.ClauseElement:
        """last_days / date_range 操作符（仅用于日期字段）。

        前端实测 value 形态（formatParamValue 对 date 字段 JSON.stringify 后）：
          - last_days: '{"days": 7}'
          - date_range: '{"start": "...", "end": "..."}'
        """
        # value 可能是 JSON 字符串或已解构的 dict
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{operator} requires valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{operator} requires an object value")

        if operator == "last_days":
            days = value.get("days")
            if days is None:
                raise ValueError("last_days requires days")
            try:
                days = int(days)
            except (TypeError, ValueError) as exc:
                raise ValueError("last_days requires integer days") from exc
            if days < 1:
                raise ValueError("last_days requires a positive day count")
            threshold = datetime.now() - timedelta(days=days)
            return column >= threshold

        # date_range
        start_raw = value.get("start")
        end_raw = value.get("end")
        conditions = []
        if start_raw is not None:
            start = validate_date_string(start_raw) if isinstance(start_raw, str) else start_raw
            if start is None:
                raise ValueError("invalid date_range start")
            conditions.append(column >= start)
        if end_raw is not None:
            end = validate_date_string(end_raw) if isinstance(end_raw, str) else end_raw
            if end is None:
                raise ValueError("invalid date_range end")
            if isinstance(end_raw, str) and len(end_raw.strip()) == 10:
                end = end.replace(hour=23, minute=59, second=59)
            conditions.append(column <= end)
        if not conditions:
            raise ValueError("date_range requires at least one boundary")
        return and_(*conditions)

    def _build_tracker_msg_filter(self, operator: str, value: Any) -> expression.ClauseElement:
        """
        Build tracker_msg filter using tracker_info table.
        Match last_announce_msg OR last_scrape_msg on active trackers (dr == 0).
        """
        tracker_text_filter = self._build_tracker_msg_text_filter(operator, value)

        return exists().where(
            and_(TrackerInfo.torrent_info_id == TorrentInfo.info_id, TrackerInfo.dr == 0, tracker_text_filter)
        )

    def _build_tracker_msg_text_filter(self, operator: str, value: Any) -> expression.ClauseElement:
        """Build OR text filter for tracker announce/scrape message fields."""
        announce_filter = self._build_text_filter(TrackerInfo.last_announce_msg, operator, value)
        scrape_filter = self._build_text_filter(TrackerInfo.last_scrape_msg, operator, value)

        return or_(announce_filter, scrape_filter)

    def _build_tracker_url_filter(self, operator: str, value: Any) -> expression.ClauseElement:
        """
        Build tracker_url filter using tracker_info table.
        Match tracker_url field on active trackers (dr == 0).
        """
        tracker_url_filter = self._build_text_filter(TrackerInfo.tracker_url, operator, value)

        return exists().where(
            and_(TrackerInfo.torrent_info_id == TorrentInfo.info_id, TrackerInfo.dr == 0, tracker_url_filter)
        )

    def _build_text_filter(self, column, operator: str, value: Any) -> expression.ClauseElement:
        """
        Build text filter for a single column with None safety.

        ✅ P2修复：添加None值安全处理，避免SQL错误
        - 对于字符串操作符，先过滤掉None值
        - 对于等值比较操作符，可以安全处理None（SQL语义）
        """
        if operator == "regex":
            return self._build_regex_filter(column, value)
        if operator == "in":
            return and_(column.is_not(None), column.in_(value))
        if operator == "not_in":
            return or_(column.is_(None), ~column.in_(value))
        if operator == "is_null":
            return column.is_(None)
        if operator == "is_not_null":
            return column.is_not(None)

        # 字符串操作符：需要先过滤None值，否则会引发SQL错误
        if operator in ["contains", "not_contains", "starts_with", "ends_with", "not_starts_with", "not_ends_with"]:
            # 使用AND确保列值不为None，然后应用文本操作符
            if operator == "contains":
                return and_(column.is_not(None), column.contains(value))
            if operator == "not_contains":
                # 对于not_contains，None值也不包含目标字符串，所以视为匹配
                return or_(column.is_(None), and_(column.is_not(None), ~column.contains(value)))
            if operator == "starts_with":
                return and_(column.is_not(None), column.startswith(value))
            if operator == "ends_with":
                return and_(column.is_not(None), column.endswith(value))
            if operator == "not_starts_with":
                # None不匹配任何前缀，所以视为符合not_starts_with条件
                return or_(column.is_(None), and_(column.is_not(None), ~column.startswith(value)))
            if operator == "not_ends_with":
                # None不匹配任何后缀，所以视为符合not_ends_with条件
                return or_(column.is_(None), and_(column.is_not(None), ~column.endswith(value)))

        # 等值比较操作符：SQL语义可以安全处理None
        if operator in ["eq", "equals"]:
            return column == value
        if operator in ["ne", "not_equals"]:
            return column != value

        raise ValueError(f"tracker text operator has no implementation: {operator}")

    def apply_sorting(self, sort_by: str, sort_order: str = "desc") -> "SearchQueryBuilder":
        """
        应用排序

        Args:
            sort_by: 排序字段
            sort_order: 排序方向 (asc/desc)

        Returns:
            self 支持链式调用
        """
        if sort_by not in self.FIELD_MAPPING:
            logger.warning(f"无效的排序字段: {sort_by}, 使用默认字段 added_date")
            sort_by = "added_date"

        column = self.FIELD_MAPPING[sort_by]
        # ratio / ratio_limit / size 已是 Float 列，order_by 天然数值排序（无需 cast）；
        # 历史 String 列字典序 bug（"10.0" < "2"）随 v1.0.6.1 列类型迁移根治。

        if sort_order and sort_order.lower() == "asc":
            self.base_query = self.base_query.order_by(asc(column))
        else:
            self.base_query = self.base_query.order_by(desc(column))

        return self

    def apply_pagination(self, page: int = 1, limit: int = 20) -> "SearchQueryBuilder":
        """
        应用分页

        Args:
            page: 页码 (从1开始)
            limit: 每页数量

        Returns:
            self 支持链式调用
        """
        offset = (page - 1) * limit
        self.base_query = self.base_query.offset(offset).limit(limit)
        return self

    def get_query(self):
        """
        获取构建好的查询对象

        Returns:
            SQLAlchemy Query 对象
        """
        return self.base_query

    def count(self) -> int:
        """
        获取结果总数

        Returns:
            结果数量
        """
        return self.base_query.count()


class SearchTemplateModel:
    """搜索模板数据模型（ORM 实现）

    第四轨归位：原用原生 SQL 自建表 + 操作，现统一用 ORM。
    表结构由 Alembic 迁移管理（95ef8bd8b47a），本类不再负责建表。
    """

    def __init__(self, db: Session):
        self.db = db

    def create(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建搜索模板

        Args:
            template_data: 模板数据

        Returns:
            创建的模板信息
        """
        try:
            template_id = str(uuid.uuid4())
            now = datetime.utcnow()

            template = SearchTemplate(
                id=template_id,
                user_id=template_data["user_id"],
                name=template_data["name"],
                description=template_data.get("description", ""),
                conditions=json.dumps(template_data["conditions"], ensure_ascii=False),
                is_default=1 if template_data.get("is_default", False) else 0,
                is_public=1 if template_data.get("is_public", False) else 0,
                usage_count=0,
                created_time=now,
                updated_time=now,
            )
            self.db.add(template)
            self.db.commit()

            logger.info(f"创建搜索模板成功: {template_id}")
            return {"id": template_id, "created_time": now, **template_data}

        except Exception as e:
            self.db.rollback()
            logger.error(f"创建搜索模板失败: {str(e)}")
            raise

    def _row_to_dict(self, template: SearchTemplate) -> Dict[str, Any]:
        """ORM 对象转字典（conditions 反序列化为 dict）。"""
        return {
            "id": template.id,
            "user_id": template.user_id,
            "name": template.name,
            "description": template.description,
            "conditions": safe_json_parse(template.conditions, {}),
            "is_default": bool(template.is_default),
            "is_public": bool(template.is_public),
            "usage_count": template.usage_count,
            "created_time": template.created_time,
            "updated_time": template.updated_time,
        }

    def get_by_user(self, user_id: str, is_public: bool = False) -> List[Dict[str, Any]]:
        """
        获取用户的搜索模板

        Args:
            user_id: 用户ID
            is_public: 是否包含公开模板

        Returns:
            模板列表
        """
        try:
            query = self.db.query(SearchTemplate)
            if is_public:
                query = query.filter(or_(SearchTemplate.user_id == user_id, SearchTemplate.is_public == 1))
            else:
                query = query.filter(SearchTemplate.user_id == user_id)
            query = query.order_by(SearchTemplate.created_time.desc())

            return [self._row_to_dict(t) for t in query.all()]

        except Exception as e:
            logger.error(f"获取搜索模板失败: {str(e)}")
            return []

    def get_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取模板

        Args:
            template_id: 模板ID

        Returns:
            模板数据或None
        """
        try:
            template = self.db.query(SearchTemplate).filter(SearchTemplate.id == template_id).first()
            return self._row_to_dict(template) if template else None

        except Exception as e:
            logger.error(f"获取模板失败: {str(e)}")
            return None

    def update(self, template_id: str, update_data: Dict[str, Any]) -> bool:
        """
        更新搜索模板

        Args:
            template_id: 模板ID
            update_data: 更新数据（支持 name/description/conditions/is_public）

        Returns:
            是否成功
        """
        try:
            template = self.db.query(SearchTemplate).filter(SearchTemplate.id == template_id).first()
            if not template:
                return False

            if "name" in update_data:
                template.name = update_data["name"]
            if "description" in update_data:
                template.description = update_data["description"]
            if "conditions" in update_data:
                template.conditions = json.dumps(update_data["conditions"], ensure_ascii=False)
            if "is_public" in update_data:
                template.is_public = 1 if update_data["is_public"] else 0

            template.updated_time = datetime.utcnow()
            self.db.commit()

            logger.info(f"更新搜索模板成功: {template_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"更新搜索模板失败: {str(e)}")
            return False

    def delete(self, template_id: str) -> bool:
        """
        删除搜索模板

        Args:
            template_id: 模板ID

        Returns:
            是否成功
        """
        try:
            deleted = (
                self.db.query(SearchTemplate).filter(SearchTemplate.id == template_id).delete(synchronize_session=False)
            )
            self.db.commit()

            if deleted:
                logger.info(f"删除搜索模板成功: {template_id}")
                return True
            return False

        except Exception as e:
            self.db.rollback()
            logger.error(f"删除搜索模板失败: {str(e)}")
            return False

    def increment_usage(self, template_id: str) -> bool:
        """
        增加模板使用次数

        Args:
            template_id: 模板ID

        Returns:
            是否成功（模板不存在时返回 False）
        """
        try:
            from sqlalchemy import update

            result = self.db.execute(
                update(SearchTemplate)
                .where(SearchTemplate.id == template_id)
                .values(usage_count=SearchTemplate.usage_count + 1)
            )
            self.db.commit()
            # SQLAlchemy update 对不存在的行不抛异常，需检查 rowcount
            return (result.rowcount or 0) > 0

        except Exception as e:
            self.db.rollback()
            logger.error(f"增加模板使用次数失败: {str(e)}")
            return False


class AdvancedSearchService:
    """
    高级搜索服务主类
    提供13字段全字段搜索和多选排除功能
    """

    def __init__(self, db: Session):
        """
        初始化高级搜索服务

        Args:
            db: 数据库会话
        """
        self.db = db
        self.query_builder = SearchQueryBuilder(db)
        self.template_model = SearchTemplateModel(db)
        self.deletion_service = TorrentDeletionService(db)

    def search_torrents(self, request: EnhancedAdvancedSearchRequest, user_id: str) -> Dict[str, Any]:
        """
        执行高级搜索

        Args:
            request: 搜索请求对象
            user_id: 用户ID

        Returns:
            搜索结果字典，包含:
            - status: 状态 (success/failed)
            - msg: 消息
            - code: 状态码
            - data: 结果列表
            - total: 总记录数
            - page: 当前页
            - limit: 每页数量
            - total_pages: 总页数
        """
        try:
            # Revalidate at the service boundary as callers may mutate a Pydantic
            # instance after construction or invoke the service without FastAPI.
            request = EnhancedAdvancedSearchRequest.model_validate(
                request.model_dump() if hasattr(request, "model_dump") else request
            )

            # 添加调试日志：记录搜索请求参数
            logger.info(f"[高级搜索] 用户 {user_id} 发起搜索请求")
            logger.info(
                f"[高级搜索] 基础参数: name={request.name}, status={request.status}, category={request.category}"
            )
            logger.info(f"[高级搜索] 条件组数量: {len(request.condition_groups) if request.condition_groups else 0}")
            logger.info(f"[高级搜索] 组间逻辑关系: {request.between_group_logics}")

            # 构建查询
            self.query_builder.reset()

            # 应用基础过滤
            self.query_builder.apply_basic_filters(request)
            logger.info("[高级搜索] 基础过滤已应用")

            # 应用高级条件组
            if request.condition_groups:
                logger.info(f"[高级搜索] 应用条件组，数量: {len(request.condition_groups)}")
                for idx, group in enumerate(request.condition_groups):
                    group_logic = group.logic if hasattr(group, "logic") else group.get("logic", "AND")
                    conditions = group.conditions if hasattr(group, "conditions") else group.get("conditions", [])
                    logger.info(f"[高级搜索] 条件组 {idx}: logic={group_logic}, 条件数={len(conditions)}")
                    for cond_idx, cond in enumerate(conditions):
                        cond_field = cond.field if hasattr(cond, "field") else cond.get("field")
                        cond_operator = cond.operator if hasattr(cond, "operator") else cond.get("operator")
                        cond_value = cond.value if hasattr(cond, "value") else cond.get("value")
                        logger.info(
                            f"[高级搜索]   条件 {cond_idx}: field={cond_field}, operator={cond_operator}, value={cond_value}"
                        )

                self.query_builder.apply_condition_groups(request.condition_groups, request.between_group_logics)
                logger.info("[高级搜索] 条件组已应用")

            has_regex = any(
                condition.operator == "regex"
                for group in (request.condition_groups or [])
                for condition in group.conditions
            )
            consume_regex_runtime_error()
            query_scope = regex_query_budget(self.db) if has_regex else nullcontext()
            with query_scope:
                # 获取总数（在排序和分页之前）
                total = self.query_builder.count()
                logger.info(f"[高级搜索] 查询总数: {total}")

                # 应用排序和分页
                self.query_builder.apply_sorting(request.sort_by, request.sort_order)
                self.query_builder.apply_pagination(request.page, request.limit)

                # 执行查询
                results = self.query_builder.get_query().all()
                logger.info(f"[高级搜索] 实际返回结果数: {len(results)}")

            # 转换为字典列表（包含tracker信息，与/torrent/getList接口保持一致）
            # 使用 model_dump() 方法让 Pydantic 自动序列化（支持 camelCase 别名和 datetime ISO 格式）
            data = [
                torrent.model_dump(by_alias=True, exclude_none=True)
                for torrent in convert_to_vos_with_trackers(self.db, results)
            ]

            # 计算总页数
            total_pages = (total + request.limit - 1) // request.limit

            logger.info(f"用户 {user_id} 执行高级搜索，找到 {total} 条结果")

            return {
                "status": "success",
                "msg": "搜索成功",
                "code": "200",
                "data": data,
                "total": total,
                "page": request.page,
                "limit": request.limit,
                "total_pages": total_pages,
            }

        except OperationalError as e:
            runtime_error = consume_regex_runtime_error()
            if runtime_error:
                logger.warning(
                    "高级搜索正则执行被中止: reason=%s user=%s",
                    runtime_error,
                    user_id,
                )
                raise RegexSearchTimeout("regular expression search exceeded its execution budget") from e
            logger.exception("高级搜索数据库执行失败")
            raise
        except Exception as e:
            logger.error(f"高级搜索失败: {str(e)}")
            import traceback

            logger.error(f"高级搜索异常堆栈: {traceback.format_exc()}")
            raise

    def create_search_template(self, request, user_id: str) -> Dict[str, Any]:
        """
        创建搜索模板

        Args:
            request: 模板创建请求（SearchTemplateCreate对象或字典）
            user_id: 用户ID

        Returns:
            创建结果
        """
        try:
            # 兼容Pydantic对象和字典
            if hasattr(request, "name"):
                # SearchTemplateCreate Pydantic对象
                template_data = {
                    "user_id": user_id,
                    "name": request.name,
                    "description": request.description,
                    "conditions": request.conditions,
                    "is_default": False,
                    "is_public": request.is_public,
                }
            else:
                # 字典格式
                template_data = {
                    "user_id": user_id,
                    "name": request.get("name"),
                    "description": request.get("description"),
                    "conditions": request.get("conditions"),
                    "is_default": False,
                    "is_public": request.get("is_public", False),
                }

            validate_template_conditions_payload(template_data["conditions"])
            result = self.template_model.create(template_data)

            return {"status": "success", "msg": "创建模板成功", "code": "200", "data": result}

        except ValueError as e:
            logger.warning("拒绝无效搜索模板: %s", e)
            return {
                "status": "failed",
                "msg": f"模板条件无效: {e}",
                "code": "422",
                "data": None,
            }
        except Exception as e:
            logger.error(f"创建搜索模板失败: {str(e)}")
            return {"status": "failed", "msg": f"创建模板失败: {str(e)}", "code": "500", "data": None}

    def get_search_templates(self, user_id: str, is_public: bool = False) -> Dict[str, Any]:
        """
        获取搜索模板列表

        Args:
            user_id: 用户ID
            is_public: 是否包含公开模板

        Returns:
            模板列表
        """
        try:
            templates = self.template_model.get_by_user(user_id, is_public)

            return {
                "status": "success",
                "msg": "获取模板成功",
                "code": "200",
                "data": templates,
                "total": len(templates),
            }

        except Exception as e:
            logger.error(f"获取搜索模板失败: {str(e)}")
            return {"status": "failed", "msg": f"获取模板失败: {str(e)}", "code": "500", "data": [], "total": 0}

    def update_search_template(self, template_id: str, request: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        更新搜索模板

        Args:
            template_id: 模板ID
            request: 更新请求
            user_id: 用户ID

        Returns:
            更新结果
        """
        try:
            # 验证模板存在且属于当前用户
            template = self.template_model.get_by_id(template_id)
            if not template:
                return {"status": "failed", "msg": "模板不存在", "code": "404", "data": None}

            if template["user_id"] != user_id:
                return {"status": "failed", "msg": "无权修改此模板", "code": "403", "data": None}

            # 执行更新
            update_data = {}
            if "name" in request:
                update_data["name"] = request["name"]
            if "description" in request:
                update_data["description"] = request["description"]
            if "conditions" in request:
                update_data["conditions"] = validate_template_conditions_payload(request["conditions"])
            if "is_public" in request:
                update_data["is_public"] = request["is_public"]

            success = self.template_model.update(template_id, update_data)

            if success:
                return {
                    "status": "success",
                    "msg": "更新模板成功",
                    "code": "200",
                    "data": {"id": template_id, **update_data},
                }
            else:
                return {"status": "failed", "msg": "更新模板失败", "code": "500", "data": None}

        except ValueError as e:
            logger.warning("拒绝无效搜索模板更新: %s", e)
            return {
                "status": "failed",
                "msg": f"模板条件无效: {e}",
                "code": "422",
                "data": None,
            }
        except Exception as e:
            logger.error(f"更新搜索模板失败: {str(e)}")
            return {"status": "failed", "msg": f"更新模板失败: {str(e)}", "code": "500", "data": None}

    def delete_search_template(self, template_id: str, user_id: str) -> Dict[str, Any]:
        """
        删除搜索模板

        Args:
            template_id: 模板ID
            user_id: 用户ID

        Returns:
            删除结果
        """
        try:
            # 验证模板存在且属于当前用户
            template = self.template_model.get_by_id(template_id)
            if not template:
                return {"status": "failed", "msg": "模板不存在", "code": "404", "data": None}

            if template["user_id"] != user_id:
                return {"status": "failed", "msg": "无权删除此模板", "code": "403", "data": None}

            # 执行删除
            success = self.template_model.delete(template_id)

            if success:
                return {"status": "success", "msg": "删除模板成功", "code": "200", "data": {"id": template_id}}
            else:
                return {"status": "failed", "msg": "删除模板失败", "code": "500", "data": None}

        except Exception as e:
            logger.error(f"删除搜索模板失败: {str(e)}")
            return {"status": "failed", "msg": f"删除模板失败: {str(e)}", "code": "500", "data": None}

    def apply_search_template(self, template_id: str, user_id: str) -> Dict[str, Any]:
        """
        应用搜索模板

        Args:
            template_id: 模板ID
            user_id: 用户ID

        Returns:
            模板条件数据
        """
        try:
            # 获取模板
            template = self.template_model.get_by_id(template_id)

            if not template:
                return {"status": "failed", "msg": "模板不存在", "code": "404", "data": None}

            # 检查权限（公开模板或自己的模板）
            if template["user_id"] != user_id and not template["is_public"]:
                return {"status": "failed", "msg": "无权使用此模板", "code": "403", "data": None}

            validate_template_conditions_payload(template["conditions"])

            # 增加使用次数
            self.template_model.increment_usage(template_id)

            logger.info(f"用户 {user_id} 应用搜索模板: {template_id}")

            return {
                "status": "success",
                "msg": "应用模板成功",
                "code": "200",
                "data": {
                    "id": template["id"],
                    "name": template["name"],
                    "description": template["description"],
                    "conditions": template["conditions"],
                },
            }

        except ValueError as e:
            logger.warning("拒绝应用无效搜索模板: %s", e)
            return {
                "status": "failed",
                "msg": f"模板条件无效: {e}",
                "code": "422",
                "data": None,
            }
        except Exception as e:
            logger.error(f"应用搜索模板失败: {str(e)}")
            return {"status": "failed", "msg": f"应用模板失败: {str(e)}", "code": "500", "data": None}

    def delete_torrents_batch(self, request, user_id: str) -> Dict[str, Any]:
        """
        批量删除种子（复用torrent_deletion_service）

        Args:
            request: 删除请求（TorrentDeleteRequest对象或字典），包含torrent_ids, delete_data, id_recycle
            user_id: 用户ID

        Returns:
            删除结果
        """
        try:
            # 兼容Pydantic对象和字典
            if hasattr(request, "torrent_ids"):
                # TorrentDeleteRequest Pydantic对象
                torrent_ids = request.torrent_ids
                delete_data = request.delete_data
                request.id_recycle
            else:
                # 字典格式
                torrent_ids = request.get("torrent_ids", [])
                delete_data = request.get("delete_data", True)
                request.get("id_recycle", False)

            if not torrent_ids:
                return {"status": "failed", "msg": "请选择要删除的种子", "code": "400", "data": None}

            # 构建删除请求
            if delete_data:
                delete_option = DeleteOption.DELETE_FILES_AND_TORRENT
            else:
                delete_option = DeleteOption.DELETE_ONLY_TORRENT

            delete_request = DeleteRequest(
                torrent_info_ids=torrent_ids,
                delete_option=delete_option,
                safety_check_level=SafetyCheckLevel.ENHANCED,
                force_delete=False,
                reason=f"用户 {user_id} 批量删除",
            )

            # 执行删除
            result = self.deletion_service.delete_torrents(delete_request)

            # 构建响应数据
            response_data = {
                "success_count": result.success_count,
                "failed_count": result.failed_count,
                "skipped_count": result.skipped_count,
                "total_size_freed": result.total_size_freed,
                "deleted_torrents": result.deleted_torrents,
                "failed_torrents": result.failed_torrents,
                "safety_warnings": result.safety_warnings,
            }

            logger.info(f"用户 {user_id} 批量删除种子: 成功{result.success_count}, 失败{result.failed_count}")

            return {
                "status": "success",
                "msg": f"删除完成: 成功{result.success_count}, 失败{result.failed_count}, 跳过{result.skipped_count}",
                "code": "200",
                "data": response_data,
            }

        except Exception as e:
            logger.error(f"批量删除种子失败: {str(e)}")
            return {"status": "failed", "msg": f"批量删除失败: {str(e)}", "code": "500", "data": None}

    def get_search_statistics(self) -> Dict[str, Any]:
        """
        获取搜索统计信息

        Returns:
            统计数据，包含:
            - field_distribution: 字段分布统计
            - operator_usage: 操作符使用统计
            - search_performance: 搜索性能统计
        """
        try:
            # 获取字段分布统计
            stats = {}

            # 状态分布
            status_stats = (
                self.db.query(TorrentInfo.status, func.count(TorrentInfo.info_id))
                .filter(TorrentInfo.dr == 0)
                .group_by(TorrentInfo.status)
                .all()
            )

            stats["status_distribution"] = [{"status": s[0] or "unknown", "count": s[1]} for s in status_stats]

            # 分类分布
            category_stats = (
                self.db.query(TorrentInfo.category, func.count(TorrentInfo.info_id))
                .filter(TorrentInfo.dr == 0, TorrentInfo.category.isnot(None))
                .group_by(TorrentInfo.category)
                .all()
            )

            stats["category_distribution"] = [
                {"category": c[0] or "uncategorized", "count": c[1]} for c in category_stats
            ]

            # 下载器分布
            downloader_stats = (
                self.db.query(TorrentInfo.downloader_name, func.count(TorrentInfo.info_id))
                .filter(TorrentInfo.dr == 0)
                .group_by(TorrentInfo.downloader_name)
                .all()
            )

            stats["downloader_distribution"] = [{"downloader": d[0], "count": d[1]} for d in downloader_stats]

            # 总体统计
            total_torrents = self.db.query(func.count(TorrentInfo.info_id)).filter(TorrentInfo.dr == 0).scalar()

            total_size = self.db.query(func.sum(TorrentInfo.size)).filter(TorrentInfo.dr == 0).scalar() or 0

            stats["total_torrents"] = total_torrents
            stats["total_size"] = total_size

            # 模板统计（表由 Alembic 迁移管理，无需 _ensure_table_exists）
            template_count = self.db.query(func.count(SearchTemplate.id)).scalar()

            stats["total_templates"] = template_count or 0

            return {"status": "success", "msg": "获取统计成功", "code": "200", "data": stats}

        except Exception as e:
            logger.error(f"获取搜索统计失败: {str(e)}")
            return {"status": "failed", "msg": f"获取统计失败: {str(e)}", "code": "500", "data": {}}
