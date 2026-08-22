# -*- coding: utf-8 -*-
"""
exception_handlers 回归测试（prod-hotfix-2026-07-19）

修复目标：消除生产偶发 500 响应 ``data.error="Object of type ValueError is not
JSON serializable"``。

真实根因（已通过用户提供的 traceback 精确定位）：
    validation_exception_handler 把 ``RequestValidationError.errors()`` 原样塞进
    ``JSONResponse(content=body)``。FastAPI/Pydantic 在某些校验失败路径下
    （如 ``Optional[UploadFile] = File(...)`` 接收到字符串 'undefined'），
    会把原始 ``ValueError`` 异常对象放进 error dict 的 ``ctx`` 字段::

        {'type': 'value_error', 'loc': ('body', 'torrent_file'),
         'msg': '...', 'input': 'undefined',
         'ctx': {'error': ValueError("Expected UploadFile, ...")}}

    ``JSONResponse.render`` 用 ``json.dumps`` 序列化 body 时撞到 ``ValueError``
    实例，抛 ``TypeError("Object of type ValueError is not JSON serializable")``。
    该 TypeError 不是 ``RequestValidationError``，会冒泡到
    ``unhandled_exception_handler``，使原本应返回 422 的校验错误变成 500。

修复：``validation_exception_handler`` 调用 ``_sanitize_validation_errors`` 对
errors 逐字段做 JSON 安全化，不可序列化的字段（如 ``ctx.error``）降级为字符串。

用户实际现象：添加种子接口返回上述 500，但 qBittorrent 客户端里种子已添加成功——
说明前端发了两次请求：一次 ``torrent_file='undefined'``（触发本 bug 返回 500），
一次正常文件（添加成功）。
"""

import json
from unittest.mock import MagicMock

import pytest
from fastapi.exceptions import RequestValidationError

from app.exception_handlers import (
    _sanitize_validation_errors,
    validation_exception_handler,
)


def _make_errors_with_value_error_in_ctx() -> list:
    """构造与用户报错完全一致的 errors（ctx 含 ValueError 对象）。

    复刻 Pydantic/FastAPI 在 ``Optional[UploadFile] = File(...)`` 收到
    字符串 'undefined' 时产生的校验错误结构。
    """
    return [
        {
            "type": "value_error",
            "loc": ("body", "torrent_file"),
            "msg": "Value error, Expected UploadFile, received: <class 'str'>",
            "input": "undefined",
            "ctx": {"error": ValueError("Expected UploadFile, received: <class 'str'>")},
        }
    ]


def test_sanitize_errors_with_value_error_in_ctx():
    """_sanitize_validation_errors 清除 ctx 里的 ValueError 对象。"""
    raw_errors = _make_errors_with_value_error_in_ctx()
    sanitized = _sanitize_validation_errors(raw_errors)

    # 关键：sanitized 后整个列表必须可 json.dumps（这是修复的核心契约）
    serialized = json.dumps({"errors": sanitized})
    assert serialized  # 不抛即通过

    # ctx 字段从 ValueError 对象降级为字符串
    ctx = sanitized[0]["ctx"]
    assert isinstance(ctx["error"], str)
    assert "Expected UploadFile" in ctx["error"]
    # 其它字段保持不变
    assert sanitized[0]["type"] == "value_error"
    assert sanitized[0]["loc"] == ("body", "torrent_file")
    assert sanitized[0]["msg"] == "Value error, Expected UploadFile, received: <class 'str'>"
    assert sanitized[0]["input"] == "undefined"


def test_sanitize_errors_preserves_normal_fields():
    """正常（可序列化）字段不被改动。"""
    raw_errors = [
        {
            "type": "missing",
            "loc": ("body", "save_path"),
            "msg": "Field required",
            "input": None,
            "url": "https://errors.pydantic.dev/2.x/v/missing",
        }
    ]
    sanitized = _sanitize_validation_errors(raw_errors)
    assert sanitized == raw_errors
    # 可正常序列化
    json.dumps({"errors": sanitized})


def test_sanitize_errors_handles_non_dict_entry():
    """非 dict 条目降级为 {'error': str(value)}。"""
    raw_errors = [{"loc": ("body", "x")}, "weird string entry", 42]
    sanitized = _sanitize_validation_errors(raw_errors)
    json.dumps({"errors": sanitized})  # 不抛即通过
    assert sanitized[1] == {"error": "weird string entry"}
    assert sanitized[2] == {"error": "42"}


@pytest.mark.asyncio
async def test_validation_handler_returns_422_not_500_on_value_error_ctx():
    """prod 根因回归：ctx 含 ValueError 时返回 422，不冒泡 TypeError。

    修复前：JSONResponse json.dumps 撞 ValueError 抛 TypeError → 冒泡到
    unhandled_exception_handler → 前端看到 500 +
    "Object of type ValueError is not JSON serializable"。
    修复后：正常返回 422 + CommonResponse。
    """
    exc = RequestValidationError(_make_errors_with_value_error_in_ctx())
    request = MagicMock()
    request.method = "POST"
    request.url.path = "/api/v1/torrents/add"

    response = await validation_exception_handler(request, exc)

    assert response.status_code == 422
    body = json.loads(response.body.decode())
    assert body["status"] == "error"
    assert body["code"] == "422"
    assert "Expected UploadFile" in body["msg"]
    # data.errors 可安全序列化（响应已成功 render 即证明）
    assert "errors" in body["data"]


@pytest.mark.asyncio
async def test_validation_handler_first_msg_extraction():
    """msg 取 errors[0].msg，errors 为空时回退默认值。"""
    # 空 errors
    exc = RequestValidationError([])
    request = MagicMock()
    request.method = "POST"
    request.url.path = "/x"
    response = await validation_exception_handler(request, exc)
    body = json.loads(response.body.decode())
    assert body["msg"] == "参数校验失败"
    assert body["data"]["errors"] == []


# ============================================================================
# 端到端集成测试：通过真实 FastAPI app + 真实路由复现用户场景
#
# 与前面 5 个单元测试的区别：
#   - 单元测试直接 await handler 函数，用 MagicMock 构造 RequestValidationError
#   - 端到端测试用真实 FastAPI app + 真实 UploadFile 参数声明 + 真实 Starlette
#     中间件链，复现「前端发送 torrent_file='undefined' 字符串」的完整请求路径
#
# 这类测试锚定的是「整个异常处理管线在真实 Pydantic ctx.error 形态下不再
# 冒泡到 500」这一端到端契约，防止单元测试通过但集成路径仍 broken 的情况。
# ============================================================================


def _build_e2e_app():
    """构造挂载了全局异常处理器 + 单个 add 端点的最小 FastAPI app。

    复刻生产路由的真实参数声明（``Optional[UploadFile] = File(...)``），
    触发 Pydantic 在收到字符串时把 ``ValueError`` 放进 ``ctx.error`` 的真实路径。
    """
    from typing import Optional

    from fastapi import FastAPI, File, Form, UploadFile
    from fastapi.testclient import TestClient

    from app.api.responseVO import CommonResponse
    from app.exception_handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/torrents/add", response_model=CommonResponse)
    async def add_torrent(  # noqa: ANN202 - 测试桩端点
        downloader_id: Optional[str] = Form(...),
        save_path: Optional[str] = Form(...),
        torrent_file: Optional[UploadFile] = File(description="种子文件"),
    ):
        # 端点正常逻辑——校验失败时不会执行到这里
        return CommonResponse(status="success", msg="ok", code="200")

    return app, TestClient


def test_e2e_string_torrent_file_returns_422_not_500():
    """端到端回归：前端发送 torrent_file='undefined' 字符串时返回 422。

    复刻用户报错的完整路径：FormData 把 undefined 序列化成字符串 'undefined'，
    Pydantic 校验失败，ctx.error 含 ValueError 对象。

    修复前：validation_exception_handler 序列化失败 → TypeError 冒泡 → 500 +
    "Object of type ValueError is not JSON serializable"
    修复后：正常返回 422 + CommonResponse(data.errors 可安全序列化)
    """
    app, TestClient = _build_e2e_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        # 关键：torrent_file 作为普通表单字段传字符串 'undefined'，而非文件上传
        data = {
            "downloader_id": "dl-test",
            "save_path": "/downloads",
            "torrent_file": "undefined",
        }
        resp = client.post("/torrents/add", data=data)

    # 核心断言：HTTP 422，而非 500
    assert resp.status_code == 422, f"期望 422，实际 {resp.status_code}: {resp.text}"
    body = json.loads(resp.text)
    assert body["status"] == "error"
    assert body["code"] == "422"
    # 用户友好的错误消息
    assert "Expected UploadFile" in body["msg"] or "torrent_file" in body["msg"]
    # data.errors 存在且可安全序列化（响应成功 render 即证明）
    assert "errors" in body["data"]
    assert len(body["data"]["errors"]) > 0


def test_e2e_normal_file_upload_still_works():
    """对照测试：正常文件上传时端点正常执行，不受修复影响。

    确保修复没有破坏正常路径（即真正的 UploadFile 仍能进入端点函数体）。
    """
    from io import BytesIO

    app, TestClient = _build_e2e_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        files = {"torrent_file": ("test.torrent", BytesIO(b"fake torrent content"), "application/x-bittorrent")}
        data = {"downloader_id": "dl-test", "save_path": "/downloads"}
        resp = client.post("/torrents/add", files=files, data=data)

    assert resp.status_code == 200
    body = json.loads(resp.text)
    assert body["code"] == "200"
    assert body["status"] == "success"


def test_e2e_missing_required_field_returns_422():
    """对照测试：缺失必填字段（无 ctx.error）也返回 422，结构一致。

    确保修复对「正常校验错误（无异常对象）」路径无副作用，且 errors 结构完整。
    """
    app, TestClient = _build_e2e_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        # 缺少必填的 downloader_id 和 save_path
        resp = client.post("/torrents/add", data={})

    assert resp.status_code == 422
    body = json.loads(resp.text)
    assert body["code"] == "422"
    assert "errors" in body["data"]
    # 缺字段错误的 errors 里通常没有 ctx，但结构应正常
    for err in body["data"]["errors"]:
        assert "loc" in err
        assert "msg" in err
