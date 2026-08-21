# -*- coding: utf-8 -*-
"""API 路由鉴权覆盖回归测试（安全审计 2026-08 附加发现 #2 的机器强制门禁）。

背景：应用无全局鉴权中间件，所有 APIRouter 均为裸声明，业务端点的鉴权完全
依赖函数签名/装饰器手动声明 Depends。既有门禁对此存在结构盲区：

- test_architecture_constraints 的比例断言只看"Depends 占比"，完全不带鉴权的
  新端点不进分子也不进分母；
- BTD201 只禁止手动解析 token，不管"什么都不写"；
- tests/api/test_auth_protection*.py 是逐端点硬编码清单，新端点须有人记得补测。

本测试遍历运行时 app.routes，把"非白名单路由的依赖树必须含鉴权函数"固化为
不变量：漏写者本地跑 pytest 即报红，无需等待下一次安全审计。同时校验白名单
本身未失真（公开端点必须存在、不得误挂鉴权）。
"""

from __future__ import annotations

from typing import Any, Iterator

from fastapi.routing import APIRoute, APIWebSocketRoute

from app.factory import app

# 鉴权依赖函数名：未来若引入新的鉴权依赖，在此登记，保持口径集中。
_AUTH_DEPENDENCY_NAMES = frozenset({"require_authenticated_user", "get_current_user"})

# 业务上必须可匿名访问的端点（必须存在；若被误挂鉴权也报红——login 挂上
# 鉴权等于无人能登录，health 挂上鉴权会打断 Docker 探针）。
_REQUIRED_PUBLIC_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/health/live",
        "/health/ready",
        "/api/v1/health/live",
        "/api/v1/health/ready",
    }
)

# 允许匿名但存在与否取决于环境的路由：SPA fallback 只在 frontend/dist 构建
# 后挂载。FastAPI 文档路由（/docs、/redoc、openapi.json）是 starlette Route
# 而非 APIRoute，天然被 isinstance 过滤（且生产 DEV=False 时已整体关闭）。
_OPTIONAL_PUBLIC_PATHS = frozenset({"/{path:path}"})

# 防御"路由注册整体失败仍静默通过"（历史 bug：endpoint 顶层 import
# app.factory 触发循环 import，全局 app 丢失全部业务路由，测试集体 404）。
# 当前受保护路由 206 条，阈值取 100 留出收缩余量。
_MINIMUM_PROTECTED_ROUTES = 100


def _iter_auth_dependency_names(dependant: Any) -> Iterator[str]:
    """深度遍历依赖树，产出其中出现的鉴权依赖函数名。

    FastAPI 构造 APIRoute 时会把装饰器级 dependencies 与参数级 Depends 合并进
    route.dependant.dependencies，因此从 dependant 递归即可全覆盖两种声明方式。
    """
    stack = [dependant]
    while stack:
        current = stack.pop()
        name = getattr(getattr(current, "call", None), "__name__", None)
        if name in _AUTH_DEPENDENCY_NAMES:
            yield str(name)
        stack.extend(current.dependencies)


def test_all_api_routes_require_auth() -> None:
    """非白名单路由必须携带鉴权依赖；白名单必须与实际注册状态一致。"""
    violations: list[str] = []
    seen_public: set[str] = set()
    protected_count = 0

    for route in app.routes:
        if not isinstance(route, (APIRoute, APIWebSocketRoute)):
            continue
        path = route.path
        if path in _OPTIONAL_PUBLIC_PATHS:
            continue
        route_kind = "WS" if isinstance(route, APIWebSocketRoute) else ",".join(sorted(route.methods))
        found_auth = set(_iter_auth_dependency_names(route.dependant))

        if path in _REQUIRED_PUBLIC_PATHS:
            seen_public.add(path)
            if found_auth:
                violations.append(f"[{route_kind}] {path}: 公开白名单端点意外携带鉴权依赖 {sorted(found_auth)}")
            continue

        if found_auth:
            protected_count += 1
        else:
            violations.append(
                f"[{route_kind}] {path}: 依赖树不含鉴权函数（require_authenticated_user / get_current_user）"
            )

    missing = _REQUIRED_PUBLIC_PATHS - seen_public
    assert not missing, f"公开路由白名单中的路径未注册（路径漂移或路由挂载失败）: {sorted(missing)}"
    assert protected_count >= _MINIMUM_PROTECTED_ROUTES, (
        f"受鉴权保护的路由仅 {protected_count} 条（< {_MINIMUM_PROTECTED_ROUTES}），"
        "疑似路由注册整体失败（参见历史 bug：endpoint 顶层 import app.factory 循环依赖）"
    )
    assert not violations, "以下路由缺少鉴权依赖:\n" + "\n".join(violations)
