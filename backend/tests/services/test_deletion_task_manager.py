# -*- coding: utf-8 -*-
"""异步种子删除任务的数据占用与查询排除回归测试。"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.deletion_task_manager as manager_module
from app.database import Base
from app.services.deletion_task_manager import (
    DeletionTaskManager,
    TaskStatus,
    build_active_deletion_exclusion,
)
from app.torrents.models import TorrentInfo
from tests.api.conftest import make_torrent

pytestmark = pytest.mark.asyncio


@pytest.fixture
def deletion_manager(monkeypatch):
    """隔离模块级单例，并禁用与断言无关的定时清理协程。"""
    original_manager = manager_module._manager
    original_instance = DeletionTaskManager._instance
    monkeypatch.setattr(DeletionTaskManager, "_start_cleanup_task", lambda self: None)
    manager_module._manager = None
    DeletionTaskManager._instance = None
    manager = manager_module.get_deletion_task_manager()
    try:
        yield manager
    finally:
        manager_module._manager = original_manager
        DeletionTaskManager._instance = original_instance


async def test_concurrent_submissions_reserve_each_info_id_once(deletion_manager):
    first, second = await asyncio.gather(
        deletion_manager.create_task_reserving(
            ["shared", "left"],
            delete_level=2,
            operator="tester-a",
        ),
        deletion_manager.create_task_reserving(
            ["shared", "right"],
            delete_level=2,
            operator="tester-b",
        ),
    )

    accepted = first.accepted_info_ids + second.accepted_info_ids
    skipped = first.skipped_info_ids + second.skipped_info_ids
    assert accepted.count("shared") == 1
    assert skipped.count("shared") == 1
    assert set(accepted) == {"shared", "left", "right"}
    assert deletion_manager.get_active_torrent_info_ids_snapshot() == {
        "shared",
        "left",
        "right",
    }


async def test_mixed_submission_skips_active_and_terminal_status_releases_ids(
    deletion_manager,
):
    first = await deletion_manager.create_task_reserving(
        ["a", "b"],
        delete_level=2,
        operator="tester",
    )
    mixed = await deletion_manager.create_task_reserving(
        ["b", "c"],
        delete_level=2,
        operator="tester",
    )
    all_active = await deletion_manager.create_task_reserving(
        ["a", "b", "c"],
        delete_level=2,
        operator="tester",
    )

    assert first.task_id is not None
    assert mixed.accepted_info_ids == ["c"]
    assert mixed.skipped_info_ids == ["b"]
    assert all_active.task_id is None
    assert all_active.skipped_info_ids == ["a", "b", "c"]

    assert await deletion_manager.update_task_status(first.task_id, TaskStatus.FAILED)
    retry = await deletion_manager.create_task_reserving(
        ["a", "b"],
        delete_level=2,
        operator="tester",
    )
    assert retry.accepted_info_ids == ["a", "b"]
    assert retry.skipped_info_ids == []


async def test_query_exclusion_uses_one_json_binding_for_large_active_set(
    deletion_manager,
):
    active_ids = [f"active-{index}" for index in range(1200)]
    await deletion_manager.create_task_reserving(
        active_ids,
        delete_level=2,
        operator="tester",
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[TorrentInfo.__table__])
    db = sessionmaker(bind=engine)()
    try:
        make_torrent(
            db,
            info_id="active-1199",
            downloader_id="dl-a",
            hash_="hash-active",
            name="active",
        )
        make_torrent(
            db,
            info_id="available",
            downloader_id="dl-a",
            hash_="hash-available",
            name="available",
        )
        condition = build_active_deletion_exclusion(TorrentInfo.info_id)
        assert condition is not None

        visible_ids = {
            row.info_id for row in db.query(TorrentInfo).filter(condition).all()
        }
        assert visible_ids == {"available"}
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=[TorrentInfo.__table__])
        engine.dispose()
