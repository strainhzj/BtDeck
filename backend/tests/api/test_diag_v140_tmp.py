# -*- coding: utf-8 -*-
"""临时诊断（fastapi 0.140 升级回归）：dump 全局 app.routes 的真实结构。

test_auth_route_coverage 在 CI（fastapi 0.140.13 + starlette 1.9.0）下报 6 个
公开白名单路径未注册，但同批 test_auth_refresh 5 例全过（HTTP 分发正常），
且无循环 import warning——嫌疑收窄为 app.routes 可见性/类型匹配问题。
本测试强制失败以输出完整路由清单，拿到真相后即删除。
"""

from __future__ import annotations


def test_diag_v140_route_dump() -> None:
    from app.factory import app

    lines = [f"TOTAL={len(app.routes)}", f"fastapi routes attr: {type(app.routes).__name__}"]
    for r in app.routes:
        path = getattr(r, "path", "?")
        routes_inner = getattr(r, "routes", None)
        inner = f" inner={len(routes_inner)}" if routes_inner is not None else ""
        lines.append(f"{type(r).__module__}.{type(r).__qualname__} path={path}{inner}")
        if routes_inner:
            for sub in routes_inner[:40]:
                lines.append(f"    SUB {type(sub).__module__}.{type(sub).__qualname__} path={getattr(sub, 'path', '?')}")

    import fastapi
    import starlette

    lines.append(f"VERSIONS fastapi={fastapi.__version__} starlette={starlette.__version__}")
    assert False, "DIAG-INTENTIONAL-FAIL:\n" + "\n".join(lines[:200])
