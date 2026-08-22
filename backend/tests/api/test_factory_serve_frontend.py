# -*- coding: utf-8 -*-
"""serve_frontend SPA fallback 路径包含校验测试。

安全背景：catch-all 路由曾直接用 ``frontend_path / path`` 提供文件，
经 URL 编码的 .. 段（%2e%2e）或绝对路径注入可未认证读取任意文件。
修复后 resolve + is_relative_to 强制路径留在前端目录内。

测试直调 endpoint 函数而非 HTTP 客户端：httpx/TestClient 会在客户端
规范化 ../ 段导致穿越用例失真（历史实测），而 Starlette 在路由匹配前
已对 %2e%2e 解码，直调传入解码后的字符串等价于线上路径。
"""

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException

from app import factory


@pytest.fixture()
def frontend_env(tmp_path, monkeypatch):
    """构造带 index.html/assets 的伪前端目录，及目录外的机密文件。"""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("INDEX_MARKER", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("JS_MARKER", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP_SECRET", encoding="utf-8")
    monkeypatch.setattr(factory, "_get_frontend_dist_path", lambda: dist)
    return dist, secret


def _serve(path: str):
    """挂载静态路由并直调 serve_frontend（decode 后的路径参数）。"""
    app = FastAPI()
    factory._mount_frontend_static(app)
    route = app.routes[-1]
    return asyncio.run(route.endpoint(path))


def _assert_fallback_to_index(response, dist: Path) -> None:
    assert str(response.path).endswith("index.html")
    assert Path(str(response.path)).resolve().is_relative_to(dist.resolve())


def test_traversal_parent_denied(frontend_env):
    """../ 穿越（含 URL 解码后的 %2e%2e 形态）必须回退 index.html。"""
    dist, secret = frontend_env
    response = _serve(f"../{secret.name}")
    _assert_fallback_to_index(response, dist)


def test_traversal_deep_relative_denied(frontend_env):
    dist, _ = frontend_env
    response = _serve("../../../../etc/passwd")
    _assert_fallback_to_index(response, dist)


def test_traversal_backslash_variant_denied(frontend_env):
    """Windows 反斜杠（%5c 解码后）穿越必须回退。"""
    dist, secret = frontend_env
    response = _serve(f"..\\..\\{secret.name}")
    _assert_fallback_to_index(response, dist)


def test_absolute_path_injection_denied(frontend_env):
    """绝对路径注入（pathlib 锚点替换）必须回退。"""
    dist, secret = frontend_env
    response = _serve(str(secret))
    _assert_fallback_to_index(response, dist)
    response = _serve("C:/Windows/win.ini")
    _assert_fallback_to_index(response, dist)


def test_normal_assets_still_served(frontend_env):
    dist, _ = frontend_env
    response = _serve("assets/app.js")
    assert Path(str(response.path)).name == "app.js"


def test_index_served_directly(frontend_env):
    dist, _ = frontend_env
    response = _serve("index.html")
    _assert_fallback_to_index(response, dist)


def test_api_prefix_raises_404(frontend_env):
    with pytest.raises(HTTPException) as exc_info:
        _serve("api/v1/anything")
    assert exc_info.value.status_code == 404
