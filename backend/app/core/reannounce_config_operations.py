# -*- coding: utf-8 -*-
"""
Tracker Reannounce 站点配置数据库操作

提供 tracker_reannounce_config 表的 CRUD 操作和域名匹配工具函数。
"""

import uuid
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
from datetime import datetime

from sqlalchemy.orm import Session

from app.torrents.models import TrackerReannounceConfig
from app.core.database_result import DatabaseResult

import logging
logger = logging.getLogger(__name__)


# ==================== CRUD 操作 ====================

def create_config(db: Session, config_data: Dict[str, Any]) -> DatabaseResult:
    """创建站点配置"""
    try:
        if not config_data.get("domain_pattern"):
            return DatabaseResult.validation_error_result("domain_pattern 不能为空")

        interval = config_data.get("interval_minutes", 30)
        if not validate_interval(interval):
            return DatabaseResult.validation_error_result("interval_minutes 无效，须为正整数")

        config = TrackerReannounceConfig(
            domain_pattern=config_data["domain_pattern"],
            domain_display_name=config_data.get("domain_display_name", config_data["domain_pattern"]),
            interval_minutes=interval,
            enabled=config_data.get("enabled", True),
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        return DatabaseResult.success_result(data=config, message="配置创建成功", affected_rows=1)

    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(message=f"创建配置失败: {str(e)}")


def get_config(db: Session, config_id: str) -> DatabaseResult:
    """按ID查询配置"""
    try:
        config = db.query(TrackerReannounceConfig).filter(
            TrackerReannounceConfig.id_ == config_id,
            TrackerReannounceConfig.dr == 0,
        ).first()
        if config:
            return DatabaseResult.success_result(data=config, message="查询成功")
        return DatabaseResult.not_found_result(message=f"配置不存在 [id={config_id}]")
    except Exception as e:
        return DatabaseResult.database_error_result(message=f"查询失败: {str(e)}")


def get_configs(db: Session) -> DatabaseResult:
    """查询所有配置"""
    try:
        configs = db.query(TrackerReannounceConfig).filter(
            TrackerReannounceConfig.dr == 0,
        ).all()
        return DatabaseResult.success_result(data=configs, message="查询成功", total_count=len(configs))
    except Exception as e:
        return DatabaseResult.database_error_result(message=f"查询失败: {str(e)}")


def get_enabled_configs(db: Session) -> DatabaseResult:
    """查询所有启用的配置"""
    try:
        configs = db.query(TrackerReannounceConfig).filter(
            TrackerReannounceConfig.enabled == True,
            TrackerReannounceConfig.dr == 0,
        ).all()
        return DatabaseResult.success_result(data=configs, message="查询成功", total_count=len(configs))
    except Exception as e:
        return DatabaseResult.database_error_result(message=f"查询失败: {str(e)}")


def update_config(db: Session, config_id: str, update_data: Dict[str, Any]) -> DatabaseResult:
    """更新配置"""
    try:
        config = db.query(TrackerReannounceConfig).filter(
            TrackerReannounceConfig.id_ == config_id,
            TrackerReannounceConfig.dr == 0,
        ).first()
        if not config:
            return DatabaseResult.not_found_result(message=f"配置不存在 [id={config_id}]")

        if "interval_minutes" in update_data and not validate_interval(update_data["interval_minutes"]):
            return DatabaseResult.validation_error_result("interval_minutes 无效")

        for key, value in update_data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        config.update_time = datetime.now()

        db.commit()
        db.refresh(config)
        return DatabaseResult.success_result(data=config, message="更新成功", affected_rows=1)

    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(message=f"更新失败: {str(e)}")


def update_last_announce_time(db: Session, config_id: str) -> None:
    """更新配置的最后汇报时间（单条，向后兼容）"""
    batch_update_last_announce_time(db, [config_id])


def batch_update_last_announce_time(db: Session, config_ids: list) -> None:
    """批量更新配置的最后汇报时间，单次commit减少SQLite锁竞争"""
    if not config_ids:
        return
    try:
        now = datetime.now()
        configs = db.query(TrackerReannounceConfig).filter(
            TrackerReannounceConfig.id_.in_(config_ids),
        ).all()
        for config in configs:
            config.last_announce_time = now
        db.commit()
    except Exception as e:
        logger.warning(f"批量更新最后汇报时间失败: {e}")
        db.rollback()


def delete_config(db: Session, config_id: str) -> DatabaseResult:
    """软删除配置"""
    try:
        config = db.query(TrackerReannounceConfig).filter(
            TrackerReannounceConfig.id_ == config_id,
            TrackerReannounceConfig.dr == 0,
        ).first()
        if not config:
            return DatabaseResult.not_found_result(message=f"配置不存在 [id={config_id}]")

        config.dr = 1
        db.commit()
        return DatabaseResult.success_result(message="删除成功", affected_rows=1)

    except Exception as e:
        db.rollback()
        return DatabaseResult.database_error_result(message=f"删除失败: {str(e)}")


def batch_update_configs(db: Session, items: List[Dict[str, Any]]) -> DatabaseResult:
    """
    批量更新配置（支持部分成功）

    Args:
        items: 配置项列表，每项包含 config_id 和需要更新的字段

    Returns:
        DatabaseResult 包含批量更新结果
    """
    results = []
    success_count = 0
    failed_count = 0

    logger.info(f"batch_update_configs 收到 {len(items)} 个项目")

    for item in items:
        config_id = item.get("config_id")
        logger.info(f"处理项目 config_id={config_id}, 完整数据={item}")
        logger.info(f"item 类型: {type(item)}, item.items() 结果: {list(item.items()) if hasattr(item, 'items') else 'N/A'}")

        if not config_id:
            results.append({"config_id": None, "success": False, "message": "config_id 不能为空"})
            failed_count += 1
            continue

        # 提取需要更新的字段（排除 config_id）
        update_data = {}
        for k, v in item.items():
            logger.info(f"  检查字段: k={k}, v={v}, v类型={type(v)}, k!='config_id'={k != 'config_id'}, v is not None={v is not None}")
            if k != "config_id" and v is not None:
                update_data[k] = v

        logger.info(f"最终提取的 update_data={update_data}, 长度={len(update_data)}")

        if not update_data:
            results.append({"config_id": config_id, "success": False, "message": "没有需要更新的字段"})
            failed_count += 1
            continue

        try:
            config = db.query(TrackerReannounceConfig).filter(
                TrackerReannounceConfig.id_ == config_id,
                TrackerReannounceConfig.dr == 0,
            ).first()

            if not config:
                results.append({"config_id": config_id, "success": False, "message": "配置不存在"})
                failed_count += 1
                continue

            # 验证间隔
            if "interval_minutes" in update_data and not validate_interval(update_data["interval_minutes"]):
                results.append({"config_id": config_id, "success": False, "message": "interval_minutes 无效"})
                failed_count += 1
                continue

            # 更新字段
            for key, value in update_data.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            config.update_time = datetime.now()

            db.commit()
            results.append({"config_id": config_id, "success": True, "message": "更新成功"})
            success_count += 1

        except Exception as e:
            db.rollback()
            results.append({"config_id": config_id, "success": False, "message": f"更新失败: {str(e)}"})
            failed_count += 1

    return DatabaseResult.success_result(
        data={
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        },
        message=f"批量更新完成，成功{success_count}条，失败{failed_count}条",
        total_count=len(items)
    )


# ==================== 工具函数 ====================

def match_domain(domain: str, config) -> bool:
    """
    判断域名是否匹配配置

    Args:
        domain: 待匹配的域名
        config: 配置对象（需有 domain_pattern 属性）

    Returns:
        是否匹配
    """
    if not domain or not config.domain_pattern:
        return False

    pattern = config.domain_pattern
    # 先将 % 通配符替换为占位符，再转义其余特殊字符，最后还原占位符为 .*
    placeholder = "\x00PCT\x00"
    safe = pattern.replace("%", placeholder)
    escaped = re.escape(safe)
    regex_pattern = "^" + escaped.replace(placeholder, ".*") + "$"
    try:
        return bool(re.match(regex_pattern, domain, re.IGNORECASE))
    except re.error:
        return domain == pattern


def filter_enabled_configs(configs: list) -> list:
    """过滤出启用的配置"""
    return [c for c in configs if c.enabled]


def validate_interval(interval) -> bool:
    """验证汇报间隔是否有效"""
    if interval is None:
        return False
    return isinstance(interval, int) and interval >= 1


def extract_domains_from_trackers(tracker_urls: List[str]) -> List[str]:
    """
    从 tracker URL 列表中提取去重的域名

    Args:
        tracker_urls: tracker URL 列表

    Returns:
        去重后的域名列表
    """
    domains = set()
    for url in tracker_urls:
        if not url:
            continue
        try:
            parsed = urlparse(url if "://" in url else f"http://{url}")
            host = parsed.hostname
            # 过滤无效 hostname：需包含点号或为IP地址格式
            if host and ("." in host or re.match(r'^\d{1,3}(\.\d{1,3}){3}$', host)):
                domains.add(host)
        except Exception:
            continue
    return list(domains)
