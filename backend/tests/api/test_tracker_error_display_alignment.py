# -*- coding: utf-8 -*-
"""
Tracker 错误展示对齐（展示层 ↔ 判定任务）的 API 级测试

背景：Transmission 对「HTTP 200 + bencode failure reason」的 announce 上报
lastAnnounceSucceeded=true，同步落库状态码 2（工作中）；判定任务按消息文本
精确匹配失败池置 has_tracker_error=1。本文件锁定展示层与判定同口径：
- getList 的 trackerInfo announce/scrape 文本在消息命中失败池时覆写"工作失败"
- TorrentInfoVO 透传 hasTrackerError（getList camelCase / duplicates snake_case）
- duplicates 端点 status=error 筛选口径与 getList 一致（OR has_tracker_error）
- not-contacted 中性状态码下的残留消息不覆写（对齐判定任务语义）
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.api.models.advanced_search import EnhancedAdvancedSearchRequest
from app.auth.dependencies import get_current_user, require_authenticated_user
from app.core.tracker_keyword_map import load_active_keyword_map
from app.core.tracker_status_policy import tracker_display_failed
from app.database import Base, get_db
from app.downloader.models import BtDownloaders
from app.services.advanced_search import AdvancedSearchService
from app.tasks.scheduler.torrent_tracker_status_judge import (
    TorrentTrackerStatusJudge,
    evaluate_tracker_error_state,
)
from app.torrents.models import TorrentInfo, TrackerInfo, TrackerKeywordConfig
from tests.api.conftest import make_torrent

FAILED_MSG = "You cannot seed the same torrent in the same location from more than 1 client."
IGNORED_MSG = "您已在 tracker.hdkyl.in 汇报过了"
SCRAPE_FAILED_MSG = "Torrent not exists"

GET_LIST_URL = "/api/v1/torrents/getList"
DUPLICATES_URL = "/api/v1/torrents/duplicates"

# ==================== Fixtures ====================


@pytest.fixture
def db_session():
    """内存 SQLite（StaticPool 复用单连接），建 4 张表。

    TrackerKeywordConfig 供展示覆写加载关键词池（与判定任务共用 loader）。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        TorrentInfo.__table__,
        TrackerInfo.__table__,
        BtDownloaders.__table__,
        TrackerKeywordConfig.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=list(reversed(tables)))


@pytest.fixture
def client(db_session):
    """独立 FastAPI app，同时覆盖两种鉴权依赖（getList 与 duplicates 各用其一）。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")

    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ==================== 辅助构造 ====================


def _add_keyword(db, keyword_type, keyword, *, enabled=True, dr=0):
    db.add(TrackerKeywordConfig(keyword_type=keyword_type, keyword=keyword, enabled=enabled, dr=dr))
    db.commit()


def _seed_default_pools(db):
    """与生产关键词池同构的三池样例（failed/ignored/success 各一）。"""
    _add_keyword(db, "failed", FAILED_MSG)
    _add_keyword(db, "failed", SCRAPE_FAILED_MSG)
    _add_keyword(db, "ignored", IGNORED_MSG)
    _add_keyword(db, "success", "Success")


def _add_tracker(
    db,
    torrent_info_id,
    *,
    tracker_name="1ptba",
    announce_code=2,
    announce_msg=None,
    scrape_code=2,
    scrape_msg=None,
):
    now = datetime.now()
    db.add(
        TrackerInfo(
            tracker_id=f"trk-{uuid4().hex[:8]}",
            torrent_info_id=torrent_info_id,
            tracker_name=tracker_name,
            tracker_url=f"https://{tracker_name}.com/announce",
            last_announce_succeeded=announce_code,
            last_announce_msg=announce_msg,
            last_scrape_succeeded=scrape_code,
            last_scrape_msg=scrape_msg,
            create_time=now,
            create_by="tester",
            update_time=now,
            update_by="tester",
            dr=0,
        )
    )
    db.commit()


def _get_list_item(client, info_id):
    body = client.get(GET_LIST_URL, params={"skip": 0, "limit": 200}).json()
    assert body["status"] == "success", body
    for item in body["data"]["list"]:
        if item["infoId"] == info_id:
            return item
    raise AssertionError(f"infoId={info_id} 未出现在 getList 结果中")


# ==================== 组1：共享关键词加载器 ====================


class TestLoadActiveKeywordMap:
    def test_只加载三池关键词(self, db_session):
        """candidate 不参与判定；重复关键词被唯一索引拦截，first-wins 仅为防御。"""
        _seed_default_pools(db_session)
        _add_keyword(db_session, "candidate", "待定关键词")

        keyword_map = load_active_keyword_map(db_session)

        assert keyword_map.get(FAILED_MSG) == "failed"
        assert keyword_map.get(IGNORED_MSG) == "ignored"
        assert keyword_map.get("Success") == "success"
        assert "待定关键词" not in keyword_map

    def test_禁用与逻辑删除关键词不参与(self, db_session):
        _add_keyword(db_session, "failed", FAILED_MSG, enabled=False)
        _add_keyword(db_session, "failed", SCRAPE_FAILED_MSG, dr=1)

        assert load_active_keyword_map(db_session) == {}


# ==================== 组2：getList 展示覆写 ====================


class TestGetListDisplayOverride:
    def test_失败消息覆写为工作失败并透传种子标记(self, client, db_session):
        """tr 下载器 + 状态码 2 + 失败消息：展示对齐判定（1ptba 场景）。"""
        db_session.add(BtDownloaders(downloader_id="dl-tr", nickname="tr", downloader_type=1))
        db_session.commit()
        _seed_default_pools(db_session)
        make_torrent(
            db_session,
            info_id="info-tr-1",
            downloader_id="dl-tr",
            hash_="hash-tr-1",
            name="锦心似玉",
            status="seeding",
            has_tracker_error=True,
        )
        _add_tracker(db_session, "info-tr-1", announce_code=2, announce_msg=FAILED_MSG)

        item = _get_list_item(client, "info-tr-1")

        assert item["hasTrackerError"] is True
        assert item["trackerInfo"][0]["last_announce_succeeded"] == "工作失败"
        assert item["lastAnnounceSucceeded"] == "工作失败"

    def test_忽略池消息保持工作中(self, client, db_session):
        """ignored 属正常证据（判定语义），展示不覆写。"""
        _seed_default_pools(db_session)
        make_torrent(
            db_session,
            info_id="info-ign-1",
            downloader_id="dl-a",
            hash_="hash-ign-1",
            name="torrent-ign",
            has_tracker_error=False,
        )
        _add_tracker(db_session, "info-ign-1", announce_msg=IGNORED_MSG)

        item = _get_list_item(client, "info-ign-1")
        assert item["trackerInfo"][0]["last_announce_succeeded"] == "工作中"

    def test_成功消息保持工作中(self, client, db_session):
        _seed_default_pools(db_session)
        make_torrent(
            db_session,
            info_id="info-ok-1",
            downloader_id="dl-a",
            hash_="hash-ok-1",
            name="torrent-ok",
        )
        _add_tracker(db_session, "info-ok-1", announce_msg="Success")

        item = _get_list_item(client, "info-ok-1")
        assert item["trackerInfo"][0]["last_announce_succeeded"] == "工作中"

    def test_空关键词池不覆写(self, client, db_session):
        """无关键词时展示保持原始状态码语义（与判定任务空池跳过一致）。

        标记透传与文本覆写解耦：空池只影响覆写，不影响 hasTrackerError 透传。
        """
        make_torrent(
            db_session,
            info_id="info-empty-1",
            downloader_id="dl-a",
            hash_="hash-empty-1",
            name="torrent-empty",
            has_tracker_error=True,
        )
        _add_tracker(db_session, "info-empty-1", announce_msg=FAILED_MSG)

        item = _get_list_item(client, "info-empty-1")
        assert item["trackerInfo"][0]["last_announce_succeeded"] == "工作中"
        assert item["hasTrackerError"] is True

    def test_tr未联系与发送中不覆写残留消息(self, client, db_session):
        """tr 中性码 0/1 下的失败消息是残留旧值，展示不覆写；对照 code=2 覆写。"""
        db_session.add(BtDownloaders(downloader_id="dl-tr2", nickname="tr", downloader_type=1))
        db_session.commit()
        _seed_default_pools(db_session)
        cases = (("nc0", 0, "未联系"), ("nc1", 1, "发送中"), ("work", 2, "工作失败"))
        for suffix, code, expected_text in cases:
            make_torrent(
                db_session,
                info_id=f"info-trn-{suffix}",
                downloader_id="dl-tr2",
                hash_=f"hash-trn-{suffix}",
                name=f"torrent-trn-{suffix}",
            )
            _add_tracker(
                db_session,
                f"info-trn-{suffix}",
                tracker_name="trtrk",
                announce_code=code,
                announce_msg=FAILED_MSG,
            )

        for suffix, _, expected_text in cases:
            item = _get_list_item(client, f"info-trn-{suffix}")
            assert item["trackerInfo"][0]["last_announce_succeeded"] == expected_text

    def test_qb未联系状态不覆写残留消息(self, client, db_session):
        """qb 状态码 1（未联系）为中性：判定任务不采信消息，展示同样不覆写。"""
        _seed_default_pools(db_session)
        make_torrent(
            db_session,
            info_id="info-nc-1",
            downloader_id="dl-a",
            hash_="hash-nc-1",
            name="torrent-nc",
        )
        _add_tracker(db_session, "info-nc-1", tracker_name="qb-trk", announce_code=1, announce_msg=FAILED_MSG)

        item = _get_list_item(client, "info-nc-1")
        assert item["trackerInfo"][0]["last_announce_succeeded"] == "未联系"

    def test_scrape列独立覆写(self, client, db_session):
        """announce 正常 + scrape 消息命中失败池：仅 scrape 列显示失败。"""
        _seed_default_pools(db_session)
        make_torrent(
            db_session,
            info_id="info-sc-1",
            downloader_id="dl-a",
            hash_="hash-sc-1",
            name="torrent-sc",
        )
        _add_tracker(
            db_session,
            "info-sc-1",
            announce_msg="Success",
            scrape_code=2,
            scrape_msg=SCRAPE_FAILED_MSG,
        )

        item = _get_list_item(client, "info-sc-1")
        tracker_vo = item["trackerInfo"][0]
        assert tracker_vo["last_announce_succeeded"] == "工作中"
        assert tracker_vo["last_scrape_succeeded"] == "工作失败"

    def test_行级覆写互不影响健康种子(self, client, db_session):
        _seed_default_pools(db_session)
        make_torrent(
            db_session,
            info_id="info-bad-1",
            downloader_id="dl-a",
            hash_="hash-bad-1",
            name="torrent-bad",
            has_tracker_error=True,
        )
        _add_tracker(db_session, "info-bad-1", announce_msg=FAILED_MSG)
        make_torrent(
            db_session,
            info_id="info-good-1",
            downloader_id="dl-a",
            hash_="hash-good-1",
            name="torrent-good",
            has_tracker_error=False,
        )
        _add_tracker(db_session, "info-good-1", tracker_name="haidan", announce_msg="Success")

        bad = _get_list_item(client, "info-bad-1")
        good = _get_list_item(client, "info-good-1")
        assert bad["trackerInfo"][0]["last_announce_succeeded"] == "工作失败"
        assert bad["hasTrackerError"] is True
        assert good["trackerInfo"][0]["last_announce_succeeded"] == "工作中"
        assert good["hasTrackerError"] is False


# ==================== 组3：duplicates error 筛选口径对齐 ====================


class TestDuplicatesErrorFilterAlignment:
    def _make_duplicate_pair(self, db, hash_, *, flag, status="seeding"):
        """构造一对同 hash 种子（跨下载器，构成重复组），返回两个 info_id。"""
        ids = []
        for suffix in ("a", "b"):
            info_id = f"info-{hash_}-{suffix}"
            make_torrent(
                db,
                info_id=info_id,
                downloader_id=f"dl-{suffix}",
                downloader_name=suffix.upper(),
                hash_=hash_,
                name=f"torrent-{hash_}",
                status=status,
                has_tracker_error=flag,
            )
            ids.append(info_id)
        return ids

    def test_tracker异常种子命中error筛选(self, client, db_session):
        """seeding + has_tracker_error=True 的重复组被 status=error 筛出。"""
        _seed_default_pools(db_session)
        error_ids = self._make_duplicate_pair(db_session, "hashflag", flag=True)
        normal_ids = self._make_duplicate_pair(db_session, "hashnorm", flag=False)
        for info_id in error_ids:
            _add_tracker(
                db_session,
                info_id,
                announce_msg=FAILED_MSG,
                scrape_msg=SCRAPE_FAILED_MSG,
            )

        body = client.post(DUPLICATES_URL, json={"status": "error", "page": 1, "pageSize": 50}).json()
        assert body["status"] == "success", body

        returned = {item["info_id"] for item in body["data"]["list"]}
        assert set(error_ids) <= returned
        assert not (set(normal_ids) & returned)
        for item in body["data"]["list"]:
            if item["info_id"] in error_ids:
                # duplicates 端点 by_alias=False → snake_case
                assert item["has_tracker_error"] is True
                assert item["tracker_info"][0]["last_announce_succeeded"] == "工作失败"
                assert item["tracker_info"][0]["last_scrape_succeeded"] == "工作失败"

    def test_整种error状态仍然命中(self, client, db_session):
        """旧语义（status='error'）不回归。"""
        self._make_duplicate_pair(db_session, "hasherr", flag=False, status="error")

        body = client.post(DUPLICATES_URL, json={"status": "error", "page": 1, "pageSize": 50}).json()
        returned = {item["info_id"] for item in body["data"]["list"]}
        assert any(info_id in returned for info_id in ("info-hasherr-a", "info-hasherr-b"))

    def test_非error状态筛选不受影响(self, client, db_session):
        """普通状态筛选用精确匹配，tracker 异常种子不混入。"""
        self._make_duplicate_pair(db_session, "hashseed", flag=True)

        body = client.post(DUPLICATES_URL, json={"status": "seeding", "page": 1, "pageSize": 50}).json()
        returned = {item["info_id"] for item in body["data"]["list"]}
        assert "info-hashseed-a" in returned


# ==================== 组4：判定任务关键词加载委托链路 ====================


class TestJudgeTaskKeywordLoading:
    """锁定判定任务 _load_keywords → 共享 loader 的委托关系与降级语义。

    方法名与 to_thread 调用点是写库治理测试（test_heavy_task_db_write_governance）
    的锚点；本组保证委托后三池过滤与异常降级行为不回归。
    """

    def test_判定任务委托共享加载器保持三池语义(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine, tables=[TrackerKeywordConfig.__table__])
        factory = sessionmaker(bind=engine)
        db = factory()
        try:
            db.add(TrackerKeywordConfig(keyword_type="failed", keyword=FAILED_MSG))
            db.add(TrackerKeywordConfig(keyword_type="ignored", keyword=IGNORED_MSG))
            db.add(TrackerKeywordConfig(keyword_type="success", keyword="Success"))
            db.add(TrackerKeywordConfig(keyword_type="candidate", keyword="待定关键词"))
            db.commit()
        finally:
            db.close()

        task = TorrentTrackerStatusJudge()
        try:
            with patch(
                "app.tasks.scheduler.torrent_tracker_status_judge.SessionLocal",
                side_effect=factory,
            ):
                keyword_map = task._load_keywords()

            assert keyword_map.get(FAILED_MSG) == "failed"
            assert keyword_map.get(IGNORED_MSG) == "ignored"
            assert keyword_map.get("Success") == "success"
            assert "待定关键词" not in keyword_map
        finally:
            Base.metadata.drop_all(bind=engine, tables=[TrackerKeywordConfig.__table__])
            engine.dispose()

    def test_关键词表缺失时降级为空池不抛异常(self):
        """表缺失（如测试内存库未建表）时 loader 吞异常返回 {}，任务按空池跳过。"""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        factory = sessionmaker(bind=engine)
        task = TorrentTrackerStatusJudge()
        try:
            with patch(
                "app.tasks.scheduler.torrent_tracker_status_judge.SessionLocal",
                side_effect=factory,
            ):
                assert task._load_keywords() == {}
        finally:
            engine.dispose()


# ==================== 组5：判定 ↔ 展示一致性契约 ====================


class TestJudgeDisplayConsistency:
    """核心不变量：展示覆写口径 ⊆ 种子级 has_tracker_error 判定口径。

    两者共用同一 keyword_map 与同一中性码语义（tracker_display_failed 复刻
    evaluate_tracker_error_state 的 not-contacted 判定）。任何一侧单独调整
    匹配语义都会在此处红。
    """

    @pytest.mark.parametrize(
        ("judge_dl_type", "display_dl_type", "status_code", "message", "expected_flag", "expected_display"),
        [
            (1, "transmission", 2, FAILED_MSG, True, True),  # tr 工作中+失败消息（1ptba 场景）
            (0, "qbittorrent", 2, FAILED_MSG, True, True),  # qb 工作中+失败消息
            (1, "transmission", 3, FAILED_MSG, True, True),  # 本就是失败码
            (1, "transmission", 2, IGNORED_MSG, False, False),  # ignored 属正常证据，展示不覆写
            (1, "transmission", 2, "未配置的消息", None, False),  # unknown：判定保留旧值，展示保持原文本
            (0, "qbittorrent", 1, FAILED_MSG, False, False),  # qb 未联系：中性，残留消息不采信
            (1, "transmission", 0, FAILED_MSG, False, False),  # tr 未联系：同上
            (1, "transmission", 1, FAILED_MSG, False, False),  # tr 发送中：同上
        ],
    )
    def test_展示覆写与种子级判定共享同一口径(
        self, judge_dl_type, display_dl_type, status_code, message, expected_flag, expected_display
    ):
        keyword_map = {FAILED_MSG: "failed", IGNORED_MSG: "ignored"}
        tracker = SimpleNamespace(
            last_announce_succeeded=status_code,
            last_announce_msg=message,
            last_scrape_msg="",
        )

        flag = evaluate_tracker_error_state([tracker], keyword_map, judge_dl_type)
        display = tracker_display_failed(status_code, message, keyword_map, display_dl_type)

        assert flag is expected_flag
        assert display is expected_display


# ==================== 组6：高级搜索同源展示 ====================


class TestAdvancedSearchIntegration:
    """advanced_search 复用 convert_to_vos_with_trackers，必须同样获得
    hasTrackerError 透传与失败消息覆写（by_alias=True → camelCase）。"""

    def test_高级搜索透传标记并覆写展示(self, db_session):
        _seed_default_pools(db_session)
        make_torrent(
            db_session,
            info_id="info-as-1",
            downloader_id="dl-a",
            hash_="hash-as-1",
            name="torrent-advanced",
            status="seeding",
            has_tracker_error=True,
        )
        _add_tracker(db_session, "info-as-1", announce_msg=FAILED_MSG)

        result = AdvancedSearchService(db_session).search_torrents(
            EnhancedAdvancedSearchRequest(page=1, limit=100000),
            user_id="tester",
        )

        assert result["code"] == "200", result["msg"]
        items = [item for item in result["data"] if item["infoId"] == "info-as-1"]
        assert len(items) == 1
        assert items[0]["hasTrackerError"] is True
        assert items[0]["trackerInfo"][0]["last_announce_succeeded"] == "工作失败"
