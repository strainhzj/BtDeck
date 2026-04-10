# -*- coding: utf-8 -*-
"""
ReannounceService 的单元测试

测试 tracker 汇报核心服务的所有边界情况：
- qBittorrent reannounce 调用
- Transmission reannounce 调用（使用 torrent_id 而非 hash）
- 分批执行逻辑（每批500个）
- 空数据 / 无效下载器 / 下载器不可用
- SDK 调用异常处理
- 下载器类型不支持
- 大批量种子分批验证
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from datetime import datetime


# ==================== 辅助工具 ====================

class _FakeTorrentRecord:
    """轻量级种子记录对象，避免 ORM 依赖"""
    def __init__(
        self,
        info_id="info-001",
        hash="abc123def456",
        torrent_id="100",
        name="test.torrent",
        downloader_id="dl-001",
        status="downloading",
        dr=0,
    ):
        self.info_id = info_id
        self.hash = hash
        self.torrent_id = torrent_id
        self.name = name
        self.downloader_id = downloader_id
        self.status = status
        self.dr = dr


class _FakeDownloaderVO:
    """轻量级下载器VO对象"""
    def __init__(
        self,
        downloader_id="dl-001",
        downloader_type=0,
        nickname="test-qb",
        fail_time=0,
    ):
        self.downloader_id = downloader_id
        self.downloader_type = downloader_type
        self.nickname = nickname
        self.fail_time = fail_time
        self.client = MagicMock()


def make_torrent(**kwargs):
    return _FakeTorrentRecord(**kwargs)


def make_downloader(**kwargs):
    return _FakeDownloaderVO(**kwargs)


def make_torrents_batch(count, start_index=0, downloader_id="dl-001"):
    """批量创建种子记录"""
    return [
        make_torrent(
            info_id=f"info-{start_index + i:04d}",
            hash=f"hash_{start_index + i:04d}",
            torrent_id=str(start_index + i),
            name=f"torrent_{start_index + i}.torrent",
            downloader_id=downloader_id,
        )
        for i in range(count)
    ]


# ==================== Fixtures ====================

@pytest.fixture
def mock_db():
    """Mock 数据库 Session"""
    return MagicMock()


@pytest.fixture
def mock_app():
    """Mock FastAPI app with state.store"""
    app = MagicMock()
    app.state = MagicMock()
    app.state.store = MagicMock()
    app.state.store.get_snapshot_sync = MagicMock(return_value=[])
    return app


@pytest.fixture
def qb_downloader():
    """qBittorrent 下载器"""
    dl = make_downloader(downloader_id="dl-qb", downloader_type=0, nickname="qBittorrent")
    dl.client.torrents_reannounce = MagicMock()
    return dl


@pytest.fixture
def tr_downloader():
    """Transmission 下载器"""
    dl = make_downloader(downloader_id="dl-tr", downloader_type=1, nickname="Transmission")
    dl.client.reannounce_torrent = MagicMock()
    return dl


# ==================== 测试：execute_reannounce 基本调用 ====================

class TestExecuteReannounceBasic:
    """测试基本的 reannounce 执行"""

    @pytest.mark.asyncio
    async def test_qbittorrent_single_batch(self, mock_db, mock_app, qb_downloader):
        """qBittorrent 少于500个种子，单批次执行"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = make_torrents_batch(10, downloader_id="dl-qb")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app,
            db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["success_count"] == 10
        assert result["failed_count"] == 0
        qb_downloader.client.torrents_reannounce.assert_called_once()
        # 验证传入的 hashes
        call_args = qb_downloader.client.torrents_reannounce.call_args
        assert "torrent_hashes" in call_args.kwargs
        assert len(call_args.kwargs["torrent_hashes"]) == 10

    @pytest.mark.asyncio
    async def test_transmission_single_batch(self, mock_db, mock_app, tr_downloader):
        """Transmission 少于500个种子，单批次执行，使用 torrent_id"""
        mock_app.state.store.get_snapshot_sync.return_value = [tr_downloader]
        torrents = make_torrents_batch(10, downloader_id="dl-tr")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app,
            db=mock_db,
            downloader_id="dl-tr",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["success_count"] == 10
        assert result["failed_count"] == 0
        tr_downloader.client.reannounce_torrent.assert_called_once()
        # 验证传入的是 torrent_id 而非 hash
        call_args = tr_downloader.client.reannounce_torrent.call_args
        ids = call_args[0][0] if call_args[0] else call_args.kwargs.get("ids", [])
        assert len(ids) == 10
        # 确保 id 是字符串形式的数字
        assert ids[0] == "0"

    @pytest.mark.asyncio
    async def test_empty_torrent_list(self, mock_db, mock_app, qb_downloader):
        """空种子列表，应返回成功但数量为0"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app,
            db=mock_db,
            downloader_id="dl-qb",
            torrent_records=[],
            trigger_type="manual",
        )

        assert result["success_count"] == 0
        assert result["failed_count"] == 0
        qb_downloader.client.torrents_reannounce.assert_not_called()


# ==================== 测试：分批执行逻辑 ====================

class TestBatchExecution:
    """测试每批500个的分批执行逻辑"""

    @pytest.mark.asyncio
    async def test_exact_500_torrents(self, mock_db, mock_app, qb_downloader):
        """恰好500个种子，应单批次执行"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = make_torrents_batch(500, downloader_id="dl-qb")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["success_count"] == 500
        # qBittorrent 应只调用一次（恰好500个）
        assert qb_downloader.client.torrents_reannounce.call_count == 1

    @pytest.mark.asyncio
    async def test_501_torrents_two_batches(self, mock_db, mock_app, qb_downloader):
        """501个种子，应分为2批次（500 + 1）"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = make_torrents_batch(501, downloader_id="dl-qb")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["success_count"] == 501
        assert qb_downloader.client.torrents_reannounce.call_count == 2
        # 第一批500个，第二批1个
        first_call = qb_downloader.client.torrents_reannounce.call_args_list[0]
        second_call = qb_downloader.client.torrents_reannounce.call_args_list[1]
        assert len(first_call.kwargs["torrent_hashes"]) == 500
        assert len(second_call.kwargs["torrent_hashes"]) == 1

    @pytest.mark.asyncio
    async def test_1200_torrents_three_batches(self, mock_db, mock_app, qb_downloader):
        """1200个种子，应分为3批次（500 + 500 + 200）"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = make_torrents_batch(1200, downloader_id="dl-qb")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["success_count"] == 1200
        assert qb_downloader.client.torrents_reannounce.call_count == 3

    @pytest.mark.asyncio
    async def test_transmission_batching_with_ids(self, mock_db, mock_app, tr_downloader):
        """Transmission 大批量种子分批使用 torrent_id"""
        mock_app.state.store.get_snapshot_sync.return_value = [tr_downloader]
        torrents = make_torrents_batch(750, downloader_id="dl-tr")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-tr",
            torrent_records=torrents,
            trigger_type="scheduled",
        )

        assert result["success_count"] == 750
        assert tr_downloader.client.reannounce_torrent.call_count == 2


# ==================== 测试：下载器异常处理 ====================

class TestDownloaderErrors:
    """测试下载器相关的错误场景"""

    @pytest.mark.asyncio
    async def test_downloader_not_in_cache(self, mock_db, mock_app):
        """下载器不在缓存中，应返回失败"""
        mock_app.state.store.get_snapshot_sync.return_value = []

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-not-exist",
            torrent_records=make_torrents_batch(5),
            trigger_type="manual",
        )

        assert result["success_count"] == 0
        assert result["failed_count"] > 0

    @pytest.mark.asyncio
    async def test_downloader_failed(self, mock_db, mock_app):
        """下载器已失效（fail_time > 0），应返回失败"""
        dl = make_downloader(fail_time=3)
        mock_app.state.store.get_snapshot_sync.return_value = [dl]

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-001",
            torrent_records=make_torrents_batch(5),
            trigger_type="manual",
        )

        assert result["success_count"] == 0
        assert result["failed_count"] > 0

    @pytest.mark.asyncio
    async def test_downloader_no_client(self, mock_db, mock_app):
        """下载器客户端连接为None"""
        dl = make_downloader()
        dl.client = None
        mock_app.state.store.get_snapshot_sync.return_value = [dl]

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-001",
            torrent_records=make_torrents_batch(5),
            trigger_type="manual",
        )

        assert result["success_count"] == 0
        assert result["failed_count"] > 0

    @pytest.mark.asyncio
    async def test_unsupported_downloader_type(self, mock_db, mock_app):
        """不支持的下载器类型，应返回失败"""
        dl = make_downloader(downloader_type=99)
        mock_app.state.store.get_snapshot_sync.return_value = [dl]

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-001",
            torrent_records=make_torrents_batch(5),
            trigger_type="manual",
        )

        assert result["success_count"] == 0
        assert result["failed_count"] > 0


# ==================== 测试：SDK调用异常 ====================

class TestSDKExceptions:
    """测试SDK调用过程中的异常"""

    @pytest.mark.asyncio
    async def test_qbittorrent_sdk_error(self, mock_db, mock_app, qb_downloader):
        """qBittorrent SDK 抛出异常"""
        qb_downloader.client.torrents_reannounce.side_effect = Exception("Connection refused")
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = make_torrents_batch(10, downloader_id="dl-qb")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["failed_count"] == 10
        assert result["success_count"] == 0

    @pytest.mark.asyncio
    async def test_transmission_sdk_error(self, mock_db, mock_app, tr_downloader):
        """Transmission SDK 抛出异常"""
        tr_downloader.client.reannounce_torrent.side_effect = Exception("RPC error")
        mock_app.state.store.get_snapshot_sync.return_value = [tr_downloader]
        torrents = make_torrents_batch(10, downloader_id="dl-tr")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-tr",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["failed_count"] == 10
        assert result["success_count"] == 0

    @pytest.mark.asyncio
    async def test_partial_batch_failure(self, mock_db, mock_app, qb_downloader):
        """分批执行时第二批失败，第一批成功"""
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise Exception("Second batch failed")

        qb_downloader.client.torrents_reannounce.side_effect = side_effect
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = make_torrents_batch(600, downloader_id="dl-qb")  # 500 + 100

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["success_count"] == 500  # 第一批成功
        assert result["failed_count"] == 100   # 第二批失败


# ==================== 测试：触发类型 ====================

class TestTriggerType:
    """测试不同触发类型的日志记录"""

    @pytest.mark.asyncio
    async def test_manual_trigger(self, mock_db, mock_app, qb_downloader):
        """手动触发类型"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = make_torrents_batch(3, downloader_id="dl-qb")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["trigger_type"] == "manual"
        assert result["success_count"] == 3

    @pytest.mark.asyncio
    async def test_scheduled_trigger(self, mock_db, mock_app, qb_downloader):
        """定时触发类型"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = make_torrents_batch(3, downloader_id="dl-qb")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="scheduled",
        )

        assert result["trigger_type"] == "scheduled"
        assert result["success_count"] == 3


# ==================== 测试：边界值 ====================

class TestEdgeCases:
    """测试边界情况"""

    @pytest.mark.asyncio
    async def test_single_torrent(self, mock_db, mock_app, qb_downloader):
        """仅1个种子"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = [make_torrent(hash="single_hash", downloader_id="dl-qb")]

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["success_count"] == 1

    @pytest.mark.asyncio
    async def test_torrent_with_none_hash(self, mock_db, mock_app, qb_downloader):
        """种子 hash 为 None，应跳过"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = [
            make_torrent(hash="valid_hash", downloader_id="dl-qb"),
            make_torrent(hash=None, downloader_id="dl-qb"),
        ]

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        # None hash 应被安全过滤
        assert result["success_count"] >= 1

    @pytest.mark.asyncio
    async def test_transmission_torrent_with_none_id(self, mock_db, mock_app, tr_downloader):
        """Transmission 种子 torrent_id 为 None，应跳过"""
        mock_app.state.store.get_snapshot_sync.return_value = [tr_downloader]
        torrents = [
            make_torrent(torrent_id="100", downloader_id="dl-tr"),
            make_torrent(torrent_id=None, downloader_id="dl-tr"),
        ]

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-tr",
            torrent_records=torrents,
            trigger_type="manual",
        )

        # None torrent_id 应被安全过滤
        assert result["success_count"] >= 1

    @pytest.mark.asyncio
    async def test_app_state_no_store(self, mock_db, mock_app):
        """app.state 没有 store 属性"""
        del mock_app.state.store

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-001",
            torrent_records=make_torrents_batch(5),
            trigger_type="manual",
        )

        assert result["success_count"] == 0
        assert result["failed_count"] > 0

    @pytest.mark.asyncio
    async def test_very_large_batch(self, mock_db, mock_app, qb_downloader):
        """极大数量种子（10000个），验证分批正确性"""
        mock_app.state.store.get_snapshot_sync.return_value = [qb_downloader]
        torrents = make_torrents_batch(10000, downloader_id="dl-qb")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app, db=mock_db,
            downloader_id="dl-qb",
            torrent_records=torrents,
            trigger_type="manual",
        )

        assert result["success_count"] == 10000
        # 10000 / 500 = 20 批次
        assert qb_downloader.client.torrents_reannounce.call_count == 20
