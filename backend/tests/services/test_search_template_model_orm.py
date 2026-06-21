# -*- coding: utf-8 -*-
"""
SearchTemplateModel ORM 改造后的真实 DB 集成测试

验证从原生 SQL 迁移到 ORM 后，CRUD 行为正确。
现有 test_advanced_search.py 全 mock 掉了 SearchTemplateModel，
本测试用真实内存 SQLite + create_all 钉死实现正确性。
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
# 关键：显式 import SearchTemplate，否则 Base.metadata 不含该表，create_all 建不出
from app.models.search_template import SearchTemplate
from app.services.advanced_search import SearchTemplateModel


@pytest.fixture
def db_session():
    """内存 SQLite + create_all（显式注册 SearchTemplate 模型）。"""
    # 触发所有依赖模型注册到 Base.metadata
    from app.auth.models import User, LoginLog, Config  # noqa: F401
    from app.downloader.models import BtDownloaders  # noqa: F401
    from app.torrents.models import TorrentInfo, TrackerInfo  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestSearchTemplateModelOrm:
    """SearchTemplateModel ORM CRUD 集成测试。"""

    def test_create_and_get_by_id(self, db_session):
        model = SearchTemplateModel(db_session)
        created = model.create({
            'user_id': 'user1',
            'name': '我的模板',
            'description': '测试模板',
            'conditions': {'field': 'name', 'op': 'eq'},
            'is_default': False,
            'is_public': True,
        })

        assert created['id']
        fetched = model.get_by_id(created['id'])
        assert fetched is not None
        assert fetched['name'] == '我的模板'
        assert fetched['user_id'] == 'user1'
        assert fetched['is_public'] is True
        assert fetched['usage_count'] == 0
        # conditions 反序列化为 dict
        assert fetched['conditions'] == {'field': 'name', 'op': 'eq'}

    def test_get_by_user(self, db_session):
        model = SearchTemplateModel(db_session)
        model.create({'user_id': 'user1', 'name': 't1', 'conditions': {}})
        model.create({'user_id': 'user2', 'name': 't2', 'conditions': {}, 'is_public': True})

        # 只看自己的
        own = model.get_by_user('user1', is_public=False)
        assert len(own) == 1
        assert own[0]['name'] == 't1'

        # 包含公开
        with_public = model.get_by_user('user1', is_public=True)
        assert len(with_public) == 2

    def test_update(self, db_session):
        model = SearchTemplateModel(db_session)
        created = model.create({'user_id': 'u1', 'name': 'orig', 'conditions': {}})

        ok = model.update(created['id'], {
            'name': 'renamed',
            'conditions': {'new': True},
            'is_public': True,
        })
        assert ok is True

        fetched = model.get_by_id(created['id'])
        assert fetched['name'] == 'renamed'
        assert fetched['conditions'] == {'new': True}
        assert fetched['is_public'] is True

    def test_update_nonexistent_returns_false(self, db_session):
        model = SearchTemplateModel(db_session)
        assert model.update('nonexistent-id', {'name': 'x'}) is False

    def test_delete(self, db_session):
        model = SearchTemplateModel(db_session)
        created = model.create({'user_id': 'u1', 'name': 'todelete', 'conditions': {}})

        assert model.delete(created['id']) is True
        assert model.get_by_id(created['id']) is None
        # 再删返回 False（已不存在）
        assert model.delete(created['id']) is False

    def test_increment_usage(self, db_session):
        model = SearchTemplateModel(db_session)
        created = model.create({'user_id': 'u1', 'name': 't', 'conditions': {}})

        assert model.increment_usage(created['id']) is True
        assert model.increment_usage(created['id']) is True

        fetched = model.get_by_id(created['id'])
        assert fetched['usage_count'] == 2

    def test_search_template_model_has_no_ensure_table_exists(self):
        """验证 _ensure_table_exists 方法已被删除（第四轨归位）。"""
        assert not hasattr(SearchTemplateModel, '_ensure_table_exists'), \
            "_ensure_table_exists 应已删除，表由 Alembic 迁移管理"

    def test_create_table_via_create_all_includes_search_templates(self, db_session):
        """验证 create_all 能建出 search_templates 表（SearchTemplate 已注册）。"""
        from sqlalchemy import inspect
        insp = inspect(db_session.bind)
        assert insp.has_table('search_templates'), \
            "create_all 应建出 search_templates 表（需显式 import SearchTemplate 模型）"
