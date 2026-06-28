# -*- coding: utf-8 -*-
"""
查询重复种子接口 POST /api/v1/torrents/duplicates 的 API 级回归测试

覆盖范围（17 个测试）：
- 认证拒绝 / 空数据
- 核心重复检测（HAVING count>=2）/ 唯一 hash 不返回 / dr 过滤
- 分页（pageSize / 超范围）
- 参数验证 422（page>=1 / pageSize<=200）
- 空列表 panic 防护（downloader_id="," / status="," 不报错）—— 锚定 commit 0622d53
- 过滤条件（多选/单值/min_size/hash 空值排除）
- 排序（hash DESC）/ name_like 模糊匹配
- tracker 批量组装（N+1 防护）

测试范式照搬 tests/api/test_cron_task_cleanup.py（独立 FastAPI app + 内存 StaticPool SQLite +
指定表建表 + 依赖覆盖）。经独立审查修订：
- 种子构造走 tests/api/conftest.py 的 make_torrent 工厂（24 位置参数 + 显式设
  has_tracker_error=False 已在工厂内收口）
- client 覆盖 get_current_user（非 require_authenticated_user）
- 所有断言用 code == "200"（字符串，避免类型假失败）
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import get_current_user
from app.database import Base, get_db
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo
from tests.api.conftest import make_torrent

# ==================== Fixtures ====================


@pytest.fixture
def db_session():
    """内存 SQLite（StaticPool 复用单连接），只建本接口用到的 3 张表。

    不做全量 create_all：避免 import 副作用（database.py 顶部 create_engine 读 settings）
    和无关表的外键依赖问题。
    """
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


@pytest.fixture
def client(db_session):
    """独立 FastAPI app，覆盖 get_db 指向内存库 + get_current_user 绕过 JWT。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")

    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ==================== 组1：认证与空数据 ====================


class TestAuthAndEmpty:
    """认证拒绝 + 空数据返回。"""

    def test_no_token_returns_401(self, db_session):
        """无 token（未覆盖 get_current_user）→ 401。"""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        # 注意：不覆盖 get_current_user，让其真实执行 → 无 token 抛 401
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post("/api/v1/torrents/duplicates", json={})
        assert r.status_code == 401

    def test_empty_db_returns_zero(self, client):
        """空 DB → code='200', total=0, list=[]。"""
        r = client.post("/api/v1/torrents/duplicates", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0
        assert body["data"]["list"] == []


# ==================== 组2：核心重复检测 ====================


class TestDuplicateDetection:
    """HAVING count>=2 / 唯一 hash / dr 过滤。"""

    def test_duplicate_hash_across_downloaders(self, client, db_session):
        """同 hash 跨 2 个 downloader → total=2（记录数口径）。"""
        make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A", hash_="aaa", name="t1")
        make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B", hash_="aaa", name="t2")

        r = client.post("/api/v1/torrents/duplicates", json={})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 2
        assert len(body["data"]["list"]) == 2

    def test_unique_hash_not_returned(self, client, db_session):
        """仅出现 1 次的 hash → 不在结果中（HAVING count>=2）。"""
        # 唯一 hash（只 1 条）
        make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A", hash_="unique1", name="t1")
        # 重复 hash（2 条）
        make_torrent(db_session, info_id="i2", downloader_id="dl-a", downloader_name="A", hash_="dup", name="t2")
        make_torrent(db_session, info_id="i3", downloader_id="dl-b", downloader_name="B", hash_="dup", name="t3")

        r = client.post("/api/v1/torrents/duplicates", json={})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 2  # 只有 dup 的 2 条
        hashes = [item["hash"] for item in body["data"]["list"]]
        assert "unique1" not in hashes
        assert all(h == "dup" for h in hashes)

    def test_deleted_record_filtered(self, client, db_session):
        """dr=1 的重复记录被排除（base_conditions dr==0）。"""
        make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A", hash_="dup", name="t1", dr=0)
        make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B", hash_="dup", name="t2", dr=0)
        # 第 3 条 dr=1（已删除），跨 downloader 所以不受唯一索引约束
        make_torrent(db_session, info_id="i3", downloader_id="dl-c", downloader_name="C", hash_="dup", name="t3", dr=1)

        r = client.post("/api/v1/torrents/duplicates", json={})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 2  # dr=1 的不计入


# ==================== 组3：分页 ====================


class TestPagination:
    """分页（pageSize / 超范围）。"""

    def test_pagination_page_size(self, client, db_session):
        """3 个 hash × 2 条 = 6 条，pageSize=2 → 第1页 list 2 条，total=6。"""
        for idx, h in enumerate(["h1", "h2", "h3"]):
            make_torrent(
                db_session, info_id=f"a{idx}", downloader_id="dl-a", downloader_name="A", hash_=h, name=f"t{idx}"
            )
            make_torrent(
                db_session, info_id=f"b{idx}", downloader_id="dl-b", downloader_name="B", hash_=h, name=f"t{idx}"
            )

        r = client.post("/api/v1/torrents/duplicates", json={"page": 1, "pageSize": 2})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 6
        assert len(body["data"]["list"]) == 2
        assert body["data"]["page"] == 1
        assert body["data"]["pageSize"] == 2

    def test_pagination_out_of_range(self, client, db_session):
        """超范围 page → list=[] 但 total 正确。"""
        make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A", hash_="h1", name="t1")
        make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B", hash_="h1", name="t2")

        r = client.post("/api/v1/torrents/duplicates", json={"page": 99, "pageSize": 20})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 2
        assert body["data"]["list"] == []


# ==================== 组4：参数验证 422 ====================


class TestParamValidation:
    """pydantic 约束验证（page>=1 / pageSize<=200）。"""

    def test_page_zero_returns_422(self, client):
        """page=0 → 422（ge=1）。"""
        r = client.post("/api/v1/torrents/duplicates", json={"page": 0, "pageSize": 20})
        assert r.status_code == 422

    def test_page_size_over_limit_returns_422(self, client):
        """pageSize=201 → 422（le=200）。"""
        r = client.post("/api/v1/torrents/duplicates", json={"page": 1, "pageSize": 201})
        assert r.status_code == 422


# ==================== 组5：空列表 panic 防护 ====================


class TestEmptyListPanicGuard:
    """空列表 panic 防护（锚定 commit 0622d53）。

    downloader_id/status 为 "," 或 "" 时，split 后过滤空白得空列表，不应再加 IN() 条件。
    断言 code=='200'（而非 HTTP 200）才能证明 panic 未发生（异常会返回 code='500'）。
    """

    def test_empty_downloader_id_list_no_panic(self, client, db_session):
        """downloader_id=',' → 不报错，返回 code='200'。"""
        make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A", hash_="h1", name="t1")
        make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B", hash_="h1", name="t2")

        r = client.post("/api/v1/torrents/duplicates", json={"downloader_id": ","})
        body = r.json()
        assert body["code"] == "200", f"空列表应走 pass 不加条件，不应 panic: {body.get('msg')}"
        assert body["data"]["total"] == 2

    def test_empty_status_list_no_panic(self, client, db_session):
        """status=',' → 不报错，返回 code='200'。"""
        make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A", hash_="h1", name="t1")
        make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B", hash_="h1", name="t2")

        r = client.post("/api/v1/torrents/duplicates", json={"status": ","})
        body = r.json()
        assert body["code"] == "200", f"空列表应走 pass 不加条件，不应 panic: {body.get('msg')}"
        assert body["data"]["total"] == 2


# ==================== 组6：过滤条件 ====================


class TestFilters:
    """多选 / 单值 / min_size / hash 空值排除。"""

    def test_multi_select_downloader_filter(self, client, db_session):
        """downloader_id='dl-a,dl-b' 多选 → 只返回这两个 downloader 的。"""
        make_torrent(db_session, info_id="a1", downloader_id="dl-a", downloader_name="A", hash_="h1", name="t1")
        make_torrent(db_session, info_id="a2", downloader_id="dl-a", downloader_name="A", hash_="h2", name="t2")
        make_torrent(db_session, info_id="b1", downloader_id="dl-b", downloader_name="B", hash_="h1", name="t3")
        make_torrent(db_session, info_id="c1", downloader_id="dl-c", downloader_name="C", hash_="h3", name="t4")
        make_torrent(db_session, info_id="c2", downloader_id="dl-c", downloader_name="C", hash_="h4", name="t5")

        r = client.post("/api/v1/torrents/duplicates", json={"downloader_id": "dl-a,dl-b"})
        body = r.json()
        assert body["code"] == "200"
        dl_ids = {item["downloader_id"] for item in body["data"]["list"]}
        assert dl_ids <= {"dl-a", "dl-b"}, f"不应含 dl-c: {dl_ids}"

    def test_single_downloader_filter(self, client, db_session):
        """downloader_id='dl-a' 单值（== 分支）→ 过滤后只含 dl-a 的记录。

        注意：重复判定是「先过滤再 HAVING count>=2」。单值过滤 dl-a 后，
        子查询里只剩 dl-a 的种子；要让其仍满足 count>=2，需该 hash 在 dl-a 内有 ≥2 条。
        但唯一索引限制同 downloader 内 hash 唯一(dr=0)，所以构造：
        dl-a 有 h1(未删) + h1(已删 dr=1，不受唯一索引) → 但 dr=1 会被 base_conditions 过滤。
        因此单值过滤下「同 downloader 内重复」在正常数据下无法成立。
        正确验证方式：过滤 dl-a 后，h1 在 dl-a 出现 1 次，count<2，不应返回。
        此测试验证 == 分支正确生效（返回空，而非忽略过滤返回全部）。
        """
        make_torrent(db_session, info_id="a1", downloader_id="dl-a", downloader_name="A", hash_="h1", name="t1")
        make_torrent(db_session, info_id="b1", downloader_id="dl-b", downloader_name="B", hash_="h1", name="t2")

        # 过滤 dl-a：h1 在 dl-a 仅 1 条，过滤后 count=1 < 2，应返回空
        r = client.post("/api/v1/torrents/duplicates", json={"downloader_id": "dl-a"})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0, "单值 dl-a 过滤后 h1 仅 1 条，不满足 count>=2，应返回空"
        assert body["data"]["list"] == []

    def test_min_size_filter(self, client, db_session):
        """min_size=150 → 只返回 size>=150 的重复。"""
        # size=100 的重复对（应被过滤）
        make_torrent(
            db_session, info_id="a1", downloader_id="dl-a", downloader_name="A", hash_="small", name="t1", size=100
        )
        make_torrent(
            db_session, info_id="a2", downloader_id="dl-b", downloader_name="B", hash_="small", name="t2", size=100
        )
        # size=200 的重复对（应保留）
        make_torrent(
            db_session, info_id="a3", downloader_id="dl-a", downloader_name="A", hash_="big", name="t3", size=200
        )
        make_torrent(
            db_session, info_id="a4", downloader_id="dl-b", downloader_name="B", hash_="big", name="t4", size=200
        )

        r = client.post("/api/v1/torrents/duplicates", json={"min_size": 150})
        body = r.json()
        assert body["code"] == "200"
        hashes = {item["hash"] for item in body["data"]["list"]}
        assert hashes == {"big"}, f"应只剩 big（size>=150）: {hashes}"

    def test_empty_hash_excluded(self, client, db_session):
        """hash='' / hash=None 的记录被排除（base_conditions）。"""
        # 空字符串 hash（跨 downloader，绕过唯一索引）
        make_torrent(db_session, info_id="e1", downloader_id="dl-a", downloader_name="A", hash_="", name="empty")
        make_torrent(db_session, info_id="e2", downloader_id="dl-b", downloader_name="B", hash_="", name="empty")
        # 正常重复 hash
        make_torrent(db_session, info_id="n1", downloader_id="dl-a", downloader_name="A", hash_="valid", name="valid")
        make_torrent(db_session, info_id="n2", downloader_id="dl-b", downloader_name="B", hash_="valid", name="valid")

        r = client.post("/api/v1/torrents/duplicates", json={})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 2  # 只剩 valid 的 2 条
        hashes = {item["hash"] for item in body["data"]["list"]}
        assert "" not in hashes


# ==================== 组7：排序与 name_like ====================


class TestSortingAndNameLike:
    """排序（hash DESC）+ name_like 模糊匹配。"""

    def test_sorting_hash_desc(self, client, db_session):
        """多 hash，验证 list 按 hash DESC 顺序（added_date 至少差 1 秒避免精度丢失）。"""
        # 3 个不同 hash 的重复对，added_date 各差 1 秒
        for idx, h in enumerate(["hash_c", "hash_a", "hash_b"]):
            base_dt = datetime(2026, 1, 1, 12, 0, idx)  # 差 idx 秒
            make_torrent(
                db_session,
                info_id=f"a{idx}",
                downloader_id="dl-a",
                downloader_name="A",
                hash_=h,
                name=f"t{idx}",
                added_date=base_dt,
            )
            make_torrent(
                db_session,
                info_id=f"b{idx}",
                downloader_id="dl-b",
                downloader_name="B",
                hash_=h,
                name=f"t{idx}",
                added_date=base_dt,
            )

        r = client.post("/api/v1/torrents/duplicates", json={"page": 1, "pageSize": 20})
        body = r.json()
        assert body["code"] == "200"
        # total=6（3 hash × 2 条），按 hash DESC 分组排序：hash_c, hash_b, hash_a
        hashes = [item["hash"] for item in body["data"]["list"]]
        # 按 hash DESC：c 组应在前，a 组应在后
        assert hashes[0] == "hash_c", f"hash DESC 首条应为 hash_c: {hashes}"
        assert hashes[-1] == "hash_a", f"hash DESC 末条应为 hash_a: {hashes}"

    def test_name_like_filter(self, client, db_session):
        """name_like='keyword' → 只返回名称含该关键词的。"""
        make_torrent(
            db_session, info_id="a1", downloader_id="dl-a", downloader_name="A", hash_="h1", name="[keyword] movie"
        )
        make_torrent(
            db_session, info_id="a2", downloader_id="dl-b", downloader_name="B", hash_="h1", name="[keyword] movie"
        )
        # 不含关键词的重复
        make_torrent(
            db_session, info_id="a3", downloader_id="dl-a", downloader_name="A", hash_="h2", name="other thing"
        )
        make_torrent(
            db_session, info_id="a4", downloader_id="dl-b", downloader_name="B", hash_="h2", name="other thing"
        )

        r = client.post("/api/v1/torrents/duplicates", json={"name_like": "keyword"})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 2
        for item in body["data"]["list"]:
            assert "keyword" in item["name"]


# ==================== 组8：tracker 组装 ====================


class TestTrackerAssembly:
    """tracker 批量组装（N+1 防护）+ 默认 downloader_type。"""

    def test_tracker_assembled(self, client, db_session):
        """有 tracker 数据时，list 元素 tracker_info 字段被正确组装；无 BtDownloaders 时默认 qbittorrent 不报错。"""
        # 造重复种子
        make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A", hash_="h1", name="t1")
        make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B", hash_="h1", name="t2")

        # 为 i1 造 tracker（注意唯一索引：同种子同 tracker_url 唯一，dr=0）
        now = datetime(2026, 1, 1, 12, 0, 0)
        db_session.add(
            TrackerInfo(
                tracker_id="trk1",
                torrent_info_id="i1",
                tracker_name="tracker1",
                tracker_url="http://tracker.example.com/announce",
                last_announce_succeeded=2,  # qbittorrent 状态码
                last_announce_msg="ok",
                last_scrape_succeeded=2,
                create_time=now,
                create_by="tester",
                update_time=now,
                update_by="tester",
                dr=0,
            )
        )
        db_session.commit()

        r = client.post("/api/v1/torrents/duplicates", json={})
        body = r.json()
        assert body["code"] == "200", f"tracker 组装不应报错: {body.get('msg')}"
        assert body["data"]["total"] == 2

        # i1 应有 tracker_info 字段且非空
        i1_item = next(item for item in body["data"]["list"] if item["info_id"] == "i1")
        assert "tracker_info" in i1_item
        assert len(i1_item["tracker_info"]) >= 1
        trk = i1_item["tracker_info"][0]
        assert trk["tracker_url"] == "http://tracker.example.com/announce"
