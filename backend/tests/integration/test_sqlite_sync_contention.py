# -*- coding: utf-8 -*-
"""
W1-1 最小文件型 SQLite 争用回归（PLANS/sync-database-blocking-remediation.md）

【覆盖目标】用真实临时文件型 SQLite（不是内存库、不是 Mock、不是全局
app.database 引擎）证明：同步分批写入期间，交互（普通请求侧）写操作能
在批次间获得写锁——即 W1-1 的"每批独立 commit、批间让行"消除单大事务
对 SQLite 写锁的长时间持有。

【用例清单】
1. test_interactive_write_succeeds_during_chunked_sync（核心回归）：
   同步写者 bulk_upsert_with_retry 写 2000 行（batch_size=100 → 20 批），
   交互写者并发做 10 笔独立 INSERT，全部成功且每笔 < 5s（远小于
   busy_timeout 15s），stats.batches == 20 证明真实分批生效，两连接
   最终读到完整 2000 行（分批提交不丢行），并附"穿插证明"。
2. test_single_batch_commit_releases_lock_between_batches：短事务边界
   锁释放——事务 A 写 100 行 commit 后、事务 B 前，交互连接立即可见
   100 行（WAL 提交可见 + 写锁已释放）。与统一写入器解耦（见用例内
   设计意图说明）。
3. test_busy_retry_uses_error_codes_on_real_file_db：真实锁冲突错误码
   分类——A 持写锁未 commit，B（busy_timeout=200ms）INSERT 抛
   OperationalError 且 orig.sqlite_errorcode == 5（SQLITE_BUSY），
   _is_sqlite_lock_conflict() 返回 True；A commit 后 B 重试成功。
4. test_bulk_upsert_with_retry_recovers_on_real_file_busy：真实调用
   bulk_upsert_with_retry 在锁冲突下只重试当前批并最终成功（retries>=1，
   已提交统计正确）。
5. test_no_write_lock_held_when_no_changes：零变化同步（空 to_insert /
   to_update）返回零值 WriteStats、不 commit、不持锁；交互连接连续
   5 笔写全部无等待完成（每笔 < 1s）。结合 W1-2 语义（零变化零 DML）。
6. test_bulk_commit_p99_budget_on_22k_rows（@pytest.mark.performance，
   默认 skip）：22k 行分批基准，单批 commit P99 < 250ms，数据校准留给
   G1 压测，避免拖慢常规 CI。

【fixture 设计（真实文件型保证）】
- tmp_path 每测试独立临时目录 + 真实 .db 文件（WAL/SHM 同步落盘）。
- 独立 async_engine（sqlite+aiosqlite，NullPool，check_same_thread=False，
  timeout=15），connect 事件显式下发 PRAGMA（journal_mode=WAL /
  synchronous=NORMAL / busy_timeout=15000），语义与 app/database.py
  的 _apply_sqlite_pragmas 一致。
- 两个独立 AsyncSession（同步写者 / 交互写者），模拟两个真实连接；
  NullPool 下每个事务使用独立 sqlite3 连接，锁行为与生产一致。
- 不触碰 app.database 全局引擎，避免与进程级测试库纠缠。
- 使用本地最小 ORM 模型 SyncContentionRow，避免生产模型耦合。

【WAL 快照注意】WAL 下读事务持有开启时刻的快照，同一读事务内看不到
之后新提交的行。因此任何"轮询/分次读取"之间必须结束读事务
（commit/rollback），否则断言会读到过期快照——用例内已显式处理。
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String, event, func, insert, select, text
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from app.services.sync_db_write import WriteStats, _is_sqlite_lock_conflict, bulk_upsert_with_retry
from app.tasks.resource_guard import admission_controller

pytestmark = pytest.mark.integration

# 交互写单笔耗时上限（ms）：远小于 busy_timeout 15000ms。
# 若同步写者长时间独占写锁（回归场景），交互写会被迫等满整个同步，必然超限。
_INTERACTIVE_WRITE_MAX_MS = 5000.0
# 零变化同步下的交互写耗时上限（ms）：无任何锁竞争，应接近毫秒级。
_NO_CONTENTION_WRITE_MAX_MS = 1000.0


# =============================================================================
# 最小 ORM 模型（测试文件内自建，避免生产模型耦合）
# =============================================================================

Base = declarative_base()


class SyncContentionRow(Base):
    """争用回归用最小表：id 主键 + seq + payload。"""

    __tablename__ = "sync_contention_rows"

    id = Column(String(32), primary_key=True)
    seq = Column(Integer, nullable=False)
    payload = Column(String(64), nullable=False)


@dataclass
class _ContentionEnv:
    """真实文件型 SQLite 争用环境：一个引擎 + 两个独立会话（两个真实连接）。"""

    engine: AsyncEngine
    writer: AsyncSession  # 同步写者连接
    interactive: AsyncSession  # 交互写者连接
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
async def contention_db(tmp_path):
    """真实文件型 SQLite 争用环境（每测试独立）。"""
    db_path = tmp_path / "sync_contention.db"
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
    interactive = session_factory()
    env = _ContentionEnv(engine=engine, writer=writer, interactive=interactive, db_path=db_path)
    try:
        yield env
    finally:
        await writer.close()
        await interactive.close()
        await engine.dispose()
        admission_controller.reset_state()


def _make_rows(prefix: str, start: int, count: int) -> list:
    """构造批量行 dict（id=prefix-NNNN 全局唯一）。"""
    return [
        {"id": f"{prefix}-{i:04d}", "seq": i, "payload": f"{prefix}-payload-{i}"} for i in range(start, start + count)
    ]


async def _count_rows(db: AsyncSession, id_prefix: str = "") -> int:
    """交互连接读已提交行数；id_prefix 非空时按 id 前缀过滤。

    注意：读事务结束后立即 rollback（结束 WAL 快照），供调用方轮询新提交。
    """
    stmt = select(func.count()).select_from(SyncContentionRow)
    if id_prefix:
        stmt = stmt.where(SyncContentionRow.id.like(f"{id_prefix}-%"))
    count = (await db.execute(stmt)).scalar()
    await db.rollback()  # 结束读事务，释放 WAL 快照（否则同一事务内看不到新提交）
    return count


async def _interactive_insert(db: AsyncSession, row_id: str, seq: int, payload: str) -> float:
    """交互写者一笔独立写：BEGIN 事务 → INSERT → commit，返回耗时（ms）。"""
    t0 = time.perf_counter()
    async with db.begin():
        await db.execute(insert(SyncContentionRow).values(id=row_id, seq=seq, payload=payload))
    return (time.perf_counter() - t0) * 1000.0


# =============================================================================
# 用例 1：核心回归——同步分批写入期间，交互写在批次间获得写锁
# =============================================================================


async def test_interactive_write_succeeds_during_chunked_sync(contention_db):
    """同步写者分批写 2000 行（20 批）期间，交互写者 10 笔全部成功且不被阻塞。

    【回归意义】修复前（单大事务）同步会持续持有写锁直到全部写完，
    交互写只能靠 busy_timeout 排队；修复后每批独立 commit，交互写在
    批次间获得写锁。断言组合证明：
    - 10 笔交互写全部成功（无最终 SQLITE_BUSY）；
    - 每笔 < 5s（远小于 busy_timeout 15s，未等待整个同步）；
    - stats.batches == 20（真实分批提交边界生效）、committed == 2000；
    - 同步完成后两连接都能读到完整 2000 行（分批提交不丢行）；
    - 穿插证明：交互写第 1 笔完成时同步写者尚未结束。
    """
    env = contention_db
    sync_rows = _make_rows("sync", start=0, count=2000)

    sync_started = asyncio.Event()
    sync_done = asyncio.Event()

    async def sync_writer() -> WriteStats:
        sync_started.set()
        stats = await bulk_upsert_with_retry(
            env.writer,
            sync_rows,
            [],
            model=SyncContentionRow,
            label="chunked_sync",
            batch_size=100,  # 显式传批大小，不依赖配置
        )
        sync_done.set()
        return stats

    async def interactive_writer() -> dict:
        # 等同步写者真正开始后再动手，保证"穿插"不是发生在同步之前
        await sync_started.wait()
        times_ms = []
        sync_running_at_first_write = None
        rows_seen_before_first_write = None
        # 第 1 笔立即执行：此时同步写者最多完成第 1 批（19 批待写），
        # 第 1 笔完成时同步写者必然尚未结束（见穿插证明）。
        elapsed = await _interactive_insert(env.interactive, "interactive-0", 10000, "interactive")
        times_ms.append(elapsed)
        sync_running_at_first_write = not sync_done.is_set()
        # 等第 1 批（100 行）提交可见，进一步证明交互观测发生在同步运行中途
        deadline = time.monotonic() + 15.0
        while True:
            seen = await _count_rows(env.interactive)
            if seen >= 100:
                break
            assert time.monotonic() < deadline, "同步写者迟迟未提交第 1 批，分批写入疑似失效"
            await asyncio.sleep(0.005)
        rows_seen_before_first_write = seen
        # 其余 9 笔独立写
        for i in range(1, 10):
            elapsed = await _interactive_insert(env.interactive, f"interactive-{i}", 10000 + i, "interactive")
            times_ms.append(elapsed)
        return {
            "times_ms": times_ms,
            "sync_running_at_first_write": sync_running_at_first_write,
            "rows_seen_before_first_write": rows_seen_before_first_write,
        }

    stats, interactive_result = await asyncio.gather(sync_writer(), interactive_writer())

    # 1) 真实分批生效：2000 行 / 100 = 20 批，全部提交
    assert stats.scanned == 2000
    assert stats.batches == 20, f"应真实分批为 20 批，实际 {stats.batches}"
    assert stats.committed == 2000
    assert stats.changed == 2000
    # 交互写与同步写交替 commit，busy_timeout 15s 下不会触发 BUSY 重试
    assert stats.retries == 0

    # 2) 交互写 10 笔全部成功且每笔远小于 busy_timeout（未等待整个同步）
    times_ms = interactive_result["times_ms"]
    assert len(times_ms) == 10
    assert all(
        t < _INTERACTIVE_WRITE_MAX_MS for t in times_ms
    ), f"交互写存在阻塞：{times_ms}（上限 {_INTERACTIVE_WRITE_MAX_MS}ms）"

    # 3) 穿插证明：交互写第 1 笔完成时同步写者尚未结束
    assert (
        interactive_result["sync_running_at_first_write"] is True
    ), "交互写第 1 笔完成时同步写者已结束——穿插未发生，分批提交疑似未生效"
    # 4) 第 1 批提交对交互连接可见（批间获得读/写机会的旁证）
    assert interactive_result["rows_seen_before_first_write"] >= 100

    # 5) 同步完成后两连接都能读到完整数据（分批提交不丢行）
    for db in (env.writer, env.interactive):
        assert await _count_rows(db) == 2010, "交互连接应读到 2000 行同步 + 10 行交互"
        assert await _count_rows(db, id_prefix="sync") == 2000, "同步行缺失（分批提交丢行）"


# =============================================================================
# 用例 2：批次边界锁释放——短事务 commit 后，交互连接立即可见已提交批
# =============================================================================


async def test_single_batch_commit_releases_lock_between_batches(contention_db):
    """短事务（100 行）commit 后、下一批事务前，交互连接能读到已提交的 100 行。

    【设计意图】本用例验证"短事务释放写锁 + WAL 提交立即可见"这一物理
    事实，因此不调用 bulk_upsert_with_retry（其批次边界由循环内部驱动、
    不可从外部精确插入观测点），而是直接模拟它的批处理结构——两个短事务
    A/B 各写 100 行并独立 commit，与统一写入器解耦。事件协议（无任何
    时间断言）保证每个观测点精确落在事务边界上，完全确定性：
    - 事务 A 打开未提交 → 交互连接 SELECT 看到 0 行且不被阻塞
      （WAL 快照隔离：未提交行不可见，读者不等待写者）；
    - 事务 A commit 后 → 交互连接 SELECT 看到 100 行（提交边界真实、
      写锁已释放）；
    - 事务 B commit 后 → 交互连接 SELECT 看到 200 行。
    """
    env = contention_db
    txn_a_open = asyncio.Event()
    a_open_checked = asyncio.Event()
    a_committed = asyncio.Event()
    a_visible_checked = asyncio.Event()
    b_committed = asyncio.Event()
    b_visible_checked = asyncio.Event()
    reads = []

    async def txn_ab_runner():
        # 事务 A：写 100 行（不 commit，持有写锁）
        await env.writer.run_sync(lambda s: s.bulk_insert_mappings(SyncContentionRow, _make_rows("batch-a", 0, 100)))
        txn_a_open.set()
        await a_open_checked.wait()
        # 事务 A commit（模拟"第 1 批提交"，写锁释放）
        await env.writer.commit()
        a_committed.set()
        await a_visible_checked.wait()
        # 事务 B：写 100 行并 commit（模拟"第 2 批提交"）
        await env.writer.run_sync(lambda s: s.bulk_insert_mappings(SyncContentionRow, _make_rows("batch-b", 100, 100)))
        await env.writer.commit()
        b_committed.set()
        await b_visible_checked.wait()

    async def interactive_reader():
        # 读 1：事务 A 打开未提交——WAL 快照看不到未提交行（0 行），且不阻塞
        await txn_a_open.wait()
        reads.append(await _count_rows(env.interactive))
        a_open_checked.set()
        # 读 2：事务 A 已 commit——新读事务立即可见 100 行（写锁已释放）
        await a_committed.wait()
        reads.append(await _count_rows(env.interactive))
        a_visible_checked.set()
        # 读 3：事务 B 已 commit——200 行
        await b_committed.wait()
        reads.append(await _count_rows(env.interactive))
        b_visible_checked.set()

    await asyncio.gather(txn_ab_runner(), interactive_reader())

    # 0（未提交不可见）→ 100（第 1 批提交后立即可见）→ 200（第 2 批提交后）
    assert reads == [0, 100, 200], f"批次边界可见性异常：{reads}"
    assert await _count_rows(env.interactive) == 200


# =============================================================================
# 用例 3：真实锁冲突的错误码分类（SQLITE_BUSY=5）与释放后重试
# =============================================================================


async def test_busy_retry_uses_error_codes_on_real_file_db(contention_db):
    """真实文件库：连接 A 持写锁未 commit，连接 B（短 busy_timeout）写失败。

    - B 抛 SQLAlchemy OperationalError，orig.sqlite_errorcode == 5
      （SQLITE_BUSY）——证明错误码分类在真实文件库上成立（非 Mock）；
    - _is_sqlite_lock_conflict(exc) 返回 True（错误码集合命中）；
    - A commit 释放锁后，B 重试同一行 INSERT 成功。
    """
    env = contention_db
    # A：开启事务写 100 行但不 commit（持有 SQLite 写锁）
    await env.writer.run_sync(lambda s: s.bulk_insert_mappings(SyncContentionRow, _make_rows("hold", 0, 100)))
    # B：把本连接 busy_timeout 调小到 200ms（生产为 15s），让锁冲突快速暴露
    await env.interactive.execute(text("PRAGMA busy_timeout=200"))

    with pytest.raises(SAOperationalError) as exc_info:
        await env.interactive.execute(insert(SyncContentionRow).values(id="probe-1", seq=1, payload="probe"))
    orig = exc_info.value.orig
    assert (
        getattr(orig, "sqlite_errorcode", None) == 5
    ), f"应为 SQLITE_BUSY(5)，实际 {getattr(orig, 'sqlite_errorcode', None)}"
    assert getattr(orig, "sqlite_errorname", None) == "SQLITE_BUSY"
    assert _is_sqlite_lock_conflict(exc_info.value) is True

    # 清理 B 的失败事务状态（否则后续语句触发 PendingRollbackError）
    await env.interactive.rollback()

    # A commit 释放写锁后，B 重试同一行 INSERT 成功
    await env.writer.commit()
    await env.interactive.execute(insert(SyncContentionRow).values(id="probe-1", seq=1, payload="probe"))
    await env.interactive.commit()

    assert await _count_rows(env.interactive) == 101  # A 的 100 行 + B 重试的 1 行


async def test_bulk_upsert_with_retry_recovers_on_real_file_busy(contention_db):
    """真实文件库：锁冲突期间真实调用 bulk_upsert_with_retry，只重试当前批并最终成功。

    B 在 A 持有写锁期间调用 bulk_upsert_with_retry 单批（100 行）：
    - 第 1 次尝试 commit 遇 SQLITE_BUSY（B 连接 busy_timeout=200ms）；
    - 有限退避后重试，A commit 释放锁 → 重试批成功；
    - stats.retries >= 1、batches == 1、committed == 100（统计正确，
      不丢行、不重复提交）。
    """
    env = contention_db
    # A：开启事务写 100 行但不 commit（持有写锁）
    await env.writer.run_sync(lambda s: s.bulk_insert_mappings(SyncContentionRow, _make_rows("hold", 0, 100)))

    # B：短 busy_timeout=200ms（挂在本会话当前连接上，供第 1 次尝试快速失败）
    await env.interactive.execute(text("PRAGMA busy_timeout=200"))

    async def busy_writer() -> WriteStats:
        return await bulk_upsert_with_retry(
            env.interactive,
            _make_rows("retry", 1000, 100),
            [],
            model=SyncContentionRow,
            label="real_busy_retry",
            batch_size=100,
            max_retries=5,  # 给足尝试次数，避免 CI 调度抖动
            base_delay=0.05,  # 退避基数小，重试间隔毫秒级
        )

    task = asyncio.create_task(busy_writer())
    # 让 B 第 1 次尝试先撞上锁冲突（busy_timeout=200ms 内必然失败），
    # 再释放锁让重试批成功：窗口 (200ms, 第 2 次尝试超时) 内 commit 即可
    await asyncio.sleep(0.35)
    await env.writer.commit()  # 释放写锁
    stats = await task

    assert stats.retries >= 1, "B 第 1 次尝试应撞上真实 SQLITE_BUSY 并重试"
    assert stats.batches == 1
    assert stats.committed == 100
    assert stats.changed == 100
    assert await _count_rows(env.interactive) == 200  # A 的 100 + B 重试成功的 100


# =============================================================================
# 用例 4：零变化同步不产生写锁（W1-2 语义：零变化零 DML）
# =============================================================================


async def test_no_write_lock_held_when_no_changes(contention_db):
    """空 to_insert/to_update 的同步写者：零值 WriteStats、不 commit、不持锁。

    与交互连接 5 笔独立写并发执行，全部无等待完成（每笔 < 1s）——
    证明零变化同步不产生任何写锁竞争；库中最终只有交互写的 5 行。
    """
    env = contention_db

    async def noop_sync() -> WriteStats:
        return await bulk_upsert_with_retry(env.writer, [], [], model=SyncContentionRow, label="noop_sync")

    async def interactive_writer() -> list:
        times_ms = []
        for i in range(5):
            elapsed = await _interactive_insert(env.interactive, f"noop-write-{i}", 20000 + i, "interactive")
            times_ms.append(elapsed)
        return times_ms

    stats, times_ms = await asyncio.gather(noop_sync(), interactive_writer())

    # 零值 WriteStats：不扫描、不写、不 commit、不进 db_write_scope
    assert stats.scanned == 0
    assert stats.changed == 0
    assert stats.committed == 0
    assert stats.batches == 0
    assert stats.retries == 0
    assert stats.elapsed_ms == 0.0

    # 交互写全部无等待完成
    assert all(t < _NO_CONTENTION_WRITE_MAX_MS for t in times_ms), f"交互写出现等待：{times_ms}"

    # 库中只有交互写的 5 行（零变化同步未写任何行）
    assert await _count_rows(env.interactive) == 5


# =============================================================================
# 可选：22k 行分批基准（数据校准留给 G1 压测，常规 CI 默认跳过）
# =============================================================================


@pytest.mark.performance
@pytest.mark.skip(reason="单批 commit P99 数据校准留给 G1 压测（scripts/sync_contention_benchmark.py），常规 CI 不执行")
async def test_bulk_commit_p99_budget_on_22k_rows(contention_db):
    """22k 行分批写：单批 commit P99 < 250ms（W1-1 G1 验收门槛）。

    手动短事务逐批计时（批次边界完全受控），批大小 500 → 44 批。
    """
    env = contention_db
    rows = _make_rows("perf", start=0, count=22000)
    commit_ms = []
    for start in range(0, len(rows), 500):
        await env.writer.run_sync(lambda s: s.bulk_insert_mappings(SyncContentionRow, rows[start : start + 500]))
        t0 = time.perf_counter()
        await env.writer.commit()
        commit_ms.append((time.perf_counter() - t0) * 1000.0)

    commit_ms.sort()
    p99 = commit_ms[int(len(commit_ms) * 0.99) - 1]
    assert p99 < 250.0, f"单批 commit P99={p99:.1f}ms 超过 250ms 门槛"
    assert await _count_rows(env.interactive) == 22000
