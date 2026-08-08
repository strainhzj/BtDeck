# -*- coding: utf-8 -*-
"""
tracker_status_sync 服务层单测（W1-2 只写变化行）

【覆盖目标】
1. 无关键词 / 无 Tracker：提前返回，不写库不 commit。
2. 变化检测：全不变（DML=0/commit=0）、部分变化（只写变化行）、全部变化。
3. 判定规则保留：精确匹配优先于部分匹配、大小写不敏感部分匹配、
   重复关键词保留后读取、全部 failed→error / 有 success|ignored→normal /
   其他→unknown（含 candidate 关键词判 unknown）。
4. 消息兜底：无 announce_msg 用 scrape_msg；host 为空从 URL 提取；空消息跳过。
5. 开关回退：SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED=False 时全部写回。
6. 大数据集分块：commit 次数 == ceil(n/batch_size)。
7. 兼容包装：update_tracker_status_from_keywords 返回旧字段 + 新字段，
   无关键词/无 tracker 保持原消息语义。
8. 架构断言：端点层函数体不再直接执行 UPDATE（无 sa_update）。

【测试装配】
- async_tracker_sync_db fixture（tests/services/conftest.py）：内存 aiosqlite，
  只建 TrackerInfo + TrackerKeywordConfig 两张表。
- commit spy / run_sync spy 挂在 fixture session 上，断言零变化零 DML。
- 兼容包装测试用 patch("app.database.AsyncSessionLocal") 指向内存库 sessionmaker。
"""

import inspect
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.tracker_status_sync import TrackerStatusStats, sync_tracker_status_from_keywords
from app.tasks.resource_guard import admission_controller
from app.torrents.models import TrackerInfo, TrackerKeywordConfig

# ==================== 数据构造 helper ====================


def _make_tracker(
    tracker_id,
    host="tracker.example.com",
    announce_msg=None,
    scrape_msg=None,
    status=None,
    msg=None,
    url=None,
    dr=0,
):
    """构造一行 TrackerInfo（torrent_info_id 唯一，避免 (torrent_info_id, tracker_url) 唯一索引冲突）。"""
    return TrackerInfo(
        tracker_id=tracker_id,
        torrent_info_id=f"torrent_{tracker_id}",
        tracker_url=url,
        last_announce_msg=announce_msg,
        last_scrape_msg=scrape_msg,
        tracker_host=host,
        status=status,
        msg=msg,
        create_time=datetime.now(),
        update_time=datetime.now(),
        dr=dr,
    )


def _make_keyword(keyword, keyword_type, enabled=True, dr=0):
    """构造一行关键词（keyword 全局唯一，受 idx_tracker_keyword_unique 约束）。"""
    return TrackerKeywordConfig(
        keyword_type=keyword_type,
        keyword=keyword,
        enabled=enabled,
        dr=dr,
    )


async def _seed(db, *rows):
    """批量插入并真实 commit（发生在 spy 安装之前，不污染 commit 计数）。"""
    db.add_all(rows)
    await db.commit()


async def _fetch_state(db, tracker_id):
    """读取指定 tracker 的 (status, msg)。"""
    row = await db.execute(select(TrackerInfo.status, TrackerInfo.msg).where(TrackerInfo.tracker_id == tracker_id))
    return row.one()


# ==================== spy helper ====================


def _spy_commit(db):
    """包裹 session.commit，记录真实 commit 调用次数。"""
    calls = []
    real_commit = db.commit

    async def spied_commit():
        calls.append(1)
        await real_commit()

    db.commit = spied_commit  # type: ignore[method-assign]
    return calls


def _spy_run_sync(db):
    """包裹 session.run_sync（bulk_insert/bulk_update 的 DML 执行点），记录调用次数。"""
    calls = []
    real_run_sync = db.run_sync

    async def spied_run_sync(*args, **kwargs):
        calls.append(1)
        return await real_run_sync(*args, **kwargs)

    db.run_sync = spied_run_sync  # type: ignore[method-assign]
    return calls


@pytest.fixture(autouse=True)
def _reset_admission():
    """每个测试前后清理 admission_controller 单例状态（db_write_scope 信号量隔离）。"""
    admission_controller.reset_state()
    yield
    admission_controller.reset_state()


# ==================== 1/2. 无关键词 / 无 Tracker ====================


class TestEarlyReturnNoKeywordsNoTrackers:
    """关键词为空 / 无 tracker：提前返回，不写库不 commit。"""

    async def test_no_keywords_skips_db_writes(self, async_tracker_sync_db):
        """关键词表为空：reason=no_keywords，commit=0、run_sync=0、changed=0。"""
        await _seed(
            async_tracker_sync_db,
            _make_tracker("t1", announce_msg="失败"),
            _make_tracker("t2", announce_msg="成功"),
        )
        commits = _spy_commit(async_tracker_sync_db)
        run_sync_calls = _spy_run_sync(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert isinstance(stats, TrackerStatusStats)
        assert stats.reason == "no_keywords"
        assert stats.scanned == 0
        assert stats.changed == 0
        assert stats.unchanged == 0
        assert stats.batches == 0
        assert commits == []
        assert run_sync_calls == []

    async def test_no_trackers_skips_db_writes(self, async_tracker_sync_db):
        """tracker 表为空：reason=no_trackers，commit=0、run_sync=0、changed=0。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("失败", "failed"),
        )
        commits = _spy_commit(async_tracker_sync_db)
        run_sync_calls = _spy_run_sync(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.reason == "no_trackers"
        assert stats.changed == 0
        assert stats.batches == 0
        assert commits == []
        assert run_sync_calls == []

    async def test_no_keywords_wrapper_message(self):
        """兼容包装：无关键词返回 "未加载到任何关键词"，updated_count=0。"""
        engine, maker = await _build_memory_engine()
        async with maker() as db:
            await _seed(db, _make_tracker("t1", announce_msg="失败"))

        from app.api.endpoints.torrent_sync import update_tracker_status_from_keywords

        with patch("app.database.AsyncSessionLocal", maker):
            result = await update_tracker_status_from_keywords()

        assert result["status"] == "success"
        assert result["message"] == "未加载到任何关键词"
        assert result["updated_count"] == 0
        assert result["changed"] == 0
        await engine.dispose()

    async def test_no_trackers_wrapper_message(self):
        """兼容包装：无 tracker 返回 "未发现任何tracker"，updated_count=0。"""
        engine, maker = await _build_memory_engine()
        async with maker() as db:
            await _seed(db, _make_keyword("失败", "failed"))

        from app.api.endpoints.torrent_sync import update_tracker_status_from_keywords

        with patch("app.database.AsyncSessionLocal", maker):
            result = await update_tracker_status_from_keywords()

        assert result["status"] == "success"
        assert result["message"] == "未发现任何tracker"
        assert result["updated_count"] == 0
        await engine.dispose()


# ==================== 3/4/5. 变化检测 ====================


class TestChangeDetection:
    """变化检测：全不变零 DML、部分变化只写变化行、全部变化全写。"""

    async def test_all_unchanged_zero_dml(self, async_tracker_sync_db):
        """判定结果与库中状态一致：changed=0、unchanged=N、commit=0、run_sync=0。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("失败", "failed"),
            _make_keyword("成功", "success"),
            _make_tracker("t1", host="h1", announce_msg="失败", status="error", msg="失败"),
            _make_tracker("t2", host="h2", announce_msg="成功", status="normal", msg="正常"),
        )
        commits = _spy_commit(async_tracker_sync_db)
        run_sync_calls = _spy_run_sync(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.scanned == 2
        assert stats.changed == 0
        assert stats.unchanged == 2
        assert stats.batches == 0
        assert stats.total_hosts == 2
        assert commits == []
        assert run_sync_calls == []

    async def test_partial_change_writes_only_changed_rows(self, async_tracker_sync_db):
        """一半变化一半不变：只写变化行，unchanged 计数正确，库状态按预期落盘。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("失败", "failed"),
            _make_keyword("成功", "success"),
            # 各 tracker 独立 host，方便逐行断言
            _make_tracker("t1", host="h1", announce_msg="失败", status="error", msg="失败"),  # 不变
            _make_tracker("t2", host="h2", announce_msg="失败", status="normal", msg="正常"),  # 变化
            _make_tracker("t3", host="h3", announce_msg="成功", status="normal", msg="正常"),  # 不变
            _make_tracker("t4", host="h4", announce_msg="成功", status="unknown", msg="未知"),  # 变化
        )
        commits = _spy_commit(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.scanned == 4
        assert stats.changed == 2
        assert stats.unchanged == 2
        assert stats.batches == 1
        assert len(commits) == 1

        # 变化行已落盘，不变行保持原值
        assert await _fetch_state(async_tracker_sync_db, "t2") == ("error", "失败")
        assert await _fetch_state(async_tracker_sync_db, "t4") == ("normal", "正常")
        assert await _fetch_state(async_tracker_sync_db, "t1") == ("error", "失败")
        assert await _fetch_state(async_tracker_sync_db, "t3") == ("normal", "正常")

    async def test_all_changed_writes_everything(self, async_tracker_sync_db):
        """全部变化：changed=N、unchanged=0，所有行写入。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("失败", "failed"),
            _make_tracker("t1", host="h1", announce_msg="失败", status="normal", msg="正常"),
            _make_tracker("t2", host="h2", announce_msg="失败", status="unknown", msg="未知"),
            _make_tracker("t3", host="h3", announce_msg="失败", status=None, msg=None),
        )
        commits = _spy_commit(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.scanned == 3
        assert stats.changed == 3
        assert stats.unchanged == 0
        assert stats.batches == 1
        assert len(commits) == 1
        for tid in ("t1", "t2", "t3"):
            assert await _fetch_state(async_tracker_sync_db, tid) == ("error", "失败")

    async def test_strip_normalization_treats_trailing_space_as_unchanged(self, async_tracker_sync_db):
        """strip 归一化：库中 msg 带尾空格 / None 与判定结果等价，不视为变化。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("失败", "failed"),
            _make_keyword("成功", "success"),
            _make_tracker("t1", host="h1", announce_msg="失败", status="error", msg="失败 "),  # 尾空格
            _make_tracker("t2", host="h2", announce_msg="成功", status="normal", msg=None),  # None
        )
        commits = _spy_commit(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.unchanged == 1  # t1：尾空格不视为变化
        assert stats.changed == 1  # t2：normal + msg None → msg "正常" 是真实变化
        assert len(commits) == 1


# ==================== 6. 判定规则保留 ====================


class TestJudgmentRulesPreserved:
    """判定规则语义逐行保留（与端点层原实现一致）。"""

    async def test_exact_match_priority_over_partial(self, async_tracker_sync_db):
        """精确匹配优先：msg 精确命中 'ok done'（success），不会被部分匹配 'ok'（failed）抢占。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("ok", "failed"),
            _make_keyword("ok done", "success"),
            _make_tracker("t1", announce_msg="ok done", status="unknown", msg="未知"),
        )

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.changed == 1
        assert await _fetch_state(async_tracker_sync_db, "t1") == ("normal", "正常")

    async def test_partial_match_case_insensitive(self, async_tracker_sync_db):
        """部分匹配大小写不敏感：'Connection TimeOut' 命中关键词 'timeout' → error。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("timeout", "failed"),
            _make_tracker("t1", announce_msg="Connection TimeOut", status="unknown", msg="未知"),
        )

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.changed == 1
        assert await _fetch_state(async_tracker_sync_db, "t1") == ("error", "失败")

    async def test_duplicate_keyword_keeps_first_read(self, async_tracker_sync_db):
        """重复关键词保留先读取的（与端点层原实现逐行一致）。

        注意：原代码 `if kw.keyword not in keyword_map` 只写入首见值——注释
        "如果重复，保留后读取的"与实际行为不符，按"判定规则逐行保持"约束
        不改动代码，测试钉住实际行为。
        服务层查询无 ORDER BY：为保证"先读取"确定性，先移除 keyword 表全部
        索引（避免查询计划走 idx_tracker_keyword_type_enabled 等索引导致顺序
        不可控），再用原始 INSERT 按显式顺序写入——ORM add_all 的 executemany
        会按随机 keyword_id 排序，顺序不可控。无索引后全表扫描按 rowid 顺序。
        """
        for idx in (
            "idx_tracker_keyword_unique",
            "idx_tracker_keyword_type_enabled",
            "idx_tracker_keyword_language",
            "idx_tracker_keyword_priority",
        ):
            await async_tracker_sync_db.execute(text(f"DROP INDEX {idx}"))
        now = datetime.now()
        await async_tracker_sync_db.execute(
            insert(TrackerKeywordConfig).values(
                [
                    {
                        "keyword_id": "k_dup_1",
                        "keyword_type": "success",
                        "keyword": "dup",
                        "language": None,
                        "priority": 100,
                        "enabled": True,
                        "category": None,
                        "description": None,
                        "create_time": now,
                        "update_time": now,
                        "create_by": "tester",
                        "update_by": "tester",
                        "dr": 0,
                    },
                    {
                        "keyword_id": "k_dup_2",
                        "keyword_type": "failed",
                        "keyword": "dup",
                        "language": None,
                        "priority": 100,
                        "enabled": True,
                        "category": None,
                        "description": None,
                        "create_time": now,
                        "update_time": now,
                        "create_by": "tester",
                        "update_by": "tester",
                        "dr": 0,
                    },
                ]
            )
        )
        async_tracker_sync_db.add(_make_tracker("t1", announce_msg="dup", status="unknown", msg="未知"))
        await async_tracker_sync_db.commit()

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.changed == 1
        # 首见 "success" 保留 → 精确匹配 success → normal
        assert await _fetch_state(async_tracker_sync_db, "t1") == ("normal", "正常")

    async def test_disabled_keyword_not_loaded(self, async_tracker_sync_db):
        """失效关键词（enabled=False）不参与判定 → unknown。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("超时", "failed"),
            _make_keyword("失败", "failed", enabled=False),
            _make_tracker("t1", host="h1", announce_msg="失败", status=None, msg=None),  # 仅命中失效关键词
            _make_tracker("t2", host="h2", announce_msg="超时", status=None, msg=None),  # 命中启用关键词
        )

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.changed == 2
        assert await _fetch_state(async_tracker_sync_db, "t1") == ("unknown", "未知")
        assert await _fetch_state(async_tracker_sync_db, "t2") == ("error", "失败")

    async def test_host_rule_error_normal_unknown(self, async_tracker_sync_db):
        """host 级规则：全部 failed→error；有 success/ignored→normal；其他→unknown（含 candidate）。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("超时", "failed"),
            _make_keyword("成功", "success"),
            _make_keyword("忽略", "ignored"),
            _make_keyword("候选", "candidate"),
            # A：全部 failed → error
            _make_tracker("t1", host="h_a", announce_msg="超时", status=None, msg=None),
            # B：failed + success 混合 → normal（any success/ignored 优先于 all failed）
            _make_tracker("t2", host="h_b", announce_msg="超时", status=None, msg=None),
            _make_tracker("t3", host="h_b", announce_msg="成功", status=None, msg=None),
            # C：ignored → normal
            _make_tracker("t4", host="h_c", announce_msg="忽略", status=None, msg=None),
            # D：仅 candidate 匹配 → unknown
            _make_tracker("t5", host="h_d", announce_msg="候选", status=None, msg=None),
            # E：无任何关键词匹配 → unknown
            _make_tracker("t6", host="h_e", announce_msg="神秘错误xyz", status=None, msg=None),
        )

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.changed == 6
        assert stats.total_hosts == 5
        assert await _fetch_state(async_tracker_sync_db, "t1") == ("error", "失败")
        assert await _fetch_state(async_tracker_sync_db, "t2") == ("normal", "正常")
        assert await _fetch_state(async_tracker_sync_db, "t3") == ("normal", "正常")
        assert await _fetch_state(async_tracker_sync_db, "t4") == ("normal", "正常")
        assert await _fetch_state(async_tracker_sync_db, "t5") == ("unknown", "未知")
        assert await _fetch_state(async_tracker_sync_db, "t6") == ("unknown", "未知")

    async def test_host_status_applies_to_all_trackers_under_host(self, async_tracker_sync_db):
        """同一 host 下多个 tracker 共享同一判定状态。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("超时", "failed"),
            _make_tracker("t1", host="shared", announce_msg="超时", status=None, msg=None),
            _make_tracker("t2", host="shared", announce_msg="超时", status=None, msg=None),
        )

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.changed == 2
        assert stats.total_hosts == 1
        assert await _fetch_state(async_tracker_sync_db, "t1") == ("error", "失败")
        assert await _fetch_state(async_tracker_sync_db, "t2") == ("error", "失败")


# ==================== 7. 消息兜底 / host 提取 / 空消息跳过 ====================


class TestMsgFallbackAndHostExtraction:
    """无 announce_msg 用 scrape_msg；host 为空从 URL 提取；空消息/无 host 跳过。"""

    async def test_scrape_msg_fallback_and_host_extraction_and_skip(self, async_tracker_sync_db):
        await _seed(
            async_tracker_sync_db,
            _make_keyword("失败", "failed"),
            _make_keyword("成功", "success"),
            # 无 announce_msg → 用 scrape_msg 判定
            _make_tracker("t1", host="h1", announce_msg=None, scrape_msg="失败", status=None, msg=None),
            # host 为空 → 从 URL 提取 hostname
            _make_tracker(
                "t2", host=None, url="http://tracker.example.com/announce", announce_msg="成功", status=None, msg=None
            ),
            # 空消息（announce/scrape 均空）→ 跳过
            _make_tracker("t3", host="h3", announce_msg="", scrape_msg=None, status=None, msg=None),
            # 空白消息 → 跳过
            _make_tracker("t4", host="h4", announce_msg="   ", scrape_msg=None, status=None, msg=None),
            # host 与 URL 均无 → 跳过
            _make_tracker("t5", host=None, url=None, announce_msg="失败", status=None, msg=None),
        )
        commits = _spy_commit(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.scanned == 2  # 只统计参与判定的行
        assert stats.changed == 2
        assert stats.total_hosts == 2
        assert len(commits) == 1
        assert await _fetch_state(async_tracker_sync_db, "t1") == ("error", "失败")
        assert await _fetch_state(async_tracker_sync_db, "t2") == ("normal", "正常")
        # 被跳过的行保持原值（未写入；status 列默认值 "unknown" 在插入时已落库）
        assert await _fetch_state(async_tracker_sync_db, "t3") == ("unknown", None)
        assert await _fetch_state(async_tracker_sync_db, "t4") == ("unknown", None)
        assert await _fetch_state(async_tracker_sync_db, "t5") == ("unknown", None)


# ==================== 8. 开关回退 ====================


class TestIncrementalSwitchFallback:
    """SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED=False：跳过变化检测，全部写回。"""

    async def test_disabled_writes_even_when_all_unchanged(self, async_tracker_sync_db, monkeypatch):
        """全部不变场景下，开关关闭仍全部写入（changed=N，判定规则不变）。"""
        monkeypatch.setattr("app.core.config.settings.SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED", False)
        await _seed(
            async_tracker_sync_db,
            _make_keyword("失败", "failed"),
            _make_tracker("t1", host="h1", announce_msg="失败", status="error", msg="失败"),
            _make_tracker("t2", host="h2", announce_msg="失败", status="error", msg="失败"),
            _make_tracker("t3", host="h3", announce_msg="失败", status="error", msg="失败"),
        )
        commits = _spy_commit(async_tracker_sync_db)
        run_sync_calls = _spy_run_sync(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.scanned == 3
        assert stats.changed == 3
        assert stats.unchanged == 0
        assert stats.batches == 1
        assert len(commits) == 1
        assert len(run_sync_calls) == 1


# ==================== 9. 大数据集分块 ====================


class TestChunkedCommitBatching:
    """变化集按 batch_size 真实分批提交：commit 次数 == ceil(n/batch_size)。"""

    async def test_small_batch_size_commits_ceil_n_over_batch(self, async_tracker_sync_db):
        """5 行变化 + batch_size=2 → commit 3 次（ceil(5/2)）。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("失败", "failed"),
            *[_make_tracker(f"t{i}", host=f"h{i}", announce_msg="失败", status="normal", msg="正常") for i in range(5)],
        )
        commits = _spy_commit(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db, batch_size=2)

        assert stats.changed == 5
        assert stats.batches == 3
        assert len(commits) == 3

    async def test_default_batch_size_over_200_rows(self, async_tracker_sync_db):
        """450 行变化 + 默认批大小（SYNC_DB_COMMIT_BATCH_SIZE=200）→ commit 3 次（ceil(450/200)）。"""
        await _seed(
            async_tracker_sync_db,
            _make_keyword("失败", "failed"),
            *[
                _make_tracker(f"t{i}", host=f"h{i}", announce_msg="失败", status="normal", msg="正常")
                for i in range(450)
            ],
        )
        commits = _spy_commit(async_tracker_sync_db)

        stats = await sync_tracker_status_from_keywords(async_tracker_sync_db)

        assert stats.changed == 450
        assert stats.batches == 3
        assert len(commits) == 3


# ==================== 10/11. 兼容包装 & 架构断言 ====================


async def _build_memory_engine():
    """构造内存 aiosqlite engine + sessionmaker，只建 Tracker 相关两张表。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [TrackerInfo.__table__, TrackerKeywordConfig.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    return engine, maker


class TestCompatWrapper:
    """update_tracker_status_from_keywords 兼容包装返回结构。"""

    async def test_wrapper_returns_legacy_and_new_fields(self):
        """正常路径：返回全部旧字段 + 新增统计字段。"""
        engine, maker = await _build_memory_engine()
        async with maker() as db:
            await _seed(
                db,
                _make_keyword("失败", "failed"),
                _make_keyword("成功", "success"),
                _make_tracker("t1", host="h1", announce_msg="失败", status="unknown", msg="未知"),
                _make_tracker("t2", host="h2", announce_msg="成功", status="unknown", msg="未知"),
            )

        from app.api.endpoints.torrent_sync import update_tracker_status_from_keywords

        with patch("app.database.AsyncSessionLocal", maker):
            result = await update_tracker_status_from_keywords()

        # 旧字段齐全
        assert result["status"] == "success"
        assert result["message"] == "更新完成: 2条成功, 0条失败"
        assert result["updated_count"] == 2
        assert result["failed_count"] == 0
        assert result["total_hosts"] == 2
        # 新字段齐全
        assert result["scanned"] == 2
        assert result["changed"] == 2
        assert result["unchanged"] == 0
        assert result["batches"] == 1
        assert isinstance(result["duration_ms"], float)
        assert result["duration_ms"] >= 0.0
        await engine.dispose()

    async def test_wrapper_error_path_returns_error_dict(self):
        """异常路径：返回 error dict，updated_count=0（与原实现一致）。"""
        from app.api.endpoints.torrent_sync import update_tracker_status_from_keywords

        with patch("app.database.AsyncSessionLocal", side_effect=RuntimeError("boom")):
            result = await update_tracker_status_from_keywords()

        assert result["status"] == "error"
        assert result["updated_count"] == 0
        assert "boom" in result["message"]


class TestEndpointNoDirectUpdate:
    """架构断言：端点层不再承载 Tracker 全表更新业务逻辑。"""

    def test_endpoint_wrapper_has_no_sa_update(self):
        """update_tracker_status_from_keywords 函数体不再直接执行 UPDATE。

        旧实现函数体内有 `from sqlalchemy import update as sa_update` 并执行批量
        UPDATE；W1-2 改为纯兼容包装后函数体只剩服务调用 + 返回结构映射。
        """
        from app.api.endpoints.torrent_sync import update_tracker_status_from_keywords

        src = inspect.getsource(update_tracker_status_from_keywords)
        assert "sa_update" not in src
        assert "sync_tracker_status_from_keywords" in src  # 只调服务层
