# -*- coding: utf-8 -*-
"""
高级搜索完备回归测试。

设计目标：用真实内存 SQLite 系统覆盖各种查询组合的实际命中语义，
取代既有"仅 mock DB 验证 filter 被调用"的脆弱测试。

覆盖维度：
  A. 基础过滤真实命中（name/status/category/tags/size/ratio/date）
  B. 全 22 操作符 × 字段类型矩阵
  C. 条件组组合（单/多组 + between_group_logics + 降级）
  D. *_multi 死代码删除守卫（防回归）
  E. tracker_url / tracker_msg EXISTS 子查询
  F. 排序与分页
  G. 端到端 search_torrents 全链路（含 VO 序列化）
  H. NULL 安全边界（characterization）

种子数据集见 `_seed_torrents`，所有断言用精确集合断言（非 `in` 弱断言）。
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.models.advanced_search import (
    EnhancedAdvancedSearchRequest,
    SearchCondition,
    SearchGroup,
)
from app.database import Base
from app.downloader.models import BtDownloaders
from app.services.advanced_search import AdvancedSearchService, SearchQueryBuilder
from app.torrents.models import TorrentInfo, TrackerInfo
from tests.api.conftest import make_torrent

# ==================== 共享 fixture ====================


@pytest.fixture
def db_session():
    """真实内存 SQLite + StaticPool（单连接跨 query 共享），建 3 张关联表。

    复刻 test_advanced_search_batching.py 的范式：
      - StaticPool 必需，否则内存库跨 query 丢数据
      - TorrentInfo / TrackerInfo / BtDownloaders 三表是 search_torrents 全链路依赖
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [TorrentInfo.__table__, TrackerInfo.__table__, BtDownloaders.__table__]
    Base.metadata.create_all(bind=engine, tables=tables)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine, tables=list(reversed(tables)))
        engine.dispose()


def _seed_torrents(session):
    """插入覆盖所有边界场景的 6 颗种子。

    覆盖维度：
      - status: downloading/seeding/paused/error/completed（含 dr=1 软删除）
      - category: 电影/音乐/游戏/软件（t4=NULL 用于 is_null 测试）
      - tags: 逗号串列（"movie,4k"）/ 单值 / None（NULL 用于 is_null）
      - size: 0 / 100MB / 200MB / 500MB / 1GB / 5GB
      - ratio: 0.5/1.0/1.5/2.5/10.0/NULL（Float 列，v1.0.6.1 后天然数值比较）
      - ratio_limit: 10.0/2.0/1.5/0.0/NULL/NULL（差异化值，验证 ratio_limit filter+sort 的 TDD 区分力）
      - added_date: ISO 标准格式（validate_date_string 可解析）
      - completed_date: 部分有值（验证范围过滤 + NULL 排序）
      - tracker: 部分 active(dr=0) / 部分已删除(dr=1)
    """
    now_base = datetime(2026, 1, 1, 0, 0, 0)
    # 下载器配置（convert_to_vos_with_trackers 会查 BtDownloaders）
    session.add_all(
        [
            BtDownloaders(downloader_id="d1", nickname="qbit-主", downloader_type=0),
            BtDownloaders(downloader_id="d2", nickname="tr-辅", downloader_type=1),
        ]
    )
    session.commit()

    # t1: 电影 + 多标签 + ratio=2.5 + active tracker
    make_torrent(
        session,
        info_id="t1",
        downloader_id="d1",
        downloader_name="qbit-主",
        hash_="h1",
        name="Avatar 4K BluRay",
        size=100 * 1024 * 1024,  # 100MB
        status="downloading",
        ratio=2.5,
        ratio_limit=10.0,  # 双位数 ratio_limit（验证数值排序/过滤，避免字典序 bug）
        tags="movie,4k",
        category="电影",
        added_date=datetime(2026, 1, 15, 10, 0, 0),
    )
    session.add(
        TrackerInfo(
            tracker_id="tk1",
            torrent_info_id="t1",
            tracker_name="Tracker1",
            tracker_url="https://tracker1.example.com/announce",
            last_announce_msg="ok",
            last_scrape_msg="seeds=10",
            create_time=now_base,
            create_by="tester",
            update_time=now_base,
            update_by="tester",
            dr=0,
        )
    )

    # t2: 音乐 + 单标签 + ratio=0.5 + 已完成 + 已删除 tracker
    make_torrent(
        session,
        info_id="t2",
        downloader_id="d1",
        downloader_name="qbit-主",
        hash_="h2",
        name="Pink Floyd FLAC",
        size=500 * 1024 * 1024,  # 500MB
        status="seeding",
        ratio=0.5,
        ratio_limit=2.0,
        tags="flac",
        category="音乐",
        added_date=datetime(2026, 2, 20, 14, 30, 0),
        completed_date=datetime(2026, 3, 1, 0, 0, 0),
    )
    session.add(
        TrackerInfo(
            tracker_id="tk2",
            torrent_info_id="t2",
            tracker_name="Tracker2",
            tracker_url="https://tracker2.example.com/announce",
            last_announce_msg="working",
            last_scrape_msg="seeds=5",
            create_time=now_base,
            create_by="tester",
            update_time=now_base,
            update_by="tester",
            dr=1,  # 已删除 tracker，不应参与 tracker 搜索
        )
    )

    # t3: 电影 + 多标签 + ratio=10.0（关键：数值 10.0 > 2.5，验证 Float 列数值比较/排序）
    make_torrent(
        session,
        info_id="t3",
        downloader_id="d2",
        downloader_name="tr-辅",
        hash_="h3",
        name="Inception 1080p",
        size=1024 * 1024 * 1024,  # 1GB
        status="paused",
        ratio=10.0,
        ratio_limit=1.5,
        tags="movie,1080p",
        category="电影",
        added_date=datetime(2026, 3, 10, 9, 15, 0),
    )

    # t4: 游戏 + tags=NULL + ratio=NULL + 错误状态 + 含错误 msg 的 tracker
    make_torrent(
        session,
        info_id="t4",
        downloader_id="d2",
        downloader_name="tr-辅",
        hash_="h4",
        name="Witcher 3",
        size=5 * 1024 * 1024 * 1024,  # 5GB
        status="error",
        ratio=None,  # NULL
        ratio_limit=None,  # NULL（无限制）
        tags=None,  # NULL，验证 is_null
        category="游戏",
        added_date=datetime(2026, 4, 5, 16, 45, 0),
    )
    session.add(
        TrackerInfo(
            tracker_id="tk4",
            torrent_info_id="t4",
            tracker_name="Tracker4",
            tracker_url="https://tracker4.example.com/announce",
            last_announce_msg="connection timeout",
            last_scrape_msg="error: invalid",
            create_time=now_base,
            create_by="tester",
            update_time=now_base,
            update_by="tester",
            dr=0,
        )
    )

    # t5: 软件 + 空标签 + ratio=1.0 + 0 字节 + 已完成（NULL 排序测试中作为有值锚点）
    make_torrent(
        session,
        info_id="t5",
        downloader_id="d1",
        downloader_name="qbit-主",
        hash_="h5",
        name="VSCode Installer",
        size=0,
        status="completed",
        ratio=1.0,
        ratio_limit=0.0,
        tags="",
        category="软件",
        added_date=datetime(2026, 5, 25, 8, 0, 0),
        completed_date=datetime(2026, 5, 25, 20, 0, 0),
    )

    # t6: 电影 + ratio=1.5 + dr=1（软删除，验证 dr=0 自动过滤）
    make_torrent(
        session,
        info_id="t6",
        downloader_id="d1",
        downloader_name="qbit-主",
        hash_="h6",
        name="Deleted Movie",
        size=200 * 1024 * 1024,  # 200MB
        status="seeding",
        ratio=1.5,
        ratio_limit=None,  # 无限制
        tags="movie",
        category="电影",
        added_date=datetime(2026, 1, 1, 0, 0, 0),
        dr=1,
    )

    session.commit()
    return session


def _search(session, **kwargs):
    """便捷封装：构造 EnhancedAdvancedSearchRequest 并执行 search_torrents。"""
    request = EnhancedAdvancedSearchRequest(**kwargs)
    return AdvancedSearchService(session).search_torrents(request, user_id="tester")


def _info_ids(result):
    """从 search_torrents 返回中提取 info_id 集合（VO 用 camelCase 别名 infoId）。"""
    return {item["infoId"] for item in result["data"]}


# ==================== ratio 数值比较回归（v1.0.6.1：String 列已迁移为 Float）====================


class TestRatioNumericCompare:
    """验证 ratio Float 列的数值比较（v1.0.6.1 列类型迁移后）。

    历史 bug：TorrentInfo.ratio 原是 String 列，apply_basic_filters 和 _build_condition_filter
    都做字符串比较，导致 "10.0" < "2"（字典序），ratio_min=2 漏匹配 ratio="10.0" 的种子。
    v1.0.6.1 把 ratio/ratio_limit 列改为 Float，从根因上消除字典序 bug。

    本类锚定迁移后的正确数值语义，防止列类型被误改回 String。
    """

    def test_basic_filter_ratio_min_should_match_double_digit(self, db_session):
        """基础过滤：ratio_min=2 应同时命中 ratio=2.5 和 ratio=10.0。

        若列被改回 String：'10.0' < '2' 字典序 → t3 漏匹配，本测试失败。
        Float 列：2.5 >= 2 且 10.0 >= 2 → 返回 {'t1', 't3'}。
        """
        _seed_torrents(db_session)
        # 注意：t4 ratio=NULL 在 SQL 三值逻辑下被排除，符合预期
        # t5 ratio=1.0 < 2，不命中；t6 dr=1 已软删除，不命中
        result = _search(db_session, ratio_min=2, limit=100000)

        assert result["code"] == "200"
        assert result["total"] == 2, f"ratio_min=2 应命中 t1(2.5)+t3(10.0)，实际 {result['total']}"
        assert _info_ids(result) == {
            "t1",
            "t3",
        }, f"列若被改回 String：'10.0' < '2' 字典序导致 t3 漏匹配。实际 {_info_ids(result)}"

    def test_condition_group_ratio_gte_should_match_double_digit(self, db_session):
        """条件组：ratio >= 2 应同时命中 ratio=2.5 和 ratio=10.0。

        若列被改回 String：condition_groups 路径走字符串比较 → 漏 t3。
        Float 列：_build_condition_filter 直接数值比较（无需 cast）。
        """
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[SearchCondition(field="ratio", operator="gte", value=2)],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)

        assert result["code"] == "200"
        assert result["total"] == 2, f"条件组 ratio>=2 应命中 t1+t3，实际 {result['total']}"
        assert _info_ids(result) == {
            "t1",
            "t3",
        }, f"condition_groups 路径 ratio 字符串比较 bug。实际 {_info_ids(result)}"


# ==================== A. TestBasicFiltersRealDb ====================


class TestBasicFiltersRealDb:
    """基础过滤（apply_basic_filters）真实命中语义。

    种子数据集（dr=0 活跃种子，t6 dr=1 不应出现）：
      t1: Avatar 4K / 电影 / movie,4k / 100MB / 2.5 / 2026-01-15
      t2: Pink Floyd FLAC / 音乐 / flac / 500MB / 0.5 / 2026-02-20 / 完成 2026-03-01
      t3: Inception 1080p / 电影 / movie,1080p / 1GB / 10.0 / 2026-03-10
      t4: Witcher 3 / 游戏 / NULL / 5GB / NULL / 2026-04-05
      t5: VSCode / 软件 / "" / 0 / 1.0 / 2026-05-25 / 完成 2026-05-25
      t6: Deleted Movie / 电影 / movie / 200MB / 1.5 / dr=1（不应命中）
    """

    def test_filter_by_name_substring(self, db_session):
        """name 基础过滤用 contains（子串匹配）"""
        _seed_torrents(db_session)
        result = _search(db_session, name="Avatar", limit=100000)
        assert result["total"] == 1
        assert _info_ids(result) == {"t1"}

    def test_builder_and_reset_hide_active_deletion_rows(self, db_session):
        _seed_torrents(db_session)
        with patch(
            "app.services.advanced_search.build_active_deletion_exclusion",
            return_value=TorrentInfo.info_id != "t1",
        ):
            builder = SearchQueryBuilder(db_session)
            initial_ids = {row.info_id for row in builder.base_query.all()}
            reset_ids = {row.info_id for row in builder.reset().base_query.all()}

        assert "t1" not in initial_ids
        assert initial_ids == reset_ids == {"t2", "t3", "t4", "t5"}

    def test_filter_by_downloader_id(self, db_session):
        """downloader_id 精确匹配"""
        _seed_torrents(db_session)
        result = _search(db_session, downloader_id="d2", limit=100000)
        assert result["total"] == 2
        assert _info_ids(result) == {"t3", "t4"}

    def test_filter_by_downloader_name_substring(self, db_session):
        """downloader_name 用 contains（'tr' 命中 'tr-辅'）"""
        _seed_torrents(db_session)
        result = _search(db_session, downloader_name="tr", limit=100000)
        assert result["total"] == 2
        assert _info_ids(result) == {"t3", "t4"}

    def test_filter_by_status_exact(self, db_session):
        """status 用 ==（精确匹配，非子串）"""
        _seed_torrents(db_session)
        result = _search(db_session, status="error", limit=100000)
        assert result["total"] == 1
        assert _info_ids(result) == {"t4"}

    def test_filter_by_category_exact(self, db_session):
        """category 用 ==（精确匹配）"""
        _seed_torrents(db_session)
        result = _search(db_session, category="电影", limit=100000)
        assert result["total"] == 2  # t1 + t3（t6 dr=1 排除）
        assert _info_ids(result) == {"t1", "t3"}

    def test_filter_by_tags_substring(self, db_session):
        """tags 基础过滤用 contains（子串匹配逗号串列）"""
        _seed_torrents(db_session)
        result = _search(db_session, tags="flac", limit=100000)
        assert result["total"] == 1
        assert _info_ids(result) == {"t2"}

    def test_filter_by_size_min_with_unit(self, db_session):
        """size_min='1GB' 单位转换 → size >= 1GB 命中 t3(1GB) + t4(5GB)"""
        _seed_torrents(db_session)
        result = _search(db_session, size_min="1GB", limit=100000)
        assert result["total"] == 2
        assert _info_ids(result) == {"t3", "t4"}

    def test_filter_by_size_max_excludes_large(self, db_session):
        """size_max='200MB' 命中 t1(100MB)/t5(0)/t6(200MB 但 dr=1 排除) → t1+t5"""
        _seed_torrents(db_session)
        result = _search(db_session, size_max="200MB", limit=100000)
        assert result["total"] == 2
        assert _info_ids(result) == {"t1", "t5"}

    def test_filter_by_ratio_min_numeric_compare(self, db_session):
        """ratio_min=2 数值比较（验证修复）：命中 ratio>=2 的 t1(2.5)+t3(10.0)"""
        _seed_torrents(db_session)
        result = _search(db_session, ratio_min=2, limit=100000)
        assert result["total"] == 2
        assert _info_ids(result) == {"t1", "t3"}

    def test_filter_by_ratio_max_numeric_compare(self, db_session):
        """ratio_max=1.5 数值比较：命中 ratio<=1.5 的 t2(0.5)+t5(1.0)；t4(NULL) 被 SQL NULL 三值逻辑排除"""
        _seed_torrents(db_session)
        result = _search(db_session, ratio_max=1.5, limit=100000)
        assert result["total"] == 2
        assert _info_ids(result) == {"t2", "t5"}

    def test_filter_by_ratio_range_inclusive_both(self, db_session):
        """ratio_min + ratio_max 同时生效：[1, 3] 命中 t1(2.5)+t5(1.0)；t2(0.5)<1 排除"""
        _seed_torrents(db_session)
        result = _search(db_session, ratio_min=1, ratio_max=3, limit=100000)
        # t1(2.5)+t5(1.0)；t2(0.5)<1 排除；t3(10.0)>3 排除；t4(NULL) SQL 三值逻辑排除
        assert result["total"] == 2
        assert _info_ids(result) == {"t1", "t5"}

    def test_filter_by_ratio_null_excluded_by_max(self, db_session):
        """ratio=NULL 的 t4 在 ratio_max=999 下不应被误命中（CAST(NULL AS FLOAT) <= 999 → NULL → 排除）"""
        _seed_torrents(db_session)
        result = _search(db_session, ratio_max=999, limit=100000)
        # t1(2.5)+t2(0.5)+t3(10.0)+t5(1.0)，t4(NULL) 被 SQL NULL 语义排除
        assert result["total"] == 4
        assert _info_ids(result) == {"t1", "t2", "t3", "t5"}

    def test_filter_by_added_date_range(self, db_session):
        """added_date_min + added_date_max 范围过滤"""
        _seed_torrents(db_session)
        result = _search(db_session, added_date_min="2026-02-01", added_date_max="2026-03-31", limit=100000)
        # t2(02-20) + t3(03-10)；t1(01-15) 在 min 之前；t4(04-05)/t5(05-25) 在 max 之后
        assert result["total"] == 2
        assert _info_ids(result) == {"t2", "t3"}

    def test_filter_by_added_date_max_includes_full_day(self, db_session):
        """added_date_max='2026-01-15' 应补到 23:59:59，命中 t1(01-15 10:00)"""
        _seed_torrents(db_session)
        result = _search(db_session, added_date_max="2026-01-15", limit=100000)
        # t1(01-15 10:00)+t6(01-01 但 dr=1 排除)→ t1
        assert result["total"] == 1
        assert _info_ids(result) == {"t1"}

    def test_filter_by_completed_date_range(self, db_session):
        """completed_date 范围：t2 完成 03-01，t5 完成 05-25"""
        _seed_torrents(db_session)
        result = _search(db_session, completed_date_min="2026-03-01", completed_date_max="2026-03-31", limit=100000)
        assert result["total"] == 1
        assert _info_ids(result) == {"t2"}

    def test_multiple_basic_filters_combined_and(self, db_session):
        """多个基础过滤 AND 组合：downloader_id=d1 + status=seeding → t2（t6 dr=1 排除）"""
        _seed_torrents(db_session)
        result = _search(db_session, downloader_id="d1", status="seeding", limit=100000)
        assert result["total"] == 1
        assert _info_ids(result) == {"t2"}

    def test_soft_deleted_torrents_excluded(self, db_session):
        """dr=1 的 t6 在所有基础查询中都不应出现（base_query 已 filter dr=0）"""
        _seed_torrents(db_session)
        result = _search(db_session, category="电影", limit=100000)
        # t1+t3(电影,dr=0)，t6(电影,dr=1) 排除
        assert "t6" not in _info_ids(result)
        assert _info_ids(result) == {"t1", "t3"}


# ==================== B. TestOperatorMappingRealDb ====================


class TestOperatorMappingRealDb:
    """全 22 操作符 × 字段类型矩阵真实命中语义。

    覆盖：比较类(eq/ne/gt/gte/lt/lte)、字符串类(contains/not_contains/starts_with/ends_with/
    not_starts_with/not_ends_with)、集合类(in/not_in)、NULL类(is_null/is_not_null)、
    多值类(contains_any/contains_all/not_contains_any/not_contains_all)。
    """

    # --- 比较类操作符 ---

    def test_eq_on_size(self, db_session):
        """eq 对 size：size == 0 命中 t5"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="size", operator="eq", value=0))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t5"}

    def test_ne_on_status(self, db_session):
        """ne 对 status：status != 'error' 排除 t4"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="status", operator="ne", value="error"))
        )
        # t1/t2/t3/t5（t4 error 排除，t6 dr=1 排除）
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t2", "t3", "t5"}

    def test_gt_on_size_numeric(self, db_session):
        """gt 对 size：size > 1GB 命中 t4(5GB)"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="size", operator="gt", value="1GB"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t4"}

    def test_gte_on_size_inclusive(self, db_session):
        """gte 对 size：size >= 1GB 命中 t3(1GB)+t4(5GB)"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="size", operator="gte", value="1GB"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t3", "t4"}

    def test_lt_on_size(self, db_session):
        """lt 对 size：size < 500MB 命中 t1(100MB)+t5(0)+t6(200MB 但 dr=1)→ t1+t5"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="size", operator="lt", value="500MB"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t5"}

    def test_lte_on_added_date_inclusive(self, db_session):
        """lte 对 added_date：added_date <= 2026-01-15 命中 t1(01-15)+t6(01-01 但 dr=1)→ t1"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(field="added_date", operator="lte", value="2026-01-15 23:59:59")
            )
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1"}

    def test_gte_on_ratio_numeric_after_fix(self, db_session):
        """gte 对 ratio（条件组路径验证修复）：ratio >= 2 命中 t1(2.5)+t3(10.0)"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="ratio", operator="gte", value=2))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t3"}

    def test_gt_on_ratio_with_null_excluded(self, db_session):
        """gt 对 ratio：ratio > 0 命中 t1/t2/t3/t5；t4(NULL) 被 SQL NULL 三值逻辑排除"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="ratio", operator="gt", value=0))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t2", "t3", "t5"}

    # --- 字符串类操作符 ---

    def test_contains_on_name(self, db_session):
        """contains 对 name：'4K' 命中 t1(Avatar 4K)"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="name", operator="contains", value="4K"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1"}

    def test_not_contains_on_name(self, db_session):
        """not_contains 对 name：排除含 'Movie' 的行（t6 dr=1 已排除）"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="name", operator="not_contains", value="Movie"))
        )
        # t1/t2/t3/t4/t5（name 无 "Movie"），t6(Deleted Movie dr=1)
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t2", "t3", "t4", "t5"}

    def test_starts_with_on_name(self, db_session):
        """starts_with：'Avatar' 命中 t1"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="name", operator="starts_with", value="Avatar"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1"}

    def test_ends_with_on_name(self, db_session):
        """ends_with：'FLAC' 命中 t2(Pink Floyd FLAC)"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="name", operator="ends_with", value="FLAC"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t2"}

    def test_not_starts_with_on_name(self, db_session):
        """not_starts_with：排除以 'Avatar' 开头的（t1）"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="name", operator="not_starts_with", value="Avatar"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t2", "t3", "t4", "t5"}

    def test_not_ends_with_on_name(self, db_session):
        """not_ends_with：排除以 'FLAC' 结尾的（t2）"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="name", operator="not_ends_with", value="FLAC"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t3", "t4", "t5"}

    # --- 集合类操作符 ---

    def test_in_on_category(self, db_session):
        """in 对 category 单值列：['电影','游戏'] 命中 t1/t3(电影)+t4(游戏)"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="category", operator="in", value=["电影", "游戏"]))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t3", "t4"}

    def test_in_does_not_substring_match(self, db_session):
        """in 对 category 是精确匹配：['电'] 不命中任何（无 category 恰等于 '电'）"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="category", operator="in", value=["电"]))
        )
        assert {r.info_id for r in builder.base_query.all()} == set()

    def test_not_in_excludes_matching_and_null(self, db_session):
        """not_in 对 status：排除 downloading，但 NULL/不在列表的行也命中。

        注意：not_in 是 ~column.in_(list)，对非匹配行返回 True。
        t5(category=软件) 不在 ['电影'] → 命中；t4(游戏) → 命中；
        但若对 NULL 列用 not_in：NOT(NULL IN list) → NULL → WHERE 不匹配（被排除）。
        这里用 category（无 NULL），测 status 也类似。
        """
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(field="status", operator="not_in", value=["downloading", "error"])
            )
        )
        # 排除 t1(downloading)+t4(error)，剩 t2(seeding)+t3(paused)+t5(completed)
        assert {r.info_id for r in builder.base_query.all()} == {"t2", "t3", "t5"}

    # --- NULL 类操作符 ---

    def test_is_null_on_tags(self, db_session):
        """is_null 对 tags：命中 tags=NULL 的 t4。

        注意：SearchCondition.value 是 Pydantic 必填字段（Union 不含 None），
        但 OPERATOR_MAPPING 的 is_null lambda 忽略 value，故传占位字符串。
        """
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tags", operator="is_null", value="_ignored_"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t4"}

    def test_is_not_null_on_completed_date(self, db_session):
        """is_not_null 对 completed_date：t2(2026-03-01)+t5(2026-05-25)"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(field="completed_date", operator="is_not_null", value="_ignored_")
            )
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t2", "t5"}

    # --- 多值子串操作符（逗号串列 tags 专属） ---

    def test_contains_any_matches_substring_in_comma_tags(self, db_session):
        """contains_any 对 tags 逗号串列：['movie'] 命中 t1(movie,4k)+t3(movie,1080p)"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tags", operator="contains_any", value=["movie"]))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t3"}

    def test_contains_any_multiple_values_or_semantics(self, db_session):
        """contains_any(['flac','4k']) OR 语义：t1(含4k)+t2(含flac)"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(field="tags", operator="contains_any", value=["flac", "4k"])
            )
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t2"}

    def test_contains_all_requires_every_value(self, db_session):
        """contains_all(['movie','4k']) AND 语义：仅 t1 同时含两者"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(field="tags", operator="contains_all", value=["movie", "4k"])
            )
        )
        # t1(movie,4k) 含两者；t3(movie,1080p) 不含 4k
        assert {r.info_id for r in builder.base_query.all()} == {"t1"}

    def test_not_contains_any_excludes_matching(self, db_session):
        """not_contains_any(['movie'])：排除含 movie 的 t1/t3；t4(NULL) 被 SQL NULL 语义排除"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tags", operator="not_contains_any", value=["movie"]))
        )
        # t2(flac) 不含 movie 命中；t1/t3 含 movie 排除；t4(NULL) NOT(NULL LIKE)→NULL 排除；t5("") 不含 movie 命中
        assert {r.info_id for r in builder.base_query.all()} == {"t2", "t5"}

    def test_not_contains_all_excludes_rows_matching_all(self, db_session):
        """not_contains_all(['movie','4k'])：排除同时含两者的（t1）"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(field="tags", operator="not_contains_all", value=["movie", "4k"])
            )
        )
        # NOT(tags LIKE movie AND tags LIKE 4k)：t1 同时含两者被排除
        assert {r.info_id for r in builder.base_query.all()} == {"t2", "t3", "t5"}

    def test_contains_any_with_comma_string_value_fallback(self, db_session):
        """contains_any 收到逗号串 value（历史形态）→ _normalize_multi_value 拆分"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tags", operator="contains_any", value="movie,flac"))
        )
        # movie 命中 t1/t3，flac 命中 t2
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t2", "t3"}

    # --- 边界：未知字段/非法值必须拒绝 ---

    def test_unknown_field_rejected(self, db_session):
        """未知 field 不能被静默丢弃，否则会扩大结果集。"""
        with pytest.raises(ValueError, match="unknown search field"):
            SearchCondition(field="foobar", operator="eq", value="x")

    def test_size_gt_invalid_string_rejected(self, db_session):
        """非法大小值必须拒绝，不能丢弃条件后返回未过滤数据。"""
        with pytest.raises(ValueError, match="invalid size value"):
            SearchCondition(field="size", operator="gt", value="abc")


# ==================== C. TestConditionGroupsRealDb ====================


class TestConditionGroupsRealDb:
    """条件组组合逻辑（apply_condition_groups）真实命中语义。"""

    def test_single_and_group(self, db_session):
        """单 AND 组：name contains 'Movie' AND status='error' → 空（无种子同时满足）"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(field="name", operator="contains", value="Movie"),
                SearchCondition(field="status", operator="eq", value="error"),
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        # name 含 Movie 的只有 t6(Deleted Movie)，但 dr=1 排除；status=error 是 t4 但 name 不含 Movie
        assert result["total"] == 0

    def test_single_or_group(self, db_session):
        """单 OR 组：status='error' OR status='paused' → t3(paused)+t4(error)"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="OR",
            conditions=[
                SearchCondition(field="status", operator="eq", value="error"),
                SearchCondition(field="status", operator="eq", value="paused"),
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert _info_ids(result) == {"t3", "t4"}

    def test_multiple_groups_explicit_and(self, db_session):
        """多组必须显式声明组间 AND，且按 AND 连接。"""
        _seed_torrents(db_session)
        groups = [
            SearchGroup(
                logic="AND",
                conditions=[SearchCondition(field="category", operator="eq", value="电影")],
            ),
            SearchGroup(
                logic="AND",
                conditions=[SearchCondition(field="downloader_id", operator="eq", value="d2")],
            ),
        ]
        result = _search(
            db_session,
            condition_groups=groups,
            between_group_logics=["AND"],
            limit=100000,
        )
        # 电影 ∩ d2 → t3（t1 是电影+d1，t4 是 d2+游戏）
        assert _info_ids(result) == {"t3"}

    def test_multiple_groups_with_between_group_logics_mixed(self, db_session):
        """多组 + between_group_logics=[OR]：组1 OR 组2"""
        _seed_torrents(db_session)
        groups = [
            SearchGroup(
                logic="AND",
                conditions=[SearchCondition(field="category", operator="eq", value="音乐")],
            ),
            SearchGroup(
                logic="AND",
                conditions=[SearchCondition(field="category", operator="eq", value="游戏")],
            ),
        ]
        result = _search(db_session, condition_groups=groups, between_group_logics=["OR"], limit=100000)
        # 音乐(t2) OR 游戏(t4)
        assert _info_ids(result) == {"t2", "t4"}

    def test_between_group_logics_length_insufficient_rejected(self, db_session):
        """组间逻辑数量不足必须拒绝，不能猜测为 AND。"""
        groups = [
            SearchGroup(
                logic="AND",
                conditions=[SearchCondition(field="category", operator="eq", value="音乐")],
            ),
            SearchGroup(
                logic="AND",
                conditions=[SearchCondition(field="category", operator="eq", value="游戏")],
            ),
        ]
        with pytest.raises(ValueError, match="between_group_logics length"):
            EnhancedAdvancedSearchRequest(
                condition_groups=groups,
                between_group_logics=[],
                limit=100000,
            )

    def test_invalid_condition_in_group_rejected(self, db_session):
        """组内任一未知字段都必须使整个请求失败。"""
        with pytest.raises(ValueError, match="unknown search field"):
            SearchGroup.model_validate(
                {
                    "logic": "AND",
                    "conditions": [
                        {"field": "foobar", "operator": "eq", "value": "x"},
                        {"field": "status", "operator": "eq", "value": "error"},
                    ],
                }
            )

    def test_or_group_all_invalid_conditions_rejected(self, db_session):
        """全非法 OR 组不能退化成“无过滤”。"""
        with pytest.raises(ValueError, match="unknown search field"):
            SearchGroup.model_validate(
                {
                    "logic": "OR",
                    "conditions": [
                        {"field": "foobar1", "operator": "eq", "value": "x"},
                        {"field": "foobar2", "operator": "eq", "value": "y"},
                    ],
                }
            )

    def test_dict_format_group_compatible(self, db_session):
        """dict 格式条件组（search-preview 路径）兼容"""
        _seed_torrents(db_session)
        # 注意：condition_groups 直接赋值 dict 而非 SearchGroup，绕过 Pydantic 校验
        # 这里通过构造 SearchGroup 但内部 condition 用 dict 验证 _build_condition_filter 双路径
        request = EnhancedAdvancedSearchRequest(limit=100000)
        request.condition_groups = [
            {
                "logic": "AND",
                "conditions": [{"field": "status", "operator": "eq", "value": "error"}],
            }
        ]
        result = AdvancedSearchService(db_session).search_torrents(request, user_id="tester")
        assert _info_ids(result) == {"t4"}

    def test_empty_condition_groups_no_filter(self, db_session):
        """空 condition_groups 列表 → 无高级过滤 → 返回全部活跃种子"""
        _seed_torrents(db_session)
        result = _search(db_session, condition_groups=[], limit=100000)
        assert result["total"] == 5  # 5 颗活跃（t6 dr=1 排除）

    def test_between_group_logics_three_groups_alternating(self, db_session):
        """3 组 + between_group_logics=[OR, AND]：(组1 OR 组2) AND 组3"""
        _seed_torrents(db_session)
        groups = [
            SearchGroup(
                logic="AND",
                conditions=[SearchCondition(field="category", operator="eq", value="电影")],
            ),
            SearchGroup(
                logic="AND",
                conditions=[SearchCondition(field="category", operator="eq", value="音乐")],
            ),
            SearchGroup(
                logic="AND",
                conditions=[SearchCondition(field="downloader_id", operator="eq", value="d1")],
            ),
        ]
        result = _search(
            db_session,
            condition_groups=groups,
            between_group_logics=["OR", "AND"],
            limit=100000,
        )
        # (电影 OR 音乐) AND d1
        # 电影={t1,t3}, 音乐={t2}, OR={t1,t2,t3}; d1={t1,t2,t5}; AND={t1,t2}
        assert _info_ids(result) == {"t1", "t2"}


# ==================== D. TestMultiSelectRemovedGuard ====================


class TestMultiSelectRemovedGuard:
    """防止 *_multi 死代码路径复活的守卫测试。

    背景：apply_multi_select_conditions 及 EnhancedAdvancedSearchRequest 的 *_multi 字段
    是前端从不调用的死代码路径（前端 multiSelect 字段统一走 condition_groups + contains_any）。
    v1.0.5.15 删除了这条路径，本类防止未来误用复活。
    """

    def test_enhanced_request_has_no_multi_fields(self):
        """EnhancedAdvancedSearchRequest 不再声明 *_multi 字段。

        Pydantic v2 默认允许 extra 字段（不报错但忽略），故守卫改为检查 model_fields。
        """
        multi_field_names = [name for name in EnhancedAdvancedSearchRequest.model_fields if name.endswith("_multi")]
        assert multi_field_names == [], f"不应再有 *_multi 字段，实际存在：{multi_field_names}"

    def test_apply_multi_select_conditions_method_removed(self):
        """SearchQueryBuilder 不再有 apply_multi_select_conditions 方法"""
        assert not hasattr(SearchQueryBuilder, "apply_multi_select_conditions")

    def test_multi_select_condition_class_removed(self):
        """app.api.models.advanced_search 不再导出 MultiSelectCondition"""
        import app.api.models.advanced_search as models

        assert not hasattr(models, "MultiSelectCondition")


# ==================== E. TestTrackerSubqueryRealDb ====================


class TestTrackerSubqueryRealDb:
    """tracker_url / tracker_msg EXISTS 子查询真实命中语义。

    种子 tracker 分布：
      t1: tk1 dr=0 url=tracker1 msg=ok/seeds=10
      t2: tk2 dr=1 url=tracker2（已删除，不参与匹配）
      t4: tk4 dr=0 url=tracker4 msg='connection timeout'/'error: invalid'
      t3/t5/t6: 无 tracker
    """

    def test_tracker_url_contains(self, db_session):
        """tracker_url contains 'tracker1' → 命中含该 tracker 的种子（t1）"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tracker_url", operator="contains", value="tracker1"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1"}

    def test_tracker_url_contains_matches_multiple_torrents(self, db_session):
        """tracker_url contains 'tracker' → t1(tk1)+t4(tk4)；t2 tk2 dr=1 排除"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tracker_url", operator="contains", value="tracker"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t4"}

    def test_tracker_url_not_contains(self, db_session):
        """tracker_url not_contains 'tracker4' → 排除 t4；但需注意 EXISTS 语义"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(field="tracker_url", operator="not_contains", value="tracker4")
            )
        )
        # not_contains 走 _build_text_filter：OR col IS NULL OR (IS NOT NULL AND NOT LIKE)
        # EXISTS 语义：种子存在 dr=0 tracker 且其 url not_contains 'tracker4'
        # t1(tk1 url not_contains tracker4) → 命中；t4(tk4 url 含 tracker4) → 不命中
        # 无 tracker 的种子（t2/t3/t5）：EXISTS 为假 → 不命中
        assert {r.info_id for r in builder.base_query.all()} == {"t1"}

    def test_tracker_url_starts_with(self, db_session):
        """tracker_url starts_with 'https://tracker1' → t1"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(field="tracker_url", operator="starts_with", value="https://tracker1")
            )
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t1"}

    def test_tracker_msg_matches_announce_or_scrape(self, db_session):
        """tracker_msg contains 'timeout' → 匹配 announce_msg 或 scrape_msg；t4 命中"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tracker_msg", operator="contains", value="timeout"))
        )
        # t4 last_announce_msg='connection timeout' 命中
        assert {r.info_id for r in builder.base_query.all()} == {"t4"}

    def test_tracker_msg_matches_scrape_field(self, db_session):
        """tracker_msg contains 'invalid' → 命中 t4(last_scrape_msg='error: invalid')"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tracker_msg", operator="contains", value="invalid"))
        )
        assert {r.info_id for r in builder.base_query.all()} == {"t4"}

    def test_tracker_url_uses_real_regex_semantics(self, db_session):
        """tracker_url regex honors anchors and character classes."""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(
                    field="tracker_url",
                    operator="regex",
                    value={
                        "pattern": r"^https://tracker[14]\.example\.com/announce$",
                        "caseSensitive": True,
                    },
                )
            )
        )
        assert {row.info_id for row in builder.base_query.all()} == {"t1", "t4"}

    def test_tracker_msg_uses_real_regex_semantics(self, db_session):
        """tracker_msg regex is evaluated against announce and scrape messages."""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(
                    field="tracker_msg",
                    operator="regex",
                    value={
                        "pattern": r"^(connection\s+timeout|error:\s+invalid)$",
                        "caseSensitive": True,
                    },
                )
            )
        )
        assert {row.info_id for row in builder.base_query.all()} == {"t4"}

    def test_deleted_tracker_excluded(self, db_session):
        """dr=1 的 tracker 不参与匹配：t2 的 tk2 dr=1，搜 tracker2 不应命中 t2"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tracker_url", operator="contains", value="tracker2"))
        )
        # t2 的 tracker dr=1，被 EXISTS 子查询的 TrackerInfo.dr==0 排除
        assert {r.info_id for r in builder.base_query.all()} == set()

    def test_tracker_msg_eq_falls_back_to_contains(self, db_session):
        """tracker_msg 用 eq 操作符 → _build_text_filter fallback to contains（warning + contains）"""
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tracker_msg", operator="eq", value="ok"))
        )
        # eq 在 _build_text_filter 走 :446-447 直接 column == value（不走 contains fallback）
        # 但 tracker_msg 是 announce OR scrape 的组合，eq 对组合表达式不直接生效
        # 实际行为：announce_msg == 'ok' OR scrape_msg == 'ok' → t1(announce_msg='ok') 命中
        assert {r.info_id for r in builder.base_query.all()} == {"t1"}


# ==================== F. TestSortingAndPaginationRealDb ====================


class TestSortingAndPaginationRealDb:
    """排序与分页真实命中语义。

    注意：SQLite 对 NULL 列默认 NULL FIRST（ASC 时 NULL 排最前，DESC 时排最后）。
    本类排序测试对含 NULL 的列（ratio/completed_date）单独构造无 NULL 子集或显式处理 NULL 位置。
    """

    def test_sort_by_added_date_desc(self, db_session):
        """sort_by=added_date desc：t5(05-25) > t4(04-05) > t3(03-10) > t2(02-20) > t1(01-15)"""
        _seed_torrents(db_session)
        result = _search(db_session, sort_by="added_date", sort_order="desc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        assert ids == ["t5", "t4", "t3", "t2", "t1"]

    def test_sort_by_added_date_asc(self, db_session):
        """sort_by=added_date asc：t1(01-15) < t2(02-20) < t3(03-10) < t4(04-05) < t5(05-25)"""
        _seed_torrents(db_session)
        result = _search(db_session, sort_by="added_date", sort_order="asc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        assert ids == ["t1", "t2", "t3", "t4", "t5"]

    def test_sort_by_size_desc(self, db_session):
        """sort_by=size desc：t4(5GB) > t3(1GB) > t2(500MB) > t1(100MB) > t5(0)"""
        _seed_torrents(db_session)
        result = _search(db_session, sort_by="size", sort_order="desc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        assert ids == ["t4", "t3", "t2", "t1", "t5"]

    def test_sort_by_name_asc(self, db_session):
        """sort_by=name asc：按字典序"""
        _seed_torrents(db_session)
        result = _search(db_session, sort_by="name", sort_order="asc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        # Avatar < Inception < Pink Floyd < VSCode < Witcher
        assert ids == ["t1", "t3", "t2", "t5", "t4"]

    def test_sort_by_invalid_field_rejected(self, db_session):
        """无效 sort_by 必须明确失败，不能静默更改排序语义。"""
        with pytest.raises(ValueError, match="unknown sort field"):
            EnhancedAdvancedSearchRequest(
                sort_by="nonexistent_field",
                sort_order="desc",
                limit=100000,
            )

    def test_pagination_first_page(self, db_session):
        """分页第 1 页（limit=2）：返回 t5+t4（按 added_date desc）"""
        _seed_torrents(db_session)
        result = _search(db_session, page=1, limit=2, sort_by="added_date", sort_order="desc")
        assert result["total"] == 5  # total 是总数（不受分页影响）
        assert result["total_pages"] == 3  # (5+2-1)//2 = 3
        assert [item["infoId"] for item in result["data"]] == ["t5", "t4"]

    def test_pagination_third_page_partial(self, db_session):
        """分页第 3 页（limit=2）：只剩 t1"""
        _seed_torrents(db_session)
        result = _search(db_session, page=3, limit=2, sort_by="added_date", sort_order="desc")
        assert result["total"] == 5
        assert [item["infoId"] for item in result["data"]] == ["t1"]

    # ---------- v1.0.6.1 新增：ratio/ratio_limit 数值排序回归 ----------

    def test_sort_by_ratio_desc_numeric(self, db_session):
        """sort_by=ratio desc：Float 列数值排序 → [t3(10.0), t1(2.5), t6(1.5), t5(1.0), t2(0.5)]。

        历史 bug：ratio 原是 String 列，apply_sorting 直接 order_by(String 列) 走字典序，
        desc 返回 [t1(2.5), t6(1.5), t5(1.0), t2(0.5), t3(10.0)]（"2">"1">"0"）。
        v1.0.6.1 列改 Float 后排序自动正确。
        mutation：若列被改回 String → 本测试应失败。
        """
        _seed_torrents(db_session)
        # t6 dr=1 软删除自动排除；t4 ratio=NULL 在 SQLite desc 排末尾
        result = _search(db_session, sort_by="ratio", sort_order="desc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        # 非空 ratio 的种子按数值 desc：t3(10.0) > t1(2.5) > t5(1.0) > t2(0.5)；t4(NULL) 排末尾
        assert ids[:4] == ["t3", "t1", "t5", "t2"], f"Float 数值 desc 应为 t3,t1,t5,t2，实际 {ids}"

    def test_sort_by_ratio_asc_numeric(self, db_session):
        """sort_by=ratio asc：Float 列数值升序 → [t2(0.5), t5(1.0), t1(2.5), t3(10.0)]。"""
        _seed_torrents(db_session)
        result = _search(db_session, sort_by="ratio", sort_order="asc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        # SQLite asc 时 NULL（t4）排首位，其后数值升序（t6 软删除已排除，只剩 5 行）
        assert ids[1:5] == ["t2", "t5", "t1", "t3"], f"Float 数值 asc 应为 t2,t5,t1,t3，实际 {ids}"

    def test_sort_by_ratio_null_position_desc(self, db_session):
        """ratio=NULL 的 t4 在 desc 时排末尾（SQLite 三值逻辑）。"""
        _seed_torrents(db_session)
        result = _search(db_session, sort_by="ratio", sort_order="desc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        # t4 ratio=NULL 应在所有非 NULL 行之后
        assert ids[-1] == "t4", f"NULL 在 desc 应排末尾，实际末位 {ids[-1]}"

    def test_sort_by_ratio_limit_desc_numeric(self, db_session):
        """sort_by=ratio_limit desc：Float 列数值排序 → [t1(10.0), t2(2.0), t3(1.5), t5(0.0)]。

        历史 bug：ratio_limit 同样是 String 列，sort 路径无 cast → 字典序错误。
        v1.0.6.1 列改 Float 后排序自动正确。
        """
        _seed_torrents(db_session)
        result = _search(db_session, sort_by="ratio_limit", sort_order="desc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        # 非 NULL ratio_limit 按 desc：t1(10.0) > t2(2.0) > t3(1.5) > t5(0.0)
        # NULL（t4, t6）在 desc 时排末尾
        assert ids[:4] == ["t1", "t2", "t3", "t5"], f"ratio_limit 数值 desc 应为 t1,t2,t3,t5，实际 {ids}"

    def test_sort_by_ratio_limit_asc_numeric(self, db_session):
        """sort_by=ratio_limit asc：Float 列数值升序 → [t5(0.0), t3(1.5), t2(2.0), t1(10.0)]。"""
        _seed_torrents(db_session)
        result = _search(db_session, sort_by="ratio_limit", sort_order="asc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        # NULL（t4）排首位，其后数值升序（t6 软删除已排除，只剩 5 行）
        assert ids[1:5] == ["t5", "t3", "t2", "t1"], f"ratio_limit 数值 asc 应为 t5,t3,t2,t1，实际 {ids}"

    def test_sort_by_ratio_with_filter_combined(self, db_session):
        """组合：ratio_min=1 + sort_by=ratio desc → 命中 t3(10.0),t1(2.5),t5(1.0)，按数值降序。"""
        _seed_torrents(db_session)
        result = _search(db_session, ratio_min=1, sort_by="ratio", sort_order="desc", limit=100000)
        ids = [item["infoId"] for item in result["data"]]
        # t2(0.5)<1 排除；t4 NULL 排除；剩余 t3(10.0),t1(2.5),t5(1.0) 数值 desc
        assert ids == ["t3", "t1", "t5"], f"filter+sort 组合，实际 {ids}"


# ==================== G. TestEndToEndSearchTorrents ====================


class TestEndToEndSearchTorrents:
    """search_torrents 全链路：基础+条件组+排序+分页 + VO 序列化。"""

    def test_combined_filters_with_sorting_and_pagination(self, db_session):
        """综合：downloader_id=d1 + 条件组 + 排序 + 分页"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="OR",
            conditions=[
                SearchCondition(field="status", operator="eq", value="downloading"),
                SearchCondition(field="status", operator="eq", value="seeding"),
            ],
        )
        result = _search(
            db_session,
            downloader_id="d1",
            condition_groups=[group],
            sort_by="added_date",
            sort_order="desc",
            page=1,
            limit=10,
        )
        # d1 = {t1(downloading), t2(seeding), t5(completed)} ∩ (downloading OR seeding) = {t1, t2}
        # 按 added_date desc: t2(02-20) > t1(01-15)
        assert result["total"] == 2
        assert [item["infoId"] for item in result["data"]] == ["t2", "t1"]

    def test_vo_serialization_camel_case_and_tracker_info(self, db_session):
        """VO 序列化：camelCase 别名（infoId/trackerInfo）+ tracker 信息预加载"""
        _seed_torrents(db_session)
        result = _search(db_session, name="Avatar", limit=100000)
        assert result["total"] == 1
        item = result["data"][0]
        # camelCase 别名
        assert "infoId" in item
        assert item["infoId"] == "t1"
        assert item["name"] == "Avatar 4K BluRay"
        # tracker 信息（t1 有 tk1 dr=0）
        assert "trackerInfo" in item
        assert len(item["trackerInfo"]) == 1
        assert item["trackerInfo"][0]["tracker_url"] == "https://tracker1.example.com/announce"

    def test_empty_query_returns_all_active(self, db_session):
        """smoke：空查询返回所有 dr=0 活跃种子（5 颗，t6 dr=1 排除）"""
        _seed_torrents(db_session)
        result = _search(db_session, limit=100000)
        assert result["code"] == "200"
        assert result["total"] == 5
        assert _info_ids(result) == {"t1", "t2", "t3", "t4", "t5"}

    def test_no_match_returns_empty(self, db_session):
        """完全不匹配返回空 list + total=0（合并 smoke，验证不崩）"""
        _seed_torrents(db_session)
        result = _search(db_session, name="不存在的种子名称XYZ", limit=100000)
        assert result["code"] == "200"
        assert result["total"] == 0
        assert result["data"] == []

    def test_search_preview_dict_conditions_via_service(self, db_session):
        """search-preview 路径：dict 格式单 AND 条件组（不经 Pydantic 校验）"""
        _seed_torrents(db_session)
        # 模拟 search-preview 端点构造的请求（dict 格式 condition_groups）
        request = EnhancedAdvancedSearchRequest(limit=20, sort_by="added_time")
        request.condition_groups = [
            {
                "logic": "AND",
                "conditions": [
                    {"field": "category", "operator": "eq", "value": "电影"},
                    {"field": "downloader_id", "operator": "eq", "value": "d2"},
                ],
            }
        ]
        result = AdvancedSearchService(db_session).search_torrents(request, user_id="tester")
        # 电影 ∩ d2 = {t3}
        assert _info_ids(result) == {"t3"}


# ==================== H. TestNullSafetyBoundary ====================


class TestNullSafetyBoundary:
    """NULL 安全边界（characterization test，钉死当前行为）。

    本类不是 xfail 对照，而是独立断言两条 NULL 处理路径的当前行为：
      - 顶层 OPERATOR_MAPPING 的字符串操作符（作用于 name/tags/category 等）
      - _build_text_filter（仅服务 tracker_url/tracker_msg 子查询）

    两条路径 NULL 行为不同是 SQL 实现必需的安全处理（避免 None.contains 报错），
    非 bug。本类钉死现状防回归，标注"当前行为"。
    """

    def test_top_level_not_contains_on_null_tags_excludes_row(self, db_session):
        """顶层 not_contains 对 NULL 列：t4(tags=NULL) 在 not_contains('xx') 下被排除。

        当前行为：~column.contains('xx') 生成 NOT(tags LIKE '%xx%')，
        SQL 三值逻辑下 NOT(NULL LIKE) → NULL → WHERE 视为不匹配 → 行被排除。
        这与 _build_text_filter 的 not_contains（NULL 视为匹配）行为相反。
        """
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tags", operator="not_contains", value="xx"))
        )
        # t1/t2/t3/t5（tags 不含 xx，not_contains 为 True）；t4(NULL) 被排除
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t2", "t3", "t5"}

    def test_tracker_not_contains_null_msg_excludes_via_exists(self, db_session):
        """tracker 子查询 _build_text_filter 的 not_contains 对 NULL tracker msg 的行为。

        当前行为：_build_text_filter 的 not_contains 用
          OR col IS NULL OR (IS NOT NULL AND NOT LIKE)
        但在 EXISTS 子查询上下文，种子的 tracker 必须存在（dr=0）。
        t3/t5 无 tracker → EXISTS 为假 → 不命中（无论 msg NULL 与否）。
        """
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(
                SearchCondition(field="tracker_msg", operator="not_contains", value="nonexistent_text")
            )
        )
        # 有 dr=0 tracker 且 msg not_contains 'nonexistent_text'：
        # t1(msg=ok/seeds=10 不含 nonexistent_text) → 命中
        # t4(msg 含 timeout/error 不含 nonexistent_text) → 命中
        # t2(tk2 dr=1 排除)、t3/t5(无 tracker) → 不命中
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t4"}

    def test_top_level_contains_on_null_excludes_row(self, db_session):
        """顶层 contains 对 NULL 列：t4(tags=NULL) 在 contains('movie') 下不命中。

        当前行为：column.contains('movie') 生成 tags LIKE '%movie%'，
        NULL LIKE → NULL → WHERE 不匹配 → 行被排除。这是 SQL 标准三值逻辑。
        """
        _seed_torrents(db_session)
        builder = SearchQueryBuilder(db_session)
        builder.base_query = builder.base_query.filter(
            builder._build_condition_filter(SearchCondition(field="tags", operator="contains", value="movie"))
        )
        # t1(movie,4k)+t3(movie,1080p) 含 movie；t4(NULL) 排除；t2(flac)+t5("") 不含
        assert {r.info_id for r in builder.base_query.all()} == {"t1", "t3"}


# ==================== I. v1.0.6.1 ratio_limit filter 回归（红队漏洞 #1）====================


class TestRatioLimitFilterRegression:
    """验证 ratio_limit 字段在 condition_groups 路径下的数值比较。

    红队漏洞 #1：v1.0.5.15 的 cast 修复只点名 field=="ratio"，遗漏 ratio_limit。
    ratio_limit 列与 ratio 同类型（String）、同前端入口（number 类型，gt/gte/lt/lte），
    但 cast 修复未覆盖。v1.0.6.1 把 ratio_limit 列改为 Float，从根因上消除 bug。
    """

    def test_ratio_limit_gte_should_match_double_digit(self, db_session):
        """ratio_limit >= 2 应命中 t1(10.0) + t2(2.0)，不漏 t1。

        历史 bug：String 列字典序下 '10.0' < '2' → t1 漏匹配，只返回 {'t2'}。
        Float 列：10.0 >= 2 且 2.0 >= 2 → 返回 {'t1', 't2'}。
        mutation：列被改回 String → 本测试应失败（红队漏洞 #1 复现）。
        """
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[SearchCondition(field="ratio_limit", operator="gte", value=2)],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert result["code"] == "200"
        assert _info_ids(result) == {"t1", "t2"}, f"ratio_limit>=2 应命中 t1(10.0)+t2(2.0)。实际 {_info_ids(result)}"

    def test_ratio_limit_lte_excludes_double_digit(self, db_session):
        """ratio_limit <= 5 应命中 t2(2.0)+t3(1.5)+t5(0.0)，排除 t1(10.0)。

        历史 bug：String 列字典序 '10.0' < '5' → t1 被误命中。
        """
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[SearchCondition(field="ratio_limit", operator="lte", value=5)],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert _info_ids(result) == {"t2", "t3", "t5"}, f"ratio_limit<=5 应排除 t1(10.0)。实际 {_info_ids(result)}"

    def test_ratio_limit_null_excluded_by_filter(self, db_session):
        """ratio_limit=NULL（t4, t6）在 gte 比较下被 SQL 三值逻辑排除。"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[SearchCondition(field="ratio_limit", operator="gte", value=0)],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        # t6 已软删除；t4 ratio_limit=NULL 被排除
        assert "t4" not in _info_ids(result), "NULL 行不应被 gte 命中"


# ==================== J. v1.0.6.1 新增 4 操作符回归（between/regex/last_days/date_range）====================


class TestNewOperatorsRegression:
    """验证 v1.0.6.1 新增的 between/regex/last_days/date_range 操作符。

    前端 AdvancedSearchBuilder 暴露这 4 个操作符但后端 OPERATOR_MAPPING 不支持，
    Pydantic allowed_operators 也不含 → 历史是 422 硬失败。v1.0.6.1 后端补齐实现。
    """

    def test_between_on_size_with_units(self, db_session):
        """between on size：value={min:'1 GB', max:'10 GB', minUnit, maxUnit} → 命中 t3(1GB),t4(5GB)。"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(
                    field="size",
                    operator="between",
                    value={"min": "1 GB", "max": "10 GB", "minUnit": "GB", "maxUnit": "GB"},
                )
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert _info_ids(result) == {"t3", "t4"}, f"size between [1GB,10GB] 实际 {_info_ids(result)}"

    def test_between_on_ratio_numeric(self, db_session):
        """between on ratio：value={min:1, max:3} → 命中 t1(2.5),t5(1.0)（t3=10.0 超上限）。"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(
                    field="ratio",
                    operator="between",
                    value={"min": 1, "max": 3},
                )
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert _info_ids(result) == {"t1", "t5"}, f"ratio between [1,3] 实际 {_info_ids(result)}"

    def test_between_on_added_date_range(self, db_session):
        """between on added_date：value={start, end} → 命中 t2(2026-02-20) 在 [2026-02-01, 2026-03-01] 内。"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(
                    field="added_date",
                    operator="between",
                    value={"start": "2026-02-01", "end": "2026-03-01"},
                )
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert _info_ids(result) == {"t2"}, f"added_date between 实际 {_info_ids(result)}"

    def test_regex_on_name_case_insensitive(self, db_session):
        """regex on name：value={pattern:'avatar', caseSensitive:false} → 命中 t1(Avatar 4K)。

        SQLite 连接注册受限时长的真实正则函数；caseSensitive=false 时忽略大小写。
        """
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(
                    field="name",
                    operator="regex",
                    value={"pattern": "avatar", "caseSensitive": False},
                )
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert _info_ids(result) == {"t1"}, f"regex 'avatar' 应命中 t1(Avatar)。实际 {_info_ids(result)}"

    def test_regex_on_name_case_sensitive_excludes_mismatch(self, db_session):
        """regex on name caseSensitive=true：小写 pattern 不应命中大写 A。"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(
                    field="name",
                    operator="regex",
                    value={"pattern": "avatar", "caseSensitive": True},
                )
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert result["total"] == 0

    def test_regex_on_name_honors_anchors_and_quantifiers(self, db_session):
        """正则不是 LIKE：锚点、空白类和量词必须按正则语义执行。"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(
                    field="name",
                    operator="regex",
                    value={
                        "pattern": r"^Avatar\s+\dK\s+BluRay$",
                        "caseSensitive": True,
                    },
                )
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert _info_ids(result) == {"t1"}

    def test_last_days_on_added_date(self, db_session):
        """last_days on added_date：value='{"days": N}'（JSON 字符串）→ 命中最近 N 天添加的种子。

        由于种子数据 added_date 是固定历史日期（2026-01-15 等），用一个极大天数确保全部命中。
        """
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(
                    field="added_date",
                    operator="last_days",
                    value='{"days": 36500}',
                )
            ],  # 100 年，确保所有 2026 年种子都被命中
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        # 5 个活跃种子（t6 软删除排除）都应在最近 100 年内
        assert result["total"] == 5, f"last_days=36500 应命中全部活跃种子。实际 {result['total']}"

    def test_last_days_excludes_old_dates(self, db_session):
        """last_days=1 只命中最近 1 天（种子都是历史日期，应返回空）。"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(
                    field="added_date",
                    operator="last_days",
                    value='{"days": 1}',
                )
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        assert result["total"] == 0, f"last_days=1 不应命中 2026 年历史种子。实际 {result['total']}"

    def test_date_range_on_added_date(self, db_session):
        """date_range on added_date：value='{"start","end"}'（JSON 字符串）→ 命中区间内种子。"""
        _seed_torrents(db_session)
        group = SearchGroup(
            logic="AND",
            conditions=[
                SearchCondition(
                    field="added_date",
                    operator="date_range",
                    value='{"start": "2026-03-01", "end": "2026-05-01"}',
                )
            ],
        )
        result = _search(db_session, condition_groups=[group], limit=100000)
        # t3(2026-03-10), t4(2026-04-05) 在 [03-01, 05-01] 内
        assert _info_ids(result) == {"t3", "t4"}, f"date_range 实际 {_info_ids(result)}"


# ==================== K. v1.0.6.1 前后端操作符契约守卫 ====================


class TestOperatorContractGuard:
    """冻结前端暴露的操作符集合，防止后端 silently 不支持导致 422 或语义降级。

    红队发现：前端 AdvancedSearchBuilder 暴露 between/regex/last_days/date_range，
    但后端 allowed_operators 不含 → Pydantic 直接 422 拒整个请求。
    v1.0.6.1 已在后端补齐这 4 个操作符，本测试冻结契约，强制任何新增前端操作符
    必须同步在后端 allowed_operators 登记。
    """

    def test_all_frontend_operators_are_backend_supported(self):
        """前端 operatorGroups 里全部 backendValue 必须在后端 allowed_operators 集合内。"""
        from app.contracts.advanced_search import (
            ADVANCED_SEARCH_CONTRACT,
            NEGATED_SEARCH_OPERATORS,
            SEARCH_FIELD_CONTRACT,
            SUPPORTED_SEARCH_OPERATORS,
        )

        frontend_operators = {
            item["backendValue"]
            for group in ADVANCED_SEARCH_CONTRACT["operatorGroups"].values()
            for item in group
        }
        assert frontend_operators <= SUPPORTED_SEARCH_OPERATORS
        for operator in frontend_operators:
            assert any(
                operator in field["operators"]
                for field in SEARCH_FIELD_CONTRACT.values()
            ), f"{operator} is exposed by the UI but allowed by no field"
        for operator, negated in NEGATED_SEARCH_OPERATORS.items():
            assert NEGATED_SEARCH_OPERATORS[negated] == operator
            for field in SEARCH_FIELD_CONTRACT.values():
                if operator in field["operators"]:
                    assert negated in field["operators"]
