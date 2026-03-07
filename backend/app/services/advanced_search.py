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
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, not_, desc, asc, func, extract, text, exists
from sqlalchemy.sql import expression

from app.core.json_parser import safe_json_parse

from app.torrents.models import TorrentInfo, TrackerInfo
from app.downloader.models import BtDownloaders
from app.services.torrent_deletion_service import (
    TorrentDeletionService, DeleteRequest, DeleteOption, SafetyCheckLevel
)
from app.api.models.advanced_search import (
    EnhancedAdvancedSearchRequest, SearchCondition, MultiSelectCondition,
    validate_size_string, validate_date_string
)
# 导入种子信息转换函数（包含tracker信息）
from app.api.endpoints.torrents import convert_to_vo_with_trackers

logger = logging.getLogger(__name__)


class SearchQueryBuilder:
    """搜索查询构建器 - 负责构建复杂的SQLAlchemy查询"""

    # 字段到数据库列的映射
    FIELD_MAPPING = {
        'info_id': TorrentInfo.info_id,
        'downloader_id': TorrentInfo.downloader_id,
        'downloader_name': TorrentInfo.downloader_name,
        'torrent_id': TorrentInfo.torrent_id,
        'hash': TorrentInfo.hash,
        'name': TorrentInfo.name,
        'save_path': TorrentInfo.save_path,
        'size': TorrentInfo.size,
        'status': TorrentInfo.status,
        'torrent_file': TorrentInfo.torrent_file,
        'added_date': TorrentInfo.added_date,
        'added_time': TorrentInfo.added_date,  # 别名
        'completed_date': TorrentInfo.completed_date,
        'ratio': TorrentInfo.ratio,
        'ratio_limit': TorrentInfo.ratio_limit,
        'tags': TorrentInfo.tags,
        'category': TorrentInfo.category,
        'super_seeding': TorrentInfo.super_seeding,
        'enabled': TorrentInfo.enabled,
    }

    # 操作符到SQLAlchemy的映射
    OPERATOR_MAPPING = {
        'eq': lambda column, value: column == value,
        'ne': lambda column, value: column != value,
        'gt': lambda column, value: column > value,
        'gte': lambda column, value: column >= value,
        'lt': lambda column, value: column < value,
        'lte': lambda column, value: column <= value,
        'contains': lambda column, value: column.contains(value) if isinstance(value, str) else column == value,
        'not_contains': lambda column, value: ~column.contains(value) if isinstance(value, str) else column != value,
        'starts_with': lambda column, value: column.startswith(value) if isinstance(value, str) else column == value,
        'ends_with': lambda column, value: column.endswith(value) if isinstance(value, str) else column == value,
        'not_starts_with': lambda column, value: ~column.startswith(value) if isinstance(value, str) else column != value,
        'not_ends_with': lambda column, value: ~column.endswith(value) if isinstance(value, str) else column != value,
        'in': lambda column, value: column.in_(value if isinstance(value, (list, tuple)) else [value]),
        'not_in': lambda column, value: ~column.in_(value if isinstance(value, (list, tuple)) else [value]),
        'is_null': lambda column, value: column.is_(None),
        'is_not_null': lambda column, value: column.isnot(None),
    }

    def __init__(self, db: Session):
        """
        初始化查询构建器

        Args:
            db: 数据库会话
        """
        self.db = db
        self.base_query = db.query(TorrentInfo).filter(TorrentInfo.dr == 0)

    def reset(self) -> 'SearchQueryBuilder':
        """重置查询到初始状态"""
        self.base_query = self.db.query(TorrentInfo).filter(TorrentInfo.dr == 0)
        return self

    def apply_basic_filters(self, request: EnhancedAdvancedSearchRequest) -> 'SearchQueryBuilder':
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

        # 分享比率范围过滤
        if request.ratio_min is not None:
            filters.append(TorrentInfo.ratio >= str(request.ratio_min))

        if request.ratio_max is not None:
            filters.append(TorrentInfo.ratio <= str(request.ratio_max))

        # 添加日期范围过滤
        if request.added_date_min:
            added_min = validate_date_string(request.added_date_min)
            if added_min is not None:
                filters.append(TorrentInfo.added_date >= added_min)

        if request.added_date_max:
            added_max = validate_date_string(request.added_date_max)
            if added_max is not None:
                # 包含当天的23:59:59
                from datetime import timedelta
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

    def apply_condition_groups(self, condition_groups: Optional[List], between_group_logics: Optional[List[str]] = None) -> 'SearchQueryBuilder':
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
            try:
                # ✅ P2-1修复: 更安全的Pydantic对象和字典兼容处理
                if hasattr(group, 'logic'):
                    # SearchGroup Pydantic对象 - 使用getattr保护属性访问
                    logic = getattr(group, 'logic', None)
                    conditions = getattr(group, 'conditions', None)
                else:
                    # 字典格式
                    logic = group.get('logic') if group else None
                    conditions = group.get('conditions') if group else None

                # 验证必需字段
                if not logic or not isinstance(logic, str):
                    logger.warning(f"条件组缺少有效的logic字段: {logic}")
                    continue

                if not conditions or not isinstance(conditions, list):
                    logger.warning(f"条件组缺少有效的conditions字段: {conditions}")
                    continue

                # 转换为大写
                logic = logic.upper()

                if not conditions:
                    continue
            except Exception as e:
                logger.warning(f"解析条件组异常: {e}, group: {group}")
                continue

            condition_filters = []
            for condition in conditions:
                try:
                    condition_filter = self._build_condition_filter(condition)
                    if condition_filter is not None:
                        condition_filters.append(condition_filter)
                except Exception as e:
                    logger.warning(f"跳过无效条件 {condition}: {str(e)}")
                    continue

            if condition_filters:
                if logic == 'AND':
                    group_filters.append(and_(*condition_filters))
                else:  # OR
                    group_filters.append(or_(*condition_filters))

        if group_filters:
            # 使用组间逻辑关系连接条件组
            if between_group_logics and len(between_group_logics) >= len(group_filters) - 1:
                # 根据组间逻辑关系构建查询
                result_filter = group_filters[0]
                for i, group_filter in enumerate(group_filters[1:]):
                    logic = between_group_logics[i].upper() if i < len(between_group_logics) else 'AND'
                    if logic == 'AND':
                        result_filter = and_(result_filter, group_filter)
                    else:  # OR
                        result_filter = or_(result_filter, group_filter)
                self.base_query = self.base_query.filter(result_filter)
            else:
                # 默认组间使用AND逻辑
                self.base_query = self.base_query.filter(and_(*group_filters))

        return self

    def _build_condition_filter(self, condition) -> Optional:
        """
        构建单个条件的过滤

        Args:
            condition: 条件对象（SearchCondition Pydantic对象或字典）

        Returns:
            SQLAlchemy 过滤表达式
        """
        try:
            # ✅ P2-1修复: 更安全的Pydantic对象和字典兼容处理
            if hasattr(condition, 'field'):
                # SearchCondition Pydantic对象 - 使用getattr保护属性访问
                field = getattr(condition, 'field', None)
                operator = getattr(condition, 'operator', None)
                value = getattr(condition, 'value', None)
            else:
                # 字典格式
                if not condition or not isinstance(condition, dict):
                    logger.warning(f"条件对象无效: {condition}")
                    return None

                field = condition.get('field')
                operator = condition.get('operator')
                value = condition.get('value')

            # 验证必需字段
            if not field or not isinstance(field, str):
                logger.warning(f"条件缺少有效的field字段: {field}")
                return None

            if not operator or not isinstance(operator, str):
                logger.warning(f"条件缺少有效的operator字段: {operator}")
                return None

            if field == 'tracker_url':
                return self._build_tracker_url_filter(operator, value)

            if field == 'tracker_msg':
                return self._build_tracker_msg_filter(operator, value)

            if field not in self.FIELD_MAPPING:
                logger.warning(f"未知的搜索字段: {field}")
                return None

            column = self.FIELD_MAPPING[field]

            if operator not in self.OPERATOR_MAPPING:
                logger.warning(f"未知的操作符: {operator}")
                return None
        except Exception as e:
            logger.error(f"解析条件异常: {e}, condition: {condition}")
            return None

        # 处理特殊字段类型
        if field in ['size'] and operator in ['gt', 'gte', 'lt', 'lte']:
            # 大小字段可能包含单位
            if isinstance(value, str):
                value = validate_size_string(value)
                if value is None:
                    return None

        if field in ['added_date', 'completed_date', 'added_time'] and operator in ['gt', 'gte', 'lt', 'lte']:
            # 日期字段处理
            if isinstance(value, str):
                value = validate_date_string(value)
                if value is None:
                    return None




        return self.OPERATOR_MAPPING[operator](column, value)

    def _build_tracker_msg_filter(self, operator: str, value: Any) -> Optional[expression.ClauseElement]:
        """
        Build tracker_msg filter using tracker_info table.
        Match last_announce_msg OR last_scrape_msg on active trackers (dr == 0).
        """
        if not isinstance(value, str):
            logger.warning(f"tracker_msg search value must be string: {value}")
            return None

        tracker_text_filter = self._build_tracker_msg_text_filter(operator, value)
        if tracker_text_filter is None:
            return None

        return exists().where(
            and_(
                TrackerInfo.torrent_info_id == TorrentInfo.info_id,
                TrackerInfo.dr == 0,
                tracker_text_filter
            )
        )

    def _build_tracker_msg_text_filter(self, operator: str, value: str) -> Optional[expression.ClauseElement]:
        """Build OR text filter for tracker announce/scrape message fields."""
        announce_filter = self._build_text_filter(TrackerInfo.last_announce_msg, operator, value)
        scrape_filter = self._build_text_filter(TrackerInfo.last_scrape_msg, operator, value)

        if announce_filter is None or scrape_filter is None:
            return None

        return or_(announce_filter, scrape_filter)


    def _build_tracker_url_filter(self, operator: str, value: Any) -> Optional[expression.ClauseElement]:
        """
        Build tracker_url filter using tracker_info table.
        Match tracker_url field on active trackers (dr == 0).
        """
        if not isinstance(value, str):
            logger.warning(f"tracker_url search value must be string: {value}")
            return None

        tracker_url_filter = self._build_text_filter(TrackerInfo.tracker_url, operator, value)
        if tracker_url_filter is None:
            return None

        return exists().where(
            and_(
                TrackerInfo.torrent_info_id == TorrentInfo.info_id,
                TrackerInfo.dr == 0,
                tracker_url_filter
            )
        )

    def _build_text_filter(self, column, operator: str, value: str) -> Optional[expression.ClauseElement]:
        """
        Build text filter for a single column with None safety.

        ✅ P2修复：添加None值安全处理，避免SQL错误
        - 对于字符串操作符，先过滤掉None值
        - 对于等值比较操作符，可以安全处理None（SQL语义）
        """
        # 字符串操作符：需要先过滤None值，否则会引发SQL错误
        if operator in ['contains', 'not_contains', 'starts_with', 'ends_with',
                       'not_starts_with', 'not_ends_with']:
            from sqlalchemy import false as sql_false
            # 使用AND确保列值不为None，然后应用文本操作符
            if operator == 'contains':
                return and_(column.is_not(None), column.contains(value))
            if operator == 'not_contains':
                # 对于not_contains，None值也不包含目标字符串，所以视为匹配
                return or_(column.is_(None), and_(column.is_not(None), ~column.contains(value)))
            if operator == 'starts_with':
                return and_(column.is_not(None), column.startswith(value))
            if operator == 'ends_with':
                return and_(column.is_not(None), column.endswith(value))
            if operator == 'not_starts_with':
                # None不匹配任何前缀，所以视为符合not_starts_with条件
                return or_(column.is_(None), and_(column.is_not(None), ~column.startswith(value)))
            if operator == 'not_ends_with':
                # None不匹配任何后缀，所以视为符合not_ends_with条件
                return or_(column.is_(None), and_(column.is_not(None), ~column.endswith(value)))

        # 等值比较操作符：SQL语义可以安全处理None
        if operator in ['eq', 'equals']:
            return column == value
        if operator in ['ne', 'not_equals']:
            return column != value

        logger.warning(f"tracker_msg unsupported operator {operator}, fallback to contains")
        # 默认安全处理
        from sqlalchemy import false as sql_false
        return and_(column.is_not(None), column.contains(value))

    def apply_multi_select_conditions(
        self,
        status_multi: Optional[MultiSelectCondition],
        category_multi: Optional[MultiSelectCondition],
        tags_multi: Optional[MultiSelectCondition],
        downloader_multi: Optional[MultiSelectCondition]
    ) -> 'SearchQueryBuilder':
        """
        应用多选排除条件

        Args:
            status_multi: 状态多选条件
            category_multi: 分类多选条件
            tags_multi: 标签多选条件
            downloader_multi: 下载器多选条件

        Returns:
            self 支持链式调用
        """
        multi_conditions = [
            (status_multi, TorrentInfo.status, 'status'),
            (category_multi, TorrentInfo.category, 'category'),
            (tags_multi, TorrentInfo.tags, 'tags'),
            (downloader_multi, TorrentInfo.downloader_id, 'downloader_id')
        ]

        for condition, column, field_name in multi_conditions:
            if condition is None:
                continue

            values = condition.value
            if not values:
                continue

            # 确保values是列表
            if isinstance(values, str):
                separator = condition.separator or ','
                values = [v.strip() for v in values.split(separator) if v.strip()]
            elif not isinstance(values, list):
                values = [values]

            if not values:
                continue

            if condition.mode == 'include':
                # 包含模式: field IN (values)
                self.base_query = self.base_query.filter(column.in_(values))
            else:
                # 排除模式: field NOT IN (values)
                self.base_query = self.base_query.filter(~column.in_(values))

            logger.debug(f"应用多选条件 {field_name}: mode={condition.mode}, values={values}")

        return self

    def apply_sorting(self, sort_by: str, sort_order: str = 'desc') -> 'SearchQueryBuilder':
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
            sort_by = 'added_date'

        column = self.FIELD_MAPPING[sort_by]

        if sort_order and sort_order.lower() == 'asc':
            self.base_query = self.base_query.order_by(asc(column))
        else:
            self.base_query = self.base_query.order_by(desc(column))

        return self

    def apply_pagination(self, page: int = 1, limit: int = 20) -> 'SearchQueryBuilder':
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
    """搜索模板数据模型（用于数据库存储）"""

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
            # 生成模板ID
            template_id = str(uuid.uuid4())
            created_time = datetime.now()

            # 使用原生SQL创建表（如果不存在）
            self._ensure_table_exists()

            # 插入模板记录
            insert_sql = text("""
                INSERT INTO search_templates (id, user_id, name, description, conditions, is_default, is_public, usage_count, created_time, updated_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """)
            self.db.execute(insert_sql, (
                template_id,
                template_data['user_id'],
                template_data['name'],
                template_data.get('description', ''),
                json.dumps(template_data['conditions'], ensure_ascii=False),
                template_data.get('is_default', False),
                template_data.get('is_public', False),
                0,
                created_time,
                created_time
            ))
            self.db.commit()

            logger.info(f"创建搜索模板成功: {template_id}")
            return {
                'id': template_id,
                'created_time': created_time,
                **template_data
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"创建搜索模板失败: {str(e)}")
            raise

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
            self._ensure_table_exists()

            if is_public:
                query_sql = text("""
                    SELECT id, user_id, name, description, conditions, is_default, is_public, usage_count, created_time, updated_time
                    FROM search_templates
                    WHERE user_id = ? OR is_public = 1
                    ORDER BY created_time DESC
                """)
                params = [user_id]
            else:
                query_sql = text("""
                    SELECT id, user_id, name, description, conditions, is_default, is_public, usage_count, created_time, updated_time
                    FROM search_templates
                    WHERE user_id = ?
                    ORDER BY created_time DESC
                """)
                params = [user_id]

            result = self.db.execute(query_sql, params)
            rows = result.fetchall()

            templates = []
            for row in rows:
                templates.append({
                    'id': row[0],
                    'user_id': row[1],
                    'name': row[2],
                    'description': row[3],
                    'conditions': safe_json_parse(row[4], {}),
                    'is_default': bool(row[5]),
                    'is_public': bool(row[6]),
                    'usage_count': row[7],
                    'created_time': row[8],
                    'updated_time': row[9]
                })

            return templates

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
            self._ensure_table_exists()

            query_sql = text("""
                SELECT id, user_id, name, description, conditions, is_default, is_public, usage_count, created_time, updated_time
                FROM search_templates
                WHERE id = ?
            """)
            result = self.db.execute(query_sql, [template_id])
            row = result.fetchone()

            if row:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'name': row[2],
                    'description': row[3],
                    'conditions': safe_json_parse(row[4], {}),
                    'is_default': bool(row[5]),
                    'is_public': bool(row[6]),
                    'usage_count': row[7],
                    'created_time': row[8],
                    'updated_time': row[9]
                }

            return None

        except Exception as e:
            logger.error(f"获取模板失败: {str(e)}")
            return None

    def update(self, template_id: str, update_data: Dict[str, Any]) -> bool:
        """
        更新搜索模板

        Args:
            template_id: 模板ID
            update_data: 更新数据

        Returns:
            是否成功
        """
        try:
            self._ensure_table_exists()

            update_fields = []
            params = []

            if 'name' in update_data:
                update_fields.append('name = ?')
                params.append(update_data['name'])

            if 'description' in update_data:
                update_fields.append('description = ?')
                params.append(update_data['description'])

            if 'conditions' in update_data:
                update_fields.append('conditions = ?')
                params.append(json.dumps(update_data['conditions'], ensure_ascii=False))

            if 'is_public' in update_data:
                update_fields.append('is_public = ?')
                params.append(update_data['is_public'])

            if not update_fields:
                return False

            update_fields.append('updated_time = ?')
            params.append(datetime.now())
            params.append(template_id)

            update_sql = text(f"""
                UPDATE search_templates
                SET {', '.join(update_fields)}
                WHERE id = ?
            """)

            self.db.execute(update_sql, params)
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
            self._ensure_table_exists()

            delete_sql = text("DELETE FROM search_templates WHERE id = ?")
            self.db.execute(delete_sql, [template_id])
            self.db.commit()

            logger.info(f"删除搜索模板成功: {template_id}")
            return True

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
            是否成功
        """
        try:
            self._ensure_table_exists()

            update_sql = text("""
                UPDATE search_templates
                SET usage_count = usage_count + 1
                WHERE id = ?
            """)
            self.db.execute(update_sql, [template_id])
            self.db.commit()

            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"增加模板使用次数失败: {str(e)}")
            return False

    def _ensure_table_exists(self):
        """确保search_templates表存在"""
        check_sql = text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='search_templates'
        """)
        result = self.db.execute(check_sql).fetchone()

        if not result:
            create_sql = text("""
                CREATE TABLE search_templates (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description VARCHAR(500),
                    conditions TEXT NOT NULL,
                    is_default BOOLEAN DEFAULT 0,
                    is_public BOOLEAN DEFAULT 0,
                    usage_count INTEGER DEFAULT 0,
                    created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_time DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.db.execute(create_sql)

            # 创建索引（分开执行，SQLite一次只能执行一条语句）
            index_sql_1 = text("CREATE INDEX idx_search_templates_user_id ON search_templates(user_id)")
            index_sql_2 = text("CREATE INDEX idx_search_templates_is_public ON search_templates(is_public)")
            self.db.execute(index_sql_1)
            self.db.execute(index_sql_2)
            self.db.commit()

            logger.info("创建search_templates表成功")


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

    def search_torrents(
        self,
        request: EnhancedAdvancedSearchRequest,
        user_id: str
    ) -> Dict[str, Any]:
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
            # 添加调试日志：记录搜索请求参数
            logger.info(f"[高级搜索] 用户 {user_id} 发起搜索请求")
            logger.info(f"[高级搜索] 基础参数: name={request.name}, status={request.status}, category={request.category}")
            logger.info(f"[高级搜索] 条件组数量: {len(request.condition_groups) if request.condition_groups else 0}")
            logger.info(f"[高级搜索] 组间逻辑关系: {request.between_group_logics}")
            
            # 构建查询
            self.query_builder.reset()

            # 应用基础过滤
            self.query_builder.apply_basic_filters(request)
            logger.info(f"[高级搜索] 基础过滤已应用")

            # 应用高级条件组
            if request.condition_groups:
                logger.info(f"[高级搜索] 应用条件组，数量: {len(request.condition_groups)}")
                for idx, group in enumerate(request.condition_groups):
                    group_logic = group.logic if hasattr(group, 'logic') else group.get('logic', 'AND')
                    conditions = group.conditions if hasattr(group, 'conditions') else group.get('conditions', [])
                    logger.info(f"[高级搜索] 条件组 {idx}: logic={group_logic}, 条件数={len(conditions)}")
                    for cond_idx, cond in enumerate(conditions):
                        cond_field = cond.field if hasattr(cond, 'field') else cond.get('field')
                        cond_operator = cond.operator if hasattr(cond, 'operator') else cond.get('operator')
                        cond_value = cond.value if hasattr(cond, 'value') else cond.get('value')
                        logger.info(f"[高级搜索]   条件 {cond_idx}: field={cond_field}, operator={cond_operator}, value={cond_value}")
                
                self.query_builder.apply_condition_groups(request.condition_groups, request.between_group_logics)
                logger.info(f"[高级搜索] 条件组已应用")

            # 应用多选排除条件
            self.query_builder.apply_multi_select_conditions(
                request.status_multi,
                request.category_multi,
                request.tags_multi,
                request.downloader_multi
            )

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
            data = [convert_to_vo_with_trackers(self.db, torrent).model_dump(by_alias=True, exclude_none=True) for torrent in results]

            # 计算总页数
            total_pages = (total + request.limit - 1) // request.limit

            logger.info(f"用户 {user_id} 执行高级搜索，找到 {total} 条结果")

            return {
                'status': 'success',
                'msg': '搜索成功',
                'code': '200',
                'data': data,
                'total': total,
                'page': request.page,
                'limit': request.limit,
                'total_pages': total_pages
            }

        except Exception as e:
            logger.error(f"高级搜索失败: {str(e)}")
            import traceback
            logger.error(f"高级搜索异常堆栈: {traceback.format_exc()}")
            return {
                'status': 'failed',
                'msg': f'搜索失败: {str(e)}',
                'code': '500',
                'data': [],
                'total': 0,
                'page': request.page,
                'limit': request.limit,
                'total_pages': 0
            }

    def create_search_template(
        self,
        request,
        user_id: str
    ) -> Dict[str, Any]:
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
            if hasattr(request, 'name'):
                # SearchTemplateCreate Pydantic对象
                template_data = {
                    'user_id': user_id,
                    'name': request.name,
                    'description': request.description,
                    'conditions': request.conditions,
                    'is_default': False,
                    'is_public': request.is_public
                }
            else:
                # 字典格式
                template_data = {
                    'user_id': user_id,
                    'name': request.get('name'),
                    'description': request.get('description'),
                    'conditions': request.get('conditions'),
                    'is_default': False,
                    'is_public': request.get('is_public', False)
                }

            result = self.template_model.create(template_data)

            return {
                'status': 'success',
                'msg': '创建模板成功',
                'code': '200',
                'data': result
            }

        except Exception as e:
            logger.error(f"创建搜索模板失败: {str(e)}")
            return {
                'status': 'failed',
                'msg': f'创建模板失败: {str(e)}',
                'code': '500',
                'data': None
            }

    def get_search_templates(
        self,
        user_id: str,
        is_public: bool = False
    ) -> Dict[str, Any]:
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
                'status': 'success',
                'msg': '获取模板成功',
                'code': '200',
                'data': templates,
                'total': len(templates)
            }

        except Exception as e:
            logger.error(f"获取搜索模板失败: {str(e)}")
            return {
                'status': 'failed',
                'msg': f'获取模板失败: {str(e)}',
                'code': '500',
                'data': [],
                'total': 0
            }

    def update_search_template(
        self,
        template_id: str,
        request: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
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
                return {
                    'status': 'failed',
                    'msg': '模板不存在',
                    'code': '404',
                    'data': None
                }

            if template['user_id'] != user_id:
                return {
                    'status': 'failed',
                    'msg': '无权修改此模板',
                    'code': '403',
                    'data': None
                }

            # 执行更新
            update_data = {}
            if 'name' in request:
                update_data['name'] = request['name']
            if 'description' in request:
                update_data['description'] = request['description']
            if 'conditions' in request:
                update_data['conditions'] = request['conditions']
            if 'is_public' in request:
                update_data['is_public'] = request['is_public']

            success = self.template_model.update(template_id, update_data)

            if success:
                return {
                    'status': 'success',
                    'msg': '更新模板成功',
                    'code': '200',
                    'data': {'id': template_id, **update_data}
                }
            else:
                return {
                    'status': 'failed',
                    'msg': '更新模板失败',
                    'code': '500',
                    'data': None
                }

        except Exception as e:
            logger.error(f"更新搜索模板失败: {str(e)}")
            return {
                'status': 'failed',
                'msg': f'更新模板失败: {str(e)}',
                'code': '500',
                'data': None
            }

    def delete_search_template(
        self,
        template_id: str,
        user_id: str
    ) -> Dict[str, Any]:
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
                return {
                    'status': 'failed',
                    'msg': '模板不存在',
                    'code': '404',
                    'data': None
                }

            if template['user_id'] != user_id:
                return {
                    'status': 'failed',
                    'msg': '无权删除此模板',
                    'code': '403',
                    'data': None
                }

            # 执行删除
            success = self.template_model.delete(template_id)

            if success:
                return {
                    'status': 'success',
                    'msg': '删除模板成功',
                    'code': '200',
                    'data': {'id': template_id}
                }
            else:
                return {
                    'status': 'failed',
                    'msg': '删除模板失败',
                    'code': '500',
                    'data': None
                }

        except Exception as e:
            logger.error(f"删除搜索模板失败: {str(e)}")
            return {
                'status': 'failed',
                'msg': f'删除模板失败: {str(e)}',
                'code': '500',
                'data': None
            }

    def apply_search_template(
        self,
        template_id: str,
        user_id: str
    ) -> Dict[str, Any]:
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
                return {
                    'status': 'failed',
                    'msg': '模板不存在',
                    'code': '404',
                    'data': None
                }

            # 检查权限（公开模板或自己的模板）
            if template['user_id'] != user_id and not template['is_public']:
                return {
                    'status': 'failed',
                    'msg': '无权使用此模板',
                    'code': '403',
                    'data': None
                }

            # 增加使用次数
            self.template_model.increment_usage(template_id)

            logger.info(f"用户 {user_id} 应用搜索模板: {template_id}")

            return {
                'status': 'success',
                'msg': '应用模板成功',
                'code': '200',
                'data': {
                    'id': template['id'],
                    'name': template['name'],
                    'description': template['description'],
                    'conditions': template['conditions']
                }
            }

        except Exception as e:
            logger.error(f"应用搜索模板失败: {str(e)}")
            return {
                'status': 'failed',
                'msg': f'应用模板失败: {str(e)}',
                'code': '500',
                'data': None
            }

    def delete_torrents_batch(
        self,
        request,
        user_id: str
    ) -> Dict[str, Any]:
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
            if hasattr(request, 'torrent_ids'):
                # TorrentDeleteRequest Pydantic对象
                torrent_ids = request.torrent_ids
                delete_data = request.delete_data
                id_recycle = request.id_recycle
            else:
                # 字典格式
                torrent_ids = request.get('torrent_ids', [])
                delete_data = request.get('delete_data', True)
                id_recycle = request.get('id_recycle', False)

            if not torrent_ids:
                return {
                    'status': 'failed',
                    'msg': '请选择要删除的种子',
                    'code': '400',
                    'data': None
                }

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
                reason=f"用户 {user_id} 批量删除"
            )

            # 执行删除
            result = self.deletion_service.delete_torrents(delete_request)

            # 构建响应数据
            response_data = {
                'success_count': result.success_count,
                'failed_count': result.failed_count,
                'skipped_count': result.skipped_count,
                'total_size_freed': result.total_size_freed,
                'deleted_torrents': result.deleted_torrents,
                'failed_torrents': result.failed_torrents,
                'safety_warnings': result.safety_warnings
            }

            logger.info(f"用户 {user_id} 批量删除种子: 成功{result.success_count}, 失败{result.failed_count}")

            return {
                'status': 'success',
                'msg': f'删除完成: 成功{result.success_count}, 失败{result.failed_count}, 跳过{result.skipped_count}',
                'code': '200',
                'data': response_data
            }

        except Exception as e:
            logger.error(f"批量删除种子失败: {str(e)}")
            return {
                'status': 'failed',
                'msg': f'批量删除失败: {str(e)}',
                'code': '500',
                'data': None
            }

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
            status_stats = self.db.query(
                TorrentInfo.status,
                func.count(TorrentInfo.info_id)
            ).filter(TorrentInfo.dr == 0).group_by(TorrentInfo.status).all()

            stats['status_distribution'] = [
                {'status': s[0] or 'unknown', 'count': s[1]}
                for s in status_stats
            ]

            # 分类分布
            category_stats = self.db.query(
                TorrentInfo.category,
                func.count(TorrentInfo.info_id)
            ).filter(
                TorrentInfo.dr == 0,
                TorrentInfo.category.isnot(None)
            ).group_by(TorrentInfo.category).all()

            stats['category_distribution'] = [
                {'category': c[0] or 'uncategorized', 'count': c[1]}
                for c in category_stats
            ]

            # 下载器分布
            downloader_stats = self.db.query(
                TorrentInfo.downloader_name,
                func.count(TorrentInfo.info_id)
            ).filter(TorrentInfo.dr == 0).group_by(TorrentInfo.downloader_name).all()

            stats['downloader_distribution'] = [
                {'downloader': d[0], 'count': d[1]}
                for d in downloader_stats
            ]

            # 总体统计
            total_torrents = self.db.query(func.count(TorrentInfo.info_id)).filter(
                TorrentInfo.dr == 0
            ).scalar()

            total_size = self.db.query(
                func.sum(TorrentInfo.size)
            ).filter(TorrentInfo.dr == 0).scalar() or 0

            stats['total_torrents'] = total_torrents
            stats['total_size'] = total_size

            # 模板统计
            self.template_model._ensure_table_exists()
            template_count = self.db.execute(
                text("SELECT COUNT(*) FROM search_templates")
            ).scalar()

            stats['total_templates'] = template_count or 0

            return {
                'status': 'success',
                'msg': '获取统计成功',
                'code': '200',
                'data': stats
            }

        except Exception as e:
            logger.error(f"获取搜索统计失败: {str(e)}")
            return {
                'status': 'failed',
                'msg': f'获取统计失败: {str(e)}',
                'code': '500',
                'data': {}
            }
