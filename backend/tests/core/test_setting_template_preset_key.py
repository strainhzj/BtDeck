# -*- coding: utf-8 -*-
"""
setting_templates.preset_key 迁移与幂等测试（desktop-bilingual P6-2 子范围）

验证目标（PLANS/bilingual/system-content.md §2 提案 + 验收矩阵 B01/B02/Q01）：
1. 迁移：加列 + 索引 + 按中文名一次性回填（仅 is_system_default=1 恰一行时回填）；
2. B02 用户数据保护：用户同名模板（is_system_default=0）与歧义预设行（同名多行）
   一律不猜、保持 NULL；
3. init_default_templates 按 preset_key 幂等：新库插入带 key、已回填库零新建、
   旧库中文名恰一行自愈回填、歧义不猜；
4. API 透出：SettingTemplate.to_dict 携带 preset_key（用户模板为 None）；
5. downgrade 可回滚且重复升级幂等。
"""

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

from app.data.default_templates import DEFAULT_TEMPLATES
from app.database import Base
from app.models.setting_templates import SettingTemplate

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

PRESET_KEY_PREV = "b3e5f7a9c1d2"
EXPECTED_HEAD = "d1e2f3a4b5c6"

# 中文名 → 稳定键（与迁移/初始化数据同源；P0 冻结键名）
PRESETS = {
    "qBittorrent标准模板": "qb_standard",
    "qBittorrent高性能模板": "qb_highperf",
    "Transmission标准模板": "tr_standard",
    "Transmission高性能模板": "tr_highperf",
    "夜间不限速模板": "night_unlimited",
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


def _insert_template(db_path, name, *, is_system_default, row_seq=0, downloader_type=0):
    """在旧形态 schema（无 preset_key 列）上插入一行模板。"""
    now = datetime.now().isoformat(sep=" ")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO setting_templates (name, description, downloader_type, template_config, "
            "is_system_default, created_by, path_mapping, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
            (
                name,
                f"desc-{row_seq}",
                downloader_type,
                "{}",
                1 if is_system_default else 0,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_preset_keys(db_path):
    """读取 (name, is_system_default, preset_key) 全表行。"""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT name, is_system_default, preset_key FROM setting_templates").fetchall()
    finally:
        conn.close()


class TestPresetKeyMigration:
    """d1e2f3a4b5c6 迁移：加列 + 回填 + 用户数据保护（B01/B02）。"""

    def test_upgrade_backfills_legacy_presets_by_name(self, tmp_path):
        """旧库 5 个中文名系统预设恰一行 → 回填对应稳定键。"""
        db_path = tmp_path / "backfill.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, PRESET_KEY_PREV)

        for index, name in enumerate(PRESETS):
            _insert_template(db_path, name, is_system_default=1, row_seq=index)

        command.upgrade(cfg, "head")
        rows = _fetch_preset_keys(db_path)
        by_name = {name: key for name, is_system_default, key in rows if is_system_default == 1}
        assert by_name == PRESETS

    def test_user_template_with_same_name_stays_null(self, tmp_path):
        """B02：用户模板（is_system_default=0）即便占用预设名也不被回填。

        注：setting_templates.name 有 UNIQUE 约束（uq_setting_templates_name），
        用户行与系统行不可能同名共存——测试改为「仅用户行占名」场景。
        """
        db_path = tmp_path / "user_same_name.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, PRESET_KEY_PREV)

        _insert_template(db_path, "qBittorrent标准模板", is_system_default=0)

        command.upgrade(cfg, "head")
        rows = _fetch_preset_keys(db_path)
        assert rows == [("qBittorrent标准模板", 0, None)], "用户模板必须保持 preset_key NULL"

    def test_name_unique_constraint_blocks_duplicates(self, tmp_path):
        """不变量：name 唯一约束使「同名多行歧义」在数据层不可能出现。

        与 search_templates 不同，本表 uq_setting_templates_name 保证同名仅一行，
        因此迁移回填无歧义分支；此测试把该前提显式钉住（约束被移除时会红）。
        """
        db_path = tmp_path / "unique_name.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, PRESET_KEY_PREV)

        _insert_template(db_path, "夜间不限速模板", is_system_default=1, row_seq=1)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_template(db_path, "夜间不限速模板", is_system_default=1, row_seq=2)

        command.upgrade(cfg, "head")
        assert _fetch_preset_keys(db_path) == [("夜间不限速模板", 1, "night_unlimited")]

    def test_repeated_upgrade_is_idempotent(self, tmp_path):
        """已回填库再次 upgrade 无副作用（版本不变、键不变）。"""
        db_path = tmp_path / "idempotent.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, PRESET_KEY_PREV)
        _insert_template(db_path, "Transmission标准模板", is_system_default=1)
        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        try:
            version_before = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            conn.close()

        command.upgrade(cfg, "head")
        assert _fetch_preset_keys(db_path) == [("Transmission标准模板", 1, "tr_standard")]

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
        _insert_template(db_path, "Transmission高性能模板", is_system_default=1)
        command.upgrade(cfg, "head")
        assert _fetch_preset_keys(db_path) == [("Transmission高性能模板", 1, "tr_highperf")]

        command.downgrade(cfg, PRESET_KEY_PREV)
        conn = sqlite3.connect(db_path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(setting_templates)").fetchall()}
        finally:
            conn.close()
        assert "preset_key" not in columns

        command.upgrade(cfg, "head")
        assert _fetch_preset_keys(db_path) == [("Transmission高性能模板", 1, "tr_highperf")]


@pytest.fixture
def orm_session():
    """内存 SQLite + create_all（模型已含 preset_key 列）。"""
    from app.auth.models import User, LoginLog, Config  # noqa: F401

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
    """init_default_templates 按 preset_key 幂等（含旧库自愈与歧义保护）。"""

    def test_fresh_insert_writes_preset_key(self, orm_session):
        """新库插入 5 条记录均携带稳定键。"""
        from app.data.default_templates import init_default_templates

        count = init_default_templates(orm_session)
        assert count == len(PRESETS)

        rows = orm_session.query(SettingTemplate).filter(SettingTemplate.is_system_default.is_(True)).all()
        assert {row.preset_key for row in rows} == set(PRESETS.values())

    def test_reseed_after_key_insert_is_idempotent(self, orm_session):
        """按 key 幂等：重复 init 零新建。"""
        from app.data.default_templates import init_default_templates

        assert init_default_templates(orm_session) == len(PRESETS)
        assert init_default_templates(orm_session) == 0

    def test_legacy_name_single_row_self_heals_key(self, orm_session):
        """迁移回填遗漏的旧库：恰一行旧中文名 → 回填身份，不重复插入。"""
        from app.data.default_templates import init_default_templates

        legacy = SettingTemplate(
            name="qBittorrent标准模板",
            description="旧库行",
            downloader_type=0,
            template_config="{}",
            is_system_default=True,
        )
        orm_session.add(legacy)
        orm_session.commit()
        legacy_id = legacy.id

        count = init_default_templates(orm_session)
        assert count == len(PRESETS) - 1, "仅补其余 4 个缺失预设，旧中文名行不重复插入"

        rows = orm_session.query(SettingTemplate).filter(SettingTemplate.preset_key == "qb_standard").all()
        assert len(rows) == 1
        assert rows[0].id == legacy_id, "旧行应原地回填身份而非新插入"

    def test_legacy_system_row_with_existing_key_not_duplicated(self, orm_session):
        """已带 key 的系统行不重复插入（唯一名约束下不会 IntegrityError）。"""
        from app.data.default_templates import init_default_templates

        orm_session.add(
            SettingTemplate(
                name="夜间不限速模板",
                description="已回填行",
                downloader_type=0,
                template_config="{}",
                is_system_default=True,
                preset_key="night_unlimited",
            )
        )
        orm_session.commit()

        assert init_default_templates(orm_session) == len(PRESETS) - 1
        rows = orm_session.query(SettingTemplate).filter(SettingTemplate.name == "夜间不限速模板").all()
        assert len(rows) == 1
        assert rows[0].preset_key == "night_unlimited"

    def test_user_template_with_same_name_untouched(self, orm_session):
        """B02：用户同名模板不被回填身份，init 照常插入系统预设。"""
        from app.data.default_templates import init_default_templates

        orm_session.add(
            SettingTemplate(
                name="qBittorrent高性能模板",
                description="用户副本",
                downloader_type=0,
                template_config="{}",
                is_system_default=False,
            )
        )
        orm_session.commit()

        # 同名唯一约束下不得插入同名系统预设（否则 IntegrityError）：
        # init 跳过该名并保留用户行原状（B02）
        assert init_default_templates(orm_session) == len(PRESETS) - 1

        user_row = orm_session.query(SettingTemplate).filter(SettingTemplate.is_system_default.is_(False)).one()
        assert user_row.preset_key is None
        # 同名系统预设未插入，其余 4 个预设就位
        assert orm_session.query(SettingTemplate).filter(SettingTemplate.name == "qBittorrent高性能模板").count() == 1


class TestPresetKeyApiSurface:
    """API/模型透出：to_dict 携带 preset_key（用户模板 None）。"""

    def test_default_presets_expose_keys_via_model(self, orm_session):
        from app.data.default_templates import init_default_templates

        init_default_templates(orm_session)
        rows = orm_session.query(SettingTemplate).filter(SettingTemplate.is_system_default.is_(True)).all()
        payloads = [row.to_dict() for row in rows]
        assert {payload["preset_key"] for payload in payloads} == set(PRESETS.values())
        # 名称/描述存储值不变（Q02：展示层映射，不改存储）
        assert {payload["name"] for payload in payloads} == set(PRESETS)

    def test_user_template_preset_key_is_none(self, orm_session):
        user_row = SettingTemplate(
            name="我的模板",
            description="",
            downloader_type=0,
            template_config="{}",
            is_system_default=False,
        )
        orm_session.add(user_row)
        orm_session.commit()
        assert user_row.to_dict()["preset_key"] is None

    def test_default_templates_declare_frozen_keys(self):
        """P0 冻结键名与数据源一致（防键名漂移）。"""
        keys = {tpl.get("preset_key") for tpl in DEFAULT_TEMPLATES}
        assert keys == set(PRESETS.values())
        assert None not in keys
