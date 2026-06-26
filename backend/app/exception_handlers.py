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


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 校验错误：保持 array detail 语义，包进 CommonResponse。

    detail 是 [{loc, msg, type, ...}] 数组，前端按 422 分支取 detail[0].msg。
    """
    errors = exc.errors()
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

    堆栈写入日志；DEBUG 模式下附带 trace 信息，生产环境不泄露内部细节。
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)

    body: dict[str, Any] = {
        "status": "error",
        "msg": "服务器内部错误",
        "code": str(status.HTTP_500_INTERNAL_SERVER_ERROR),
        "data": None,
    }
    if settings.DEBUG:
        # 开发环境附带异常摘要，便于联调，但不暴露完整堆栈给外部。
        body["data"] = {"error": str(exc)}

    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。应在 create_app() 中、路由挂载前调用。"""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
