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
- 【回归】Transmission torrent_id 必须转 int（修复 "is not valid torrent id" 报错）
"""

import re

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from datetime import datetime


@pytest.fixture(autouse=True)
def _patch_call_downloader_api(monkeypatch):
    """本文件测试直接执行 func，不经过真实 runtime 单例（与 test_torrent_speed_regression
    同款约定，见其 456 行注释）：同一 pytest 进程中先跑的 API 测试用 TestClient 触发
    lifespan，会把全局单例 downloader_api_runtime 的 executor shutdown（不可逆），
    导致本文件调用真实 call_downloader_api 报 cannot schedule new futures after shutdown。
    直接执行 func 保持异常语义（client 抛什么异常就透传什么），与迁移前行为一致。
    """
    from app.services import reannounce_service as _rs

    async def _direct_call(downloader_id, lane, func, args=(), kwargs=None, *, timeout=None, operation=""):
        return func(*args, **(kwargs or {}))

    monkeypatch.setattr(_rs, "call_downloader_api", _direct_call)


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

# 40 位十六进制（v1 BTIH），用于校验 str 类型 id 是否为合法 hash
_HEX40_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class _TypeCheckingTransmissionClient:
    """模拟真实 transmission_rpc.Client 的 id 校验行为（回归测试专用）。

    transmission_rpc 的 _parse_torrent_id 规则：
    - int 且 >= 0 → 通过（数字 ID）
    - str 且正好 40 位 hex → 通过（sha1 hash）
    - 其他 → 抛 ValueError "is not valid torrent id, should be a hex str for sha1 hash"

    本库 torrent_info.torrent_id 列存为 text 形式的数字（如 '103'），
    服务层必须用 _to_transmission_id 转成 int 才能通过该校验。
    若有人改回直接传字符串 id，此 fake client 会抛出与生产环境一致的 ValueError，
    使回归测试在 client 层即失败（而非靠 isinstance 间接断言），收敛性最强。
    """

    def __init__(self):
        self.calls = []  # 记录每次 reannounce_torrent 调用传入的 ids

    @staticmethod
    def _parse(tid):
        # bool 是 int 子类，但不是合法 torrent id，先排除
        if isinstance(tid, bool):
            raise ValueError(f"{tid} is not valid torrent id")
        if isinstance(tid, int):
            if tid < 0:
                raise ValueError(f"{tid} is not valid torrent id")
            return tid
        if isinstance(tid, str):
            if _HEX40_RE.match(tid):
                return tid
            raise ValueError(
                f"{tid} is not valid torrent id, should be a hex str for sha1 hash"
            )
        raise ValueError(f"{tid} is not valid torrent id")

    def reannounce_torrent(self, ids):
        # 逐个校验（与 transmission_rpc 的批量解析一致）
        for tid in ids:
            self._parse(tid)  # 抛出即代表回归：传入了字符串数字 id
        self.calls.append(list(ids))


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


@pytest.fixture
def strict_tr_downloader():
    """Transmission 下载器，client 会真实校验 id 类型（复现 transmission_rpc._parse_torrent_id）。

    与 tr_downloader（MagicMock，不校验）的区别：若服务层漏转 int 而传入字符串数字 id，
    此 client 会抛 ValueError "is not valid torrent id"，使回归在 client 层失败。
    """
    dl = make_downloader(downloader_id="dl-tr", downloader_type=1, nickname="Transmission")
    dl.client = _TypeCheckingTransmissionClient()
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
        # transmission_rpc 要求 int 或 40 位 hex；本库 torrent_id 存为 text 形式的数字，
        # 服务层已转 int，故此处断言为整数 0
        assert ids[0] == 0
        assert isinstance(ids[0], int)

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


# ==================== 回归测试：Transmission torrent_id 必须转 int ====================

class TestTransmissionIdTypeRegression:
    """【回归】问题1：Transmission 分支必须把 torrent_id(text) 转成 int。

    根因：torrent_info.torrent_id 列存为 text 形式的数字（如 '103'），而 transmission_rpc 的
    _parse_torrent_id 只接受 int(>=0) 或 40 位 hex。直接传字符串数字会抛
    "torrent ids 103 is not valid torrent id, should be a hex str for sha1 hash"。

    本测试用 _TypeCheckingTransmissionClient（真实复现该校验）替代 MagicMock，
    让"漏转 int"的回归在 client 层即抛错，而非靠 isinstance 间接断言。
    """

    @pytest.mark.asyncio
    async def test_transmission_ids_are_int_not_str(self, mock_app, strict_tr_downloader):
        """少量种子：所有传给 client 的 id 必须是 int，不能是字符串数字。

        收敛点：若服务层把 _to_transmission_id 改回直接取 r.torrent_id（字符串 '0'..'9'），
        _TypeCheckingTransmissionClient 会抛 ValueError "is not valid torrent id"，测试报红。
        """
        mock_app.state.store.get_snapshot_sync.return_value = [strict_tr_downloader]
        torrents = make_torrents_batch(10, downloader_id="dl-tr")  # torrent_id="0".."9"

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app,
            downloader_id="dl-tr",
            torrent_records=torrents,
            trigger_type="manual",
        )

        # fake client 未抛异常 ⇒ 所有 id 都是合法 int
        assert result["success_count"] == 10
        assert result["failed_count"] == 0
        assert len(strict_tr_downloader.client.calls) == 1
        # 收敛锚点：每个 id 必须是 int（不是字符串数字）
        ids = strict_tr_downloader.client.calls[0]
        assert len(ids) == 10
        for tid in ids:
            assert isinstance(tid, int), "id 必须是 int（torrent_id 列存 text，需转换）"
            assert tid >= 0, "id 必须非负"

    @pytest.mark.asyncio
    async def test_transmission_batching_all_ids_valid(self, mock_app, strict_tr_downloader):
        """大批量分批：补强 test_transmission_batching_with_ids（原测试只查数量不查类型）。

        收敛点：750 个种子分 2 批，每批每个 id 都必须通过 fake client 的类型校验。
        若任一 id 是字符串数字，client 抛 ValueError，测试报红。
        """
        mock_app.state.store.get_snapshot_sync.return_value = [strict_tr_downloader]
        torrents = make_torrents_batch(750, downloader_id="dl-tr")

        from app.services.reannounce_service import execute_reannounce

        result = await execute_reannounce(
            app=mock_app,
            downloader_id="dl-tr",
            torrent_records=torrents,
            trigger_type="scheduled",
        )

        assert result["success_count"] == 750
        # 2 批，且 750 个 id 全部通过校验（fake client 未抛异常即证明）
        assert len(strict_tr_downloader.client.calls) == 2
        total = sum(len(c) for c in strict_tr_downloader.client.calls)
        assert total == 750
        for batch_ids in strict_tr_downloader.client.calls:
            assert all(isinstance(tid, int) for tid in batch_ids), \
                "每批所有 id 必须是 int（批量场景同样需转换）"
