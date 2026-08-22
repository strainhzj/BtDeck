# -*- coding: utf-8 -*-
"""
种子转移接口回归测试——下载器不存在场景

覆盖 POST /api/v1/seed-transfer/transfer 的"下载器不存在"分支：
- 源下载器不存在 → code='400' + failed 审计日志（"源下载器不存在"）
- 目标下载器不存在（源存在）→ code='400' + failed 审计日志（"目标下载器不存在"）
- 源和目标都不存在 → 走源分支优先
- schema 校验：info_hash 非 40 位 hex → 422；source==target → 422

关键架构点（经探索确认）：
- 下载器不存在分支是**纯 DB + 零网络**：只查 BtDownloaders + 写 SeedTransferAuditLog，
  不触达下载器 client、不读 store snapshot（store 仅在下载器都存在后才用）。
- endpoint 从 app.factory 导入全局 app 实例，直接用 app.state.store（非 Depends）。
  → 测试需在全局 app.state 上设 store（或 patch hasattr 检查）。
- endpoint 和 service 的 _log_transfer_attempt 都用 `from app.database import AsyncSessionLocal`
  模块级导入自建 session → 测试 patch app.database.AsyncSessionLocal 注入测试库。
- SeedTransferAuditLog.source/target_downloader_id 是 Integer 列，但 schema 传 str。
  → 测试用纯数字字符串（如 "99999"）规避类型边界（SQLite 容忍）。
- 审计日志写入有 try/except 兜底（失败只 logger.error，不让请求 500）。
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import Base
from app.downloader.models import BtDownloaders
from app.factory import app as global_app
from app.models.seed_transfer_audit_log import SeedTransferAuditLog

URL = "/api/v1/torrents/transfer"


def _body(*, source="99999", target="88888", info_hash=None, target_path="/downloads/movies"):
    """构造最小合法 SeedTransferRequest body。

    downloader_id 用纯数字字符串（SQLite Integer 列容忍，规避类型边界）。
    info_hash 默认一个合法 40 位 hex。
    """
    return {
        "source_downloader_id": source,
        "target_downloader_id": target,
        "info_hash": info_hash or "a" * 40,
        "target_path": target_path,
        "delete_source": False,
    }


@pytest.fixture
async def async_engine_factory():
    """aiosqlite 异步内存库 + patch AsyncSessionLocal 注入。

    patch app.database.AsyncSessionLocal 同时覆盖 endpoint（seed_transfer.py:86）
    和 service._log_transfer_attempt（seed_transfer_service.py:624）两处自建 session。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [BtDownloaders.__table__, SeedTransferAuditLog.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    test_session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # patch 三处导入点：app.database / endpoints.seed_transfer / services.seed_transfer_service
    # （service._log_transfer_attempt 在模块内直接用 AsyncSessionLocal 名字）
    with (
        patch("app.database.AsyncSessionLocal", test_session_factory),
        patch("app.api.endpoints.seed_transfer.AsyncSessionLocal", test_session_factory),
        patch("app.services.seed_transfer_service.AsyncSessionLocal", test_session_factory),
    ):
        # 在全局 app.state 上挂 store（endpoint 直接读 global_app.state.store）
        had_store = hasattr(global_app.state, "store")
        old_store = getattr(global_app.state, "store", None)
        global_app.state.store = SimpleNamespace()  # 占位（下载器不存在场景不实际调用）
        try:
            yield engine, test_session_factory
        finally:
            if had_store:
                global_app.state.store = old_store
            else:
                del global_app.state.store
            async with engine.begin() as conn:
                await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=tables))


@pytest.fixture
def client(async_engine_factory):
    """独立 FastAPI app，override 认证（endpoint 用全局 app.state.store，已在上 fixture 挂载）。"""
    engine, _ = async_engine_factory
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


async def _add_downloader(engine, factory, *, downloader_id, nickname):
    """预置一个 BtDownloaders 行（Integer 列，传 int）。"""
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        dl = BtDownloaders(downloader_id=str(downloader_id), nickname=nickname, downloader_type=0)
        s.add(dl)
        await s.commit()


async def _count_audit(engine, *, status=None, error_contains=None):
    """查 SeedTransferAuditLog 表，按状态/错误关键词过滤计数。"""
    from sqlalchemy import select

    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        q = select(SeedTransferAuditLog)
        if status:
            q = q.where(SeedTransferAuditLog.transfer_status == status)
        rows = (await s.execute(q)).scalars().all()
        if error_contains:
            rows = [r for r in rows if r.error_message and error_contains in r.error_message]
        return rows


# ==================== 组1：下载器不存在（核心，纯 DB 零网络） ====================


class TestDownloaderNotFound:
    @pytest.mark.asyncio
    async def test_source_not_found(self, client, async_engine_factory):
        """源下载器不存在 → code='400'，error_message 含"源下载器不存在"。"""
        engine, factory = async_engine_factory
        r = client.post(URL, json=_body(source="99999"))
        body = r.json()
        assert body["code"] == "400"
        assert body["status"] == "error"
        assert "源下载器不存在" in body["data"]["error_message"]
        assert body["data"]["transfer_status"] == "failed"
        assert body["data"]["success"] is False

    @pytest.mark.asyncio
    async def test_source_not_found_writes_failed_audit(self, client, async_engine_factory):
        """源下载器不存在 → 写一条 failed 审计日志（error_message 含"源下载器不存在"+ id 渲染）。"""
        client.post(URL, json=_body(source="99999"))
        engine, _ = async_engine_factory
        logs = await _count_audit(engine, status="failed", error_contains="源下载器不存在")
        assert len(logs) == 1
        assert logs[0].transfer_status == "failed"
        # 身份锁定：error_message 须含请求的 id（锁定 id 渲染正确）
        assert "99999" in logs[0].error_message

    @pytest.mark.asyncio
    async def test_target_not_found(self, client, async_engine_factory):
        """源存在但目标不存在 → error_message 含"目标下载器不存在"，审计 source_name 有值。"""
        engine, factory = async_engine_factory
        await _add_downloader(engine, factory, downloader_id="11111", nickname="源下载器")
        r = client.post(URL, json=_body(source="11111", target="88888"))
        body = r.json()
        assert body["code"] == "400"
        assert "目标下载器不存在" in body["data"]["error_message"]
        # 审计日志：source_downloader_name 应有值（源存在），target 为空
        logs = await _count_audit(engine, status="failed", error_contains="目标下载器不存在")
        assert len(logs) == 1
        assert logs[0].source_downloader_name == "源下载器"
        assert logs[0].target_downloader_name == ""

    @pytest.mark.asyncio
    async def test_both_not_found_goes_source_branch(self, client, async_engine_factory):
        """源和目标都不存在 → 走源分支优先（error_message 是"源下载器不存在"）。"""
        client.post(URL, json=_body(source="99999", target="88888"))
        engine, _ = async_engine_factory
        logs = await _count_audit(engine, error_contains="源下载器不存在")
        assert len(logs) == 1
        # source/target name 都为空（都不存在）
        assert logs[0].source_downloader_name == ""
        assert logs[0].target_downloader_name == ""

    @pytest.mark.asyncio
    async def test_audit_records_info_hash_and_user(self, client, async_engine_factory):
        """审计日志记录 info_hash / username / target_path（身份锁定）。"""
        client.post(URL, json=_body(source="99999", info_hash="b" * 40))
        engine, _ = async_engine_factory
        logs = await _count_audit(engine, status="failed")
        assert logs[0].info_hash == "b" * 40
        assert logs[0].username == "tester", "转移审计使用真实登录用户（修复硬编码 admin）"
        assert logs[0].target_path == "/downloads/movies"


# ==================== 组2：schema 校验（422，不打 DB） ====================


class TestSchemaValidation:
    def test_invalid_info_hash_returns_422(self, client):
        """info_hash 非 40 位 hex → 422（Pydantic field_validator）。"""
        r = client.post(URL, json=_body(info_hash="short"))
        assert r.status_code == 422

    def test_non_hex_info_hash_returns_422(self, client):
        """info_hash 含非 hex 字符 → 422。"""
        r = client.post(URL, json=_body(info_hash="z" * 40))
        assert r.status_code == 422

    def test_same_downloader_returns_422(self, client):
        """source == target → 422（different_downloaders validator）。"""
        r = client.post(URL, json=_body(source="11111", target="11111"))
        assert r.status_code == 422

    def test_missing_required_field_returns_422(self, client):
        """缺 target_path → 422。"""
        body = _body()
        del body["target_path"]
        r = client.post(URL, json=body)
        assert r.status_code == 422


# ==================== 组3：认证 ====================


class TestAuth:
    def test_no_token_returns_401(self, async_engine_factory):
        """无认证 → 401（detail 是 dict）。"""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(URL, json=_body())
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "401"
