"""
安全的JSON解析工具模块

提供异常安全的JSON解析函数，避免JSONDecodeError导致的panic。
"""

import json
import logging
from typing import Any, Optional, TypeVar, Callable

logger = logging.getLogger(__name__)

T = TypeVar('T')


def safe_json_parse(
    json_str: Optional[str],
    default: T = None,
    *,
    log_errors: bool = True,
    error_context: str = ""
) -> Any:
    """
    安全的JSON解析函数，捕获所有异常并提供默认值

    Args:
        json_str: 要解析的JSON字符串
        default: 解析失败时的默认返回值
        log_errors: 是否记录错误日志
        error_context: 错误上下文信息，用于日志

    Returns:
        解析后的Python对象，或默认值

    Examples:
        >>> safe_json_parse('{"name": "test"}', {})
        {'name': 'test'}

        >>> safe_json_parse('invalid json', {})
        解析失败时返回 {}
    """
    if not json_str:
        return default

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        if log_errors:
            logger.error(
                f"JSON解析失败{error_context}: {e}\n"
                f"原始数据: {json_str[:200]}{'...' if len(json_str) > 200 else ''}"
            )
        return default
    except Exception as e:
        if log_errors:
            logger.error(
                f"JSON解析意外错误{error_context}: {e}\n"
                f"原始数据: {json_str[:200]}{'...' if len(json_str) > 200 else ''}"
            )
        return default


def safe_json_parse_with_validator(
    json_str: Optional[str],
    validator: Callable[[Any], bool],
    default: T = None,
    *,
    log_errors: bool = True,
    error_context: str = ""
) -> Any:
    """
    带验证器的安全JSON解析函数

    Args:
        json_str: 要解析的JSON字符串
        validator: 验证函数，接收解析后的对象，返回bool
        default: 解析或验证失败时的默认返回值
        log_errors: 是否记录错误日志
        error_context: 错误上下文信息

    Returns:
        解析后的Python对象，或默认值

    Examples:
        >>> def is_list(obj): return isinstance(obj, list)
        >>> safe_json_parse_with_validator('["a", "b"]', is_list, [])
        ['a', 'b']
    """
    parsed = safe_json_parse(json_str, default, log_errors=log_errors, error_context=error_context)

    if parsed is None:
        return default

    try:
        if not validator(parsed):
            if log_errors:
                logger.warning(f"JSON数据验证失败{error_context}: 数据格式不符合要求")
            return default
        return parsed
    except Exception as e:
        if log_errors:
            logger.error(f"JSON验证异常{error_context}: {e}")
        return default


def safe_json_dumps(
    obj: Any,
    default: str = "{}",
    *,
    ensure_ascii: bool = False,
    log_errors: bool = True,
    error_context: str = ""
) -> str:
    """
    安全的JSON序列化函数

    Args:
        obj: 要序列化的Python对象
        default: 序列化失败时的默认返回值
        ensure_ascii: 是否确保ASCII编码
        log_errors: 是否记录错误日志
        error_context: 错误上下文信息

    Returns:
        JSON字符串，或默认值
    """
    try:
        return json.dumps(obj, ensure_ascii=ensure_ascii)
    except (TypeError, ValueError) as e:
        if log_errors:
            logger.error(f"JSON序列化失败{error_context}: {e}")
        return default
    except Exception as e:
        if log_errors:
            logger.error(f"JSON序列化意外错误{error_context}: {e}")
        return default
