# -*- coding: utf-8 -*-
"""
search_templates.preset_key 迁移与幂等测试（desktop-bilingual P4 子范围提前）

验证目标（PLANS/bilingual/system-content.md §1 提案 + 验收矩阵 B01/B02/Q01）：
1. 迁移：加列 + 索引 + 按中文名一次性回填（仅 is_default=1 恰一行时回填）；
2. B02 用户数据保护：用户同名模板（is_default=0）与歧义预设行（同名多行）
   一律不猜、保持 NULL；
3. init_default_search_templates 按 preset_key 幂等：新库插入带 key、
   已回填库零新建、旧库中文名恰一行自愈回填、歧义不猜；
4. API 透出：SearchTemplateModel._row_to_dict 携带 preset_key（用户模板为 None）；
5. downgrade 可回滚且重复升级幂等。
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.search_template import SearchTemplate
from app.services.advanced_search import SearchTemplateModel

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

from tests.core.alembic_head import current_head  # noqa: E402（需在 BACKEND_ROOT 定义后）

PRESET_KEY_PREV = "c1d2e3f4a5b6"
EXPECTED_HEAD = current_head()  # 动态读取（dev1.0.7 合入后 head 前移至 053003337878）

# 中文名 → 稳定键（与迁移/初始化数据同源）
PRESETS = {
    "活跃种子": "active_torrents",
    "错误状态": "error_status",
    "已暂停": "paused",
    "大文件": "large_files",
}


@pytest.fixture(autouse=True)
def _clean_database_path_env():
    """自动清理 DATABASE_PATH 环境变量，防止跨测试污染（测试隔离）。"""
    old = os.environ.pop("DATABASE_PATH", None)
    yield
    if old is not None:
        os.environ["DATABASE_PATH"] = old
    else:
        os.environ.pop("DATABASE_PATH", None)


def _make_alembic_config(db_path: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    os.environ["DATABASE_PATH"] = str(db_path)
    return cfg


def _insert_template(
    db_path,
    name,
    *,
    is_default,
    user_id="system",
    description="",
    conditions=None,
    row_seq=0,
):
    """在旧形态 schema（无 preset_key 列）上插入一行模板。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO search_templates (id, user_id, name, description, conditions, "
            "is_default, is_public, usage_count, created_time, updated_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (
                f"row-{name}-{user_id}-{is_default}-{row_seq}",
                user_id,
                name,
                description,
                json.dumps(conditions or {"source": "simple", "version": 1, "listQuery": {}}, ensure_ascii=False),
                is_default,
                1 if is_default else 0,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_preset_keys(db_path):
    """读取 (name, is_default, preset_key) 全表行。"""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT name, is_default, preset_key FROM search_templates").fetchall()
    finally:
        conn.close()


class TestPresetKeyMigration:
    """b3e5f7a9c1d2 迁移：加列 + 回填 + 用户数据保护（B01/B02）。"""

    def test_upgrade_backfills_legacy_presets_by_name(self, tmp_path):
        """旧库 4 个中文名系统预设恰一行 → 回填对应稳定键。"""
        db_path = tmp_path / "backfill.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, PRESET_KEY_PREV)

        for name in PRESETS:
            _insert_template(db_path, name, is_default=1)

        command.upgrade(cfg, "head")
        rows = _fetch_preset_keys(db_path)
        by_name = {name: key for name, is_default, key in rows if is_default == 1}
        assert by_name == PRESETS

    def test_user_template_with_same_name_stays_null(self, tmp_path):
        """B02：用户同名模板（is_default=0）不被回填、不被覆盖。"""
        db_path = tmp_path / "user_same_name.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, PRESET_KEY_PREV)

        _insert_template(db_path, "活跃种子", is_default=1)
        _insert_template(db_path, "活跃种子", is_default=0, user_id="user-1")

        command.upgrade(cfg, "head")
        rows = _fetch_preset_keys(db_path)
        system_rows = [(name, key) for name, is_default, key in rows if is_default == 1]
        user_rows = [(name, key) for name, is_default, key in rows if is_default == 0]
        assert system_rows == [("活跃种子", "active_torrents")]
        assert user_rows == [("活跃种子", None)], "用户同名模板必须保持 preset_key NULL"

    def test_ambiguous_legacy_rows_left_null(self, tmp_path):
        """B02：同名系统预设多行（人工复制）歧义不猜，全部保持 NULL。"""
        db_path = tmp_path / "ambiguous.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, PRESET_KEY_PREV)

        _insert_template(db_path, "活跃种子", is_default=1, user_id="system", row_seq=1)
        _insert_template(db_path, "活跃种子", is_default=1, user_id="system", row_seq=2)

        command.upgrade(cfg, "head")
        rows = _fetch_preset_keys(db_path)
        assert all(key is None for _name, _is_default, key in rows), "歧义行必须全部保持 NULL"

    def test_repeated_upgrade_is_idempotent(self, tmp_path):
        """已回填库再次 upgrade 无副作用（版本不变、键不变）。"""
        db_path = tmp_path / "idempotent.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, PRESET_KEY_PREV)
        _insert_template(db_path, "活跃种子", is_default=1)
        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        try:
            version_before = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            conn.close()

        command.upgrade(cfg, "head")
        rows = _fetch_preset_keys(db_path)
        assert rows == [("活跃种子", 1, "active_torrents")]

        conn = sqlite3.connect(db_path)
        try:
            version_after = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            conn.close()
        assert version_before == version_after == EXPECTED_HEAD

    def test_downgrade_then_upgrade_roundtrip(self, tmp_path):
        """downgrade drop 列后再次 upgrade 补列（数据行保留）。"""
        db_path = tmp_path / "roundtrip.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, PRESET_KEY_PREV)
        _insert_template(db_path, "大文件", is_default=1)
        command.upgrade(cfg, "head")
        assert _fetch_preset_keys(db_path) == [("大文件", 1, "large_files")]

        command.downgrade(cfg, PRESET_KEY_PREV)
        conn = sqlite3.connect(db_path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(search_templates)").fetchall()}
        finally:
            conn.close()
        assert "preset_key" not in columns

        command.upgrade(cfg, "head")
        assert _fetch_preset_keys(db_path) == [("大文件", 1, "large_files")]


@pytest.fixture
def orm_session():
    """内存 SQLite + create_all（模型已含 preset_key 列）。"""
    from app.auth.models import User, LoginLog, Config  # noqa: F401
    from app.downloader.models import BtDownloaders  # noqa: F401
    from app.torrents.models import TorrentInfo, TrackerInfo  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


class TestInitByIdempotencyByPresetKey:
    """init_default_search_templates 按 preset_key 幂等（含旧库自愈与歧义保护）。"""

    def test_fresh_insert_writes_preset_key(self, orm_session):
        """新库插入 4 条记录均携带稳定键。"""
        from app.data.default_search_templates import DEFAULT_SEARCH_TEMPLATE_KEYS, init_default_search_templates

        count = init_default_search_templates(orm_session)
        assert count == 4

        keys = {
            row.preset_key for row in orm_session.query(SearchTemplate).filter(SearchTemplate.is_default == 1).all()
        }
        assert keys == DEFAULT_SEARCH_TEMPLATE_KEYS

    def test_reseed_after_key_insert_is_idempotent(self, orm_session):
        """按 key 幂等：重复 init 零新建。"""
        from app.data.default_search_templates import init_default_search_templates

        assert init_default_search_templates(orm_session) == 4
        assert init_default_search_templates(orm_session) == 0

    def test_legacy_name_single_row_self_heals_key(self, orm_session):
        """迁移回填遗漏的旧库：恰一行旧中文名 → 回填身份，不重复插入。"""
        from app.data.default_search_templates import init_default_search_templates

        # 手工构造旧形态行（无 preset_key）
        legacy = SearchTemplate(
            id="legacy-1",
            user_id="system",
            name="活跃种子",
            description="",
            conditions="{}",
            is_default=1,
            is_public=1,
        )
        orm_session.add(legacy)
        orm_session.commit()

        count = init_default_search_templates(orm_session)
        assert count == 3, "仅补其余 3 个缺失预设，旧中文名行不重复插入"

        rows = orm_session.query(SearchTemplate).filter(SearchTemplate.is_default == 1).all()
        active = [row for row in rows if row.preset_key == "active_torrents"]
        assert len(active) == 1
        assert active[0].id == "legacy-1", "旧行应原地回填身份而非新插入"

    def test_ambiguous_legacy_names_not_guessed(self, orm_session):
        """歧义旧名（两行同名）保持 NULL 不猜，且不重复插入（B02）。"""
        from app.data.default_search_templates import init_default_search_templates

        orm_session.add_all(
            [
                SearchTemplate(
                    id="amb-1", user_id="system", name="活跃种子", description="", conditions="{}", is_default=1
                ),
                SearchTemplate(
                    id="amb-2", user_id="system", name="活跃种子", description="", conditions="{}", is_default=1
                ),
            ]
        )
        orm_session.commit()

        count = init_default_search_templates(orm_session)
        assert count == 3, "其余 3 个正常插入，歧义预设不新增"

        ambiguous = orm_session.query(SearchTemplate).filter(SearchTemplate.id.in_(["amb-1", "amb-2"])).all()
        assert all(row.preset_key is None for row in ambiguous), "歧义行必须保持 NULL"

    def test_user_template_with_same_name_untouched(self, orm_session):
        """B02：用户同名模板不被回填身份，init 照常插入系统预设。"""
        from app.data.default_search_templates import init_default_search_templates

        orm_session.add(
            SearchTemplate(
                id="user-tpl", user_id="user-1", name="活跃种子", description="用户副本", conditions="{}", is_default=0
            )
        )
        orm_session.commit()

        assert init_default_search_templates(orm_session) == 4

        user_row = orm_session.query(SearchTemplate).filter(SearchTemplate.id == "user-tpl").one()
        assert user_row.preset_key is None
        assert user_row.name == "活跃种子"


class TestPresetKeyApiSurface:
    """API 透出：模板字典携带 preset_key（前端展示映射的数据源）。"""

    def test_row_to_dict_exposes_preset_key(self, orm_session):
        model = SearchTemplateModel(orm_session)
        created = model.create({"user_id": "u1", "name": "t", "conditions": {}})

        fetched = model.get_by_id(created["id"])
        assert "preset_key" in fetched
        assert fetched["preset_key"] is None, "用户模板无稳定身份键"

        # 系统预设行经 ORM 写入 preset_key 后透出
        orm_session.query(SearchTemplate).filter(SearchTemplate.id == created["id"]).update(
            {"preset_key": "active_torrents"}
        )
        orm_session.commit()
        assert model.get_by_id(created["id"])["preset_key"] == "active_torrents"

    def test_default_presets_expose_keys_via_model(self, orm_session):
        """init 后经 get_by_user 读取，系统预设带键、可按键定位（Q01 前提）。"""
        from app.data.default_search_templates import init_default_search_templates

        init_default_search_templates(orm_session)
        model = SearchTemplateModel(orm_session)
        templates = model.get_by_user("system", is_public=True)

        keyed = {t["preset_key"]: t for t in templates if t.get("preset_key")}
        assert set(keyed) == set(PRESETS.values())
        assert all(t["is_default"] for t in keyed.values())
