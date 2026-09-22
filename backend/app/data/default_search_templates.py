# -*- coding: utf-8 -*-
"""
系统预设搜索模板（v1.0.5 查询模板系统）

提供 4 个精选常用查询模板，在 init_db() 时幂等初始化。
模板 conditions 遵循"前端形态"约定（见 PLANS/archive/v1.0.5.md query_config 设计）：
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

# ========== 系统预设稳定身份键（desktop-bilingual P4 子范围提前）==========
# 与名称/描述解耦的幂等身份；前端按该键本地化展示（Q01），
# 中文名称仅作为一次性回填的历史迁移辅助证据（PLANS/bilingual/system-content.md §1）。
DEFAULT_SEARCH_TEMPLATE_KEYS = {
    "active_torrents",
    "error_status",
    "paused",
    "large_files",
}

# ========== 精选预设模板（4 个）==========
DEFAULT_SEARCH_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "活跃种子",
        "description": "正在下载或做种的种子",
        "preset_key": "active_torrents",
        "conditions": {
            "source": "simple",
            "version": 1,
            "listQuery": {
                "name_like": "",
                "downloader_id": [],
                "status": ["downloading", "seeding"],
                "showActiveOnly": False,
                "sort_by": "added_date",
                "sort_order": "desc",
            },
        },
    },
    {
        "name": "错误状态",
        "description": "处于错误状态的种子（含 tracker 异常）",
        "preset_key": "error_status",
        "conditions": {
            "source": "simple",
            "version": 1,
            "listQuery": {
                "name_like": "",
                "downloader_id": [],
                "status": ["error"],
                "showActiveOnly": False,
                "sort_by": "added_date",
                "sort_order": "desc",
            },
        },
    },
    {
        "name": "已暂停",
        "description": "所有已暂停的种子",
        "preset_key": "paused",
        "conditions": {
            "source": "simple",
            "version": 1,
            "listQuery": {
                "name_like": "",
                "downloader_id": [],
                "status": ["paused"],
                "showActiveOnly": False,
                "sort_by": "added_date",
                "sort_order": "desc",
            },
        },
    },
    {
        "name": "大文件",
        "description": "大于 10GB 的种子（高级搜索）",
        "preset_key": "large_files",
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
                            "operator": "greater_than",
                            "value": {"value": 10, "unit": "GB"},
                            "mode": "include",
                        }
                    ],
                }
            ],
            "sort_by": "size",
            "sort_order": "desc",
        },
    },
]


def init_default_search_templates(db_session: Session) -> int:
    """
    初始化系统预设搜索模板到 search_templates 表。

    幂等（desktop-bilingual P4 子范围：按 preset_key，与名称解耦）：
    1. 先查 preset_key：已存在的跳过；
    2. key 不存在但旧中文名存在（is_default=1 的历史行，迁移回填遗漏的自愈路径）
       → 恰一行时回填该行 preset_key（首启兼容，中文名仅作迁移辅助证据），
         多行歧义不猜（B02，保持 NULL 并记日志），零行走插入；
    3. 都不存在 → 插入新记录（直接写 preset_key）。

    注意：search_templates 表由 Alembic 迁移（95ef8bd8b47a 建表 /
    b3e5f7a9c1d2 加 preset_key 列）统一管理，本函数不再负责建表。

    Args:
        db_session: SQLAlchemy 同步会话

    Returns:
        int: 本次新建的模板数量（回填不计入新建）
    """
    created_count = 0
    try:
        # 已存在的系统预设身份：preset_key（新库）与中文名（旧库兼容判定）双读
        existing_sql = text(
            "SELECT name, preset_key FROM search_templates "
            "WHERE is_default = 1 AND (preset_key IS NOT NULL OR name IS NOT NULL)"
        )
        existing_rows = db_session.execute(existing_sql).fetchall()
        existing_keys = {row[1] for row in existing_rows if row[1]}
        existing_names = [row[0] for row in existing_rows if row[0]]

        now = datetime.now()
        import uuid

        for tpl in DEFAULT_SEARCH_TEMPLATES:
            name = tpl["name"]
            preset_key = tpl["preset_key"]
            if preset_key in existing_keys:
                logger.info(f"系统预设搜索模板已存在（preset_key={preset_key}），跳过")
                continue

            # 首启兼容：旧库历史行（迁移回填遗漏）按中文名识别；仅恰一行时回填
            if name in existing_names:
                legacy_count = existing_names.count(name)
                if legacy_count == 1:
                    db_session.execute(
                        text(
                            "UPDATE search_templates SET preset_key = :key "
                            "WHERE is_default = 1 AND preset_key IS NULL AND name = :name"
                        ),
                        {"key": preset_key, "name": name},
                    )
                    logger.info(f"系统预设搜索模板按旧中文名回填身份: {name} -> {preset_key}")
                else:
                    # 歧义（人工复制/同名）：不猜，保持 NULL（B02）
                    logger.warning(f"系统预设搜索模板中文名存在 {legacy_count} 行歧义，保持 preset_key 为 NULL: {name}")
                continue

            template_id = str(uuid.uuid4())
            insert_sql = text(
                """
                INSERT INTO search_templates
                    (id, user_id, name, description, conditions, is_default, is_public, usage_count, created_time, updated_time, preset_key)
                VALUES
                    (:id, :user_id, :name, :description, :conditions, :is_default, :is_public, :usage_count, :created_time, :updated_time, :preset_key)
            """
            )
            db_session.execute(
                insert_sql,
                {
                    "id": template_id,
                    "user_id": "system",  # 系统预设模板 user_id 标记为 system
                    "name": name,
                    "description": tpl.get("description", ""),
                    "conditions": json.dumps(tpl["conditions"], ensure_ascii=False),
                    "is_default": 1,  # 系统预设
                    "is_public": 1,  # 所有人可见
                    "usage_count": 0,
                    "created_time": now,
                    "updated_time": now,
                    "preset_key": preset_key,
                },
            )
            created_count += 1
            logger.info(f"创建系统预设搜索模板: {name} (preset_key={preset_key})")

        db_session.commit()
        logger.info(f"系统预设搜索模板初始化完成，共创建 {created_count} 个模板")
        return created_count

    except Exception as e:
        db_session.rollback()
        logger.error(f"初始化系统预设搜索模板失败: {e}")
        raise


__all__ = [
    "DEFAULT_SEARCH_TEMPLATES",
    "DEFAULT_SEARCH_TEMPLATE_KEYS",
    "init_default_search_templates",
]
