# -*- coding: utf-8 -*-
"""维护准入/屏障中间件（database-migration-ui W2-3，PLANS §5.2/§11 T03/T05）。

单中间件承担两职（同一判定面，避免两个模块各自取状态产生窗口）：

1. **普通模式**：对业务面（``/api/*`` 与 ``/mcp``）请求自入口持有操作级
   lease，直至响应完成（含 handler finally 中的通知/审计/远端动作收尾）；
   静态/health 等非业务路径零开销直通。维护开始关闸后，闸内未完成请求
   继续持有 lease——排空等它们收尾（最后业务提交→通知/审计，T03）。
2. **维护模式**：默认拒绝**全部普通业务 API（含 GET）**与新 MCP/业务
   WebSocket——返回 HTTP 503 + CommonResponse（reasonCode
   ``MAINTENANCE_MODE``）；不再以 HTTP method 推断安全。显式放行：

   - ``/health/live``、``/health/ready``（ready 自身维护期返回 503 语义）；
   - 静态前端（非 ``/api``/``/mcp`` 路径——维护页面由前端提供，§5.4）；
   - ``/api/v1/maintenance/*``（独立维护认证的控制端点）。

纯 ASGI 中间件（非 BaseHTTPMiddleware）：零拷贝包装、对挂载子应用
（/mcp）与 WebSocket 同样生效；维护控制器经进程级默认单例获取
（lifespan 装载，未初始化时直通——测试/CLI 场景）。
"""

from __future__ import annotations

import json
from typing import Any

from app.services.db_migration.maintenance import (
    AdmissionRejected,
    get_default_controller,
)

_MAINTENANCE_API_PREFIX = "/api/v1/maintenance/"
_HEALTH_ALLOWED = frozenset({"/health/live", "/health/ready"})

_MAINTENANCE_503_BODY = {
    "status": "error",
    "msg": "maintenance mode",
    "code": "503",
    "data": {"reasonCode": "MAINTENANCE_MODE"},
}


def _is_business_path(path: str) -> bool:
    """业务面判定：/api/*（除维护控制端点）与 /mcp*。"""
    if path.startswith("/mcp"):
        return True
    if path.startswith("/api/"):
        return not path.startswith(_MAINTENANCE_API_PREFIX)
    return False


class MaintenanceBarrierMiddleware:
    """纯 ASGI：普通模式持 lease；维护模式默认拒（§5.2）。"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        controller = get_default_controller()
        if controller is None:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        status = controller.status()

        if status.in_maintenance:
            # 维护模式：health/静态/维护控制端点放行，其余业务面 503
            if path in _HEALTH_ALLOWED or not _is_business_path(path):
                await self.app(scope, receive, send)
                return
            if scope["type"] == "websocket":
                # WebSocket 拒绝：发送 close（1013 try again later）
                await send({"type": "websocket.close", "code": 1013, "reason": "maintenance"})
                return
            await _send_json_503(send)
            return

        # 普通模式：业务面请求自入口持 lease 直至响应完成（T03）
        if not _is_business_path(path):
            await self.app(scope, receive, send)
            return
        try:
            with controller.admission_slot(kind=f"http:{path.split('?')[0]}"):
                await self.app(scope, receive, send)
        except AdmissionRejected:
            # 闸门在排队后、进入前关上（PREPARING 已关新准入）
            await _send_json_503(send)


async def _send_json_503(send: Any) -> None:
    body = json.dumps(_MAINTENANCE_503_BODY).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 503,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
