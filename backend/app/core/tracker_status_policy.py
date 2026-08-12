"""Tracker 原始状态与关键词的共享判定策略。

Tracker 行级状态同步与种子级错误判断必须使用同一套证据语义，避免一层已经
恢复正常、另一层仍保留历史错误。该模块只提供纯函数，不访问数据库。
"""

from collections.abc import Mapping, Sequence
from typing import Any, List, Optional

NORMAL_EVIDENCE_TYPES = frozenset({"success", "ignored", "working"})


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
