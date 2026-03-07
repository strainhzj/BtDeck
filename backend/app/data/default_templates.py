# -*- coding: utf-8 -*-
"""
系统默认配置模板数据

提供5个系统默认模板，涵盖qBittorrent和Transmission两种下载器类型，
包括标准配置、高性能配置和分时段配置示例。
"""
import logging

logger = logging.getLogger(__name__)


# ========== 模板配置常量 ==========

# qBittorrent标准配置：适合家庭用户，适中的速度限制
QB_STANDARD_CONFIG = {
    "dl_speed_limit": 1024,  # 1MB/s下载速度
    "ul_speed_limit": 512,   # 512KB/s上传速度
    "speed_unit": 0,         # KB/s单位
    "enable_schedule": False,
    "override_local": True,
    "advanced_settings": {
        # 连接设置
        "max_connec": 500,          # 最大全局连接数
        "max_numconn": 100,         # 每任务最大连接数
        "max_uploads": 20,          # 最大上传 slots

        # 队列设置
        "queueing_enabled": True,
        "max_active_downloads": 3,
        "max_active_torrents": 5,
        "max_active_uploads": 3,

        # 资源限制
        "dl_limit": 1024,           # 下载限制(KB/s)
        "up_limit": 512,            # 上传限制(KB/s)

        # 其他设置
        "alt_dl_limit": 1024,       # 备用下载限制
        "alt_up_limit": 512,        # 备用上传限制
        "scheduler": False,         # 不使用分时段
    }
}

# qBittorrent高性能配置：高带宽、高连接数，不限速
QB_HIGH_PERFORMANCE_CONFIG = {
    "dl_speed_limit": 0,       # 不限速
    "ul_speed_limit": 0,       # 不限速
    "speed_unit": 1,           # MB/s单位
    "enable_schedule": False,
    "override_local": True,
    "advanced_settings": {
        # 连接设置 - 更激进的参数
        "max_connec": 1000,         # 最大全局连接数
        "max_numconn": 500,         # 每任务最大连接数
        "max_uploads": 100,         # 最大上传 slots

        # 队列设置 - 更多并发任务
        "queueing_enabled": True,
        "max_active_downloads": 10,
        "max_active_torrents": 20,
        "max_active_uploads": 10,

        # 资源限制 - 不限速
        "dl_limit": 0,              # 不限速
        "up_limit": 0,              # 不限速

        # 其他设置
        "alt_dl_limit": 0,
        "alt_up_limit": 0,
        "scheduler": False,
    }
}

# Transmission标准配置：适合家庭用户
TR_STANDARD_CONFIG = {
    "dl_speed_limit": 1024,  # 1MB/s下载速度
    "ul_speed_limit": 512,   # 512KB/s上传速度
    "speed_unit": 0,         # KB/s单位
    "enable_schedule": False,
    "override_local": True,
    "advanced_settings": {
        # 速度设置
        "speed-limit-down": 1024,       # 下载限制(KB/s)
        "speed-limit-up": 512,          # 上传限制(KB/s)
        "speed-limit-down-enabled": True,
        "speed-limit-up-enabled": True,

        # 连接设置
        "peer-limit-global": 500,       # 全局连接数限制
        "peer-limit-per-torrent": 100,  # 每任务连接数限制

        # 队列设置
        "queue-stalled-enabled": True,
        "queue-stalled-minutes": 30,
        "download-queue-enabled": True,
        "download-queue-size": 3,
        "seed-queue-enabled": True,
        "seed-queue-size": 3,

        # 其他设置
        "alt-speed-enabled": False,     # 不使用备用速度
    }
}

# Transmission高性能配置：高带宽、高连接数
TR_HIGH_PERFORMANCE_CONFIG = {
    "dl_speed_limit": 0,       # 不限速
    "ul_speed_limit": 0,       # 不限速
    "speed_unit": 1,           # MB/s单位
    "enable_schedule": False,
    "override_local": True,
    "advanced_settings": {
        # 速度设置 - 不限速
        "speed-limit-down": 0,
        "speed-limit-up": 0,
        "speed-limit-down-enabled": False,
        "speed-limit-up-enabled": False,

        # 连接设置 - 更激进的参数
        "peer-limit-global": 1000,      # 全局连接数限制
        "peer-limit-per-torrent": 500,  # 每任务连接数限制

        # 队列设置 - 更多并发任务
        "queue-stalled-enabled": True,
        "queue-stalled-minutes": 30,
        "download-queue-enabled": True,
        "download-queue-size": 10,
        "seed-queue-enabled": True,
        "seed-queue-size": 10,

        # 其他设置
        "alt-speed-enabled": False,
    }
}

# 夜间不限速模板：包含分时段速度规则
NIGHT_UNLIMITED_CONFIG = {
    "dl_speed_limit": 0,      # 默认不限速（会被分时段规则覆盖）
    "ul_speed_limit": 0,      # 默认不限速
    "speed_unit": 0,          # KB/s单位
    "enable_schedule": True,  # 启用分时段
    "override_local": True,
    "advanced_settings": {
        # qBittorrent基本配置
        "max_connec": 500,
        "max_numconn": 100,
        "max_uploads": 20,
    },
    # 分时段规则（独立存储到 speed_schedule_rules 表）
    # 注意：这些规则会在应用模板时创建到数据库表中
    "schedule_rules": [
        {
            "start_time": "08:00:00",
            "end_time": "23:59:59",
            "dl_speed_limit": 512,    # 工作日白天限速512KB/s
            "ul_speed_limit": 256,    # 工作日白天限速256KB/s
            "days_of_week": "12345",  # 1=周一，5=周五
            "enabled": True
        }
    ]
}


# ========== 系统默认模板定义 ==========

DEFAULT_TEMPLATES = [
    {
        "name": "qBittorrent标准模板",
        "description": "适合家庭用户的默认配置，适中的速度限制（1MB/s下载，512KB/s上传），500个全局连接数",
        "downloader_type": 0,  # qBittorrent
        "template_config": QB_STANDARD_CONFIG,
        "is_system_default": True,
        "created_by": None,  # 系统默认模板无创建者
    },
    {
        "name": "qBittorrent高性能模板",
        "description": "高带宽、高连接数配置，不限速，1000个全局连接数，最多20个并发任务",
        "downloader_type": 0,  # qBittorrent
        "template_config": QB_HIGH_PERFORMANCE_CONFIG,
        "is_system_default": True,
        "created_by": None,
    },
    {
        "name": "Transmission标准模板",
        "description": "适合家庭用户的默认配置，适中的速度限制（1MB/s下载，512KB/s上传），500个全局连接数",
        "downloader_type": 1,  # Transmission
        "template_config": TR_STANDARD_CONFIG,
        "is_system_default": True,
        "created_by": None,
    },
    {
        "name": "Transmission高性能模板",
        "description": "高带宽、高连接数配置，不限速，1000个全局连接数，最多20个并发任务",
        "downloader_type": 1,  # Transmission
        "template_config": TR_HIGH_PERFORMANCE_CONFIG,
        "is_system_default": True,
        "created_by": None,
    },
    {
        "name": "夜间不限速模板",
        "description": "分时段速度配置示例：工作日白天限速（512KB/s下载），晚上和周末不限速。适用于qBittorrent",
        "downloader_type": 0,  # qBittorrent
        "template_config": NIGHT_UNLIMITED_CONFIG,
        "is_system_default": True,
        "created_by": None,
    },
]


# ========== 初始化函数 ==========

def init_default_templates(db_session) -> int:
    """
    初始化系统默认模板到数据库

    Args:
        db_session: SQLAlchemy数据库会话

    Returns:
        int: 创建的模板数量

    Raises:
        Exception: 数据库操作失败时抛出异常
    """
    import json
    from datetime import datetime
    from app.models.setting_templates import SettingTemplate

    try:
        created_count = 0

        for template_data in DEFAULT_TEMPLATES:
            # 检查模板是否已存在
            existing = db_session.query(SettingTemplate).filter_by(
                name=template_data["name"]
            ).first()

            if existing:
                logger.info(f"系统默认模板已存在，跳过: {template_data['name']}")
                continue

            # 创建新模板
            template_config = template_data["template_config"]

            # 序列化配置为JSON字符串
            if isinstance(template_config, dict):
                template_config_json = json.dumps(template_config, ensure_ascii=False)
            else:
                template_config_json = template_config

            template = SettingTemplate(
                name=template_data["name"],
                description=template_data["description"],
                downloader_type=template_data["downloader_type"],
                template_config=template_config_json,
                is_system_default=template_data["is_system_default"],
                created_by=template_data["created_by"],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )

            db_session.add(template)
            created_count += 1
            logger.info(f"创建系统默认模板: {template_data['name']}")

        # 提交所有更改
        db_session.commit()
        logger.info(f"系统默认模板初始化完成，共创建 {created_count} 个模板")

        return created_count

    except Exception as e:
        db_session.rollback()
        logger.error(f"初始化系统默认模板失败: {e}")
        raise


def get_default_templates() -> list:
    """
    获取所有系统默认模板的配置数据

    Returns:
        list: 模板配置数据列表
    """
    return DEFAULT_TEMPLATES.copy()


def get_template_by_name(name: str) -> dict:
    """
    根据名称获取系统默认模板配置

    Args:
        name: 模板名称

    Returns:
        dict: 模板配置数据，不存在返回None
    """
    for template in DEFAULT_TEMPLATES:
        if template["name"] == name:
            return template.copy()
    return None


def get_templates_by_downloader_type(downloader_type: int) -> list:
    """
    根据下载器类型获取系统默认模板列表

    Args:
        downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）

    Returns:
        list: 匹配的模板配置数据列表
    """
    return [
        template.copy()
        for template in DEFAULT_TEMPLATES
        if template["downloader_type"] == downloader_type
    ]


# ========== 模板验证函数 ==========

def validate_template_config(config: dict, downloader_type: int) -> tuple[bool, str]:
    """
    验证模板配置的有效性

    Args:
        config: 模板配置字典
        downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）

    Returns:
        tuple[bool, str]: (是否有效, 错误消息)
    """
    # 检查必需字段
    required_fields = ["dl_speed_limit", "ul_speed_limit", "speed_unit"]
    for field in required_fields:
        if field not in config:
            return False, f"缺少必需字段: {field}"

    # 验证速度值
    if config["dl_speed_limit"] < 0:
        return False, "下载速度限制不能为负数"

    if config["ul_speed_limit"] < 0:
        return False, "上传速度限制不能为负数"

    # 验证速度单位
    if config["speed_unit"] not in [0, 1]:
        return False, "速度单位必须是0(KB/s)或1(MB/s)"

    # 验证高级配置（如果存在）
    if "advanced_settings" in config and config["advanced_settings"]:
        advanced = config["advanced_settings"]

        # qBittorrent特有字段验证
        if downloader_type == 0:
            qb_fields = ["max_connec", "max_numconn", "max_uploads"]
            for field in qb_fields:
                if field in advanced and advanced[field] < 0:
                    return False, f"高级配置字段 {field} 不能为负数"

        # Transmission特有字段验证
        elif downloader_type == 1:
            tr_fields = ["peer-limit-global", "peer-limit-per-torrent"]
            for field in tr_fields:
                if field in advanced and advanced[field] < 0:
                    return False, f"高级配置字段 {field} 不能为负数"

    return True, ""


# ========== 模块导出 ==========

__all__ = [
    "DEFAULT_TEMPLATES",
    "init_default_templates",
    "get_default_templates",
    "get_template_by_name",
    "get_templates_by_downloader_type",
    "validate_template_config",
]
