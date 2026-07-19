"""全局异常处理器。

为 FastAPI 应用注册统一的异常处理 handler，将所有未捕获异常与手写
``HTTPException`` 归一化为 ``CommonResponse`` JSON 结构，消除审计文档
``backend/docs/style-and-contract-audit.md`` 第 2 节指出的「直接 HTTP 500
与包装 ``code=500`` 并存」「HTTPException detail 三种形态不一致」问题。

设计要点：
- ``HTTPException`` 的 detail 可能是纯字符串、``CommonResponse.model_dump()``
  字典或其它结构。本处理器优先识别 envelope dict（含 ``code`` 字段），
  直接复用其 ``code/msg``；否则按字符串/兜底包装。
- 未捕获 ``Exception`` 统一返回 HTTP 500 + ``CommonResponse(code=500)``，
  堆栈仅在 ``settings.DEBUG`` 下写入响应体，避免生产环境泄露内部信息。
- ``RequestValidationError``（422）保持 array detail 语义，但包进
  ``CommonResponse``，便于前端归一化层按统一约定读取。
"""

import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


def _looks_like_envelope(detail: Any) -> bool:
    """判断 detail 是否已经是 CommonResponse envelope（含 code 字段的 dict）。"""
    return isinstance(detail, dict) and "code" in detail


def _envelope_to_response(
    detail: Any,
    *,
    default_status: int,
    default_code: str,
    default_msg: str,
) -> JSONResponse:
    """把任意 detail 形态转换为统一 CommonResponse JSONResponse。

    - envelope dict：复用其 code/msg/status/data，HTTP status 取 default_status。
    - dict 但非 envelope：msg 走 JSON 序列化。
    - str：msg = detail。
    - 其它：msg = default_msg。
    """
    if _looks_like_envelope(detail):
        # detail 即 CommonResponse.model_dump()，直接透传字段，保持 code/msg 一致。
        code = str(detail.get("code") or default_code)
        msg = detail.get("msg") or default_msg
        body = {
            "status": detail.get("status") or ("success" if code == "200" else "error"),
            "msg": msg,
            "code": code,
            "data": detail.get("data"),
        }
    elif isinstance(detail, str):
        body = {
            "status": "error",
            "msg": detail or default_msg,
            "code": default_code,
            "data": None,
        }
    elif isinstance(detail, dict):
        body = {
            "status": "error",
            "msg": default_msg,
            "code": default_code,
            "data": detail,
        }
    else:
        body = {
            "status": "error",
            "msg": default_msg,
            "code": default_code,
            "data": None,
        }

    return JSONResponse(status_code=default_status, content=body)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """归一化手写 HTTPException，统一返回 CommonResponse 结构。

    兼容三种既有 detail 形态：
    1. 纯字符串（如 torrent_backup.py:917 ``detail="info_hash格式错误"``）
    2. CommonResponse.model_dump() 字典（如 dependencies.py:84）
    3. 其它结构
    """
    code = str(exc.status_code)
    default_msg = "请求错误"
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        default_msg = "认证失败"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        default_msg = "无权限"
    elif exc.status_code == status.HTTP_404_NOT_FOUND:
        default_msg = "资源不存在"
    elif exc.status_code >= 500:
        default_msg = "服务器内部错误"

    return _envelope_to_response(
        exc.detail,
        default_status=exc.status_code,
        default_code=code,
        default_msg=default_msg,
    )


def _json_safe(value: Any) -> Any:
    """递归把任意值转为 JSON 安全结构。

    策略：先尝试整体 ``json.dumps(value)``，成功则原样返回（保留 tuple 等
    JSON 兼容容器类型）；失败时按容器类型递归处理，对不可序列化的叶子值
    （如异常对象）降级为 ``str(value)``。

    示例：
        {'ctx': {'error': ValueError('x')}}  →
        {'ctx': {'error': "ValueError('x')" 字符串}}   # ctx 仍是 dict
        ('body', 'torrent_file')             →  原样 tuple（JSON 序列化为数组）
    """
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        pass
    # 整体不可序列化：递归处理容器，逐元素降级
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    # 叶子值且不可序列化（典型：异常对象），降级为字符串
    return str(value)


def _sanitize_validation_errors(errors: list[Any]) -> list[dict[str, Any]]:
    """把 RequestValidationError.errors() 安全化为可 JSON 序列化的列表。

    FastAPI/Pydantic 在某些校验失败路径下，会把原始异常对象（如 ``ValueError``）
    放进 error dict 的 ``ctx`` 字段::

        {'type': 'value_error', 'loc': ('body', 'torrent_file'),
         'msg': '...', 'input': 'undefined',
         'ctx': {'error': ValueError("Expected UploadFile, ...")}}  # ← 不可序列化

    若原样塞进 ``JSONResponse``，``json.dumps`` 会在序列化阶段抛
    ``TypeError: Object of type ValueError is not JSON serializable``，
    这个 TypeError 会冒泡到 ``unhandled_exception_handler``，使原本应
    返回 422 的校验错误变成 500（prod-hotfix-2026-07-19 真实根因）。

    本函数用 ``_json_safe`` 递归处理每个 error，保留容器结构，只把
    不可序列化的叶子值（如 ``ctx.error``）降级为字符串。
    """
    return [_json_safe(err) if isinstance(err, dict) else {"error": str(err)} for err in errors]


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 校验错误：保持 array detail 语义，包进 CommonResponse。

    detail 是 [{loc, msg, type, ...}] 数组，前端按 422 分支取 detail[0].msg。

    ⚠️ prod-hotfix-2026-07-19 修复：原始 errors() 的 ctx 字段可能含异常对象
    （如 ValueError），直接 JSONResponse 会触发 TypeError 冒泡到 500。
    改用 _sanitize_validation_errors 先做 JSON 安全化。
    """
    errors = _sanitize_validation_errors(exc.errors())
    first_msg = errors[0].get("msg") if errors else "参数校验失败"
    body = {
        "status": "error",
        "msg": first_msg,
        "code": str(status.HTTP_422_UNPROCESSABLE_ENTITY),
        "data": {"errors": errors},
    }
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """未捕获异常兜底：HTTP 500 + CommonResponse(code=500)。

    堆栈写入日志；DEBUG 模式下附带异常类型、消息与完整 traceback，生产环境不泄露内部细节。

    返回结构（DEBUG 模式）::

        data = {
            "exception_type": "TypeError",   # 异常类名，便于前端/运维快速定位
            "message": "Object of type ...", # str(exc)，安全字符串
            "traceback": "...",              # 完整堆栈字符串，精确定位抛出点
        }

    注意：早期版本 data 为 ``{"error": str(exc)}``，已迁移为上述结构。
    前端 ``error-normalize.ts`` 的 ``pickErrorPayload`` 只读 body.msg 不依赖 data.error，
    故字段重命名对前端无影响。原 ``error`` 字段保留为同义别名以向后兼容旧调用方。

    traceback 字段仅 DEBUG 模式输出，用于定位"异常为何绕过端点 except 冒泡到此处"
    这类难以复现的问题（如 prod-hotfix-2026-07-19 添加种子接口的 TypeError）。
    """
    import traceback as _traceback

    # 完整堆栈写入日志（含 logger.exception 的等价信息）
    tb_str = _traceback.format_exception(type(exc), exc, exc.__traceback__)
    tb_text = "".join(tb_str)
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url.path,
        tb_text,
    )

    body: dict[str, Any] = {
        "status": "error",
        "msg": "服务器内部错误",
        "code": str(status.HTTP_500_INTERNAL_SERVER_ERROR),
        "data": None,
    }
    if settings.DEBUG:
        # 开发环境附带异常类型、消息与完整堆栈，便于联调定位。
        # 显式 str() 化，杜绝任何异常对象本身进入响应体被 JSON 序列化时
        # 再抛 TypeError（例如原 exc 是 ValueError 实例时）。
        exc_message = str(exc) if exc is not None else ""
        body["data"] = {
            "exception_type": type(exc).__name__ if exc is not None else "",
            "message": exc_message,
            "traceback": tb_text,
            # 向后兼容：旧调用方若读 data.error 仍可拿到字符串
            "error": exc_message,
        }

    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。应在 create_app() 中、路由挂载前调用。"""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
