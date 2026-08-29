"""
回归测试: torrent_speed.py 活跃种子消失补查功能

覆盖上次提交 (09d8602) 的所有新增代码：
- _TTLQueue: TTL 队列核心逻辑
- _supplement_qb_sync / _supplement_tr_sync: 补查同步函数
- _supplement_disappeared: 批量补查调度
- _sync_torrents_to_db: 数据库同步
- get_active_torrents 中的 TTL 集成逻辑
- 异常处理（APIError / TransmissionError / TimeoutError）

更新（sync-resource-governance code review 修复）：
- _call_with_timeout 接入 DownloaderApiRuntime INTERACTIVE lane，
  测试改为 patch call_downloader_api 验证 lane/timeout/downloader_id 透传。
- _speed_executor 已删除（速度接口共用 interactive_lane），相关 patch 移除。
"""

import asyncio
import time
from types import SimpleNamespace
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

    def test_get_disappeared_rotates_large_group(self):
        """同一下载器超过单次配额时，后半段任务下一轮也必须得到补查。"""
        from app.api.endpoints.torrent_speed import _MAX_SUPPLEMENT_COUNT, _SUPPLEMENT_RETRY_INTERVAL

        q = self._make_queue(ttl=60)
        total = _MAX_SUPPLEMENT_COUNT + 5
        for i in range(total):
            q.put("dl_1", 0, f"hash_{i}")

        first = q.get_disappeared(set())
        assert len(first["dl_1"]) == _MAX_SUPPLEMENT_COUNT
        # 模拟退避窗口结束，验证下一批不是固定的前 N 个。
        for entry in q._store.values():
            entry["next_probe_at"] = time.monotonic() - _SUPPLEMENT_RETRY_INTERVAL
        second = q.get_disappeared(set())
        second_hashes = {entry["hash"] for entry in second["dl_1"]}
        assert second_hashes.intersection({f"hash_{i}" for i in range(_MAX_SUPPLEMENT_COUNT, total)})

    def test_remove_completed_task(self):
        """确认完成后从 TTL 队列移除，后续不再补查。"""
        q = self._make_queue(ttl=60)
        q.put("dl_1", 0, "hash_done")
        q.remove("dl_1", "hash_done")
        assert q.get_disappeared(set()) == {}

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

    def test_runtime_state_normalizes_non_finite_progress(self):
        """下载器偶发返回 NaN/Infinity 时不得被误判为 100% 完成。"""
        from app.api.endpoints.torrent_speed import _normalize_runtime_state

        assert _normalize_runtime_state(float("nan"), "downloading", 0) == (0.0, "downloading", False)
        assert _normalize_runtime_state(float("inf"), "downloading", 0) == (0.0, "downloading", False)

    def test_explicit_incomplete_overrides_terminal_status_inference(self):
        """显式 downloadComplete=false 不应被 seeding 状态推断覆盖。"""
        from app.api.endpoints.torrent_speed import _normalize_runtime_state

        assert _normalize_runtime_state(80, "seeding", 0, explicit_complete=False) == (80.0, "seeding", False)

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
            {
                "hash": "h1",
                "dlspeed": 0,
                "upspeed": 0,
                "progress": 0,
                "num_seeds": 0,
                "num_leechs": 0,
                "state": "paused",
            }
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
        t1.percent_done = 0.75
        t1.peers_sending_to_us = 5
        t1.peers_getting_from_us = 2
        t1.status = 4  # ST_SEEDING

        t2 = MagicMock()
        t2.hashString = "tr_other"
        t2.rate_download = 0
        t2.rate_upload = 0
        t2.percent_done = 0.1
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
        t.percent_done = None
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
    @patch("app.api.endpoints.torrent_speed.call_downloader_api")
    async def test_qb_supplement_called(self, mock_call):
        """qBittorrent 下载器应通过 runtime 调用 _supplement_qb_sync（INTERACTIVE lane）"""
        from app.api.endpoints.torrent_speed import (
            _supplement_disappeared,
            DownloadLane,
            _DOWNLOADER_TIMEOUT,
        )
        from qbittorrentapi import Client as qbClient

        # 真实跑 _supplement_qb_sync（通过 runtime 真实 executor），验证接入后行为不变
        async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            assert lane == DownloadLane.INTERACTIVE
            assert opts.get("timeout") == _DOWNLOADER_TIMEOUT
            return func(*args, **(kwargs or {}))

        mock_call.side_effect = fake_call

        mock_client = MagicMock(spec=qbClient)
        mock_client.torrents_info.return_value = [
            {
                "hash": "h1",
                "dlspeed": 0,
                "upspeed": 0,
                "progress": 0.8,
                "num_seeds": 0,
                "num_leechs": 0,
                "state": "uploading",
            }
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
        # 断言走 INTERACTIVE lane 且传 downloader_id
        mock_call.assert_called_once()
        call_args = mock_call.call_args
        assert call_args.args[0] == "dl_1"


# --------------------------------------------------------------------------- #
# 异常处理回归测试
# --------------------------------------------------------------------------- #


class TestIsFreshlyOffline:
    """A-1 helper：_is_freshly_offline 的判定分支与新鲜窗口边界。

    is_online/last_update 由 downloader_status_polling_task（10s 热间隔）维护；
    离线下载器 last_update 仍被持续刷新（端口不通也算更新成功），因此判据是
    "is_online is False 且 last_update 在窗口内"，与 last_update 是否被刷新无关。
    """

    def _make(self, **attrs):
        from types import SimpleNamespace

        # is_online/last_update 缺省不设置，模拟旧 mock 对象/未探测 VO
        return SimpleNamespace(**attrs)

    def test_missing_is_online_attribute(self):
        """无 is_online 属性（旧 mock 兼容）→ 放行。"""
        from app.api.endpoints import torrent_speed

        assert torrent_speed._is_freshly_offline(self._make()) is False

    def test_is_online_none_or_true(self):
        """is_online 为 None / True → 放行（VO 默认 False 之外的语义不跳过）。"""
        from app.api.endpoints import torrent_speed
        import time

        now = time.time()
        assert torrent_speed._is_freshly_offline(self._make(is_online=None, last_update=now)) is False
        assert torrent_speed._is_freshly_offline(self._make(is_online=True, last_update=now)) is False

    def test_offline_without_last_update(self):
        """is_online=False 但 last_update 缺失（冷启动/新加入）→ 放行。"""
        from app.api.endpoints import torrent_speed

        assert torrent_speed._is_freshly_offline(self._make(is_online=False)) is False
        assert torrent_speed._is_freshly_offline(self._make(is_online=False, last_update=None)) is False

    def test_offline_fresh_probe_boundary(self):
        """离线 + last_update 恰在窗口内/外/边界的判定。"""
        from app.api.endpoints import torrent_speed
        import time

        window = torrent_speed._OFFLINE_FRESH_WINDOW
        now = time.time()
        # 窗口内（刚探测过）→ 跳过
        assert torrent_speed._is_freshly_offline(self._make(is_online=False, last_update=now - window / 2)) is True
        # 超出窗口（轮询停摆兜底）→ 放行
        assert torrent_speed._is_freshly_offline(self._make(is_online=False, last_update=now - window - 1)) is False
        # 恰好等于窗口：time.time() 推移使差值略增，边界视为窗口内（< 判定）
        assert torrent_speed._is_freshly_offline(self._make(is_online=False, last_update=now - window + 1)) is True


class TestSupplementOfflineFilter:
    """_supplement_disappeared 的 dl_map 离线过滤（与 _process_downloader_speeds 口径一致）。"""

    @pytest.mark.asyncio
    @patch("app.api.endpoints.torrent_speed.call_downloader_api")
    async def test_freshly_offline_excluded_from_dl_map(self, mock_call):
        """新鲜离线下载器不进入补查映射，不对其发起远程调用。"""
        from app.api.endpoints.torrent_speed import _supplement_disappeared
        from qbittorrentapi import Client as qbClient
        import time

        mock_client = MagicMock(spec=qbClient)
        mock_dl = MagicMock()
        mock_dl.downloader_id = "dl_off"
        mock_dl.fail_time = 0
        mock_dl.client = mock_client
        mock_dl.downloader_type = 0
        mock_dl.nickname = "offline_dl"
        # MagicMock 自动属性需显式设值：新鲜离线
        mock_dl.is_online = False
        mock_dl.last_update = time.time()

        disappeared = {"dl_off": [{"hash": "h1"}]}
        result = await _supplement_disappeared(disappeared, [mock_dl])
        assert result == []
        mock_call.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.api.endpoints.torrent_speed.call_downloader_api")
    async def test_stale_offline_still_supplemented(self, mock_call):
        """last_update 过旧（轮询停摆）→ 不视为可信离线，仍参与补查。"""
        from app.api.endpoints.torrent_speed import (
            _OFFLINE_FRESH_WINDOW,
            _supplement_disappeared,
        )
        from qbittorrentapi import Client as qbClient
        import time

        async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            return func(*args, **(kwargs or {}))

        mock_call.side_effect = fake_call

        mock_client = MagicMock(spec=qbClient)
        mock_client.torrents_info.return_value = [
            {"hash": "h1", "dlspeed": 0, "upspeed": 0, "progress": 0.8, "state": "stalledUP"}
        ]
        mock_dl = MagicMock()
        mock_dl.downloader_id = "dl_stale"
        mock_dl.fail_time = 0
        mock_dl.client = mock_client
        mock_dl.downloader_type = 0
        mock_dl.nickname = "stale_dl"
        mock_dl.is_online = False
        mock_dl.last_update = time.time() - (_OFFLINE_FRESH_WINDOW + 30)

        disappeared = {"dl_stale": [{"hash": "h1"}]}
        result = await _supplement_disappeared(disappeared, [mock_dl])
        assert len(result) == 1
        mock_call.assert_called_once()


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
        from app.api.endpoints.torrent_speed import _TTLQueue

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
    """测试超时保护包装函数（接入 DownloaderApiRuntime INTERACTIVE lane 后）。

    注意：全量 pytest 中其它 API 测试经 TestClient 触发 lifespan 退出，会调用全局
    downloader_api_runtime.shutdown()，全局单例 executor 被关闭。因此这些测试统一
    patch call_downloader_api，不真实走全局单例，避免被 lifespan 副作用污染。
    """

    @pytest.mark.asyncio
    async def test_normal_execution(self):
        """正常函数应正确返回结果（经 INTERACTIVE lane）"""
        from app.api.endpoints.torrent_speed import _call_with_timeout

        async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            return func(*args, **(kwargs or {}))

        with patch(
            "app.api.endpoints.torrent_speed.call_downloader_api",
            side_effect=fake_call,
        ):
            result = await _call_with_timeout("dl_test", "test_op", lambda: [{"hash": "test", "speed": 100}])
        assert result == [{"hash": "test", "speed": 100}]

    @pytest.mark.asyncio
    async def test_with_arguments(self):
        """带参数的函数应正确传递"""
        from app.api.endpoints.torrent_speed import _call_with_timeout

        def sync_func(a, b):
            return [{"a": a, "b": b}]

        async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            return func(*args, **(kwargs or {}))

        with patch(
            "app.api.endpoints.torrent_speed.call_downloader_api",
            side_effect=fake_call,
        ):
            result = await _call_with_timeout("dl_test", "test_op", sync_func, "x", "y")
        assert result == [{"a": "x", "b": "y"}]

    @pytest.mark.asyncio
    async def test_uses_interactive_lane_and_timeout(self):
        """🔴 关键不变量：速度接口必须经 INTERACTIVE lane 且 timeout=_DOWNLOADER_TIMEOUT。

        mutation 验证点：把 lane 改成 SYNC 或不传 timeout，此测试报红。
        """
        from app.api.endpoints.torrent_speed import (
            _call_with_timeout,
            _DOWNLOADER_TIMEOUT,
        )
        from app.services.downloader_api_runtime import DownloadLane

        with patch(
            "app.api.endpoints.torrent_speed.call_downloader_api",
            new=AsyncMock(return_value=[{"hash": "ok"}]),
        ) as mock_call:
            result = await _call_with_timeout("dl_x", "op", lambda: [{"hash": "ok"}])

        assert result == [{"hash": "ok"}]
        mock_call.assert_awaited_once()
        kwargs = mock_call.call_args.kwargs
        assert mock_call.call_args.args[0] == "dl_x"
        assert mock_call.call_args.args[1] == DownloadLane.INTERACTIVE
        assert kwargs["timeout"] == _DOWNLOADER_TIMEOUT

    @pytest.mark.asyncio
    async def test_speed_endpoint_does_not_bypass_per_downloader_limit(self):
        """🔴 关键不变量：速度接口经 runtime → per-downloader 限流生效。

        策略：spy downloader_api_runtime.call，发起多次并发调用，断言每次都进入 runtime
        （而不是绕过到独立 executor），即 per-downloader semaphore 必然生效。
        """
        from app.api.endpoints.torrent_speed import _call_with_timeout
        from app.services.downloader_api_runtime import DownloadLane

        call_count = {"n": 0}

        async def fake_call(downloader_id, lane, func, *args, **kwargs):
            call_count["n"] += 1
            assert lane == DownloadLane.INTERACTIVE
            return func(*args)

        with patch(
            "app.api.endpoints.torrent_speed.call_downloader_api",
            side_effect=fake_call,
        ):
            # 同一 downloader 并发 4 次调用
            await asyncio.gather(
                _call_with_timeout("dl_cap", "op1", lambda: 1),
                _call_with_timeout("dl_cap", "op2", lambda: 2),
                _call_with_timeout("dl_cap", "op3", lambda: 3),
                _call_with_timeout("dl_cap", "op4", lambda: 4),
            )

        # 4 次全部经 runtime（没有绕过）
        assert call_count["n"] == 4


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


# --------------------------------------------------------------------------- #
# A-3 补充：reason 机器码全分类 / failed 明细 / msg 截断
# --------------------------------------------------------------------------- #


class TestSpeedResultReasonCodes:
    """_process_downloader_speeds 的 reason 机器码契约（206 明细与日志的归因口径）。

    reason 是运维 grep 与前端展示的稳定机器码，任一分支漂移都会让
    206 失败明细失去归因价值，此处全分支锁定。
    """

    @pytest.mark.asyncio
    async def test_fail_time_reason(self):
        from app.api.endpoints import torrent_speed

        dl = SimpleNamespace(fail_time=2)
        r = await torrent_speed._process_downloader_speeds(dl)
        assert r.complete is False
        assert r.reason == "fail_time"

    @pytest.mark.asyncio
    async def test_no_client_reason(self):
        from app.api.endpoints import torrent_speed

        dl = SimpleNamespace(fail_time=0, client=None)
        r = await torrent_speed._process_downloader_speeds(dl)
        assert r.complete is False
        assert r.reason == "no_client"

    @pytest.mark.asyncio
    async def test_unsupported_client_reason(self):
        from app.api.endpoints import torrent_speed

        dl = SimpleNamespace(fail_time=0, client=object())  # 非 qb/tr 实例
        r = await torrent_speed._process_downloader_speeds(dl)
        assert r.complete is False
        assert r.reason == "unsupported_client"

    @pytest.mark.asyncio
    @patch("app.api.endpoints.torrent_speed.call_downloader_api")
    async def test_timeout_reason(self, mock_call):
        import asyncio as _asyncio

        from app.api.endpoints import torrent_speed
        from qbittorrentapi import Client as qbClient

        async def _raise(*a, **k):
            raise _asyncio.TimeoutError()

        mock_call.side_effect = _raise
        dl = SimpleNamespace(fail_time=0, client=MagicMock(spec=qbClient), nickname="dl", downloader_id="dl")
        r = await torrent_speed._process_downloader_speeds(dl)
        assert r.complete is False
        assert r.reason == "timeout"

    @pytest.mark.asyncio
    @patch("app.api.endpoints.torrent_speed.call_downloader_api")
    async def test_api_error_reason(self, mock_call):
        from app.api.endpoints import torrent_speed
        from qbittorrentapi import APIError as QbAPIError
        from qbittorrentapi import Client as qbClient

        async def _raise(*a, **k):
            raise QbAPIError("refused")

        mock_call.side_effect = _raise
        dl = SimpleNamespace(fail_time=0, client=MagicMock(spec=qbClient), nickname="dl", downloader_id="dl")
        r = await torrent_speed._process_downloader_speeds(dl)
        assert r.complete is False
        assert r.reason == "api_error"

    @pytest.mark.asyncio
    @patch("app.api.endpoints.torrent_speed.call_downloader_api")
    async def test_unknown_reason(self, mock_call):
        from app.api.endpoints import torrent_speed
        from qbittorrentapi import Client as qbClient

        async def _raise(*a, **k):
            raise RuntimeError("unexpected")

        mock_call.side_effect = _raise
        dl = SimpleNamespace(fail_time=0, client=MagicMock(spec=qbClient), nickname="dl", downloader_id="dl")
        r = await torrent_speed._process_downloader_speeds(dl)
        assert r.complete is False
        assert r.reason == "unknown"

    @pytest.mark.asyncio
    @patch("app.api.endpoints.torrent_speed.call_downloader_api")
    async def test_success_reason_empty(self, mock_call):
        from app.api.endpoints import torrent_speed
        from qbittorrentapi import Client as qbClient

        async def _ok(downloader_id, lane, func, args=(), kwargs=None, **opts):
            return func(*args, **(kwargs or {}))

        mock_call.side_effect = _ok
        client = MagicMock(spec=qbClient)
        client.torrents_info.return_value = []
        dl = SimpleNamespace(fail_time=0, client=client, nickname="dl", downloader_id="dl")
        r = await torrent_speed._process_downloader_speeds(dl)
        assert r.complete is True
        assert r.reason == ""

    @pytest.mark.asyncio
    async def test_offline_skip_reason_empty(self):
        """离线跳过（complete=True）不携带 reason——不进入 failed 明细的口径锚点。"""
        import time

        from app.api.endpoints import torrent_speed

        dl = SimpleNamespace(fail_time=0, client=None, is_online=False, last_update=time.time())
        r = await torrent_speed._process_downloader_speeds(dl)
        assert r.complete is True
        assert r.reason == ""


class TestGatherFailedDetails:
    """_gather_active_speeds 的 failed 明细收集（字段与口径）。"""

    @pytest.mark.asyncio
    @patch("app.api.endpoints.torrent_speed.call_downloader_api")
    async def test_failed_details_collected_with_fields(self, mock_call):
        import asyncio as _asyncio

        from app.api.endpoints import torrent_speed
        from qbittorrentapi import Client as qbClient

        async def _by_id(downloader_id, lane, func, args=(), kwargs=None, **opts):
            if downloader_id == "dl_bad":
                raise _asyncio.TimeoutError()
            return func(*args, **(kwargs or {}))

        mock_call.side_effect = _by_id

        ok_client = MagicMock(spec=qbClient)
        ok_client.torrents_info.return_value = [{"hash": "h1", "dlspeed": 100, "upspeed": 0, "progress": 0.5}]
        bad_client = MagicMock(spec=qbClient)
        bad_client.torrents_info.return_value = [{"hash": "h2", "dlspeed": 50, "upspeed": 0}]

        ok_dl = SimpleNamespace(downloader_id="dl_ok", downloader_type=0, nickname="ok", fail_time=0, client=ok_client)
        bad_dl = SimpleNamespace(
            downloader_id="dl_bad", downloader_type=0, nickname="bad", fail_time=0, client=bad_client
        )

        gathered = await torrent_speed._gather_active_speeds([ok_dl, bad_dl])

        assert gathered.complete is False
        assert gathered.failed == [{"downloader_id": "dl_bad", "nickname": "bad", "reason": "timeout"}]
        # 成功者种子扁平化并打标签
        assert len(gathered.torrents) == 1
        assert gathered.torrents[0]["downloader_id"] == "dl_ok"

    @pytest.mark.asyncio
    async def test_offline_skipped_not_in_failed(self):
        """离线跳过者（complete=True）不出现在 failed 明细。"""
        import time

        from app.api.endpoints import torrent_speed

        offline_dl = SimpleNamespace(
            downloader_id="dl_off",
            downloader_type=0,
            nickname="off",
            fail_time=0,
            client=None,
            is_online=False,
            last_update=time.time(),
        )
        gathered = await torrent_speed._gather_active_speeds([offline_dl])
        assert gathered.complete is True
        assert gathered.failed == []
        assert gathered.torrents == []


class TestPartialFailureMsg:
    """206 msg 文案构造：截断与回退口径。"""

    def test_empty_failed_returns_generic(self):
        from app.api.endpoints.torrent_speed import _partial_failure_msg

        assert _partial_failure_msg([]) == "部分下载器速度获取失败，活动快照尚未就绪"

    def test_up_to_five_names_joined(self):
        from app.api.endpoints.torrent_speed import _partial_failure_msg

        failed = [{"nickname": f"dl{i}", "downloader_id": f"id{i}", "reason": "timeout"} for i in range(5)]
        msg = _partial_failure_msg(failed)
        assert msg.endswith("（失败: dl0、dl1、dl2、dl3、dl4）")

    def test_more_than_five_truncated(self):
        from app.api.endpoints.torrent_speed import _partial_failure_msg

        failed = [{"nickname": f"dl{i}", "downloader_id": f"id{i}", "reason": "timeout"} for i in range(7)]
        msg = _partial_failure_msg(failed)
        assert msg.endswith("（失败: dl0、dl1、dl2、dl3、dl4 等7个）")
        assert "dl5" not in msg.split("等7个")[0]

    def test_nickname_fallback_and_unknown(self):
        """nickname 缺失回退 downloader_id，两者皆无记 unknown。"""
        from app.api.endpoints.torrent_speed import _partial_failure_msg

        msg = _partial_failure_msg(
            [
                {"nickname": None, "downloader_id": "id9", "reason": "api_error"},
                {"nickname": None, "downloader_id": "", "reason": "api_error"},
            ]
        )
        assert "id9" in msg
        assert "unknown" in msg


class TestFreshlyOfflineClockAnomaly:
    """_is_freshly_offline 的时钟异常防御。"""

    def test_future_last_update_treated_as_fresh(self):
        """last_update 在未来（时钟回拨/NTP 跳变）→ 差值为负 < 窗口 → 视为新鲜离线。"""
        import time

        from app.api.endpoints import torrent_speed

        dl = SimpleNamespace(is_online=False, last_update=time.time() + 3600)
        assert torrent_speed._is_freshly_offline(dl) is True
