# -*- coding: utf-8 -*-
"""双语 P4 错误契约测试（M1 剩余子范围：种子操作 / Tracker 操作 / 查询模板 / 添加链路）。

锁定的不变量（PLANS/desktop-bilingual.md §3.3、error-contract.md §1 原则）：
- CommonResponse 信封四字段不变；仅 data 新增 reasonCode 字段；
- 前端依赖 reasonCode 本地化展示（禁止按中文 msg 匹配），因此 reasonCode
  取值属于对外契约，本文件逐路径钉死；
- 动态拼接 msg（str(e)/type(e)）只进日志，msg 固定（防泄露 + 可翻译）；
- E02 历史双形态（成功信封携带失败语义）钉住不改协议；
- E03 通知事件键（version_update/orphan_scan_completed 的 extra_data.event）
  属于前端本地化契约，同样钉死。
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_db
from app.downloader.models import BtDownloaders
from app.exception_handlers import register_exception_handlers
from app.models.notification import Notification
from app.models.search_template import SearchTemplate
from app.torrents.models import TorrentInfo


def _reason_code(body: dict) -> str:
    data = body["data"]
    assert isinstance(data, dict), f"data 应为携带 reasonCode 的 dict，实际: {data!r}"
    return data["reasonCode"]


class _FakeStore:
    """最小化下载器缓存替身：get_snapshot 返回注入的 VO 列表。"""

    def __init__(self, items=None):
        self._items = items or []

    async def get_snapshot(self):
        return self._items


@pytest.fixture()
def contract_env():
    """内存库 + 认证豁免的 TestClient（store 由用例按需注入 app.state）。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            BtDownloaders.__table__,
            TorrentInfo.__table__,
            SearchTemplate.__table__,
            Notification.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()

    app = FastAPI()
    # 复刻生产异常处理链（422 归一化为 CommonResponse + data.errors 数组）
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id="1")
    client = TestClient(app, raise_server_exceptions=False)
    yield client, app, Session
    db.close()
    engine.dispose()


# ====================================================================
# 一、种子状态操作（/torrent-status）：pause / resume / recheck
# ====================================================================

URL_PAUSE = "/api/v1/torrent-status/pause"
URL_RESUME = "/api/v1/torrent-status/resume"
URL_RECHECK = "/api/v1/torrent-status/recheck"
URL_REANNOUNCE = "/api/v1/torrent-status/reannounce"
URL_REANNOUNCE_BY_DL = "/api/v1/torrent-status/reannounce-by-downloader"


@pytest.mark.parametrize("url", [URL_PAUSE, URL_RESUME, URL_RECHECK])
def test_torrent_op_empty_hashes_e17_shape(url, contract_env):
    """hashes 空 → 被 pydantic min_length=1 拦截，HTTP 422 + data.errors 数组
    （E17 字段校验契约：type=missing，业务 400 分支为防御性死代码不可达）。"""
    client, app, _ = contract_env
    resp = client.post(url, json={"downloader_id": "d1", "hashes": []})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "422"
    errors = body["data"]["errors"]
    assert errors[0]["type"] == "too_short"
    assert errors[0]["loc"][-1] == "hashes"


@pytest.mark.parametrize("url", [URL_PAUSE, URL_RESUME, URL_RECHECK])
def test_torrent_op_cache_missing_reason(url, contract_env):
    """app.state.store 缺失 → 500 + DOWNLOADER_CACHE_UNAVAILABLE（fail-closed）。"""
    client, app, _ = contract_env
    resp = client.post(url, json={"downloader_id": "d1", "hashes": ["h1"]})
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == "500"
    assert _reason_code(body) == "DOWNLOADER_CACHE_UNAVAILABLE"


def test_torrent_op_downloader_not_in_cache_reason(contract_env):
    """store 有快照但目标下载器不在缓存 → 404 + DOWNLOADER_NOT_FOUND。"""
    client, app, _ = contract_env
    app.state.store = _FakeStore(items=[])
    resp = client.post(URL_PAUSE, json={"downloader_id": "missing", "hashes": ["h1"]})
    body = resp.json()
    assert body["code"] == "404"
    assert _reason_code(body) == "DOWNLOADER_NOT_FOUND"


def test_torrent_op_downloader_offline_reason(contract_env):
    """下载器 fail_time>0 → 503 + DOWNLOADER_OFFLINE（E12 状态语义）。"""
    client, app, _ = contract_env
    app.state.store = _FakeStore(
        items=[SimpleNamespace(downloader_id="d1", fail_time=123, nickname="n", client=object())]
    )
    resp = client.post(URL_PAUSE, json={"downloader_id": "d1", "hashes": ["h1"]})
    body = resp.json()
    assert body["code"] == "503"
    assert _reason_code(body) == "DOWNLOADER_OFFLINE"


def test_torrent_op_client_missing_reason(contract_env):
    """缓存对象无 client 连接 → 500 + DOWNLOADER_CONNECTION_MISSING（E13）。"""
    client, app, _ = contract_env
    app.state.store = _FakeStore(items=[SimpleNamespace(downloader_id="d1", fail_time=0, nickname="n", client=None)])
    resp = client.post(URL_PAUSE, json={"downloader_id": "d1", "hashes": ["h1"]})
    body = resp.json()
    assert body["code"] == "500"
    assert _reason_code(body) == "DOWNLOADER_CONNECTION_MISSING"


def test_torrent_op_records_not_found_reason(contract_env):
    """下载器可用但库中无匹配种子记录 → 404 + TORRENT_RECORDS_NOT_FOUND。"""
    client, app, Session = contract_env
    app.state.store = _FakeStore(
        items=[SimpleNamespace(downloader_id="d1", fail_time=0, nickname="n", client=object())]
    )
    resp = client.post(URL_PAUSE, json={"downloader_id": "d1", "hashes": ["nope"]})
    body = resp.json()
    assert body["code"] == "404"
    assert _reason_code(body) == "TORRENT_RECORDS_NOT_FOUND"


def test_reannounce_empty_params_reason(contract_env):
    """Tracker 汇报：hashes 与 info_ids 均空 → 400 + TORRENT_HASHES_REQUIRED。"""
    client, _, _ = contract_env
    resp = client.post(URL_REANNOUNCE, json={"downloader_id": "d1"})
    body = resp.json()
    assert body["code"] == "400"
    assert _reason_code(body) == "TORRENT_HASHES_REQUIRED"


def test_reannounce_by_downloader_no_torrents_reason(contract_env):
    """按下载器汇报：下载器行存在但无种子 → 404 + DOWNLOADER_NO_TORRENTS。"""
    client, app, Session = contract_env
    s = Session()
    s.add(
        BtDownloaders(
            downloader_id="d1",
            nickname="dl",
            downloader_type=0,
            dr=0,
            enabled=True,
            status="1",
        )
    )
    s.commit()
    s.close()
    resp = client.post(URL_REANNOUNCE_BY_DL, json={"downloader_id": "d1", "trackers": "http://t"})
    body = resp.json()
    assert body["code"] == "404"
    assert _reason_code(body) == "DOWNLOADER_NO_TORRENTS"


# ====================================================================
# 二、Tracker 操作（/tracker）
# ====================================================================

URL_ADD_BY_DL = "/api/v1/tracker/addTracker-by-downloader"
URL_MODIFY_BY_DL = "/api/v1/tracker/modifyTracker-by-downloader"


@pytest.mark.parametrize("url", [URL_ADD_BY_DL, URL_MODIFY_BY_DL])
def test_tracker_by_downloader_empty_trackers_reason(url, contract_env):
    """by-downloader：trackers 空 → 400 + TRACKER_URL_REQUIRED。"""
    client, _, _ = contract_env
    resp = client.post(url, json={"downloader_id": "d1", "trackers": ""})
    body = resp.json()
    assert body["code"] == "400"
    assert _reason_code(body) == "TRACKER_URL_REQUIRED"


def test_tracker_by_downloader_downloader_missing_reason(contract_env):
    """by-downloader：下载器行不存在 → 404 + DOWNLOADER_NOT_FOUND。"""
    client, _, _ = contract_env
    resp = client.post(URL_ADD_BY_DL, json={"downloader_id": "ghost", "trackers": "http://t"})
    body = resp.json()
    assert body["code"] == "404"
    assert _reason_code(body) == "DOWNLOADER_NOT_FOUND"


@pytest.mark.asyncio
async def test_tracker_by_downloader_cache_missing_reason():
    """by-downloader：缓存未初始化 → 500 + DOWNLOADER_CACHE_UNAVAILABLE
    （_DownloaderUnavailableError 携带 reason_code 透传路径；直调共享体避免 ORM 全字段构造）。"""
    from unittest.mock import MagicMock

    from app.api.endpoints.tracker import _apply_tracker_op_by_downloader

    # req.app.state 无 store 属性 → _get_downloader_vo_map 抛 _DownloaderUnavailableError
    req = MagicMock()
    req.app = SimpleNamespace(state=SimpleNamespace())
    db = MagicMock()
    dl_result = MagicMock()
    dl_result.scalars.return_value.first.return_value = SimpleNamespace(is_qbittorrent=True)
    ti_result = MagicMock()
    ti_result.scalars.return_value.all.return_value = [SimpleNamespace(info_id="i1", torrent_id="t1")]
    db.execute = AsyncMock(side_effect=[dl_result, ti_result])

    resp = await _apply_tracker_op_by_downloader(
        req=req,
        background_tasks=MagicMock(),
        db=db,
        downloader_id="d1",
        tracker_list=["http://t/ann"],
        operation="add",
    )
    assert resp.code == "500"
    assert resp.data == {"reasonCode": "DOWNLOADER_CACHE_UNAVAILABLE"}


def test_tracker_replace_not_found_reason(contract_env):
    """replaceTracker：未命中 tracker → 404 + TRACKER_NOT_FOUND。"""
    client, _, _ = contract_env
    resp = client.post(
        "/api/v1/tracker/replaceTracker",
        params={"replace_tracker_url": "http://a/ann", "target_tracker_url": "http://b/ann"},
    )
    body = resp.json()
    assert body["code"] == "404"
    assert _reason_code(body) == "TRACKER_NOT_FOUND"


# ====================================================================
# 三、查询模板 CRUD（/advanced-search/search-templates）
# ====================================================================

URL_TEMPLATES = "/api/v1/advanced-search/search-templates"


def _valid_conditions():
    return {"condition_groups": [], "match_mode": "all"}


def test_template_create_invalid_conditions_e17_shape(contract_env):
    """创建模板条件无效 → 被 pydantic 字段校验拦截，HTTP 422 + data.errors
    （E17 契约：type=value_error + loc；服务层 ValueError 分支为非 HTTP 调用方防御）。"""
    client, _, _ = contract_env
    resp = client.post(
        URL_TEMPLATES,
        json={"name": "t", "description": "", "conditions": {"condition_groups": "not-a-list"}},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "422"
    errors = body["data"]["errors"]
    assert errors[0]["type"] == "value_error"
    assert errors[0]["loc"][-1] == "conditions"


def test_template_service_invalid_conditions_reason_code():
    """服务层直调：ValueError → 422 + SEARCH_TEMPLATE_INVALID_CONDITIONS
    （MCP 等非 HTTP 调用方依赖该 reasonCode）。"""
    from unittest.mock import MagicMock

    from app.services.advanced_search import AdvancedSearchService

    svc = AdvancedSearchService.__new__(AdvancedSearchService)
    svc.template_model = MagicMock()
    result = svc.create_search_template(
        {"name": "t", "description": "", "conditions": {"source": "bogus"}, "is_public": False},
        "user-1",
    )
    assert result["code"] == "422"
    assert result["data"] == {"reasonCode": "SEARCH_TEMPLATE_INVALID_CONDITIONS"}


def test_template_update_not_found_reason(contract_env):
    """更新不存在的模板 → 404 + SEARCH_TEMPLATE_NOT_FOUND。"""
    client, _, _ = contract_env
    resp = client.put(
        f"{URL_TEMPLATES}/tpl-missing",
        json={"id": "tpl-missing", "name": "n"},
    )
    body = resp.json()
    assert body["code"] == "404"
    assert _reason_code(body) == "SEARCH_TEMPLATE_NOT_FOUND"


def test_template_update_forbidden_reason(contract_env):
    """更新他人模板 → 403 + SEARCH_TEMPLATE_FORBIDDEN。"""
    client, _, Session = contract_env
    s = Session()
    s.add(
        SearchTemplate(
            id="tpl-1",
            user_id="someone-else",
            name="other",
            description="",
            conditions="{}",
            is_default=0,
            is_public=0,
        )
    )
    s.commit()
    s.close()
    resp = client.put(
        f"{URL_TEMPLATES}/tpl-1",
        json={"id": "tpl-1", "name": "steal"},
    )
    body = resp.json()
    assert body["code"] == "403"
    assert _reason_code(body) == "SEARCH_TEMPLATE_FORBIDDEN"


def test_template_delete_not_found_reason(contract_env):
    """删除不存在的模板 → 404 + SEARCH_TEMPLATE_NOT_FOUND。"""
    client, _, _ = contract_env
    resp = client.delete(f"{URL_TEMPLATES}/tpl-missing")
    body = resp.json()
    assert body["code"] == "404"
    assert _reason_code(body) == "SEARCH_TEMPLATE_NOT_FOUND"


# ====================================================================
# 四、种子添加链路（/torrents/add、/torrents/add-batch）
# ====================================================================

URL_ADD = "/api/v1/torrents/add"
URL_ADD_BATCH = "/api/v1/torrents/add-batch"


def test_add_single_cache_missing_reason(contract_env):
    """单添加：store 未注入 → 500 + DOWNLOADER_CACHE_UNAVAILABLE + 固定 msg。"""
    client, app, _ = contract_env
    resp = client.post(
        URL_ADD,
        data={"downloader_id": "d1", "save_path": "/x"},
        files={"torrent_file": ("a.torrent", b"x", "application/x-bittorrent")},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == "500"
    assert _reason_code(body) == "DOWNLOADER_CACHE_UNAVAILABLE"


def test_add_single_downloader_not_found_reason(contract_env):
    """单添加：下载器不在缓存 → 404 + DOWNLOADER_NOT_FOUND。"""
    client, app, _ = contract_env
    app.state.store = _FakeStore(items=[])
    resp = client.post(
        URL_ADD,
        data={"downloader_id": "d1", "save_path": "/x"},
        files={"torrent_file": ("a.torrent", b"x", "application/x-bittorrent")},
    )
    body = resp.json()
    assert body["code"] == "404"
    assert _reason_code(body) == "DOWNLOADER_NOT_FOUND"


def test_add_batch_empty_files_e17_shape(contract_env):
    """批量添加提交：未选文件 → pydantic 422 + data.errors（E17 形态；
    torrent_files 为 File(...) 必填，业务空列表分支为防御性代码不可达）。"""
    client, _, _ = contract_env
    resp = client.post(
        URL_ADD_BATCH,
        data={"downloader_id": "d1", "save_path": "/x"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "422"
    errors = body["data"]["errors"]
    assert errors[0]["type"] == "missing"
    assert errors[0]["loc"][-1] == "torrent_files"


def test_add_batch_cache_missing_reason(contract_env):
    """批量添加提交：store 缺失 → 500 + DOWNLOADER_CACHE_UNAVAILABLE。"""
    client, app, _ = contract_env
    resp = client.post(
        URL_ADD_BATCH,
        data={"downloader_id": "d1", "save_path": "/x"},
        files={"torrent_files": ("a.torrent", b"de", "application/x-bittorrent")},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == "500"
    assert _reason_code(body) == "DOWNLOADER_CACHE_UNAVAILABLE"


def test_add_batch_downloader_offline_reason(contract_env):
    """批量添加提交：下载器已失效 → 503 + DOWNLOADER_OFFLINE + 固定 msg。"""
    client, app, _ = contract_env
    app.state.store = _FakeStore(
        items=[SimpleNamespace(downloader_id="d1", fail_time=99, nickname="n", client=object())]
    )
    resp = client.post(
        URL_ADD_BATCH,
        data={"downloader_id": "d1", "save_path": "/x"},
        files={"torrent_files": ("a.torrent", b"de", "application/x-bittorrent")},
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == "503"
    assert _reason_code(body) == "DOWNLOADER_OFFLINE"


# ====================================================================
# 五、E02 历史形态钉住（成功信封携带失败语义 → 冻结不改协议）
# ====================================================================


def test_e02_downloader_getlist_cache_missing_form_pinned(contract_env):
    """E11/E02：/downloader/getList 缓存未初始化返回 success+200+data=[]，
    信封携带失败语义属历史形态——钉住不改（前端按空列表展示，不按 msg 分支）。"""
    client, app, _ = contract_env
    assert not hasattr(app.state, "store")
    resp = client.get("/api/v1/downloader/getList")
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "success"
    assert body["code"] == "200"
    assert body["data"] == []


# ====================================================================
# 六、E03 通知事件键（extra_data.event 契约）
# ====================================================================


@pytest.mark.asyncio
async def test_e03_orphan_scan_event_includes_warning_flag(contract_env):
    """孤儿扫描通知 extra_data：event/orphan_count/orphan_size/orphan_count_warning 契约。"""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

    from app.services.orphan_notification import notify_scan_completed

    _, _, Session = contract_env
    # 复用同一内存库的异步形态（StaticPool 单连接）
    aengine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with aengine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Notification.__table__.create(sync_conn, checkfirst=True))
    async_session = async_sessionmaker(aengine, class_=AsyncSession)
    async with async_session() as adb:
        notif = await notify_scan_completed(
            db=adb,
            scan_id="scan-1",
            scan_type="manual",
            orphan_count=5,
            orphan_size=1024,
            orphan_count_warning=True,
        )
        assert notif is not None
        extra = json.loads(notif.extra_data) if isinstance(notif.extra_data, str) else notif.extra_data
        assert extra["event"] == "orphan_scan_completed"
        assert extra["orphan_count"] == 5
        assert extra["orphan_size"] == 1024
        assert extra["orphan_count_warning"] is True
    await aengine.dispose()


@pytest.mark.asyncio
async def test_e03_version_update_notification_event_key(contract_env, monkeypatch):
    """版本更新通知 extra_data 必须携带 event=version_update（E03 前端本地化契约）。"""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

    from app.services.notification_service import NotificationService

    aengine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with aengine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Notification.__table__.create(sync_conn, checkfirst=True))
    async_session = async_sessionmaker(aengine, class_=AsyncSession)

    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "tag_name": "v1.9.9",
                "html_url": "https://github.com/strainhzj/BtDeck/releases/tag/v1.9.9",
                "body": "release notes",
                "published_at": "2026-01-01T00:00:00Z",
            }

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _FakeClient())

    async with async_session() as adb:
        service = NotificationService(adb)
        notif = await service.check_version_update(current_version="1.0.5")
        assert notif is not None
        extra = json.loads(notif.extra_data) if isinstance(notif.extra_data, str) else notif.extra_data
        assert extra["event"] == "version_update"
        assert extra["version"] == "1.9.9"
        assert extra["release_url"].endswith("v1.9.9")
    await aengine.dispose()
