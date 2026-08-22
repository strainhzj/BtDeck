"""Bounded SQLite regular-expression runtime for advanced search."""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

import regex

REGEX_MATCH_TIMEOUT_SECONDS = 0.01
REGEX_QUERY_BUDGET_SECONDS = 2.0
_runtime_state = threading.local()


class RegexSearchTimeout(ValueError):
    """Raised when a regex match or its enclosing SQLite query exceeds budget."""


@lru_cache(maxsize=256)
def _compile_pattern(pattern: str, case_sensitive: bool) -> regex.Pattern:
    flags = regex.VERSION1
    if not case_sensitive:
        flags |= regex.IGNORECASE
    return regex.compile(pattern, flags)


def validate_regex_pattern(pattern: str, *, case_sensitive: bool) -> None:
    """Compile once at request validation time and cache the result."""
    try:
        _compile_pattern(pattern, case_sensitive)
    except regex.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc


def _sqlite_bt_regexp(pattern: Any, value: Any, case_sensitive: Any) -> int:
    if value is None:
        return 0
    try:
        compiled = _compile_pattern(str(pattern), bool(case_sensitive))
        return int(compiled.search(str(value), timeout=REGEX_MATCH_TIMEOUT_SECONDS) is not None)
    except TimeoutError as exc:
        _runtime_state.regex_error = "match_timeout"
        raise RegexSearchTimeout("regular expression match timed out") from exc
    except regex.error as exc:
        _runtime_state.regex_error = "invalid_pattern"
        raise ValueError(f"invalid regular expression: {exc}") from exc


def install_sqlite_search_functions(dbapi_connection: Any) -> None:
    """Install deterministic search functions on one sqlite3 connection."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    dbapi_connection.create_function("bt_regexp", 3, _sqlite_bt_regexp, deterministic=True)


def consume_regex_runtime_error() -> str | None:
    error = getattr(_runtime_state, "regex_error", None)
    _runtime_state.regex_error = None
    return error


def _raw_sqlite_connection(session: Any) -> sqlite3.Connection | None:
    try:
        connection = session.connection()
        raw = connection.connection.driver_connection
    except (AttributeError, TypeError):
        return None
    return raw if isinstance(raw, sqlite3.Connection) else None


def ensure_search_runtime(session: Any) -> None:
    raw = _raw_sqlite_connection(session)
    if raw is not None:
        install_sqlite_search_functions(raw)


@contextmanager
def regex_query_budget(session: Any, *, seconds: float = REGEX_QUERY_BUDGET_SECONDS) -> Iterator[None]:
    """Abort a regex-bearing SQLite query after a total wall-clock budget."""
    raw = _raw_sqlite_connection(session)
    if raw is None:
        yield
        return
    deadline = time.monotonic() + seconds

    def _progress_handler() -> int:
        if time.monotonic() >= deadline:
            _runtime_state.regex_error = "query_timeout"
            return 1
        return 0

    raw.set_progress_handler(_progress_handler, 1000)
    try:
        yield
    finally:
        raw.set_progress_handler(None, 0)
