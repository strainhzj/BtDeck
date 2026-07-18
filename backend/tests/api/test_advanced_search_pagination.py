# -*- coding: utf-8 -*-
"""Advanced search pagination response contract tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthenticatedUserInfo, require_authenticated_user


class FakeAdvancedSearchService:
    def __init__(self, result):
        self.result = result

    def search_torrents(self, request, user_id):
        return self.result


def _create_client(result):
    from app.api.api import api_router
    from app.api.endpoints.advanced_search import get_advanced_search_service

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUserInfo(
        username="admin", payload={"sub": "admin", "user_id": 1}, token="test-token", user_id=1
    )
    app.dependency_overrides[get_advanced_search_service] = lambda: FakeAdvancedSearchService(result)
    return TestClient(app, raise_server_exceptions=False), app


def test_advanced_search_uses_list_page_size_total_contract():
    result = {
        "status": "success",
        "msg": "搜索成功",
        "code": "200",
        "data": [{"info_id": "torrent-1"}],
        "total": 1,
        "page": 2,
        "limit": 50,
        "total_pages": 1,
    }
    client, app = _create_client(result)

    response = client.post("/api/v1/advanced-search/advanced-search", json={"page": 2, "limit": 50})

    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"] == {
        "list": [{"info_id": "torrent-1"}],
        "total": 1,
        "page": 2,
        "pageSize": 50,
    }
    assert "data" not in body["data"]
    assert "limit" not in body["data"]
    assert "total_pages" not in body["data"]


def test_advanced_search_empty_results_return_empty_list_and_total_zero():
    result = {
        "status": "success",
        "msg": "搜索成功",
        "code": "200",
        "data": [],
        "total": 0,
        "page": 1,
        "limit": 20,
        "total_pages": 0,
    }
    client, app = _create_client(result)

    response = client.post("/api/v1/advanced-search/advanced-search", json={"page": 1, "limit": 20})

    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "200"
    assert body["data"]["list"] == []
    assert body["data"]["total"] == 0
    assert body["data"]["pageSize"] == 20


def test_advanced_search_accepts_limit_100000():
    result = {
        "status": "success",
        "msg": "search complete",
        "code": "200",
        "data": [],
        "total": 0,
        "page": 1,
        "limit": 100000,
        "total_pages": 0,
    }
    client, app = _create_client(result)

    response = client.post(
        "/api/v1/advanced-search/advanced-search",
        json={"page": 1, "limit": 100000},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["data"]["pageSize"] == 100000


def test_advanced_search_rejects_limit_above_100000():
    client, app = _create_client({})

    response = client.post(
        "/api/v1/advanced-search/advanced-search",
        json={"page": 1, "limit": 100001},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 422
