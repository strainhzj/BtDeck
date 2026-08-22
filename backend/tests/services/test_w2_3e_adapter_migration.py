# -*- coding: utf-8 -*-
"""
删除/位置下载器适配器迁移测试（sync-database-blocking-remediation W2-3e，P0-04 收尾）

覆盖 backend/app/services/downloader_adapters/ 下 4 个文件的 async 方法迁移：
- qbittorrent.py：_delete_torrents_impl / _delete_torrents_individually /
  validate_torrents_exist / get_torrent_info / test_connection / get_downloader_info /
  get_torrents_for_detection / add_tag_to_torrent / get_torrent_files
- transmission.py：_delete_torrents_impl（remove_torrent）
- qbittorrent_location.py / transmission_location.py：set_location

迁移方式：所有同步下载器调用改为 await asyncio.to_thread(...)（qbittorrent.py 用
lambda 包裹，保证 client property 懒建 Client(...) + auth.log_in() 也发生在工作线程，
不阻塞事件循环）。适配器无 downloader_id 属性且构造签名由工厂强制传缓存客户端，
因此不使用 call_downloader_api（避免改动工厂/调用方）。

每个迁移方法至少两条路径：
- 成功：客户端 mock 被调用，且调用发生在工作线程（非事件循环线程）——证明
  to_thread 真正生效，而非仅改写法。
- 异常映射保留：APIError / TransmissionError 等远程异常仍按迁移前语义处理
  （删除失败记录 failed_hashes、验证失败全部视为不存在、info 失败返回 None、
  test_connection 返回 False、set_location 返回 error_message 等）。
"""

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qbittorrentapi.exceptions import APIError
from transmission_rpc.error import TransmissionError

from app.services.downloader_adapters.qbittorrent import QBittorrentDeleteAdapter
from app.services.downloader_adapters.qbittorrent_location import QBittorrentLocationAdapter
from app.services.downloader_adapters.transmission import TransmissionDeleteAdapter
from app.services.downloader_adapters.transmission_location import TransmissionLocationAdapter
from app.services.torrent_deletion_service import DeleteOption, SafetyCheckLevel

HASH_A = "a" * 40
HASH_B = "b" * 40
ALL_HASHES = [HASH_A, HASH_B]


class _FakeTorrentFile:
    """模拟 qBittorrent torrent file 条目（get_torrent_files 使用 .name）"""

    def __init__(self, name):
        self.name = name


def _make_qb_torrent(hash_value, name="test", size=1024, state="seeding", progress=1.0):
    """构造 qBittorrent torrent 条目（SimpleNamespace，字段对齐 get_torrent_info 取值）。"""
    return SimpleNamespace(
        hash=hash_value,
        name=name,
        size=size,
        state=state,
        progress=progress,
        ratio=2.0,
        downloaded=size,
        uploaded=size * 2,
        save_path="/downloads",
        completion_on=123456,
        added_on=100000,
        category="",
        tags=[],
    )


def _qb_info_side_effect(hashes=None):
    """模拟 client.torrents.info：无参返回全部种子，带 hashes 参数返回子集。"""
    if hashes is None:
        return [_make_qb_torrent(h) for h in ALL_HASHES]
    return [_make_qb_torrent(h) for h in hashes if h in ALL_HASHES]


def _probe_thread(thread_names, key):
    """side_effect 工厂：记录远程调用发生的线程名（证明调用移出事件循环线程）。"""

    def _probe(*args, **kwargs):
        thread_names[key] = threading.current_thread().name

    return _probe


def _assert_ran_in_worker_thread(thread_names, key):
    """断言客户端调用已迁移：调用线程 != 事件循环（测试体）线程。"""
    loop_thread = threading.current_thread().name
    assert key in thread_names, f"客户端方法 {key} 未被调用"
    assert thread_names[key] != loop_thread, f"客户端调用 {key} 仍在事件循环线程执行（迁移失败）"


# =============================================================================
# QBittorrentDeleteAdapter：删除路径
# =============================================================================


async def test_qb_delete_torrents_success_batch_runs_in_thread():
    """成功批量删除：to_thread 生效（工作线程执行）+ 删除参数与结果语义不变。"""
    client = MagicMock()
    client.torrents.info.side_effect = _qb_info_side_effect
    thread_names = {}
    client.torrents.delete.side_effect = _probe_thread(thread_names, "delete")

    adapter = QBittorrentDeleteAdapter(client=client)
    result = await adapter.delete_torrents(ALL_HASHES, DeleteOption.DELETE_FILES_AND_TORRENT, SafetyCheckLevel.BASIC)

    assert result["success_hashes"] == ALL_HASHES
    assert result["deleted_files"] == ALL_HASHES
    assert result["failed_hashes"] == {}
    client.torrents.delete.assert_called_once_with(hashes=ALL_HASHES, delete_files=True, skip_other_check=True)
    _assert_ran_in_worker_thread(thread_names, "delete")


async def test_qb_delete_torrents_empty_list_no_client_call():
    """空列表：直接返回空结果，不触发任何下载器调用（幂等语义保留）。"""
    client = MagicMock()
    adapter = QBittorrentDeleteAdapter(client=client)
    result = await adapter.delete_torrents([], DeleteOption.DELETE_FILES_AND_TORRENT, SafetyCheckLevel.ENHANCED)

    assert result["success_hashes"] == []
    assert result["failed_hashes"] == {}
    client.torrents.delete.assert_not_called()
    client.torrents.info.assert_not_called()


async def test_qb_delete_torrents_all_missing_no_delete():
    """全部种子不存在：警告提示，不执行删除。"""
    client = MagicMock()
    client.torrents.info.return_value = []  # 下载器无任何种子
    adapter = QBittorrentDeleteAdapter(client=client)
    result = await adapter.delete_torrents([HASH_A], DeleteOption.DELETE_ONLY_TORRENT, SafetyCheckLevel.ENHANCED)

    assert result["success_hashes"] == []
    assert any("没有找到可删除的有效种子" in w for w in result["warnings"])
    client.torrents.delete.assert_not_called()


async def test_qb_delete_batch_failure_falls_back_to_individual_partial():
    """部分失败语义（迁移前行为）：批量删除抛 APIError → 逐个删除回退；
    单个失败记录 failed_hashes，其余成功。"""
    client = MagicMock()
    client.torrents.info.side_effect = _qb_info_side_effect
    thread_names = {}
    batch_attempted = {"count": 0}

    def _delete_side_effect(hashes=None, delete_files=None, skip_other_check=None):
        thread_names["delete"] = threading.current_thread().name
        if batch_attempted["count"] == 0:
            # 第一次调用是批量删除 → 失败，触发逐个删除回退
            batch_attempted["count"] += 1
            raise APIError("batch remote error")
        if hashes == [HASH_B]:
            raise APIError("single remote error")

    client.torrents.delete.side_effect = _delete_side_effect
    adapter = QBittorrentDeleteAdapter(client=client)
    result = await adapter.delete_torrents(ALL_HASHES, DeleteOption.DELETE_ONLY_TORRENT, SafetyCheckLevel.BASIC)

    assert result["success_hashes"] == [HASH_A]
    assert HASH_B in result["failed_hashes"]
    assert "single remote error" in result["failed_hashes"][HASH_B]
    _assert_ran_in_worker_thread(thread_names, "delete")


# =============================================================================
# QBittorrentDeleteAdapter：验证/信息/连接/标签/文件
# =============================================================================


async def test_qb_validate_torrents_exist_success():
    """验证存在性成功：命中/未命中映射正确。"""
    client = MagicMock()
    client.torrents.info.side_effect = _qb_info_side_effect
    adapter = QBittorrentDeleteAdapter(client=client)
    existence = await adapter.validate_torrents_exist([HASH_A, HASH_B, "c" * 40])

    assert existence == {HASH_A: True, HASH_B: True, "c" * 40: False}


async def test_qb_validate_torrents_exist_error_marks_all_missing():
    """验证失败（APIError）：按迁移前语义全部视为不存在，不抛出。"""
    client = MagicMock()
    client.torrents.info.side_effect = APIError("remote down")
    adapter = QBittorrentDeleteAdapter(client=client)
    existence = await adapter.validate_torrents_exist([HASH_A, HASH_B])

    assert existence == {HASH_A: False, HASH_B: False}


async def test_qb_get_torrent_info_success_and_error():
    """获取种子信息：成功返回字段映射；APIError → None（迁移前语义）。"""
    client = MagicMock()
    client.torrents.info.side_effect = _qb_info_side_effect
    adapter = QBittorrentDeleteAdapter(client=client)
    info = await adapter.get_torrent_info(HASH_A)

    assert info is not None
    assert info["hash"] == HASH_A
    assert info["name"] == "test"
    assert info["download_path"] == "/downloads"

    bad_client = MagicMock()
    bad_client.torrents.info.side_effect = APIError("remote down")
    assert await QBittorrentDeleteAdapter(client=bad_client).get_torrent_info(HASH_A) is None


async def test_qb_test_connection_success_and_error():
    """测试连接：成功 True；APIError → False（迁移前语义）。"""
    ok_client = MagicMock()
    ok_client.app.version.return_value = "v4.6.3"
    assert await QBittorrentDeleteAdapter(client=ok_client).test_connection() is True

    bad_client = MagicMock()
    bad_client.app.version.side_effect = APIError("connection refused")
    assert await QBittorrentDeleteAdapter(client=bad_client).test_connection() is False


async def test_qb_get_downloader_info_success_and_error():
    """下载器信息：成功返回 4 项探测结果；APIError → {}（迁移前语义）。"""
    ok_client = MagicMock()
    ok_client.app.preferences.return_value = {
        "save_path": "/dl",
        "temp_path": "/tmp",
        "max_conn_per_torrent": 5,
        "max_uploads_per_torrent": 2,
    }
    ok_client.app.version.return_value = "v4.6.3"
    ok_client.app.build_info.return_value = {"qt": "6.7"}
    ok_client.app.web_api_version.return_value = "2.10.1"
    info = await QBittorrentDeleteAdapter(client=ok_client).get_downloader_info()

    assert info["version"] == "v4.6.3"
    assert info["build_info"] == {"qt": "6.7"}
    assert info["web_api_version"] == "2.10.1"
    assert info["download_path"] == "/dl"
    assert info["max_connections"] == 5
    assert info["max_upload_slots"] == 2

    bad_client = MagicMock()
    bad_client.app.preferences.side_effect = APIError("remote down")
    assert await QBittorrentDeleteAdapter(client=bad_client).get_downloader_info() == {}


async def test_qb_get_torrents_for_detection_success_and_reraises():
    """重复检测列表：hash 标准化 + 无效 hash 跳过；APIError 原样抛出（迁移前语义）。"""
    ok_client = MagicMock()
    ok_client.torrents.info.return_value = [
        _make_qb_torrent(HASH_A),
        _make_qb_torrent("not-a-valid-hash", name="bad"),
    ]
    result = await QBittorrentDeleteAdapter(client=ok_client).get_torrents_for_detection()
    assert result == [{"hash": HASH_A, "name": "test", "size": 1024}]

    bad_client = MagicMock()
    bad_client.torrents.info.side_effect = APIError("remote down")
    with pytest.raises(APIError):
        await QBittorrentDeleteAdapter(client=bad_client).get_torrents_for_detection()


async def test_qb_add_tag_to_torrent_create_tag_failure_ignored():
    """添加标签：create_tags 失败（标签已存在）被忽略，add_tags 成功 → (True, "")。"""
    client = MagicMock()
    client.torrent_tags.create_tags.side_effect = APIError("tag exists")
    adapter = QBittorrentDeleteAdapter(client=client)
    ok, msg = await adapter.add_tag_to_torrent(HASH_A, "keep")

    assert ok is True
    assert msg == ""
    client.torrents_add_tags.assert_called_once_with(torrent_hashes=[HASH_A], tags=["keep"])


async def test_qb_add_tag_to_torrent_error_preserved():
    """添加标签失败（APIError）：返回 (False, 含错误信息)，不抛出。"""
    client = MagicMock()
    client.torrents_add_tags.side_effect = APIError("permission denied")
    adapter = QBittorrentDeleteAdapter(client=client)
    ok, msg = await adapter.add_tag_to_torrent(HASH_A, "keep")

    assert ok is False
    assert "permission denied" in msg


async def test_qb_get_torrent_files_success_and_error():
    """获取文件列表：成功返回相对路径列表；APIError → (False, None, 错误信息)。"""
    ok_client = MagicMock()
    ok_client.torrents.files.return_value = [_FakeTorrentFile("dir/a.mkv"), _FakeTorrentFile("dir/b.srt")]
    ok, file_list, err = await QBittorrentDeleteAdapter(client=ok_client).get_torrent_files(HASH_A)
    assert ok is True
    assert file_list == ["dir/a.mkv", "dir/b.srt"]
    assert err == ""

    bad_client = MagicMock()
    bad_client.torrents.files.side_effect = APIError("remote down")
    ok, file_list, err = await QBittorrentDeleteAdapter(client=bad_client).get_torrent_files(HASH_A)
    assert ok is False
    assert file_list is None
    assert "remote down" in err


async def test_qb_lazy_construction_happens_in_worker_thread():
    """构造懒建（client=None 兼容路径）：Client(...) + auth.log_in() 必须发生在工作线程，
    不阻塞事件循环。"""
    thread_names = {}
    fake_client = MagicMock()

    def _fake_client_ctor(*args, **kwargs):
        thread_names["construct"] = threading.current_thread().name
        return fake_client

    def _fake_log_in(*args, **kwargs):
        thread_names["login"] = threading.current_thread().name

    fake_client.auth.log_in.side_effect = _fake_log_in
    fake_client.app.version.return_value = "v5.0.0"

    with (
        patch("app.services.downloader_adapters.qbittorrent.Client", side_effect=_fake_client_ctor),
        patch("app.services.downloader_adapters.qbittorrent.decrypt_password", return_value="plain"),
    ):
        adapter = QBittorrentDeleteAdapter(
            client=None, host="127.0.0.1", username="admin", password="enc", port=8080, use_ssl=False
        )
        assert await adapter.test_connection() is True

    # 懒建与登录发生在同一工作线程，且不是事件循环（测试体）线程
    assert thread_names["construct"] == thread_names["login"]
    _assert_ran_in_worker_thread(thread_names, "login")


# =============================================================================
# TransmissionDeleteAdapter：删除路径
# =============================================================================


async def test_tr_delete_torrents_success_runs_in_thread():
    """成功删除：to_thread 生效（工作线程执行）+ remove_torrent 参数与结果语义不变。"""
    client = MagicMock()
    thread_names = {}
    client.remove_torrent.side_effect = _probe_thread(thread_names, "remove")

    adapter = TransmissionDeleteAdapter(client=client)
    adapter.get_torrent_info = AsyncMock(return_value={"state": "paused", "progress": 0.5, "ratio": 2.0, "size": 1024})
    result = await adapter.delete_torrents([HASH_A], DeleteOption.DELETE_FILES_AND_TORRENT, SafetyCheckLevel.BASIC)

    assert result["success_hashes"] == [HASH_A]
    assert result["deleted_files"] == [HASH_A]
    assert result["failed_hashes"] == {}
    client.remove_torrent.assert_called_once_with(ids=HASH_A, delete_data=True)
    _assert_ran_in_worker_thread(thread_names, "remove")


async def test_tr_delete_torrents_partial_failure():
    """部分失败语义（迁移前行为）：单个种子删除抛 TransmissionError 记录 failed_hashes，
    其余成功；不中断循环。"""
    client = MagicMock()
    thread_names = {}

    def _remove_side_effect(ids=None, delete_data=None):
        thread_names["remove"] = threading.current_thread().name
        if ids == HASH_B:
            raise TransmissionError("remote refused")

    client.remove_torrent.side_effect = _remove_side_effect
    adapter = TransmissionDeleteAdapter(client=client)
    adapter.get_torrent_info = AsyncMock(return_value={"state": "paused", "progress": 0.5, "ratio": 2.0, "size": 1024})
    result = await adapter.delete_torrents(ALL_HASHES, DeleteOption.DELETE_ONLY_TORRENT, SafetyCheckLevel.BASIC)

    assert result["success_hashes"] == [HASH_A]
    assert HASH_B in result["failed_hashes"]
    assert "remote refused" in result["failed_hashes"][HASH_B]
    _assert_ran_in_worker_thread(thread_names, "remove")


async def test_tr_delete_torrents_empty_list_no_client_call():
    """空列表：直接返回空结果，不触发任何下载器调用（幂等语义保留）。"""
    client = MagicMock()
    adapter = TransmissionDeleteAdapter(client=client)
    result = await adapter.delete_torrents([], DeleteOption.DELETE_ONLY_TORRENT, SafetyCheckLevel.ENHANCED)

    assert result["success_hashes"] == []
    assert result["failed_hashes"] == {}
    client.remove_torrent.assert_not_called()


# =============================================================================
# 位置修改适配器：set_location
# =============================================================================


async def test_qb_location_set_location_move_files_true_runs_in_thread():
    """qB 位置修改（移动文件）：torrents_set_location 在工作线程执行，参数与结果语义不变。"""
    client = MagicMock()
    thread_names = {}
    client.torrents_set_location.side_effect = _probe_thread(thread_names, "set_location")

    adapter = QBittorrentLocationAdapter(client=client)
    result = await adapter.set_location(ALL_HASHES, "/target", True)

    assert result["success"] is True
    assert result["moved_count"] == 2
    assert result["failed_count"] == 0
    client.torrents_set_location.assert_called_once_with(location="/target", torrent_hashes="|".join(ALL_HASHES))
    client.torrents_set_save_path.assert_not_called()
    _assert_ran_in_worker_thread(thread_names, "set_location")


async def test_qb_location_set_location_move_files_false():
    """qB 位置修改（不移动文件）：走 torrents_set_save_path 分支。"""
    client = MagicMock()
    adapter = QBittorrentLocationAdapter(client=client)
    result = await adapter.set_location([HASH_A], "/target", False)

    assert result["success"] is True
    assert result["moved_count"] == 1
    client.torrents_set_save_path.assert_called_once_with(save_path="/target", torrent_hashes=HASH_A)
    client.torrents_set_location.assert_not_called()


async def test_qb_location_set_location_error_preserved():
    """qB 位置修改失败（APIError）：返回 error_message + failed_count，不抛出。"""
    client = MagicMock()
    client.torrents_set_location.side_effect = APIError("path not writable")
    adapter = QBittorrentLocationAdapter(client=client)
    result = await adapter.set_location(ALL_HASHES, "/bad", True)

    assert result["success"] is False
    assert result["failed_count"] == 2
    assert "path not writable" in result["error_message"]


async def test_tr_location_set_location_success_runs_in_thread():
    """TR 位置修改成功：move_torrent_data 在工作线程执行，参数与结果语义不变。"""
    client = MagicMock()
    thread_names = {}
    client.move_torrent_data.side_effect = _probe_thread(thread_names, "move")

    adapter = TransmissionLocationAdapter(client=client)
    result = await adapter.set_location(ALL_HASHES, "/target", True)

    assert result["success"] is True
    assert result["moved_count"] == 2
    assert result["failed_count"] == 0
    client.move_torrent_data.assert_called_once_with(ids=ALL_HASHES, location="/target", move=True)
    _assert_ran_in_worker_thread(thread_names, "move")


async def test_tr_location_set_location_error_preserved():
    """TR 位置修改失败（TransmissionError）：返回 error_message + failed_count，不抛出。"""
    client = MagicMock()
    client.move_torrent_data.side_effect = TransmissionError("no such dir")
    adapter = TransmissionLocationAdapter(client=client)
    result = await adapter.set_location([HASH_A], "/bad", False)

    assert result["success"] is False
    assert result["failed_count"] == 1
    assert "no such dir" in result["error_message"]
