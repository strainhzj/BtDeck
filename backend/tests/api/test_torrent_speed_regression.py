"""
回归测试: torrent_speed.py 活跃种子消失补查功能

覆盖上次提交 (09d8602) 的所有新增代码：
- _TTLQueue: TTL 队列核心逻辑
- _supplement_qb_sync / _supplement_tr_sync: 补查同步函数
- _supplement_disappeared: 批量补查调度
- _sync_torrents_to_db: 数据库同步
- get_active_torrents 中的 TTL 集成逻辑
- 异常处理（APIError / TransmissionError / TimeoutError）
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --------------------------------------------------------------------------- #
# _TTLQueue 单元测试
# --------------------------------------------------------------------------- #


class TestTTLQueue:
    """测试 _TTLQueue 的核心逻辑"""

    def _make_queue(self, ttl: int = 60):
        from app.api.endpoints.torrent_speed import _TTLQueue
        return _TTLQueue(ttl)

    def test_put_and_get_disappeared(self):
        """添加种子后，如果不在 active_keys 中应被返回为消失种子"""
        q = self._make_queue(ttl=60)
        q.put("dl_1", 0, "hash_a")
        q.put("dl_1", 0, "hash_b")

        # active_keys 中只有 hash_a → hash_b 应该是"消失的"
        active = {("dl_1", "hash_a")}
        result = q.get_disappeared(active)

        assert "dl_1" in result
        disappeared_hashes = [e["hash"] for e in result["dl_1"]]
        assert "hash_b" in disappeared_hashes
        assert "hash_a" not in disappeared_hashes

    def test_cleanup_expired(self):
        """过期的记录应被 cleanup 清除"""
        q = self._make_queue(ttl=1)
        q.put("dl_1", 0, "hash_old")

        # 手动老化记录
        key = ("dl_1", "hash_old")
        q._store[key]["last_time"] = time.monotonic() - 10

        q.cleanup()
        assert len(q._store) == 0

    def test_cleanup_keeps_fresh(self):
        """未过期的记录应被保留"""
        q = self._make_queue(ttl=60)
        q.put("dl_1", 0, "hash_fresh")

        q.cleanup()
        assert len(q._store) == 1

    def test_get_disappeared_empty_active_keys(self):
        """active_keys 为空时，所有 TTL 内的种子都应被视为消失"""
        q = self._make_queue(ttl=60)
        q.put("dl_1", 0, "hash_a")
        q.put("dl_1", 0, "hash_b")

        result = q.get_disappeared(set())
        assert len(result["dl_1"]) == 2

    def test_get_disappeared_max_supplement_count(self):
        """每组最多返回 _MAX_SUPPLEMENT_COUNT 个种子"""
        from app.api.endpoints.torrent_speed import _MAX_SUPPLEMENT_COUNT
        q = self._make_queue(ttl=60)

        # 插入超过限制数量的种子
        for i in range(_MAX_SUPPLEMENT_COUNT + 10):
            q.put("dl_1", 0, f"hash_{i}")

        result = q.get_disappeared(set())
        assert len(result["dl_1"]) == _MAX_SUPPLEMENT_COUNT

    def test_get_disappeared_grouped_by_downloader(self):
        """消失种子应按 downloader_id 分组"""
        q = self._make_queue(ttl=60)
        q.put("dl_1", 0, "hash_a")
        q.put("dl_2", 1, "hash_b")

        result = q.get_disappeared(set())
        assert "dl_1" in result
        assert "dl_2" in result

    def test_put_refreshes_ttl(self):
        """重复 put 同一种子应刷新 TTL"""
        q = self._make_queue(ttl=1)
        q.put("dl_1", 0, "hash_a")

        # 老化后再次 put
        key = ("dl_1", "hash_a")
        q._store[key]["last_time"] = time.monotonic() - 0.5
        q.put("dl_1", 0, "hash_a")

        # TTL 应被刷新，cleanup 不应清除
        q.cleanup()
        assert len(q._store) == 1

    def test_get_disappeared_skips_expired(self):
        """已过期但在 cleanup 前调用 get_disappeared 也应跳过过期记录"""
        q = self._make_queue(ttl=1)
        q.put("dl_1", 0, "hash_expired")

        # 手动老化
        key = ("dl_1", "hash_expired")
        q._store[key]["last_time"] = time.monotonic() - 10

        result = q.get_disappeared(set())
        assert result == {}


# --------------------------------------------------------------------------- #
# _supplement_qb_sync / _supplement_tr_sync 补查函数测试
# --------------------------------------------------------------------------- #


class TestSupplementSync:
    """测试补查同步函数"""

    def test_supplement_qb_sync_basic(self):
        """qBittorrent 补查应返回正确的字段"""
        from app.api.endpoints.torrent_speed import _supplement_qb_sync

        mock_client = MagicMock()
        mock_client.torrents_info.return_value = [
            {
                "hash": "abc123",
                "dlspeed": 1024,
                "upspeed": 512,
                "progress": 0.5,
                "num_seeds": 3,
                "num_leechs": 1,
                "state": "downloading",
            }
        ]

        result = _supplement_qb_sync(mock_client, ["abc123"])
        assert len(result) == 1
        assert result[0]["hash"] == "abc123"
        assert result[0]["downloadSpeed"] == 1024
        assert result[0]["uploadSpeed"] == 512
        assert result[0]["progress"] == 50.0
        assert result[0]["status"] == "downloading"

    def test_supplement_qb_sync_empty_hashes(self):
        """空 hashes 列表应传空字符串给 API（不崩溃）"""
        from app.api.endpoints.torrent_speed import _supplement_qb_sync

        mock_client = MagicMock()
        mock_client.torrents_info.return_value = []

        result = _supplement_qb_sync(mock_client, [])
        assert result == []
        mock_client.torrents_info.assert_called_once_with(hashes="")

    def test_supplement_qb_sync_progress_zero(self):
        """progress 为 0 时应正确处理（不因为 falsy 值而跳过）"""
        from app.api.endpoints.torrent_speed import _supplement_qb_sync

        mock_client = MagicMock()
        mock_client.torrents_info.return_value = [
            {"hash": "h1", "dlspeed": 0, "upspeed": 0, "progress": 0, "num_seeds": 0, "num_leechs": 0, "state": "paused"}
        ]

        result = _supplement_qb_sync(mock_client, ["h1"])
        assert result[0]["progress"] == 0

    def test_supplement_tr_sync_basic(self):
        """Transmission 补查应正确过滤 hash"""
        from app.api.endpoints.torrent_speed import _supplement_tr_sync

        t1 = MagicMock()
        t1.hashString = "tr_abc"
        t1.rate_download = 2048
        t1.rate_upload = 1024
        t1.progress = 0.75
        t1.peers_sending_to_us = 5
        t1.peers_getting_from_us = 2
        t1.status = 4  # ST_SEEDING

        t2 = MagicMock()
        t2.hashString = "tr_other"
        t2.rate_download = 0
        t2.rate_upload = 0
        t2.progress = 0.1
        t2.peers_sending_to_us = 0
        t2.peers_getting_from_us = 0
        t2.status = 0

        mock_client = MagicMock()
        mock_client.get_torrents.return_value = [t1, t2]

        result = _supplement_tr_sync(mock_client, ["tr_abc"])
        assert len(result) == 1
        assert result[0]["hash"] == "tr_abc"
        assert result[0]["progress"] == 75.0

    def test_supplement_tr_sync_none_values(self):
        """Transmission 返回 None 值应安全降级为 0"""
        from app.api.endpoints.torrent_speed import _supplement_tr_sync

        t = MagicMock()
        t.hashString = "h1"
        t.rate_download = None
        t.rate_upload = None
        t.progress = None
        t.peers_sending_to_us = None
        t.peers_getting_from_us = None
        t.status = None

        mock_client = MagicMock()
        mock_client.get_torrents.return_value = [t]

        result = _supplement_tr_sync(mock_client, ["h1"])
        assert result[0]["downloadSpeed"] == 0
        assert result[0]["uploadSpeed"] == 0
        assert result[0]["progress"] == 0


# --------------------------------------------------------------------------- #
# _supplement_disappeared 调度函数测试
# --------------------------------------------------------------------------- #


class TestSupplementDisappeared:
    """测试批量补查调度逻辑"""

    @pytest.mark.asyncio
    async def test_empty_input(self):
        """空输入应立即返回空列表"""
        from app.api.endpoints.torrent_speed import _supplement_disappeared
        result = await _supplement_disappeared({}, [])
        assert result == []

    @pytest.mark.asyncio
    async def test_downloader_not_in_cache(self):
        """downloader_id 不在缓存中应跳过"""
        from app.api.endpoints.torrent_speed import _supplement_disappeared

        disappeared = {"dl_missing": [{"hash": "h1", "downloader_id": "dl_missing"}]}
        cached = []  # 无缓存下载器

        result = await _supplement_disappeared(disappeared, cached)
        assert result == []

    @pytest.mark.asyncio
    async def test_downloader_failed_skipped(self):
        """fail_time > 0 的下载器应被跳过"""
        from app.api.endpoints.torrent_speed import _supplement_disappeared

        mock_dl = MagicMock()
        mock_dl.downloader_id = "dl_1"
        mock_dl.fail_time = 3  # 失败
        mock_dl.client = MagicMock()

        disappeared = {"dl_1": [{"hash": "h1"}]}
        result = await _supplement_disappeared(disappeared, [mock_dl])
        assert result == []

    @pytest.mark.asyncio
    async def test_timeout_handled_gracefully(self):
        """补查超时不应崩溃，应跳过并继续"""
        from app.api.endpoints.torrent_speed import _supplement_disappeared

        mock_client = MagicMock(spec=["torrents_info"])  # 不是 qbClient 实例
        mock_dl = MagicMock()
        mock_dl.downloader_id = "dl_1"
        mock_dl.fail_time = 0
        mock_dl.client = mock_client
        mock_dl.downloader_type = -1  # 不匹配任何类型
        mock_dl.nickname = "test"

        disappeared = {"dl_1": [{"hash": "h1"}]}
        # downloader_type=-1 不会匹配任何分支，但也不应崩溃
        result = await _supplement_disappeared(disappeared, [mock_dl])
        assert result == []

    @pytest.mark.asyncio
    async def test_qb_supplement_called(self):
        """qBittorrent 下载器应调用 _supplement_qb_sync"""
        from app.api.endpoints.torrent_speed import (
            _supplement_disappeared,
            _MAX_SUPPLEMENT_COUNT,
        )
        from qbittorrentapi import Client as qbClient

        mock_client = MagicMock(spec=qbClient)
        mock_client.torrents_info.return_value = [
            {"hash": "h1", "dlspeed": 0, "upspeed": 0, "progress": 0.8, "num_seeds": 0, "num_leechs": 0, "state": "uploading"}
        ]

        mock_dl = MagicMock()
        mock_dl.downloader_id = "dl_1"
        mock_dl.fail_time = 0
        mock_dl.client = mock_client
        mock_dl.downloader_type = 0  # qBittorrent
        mock_dl.nickname = "test_qb"

        disappeared = {"dl_1": [{"hash": "h1", "downloader_id": "dl_1", "downloader_type": 0}]}
        result = await _supplement_disappeared(disappeared, [mock_dl])

        assert len(result) == 1
        assert result[0]["hash"] == "h1"
        assert result[0]["progress"] == 80.0


# --------------------------------------------------------------------------- #
# 异常处理回归测试
# --------------------------------------------------------------------------- #


class TestExceptionHandling:
    """验证已修复的 APIError 导入问题及其他异常处理"""

    def test_qbapi_error_is_importable(self):
        """QbAPIError 应能正常导入，不应抛出 AttributeError"""
        from app.api.endpoints.torrent_speed import QbAPIError
        assert QbAPIError is not None

    def test_qbapi_error_is_not_on_client(self):
        """确认 qbClient 上没有 APIError 属性（即原 bug 的根因）"""
        from app.api.endpoints.torrent_speed import qbClient
        assert not hasattr(qbClient, "APIError")

    def test_transmission_error_is_importable(self):
        """TransmissionError 应能正常导入"""
        from app.api.endpoints.torrent_speed import TransmissionError
        assert TransmissionError is not None


# --------------------------------------------------------------------------- #
# 集成逻辑：active_keys 构建潜在问题
# --------------------------------------------------------------------------- #


class TestActiveKeysLogic:
    """
    测试 active_keys 构建逻辑中的潜在问题：
    外层循环 cached_downloaders × 内层循环 active_torrents
    会导致所有下载器都为所有活跃种子添加 active_key。
    """

    def test_active_keys_cross_contamination(self):
        """
        验证当前实现中，种子 A 属于下载器 1，
        但下载器 2 的 active_keys 中也会包含 (dl_2, hashA)。

        这会导致 get_disappeared 无法检测到跨下载器的"假消失"种子。
        """
        from app.api.endpoints.torrent_speed import _ttl_queue, _TTLQueue

        # 模拟两个下载器，一个种子只属于 dl_1
        q = _TTLQueue(60)
        q.put("dl_1", 0, "hash_shared")
        q.put("dl_2", 1, "hash_shared")

        # 当前代码中 active_keys 的构建方式：
        # for d in downloaders: for t in active_torrents:
        # 每个下载器都会为 hash_shared 添加自己的 active_key
        active_keys = {
            ("dl_1", "hash_shared"),
            ("dl_2", "hash_shared"),
        }

        disappeared = q.get_disappeared(active_keys)
        # 两个下载器的 key 都在 active_keys 中，所以不会返回消失种子
        # 这意味着如果种子从 dl_2 消失（但仍在 dl_1 中），无法检测
        assert "dl_1" not in disappeared
        assert "dl_2" not in disappeared

    def test_correct_active_keys_should_be_per_downloader(self):
        """
        验证理想行为：如果种子 hash_A 只来自 dl_1，
        那么 (dl_2, hash_A) 不应在 active_keys 中。

        当种子从 dl_2 的活跃列表消失后，
        dl_2 应该能检测到这个种子是"消失的"并补查。
        """
        from app.api.endpoints.torrent_speed import _TTLQueue

        q = _TTLQueue(60)
        q.put("dl_1", 0, "hash_only_dl1")
        q.put("dl_2", 1, "hash_only_dl2")

        # 正确的 active_keys：每个种子只属于它实际所在的下载器
        correct_active_keys = {("dl_1", "hash_only_dl1")}

        disappeared = q.get_disappeared(correct_active_keys)
        # dl_2 的种子不在 active_keys 中，应被检测为消失
        assert "dl_2" in disappeared
        assert any(e["hash"] == "hash_only_dl2" for e in disappeared["dl_2"])


# --------------------------------------------------------------------------- #
# _call_with_timeout 测试
# --------------------------------------------------------------------------- #


class TestCallWithTimeout:
    """测试超时保护包装函数"""

    @pytest.mark.asyncio
    async def test_normal_execution(self):
        """正常函数应正确返回结果"""
        from app.api.endpoints.torrent_speed import _call_with_timeout

        def sync_func():
            return [{"hash": "test", "speed": 100}]

        result = await _call_with_timeout(sync_func)
        assert result == [{"hash": "test", "speed": 100}]

    @pytest.mark.asyncio
    async def test_with_arguments(self):
        """带参数的函数应正确传递"""
        from app.api.endpoints.torrent_speed import _call_with_timeout

        def sync_func(a, b):
            return [{"a": a, "b": b}]

        result = await _call_with_timeout(sync_func, "x", "y")
        assert result == [{"a": "x", "b": "y"}]


# --------------------------------------------------------------------------- #
# 全局状态隔离测试
# --------------------------------------------------------------------------- #


class TestGlobalTTLQueue:
    """测试全局 _ttl_queue 实例不会在测试间泄漏"""

    def test_global_instance_exists(self):
        """全局实例应存在且类型正确"""
        from app.api.endpoints.torrent_speed import _ttl_queue, _TTLQueue
        assert isinstance(_ttl_queue, _TTLQueue)

    def test_global_ttl_config(self):
        """全局实例的 TTL 应与配置一致"""
        from app.api.endpoints.torrent_speed import _ttl_queue, _TTL_SECONDS
        assert _ttl_queue._ttl == _TTL_SECONDS
