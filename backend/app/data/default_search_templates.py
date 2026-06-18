# -*- coding: utf-8 -*-
"""
系统预设搜索模板（v1.0.5 查询模板系统）

提供 4 个精选常用查询模板，在 init_db() 时幂等初始化。
模板 conditions 遵循"前端形态"约定（见 PLANS/v1.0.5.md query_config 设计）：
  - source=simple：与 index.vue 的 listQuery 1:1 对齐，数组保留数组形态
  - source=advanced：AdvancedSearchBuilder 的 condition_groups 结构

这些模板写入 search_templates 表，is_default=True（系统预设）、is_public=True（所有人可见）。
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ========== 状态枚举（与 frontend/src/constants/status-config.ts STATUS_OPTIONS 对齐）==========
# STATUS_OPTIONS = [seeding, downloading, paused, queuedDL, error, checking]

# ========== 精选预设模板（4 个）==========
DEFAULT_SEARCH_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "活跃种子",
        "description": "正在下载或做种的种子",
        "conditions": {
            "source": "simple",
            "version": 1,
            "listQuery": {
                "name_like": "",
                "downloader_id": [],
                "status": ["downloading", "seeding"],
                "showActiveOnly": False,
                "sort_by": "added_date",
                "sort_order": "desc"
            }
        },
    },
    {
        "name": "错误状态",
        "description": "处于错误状态的种子（含 tracker 异常）",
        "conditions": {
            "source": "simple",
            "version": 1,
            "listQuery": {
                "name_like": "",
                "downloader_id": [],
                "status": ["error"],
                "showActiveOnly": False,
                "sort_by": "added_date",
                "sort_order": "desc"
            }
        },
    },
    {
        "name": "已暂停",
        "description": "所有已暂停的种子",
        "conditions": {
            "source": "simple",
            "version": 1,
            "listQuery": {
                "name_like": "",
                "downloader_id": [],
                "status": ["paused"],
                "showActiveOnly": False,
                "sort_by": "added_date",
                "sort_order": "desc"
            }
        },
    },
    {
        "name": "大文件",
        "description": "大于 10GB 的种子（高级搜索）",
        "conditions": {
            "source": "advanced",
            "version": 1,
            "condition_groups": [
                {
                    "id": "preset_large_files",
                    "name": "大文件",
                    "logic": "and",
                    "conditions": [
                        {
                            "id": "preset_large_files_cond",
                            "field": "size",
                            "operator": "gt",
                            "value": {"min": 10, "minUnit": "GB"},
                            "mode": "include"
                        }
                    ]
                }
            ],
            "sort_by": "size",
            "sort_order": "desc"
        },
    },
]


def init_default_search_templates(db_session: Session) -> int:
    """
    初始化系统预设搜索模板到 search_templates 表。

    幂等：按 name 去重，已存在的跳过。
    复用 SearchTemplateModel._ensure_table_exists 的建表逻辑（确保表存在）。

    Args:
        db_session: SQLAlchemy 同步会话

    Returns:
        int: 本次新建的模板数量
    """
    from app.services.advanced_search import SearchTemplateModel

    created_count = 0
    try:
        # 复用既有建表逻辑（避免重复实现 CREATE TABLE）
        template_model = SearchTemplateModel(db_session)
        template_model._ensure_table_exists()

        # 查询已存在的预设模板名（is_default=1 视为系统预设，幂等依据）
        existing_sql = text(
            "SELECT name FROM search_templates WHERE is_default = 1"
        )
        existing_rows = db_session.execute(existing_sql).fetchall()
        existing_names = {row[0] for row in existing_rows}

        now = datetime.now()
        import uuid

        for tpl in DEFAULT_SEARCH_TEMPLATES:
            name = tpl["name"]
            if name in existing_names:
                logger.info(f"系统预设搜索模板已存在，跳过: {name}")
                continue

            template_id = str(uuid.uuid4())
            insert_sql = text("""
                INSERT INTO search_templates
                    (id, user_id, name, description, conditions, is_default, is_public, usage_count, created_time, updated_time)
                VALUES
                    (:id, :user_id, :name, :description, :conditions, :is_default, :is_public, :usage_count, :created_time, :updated_time)
            """)
            db_session.execute(insert_sql, {
                "id": template_id,
                "user_id": "system",  # 系统预设模板 user_id 标记为 system
                "name": name,
                "description": tpl.get("description", ""),
                "conditions": json.dumps(tpl["conditions"], ensure_ascii=False),
                "is_default": 1,  # 系统预设
                "is_public": 1,   # 所有人可见
                "usage_count": 0,
                "created_time": now,
                "updated_time": now,
            })
            created_count += 1
            logger.info(f"创建系统预设搜索模板: {name}")

        db_session.commit()
        logger.info(f"系统预设搜索模板初始化完成，共创建 {created_count} 个模板")
        return created_count

    except Exception as e:
        db_session.rollback()
        logger.error(f"初始化系统预设搜索模板失败: {e}")
        raise


__all__ = [
    "DEFAULT_SEARCH_TEMPLATES",
    "init_default_search_templates",
]
