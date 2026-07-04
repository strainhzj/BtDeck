# -*- coding: utf-8 -*-
"""
tracker 批量写入治理集成测试（阶段 2.5 P0 核心）

【测试分层】
用真实 SQLite（aiosqlite :memory: + StaticPool + create_all）验证 SQL 语义，
覆盖 mock 测不到的部分索引 on_conflict_do_update(index_where dr=0) 行为。

【覆盖目标】
1. 变更检测：相同 tracker 状态 → skip，不触发 upsert。
2. 软删行（dr=1）不复活：upsert 不会让 dr=1 行变 dr=0。
3. mark_removed 元组语义：种子 A 独有 url 不被种子 B 误删（审查1-C6 必修2）。
4. 插入新行 vs 更新现有行的统计正确。
5. db_write_scope 进入（真实信号量 acquire spy）。
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.torrents.models import TrackerInfo as trackerInfoModel


@pytest.fixture
async def tracker_db():
    """异步内存 SQLite，建 tracker_info 表（含部分索引 idx_tracker_unique_url）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[trackerInfoModel.__table__]))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=[trackerInfoModel.__table__]))


def _make_row(info_id: str, url: str, *, announce_msg: str = "ok", host: str = "h", name: str = "n") -> dict:
    """构造单个 tracker row dict。"""
    return {
        "tracker_id": str(uuid.uuid4()),
        "torrent_info_id": info_id,
        "tracker_name": name,
        "tracker_url": url,
        "tracker_host": host,
        "last_announce_succeeded": 1,
        "last_announce_msg": announce_msg,
        "last_scrape_succeeded": 1,
        "last_scrape_msg": announce_msg,
        "create_time": datetime.now(),
        "create_by": "admin",
        "update_time": datetime.now(),
        "update_by": "admin",
        "dr": 0,
    }


class TestSyncTrackersBatchChangeDetection:
    """变更检测：相同状态跳过，不同状态 upsert。"""

    async def test_unchanged_trackers_skipped(self, tracker_db):
        """相同 tracker 状态的行不触发 upsert（stats["skip"] 计数）。"""
        from app.api.endpoints.torrents_async import sync_trackers_batch_async

        info_id = "info-1"
        # 先插入旧数据
        old_row = trackerInfoModel(
            tracker_id=str(uuid.uuid4()),
            torrent_info_id=info_id,
            tracker_name="tracker.example.com",
            tracker_url="http://tracker.example.com/announce",
            tracker_host="tracker.example.com",
            last_announce_succeeded=1,
            last_announce_msg="ok",
            last_scrape_succeeded=1,
            last_scrape_msg="ok",
            create_time=datetime.now(),
            create_by="admin",
            update_time=datetime.now(),
            update_by="admin",
            dr=0,
        )
        tracker_db.add(old_row)
        await tracker_db.commit()

        # 构造相同状态的新 row
        new_rows = [
            _make_row(
                info_id,
                "http://tracker.example.com/announce",
                announce_msg="ok",
                host="tracker.example.com",
                name="tracker.example.com",
            )
        ]
        stats = await sync_trackers_batch_async(tracker_db, new_rows, datetime.now())

        # 关键断言：skip=1，insert/update=0
        assert stats["skip"] == 1
        assert stats["insert"] == 0
        assert stats["update"] == 0

    async def test_changed_trackers_upserted(self, tracker_db):
        """状态变化的行触发 upsert。"""
        from app.api.endpoints.torrents_async import sync_trackers_batch_async

        info_id = "info-2"
        old_row = trackerInfoModel(
            tracker_id=str(uuid.uuid4()),
            torrent_info_id=info_id,
            tracker_name="t",
            tracker_url="http://t/announce",
            tracker_host="t",
            last_announce_succeeded=1,
            last_announce_msg="ok",
            last_scrape_succeeded=1,
            last_scrape_msg="ok",
            create_time=datetime.now(),
            create_by="admin",
            update_time=datetime.now(),
            update_by="admin",
            dr=0,
        )
        tracker_db.add(old_row)
        await tracker_db.commit()

        # 状态变化：announce_msg 从 ok → fail
        new_rows = [_make_row(info_id, "http://t/announce", announce_msg="fail")]
        stats = await sync_trackers_batch_async(tracker_db, new_rows, datetime.now())

        assert stats["update"] == 1
        assert stats["skip"] == 0

        # 验证 DB 中确实更新了（expire_all 排除 identity map 缓存）
        tracker_db.expire_all()
        result = await tracker_db.execute(select(trackerInfoModel).where(trackerInfoModel.torrent_info_id == info_id))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].last_announce_msg == "fail"


class TestSyncTrackersBatchSoftDeleteNoResurrect:
    """软删行（dr=1）不复活。"""

    async def test_soft_deleted_row_not_resurrected(self, tracker_db):
        """dr=1 的软删行在 upsert 后不应变 dr=0（部分索引 dr=0 conflict 不命中→insert 新行）。

        验证：upsert 前 sync_trackers_batch_async 会先 DELETE dr=1 pairs，
        所以最终只剩 1 行 dr=0（新 insert 的），不会留下 dr=1 孤儿。
        """
        from app.api.endpoints.torrents_async import sync_trackers_batch_async

        info_id = "info-3"
        url = "http://t3/announce"
        # 插入软删行
        soft_row = trackerInfoModel(
            tracker_id=str(uuid.uuid4()),
            torrent_info_id=info_id,
            tracker_name="t3",
            tracker_url=url,
            tracker_host="t3",
            last_announce_succeeded=0,
            last_announce_msg="old",
            last_scrape_succeeded=0,
            last_scrape_msg="old",
            create_time=datetime.now(),
            create_by="admin",
            update_time=datetime.now(),
            update_by="admin",
            dr=1,  # 软删
        )
        tracker_db.add(soft_row)
        await tracker_db.commit()

        # upsert 同一 (info_id, url)
        new_rows = [_make_row(info_id, url, announce_msg="new")]
        await sync_trackers_batch_async(tracker_db, new_rows, datetime.now())

        # 查询所有行（含 dr=1）
        result = await tracker_db.execute(select(trackerInfoModel).where(trackerInfoModel.torrent_info_id == info_id))
        rows = result.scalars().all()
        # 关键：不应有 dr=1 孤儿（应被 Step2 物理删除）
        dr1_orphans = [r for r in rows if r.dr == 1]
        assert len(dr1_orphans) == 0, f"不应留下 dr=1 孤儿，实际有 {len(dr1_orphans)} 行"
        # 应有 1 行 dr=0（新 insert 或恢复的）
        dr0 = [r for r in rows if r.dr == 0]
        assert len(dr0) == 1


class TestSyncTrackersBatchMarkRemovedTupleSemantics:
    """mark_removed 元组语义（审查1-C6 必修2）。

    关键场景：种子 A 独有的 url 不应被种子 B 的存在而误删。
    """

    async def test_torrent_a_url_not_removed_by_torrent_b(self, tracker_db):
        """两个种子同时在本批次，各自有独有 url；元组语义保证不误删。

        关键场景（审查1-C6 必修2）：
        - info_A 有 url_a（独有）
        - info_B 有 url_b（独有）
        - 本批次同时更新 A 和 B（两个 info_id 都在 batch_info_ids 内）
        - 扁平化 url 集合 [url_a, url_b] 后，对 info_A 来说 url_a 在集合内不会被删；
          但如果 url_a 不在 B 的批次行里，扁平化逻辑会"正确"——所以要构造更刁钻的场景：
        - info_A 有两个 url：url_shared（与 B 共享同名）+ url_a_only（A 独有）
        - info_B 有 url_b_only（B 独有）
        - 本批次传 info_A 的 url_shared + info_B 的 url_b_only
        - 元组语义：info_A 的 url_a_only 应被 mark_removed（不在批次 pairs）
        - 扁平化 bug：url_a_only 不在 [url_shared, url_b_only] → 也会被 mark_removed（恰好对）
        所以要构造：扁平化会让"应该保留的"被误删。
        - info_A 有 url_a + url_common
        - info_B 有 url_b + url_common
        - 本批次传 info_A 的 url_a + info_B 的 url_b（不传 url_common）
        - 元组语义：(info_A, url_common) 不在批次 → mark_removed； (info_B, url_common) 不在批次 → mark_removed
        - 扁平化：url_common 在 [url_a, url_b] 集合? No，url_common 不在 → 都被 mark_removed（与元组一致）
        真正差异场景：info_A 有 url_x，info_B 没有；本批次传 info_B（不含 url_x）。
        - 元组：(info_A, url_x) 不在批次 pairs → 如果 info_A 不在 batch_info_ids，根本不查。
        所以差异仅在"两个 info_id 都在 batch_info_ids，且 url 集合扁平化后产生跨 info 误判"。
        构造：info_A 有 url_shared；info_B 有 url_shared（同名）+ url_b_only。
        - 本批次传 (info_A, url_shared) + (info_B, url_b_only)
        - 批次 pairs = {(A, url_shared), (B, url_b_only)}
        - 扁平化 urls = {url_shared, url_b_only}
        - info_B 的 url_shared：元组 (B, url_shared) 不在 pairs → 应 mark_removed
          扁平化 url_shared 在集合 → 不 mark_removed（差异！元组会删，扁平化不删）
        所以构造这种"同名 url 跨种子"场景才能暴露差异。
        """
        from app.api.endpoints.torrents_async import sync_trackers_batch_async

        info_a = "info-A"
        info_b = "info-B"
        url_shared = "http://shared/announce"  # A 和 B 都有这个 url
        url_b_only = "http://b-only/announce"  # B 独有

        # 预置：A 有 url_shared，B 有 url_shared + url_b_only
        for info_id in [info_a, info_b]:
            tracker_db.add(
                trackerInfoModel(
                    tracker_id=str(uuid.uuid4()),
                    torrent_info_id=info_id,
                    tracker_name=url_shared,
                    tracker_url=url_shared,
                    tracker_host="h",
                    last_announce_succeeded=1,
                    last_announce_msg="ok",
                    last_scrape_succeeded=1,
                    last_scrape_msg="ok",
                    create_time=datetime.now(),
                    create_by="admin",
                    update_time=datetime.now(),
                    update_by="admin",
                    dr=0,
                )
            )
        tracker_db.add(
            trackerInfoModel(
                tracker_id=str(uuid.uuid4()),
                torrent_info_id=info_b,
                tracker_name=url_b_only,
                tracker_url=url_b_only,
                tracker_host="h",
                last_announce_succeeded=1,
                last_announce_msg="ok",
                last_scrape_succeeded=1,
                last_scrape_msg="ok",
                create_time=datetime.now(),
                create_by="admin",
                update_time=datetime.now(),
                update_by="admin",
                dr=0,
            )
        )
        await tracker_db.commit()

        # 本批次传 (A, url_shared) + (B, url_b_only)，不传 (B, url_shared)
        new_rows = [
            _make_row(info_a, url_shared, announce_msg="changed-a"),
            _make_row(info_b, url_b_only, announce_msg="changed-b"),
        ]
        await sync_trackers_batch_async(tracker_db, new_rows, datetime.now())

        # 关键断言（元组语义）：
        # (B, url_shared) 不在批次 pairs → 应被 mark_removed（dr=1）
        # 扁平化 bug：url_shared 在 [url_shared, url_b_only] 集合 → 不 mark_removed（错误保留 dr=0）
        tracker_db.expire_all()
        result = await tracker_db.execute(select(trackerInfoModel).where(trackerInfoModel.torrent_info_id == info_b))
        b_rows = {r.tracker_url: r.dr for r in result.scalars().all()}
        # 元组语义正确行为：(B, url_shared) 应被 mark_removed
        assert b_rows.get(url_shared) == 1, (
            f"(info_B, url_shared) 应被 mark_removed（元组语义：不在批次 pairs），"
            f"实际 dr={b_rows.get(url_shared)}。若 dr=0 说明用了扁平化 url 集合（bug）。"
        )
        assert b_rows.get(url_b_only) == 0

    async def test_removed_url_marked_dr1_only_for_batch_info_ids(self, tracker_db):
        """mark_removed 只影响本批次涉及的 info_id，且只标记"本 info_id 有但本批次没传的 url"。"""
        from app.api.endpoints.torrents_async import sync_trackers_batch_async

        info_x = "info-X"
        url_keep = "http://keep/announce"
        url_remove = "http://remove/announce"

        # 预置：info_x 有两个 url
        for url in [url_keep, url_remove]:
            tracker_db.add(
                trackerInfoModel(
                    tracker_id=str(uuid.uuid4()),
                    torrent_info_id=info_x,
                    tracker_name=url,
                    tracker_url=url,
                    tracker_host="h",
                    last_announce_succeeded=1,
                    last_announce_msg="ok",
                    last_scrape_succeeded=1,
                    last_scrape_msg="ok",
                    create_time=datetime.now(),
                    create_by="admin",
                    update_time=datetime.now(),
                    update_by="admin",
                    dr=0,
                )
            )
        await tracker_db.commit()

        # 本批次只传 url_keep（url_remove 应被 mark_removed）
        new_rows = [_make_row(info_x, url_keep, announce_msg="changed")]
        stats = await sync_trackers_batch_async(tracker_db, new_rows, datetime.now())

        assert stats["removed"] == 1, f"应标记 1 个 url removed，实际 {stats['removed']}"

        # 验证 url_remove 被标 dr=1，url_keep 仍 dr=0
        result = await tracker_db.execute(select(trackerInfoModel).where(trackerInfoModel.torrent_info_id == info_x))
        rows = {r.tracker_url: r.dr for r in result.scalars().all()}
        assert rows[url_keep] == 0
        assert rows[url_remove] == 1


class TestSyncTrackersBatchDbWriteScope:
    """sync_trackers_batch_async 进入 db_write_scope。"""

    async def test_db_write_scope_entered(self, tracker_db):
        """批量写入时进入 db_write_scope（真实信号量 acquire spy）。"""
        from app.tasks.resource_guard import admission_controller

        with patch("app.core.config.settings.SYNC_DB_WRITE_SCOPE_ENABLED", True):
            admission_controller.reset_state()
            from app.api.endpoints.torrents_async import sync_trackers_batch_async

            real_sem = admission_controller._state.db_writer
            acquire_spy = AsyncMock(wraps=real_sem.acquire)
            with patch.object(real_sem, "acquire", acquire_spy):
                new_rows = [_make_row("info-scope", "http://scope/announce")]
                await sync_trackers_batch_async(tracker_db, new_rows, datetime.now())

            acquire_spy.assert_awaited()
            admission_controller.reset_state()


class TestStatsConservation:
    """stats 守恒：insert + update + skip 应等于传入总行数（error 另算）。"""

    async def test_stats_conservation_mixed_batch(self, tracker_db):
        """混合批次：部分 insert + 部分 update + 部分 skip，三者之和 == 总输入行数。"""
        from app.api.endpoints.torrents_async import sync_trackers_batch_async

        info_new = "info-new"  # 全新，会 insert
        info_existing = "info-existing"  # 已有，测试 update + skip

        # 预置 existing（host/name 与 _make_row 默认值一致，确保 unchanged 那行真不变）
        existing_row = trackerInfoModel(
            tracker_id=str(uuid.uuid4()),
            torrent_info_id=info_existing,
            tracker_name="n",
            tracker_url="http://unchanged/announce",
            tracker_host="h",
            last_announce_succeeded=1,
            last_announce_msg="ok",
            last_scrape_succeeded=1,
            last_scrape_msg="ok",
            create_time=datetime.now(),
            create_by="admin",
            update_time=datetime.now(),
            update_by="admin",
            dr=0,
        )
        changed_row = trackerInfoModel(
            tracker_id=str(uuid.uuid4()),
            torrent_info_id=info_existing,
            tracker_name="n",
            tracker_url="http://changed/announce",
            tracker_host="h",
            last_announce_succeeded=1,
            last_announce_msg="ok",
            last_scrape_succeeded=1,
            last_scrape_msg="ok",
            create_time=datetime.now(),
            create_by="admin",
            update_time=datetime.now(),
            update_by="admin",
            dr=0,
        )
        tracker_db.add_all([existing_row, changed_row])
        await tracker_db.commit()

        new_rows = [
            _make_row(info_new, "http://new/announce"),  # insert
            _make_row(info_existing, "http://changed/announce", announce_msg="diff"),  # update
            _make_row(info_existing, "http://unchanged/announce"),  # skip（状态相同）
        ]

        stats = await sync_trackers_batch_async(tracker_db, new_rows, datetime.now())

        # 守恒断言：insert + update + skip == 总输入行数
        total_in = len(new_rows)
        actual_sum = stats["insert"] + stats["update"] + stats["skip"]
        assert actual_sum == total_in, (
            f"stats 不守恒：insert({stats['insert']}) + update({stats['update']}) + "
            f"skip({stats['skip']}) = {actual_sum} != 输入 {total_in}"
        )
        assert stats["insert"] == 1
        assert stats["update"] == 1
        assert stats["skip"] == 1
