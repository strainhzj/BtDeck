# -*- coding: utf-8 -*-
"""
SyncCheckpoint 持久化检查点测试（W3-2，PLANS/sync-database-blocking-remediation.md）

覆盖行为契约：
1. 模型 CRUD + 唯一约束（同 downloader+sync_type 重复插入失败）。
2. 乐观锁冲突：version 不匹配时更新不倒退（既有 cursor 保留、终态 outcome
   不被降级；冲突重试一次后仍成功）。
3. Coordinator 集成：
   - run_sync 首次运行后 checkpoint 创建（outcome/last_attempt_at/
     cycle_started_at/last_full_sync_at 正确）；
   - 重启续跑：第一次 run_sync 中途异常（部分批次已提交）→ checkpoint 记录
     partial + last_success_at + cursor；第二次 run_sync 读取 checkpoint
     （SyncResult.checkpoint 含之前 cursor/outcome；同步函数第二次调用收到
     续跑上下文）；
   - 取消（is_cancelled）后 checkpoint outcome=cancelled 且 last_success_at 保留；
   - dry_run 不写 checkpoint（零副作用）；
   - 并发推进不倒退（两个协程同时推进同一 checkpoint，version 冲突路径）；
   - detail_json 只存白名单聚合统计（敏感 key 不落库）。
4. SyncResult.checkpoint 不再是 None（运行后）。
"""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.sync_checkpoint import SyncCheckpoint, sanitize_detail_json
from app.services.sync_coordinator import (
    SyncCheckpointStore,
    SyncRequest,
    get_run_checkpoint,
    push_sync_progress,
    run_sync,
    set_checkpoint_store,
)
from app.tasks.resource_guard import admission_controller

# =============================================================================
# fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_admission():
    """每个测试前后清理 admission_controller 单例状态（防进程级状态泄漏）。"""
    admission_controller.reset_state()
    yield
    admission_controller.reset_state()


@pytest.fixture
async def checkpoint_env():
    """独立内存库（aiosqlite + StaticPool）：sync_checkpoints 表 + 绑定 store。

    同时把全局 _CHECKPOINT_STORE 换成本 store，供 run_sync 集成测试使用；
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
    set_checkpoint_store(store)
    env = SimpleNamespace(store=store, session_factory=Session, engine=engine)
    try:
        yield env
    finally:
        set_checkpoint_store(None)
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
    """构造带 store 的伪 FastAPI 实例。"""
    store = SimpleNamespace()
    store.get_snapshot = AsyncMock(return_value=vos or [])
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    app.state.store = store
    return app


async def _checkpoint_count(checkpoint_env) -> int:
    """查询表内检查点行数。"""
    async with checkpoint_env.session_factory() as db:
        count = (await db.execute(select(func.count()).select_from(SyncCheckpoint))).scalar()
        return int(count or 0)


# =============================================================================
# 1. 模型 CRUD + 唯一约束
# =============================================================================


class TestModelCrudAndUniqueConstraint:
    async def test_get_or_create_roundtrip_and_idempotent(self, checkpoint_env):
        """get_or_create 创建字段正确；重复调用返回同一行；sync_type 隔离。"""
        store = checkpoint_env.store
        row = await store.get_or_create("dl_001", "info")
        assert row["downloader_id"] == "dl_001"
        assert row["sync_type"] == "info"
        assert row["outcome"] is None  # 新建行无历史终态
        assert row["version"] == 0
        assert row["cycle_started_at"] is not None
        assert row["last_attempt_at"] is not None

        again = await store.get_or_create("dl_001", "info")
        assert again["id"] == row["id"]  # 幂等：不重复创建

        other = await store.get_or_create("dl_001", "tracker")
        assert other["id"] != row["id"]  # 不同 sync_type 是独立行

        assert await _checkpoint_count(checkpoint_env) == 2

    async def test_unique_constraint_blocks_duplicate_insert(self, checkpoint_env):
        """同 (downloader_id, sync_type) 直接插入第二行 → IntegrityError。"""
        now = datetime.utcnow()
        Session = checkpoint_env.session_factory
        async with Session() as db:
            db.add(
                SyncCheckpoint(
                    downloader_id="dl_001",
                    sync_type="info",
                    cycle_started_at=now,
                    last_attempt_at=now,
                )
            )
            await db.commit()
        with pytest.raises(IntegrityError):
            async with Session() as db:
                db.add(
                    SyncCheckpoint(
                        downloader_id="dl_001",
                        sync_type="info",
                        cycle_started_at=now,
                        last_attempt_at=now,
                    )
                )
                await db.commit()

    async def test_model_to_dict_serializes_datetimes(self, checkpoint_env):
        """模型 to_dict 输出 UTC ISO 字符串（对外契约）。"""
        row = await checkpoint_env.store.get_or_create("dl_001", "info")
        async with checkpoint_env.session_factory() as db:
            orm_row = (await db.execute(select(SyncCheckpoint).where(SyncCheckpoint.id == row["id"]))).scalar_one()
            dumped = orm_row.to_dict()
        assert dumped["downloader_id"] == "dl_001"
        assert dumped["cursor"] is None
        assert dumped["outcome"] is None
        assert dumped["cycle_started_at"].endswith("Z")  # UTC ISO-8601
        assert dumped["last_attempt_at"].endswith("Z")


# =============================================================================
# 2. 乐观锁冲突：更新不倒退
# =============================================================================


class TestOptimisticLock:
    async def test_version_conflict_does_not_regress_cursor(self, checkpoint_env):
        """两个写者持同一 stale 版本推进：冲突方重试成功但游标不倒退。"""
        store = checkpoint_env.store
        row = await store.get_or_create("dl_001", "info")

        out1 = await store.advance(row["id"], 0, cursor="c1")
        assert out1["applied"] is True
        assert out1["conflicts"] == 0

        # 第二个写者仍持旧版本快照（模拟并发写者共享同一 stale 视图）
        out2 = await store.advance(row["id"], 0, cursor="c2")
        assert out2["applied"] is True  # 冲突后重读重试成功
        assert out2["conflicts"] == 1
        fresh = out2["checkpoint"]
        assert fresh["version"] == 2
        assert fresh["cursor"] == "c1"  # 不倒退：既有游标不被旧写者覆盖
        assert fresh["outcome"] == "partial"

    async def test_advance_conflict_does_not_downgrade_terminal_outcome(self, checkpoint_env):
        """对方已落终态时，冲突重试不把终态降级为 partial。"""
        store = checkpoint_env.store
        row = await store.get_or_create("dl_001", "info")
        await store.finalize(row["id"], 0, outcome="success", last_success=True)

        out = await store.advance(row["id"], 0, cursor="c3")  # 基于旧版本（stale）
        assert out["applied"] is True
        assert out["conflicts"] == 1
        fresh = out["checkpoint"]
        assert fresh["outcome"] == "success"  # 终态不被进行中状态降级
        assert fresh["last_success_at"] is not None

    async def test_finalize_failure_outcome_keeps_last_success_at(self, checkpoint_env):
        """finalize(failed) 只更新 outcome + last_attempt_at，last_success_at 保留。"""
        store = checkpoint_env.store
        row = await store.get_or_create("dl_001", "info")
        await store.advance(row["id"], 0, cursor="c1")
        fresh = await store.get_or_create("dl_001", "info")
        last_success = fresh["last_success_at"]

        out = await store.finalize(fresh["id"], fresh["version"], outcome="failed")
        assert out["applied"] is True
        finalized = out["checkpoint"]
        assert finalized["outcome"] == "failed"
        assert finalized["last_success_at"] == last_success  # 保留最近成功提交时间
        assert finalized["last_full_sync_at"] is None


# =============================================================================
# 3. Coordinator 集成
# =============================================================================


class TestCoordinatorIntegration:
    async def test_first_run_creates_checkpoint(self, checkpoint_env):
        """run_sync 首次运行后 checkpoint 创建（outcome/last_attempt_at/cycle_started_at 正确）。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=AsyncMock()):
            result = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual"),
                app=app,
            )

        assert result.outcome == "success"
        # SyncResult.checkpoint 不再是 None，且含读取时快照字段
        assert result.checkpoint is not None
        assert len(result.checkpoint) == 1
        entry = result.checkpoint[0]
        assert entry["downloader_id"] == "dl_001"
        assert entry["sync_type"] == "info"
        assert "cursor" in entry and "cycle_started_at" in entry and "outcome" in entry

        row = await checkpoint_env.store.get_or_create("dl_001", "info")
        assert row["outcome"] == "success"
        assert row["last_attempt_at"] is not None
        assert row["cycle_started_at"] is not None
        assert row["last_success_at"] is not None
        # 无游标 → 本轮覆盖全部 → 记录最近完整覆盖时间
        assert row["last_full_sync_at"] is not None
        assert row["version"] == 2  # 推进(1) + 终态(1)

    async def test_restart_resume_from_checkpoint(self, checkpoint_env):
        """中断（部分批次已提交）后重启：checkpoint 记 partial + last_success_at + cursor，续跑上下文传递。"""
        app = make_fake_app(
            [
                make_vo(downloader_id="dl_001", client=MagicMock()),
                make_vo(downloader_id="dl_002", client=MagicMock()),
            ]
        )
        resumed: dict = {}

        async def first_run_mock(db, downloaders, client=None):
            did = str(downloaders[0].downloader_id)
            if did == "dl_002":
                raise RuntimeError("下载器2中途异常（模拟部分批次已提交后中断）")
            # dl_001 正常完成并推进游标（W3-1 语义：批次 durable commit 后推进）
            await push_sync_progress("dl_001", cursor="hash-100", detail={"scanned": 42})

        with patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=first_run_mock):
            first = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001", "dl_002"], trigger="manual"),
                app=app,
            )

        assert first.outcome == "partial"  # 1 成功 + 1 失败
        row = await checkpoint_env.store.get_or_create("dl_001", "info")
        assert row["outcome"] == "partial"
        assert row["last_success_at"] is not None
        assert row["cursor"] == "hash-100"

        # 第二次运行（重启续跑）：读取 checkpoint，游标/outcome 透传
        async def second_run_mock(db, downloaders, client=None):
            did = str(downloaders[0].downloader_id)
            resumed[did] = get_run_checkpoint(did)

        with patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=second_run_mock):
            second = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001", "dl_002"], trigger="manual"),
                app=app,
            )

        assert second.outcome == "success"
        # SyncResult.checkpoint 含之前 cursor/outcome（读取时快照）
        by_dl = {entry["downloader_id"]: entry for entry in second.checkpoint}
        assert by_dl["dl_001"]["cursor"] == "hash-100"
        assert by_dl["dl_001"]["outcome"] == "partial"
        # 同步函数第二次调用收到续跑上下文
        assert resumed.get("dl_001") is not None
        assert resumed["dl_001"]["cursor"] == "hash-100"
        assert resumed["dl_001"]["outcome"] == "partial"

    async def test_cancel_sets_checkpoint_cancelled_preserving_last_success(self, checkpoint_env):
        """取消后 checkpoint outcome=cancelled 且 last_success_at 保留（已提交批次成果不清零）。"""
        app = make_fake_app(
            [
                make_vo(downloader_id="dl_001", client=MagicMock()),
                make_vo(downloader_id="dl_002", client=MagicMock()),
            ]
        )
        state = {"write_calls": 0}

        async def counting_sync(db, downloaders, client=None):
            state["write_calls"] += 1

        def is_cancelled():
            # 第一个下载器完成后取消（阶段间检查点）
            return state["write_calls"] >= 1

        with patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=counting_sync):
            result = await run_sync(
                SyncRequest(
                    sync_type="info",
                    downloader_ids=["dl_001", "dl_002"],
                    trigger="manual",
                    is_cancelled=is_cancelled,
                ),
                app=app,
            )

        assert result.outcome == "cancelled"
        row = await checkpoint_env.store.get_or_create("dl_001", "info")
        assert row["outcome"] == "cancelled"
        assert row["last_success_at"] is not None  # 取消不清空最近成功提交时间
        # 未运行的下载器：只创建了行，无成功提交时间
        row2 = await checkpoint_env.store.get_or_create("dl_002", "info")
        assert row2["outcome"] == "cancelled"
        assert row2["last_success_at"] is None

    async def test_dry_run_does_not_write_checkpoint(self, checkpoint_env):
        """dry_run 零副作用：不读不写检查点，表内无任何行。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=AsyncMock()) as mock_qb:
            result = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual", dry_run=True),
                app=app,
            )

        assert mock_qb.await_count == 0
        assert result.outcome == "no_action"
        assert result.checkpoint is None
        assert await _checkpoint_count(checkpoint_env) == 0


# =============================================================================
# 4. 并发推进不倒退（version 冲突路径）
# =============================================================================


class TestConcurrentAdvance:
    async def test_concurrent_advance_no_regression(self, checkpoint_env):
        """两个协程基于同一 stale 版本并发推进：冲突方重试成功，游标不丢失不倒退。"""
        store = checkpoint_env.store
        row = await store.get_or_create("dl_001", "info")

        outs = await asyncio.gather(
            store.advance(row["id"], 0, cursor="cursor-x", detail={"scanned": 10}),
            store.advance(row["id"], 0, cursor="cursor-x", detail={"scanned": 10}),
        )
        assert all(out["applied"] for out in outs)  # 冲突方重读重试后仍推进成功
        assert sum(out["conflicts"] for out in outs) == 1

        fresh = await store.get_or_create("dl_001", "info")
        assert fresh["version"] == 2
        assert fresh["cursor"] == "cursor-x"  # 游标保留
        assert fresh["outcome"] == "partial"


# =============================================================================
# 5. detail_json 白名单（禁止敏感数据）
# =============================================================================


class TestDetailWhitelist:
    def test_sanitize_detail_json_keeps_aggregates_only(self):
        """含种子 hash/Tracker URL/凭据的 detail 只保留白名单聚合统计。"""
        raw = {
            "scanned": 10,
            "changed": 5,
            "committed": 5,
            "batches": 2,
            "retries": 0,
            "duration_ms": 12.5,
            "hash": "abc123deadbeef",
            "announce_url": "https://tracker.example/announce",
            "password": "secret",
            "cookie": "sid=xxx",
            "username": "admin",
        }
        cleaned = json.loads(sanitize_detail_json(raw) or "{}")
        assert cleaned == {
            "scanned": 10,
            "changed": 5,
            "committed": 5,
            "batches": 2,
            "retries": 0,
            "duration_ms": 12.5,
        }
        sensitive = {"hash", "announce_url", "password", "cookie", "username"}
        assert not (sensitive & cleaned.keys()), f"敏感 key 不应落库: {cleaned}"

    async def test_advance_persists_whitelisted_detail_only(self, checkpoint_env):
        """推进落库的 detail_json 只含白名单 key，数值字符串归一化。"""
        store = checkpoint_env.store
        row = await store.get_or_create("dl_001", "info")
        out = await store.advance(
            row["id"],
            0,
            cursor="c",
            detail={
                "scanned": 100,
                "committed": "90",  # 数值字符串归一
                "hash": "abc",
                "passkey": "pk",
                "url": "https://x/announce",
            },
        )
        fresh = out["checkpoint"]
        assert fresh["detail"] == {"scanned": 100, "committed": 90.0}
