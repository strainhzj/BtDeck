"""
Tracker状态映射模块

该模块负责将qBittorrent和Transmission的tracker状态映射为统一的状态格式，
并集成基于关键词池的判断引擎，提供更准确的tracker状态判断。

核心特性:
- 统一的状态映射：将不同下载器的tracker状态映射为统一格式
- 智能状态判断：基于关键词池的状态判断，支持失败优先策略
- 向后兼容：保持原有API接口不变

作者: AI开发助手
创建时间: 2026-01-26
版本: 1.0.0
"""

import logging
from typing import Dict, Optional
from urllib.parse import urlparse

from app.core.tracker_judgment import judgment_engine, TrackerStatus

logger = logging.getLogger(__name__)


def extract_tracker_host(tracker_url: str) -> str:
    """
    从tracker URL中提取主机名

    Args:
        tracker_url: tracker完整URL

    Returns:
        tracker主机名

    示例:
        >>> extract_tracker_host("http://tracker.example.com:8080/announce")
        'tracker.example.com'
        >>> extract_tracker_host("https://tracker.pterclub.com/announce")
        'tracker.pterclub.com'
    """
    try:
        if not tracker_url:
            return "Unknown"

        parsed = urlparse(tracker_url)
        return parsed.netloc or parsed.hostname or "Unknown"
    except Exception:
        return "Unknown"


def map_qbittorrent_tracker_status(status: int) -> str:
    """
    映射qBittorrent的tracker状态数值为字符串

    qBittorrent tracker状态:
        0: 已禁用
        1: 未联系
        2: 工作中
        3: 工作失败
        4: 超时

    Args:
        status: qBittorrent状态数值

    Returns:
        映射后的状态字符串

    示例:
        >>> map_qbittorrent_tracker_status(0)
        '已禁用'
        >>> map_qbittorrent_tracker_status(2)
        '工作中'
    """
    status_mapping = {
        0: TrackerStatus.DISABLED,   # 已禁用
        1: TrackerStatus.NOT_CONTACTED,  # 未联系
        2: TrackerStatus.WORKING,     # 工作中
        3: TrackerStatus.FAILED,      # 工作失败
        4: TrackerStatus.NOT_CONTACTED  # 超时 -> 未联系
    }
    return status_mapping.get(status, TrackerStatus.NOT_CONTACTED)


def map_transmission_tracker_status(status: int) -> str:
    """
    映射Transmission的tracker状态数值为字符串

    Transmission tracker状态:
        0: 未联系
        1: 发送中
        2: 工作中
        3: 工作失败
        4: 超时
        5: 已清除

    Args:
        status: Transmission状态数值

    Returns:
        映射后的状态字符串

    示例:
        >>> map_transmission_tracker_status(0)
        '未联系'
        >>> map_transmission_tracker_status(2)
        '工作中'
    """
    status_mapping = {
        0: TrackerStatus.NOT_CONTACTED,  # 未联系
        1: TrackerStatus.NOT_CONTACTED,  # 发送中 -> 未联系
        2: TrackerStatus.WORKING,        # 工作中
        3: TrackerStatus.FAILED,         # 工作失败
        4: TrackerStatus.NOT_CONTACTED,  # 超时 -> 未联系
        5: TrackerStatus.DISABLED        # 已清除 -> 已禁用
    }
    return status_mapping.get(status, TrackerStatus.NOT_CONTACTED)


def map_qbittorrent_tracker(tracker: Dict) -> Dict:
    """
    映射qBittorrent的tracker信息为统一格式

    该函数将qBittorrent返回的tracker信息映射为统一格式，
    并使用判断引擎基于消息内容进行智能状态判断。

    Args:
        tracker: qBittorrent返回的tracker字典，包含以下字段:
            - url: tracker URL
            - status: 状态数值(0-4)
            - msg: tracker返回的消息
            - tier: 层级
            - num_peers: 连接的peer数量
            - num_seeds: 连接的seed数量
            - num_leeches: 连接的leech数量
            - downloaded: 下载量
            - uploaded: 上传量

    Returns:
        映射后的tracker信息字典，包含:
            - tracker_host: tracker主机名
            - status: 最终判定的状态
            - msg: tracker消息
            - tier: 层级
            - num_peers: peer数量
            - num_seeds: seed数量
            - num_leeches: leech数量
            - downloaded: 下载量
            - uploaded: 上传量

    示例:
        >>> tracker = {
        ...     'url': 'http://tracker.example.com:8080/announce',
        ...     'status': 2,
        ...     'msg': 'Success',
        ...     'tier': 1,
        ...     'num_peers': 10,
        ...     'num_seeds': 5,
        ...     'num_leeches': 5,
        ...     'downloaded': 1024,
        ...     'uploaded': 2048
        ... }
        >>> result = map_qbittorrent_tracker(tracker)
        >>> print(result['status'])
        '工作中'
    """
    # 提取基本信息
    tracker_url = tracker.get('url', '')
    tracker_host = extract_tracker_host(tracker_url)
    raw_status = tracker.get('status', 1)
    msg = tracker.get('msg', '')

    # 映射基础状态
    base_status = map_qbittorrent_tracker_status(raw_status)

    # 使用判断引擎进行智能状态判断
    final_status = judgment_engine.judge_status(
        original_status=base_status,
        msg=msg,
        language=None  # 可从用户配置获取
    )

    # 构建返回结果
    return {
        'tracker_host': tracker_host,
        'tracker_url': tracker_url,
        'status': final_status,
        'msg': msg,
        'tier': tracker.get('tier', 0),
        'num_peers': tracker.get('num_peers', 0),
        'num_seeds': tracker.get('num_seeds', 0),
        'num_leeches': tracker.get('num_leeches', 0),
        'downloaded': tracker.get('downloaded', 0),
        'uploaded': tracker.get('uploaded', 0)
    }


def map_transmission_tracker(tracker: Dict) -> Dict:
    """
    映射Transmission的tracker信息为统一格式

    该函数将Transmission返回的tracker信息映射为统一格式，
    并使用判断引擎基于消息内容进行智能状态判断。

    Args:
        tracker: Transmission返回的tracker字典，包含以下字段:
            - announce: tracker URL
            - trackerId: tracker ID
            - site_name: 站点名称
            - last_announce_peer_count: 上次announce时的peer数量
            - last_announce_result: 上次announce结果
            - last_announce_succeeded: 上次announce是否成功
            - last_announce_time: 上次announce时间
            - last_scrape_peer_count: 上次scrape时的peer数量
            - last_scrape_result: 上次scrape结果
            - last_scrape_succeeded: 上次scrape是否成功
            - last_scrape_time: 上次scrape时间
            - host: tracker主机
            - tier: 层级

    Returns:
        映射后的tracker信息字典，包含:
            - tracker_host: tracker主机名
            - tracker_url: tracker URL
            - status: 最终判定的状态
            - msg: tracker消息
            - tier: 层级
            - num_peers: peer数量
            - last_announce_time: 上次announce时间
            - last_scrape_time: 上次scrape时间

    示例:
        >>> tracker = {
        ...     'announce': 'http://tracker.example.com:8080/announce',
        ...     'last_announce_result': 'Success',
        ...     'last_announce_succeeded': True,
        ...     'tier': 1
        ... }
        >>> result = map_transmission_tracker(tracker)
        >>> print(result['status'])
        '工作中'
    """
    # 提取基本信息
    tracker_url = tracker.get('announce', '')
    tracker_host = tracker.get('host', '') or extract_tracker_host(tracker_url)

    # 判断基础状态
    last_announce_succeeded = tracker.get('last_announce_succeeded', False)

    if last_announce_succeeded:
        base_status = TrackerStatus.WORKING  # 工作中
    else:
        base_status = TrackerStatus.NOT_CONTACTED  # 未联系

    # 获取消息
    msg = tracker.get('last_announce_result', '') or tracker.get('last_scrape_result', '')

    # 使用判断引擎进行智能状态判断
    final_status = judgment_engine.judge_status(
        original_status=base_status,
        msg=msg,
        language=None  # 可从用户配置获取
    )

    # 构建返回结果
    return {
        'tracker_host': tracker_host,
        'tracker_url': tracker_url,
        'status': final_status,
        'msg': msg,
        'tier': tracker.get('tier', 0),
        'num_peers': tracker.get('last_announce_peer_count', 0),
        'last_announce_time': tracker.get('last_announce_time', 0),
        'last_scrape_time': tracker.get('last_scrape_time', 0),
        'site_name': tracker.get('site_name', '')
    }


def refresh_judgment_engine_cache() -> bool:
    """
    刷新判断引擎的关键词缓存

    提供给外部调用的缓存刷新接口，用于在关键词更新后手动刷新缓存。

    Returns:
        bool: 刷新是否成功

    示例:
        >>> refresh_judgment_engine_cache()
        True
    """
    return judgment_engine.refresh_cache()


def get_judgment_engine_stats() -> Dict:
    """
    获取判断引擎的缓存统计信息

    提供给外部调用的统计接口，用于监控关键词缓存状态。

    Returns:
        包含缓存统计信息的字典

    示例:
        >>> stats = get_judgment_engine_stats()
        >>> print(stats['success_count'])
        15
    """
    return judgment_engine.get_cache_stats()
