# -*- coding: utf-8 -*-
"""
Tracker 关键词池 prefix-match-preview 端点测试

验证 POST /api/v1/tracker-keywords/pool/prefix-match-preview：
- 严格左匹配语义（非 contains）：LIKE 'prefix%' ESCAPE '\\'
- LIKE 通配符 % / _ / \\ 的字面量转义
- SQLite 默认 ASCII 大小写不敏感（与孤儿文件 file_path 左匹配一致）
- pool_type 隔离、dr=1 排除、空 prefix / 非法 pool_type 校验
- 鉴权：无 token → 401

测试装配（同步 get_db，与端点同文件既有风格一致；不套用 orphan-files 的异步 get_async_db 模式）：
- TestClient + dependency_overrides[get_db] 注入指向 isolated_application_database 的真实 SessionLocal
- dependency_overrides[require_authenticated_user] 绕过认证（鉴权用例除外）
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import SessionLocal, engine, get_db
from app.torrents.models import TrackerKeywordConfig

_BASE = "/api/v1/tracker-keywords/pool/prefix-match-preview"


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    return app


def _override_get_db():
    """返回绑定到测试 engine 的同步 Session（真实迁移库）。"""
    db = SessionLocal(bind=engine)
    try:
        yield db
    finally:
        db.close()


def _make_keyword(pool: str, text: str, dr: int = 0) -> TrackerKeywordConfig:
    """构造一行关键词（唯一索引含软删除行，测试用 text 必须全局唯一）。"""
    return TrackerKeywordConfig(
        keyword_type=pool,
        keyword=text,
        language=None,
        priority=100,
        enabled=True,
        create_time=datetime.now(),
        update_time=datetime.now(),
        create_by="tester",
        update_by="tester",
        dr=dr,
    )


class TestPrefixMatchPreviewAuth:
    """鉴权：无 token 应返回 401。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _create_test_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        yield

    def test_no_token_returns_401(self):
        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "x"})
        assert response.status_code == 401


class TestPrefixMatchPreview:
    """业务逻辑测试（真实迁移库 + 同步 get_db 注入）。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _create_test_app()
        self.app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
        self.app.dependency_overrides[get_db] = _override_get_db
        self.client = TestClient(self.app, raise_server_exceptions=False)

        # 每个用例前清空表，保证隔离
        db = SessionLocal(bind=engine)
        try:
            db.query(TrackerKeywordConfig).delete()
            db.commit()
        finally:
            db.close()

        yield
        self.app.dependency_overrides.clear()

    def _seed(self, rows):
        db = SessionLocal(bind=engine)
        try:
            for r in rows:
                db.add(r)
            db.commit()
        finally:
            db.close()

    def test_normal_prefix_match(self):
        """前缀匹配：prefix='test-' 命中 test-001/test-002，排除 other。"""
        self._seed(
            [
                _make_keyword("candidate", "test-001"),
                _make_keyword("candidate", "test-002"),
                _make_keyword("candidate", "other"),
            ]
        )

        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "test-"})
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "200"
        assert data["data"]["count"] == 2
        assert set(data["data"]["sample_keywords"]) == {"test-001", "test-002"}
        assert len(data["data"]["keyword_ids"]) == 2

    def test_strict_prefix_not_contains(self):
        """严格左匹配：后缀 '001' 匹配不到任何词（证明非 contains）。"""
        self._seed([_make_keyword("candidate", "test-001")])

        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "001"})
        assert response.json()["data"]["count"] == 0

    def test_percent_wildcard_escaped(self):
        """% 被转义为字面量：prefix='50%' 只匹 '50%-off'，不匹全部。"""
        self._seed(
            [
                _make_keyword("candidate", "50%-off"),
                _make_keyword("candidate", "50abc"),
                _make_keyword("candidate", "discount"),
            ]
        )

        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "50%"})
        assert response.json()["data"]["count"] == 1
        assert response.json()["data"]["sample_keywords"] == ["50%-off"]

    def test_underscore_wildcard_escaped(self):
        """_ 被转义为字面量：prefix='a_' 只匹 'a_b'，不匹 'axb'/'ayb'。"""
        self._seed(
            [
                _make_keyword("candidate", "a_b"),
                _make_keyword("candidate", "axb"),
                _make_keyword("candidate", "ayb"),
            ]
        )

        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "a_"})
        assert response.json()["data"]["count"] == 1
        assert response.json()["data"]["sample_keywords"] == ["a_b"]

    def test_case_insensitive(self):
        """SQLite LIKE 对 ASCII 大小写不敏感：prefix='Test' 匹 'test-001'。

        该行为与孤儿文件 file_path 左匹配一致，此处钉死以防止迁移到大小写敏感引擎时静默回归。
        """
        self._seed([_make_keyword("candidate", "test-001")])

        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "Test"})
        assert response.json()["data"]["count"] == 1

    def test_empty_prefix_returns_400(self):
        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "   "})
        assert response.status_code == 200
        assert response.json()["code"] == "400"

    def test_invalid_pool_type_returns_400(self):
        response = self.client.post(_BASE, json={"pool_type": "unknown", "prefix": "x"})
        assert response.status_code == 200
        assert response.json()["code"] == "400"

    def test_pool_type_isolation(self):
        """pool_type 隔离：查 candidate 池不返回 ignored 池的同前缀词。"""
        self._seed(
            [
                _make_keyword("candidate", "shared-prefix-a"),
                _make_keyword("ignored", "shared-prefix-b"),
            ]
        )

        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "shared-prefix-"})
        assert response.json()["data"]["count"] == 1
        assert response.json()["data"]["sample_keywords"] == ["shared-prefix-a"]

    def test_soft_deleted_excluded(self):
        """dr=1 的软删除行被排除。"""
        self._seed(
            [
                _make_keyword("candidate", "gone-001", dr=1),
                _make_keyword("candidate", "gone-002", dr=0),
            ]
        )

        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "gone-"})
        assert response.json()["data"]["count"] == 1
        assert response.json()["data"]["sample_keywords"] == ["gone-002"]

    def test_sample_keywords_capped_at_10(self):
        """sample_keywords 最多 10 条，但 count 和 keyword_ids 是全量。"""
        rows = [_make_keyword("candidate", f"bulk-{i:03d}") for i in range(15)]
        self._seed(rows)

        response = self.client.post(_BASE, json={"pool_type": "candidate", "prefix": "bulk-"})
        data = response.json()["data"]
        assert data["count"] == 15
        assert len(data["sample_keywords"]) == 10
        assert len(data["keyword_ids"]) == 15
