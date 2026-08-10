# -*- coding: utf-8 -*-
"""
W3-3 第二部分（P1-02）：info-only 分阶段流水线验证与内存峰值集成测试
（PLANS/sync-database-blocking-remediation.md W3-3；本文件即计划目标文件
tests/integration/test_sync_memory_bound.py）

【覆盖目标】（对应计划 W3-3 "测试"清单与任务书 W3-3 第二部分）：
1. 分阶段流水线时序（test_fetch_phase_no_db_write_and_write_phase_no_fetch）：
   fetch（远程读取）期间不持有 DB 写锁；write 阶段无下载器调用。真实文件型
   SQLite + 真实 bulk_upsert_with_retry，以时序探针记录每次远程调用与每次
   DB commit 的时刻，断言二者不重叠（fetch 全部结束后才开始 commit）。
2. 下载器实际并发符合配置（test_concurrency_matches_config）：经真实
   TorrentInfoSyncTask.execute → execute_sync_with_concurrency（真实
   asyncio.Semaphore），4 个下载器各 10k 规模并发执行 info-only 同步，
   计数探针断言任意时刻活跃同步数 ≤ INFO_SYNC_DOWNLOADER_CONCURRENCY
   （=1 时 ≤1；=2 时 ≤2 且确实发生重叠）。
3. 内存峰值不随全部下载器总量线性叠加（test_memory_peak_bounded_*）：
   串行（并发 1）与并发（并发 2）各处理 2×10k，用完成日志 rows_buffered
   （逐轮峰值）与记录型 bulk 探针（任意时刻正在写入行数总和）断言峰值有界
   （rows_buffered ≤ INFO_SYNC_MAX_BUFFERED_ROWS + 下载器数×分页大小），
   远小于总量 20k。不做真实 RSS 断言（psutil 未安装，见报告说明）。
4. downloader 部分失败不阻止其他下载器完成：一个下载器远程调用抛异常 →
   函数层原样上抛（test_failing_downloader_propagates_at_function_level）；
   任务编排层该下载器 failed、其余 success，结果标记 partial
   （test_partial_failure_does_not_block_other_downloaders）。
5. qB RID 增量捷径完整性保护（代码顺序经判定已正确，本部分只加测试证明）：
   - test_rid_confirmed_only_after_durable_commit：成功路径
     _confirm_qb_sync_rid 只在全部 DB durable commit 之后调用；
   - test_rid_not_confirmed_when_commit_fails：commit 抛异常 → 不确认 RID
     （下轮从未确认 RID 重新对账，不丢数据）；
   - test_incremental_failure_falls_back_to_paged_full_sync：sync_maindata
     增量失败 → 降级 torrents_info 分页全量，且仍受单轮预算限制
     （budget_reason=count），不确认 RID。

【fixture 设计】
- mem_db：真实文件型 SQLite（WAL / synchronous=NORMAL / busy_timeout=15000，
  NullPool，语义与 app/database.py _apply_sqlite_pragmas 一致），只建
  torrent_info 表（生产 TorrentInfo 模型，与 tests/api/test_torrents_async_
  info_budget.py 同款）；每测试独立临时目录。
- call_downloader_api 全量替换为直调 fake（记录每次远程调用时刻），同时
  覆盖 torrents_async 与 torrent_metadata 两个消费模块（增量水合路径）；
  不经 downloader_api_runtime 全局单例（避免被 TestClient lifespan shutdown，
  与 tests/api/test_torrents_async_info_budget.py 的隔离原因一致）。
- 异步测试直接 async def（pytest.ini asyncio_mode=auto）。

【与既有测试的关系】
- tests/api/test_torrents_async_info_budget.py：预算/分页/缓冲单测（mock 层）；
  本文件在其之上做并发/时序/峰值集成验证（真实 SQLite + 真实编排）。
- tests/integration/test_sqlite_sync_contention.py：SQLite 写锁争用物理事实；
  本文件验证 fetch/write 阶段边界（时序探针），不重复锁争用用例。
"""

import asyncio
import math
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.endpoints import torrents_async
from app.core.config import settings
from app.services import sync_coordinator
from app.services.sync_coordinator import SyncResult
from app.services.sync_db_write import WriteStats
from app.services import torrent_metadata
from app.tasks.resource_guard import admission_controller
from app.tasks.scheduler.torrent_sync.torrent_info_sync_task import TorrentInfoSyncTask
from app.torrents.models import TorrentInfo

pytestmark = pytest.mark.integration


# =============================================================================
# 公共 fixture：call_downloader_api 直调 fake + 远程调用时序记录
# =============================================================================

# 每次远程调用的记录：(operation, 开始时刻, 结束时刻)（time.monotonic）。
# 供"fetch 与 DB commit 不重叠"时序断言使用；autouse fixture 每测试清空。
CALL_RECORD: List[tuple] = []


@pytest.fixture(autouse=True)
def _patch_call_downloader_api(monkeypatch):
    """把 torrents_async / torrent_metadata 的 call_downloader_api 替换为直调 fake。

    同时记录每次远程调用的时刻窗口（CALL_RECORD），供分阶段流水线时序断言。
    直调（不经 downloader_api_runtime 全局单例）：避免 TestClient lifespan
    shutdown 全局 executor 后 cannot schedule new futures after shutdown。
    """

    async def fake_call_downloader_api(downloader_id, lane, func, args=(), kwargs=None, timeout=None, operation=""):
        t0 = time.monotonic()
        result = func(*args, **(kwargs or {}))
        CALL_RECORD.append((operation, t0, time.monotonic()))
        return result

    # 每测试清空时序记录（避免跨用例残留干扰 fetch/commit 断言）
    CALL_RECORD.clear()
    monkeypatch.setattr(torrents_async, "call_downloader_api", fake_call_downloader_api)
    monkeypatch.setattr(torrent_metadata, "call_downloader_api", fake_call_downloader_api)


# =============================================================================
# fixture：真实文件型 SQLite（每测试独立临时目录 + .db 文件）
# =============================================================================


def _apply_sqlite_pragmas(dbapi_conn, conn_record):  # noqa: ANN001 - SQLAlchemy 事件回调签名
    """对每个新建连接下发与 app/database.py _apply_sqlite_pragmas 一致的 PRAGMA。"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()


@dataclass
class _MemDbEnv:
    """真实文件型 SQLite 环境：引擎 + 会话工厂 + db 文件路径。"""

    engine: AsyncEngine
    factory: Any
    db_path: Path


@pytest.fixture
async def mem_db(tmp_path):
    """真实文件型 SQLite（WAL + NullPool），只建 torrent_info 表。"""
    db_path = tmp_path / "sync_memory_bound.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 15},
        poolclass=NullPool,
    )
    event.listens_for(engine.sync_engine, "connect")(_apply_sqlite_pragmas)

    async with engine.begin() as conn:
        await conn.run_sync(lambda c: TorrentInfo.__table__.create(c))

    # 防御性重建进程级准入信号量（绑定当前事件循环，避免历史测试遗留状态干扰）
    admission_controller.reset_state()

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    env = _MemDbEnv(engine=engine, factory=factory, db_path=db_path)
    try:
        yield env
    finally:
        await engine.dispose()
        admission_controller.reset_state()


# =============================================================================
# 构造辅助（与 tests/api/test_torrents_async_info_budget.py 同款字段）
# =============================================================================

ADDED_DT = datetime(2026, 1, 1, 12, 0, 0)
ADDED_TS = int(ADDED_DT.timestamp())


def _qb_downloader(downloader_id: str = "dl-1", nickname: str = "qb") -> SimpleNamespace:
    """info-only 同步函数接收的下载器 VO（SimpleNamespace，兼容 _qb_get_attr 用法）。"""
    return SimpleNamespace(
        downloader_id=downloader_id,
        nickname=nickname,
        host="localhost",
        port=8080,
        username="admin",
        password="secret",
    )


def _qb_seed(hash_: str, name: str) -> SimpleNamespace:
    """远程 qB 种子（SimpleNamespace，字段与 diff 构造代码逐项对齐）。"""
    return SimpleNamespace(
        hash=hash_,
        name=name,
        save_path="/downloads",
        total_size=4096,
        progress=0.5,
        state="stalledUP",
        added_on=ADDED_TS,
        completion_on=0,
        ratio=1.5,
        ratio_limit=2.0,
        tags="PT",
        category="电影",
        super_seeding=False,
    )


def _qb_seeds(count: int, prefix: str = "h") -> List[SimpleNamespace]:
    """构造 count 个 hash 唯一（prefix + 6 位序号）的远程种子。"""
    return [_qb_seed(f"{prefix}{i:06d}", f"name-{i}") for i in range(count)]


def _qb_sync_payload(rid: int, seeds: List[SimpleNamespace], removed: Optional[List[str]] = None) -> Dict[str, Any]:
    """构造 sync/maindata 增量响应：torrents dict 值即 _qb_dict_to_objects 的 payload。"""
    torrents: Dict[str, Any] = {}
    for seed in seeds:
        payload = {
            "name": seed.name,
            "save_path": seed.save_path,
            "total_size": seed.total_size,
            "progress": seed.progress,
            "state": seed.state,
            "added_on": seed.added_on,
            "completion_on": seed.completion_on,
            "ratio": seed.ratio,
            "ratio_limit": seed.ratio_limit,
            "tags": seed.tags,
            "category": seed.category,
            "super_seeding": seed.super_seeding,
        }
        torrents[seed.hash] = payload
    return {"rid": rid, "torrents": torrents, "torrents_removed": list(removed or [])}


def _make_qb_client(
    seeds: List[SimpleNamespace],
    sync_payload: Optional[Dict[str, Any]] = None,
    sync_maindata_raises: bool = False,
    torrents_info_raises: bool = False,
) -> SimpleNamespace:
    """伪 qB 客户端：torrents_info 同时支持 limit/offset 分页与 torrent_hashes 水合。

    - 分页（全量同步路径）：torrents_info(limit=..., offset=...) 切片返回；
    - 水合（增量路径，_hydrate_qb_incremental_torrents）：torrents_info(
      torrent_hashes=[...]) 按 hash 返回完整行。
    """
    by_hash = {str(getattr(s, "hash")).strip().lower(): s for s in seeds}

    def torrents_info(**kwargs):
        if torrents_info_raises:
            raise RuntimeError("模拟 torrents_info 失败")
        if "torrent_hashes" in kwargs:
            return [by_hash[h] for h in kwargs["torrent_hashes"] if str(h).strip().lower() in by_hash]
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 500)
        return seeds[offset : offset + limit]

    def sync_maindata(**kwargs):  # noqa: ANN003 - 伪客户端方法签名
        if sync_maindata_raises:
            raise RuntimeError("模拟 sync_maindata 失败")
        if sync_payload is not None:
            return sync_payload
        return {"rid": 0, "torrents": {}, "torrents_removed": []}

    return SimpleNamespace(torrents_info=torrents_info, sync_maindata=sync_maindata)


def _qb_row(info_id: str, hash_: str) -> TorrentInfo:
    """与 _qb_seed 字段匹配的现有 DB 行（TorrentInfo ORM，downloader dl-1/qb）。"""
    t = TorrentInfo(
        info_id,
        "dl-1",
        "qb",
        f"tid-{hash_}",
        hash_,
        "existing",
        "/downloads",
        4096.0,
        "seeding",
        50.0,
        None,
        ADDED_DT,
        None,
        1.5,
        2.0,
        "PT",
        "电影",
        False,
        True,
        ADDED_DT,
        "tester",
        ADDED_DT,
        "tester",
        0,
    )
    t.has_tracker_error = False
    return t


def _empty_db() -> AsyncMock:
    """空库 AsyncMock：所有 select 返回空结果（与 test_torrents_async_info_budget 同款）。"""
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.execute.return_value = query_result
    return db


def _completion_log(mock_info: MagicMock, marker: str) -> str:
    """从 patch 的 logger.info 调用列表中提取完成日志文本（与 budget 测试同款）。"""
    hits = [str(c) for c in mock_info.call_args_list if marker in str(c)]
    assert hits, f"未捕获完成日志（{marker}）"
    return hits[-1]


def _completion_logs_since(mock_info: MagicMock, marker: str, start_index: int) -> List[str]:
    """提取 start_index 之后的所有完成日志文本（供多轮场景按轮断言）。"""
    return [str(c) for c in mock_info.call_args_list[start_index:] if marker in str(c)]


def _rows_buffered_from_log(text: str) -> int:
    """从完成日志解析 rows_buffered 峰值。"""
    match = re.search(r"rows_buffered=(\d+)", text)
    assert match, f"完成日志缺少 rows_buffered 字段: {text[:200]}"
    return int(match.group(1))


def _make_recording_bulk(state: Dict[str, Any]):
    """构造记录型 bulk_upsert_with_retry 替身。

    记录每次 flush 的待写行数（sizes），并跟踪"任意时刻正在写入的行数总和"
    （active/peak）——跨并发运行的内存峰值代理（真实待写缓冲峰值 ≤
    INFO_SYNC_MAX_BUFFERED_ROWS，flush 大小即缓冲实际内容）。
    """

    async def recording_bulk(db, to_insert, to_update, *, model, label="", **kwargs):
        size = len(to_insert) + len(to_update)
        state["active"] += size
        state["peak"] = max(state["peak"], state["active"])
        state["calls"] += 1
        state["sizes"].append(size)
        try:
            # 让行窗口：模拟真实写入期间事件循环可被并发运行插入（瞬时峰值可观测）
            await asyncio.sleep(0)
            return WriteStats(scanned=size, changed=size, committed=size, batches=1, elapsed_ms=0.0)
        finally:
            state["active"] -= size

    return recording_bulk


@contextmanager
def _fake_app_main():
    """临时替换 sys.modules['app.main'] 为伪模块（与 budget 测试同款）。

    TorrentInfoSyncTask.execute 内部 `from app.main import app` 在调用时解析
    sys.modules，替换后取到伪 app（execute 只把它透传给已 patch 的
    get_valid_downloaders，实际不使用）。避免导入真实 app.main 的副作用。
    """
    fake = SimpleNamespace(app=SimpleNamespace())
    original = sys.modules.get("app.main")
    sys.modules["app.main"] = fake
    try:
        yield fake
    finally:
        if original is not None:
            sys.modules["app.main"] = original
        else:
            sys.modules.pop("app.main", None)


def _patch_info_run_config(monkeypatch) -> None:
    """info-only 运行参数统一打点：不设数量/时间预算（只测缓冲与并发）。"""
    monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 10**7)
    monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)
    monkeypatch.setattr(settings, "INFO_SYNC_DB_READ_PAGE_SIZE", 500)
    monkeypatch.setattr(settings, "INFO_SYNC_MAX_BUFFERED_ROWS", 2000)
    monkeypatch.setattr(torrents_async, "QB_USE_INCREMENTAL_SYNC", False)
    monkeypatch.setattr(torrents_async, "_QB_LAST_FULL_SYNC", {})
    monkeypatch.setattr(torrents_async, "_QB_SYNC_RID_CACHE", {})


# =============================================================================
# 1. 分阶段流水线时序：fetch 不持 DB 写锁；write 无下载器调用
# =============================================================================


async def test_fetch_phase_no_db_write_and_write_phase_no_fetch(mem_db, monkeypatch):
    """真实文件型 SQLite + 真实分批写入：fetch 与 DB commit 时序不重叠。

    【时序探针】
    - CALL_RECORD：每次远程调用（qb_torrents_info_only 分页）的 (operation, 起, 止)；
    - commit 探针：包裹真实 session.commit，记录每次 durable commit 时刻。
    【断言】
    1. fetch 全部结束后才开始 commit：max(fetch_end) < min(commit)；
    2. 写阶段（首个 commit 之后）无任何新的远程调用；
    3. 真实分批提交生效：commit 次数 == ceil(10000 / SYNC_DB_COMMIT_BATCH_SIZE)；
    4. 10k 行全部落库（分批提交不丢行）。
    """
    _patch_info_run_config(monkeypatch)
    seeds = _qb_seeds(10000, prefix="p")
    client = _make_qb_client(seeds)

    session = mem_db.factory()
    real_commit = session.commit
    commits: List[float] = []

    async def recording_commit():
        commits.append(time.monotonic())
        return await real_commit()

    monkeypatch.setattr(session, "commit", recording_commit)

    await torrents_async.qb_add_torrents_info_only_async(session, [_qb_downloader()], client=client)

    # 1) fetch 全部结束后才开始 commit（fetch 期间不持有 DB 写锁）
    fetch_ops = [rec for rec in CALL_RECORD if rec[0] == "qb_torrents_info_only"]
    expected_fetch_calls = math.ceil(10000 / torrents_async.QB_BATCH_SIZE) + (
        1 if 10000 % torrents_async.QB_BATCH_SIZE == 0 else 0
    )
    assert len(fetch_ops) == expected_fetch_calls, f"分页 fetch 调用次数异常: {len(fetch_ops)}"
    assert commits, "应发生真实 DB commit"
    last_fetch_end = max(end for _, _, end in fetch_ops)
    first_commit = min(commits)
    assert last_fetch_end < first_commit, (
        f"fetch 与 DB commit 重叠：last_fetch_end={last_fetch_end:.6f} " f"first_commit={first_commit:.6f}"
    )

    # 2) 写阶段（首个 commit 之后）无新的下载器调用
    calls_started_after_first_commit = [rec for rec in CALL_RECORD if rec[1] >= first_commit]
    assert calls_started_after_first_commit == [], f"写阶段仍有下载器调用: {calls_started_after_first_commit}"

    # 3) 真实分批提交：每批独立 commit（W1-1 语义在 info-only 路径仍生效）
    if settings.SYNC_CHUNKED_COMMIT_ENABLED:
        expected_commits = math.ceil(10000 / settings.SYNC_DB_COMMIT_BATCH_SIZE)
        assert len(commits) == expected_commits, f"commit 次数应为 {expected_commits}，实际 {len(commits)}"

    # 4) 10k 行全部落库（分批提交不丢行）
    count = (await session.execute(select(func.count()).select_from(TorrentInfo))).scalar()
    assert count == 10000, f"落库行数异常: {count}"
    await session.close()


# =============================================================================
# 2. 下载器实际并发符合配置（真实编排：Semaphore + 每下载器锁 + info-only）
# =============================================================================


@pytest.mark.parametrize(
    "concurrency, expected_max, expect_overlap",
    [(1, 1, False), (2, 2, True)],
    ids=["concurrency-1", "concurrency-2"],
)
async def test_concurrency_matches_config(monkeypatch, concurrency, expected_max, expect_overlap):
    """4 个下载器各 10k 规模经真实编排并发执行，任意时刻活跃同步数 ≤ 配置。

    【路径】TorrentInfoSyncTask.execute（生产入口）→ execute_sync_with_
    concurrency（真实 asyncio.Semaphore(max_concurrent=配置)）→ 每下载器锁 →
    _sync_torrent_info_only → sync_coordinator.run_sync（patch 为计数探针，
    探针内执行真实 qb_add_torrents_info_only_async 全流程）。
    【断言】
    1. 4 个下载器全部 success（successful_syncs=4）；
    2. 活跃同步数峰值 ≤ INFO_SYNC_DOWNLOADER_CONCURRENCY（=1 时 ≤1）；
    3. =2 时峰值 ≥2（并发确实发生重叠，证明信号量放行而非退化为串行）；
    4. 4×10k 全部经真实流水线处理（记录型 bulk 共 20 次 flush / 40000 行）。
    """
    monkeypatch.setattr(settings, "INFO_SYNC_DOWNLOADER_CONCURRENCY", concurrency)
    _patch_info_run_config(monkeypatch)

    bulk_state: Dict[str, Any] = {"active": 0, "peak": 0, "calls": 0, "sizes": []}
    monkeypatch.setattr(torrents_async, "bulk_upsert_with_retry", _make_recording_bulk(bulk_state))

    run_state: Dict[str, Any] = {"active": 0, "peak": 0, "calls": 0}
    clients: Dict[str, Any] = {}
    for i in range(1, 5):
        did = f"dl-{i}"
        clients[did] = _make_qb_client(_qb_seeds(10000, prefix=f"c{i}-"))

    async def probe_run_sync(req, app=None):
        """计数探针：包裹真实 info-only 同步，记录任意时刻活跃同步数。"""
        did = str(req.downloader_ids[0])
        run_state["active"] += 1
        run_state["peak"] = max(run_state["peak"], run_state["active"])
        run_state["calls"] += 1
        try:
            await torrents_async.qb_add_torrents_info_only_async(
                _empty_db(),
                [_qb_downloader(did, f"qb-{did}")],
                client=clients[did],
            )
            # 拉长临界区窗口：并发=2 时第二任务必然在第一任务临界区内进入
            await asyncio.sleep(0.05)
            return SyncResult(outcome="success", message="ok", run_id=f"probe-{did}", details={})
        finally:
            run_state["active"] -= 1

    monkeypatch.setattr(sync_coordinator, "run_sync", probe_run_sync)

    task = TorrentInfoSyncTask()
    vos = [
        SimpleNamespace(
            downloader_id=f"dl-{i}",
            nickname=f"qb-{i}",
            host="localhost",
            port=8080,
            username="admin",
            password="secret",
            downloader_type=0,
            torrent_save_path="/downloads",
            fail_time=0,
        )
        for i in range(1, 5)
    ]
    with (
        _fake_app_main(),
        patch.object(task, "get_valid_downloaders", new=AsyncMock(return_value=vos)),
    ):
        result = await task.execute()

    # 1) 4 个下载器全部成功
    assert result["status"] == "success", f"任务结果异常: {result}"
    assert result["successful_syncs"] == 4
    assert result["failed_syncs"] == 0
    assert result["total_downloaders"] == 4

    # 2) 计数探针：每次 run_sync 恰好执行一次真实 info-only 同步
    assert run_state["calls"] == 4

    # 3) 任意时刻活跃同步数 ≤ 配置
    assert run_state["peak"] <= expected_max, f"并发={concurrency} 时活跃同步峰值 {run_state['peak']} 超过配置"
    if expect_overlap:
        # 并发=2 必须观察到重叠（否则退化为串行，信号量未生效）
        assert run_state["peak"] >= 2, f"并发=2 未观察到活跃同步重叠: peak={run_state['peak']}"

    # 4) 4×10k 全部经真实流水线处理：每轮 10k/2000 → 4 次 flush + 1 次收尾
    assert bulk_state["calls"] == 20, f"bulk flush 次数异常: {bulk_state['calls']}"
    assert sum(bulk_state["sizes"]) == 40000, f"总处理行数异常: {sum(bulk_state['sizes'])}"


# =============================================================================
# 3. 内存峰值有界：不随全部下载器总量线性叠加
# =============================================================================


async def test_memory_peak_bounded_serial_vs_concurrent(monkeypatch):
    """串行（并发 1）与并发（并发 2）各处理 2×10k，峰值缓冲行数均有界。

    【度量方式】
    - 每轮完成日志 rows_buffered：该轮待写缓冲峰值（观测日志，权威）；
    - 记录型 bulk 探针 active/peak：任意时刻正在写入的行数总和（跨并发
      运行的瞬时峰值代理）。
    【断言】（psutil 未安装，不做真实 RSS 断言——见报告说明）
    1. 每轮 rows_buffered ≤ INFO_SYNC_MAX_BUFFERED_ROWS + 下载器数×页大小
       （契约公式：串行 N=1 → 2000+500；并发 N=2 → 2000+2×500）；
    2. 每轮 rows_buffered ≤ INFO_SYNC_MAX_BUFFERED_ROWS（结构上限：flush 在
       buffered >= 上限时触发，缓冲永不越过上限）；
    3. 瞬时写入峰值：串行 ≤ 2000；并发 ≤ 2×2000（每轮 flush ≤ 上限）；
    4. 反线性叠加：并发峰值（≤4000）远小于全部下载器总量 20000——
       内存峰值不随总行数线性增长；
    5. 两个场景 4 轮均完整处理 10k 行（不因缓冲控制丢行）。
    """
    _patch_info_run_config(monkeypatch)
    max_buffered = settings.INFO_SYNC_MAX_BUFFERED_ROWS
    page_size = settings.INFO_SYNC_DB_READ_PAGE_SIZE
    total_per_downloader = 10000

    bulk_state: Dict[str, Any] = {"active": 0, "peak": 0, "calls": 0, "sizes": []}
    monkeypatch.setattr(torrents_async, "bulk_upsert_with_retry", _make_recording_bulk(bulk_state))
    mock_info = MagicMock()
    monkeypatch.setattr(torrents_async.logger, "info", mock_info)

    def make_run(did: str, prefix: str):
        return _qb_downloader(did, f"qb-{did}"), _make_qb_client(_qb_seeds(total_per_downloader, prefix=prefix))

    dl_a, client_a = make_run("dl-a", "a")
    dl_b, client_b = make_run("dl-b", "b")

    # ---- 场景 1：串行（并发 1）处理 2×10k ----
    serial_start = len(mock_info.call_args_list)
    await torrents_async.qb_add_torrents_info_only_async(_empty_db(), [dl_a], client=client_a)
    await torrents_async.qb_add_torrents_info_only_async(_empty_db(), [dl_b], client=client_b)
    serial_logs = _completion_logs_since(mock_info, "[QB_INFO_SYNC]", serial_start)
    assert len(serial_logs) == 2, f"串行场景应有 2 条完成日志: {len(serial_logs)}"
    serial_rows_buffered = [_rows_buffered_from_log(text) for text in serial_logs]
    serial_peak = bulk_state["peak"]
    assert all(v == total_per_downloader for v in [sum(bulk_state["sizes"][:5]), sum(bulk_state["sizes"][5:10])])

    # 串行每轮 rows_buffered ≤ 上限 + 1×页大小（契约公式 N=1），且 ≤ 结构上限
    assert max(serial_rows_buffered) <= max_buffered + 1 * page_size
    assert max(serial_rows_buffered) <= max_buffered
    # 串行瞬时写入峰值：单轮 flush 不超过缓冲上限
    assert serial_peak <= max_buffered, f"串行瞬时写入峰值 {serial_peak} 超过单轮上限"

    # ---- 场景 2：并发（并发 2）处理 2×10k ----
    bulk_state["active"] = 0
    bulk_state["peak"] = 0
    concurrent_start = len(mock_info.call_args_list)
    await asyncio.gather(
        torrents_async.qb_add_torrents_info_only_async(_empty_db(), [dl_a], client=client_a),
        torrents_async.qb_add_torrents_info_only_async(_empty_db(), [dl_b], client=client_b),
    )
    concurrent_logs = _completion_logs_since(mock_info, "[QB_INFO_SYNC]", concurrent_start)
    assert len(concurrent_logs) == 2, f"并发场景应有 2 条完成日志: {len(concurrent_logs)}"
    concurrent_rows_buffered = [_rows_buffered_from_log(text) for text in concurrent_logs]
    concurrent_peak = bulk_state["peak"]

    # 并发每轮 rows_buffered ≤ 上限 + 2×页大小（契约公式 N=2），且 ≤ 结构上限
    assert max(concurrent_rows_buffered) <= max_buffered + 2 * page_size
    assert max(concurrent_rows_buffered) <= max_buffered
    # 并发瞬时写入峰值：两轮同时 flush 时 ≤ 2×上限（每轮 flush ≤ 上限）
    assert concurrent_peak <= 2 * max_buffered, f"并发瞬时写入峰值 {concurrent_peak} 超过 2×缓冲上限"

    # ---- 反线性叠加：峰值与总行数（20000）无关，被缓冲上限约束 ----
    assert concurrent_peak < total_per_downloader, f"并发峰值 {concurrent_peak} 接近单下载器全量行数——缓冲控制疑似失效"
    assert max(serial_peak, concurrent_peak) < 2 * total_per_downloader

    # ---- 数据完整性：4 轮全部处理 10k 行（不因缓冲控制丢行） ----
    assert sum(bulk_state["sizes"][10:]) == 2 * total_per_downloader
    assert bulk_state["calls"] == 20, f"两场景共 4 轮 × 5 次 flush，实际 {bulk_state['calls']}"


# =============================================================================
# 4. downloader 部分失败不阻止其他下载器完成（结果标记 partial）
# =============================================================================


async def test_failing_downloader_propagates_at_function_level(mem_db, monkeypatch):
    """函数层：下载器远程调用抛异常时 info-only 同步函数原样上抛。

    全量（分页）路径的 fetch 循环无 try/except——异常向上传播，由编排层
    （sync_single_downloader / _sync_one_downloader）按下载器粒度捕获。
    """
    _patch_info_run_config(monkeypatch)
    client = _make_qb_client(seeds=[_qb_seed("h000000", "x")], torrents_info_raises=True)
    session = mem_db.factory()
    try:
        with pytest.raises(RuntimeError, match="模拟 torrents_info 失败"):
            await torrents_async.qb_add_torrents_info_only_async(session, [_qb_downloader()], client=client)
    finally:
        await session.rollback()
        await session.close()


async def test_partial_failure_does_not_block_other_downloaders(monkeypatch):
    """编排层：4 个下载器之一失败 → 该下载器 failed、其余 success，结果 partial。

    经真实 execute_sync_with_concurrency（生产 info 任务聚合层）：
    sync_single_downloader 按下载器捕获异常并返回 failed 结果字典，
    其余 3 个下载器正常完成（记录型 bulk 证明 3×50 行全部经真实流水线）。
    """
    _patch_info_run_config(monkeypatch)

    bulk_state: Dict[str, Any] = {"active": 0, "peak": 0, "calls": 0, "sizes": []}
    monkeypatch.setattr(torrents_async, "bulk_upsert_with_retry", _make_recording_bulk(bulk_state))

    clients: Dict[str, Any] = {}
    for i in range(1, 5):
        clients[f"dl-{i}"] = _make_qb_client(
            _qb_seeds(50, prefix=f"p{i}-"),
            torrents_info_raises=(i == 2),  # 第 2 个下载器失败
        )

    async def probe_sync(downloader_info: Dict[str, Any]) -> Dict[str, Any]:
        did = str(downloader_info["downloader_id"])
        nickname = str(downloader_info.get("nickname", "unknown"))
        await torrents_async.qb_add_torrents_info_only_async(
            _empty_db(),
            [_qb_downloader(did, nickname)],
            client=clients[did],
        )
        return {"status": "success", "message": "ok", "nickname": nickname}

    task = TorrentInfoSyncTask()
    vos = [
        SimpleNamespace(
            downloader_id=f"dl-{i}",
            nickname=f"qb-{i}",
            host="localhost",
            port=8080,
            username="admin",
            password="secret",
            downloader_type=0,
            torrent_save_path="/downloads",
        )
        for i in range(1, 5)
    ]
    result = await task.execute_sync_with_concurrency(
        downloaders=vos,
        sync_func=probe_sync,
        sync_type="TorrentInfo",
        max_concurrent=4,
    )

    # 结果标记 partial：3 成功 + 1 失败，不阻塞其他下载器
    assert result["status"] == "partial", f"应标记 partial: {result}"
    assert result["successful_syncs"] == 3
    assert result["failed_syncs"] == 1
    assert result["total_downloaders"] == 4

    # 3 个成功下载器的 50 行全部经真实流水线（3 轮 × 1 次收尾写入）
    assert bulk_state["calls"] == 3, f"成功下载器 flush 次数异常: {bulk_state['calls']}"
    assert sum(bulk_state["sizes"]) == 150, f"成功下载器处理行数异常: {sum(bulk_state['sizes'])}"


# =============================================================================
# 5. qB RID 增量捷径完整性保护（顺序判定已正确，测试证明）
# =============================================================================


def _patch_incremental_run_config(monkeypatch) -> None:
    """qB 增量路径运行参数打点：最近全量时间戳 + 空 RID 缓存。"""
    _patch_info_run_config(monkeypatch)
    monkeypatch.setattr(torrents_async, "QB_USE_INCREMENTAL_SYNC", True)
    monkeypatch.setattr(torrents_async, "_QB_LAST_FULL_SYNC", {"dl-1": time.time()})
    monkeypatch.setattr(torrents_async, "_QB_SYNC_RID_CACHE", {})
    # 阻止 RID 缓存落盘（避免污染仓库 CONFIG_PATH 下的真实缓存文件）
    monkeypatch.setattr(torrents_async, "_save_qb_rid_cache", lambda cache: None)


async def test_rid_confirmed_only_after_durable_commit(mem_db, monkeypatch):
    """成功路径：RID 只在全部 DB durable commit 之后确认（顺序无缺口）。

    【场景】增量（rid=100，上一已确认 rid=50）携带 2 个新增种子 + 1 个删除标记：
    - removed 标记（真实 bulk 写入，commit #1）在 fetch 阶段完成；
    - 主写入（新增 2 行，真实分批 commit）在 write 阶段完成；
    - _confirm_qb_sync_rid("dl-1", 100) 在最后 commit 之后调用。
    【断言】
    1. confirm 恰好调用一次，参数为 ("dl-1", 100)，且时刻 ≥ 全部 commit 时刻；
    2. RID 缓存已推进（下轮从 rid=100 增量）；
    3. 删除种子已标记 dr=1、新增种子已落库（数据与 RID 同时 durable）。
    """
    _patch_incremental_run_config(monkeypatch)
    # 上一轮已确认 RID=50 → 本轮走 sync_maindata 增量分支（该分支处理
    # torrents_removed；rid=0 初始化分支视作全量快照，不处理 removed）
    monkeypatch.setattr(torrents_async, "_QB_SYNC_RID_CACHE", {"dl-1": 50})

    session = mem_db.factory()
    session.add(_qb_row("existing-1", "rh1"))
    await session.commit()

    # commit 时刻探针（在种子 commit 之后打点，避免把铺垫计入）
    real_commit = session.commit
    commits: List[float] = []

    async def recording_commit():
        commits.append(time.monotonic())
        return await real_commit()

    monkeypatch.setattr(session, "commit", recording_commit)

    # confirm 间谍：记录调用（时刻 + 参数），并调用真实实现（缓存推进）
    confirm_calls: List[tuple] = []
    real_confirm = torrents_async._confirm_qb_sync_rid

    def recording_confirm(downloader_id: str, rid: int) -> None:
        confirm_calls.append((downloader_id, rid, time.monotonic()))
        real_confirm(downloader_id, rid)

    monkeypatch.setattr(torrents_async, "_confirm_qb_sync_rid", recording_confirm)

    delta = [_qb_seed("ha", "alpha"), _qb_seed("hb", "beta")]
    client = _make_qb_client(
        seeds=delta,
        sync_payload=_qb_sync_payload(rid=100, seeds=delta, removed=["rh1"]),
    )

    await torrents_async.qb_add_torrents_info_only_async(session, [_qb_downloader()], client=client)

    # 1) confirm 在全部 durable commit 之后，且恰好一次
    assert len(confirm_calls) == 1, f"confirm 应恰好调用一次: {confirm_calls}"
    assert confirm_calls[0][:2] == ("dl-1", 100)
    assert commits, "增量写入应发生真实 DB commit"
    assert confirm_calls[0][2] >= max(commits), (
        f"RID 应在全部 durable commit 之后确认: confirm={confirm_calls[0][2]:.6f} " f"last_commit={max(commits):.6f}"
    )

    # 2) RID 缓存已推进（下轮从 100 增量）
    assert torrents_async._QB_SYNC_RID_CACHE.get("dl-1") == 100

    # 3) 数据与 RID 同时 durable：removed 已标记、新增已落库
    removed_row = (await session.execute(select(TorrentInfo).where(TorrentInfo.hash == "rh1"))).scalar_one()
    assert removed_row.dr == 1, "增量 removed 种子应标记 dr=1"
    alive_count = (
        await session.execute(select(func.count()).select_from(TorrentInfo).where(TorrentInfo.dr == 0))
    ).scalar()
    assert alive_count == 2, f"新增种子应全部落库（dr=0 共 2 行），实际 {alive_count}"
    await session.close()


async def test_rid_not_confirmed_when_commit_fails(mem_db, monkeypatch):
    """失败路径：DB durable commit 抛异常 → RID 不被确认（无顺序缺口）。

    模拟"增量成功但 DB 写失败"的缺口场景：commit 抛异常 → bulk_upsert 上抛
    → info-only 回滚后上抛 → _confirm_qb_sync_rid 未被调用、RID 缓存保持
    空——下轮从上一已确认 RID 重新对账，不丢数据。
    """
    _patch_incremental_run_config(monkeypatch)

    session = mem_db.factory()

    async def failing_commit():
        raise RuntimeError("模拟 commit 失败")

    monkeypatch.setattr(session, "commit", failing_commit)

    confirm_calls: List[tuple] = []
    monkeypatch.setattr(torrents_async, "_confirm_qb_sync_rid", lambda d, r: confirm_calls.append((d, r)))

    delta = [_qb_seed("ha", "alpha"), _qb_seed("hb", "beta")]
    client = _make_qb_client(seeds=delta, sync_payload=_qb_sync_payload(rid=100, seeds=delta))

    try:
        with pytest.raises(RuntimeError, match="模拟 commit 失败"):
            await torrents_async.qb_add_torrents_info_only_async(session, [_qb_downloader()], client=client)

        # 1) commit 失败 → 不确认 RID（与缓存状态一致：下轮重新对账）
        assert confirm_calls == [], f"commit 失败时不应确认 RID: {confirm_calls}"
        assert torrents_async._QB_SYNC_RID_CACHE.get("dl-1") is None, "RID 缓存不应推进"

        # 2) 失败事务已回滚：无任何残留行
        count = (await session.execute(select(func.count()).select_from(TorrentInfo))).scalar()
        assert count == 0, f"失败写入不应落库: {count}"
    finally:
        await session.rollback()
        await session.close()


async def test_incremental_failure_falls_back_to_paged_full_sync(monkeypatch):
    """异常回退：增量捷径失败 → 降级 torrents_info 分页全量，仍受单轮预算限制。

    【场景】sync_maindata 抛异常 → incremental_failed=True、pending_rid=None
    → 回退分页全量（qb_torrents_info_only）→ 单轮数量预算 100 → 只处理 100
    个种子（budget_reason=count、partial=True）。
    【断言】
    1. 回退告警日志存在（"incremental failed, fallback to batch"）；
    2. 回退走分页全量（fetch 调用 operation=qb_torrents_info_only，≥2 次）；
    3. 回退受单轮预算限制（插入 100、partial=True、budget_reason=count）；
    4. 不确认 RID（pending_rid 已被清空，缓存保持空）。
    """
    _patch_incremental_run_config(monkeypatch)
    monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 100)

    bulk_state: Dict[str, Any] = {"active": 0, "peak": 0, "calls": 0, "sizes": []}
    monkeypatch.setattr(torrents_async, "bulk_upsert_with_retry", _make_recording_bulk(bulk_state))

    confirm_calls: List[tuple] = []
    monkeypatch.setattr(torrents_async, "_confirm_qb_sync_rid", lambda d, r: confirm_calls.append((d, r)))

    client = _make_qb_client(seeds=_qb_seeds(500, prefix="f"), sync_maindata_raises=True)
    db = _empty_db()

    with (
        patch.object(torrents_async.logger, "info") as mock_info,
        patch.object(torrents_async.logger, "warning") as mock_warning,
    ):
        await torrents_async.qb_add_torrents_info_only_async(db, [_qb_downloader()], client=client)

    # 1) 回退告警日志存在
    fallback_warnings = [
        str(c) for c in mock_warning.call_args_list if "incremental failed, fallback to batch" in str(c)
    ]
    assert fallback_warnings, "缺少增量失败回退告警日志"

    # 2) 回退走分页全量（500 种子 / QB_BATCH_SIZE → ≥2 次 fetch 调用）
    fetch_ops = [rec for rec in CALL_RECORD if rec[0] == "qb_torrents_info_only"]
    assert len(fetch_ops) >= 2, f"回退应走分页全量 fetch: {len(fetch_ops)}"
    assert len(CALL_RECORD) == len(fetch_ops), "回退路径不应再触发增量调用"

    # 3) 回退受单轮预算限制：只处理 100 个种子（budget_reason=count）
    text = _completion_log(mock_info, "[QB_INFO_SYNC]")
    assert "插入 100" in text
    assert "partial=True" in text
    assert "budget_reason=count" in text
    assert sum(bulk_state["sizes"]) == 100, f"回退写入行数应受预算限制: {sum(bulk_state['sizes'])}"

    # 4) 不确认 RID：增量失败清空 pending_rid，缓存保持空
    assert confirm_calls == [], f"增量失败回退不应确认 RID: {confirm_calls}"
    assert torrents_async._QB_SYNC_RID_CACHE.get("dl-1") is None
    # 回退完成后记录全量时间戳（下一轮按增量调度）
    assert torrents_async._QB_LAST_FULL_SYNC.get("dl-1") is not None
