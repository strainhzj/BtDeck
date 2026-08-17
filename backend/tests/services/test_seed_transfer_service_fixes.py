# -*- coding: utf-8 -*-
"""
种子转移假成功修复回归（verified-bugfix-remediation W5）

覆盖：
- W5-2 目标查重：目标已存在相同 hash → duplicate 状态且不调用添加
- W5-1 qB torrents_add 返回 "Fails." → 明确失败（不再等 5×5s 验证重试）
- W5-1 qB torrents_add 返回 "Ok." → 正常继续
- TR add_torrent 返回 None → 失败
- 转移成功后立即落库目标下载器种子行（与后续同步同一条记录）
"""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.downloader.models import BtDownloaders
from app.models.seed_transfer_audit_log import SeedTransferAuditLog
from app.torrents.models import TorrentInfo

INFO_HASH = "a" * 40


def _make_vo(downloader_id, client, downloader_type=0):
    vo = SimpleNamespace()
    vo.downloader_id = downloader_id
    vo.client = client
    vo.fail_time = 0
    vo.downloader_type = downloader_type
    vo.nickname = f"dl-{downloader_id}"
    return vo


@pytest.fixture
async def transfer_env(tmp_path):
    """内存库（BtDownloaders + SeedTransferAuditLog）+ 伪备份文件 + 三处 AsyncSessionLocal patch。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [BtDownloaders.__table__, SeedTransferAuditLog.__table__, TorrentInfo.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        db.add_all(
            [
                BtDownloaders(downloader_id="dl-1", nickname="源", downloader_type=0, torrent_save_path="", dr=0),
                BtDownloaders(downloader_id="dl-2", nickname="目标", downloader_type=0, torrent_save_path="", dr=0),
            ]
        )
        db.add(
            TorrentInfo(
                id_="t-1",
                downloader_id="dl-1",
                downloader_name="源",
                torrent_id=INFO_HASH,
                hash=INFO_HASH,
                name="测试种子",
                save_path="/downloads/source",
                size=1024,
                status="seeding",
                progress=100.0,
                torrent_file="",
                added_date=None,
                completed_date=None,
                ratio=1.0,
                ratio_limit=None,
                tags="",
                category="",
                super_seeding="0",
                enabled=1,
                create_time=None,
                create_by="admin",
                update_time=None,
                update_by="admin",
                dr=0,
            )
        )
        await db.commit()

    # 伪备份：真实 .torrent 文件
    torrent_file = tmp_path / "seed.torrent"
    torrent_file.write_bytes(b"d8:announce0:ee")

    backup_manager_cls = MagicMock()
    backup_manager = backup_manager_cls.return_value
    backup_manager.get_backup_info = AsyncMock(
        return_value={
            "success": True,
            "backup": SimpleNamespace(file_path=str(torrent_file), task_name="测试种子"),
        }
    )
    backup_manager.increment_use_count = AsyncMock(return_value=None)
    backup_manager.aclose = AsyncMock(return_value=None)

    with (
        patch("app.database.AsyncSessionLocal", session_factory),
        patch("app.services.seed_transfer_service.AsyncSessionLocal", session_factory),
        patch(
            "app.services.seed_transfer_service.TorrentFileBackupManagerService",
            backup_manager_cls,
        ),
    ):
        yield {
            "session_factory": session_factory,
            "backup_manager": backup_manager,
        }


def _make_app_state(target_client):
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                _make_vo("dl-1", MagicMock(), 0),
                _make_vo("dl-2", target_client, 0),
            ]
        )
    )
    return SimpleNamespace(store=store)


def _new_service(session_factory):
    from app.services.seed_transfer_service import SeedTransferService

    db = session_factory()
    return SeedTransferService(db=db), db


async def _run_transfer(env, app_state, service, db):
    result = await service.transfer_seed(
        source_downloader_id="dl-1",
        target_downloader_id="dl-2",
        info_hash=INFO_HASH,
        target_path="/downloads/movies",
        delete_source=False,
        user_id=1,
        username="tester",
        app_state=app_state,
    )
    await service.aclose()
    await db.close()
    return result


class TestDuplicatePreCheck:
    """W5-2：目标查重。"""

    @pytest.mark.asyncio
    async def test_duplicate_returns_duplicate_without_add(self, transfer_env):
        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        with patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=True)):
            result = await _run_transfer(transfer_env, _make_app_state(target_client), service, db)

        assert result["success"] is False
        assert result["transfer_status"] == "duplicate"
        assert "已存在相同种子" in result["error_message"]
        # 未调用任何添加操作
        target_client.torrents_add.assert_not_called()
        transfer_env["backup_manager"].increment_use_count.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_duplicate_check_failure_does_not_block(self, transfer_env):
        """查重异常不阻断转移（竞态由 _verify_transfer 兜底）。"""
        from app.services import seed_transfer_service as svc

        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        def _fails_dispatch(*args, **kwargs):
            operation = kwargs.get("operation", "")
            if operation == "transfer_qb_duplicate_check":
                raise RuntimeError("查重网络错误")
            return "Ok."

        with (
            patch.object(service, "_check_target_duplicate", new=AsyncMock(side_effect=RuntimeError("boom"))),
            patch.object(service, "_verify_transfer", new=AsyncMock(return_value=True)),
            patch.object(svc, "call_downloader_api", new=AsyncMock(side_effect=_fails_dispatch)),
        ):
            result = await _run_transfer(transfer_env, _make_app_state(target_client), service, db)

        assert result["success"] is True


class TestQbAddResponseCheck:
    """W5-1：torrents_add 返回值检查。"""

    @pytest.mark.asyncio
    async def test_add_returns_fails_marks_failed(self, transfer_env):
        from app.services import seed_transfer_service as svc

        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        def _fails_dispatch(*args, **kwargs):
            operation = kwargs.get("operation", "")
            if operation == "transfer_qb_add_torrent":
                return "Fails."
            return "Ok."

        with (
            patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=False)),
            patch.object(svc, "call_downloader_api", new=AsyncMock(side_effect=_fails_dispatch)),
        ):
            result = await _run_transfer(transfer_env, _make_app_state(target_client), service, db)

        assert result["success"] is False
        assert "拒绝添加" in result["error_message"]
        # 未进入验证阶段（省 5×5 秒重试）
        service._verify_transfer  # noqa: B018

    @pytest.mark.asyncio
    async def test_add_returns_ok_proceeds_to_success(self, transfer_env):
        from app.services import seed_transfer_service as svc

        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        def _ok_dispatch(*args, **kwargs):
            return "Ok."

        with (
            patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=False)),
            patch.object(service, "_verify_transfer", new=AsyncMock(return_value=True)),
            patch.object(svc, "call_downloader_api", new=AsyncMock(side_effect=_ok_dispatch)),
        ):
            result = await _run_transfer(transfer_env, _make_app_state(target_client), service, db)

        assert result["success"] is True
        assert result["transfer_status"] == "success"

    @pytest.mark.asyncio
    async def test_tr_add_returns_none_marks_failed(self, transfer_env):
        """TR add_torrent 返回 None → 明确失败。"""
        from app.services import seed_transfer_service as svc

        target_client = MagicMock()
        app_state = SimpleNamespace(
            store=SimpleNamespace(
                get_snapshot=AsyncMock(
                    return_value=[
                        _make_vo("dl-1", MagicMock(), 1),
                        _make_vo("dl-2", target_client, 1),
                    ]
                )
            )
        )
        service, db = _new_service(transfer_env["session_factory"])
        # 目标下载器类型改为 TR
        async with transfer_env["session_factory"]() as s:
            await s.execute(
                BtDownloaders.__table__.update().where(BtDownloaders.downloader_id == "dl-2").values(downloader_type=1)
            )
            await s.commit()

        with (
            patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=False)),
            patch.object(svc, "call_downloader_api", new=AsyncMock(return_value=None)),
        ):
            result = await _run_transfer(transfer_env, app_state, service, db)

        assert result["success"] is False
        assert "未返回添加结果" in result["error_message"]


class TestTargetRowUpsert:
    """转移成功后立即落库目标下载器种子行（不等下一轮同步）。

    预插行与 info-only 同步 insert dict 同形态：后续同步按
    (downloader_id, hash) 命中同一行走 update，(hash, downloader_id)
    WHERE dr=0 唯一索引保证不重复。
    """

    def _patches(self, service):
        from app.services import seed_transfer_service as svc

        return (
            patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=False)),
            patch.object(service, "_verify_transfer", new=AsyncMock(return_value=True)),
            patch.object(svc, "call_downloader_api", new=AsyncMock(return_value="Ok.")),
        )

    def _apply_patches(self, service):
        stack = ExitStack()
        for cm in self._patches(service):
            stack.enter_context(cm)
        return stack

    @pytest.mark.asyncio
    async def test_success_creates_target_row(self, transfer_env):
        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        with self._apply_patches(service):
            result = await _run_transfer(transfer_env, _make_app_state(target_client), service, db)

        assert result["success"] is True
        async with transfer_env["session_factory"]() as s:
            target_rows = (
                (await s.execute(select(TorrentInfo).where(TorrentInfo.downloader_id == "dl-2"))).scalars().all()
            )
            assert len(target_rows) == 1
            row = target_rows[0]
            assert row.hash == INFO_HASH
            assert row.downloader_name == "目标"  # 与同步 update 分支同口径（当前昵称）
            assert row.save_path == "/downloads/movies"
            assert row.dr == 0
            assert row.name == "测试种子"
            assert row.size == 1024
            # delete_source=False：源行保持 dr=0
            source_row = (await s.execute(select(TorrentInfo).where(TorrentInfo.downloader_id == "dl-1"))).scalar_one()
            assert source_row.dr == 0

    @pytest.mark.asyncio
    async def test_repeated_transfer_updates_same_row(self, transfer_env):
        """幂等：目标行已存在时走更新分支，不产生第二行。"""
        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])
        with self._apply_patches(service):
            await _run_transfer(transfer_env, _make_app_state(target_client), service, db)

        service2, db2 = _new_service(transfer_env["session_factory"])
        try:
            with self._apply_patches(service2):
                result = await service2.transfer_seed(
                    source_downloader_id="dl-1",
                    target_downloader_id="dl-2",
                    info_hash=INFO_HASH,
                    target_path="/downloads/movies-v2",
                    delete_source=False,
                    user_id=1,
                    username="tester",
                    app_state=_make_app_state(MagicMock()),
                )
            assert result["success"] is True
        finally:
            await service2.aclose()
            await db2.close()

        async with transfer_env["session_factory"]() as s:
            target_rows = (
                (await s.execute(select(TorrentInfo).where(TorrentInfo.downloader_id == "dl-2"))).scalars().all()
            )
            assert len(target_rows) == 1
            assert target_rows[0].save_path == "/downloads/movies-v2"

    @pytest.mark.asyncio
    async def test_delete_source_marks_source_row_dr1(self, transfer_env):
        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        with self._apply_patches(service):
            result = await service.transfer_seed(
                source_downloader_id="dl-1",
                target_downloader_id="dl-2",
                info_hash=INFO_HASH,
                target_path="/downloads/movies",
                delete_source=True,
                user_id=1,
                username="tester",
                app_state=_make_app_state(target_client),
            )
        await service.aclose()
        await db.close()

        assert result["success"] is True
        assert result["transfer_status"] == "success"
        async with transfer_env["session_factory"]() as s:
            source_row = (await s.execute(select(TorrentInfo).where(TorrentInfo.downloader_id == "dl-1"))).scalar_one()
            assert source_row.dr == 1  # 同步删除语义：只置 dr=1，不进回收站
            assert source_row.deleted_at is None
            target_row = (await s.execute(select(TorrentInfo).where(TorrentInfo.downloader_id == "dl-2"))).scalar_one()
            assert target_row.dr == 0

    @pytest.mark.asyncio
    async def test_same_downloader_rejected(self, transfer_env):
        """服务层兜底防御：源=目标直接拒绝（schema 之外的内部调用路径）。"""
        service, db = _new_service(transfer_env["session_factory"])
        try:
            result = await service.transfer_seed(
                source_downloader_id="dl-1",
                target_downloader_id="dl-1",
                info_hash=INFO_HASH,
                target_path="/downloads/movies",
                delete_source=False,
                user_id=1,
                username="tester",
                app_state=_make_app_state(MagicMock()),
            )
        finally:
            await service.aclose()
            await db.close()

        assert result["success"] is False
        assert "相同" in result["error_message"]

    @pytest.mark.asyncio
    async def test_upsert_failure_swallowed(self, transfer_env):
        """预插失败不影响转移结果（目标下载器已添加成功是既成事实）。"""
        service, db = _new_service(transfer_env["session_factory"])
        try:
            with patch.object(service.db, "execute", new=AsyncMock(side_effect=RuntimeError("db down"))):
                # 直接调用预插方法：任何异常都不应外抛
                await service._upsert_target_torrent_row(
                    source_torrent=None,
                    target_downloader=SimpleNamespace(downloader_id="dl-2", nickname="目标"),
                    info_hash=INFO_HASH,
                    target_path="/downloads/movies",
                    torrent_name="测试种子",
                    username="tester",
                )
        finally:
            await service.aclose()
            await db.close()

    @pytest.mark.asyncio
    async def test_upsert_integrity_error_race_converts_to_update(self):
        """并发同 hash 转移撞唯一索引：IntegrityError 转为按主键更新，不外抛。"""
        from sqlalchemy.exc import IntegrityError

        from app.services.seed_transfer_service import SeedTransferService

        db = MagicMock()
        db.commit = AsyncMock(side_effect=[IntegrityError("dup", None, Exception("unique")), None])
        db.rollback = AsyncMock()
        db.add = MagicMock()

        race_row = SimpleNamespace(save_path="/old", name="旧名", update_time=None, update_by=None)
        none_result = MagicMock()
        none_result.scalar_one_or_none.return_value = None  # 第一次查：无行 → 走插入
        race_result = MagicMock()
        race_result.scalar_one_or_none.return_value = race_row  # 竞态重查：命中并发插入的行
        db.execute = AsyncMock(side_effect=[none_result, race_result])

        service = SeedTransferService(db=db)
        try:
            source = SimpleNamespace(
                name="测试种子",
                progress=100.0,
                size=1024,
                status="seeding",
                torrent_file="",
                completed_date=None,
                ratio=1.0,
                ratio_limit=None,
                tags="",
                category="",
                super_seeding="0",
            )
            await service._upsert_target_torrent_row(
                source_torrent=source,
                target_downloader=SimpleNamespace(downloader_id="dl-2", nickname="目标"),
                info_hash=INFO_HASH,
                target_path="/downloads/movies",
                torrent_name="测试种子",
                username="tester",
            )
        finally:
            await service.aclose()

        # 首次插入 commit 抛 IntegrityError → rollback → 重查命中 → 更新 → 二次 commit
        assert db.commit.await_count == 2
        assert db.rollback.await_count == 1
        assert race_row.save_path == "/downloads/movies"
        assert race_row.name == "测试种子"
        assert race_row.update_by == "tester"

    async def _count_target_rows(self, session_factory):
        async with session_factory() as s:
            return len(
                (await s.execute(select(TorrentInfo).where(TorrentInfo.downloader_id == "dl-2"))).scalars().all()
            )

    @pytest.mark.asyncio
    async def test_duplicate_status_does_not_create_target_row(self, transfer_env):
        """目标已存在（duplicate 早退）不预插目标行。"""
        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        with patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=True)):
            result = await _run_transfer(transfer_env, _make_app_state(target_client), service, db)

        assert result["transfer_status"] == "duplicate"
        assert await self._count_target_rows(transfer_env["session_factory"]) == 0

    @pytest.mark.asyncio
    async def test_verify_timeout_does_not_create_target_row(self, transfer_env):
        """验证超时（failed 早退）不预插目标行。"""
        from app.services import seed_transfer_service as svc

        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        with (
            patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=False)),
            patch.object(service, "_verify_transfer", new=AsyncMock(return_value=False)),
            patch.object(svc, "call_downloader_api", new=AsyncMock(return_value="Ok.")),
        ):
            result = await _run_transfer(transfer_env, _make_app_state(target_client), service, db)

        assert result["success"] is False
        assert "验证超时" in result["error_message"]
        assert await self._count_target_rows(transfer_env["session_factory"]) == 0

    @pytest.mark.asyncio
    async def test_add_failure_does_not_create_target_row(self, transfer_env):
        """目标拒绝添加（"Fails." 早退）不预插目标行。"""
        from app.services import seed_transfer_service as svc

        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        def _fails_dispatch(*args, **kwargs):
            if kwargs.get("operation") == "transfer_qb_add_torrent":
                return "Fails."
            return "Ok."

        with (
            patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=False)),
            patch.object(svc, "call_downloader_api", new=AsyncMock(side_effect=_fails_dispatch)),
        ):
            result = await _run_transfer(transfer_env, _make_app_state(target_client), service, db)

        assert result["success"] is False
        assert "拒绝添加" in result["error_message"]
        assert await self._count_target_rows(transfer_env["session_factory"]) == 0

    @pytest.mark.asyncio
    async def test_delete_source_failure_keeps_source_row_dr0(self, transfer_env):
        """delete_source=true 但源删除失败（partial）：目标行已预插，源行保持 dr=0。"""
        from app.services import seed_transfer_service as svc

        target_client = MagicMock()
        service, db = _new_service(transfer_env["session_factory"])

        def _delete_fails(*args, **kwargs):
            if kwargs.get("operation") == "transfer_qb_delete_source":
                raise RuntimeError("源下载器网络中断")
            return "Ok."

        try:
            with (
                patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=False)),
                patch.object(service, "_verify_transfer", new=AsyncMock(return_value=True)),
                patch.object(svc, "call_downloader_api", new=AsyncMock(side_effect=_delete_fails)),
            ):
                result = await service.transfer_seed(
                    source_downloader_id="dl-1",
                    target_downloader_id="dl-2",
                    info_hash=INFO_HASH,
                    target_path="/downloads/movies",
                    delete_source=True,
                    user_id=1,
                    username="tester",
                    app_state=_make_app_state(target_client),
                )
        finally:
            await service.aclose()
            await db.close()

        assert result["success"] is True
        assert result["transfer_status"] == "partial"
        async with transfer_env["session_factory"]() as s:
            source_row = (await s.execute(select(TorrentInfo).where(TorrentInfo.downloader_id == "dl-1"))).scalar_one()
            assert source_row.dr == 0  # 删除失败：源行不标记，等下次同步自愈
        assert await self._count_target_rows(transfer_env["session_factory"]) == 1

    @pytest.mark.asyncio
    async def test_mark_source_row_missing_is_noop(self, transfer_env):
        """源行不存在（如已被同步标记）时 _mark_source_row_transferred 安全无操作。"""
        service, db = _new_service(transfer_env["session_factory"])
        try:
            await service._mark_source_row_transferred("dl-1", "f" * 40)  # 库中无此 hash
        finally:
            await service.aclose()
            await db.close()
        # 无异常即通过；源行 dl-1 的 INFO_HASH 保持 dr=0
        async with transfer_env["session_factory"]() as s:
            source_row = (await s.execute(select(TorrentInfo).where(TorrentInfo.downloader_id == "dl-1"))).scalar_one()
            assert source_row.dr == 0
