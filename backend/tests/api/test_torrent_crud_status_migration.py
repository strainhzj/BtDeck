# -*- coding: utf-8 -*-
"""
torrent_crud.py / torrent_status.py W2-3 垂直切片迁移端点测试
（sync-database-blocking-remediation P0-04）

覆盖迁移后的行为契约：
1. 所有下载器调用经 call_downloader_api（DownloadLane.INTERACTIVE）执行：
   断言 client 方法以 func 实参传入 runtime、downloader_id / lane / timeout /
   operation 透传正确。
2. 成功路径：create_torrent（qB/TR）、pause / resume / recheck 返回原契约 code。
3. 超时路径：runtime 抛 TimeoutError → 既有异常分支映射（code=500 + 回滚）。
4. 离线（fail_time>0 → 503）/ 缺失客户端（500）路径：不触达 runtime。
5. 权限失败：QbAPIError / TransmissionError 分类映射为 500 并回滚。
6. 漏调用修复回归：create_torrent qB 分支 30 次轮询循环内的 torrents_info
   真实经 runtime 调用（迁移前是裸同步调用；若改回裸调用此测试立即报红）。

测试风格对齐 test_torrent_crud_add_fallback.py：直接 await 端点函数 + mock
app.state.store + patch call_downloader_api。全量 pytest 中全局 runtime executor
会被其它 TestClient 测试的 lifespan 关闭（RuntimeError: cannot schedule new
futures after shutdown），故统一 patch，不真实走全局单例。
"""

import asyncio
import bencodepy
import contextlib
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile
from qbittorrentapi.exceptions import APIError
from transmission_rpc import TransmissionError

from app.api.endpoints.torrent_crud import create_torrent
from app.api.endpoints.torrent_status import (
    PauseTorrentsRequest,
    RecheckTorrentsRequest,
    ResumeTorrentsRequest,
    pause_torrents,
    recheck_torrents,
    resume_torrents,
)
from app.services.downloader_api_runtime import DownloadLane
from app.torrents.models import TorrentInfo

DL_ID = "dl-test"
DL_NICKNAME = "test-dl"

# =============================================================================
# 辅助构造
# =============================================================================


def _make_valid_torrent_bytes() -> bytes:
    """构造最小合法的 bencode 种子文件（含 info dict），供 calculate_info_hash 走通。"""
    info = {
        b"name": b"test-torrent",
        b"length": 16,
        b"piece length": 16384,
        b"pieces": b"\x00" * 20,
    }
    return bencodepy.encode({b"announce": b"http://tracker.example.com/announce", b"info": info})


def _make_upload(content: bytes) -> UploadFile:
    return UploadFile(filename="test.torrent", file=BytesIO(content))


class _FakeRequest:
    """最小 Request 桩：仅暴露端点用到的属性（headers/cookies/client 均兼容 dict 访问）。"""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.method = "POST"
        self.url = MagicMock(path="/api/v1/torrents/add")
        self.headers: dict = {}
        self.cookies: dict = {}
        self.client = None


class _FakeStore:
    """伪 store：get_snapshot 为 async，返回给定下载器列表。"""

    def __init__(self, downloaders: List[Any]) -> None:
        self._downloaders = downloaders

    async def get_snapshot(self) -> List[Any]:
        return list(self._downloaders)


def _make_downloader(*, downloader_type: int, client: Any, fail_time: int = 0) -> Any:
    """构造一个会被 app.state.store.get_snapshot() 返回的下载器 VO。"""
    downloader = MagicMock()
    downloader.downloader_id = DL_ID
    downloader.downloader_type = downloader_type
    downloader.nickname = DL_NICKNAME
    downloader.fail_time = fail_time
    downloader.client = client
    return downloader


def _make_app(downloader: Any) -> Any:
    app = MagicMock()
    app.state.store = _FakeStore([downloader])
    return app


def _make_qb_client(*, torrents_add=None, torrents_info=None) -> MagicMock:
    """qB 客户端：默认 add 成功、info 返回指定种子列表。"""
    client = MagicMock()
    client.torrents_add.return_value = torrents_add if torrents_add is not None else "Ok"
    client.torrents_info.return_value = torrents_info if torrents_info is not None else []
    return client


def _make_qb_torrent() -> MagicMock:
    """构造字段齐全的 qBittorrent 种子 mock（create_qbittorrent_torrent_record 可消费）。"""
    t = MagicMock()
    t.hash = "a" * 40
    t.name = "qb-torrent"
    t.save_path = "/downloads"
    t.total_size = 1024
    t.state = "uploading"
    t.added_on = 1700000000
    t.completion_on = 0
    t.ratio = 0.5
    t.ratio_limit = -1
    t.tags = ["tag1"]
    t.category = ""
    t.super_seeding = False
    return t


def _make_tr_client(*, add_torrent=None, get_torrents=None) -> MagicMock:
    """TR 客户端：默认 add 成功、get_torrents 返回指定列表。"""
    client = MagicMock()
    client.add_torrent.return_value = add_torrent if add_torrent is not None else None
    client.get_torrents.return_value = get_torrents if get_torrents is not None else []
    return client


def _make_tr_torrent(*, error: int = 0) -> MagicMock:
    """构造字段齐全的 Transmission 种子 mock（create_transmission_torrent_record 可消费）。

    error: Transmission error 字段（0=ok,1=tracker警告,2=tracker错误,3=本地错误）。
    必须显式设置以避免 MagicMock 自动属性陷阱（resolve_transmission_status 会用
    isinstance 守卫，但显式 int 更贴近真实对象）。
    """
    t = MagicMock()
    t.id = 42
    t.hashString = "b" * 40
    t.name = "tr-torrent"
    t.download_dir = "/downloads"
    t.total_size = 2048
    t.status = "seeding"
    t.error = error
    t.torrent_file = "/config/tr/torrents/x.torrent"
    t.added_date = datetime(2026, 1, 1, 12, 0, 0)
    t.done_date = None
    t.ratio = 0.5
    t.seed_ratio_limit = None
    t.labels = []
    return t


def _runtime_spy(side_effects: Optional[Dict[Any, Exception]] = None):
    """构造 call_downloader_api 的 spy：真实执行 func 并记录调用。

    side_effects: {client方法(边界函数): 要抛出的异常}，用于注入超时/权限失败。
    Returns: (calls, fake_call)；calls 元素含 downloader_id/lane/func/args/kwargs/opts。
    """
    calls: List[Dict[str, Any]] = []
    side_effects = side_effects or {}

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        # 迁移端点必须走 INTERACTIVE lane（W2-3 契约）
        assert lane == DownloadLane.INTERACTIVE, "迁移端点必须经 INTERACTIVE lane"
        calls.append(
            {
                "downloader_id": downloader_id,
                "lane": lane,
                "func": func,
                "args": args,
                "kwargs": kwargs or {},
                "opts": opts,
            }
        )
        if func in side_effects:
            raise side_effects[func]
        return func(*args, **(kwargs or {}))

    return calls, fake_call


@contextlib.contextmanager
def _patch_runtime(calls: List[Dict[str, Any]], fake_call):
    """同时 patch 三个模块的 call_downloader_api 引用。

    get_transmission_torrent_info 在 torrent_helpers 模块内调用自身导入的
    call_downloader_api（import 绑定）；/add 端点主体 2026-09-05 起抽取至
    torrent_add_service（符号随之迁移），状态控制端点在 torrent_status——
    三处都必须 patch。
    """
    with (
        patch("app.services.torrent_add_service.call_downloader_api", side_effect=fake_call),
        patch("app.api.endpoints.torrent_helpers.call_downloader_api", side_effect=fake_call),
        patch("app.api.endpoints.torrent_status.call_downloader_api", side_effect=fake_call),
    ):
        yield


def _find_call(calls: List[Dict[str, Any]], func: Any) -> Optional[Dict[str, Any]]:
    """按 func 边界函数（client 方法）查找 runtime 调用记录。"""
    return next((c for c in calls if c["func"] is func), None)


@pytest.fixture
def event_loop_policy():
    """保证每个测试用独立事件循环（避免 asyncio.create_task 跨用例污染）。"""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def torrent_db():
    """真实 SQLite + TorrentInfo 表：状态控制端点需要查询/回滚真实 ORM 记录。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[TorrentInfo.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[TorrentInfo.__table__])


def _seed_torrent(db, *, hash_: str, status: str = "seeding", progress: float = 0.0):
    """向 torrent_db 写入一条种子记录并返回。"""
    from tests.api.conftest import make_torrent

    return make_torrent(
        db,
        info_id=f"info-{hash_}",
        downloader_id=DL_ID,
        hash_=hash_,
        name=f"torrent-{hash_}",
        status=status,
        progress=progress,
    )


# =============================================================================
# create_torrent（torrent_crud.py）
# =============================================================================


@pytest.mark.asyncio
async def test_create_torrent_qb_success_runtime_and_polling(torrent_db):
    """qB 成功：torrents_add 与轮询内 torrents_info 均经 runtime 调用。

    漏调用修复回归：轮询循环（30 次上限）内先返回空两次、第三次命中，
    断言 3 次 torrents_info 全部真实经 runtime 执行（迁移前是裸同步调用）。
    """
    client = _make_qb_client()
    # 轮询序列：前两次空、第三次命中（side_effect 逐次返回，模拟下载器处理延迟）
    client.torrents_info.side_effect = [[], [], [_make_qb_torrent()]]
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await create_torrent(
            _user=None,
            request=_FakeRequest(app),
            downloader_id=DL_ID,
            save_path="/downloads",
            tags="tag1",
            category="",
            paused=False,
            skip_hash_check=False,
            is_sequential_download=False,
            is_first_last_piece_priority=False,
            upload_limit=0,
            download_limit=0,
            torrent_file=_make_upload(_make_valid_torrent_bytes()),
            db=torrent_db,
        )

    assert result.code == "200"
    assert result.status == "success"

    add_call = _find_call(calls, client.torrents_add)
    assert add_call is not None, "torrents_add 必须经 runtime 调用"
    assert add_call["downloader_id"] == DL_ID
    assert add_call["lane"] == DownloadLane.INTERACTIVE
    assert add_call["opts"]["operation"] == "add_torrent"
    assert add_call["kwargs"]["save_path"] == "/downloads"
    assert add_call["kwargs"]["is_stopped"] is False

    # 轮询循环回归：3 次 torrents_info 全部经 runtime（带 info_hash 与 operation）
    info_calls = [c for c in calls if c["func"] is client.torrents_info]
    assert len(info_calls) == 3, f"轮询循环内 torrents_info 应真实经 runtime 调用 3 次，实际 {len(info_calls)}"
    for c in info_calls:
        assert c["kwargs"] == {"torrent_hashes": info_calls[0]["kwargs"]["torrent_hashes"]}
        assert c["opts"]["operation"] == "get_qb_torrent_info"
    # 种子已写入数据库
    saved = torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "a" * 40).first()
    assert saved is not None
    assert saved.downloader_id == DL_ID


@pytest.mark.asyncio
async def test_create_torrent_tr_success_runtime():
    """TR 成功：add_torrent 与 get_transmission_torrent_info 内 get_torrents 均经 runtime。"""
    client = _make_tr_client(get_torrents=[_make_tr_torrent()])
    downloader = _make_downloader(downloader_type=1, client=client)
    app = _make_app(downloader)
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await create_torrent(
            _user=None,
            request=_FakeRequest(app),
            downloader_id=DL_ID,
            save_path="/downloads",
            tags="",
            category="",
            paused=True,
            skip_hash_check=False,
            is_sequential_download=False,
            is_first_last_piece_priority=False,
            upload_limit=0,
            download_limit=0,
            torrent_file=_make_upload(_make_valid_torrent_bytes()),
            db=MagicMock(),
        )

    assert result.code == "200"
    assert result.status == "success"

    add_call = _find_call(calls, client.add_torrent)
    assert add_call is not None, "add_torrent 必须经 runtime 调用"
    assert add_call["downloader_id"] == DL_ID
    assert add_call["opts"]["operation"] == "add_torrent"
    # 轮询 helper 内的 get_torrents 也必须经 runtime（torrent_helpers 模块引用）
    get_call = _find_call(calls, client.get_torrents)
    assert get_call is not None, "get_transmission_torrent_info 内的 get_torrents 必须经 runtime 调用"
    assert get_call["opts"]["operation"] == "get_transmission_torrent_info"


@pytest.mark.asyncio
async def test_create_torrent_qb_timeout_maps_500():
    """qB 超时：runtime 抛 TimeoutError → 既有兜底分支映射 code=500。"""
    client = _make_qb_client()
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    calls, fake_call = _runtime_spy({client.torrents_add: asyncio.TimeoutError()})

    with _patch_runtime(calls, fake_call):
        result = await create_torrent(
            _user=None,
            request=_FakeRequest(app),
            downloader_id=DL_ID,
            save_path="/downloads",
            tags="",
            category="",
            paused=False,
            skip_hash_check=False,
            is_sequential_download=False,
            is_first_last_piece_priority=False,
            upload_limit=0,
            download_limit=0,
            torrent_file=_make_upload(_make_valid_torrent_bytes()),
            db=MagicMock(),
        )

    assert result.code == "500"
    assert result.status == "failed"
    assert "TimeoutError" in result.msg


@pytest.mark.asyncio
async def test_create_torrent_offline_503_no_runtime():
    """离线：fail_time>0 → 503，且不触达 runtime。"""
    client = _make_qb_client()
    downloader = _make_downloader(downloader_type=0, client=client, fail_time=3)
    app = _make_app(downloader)
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await create_torrent(
            _user=None,
            request=_FakeRequest(app),
            downloader_id=DL_ID,
            save_path="/downloads",
            tags="",
            category="",
            paused=False,
            skip_hash_check=False,
            is_sequential_download=False,
            is_first_last_piece_priority=False,
            upload_limit=0,
            download_limit=0,
            torrent_file=_make_upload(_make_valid_torrent_bytes()),
            db=MagicMock(),
        )

    assert result.code == "503"
    assert "已失效" in result.msg
    assert calls == []


@pytest.mark.asyncio
async def test_create_torrent_missing_client_500_no_runtime():
    """客户端缺失：client=None → 500，且不触达 runtime。"""
    downloader = _make_downloader(downloader_type=0, client=None)
    app = _make_app(downloader)
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await create_torrent(
            _user=None,
            request=_FakeRequest(app),
            downloader_id=DL_ID,
            save_path="/downloads",
            tags="",
            category="",
            paused=False,
            skip_hash_check=False,
            is_sequential_download=False,
            is_first_last_piece_priority=False,
            upload_limit=0,
            download_limit=0,
            torrent_file=_make_upload(_make_valid_torrent_bytes()),
            db=MagicMock(),
        )

    assert result.code == "500"
    assert "客户端连接不存在" in result.msg
    assert calls == []


@pytest.mark.asyncio
async def test_create_torrent_qb_permission_error():
    """qB 权限失败：APIError 走原精细分支，msg 为原始异常文本。"""
    client = _make_qb_client()
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    calls, fake_call = _runtime_spy({client.torrents_add: APIError("qb add forbidden")})

    with _patch_runtime(calls, fake_call):
        result = await create_torrent(
            _user=None,
            request=_FakeRequest(app),
            downloader_id=DL_ID,
            save_path="/downloads",
            tags="",
            category="",
            paused=False,
            skip_hash_check=False,
            is_sequential_download=False,
            is_first_last_piece_priority=False,
            upload_limit=0,
            download_limit=0,
            torrent_file=_make_upload(_make_valid_torrent_bytes()),
            db=MagicMock(),
        )

    assert result.code == "500"
    assert result.msg == "qb add forbidden"


@pytest.mark.asyncio
async def test_create_torrent_tr_permission_error():
    """TR 权限失败：TransmissionError 走原精细分支，msg 为原始异常文本。"""
    client = _make_tr_client()
    downloader = _make_downloader(downloader_type=1, client=client)
    app = _make_app(downloader)
    calls, fake_call = _runtime_spy({client.add_torrent: TransmissionError("tr daemon down")})

    with _patch_runtime(calls, fake_call):
        result = await create_torrent(
            _user=None,
            request=_FakeRequest(app),
            downloader_id=DL_ID,
            save_path="/downloads",
            tags="",
            category="",
            paused=True,
            skip_hash_check=False,
            is_sequential_download=False,
            is_first_last_piece_priority=False,
            upload_limit=0,
            download_limit=0,
            torrent_file=_make_upload(_make_valid_torrent_bytes()),
            db=MagicMock(),
        )

    assert result.code == "500"
    assert result.msg == "tr daemon down"


# =============================================================================
# pause_torrents（torrent_status.py）
# =============================================================================


async def _call_pause(app, db, hashes):
    return await pause_torrents(
        _user=None,
        request=_FakeRequest(app),
        req_data=PauseTorrentsRequest(downloader_id=DL_ID, hashes=hashes),
        db=db,
    )


@pytest.mark.asyncio
async def test_pause_qb_success_runtime(torrent_db):
    """qB 暂停成功：torrents_pause 经 runtime 调用，DB 状态更新为 paused。"""
    client = MagicMock()
    client.torrents_pause.return_value = None
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_pause(app, torrent_db, ["h1"])

    assert result.code == "200"
    assert result.data["success_count"] == 1
    call = _find_call(calls, client.torrents_pause)
    assert call is not None, "torrents_pause 必须经 runtime 调用"
    assert call["downloader_id"] == DL_ID
    assert call["lane"] == DownloadLane.INTERACTIVE
    assert call["kwargs"] == {"torrent_hashes": ["h1"]}
    assert call["opts"]["operation"] == "pause_torrents"
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "paused"


@pytest.mark.asyncio
async def test_pause_tr_success_runtime(torrent_db):
    """TR 暂停成功：stop_torrent 经 runtime 调用（位置参数透传）。"""
    client = MagicMock()
    client.stop_torrent.return_value = None
    downloader = _make_downloader(downloader_type=1, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_pause(app, torrent_db, ["h1"])

    assert result.code == "200"
    call = _find_call(calls, client.stop_torrent)
    assert call is not None, "stop_torrent 必须经 runtime 调用"
    assert call["args"] == (["h1"],)
    assert call["opts"]["operation"] == "stop_torrents"


@pytest.mark.asyncio
async def test_pause_timeout_maps_500_and_rollback(torrent_db):
    """超时：torrents_pause 抛 TimeoutError → 500 + failed_items + 数据库回滚。"""
    client = MagicMock()
    client.torrents_pause.return_value = None
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy({client.torrents_pause: asyncio.TimeoutError()})

    with _patch_runtime(calls, fake_call):
        result = await _call_pause(app, torrent_db, ["h1"])

    assert result.code == "500"
    assert result.status == "failed"
    assert "TimeoutError" in result.msg
    assert result.data["failed_items"] == [{"hash": "h1", "name": "torrent-h1", "error": "TimeoutError: "}]
    # 严格模式：回滚后状态保持原值
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "seeding"


@pytest.mark.asyncio
async def test_pause_offline_503_no_runtime(torrent_db):
    """离线：fail_time>0 → 503，且不触达 runtime。"""
    client = MagicMock()
    downloader = _make_downloader(downloader_type=0, client=client, fail_time=3)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_pause(app, torrent_db, ["h1"])

    assert result.code == "503"
    assert "已失效" in result.msg
    assert calls == []


@pytest.mark.asyncio
async def test_pause_missing_client_500_no_runtime(torrent_db):
    """客户端缺失：client=None → 500，且不触达 runtime。"""
    downloader = _make_downloader(downloader_type=0, client=None)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_pause(app, torrent_db, ["h1"])

    assert result.code == "500"
    assert "客户端连接不存在" in result.msg
    assert calls == []


@pytest.mark.asyncio
async def test_pause_qb_permission_error(torrent_db):
    """qB 权限失败：APIError → 500 + 回滚。"""
    client = MagicMock()
    client.torrents_pause.return_value = None
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy({client.torrents_pause: APIError("forbidden")})

    with _patch_runtime(calls, fake_call):
        result = await _call_pause(app, torrent_db, ["h1"])

    assert result.code == "500"
    assert "APIError: forbidden" in result.msg
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "seeding"


@pytest.mark.asyncio
async def test_pause_tr_permission_error(torrent_db):
    """TR 权限失败：TransmissionError → 500 + 回滚。"""
    client = MagicMock()
    client.stop_torrent.return_value = None
    downloader = _make_downloader(downloader_type=1, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy({client.stop_torrent: TransmissionError("auth failed")})

    with _patch_runtime(calls, fake_call):
        result = await _call_pause(app, torrent_db, ["h1"])

    assert result.code == "500"
    assert "TransmissionError: auth failed" in result.msg
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "seeding"


# =============================================================================
# resume_torrents（torrent_status.py）
# =============================================================================


async def _call_resume(app, db, hashes):
    return await resume_torrents(
        _user=None,
        request=_FakeRequest(app),
        req_data=ResumeTorrentsRequest(downloader_id=DL_ID, hashes=hashes),
        db=db,
    )


@pytest.mark.asyncio
async def test_resume_qb_success_runtime(torrent_db):
    """qB 恢复成功：torrents_resume 经 runtime 调用，状态更新为 downloading。"""
    client = MagicMock()
    client.torrents_resume.return_value = None
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1", status="paused", progress=10.0)
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_resume(app, torrent_db, ["h1"])

    assert result.code == "200"
    assert result.data["success_count"] == 1
    call = _find_call(calls, client.torrents_resume)
    assert call is not None, "torrents_resume 必须经 runtime 调用"
    assert call["kwargs"] == {"torrent_hashes": ["h1"]}
    assert call["opts"]["operation"] == "resume_torrents"
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "downloading"


@pytest.mark.asyncio
async def test_resume_tr_success_runtime(torrent_db):
    """TR 恢复成功：start_torrent 经 runtime 调用。"""
    client = MagicMock()
    client.start_torrent.return_value = None
    downloader = _make_downloader(downloader_type=1, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1", status="paused", progress=100.0)
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_resume(app, torrent_db, ["h1"])

    assert result.code == "200"
    call = _find_call(calls, client.start_torrent)
    assert call is not None, "start_torrent 必须经 runtime 调用"
    assert call["args"] == (["h1"],)
    assert call["opts"]["operation"] == "start_torrents"
    # progress=100 → seeding
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "seeding"


@pytest.mark.asyncio
async def test_resume_timeout_maps_500(torrent_db):
    """恢复超时：TimeoutError → 500 + 回滚。"""
    client = MagicMock()
    client.torrents_resume.return_value = None
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1", status="paused")
    calls, fake_call = _runtime_spy({client.torrents_resume: asyncio.TimeoutError()})

    with _patch_runtime(calls, fake_call):
        result = await _call_resume(app, torrent_db, ["h1"])

    assert result.code == "500"
    assert "TimeoutError" in result.msg
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "paused"


@pytest.mark.asyncio
async def test_resume_offline_503_no_runtime(torrent_db):
    """恢复离线：fail_time>0 → 503，且不触达 runtime。"""
    client = MagicMock()
    downloader = _make_downloader(downloader_type=0, client=client, fail_time=3)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1", status="paused")
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_resume(app, torrent_db, ["h1"])

    assert result.code == "503"
    assert calls == []


@pytest.mark.asyncio
async def test_resume_permission_error(torrent_db):
    """恢复权限失败：APIError → 500 + 回滚。"""
    client = MagicMock()
    client.torrents_resume.return_value = None
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1", status="paused")
    calls, fake_call = _runtime_spy({client.torrents_resume: APIError("forbidden")})

    with _patch_runtime(calls, fake_call):
        result = await _call_resume(app, torrent_db, ["h1"])

    assert result.code == "500"
    assert "APIError: forbidden" in result.msg
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "paused"


# =============================================================================
# recheck_torrents（torrent_status.py）
# =============================================================================


async def _call_recheck(app, db, hashes):
    return await recheck_torrents(
        _user=None,
        request=_FakeRequest(app),
        req_data=RecheckTorrentsRequest(downloader_id=DL_ID, hashes=hashes),
        db=db,
    )


@pytest.mark.asyncio
async def test_recheck_qb_success_runtime(torrent_db):
    """qB 重检成功：torrents_recheck 经 runtime 调用，状态更新为 checking。"""
    client = MagicMock()
    client.torrents_recheck.return_value = None
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1", status="seeding")
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_recheck(app, torrent_db, ["h1"])

    assert result.code == "200"
    assert result.data["success_count"] == 1
    call = _find_call(calls, client.torrents_recheck)
    assert call is not None, "torrents_recheck 必须经 runtime 调用"
    assert call["kwargs"] == {"torrent_hashes": ["h1"]}
    assert call["opts"]["operation"] == "recheck_torrents"
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "checking"


@pytest.mark.asyncio
async def test_recheck_tr_success_runtime(torrent_db):
    """TR 重检成功：verify_torrent 经 runtime 调用。"""
    client = MagicMock()
    client.verify_torrent.return_value = None
    downloader = _make_downloader(downloader_type=1, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_recheck(app, torrent_db, ["h1"])

    assert result.code == "200"
    call = _find_call(calls, client.verify_torrent)
    assert call is not None, "verify_torrent 必须经 runtime 调用"
    assert call["args"] == (["h1"],)
    assert call["opts"]["operation"] == "verify_torrents"


@pytest.mark.asyncio
async def test_recheck_timeout_maps_500(torrent_db):
    """重检超时：TimeoutError → 500 + 回滚。"""
    client = MagicMock()
    client.torrents_recheck.return_value = None
    downloader = _make_downloader(downloader_type=0, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy({client.torrents_recheck: asyncio.TimeoutError()})

    with _patch_runtime(calls, fake_call):
        result = await _call_recheck(app, torrent_db, ["h1"])

    assert result.code == "500"
    assert "TimeoutError" in result.msg
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "seeding"


@pytest.mark.asyncio
async def test_recheck_offline_503_no_runtime(torrent_db):
    """重检离线：fail_time>0 → 503，且不触达 runtime。"""
    client = MagicMock()
    downloader = _make_downloader(downloader_type=0, client=client, fail_time=3)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy()

    with _patch_runtime(calls, fake_call):
        result = await _call_recheck(app, torrent_db, ["h1"])

    assert result.code == "503"
    assert calls == []


@pytest.mark.asyncio
async def test_recheck_permission_error(torrent_db):
    """重检权限失败：TransmissionError → 500 + 回滚。"""
    client = MagicMock()
    client.verify_torrent.return_value = None
    downloader = _make_downloader(downloader_type=1, client=client)
    app = _make_app(downloader)
    _seed_torrent(torrent_db, hash_="h1")
    calls, fake_call = _runtime_spy({client.verify_torrent: TransmissionError("forbidden")})

    with _patch_runtime(calls, fake_call):
        result = await _call_recheck(app, torrent_db, ["h1"])

    assert result.code == "500"
    assert "TransmissionError: forbidden" in result.msg
    assert torrent_db.query(TorrentInfo).filter(TorrentInfo.hash == "h1").first().status == "seeding"
