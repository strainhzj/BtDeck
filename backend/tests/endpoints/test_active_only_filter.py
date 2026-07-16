"""
get_torrent_infos 的 active_keys 过滤单元测试

覆盖修订计划的四个验证点：
1. active_keys=None → 行为不变（向后兼容）
2. active_keys=空集 → 短路返回 {total:0, data:[]}
3. active_keys={...} 含 >500 项 → 分批注入不抛异常，结果正确（修复 H1: SQLite IN 上限）
4. tuple_ 列顺序测试：(downloader_id, hash) 顺序，防顺序反转静默返回错误结果

并验证活动集合缓存的写入/读取/过期语义（_ActiveKeysCache）。
"""

import sqlite3
import time
from typing import Set, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.endpoints.torrent_crud import get_torrents
from app.api.endpoints.torrent_helpers import get_torrent_infos
from app.api.endpoints.torrent_speed import (
    ActiveKeysSnapshot,
    ActiveSnapshotStatus,
    _ActiveKeysCache,
    _ActiveSpeedGatherResult,
    _DownloaderSpeedResult,
    _gather_active_speeds,
    _active_keys_cache,
    get_active_torrents,
    get_active_keys_snapshot,
)
from app.torrents.models import TorrentInfo


def _make_session():
    """创建内存 SQLite 会话并建表（隔离于真实 DB）。

    需先导入所有模型模块，确保 Base.metadata 注册全部表，避免外键
    （如 downloader_settings → bt_downloaders）找不到被引用表。
    """
    # 导入所有模型，确保 metadata 注册完整（顺序无关，只需触发类定义）
    import app.torrents.models  # noqa: F401
    import app.downloader.models  # noqa: F401
    import app.auth.models  # noqa: F401
    from app.database import Base

    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _make_torrent(info_id, downloader_id, downloader_name, hash_value, status="downloading", dr=0):
    """构造一条未删除的 TorrentInfo（提供 __init__ 所需的全部位置参数）。"""
    return TorrentInfo(
        id_=info_id,
        downloader_id=downloader_id,
        downloader_name=downloader_name,
        torrent_id=info_id,
        hash=hash_value,
        name=info_id,
        save_path="/tmp",
        size=0.0,
        status=status,
        progress=0.0,
        torrent_file="",
        added_date=None,
        completed_date=None,
        ratio="0",
        ratio_limit="0",
        tags="",
        category="",
        super_seeding="0",
        enabled=True,
        create_time=None,
        create_by="test",
        update_time=None,
        update_by="test",
        dr=dr,
    )


def _insert_torrents(db, specs):
    """批量插入 TorrentInfo 测试行。specs: list of tuples forwarded to _make_torrent。"""
    for spec in specs:
        db.add(_make_torrent(*spec))
    db.commit()


# ============ get_torrent_infos active_keys 行为 ============


class TestActiveKeysFilter:
    """active_keys 过滤分支的行为验证。"""

    def test_none_is_backward_compatible(self):
        """active_keys=None 时行为与未传该参数一致（向后兼容）。"""
        db = _make_session()
        _insert_torrents(db, [("i1", "dl_a", "A", "h1")])
        result_none = get_torrent_infos(db, active_keys=None)
        result_default = get_torrent_infos(db)
        assert result_none["total"] == result_default["total"] == 1
        assert len(result_none["data"]) == len(result_default["data"]) == 1

    def test_empty_set_short_circuits(self):
        """空集短路返回 {total:0, data:[]}，不触发 IN() 非法 SQL。"""
        db = _make_session()
        _insert_torrents(
            db,
            [
                ("i1", "dl_a", "A", "h1"),
                ("i2", "dl_b", "B", "h2"),
            ],
        )
        result = get_torrent_infos(db, active_keys=set())
        assert result["total"] == 0
        assert result["data"] == []

    def test_filter_matches_only_active(self):
        """active_keys 集合内的种子才返回，且 total 与 data 长度口径一致。"""
        db = _make_session()
        _insert_torrents(
            db,
            [
                ("i1", "dl_a", "A", "h1"),
                ("i2", "dl_a", "A", "h2"),
                ("i3", "dl_b", "B", "h3"),
            ],
        )
        active_keys: Set[Tuple[str, str]] = {("dl_a", "h1"), ("dl_b", "h3")}
        result = get_torrent_infos(db, active_keys=active_keys)
        assert result["total"] == 2
        hashes = {t.hash for t in result["data"]}
        assert hashes == {"h1", "h3"}

    def test_large_set_does_not_explode_sqlite_limit(self):
        """即使主动把变量上限压低，大集合仍通过 TEMP 表联接正确查询。"""
        db = _make_session()
        _insert_torrents(db, [(f"i{i}", "dl_a", "A", f"h{i:05d}") for i in range(600)])
        active_keys: Set[Tuple[str, str]] = {("dl_a", f"h{i:05d}") for i in range(600)}

        connection_fairy = db.connection().connection
        driver_connection = getattr(connection_fairy, "driver_connection", connection_fairy)
        previous_limit = driver_connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 50)
        try:
            result = get_torrent_infos(db, active_keys=active_keys, limit=1000)
        finally:
            driver_connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, previous_limit)

        assert result["total"] == 600
        assert len(result["data"]) == 600
        leaked_tables = (
            db.execute(
                text("SELECT name FROM sqlite_temp_master " "WHERE type='table' AND name LIKE 'active_torrent_keys_%'")
            )
            .scalars()
            .all()
        )
        assert leaked_tables == []

    def test_column_order_downloader_id_then_hash(self):
        """tuple_ 列顺序 (downloader_id, hash)：同 hash 跨下载器不串台（修复列顺序陷阱）。

        构造 dl_a/h1 与 dl_b/h1（同 hash 不同下载器），active_keys 只含 (dl_a, h1)，
        验证 dl_b/h1 不被误匹配。
        """
        db = _make_session()
        _insert_torrents(
            db,
            [
                ("i1", "dl_a", "A", "h1"),
                ("i2", "dl_b", "B", "h1"),  # 同 hash，不同 downloader
            ],
        )
        active_keys: Set[Tuple[str, str]] = {("dl_a", "h1")}
        result = get_torrent_infos(db, active_keys=active_keys)
        assert result["total"] == 1
        assert result["data"][0].downloader_id == "dl_a"
        assert result["data"][0].hash == "h1"


# ============ _ActiveKeysCache 缓存语义 ============


class TestActiveKeysCache:
    """活动集合缓存的写入/读取/过期/空状态语义。"""

    def test_not_ready_before_first_write(self):
        """冷启动不是权威空集。"""
        cache = _ActiveKeysCache(ttl=5.0)
        snapshot = cache.snapshot()
        assert snapshot.status == ActiveSnapshotStatus.NOT_READY
        assert snapshot.ready is False
        assert snapshot.keys == frozenset()

    def test_update_then_snapshot(self):
        cache = _ActiveKeysCache(ttl=5.0)
        keys: Set[Tuple[str, str]] = {("dl_a", "h1"), ("dl_b", "h2")}
        cache.update_complete(keys)
        snapshot = cache.snapshot()
        assert snapshot.status == ActiveSnapshotStatus.READY
        assert snapshot.ready is True
        assert snapshot.keys == frozenset(keys)

    def test_update_copies_input(self):
        """调用方后续修改输入集合不会污染缓存。"""
        cache = _ActiveKeysCache(ttl=5.0)
        keys = {("dl_a", "h1")}
        cache.update_complete(keys)
        keys.add(("dl_b", "h2"))
        assert cache.snapshot().keys == frozenset({("dl_a", "h1")})

    def test_expired_is_not_ready(self):
        cache = _ActiveKeysCache(ttl=0.01)
        cache.update_complete({("dl_a", "h1")})
        time.sleep(0.02)
        snapshot = cache.snapshot()
        assert snapshot.status == ActiveSnapshotStatus.EXPIRED
        assert snapshot.ready is False
        assert snapshot.keys == frozenset()

    def test_authoritative_empty_is_ready(self):
        cache = _ActiveKeysCache(ttl=5.0)
        cache.update_complete(set())
        snapshot = cache.snapshot()
        assert snapshot.status == ActiveSnapshotStatus.READY_EMPTY
        assert snapshot.ready is True
        assert snapshot.keys == frozenset()

    def test_partial_refresh_invalidates_previous_complete_snapshot(self):
        cache = _ActiveKeysCache(ttl=5.0)
        cache.update_complete({("dl_a", "h1")})
        cache.mark_partial()
        snapshot = cache.snapshot()
        assert snapshot.status == ActiveSnapshotStatus.PARTIAL
        assert snapshot.ready is False
        assert snapshot.keys == frozenset()

    def test_update_replaces_not_merges(self):
        """全量覆写：失活的种子在下次轮询后自动剔除。"""
        cache = _ActiveKeysCache(ttl=5.0)
        cache.update_complete({("dl_a", "h1"), ("dl_a", "h2")})
        cache.update_complete({("dl_a", "h1")})  # h2 不再活动
        assert cache.snapshot().keys == frozenset({("dl_a", "h1")})


# ============ get_active_keys_snapshot 模块入口 ============


class TestGetActiveKeysSnapshot:
    """模块级读取入口的集成验证。"""

    def test_snapshot_entry_reads_global_cache(self):
        """get_active_keys_snapshot 读取全局 _active_keys_cache。"""
        try:
            _active_keys_cache.update_complete({("dl_x", "hx")})
            assert get_active_keys_snapshot().keys == frozenset({("dl_x", "hx")})
        finally:
            _active_keys_cache.reset()
        assert get_active_keys_snapshot().status == ActiveSnapshotStatus.NOT_READY


# ============ _gather_active_speeds 抽取零回归 ============


class TestGatherActiveSpeedsExtraction:
    """验证 _gather_active_speeds 从 active-torrents 端点抽取后行为不变：
    snapshot → 并发取速 → 扁平化打 downloader_id/downloader_type 标签。"""

    @pytest.mark.asyncio
    async def test_flatten_and_tag_downloader(self):
        """两个下载器各自返回的活动种子被扁平化并打上所属下载器标签。"""
        dl_a = MagicMock(downloader_id="dl_a", downloader_type=0)
        dl_b = MagicMock(downloader_id="dl_b", downloader_type=1)

        # _process_downloader_speeds 内部走 _call_with_timeout（需网络），patch 掉
        async def fake_process(d):
            if getattr(d, "downloader_id", "") == "dl_a":
                return _DownloaderSpeedResult([{"hash": "h1", "downloadSpeed": 10, "uploadSpeed": 0}], True)
            return _DownloaderSpeedResult([{"hash": "h2", "downloadSpeed": 0, "uploadSpeed": 5}], True)

        with patch("app.api.endpoints.torrent_speed._process_downloader_speeds", side_effect=fake_process):
            result = await _gather_active_speeds([dl_a, dl_b])

        assert result.complete is True
        assert len(result.torrents) == 2
        by_hash = {t["hash"]: t for t in result.torrents}
        assert by_hash["h1"]["downloader_id"] == "dl_a"
        assert by_hash["h1"]["downloader_type"] == 0
        assert by_hash["h2"]["downloader_id"] == "dl_b"
        assert by_hash["h2"]["downloader_type"] == 1

    @pytest.mark.asyncio
    async def test_empty_downloaders(self):
        """无在线下载器时返回空列表。"""
        result = await _gather_active_speeds([])
        assert result == _ActiveSpeedGatherResult([], True)

    @pytest.mark.asyncio
    async def test_partial_downloader_failure_is_reported(self):
        dl_a = MagicMock(downloader_id="dl_a", downloader_type=0)
        dl_b = MagicMock(downloader_id="dl_b", downloader_type=1)

        async def fake_process(d):
            if getattr(d, "downloader_id", "") == "dl_a":
                return _DownloaderSpeedResult([{"hash": "h1", "downloadSpeed": 10, "uploadSpeed": 0}], True)
            return _DownloaderSpeedResult([], False)

        with patch("app.api.endpoints.torrent_speed._process_downloader_speeds", side_effect=fake_process):
            result = await _gather_active_speeds([dl_a, dl_b])

        assert result.complete is False
        assert [item["hash"] for item in result.torrents] == ["h1"]


def _call_get_torrents(db, *, active_only=True):
    return get_torrents(
        downloader_id=None,
        downloader_name_like=None,
        name_like=None,
        save_path_like=None,
        size_min=None,
        size_max=None,
        added_date_min=None,
        added_date_max=None,
        completed_date_min=None,
        completed_date_max=None,
        tags_like=None,
        category_like=None,
        tracker_like=None,
        status=None,
        skip=0,
        limit=100,
        sort_by=None,
        sort_order="desc",
        active_only=active_only,
        _user=object(),
        db=db,
    )


class TestActiveOnlyEndpointWiring:
    def test_not_ready_returns_206_without_querying_database(self):
        snapshot = ActiveKeysSnapshot(frozenset(), ActiveSnapshotStatus.NOT_READY)
        with (
            patch("app.api.endpoints.torrent_crud.get_active_keys_snapshot", return_value=snapshot),
            patch("app.api.endpoints.torrent_crud.get_torrent_infos") as query,
        ):
            response = _call_get_torrents(MagicMock())

        query.assert_not_called()
        assert response.code == "206"
        assert response.data["activeSnapshotReady"] is False
        assert response.data["activeSnapshotStatus"] == "not_ready"

    def test_authoritative_empty_returns_normal_empty_result(self):
        snapshot = ActiveKeysSnapshot(frozenset(), ActiveSnapshotStatus.READY_EMPTY)
        with (
            patch("app.api.endpoints.torrent_crud.get_active_keys_snapshot", return_value=snapshot),
            patch(
                "app.api.endpoints.torrent_crud.get_torrent_infos",
                return_value={"total": 0, "data": []},
            ) as query,
        ):
            response = _call_get_torrents(MagicMock())

        assert query.call_args.kwargs["active_keys"] == set()
        assert response.code == "200"
        assert response.data["list"] == []
        assert response.data["activeSnapshotReady"] is True
        assert response.data["activeSnapshotStatus"] == "ready_empty"

    def test_ready_snapshot_passes_exact_composite_keys(self):
        keys = frozenset({("dl_a", "h1"), ("dl_b", "h2")})
        snapshot = ActiveKeysSnapshot(keys, ActiveSnapshotStatus.READY)
        with (
            patch("app.api.endpoints.torrent_crud.get_active_keys_snapshot", return_value=snapshot),
            patch(
                "app.api.endpoints.torrent_crud.get_torrent_infos",
                return_value={"total": 2, "data": []},
            ) as query,
        ):
            response = _call_get_torrents(MagicMock())

        assert query.call_args.kwargs["active_keys"] == set(keys)
        assert response.code == "200"
        assert response.data["activeSnapshotReady"] is True


class TestActiveSpeedEndpointWiring:
    @pytest.mark.asyncio
    async def test_partial_gather_marks_cache_partial_and_returns_206(self):
        request = MagicMock()
        request.app.state.store.get_snapshot = AsyncMock(return_value=[MagicMock()])
        gathered = _ActiveSpeedGatherResult(
            [{"downloader_id": "dl_a", "hash": "h1", "downloadSpeed": 1, "uploadSpeed": 0}],
            False,
        )
        _active_keys_cache.update_complete({("old", "old")})
        try:
            with (
                patch(
                    "app.api.endpoints.torrent_speed._gather_active_speeds",
                    new=AsyncMock(return_value=gathered),
                ),
                patch("app.api.endpoints.torrent_speed._ttl_queue.get_disappeared", return_value={}),
            ):
                response = await get_active_torrents(request, _user=object())

            assert response.code == "206"
            assert _active_keys_cache.snapshot().status == ActiveSnapshotStatus.PARTIAL
        finally:
            _active_keys_cache.reset()

    @pytest.mark.asyncio
    async def test_no_cached_downloaders_is_authoritative_empty(self):
        request = MagicMock()
        request.app.state.store.get_snapshot = AsyncMock(return_value=[])
        try:
            response = await get_active_torrents(request, _user=object())
            snapshot = _active_keys_cache.snapshot()
            assert response.code == "200"
            assert snapshot.status == ActiveSnapshotStatus.READY_EMPTY
            assert snapshot.ready is True
        finally:
            _active_keys_cache.reset()
