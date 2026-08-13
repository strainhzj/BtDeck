"""Tracker 状态与关键词共享策略的直接回归测试。

这些用例直接锁定 ``625c1e3d`` 新增的共享纯函数，避免行级同步和种子级判断
各自的集成测试都通过，但两层实际使用了不同的证据语义。
"""

import pytest

from app.core.tracker_status_policy import (
    build_tracker_evidence,
    collect_tracker_messages,
    decide_tracker_error_state,
    is_tracker_working,
    match_tracker_keyword_type,
)


def test_collect_tracker_messages_filters_non_strings_and_strips_blank_values():
    """announce/scrape 只保留去除首尾空白后的非空字符串。"""
    assert collect_tracker_messages(None, "  Connection refused  ") == ["Connection refused"]
    assert collect_tracker_messages("", " \t ") == []
    assert collect_tracker_messages(2, ["not-a-message"]) == []


@pytest.mark.parametrize("raw_status", [2, "2", 2.0])
def test_is_tracker_working_accepts_working_status_code(raw_status):
    """下载器返回数字或数字字符串 2 时都应识别为 Working。"""
    assert is_tracker_working(raw_status) is True


@pytest.mark.parametrize("raw_status", [None, "", 0, 1, 3, "working"])
def test_is_tracker_working_rejects_non_working_status(raw_status):
    """只有明确状态码 2 才能生成 Working 证据。"""
    assert is_tracker_working(raw_status) is False


def test_working_blank_messages_produce_normal_evidence():
    """Working + None/空串/空白消息必须产生正常证据，才能清理历史错误。"""
    for announce_msg, scrape_msg in ((None, None), ("", ""), ("  ", "\t")):
        assert build_tracker_evidence(2, announce_msg, scrape_msg, {}) == ["working"]


@pytest.mark.parametrize("announce_status", [None, 0, 1, 3, 4])
def test_blank_messages_without_working_evidence_are_unresolved(announce_status):
    """非 Working 的空消息不能猜测为正常或失败，应交由调用方保留旧值。"""
    assert build_tracker_evidence(announce_status, None, " ", {}) == []


def test_non_empty_messages_override_working_status_and_include_both_sources():
    """只要存在消息，Working 兜底就不能掩盖 announce/scrape 的关键词证据。"""
    keyword_map = {"timeout": "failed", "ok": "success"}

    assert build_tracker_evidence(2, " Connection timeout ", "ok", keyword_map) == ["failed", "success"]


def test_exact_match_has_priority_over_partial_match():
    """精确关键词优先，避免短失败关键词抢占完整成功消息。"""
    keyword_map = {"ok": "failed", "ok done": "success"}

    assert match_tracker_keyword_type("ok done", keyword_map) == "success"


def test_partial_match_is_case_insensitive():
    """未精确命中时，关键词部分匹配保持大小写不敏感。"""
    assert match_tracker_keyword_type("Connection TimeOut", {"timeout": "failed"}) == "failed"


def test_exact_match_mode_keeps_unknown_non_exact_messages_unresolved():
    """种子级判断使用精确模式时，未精确命中的消息不能被猜测分类。"""
    assert build_tracker_evidence(
        2,
        "Connection timeout",
        None,
        {"timeout": "failed"},
        match_mode="exact",
    ) == ["unknown"]


def test_invalid_match_mode_is_rejected():
    """共享策略只允许服务层部分匹配和种子级精确匹配两种模式。"""
    with pytest.raises(ValueError, match="match_mode"):
        build_tracker_evidence(2, "message", None, {}, match_mode="contains")


@pytest.mark.parametrize(
    ("evidence_types", "expected"),
    [
        ([], None),
        (["unknown"], None),
        (["failed", "unknown"], None),
        (["failed"], True),
        (["failed", "failed"], True),
        (["failed", "success"], False),
        (["ignored"], False),
        (["working"], False),
    ],
)
def test_decide_tracker_error_state_requires_all_failed_or_any_normal(evidence_types, expected):
    """全部明确失败才是错误；任一正常证据清除错误；其它组合保留旧值。"""
    assert decide_tracker_error_state(evidence_types) is expected


def test_working_evidence_is_normal_when_combined_with_a_failed_evidence():
    """共享聚合语义必须让 Working 空消息和明确失败证据组合为正常。"""
    assert decide_tracker_error_state(["failed", "working"]) is False
