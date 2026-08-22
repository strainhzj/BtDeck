# -*- coding: utf-8 -*-
"""备份端点级安全回归测试（W3/W4）。

保护点（防回归）：
1. POST /torrents/backup/import 的 multipart filename 携带 ../../ 时，
   落盘必须被限制在 data/temp_imports/<uuid>/ 子目录内且文件名已消毒
   （历史缺陷：temp_dir / file.filename 直接拼接 = 任意文件写入）；
2. 异常路径（bencode 解析失败）不得留下越界文件，且不删除并发请求的子目录；
3. POST /torrents/backup 的 source_file_path 非 .torrent 后缀必须 400
   （历史缺陷：任意文件可被复制进备份目录后经下载端点带走）。
"""

import bencodepy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user

URL_IMPORT = "/api/v1/torrents/backup/import"
URL_BACKUP = "/api/v1/torrents/backup"


def _valid_torrent_bytes() -> bytes:
    return bencodepy.encode({b"info": {b"name": b"t", b"length": 1}})


def _fake_downloader(**overrides):
    base = {
        "host": "127.0.0.1",
        "port": 8080,
        "username": "admin",
        "password": "pw",
        "torrent_save_path": "/downloads",
        "downloader_type": 0,
        "fail_time": 0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture()
def import_env(tmp_path, monkeypatch):
    """导入端点环境：隔离 CWD + mock 下载器/manager/适配器。"""
    from app.api.endpoints import torrent_backup as tb_mod

    monkeypatch.chdir(tmp_path)

    def _make_client():
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id="1")
        return TestClient(app, raise_server_exceptions=False)

    client = _make_client()
    patchers = [
        patch.object(tb_mod, "get_downloader_from_store", return_value=_fake_downloader()),
        patch.object(
            tb_mod,
            "AsyncSessionLocal",
            new=lambda: _FakeSession(),
        ),
        patch.object(
            tb_mod.TorrentFileBackupManagerService,
            "backup_torrent_from_path",
            new=AsyncMock(return_value={"success": True, "backup_file_path": "/tmp/x.torrent"}),
        ),
    ]
    for p in patchers:
        p.start()
    yield client, tmp_path
    for p in patchers:
        p.stop()


class _FakeSession:
    """最小 AsyncSession 替身（manager 构造仅需可关闭的会话）。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def close(self):
        pass


class TestBackupImportFilenameSecurity:
    """导入端点多文件上传：穿越 filename 不出界、异常不残留。"""

    def test_traversal_filename_confined_to_request_dir(self, import_env):
        client, tmp_path = import_env
        payload = _valid_torrent_bytes()
        r = client.post(
            URL_IMPORT,
            params={"downloader_id": "dl-1"},
            files=[("files", ("../../evil.torrent", payload, "application/x-bittorrent"))],
        )
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == "200", r.text

        temp_root = tmp_path / "data" / "temp_imports"
        assert temp_root.exists(), "临时目录应存在"
        # 穿越文件绝不允许出现在 temp_imports 之外（如 backend/ 或 tmp 根）
        assert not (tmp_path / "evil.torrent").exists()
        assert not (tmp_path.parent / "evil.torrent").exists()
        # 所有落盘文件都在 uuid 子目录内，且无目录穿越产物
        for child in temp_root.iterdir():
            assert child.is_dir(), f"temp_imports 下只允许 uuid 子目录: {child.name}"
            for f in child.iterdir():
                assert f.name != "evil.torrent", "穿越文件名必须被消毒"

    def test_invalid_bencode_leaves_no_file_outside(self, import_env):
        """非 bencode 内容抛异常后不得留下越界文件（历史缺陷：异常跳过 unlink）。"""
        client, tmp_path = import_env
        r = client.post(
            URL_IMPORT,
            params={"downloader_id": "dl-1"},
            files=[("files", ("../../payload.dat", b"not-a-torrent", "application/octet-stream"))],
        )
        assert r.status_code == 200
        # 失败的导入不得在任何地方留下越界写入
        assert not (tmp_path / "payload.dat").exists()
        assert not (tmp_path.parent / "payload.dat").exists()

    def test_normal_filename_sanitized_and_processed(self, import_env):
        """正常文件名正常处理（回归基线）。"""
        client, tmp_path = import_env
        r = client.post(
            URL_IMPORT,
            params={"downloader_id": "dl-1"},
            files=[("files", ("normal.torrent", _valid_torrent_bytes(), "application/x-bittorrent"))],
        )
        assert r.json()["code"] == "200"


class TestBackupSourceSuffixGate:
    """POST /torrents/backup：source_file_path 非 .torrent 后缀 400。"""

    def _make_client(self):
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id="1")
        return TestClient(app, raise_server_exceptions=False)

    @pytest.mark.parametrize(
        "path",
        [
            "/etc/passwd",
            "/app/config/config.yaml",
            "C:/Windows/system32/drivers/etc/hosts",
            "backup/config.yaml",
        ],
    )
    def test_non_torrent_suffix_rejected(self, path):
        from app.api.endpoints import torrent_backup as tb_mod

        client = self._make_client()
        with patch.object(tb_mod, "get_downloader_from_store", return_value=_fake_downloader()):
            r = client.post(
                URL_BACKUP,
                json={
                    "info_hash": "a" * 40,
                    "torrent_name": "x",
                    "downloader_id": "dl-1",
                    "source_file_path": path,
                },
            )
        assert r.json()["code"] == "400"
        assert "source_file_path" in r.json()["msg"]

    def test_torrent_suffix_passes_gate(self):
        """.torrent 后缀通过第一道闸门（内容校验由 core 层测试覆盖）。"""
        from app.api.endpoints import torrent_backup as tb_mod

        fake_backup = SimpleNamespace(to_dict=lambda: {"info_hash": "a" * 40, "file_path": "/tmp/x.torrent"})
        client = self._make_client()
        with (
            patch.object(tb_mod, "get_downloader_from_store", return_value=_fake_downloader()),
            patch.object(tb_mod, "AsyncSessionLocal", new=lambda: _FakeSession()),
            patch.object(
                tb_mod.TorrentFileBackupManagerService,
                "backup_torrent_from_path",
                new=AsyncMock(
                    return_value={"success": True, "backup": fake_backup, "backup_file_path": "/tmp/x.torrent"}
                ),
            ),
        ):
            r = client.post(
                URL_BACKUP,
                json={
                    "info_hash": "a" * 40,
                    "torrent_name": "x",
                    "downloader_id": "dl-1",
                    "source_file_path": "/data/x.torrent",
                },
            )
        assert r.json()["code"] == "200"
