# -*- coding: utf-8 -*-
"""路径映射“配置验证”端点回归测试。

验证必须同时覆盖：
- 下载器内部路径：通过 ``app.state.store`` 中的缓存客户端探测；
- BtDeck 外部路径：在当前运行环境中必须是可访问目录；
- 任一映射任一路径失败时，整体结果必须失败并返回逐项错误。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

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
from app.services.path_mapping_validation import validate_path_mapping_directories

URL = "/api/v1/downloader/dl-1/path-mapping/test"


@pytest.fixture
def path_mapping_client():
    """创建带 Transmission 缓存客户端的独立测试应用。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[BtDownloaders.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(BtDownloaders(downloader_id="dl-1", nickname="tr", downloader_type=1, dr=0))
    session.commit()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        request_session = Session()
        try:
            yield request_session
        finally:
            request_session.close()

    cached_client = MagicMock()
    cached_client.free_space.return_value = 1024
    cached_downloader = SimpleNamespace(
        downloader_id="dl-1",
        downloader_type=1,
        fail_time=0,
        client=cached_client,
    )
    app.state.store = SimpleNamespace(get_snapshot_sync=lambda: [cached_downloader])
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client, cached_client, app

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _payload(internal: str, external: str, *, name: str = "下载目录") -> dict:
    return {
        "path_mapping": {
            "mappings": [
                {
                    "name": name,
                    "internal": internal,
                    "external": external,
                    "mapping_type": "docker",
                }
            ]
        }
    }


class TestPathMappingValidation:
    def test_existing_internal_and_external_directories_pass(self, path_mapping_client, tmp_path):
        client, cached_client, _app = path_mapping_client

        response = client.post(URL, json=_payload("/downloads", str(tmp_path)))

        body = response.json()
        assert body["code"] == "200"
        assert body["data"]["valid"] is True
        assert body["data"]["backend_validation"]["internal_paths_valid"] is True
        assert body["data"]["backend_validation"]["external_paths_valid"] is True
        cached_client.free_space.assert_called_once_with("/downloads")

    def test_missing_external_directory_fails_instead_of_format_only_pass(self, path_mapping_client, tmp_path):
        client, _cached_client, _app = path_mapping_client
        missing_path = tmp_path / "does-not-exist"

        response = client.post(URL, json=_payload("/downloads", str(missing_path)))

        body = response.json()
        assert body["code"] == "200"
        assert body["data"]["valid"] is False
        validation = body["data"]["backend_validation"]
        assert validation["external_paths_valid"] is False
        assert any("外部路径不存在" in error for error in validation["errors"])

    def test_downloader_rejecting_internal_directory_fails_closed(self, path_mapping_client, tmp_path):
        client, cached_client, _app = path_mapping_client
        cached_client.free_space.side_effect = RuntimeError("No such directory")

        response = client.post(URL, json=_payload("/missing-on-downloader", str(tmp_path)))

        body = response.json()
        assert body["code"] == "200"
        assert body["data"]["valid"] is False
        validation = body["data"]["backend_validation"]
        assert validation["internal_paths_valid"] is False
        assert any("下载器内部路径不可用" in error for error in validation["errors"])

    def test_unavailable_cached_downloader_never_passes(self, path_mapping_client, tmp_path):
        client, _cached_client, app = path_mapping_client
        app.state.store = SimpleNamespace(get_snapshot_sync=lambda: [])

        response = client.post(URL, json=_payload("/downloads", str(tmp_path)))

        body = response.json()
        assert body["code"] == "200"
        assert body["data"]["valid"] is False
        validation = body["data"]["backend_validation"]
        assert validation["downloader_available"] is False
        assert any("下载器不在缓存中" in error for error in validation["errors"])

    def test_one_invalid_mapping_makes_whole_configuration_fail(self, path_mapping_client, tmp_path):
        client, _cached_client, _app = path_mapping_client
        payload = {
            "path_mapping": {
                "mappings": [
                    {
                        "name": "有效目录",
                        "internal": "/downloads",
                        "external": str(tmp_path),
                        "mapping_type": "docker",
                    },
                    {
                        "name": "无效目录",
                        "internal": "/media",
                        "external": str(tmp_path / "missing"),
                        "mapping_type": "docker",
                    },
                ]
            }
        }

        response = client.post(URL, json=payload)

        body = response.json()
        assert body["data"]["valid"] is False
        checks = body["data"]["backend_validation"]["path_checks"]
        assert len(checks) == 2
        assert checks[0]["valid"] is True
        assert checks[1]["valid"] is False


@pytest.fixture
def direct_downloader_calls(monkeypatch):
    """服务层单测直接执行 mock RPC，避免线程池影响断言。"""

    async def direct_call(_downloader_id, _lane, func, args=(), kwargs=None, **_options):
        return func(*args, **(kwargs or {}))

    monkeypatch.setattr(
        "app.services.path_mapping_validation.call_downloader_api",
        direct_call,
    )


def _app_state_with_client(client, *, downloader_type: int):
    cached_downloader = SimpleNamespace(
        downloader_id="dl-qb",
        downloader_type=downloader_type,
        fail_time=0,
        client=client,
    )
    return SimpleNamespace(store=SimpleNamespace(get_snapshot_sync=lambda: [cached_downloader]))


@pytest.mark.asyncio
class TestQBittorrentInternalPathValidation:
    async def test_default_path_with_free_space_is_valid(self, direct_downloader_calls, tmp_path):
        qb_client = MagicMock()
        qb_client.app_default_save_path.return_value = "/downloads"
        qb_client.sync_maindata.return_value = {
            "server_state": {"free_space_on_disk": 0},
            "torrents": {},
        }

        result = await validate_path_mapping_directories(
            _app_state_with_client(qb_client, downloader_type=0),
            "dl-qb",
            0,
            [{"name": "默认目录", "internal": "/downloads", "external": str(tmp_path)}],
        )

        assert result["internal_paths_valid"] is True
        assert result["path_checks"][0]["valid"] is True

    async def test_existing_torrent_path_below_mapping_root_is_valid(self, direct_downloader_calls, tmp_path):
        qb_client = MagicMock()
        qb_client.app_default_save_path.return_value = "/other"
        qb_client.sync_maindata.return_value = {
            "server_state": {"free_space_on_disk": -1},
            "torrents": {
                "hash": {
                    "save_path": "/library/movies",
                    "state": "uploading",
                }
            },
        }

        result = await validate_path_mapping_directories(
            _app_state_with_client(qb_client, downloader_type=0),
            "dl-qb",
            0,
            [{"name": "媒体库", "internal": "/library", "external": str(tmp_path)}],
        )

        assert result["internal_paths_valid"] is True
        assert "现有种子路径" in result["path_checks"][0]["internal"]["message"]

    async def test_unreported_qbittorrent_directory_fails_closed(self, direct_downloader_calls, tmp_path):
        qb_client = MagicMock()
        qb_client.app_default_save_path.return_value = "/downloads"
        qb_client.sync_maindata.return_value = {
            "server_state": {"free_space_on_disk": 1024},
            "torrents": {},
        }

        result = await validate_path_mapping_directories(
            _app_state_with_client(qb_client, downloader_type=0),
            "dl-qb",
            0,
            [
                {
                    "name": "未知目录",
                    "internal": "/not-reported",
                    "external": str(tmp_path),
                }
            ],
        )

        assert result["internal_paths_valid"] is False
        assert result["path_checks"][0]["valid"] is False
        assert "无法确认目录存在" in result["errors"][0]

    async def test_only_missing_files_torrents_do_not_prove_directory(self, direct_downloader_calls, tmp_path):
        qb_client = MagicMock()
        qb_client.app_default_save_path.return_value = "/other"
        qb_client.sync_maindata.return_value = {
            "server_state": {"free_space_on_disk": -1},
            "torrents": {
                "hash": {
                    "save_path": "/library/movies",
                    "state": "missingFiles",
                }
            },
        }

        result = await validate_path_mapping_directories(
            _app_state_with_client(qb_client, downloader_type=0),
            "dl-qb",
            0,
            [{"name": "丢失目录", "internal": "/library", "external": str(tmp_path)}],
        )

        assert result["internal_paths_valid"] is False
        assert "文件缺失或错误状态" in result["errors"][0]

    async def test_torrent_without_state_does_not_prove_directory(self, direct_downloader_calls, tmp_path):
        qb_client = MagicMock()
        qb_client.app_default_save_path.return_value = "/other"
        qb_client.sync_maindata.return_value = {
            "server_state": {"free_space_on_disk": -1},
            "torrents": {"hash": {"save_path": "/library/movies"}},
        }

        result = await validate_path_mapping_directories(
            _app_state_with_client(qb_client, downloader_type=0),
            "dl-qb",
            0,
            [{"name": "无状态目录", "internal": "/library", "external": str(tmp_path)}],
        )

        assert result["internal_paths_valid"] is False
        assert "文件缺失或错误状态" in result["errors"][0]
