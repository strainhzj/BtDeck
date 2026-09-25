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
from typing import Any, Dict
from urllib.parse import urlparse

from app.core.tracker_judgment import judgment_engine, TrackerStatus

logger = logging.getLogger(__name__)


# 合法 tracker URL scheme 白名单（qBittorrent/Transmission 实际可用的 tracker 协议）
VALID_TRACKER_URL_SCHEMES = frozenset({"http", "https", "udp", "ws", "wss"})


def is_valid_tracker_url(tracker_url: str) -> bool:
    """校验 tracker URL 是否为合法协议 URL。

    用于采集/入库/写回链路过滤污染条目：历史上 qbittorrent-api 的
    TorrentDictionary.trackers 属性赋值会触发 add_trackers 远程写，把
    Tracker 对象 repr 整段当作 URL 写回 qBittorrent（形如
    "Tracker({'msg': '', ..., 'url': 'https://...'})"）；qBittorrent 5.0+
    的自管 TrackerEntry 模型会原样存储并回显这类无效 URL。所有
    tracker 入库/写回点统一用本函数拦截，mark_removed 语义会随同步
    自愈清理库内既有污染行。

    Args:
        tracker_url: tracker URL 字符串

    Returns:
        是否合法（scheme 在白名单内；"** [DHT] **" 等伪条目无 scheme，同样不合法）
    """
    if not tracker_url:
        return False
    try:
        parsed = urlparse(str(tracker_url))
    except Exception:
        return False
    return (parsed.scheme or "").lower() in VALID_TRACKER_URL_SCHEMES


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
        0: TrackerStatus.DISABLED,  # 已禁用
        1: TrackerStatus.NOT_CONTACTED,  # 未联系
        2: TrackerStatus.WORKING,  # 工作中
        3: TrackerStatus.FAILED,  # 工作失败
        4: TrackerStatus.NOT_CONTACTED,  # 超时 -> 未联系
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
        2: TrackerStatus.WORKING,  # 工作中
        3: TrackerStatus.FAILED,  # 工作失败
        4: TrackerStatus.NOT_CONTACTED,  # 超时 -> 未联系
        5: TrackerStatus.DISABLED,  # 已清除 -> 已禁用
    }
    return status_mapping.get(status, TrackerStatus.NOT_CONTACTED)


def resolve_transmission_tracker_status_code(tracker_status: Any, activity: str = "announce") -> int:
    """把 Transmission TrackerStats 的布尔统计归一为项目 0-5 状态码。

    ``lastAnnounceSucceeded`` / ``lastScrapeSucceeded`` 是布尔值，不是
    ``TransmissionTrackerStatus`` 的状态码。旧实现把 False/True 直接写入整型列，
    列表随后将它们解释为 0=未联系、1=发送中，导致已联系但失败的 Tracker
    也显示成“未联系”。
    """
    if activity not in {"announce", "scrape"}:
        raise ValueError("activity must be announce or scrape")

    fields = getattr(tracker_status, "fields", None)
    fields = fields if isinstance(fields, dict) else {}
    title = activity.title()

    def read(attribute: str, field: str, default: Any = None) -> Any:
        if field in fields:
            return fields[field]
        try:
            return getattr(tracker_status, attribute)
        except (AttributeError, KeyError):
            return default

    succeeded = bool(read(f"last_{activity}_succeeded", f"last{title}Succeeded", False))
    timed_out = bool(read(f"last_{activity}_timed_out", f"last{title}TimedOut", False))
    has_contacted = read(f"has_{activity}d", f"has{title}d")
    activity_state = read(f"{activity}_state", f"{activity}State", 0)
    result = read(f"last_{activity}_result", f"last{title}Result", "")

    if succeeded:
        return 2  # 工作中
    if timed_out:
        return 4  # 超时
    if has_contacted is False:
        try:
            return 1 if int(activity_state or 0) > 0 else 0  # 发送中 / 未联系
        except (TypeError, ValueError):
            return 0
    if has_contacted is True:
        return 3  # 已联系但未成功：工作失败

    # 兼容旧测试桩或缺少 hasAnnounced/hasScraped 的旧 RPC 返回。
    try:
        if int(activity_state or 0) > 0:
            return 1
    except (TypeError, ValueError):
        pass
    return 3 if str(result or "").strip() else 0


def map_qbittorrent_tracker(tracker: Dict) -> Dict:
    """
    映射qBittorrent的tracker信息为统一格式

    该函数将qBittorrent返回的tracker信息映射为统一格式，
    并使用判断引擎基于消息内容进行智能状态判断。

    Args:
        tracker: qBittorrent返回的tracker字典（torrents_trackers 负载），包含以下字段:
            - url: tracker URL
            - status: 状态数值(0-4)
            - msg: tracker返回的消息
            - tier: 层级
            - num_peers: 已连接的 peer 数量（当前与该 tracker 建立的连接数）
            - num_seeds: scrape 群体 seed 总数（swarm 内做种者总数，非已连接数。
              2026-09-24 W2 纠错：此前误标为"连接的seed数量"；已连接数是 num_peers。
              真机 qB v4.3.9/API 2.8.2 实测键集：
              {msg, num_downloaded, num_leeches, num_peers, num_seeds, status, tier, url}）
            - num_leeches: scrape 群体 leech 总数（swarm 内下载者总数，非已连接数）
            - num_downloaded: scrape 群体累计完播下载数（未知时为 -1 哨兵；
              下方返回键沿用历史形态 downloaded/uploaded，qB 负载并无这两个键，
              恒为默认 0，仅为兼容旧消费方保留）

    Returns:
        映射后的tracker信息字典，包含:
            - tracker_host: tracker主机名
            - status: 最终判定的状态
            - msg: tracker消息
            - tier: 层级
            - num_peers: 已连接 peer 数量
            - num_seeds: scrape 群体 seed 总数
            - num_leeches: scrape 群体 leech 总数
            - downloaded: 兼容保留键（qB 负载无此键，恒 0）
            - uploaded: 兼容保留键（qB 负载无此键，恒 0）

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
    tracker_url = tracker.get("url", "")
    tracker_host = extract_tracker_host(tracker_url)
    raw_status = tracker.get("status", 1)
    msg = tracker.get("msg", "")

    # 映射基础状态
    base_status = map_qbittorrent_tracker_status(raw_status)

    # 使用判断引擎进行智能状态判断
    final_status = judgment_engine.judge_status(original_status=base_status, msg=msg, language=None)  # 可从用户配置获取

    # 构建返回结果
    return {
        "tracker_host": tracker_host,
        "tracker_url": tracker_url,
        "status": final_status,
        "msg": msg,
        "tier": tracker.get("tier", 0),
        "num_peers": tracker.get("num_peers", 0),
        "num_seeds": tracker.get("num_seeds", 0),
        "num_leeches": tracker.get("num_leeches", 0),
        "downloaded": tracker.get("downloaded", 0),
        "uploaded": tracker.get("uploaded", 0),
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
    tracker_url = tracker.get("announce", "")
    tracker_host = tracker.get("host", "") or extract_tracker_host(tracker_url)

    # 判断基础状态
    last_announce_succeeded = tracker.get("last_announce_succeeded", False)

    if last_announce_succeeded:
        base_status = TrackerStatus.WORKING  # 工作中
    else:
        base_status = TrackerStatus.NOT_CONTACTED  # 未联系

    # 获取消息
    msg = tracker.get("last_announce_result", "") or tracker.get("last_scrape_result", "")

    # 使用判断引擎进行智能状态判断
    final_status = judgment_engine.judge_status(original_status=base_status, msg=msg, language=None)  # 可从用户配置获取

    # 构建返回结果
    return {
        "tracker_host": tracker_host,
        "tracker_url": tracker_url,
        "status": final_status,
        "msg": msg,
        "tier": tracker.get("tier", 0),
        "num_peers": tracker.get("last_announce_peer_count", 0),
        "last_announce_time": tracker.get("last_announce_time", 0),
        "last_scrape_time": tracker.get("last_scrape_time", 0),
        "site_name": tracker.get("site_name", ""),
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
