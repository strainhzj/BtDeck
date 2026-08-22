# -*- coding: utf-8 -*-
"""
Service close()/aclose() 回归测试（prod-hotfix-2026-07-19 P0）

覆盖三个 Service 的资源释放契约：
1. RecycleBinService.close()                — 同步、_owns_db=True
2. TorrentFileBackupManagerService.aclose() — 异步、可注入外部 db（_owns_db=False）
3. SeedTransferService.aclose()             — 异步、级联关闭 backup_manager

测试目标（mutation 反向验证点）：
- T1: _owns_db=True 时调 close 真的关掉自建 session（mock spy）
- T2: 重复调 close 幂等（_closed 标志阻止二次 close）
- T3: close 内部异常被吞咽不向上抛（防止 finally 二次异常覆盖业务异常）
- T4: _owns_db=False（外部 session）时 close 不误关外部 session（核心安全契约）
- T5: SeedTransferService.aclose() 转发到 backup_manager.aclose()
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# RecycleBinService.close() — 三件套
# ============================================================================


class TestRecycleBinServiceClose:
    """RecycleBinService.close() 资源释放回归。"""

    def test_close_calls_db_close_once_when_owned(self):
        """T1: _owns_db=True 时 close() 应调用底层 self.db.close() 一次。"""
        with patch("app.database.SessionLocal") as MockSession:
            mock_session = MagicMock()
            MockSession.return_value = mock_session

            from app.services.recycle_bin_service import RecycleBinService

            svc = RecycleBinService()
            assert svc._owns_db is True
            assert svc._closed is False

            svc.close()

            mock_session.close.assert_called_once()
            assert svc._closed is True

    def test_close_is_idempotent(self):
        """T2: 重复 close() 只应关闭一次（_closed 标志早退）。"""
        with patch("app.database.SessionLocal") as MockSession:
            mock_session = MagicMock()
            MockSession.return_value = mock_session

            from app.services.recycle_bin_service import RecycleBinService

            svc = RecycleBinService()
            svc.close()
            svc.close()
            svc.close()

            assert mock_session.close.call_count == 1, "重复 close 不应再次关闭 session"

    def test_close_swallows_db_close_exception(self):
        """T3: close() 内部 db.close() 抛异常时应被吞咽（只 log warning），不向上传播。"""
        with patch("app.database.SessionLocal") as MockSession:
            mock_session = MagicMock()
            mock_session.close.side_effect = RuntimeError("simulated close failure")
            MockSession.return_value = mock_session

            from app.services.recycle_bin_service import RecycleBinService

            svc = RecycleBinService()
            # 不应抛
            svc.close()
            assert svc._closed is True

    def test_does_not_close_external_session_when_not_owned(self):
        """T4: _owns_db=False 时（外部传入 db）close() 不应关闭外部 session。

        这是核心安全契约：避免误关调用方持有的共享 session。
        通过 __new__ 绕过 __init__ 直接构造一个 _owns_db=False 实例。
        """
        from app.services.recycle_bin_service import RecycleBinService

        external_session = MagicMock()
        svc = RecycleBinService.__new__(RecycleBinService)
        svc.db = external_session
        svc._owns_db = False
        svc._closed = False

        svc.close()

        external_session.close.assert_not_called()


# ============================================================================
# TorrentFileBackupManagerService.aclose() — 三件套
# ============================================================================


class TestTorrentFileBackupManagerServiceAclose:
    """TorrentFileBackupManagerService.aclose() 资源释放回归。"""

    @pytest.mark.asyncio
    async def test_aclose_calls_db_close_once_when_owned(self):
        """T1: 自建 db（db=None 默认）时 aclose 关闭底层 session。"""
        mock_session = AsyncMock()
        with patch("app.services.torrent_file_backup_manager.AsyncSessionLocal") as M:
            M.return_value = mock_session

            from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService

            svc = TorrentFileBackupManagerService()
            assert svc._owns_db is True

            await svc.aclose()

            mock_session.close.assert_awaited_once()
            assert svc._closed is True

    @pytest.mark.asyncio
    async def test_aclose_is_idempotent(self):
        """T2: 重复 aclose 只关闭一次。"""
        mock_session = AsyncMock()
        with patch("app.services.torrent_file_backup_manager.AsyncSessionLocal") as M:
            M.return_value = mock_session

            from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService

            svc = TorrentFileBackupManagerService()
            await svc.aclose()
            await svc.aclose()
            await svc.aclose()

            assert mock_session.close.await_count == 1, "重复 aclose 不应再次关闭 session"

    @pytest.mark.asyncio
    async def test_aclose_swallows_db_close_exception(self):
        """T3: aclose 内部异常被吞咽不向上抛。"""
        mock_session = AsyncMock()
        mock_session.close.side_effect = RuntimeError("simulated async close failure")
        with patch("app.services.torrent_file_backup_manager.AsyncSessionLocal") as M:
            M.return_value = mock_session

            from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService

            svc = TorrentFileBackupManagerService()
            await svc.aclose()  # 不应抛
            assert svc._closed is True

    @pytest.mark.asyncio
    async def test_does_not_close_external_session_when_not_owned(self):
        """T4: 外部 db 传入时 aclose 不应关闭外部 session。"""
        external_session = AsyncMock()

        from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService

        # 传入外部 db：构造函数应置 _owns_db=False
        svc = TorrentFileBackupManagerService(db=external_session)
        assert svc._owns_db is False

        await svc.aclose()

        external_session.close.assert_not_awaited()


# ============================================================================
# SeedTransferService.aclose() — 转发与异常吞咽
# ============================================================================


class TestSeedTransferServiceAclose:
    """SeedTransferService.aclose() 资源释放回归。"""

    @pytest.mark.asyncio
    async def test_aclose_forwards_to_backup_manager(self):
        """T5: aclose() 应转发到 backup_manager.aclose()。"""
        with patch("app.services.seed_transfer_service.TorrentFileBackupManagerService") as Mgr:
            mgr = AsyncMock()
            Mgr.return_value = mgr

            from app.services.seed_transfer_service import SeedTransferService

            svc = SeedTransferService(db=MagicMock())

            await svc.aclose()

            mgr.aclose.assert_awaited_once()
            assert svc._closed is True

    @pytest.mark.asyncio
    async def test_aclose_is_idempotent(self):
        """T2: 重复 aclose 只转发一次。"""
        with patch("app.services.seed_transfer_service.TorrentFileBackupManagerService") as Mgr:
            mgr = AsyncMock()
            Mgr.return_value = mgr

            from app.services.seed_transfer_service import SeedTransferService

            svc = SeedTransferService(db=MagicMock())
            await svc.aclose()
            await svc.aclose()
            await svc.aclose()

            assert mgr.aclose.await_count == 1

    @pytest.mark.asyncio
    async def test_aclose_swallows_backup_manager_exception(self):
        """T3: backup_manager.aclose 抛异常时被吞咽。"""
        with patch("app.services.seed_transfer_service.TorrentFileBackupManagerService") as Mgr:
            mgr = AsyncMock()
            mgr.aclose.side_effect = RuntimeError("simulated cascade failure")
            Mgr.return_value = mgr

            from app.services.seed_transfer_service import SeedTransferService

            svc = SeedTransferService(db=MagicMock())
            await svc.aclose()  # 不应抛
            assert svc._closed is True
