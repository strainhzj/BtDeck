# -*- coding: utf-8 -*-
"""维护控制面端点（database-migration-ui W2-5，PLANS §5.3）。

仅维护模式可用（lifespan 维护分支装载 ``app.state.maintenance_auth`` 与
``app.state.maintenance``；普通模式这些端点返回 409——控制面不存在就不该
被调用，W3 的 start 端点另行落位）。本批交付：

- ``POST /api/v1/maintenance/auth``：账户+密码+可选 TOTP → 独立短期维护
  token（零源写；失败限流/缺 seed 语义见 maintenance_auth）；
- ``POST /api/v1/maintenance/auth/renew``：维护 token 旋转续期；
- ``GET  /api/v1/maintenance/status``：粗粒度维护状态（不泄露数据库/凭据，
  §5.4；供维护客户端与 W4 前端恢复页使用）。

认证事件全部落本地审计（先持久化后签发；磁盘满拒绝签发而非丢日志）。
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.responseVO import CommonResponse
from app.services.db_migration.local_audit import KIND_AUTH, LocalAuditUnavailable
from app.services.db_migration.maintenance import get_default_controller
from app.services.db_migration.maintenance_auth import (
    MaintenanceAuthError,
    MaintenanceAuthService,
)

router = APIRouter()

_ERROR_CODES = {
    "MAINTENANCE_AUTH_INVALID": "401",
    "MAINTENANCE_AUTH_TOTP_REQUIRED": "400",
    "MAINTENANCE_AUTH_TOTP_INVALID": "401",
    "MAINTENANCE_AUTH_LOCKED": "423",
    "MAINTENANCE_AUTH_ACCOUNT_NOT_ALLOWED": "403",
    "MAINTENANCE_TOKEN_INVALID": "401",
    "MAINTENANCE_AUTH_NO_USERS": "503",
}


class MaintenanceAuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    twofa_code: Optional[str] = Field(default=None, max_length=16)


def _auth_service(request: Request) -> Optional[MaintenanceAuthService]:
    return getattr(request.app.state, "maintenance_auth", None)


def _maintenance_context(request: Request) -> tuple[Optional[MaintenanceAuthService], dict[str, Any]]:
    service = _auth_service(request)
    controller = get_default_controller()
    status = controller.status() if controller is not None else None
    if service is None or status is None or not status.in_maintenance:
        return None, {}
    return service, {
        "attempt_id": status.attempt_id,
        "epoch": status.epoch,
    }


def _audit(request: Request) -> Any:
    return getattr(request.app.state, "maintenance_audit", None)


def _extract_token(request: Request) -> Optional[str]:
    header = request.headers.get("x-access-token")
    if header:
        return header
    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def require_maintenance_token(request: Request) -> dict[str, Any]:
    """维护 token 校验依赖（aud/scope/jti/吊销；普通 access token 无此 aud 即拒）。"""
    service = _auth_service(request)
    token = _extract_token(request)
    if service is None or not token:
        raise _unauthorized()
    try:
        return service.verify_token(token)
    except MaintenanceAuthError:
        raise _unauthorized() from None


def _unauthorized() -> Exception:
    from fastapi import HTTPException

    return HTTPException(
        status_code=401,
        detail=CommonResponse(
            status="error",
            msg="maintenance token invalid",
            code="401",
            data={"reasonCode": "MAINTENANCE_TOKEN_INVALID"},
        ).model_dump(),
    )


@router.post("/auth", summary="维护认证签发", response_model=CommonResponse)
async def maintenance_auth(request: MaintenanceAuthRequest, http_request: Request) -> CommonResponse:
    service, binding = _maintenance_context(http_request)
    if service is None:
        return CommonResponse(
            status="error", msg="not in maintenance mode", code="409", data={"reasonCode": "NOT_MAINTENANCE"}
        )
    client_ip = http_request.client.host if (http_request.client and http_request.client.host) else ""
    audit = _audit(http_request)
    try:
        result = service.authenticate(
            username=request.username,
            password=request.password,
            twofa_code=request.twofa_code,
            attempt_id=binding.get("attempt_id"),
            epoch=binding.get("epoch"),
        )
    except MaintenanceAuthError as exc:
        if audit is not None:
            try:
                audit.audit_event(
                    KIND_AUTH,
                    operator=request.username,
                    action="maintenance-auth",
                    outcome="failed",
                    ip=client_ip,
                    user_agent=http_request.headers.get("user-agent") or "",
                    detail={"reason": str(exc)},
                    attempt_id=binding.get("attempt_id"),
                    epoch=binding.get("epoch"),
                )
            except LocalAuditUnavailable:
                pass  # 认证失败事件不可写不改变拒绝结果
        code = _ERROR_CODES.get(str(exc), "401")
        return CommonResponse(
            status="error",
            msg="maintenance auth failed",
            code=code,
            data={"reasonCode": str(exc)},
        )
    if audit is not None:
        try:
            audit.audit_event(
                KIND_AUTH,
                operator=request.username,
                action="maintenance-auth",
                outcome="ok",
                ip=client_ip,
                user_agent=http_request.headers.get("user-agent") or "",
                attempt_id=binding.get("attempt_id"),
                epoch=binding.get("epoch"),
            )
        except LocalAuditUnavailable:
            # 磁盘满：拒绝签发（关键副作用前审计先持久化，§5.3）
            return CommonResponse(
                status="error",
                msg="local audit unavailable",
                code="503",
                data={"reasonCode": "MAINTENANCE_AUDIT_UNAVAILABLE"},
            )
    # 不把 token 本体记进审计（T22）
    return CommonResponse(
        status="success",
        msg="maintenance token issued",
        code="200",
        data={
            "maintenanceToken": result["maintenance_token"],
            "tokenType": result["token_type"],
            "expiresIn": result["expires_in"],
        },
    )


@router.post("/auth/renew", summary="维护 token 续期", response_model=CommonResponse)
async def maintenance_auth_renew(http_request: Request) -> CommonResponse:
    service, binding = _maintenance_context(http_request)
    if service is None:
        return CommonResponse(
            status="error", msg="not in maintenance mode", code="409", data={"reasonCode": "NOT_MAINTENANCE"}
        )
    token = _extract_token(http_request)
    if not token:
        raise _unauthorized()
    try:
        result = service.renew(token, attempt_id=binding.get("attempt_id"), epoch=binding.get("epoch"))
    except MaintenanceAuthError as exc:
        return CommonResponse(
            status="error",
            msg="maintenance token invalid",
            code=_ERROR_CODES.get(str(exc), "401"),
            data={"reasonCode": str(exc)},
        )
    audit = _audit(http_request)
    if audit is not None:
        try:
            audit.audit_event(
                KIND_AUTH,
                operator=str(result.get("username") or ""),
                action="maintenance-auth-renew",
                outcome="ok",
                ip=http_request.client.host if (http_request.client and http_request.client.host) else "",
                attempt_id=binding.get("attempt_id"),
                epoch=binding.get("epoch"),
            )
        except LocalAuditUnavailable:
            return CommonResponse(
                status="error",
                msg="local audit unavailable",
                code="503",
                data={"reasonCode": "MAINTENANCE_AUDIT_UNAVAILABLE"},
            )
    return CommonResponse(
        status="success",
        msg="maintenance token renewed",
        code="200",
        data={
            "maintenanceToken": result["maintenance_token"],
            "tokenType": result["token_type"],
            "expiresIn": result["expires_in"],
        },
    )


@router.get("/status", summary="维护状态（粗粒度）", response_model=CommonResponse)
async def maintenance_status(
    http_request: Request,
    token_payload: dict[str, Any] = Depends(require_maintenance_token),
) -> CommonResponse:
    controller = get_default_controller()
    if controller is None:
        return CommonResponse(
            status="error", msg="not in maintenance mode", code="409", data={"reasonCode": "NOT_MAINTENANCE"}
        )
    status = controller.status()
    if not status.in_maintenance:
        return CommonResponse(
            status="error", msg="not in maintenance mode", code="409", data={"reasonCode": "NOT_MAINTENANCE"}
        )
    return CommonResponse(
        status="success",
        msg="ok",
        code="200",
        data={
            "state": status.state,
            "heldReason": status.held_reason,
            "attemptId": status.attempt_id,
            "activeLeases": status.active_leases,
            "cancelRequested": status.cancel_requested,
            "bootRecovery": status.boot_recovery,
        },
    )
