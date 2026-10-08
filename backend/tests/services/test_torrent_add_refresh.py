# -*- coding: utf-8 -*-
"""添加后统一落库/刷新 + tracker 刷新（torrent_add_helpers 二期新增段）单测。

覆盖：
- wait_and_upsert_torrent_row：轮询命中/重试/超时、无行创建（qB torrent_file 推导、
  added_date 兜底）、有行刷新实时字段白名单（不碰身份与管理字段）、落库异常向上抛
- refresh_trackers_after_add：qB/TR 调用契约（lane/operation/投影）、DHT 过滤、
  rows 透传 sync_trackers_batch_async、空 rows 短路、远程异常 best-effort
"""

from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.torrent_add_helpers as helpers
from app.services.torrent_add_helpers import refresh_trackers_after_add, wait_and_upsert_torrent_row

HASH_A = "a" * 40


def _qb_vo(**overrides: Any) -> dict:
    base = {
        "hash": HASH_A,
        "name": "qb-name",
        "size": 1024,
        "state": "downloading",
        "raw_state": "downloading",
        "progress": 42.5,
        "ratio": 0.5,
        "downloaded": 100,
        "uploaded": 50,
        "download_path": "/dl/qb",
        "completion_date": 0,
        "addition_date": 1700000000,
        "category": "cat",
        "tags": "t1",
        "torrent_file": None,
    }
    base.update(overrides)
    return base


def _tr_vo(**overrides: Any) -> dict:
    base = {
        "hash": HASH_A,
        "name": "tr-name",
        "size": 2048,
        "state": "seeding",
        "raw_state": "seeding",
        "progress": 100.0,
        "ratio": 1.5,
        "downloaded": 200,
        "uploaded": 300,
        "download_path": "/dl/tr",
        "completion_date": 1700000600,
        "addition_date": 1700000000,
        "category": "",
        "tags": "l1",
        "torrent_file": "/config/torrents/x.torrent",
    }
    base.update(overrides)
    return base


def _make_store(downloader: Any):
    async def get_snapshot():
        return [downloader]

    return SimpleNamespace(get_snapshot=get_snapshot)


def _make_downloader(downloader_type: int = 0, client: Any = None):
    return SimpleNamespace(
        downloader_id="dl-1", downloader_type=downloader_type, nickname="qb", fail_time=0, client=client or MagicMock()
    )


def _patch_lookup_call_with(vo_results: List[Optional[dict]]):
    """按序返回 VO 列表（None 视为命中失败）的 fake 直调；返回 mock。"""

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        result = vo_results.pop(0) if vo_results else None
        if result is None:
            return []  # 远程返回空列表 = 种子尚未出现
        # 构造可被 _qb_to_vo/_tr_to_vo 读取的 stub（qB 字段名）
        return [
            SimpleNamespace(
                hash=result["hash"],
                name=result["name"],
                size=result["size"],
                state=result["raw_state"],
                progress=result["progress"] / 100.0,
                ratio=result["ratio"],
                downloaded=result["downloaded"],
                uploaded=result["uploaded"],
                save_path=result["download_path"],
                completion_on=result["completion_date"],
                added_on=result["addition_date"],
                category=result["category"],
                tags=result["tags"],
            )
        ]

    return AsyncMock(side_effect=fake_call)


@pytest.fixture
def fast_poll(monkeypatch):
    monkeypatch.setattr(helpers, "ADD_POLL_INTERVAL", 0.0)
    monkeypatch.setattr(helpers, "refresh_trackers_after_add", AsyncMock(return_value=True))


# ---------- wait_and_upsert_torrent_row ----------


async def test_wait_and_upsert_first_miss_then_hit(fast_poll, monkeypatch):
    """首次未出现（空列表）→ 第二次命中：轮询重试语义 + 创建新行。"""
    call_mock = _patch_lookup_call_with([None, _qb_vo()])
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", call_mock)

    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = None
    # 创建路径复用 _insert_torrent_record_with_retry（真实实现：add/commit/refresh）
    row_stub = SimpleNamespace(info_id="i-1")
    insert_mock = AsyncMock(return_value=row_stub)
    monkeypatch.setattr("app.services.torrent_add_helpers._insert_torrent_record_with_retry", insert_mock)

    row, created, err = await wait_and_upsert_torrent_row(
        db, _make_store(_make_downloader()), _make_downloader(), HASH_A, operator="tester"
    )
    assert err is None and created is True and row is row_stub
    assert call_mock.await_count == 2  # miss + hit
    insert_mock.assert_awaited_once()
    factory = insert_mock.await_args.args[1]
    built = factory()
    assert built.hash == HASH_A
    assert built.name == "qb-name"
    # qB 分支 torrent_file 按 BT_backup 约定推导
    assert built.torrent_file == f"/config/qbittorrent/BT_backup/{HASH_A}.torrent"
    assert built.create_by == "tester"


async def test_wait_and_upsert_timeout(fast_poll, monkeypatch):
    call_mock = _patch_lookup_call_with([])
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", call_mock)
    db = MagicMock()
    row, created, err = await wait_and_upsert_torrent_row(
        db, _make_store(_make_downloader()), _make_downloader(), HASH_A, poll_retries=3
    )
    assert row is None and created is False
    assert err is not None and "轮询超时" in err
    assert call_mock.await_count == 3
    db.query.assert_not_called()  # 未命中不发 DB 查询


async def test_wait_and_upsert_refresh_existing_whitelist(fast_poll, monkeypatch):
    """已存在行：刷新实时字段白名单；身份/管理字段不碰。"""
    call_mock = _patch_lookup_call_with([_qb_vo()])
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", call_mock)

    existing = SimpleNamespace(
        hash=HASH_A,
        name="old-name",
        size=0,
        status="paused",
        progress=0.0,
        ratio=0.0,
        save_path="/old",
        tags="",
        category="",
        completed_date=None,
        auxiliary_seed_count=2,
        create_by="creator",
        torrent_file="/keep.torrent",
        dr=0,
        update_time=None,
        update_by="old",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = existing

    row, created, err = await wait_and_upsert_torrent_row(
        db, _make_store(_make_downloader()), _make_downloader(), HASH_A, operator="tester"
    )
    assert err is None and created is False and row is existing
    # 白名单字段刷新
    assert row.name == "qb-name" and row.size == 1024.0 and row.status == "downloading"
    assert row.progress == 42.5 and row.ratio == 0.5 and row.save_path == "/dl/qb"
    assert row.tags == "t1" and row.category == "cat" and row.update_by == "tester"
    # 身份/管理字段不动
    assert row.auxiliary_seed_count == 2 and row.create_by == "creator"
    assert row.torrent_file == "/keep.torrent" and row.dr == 0
    # completion_date=0（未完成）不覆盖既有值（本例为 None 保持）
    assert row.completed_date is None
    db.commit.assert_called_once()


async def test_wait_and_upsert_refresh_completion_only_when_positive(fast_poll, monkeypatch):
    """completion_date 仅在 VO 为正时覆盖（0=未完成不写 None 清空既有完成时间）。"""
    from datetime import datetime

    call_mock = _patch_lookup_call_with([_qb_vo(completion_date=1700000600)])
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", call_mock)
    existing = SimpleNamespace(completed_date=None, update_by="", update_time=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = existing
    await wait_and_upsert_torrent_row(db, _make_store(_make_downloader()), _make_downloader(), HASH_A, operator="t")
    assert existing.completed_date == datetime.fromtimestamp(1700000600)


async def test_wait_and_upsert_db_exception_propagates(fast_poll, monkeypatch):
    """落库异常向上抛（调用方 except 链负责 sqlite_errorcode 透传/兜底），不被吞。"""
    call_mock = _patch_lookup_call_with([_qb_vo()])
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", call_mock)
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.side_effect = RuntimeError(
        "db exploded"
    )
    with pytest.raises(RuntimeError, match="db exploded"):
        await wait_and_upsert_torrent_row(db, _make_store(_make_downloader()), _make_downloader(), HASH_A)


async def test_wait_and_upsert_tr_torrent_file_from_vo(fast_poll, monkeypatch):
    """TR 分支创建：torrent_file 取 VO 的 torrentFile 字段（qB 才推导）。"""
    # 构造 TR stub（transmission-rpc 属性名）
    vo = _tr_vo()

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        return [
            SimpleNamespace(
                hash_string=vo["hash"].upper(),
                name=vo["name"],
                total_size=vo["size"],
                status="Seeding",
                progress=vo["progress"],
                ratio=vo["ratio"],
                downloaded_ever=vo["downloaded"],
                uploaded_ever=vo["uploaded"],
                download_dir=vo["download_path"],
                done_date=None,
                added_date=SimpleNamespace(timestamp=lambda: vo["addition_date"]),
                labels=["l1"],
                torrent_file=vo["torrent_file"],
            )
        ]

    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", AsyncMock(side_effect=fake_call))
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = None
    row_stub = SimpleNamespace(info_id="i-2")
    insert_mock = AsyncMock(return_value=row_stub)
    monkeypatch.setattr("app.services.torrent_add_helpers._insert_torrent_record_with_retry", insert_mock)

    row, created, err = await wait_and_upsert_torrent_row(
        db,
        _make_store(_make_downloader(downloader_type=1)),
        _make_downloader(downloader_type=1),
        HASH_A,
        operator="tester",
    )
    assert err is None and created is True
    built = insert_mock.await_args.args[1]()
    assert built.torrent_file == "/config/torrents/x.torrent"
    assert built.tags == "l1"


# ---------- refresh_trackers_after_add ----------


def _qb_tracker(url: str, status: int = 2, msg: str = "Success") -> dict:
    return {
        "url": url,
        "status": status,
        "msg": msg,
        "tier": 0,
        "num_peers": 1,
        "num_seeds": 5,
        "num_leeches": 2,
        "num_downloaded": 9,
    }


async def test_refresh_trackers_qb_contract_and_dht_filter(monkeypatch):
    """qB：torrents_trackers(hash) + DHT/PeX 过滤 + rows 透传批量 upsert。"""
    client = MagicMock()
    client.torrents_trackers = MagicMock(
        return_value=[_qb_tracker("http://t1.example.com/announce"), _qb_tracker("** [DHT] **", 0, "")],
    )
    downloader = _make_downloader(downloader_type=0, client=client)

    # 注册表倒置模式：注册真实提取函数（endpoints 层实现）+ mock 批量写入
    from app.api.endpoints.torrents_async import extract_tracker_rows_from_torrent

    sync_mock = AsyncMock(return_value={"insert": 1, "update": 0, "skip": 0, "removed": 0})
    helpers.register_tracker_sync_hooks(extract_tracker_rows_from_torrent, sync_mock)
    session_mock = MagicMock()
    session_mock.commit = AsyncMock(return_value=None)  # refresh 内 await async_db.commit()
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(helpers, "AsyncSessionLocal", MagicMock(return_value=session_ctx))

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        assert opts.get("operation") == "add_refresh_qb_trackers"
        return func(*args, **(kwargs or {}))

    with patch("app.services.torrent_add_helpers.call_downloader_api", side_effect=fake_call):
        ok = await refresh_trackers_after_add(_make_store(downloader), downloader, HASH_A, "info-1")
    assert ok is True
    # DHT 条目被过滤，仅 1 行进入 upsert
    rows = sync_mock.await_args.args[1]
    assert len(rows) == 1 and rows[0]["tracker_url"] == "http://t1.example.com/announce"
    assert rows[0]["torrent_info_id"] == "info-1"
    assert rows[0]["seeder_count"] == 5


async def test_refresh_trackers_tr_projection_and_rows(monkeypatch):
    """TR：get_torrents(ids, arguments=['trackerStats']) + TrackerStats stub 行提取。"""
    tracker_stat = SimpleNamespace(
        fields={"announce": "http://tr.example.com/announce", "host": "tr.example.com", "lastAnnounceSucceeded": True},
        site_name="tr-site",
        last_announce_result="Success",
        last_scrape_result="",
    )
    torrent = SimpleNamespace(tracker_stats=[tracker_stat])
    client = MagicMock()
    client.get_torrents = MagicMock(return_value=[torrent])
    downloader = _make_downloader(downloader_type=1, client=client)

    from app.api.endpoints.torrents_async import extract_tracker_rows_from_torrent

    sync_mock = AsyncMock(return_value={"insert": 1, "update": 0, "skip": 0, "removed": 0})
    helpers.register_tracker_sync_hooks(extract_tracker_rows_from_torrent, sync_mock)
    session_mock = MagicMock()
    session_mock.commit = AsyncMock(return_value=None)  # refresh 内 await async_db.commit()
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session_mock)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(helpers, "AsyncSessionLocal", MagicMock(return_value=session_ctx))

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        assert opts.get("operation") == "add_refresh_tr_trackers"
        assert kwargs == {"ids": [HASH_A], "arguments": ["trackerStats"]}
        return func(*args, **(kwargs or {}))

    with patch("app.services.torrent_add_helpers.call_downloader_api", side_effect=fake_call):
        ok = await refresh_trackers_after_add(_make_store(downloader), downloader, HASH_A, "info-1")
    assert ok is True
    rows = sync_mock.await_args.args[1]
    assert len(rows) == 1
    assert rows[0]["tracker_url"] == "http://tr.example.com/announce"
    assert rows[0]["tracker_name"] == "tr-site"


async def test_refresh_trackers_empty_rows_short_circuit(monkeypatch):
    """远程成功但 rows 为空（如全部是 DHT）：不开异步会话直接 False。"""
    client = MagicMock()
    client.torrents_trackers = MagicMock(return_value=[_qb_tracker("** [PeX] **", 0, "")])
    downloader = _make_downloader(downloader_type=0, client=client)
    session_factory = MagicMock()
    monkeypatch.setattr(helpers, "AsyncSessionLocal", session_factory)
    from app.api.endpoints.torrents_async import extract_tracker_rows_from_torrent

    helpers.register_tracker_sync_hooks(extract_tracker_rows_from_torrent, AsyncMock())

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        return func(*args, **(kwargs or {}))

    with patch("app.services.torrent_add_helpers.call_downloader_api", side_effect=fake_call):
        ok = await refresh_trackers_after_add(_make_store(downloader), downloader, HASH_A, "info-1")
    assert ok is False
    session_factory.assert_not_called()


async def test_refresh_trackers_remote_error_best_effort(monkeypatch):
    """远程异常：best-effort 返回 False 不抛（不影响添加主流程）。"""
    downloader = _make_downloader(downloader_type=0)

    async def fake_call(*a, **kw):
        raise RuntimeError("network down")

    with patch("app.services.torrent_add_helpers.call_downloader_api", side_effect=fake_call):
        ok = await refresh_trackers_after_add(_make_store(downloader), downloader, HASH_A, "info-1")
    assert ok is False


async def test_refresh_trackers_registry_not_registered(monkeypatch):
    """注册表未注册（极简启动/单测隔离环境）：跳过刷新返回 False，不发远程调用。"""
    downloader = _make_downloader(downloader_type=0)

    async def boom(*a, **kw):
        raise AssertionError("不应发起远程调用")

    with patch("app.services.torrent_add_helpers.call_downloader_api", side_effect=boom):
        ok = await refresh_trackers_after_add(_make_store(downloader), downloader, HASH_A, "info-1")
    assert ok is False
