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


@pytest.fixture(autouse=True)
def _isolate_tracker_registry():
    """tracker 注册表全局态隔离：保存/恢复，防本文件注册的 fake 泄漏到其他测试。"""
    saved = (helpers._tracker_row_extractor, helpers._tracker_batch_writer)
    yield
    helpers._tracker_row_extractor, helpers._tracker_batch_writer = saved


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


async def test_wait_and_upsert_refresh_locked_retry_and_reapply(fast_poll, monkeypatch):
    """刷新路径锁重试（验收 P2 修复）：首次 commit BUSY → 回滚 → 重放刷新 → 二次成功。

    rollback 会丢弃未提交的字段变更，重试轮必须重新 _apply_vo_refresh
    （若直接复用旧变更集会静默丢失 UPDATE——与 insert 路径重建实例同构）。
    """
    from sqlalchemy.exc import OperationalError

    call_mock = _patch_lookup_call_with([_qb_vo()])
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", call_mock)

    existing = SimpleNamespace(name="old", update_by="x", update_time=None)

    applied_names = []

    def fake_apply(row, vo, operator="admin"):
        applied_names.append(vo["name"])
        row.name = vo["name"]
        row.update_by = operator
        row.update_time = __import__("datetime").datetime.now()

    monkeypatch.setattr(helpers, "_apply_vo_refresh", fake_apply)

    lock_orig = Exception("database is locked")
    setattr(lock_orig, "sqlite_errorcode", 518)
    lock_err = OperationalError("UPDATE torrent_info ...", (), lock_orig)

    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = existing
    db.commit.side_effect = [lock_err, None]
    monkeypatch.setattr(helpers, "_LOCKED_RETRY_BASE_DELAY_SECONDS", 0)

    row, created, err = await wait_and_upsert_torrent_row(
        db, _make_store(_make_downloader()), _make_downloader(), HASH_A, operator="tester"
    )
    assert err is None and created is False and row is existing
    assert db.commit.call_count == 2
    assert db.rollback.call_count == 1
    # 每轮都重放刷新（rollback 丢弃未提交变更）
    assert applied_names == ["qb-name", "qb-name"]
    assert row.name == "qb-name"


async def test_wait_and_upsert_refresh_non_locked_no_retry(fast_poll, monkeypatch):
    """刷新路径非锁冲突（如 no such table）不重试，直接上抛。"""
    from sqlalchemy.exc import OperationalError

    call_mock = _patch_lookup_call_with([_qb_vo()])
    monkeypatch.setattr("app.services.torrent_lookup_service.call_downloader_api", call_mock)

    existing = SimpleNamespace(name="old", update_by="x", update_time=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = existing
    db.commit.side_effect = OperationalError("UPDATE ...", (), Exception("no such table: torrent_info"))

    with pytest.raises(OperationalError):
        await wait_and_upsert_torrent_row(db, _make_store(_make_downloader()), _make_downloader(), HASH_A)
    assert db.commit.call_count == 1


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


# ---------- 端到端回归：TorrentAddService 添加后落库/刷新全链路 ----------
# 保护本批核心用户价值：添加成功 → DB 行立即可见且字段正确；重复添加 → 既有行
# 实时字段刷新（不再等 10 分钟定时同步）。走真实 SQLite + 真实 wait_and_upsert，
# 仅 fake 远程层（call_downloader_api 直调 mock client）与审计/tracker 刷新。


def _make_valid_torrent_bytes() -> bytes:
    import bencodepy

    info = {b"name": b"e2e-torrent", b"length": 16, b"piece length": 16384, b"pieces": b"\x00" * 20}
    return bencodepy.encode({b"announce": b"http://tracker.example.com/announce", b"info": info})


def _real_db_session_fixture():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.torrents.models import TorrentInfo, TrackerInfo

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[TorrentInfo.__table__, TrackerInfo.__table__])
    return sessionmaker(bind=engine)()


async def _run_add_torrent(db, downloader_type: int, client: Any, vo_overrides: dict = None):
    """公共端到端驱动：fake 直调远程层 + AsyncMock 审计/tracker，跑真实 add_torrent。"""
    import app.services.torrent_add_service as add_service
    from app.services.torrent_add_service import TorrentAddParams, TorrentAddService

    downloader = _make_downloader(downloader_type=downloader_type, client=client)
    store = _make_store(downloader)

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        return func(*args, **(kwargs or {}))

    with (
        patch.object(add_service, "call_downloader_api", side_effect=fake_call),
        patch.object(add_service, "refresh_trackers_after_add", new=AsyncMock(return_value=True)),
        patch("app.services.torrent_lookup_service.call_downloader_api", side_effect=fake_call),
        patch("app.services.torrent_add_helpers.call_downloader_api", side_effect=fake_call),
        patch("app.services.torrent_add_helpers.ADD_POLL_INTERVAL", 0.0),
        patch("app.services.torrent_add_service.AsyncSessionLocal"),
    ):
        service = TorrentAddService(db, store=store)
        return await service.add_torrent(
            TorrentAddParams(
                downloader_id="dl-1",
                save_path="/downloads",
                tags="",
                category="",
                paused=False,
                skip_hash_check=False,
                is_sequential_download=False,
                is_first_last_piece_priority=False,
                upload_limit=0,
                download_limit=0,
            ),
            torrent_content=_make_valid_torrent_bytes() if downloader_type == 0 else _make_valid_torrent_bytes(),
        )


def _expected_info_hash() -> str:
    import hashlib

    import bencodepy

    data = bencodepy.decode(_make_valid_torrent_bytes())
    return hashlib.sha1(bencodepy.encode(data[b"info"])).hexdigest()


async def test_add_torrent_qb_new_row_end_to_end():
    """qB 首次添加：DB 行立即创建，字段口径正确（progress 0~100/BT_backup 路径/state 归一）。"""
    from datetime import datetime

    from app.torrents.models import TorrentInfo

    db = _real_db_session_fixture()
    info_hash = _expected_info_hash()
    client = MagicMock()
    client.torrents_info = MagicMock(
        return_value=[
            SimpleNamespace(
                hash=info_hash,
                name="e2e-qb",
                size=4096,
                state="metaDL",
                progress=0.25,
                ratio=0.0,
                downloaded=0,
                uploaded=0,
                save_path="/downloads",
                completion_on=0,
                added_on=1700000000,
                category="",
                tags="",
            )
        ]
    )

    result = await _run_add_torrent(db, 0, client)

    assert result.ok is True
    assert result.created is True
    assert result.info_hash == info_hash
    assert result.name == "e2e-qb"
    row = db.query(TorrentInfo).filter(TorrentInfo.hash == info_hash).one()
    assert row.name == "e2e-qb"
    assert float(row.size) == 4096.0
    assert row.status == "downloading"  # metaDL 归一
    assert float(row.progress) == 25.0  # 0~100 口径（qB 0.25×100）
    assert row.torrent_file == f"/config/qbittorrent/BT_backup/{info_hash}.torrent"
    assert row.added_date == datetime.fromtimestamp(1700000000)
    assert row.dr == 0


async def test_add_torrent_repeated_refreshes_existing_row():
    """核心回归：重复添加同 hash → 既有行实时字段刷新 + created=False（原行为：复用旧值不刷新）。

    场景：首次添加后下载器侧状态演进（downloading 25% → seeding 100%），
    用户再次添加（转移回/重建场景）→ DB 行应立即反映最新状态。
    """
    from app.torrents.models import TorrentInfo

    db = _real_db_session_fixture()
    info_hash = _expected_info_hash()

    def qb_stub(state: str, progress: float) -> MagicMock:
        return SimpleNamespace(
            hash=info_hash,
            name="e2e-qb-v2",
            size=8192,
            state=state,
            progress=progress,
            ratio=1.2,
            downloaded=8192,
            uploaded=9830,
            save_path="/downloads/moved",
            completion_on=1700000600,
            added_on=1700000000,
            category="cat2",
            tags="t2",
        )

    client = MagicMock()
    client.torrents_info = MagicMock(return_value=[qb_stub("downloading", 0.25)])
    result_first = await _run_add_torrent(db, 0, client)
    assert result_first.created is True

    # 第二次添加：下载器侧已 seeding 100%
    client.torrents_info = MagicMock(return_value=[qb_stub("stalledUP", 1.0)])
    result_second = await _run_add_torrent(db, 0, client)

    assert result_second.ok is True
    assert result_second.created is False  # 既有行刷新而非新建
    rows = db.query(TorrentInfo).filter(TorrentInfo.hash == info_hash).all()
    assert len(rows) == 1  # 无重复行
    row = rows[0]
    # 实时字段已刷新为第二次 VO 值
    assert row.status == "seeding"  # stalledUP 归一
    assert float(row.progress) == 100.0
    assert float(row.size) == 8192.0
    assert row.save_path == "/downloads/moved"
    assert row.tags == "t2" and row.category == "cat2"
    assert row.ratio == 1.2
    from datetime import datetime

    assert row.completed_date == datetime.fromtimestamp(1700000600)


async def test_add_torrent_tr_new_row_end_to_end():
    """TR 首次添加：DB 行创建（torrent_file 取 torrentFile 投影/torrent_id=info_hash）。"""
    from app.torrents.models import TorrentInfo

    from datetime import datetime as _dt

    db = _real_db_session_fixture()
    info_hash = _expected_info_hash()
    tr_added = _dt(2026, 1, 1, 12, 0, 0)
    client = MagicMock()
    client.add_torrent = MagicMock(return_value=None)
    client.get_torrents = MagicMock(
        return_value=[
            SimpleNamespace(
                id=9330,
                hashString=info_hash,
                name="e2e-tr",
                download_dir="/downloads/tr",
                total_size=2048,
                status="checking",
                progress=0.0,
                ratio=0.0,
                downloaded_ever=0,
                uploaded_ever=0,
                torrent_file="/config/tr/torrents/x.torrent",
                added_date=tr_added,
                done_date=None,
                labels=[],
                error=0,
                error_string="",
            )
        ]
    )

    result = await _run_add_torrent(db, 1, client)

    assert result.ok is True and result.created is True
    row = db.query(TorrentInfo).filter(TorrentInfo.hash == info_hash).one()
    assert row.name == "e2e-tr"
    assert row.torrent_file == "/config/tr/torrents/x.torrent"
    assert row.torrent_id == info_hash  # 数字 id 不持久化，统一 hash 为稳定键
    assert row.status == "checking" and row.tags == ""


async def test_refresh_existing_persists_with_real_sqlite_session(tmp_path):
    """真实 ORM 会话级验证：既有行刷新的 UPDATE 确实持久化（对标 insert 版 real_session）。

    MagicMock 层只能断言赋值发生，无法证明 rollback/refresh 状态机下变更
    落库——用全新会话二次读取验证 durable UPDATE。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.torrents.models import TorrentInfo, TrackerInfo

    engine = create_engine(f"sqlite:///{tmp_path / 'refresh.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[TorrentInfo.__table__, TrackerInfo.__table__])
    factory = sessionmaker(bind=engine)

    with factory() as seed:
        from datetime import datetime as _dt

        seed.add(
            TorrentInfo(
                id_="seed-1",
                downloader_id="dl-1",
                downloader_name="qb",
                torrent_id=HASH_A,
                hash=HASH_A,
                name="stale",
                save_path="/old",
                size=1,
                status="downloading",
                progress=10.0,
                torrent_file="",
                added_date=_dt(2026, 1, 1),
                completed_date=None,
                ratio=0.0,
                ratio_limit=None,
                tags="",
                category="",
                super_seeding="",
                enabled=True,
                create_time=_dt(2026, 1, 1),
                create_by="seeder",
                update_time=_dt(2026, 1, 1),
                update_by="seeder",
                dr=0,
            )
        )
        seed.commit()

    db = factory()
    call_mock = _patch_lookup_call_with([_qb_vo()])
    try:
        with patch("app.services.torrent_lookup_service.call_downloader_api", call_mock):
            row, created, err = await wait_and_upsert_torrent_row(
                db, _make_store(_make_downloader()), _make_downloader(), HASH_A, operator="tester"
            )
        assert err is None and created is False
        db.close()

        with factory() as verify:
            persisted = verify.query(TorrentInfo).filter(TorrentInfo.hash == HASH_A).one()
            assert persisted.name == "qb-name"  # stale → 刷新值
            assert persisted.status == "downloading"
            assert float(persisted.progress) == 42.5
            assert persisted.save_path == "/dl/qb"
    finally:
        engine.dispose()
