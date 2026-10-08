# -*- coding: utf-8 -*-
"""
torrent_crud.py 单条 add 端点非领域异常兜底回归测试（prod-hotfix-2026-07-19）

修复目标：消除生产偶发 500 响应 ``data.error="Object of type ValueError is not
JSON serializable"``。

根因链路（已通过 /tmp/repro_add*.py 复现验证）：
    create_torrent 端点
      → tr_client.add_torrent / qb_client.torrents_add
      → 下游抛非领域异常（如 transmission_rpc→requests.post(json=query) 内部
        json.dumps 撞 ValueError 实例 → TypeError）
      → 原 except 只捕获 TransmissionError / APIError，捕获不到
      → 冒泡到 unhandled_exception_handler，str(TypeError) 写入 data.error

修复：在 Transmission 分支（torrent_crud.py:281）与 qBittorrent 分支
（torrent_crud.py:326）原领域异常 except 之后，新增 ``except Exception`` 兜底，
把任意下游异常转成 ``code=500 + 友好 msg`` 返回，与 batch add 端点（torrent_crud.py:645）
对齐。

本测试通过直接 await ``create_torrent`` 端点函数（绕过 FastAPI 路由层）+
mock 下载器缓存 + mock 下载器客户端，验证：
  1. 下载器客户端抛 ValueError 时，端点返回 code=500 + msg 含异常类型与文本，
     不再让异常冒泡（即不再触发 unhandled_exception_handler）。
  2. 下载器客户端抛 TypeError（复刻 transmission_rpc→requests json.dumps
     真实路径的异常形态）时同样被兜底。
  3. 既有领域异常分支（TransmissionError / APIError）语义不被破坏。

不做端到端真实 RPC（progress.md F 项已说明 ROI 不足），仅锚定异常边界行为。
"""

import asyncio
import bencodepy
from io import BytesIO
from typing import Any, List
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from qbittorrentapi.exceptions import APIError
from transmission_rpc import TransmissionError

from app.api.endpoints.torrent_crud import create_torrent


@pytest.fixture(autouse=True)
def _patch_runtime_call():
    """端点已迁移至 call_downloader_api（W2-3 P0-04）：测试直接执行 func 保持异常语义。

    全量 pytest 中其它 TestClient 测试（如 test_tag_aggregation_api）经 lifespan 退出会
    关闭全局 downloader_api_runtime executor，此处若不 patch，真实 call_downloader_api
    会抛 RuntimeError('cannot schedule new futures after shutdown')。按仓库既有约定
    （test_torrent_speed_regression / test_active_torrents_endpoint）统一 patch。
    """

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        # 保持异常透传语义：func 抛什么异常就原样抛什么（与 runtime 行为一致）
        return func(*args, **(kwargs or {}))

    # 二期改造（torrent-lookup-service-2026-10-08）：轮询/tracker 刷新分别在
    # torrent_lookup_service / torrent_add_helpers 模块内经 call_downloader_api 调用，
    # 同步纳入 fake 直调；轮询间隔置零加速；tracker 刷新隔离 AsyncSessionLocal
    with (
        patch("app.services.torrent_add_service.call_downloader_api", side_effect=fake_call),
        patch("app.services.torrent_lookup_service.call_downloader_api", side_effect=fake_call),
        patch("app.services.torrent_add_helpers.call_downloader_api", side_effect=fake_call),
        patch("app.services.torrent_add_service.refresh_trackers_after_add", new=AsyncMock(return_value=True)),
        patch("app.services.torrent_add_helpers.ADD_POLL_INTERVAL", 0.0),
    ):
        yield


def _make_valid_torrent_bytes() -> bytes:
    """构造最小合法的 bencode 种子文件（含 info dict），供 calculate_info_hash 走通。"""
    info = {
        b"name": b"test-torrent",
        b"length": 16,
        b"piece length": 16384,
        b"pieces": b"\x00" * 20,
    }
    return bencodepy.encode({b"announce": b"http://tracker.example.com/announce", b"info": info})


class _FakeRequest:
    """最小 Request 桩：仅暴露 create_torrent 用到的属性。"""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.method = "POST"
        self.url = MagicMock(path="/api/v1/torrents/add")
        self.headers: dict = {}
        self.cookies: dict = {}
        self.client = None


def _make_cached_downloader(*, downloader_type: int, client: Any) -> Any:
    """构造一个会被 app.state.store.get_snapshot() 返回的有效下载器 VO。"""
    downloader = MagicMock()
    downloader.downloader_id = "dl-test"
    downloader.downloader_type = downloader_type
    downloader.nickname = "test-dl"
    downloader.fail_time = 0
    downloader.client = client
    return downloader


def _make_app_with_store(downloaders: List[Any]) -> Any:
    app = MagicMock()
    app.state.store.get_snapshot = AsyncMock(return_value=downloaders)
    return app


def _make_upload(content: bytes) -> UploadFile:
    return UploadFile(filename="test.torrent", file=BytesIO(content))


@pytest.fixture
def event_loop_policy():
    """保证每个测试用独立事件循环（避免 asyncio.create_task 跨用例污染）。"""
    return asyncio.DefaultEventLoopPolicy()


@pytest.mark.asyncio
async def test_transmission_value_error_is_caught():
    """Transmission 分支：add_torrent 抛 ValueError 时被 except Exception 兜底。

    复刻 prod 报错链路中最常见形态：transmission_rpc 在参数处理阶段抛 ValueError。
    修复前会冒泡到 unhandled_exception_handler，修复后转 code=500 + 友好 msg。
    """
    client = MagicMock()
    client.add_torrent.side_effect = ValueError("invalid download_dir")

    app = _make_app_with_store([_make_cached_downloader(downloader_type=1, client=client)])

    result = await create_torrent(
        _user=None,
        request=_FakeRequest(app),
        downloader_id="dl-test",
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
    assert result.status == "failed"
    # 双语 P4 错误契约：动态异常类型不再进 msg（固定文案），由 reasonCode 承载失败语义
    assert result.msg == "添加种子失败，请稍后重试"
    assert result.data == {"reasonCode": "TORRENT_ADD_FAILED"}
    # 关键：没有冒泡（如果冒泡会直接抛出而非 return）


@pytest.mark.asyncio
async def test_transmission_type_error_is_caught():
    """Transmission 分支：add_torrent 抛 TypeError 时被兜底。

    精确复刻 prod 报错字符串：transmission_rpc→requests.post(json=query) 内部
    json.dumps 撞 ValueError 实例时，requests 抛 TypeError，
    str(TypeError) 即 'Object of type ValueError is not JSON serializable'。
    """
    client = MagicMock()
    client.add_torrent.side_effect = TypeError("Object of type ValueError is not JSON serializable")

    app = _make_app_with_store([_make_cached_downloader(downloader_type=1, client=client)])

    result = await create_torrent(
        _user=None,
        request=_FakeRequest(app),
        downloader_id="dl-test",
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
    # 双语 P4 错误契约：动态异常类型不再进 msg（固定文案），由 reasonCode 承载失败语义
    assert result.msg == "添加种子失败，请稍后重试"
    assert result.data == {"reasonCode": "TORRENT_ADD_FAILED"}
    # 双语 P4：msg 固定（异常细节只进日志）；fail-closed 语义由 reasonCode 承载
    assert result.msg == "添加种子失败，请稍后重试"
    assert result.data == {"reasonCode": "TORRENT_ADD_FAILED"}


@pytest.mark.asyncio
async def test_transmission_domain_error_still_handled():
    """领域异常 TransmissionError 走原精细分支，msg 为原始异常文本（不含类型前缀）。

    确保新增 except Exception 不破坏既有领域异常语义。
    """
    client = MagicMock()
    client.add_torrent.side_effect = TransmissionError("transmission daemon down")

    app = _make_app_with_store([_make_cached_downloader(downloader_type=1, client=client)])

    result = await create_torrent(
        _user=None,
        request=_FakeRequest(app),
        downloader_id="dl-test",
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
    # 领域分支保持原语义：msg 直接是 str(e)，不加类型前缀
    assert result.msg == "transmission daemon down"


@pytest.mark.asyncio
async def test_qbittorrent_value_error_is_caught():
    """qBittorrent 分支：torrents_add 抛 ValueError 时被 except Exception 兜底。"""
    client = MagicMock()
    client.torrents_add.side_effect = ValueError("bad save_path")

    app = _make_app_with_store([_make_cached_downloader(downloader_type=0, client=client)])

    result = await create_torrent(
        _user=None,
        request=_FakeRequest(app),
        downloader_id="dl-test",
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
    # 双语 P4 错误契约：动态异常类型不再进 msg（固定文案），由 reasonCode 承载失败语义
    assert result.msg == "添加种子失败，请稍后重试"
    assert result.data == {"reasonCode": "TORRENT_ADD_FAILED"}
    # 双语 P4：msg 固定（异常细节只进日志）；fail-closed 语义由 reasonCode 承载
    assert result.msg == "添加种子失败，请稍后重试"
    assert result.data == {"reasonCode": "TORRENT_ADD_FAILED"}


@pytest.mark.asyncio
async def test_qbittorrent_type_error_is_caught():
    """qBittorrent 分支：torrents_add 抛 TypeError 时被兜底。"""
    client = MagicMock()
    client.torrents_add.side_effect = TypeError("Object of type ValueError is not JSON serializable")

    app = _make_app_with_store([_make_cached_downloader(downloader_type=0, client=client)])

    result = await create_torrent(
        _user=None,
        request=_FakeRequest(app),
        downloader_id="dl-test",
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
    # 双语 P4 错误契约：动态异常类型不再进 msg（固定文案），由 reasonCode 承载失败语义
    assert result.msg == "添加种子失败，请稍后重试"
    assert result.data == {"reasonCode": "TORRENT_ADD_FAILED"}


@pytest.mark.asyncio
async def test_qbittorrent_domain_error_still_handled():
    """领域异常 APIError 走原精细分支，msg 为原始异常文本。"""
    client = MagicMock()
    client.torrents_add.side_effect = APIError("qb add failed")

    app = _make_app_with_store([_make_cached_downloader(downloader_type=0, client=client)])

    result = await create_torrent(
        _user=None,
        request=_FakeRequest(app),
        downloader_id="dl-test",
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
    assert result.msg == "qb add failed"


# ============================================================================
# 以下为 prod-hotfix-2026-07-19 真实根因回归测试
#
# 真实根因（已用 TestClient 复现验证）：
#   qBittorrent 分支早期版本的 try/except 作用域不完整 —— 只覆盖了
#   torrents_add/torrents_info 轮询，把 create_qbittorrent_torrent_record
#   + db.commit() 留在了 try 块之外。当 qBittorrent API 返回的种子字段
#   是异常对象（如 added_on/total_size 为 ValueError 实例）时：
#     - create_qbittorrent_torrent_record 内部 `qb_torrent.added_on > 0`
#       抛 TypeError
#     - SQLAlchemy Column 类型转换抛 StatementError(TypeError(...))
#   这些异常直接冒泡到 unhandled_exception_handler，前端看到
#   "Object of type ValueError is not JSON serializable"。
#
# 修复：把整个 qBittorrent 分支（含 ORM 写入）纳入 try 块，让 except Exception
# 能捕获所有路径的异常。与 Transmission 分支（line 221）结构对齐。
#
# 这批测试用真实 SQLite + 完整 TorrentInfo 表，复刻生产数据写入路径，
# 锚定「ORM 写入阶段抛异常时不再冒泡到全局 handler」这一核心修复点。
# ============================================================================


def _make_qb_torrent_with_bad_field(*, bad_field: str):
    """构造一个 qbittorrentapi 种子对象，指定字段为 ValueError 实例。

    复刻生产场景：qBittorrent API 在异常状态下可能返回非预期类型的字段值。
    qbittorrentapi 库的属性访问是惰性解析，部分字段解析失败时会留下异常对象。
    """
    bad = MagicMock()
    bad.hash = "a" * 40
    bad.name = "test-torrent"
    bad.save_path = "/downloads"
    # 注意：VO 读的是 torrents/info 的 size 字段（原 create_*_torrent_record 误用
    # total_size，真实 qB API 无此键恒 None，二期已修正）；stub 显式补齐 VO 全字段，
    # 避免 MagicMock 自动属性混入数值转换
    bad.size = 1024
    bad.state = "pausedUP"
    bad.progress = 0.5
    bad.downloaded = 0
    bad.uploaded = 0
    bad.added_on = 1700000000
    bad.completion_on = 0
    bad.ratio = 0
    bad.ratio_limit = -1
    bad.tags = []
    bad.category = ""
    bad.super_seeding = False
    # 注入坏字段
    setattr(bad, bad_field, ValueError(f"{bad_field} parse error"))
    return bad


def _make_qb_client_returning(qb_torrent):
    """构造 qb 客户端，torrents_add 成功、torrents_info 返回指定种子。"""
    c = MagicMock()
    c.torrents_add.return_value = "OK"
    c.torrents_info.return_value = [qb_torrent]
    return c


@pytest.fixture
def real_db_session():
    """真实 SQLite + 完整 TorrentInfo 表，复刻生产 ORM 写入路径。

    MagicMock 的 db 无法触发 SQLAlchemy Column 类型转换，必须用真实 Session
    才能复现 StatementError(TypeError(float() argument...)) 这类异常。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.torrents.models import TorrentInfo, TrackerInfo
    from app.downloader.models import BtDownloaders

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[TorrentInfo.__table__, TrackerInfo.__table__, BtDownloaders.__table__],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(
        bind=engine,
        tables=[TrackerInfo.__table__, TorrentInfo.__table__, BtDownloaders.__table__],
    )


@pytest.mark.asyncio
async def test_qb_bad_added_on_field_does_not_bubble(real_db_session):
    """prod 根因回归：qb_torrent.added_on 是 ValueError 时不再冒泡到全局 handler。

    修复前：create_qbittorrent_torrent_record 内 `added_on > 0` 抛 TypeError，
    冒泡到 unhandled_exception_handler。
    修复后：整个分支纳入 try，TypeError 被 except Exception 捕获。
    """
    bad_torrent = _make_qb_torrent_with_bad_field(bad_field="added_on")
    client = _make_qb_client_returning(bad_torrent)
    app = _make_app_with_store([_make_cached_downloader(downloader_type=0, client=client)])

    result = await create_torrent(
        _user=None,
        request=_FakeRequest(app),
        downloader_id="dl-test",
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
        db=real_db_session,
    )

    # 二期演变（torrent-lookup-service-2026-10-08）：坏 added_on 经 VO 数值容错（_safe_int）
    # 归 0，走 added_date 兑底 now 语义（与 W3-2 批 added_on=0 兑底统一）——
    # 从原 500 演进为成功添加，且不再冒泡（核心修复点守住）
    assert result.code == "200"
    assert result.status == "success"
    from app.torrents.models import TorrentInfo as _TIAdded

    row = real_db_session.query(_TIAdded).filter(_TIAdded.downloader_id == "dl-test").first()
    assert row is not None
    from datetime import datetime as _dt

    assert row.added_date is not None and abs((_dt.now() - row.added_date).total_seconds()) < 60


@pytest.mark.asyncio
async def test_qb_bad_total_size_field_does_not_bubble(real_db_session):
    """prod 根因回归：qb_torrent.total_size 是 ValueError 时不再冒泡。

    修复前：size 字段是 ValueError，SQLAlchemy Column(float) 类型转换抛
    StatementError(TypeError(float() argument...))，冒泡到全局 handler。
    二期演变：VO 读 torrents/info 的 size 字段（与 total_size 无关，真实 API
    字段名修正），total_size 坏值不影响 VO 转换——改为断言添加成功且 size 落库正常。
    """
    bad_torrent = _make_qb_torrent_with_bad_field(bad_field="total_size")
    client = _make_qb_client_returning(bad_torrent)
    app = _make_app_with_store([_make_cached_downloader(downloader_type=0, client=client)])

    result = await create_torrent(
        _user=None,
        request=_FakeRequest(app),
        downloader_id="dl-test",
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
        db=real_db_session,
    )

    # 二期演变：total_size 坏值不再影响 VO（读 size 字段），种子应成功添加，
    # 且 size 落库为 VO 正常值 1024（锚定字段名修正后的正确行为）。
    # 注：行的 hash 是 calculate_info_hash 真实值，按 downloader_id 查询断言
    assert result.code == "200"
    assert result.status == "success"
    from app.torrents.models import TorrentInfo as _TI

    row = real_db_session.query(_TI).filter(_TI.downloader_id == "dl-test").first()
    assert row is not None and float(row.size or 0) == 1024.0


@pytest.mark.asyncio
async def test_qb_str_wrapped_field_is_safe(real_db_session):
    """对照测试：被 str() 包裹的字段（ratio/ratio_limit）是安全的，不会触发 bug。

    这类字段在 create_qbittorrent_torrent_record 内部用 `str(qb_torrent.xxx)`
    包裹，str() 对任何对象（包括 ValueError 实例）都不抛异常，故不会冒泡。
    本测试锚定「str() 包裹的字段不需要兜底」这一既有正确行为，防止过度修复。
    """
    bad_torrent = _make_qb_torrent_with_bad_field(bad_field="ratio")
    client = _make_qb_client_returning(bad_torrent)
    app = _make_app_with_store([_make_cached_downloader(downloader_type=0, client=client)])

    result = await create_torrent(
        _user=None,
        request=_FakeRequest(app),
        downloader_id="dl-test",
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
        db=real_db_session,
    )

    # VO 数值容错（_safe_float，对齐原 str() 包裹的防御语义）：坏 ratio 归 0.0，
    # 种子应成功添加不冒泡
    assert result.code == "200"
    assert result.status == "success"


# ==================== W3-2：UI 添加路径 added_date 兜底 ====================


class TestBuildRowFromVoAddedDateFallback:
    """_build_row_from_vo（原 create_qbittorrent_torrent_record 同职责继任）：
    VO addition_date 缺失/为 0 时本地时间兜底，>0 保留下载器时间戳。"""

    @staticmethod
    def _downloader():
        return SimpleNamespace(downloader_id="dl-1", downloader_type=0, nickname="qb")

    def test_added_on_zero_falls_back_to_now(self):
        from datetime import datetime

        from app.services.torrent_add_helpers import _build_row_from_vo

        vo = {
            "name": "测试种子",
            "download_path": "/downloads",
            "size": 1024,
            "state": "downloading",
            "progress": 0.0,
            "ratio": 0.0,
            "addition_date": 0,
            "completion_date": 0,
            "tags": "",
            "category": "",
            "torrent_file": None,
        }

        record = _build_row_from_vo(self._downloader(), "a" * 40, vo, operator="tester")

        assert record.added_date is not None
        assert abs((datetime.now() - record.added_date).total_seconds()) < 60
        assert record.create_time is not None
        assert record.update_time is not None

    def test_added_on_valid_keeps_downloader_timestamp(self):
        from datetime import datetime

        from app.services.torrent_add_helpers import _build_row_from_vo

        vo = {
            "name": "测试种子",
            "download_path": "/downloads",
            "size": 1024,
            "state": "seeding",
            "progress": 100.0,
            "ratio": 1.0,
            "addition_date": 1_700_000_000,
            "completion_date": 0,
            "tags": "",
            "category": "",
            "torrent_file": None,
        }

        record = _build_row_from_vo(self._downloader(), "a" * 40, vo, operator="tester")

        assert record.added_date == datetime.fromtimestamp(1_700_000_000)
        # qB 分支 torrent_file 按约定路径推导
        assert record.torrent_file == "/config/qbittorrent/BT_backup/" + "a" * 40 + ".torrent"
