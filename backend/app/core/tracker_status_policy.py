"""Tracker 原始状态与关键词的共享判定策略。

Tracker 行级状态同步与种子级错误判断必须使用同一套证据语义，避免一层已经
恢复正常、另一层仍保留历史错误。该模块只提供纯函数，不访问数据库。
"""

from collections.abc import Mapping, Sequence
from typing import Any, List, Optional

NORMAL_EVIDENCE_TYPES = frozenset({"success", "ignored", "working"})

# 展示层覆写文本；与两套下载器枚举 code=3 的显示文本（"工作失败"）一致。
FAILED_DISPLAY_TEXT = "工作失败"


def collect_tracker_messages(announce_msg: Any, scrape_msg: Any) -> List[str]:
    """收集 announce/scrape 的非空消息，并去除首尾空白。"""
    return [message.strip() for message in (announce_msg, scrape_msg) if isinstance(message, str) and message.strip()]


def is_tracker_working(announce_status: Any) -> bool:
    """判断统一状态码是否明确为 Working(2)。"""
    try:
        return int(announce_status) == 2
    except (TypeError, ValueError):
        return False


def match_tracker_keyword_type(message: str, keyword_map: Mapping[str, str]) -> str:
    """按精确优先、部分匹配次之的顺序返回关键词类型。"""
    normalized_message = message.strip()
    exact_match = keyword_map.get(message) or keyword_map.get(normalized_message)
    if exact_match:
        return exact_match

    lowered_message = normalized_message.lower()
    for keyword, keyword_type in keyword_map.items():
        if keyword and keyword.lower() in lowered_message:
            return keyword_type
    return "unknown"


def build_tracker_evidence(
    announce_status: Any,
    announce_msg: Any,
    scrape_msg: Any,
    keyword_map: Mapping[str, str],
    *,
    match_mode: str = "partial",
) -> List[str]:
    """构造单个 Tracker 的判定证据。

    非空消息始终优先走关键词；只有 announce/scrape 消息均为空且原始状态明确
    为 Working 时才产生 ``working`` 正常证据。空消息的其它状态没有可靠结论，
    返回空列表交由调用方选择“跳过”或“保留旧值”。
    """
    messages = collect_tracker_messages(announce_msg, scrape_msg)
    if messages:
        if match_mode == "partial":
            return [match_tracker_keyword_type(message, keyword_map) for message in messages]
        if match_mode == "exact":
            return [keyword_map.get(message, "unknown") for message in messages]
        raise ValueError("match_mode must be 'partial' or 'exact'")
    if is_tracker_working(announce_status):
        return ["working"]
    return []


def decide_tracker_error_state(evidence_types: Sequence[str]) -> Optional[bool]:
    """将证据聚合为错误状态：全部失败才为真，有正常证据即为假。"""
    if any(evidence_type in NORMAL_EVIDENCE_TYPES for evidence_type in evidence_types):
        return False
    if evidence_types and all(evidence_type == "failed" for evidence_type in evidence_types):
        return True
    return None


def tracker_message_failed(message: Any, keyword_map: Mapping[str, str]) -> bool:
    """判断单条 announce/scrape 消息是否精确命中失败关键词池。

    与 ``build_tracker_evidence`` 的 exact 分支同语义（strip 后整条查表），
    供展示层覆写与种子级 ``has_tracker_error`` 判定保持同一口径；空消息/
    非字符串不构成证据（与 ``collect_tracker_messages`` 一致）。
    """
    if not isinstance(message, str) or not message.strip():
        return False
    return keyword_map.get(message.strip()) == "failed"


def tracker_display_failed(
    activity_status: Any,
    activity_msg: Any,
    keyword_map: Mapping[str, str],
    downloader_type: Any,
) -> bool:
    """判断展示层是否应把该 announce/scrape 状态文本覆写为"工作失败"。

    Transmission 对「HTTP 200 + bencode failure reason」上报成功布尔，同步
    落库状态码 2（工作中）但消息是失败文本；此函数按判定任务口径修正展示。
    not-contacted 中性状态码（qBittorrent==1 / Transmission∈{0,1}）下的消息
    是残留旧值，判定任务（torrent_tracker_status_judge）不采信，展示层同样
    不覆写；状态码无法解析时按判定任务语义视为非中性（消息证据有效）。
    """
    if not tracker_message_failed(activity_msg, keyword_map):
        return False
    try:
        status_code = int(activity_status)
    except (TypeError, ValueError):
        return True
    if downloader_type == "qbittorrent":
        return status_code != 1
    return status_code not in (0, 1)
