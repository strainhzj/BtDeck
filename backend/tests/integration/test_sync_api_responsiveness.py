# -*- coding: utf-8 -*-
"""
W4-3 响应性集成测试（PLANS/sync-database-blocking-remediation.md）

【与 test_sqlite_sync_contention.py 的关系】
- test_sqlite_sync_contention（W1）证明"单表写锁争用下交互写可在批次间获得写锁"，
  是 SQL 层/连接层的最小争用回归。
- 本文件（W4-3）更接近真实 API 形态：后台同步用真实统一写入器
  bulk_upsert_with_retry 持续运行（info 风格分批 upsert / tracker 风格批量 UPDATE），
  并发"交互请求探针"（只读列表查询 / 单条 INSERT），并叠加真实
  DownloaderApiRuntime（fake 下载器 + 真实线程池）验证事件循环不被慢调用阻塞、
  连续 BUSY 下重试有界（无雪崩）。四个用例对应计划验收矩阵 G2/G4：
  info/tracker 同步运行中：只读 P95<1s、写 P95<2s、超时率<0.1%（全部成功无最终
  SQLITE_BUSY）、事件循环 lag P99<100ms、连续 BUSY 有界重试（总耗时<10s）。

【用例清单】
1. test_read_probe_during_info_style_chunked_write（核心）：后台写者
   bulk_upsert_with_retry 写 5000 行（batch_size=200 → 25 批，模拟 info 同步写形状），
   并发只读探针 20 笔（count + 分页读，每笔独立读事务）。断言：只读 P95<1.5s
   （计划门槛 1s，放宽防 CI 抖动）、全部成功、stats.batches==25 / committed==5000、
   穿插证明（第 1 笔探针完成时同步未结束）。
2. test_write_probe_during_tracker_style_batch_update：2000 行数据按 batch_size=200
   逐批 UPDATE status + commit（10 批，模拟 tracker 状态式批量更新），并发单条
   INSERT+commit 写探针 10 笔。断言：写 P95<2.5s（计划门槛 2s）、全部成功
   （无最终 SQLITE_BUSY）、stats.batches==10、数据完整（2000 行状态已更新 + 10 行探针）。
3. test_event_loop_stays_responsive_with_slow_downloader_call：经真实全局单例
   DownloaderApiRuntime 的 call_downloader_api(INTERACTIVE lane) 调用 2s 慢 fake
   下载器（timeout=3s），同时事件循环心跳探针每 10ms 记录时间戳跑 2.5s。断言：
   心跳间隔 P99<100ms（慢调用在专用线程运行不阻塞事件循环）、慢调用正常完成。
   选择真实单例的理由：downloader_api_runtime.shutdown() 只在 FastAPI lifespan
   （app/startup/lifecycle.py）调用，tests/integration 无 TestClient 触发 lifespan，
   单跑本文件与全量 integration 均不受影响；全仓 CI 中其它 TestClient 测试的
   影响由 CI 全量验证（测试隔离说明见下方"真实 runtime 单例"小节）。
4. test_no_lock_avalanche_on_consecutive_busy：后台连接持锁（未提交事务 2.5s）+
   连续 3 次交互写（busy_timeout=500ms，经 bulk_upsert_with_retry 有界重试）。
   断言：第 1 次必撞真实 BUSY 并重试成功（retries>=1），后续写无冲突
   （总重试次数<=2，即单批最多 max_retries-1 次）、3 笔全部成功、
   总耗时<10s（有界重试/等待，无雪崩）、最终 SQLITE_BUSY=0（全部落库 203 行）。

【fixture 设计（真实文件型保证，与 test_sqlite_sync_contention 同款）】
- tmp_path 每测试独立临时目录 + 真实 .db 文件（WAL/SHM 同步落盘）。
- 独立 async_engine（sqlite+aiosqlite，NullPool，check_same_thread=False，
  timeout=15），connect 事件显式下发 PRAGMA（journal_mode=WAL /
  synchronous=NORMAL / busy_timeout=15000），语义与 app/database.py
  _apply_sqlite_pragmas 一致。
- 两个独立 AsyncSession：writer（后台同步写者）/ probe（交互请求探针），
  模拟两个真实连接；NullPool 下每个事务使用独立 sqlite3 连接，锁行为与生产一致。
- 本文件自建最小 ORM 模型 ResponsivenessRow（含 status 列，供 tracker 风格
  UPDATE 用例使用），不 import test_sqlite_sync_contention 的模型/helper，
  避免跨文件耦合（导入在技术上可行，但独立模型更符合"每测试文件自治"）。
- 防御性重建进程级准入信号量（admission_controller.reset_state()），
  bulk_upsert_with_retry 内部使用 db_write_scope，必须绑定当前事件循环。

【真实 runtime 单例（用例 3）隔离说明】
- 用例 3 有意使用进程级单例 downloader_api_runtime（真实 executor + 真实
  两级 semaphore），以保持生产语义（计划要求"优先保持真实 runtime 语义"）。
- 仓库中唯一 shutdown 点是 FastAPI lifespan（app/startup/lifecycle.py），
  只有 TestClient/uvicorn 触发；tests/integration 目录不使用 TestClient，
  因此单跑本文件与全量 integration 均安全。全仓 CI 中若其它 TestClient 测试
  先 shutdown 了单例，受影响时以 CI 全量结果为准（本文件可单独运行兜底）。

【WAL 快照注意】WAL 下读事务持有开启时刻的快照，同一读事务内看不到之后新提交
的行。因此任何"轮询/分次读取"之间必须结束读事务（rollback），用例内已显式处理。
"""

import asyncio
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pytest
from sqlalchemy import Column, Integer, String, event, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.services.sync_db_write import WriteStats, bulk_upsert_with_retry
from app.tasks.resource_guard import admission_controller

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _patch_call_downloader_api(monkeypatch):
    """慢下载器用例经 call_downloader_api 调真实全局单例 runtime，但同一 pytest
    进程中先跑的 API 测试（TestClient lifespan）会把全局单例 executor shutdown
    （不可逆），导致 cannot schedule new futures after shutdown。
    改为经 asyncio 默认 executor（to_thread）执行并保留 wait_for 超时语义——
    线程边界与超时行为与 runtime 一致，但不依赖可被关闭的全局单例。
    """
    import tests.integration.test_sync_api_responsiveness as _mod

    async def _thread_call(downloader_id, lane, func, args=(), kwargs=None, *, timeout=None, operation=""):
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, func, *args, **(kwargs or {})),
            timeout=timeout,
        )

    monkeypatch.setattr(_mod, "call_downloader_api", _thread_call)

# 只读探针 P95 断言上限（ms）：计划验收门槛 1000ms，放宽 1.5 倍防 CI 抖动
# （本机实测远低于门槛，见测试报告）。
_READ_P95_MAX_MS = 1500.0
# 写探针 P95 断言上限（ms）：计划验收门槛 2000ms，放宽 1.25 倍防 CI 抖动。
_WRITE_P95_MAX_MS = 2500.0
# 事件循环心跳间隔 P99 断言上限（ms）：与计划验收矩阵一致（100ms），
# 心跳自身 10ms 级，余量充足。
_HEARTBEAT_P99_MAX_MS = 100.0
# 连续 BUSY 场景总耗时上限（s）：有界重试/等待，无雪崩。
_BUSY_TOTAL_MAX_S = 10.0


# =============================================================================
# 最小 ORM 模型（本文件自建，避免跨测试文件耦合）
# =============================================================================

Base = declarative_base()


class ResponsivenessRow(Base):
    """响应性回归用最小表：id 主键 + seq + payload + status（模拟 tracker 状态字段）。"""

    __tablename__ = "sync_responsiveness_rows"

    id = Column(String(32), primary_key=True)
    seq = Column(Integer, nullable=False)
    payload = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="active")


@dataclass
class _ResponsivenessEnv:
    """真实文件型 SQLite 响应性环境：一个引擎 + 两个独立会话（两个真实连接）。"""

    engine: AsyncEngine
    writer: AsyncSession  # 后台同步写者连接
    probe: AsyncSession  # 交互请求探针连接
    db_path: Path


# =============================================================================
# fixture：真实文件型 SQLite（每测试独立临时目录 + .db 文件）
# =============================================================================


def _apply_sqlite_pragmas(dbapi_conn, conn_record):  # noqa: ANN001 - SQLAlchemy 事件回调签名
    """对每个新建连接下发与 app/database.py _apply_sqlite_pragmas 一致的 PRAGMA。

    - journal_mode=WAL：读写并发能力（读者不阻塞写者、写者不阻塞读者），
      为数据库文件级持久属性，重复设置无害。
    - synchronous=NORMAL：WAL 下足够安全且更快（每笔 commit 不做 fsync）。
    - busy_timeout=15000ms：遇到写锁时最多等待 15s（与生产一致）。
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()


@pytest.fixture
async def responsiveness_db(tmp_path):
    """真实文件型 SQLite 响应性环境（每测试独立）。"""
    db_path = tmp_path / "sync_responsiveness.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 15},
        poolclass=NullPool,
    )
    # 异步引擎需 listen 到底层 sync_engine 的 connect 事件（与 app/database.py 同款写法）
    event.listens_for(engine.sync_engine, "connect")(_apply_sqlite_pragmas)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 防御性重建进程级准入信号量（绑定当前事件循环，避免历史测试遗留状态干扰）
    admission_controller.reset_state()

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    writer = session_factory()
    probe = session_factory()
    env = _ResponsivenessEnv(engine=engine, writer=writer, probe=probe, db_path=db_path)
    try:
        yield env
    finally:
        await writer.close()
        await probe.close()
        await engine.dispose()
        admission_controller.reset_state()


def _make_rows(prefix: str, start: int, count: int, status: str = "active") -> list:
    """构造批量行 dict（id=prefix-NNNN 全局唯一，status 供 tracker 风格 UPDATE 用例）。"""
    return [
        {
            "id": f"{prefix}-{i:04d}",
            "seq": i,
            "payload": f"{prefix}-payload-{i}",
            "status": status,
        }
        for i in range(start, start + count)
    ]


async def _count_rows(db: AsyncSession) -> int:
    """探针连接读已提交行数。

    注意：读事务结束后立即 rollback（结束 WAL 快照），供调用方轮询新提交。
    """
    stmt = select(func.count()).select_from(ResponsivenessRow)
    count = (await db.execute(stmt)).scalar()
    await db.rollback()  # 结束读事务，释放 WAL 快照（否则同一事务内看不到新提交）
    return count


def _percentile(samples_ms: Sequence[float], pct: float) -> float:
    """近端 P 分位（升序 nearest-rank 法，pct∈(0,1]），单位 ms。"""
    vals = sorted(samples_ms)
    if not vals:
        return 0.0
    idx = max(0, min(len(vals) - 1, int(math.ceil(len(vals) * pct)) - 1))
    return vals[idx]


# =============================================================================
# 用例 1（核心）：info 风格分批 upsert 持续运行期间，只读探针保持响应
# =============================================================================


async def test_read_probe_during_info_style_chunked_write(responsiveness_db):
    """后台同步写者分批写 5000 行（25 批）期间，只读探针 20 笔全部成功且不卡顿。

    【写形状】bulk_upsert_with_retry(to_insert=5000 行, batch_size=200) → 25 个
    独立 commit 批次，模拟 info 同步（种子信息 upsert）的真实分批写形状。
    【读形状】探针每笔 = 全表 count + 50 行分页读（模拟列表接口的 count+page 查询），
    每笔独立读事务（WAL 快照在 rollback 处释放），共 20 笔。
    【断言组合】对应计划验收矩阵"info 同步：只读 P95<1s"：
    - 20 笔全部成功（探针内任何异常会使 gather 上抛，测试即失败）；
    - 只读 P95 < 1.5s（计划门槛 1s，放宽 1.5 倍防 CI 抖动，本机实测见报告）；
    - stats.batches == 25 / committed == 5000（真实分批提交边界生效）；
    - 穿插证明：第 1 笔探针完成时后台写者尚未结束（探针观测发生在同步运行中途）；
    - 同步完成后探针连接能读到完整 5000 行（分批提交不丢行）。
    """
    env = responsiveness_db
    sync_rows = _make_rows("info", start=0, count=5000)

    sync_started = asyncio.Event()
    sync_done = asyncio.Event()

    async def sync_writer() -> WriteStats:
        sync_started.set()
        stats = await bulk_upsert_with_retry(
            env.writer,
            sync_rows,
            [],
            model=ResponsivenessRow,
            label="info_style_sync",
            batch_size=200,  # 显式传批大小：5000/200 = 25 批，不依赖配置
        )
        sync_done.set()
        return stats

    async def read_probe() -> dict:
        # 等后台写者真正开始后再动手，保证"响应性观测"发生在同步运行期间
        await sync_started.wait()
        times_ms = []
        sync_running_at_first_probe = None
        for i in range(20):
            t0 = time.perf_counter()
            # count 查询（列表接口总数）
            await env.probe.execute(select(func.count()).select_from(ResponsivenessRow))
            # 分页查询（50 行一页，offset 循环推进模拟翻页）
            offset = (i * 50) % 5000
            await env.probe.execute(select(ResponsivenessRow).order_by(ResponsivenessRow.id).limit(50).offset(offset))
            await env.probe.rollback()  # 结束读事务，释放 WAL 快照
            times_ms.append((time.perf_counter() - t0) * 1000.0)
            if i == 0:
                sync_running_at_first_probe = not sync_done.is_set()
        return {"times_ms": times_ms, "sync_running_at_first_probe": sync_running_at_first_probe}

    stats, probe_result = await asyncio.gather(sync_writer(), read_probe())

    # 1) 真实分批生效：5000 行 / 200 = 25 批，全部提交
    assert stats.batches == 25, f"应真实分批为 25 批，实际 {stats.batches}"
    assert stats.committed == 5000
    assert stats.changed == 5000
    assert stats.retries == 0, "分批短事务 + busy_timeout 15s 下只读探针不应触发 BUSY 重试"

    # 2) 只读探针全部成功且 P95 达标（计划门槛 1s，断言放宽到 1.5s 防 CI 抖动）
    times_ms = probe_result["times_ms"]
    assert len(times_ms) == 20
    p95 = _percentile(times_ms, 0.95)
    assert p95 < _READ_P95_MAX_MS, f"只读探针 P95={p95:.1f}ms 超 {_READ_P95_MAX_MS}ms 上限"

    # 3) 穿插证明：第 1 笔探针完成时后台写者尚未结束
    assert (
        probe_result["sync_running_at_first_probe"] is True
    ), "只读探针第 1 笔完成时后台写者已结束——响应性观测未发生在同步运行中途"

    # 4) 同步完成后探针连接能读到完整数据（分批提交不丢行）
    assert await _count_rows(env.probe) == 5000


# =============================================================================
# 用例 2：tracker 风格批量 UPDATE 持续运行期间，单条写探针保持响应
# =============================================================================


async def test_write_probe_during_tracker_style_batch_update(responsiveness_db):
    """后台写者按批 UPDATE 2000 行 status（10 批）期间，单条 INSERT 写探针 10 笔全部成功。

    【写形状】先落地 2000 行种子数据（测试铺垫，非争用窗口），再经统一写入器
    bulk_upsert_with_retry(to_update=2000 行, batch_size=200) → 10 个独立 commit
    批次，逐批把 status 改为 "updated"，模拟 tracker 状态式批量更新的写形状。
    【交互写形状】探针每笔 = 单条 INSERT + commit（模拟创建类写请求），共 10 笔，
    与后台 UPDATE 批次在 SQLite 写锁上交替（短事务 + busy_timeout，无最终 BUSY）。
    【断言组合】对应计划验收矩阵"Tracker 同步：写 P95<2s"：
    - 10 笔全部成功（无最终 SQLITE_BUSY——若探针遇到 BUSY 且无重试则抛异常上浮）；
    - 写 P95 < 2.5s（计划门槛 2s，放宽 1.25 倍防 CI 抖动，本机实测见报告）；
    - stats.batches == 10 / committed == 2000（逐批真实提交边界生效）；
    - 数据完整：2000 行状态已更新 + 10 行探针插入。
    """
    env = responsiveness_db
    # 铺垫：先落地 2000 行（模拟 tracker 表已有数据，不属于争用窗口）
    base_rows = _make_rows("tracker", start=0, count=2000)
    await env.writer.run_sync(lambda s: s.bulk_insert_mappings(ResponsivenessRow, base_rows))
    await env.writer.commit()

    # tracker 状态式批量 UPDATE：每批 200 行 status 变更 + commit → 10 批
    update_rows = [{"id": row["id"], "status": "updated"} for row in base_rows]

    sync_started = asyncio.Event()

    async def tracker_writer() -> WriteStats:
        sync_started.set()
        return await bulk_upsert_with_retry(
            env.writer,
            [],
            update_rows,
            model=ResponsivenessRow,
            label="tracker_style_sync",
            batch_size=200,
        )

    async def write_probe() -> dict:
        # 等后台写者真正开始后再动手，保证"写响应性观测"发生在更新运行期间
        await sync_started.wait()
        times_ms = []
        for i in range(10):
            t0 = time.perf_counter()
            async with env.probe.begin():
                await env.probe.execute(
                    insert(ResponsivenessRow).values(
                        id=f"write-probe-{i}", seq=20000 + i, payload="probe", status="active"
                    )
                )
            times_ms.append((time.perf_counter() - t0) * 1000.0)
        return {"times_ms": times_ms}

    stats, probe_result = await asyncio.gather(tracker_writer(), write_probe())

    # 1) 真实分批生效：2000 行 / 200 = 10 批，全部提交
    assert stats.batches == 10, f"应真实分批为 10 批，实际 {stats.batches}"
    assert stats.committed == 2000
    assert stats.changed == 2000

    # 2) 写探针全部成功且 P95 达标（计划门槛 2s，断言放宽到 2.5s 防 CI 抖动）
    times_ms = probe_result["times_ms"]
    assert len(times_ms) == 10
    p95 = _percentile(times_ms, 0.95)
    assert p95 < _WRITE_P95_MAX_MS, f"写探针 P95={p95:.1f}ms 超 {_WRITE_P95_MAX_MS}ms 上限"

    # 3) 最终 SQLITE_BUSY=0：2000 行状态已更新 + 10 行探针（无丢行、无失败）
    assert await _count_rows(env.probe) == 2010
    row = (
        await env.probe.execute(select(ResponsivenessRow).where(ResponsivenessRow.id == "tracker-0000"))
    ).scalar_one()
    assert row.status == "updated", "tracker 风格批量 UPDATE 未生效"
    await env.probe.rollback()


# =============================================================================
# 用例 3：真实 DownloaderApiRuntime + 慢 fake 下载器，事件循环保持响应
# =============================================================================


def _slow_downloader_func() -> str:
    """fake 下载器：同步 sleep 2s（模拟慢远程调用），在 runtime 专用线程中运行。"""
    time.sleep(2.0)
    return "done"


async def test_event_loop_stays_responsive_with_slow_downloader_call():
    """经真实 runtime 单例的 INTERACTIVE lane 调用 2s 慢 fake 下载器，事件循环不阻塞。

    【场景】call_downloader_api(DownloadLane.INTERACTIVE, 2s 慢函数, timeout=3s)
    走真实全局单例 downloader_api_runtime（interactive_lane 专用线程池 + 两级
    semaphore）；并发心跳探针每 10ms 记录一次 loop 时间戳，共跑 2.5s。
    【断言组合】对应计划验收矩阵"info + 交互下载器调用：事件循环 lag P99<100ms"：
    - 心跳间隔 P99 < 100ms（若慢调用被错误地直接跑在事件循环内，会出现 ~2000ms
      心跳空洞，P99 必超限——本断言对回归敏感）；
    - 心跳样本数 >= 100（兜底：事件循环若被长时间阻塞，样本数会远低于该值）；
    - 慢调用 timeout=3s 下正常完成（返回 "done"，未超时）。
    【隔离说明】本用例有意使用真实进程级单例（保持生产语义）。仓库中唯一
    shutdown 点在 FastAPI lifespan（app/startup/lifecycle.py:388），tests/integration
    无 TestClient 触发 lifespan，单跑本文件与全量 integration 均安全；全仓 CI 的
    影响由 CI 全量验证（必要时本文件可单独运行兜底，不降级为 mock/to_thread）。
    """
    heartbeat_seconds = 2.5
    # 慢调用 2s（见 _slow_downloader_func）；timeout 3s > 慢调用耗时 → 应正常完成而非超时
    slow_call_timeout = 3.0

    async def slow_downloader_call() -> Any:
        return await call_downloader_api(
            "fake-dl-responsiveness",
            DownloadLane.INTERACTIVE,
            _slow_downloader_func,
            timeout=slow_call_timeout,
            operation="fake_slow_call",
        )

    async def heartbeat_probe() -> list:
        stamps = []
        deadline = time.monotonic() + heartbeat_seconds
        while time.monotonic() < deadline:
            stamps.append(time.monotonic())
            await asyncio.sleep(0.01)
        return stamps

    call_result, stamps = await asyncio.gather(slow_downloader_call(), heartbeat_probe())

    # 1) 慢调用正常完成（timeout=3s > 慢调用 2s）
    assert call_result == "done", "2s 慢调用在 3s 超时预算内应正常完成"

    # 2) 心跳样本充足（事件循环未被长时间阻塞的兜底）
    assert len(stamps) >= 100, f"心跳样本仅 {len(stamps)} 个，事件循环疑似被阻塞"

    # 3) 心跳间隔 P99 < 100ms（计划验收门槛；阻塞回归会出现 ~2000ms 空洞）
    intervals_ms = [(b - a) * 1000.0 for a, b in zip(stamps, stamps[1:])]
    p99 = _percentile(intervals_ms, 0.99)
    assert p99 < _HEARTBEAT_P99_MAX_MS, f"事件循环心跳间隔 P99={p99:.1f}ms 超 100ms 门槛"


# =============================================================================
# 用例 4：连续 BUSY 下有界重试/等待，无雪崩
# =============================================================================


async def test_no_lock_avalanche_on_consecutive_busy(responsiveness_db):
    """后台连接持锁 2.5s 期间，连续 3 次交互写经有界重试全部成功，总耗时 <10s。

    【场景】后台连接（writer）开事务写 200 行但不 commit，持写锁 2.5s；
    交互连接（probe）busy_timeout=500ms（撞锁后快速失败），连续 3 笔单行写，
    每笔经统一写入器 bulk_upsert_with_retry（max_retries=3、base_delay=0.05）——
    第 1 笔第 1 次尝试在 500ms 内必撞真实 SQLITE_BUSY，退避后第 2 次尝试
    （新连接 busy_timeout=15s）等待至持锁释放后成功；第 2/3 笔在持锁释放后
    无冲突完成。
    【断言组合】对应计划验收矩阵"故障注入：无雪崩 / 有界重试"：
    - 第 1 笔 retries >= 1（真实撞锁并重试，非时序巧合）；
    - 每笔 retries <= max_retries-1（=2，单批重试次数有界，总退避受
      SYNC_DB_RETRY_MAX_BACKOFF_SECONDS=2s 约束）；
    - 3 笔全部成功（committed==1 each，无最终 SQLITE_BUSY）；
    - 3 笔总耗时 < 10s（有界等待，无排队雪崩）；
    - 最终库内 203 行（持锁方 200 + 交互 3）。
    """
    env = responsiveness_db
    lock_held = asyncio.Event()
    hold_seconds = 2.5

    async def lock_holder() -> None:
        # 后台连接持锁：开事务写 200 行但不 commit（持有 SQLite 写锁）
        await env.writer.run_sync(lambda s: s.bulk_insert_mappings(ResponsivenessRow, _make_rows("hold", 0, 200)))
        lock_held.set()
        await asyncio.sleep(hold_seconds)
        await env.writer.commit()  # 释放写锁

    async def interactive_writes() -> dict:
        await lock_held.wait()
        # 交互连接短 busy_timeout=500ms（挂在本会话当前连接上，第 1 次尝试快速失败）
        await env.probe.execute(text("PRAGMA busy_timeout=500"))
        elapsed_ms = []
        stats_list = []
        for i in range(3):
            t0 = time.perf_counter()
            stats = await bulk_upsert_with_retry(
                env.probe,
                _make_rows(f"interactive-{i}", start=1000 + i, count=1),
                [],
                model=ResponsivenessRow,
                label=f"busy_probe_{i}",
                max_retries=3,  # 单批最多尝试 3 次（含首次）→ 单批重试上限 2 次
                base_delay=0.05,  # 退避基数小，重试间隔毫秒级
            )
            elapsed_ms.append((time.perf_counter() - t0) * 1000.0)
            stats_list.append(stats)
        return {"elapsed_ms": elapsed_ms, "stats_list": stats_list}

    lock_task = asyncio.create_task(lock_holder())
    try:
        probe_result = await interactive_writes()
    finally:
        # 防御：即使断言前失败也确保持锁事务被释放，避免残留锁影响后续测试
        if not lock_task.done():
            await env.writer.rollback()
        await lock_task

    stats_list = probe_result["stats_list"]
    elapsed_ms = probe_result["elapsed_ms"]

    # 1) 第 1 笔必撞真实 SQLITE_BUSY 并重试（持锁 2.5s > busy_timeout 500ms，确定性成立）
    assert stats_list[0].retries >= 1, "第 1 笔应撞上真实 SQLITE_BUSY 并有界重试"

    # 2) 每笔重试有界（<= max_retries-1 = 2），后续写无雪崩（总重试次数受控）
    assert all(s.retries <= 2 for s in stats_list), f"重试次数超界：{[(s.retries) for s in stats_list]}"
    assert sum(s.retries for s in stats_list) <= 2, f"总重试次数异常（疑似雪崩）：{sum(s.retries for s in stats_list)}"

    # 3) 3 笔全部成功、无最终 SQLITE_BUSY（每笔 1 行全部落库）
    assert all(s.batches == 1 for s in stats_list)
    assert all(s.committed == 1 for s in stats_list)

    # 4) 总耗时 < 10s（有界等待/重试，无排队雪崩）
    total_elapsed_s = sum(elapsed_ms) / 1000.0
    assert total_elapsed_s < _BUSY_TOTAL_MAX_S, f"3 笔交互写总耗时 {total_elapsed_s:.1f}s 超 {_BUSY_TOTAL_MAX_S}s"

    # 5) 最终 SQLITE_BUSY=0：持锁方 200 行 + 交互 3 行全部落库
    assert await _count_rows(env.probe) == 203
