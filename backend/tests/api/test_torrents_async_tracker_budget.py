# -*- coding: utf-8 -*-
"""
qB Tracker 有界队列与单轮预算测试（W3-1 第一部分 + 第二部分）

【覆盖目标 · W3-1 第一部分（有界队列与单轮预算）】
1. 10k hash + worker_count=2：活跃 asyncio 任务数 ≤ 4（生产者 1 + worker 2 + 当前协程），
   禁止一次性为全部 hash 创建任务对象。
2. 数量预算：QB_TRACKER_MAX_TORRENTS_PER_RUN 到期 → 远程调用数 ≤ 上限且
   budget_reason=count。
3. 时间预算：QB_TRACKER_RUN_BUDGET_SECONDS 到期 → budget_reason=time。
4. 预算到期快速返回：总耗时远小于全量处理耗时。
5. 无预算限制时全量处理，成功/失败计数与旧信号量实现语义一致。
6. 单调用超时透传 QB_TRACKER_PER_CALL_TIMEOUT（_fetch_single_trackers 传入 timeout）。

【覆盖目标 · W3-1 第二部分（持久化 cursor 续跑 + cycle 语义 + Coordinator 预算接线）】
7. 重启续跑：第一轮预算到期 partial（检查点保存 cursor）→ 第二轮从 cursor 继续，
   第二轮处理的 hash 集合 = 第一轮未处理部分（无重复、无遗漏）。
8. 第 N 批失败 cursor 停驻：mock flush 第 N 次抛异常 → checkpoint cursor 停在
   最后成功批（未越过失败批）；重试从该处续跑。
9. cycle complete：全部处理完且全部批 commit 成功 → last_full_sync_at 更新 +
   cursor 清空（下一轮从头开始新周期）。
10. 稳定排序：hash 乱序输入 → 处理顺序为字典序（续跑游标依赖）。
11. Coordinator 预算透传：SyncRequest.deadline/record_budget 传给 qB tracker
    单轮预算；缺省（手动/定时共用）回落 settings 默认。
12. producer 哨兵在队列满时重试，且所有哨兵丢失时 worker 仍能轮询自愈退出。
13. enrich 被取消后 producer/worker 不遗留后台任务。

设计依据：
- asyncio_mode=auto（pytest.ini），异步测试直接 async def。
- 直接调用 _enrich_qb_torrents_with_trackers / qb_sync_trackers_only_async，
  客户端用 MagicMock（参照 tests/services/conftest.py 的 fake client 样板）。
- call_downloader_api 全部替换为直调 fake，不依赖进程级 downloader_api_runtime 单例：
  tests 全量运行时，其他测试文件（如 test_tag_aggregation_api）的 TestClient(app)
  会在 lifespan 退出时对单例执行 shutdown()（app/startup/lifecycle.py），此后
  run_in_executor 会抛 RuntimeError。本文件只测队列/预算/续跑逻辑，与真实 runtime
  解耦（runtime 自身有专门测试 tests/services/test_downloader_api_runtime.py）。
- 预算结果从 [QB_TRACKER_ENRICH] Completed 日志读取（函数签名/返回结构不变）。
- 第二部分检查点用例通过 set_checkpoint_store 注入内存库（aiosqlite + StaticPool），
  直接登记运行期检查点上下文（_ACTIVE_CHECKPOINTS）模拟 Coordinator 运行中；
  部分用例走 run_sync 集成（Coordinator 终态清空 cursor / last_full_sync_at）。
"""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.endpoints import torrents_async
from app.core.config import settings
from app.database import Base
from app.downloader.models import BtDownloaders
from app.models.sync_checkpoint import SyncCheckpoint
from app.services import sync_coordinator as sc_module
from app.services.sync_coordinator import SyncCheckpointStore, SyncRequest, run_sync
from app.tasks.resource_guard import admission_controller


def _make_torrent_infos(count, prefix="h"):
    """构造 count 个含 hash 字段的伪种子对象（SimpleNamespace 兼容 _qb_get_attr）。"""
    return [SimpleNamespace(hash=f"{prefix}{i:06d}") for i in range(count)]


@pytest.fixture(autouse=True)
def isolate_call_downloader_api():
    """把 torrents_async.call_downloader_api 替换为直调 fake（不经 runtime 单例）。

    详见模块 docstring 的隔离原因：全量套件中 TestClient(app) 的 lifespan 退出
    会 shutdown 进程级 runtime 单例的 executor，导致后续真实调用全部失败。
    fake 在事件循环内直接调用 func，等价于"executor 已就绪"的最小语义。
    """

    async def fake_call_downloader_api(downloader_id, lane, func, args=(), kwargs=None, timeout=None, operation=""):
        return func(*args, **(kwargs or {}))

    with patch.object(torrents_async, "call_downloader_api", new=fake_call_downloader_api):
        yield


@pytest.fixture
def fake_client():
    """模拟 qBittorrent 客户端：torrents_trackers 返回空 tracker 列表。"""
    client = MagicMock()
    client.torrents_trackers = MagicMock(return_value=[])
    return client


def _completion_log(mock_info):
    """从 patch 的 logger.info 调用列表中提取 Completed 日志文本。"""
    hits = [str(c) for c in mock_info.call_args_list if "Completed enrichment" in str(c)]
    assert hits, "未捕获 [QB_TRACKER_ENRICH] Completed 日志"
    return hits[-1]


async def test_10k_hashes_active_tasks_bounded(fake_client, monkeypatch):
    """10k hash + worker_count=2：拉取期间活跃 asyncio 任务数 ≤ 4。"""
    monkeypatch.setattr(settings, "QB_TRACKER_WORKER_COUNT", 2)
    monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 10**7)
    monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 600.0)

    infos = _make_torrent_infos(10000)
    baseline = len(asyncio.all_tasks())
    max_seen = {"value": baseline}

    fake = torrents_async.call_downloader_api  # 当前生效的直调 fake（autouse fixture）

    async def counting_wrapper(*args, **kwargs):
        # 每次拉取时在事件循环内采样活跃任务数（worker 拉取期间记录）
        max_seen["value"] = max(max_seen["value"], len(asyncio.all_tasks()))
        return await fake(*args, **kwargs)

    with patch.object(torrents_async, "call_downloader_api", new=counting_wrapper):
        await torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_1")

    # 活跃任务数 = 当前协程 + 生产者(1) + worker(2)，恒 ≤ 4，不随 hash 总量增长
    assert max_seen["value"] <= 4
    assert max_seen["value"] - baseline <= 3
    # 无预算限制：全量拉取并写回
    assert fake_client.torrents_trackers.call_count == 10000
    assert all(t.trackers == [] for t in infos)


async def test_count_budget_stops_remote_calls(fake_client, monkeypatch):
    """数量预算：QB_TRACKER_MAX_TORRENTS_PER_RUN=500 → 远程调用 ≤ 500 且 budget_reason=count。"""
    monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 500)
    monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 600.0)

    infos = _make_torrent_infos(5000)
    with patch.object(torrents_async.logger, "info") as mock_info:
        await torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_1")

    call_count = fake_client.torrents_trackers.call_count
    assert call_count <= 500
    assert call_count < len(infos)  # 未全量处理，提前停止消费
    text = _completion_log(mock_info)
    assert "budget_reason: count" in text
    assert "processed_this_run: 500" in text


async def test_time_budget_stops(fake_client, monkeypatch):
    """时间预算：每次调用 sleep 0.05s + 预算 0.1s → budget_reason=time 且未全量处理。"""
    monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 10**6)
    monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 0.1)

    def slow_fetch(*args, **kwargs):
        time.sleep(0.05)
        return []

    fake_client.torrents_trackers.side_effect = slow_fetch
    infos = _make_torrent_infos(100)
    with patch.object(torrents_async.logger, "info") as mock_info:
        await torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_1")

    assert fake_client.torrents_trackers.call_count < len(infos)
    text = _completion_log(mock_info)
    assert "budget_reason: time" in text


async def test_budget_expiry_returns_quickly(fake_client, monkeypatch):
    """预算到期快速返回：总耗时远小于全量处理耗时（全量约 10s，预算内应 < 3s）。"""
    monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 10**6)
    monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 0.05)

    def slow_fetch(*args, **kwargs):
        time.sleep(0.01)
        return []

    fake_client.torrents_trackers.side_effect = slow_fetch
    infos = _make_torrent_infos(1000)  # 全量 1000 × 0.01s ≈ 10s

    start = time.monotonic()
    await torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_1")
    elapsed = time.monotonic() - start

    assert fake_client.torrents_trackers.call_count < len(infos)
    assert elapsed < 3.0, f"预算到期未快速返回，耗时 {elapsed:.2f}s"


async def test_no_budget_full_processing(fake_client, monkeypatch):
    """无预算限制（数量上限调大 + 时间预算 0=不限时）：全量处理且计数与旧语义一致。"""
    monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 10**7)
    monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 0.0)

    infos = _make_torrent_infos(500)
    with patch.object(torrents_async.logger, "info") as mock_info:
        await torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_1")

    assert fake_client.torrents_trackers.call_count == 500
    assert all(t.trackers == [] for t in infos)  # 成功写回内存对象
    text = _completion_log(mock_info)
    assert "budget_reason: None" in text
    assert "500 succeeded" in text
    assert "0 failed" in text
    assert "processed_this_run: 500" in text


async def test_per_call_timeout_passed_to_runtime(fake_client, monkeypatch):
    """单调用超时透传：_fetch_single_trackers 调用 call_downloader_api 时携带
    QB_TRACKER_PER_CALL_TIMEOUT 值。"""
    monkeypatch.setattr(settings, "QB_TRACKER_PER_CALL_TIMEOUT", 7.5)

    captured = {}

    fake = torrents_async.call_downloader_api  # 当前生效的直调 fake（autouse fixture）

    async def capturing_wrapper(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return await fake(*args, **kwargs)

    infos = _make_torrent_infos(10)
    with patch.object(torrents_async, "call_downloader_api", new=capturing_wrapper):
        await torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_1")

    assert captured.get("timeout") == 7.5


# =============================================================================
# W3-1 第二部分：持久化 cursor 续跑 + cycle 语义 + Coordinator 预算接线
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_admission_and_checkpoint_state():
    """每个测试前后清理 admission 与检查点进程级状态（防跨测试泄漏）。

    run_sync 集成用例（本部分新增）依赖 admission_controller 单例复位与
    _ACTIVE_CHECKPOINTS / 全局 store 清理；对既有 W3-1a 用例零副作用。
    """
    admission_controller.reset_state()
    sc_module._ACTIVE_CHECKPOINTS.clear()
    sc_module.set_checkpoint_store(None)
    yield
    admission_controller.reset_state()
    sc_module._ACTIVE_CHECKPOINTS.clear()
    sc_module.set_checkpoint_store(None)


@pytest.fixture
async def checkpoint_env():
    """独立内存库（aiosqlite + StaticPool）：sync_checkpoints 表 + 绑定 store。

    同时把全局 _CHECKPOINT_STORE 换成本 store（Coordinator 集成用例用）；
    测试结束恢复默认实现并释放引擎。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[SyncCheckpoint.__table__]))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    store = SyncCheckpointStore(session_factory=lambda: Session())
    sc_module.set_checkpoint_store(store)
    env = SimpleNamespace(store=store, session_factory=Session, engine=engine)
    try:
        yield env
    finally:
        sc_module.set_checkpoint_store(None)
        await engine.dispose()


def make_vo(downloader_id="dl_001", client=None, fail_time=0, downloader_type=0, nickname="test-dl"):
    """构造伪下载器 VO（app.state.store.get_snapshot() 返回的元素）。"""
    vo = SimpleNamespace()
    vo.downloader_id = downloader_id
    vo.client = client
    vo.fail_time = fail_time
    vo.downloader_type = downloader_type
    vo.nickname = nickname
    vo.host = "192.168.1.1"
    vo.port = 8080
    vo.username = "admin"
    vo.password = "password"
    vo.torrent_save_path = "/downloads"
    return vo


def make_fake_app(vos=None):
    """构造带 store 的伪 FastAPI 实例（run_sync 集成用例用）。"""
    store = SimpleNamespace()
    store.get_snapshot = AsyncMock(return_value=vos or [])
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    app.state.store = store
    return app


def _tracker_payload(torrent_hash):
    """单个种子的 tracker 拉取结果（fake_client.torrents_trackers side_effect）。"""
    return [{"url": f"http://{torrent_hash}.example.com/announce", "status": 1, "msg": "ok"}]


async def _seed_active_checkpoint(store, downloader_id="dl_1", sync_type="tracker"):
    """登记运行期检查点上下文（模拟 Coordinator 运行中），供 push_sync_progress 落库。"""
    row = await store.get_or_create(downloader_id, sync_type)
    sc_module._ACTIVE_CHECKPOINTS[f"{downloader_id}:{sync_type}"] = row
    return row


def _qb_tracker_client(torrents):
    """构造带 torrents_info 列表与按 hash 拉取 tracker 的伪 qB 客户端。"""
    client = MagicMock()
    client.torrents_info = MagicMock(return_value=torrents)
    client.torrents_trackers = MagicMock(side_effect=_tracker_payload)
    return client


class TestQbTrackerCursorResume:
    """重启续跑：第一轮预算到期 partial（检查点保存 cursor）→ 第二轮从 cursor 继续。"""

    async def test_budget_expiry_cursor_resume_no_dup_no_miss(self, monkeypatch, checkpoint_env):
        monkeypatch.setattr(settings, "SYNC_DB_COMMIT_BATCH_SIZE", 5)
        monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 5)  # 数量预算：每轮 5 个
        monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 600.0)

        torrents = _make_torrent_infos(20)
        fake_client = _qb_tracker_client(torrents)
        hash_map = {t.hash: i + 1 for i, t in enumerate(torrents)}
        downloader = BtDownloaders(downloader_id="dl_1", nickname="qb-test")
        db = MagicMock()

        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 1, "skip": 0, "removed": 0}),
            ),
        ):
            await _seed_active_checkpoint(checkpoint_env.store, downloader_id="dl_1")
            first = await torrents_async.qb_sync_trackers_only_async(db, downloader, fake_client)

        # 第一轮：数量预算到期 → partial，只拉取稳定排序后的前缀 5 个
        assert first["partial"] is True
        assert first["cycle_complete"] is False
        assert first["budget_reason"] == "count"
        assert first["cycle_progress"] == {"processed": 5, "total": 20}
        fetched1 = {c.args[0] for c in fake_client.torrents_trackers.call_args_list}
        assert fetched1 == {f"h{i:06d}" for i in range(5)}
        # 持久化检查点已保存 cursor（批 durable commit 后推进，滞后语义）
        persisted = await checkpoint_env.store.get_or_create("dl_1", "tracker")
        assert persisted["cursor"] == first["cursor"]
        assert persisted["outcome"] == "partial"
        assert json.loads(persisted["cursor"])["last_hash"] == "h000004"

        # 第二轮：从持久化 cursor 续跑 → 恰好处理未处理部分（无重复、无遗漏）。
        # 新进程/新一轮预算恢复（单轮预算每轮独立），放开数量上限
        monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 10**6)
        fake_client.torrents_trackers.reset_mock()
        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 1, "skip": 0, "removed": 0}),
            ),
        ):
            second = await torrents_async.qb_sync_trackers_only_async(
                db, downloader, fake_client, cursor=persisted["cursor"]
            )

        fetched2 = {c.args[0] for c in fake_client.torrents_trackers.call_args_list}
        assert fetched2 == {f"h{i:06d}" for i in range(5, 20)}
        assert fetched1.isdisjoint(fetched2)  # 无重复
        assert fetched1 | fetched2 == {t.hash for t in torrents}  # 无遗漏
        assert second["cycle_complete"] is True
        assert second["partial"] is False
        assert second["cursor"] is None  # 周期完整 → 下一轮从头开始新周期


class TestQbTrackerBatchFailureCursor:
    """第 N 批失败：cursor 停在最后 durable 批（未越过失败批），重试从该处续跑。"""

    async def test_batch_failure_cursor_stays_at_last_durable_batch(self, monkeypatch, checkpoint_env):
        monkeypatch.setattr(settings, "SYNC_DB_COMMIT_BATCH_SIZE", 5)
        monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 10**6)
        monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 600.0)

        torrents = _make_torrent_infos(20)
        fake_client = _qb_tracker_client(torrents)
        hash_map = {t.hash: i + 1 for i, t in enumerate(torrents)}
        downloader = BtDownloaders(downloader_id="dl_1", nickname="qb-test")
        db = MagicMock()
        flush_calls = {"n": 0}

        async def failing_flush(db_, rows, current_time):
            flush_calls["n"] += 1
            if flush_calls["n"] == 2:
                raise RuntimeError("第 2 批提交失败（模拟 SQLITE_BUSY/IO 异常）")
            return {"insert": 0, "update": len(rows), "skip": 0, "removed": 0}

        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(torrents_async, "sync_trackers_batch_async", new=failing_flush),
        ):
            await _seed_active_checkpoint(checkpoint_env.store, downloader_id="dl_1")
            result = await torrents_async.qb_sync_trackers_only_async(db, downloader, fake_client)

        # 第 2 批失败 → 停止本轮，cursor 停在最后成功批（第 1 批最后 hash h00004）
        assert flush_calls["n"] == 2  # 失败后不再提交后续批
        assert result["partial"] is True
        assert result["status"] == "partial"  # 既有 status 语义（error_count>0）
        persisted = await checkpoint_env.store.get_or_create("dl_1", "tracker")
        assert json.loads(persisted["cursor"])["last_hash"] == "h000004"
        assert result["cursor"] == persisted["cursor"]

        # 重试：从该 cursor 续跑，只处理未 durable 部分（不重做已提交批）
        fake_client.torrents_trackers.reset_mock()
        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 5, "skip": 0, "removed": 0}),
            ),
        ):
            retried = await torrents_async.qb_sync_trackers_only_async(
                db, downloader, fake_client, cursor=persisted["cursor"]
            )

        fetched = {c.args[0] for c in fake_client.torrents_trackers.call_args_list}
        assert fetched == {f"h{i:06d}" for i in range(5, 20)}
        assert retried["cycle_complete"] is True


class TestQbTrackerRemoteFailureCursor:
    """远程 enrich 失败时游标只能停在失败 hash 之前的 durable 前缀。"""

    async def test_remote_failure_does_not_skip_following_hashes(self, monkeypatch, checkpoint_env):
        monkeypatch.setattr(settings, "QB_TRACKER_WORKER_COUNT", 1)
        monkeypatch.setattr(settings, "SYNC_DB_COMMIT_BATCH_SIZE", 1000)
        monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 10**6)
        monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 600.0)

        torrents = _make_torrent_infos(5)
        client = MagicMock()
        client.torrents_info = MagicMock(return_value=torrents)

        def fetch_trackers(torrent_hash):
            if torrent_hash == "h000002":
                raise RuntimeError("模拟远端 tracker 请求失败")
            return []

        client.torrents_trackers = MagicMock(side_effect=fetch_trackers)
        downloader = BtDownloaders(downloader_id="dl_1", nickname="qb-test")
        db = MagicMock()
        hash_map = {t.hash: i + 1 for i, t in enumerate(torrents)}

        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 0, "skip": 0, "removed": 0}),
            ),
        ):
            await _seed_active_checkpoint(checkpoint_env.store, downloader_id="dl_1")
            result = await torrents_async.qb_sync_trackers_only_async(db, downloader, client)

        assert result["partial"] is True
        assert result["cycle_complete"] is False
        assert json.loads(result["cursor"])["last_hash"] == "h000001"
        persisted = await checkpoint_env.store.get_or_create("dl_1", "tracker")
        assert json.loads(persisted["cursor"])["last_hash"] == "h000001"


class TestQbTrackerCycleComplete:
    """周期完整：last_full_sync_at 更新 + cursor 清空（下一轮从头），经 Coordinator 终态。"""

    async def test_cycle_complete_updates_last_full_and_clears_cursor(self, monkeypatch, checkpoint_env):
        monkeypatch.setattr(settings, "SYNC_DB_COMMIT_BATCH_SIZE", 5)
        monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 10**6)
        monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 600.0)

        # 预置上一轮 partial 现场：cursor 已推进到 h000009（模拟中断/预算到期）
        row = await checkpoint_env.store.get_or_create("dl_001", "tracker")
        await checkpoint_env.store.advance(row["id"], row["version"], cursor='{"last_hash": "h000009"}')

        torrents = _make_torrent_infos(20)
        fake_client = _qb_tracker_client(torrents)
        hash_map = {t.hash: i + 1 for i, t in enumerate(torrents)}

        app = make_fake_app([make_vo(downloader_id="dl_001", client=fake_client)])
        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 1, "skip": 0, "removed": 0}),
            ),
            patch("app.api.endpoints.torrent_sync.update_tracker_status_from_keywords", new=AsyncMock()),
        ):
            result = await run_sync(
                SyncRequest(sync_type="tracker", downloader_ids=["dl_001"], trigger="cron"),
                app=app,
            )

        assert result.outcome == "success"
        # 本轮从 cursor 之后续跑：只拉取未 durable 部分（h00010..h00019）
        fetched = {c.args[0] for c in fake_client.torrents_trackers.call_args_list}
        assert fetched == {f"h{i:06d}" for i in range(10, 20)}
        # 周期完整 → 终态清空 cursor + 更新 last_full_sync_at（下一轮从头开始新周期）
        fresh = await checkpoint_env.store.get_or_create("dl_001", "tracker")
        assert fresh["cursor"] is None
        assert fresh["outcome"] == "success"
        assert fresh["last_full_sync_at"] is not None
        assert fresh["last_success_at"] is not None
        # cycle_started_at 本轮不重置（W3-2 周期语义：一轮内跨多轮预算续跑）
        assert fresh["cycle_started_at"] == row["cycle_started_at"]


class TestQbTrackerStableSort:
    """稳定排序：hash 乱序输入 → 处理顺序为字典序（续跑游标依赖同一顺序）。"""

    async def test_enrich_processes_hashes_in_dict_order(self, fake_client, monkeypatch):
        monkeypatch.setattr(settings, "QB_TRACKER_WORKER_COUNT", 1)
        monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 10**7)
        monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 0.0)

        hashes = ["h00010", "h00002", "h00019", "h00001", "h00005", "h00000", "h00015", "h00009"]
        infos = [SimpleNamespace(hash=h) for h in hashes]
        order = []
        fake = torrents_async.call_downloader_api  # 当前生效的直调 fake（autouse fixture）

        async def recording_wrapper(*args, **kwargs):
            order.append(kwargs["args"][0])  # args=(torrent_hash,)
            return await fake(*args, **kwargs)

        with patch.object(torrents_async, "call_downloader_api", new=recording_wrapper):
            await torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_1")

        assert order == sorted(hashes)


class TestCoordinatorBudgetPassthrough:
    """Coordinator 预算接线：SyncRequest.deadline/record_budget 透传到 qB tracker 单轮预算。"""

    async def test_deadline_and_record_budget_passed_to_qb_tracker_sync(self, checkpoint_env):
        """手动触发（trigger=manual）：预算显式指定 → 同步函数收到；到期 → outcome=partial。"""
        app = make_fake_app([make_vo(downloader_id="dl_001", client=MagicMock())])
        mock_qb = AsyncMock(
            return_value={
                "status": "success",
                "partial": True,
                "cursor": '{"last_hash": "h00004"}',
                "cycle_complete": False,
                "cycle_progress": {"processed": 5, "total": 20},
                "budget_reason": "count",
                "tracker_count": 5,
                "torrent_count": 20,
                "message": "budget partial",
            }
        )
        with (
            patch("app.api.endpoints.torrents_async.qb_sync_trackers_only_async", new=mock_qb),
            patch("app.api.endpoints.torrent_sync.update_tracker_status_from_keywords", new=AsyncMock()),
        ):
            result = await run_sync(
                SyncRequest(
                    sync_type="tracker",
                    downloader_ids=["dl_001"],
                    trigger="manual",
                    deadline=12.5,
                    record_budget=250,
                ),
                app=app,
            )

        assert mock_qb.await_count == 1
        kwargs = mock_qb.await_args.kwargs
        assert kwargs["deadline"] == 12.5
        assert kwargs["record_budget"] == 250
        # 预算到期 → outcome=partial，持久化 checkpoint 含最后 durable 批 cursor
        assert result.outcome == "partial"
        assert result.details["successful_syncs"] == 1
        assert result.details["failed_syncs"] == 0
        fresh = await checkpoint_env.store.get_or_create("dl_001", "tracker")
        assert fresh["cursor"] == '{"last_hash": "h00004"}'

    async def test_default_budget_uses_settings_fallback(self, checkpoint_env):
        """定时触发（trigger=cron）缺省预算（None）→ 同步函数回落 settings 默认（两触发同源）。"""
        app = make_fake_app([make_vo(downloader_id="dl_001", client=MagicMock())])
        mock_qb = AsyncMock(
            return_value={
                "status": "success",
                "partial": False,
                "cursor": None,
                "cycle_complete": True,
                "cycle_progress": {"processed": 0, "total": 0},
                "tracker_count": 0,
                "torrent_count": 0,
                "message": "ok",
            }
        )
        with (
            patch("app.api.endpoints.torrents_async.qb_sync_trackers_only_async", new=mock_qb),
            patch("app.api.endpoints.torrent_sync.update_tracker_status_from_keywords", new=AsyncMock()),
        ):
            result = await run_sync(
                SyncRequest(sync_type="tracker", downloader_ids=["dl_001"], trigger="cron"),
                app=app,
            )

        kwargs = mock_qb.await_args.kwargs
        assert kwargs.get("deadline") is None
        assert kwargs.get("record_budget") is None
        assert result.outcome == "success"
        # 周期完整（空集）→ 终态清空 cursor + 更新 last_full_sync_at
        fresh = await checkpoint_env.store.get_or_create("dl_001", "tracker")
        assert fresh["cursor"] is None
        assert fresh["last_full_sync_at"] is not None


class TestSentinelLossSelfHealing:
    """【2026-08-25 生产 cron-7-20260825223237 回归】producer 哨兵丢失自愈。

    根因（双子代理验证定位）：producer 收尾放哨兵时队列恰被未消费 hash 占满
    （worker 各挂在 30s 慢调用上不消费），首个哨兵 put 0.5s 超时即 break 丢弃
    全部哨兵，worker 处理完后在 queue.get()（无超时）永久挂起——enrich 永不
    返回、任务挂死 8.75h（叠加下载器级熔断前无强制取消）。修复双保险：
    producer 哨兵 put 带总限重试 + worker get 超时轮询（producer done 且队列空
    即退出）。若有人改回 break 丢弃哨兵或去掉轮询，本测试即挂起超时失败。
    """

    async def test_slow_fetch_sentinel_timeout_does_not_hang(self):
        """确定性时序复现：fetch 0.8s > 哨兵 put 0.5s 窗口 → 首个哨兵 put
        必超时（队列被 hash3/4 占满、两 worker 挂在 0.8s fetch 上）→ 修复后
        enrich 仍正常收尾并打 Completed（修复前 worker 永久挂死）。"""
        infos = _make_torrent_infos(4)

        async def slow_fetch(downloader_id, lane, func, args=(), kwargs=None, timeout=None, operation=""):
            await asyncio.sleep(0.8)  # > 0.5s：保证哨兵首个 put 在队列满时超时
            raise asyncio.TimeoutError("simulated slow qb webui")

        with (
            patch.object(torrents_async, "call_downloader_api", new=slow_fetch),
            patch.object(torrents_async, "_WORKER_GET_POLL_SECONDS", 0.2),
            patch.object(torrents_async.logger, "info") as mock_info,
        ):
            # 修复前：worker 挂在 queue.get()，15s wait_for 超时即测试失败
            await asyncio.wait_for(
                torrents_async._enrich_qb_torrents_with_trackers(MagicMock(), infos, "dl_sentinel_loss"),
                timeout=15.0,
            )

        completed = _completion_log(mock_info)
        assert "4 failed" in completed, f"4 个 hash 应全部计为失败: {completed}"

    async def test_worker_polling_self_heals_when_all_sentinels_are_lost(self, fake_client, monkeypatch):
        """独立验证 worker 轮询兜底：模拟 producer 的所有哨兵 put 都失败。

        本用例不依赖 producer 的重试修复，直接让哨兵永远无法入队，并用隔离的
        单调时钟让 producer 快速放弃 30 秒总限；worker 处理完正常任务后只能依靠
        ``producer_task.done() + queue.empty()`` 退出。若删除 queue.get 超时轮询，
        本用例会在外层 wait_for 超时。
        """
        monkeypatch.setattr(settings, "QB_TRACKER_WORKER_COUNT", 1)
        monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 100)
        monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 0.0)
        monkeypatch.setattr(torrents_async, "_WORKER_GET_POLL_SECONDS", 0.01)

        original_queue = torrents_async.asyncio.Queue
        queues = []

        class DropAllSentinelQueue(original_queue):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.sentinel_attempts = 0
                queues.append(self)

            async def put(self, item):
                if item is None:
                    self.sentinel_attempts += 1
                    raise asyncio.TimeoutError("simulated lost sentinel")
                return await super().put(item)

        # 仅替换被测模块的 time 对象，避免改动 asyncio 事件循环使用的全局时钟。
        clock_values = iter((0.0, 0.0, 31.0))

        def fake_monotonic():
            return next(clock_values, 31.0)

        monkeypatch.setattr(torrents_async, "time", SimpleNamespace(monotonic=fake_monotonic))
        monkeypatch.setattr(torrents_async.asyncio, "Queue", DropAllSentinelQueue)

        infos = _make_torrent_infos(3)
        await asyncio.wait_for(
            torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_lost_all_sentinels"),
            timeout=2.0,
        )

        assert len(queues) == 1
        assert queues[0].sentinel_attempts == 1
        assert fake_client.torrents_trackers.call_count == 3
        assert all(t.trackers == [] for t in infos)

    async def test_producer_retries_sentinel_until_each_worker_receives_one(self, fake_client, monkeypatch):
        """独立验证 producer 重试层：前两次哨兵入队超时后仍为两个 worker 补齐哨兵。"""
        monkeypatch.setattr(settings, "QB_TRACKER_WORKER_COUNT", 2)
        monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 100)
        monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 0.0)
        monkeypatch.setattr(torrents_async, "_WORKER_GET_POLL_SECONDS", 0.01)

        original_queue = torrents_async.asyncio.Queue
        queues = []

        class FlakySentinelQueue(original_queue):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.sentinel_attempts = 0
                self.accepted_sentinels = 0
                queues.append(self)

            async def put(self, item):
                if item is None:
                    self.sentinel_attempts += 1
                    if self.sentinel_attempts <= 2:
                        raise asyncio.TimeoutError("simulated full queue")
                    self.accepted_sentinels += 1
                return await super().put(item)

        monkeypatch.setattr(torrents_async.asyncio, "Queue", FlakySentinelQueue)

        infos = _make_torrent_infos(4)
        await asyncio.wait_for(
            torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_retry_sentinels"),
            timeout=2.0,
        )

        assert len(queues) == 1
        assert queues[0].sentinel_attempts == 4
        assert queues[0].accepted_sentinels == 2
        assert fake_client.torrents_trackers.call_count == 4

    async def test_cancelled_enrichment_cleans_up_producer_and_workers(self, fake_client, monkeypatch):
        """取消 enrich 后，固定控制任务全部结束，不遗留悬挂 worker/producer。"""
        monkeypatch.setattr(settings, "QB_TRACKER_WORKER_COUNT", 2)
        monkeypatch.setattr(settings, "QB_TRACKER_MAX_TORRENTS_PER_RUN", 100)
        monkeypatch.setattr(settings, "QB_TRACKER_RUN_BUDGET_SECONDS", 0.0)

        started = asyncio.Event()
        baseline_tasks = set(asyncio.all_tasks())

        async def hanging_call(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        infos = _make_torrent_infos(10)
        with patch.object(torrents_async, "call_downloader_api", new=hanging_call):
            enrich_task = asyncio.create_task(
                torrents_async._enrich_qb_torrents_with_trackers(fake_client, infos, "dl_cancelled")
            )
            await asyncio.wait_for(started.wait(), timeout=1.0)
            enrich_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(enrich_task, timeout=1.0)

        await asyncio.sleep(0)
        leaked_tasks = [task for task in asyncio.all_tasks() if task not in baseline_tasks and not task.done()]
        assert not leaked_tasks, f"取消后不应遗留后台任务: {leaked_tasks}"
