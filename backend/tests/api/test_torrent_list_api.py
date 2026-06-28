# -*- coding: utf-8 -*-
"""
种子列表查询 GET /api/v1/torrents/getList 的 API 级回归测试

覆盖范围（29 个测试）：
- 认证拒绝 / 空数据
- 基础查询 + 软删除过滤（回收站 deleted_at + 逻辑删除 dr=1）
- status 复合条件（error 命中 has_tracker_error==True）
- 空多选 panic 防护（downloader_id="," / status=","）
- 过滤条件（多选/单值/LIKE/size区间/size单位/completed_date/tracker子查询/字段大小写契约）
- 排序（指定字段/默认/非法字段静默忽略）
- 分页（skip/limit / 超范围）
- 参数验证 422（skip/limit/sort_order）

与 duplicate_torrents 测试的关键差异（经独立审查核实）：
- GET + Query params（非 POST JSON body）
- 认证依赖 require_authenticated_user（非 get_current_user）
- list 元素字段是 camelCase（getList 无 response_model + endpoint 不 dump → Pydantic by_alias 输出）
- data 只有 total/list（无 page/pageSize）
- 分页用 skip/limit（非 page/pageSize）
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
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_db
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo

URL = "/api/v1/torrents/getList"


# ==================== Fixtures ====================

@pytest.fixture
def db_session():
    """内存 SQLite（StaticPool），建本接口用到的 3 张表。

    convert_to_vo_with_trackers 会逐条查 BtDownloaders 取 downloader_type
    （缺失走默认 qbittorrent，不报错），故必须建 BtDownloaders 表。
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
    """独立 FastAPI app，覆盖 get_db + require_authenticated_user。

    require_authenticated_user 是 async def，但用同步 lambda 覆盖也能工作
    （FastAPI dependency_overrides 不区分 async/sync）。endpoint 的 _user
    仅作守卫不访问字段，故 SimpleNamespace 内容不重要。
    """
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")

    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _make_torrent(
    db,
    *,
    info_id,
    downloader_id,
    hash_,
    name,
    downloader_name="dl",
    size=0,
    status="seeding",
    dr=0,
    added_date=None,
    completed_date=None,
    has_tracker_error=False,
    deleted_at=None,
):
    """构造真 ORM TorrentInfo（按位置传 24 参数）。

    注意：
    - has_tracker_error 是 NOT NULL 且 __init__ 未赋值，必须显式设。
    - deleted_at 用关键字传（第 25 个位置参数，避免与位置参数冲突）。
    """
    if added_date is None:
        added_date = datetime(2026, 1, 1, 12, 0, 0)
    t = TorrentInfo(
        info_id,            # id_
        downloader_id,      # downloader_id
        downloader_name,    # downloader_name
        None,               # torrent_id
        hash_,              # hash
        name,               # name
        "/path",            # save_path
        size,               # size
        status,             # status
        0.0,                # progress
        None,               # torrent_file
        added_date,         # added_date
        completed_date,     # completed_date
        "0",                # ratio
        "0",                # ratio_limit
        "",                 # tags
        "",                 # category
        "否",               # super_seeding
        True,               # enabled
        added_date,         # create_time
        "tester",           # create_by
        added_date,         # update_time
        "tester",           # update_by
        dr,                 # dr
    )
    t.has_tracker_error = has_tracker_error  # NOT NULL，__init__ 未赋值
    if deleted_at is not None:
        t.deleted_at = deleted_at
    db.add(t)
    db.commit()
    return t


def _info_ids(body):
    """从响应提取返回的 infoId 集合（camelCase 字段）。"""
    return {item["infoId"] for item in body["data"]["list"]}


# ==================== 组1：认证与空数据 ====================

class TestAuthAndEmpty:
    def test_no_token_returns_401(self, db_session):
        """未覆盖 require_authenticated_user 时 → 401。"""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get(URL)
        assert r.status_code == 401

    def test_empty_db_returns_empty_list(self, client):
        """空 DB → code='200', total=0, list=[]。"""
        r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0
        assert body["data"]["list"] == []


# ==================== 组2：基础查询 + 软删除过滤 ====================

class TestBasicAndSoftDelete:
    def test_basic_list_returns_all_active(self, client, db_session):
        """3 条正常种子 → total=3, 且返回的 infoId 集合精确匹配（强断言，防弱断言假通过）。"""
        for i in range(3):
            _make_torrent(db_session, info_id=f"i{i}", downloader_id=f"dl-{i}",
                          downloader_name=f"D{i}", hash_=f"h{i}", name=f"t{i}")
        r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 3
        assert len(body["data"]["list"]) == 3
        assert _info_ids(body) == {"i0", "i1", "i2"}

    def test_recycle_bin_excluded(self, client, db_session):
        """deleted_at 非空的记录被排除（方案B：不同 hash 避免唯一索引冲突）。

        2 条不同 hash 活跃 → total=2 → 把其中 1 条设 deleted_at → total=1（真验证过滤）。
        """
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="t1")
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="t2", deleted_at=datetime(2026, 1, 2, 12, 0, 0))

        r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 1  # deleted_at 非空的 i2 被排除
        assert _info_ids(body) == {"i1"}

    def test_dr1_excluded(self, client, db_session):
        """dr=1 的记录被排除（独立于 deleted_at 的过滤维度）。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="t1", dr=0)
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="t2", dr=1)  # 逻辑删除

        r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 1
        assert _info_ids(body) == {"i1"}


# ==================== 组3：status 复合条件 ====================

class TestStatusCompound:
    """status='error' 命中 status=='error' 或 has_tracker_error==True。"""

    def test_status_single_exact(self, client, db_session):
        """status=seeding → 只返回 status=seeding（断言 name 集合，不只 total）。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="seeding_one", status="seeding")
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="paused_one", status="paused")

        r = client.get(URL, params={"status": "seeding"})
        body = r.json()
        assert body["code"] == "200"
        assert _info_ids(body) == {"i1"}

    def test_status_error_compound(self, client, db_session):
        """核心：status=downloading + has_tracker_error=True 的种子，status=error 过滤命中它。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="normal_dl", status="downloading", has_tracker_error=False)
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="tracker_err", status="downloading", has_tracker_error=True)

        r = client.get(URL, params={"status": "error"})
        body = r.json()
        assert body["code"] == "200"
        # 只有 has_tracker_error=True 的 i2 命中（i1 status=downloading 不命中）
        assert _info_ids(body) == {"i2"}, "status=error 应命中 has_tracker_error=True 的种子"

    def test_status_multi_select(self, client, db_session):
        """status=error,seeding → 同时命中 error 复合 + seeding（断言具体命中集合）。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="hte_one", status="downloading", has_tracker_error=True)
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="seed_one", status="seeding")
        _make_torrent(db_session, info_id="i3", downloader_id="dl-c", downloader_name="C",
                      hash_="h3", name="paused_one", status="paused")

        r = client.get(URL, params={"status": "error,seeding"})
        body = r.json()
        assert body["code"] == "200"
        assert _info_ids(body) == {"i1", "i2"}  # i1(error复合) + i2(seeding)，i3 不命中


# ==================== 组4：空多选 panic 防护 ====================

class TestEmptyListPanicGuard:
    """downloader_id/status 为 ',' 时空列表防护，不加 IN() 条件。

    断言 code=='200'（异常会返回 code='500' 但 HTTP 仍 200）。
    """

    def test_empty_downloader_id_no_panic(self, client, db_session):
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="t1")
        r = client.get(URL, params={"downloader_id": ","})
        body = r.json()
        assert body["code"] == "200", f"空列表应走 pass 不加条件，不应 panic: {body.get('msg')}"
        assert body["data"]["total"] == 1

    def test_empty_status_no_panic(self, client, db_session):
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="t1")
        r = client.get(URL, params={"status": ","})
        body = r.json()
        assert body["code"] == "200", f"空列表应走 pass 不加条件，不应 panic: {body.get('msg')}"
        assert body["data"]["total"] == 1


# ==================== 组5：过滤条件 ====================

class TestFilters:
    def test_downloader_id_multi_select(self, client, db_session):
        """downloader_id='dl-a,dl-b' 多选 → 只含这两 downloader。"""
        _make_torrent(db_session, info_id="a1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="t1")
        _make_torrent(db_session, info_id="b1", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="t2")
        _make_torrent(db_session, info_id="c1", downloader_id="dl-c", downloader_name="C",
                      hash_="h3", name="t3")

        r = client.get(URL, params={"downloader_id": "dl-a,dl-b"})
        body = r.json()
        assert body["code"] == "200"
        ids = {item["downloaderId"] for item in body["data"]["list"]}
        assert ids == {"dl-a", "dl-b"}

    def test_downloader_id_single(self, client, db_session):
        """downloader_id='dl-a' 单值（== 分支）。"""
        _make_torrent(db_session, info_id="a1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="t1")
        _make_torrent(db_session, info_id="b1", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="t2")

        r = client.get(URL, params={"downloader_id": "dl-a"})
        body = r.json()
        assert body["code"] == "200"
        ids = {item["downloaderId"] for item in body["data"]["list"]}
        assert ids == {"dl-a"}

    def test_name_like_filter(self, client, db_session):
        """name_like='keyword' → 模糊匹配。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="[keyword] movie")
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="other thing")

        r = client.get(URL, params={"name_like": "keyword"})
        body = r.json()
        assert body["code"] == "200"
        assert _info_ids(body) == {"i1"}

    def test_downloader_name_like_filter(self, client, db_session):
        """downloader_name_like='Alpha' → 模糊匹配 downloader_name。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="Alpha",
                      hash_="h1", name="t1")
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="Beta",
                      hash_="h2", name="t2")

        r = client.get(URL, params={"downloader_name_like": "Alpha"})
        body = r.json()
        assert body["code"] == "200"
        assert _info_ids(body) == {"i1"}

    def test_size_range_filter(self, client, db_session):
        """size_min=150 + size_max=300 → 区间过滤。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="small", size=100)
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="mid", size=200)
        _make_torrent(db_session, info_id="i3", downloader_id="dl-c", downloader_name="C",
                      hash_="h3", name="big", size=400)

        r = client.get(URL, params={"size_min": "150", "size_max": "300"})
        body = r.json()
        assert body["code"] == "200"
        assert _info_ids(body) == {"i2"}

    def test_size_unit_parsing(self, client, db_session):
        """size_min='1K' → 1024 bytes（单位换算）。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="tiny", size=500)
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="kilo", size=1024)

        r = client.get(URL, params={"size_min": "1K"})
        body = r.json()
        assert body["code"] == "200"
        assert _info_ids(body) == {"i2"}, "1K 应换算为 1024，只命中 size=1024"

    def test_completed_date_range_filter(self, client, db_session):
        """completed_date_min/max 区间过滤。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="early",
                      completed_date=datetime(2026, 1, 5, 0, 0, 0))
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="late",
                      completed_date=datetime(2026, 3, 5, 0, 0, 0))

        r = client.get(URL, params={"completed_date_min": "2026-02-01",
                                    "completed_date_max": "2026-04-01"})
        body = r.json()
        assert body["code"] == "200"
        assert _info_ids(body) == {"i2"}

    def test_tracker_like_filter_hit(self, client, db_session):
        """tracker_like='example' → 子查询命中（关联键是 info_id）。"""
        t1 = _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                           hash_="h1", name="t1")
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="t2")

        now = datetime(2026, 1, 1, 12, 0, 0)
        db_session.add(TrackerInfo(
            tracker_id="trk1", torrent_info_id=t1.info_id, tracker_name="ex",
            tracker_url="http://tracker.example.com/announce",
            create_time=now, create_by="tester", update_time=now, update_by="tester", dr=0,
        ))
        db_session.commit()

        r = client.get(URL, params={"tracker_like": "example"})
        body = r.json()
        assert body["code"] == "200"
        assert _info_ids(body) == {"i1"}

    def test_tracker_like_empty_result_no_filter(self, client, db_session):
        """tracker_like 子查询空结果时 → 不加过滤（total 等于无 tracker 条件的 total）。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="t1")
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="t2")

        # 无 tracker 条件的 total
        r_all = client.get(URL)
        total_all = r_all.json()["data"]["total"]

        # tracker_like 不存在的关键字 → 子查询空 → 不加过滤 → total 应相等
        r = client.get(URL, params={"tracker_like": "zzznope"})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == total_all, "tracker 子查询空结果时不应过滤掉任何种子"


# ==================== 组6：字段大小写契约 ====================

class TestFieldCasingContract:
    """锚定 list 元素字段为 camelCase。

    机制：getList 端点无 response_model + endpoint 不手动 dump，
    Pydantic 默认 by_alias 序列化 TorrentInfoVO（alias_generator=alias_camel）。
    若有人给 getList 加 response_model 或在 endpoint 里 model_dump(by_alias=False)，
    此契约测试会捕获字段风格变化。
    """

    def test_list_elements_use_camel_case(self, client, db_session):
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="Alpha",
                      hash_="h1", name="test", added_date=datetime(2026, 1, 1, 12, 0, 0))
        r = client.get(URL)
        body = r.json()
        item = body["data"]["list"][0]
        # camelCase 字段必须存在
        assert "infoId" in item, "字段应为 camelCase infoId（非 info_id）"
        assert "downloaderName" in item
        assert "addedDate" in item
        # snake_case 字段不应存在
        assert "info_id" not in item
        assert "downloader_name" not in item
        assert item["infoId"] == "i1"
        assert item["downloaderName"] == "Alpha"


# ==================== 组7：排序 ====================

class TestSorting:
    def test_sort_by_name_asc(self, client, db_session):
        """sort_by=name + sort_order=asc → 按名称升序（数据全小写保证确定）。"""
        for nm in ["charlie", "alpha", "bravo"]:
            _make_torrent(db_session, info_id=nm, downloader_id=f"dl-{nm}",
                          downloader_name=nm, hash_=f"h_{nm}", name=nm)
        r = client.get(URL, params={"sort_by": "name", "sort_order": "asc"})
        body = r.json()
        names = [item["name"] for item in body["data"]["list"]]
        assert names == ["alpha", "bravo", "charlie"]

    def test_sort_by_name_desc(self, client, db_session):
        """sort_by=name + sort_order=desc → 按名称降序（显式锚定 desc 分支，区别于默认值）。"""
        for nm in ["charlie", "alpha", "bravo"]:
            _make_torrent(db_session, info_id=nm, downloader_id=f"dl-{nm}",
                          downloader_name=nm, hash_=f"h_{nm}", name=nm)
        r = client.get(URL, params={"sort_by": "name", "sort_order": "desc"})
        body = r.json()
        names = [item["name"] for item in body["data"]["list"]]
        assert names == ["charlie", "bravo", "alpha"], "显式 sort_order=desc 应降序"

    def test_default_sort_added_date_desc(self, client, db_session):
        """不传 sort_by → 默认 added_date 倒序（added_date 差异 ≥1月）。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="old", added_date=datetime(2026, 1, 1, 0, 0, 0))
        _make_torrent(db_session, info_id="i2", downloader_id="dl-b", downloader_name="B",
                      hash_="h2", name="new", added_date=datetime(2026, 6, 1, 0, 0, 0))
        r = client.get(URL)
        body = r.json()
        ids = [item["infoId"] for item in body["data"]["list"]]
        assert ids == ["i2", "i1"], "默认应按 added_date 倒序（新的在前）"

    def test_sort_by_invalid_field_ignored(self, client, db_session):
        """sort_by=nonexistent → code='200' 不报错（静默忽略，不断言顺序）。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="t1")
        r = client.get(URL, params={"sort_by": "nonexistent_field"})
        body = r.json()
        assert body["code"] == "200", "非法 sort_by 应静默忽略不报错"


# ==================== 组8：分页 ====================

class TestPagination:
    def test_skip_limit_pagination(self, client, db_session):
        """5 条，skip=2 + limit=2 → list 2 条, total=5，且返回的是跳过最新 2 条后的中间 2 条。

        数据 added_date 按天递增（i0=1月1日 ... i4=1月5日），默认排序 added_date desc。
        skip=2 跳过最新的 i4/i3，limit=2 返回 i2/i1（i0 被 limit 截断）。
        断言具体 infoId 集合，锁定 skip 真的生效（而非返回任意 2 条）。
        """
        for i in range(5):
            _make_torrent(db_session, info_id=f"i{i}", downloader_id=f"dl-{i}",
                          downloader_name=f"D{i}", hash_=f"h{i}", name=f"t{i}",
                          added_date=datetime(2026, 1, i + 1, 0, 0, 0))
        r = client.get(URL, params={"skip": 2, "limit": 2})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 5
        assert len(body["data"]["list"]) == 2
        # 锁定具体返回页（skip 跳过 i4/i3，limit 取 i2/i1）
        assert _info_ids(body) == {"i2", "i1"}

    def test_skip_beyond_range(self, client, db_session):
        """skip 超范围 → list=[] 但 total 正确。"""
        _make_torrent(db_session, info_id="i1", downloader_id="dl-a", downloader_name="A",
                      hash_="h1", name="t1")
        r = client.get(URL, params={"skip": 99, "limit": 20})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 1
        assert body["data"]["list"] == []


# ==================== 组9：参数验证 422 ====================

class TestParamValidation:
    def test_skip_negative_returns_422(self, client):
        r = client.get(URL, params={"skip": -1})
        assert r.status_code == 422

    def test_limit_over_max_returns_422(self, client):
        r = client.get(URL, params={"limit": 1001})
        assert r.status_code == 422

    def test_invalid_sort_order_returns_422(self, client):
        r = client.get(URL, params={"sort_order": "invalid"})
        assert r.status_code == 422
