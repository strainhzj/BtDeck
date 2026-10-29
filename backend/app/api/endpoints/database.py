# -*- coding: utf-8 -*-
"""数据库迁移控制端点（database-migration-ui W3-4/5/6/7，PLANS §8）。

鉴权（评审修正：前缀放行只是传输可达，不是授权豁免）：
- **统一控制依赖** ``require_database_control_access``：普通模式=普通管理员
  （require_authenticated_user 语义）；维护模式=维护 token（aud=btdeck-
  maintenance；无 verify_secret → 普通 API 天然拒，反向亦然）；
- 维护态动作参数必须携带 attemptId+epoch+stateVersion（CAS）；
- test-connection/target-readiness 只读（不建 schema、不 seed、不写源审计）；
- 屏障（W2）放行 ``/api/v1/database/`` 前缀仅为控制面可达，每条路由各自
  声明鉴权依赖（auth 路由覆盖契约测试强制）。

动作语义：start 单飞行；cancel 先 CANCELLING 后 worker ACK 才 CANCELLED；
leave 须安全收尾+未 COMMITTED；discard 走 §6.5 双确认；switch=§7 提交；
activation/clear=§7.3 同库交接。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.responseVO import CommonResponse
from app.services.db_migration.journal import Journal, JournalCorrupted

router = APIRouter()

_ERROR_CODES = {
    "DB_MIGRATION_STATE_CONFLICT": "409",
    "DB_MIGRATION_IN_PROGRESS": "409",
    "DB_MIGRATION_NEEDS_CREDENTIALS": "401",
    "DB_MIGRATION_WORKER_NOT_STOPPED": "409",
    "DB_MIGRATION_COMMITTED": "409",
    "DB_MIGRATION_DISCARD_REJECTED": "409",
    "DB_MIGRATION_ACTIVATION_ERROR": "409",
    "DB_MIGRATION_NOT_FOUND": "404",
    "DB_MIGRATION_UNAVAILABLE": "503",
}


# ---------------------------------------------------------------------------
# 统一控制依赖（普通态=普通管理员；维护态=维护 token）
# ---------------------------------------------------------------------------


async def require_database_control_access(request: Request) -> Dict[str, Any]:
    """数据库控制面鉴权（模式分派；显式依赖名供契约测试登记）。"""
    maintenance_mode = bool(getattr(request.app.state, "maintenance_mode", False))
    if maintenance_mode:
        from app.api.endpoints.maintenance import require_maintenance_token

        principal = await require_maintenance_token(request)
        return {"mode": "maintenance", "principal": getattr(principal, "username", "maintenance-user")}
    from app.auth.dependencies import require_authenticated_user

    user = await require_authenticated_user(request)
    return {"mode": "normal", "principal": getattr(user, "username", "user")}


def _manager(request: Request):
    manager = getattr(request.app.state, "database_migration_manager", None)
    if manager is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="DB_MIGRATION_UNAVAILABLE")
    return manager


# ---------------------------------------------------------------------------
# 只读组（§8：/status /migration/status /target-readiness /test-connection）
# ---------------------------------------------------------------------------


@router.get("/status", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)])
async def database_status(request: Request) -> CommonResponse:
    """当前有效库/配置来源/托管能力（脱敏；§9 展示有效实况不把 env 当实况）。"""
    from app.core.config import settings
    from app.services.db_migration.restart_adapter import hosting_capability

    from app.database import get_effective_database_config

    effective = get_effective_database_config()
    journal = Journal(str(settings.CONFIG_DIR))
    control = None
    try:
        control = journal.read_control()
    except JournalCorrupted:
        control = None
    return CommonResponse(
        status="success",
        code="200",
        data={
            "effective": effective.masked_summary(),
            "control": (
                {
                    "deploymentId": (control or {}).get("deployment_id"),
                    "generation": (control or {}).get("generation"),
                    "restartPending": bool((control or {}).get("restart_pending", False)),
                }
                if control is not None
                else None
            ),
            "hosting": hosting_capability(),
        },
    )


@router.get("/migration/status", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)])
async def migration_status(request: Request) -> CommonResponse:
    """attempt/phase/epoch/stateVersion/可用动作（§8；不暴露凭据）。"""
    manager = _manager(request)
    return CommonResponse(status="success", code="200", data=manager.status().as_dict())


@router.get("/target-readiness", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)])
async def target_readiness(request: Request) -> CommonResponse:
    """只读就绪面（switch 全量复核仍在管理器执行；§8）。"""
    manager = _manager(request)
    status = manager.status()
    return CommonResponse(
        status="success",
        code="200",
        data={
            "attemptId": status.attempt_id,
            "phase": status.phase,
            "readyToSwitch": status.phase == "ready_to_switch" and status.commit_phase == "NONE",
            "needsCredentials": status.needs_credentials,
        },
    )


class TestConnectionRequest(BaseModel):
    dialect: str = Field(pattern="^(sqlite|postgresql)$")
    sqlite_path: Optional[str] = None
    postgresql: Optional[Dict[str, Any]] = None


@router.post("/test-connection", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)])
async def test_connection(payload: TestConnectionRequest) -> CommonResponse:
    """显式目标连通/版本/TLS/权限探测（只读；不建 schema、不保存密码）。"""
    try:
        if payload.dialect == "sqlite":
            import os
            from pathlib import Path

            path = Path(payload.sqlite_path or "")
            if not path.is_absolute():
                return CommonResponse(status="error", code="400", msg="sqlite_path 必须为绝对路径")
            exists = path.exists()
            return CommonResponse(
                status="success",
                code="200",
                data={"dialect": "sqlite", "reachable": exists, "writable": os.access(path.parent, os.W_OK)},
            )
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool

        from app.services.db_migration.target_params import build_pg_url, pg_params_from_mapping

        params = pg_params_from_mapping(payload.postgresql or {})
        engine = create_engine(build_pg_url(params), poolclass=NullPool, connect_args={"connect_timeout": 8})
        try:
            with engine.connect() as conn:
                version = conn.execute(text("SHOW server_version")).scalar()
                empty = conn.execute(
                    text("SELECT count(*) FROM pg_tables WHERE schemaname = current_schema()")
                ).scalar()
        finally:
            engine.dispose()
        major = int(str(version).split(".")[0])
        return CommonResponse(
            status="success",
            code="200",
            data={
                "dialect": "postgresql",
                "reachable": True,
                "serverVersion": str(version),
                "versionOk": major >= 16,
                "targetEmpty": int(empty or 0) == 0,
                "sslmode": params.sslmode,
            },
        )
    except Exception as exc:  # noqa: BLE001 - 探测面汇总错误
        return CommonResponse(status="error", code="DB_MIGRATION_UNAVAILABLE", msg=f"连接失败: {exc}")


# ---------------------------------------------------------------------------
# 动作组（§8：start/credentials/resume/cancel/leave/discard-target）
# ---------------------------------------------------------------------------


class MigrationStartRequest(BaseModel):
    direction: str = Field(pattern="^(sqlite-to-pg|pg-to-sqlite)$")
    target: Dict[str, Any]
    password: str = Field(min_length=1, max_length=256)
    source: Optional[Dict[str, Any]] = None


@router.post("/migration/start", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)])
async def migration_start(request: Request, payload: MigrationStartRequest) -> CommonResponse:
    """管理器单飞行：关准入→排空→冻结→快照（§5.1/§6.1）。"""
    manager = _manager(request)
    try:
        status = manager.start_migration(
            payload.direction,
            payload.target,
            password=payload.password,
            source_desc=payload.source,
        )
        return CommonResponse(status="success", code="200", data=status.as_dict())
    except Exception as exc:  # noqa: BLE001 - 状态冲突面
        from app.services.db_migration.manager import StateConflict

        code = "DB_MIGRATION_STATE_CONFLICT" if isinstance(exc, StateConflict) else "DB_MIGRATION_UNAVAILABLE"
        return CommonResponse(status="error", code=_ERROR_CODES.get(code, "500"), msg=str(exc))


class CredentialsRequest(BaseModel):
    attempt_id: str = Field(min_length=1, max_length=96)
    password: str = Field(min_length=1, max_length=256)
    target: Dict[str, Any]


@router.post(
    "/migration/credentials", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)]
)
async def migration_credentials(request: Request, payload: CredentialsRequest) -> CommonResponse:
    """NEEDS_CREDENTIALS 恢复：重输绑定目标凭据（不临时换目标）。"""
    manager = _manager(request)
    try:
        manager.provide_credentials(payload.attempt_id, password=payload.password, target=payload.target)
        return CommonResponse(status="success", code="200", data=manager.status().as_dict())
    except Exception as exc:  # noqa: BLE001
        return CommonResponse(status="error", code="409", msg=str(exc))


class CasRequest(BaseModel):
    attempt_id: str = Field(min_length=1, max_length=96)
    epoch: str = Field(min_length=1, max_length=64)
    state_version: int = Field(ge=1)
    reason: Optional[str] = None


@router.post(
    "/migration/cancel", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)]
)
async def migration_cancel(request: Request, payload: CasRequest) -> CommonResponse:
    """请求协作取消（CANCELLING；worker ACK 前不报 CANCELLED，§6.4）。"""
    manager = _manager(request)
    manager.request_cancel(reason=payload.reason or "")
    return CommonResponse(status="success", code="200", data=manager.status().as_dict())


@router.post("/migration/leave", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)])
async def migration_leave(request: Request, payload: CasRequest) -> CommonResponse:
    """安全放弃回源（须已安全停止+未 COMMITTED；先撤销资格+推进 epoch）。"""
    manager = _manager(request)
    try:
        status = manager.leave(expect_epoch=payload.epoch, expect_state_version=payload.state_version)
        return CommonResponse(status="success", code="200", data=status.as_dict())
    except Exception as exc:  # noqa: BLE001
        return CommonResponse(status="error", code="409", msg=str(exc))


class DiscardRequest(BaseModel):
    attempt_id: str = Field(min_length=1, max_length=96)
    ownership_nonce: str = Field(min_length=1, max_length=128)
    database_id: str = Field(min_length=1, max_length=64)
    confirm_token: str = Field(min_length=1, max_length=160)


@router.post(
    "/migration/discard-target",
    response_model=CommonResponse,
    dependencies=[Depends(require_database_control_access)],
)
async def migration_discard_target(request: Request, payload: DiscardRequest) -> CommonResponse:
    """§6.5 最小删除授权（manifest 固定目标+双确认；PG 禁 CASCADE）。"""
    from app.core.config import settings

    from app.services.db_migration.discard import DiscardError, DiscardTargetService

    service = DiscardTargetService(str(settings.CONFIG_DIR))
    try:
        summary = service.authorize(
            payload.attempt_id,
            ownership_nonce=payload.ownership_nonce,
            database_id=payload.database_id,
            confirm_token=payload.confirm_token,
        )
    except DiscardError as exc:
        return CommonResponse(status="error", code="409", msg=str(exc))
    # 实际清理由维护流程在目标连接上执行（本端点返回授权+计划；§6.5 逐对象
    # 事务清理由 manager/CLI 调 discard_pg/discard_sqlite——避免端点内直连
    # 目标库的凭据面扩大）。
    return CommonResponse(
        status="success",
        code="200",
        data={"authorized": True, "plan": summary, "note": "授权核验通过；清理由维护流程在目标连接执行"},
    )


# ---------------------------------------------------------------------------
# switch + clear（§7 提交 / §7.3 同库交接）
# ---------------------------------------------------------------------------


class SwitchRequest(CasRequest):
    mode: str = Field(pattern="^(A|B)$")


@router.post(
    "/migration/switch", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)]
)
async def migration_switch(request: Request, payload: SwitchRequest) -> CommonResponse:
    """§7.2 提交（PREPARED→COMMITTED→发布→RESTART_PENDING；幂等）。"""
    from app.core.config import settings

    from app.services.db_migration.activation import ActivationError, ActivationService

    service = ActivationService(str(settings.CONFIG_DIR))
    try:
        manifest = service.manifest(payload.attempt_id)
        identity = {
            "expected_database_id": (manifest.get("target", {}) or {}).get("database_id"),
            "receipt_attempt_id": payload.attempt_id,
            "revision_at_import": manifest.get("tool_version"),
        }
        prepared = service.prepare_switch(
            payload.attempt_id,
            mode=payload.mode,
            candidate_active=(manifest.get("candidate_active") or {}),
            identity=identity,
        )
        result = service.commit_switch(payload.attempt_id)
        return CommonResponse(
            status="success",
            code="200",
            data={"prepared": prepared.__dict__, "commit": result},
        )
    except ActivationError as exc:
        return CommonResponse(status="error", code="409", msg=str(exc))
    except Exception as exc:  # noqa: BLE001
        return CommonResponse(status="error", code="500", msg=str(exc))


@router.post(
    "/activation/clear", response_model=CommonResponse, dependencies=[Depends(require_database_control_access)]
)
async def activation_clear(request: Request, payload: CasRequest) -> CommonResponse:
    """§7.3 同库受控交接（HANDOFF_SAME_DB；异库目标拒绝——引导新迁移）。"""
    from app.core.config import settings

    from app.services.db_migration.handoff import HandoffError, plan_handoff_same_db

    try:
        plan = plan_handoff_same_db(str(settings.CONFIG_DIR), payload.attempt_id)
    except HandoffError as exc:
        return CommonResponse(status="error", code="409", msg=str(exc))
    return CommonResponse(status="success", code="200", data=plan)
