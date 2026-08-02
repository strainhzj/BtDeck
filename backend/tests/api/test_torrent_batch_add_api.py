"""批量添加种子后台任务接口测试。"""

import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, UploadFile

from app.api.endpoints import torrent_crud
from app.services.torrent_batch_add_service import (
    StagedTorrentFile,
    TorrentBatchAddOptions,
    _create_completion_notification,
)


@pytest.mark.asyncio
async def test_batch_add_accepts_more_than_ten_files_and_returns_immediately(tmp_path, monkeypatch):
    """批量接口不再限制数量，并在后台任务提交后立即返回 202。"""

    app = FastAPI()

    class Store:
        async def get_snapshot(self):
            return [SimpleNamespace(downloader_id="dl-1", fail_time=0, client=object())]

    app.state.store = Store()
    request = SimpleNamespace(app=app)
    staged_files = [
        StagedTorrentFile(file_name=f"test-{index}.torrent", file_path=str(tmp_path / f"test-{index}.torrent"))
        for index in range(11)
    ]
    staged_iterator = iter(staged_files)

    async def fake_stage(_upload_file):
        return next(staged_iterator)

    async def fake_process(*_args, **_kwargs):
        return None

    monkeypatch.setattr(torrent_crud, "stage_torrent_file", fake_stage)
    monkeypatch.setattr(torrent_crud, "process_torrent_batch_job", fake_process)

    files = [UploadFile(filename=staged.file_name, file=BytesIO(b"torrent")) for staged in staged_files]
    response = await torrent_crud.create_torrents_batch(
        _user=SimpleNamespace(username="tester"),
        request=request,
        torrent_files=files,
        downloader_id="dl-1",
        save_path="/downloads",
        tags="",
        category="",
        paused=False,
        skip_hash_check=False,
        is_sequential_download=False,
        is_first_last_piece_priority=False,
        upload_limit=False,
        download_limit=False,
        db=MagicMock(),
    )

    assert response.code == "202"
    assert response.data["status"] == "queued"
    assert response.data["total"] == 11

    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_batch_add_completion_notification_contains_failure_details():
    """完成通知包含成功/失败数量和失败文件，供通知中心展示。"""

    options = TorrentBatchAddOptions(
        downloader_id="dl-1",
        save_path="/downloads",
        tags="",
        category="",
        paused=False,
        skip_hash_check=False,
        is_sequential_download=False,
        is_first_last_piece_priority=False,
        upload_limit=None,
        download_limit=None,
        operator="tester",
        audit_info={},
    )
    service = MagicMock()
    service.create_notification = AsyncMock()

    class SessionContext:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *_args):
            return None

    results = [
        {"file_name": "ok.torrent", "success": True, "info_id": "info-1", "error": None},
        {"file_name": "bad.torrent", "success": False, "info_id": None, "error": "解析失败"},
    ]

    with (
        patch("app.services.torrent_batch_add_service.AsyncSessionLocal", return_value=SessionContext()),
        patch("app.services.torrent_batch_add_service.NotificationService", return_value=service),
    ):
        await _create_completion_notification("task-1", options, results)

    service.create_notification.assert_awaited_once()
    notification_kwargs = service.create_notification.await_args.kwargs
    assert notification_kwargs["priority"] == "warning"
    assert notification_kwargs["extra_data"]["task_id"] == "task-1"
    assert notification_kwargs["extra_data"]["success_count"] == 1
    assert notification_kwargs["extra_data"]["failed_list"] == [{"file_name": "bad.torrent", "reason": "解析失败"}]
