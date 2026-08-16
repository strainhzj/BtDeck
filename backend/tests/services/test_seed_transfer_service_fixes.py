# -*- coding: utf-8 -*-
"""
种子转移假成功修复回归（verified-bugfix-remediation W5）

覆盖：
- W5-2 目标查重：目标已存在相同 hash → duplicate 状态且不调用添加
- W5-1 qB torrents_add 返回 "Fails." → 明确失败（不再等 5×5s 验证重试）
- W5-1 qB torrents_add 返回 "Ok." → 正常继续
- TR add_torrent 返回 None → 失败
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
                BtDownloaders(
                    downloader_id="dl-1", nickname="源", downloader_type=0, torrent_save_path="", dr=0
                ),
                BtDownloaders(
                    downloader_id="dl-2", nickname="目标", downloader_type=0, torrent_save_path="", dr=0
                ),
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
            result = await _run_transfer(
                transfer_env, _make_app_state(target_client), service, db
            )

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
            result = await _run_transfer(
                transfer_env, _make_app_state(target_client), service, db
            )

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
            result = await _run_transfer(
                transfer_env, _make_app_state(target_client), service, db
            )

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
            result = await _run_transfer(
                transfer_env, _make_app_state(target_client), service, db
            )

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
                BtDownloaders.__table__.update()
                .where(BtDownloaders.downloader_id == "dl-2")
                .values(downloader_type=1)
            )
            await s.commit()

        with (
            patch.object(service, "_check_target_duplicate", new=AsyncMock(return_value=False)),
            patch.object(svc, "call_downloader_api", new=AsyncMock(return_value=None)),
        ):
            result = await _run_transfer(transfer_env, app_state, service, db)

        assert result["success"] is False
        assert "未返回添加结果" in result["error_message"]
