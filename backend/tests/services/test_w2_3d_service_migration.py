# -*- coding: utf-8 -*-
"""
W2-3d 服务层下载器调用迁移测试（sync-database-blocking-remediation P0-04 收尾）

验证 reannounce / recycle_bin / seed_transfer 三个服务的 async 方法内，所有
下载器网络调用均经 call_downloader_api（DownloadLane.INTERACTIVE）执行，不再
直接同步调用 qB/TR 客户端：

- 成功路径：client 方法作为 func 传入 runtime，lane=INTERACTIVE（超时/操作名透传）
- 超时路径：call_downloader_api 抛 asyncio.TimeoutError 时，服务降级行为与迁移前一致
- 客户端缺失路径：store 中无客户端时服务降级行为不变，且不触发 runtime 调用
- reannounce 分批循环：每批都经 runtime 执行（500/500/200 三批断言）
- recycle_bin 轮询：等待 helper 的每次轮询都经 runtime 执行
- seed_transfer 双客户端：source/target 客户端在同一流程中都经 runtime 执行

所有用例 patch 服务模块命名空间内的 call_downloader_api（AsyncMock），不触碰真实
DownloaderApiRuntime 线程池；构造服务时 patch 其自建 DB 会话，避免触碰真实数据库。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.downloader_api_runtime import DownloadLane
from app.services.reannounce_service import BATCH_SIZE
from app.services.recycle_bin_service import RecycleBinService
from app.services.seed_transfer_service import SeedTransferService

import app.services.reannounce_service as reannounce_service
import app.services.recycle_bin_service as recycle_bin_service
import app.services.seed_transfer_service as seed_transfer_service

# ==================== 辅助工具 ====================


class _FakeTorrentRecord:
    """轻量级种子记录对象，避免 ORM 依赖"""

    def __init__(self, info_id="info-001", hash="abc123def456", torrent_id="100", downloader_id="dl-001"):
        self.info_id = info_id
        self.hash = hash
        self.torrent_id = torrent_id
        self.downloader_id = downloader_id


def make_torrents(count, downloader_id="dl-001"):
    """批量创建种子记录（torrent_id 为 text 形式数字，模拟库内存储）"""
    return [
        _FakeTorrentRecord(
            info_id=f"info-{i:04d}",
            hash=f"hash_{i:04d}",
            torrent_id=str(i),
            downloader_id=downloader_id,
        )
        for i in range(count)
    ]


def make_downloader_vo(downloader_id="dl-001", client=None, fail_time=0, downloader_type=0):
    """构造伪下载器 VO（app.state.store 快照元素）"""
    vo = SimpleNamespace()
    vo.downloader_id = downloader_id
    vo.client = client
    vo.fail_time = fail_time
    vo.downloader_type = downloader_type
    vo.nickname = "fake-downloader"
    return vo


def _assert_interactive_call(mock_call, func, downloader_id, timeout=30.0):
    """断言一次 runtime 调用：lane=INTERACTIVE、func 为客户端方法、downloader_id 正确。

    call_downloader_api 的 downloader_id/lane/func 为位置参数，kwargs/operation/timeout 为关键字参数。
    """
    call_args = mock_call.args
    call_kwargs = mock_call.kwargs
    assert call_args[0] == downloader_id, "downloader_id 必须透传"
    assert call_args[1] == DownloadLane.INTERACTIVE, "下载器调用必须走 INTERACTIVE lane"
    assert call_args[2] is func, "client 方法必须作为 func 传入 runtime"
    assert call_kwargs["timeout"] == timeout


class _FakeAsyncSession:
    """模拟 async with AsyncSessionLocal() 会话（审计日志写入用，commit/execute 可 await）。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def commit(self):
        pass

    async def execute(self, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        return result

    def add(self, *args, **kwargs):
        pass


# ==================== reannounce_service ====================


class TestReannounceMigration:
    """execute_reannounce 的所有远程调用必须经 call_downloader_api(INTERACTIVE)。"""

    @pytest.fixture
    def qb_app(self):
        client = MagicMock()
        vo = make_downloader_vo(downloader_id="dl-qb", client=client, downloader_type=0)
        app = SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace(get_snapshot_sync=lambda: [vo])))
        return app, client

    @pytest.fixture
    def tr_app(self):
        client = MagicMock()
        vo = make_downloader_vo(downloader_id="dl-tr", client=client, downloader_type=1)
        app = SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace(get_snapshot_sync=lambda: [vo])))
        return app, client

    @pytest.mark.asyncio
    async def test_qb_success_goes_through_runtime(self, qb_app):
        """成功路径：qB torrents_reannounce 经 runtime 调用，lane=INTERACTIVE。"""
        app, client = qb_app

        with patch.object(reannounce_service, "call_downloader_api", new=AsyncMock(return_value=None)) as mock_call:
            result = await reannounce_service.execute_reannounce(
                app=app,
                downloader_id="dl-qb",
                torrent_records=make_torrents(10, "dl-qb"),
                trigger_type="manual",
            )

        assert result["success_count"] == 10
        assert result["failed_count"] == 0
        mock_call.assert_awaited_once()
        _assert_interactive_call(mock_call.await_args, client.torrents_reannounce, "dl-qb")
        assert mock_call.await_args.kwargs["kwargs"] == {"torrent_hashes": [f"hash_{i:04d}" for i in range(10)]}
        assert mock_call.await_args.kwargs["operation"] == "qb_reannounce"

    @pytest.mark.asyncio
    async def test_tr_success_goes_through_runtime(self, tr_app):
        """成功路径：TR reannounce_torrent 经 runtime 调用，ids 为 int 列表。"""
        app, client = tr_app

        with patch.object(reannounce_service, "call_downloader_api", new=AsyncMock(return_value=None)) as mock_call:
            result = await reannounce_service.execute_reannounce(
                app=app,
                downloader_id="dl-tr",
                torrent_records=make_torrents(10, "dl-tr"),
                trigger_type="manual",
            )

        assert result["success_count"] == 10
        mock_call.assert_awaited_once()
        _assert_interactive_call(mock_call.await_args, client.reannounce_torrent, "dl-tr")
        ids = mock_call.await_args.kwargs["args"][0]
        assert ids == list(range(10))
        assert all(isinstance(tid, int) for tid in ids)
        assert mock_call.await_args.kwargs["operation"] == "tr_reannounce"

    @pytest.mark.asyncio
    async def test_batches_all_go_through_runtime(self, qb_app):
        """分批循环：1200 个种子分 3 批（500/500/200），每批都经 runtime 执行。"""
        app, client = qb_app

        with patch.object(reannounce_service, "call_downloader_api", new=AsyncMock(return_value=None)) as mock_call:
            result = await reannounce_service.execute_reannounce(
                app=app,
                downloader_id="dl-qb",
                torrent_records=make_torrents(1200, "dl-qb"),
                trigger_type="manual",
            )

        assert result["success_count"] == 1200
        assert mock_call.await_count == 3
        batch_sizes = [len(call.kwargs["kwargs"]["torrent_hashes"]) for call in mock_call.await_args_list]
        assert batch_sizes == [BATCH_SIZE, BATCH_SIZE, 200]
        for call in mock_call.await_args_list:
            assert call.args[1] == DownloadLane.INTERACTIVE
            assert call.args[2] is client.torrents_reannounce

    @pytest.mark.asyncio
    async def test_timeout_maps_to_batch_failure(self, qb_app):
        """超时路径：runtime 抛 asyncio.TimeoutError → 该批计入 failed，与迁移前一致。"""
        app, client = qb_app

        with patch.object(
            reannounce_service, "call_downloader_api", new=AsyncMock(side_effect=asyncio.TimeoutError())
        ) as mock_call:
            result = await reannounce_service.execute_reannounce(
                app=app,
                downloader_id="dl-qb",
                torrent_records=make_torrents(10, "dl-qb"),
                trigger_type="manual",
            )

        assert result["success_count"] == 0
        assert result["failed_count"] == 10
        assert len(result["failed_items"]) == 1
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_client_missing_short_circuits_without_runtime_call(self):
        """客户端缺失路径：store 中 client 为 None → 返回失败且不触发 runtime 调用。"""
        vo = make_downloader_vo(downloader_id="dl-qb", client=None, downloader_type=0)
        app = SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace(get_snapshot_sync=lambda: [vo])))

        with patch.object(reannounce_service, "call_downloader_api", new=AsyncMock(return_value=None)) as mock_call:
            result = await reannounce_service.execute_reannounce(
                app=app,
                downloader_id="dl-qb",
                torrent_records=make_torrents(5, "dl-qb"),
                trigger_type="manual",
            )

        assert result["success_count"] == 0
        assert result["failed_count"] == 5
        mock_call.assert_not_awaited()


# ==================== recycle_bin_service ====================


class TestRecycleBinMigration:
    """还原流程（torrents_add / add_torrent + 30 次轮询）全部经 runtime 执行。"""

    def make_service(self):
        """构造 RecycleBinService，用 MagicMock 替代自建同步 DB 会话。"""
        with patch("app.database.SessionLocal"):
            service = RecycleBinService()
        service.db = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_wait_qb_poll_goes_through_runtime(self):
        """轮询成功路径：qb torrents_info 每次轮询都经 runtime，lane=INTERACTIVE。"""
        qb_client = MagicMock()
        service = self.make_service()
        try:
            with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
                with patch.object(
                    recycle_bin_service, "call_downloader_api", new=AsyncMock(return_value=[object()])
                ) as mock_call:
                    ok = await service._wait_for_qb_torrent("dl-001", qb_client, "abc", max_retries=2)
        finally:
            service.close()

        assert ok is True
        mock_call.assert_awaited_once()
        _assert_interactive_call(mock_call.await_args, qb_client.torrents_info, "dl-001")
        assert mock_call.await_args.kwargs["kwargs"] == {"torrent_hashes": "abc"}
        assert mock_call.await_args.kwargs["operation"] == "restore_qb_wait_torrent"

    @pytest.mark.asyncio
    async def test_wait_tr_poll_goes_through_runtime(self):
        """轮询成功路径：tr get_torrent 经 runtime，lane=INTERACTIVE。"""
        tr_client = MagicMock()
        service = self.make_service()
        try:
            with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
                with patch.object(
                    recycle_bin_service, "call_downloader_api", new=AsyncMock(return_value=object())
                ) as mock_call:
                    ok = await service._wait_for_tr_torrent("dl-001", tr_client, "abc", max_retries=2)
        finally:
            service.close()

        assert ok is True
        mock_call.assert_awaited_once()
        _assert_interactive_call(mock_call.await_args, tr_client.get_torrent, "dl-001")
        assert mock_call.await_args.kwargs["args"] == ("abc",)
        assert mock_call.await_args.kwargs["operation"] == "restore_tr_wait_torrent"

    @pytest.mark.asyncio
    async def test_wait_poll_timeout_returns_false(self):
        """轮询超时路径：runtime 持续抛 TimeoutError → 轮询耗尽返回 False（每次仍经 runtime）。"""
        qb_client = MagicMock()
        service = self.make_service()
        try:
            with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
                with patch.object(
                    recycle_bin_service,
                    "call_downloader_api",
                    new=AsyncMock(side_effect=asyncio.TimeoutError()),
                ) as mock_call:
                    ok = await service._wait_for_qb_torrent("dl-001", qb_client, "abc", max_retries=3)
        finally:
            service.close()

        assert ok is False
        assert mock_call.await_count == 3
        for call in mock_call.await_args_list:
            assert call.args[1] == DownloadLane.INTERACTIVE
            assert call.args[2] is qb_client.torrents_info

    @pytest.mark.asyncio
    async def test_restore_qb_add_goes_through_runtime(self, tmp_path):
        """成功路径：还原到 qB 的 torrents_add + 轮询均经 runtime，参数透传不变。"""
        backup_file = tmp_path / "seed.torrent"
        backup_file.write_bytes(b"torrent-data")
        torrent = SimpleNamespace(
            hash="abc123",
            save_path="/data/save",
            backup_file_path=str(backup_file),
            downloader_id="dl-001",
        )
        downloader = SimpleNamespace(
            downloader_id="dl-001",
            is_qbittorrent=True,
            is_transmission=False,
            downloader_type=0,
            nickname="qb",
            fail_time=0,
            path_mapping=None,
        )
        qb_client = MagicMock()
        vo = make_downloader_vo(downloader_id="dl-001", client=qb_client, downloader_type=0)
        app = SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace(get_snapshot_sync=lambda: [vo])))

        service = self.make_service()
        try:
            with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
                with patch.object(
                    recycle_bin_service, "call_downloader_api", new=AsyncMock(return_value=[object()])
                ) as mock_call:
                    result = await service._restore_torrent_to_downloader(torrent, downloader, app=app)
        finally:
            service.close()

        assert result["success"] is True
        assert mock_call.await_count == 2  # torrents_add + 一次轮询

        add_call = mock_call.await_args_list[0]
        _assert_interactive_call(add_call, qb_client.torrents_add, "dl-001")
        add_kwargs = add_call.kwargs["kwargs"]
        assert add_kwargs["save_path"] == "/data/save"
        assert add_kwargs["is_stopped"] is True
        assert add_kwargs["skip_checking"] is True
        assert add_call.kwargs["operation"] == "restore_qb_add_torrent"

        poll_call = mock_call.await_args_list[1]
        _assert_interactive_call(poll_call, qb_client.torrents_info, "dl-001")
        assert poll_call.kwargs["operation"] == "restore_qb_wait_torrent"

    @pytest.mark.asyncio
    async def test_restore_add_timeout_returns_failure(self, tmp_path):
        """超时路径：还原添加调用抛 TimeoutError → 返回 success=False（不向上抛）。"""
        backup_file = tmp_path / "seed.torrent"
        backup_file.write_bytes(b"torrent-data")
        torrent = SimpleNamespace(
            hash="abc123",
            save_path="/data/save",
            backup_file_path=str(backup_file),
            downloader_id="dl-001",
        )
        downloader = SimpleNamespace(
            downloader_id="dl-001",
            is_qbittorrent=True,
            is_transmission=False,
            downloader_type=0,
            nickname="qb",
            fail_time=0,
            path_mapping=None,
        )
        qb_client = MagicMock()
        vo = make_downloader_vo(downloader_id="dl-001", client=qb_client, downloader_type=0)
        app = SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace(get_snapshot_sync=lambda: [vo])))

        service = self.make_service()
        try:
            with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
                with patch.object(
                    recycle_bin_service, "call_downloader_api", new=AsyncMock(side_effect=asyncio.TimeoutError())
                ) as mock_call:
                    result = await service._restore_torrent_to_downloader(torrent, downloader, app=app)
        finally:
            service.close()

        assert result["success"] is False
        assert "error" in result
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restore_client_missing_short_circuits_without_runtime_call(self, tmp_path):
        """客户端缺失路径：store 中 client 为 None → success=False 且不触发 runtime。"""
        backup_file = tmp_path / "seed.torrent"
        backup_file.write_bytes(b"torrent-data")
        torrent = SimpleNamespace(
            hash="abc123",
            save_path="/data/save",
            backup_file_path=str(backup_file),
            downloader_id="dl-001",
        )
        downloader = SimpleNamespace(
            downloader_id="dl-001",
            is_qbittorrent=True,
            is_transmission=False,
            downloader_type=0,
            nickname="qb",
            fail_time=0,
            path_mapping=None,
        )
        vo = make_downloader_vo(downloader_id="dl-001", client=None, downloader_type=0)
        app = SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace(get_snapshot_sync=lambda: [vo])))

        service = self.make_service()
        try:
            with patch.object(
                recycle_bin_service, "call_downloader_api", new=AsyncMock(return_value=None)
            ) as mock_call:
                result = await service._restore_torrent_to_downloader(torrent, downloader, app=app)
        finally:
            service.close()

        assert result["success"] is False
        assert "客户端连接不存在" in result["error"]
        mock_call.assert_not_awaited()


# ==================== seed_transfer_service ====================


class TestSeedTransferMigration:
    """转移流程（target 添加/验证 + source 删除）双客户端全部经 runtime 执行。"""

    def make_service(self, db=None):
        """构造 SeedTransferService，backup_manager 用 MagicMock 替代（避免自建 DB 会话）。"""
        with patch.object(seed_transfer_service, "TorrentFileBackupManagerService", return_value=MagicMock()):
            return SeedTransferService(db=db if db is not None else MagicMock())

    @pytest.mark.asyncio
    async def test_verify_qb_goes_through_runtime(self):
        """成功路径：验证 qB 种子状态经 runtime（target_client.torrents_info），lane=INTERACTIVE。"""
        service = self.make_service()
        target_client = MagicMock()
        fake_torrent = SimpleNamespace(state="downloading")

        with patch.object(
            seed_transfer_service, "call_downloader_api", new=AsyncMock(return_value=[fake_torrent])
        ) as mock_call:
            ok = await service._verify_transfer(
                downloader_id=2,
                target_client=target_client,
                downloader_type=0,
                info_hash="h",
                max_retries=1,
                retry_interval=0,
            )

        assert ok is True
        mock_call.assert_awaited_once()
        _assert_interactive_call(mock_call.await_args, target_client.torrents_info, 2)
        assert mock_call.await_args.kwargs["kwargs"] == {"torrent_hashes": "h"}
        assert mock_call.await_args.kwargs["operation"] == "transfer_qb_verify"

    @pytest.mark.asyncio
    async def test_verify_tr_goes_through_runtime(self):
        """成功路径：验证 TR 种子状态经 runtime（target_client.get_torrents）。"""
        service = self.make_service()
        target_client = MagicMock()
        fake_torrent = SimpleNamespace(status="downloading")

        with patch.object(
            seed_transfer_service, "call_downloader_api", new=AsyncMock(return_value=[fake_torrent])
        ) as mock_call:
            ok = await service._verify_transfer(
                downloader_id=2,
                target_client=target_client,
                downloader_type=1,
                info_hash="h",
                max_retries=1,
                retry_interval=0,
            )

        assert ok is True
        mock_call.assert_awaited_once()
        _assert_interactive_call(mock_call.await_args, target_client.get_torrents, 2)
        assert mock_call.await_args.kwargs["args"] == ("h",)
        assert mock_call.await_args.kwargs["operation"] == "transfer_tr_verify"

    @pytest.mark.asyncio
    async def test_verify_timeout_returns_false(self):
        """超时路径：验证轮询抛 TimeoutError → 返回 False（每次仍经 runtime）。"""
        service = self.make_service()
        target_client = MagicMock()

        with patch.object(
            seed_transfer_service,
            "call_downloader_api",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ) as mock_call:
            ok = await service._verify_transfer(
                downloader_id=2,
                target_client=target_client,
                downloader_type=0,
                info_hash="h",
                max_retries=2,
                retry_interval=0,
            )

        assert ok is False
        assert mock_call.await_count == 2
        for call in mock_call.await_args_list:
            assert call.args[1] == DownloadLane.INTERACTIVE
            assert call.args[2] is target_client.torrents_info

    @pytest.mark.asyncio
    async def test_delete_source_qb_goes_through_runtime(self):
        """成功路径：删除 qB 源种子经 runtime（source_client.torrents_delete），lane=INTERACTIVE。"""
        service = self.make_service()
        source_client = MagicMock()

        with patch.object(seed_transfer_service, "call_downloader_api", new=AsyncMock(return_value=None)) as mock_call:
            ok = await service._delete_source_torrent(
                downloader_id=1, source_client=source_client, downloader_type=0, info_hash="h", delete_files=False
            )

        assert ok is True
        mock_call.assert_awaited_once()
        _assert_interactive_call(mock_call.await_args, source_client.torrents_delete, 1)
        assert mock_call.await_args.kwargs["kwargs"] == {"delete_files": False, "torrent_hashes": "h"}
        assert mock_call.await_args.kwargs["operation"] == "transfer_qb_delete_source"

    @pytest.mark.asyncio
    async def test_delete_source_tr_goes_through_runtime(self):
        """成功路径：删除 TR 源种子经 runtime（source_client.remove_torrent）。"""
        service = self.make_service()
        source_client = MagicMock()

        with patch.object(seed_transfer_service, "call_downloader_api", new=AsyncMock(return_value=None)) as mock_call:
            ok = await service._delete_source_torrent(
                downloader_id=1, source_client=source_client, downloader_type=1, info_hash="h", delete_files=True
            )

        assert ok is True
        mock_call.assert_awaited_once()
        _assert_interactive_call(mock_call.await_args, source_client.remove_torrent, 1)
        assert mock_call.await_args.kwargs["kwargs"] == {"delete_data": True, "ids": "h"}
        assert mock_call.await_args.kwargs["operation"] == "transfer_tr_delete_source"

    @pytest.mark.asyncio
    async def test_delete_source_timeout_returns_false(self):
        """超时路径：删除源种子抛 TimeoutError → 返回 False（异常被吞，与迁移前一致）。"""
        service = self.make_service()
        source_client = MagicMock()

        with patch.object(
            seed_transfer_service,
            "call_downloader_api",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ) as mock_call:
            ok = await service._delete_source_torrent(
                downloader_id=1, source_client=source_client, downloader_type=0, info_hash="h", delete_files=False
            )

        assert ok is False
        mock_call.assert_awaited_once()
        assert mock_call.await_args.args[1] == DownloadLane.INTERACTIVE

    @pytest.mark.asyncio
    async def test_transfer_seed_source_and_target_both_go_through_runtime(self, tmp_path):
        """双客户端：完整转移流程中 target 添加/验证与 source 删除均经 runtime 执行。"""
        backup_file = tmp_path / "seed.torrent"
        backup_file.write_bytes(b"torrent-data")

        source_dl = SimpleNamespace(downloader_id=1, nickname="src", downloader_type=0, torrent_save_path="")
        target_dl = SimpleNamespace(downloader_id=2, nickname="dst", downloader_type=0, torrent_save_path="")
        torrent_info = SimpleNamespace(name="my-seed", save_path="/src/path")

        db = MagicMock()
        db_result = MagicMock()
        db_result.scalar_one_or_none.side_effect = [source_dl, target_dl, torrent_info]
        db.execute = AsyncMock(return_value=db_result)

        target_client = MagicMock()
        source_client = MagicMock()
        target_vo = make_downloader_vo(downloader_id=2, client=target_client, downloader_type=0)
        source_vo = make_downloader_vo(downloader_id=1, client=source_client, downloader_type=0)
        store = SimpleNamespace(get_snapshot=AsyncMock(return_value=[target_vo, source_vo]))
        app_state = SimpleNamespace(store=store)

        fake_torrent = SimpleNamespace(state="downloading")  # 验证轮询直接命中成功

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            with patch.object(seed_transfer_service, "TorrentFileBackupManagerService", return_value=MagicMock()):
                service = SeedTransferService(db=db)
            service.backup_manager.get_backup_info = AsyncMock(
                return_value={
                    "success": True,
                    "backup": SimpleNamespace(task_name="my-seed", file_path=str(backup_file)),
                }
            )
            service.backup_manager.increment_use_count = AsyncMock()
            with patch.object(
                seed_transfer_service, "call_downloader_api", new=AsyncMock(return_value=[fake_torrent])
            ) as mock_call:
                with patch.object(seed_transfer_service, "AsyncSessionLocal", return_value=_FakeAsyncSession()):
                    result = await service.transfer_seed(
                        source_downloader_id=1,
                        target_downloader_id=2,
                        info_hash="h",
                        target_path="/dst/path",
                        delete_source=True,
                        user_id=1,
                        username="tester",
                        app_state=app_state,
                    )

        assert result["success"] is True
        assert result["transfer_status"] == "success"
        # 添加(target) + 验证(target) + 删除(source) 三次 runtime 调用
        assert mock_call.await_count == 3
        add_call = mock_call.await_args_list[0]
        _assert_interactive_call(add_call, target_client.torrents_add, 2)
        assert add_call.kwargs["kwargs"]["save_path"] == "/dst/path"
        assert add_call.kwargs["operation"] == "transfer_qb_add_torrent"

        verify_call = mock_call.await_args_list[1]
        _assert_interactive_call(verify_call, target_client.torrents_info, 2)
        assert verify_call.kwargs["operation"] == "transfer_qb_verify"

        delete_call = mock_call.await_args_list[2]
        _assert_interactive_call(delete_call, source_client.torrents_delete, 1)
        assert delete_call.kwargs["operation"] == "transfer_qb_delete_source"

    @pytest.mark.asyncio
    async def test_transfer_target_client_missing_short_circuits(self, tmp_path):
        """客户端缺失路径：目标下载器 client 为 None → 转移失败且不触发 runtime。"""
        backup_file = tmp_path / "seed.torrent"
        backup_file.write_bytes(b"torrent-data")

        source_dl = SimpleNamespace(downloader_id=1, nickname="src", downloader_type=0, torrent_save_path="")
        target_dl = SimpleNamespace(downloader_id=2, nickname="dst", downloader_type=0, torrent_save_path="")
        torrent_info = SimpleNamespace(name="my-seed", save_path="/src/path")

        db = MagicMock()
        db_result = MagicMock()
        db_result.scalar_one_or_none.side_effect = [source_dl, target_dl, torrent_info]
        db.execute = AsyncMock(return_value=db_result)

        target_vo = make_downloader_vo(downloader_id=2, client=None, downloader_type=0)
        source_vo = make_downloader_vo(downloader_id=1, client=MagicMock(), downloader_type=0)
        store = SimpleNamespace(get_snapshot=AsyncMock(return_value=[target_vo, source_vo]))
        app_state = SimpleNamespace(store=store)

        with patch.object(seed_transfer_service, "TorrentFileBackupManagerService", return_value=MagicMock()):
            service = SeedTransferService(db=db)
        service.backup_manager.get_backup_info = AsyncMock(
            return_value={"success": True, "backup": SimpleNamespace(task_name="my-seed", file_path=str(backup_file))}
        )
        with patch.object(seed_transfer_service, "call_downloader_api", new=AsyncMock(return_value=None)) as mock_call:
            with patch.object(seed_transfer_service, "AsyncSessionLocal", return_value=_FakeAsyncSession()):
                result = await service.transfer_seed(
                    source_downloader_id=1,
                    target_downloader_id=2,
                    info_hash="h",
                    target_path="/dst/path",
                    delete_source=False,
                    user_id=1,
                    username="tester",
                    app_state=app_state,
                )

        assert result["success"] is False
        assert "添加种子到qBittorrent失败" in result["error_message"]
        mock_call.assert_not_awaited()
