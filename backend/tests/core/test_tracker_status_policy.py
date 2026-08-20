"""Tracker 状态与关键词共享策略的直接回归测试。

这些用例直接锁定 ``625c1e3d`` 新增的共享纯函数，避免行级同步和种子级判断
各自的集成测试都通过，但两层实际使用了不同的证据语义。
"""

import pytest

from app.core.tracker_status_policy import (
    FAILED_DISPLAY_TEXT,
    build_tracker_evidence,
    collect_tracker_messages,
    decide_tracker_error_state,
    is_tracker_working,
    match_tracker_keyword_type,
    tracker_display_failed,
    tracker_message_failed,
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


# ==================== 展示层覆写（展示对齐判定） ====================


@pytest.mark.parametrize(
    "message",
    [None, "", "  \t ", 2, ["not-a-message"]],
)
def test_tracker_message_failed_ignores_non_string_or_blank_messages(message):
    """空消息/非字符串不构成证据（与 collect_tracker_messages 同语义）。"""
    assert tracker_message_failed(message, {"anything": "failed"}) is False


def test_tracker_message_failed_requires_exact_failed_keyword():
    """精确命中失败池才算失败；ignored/success/未配置消息都不覆写。"""
    keyword_map = {
        "You cannot seed the same torrent in the same location from more than 1 client.": "failed",
        "您已在 tracker.hdkyl.in 汇报过了": "ignored",
        "Success": "success",
    }
    exact_failed = "You cannot seed the same torrent in the same location from more than 1 client."

    assert tracker_message_failed(f"  {exact_failed}  ", keyword_map) is True
    assert tracker_message_failed("您已在 tracker.hdkyl.in 汇报过了", keyword_map) is False
    assert tracker_message_failed("Success", keyword_map) is False
    # 未精确命中（部分匹配不算，与种子级 exact 判定一致）
    assert tracker_message_failed("You cannot seed the torrent", keyword_map) is False
    # 空池永不覆写
    assert tracker_message_failed(exact_failed, {}) is False


def test_failed_display_text_matches_enums_code3():
    """覆写文本必须与两套下载器枚举 code=3 的显示文本一致。"""
    from app.enums.tracker_status import QBittorrentTrackerStatus, TransmissionTrackerStatus

    assert FAILED_DISPLAY_TEXT == QBittorrentTrackerStatus.get_display_text(3)
    assert FAILED_DISPLAY_TEXT == TransmissionTrackerStatus.get_display_text(3)


@pytest.mark.parametrize(
    ("status_code", "downloader_type", "expected"),
    [
        (2, "transmission", True),  # tr 工作中 + 失败消息 → 覆写（核心场景）
        (2, "qbittorrent", True),  # qb 工作中 + 失败消息 → 覆写
        (3, "transmission", True),  # 本就是失败，覆写无变化
        (None, "transmission", True),  # 状态码不可解析按非中性处理（对齐判定任务）
        ("abc", "qbittorrent", True),
        (1, "qbittorrent", False),  # qb 未联系：残留消息不采信
        (1, "transmission", False),  # tr 发送中：同上
        (0, "transmission", False),  # tr 未联系：同上
        (0, "qbittorrent", True),  # qb 已禁用不是中性码，消息证据有效
    ],
)
def test_tracker_display_failed_aligns_with_judge_neutral_semantics(status_code, downloader_type, expected):
    """覆写条件与判定任务的中性码语义一致：qb==1 / tr∈{0,1} 不覆写。"""
    keyword_map = {"You cannot seed the same torrent in the same location from more than 1 client.": "failed"}
    msg = "You cannot seed the same torrent in the same location from more than 1 client."

    assert tracker_display_failed(status_code, msg, keyword_map, downloader_type) is expected


def test_tracker_display_failed_ignores_non_failed_messages():
    """ignored/success/空池消息永不触发覆写，状态码不影响结论。"""
    keyword_map = {"您已在 tracker.hdkyl.in 汇报过了": "ignored", "Success": "success"}

    assert tracker_display_failed(2, "您已在 tracker.hdkyl.in 汇报过了", keyword_map, "transmission") is False
    assert tracker_display_failed(2, "Success", keyword_map, "qbittorrent") is False
    assert tracker_display_failed(2, "任意消息", {}, "transmission") is False
    assert tracker_display_failed(2, None, keyword_map, "transmission") is False
