# -*- coding: utf-8 -*-
"""临时诊断（fastapi 0.140 升级回归第二轮）：验证 _iter_app_api_routes 展开。

上一轮 dump 证实 fastapi 0.140.13 include_router 产物为惰性 _IncludedRouter
（app.routes 顶层 7 项，业务路由全在内层）。本轮验证 test_auth_route_coverage
新增的递归展开器能否取回全部业务路径 + 完整前缀。确认后即删除本文件。
"""

from __future__ import annotations

from typing import Any

from app.factory import app


def test_diag_v140_expand_dump() -> None:
    from fastapi.routing import APIRoute, APIWebSocketRoute

    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    from test_auth_route_coverage import _iter_app_api_routes

    lines: list[str] = []
    total = 0
    public_seen = []
    for route, path in _iter_app_api_routes(app):
        total += 1
        if total <= 30 or "auth" in path or "health" in path:
            kind = "WS" if isinstance(route, APIWebSocketRoute) else ",".join(sorted(route.methods))
            lines.append(f"{kind:8s} {path}")
        if path in ("/api/v1/auth/login", "/api/v1/auth/refresh", "/health/live", "/health/ready",
                    "/api/v1/health/live", "/api/v1/health/ready"):
            public_seen.append(path)

    import fastapi
    import starlette

    lines.append(f"TOTAL_EXPANDED={total}")
    lines.append(f"PUBLIC_SEEN={sorted(public_seen)}")
    lines.append(f"VERSIONS fastapi={fastapi.__version__} starlette={starlette.__version__}")
    assert False, "DIAG-INTENTIONAL-FAIL:\n" + "\n".join(lines)
