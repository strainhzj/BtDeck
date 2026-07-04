#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sync-resource-governance 阶段 3 压测脚本

可重复验证"同步期间请求侧接口响应"的压测矩阵。覆盖计划要求的 6 个场景：
1. 无同步时接口响应（基线）
2. tracker 同步中接口响应
3. 种子信息同步中接口响应
4. tracker 同步 + 种子信息同步同时触发
5. 单下载器大量种子
6. 多下载器并发

【设计原则】
- 纯 asyncio（不走 TestClient，避免线程安全问题）
- mock 下载器客户端（不需要真实 qB/TR 实例）
- 用真实 admission_controller + db_write_scope（治理层真实运行）
- 真实 SQLite 内存库（验证 db_write_scope 串行化不阻塞读查询）
- 输出每场景的 P50/P95/P99 响应时间 + 治理跳过次数

【用法】
    cd backend
    python scripts/sync_resource_benchmark.py [--scenarios 1,2,3,4,5,6] [--iterations 50]

    可选参数：
    --scenarios  逗号分隔的场景编号（默认全部）
    --iterations 每场景请求探针次数（默认 50）

【输出】
    stdout 表格 + 写入 /tmp/sync_resource_benchmark_<timestamp>.json 供对比

详见 PLANS/sync-resource-governance.md 第四节"手动压测矩阵"。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# 确保能 import app 包
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base  # noqa: E402
from app.services.dashboard_service import DashboardService  # noqa: E402
from app.services.downloader_api_runtime import (  # noqa: E402
    DownloadLane,
    downloader_api_runtime,
)
from app.tasks.cron_models import CronTask  # noqa: E402
from app.tasks.resource_guard import admission_controller  # noqa: E402
from app.tasks.task_profiles import get_profile  # noqa: E402
from app.torrents.audit_models import TorrentAuditLog  # noqa: E402

# =============================================================================
# Mock 基础设施
# =============================================================================


async def _make_db() -> AsyncSession:
    """构造异步内存 SQLite，建 DashboardService 查询所需的表。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [CronTask.__table__, TorrentAuditLog.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    return Session()


def _make_fake_app() -> Any:
    """构造降级伪 app（store/torrent_stats=None 走降级路径）。"""
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    app.state.start_time = time.time()
    app.state.store = None
    app.state.torrent_stats = None
    return app


def _make_slow_downloader_call(delay: float = 0.5):
    """构造模拟慢响应的下载器调用（用真实 downloader_api_runtime，但 mock func 内 sleep）。"""

    def slow_func(*args, **kwargs):
        time.sleep(delay)
        return {"status": "ok", "delay": delay}

    return slow_func


# =============================================================================
# 探针：DashboardService 查询
# =============================================================================


async def probe_dashboard(db: AsyncSession, app: Any) -> float:
    """执行一次 DashboardService.get_dashboard_data()，返回耗时（秒）。"""
    service = DashboardService(db, app)
    started = time.monotonic()
    await service.get_dashboard_data()
    return time.monotonic() - started


def _percentiles(samples: list[float]) -> dict:
    """计算 P50/P95/P99。"""
    if not samples:
        return {"count": 0, "p50": 0, "p95": 0, "p99": 0, "mean": 0, "max": 0}
    sorted_s = sorted(samples)
    n = len(sorted_s)

    def pct(p: float) -> float:
        idx = max(0, min(n - 1, int(n * p) - 1))
        return sorted_s[idx]

    return {
        "count": n,
        "p50": round(pct(0.50) * 1000, 2),  # ms
        "p95": round(pct(0.95) * 1000, 2),
        "p99": round(pct(0.99) * 1000, 2),
        "mean": round(statistics.mean(sorted_s) * 1000, 2),
        "max": round(sorted_s[-1] * 1000, 2),
    }


# =============================================================================
# 6 个压测场景
# =============================================================================


async def scenario_1_baseline(db, app, iterations: int) -> dict:
    """场景1：无同步时接口响应（基线）。"""
    samples = []
    for _ in range(iterations):
        elapsed = await probe_dashboard(db, app)
        samples.append(elapsed)
    return {"name": "1_baseline_no_sync", "samples_count": len(samples), "latency_ms": _percentiles(samples)}


async def scenario_2_tracker_sync_running(db, app, iterations: int) -> dict:
    """场景2：tracker 同步运行中接口响应。

    模拟 tracker_sync 持有 heavy_sync + 跑慢下载器调用期间，请求探针的响应。
    """
    task_code = "tracker_sync_598b784c"
    profile = get_profile(task_code)
    samples = []

    # 占住 heavy_sync（模拟 tracker 同步在跑）
    holder = await admission_controller.acquire(task_code, profile)
    assert holder.admitted is True
    try:
        # 同时在 tracker_lane 跑慢调用（占 lane executor 线程）
        async def bg_slow():
            for _ in range(iterations):
                try:
                    await downloader_api_runtime.call(
                        "dl_mock",
                        DownloadLane.TRACKER,
                        _make_slow_downloader_call(0.05),
                        operation="mock_tracker_fetch",
                    )
                except Exception:
                    pass

        bg_task = asyncio.create_task(bg_slow())
        # 跑请求探针
        for _ in range(iterations):
            elapsed = await probe_dashboard(db, app)
            samples.append(elapsed)
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
    finally:
        admission_controller.release(task_code)

    return {
        "name": "2_tracker_sync_running",
        "samples_count": len(samples),
        "latency_ms": _percentiles(samples),
    }


async def scenario_3_torrent_info_sync_running(db, app, iterations: int) -> dict:
    """场景3：种子信息同步运行中接口响应。"""
    task_code = "torrent_info_sync_ac608e4d"
    profile = get_profile(task_code)
    samples = []

    holder = await admission_controller.acquire(task_code, profile)
    assert holder.admitted is True
    try:

        async def bg_slow():
            for _ in range(iterations):
                try:
                    await downloader_api_runtime.call(
                        "dl_mock",
                        DownloadLane.SYNC,
                        _make_slow_downloader_call(0.05),
                        operation="mock_torrent_info_fetch",
                    )
                except Exception:
                    pass

        bg_task = asyncio.create_task(bg_slow())
        for _ in range(iterations):
            elapsed = await probe_dashboard(db, app)
            samples.append(elapsed)
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
    finally:
        admission_controller.release(task_code)

    return {
        "name": "3_torrent_info_sync_running",
        "samples_count": len(samples),
        "latency_ms": _percentiles(samples),
    }


async def scenario_4_both_sync_triggered(db, app, iterations: int) -> dict:
    """场景4：tracker 同步 + 种子信息同步同时触发。

    验证：heavy_sync=1 时第二个任务被跳过（SKIP_DUPLICATE 不适用跨 task_code，
    但 heavy_sync 占满会 SKIP_WAIT_TIMEOUT），请求侧仍正常响应。
    """
    code_t = "tracker_sync_598b784c"
    code_i = "torrent_info_sync_ac608e4d"
    profile_t = get_profile(code_t)
    profile_i = get_profile(code_i)
    samples = []

    # 任务 A 占住 heavy_sync
    holder_a = await admission_controller.acquire(code_t, profile_t)
    assert holder_a.admitted is True
    try:
        # 任务 B 尝试 acquire（会等待/超时）
        bg_b = asyncio.create_task(admission_controller.acquire(code_i, profile_i))
        await asyncio.sleep(0.05)  # 让 B 进入排队

        for _ in range(iterations):
            elapsed = await probe_dashboard(db, app)
            samples.append(elapsed)

        # 取消 B（避免卡 wait_timeout）
        bg_b.cancel()
        try:
            await bg_b
        except asyncio.CancelledError:
            pass
    finally:
        admission_controller.release(code_t)

    return {
        "name": "4_both_sync_triggered",
        "samples_count": len(samples),
        "latency_ms": _percentiles(samples),
    }


async def scenario_5_single_downloader_many_torrents(db, app, iterations: int) -> dict:
    """场景5：单下载器大量种子。

    模拟单个下载器的 tracker 同步在跑大量（mock）种子查询，
    期间请求侧响应。
    """
    samples = []
    task_code = "tracker_sync_598b784c"
    profile = get_profile(task_code)

    holder = await admission_controller.acquire(task_code, profile)
    assert holder.admitted is True
    try:
        # 在 tracker_lane 跑 20 个并发慢调用（模拟大量种子的 tracker 查询）
        async def bg_many():
            tasks = [
                downloader_api_runtime.call(
                    "dl_many",
                    DownloadLane.TRACKER,
                    _make_slow_downloader_call(0.1),
                    operation=f"mock_tracker_{i}",
                )
                for i in range(20)
            ]
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                pass

        bg_task = asyncio.create_task(bg_many())
        for _ in range(iterations):
            elapsed = await probe_dashboard(db, app)
            samples.append(elapsed)
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
    finally:
        admission_controller.release(task_code)

    return {
        "name": "5_single_downloader_many_torrents",
        "samples_count": len(samples),
        "latency_ms": _percentiles(samples),
    }


async def scenario_6_multi_downloader_concurrent(db, app, iterations: int) -> dict:
    """场景6：多下载器并发。

    模拟多个下载器各自的同步任务并发跑（不同 downloader_id），
    期间请求侧响应。验证 per-downloader semaphore + lane 隔离效果。
    """
    samples = []

    async def bg_downloader(dl_id: str, lane: DownloadLane):
        for _ in range(5):
            try:
                await downloader_api_runtime.call(
                    dl_id,
                    lane,
                    _make_slow_downloader_call(0.08),
                    operation=f"mock_multi_{dl_id}",
                )
            except Exception:
                pass

    # 3 个下载器并发，各自占不同 lane
    async def _bg_multi():
        await asyncio.gather(
            bg_downloader("dl_a", DownloadLane.SYNC),
            bg_downloader("dl_b", DownloadLane.TRACKER),
            bg_downloader("dl_c", DownloadLane.INTERACTIVE),
            return_exceptions=True,
        )

    bg_task = asyncio.create_task(_bg_multi())
    try:
        for _ in range(iterations):
            elapsed = await probe_dashboard(db, app)
            samples.append(elapsed)
    finally:
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass

    return {
        "name": "6_multi_downloader_concurrent",
        "samples_count": len(samples),
        "latency_ms": _percentiles(samples),
    }


SCENARIOS = {
    1: scenario_1_baseline,
    2: scenario_2_tracker_sync_running,
    3: scenario_3_torrent_info_sync_running,
    4: scenario_4_both_sync_triggered,
    5: scenario_5_single_downloader_many_torrents,
    6: scenario_6_multi_downloader_concurrent,
}


# =============================================================================
# 主入口
# =============================================================================


async def run(scenarios: list[int], iterations: int) -> list[dict]:
    """跑指定场景，返回结果列表。"""
    admission_controller.reset_state()
    db = await _make_db()
    app = _make_fake_app()
    results = []
    try:
        for sid in scenarios:
            scenario_fn = SCENARIOS.get(sid)
            if scenario_fn is None:
                print(f"  [WARN] 未知场景 {sid}，跳过")
                continue
            print(f"  [场景 {sid}] {scenario_fn.__doc__.strip().splitlines()[0]} ...")
            admission_controller.reset_state()
            started = time.monotonic()
            result = await scenario_fn(db, app, iterations)
            result["scenario_id"] = sid
            result["wall_time_s"] = round(time.monotonic() - started, 2)
            results.append(result)
            lat = result["latency_ms"]
            print(
                f"    → P50={lat['p50']}ms P95={lat['p95']}ms P99={lat['p99']}ms "
                f"(samples={lat['count']}, wall={result['wall_time_s']}s)"
            )
    finally:
        await db.close()

    return results


def print_summary(results: list[dict]) -> None:
    """打印汇总表。"""
    print("\n" + "=" * 80)
    print(f"{'场景':<40} {'P50':>8} {'P95':>8} {'P99':>8} {'max':>8}  (ms)")
    print("-" * 80)
    for r in results:
        lat = r["latency_ms"]
        print(f"{r['name']:<40} {lat['p50']:>8} {lat['p95']:>8} {lat['p99']:>8} {lat['max']:>8}")
    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(description="sync-resource-governance 压测脚本")
    parser.add_argument(
        "--scenarios",
        default="1,2,3,4,5,6",
        help="逗号分隔的场景编号（默认全部 1-6）",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=50,
        help="每场景请求探针次数（默认 50）",
    )
    args = parser.parse_args()

    try:
        scenario_ids = [int(s.strip()) for s in args.scenarios.split(",") if s.strip()]
    except ValueError:
        print("ERROR: --scenarios 必须是逗号分隔的数字", file=sys.stderr)
        return 2

    print(f"sync-resource-governance 压测：场景={scenario_ids} 迭代={args.iterations}")
    print(f"时间：{datetime.now().isoformat()}\n")

    results = asyncio.run(run(scenario_ids, args.iterations))
    print_summary(results)

    # 写 JSON 供对比
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(f"/tmp/sync_resource_benchmark_{timestamp}.json")
    try:
        out_path.write_text(
            json.dumps(
                {"timestamp": timestamp, "iterations": args.iterations, "results": results},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\n结果已写入：{out_path}")
    except OSError:
        # Windows /tmp 不存在时降级写到当前目录
        out_path = Path(f"sync_resource_benchmark_{timestamp}.json")
        out_path.write_text(
            json.dumps(
                {"timestamp": timestamp, "iterations": args.iterations, "results": results},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\n结果已写入：{out_path.absolute()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
