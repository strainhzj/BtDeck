#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
W4-3 真实文件型 SQLite 争用基准（PLANS/sync-database-blocking-remediation.md）

【定位】与 scripts/sync_resource_benchmark.py（内存 SQLite + mock 的治理层压测）
互补：本脚本用【真实临时文件型 SQLite + 生产近似数据量 + 后台真实 DML +
可控延迟 fake 下载器 + 故障注入】暴露 WAL/fsync/索引更新/锁等待/真实并发
请求的组合问题（P1-07），作为 CI nightly / 发布门基准与前后版本对比工具。

【场景】
- 0_baseline: 无同步基线（仅请求探针，对应验收矩阵"无同步基线"行）。
- A_info_upsert: info 式分批 upsert（真实 bulk_upsert_with_retry，batch 200）。
- B_tracker_status: tracker 状态式增量写（真实 sync_tracker_status_from_keywords：
  第 1 遍全量判定写回、第 2 遍验证零变化零 DML）。
- C_qb_removed_mark: qB removed 式标记更新（批量 UPDATE dr=1，逐批 commit + 有界重试）。

【请求探针】只读 count / 分页 / 任务状态 + 单条 INSERT / UPDATE dr=1，
每探针独立连接（NullPool），与后台 DML 并发运行；--probe-iterations 控制轮数。

【fake 下载器】slow_func(time.sleep(delay)) 经 call_downloader_api 真实调用
（lane executor + 两级 semaphore + wait_for 超时路径，不跳过网络阶段）；
--downloader-delay-ms 默认 0 关闭。

【故障注入】--fault busy / slow-downloader / cancel，断言"可解释降级、无雪崩"。

【输出】stdout 表格 + backend/benchmark_results/sync_contention_<ts>.json
（JSON 仅含合成数据，无任何敏感信息）。

【SLO 发布门】--assert-slo：大档只读 P95<1s、写 P95<2s、超时率<0.1%、
最终 SQLITE_BUSY 失败=0；不满足 exit 1 并输出失败诊断。

详见 docs/operations/sync-contention-runbook.md。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime
from itertools import zip_longest
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

# 确保能 import app 包（脚本位于 backend/scripts/）
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import (  # noqa: E402
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    event,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.exc import OperationalError as SAOperationalError  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.downloader_api_runtime import (  # noqa: E402
    DownloadLane,
    call_downloader_api,
)
from app.services.sync_db_write import (  # noqa: E402
    WriteStats,
    _is_sqlite_lock_conflict,
    bulk_upsert_with_retry,
)
from app.services.tracker_status_sync import sync_tracker_status_from_keywords  # noqa: E402
from app.tasks.resource_guard import admission_controller  # noqa: E402

# =============================================================================
# 常量
# =============================================================================

# 数据规模档：（torrents, trackers），大档对应生产 22k torrents / 30k trackers
SIZES: Dict[str, Tuple[int, int]] = {
    "small": (2000, 3000),
    "medium": (10000, 15000),
    "large": (22000, 30000),
}

# 统一写入批大小（与 settings.SYNC_DB_COMMIT_BATCH_SIZE 生产默认一致，显式传入）
BATCH_SIZE = 200
# 单探针 DB 操作超时（秒）：busy_timeout=15s 之下的合理请求预算，超限计为探针超时
PROBE_TIMEOUT_S = 15.0
# 后台 DML 持锁等待（生产 busy_timeout，与 app/database.py 语义一致）
DB_BUSY_TIMEOUT_MS = 15000
# 故障 busy 时后台 DML 的短 busy_timeout（制造真实 SQLITE_BUSY 错误码路径）
FAULT_BUSY_DML_TIMEOUT_MS = 100
# 事件循环 lag 采样间隔（秒）
LAG_SAMPLE_INTERVAL_S = 0.01

# SLO 发布门阈值（大档，验收矩阵"info/Tracker 同步"行）
SLO_READ_P95_MS = 1000.0
SLO_WRITE_P95_MS = 2000.0
SLO_TIMEOUT_RATE = 0.001  # 0.1%
SLO_FINAL_BUSY_FAILURES = 0

# 场景 A 注入行数下限（保障 cancel 故障的取消窗口；大档为 n/10）
SCN_A_INSERT_MIN = 2000

# =============================================================================
# 最小 ORM 模型（基准专用 Base，与生产模型解耦）
# =============================================================================

Base = declarative_base()


class BenchTorrent(Base):
    """基准用最小 torrent 表：id 主键 + 少量列 + 索引（模拟生产写入形状）。"""

    __tablename__ = "bench_torrent"
    __table_args__ = (
        Index("ix_bench_torrent_dr", "dr"),
        Index("ix_bench_torrent_downloader", "downloader_id"),
    )

    id = Column(String(64), primary_key=True)
    downloader_id = Column(String(32), nullable=False)
    seq = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    size = Column(Integer, nullable=False)
    progress = Column(Float, nullable=False, default=0.0)
    dr = Column(Integer, nullable=False, default=0)
    payload = Column(String(128), nullable=False)


class BenchTracker(Base):
    """基准用最小 tracker 表：表名/列名与生产 tracker_info 对齐（真实服务可调用）。"""

    __tablename__ = "tracker_info"
    __table_args__ = (Index("ix_bench_tracker_host", "tracker_host"),)

    tracker_id = Column(String(64), primary_key=True)
    tracker_url = Column(String(256), nullable=False)
    last_announce_msg = Column(String(256), nullable=False, default="")
    last_scrape_msg = Column(String(256), nullable=False, default="")
    tracker_host = Column(String(128), nullable=False, default="")
    status = Column(String(32), nullable=False, default="")
    msg = Column(String(32), nullable=False, default="")
    update_time = Column(DateTime, nullable=True)
    dr = Column(Integer, nullable=False, default=0)


class BenchKeyword(Base):
    """基准用最小关键词配置表：列与生产 tracker_keyword_config 对齐（真实服务读取）。"""

    __tablename__ = "tracker_keyword_config"

    keyword_id = Column(Integer, primary_key=True, autoincrement=True)
    keyword_type = Column(String(32), nullable=False)
    keyword = Column(String(64), nullable=False)
    language = Column(String(16), nullable=False, default="zh")
    priority = Column(Integer, nullable=False, default=0)
    enabled = Column(Integer, nullable=False, default=1)
    category = Column(String(64), nullable=False, default="")
    description = Column(String(256), nullable=False, default="")
    create_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=True)
    create_by = Column(String(32), nullable=False, default="")
    update_by = Column(String(32), nullable=False, default="")
    dr = Column(Integer, nullable=False, default=0)


# =============================================================================
# 基础设施：真实文件型 SQLite 环境
# =============================================================================


@dataclass
class _BenchEnv:
    """真实文件型 SQLite 基准环境（独立临时目录 + .db + WAL）。"""

    tmpdir: Path
    db_path: Path
    engine: AsyncEngine
    session_factory: async_sessionmaker
    busy_counter: Dict[str, int] = field(default_factory=lambda: {"count": 0})


def _apply_sqlite_pragmas(dbapi_conn, conn_record):  # noqa: ANN001 - SQLAlchemy 事件回调签名
    """对每个新连接下发与 app/database.py _apply_sqlite_pragmas 一致的 PRAGMA。

    - journal_mode=WAL：读写并发（文件级持久属性，重复设置无害）。
    - synchronous=NORMAL：WAL 下足够安全且更快。
    - busy_timeout=15000ms：写锁竞争时最多等待 15s（与生产一致）。
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()


def _make_busy_counter() -> Tuple[Dict[str, int], Callable[[Any], None]]:
    """构造 SQLITE_BUSY 计数（handle_error 事件层计数，真实错误码路径）。"""
    counter: Dict[str, int] = {"count": 0}

    def _on_handle_error(context: Any) -> None:
        exc = getattr(context, "original_exception", None) or getattr(context, "exception", None)
        if getattr(exc, "sqlite_errorcode", None) == 5 or getattr(exc, "sqlite_errorname", None) == "SQLITE_BUSY":
            counter["count"] += 1

    return counter, _on_handle_error


async def _make_env() -> _BenchEnv:
    """创建独立临时目录 + 真实 .db（WAL + NullPool + busy_timeout=15s）。"""
    tmpdir = Path(tempfile.mkdtemp(prefix="sync_contention_bench_"))
    db_path = tmpdir / "bench.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 15},
        poolclass=NullPool,
    )
    event.listens_for(engine.sync_engine, "connect")(_apply_sqlite_pragmas)
    busy_counter, on_err = _make_busy_counter()
    event.listens_for(engine.sync_engine, "handle_error")(on_err)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _BenchEnv(tmpdir=tmpdir, db_path=db_path, engine=engine, session_factory=factory, busy_counter=busy_counter)


def _wal_bytes(db_path: Path) -> int:
    """WAL 文件字节数（不存在时为 0）。"""
    wal = Path(f"{db_path}-wal")
    return wal.stat().st_size if wal.exists() else 0


def _wal_checkpoint_truncate(db_path: Path) -> None:
    """尽力截断 WAL 作为场景前基线（直接 sqlite3 连接，失败只记录）。"""
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - 基准辅助，尽力而为
        pass


try:
    import psutil  # noqa: F401

    _PROC = psutil.Process()

    def _rss_mb() -> Optional[float]:
        return _PROC.memory_info().rss / (1024.0 * 1024.0)

except ImportError:  # pragma: no cover - psutil 可选

    def _rss_mb() -> Optional[float]:
        return None


# =============================================================================
# 工具函数
# =============================================================================


def _chunks(seq: List[Any], size: int) -> Iterator[List[Any]]:
    """按 size 切分列表。"""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _percentiles(samples: List[float]) -> Dict[str, float]:
    """计算 P50/P95/P99/mean/max（ms）。"""
    if not samples:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "max": 0.0}
    sorted_s = sorted(samples)
    n = len(sorted_s)

    def pct(p: float) -> float:
        idx = max(0, min(n - 1, int(n * p) - 1))
        return sorted_s[idx]

    return {
        "p50": round(pct(0.50), 2),
        "p95": round(pct(0.95), 2),
        "p99": round(pct(0.99), 2),
        "mean": round(sum(sorted_s) / n, 2),
        "max": round(sorted_s[-1], 2),
    }


async def _count_like(env: _BenchEnv, model: Any, prefix: str) -> int:
    """统计 id 前缀匹配的行数（读事务后立即 rollback，避免 WAL 快照过期）。"""
    async with env.session_factory() as db:
        stmt = select(func.count()).select_from(model).where(model.id.like(f"{prefix}%"))
        count = (await db.execute(stmt)).scalar()
        await db.rollback()
        return count


async def _lag_sampler(stop: asyncio.Event, samples: List[float]) -> None:
    """轻量事件循环 lag 采样器：名义 sleep 与实际耗时之差（ms，负值钳位为 0）。"""
    while not stop.is_set():
        t0 = time.perf_counter()
        await asyncio.sleep(LAG_SAMPLE_INTERVAL_S)
        lag_ms = (time.perf_counter() - t0 - LAG_SAMPLE_INTERVAL_S) * 1000.0
        samples.append(max(0.0, lag_ms))


async def _dl_call(
    dl_id: str,
    lane: DownloadLane,
    delay_s: float,
    timeout_s: float,
    operation: str,
) -> Dict[str, Any]:
    """真实 call_downloader_api 调用（slow_func 内可控 sleep 代替真实下载器响应）。

    不跳过网络阶段：经 lane executor + 两级 semaphore + wait_for 超时路径。
    """

    def slow_func(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if delay_s > 0:
            time.sleep(delay_s)
        return {"status": "ok", "fake": True}

    t0 = time.perf_counter()
    try:
        await call_downloader_api(dl_id, lane, slow_func, timeout=timeout_s, operation=operation)
        return {"ok": True, "ms": (time.perf_counter() - t0) * 1000.0, "timeout": False}
    except asyncio.TimeoutError:
        return {"ok": False, "ms": (time.perf_counter() - t0) * 1000.0, "timeout": True}


class BatchLogCollector(logging.Handler):
    """捕获 sync_db_write 每批结构化日志（commit_ms / lock_wait_ms / retry_count）。

    对应 W4-1 最小字段集"数据库"类：batch_rows/changed_rows/commit_ms/
    lock_wait_ms/retry_count 由统一写入器逐批输出，这里原样收集供统计。
    """

    _PATTERN = re.compile(
        r"batch_done label=(?P<label>\S+) batch_index=\d+ batch_rows=\d+ changed_rows=\d+ "
        r"commit_ms=(?P<commit>[\d.]+) lock_wait_ms=(?P<lock>[\d.]+) retry_count=(?P<retry>\d+)"
    )

    def __init__(self, label_prefix: str = "") -> None:
        super().__init__(level=logging.INFO)
        self.label_prefix = label_prefix
        self.batches: List[Dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        m = self._PATTERN.search(msg)
        if m is None:
            return
        label = m.group("label")
        if self.label_prefix and not label.startswith(self.label_prefix):
            return
        self.batches.append(
            {
                "label": label,
                "commit_ms": float(m.group("commit")),
                "lock_wait_ms": float(m.group("lock")),
                "retry_count": int(m.group("retry")),
            }
        )


# =============================================================================
# 数据生成（全部合成数据，无任何敏感信息）
# =============================================================================


def _make_torrent_rows(n: int) -> List[Dict[str, Any]]:
    """构造 n 行合成 torrent 数据（生产近似字段分布）。"""
    return [
        {
            "id": f"bench-t-{i:06d}",
            "downloader_id": f"dl-{i % 3}",
            "seq": i,
            "name": f"bench-torrent-{i}",
            "size": 1024 * (i % 1000 + 1),
            "progress": float(i % 100),
            "dr": 0,
            "payload": f"payload-{i}",
        }
        for i in range(n)
    ]


def _make_tracker_rows(n: int) -> List[Dict[str, Any]]:
    """构造 n 行合成 tracker 数据（host 分组：failed/unknown/success 三态）。"""
    rows = []
    for i in range(n):
        host = f"tracker-bench-{i % 50}.example"
        if i % 7 == 0:
            msg = "announce failed: timeout"  # host 全 failed → error
        elif i % 7 == 3:
            msg = "status unknown report"  # host 全 unknown → unknown
        else:
            msg = "announce ok"  # host 全 success → normal
        rows.append(
            {
                "tracker_id": f"bench-r-{i:06d}",
                "tracker_url": f"http://{host}/announce",
                "last_announce_msg": msg,
                "last_scrape_msg": msg,
                "tracker_host": host,
                "status": "",
                "msg": "",
                "update_time": None,
                "dr": 0,
            }
        )
    return rows


def _make_keyword_rows() -> List[Dict[str, Any]]:
    """构造合成关键词池（success/failed 两类，供场景 B 判定）。"""
    return [
        {"keyword": "ok", "keyword_type": "success"},
        {"keyword": "timeout", "keyword_type": "failed"},
        {"keyword": "rejected", "keyword_type": "failed"},
    ]


async def _seed(env: _BenchEnv, ctx: "RunCtx") -> Dict[str, Any]:
    """建种子数据（分批 commit），返回行数据供场景复用与生成耗时。"""
    t0 = time.perf_counter()
    rss_before = _rss_mb()
    torrent_rows = _make_torrent_rows(ctx.n_torrents)
    tracker_rows = _make_tracker_rows(ctx.n_trackers)
    keyword_rows = _make_keyword_rows()

    async with env.session_factory() as db:
        for chunk in _chunks(keyword_rows, 500):
            await db.run_sync(lambda s, c=chunk: s.bulk_insert_mappings(BenchKeyword, c))
            await db.commit()
        for chunk in _chunks(torrent_rows, 2000):
            await db.run_sync(lambda s, c=chunk: s.bulk_insert_mappings(BenchTorrent, c))
            await db.commit()
        for chunk in _chunks(tracker_rows, 2000):
            await db.run_sync(lambda s, c=chunk: s.bulk_insert_mappings(BenchTracker, c))
            await db.commit()

    return {
        "torrents": torrent_rows,
        "trackers": tracker_rows,
        "keywords": keyword_rows,
        "gen_s": round(time.perf_counter() - t0, 3),
        "rss_before_mb": rss_before,
        "rss_after_mb": _rss_mb(),
        "wal_bytes": _wal_bytes(env.db_path),
    }


# =============================================================================
# 请求探针（独立连接，等价交互 API 操作）
# =============================================================================


def _probe_defs(env: _BenchEnv, scn: str, n_torrents: int) -> List[Tuple[str, Callable[[int], Any]]]:
    """构建探针定义：(名称, 生成协程的工厂)。每个探针独立会话（独立连接）。"""

    def op_read_count(i: int):  # noqa: ARG001 - 签名统一
        async def _run() -> None:
            async with env.session_factory() as db:
                await db.execute(select(func.count()).select_from(BenchTorrent))
                await db.rollback()

        return _run()

    def op_read_page(i: int) -> Any:
        offset = (i * 13) % max(1, n_torrents - 50)

        async def _run() -> None:
            async with env.session_factory() as db:
                await db.execute(
                    select(BenchTorrent.id, BenchTorrent.name, BenchTorrent.size)
                    .where(BenchTorrent.dr == 0)
                    .order_by(BenchTorrent.id)
                    .limit(50)
                    .offset(offset)
                )
                await db.rollback()

        return _run()

    def op_write_insert(i: int) -> Any:
        row_id = f"probe-{scn}-{i}"

        async def _run() -> None:
            async with env.session_factory() as db:
                await db.execute(
                    insert(BenchTorrent).values(
                        id=row_id,
                        downloader_id="probe",
                        seq=i,
                        name="probe",
                        size=i,
                        progress=0.0,
                        dr=0,
                        payload="probe",
                    )
                )
                await db.commit()

        return _run()

    def op_write_mark(i: int) -> Any:
        row_id = f"bench-t-{i % n_torrents:06d}"

        async def _run() -> None:
            async with env.session_factory() as db:
                await db.execute(update(BenchTorrent).where(BenchTorrent.id == row_id).values(dr=1))
                await db.commit()

        return _run()

    def op_task_status(i: int):  # noqa: ARG001 - 签名统一
        async def _run() -> None:
            async with env.session_factory() as db:
                await db.execute(
                    select(BenchTracker.tracker_id, BenchTracker.status).where(BenchTracker.dr == 0).limit(20)
                )
                await db.rollback()

        return _run()

    return [
        ("read_count", op_read_count),
        ("read_page", op_read_page),
        ("write_insert", op_write_insert),
        ("write_mark", op_write_mark),
        ("task_status", op_task_status),
    ]


async def _probe_loop(
    env: _BenchEnv,
    ctx: "RunCtx",
    scn: str,
    n_torrents: int,
    dl_settings: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """运行请求探针轮（可选 fake 下载器调用前置于每轮），返回 (探针结果, 下载器指标)。"""
    probe_defs = _probe_defs(env, scn, n_torrents)
    results: Dict[str, Dict[str, Any]] = {name: {"samples": [], "timeouts": 0, "failures": 0} for name, _ in probe_defs}
    dl_metrics: Dict[str, Any] = {"calls": 0, "ms": [], "timeouts": 0}

    for i in range(ctx.probe_iterations):
        # fake 下载器调用：每轮一次（INTERACTIVE lane），不跳过网络阶段
        if dl_settings["enabled"]:
            # slow-downloader 故障下用每轮唯一 downloader_id：避免同 id 的上一轮
            # 线程仍持有 per-downloader semaphore 导致本轮线程排队积压（超时后线程
            # 继续跑 2s，排队会让最后一个线程晚于排空窗口完成）
            dl_id = f"bench-probe-{scn}-{i}" if ctx.fault == "slow-downloader" else "bench-probe"
            dl = await _dl_call(
                dl_id,
                DownloadLane.INTERACTIVE,
                dl_settings["delay_s"],
                dl_settings["timeout_s"],
                "bench_probe",
            )
            dl_metrics["calls"] += 1
            dl_metrics["ms"].append(dl["ms"])
            if dl["timeout"]:
                dl_metrics["timeouts"] += 1
        for name, op_factory in probe_defs:
            t0 = time.perf_counter()
            try:
                await asyncio.wait_for(op_factory(i), timeout=PROBE_TIMEOUT_S)
                results[name]["samples"].append((time.perf_counter() - t0) * 1000.0)
            except asyncio.TimeoutError:
                results[name]["timeouts"] += 1
            except Exception:  # noqa: BLE001 - 探针异常计为失败，不中断基准
                results[name]["failures"] += 1

    return results, dl_metrics


def _probe_report(results: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """探针原始样本 → 报表（P50/P95/P99/max + 超时/失败计数 + 原始样本）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for name, r in results.items():
        out[name] = {
            "count": len(r["samples"]),
            "timeouts": r["timeouts"],
            "failures": r["failures"],
            "samples_ms": [round(v, 2) for v in r["samples"]],
            **_percentiles(r["samples"]),
        }
    return out


# =============================================================================
# 后台真实 DML 场景
# =============================================================================


async def _set_busy_timeout(db: AsyncSession, ms: int) -> None:
    """设置当前会话连接的 busy_timeout（基准可控；故障 busy 时收紧制造真实 BUSY）。"""
    await db.execute(text(f"PRAGMA busy_timeout={int(ms)}"))


def _dl_settings(ctx: "RunCtx") -> Dict[str, Any]:
    """解析 fake 下载器设置（故障 slow-downloader 覆盖：2s 延迟 / 1s 超时）。"""
    if ctx.fault == "slow-downloader":
        return {"enabled": True, "delay_s": 2.0, "timeout_s": 1.0, "bg": False}
    if ctx.dl_delay_ms > 0:
        return {
            "enabled": True,
            "delay_s": ctx.dl_delay_ms / 1000.0,
            "timeout_s": max(ctx.dl_delay_ms * 2 / 1000.0, 5.0),
            "bg": True,
        }
    return {"enabled": False, "delay_s": 0.0, "timeout_s": 30.0, "bg": False}


async def _bg_scenario_a(
    env: _BenchEnv,
    ctx: "RunCtx",
    to_insert: List[Dict[str, Any]],
    to_update: List[Dict[str, Any]],
    dl_settings: Dict[str, Any],
) -> Dict[str, Any]:
    """场景 A 后台：真实 bulk_upsert_with_retry（batch 200），块间可选下载器调用。"""
    total = WriteStats()
    chunk = 2000
    async with env.session_factory() as db:
        await _set_busy_timeout(db, ctx.effective_dml_busy_timeout_ms)
        for ins_chunk, upd_chunk in zip_longest(_chunks(to_insert, chunk), _chunks(to_update, chunk), fillvalue=[]):
            if dl_settings["enabled"] and dl_settings["bg"]:
                await _dl_call(
                    "bench-bg", DownloadLane.TRACKER, dl_settings["delay_s"], dl_settings["timeout_s"], "bench_bg_fetch"
                )
            if not ins_chunk and not upd_chunk:
                continue
            stats = await bulk_upsert_with_retry(
                db,
                ins_chunk,
                upd_chunk,
                model=BenchTorrent,
                label="bench_scnA",
                batch_size=BATCH_SIZE,
            )
            total.scanned += stats.scanned
            total.changed += stats.changed
            total.committed += stats.committed
            total.batches += stats.batches
            total.retries += stats.retries
    return {
        "label": "A_info_upsert",
        "scanned": total.scanned,
        "committed": total.committed,
        "batches": total.batches,
        "retries": total.retries,
        "final_failures": 0,
        "partial": False,
    }


async def _bg_scenario_b(
    env: _BenchEnv,
    ctx: "RunCtx",
    dl_settings: Dict[str, Any],
    dl_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """场景 B 后台：真实 sync_tracker_status_from_keywords（第 1 遍全量写、第 2 遍零变化）。

    可选并发 TRACKER lane fake 下载器调用循环，模拟同步期间网络阶段与写入并发。
    """
    async with env.session_factory() as db:
        await _set_busy_timeout(db, ctx.effective_dml_busy_timeout_ms)
        dl_task: Optional[asyncio.Task] = None
        if dl_settings["enabled"] and dl_settings["bg"]:

            async def dl_loop() -> None:
                while True:
                    dl = await _dl_call(
                        "bench-bg",
                        DownloadLane.TRACKER,
                        dl_settings["delay_s"],
                        dl_settings["timeout_s"],
                        "bench_bg_fetch",
                    )
                    dl_metrics["calls"] += 1
                    dl_metrics["ms"].append(dl["ms"])
                    if dl["timeout"]:
                        dl_metrics["timeouts"] += 1
                    await asyncio.sleep(0.05)

            dl_task = asyncio.create_task(dl_loop())
        try:
            stats1 = await sync_tracker_status_from_keywords(db, batch_size=BATCH_SIZE, label="bench_scnB")
            stats2 = await sync_tracker_status_from_keywords(db, batch_size=BATCH_SIZE, label="bench_scnB_pass2")
        finally:
            if dl_task is not None:
                dl_task.cancel()
                try:
                    await dl_task
                except asyncio.CancelledError:
                    pass
    return {
        "label": "B_tracker_status",
        "pass1": {
            "scanned": stats1.scanned,
            "changed": stats1.changed,
            "unchanged": stats1.unchanged,
            "batches": stats1.batches,
        },
        "pass2": {
            "scanned": stats2.scanned,
            "changed": stats2.changed,
            "unchanged": stats2.unchanged,
            "batches": stats2.batches,
        },
        "final_failures": 0,
        "partial": False,
    }


async def _bg_scenario_c(
    env: _BenchEnv,
    ctx: "RunCtx",
    target_ids: List[str],
    dl_settings: Dict[str, Any],
) -> Dict[str, Any]:
    """场景 C 后台：qB removed 式标记（批量 UPDATE dr=1，逐批 commit + 有界重试）。"""
    commit_ms: List[float] = []
    lock_wait_ms: List[float] = []
    retries = 0
    final_failures = 0
    max_attempts = 6
    async with env.session_factory() as db:
        await _set_busy_timeout(db, ctx.effective_dml_busy_timeout_ms)
        for ids in _chunks(target_ids, BATCH_SIZE):
            if dl_settings["enabled"] and dl_settings["bg"]:
                await _dl_call(
                    "bench-bg", DownloadLane.TRACKER, dl_settings["delay_s"], dl_settings["timeout_s"], "bench_bg_fetch"
                )
            for attempt in range(max_attempts):
                t0 = time.perf_counter()
                try:
                    await db.execute(update(BenchTorrent).where(BenchTorrent.id.in_(ids)).values(dr=1))
                    await db.commit()
                    commit_ms.append(round((time.perf_counter() - t0) * 1000.0, 2))
                    break
                except SAOperationalError as exc:
                    if not _is_sqlite_lock_conflict(exc):
                        raise
                    retries += 1
                    await db.rollback()
                    delay = min(0.05 * (2**attempt) + 0.01, 0.5)
                    lock_wait_ms.append(delay * 1000.0)
                    if attempt + 1 >= max_attempts:
                        final_failures += 1
                        break
                    await asyncio.sleep(delay)
    return {
        "label": "C_qb_removed_mark",
        "committed": len(target_ids),
        "batches": len(commit_ms),
        "retries": retries,
        "commit_ms": commit_ms,
        "lock_wait_ms": lock_wait_ms,
        "final_failures": final_failures,
        "partial": False,
    }


# =============================================================================
# 故障注入
# =============================================================================


async def _busy_holder(env: _BenchEnv, hold_s: float = 0.3, cycles: int = 4, gap_s: float = 0.05) -> Dict[str, int]:
    """故障 busy：后台持写锁不提交 hold_s 秒（真实 BEGIN + INSERT + sleep + commit）。

    持锁期间其他写者的 busy_timeout 到期即抛 SQLITE_BUSY（错误码路径），
    触发统一写入器/场景 C 的有界重试；本函数自身事务在 sleep 后提交。
    """
    holds = 0
    for _ in range(cycles):
        async with env.session_factory() as db:
            async with db.begin():
                await db.execute(
                    insert(BenchTorrent).values(
                        id=f"busyhold-{time.monotonic_ns()}",
                        downloader_id="hold",
                        seq=0,
                        name="hold",
                        size=0,
                        progress=0.0,
                        dr=0,
                        payload="hold",
                    )
                )
                await asyncio.sleep(hold_s)
        holds += 1
        if gap_s > 0:
            await asyncio.sleep(gap_s)
    return {"holds": holds}


async def _cancel_watcher(env: _BenchEnv, bg_task: asyncio.Task, prefix: str, min_batches: int, batch_size: int) -> int:
    """故障 cancel：后台 DML 提交满 min_batches 批后取消任务，返回取消时已提交行数。"""
    count = 0
    deadline = time.monotonic() + 60.0
    async with env.session_factory() as db:
        while time.monotonic() < deadline:
            stmt = select(func.count()).select_from(BenchTorrent).where(BenchTorrent.id.like(f"{prefix}%"))
            count = (await db.execute(stmt)).scalar()
            await db.rollback()
            if count >= min_batches * batch_size:
                break
            await asyncio.sleep(0.005)
    bg_task.cancel()
    return count


@contextmanager
def _fault_busy_settings() -> Iterator[None]:
    """故障 busy 期间进程内收紧统一写入器退避参数（基准专用，结束即恢复）。

    生产默认 SYNC_DB_LOCK_RETRY_COUNT=3 / SYNC_DB_RETRY_MAX_BACKOFF_SECONDS=2：
    在 300ms 持锁 + 100ms busy_timeout 的组合下，单批 3 次尝试可能耗尽导致
    ChunkedWriteError。基准收紧为 6 次/3s，验证"有界重试 + 最终一致"而非
    "耗尽重试"；生产参数下的吸收行为由集成测试与无故障运行覆盖。
    """
    old_count = settings.SYNC_DB_LOCK_RETRY_COUNT
    old_backoff = settings.SYNC_DB_RETRY_MAX_BACKOFF_SECONDS
    settings.SYNC_DB_LOCK_RETRY_COUNT = 6
    settings.SYNC_DB_RETRY_MAX_BACKOFF_SECONDS = 3.0
    try:
        yield
    finally:
        settings.SYNC_DB_LOCK_RETRY_COUNT = old_count
        settings.SYNC_DB_RETRY_MAX_BACKOFF_SECONDS = old_backoff


# =============================================================================
# 场景编排
# =============================================================================


@dataclass
class RunCtx:
    """单次基准运行上下文（命令行参数 + 派生参数）。"""

    size_name: str
    n_torrents: int
    n_trackers: int
    probe_iterations: int
    fault: str
    dl_delay_ms: int
    assert_slo: bool
    scenarios: List[str]
    out_dir: Path
    effective_dml_busy_timeout_ms: int = DB_BUSY_TIMEOUT_MS

    @property
    def fault_busy(self) -> bool:
        return self.fault == "busy"


def _make_ctx(args: argparse.Namespace) -> RunCtx:
    n_t, n_r = SIZES[args.size]
    return RunCtx(
        size_name=args.size,
        n_torrents=n_t,
        n_trackers=n_r,
        probe_iterations=args.probe_iterations,
        fault=args.fault,
        dl_delay_ms=args.downloader_delay_ms,
        assert_slo=args.assert_slo,
        scenarios=[s.strip() for s in args.scenarios.split(",") if s.strip()],
        out_dir=Path(args.out_dir),
        effective_dml_busy_timeout_ms=FAULT_BUSY_DML_TIMEOUT_MS if args.fault == "busy" else DB_BUSY_TIMEOUT_MS,
    )


def _bg_commit_metrics(collector: BatchLogCollector, label: str) -> Dict[str, Any]:
    """从逐批日志聚合批级指标（commit_ms / lock_wait_ms / retry_count 分布）。"""
    batches = [b for b in collector.batches if b["label"] == label]
    commit_ms = [b["commit_ms"] for b in batches]
    lock_wait_ms = [b["lock_wait_ms"] for b in batches]
    retries = sum(b["retry_count"] for b in batches)
    return {
        "batches": len(batches),
        "retries": retries,
        "commit_ms": commit_ms,
        "lock_wait_ms": lock_wait_ms,
        "commit_ms_stats": _percentiles(commit_ms),
        "lock_wait_ms_stats": _percentiles(lock_wait_ms),
        "max_retry_per_batch": max((b["retry_count"] for b in batches), default=0),
    }


async def _run_scenario(env: _BenchEnv, ctx: RunCtx, scn: str, seed_data: Dict[str, Any]) -> Dict[str, Any]:
    """运行单个场景：后台 DML 与请求探针并发 + 指标采集（WAL/lag/RSS/busy）。"""
    admission_controller.reset_state()
    dl_settings = _dl_settings(ctx)

    # 事件循环 lag 采样
    stop = asyncio.Event()
    lag_samples: List[float] = []
    sampler = asyncio.create_task(_lag_sampler(stop, lag_samples))

    # WAL / RSS / busy 基线
    _wal_checkpoint_truncate(env.db_path)
    # WAL 见证连接：保持一个连接常开，防止"最后一个连接关闭时 SQLite 自动
    # checkpoint 截断 WAL"，使场景后 WAL 测量真实反映本场景写入量
    witness = await env.engine.connect()
    try:
        await witness.execute(text("PRAGMA busy_timeout=15000"))
        await witness.commit()  # 结束隐式事务，保持连接空闲打开
    except Exception:  # noqa: BLE001 - 见证连接失败不阻断基准
        await witness.close()
        witness = None
    wal_before = _wal_bytes(env.db_path)
    rss_before = _rss_mb()
    busy_before = env.busy_counter["count"]

    # 逐批日志采集（统一写入器）
    collector = BatchLogCollector(label_prefix="bench_scn")
    sync_db_logger = logging.getLogger("app.services.sync_db_write")
    sync_db_logger.addHandler(collector)
    old_level = sync_db_logger.level
    sync_db_logger.setLevel(logging.INFO)

    bg_stats: Optional[Dict[str, Any]] = None
    bg_error: Optional[str] = None
    cancel_result: Optional[Dict[str, Any]] = None
    dl_metrics: Dict[str, Any] = {"calls": 0, "ms": [], "timeouts": 0}
    started = time.monotonic()
    try:
        # 启动后台 DML（按场景）
        bg_task: Optional[asyncio.Task] = None
        holder_task: Optional[asyncio.Task] = None
        watcher_task: Optional[asyncio.Task] = None
        if scn == "A":
            n_t = ctx.n_torrents
            to_update = [
                {
                    "id": row["id"],
                    "progress": (row["progress"] + 1.0) % 100.0,
                    "name": f"{row['name']}-v2",
                    "payload": f"updated-{row['id']}",
                }
                for row in seed_data["torrents"][: n_t * 4 // 10]
            ]
            to_insert = [
                {
                    "id": f"scn-a-{i:06d}",
                    "downloader_id": "dl-a",
                    "seq": i,
                    "name": f"scn-a-{i}",
                    "size": i * 2,
                    "progress": 0.0,
                    "dr": 0,
                    "payload": f"scn-a-payload-{i}",
                }
                for i in range(max(n_t // 10, SCN_A_INSERT_MIN))
            ]
            bg_task = asyncio.create_task(_bg_scenario_a(env, ctx, to_insert, to_update, dl_settings))
            if ctx.fault == "cancel":
                watcher_task = asyncio.create_task(_cancel_watcher(env, bg_task, "scn-a-", 3, BATCH_SIZE))
        elif scn == "B":
            bg_task = asyncio.create_task(_bg_scenario_b(env, ctx, dl_settings, dl_metrics))
        elif scn == "C":
            target_ids = [row["id"] for row in seed_data["torrents"][ctx.n_torrents * 7 // 10 :]]
            bg_task = asyncio.create_task(_bg_scenario_c(env, ctx, target_ids, dl_settings))

        # 故障 busy：后台持锁注入（与 DML/探针并发）
        if ctx.fault_busy:
            holder_task = asyncio.create_task(_busy_holder(env))

        # 请求探针并发运行
        probe_results, probe_dl = await _probe_loop(env, ctx, scn, ctx.n_torrents, dl_settings)
        dl_metrics["calls"] += probe_dl["calls"]
        dl_metrics["ms"].extend(probe_dl["ms"])
        dl_metrics["timeouts"] += probe_dl["timeouts"]

        # 收尾后台任务
        if watcher_task is not None:
            try:
                await bg_task
            except asyncio.CancelledError:
                pass
            cancel_committed = await watcher_task
            cancel_result = {
                "applied": True,
                "batch_size": BATCH_SIZE,
                "min_batches": 3,
                "committed_rows": cancel_committed,
            }
        elif bg_task is not None:
            try:
                bg_stats = await bg_task
            except asyncio.CancelledError:
                bg_error = "cancelled"
            except Exception as exc:  # noqa: BLE001 - 记录后台异常，不中断基准
                bg_error = f"{type(exc).__name__}: {exc}"
        holder_stats: Optional[Dict[str, int]] = None
        if holder_task is not None:
            holder_stats = await holder_task
    finally:
        stop.set()
        await sampler
        sync_db_logger.removeHandler(collector)
        sync_db_logger.setLevel(old_level)

    # 场景后指标（先关见证连接，让 WAL 保持场景结束时的帧数）
    wal_after = _wal_bytes(env.db_path)
    if witness is not None:
        await witness.close()
    rss_after = _rss_mb()
    busy_count = env.busy_counter["count"] - busy_before

    # 后台 DML 指标汇总
    if scn == "0":
        bg = {
            "label": "0_baseline",
            "batches": 0,
            "committed": 0,
            "retries": 0,
            "final_failures": 0,
            "partial": False,
        }
    elif scn == "A":
        commit_m = _bg_commit_metrics(collector, "bench_scnA")
        if cancel_result is not None:
            bg = {
                "label": "A_info_upsert",
                "committed": cancel_result["committed_rows"],
                "batches": commit_m["batches"],
                "retries": commit_m["retries"],
                "partial": True,
                "final_failures": 0,
                **commit_m,
            }
        else:
            assert bg_stats is not None, "场景 A 后台统计缺失"
            bg = {
                "label": "A_info_upsert",
                "scanned": bg_stats["scanned"],
                "committed": bg_stats["committed"],
                "batches": bg_stats["batches"],
                "retries": bg_stats["retries"],
                "partial": bg_stats["partial"],
                "final_failures": bg_stats["final_failures"],
                **commit_m,
            }
    elif scn == "B":
        assert bg_stats is not None, "场景 B 后台统计缺失"
        commit_m = _bg_commit_metrics(collector, "bench_scnB")
        commit_m2 = _bg_commit_metrics(collector, "bench_scnB_pass2")
        bg = {
            "label": "B_tracker_status",
            "pass1": {**bg_stats["pass1"], **commit_m},
            "pass2": {**bg_stats["pass2"], **commit_m2},
            "batches": bg_stats["pass1"]["batches"] + bg_stats["pass2"]["batches"],
            "committed": bg_stats["pass1"]["changed"] + bg_stats["pass2"]["changed"],
            "retries": commit_m["retries"] + commit_m2["retries"],
            "final_failures": bg_stats["final_failures"],
            "partial": False,
        }
    else:  # C
        assert bg_stats is not None, "场景 C 后台统计缺失"
        bg = {
            "label": "C_qb_removed_mark",
            "committed": bg_stats["committed"],
            "batches": bg_stats["batches"],
            "retries": bg_stats["retries"],
            "final_failures": bg_stats["final_failures"],
            "partial": bg_stats["partial"],
            "commit_ms": bg_stats["commit_ms"],
            "lock_wait_ms": bg_stats["lock_wait_ms"],
            "commit_ms_stats": _percentiles(bg_stats["commit_ms"]),
            "lock_wait_ms_stats": _percentiles(bg_stats["lock_wait_ms"]),
        }
    if bg_error is not None:
        bg["final_failures"] = 1
        bg["error"] = bg_error

    return {
        "name": scn,
        "wall_time_s": round(time.monotonic() - started, 3),
        "bg": bg,
        "probes": _probe_report(probe_results),
        "downloaders": {
            "calls": dl_metrics["calls"],
            "timeouts": dl_metrics["timeouts"],
            "ms_max": round(max(dl_metrics["ms"]), 2) if dl_metrics["ms"] else 0.0,
            "ms_mean": round(sum(dl_metrics["ms"]) / len(dl_metrics["ms"]), 2) if dl_metrics["ms"] else 0.0,
        },
        "wal": {
            "before_bytes": wal_before,
            "after_bytes": wal_after,
            "growth_bytes": max(0, wal_after - wal_before),
        },
        "loop_lag_ms": {"samples": len(lag_samples), **_percentiles(lag_samples)},
        "rss_mb": {
            "before": rss_before,
            "after": rss_after,
            "growth": (rss_after - rss_before) if (rss_before and rss_after) else None,
        },
        "busy_count": busy_count,
        "fault": cancel_result or {"applied": ctx.fault != "none", **(holder_stats or {})},
    }


# =============================================================================
# SLO 发布门
# =============================================================================


def _aggregate_slo(scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
    """聚合全部场景探针样本，评估发布门 SLO（大档验收矩阵）。"""
    read_samples: List[float] = []
    write_samples: List[float] = []
    probe_timeouts = 0
    probe_total = 0
    final_failures = 0
    for scn in scenarios:
        for pname, pres in scn["probes"].items():
            probe_total += pres["count"] + pres["timeouts"] + pres["failures"]
            probe_timeouts += pres["timeouts"]
            if pname in ("read_count", "read_page", "task_status"):
                read_samples.extend(pres["samples_ms"])
            else:
                write_samples.extend(pres["samples_ms"])
        final_failures += scn["bg"]["final_failures"]

    read_p95 = _percentiles(read_samples)["p95"]
    write_p95 = _percentiles(write_samples)["p95"]
    timeout_rate = probe_timeouts / probe_total if probe_total else 0.0
    checks = [
        {
            "name": "只读 P95 < 1s",
            "actual": read_p95,
            "threshold": SLO_READ_P95_MS,
            "passed": read_p95 < SLO_READ_P95_MS,
        },
        {
            "name": "写 P95 < 2s",
            "actual": write_p95,
            "threshold": SLO_WRITE_P95_MS,
            "passed": write_p95 < SLO_WRITE_P95_MS,
        },
        {
            "name": "探针超时率 < 0.1%",
            "actual": round(timeout_rate * 100.0, 4),
            "threshold": 0.1,
            "passed": timeout_rate < SLO_TIMEOUT_RATE,
        },
        {
            "name": "最终 SQLITE_BUSY 失败 = 0",
            "actual": final_failures,
            "threshold": SLO_FINAL_BUSY_FAILURES,
            "passed": final_failures == SLO_FINAL_BUSY_FAILURES,
        },
    ]
    passed = all(c["passed"] for c in checks)
    return {
        "passed": passed,
        "checks": checks,
        "probe_total": probe_total,
        "probe_timeouts": probe_timeouts,
    }


# =============================================================================
# 故障断言汇总（可解释降级、无雪崩）
# =============================================================================


async def _fault_summary(env: _BenchEnv, ctx: RunCtx, scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按故障类型汇总断言结果（记录到 JSON，同时决定进程内断言失败标记）。"""
    if ctx.fault == "none":
        return {"applied": False}

    if ctx.fault == "busy":
        busy_total = sum(s["busy_count"] for s in scenarios)
        retries_total = sum(s["bg"]["retries"] for s in scenarios)
        final_failures = sum(s["bg"]["final_failures"] for s in scenarios)
        max_retry_per_batch = max(
            (s["bg"].get("max_retry_per_batch", 0) for s in scenarios if "max_retry_per_batch" in s["bg"]),
            default=0,
        )
        summary = {
            "applied": True,
            "type": "busy",
            "hold_s": 0.3,
            "cycles": 4,
            "observed_busy_total": busy_total,
            "dml_retries_total": retries_total,
            "max_retry_per_batch": max_retry_per_batch,
            "final_busy_failures": final_failures,
            "assertions": {
                "observed_busy_gt_0": busy_total > 0,
                "dml_retries_bounded": retries_total > 0 and max_retry_per_batch <= 6,
                "final_consistent": final_failures == 0,
            },
        }
        return summary

    if ctx.fault == "slow-downloader":
        dl_timeouts = sum(s["downloaders"]["timeouts"] for s in scenarios)
        probe_db_timeouts = sum(p["timeouts"] for s in scenarios for p in s["probes"].values())
        max_lag = max((s["loop_lag_ms"]["max"] for s in scenarios), default=0.0)
        # 事后检查：慢下载器故障后事件循环仍可正常服务请求
        post_check_ms: Optional[float] = None
        post_ok = False
        async with env.session_factory() as db:
            t0 = time.perf_counter()
            try:
                await asyncio.wait_for(db.execute(select(func.count()).select_from(BenchTorrent)), timeout=5.0)
                post_check_ms = (time.perf_counter() - t0) * 1000.0
                post_ok = True
            except Exception:  # noqa: BLE001
                post_check_ms = (time.perf_counter() - t0) * 1000.0
        summary = {
            "applied": True,
            "type": "slow-downloader",
            "delay_s": 2.0,
            "timeout_s": 1.0,
            "dl_calls_total": sum(s["downloaders"]["calls"] for s in scenarios),
            "dl_timeouts_total": dl_timeouts,
            "probe_db_timeouts": probe_db_timeouts,
            "max_loop_lag_ms": round(max_lag, 2),
            "post_check": {"ok": post_ok, "ms": round(post_check_ms, 2) if post_check_ms else None},
            "assertions": {
                "dl_timeout_path_exercised": dl_timeouts > 0,
                "no_db_probe_timeouts": probe_db_timeouts == 0,
                "loop_responsive": max_lag < 1000.0,
                "post_check_ok": post_ok,
            },
        }
        return summary

    # cancel
    cancel_scn = next((s for s in scenarios if s["name"] == "A"), None)
    if cancel_scn is None or not cancel_scn["fault"].get("applied"):
        return {"applied": False, "type": "cancel"}
    committed = cancel_scn["fault"]["committed_rows"]
    total = max(ctx.n_torrents // 10, SCN_A_INSERT_MIN)
    post_count = await _count_like(env, BenchTorrent, "scn-a-")
    summary = {
        "applied": True,
        "type": "cancel",
        "committed_rows": committed,
        "expected_total_rows": total,
        "partial": True,
        "post_count_rows": post_count,
        "assertions": {
            "committed_gt_0": committed >= BATCH_SIZE,
            "committed_lt_total": committed < total,
            "committed_multiple_of_batch": committed % BATCH_SIZE == 0,
            "no_post_commit": post_count == committed,
        },
    }
    return summary


# =============================================================================
# 输出
# =============================================================================


def _print_scenario_table(scenarios: List[Dict[str, Any]]) -> None:
    """打印逐场景汇总表。"""
    print("\n" + "=" * 100)
    print(
        f"{'场景':<14} {'wall_s':>7} {'读P95(ms)':>10} {'写P95(ms)':>10} {'探针超时':>8} "
        f"{'批数':>6} {'写入行':>9} {'重试':>5} {'BUSY':>5} {'WAL增(KB)':>10}"
    )
    print("-" * 100)
    for s in scenarios:
        read_p95 = _scn_probe_p95(s, read_only=True)
        write_p95 = _scn_probe_p95(s, read_only=False)
        t_out = sum(p["timeouts"] for p in s["probes"].values())
        print(
            f"{s['name']:<14} {s['wall_time_s']:>7.2f} {read_p95:>10.2f} {write_p95:>10.2f} {t_out:>8} "
            f"{s['bg']['batches']:>6} {s['bg']['committed']:>9} {s['bg']['retries']:>5} "
            f"{s['busy_count']:>5} {s['wal']['growth_bytes'] / 1024:>10.1f}"
        )
    print("=" * 100)


def _scn_probe_p95(scn: Dict[str, Any], read_only: bool) -> float:
    """场景内读（或写）探针聚合 P95（ms）。"""
    samples: List[float] = []
    for pname, pres in scn["probes"].items():
        is_read = pname in ("read_count", "read_page", "task_status")
        if is_read == read_only:
            samples.extend(pres["samples_ms"])
    return _percentiles(samples)["p95"]


def _print_slo_table(slo: Dict[str, Any]) -> None:
    """打印 SLO 发布门结果表。"""
    print("\n[SLO 发布门]")
    print("-" * 100)
    for c in slo["checks"]:
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"  [{mark}] {c['name']:<28} actual={c['actual']} threshold={c['threshold']}")
    print(
        f"  探针总数={slo['probe_total']} 探针超时={slo['probe_timeouts']} → 总体 {'PASS' if slo['passed'] else 'FAIL'}"
    )
    print("-" * 100)


def _print_fault_summary(fault: Dict[str, Any]) -> None:
    """打印故障注入断言结果。"""
    if not fault.get("applied"):
        return
    print(f"\n[故障注入] {fault.get('type', '?')}")
    print("-" * 100)
    for k, v in fault.items():
        if k in ("assertions", "applied", "type"):
            continue
        print(f"  {k} = {v}")
    for k, v in fault.get("assertions", {}).items():
        mark = "PASS" if v else "FAIL"
        print(f"  [{mark}] {k} = {v}")
    print("-" * 100)


def _install_noisy_callback_filter() -> None:
    """过滤已知噪音：call_downloader_api 超时后 wait_for 会取消 wrap_future，
    downloader_api_runtime._attach_done_stats._on_done 对 cancelled future 调
    fut.exception() 抛 CancelledError（except Exception 捕获不到 BaseException），
    每次超时都向 stderr 打一条 "Exception in callback"。这是既有生产代码的观测
    缺口（W4-1 观测收口候选），基准侧只过滤该固定模式，其余异常处理保持默认。
    """
    loop = asyncio.get_event_loop()
    default_handler = loop.get_exception_handler() or loop.default_exception_handler

    def _filtered(loop_: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
        message = str(context.get("message", ""))
        handle = str(context.get("handle", ""))
        if "Exception in callback" in message and "_attach_done_stats" in handle:
            return
        default_handler(loop_, context)

    loop.set_exception_handler(_filtered)


async def _run(ctx: RunCtx) -> int:
    """基准主流程：建环境 → 播种 → 场景 → 故障断言 → SLO → JSON。"""
    _install_noisy_callback_filter()
    env = await _make_env()
    print(
        f"W4-3 真实文件型 SQLite 争用基准（{ctx.size_name} 档：{ctx.n_torrents} torrents / {ctx.n_trackers} trackers）"
    )
    print(f"时间：{datetime.now().isoformat()}  故障：{ctx.fault}  探针轮数：{ctx.probe_iterations}")
    try:
        seed = await _seed(env, ctx)
        rss_b = seed["rss_before_mb"]
        rss_a = seed["rss_after_mb"]
        rss_txt = f"{rss_b:.1f}→{rss_a:.1f}MB" if (rss_b and rss_a) else "psutil 不可用，跳过"
        print(
            f"种子数据生成：{seed['gen_s']}s（{ctx.n_torrents} torrents + {ctx.n_trackers} trackers + 3 keywords），"
            f"WAL={seed['wal_bytes']}B，RSS {rss_txt}"
        )

        scenarios: List[Dict[str, Any]] = []
        with _fault_busy_settings() if ctx.fault_busy else nullcontext():
            for scn in ctx.scenarios:
                if scn not in ("0", "A", "B", "C"):
                    print(f"  [WARN] 未知场景 {scn}，跳过")
                    continue
                print(f"  [场景 {scn}] 运行中 ...")
                result = await _run_scenario(env, ctx, scn, seed)
                scenarios.append(result)
        if ctx.fault == "slow-downloader":
            # 排空：等所有 fake 下载器 executor 线程结束，避免进程退出时
            # run_in_executor future 被取消（_attach_done_stats 回调不吞 CancelledError）
            await asyncio.sleep(2.2)
        _print_scenario_table(scenarios)

        fault = await _fault_summary(env, ctx, scenarios)
        _print_fault_summary(fault)

        slo: Optional[Dict[str, Any]] = None
        exit_code = 0
        if ctx.assert_slo:
            if ctx.fault != "none":
                print("\n[WARN] --assert-slo 仅在无故障注入时评估（故障运行是诊断模式），跳过 SLO 门禁")
            else:
                slo = _aggregate_slo(scenarios)
                _print_slo_table(slo)
                if ctx.size_name != "large":
                    print("  [WARN] 正式发布门以大档（--size large）为准，当前为校准档")
                if not slo["passed"]:
                    exit_code = 1

        # 机器可读 JSON（仅合成数据）
        out = {
            "meta": {
                "timestamp": datetime.now().isoformat(),
                "python": sys.version.split()[0],
                "sqlite_version": sqlite3.sqlite_version,
                "platform": sys.platform,
                "size": ctx.size_name,
                "torrents": ctx.n_torrents,
                "trackers": ctx.n_trackers,
                "probe_iterations": ctx.probe_iterations,
                "fault": ctx.fault,
                "downloader_delay_ms": ctx.dl_delay_ms,
                "assert_slo": ctx.assert_slo,
            },
            "seed": {k: v for k, v in seed.items() if k != "torrents" and k != "trackers" and k != "keywords"},
            "scenarios": scenarios,
            "fault": fault,
            "slo": slo,
        }
        ctx.out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = ctx.out_dir / f"sync_contention_{ts}.json"
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n结果已写入：{out_path}")
        if not slo or slo["passed"]:
            print(f"退出码：{exit_code}")
        else:
            print(f"退出码：{exit_code}（SLO 未满足，见上方失败诊断）")
        return exit_code
    finally:
        await env.engine.dispose()
        shutil.rmtree(env.tmpdir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="W4-3 真实文件型 SQLite 争用基准（P1-07）")
    parser.add_argument(
        "--size",
        choices=list(SIZES.keys()),
        default="large",
        help="数据规模档（默认 large=22k torrents/30k trackers）",
    )
    parser.add_argument(
        "--probe-iterations",
        type=int,
        default=30,
        help="每场景请求探针轮数（默认 30）",
    )
    parser.add_argument(
        "--scenarios",
        default="0,A,B,C",
        help="逗号分隔场景：0=无同步基线, A=info upsert, B=tracker status, C=qB removed mark（默认全部）",
    )
    parser.add_argument(
        "--fault",
        choices=["none", "busy", "slow-downloader", "cancel"],
        default="none",
        help="故障注入（默认 none；busy=持锁300ms×4 制造真实 BUSY，slow-downloader=探针下载器2s延迟/1s超时，cancel=后台DML中途取消）",
    )
    parser.add_argument(
        "--downloader-delay-ms",
        type=int,
        default=0,
        help="fake 下载器可控延迟（ms，默认 0 关闭）",
    )
    parser.add_argument(
        "--assert-slo",
        action="store_true",
        help="启用发布门 SLO 断言（大档：只读 P95<1s、写 P95<2s、超时率<0.1%、最终 BUSY 失败=0；不满足 exit 1）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(BACKEND_ROOT / "benchmark_results"),
        help="JSON 输出目录（默认 backend/benchmark_results）",
    )
    args = parser.parse_args()
    ctx = _make_ctx(args)
    return asyncio.run(_run(ctx))


if __name__ == "__main__":
    sys.exit(main())
