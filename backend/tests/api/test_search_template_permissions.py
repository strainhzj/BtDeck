# -*- coding: utf-8 -*-
"""Search template ownership and user_id permission tests."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.search_template import SearchTemplate


_TEST_SECRET = "test-secret-key-for-unit-testing"
_TEST_ALGORITHM = "HS256"
_TEST_LOGIN_SECRET = "test-login-secret"


def _mock_settings():
    mock_s = MagicMock()
    mock_s.SECRET_KEY = _TEST_SECRET
    mock_s.ALGORITHM = _TEST_ALGORITHM
    mock_s.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    return mock_s


def _create_token(user_id: int) -> str:
    from app.auth.utils import create_access_token

    with patch("app.auth.utils.settings", _mock_settings()):
        return create_access_token(
            {"sub": f"user_{user_id}", "user_id": user_id, "verify_secret": _TEST_LOGIN_SECRET}
        )


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SearchTemplate.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[SearchTemplate.__table__])


@pytest.fixture
def client(db_session):
    from app.api.api import api_router
    from app.database import get_db

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with patch("app.auth.utils.settings", _mock_settings()), patch(
        "app.auth.utils.get_login_secret", return_value=_TEST_LOGIN_SECRET
    ):
        yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {_create_token(user_id)}"}


def _insert_template(
    db_session,
    template_id: str,
    user_id: str,
    name: str = "模板",
    is_public: int = 0,
):
    template = SearchTemplate(
        id=template_id,
        user_id=user_id,
        name=name,
        description="",
        conditions='{"source":"simple","listQuery":{}}',
        is_default=0,
        is_public=is_public,
        usage_count=0,
        created_time=datetime.utcnow(),
        updated_time=datetime.utcnow(),
    )
    db_session.add(template)
    db_session.commit()
    return template


def test_create_template_rejects_user_id_in_request_body(client):
    response = client.post(
        "/api/v1/advanced-search/search-templates",
        json={
            "name": "用户1模板",
            "user_id": "999",
            "conditions": {"source": "simple", "listQuery": {}},
            "is_public": False,
        },
        headers=_auth(1),
    )

    assert response.status_code == 422


def test_create_template_uses_authenticated_user_id(client):
    response = client.post(
        "/api/v1/advanced-search/search-templates",
        json={
            "name": "用户1模板",
            "conditions": {"source": "simple", "listQuery": {}},
            "is_public": False,
        },
        headers=_auth(1),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"]["user_id"] == "1"


def test_list_templates_ignores_client_supplied_user_id(client, db_session):
    _insert_template(db_session, "t-user-1", "1", "用户1模板")
    _insert_template(db_session, "t-user-2", "2", "用户2模板")

    response = client.get(
        "/api/v1/advanced-search/search-templates",
        params={"user_id": "2"},
        headers=_auth(1),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert [item["id"] for item in body["data"]] == ["t-user-1"]


def test_user_a_cannot_update_user_b_template(client, db_session):
    _insert_template(db_session, "t-user-2", "2", "用户2模板")

    response = client.put(
        "/api/v1/advanced-search/search-templates/t-user-2",
        json={"id": "t-user-2", "name": "越权更新"},
        headers=_auth(1),
    )

    assert response.status_code == 200
    assert response.json()["code"] == "403"


def test_user_a_cannot_delete_user_b_template(client, db_session):
    _insert_template(db_session, "t-user-2", "2", "用户2模板")

    response = client.delete("/api/v1/advanced-search/search-templates/t-user-2", headers=_auth(1))

    assert response.status_code == 200
    assert response.json()["code"] == "403"
    assert db_session.query(SearchTemplate).filter(SearchTemplate.id == "t-user-2").first() is not None


def test_user_id_int_from_jwt_matches_string_user_id_in_db(client, db_session):
    _insert_template(db_session, "t-user-1", "1", "用户1模板")

    response = client.delete("/api/v1/advanced-search/search-templates/t-user-1", headers=_auth(1))

    assert response.status_code == 200
    assert response.json()["code"] == "200"
    assert db_session.query(SearchTemplate).filter(SearchTemplate.id == "t-user-1").first() is None


def test_update_template_rejects_invalid_conditions_with_http_422(
    client, db_session
):
    _insert_template(db_session, "t-user-1", "1", "用户1模板")

    response = client.put(
        "/api/v1/advanced-search/search-templates/t-user-1",
        json={
            "id": "t-user-1",
            "conditions": {"source": "advanced", "condition_groups": []},
        },
        headers=_auth(1),
    )

    assert response.status_code == 422


def test_apply_template_rejects_legacy_invalid_conditions_with_http_422(
    client, db_session
):
    template = _insert_template(db_session, "t-invalid", "1", "损坏模板")
    template.conditions = "{}"
    db_session.commit()

    response = client.post(
        "/api/v1/advanced-search/search-templates/t-invalid/apply",
        headers=_auth(1),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "422"
