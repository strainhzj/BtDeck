"""MCP 写工具幂等缓存（feature mcp-service-capabilities-2026-08-28 W3-②）。

进程内有界 LRU：``(tool_name, principal_user_id, idempotency_key)`` → 首次领域结果；
同键重放返回缓存结果（调用方自行补审计行）。单实例前提由 SQLite WORKERS=1
启动守卫保证；进程重启后同键会再次执行——首版口径，G7 完整重放矩阵在 W4
复核（计划 §4.7）。

幂等键只以 sha256 前 16 位进入日志/审计（不可逆短摘要）。
"""

import hashlib
from collections import OrderedDict
from threading import Lock
from typing import Any, Dict, Optional, Tuple

CacheKey = Tuple[str, Any, str]

_CACHE: "OrderedDict[CacheKey, Dict[str, Any]]" = OrderedDict()
_CACHE_LIMIT = 512
_LOCK = Lock()


def digest_idempotency_key(key: str) -> str:
    """幂等键摘要（日志/审计面只允许出现摘要，不落原值）。"""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def cache_get(cache_key: CacheKey) -> Optional[Dict[str, Any]]:
    with _LOCK:
        if cache_key in _CACHE:
            _CACHE.move_to_end(cache_key)
            return _CACHE[cache_key]
    return None


def cache_put(cache_key: CacheKey, result: Dict[str, Any]) -> None:
    with _LOCK:
        _CACHE[cache_key] = result
        _CACHE.move_to_end(cache_key)
        while len(_CACHE) > _CACHE_LIMIT:
            _CACHE.popitem(last=False)


def reset_for_tests() -> None:
    with _LOCK:
        _CACHE.clear()
