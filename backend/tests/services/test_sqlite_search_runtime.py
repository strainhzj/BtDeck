"""Adversarial tests for the bounded SQLite regex runtime."""

import pytest

import app.services.sqlite_search_runtime as runtime


def test_sqlite_regex_uses_regex_not_substring_semantics():
    assert runtime._sqlite_bt_regexp(r"^file-\d{3}\.mkv$", "file-123.mkv", 1) == 1
    assert runtime._sqlite_bt_regexp(r"^file-\d{3}\.mkv$", "xfile-123.mkv", 1) == 0
    assert runtime._sqlite_bt_regexp(r"^avatar$", "Avatar", 0) == 1
    assert runtime._sqlite_bt_regexp(r"^avatar$", "Avatar", 1) == 0


def test_invalid_pattern_is_rejected_before_sql_execution():
    with pytest.raises(ValueError, match="invalid regex pattern"):
        runtime.validate_regex_pattern("(", case_sensitive=True)


def test_pathological_match_is_bounded_and_records_reason(monkeypatch):
    runtime.consume_regex_runtime_error()
    monkeypatch.setattr(runtime, "REGEX_MATCH_TIMEOUT_SECONDS", 1e-9)

    with pytest.raises(runtime.RegexSearchTimeout):
        runtime._sqlite_bt_regexp(r"(a+)+$", ("a" * 100_000) + "!", 1)

    assert runtime.consume_regex_runtime_error() == "match_timeout"
