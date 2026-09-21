# -*- coding: utf-8 -*-
"""定时任务与主机能力门禁回归。"""

import pytest

from app.core.platform_capabilities import (
    PLATFORM_ANDROID_SERVER,
    PlatformCapabilityUnsupportedError,
    require_capability,
)
from app.tasks.task_capabilities import (
    PLATFORM_CAPABILITY_SKIP_REASON,
    capability_block_for_task,
    required_capability_for_task,
)


def test_path_and_orphan_tasks_are_blocked_on_android(monkeypatch):
    monkeypatch.setenv("BTDECK_PLATFORM", PLATFORM_ANDROID_SERVER)

    assert required_capability_for_task({"task_code": "downloader_path_scan"}) == "path_mapping"
    assert required_capability_for_task({"task_code": "orphan_scan_cleanup"}) == "orphan_files"

    block = capability_block_for_task({"task_code": "orphan_scan_cleanup"})
    assert block == {
        "capability": "orphan_files",
        "reason_code": PLATFORM_CAPABILITY_SKIP_REASON,
        "message": "当前主机形态不支持任务所需能力: orphan_files",
    }


def test_level3_cleanup_is_the_only_cleanup_level_blocked(monkeypatch):
    monkeypatch.setenv("BTDECK_PLATFORM", PLATFORM_ANDROID_SERVER)

    assert (
        required_capability_for_task(
            {
                "task_type": 5,
                "executor": '{"cleanup_level_3": true, "cleanup_level_4": true}',
            }
        )
        == "level3_recycle"
    )
    assert (
        capability_block_for_task(
            {"task_type": 5, "executor": '{"cleanup_level_3": true}'},
        )["capability"]
        == "level3_recycle"
    )
    assert (
        capability_block_for_task(
            {"task_type": 5, "executor": '{"cleanup_level_4": true}'},
        )
        is None
    )


def test_desktop_keeps_all_file_system_task_capabilities(monkeypatch):
    monkeypatch.setenv("BTDECK_PLATFORM", "desktop")

    for task_code in ("downloader_path_scan", "orphan_scan_cleanup"):
        assert capability_block_for_task({"task_code": task_code}) is None
    assert (
        capability_block_for_task(
            {"task_type": 5, "executor": '{"cleanup_level_3": true}'},
        )
        is None
    )


@pytest.mark.parametrize(
    "capability",
    [
        "path_mapping",
        "orphan_files",
        "torrent_backup",
        "seed_transfer",
        "level3_recycle",
    ],
)
def test_require_capability_raises_with_operation(monkeypatch, capability):
    monkeypatch.setenv("BTDECK_PLATFORM", PLATFORM_ANDROID_SERVER)

    with pytest.raises(PlatformCapabilityUnsupportedError) as exc_info:
        require_capability(capability, "test.operation")

    error = exc_info.value
    assert error.capability == capability
    assert error.operation == "test.operation"
    assert error.platform == PLATFORM_ANDROID_SERVER
