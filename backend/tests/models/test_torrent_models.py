"""
TorrentInfo 和 TrackerInfo 模型单元测试

测试 TorrentInfo 和 TrackerInfo 的实例方法：
- to_dict: 转换为字典
- get_deleted_at_formatted: 格式化删除时间
- is_deleted: 检查删除状态
- get_original_filename_safe: 获取原始文件名
- soft_delete: 软删除（等级3删除）
- restore_from_recycle_bin: 从回收站还原

所有测试使用 __new__ + 手动属性设置绕过 ORM 初始化。
"""

from datetime import datetime
import pytest
from unittest.mock import patch


# ============================================================
# 辅助工具
# ============================================================

def _make_torrent_info(**kwargs):
    """创建 TorrentInfo 轻量级对象，绕过 ORM 初始化"""
    from app.torrents.models import TorrentInfo
    from unittest.mock import MagicMock

    # 默认值
    defaults = {
        "info_id": "test-info-id",
        "downloader_id": "dl-001",
        "downloader_name": "测试下载器",
        "torrent_id": "torrent-001",
        "hash": "abc123",
        "name": "测试种子",
        "save_path": "/downloads/",
        "size": 1024 * 1024 * 1024,
        "status": "downloading",
        "progress": 50.0,
        "torrent_file": "test.torrent",
        "added_date": datetime(2026, 1, 1, 12, 0, 0),
        "completed_date": None,
        "ratio": "1.5",
        "ratio_limit": "2.0",
        "tags": "电影,高清",
        "category": "movies",
        "super_seeding": False,
        "enabled": True,
        "create_time": datetime(2026, 1, 1, 10, 0, 0),
        "create_by": "admin",
        "update_time": datetime(2026, 1, 1, 10, 0, 0),
        "update_by": "admin",
        "dr": 0,
        "deleted_at": None,
        "original_filename": None,
        "backup_file_path": None,
        "original_file_list": None,
        "has_tracker_error": False,
    }
    defaults.update(kwargs)

    # 创建 mock 对象并设置属性
    info = MagicMock(spec=TorrentInfo)
    for key, value in defaults.items():
        setattr(info, key, value)

    # 绑定方法
    info.to_dict = TorrentInfo.to_dict.__get__(info, TorrentInfo)
    info.get_deleted_at_formatted = TorrentInfo.get_deleted_at_formatted.__get__(info, TorrentInfo)
    info.is_deleted = TorrentInfo.is_deleted.__get__(info, TorrentInfo)
    info.get_original_filename_safe = TorrentInfo.get_original_filename_safe.__get__(info, TorrentInfo)
    info.soft_delete = TorrentInfo.soft_delete.__get__(info, TorrentInfo)
    info.restore_from_recycle_bin = TorrentInfo.restore_from_recycle_bin.__get__(info, TorrentInfo)

    return info


def _make_tracker_info(**kwargs):
    """创建 TrackerInfo 轻量级对象"""
    from app.torrents.models import TrackerInfo
    from unittest.mock import MagicMock

    defaults = {
        "tracker_id": "tracker-001",
        "torrent_info_id": "test-info-id",
        "tracker_name": "测试Tracker",
        "tracker_url": "http://tracker.example.com/announce",
        "last_announce_succeeded": 1,
        "last_announce_msg": "Success",
        "last_scrape_succeeded": 1,
        "last_scrape_msg": "OK",
        "tracker_host": "tracker.example.com",
        "status": "normal",
        "msg": None,
        "seeder_count": 10,
        "leecher_count": 5,
        "download_count": 100,
        "create_time": datetime(2026, 1, 1, 10, 0, 0),
        "create_by": "admin",
        "update_time": datetime(2026, 1, 1, 10, 0, 0),
        "update_by": "admin",
        "dr": 0,
        "version": 0,
    }
    defaults.update(kwargs)

    # 创建 mock 对象并设置属性
    info = MagicMock(spec=TrackerInfo)
    for key, value in defaults.items():
        setattr(info, key, value)

    # 绑定方法
    info.to_dict = TrackerInfo.to_dict.__get__(info, TrackerInfo)

    return info


# ============================================================
# TorrentInfo.to_dict 测试
# ============================================================

class TestTorrentInfoToDict:
    """TorrentInfo.to_dict 方法测试"""

    def test_返回包含所有字段(self):
        """to_dict 应返回包含所有字段的字典"""
        info = _make_torrent_info()
        result = info.to_dict()

        # 验证所有关键字段存在
        expected_keys = {
            "info_id", "downloader_id", "downloader_name", "torrent_id",
            "hash", "name", "save_path", "size", "status", "progress",
            "torrent_file", "added_date", "completed_date", "ratio", "ratio_limit",
            "tags", "category", "super_seeding", "enabled", "create_time",
            "create_by", "update_time", "update_by", "dr", "deleted_at",
            "original_filename", "backup_file_path", "original_file_list",
            "has_tracker_error",
        }
        assert set(result.keys()) == expected_keys

    def test_值正确映射(self):
        """所有字段值应正确映射"""
        info = _make_torrent_info(
            name="特定种子",
            size=2048,
            status="seeding",
        )
        result = info.to_dict()

        assert result["name"] == "特定种子"
        assert result["size"] == 2048
        assert result["status"] == "seeding"


# ============================================================
# get_deleted_at_formatted 测试
# ============================================================

class TestGetDeletedAtFormatted:
    """get_deleted_at_formatted 方法测试"""

    def test_deleted_at为None返回None(self):
        """deleted_at 为 None 时应返回 None"""
        info = _make_torrent_info(deleted_at=None)
        assert info.get_deleted_at_formatted() is None

    def test_deleted_at为datetime返回格式化字符串(self):
        """deleted_at 为 datetime 时应返回格式化字符串"""
        dt = datetime(2026, 4, 3, 14, 30, 0)
        info = _make_torrent_info(deleted_at=dt)
        result = info.get_deleted_at_formatted()
        assert result == "2026-04-03 14:30:00"

    def test_deleted_at为字符串自动转换(self):
        """deleted_at 为字符串时应自动转换为 datetime 再格式化"""
        info = _make_torrent_info(deleted_at="2026-04-03 14:30:00")
        result = info.get_deleted_at_formatted()
        assert result == "2026-04-03 14:30:00"

    def test_deleted_at为无效字符串返回None(self):
        """deleted_at 为无效字符串时应返回 None"""
        info = _make_torrent_info(deleted_at="invalid-date")
        result = info.get_deleted_at_formatted()
        assert result is None

    def test自定义日期格式(self):
        """自定义日期格式应正确格式化"""
        dt = datetime(2026, 4, 3, 14, 30, 0)
        info = _make_torrent_info(deleted_at=dt)
        result = info.get_deleted_at_formatted("%Y/%m/%d")
        assert result == "2026/04/03"


# ============================================================
# is_deleted 测试
# ============================================================

class TestIsDeleted:
    """is_deleted 方法测试"""

    def test_deleted_at有值返回True(self):
        """deleted_at 有值时应返回 True"""
        info = _make_torrent_info(
            deleted_at=datetime(2026, 4, 3, 14, 30, 0)
        )
        assert info.is_deleted() is True

    def test_deleted_at为None返回False(self):
        """deleted_at 为 None 时应返回 False"""
        info = _make_torrent_info(deleted_at=None)
        assert info.is_deleted() is False


# ============================================================
# get_original_filename_safe 测试
# ============================================================

class TestGetOriginalFilenameSafe:
    """get_original_filename_safe 方法测试"""

    def test_original_filename有值返回原值(self):
        """original_filename 有值时应返回原值"""
        info = _make_torrent_info(
            original_filename="original.torrent"
        )
        assert info.get_original_filename_safe() == "original.torrent"

    def test_original_filename为None且name有值返回name(self):
        """original_filename 为 None 且 name 有值时应返回 name"""
        info = _make_torrent_info(
            original_filename=None,
            name="current.torrent"
        )
        assert info.get_original_filename_safe() == "current.torrent"

    def test两者都为None返回空字符串(self):
        """original_filename 和 name 都为 None 时应返回空字符串"""
        info = _make_torrent_info(
            original_filename=None,
            name=None
        )
        assert info.get_original_filename_safe() == ""


# ============================================================
# soft_delete 测试
# ============================================================

class TestSoftDelete:
    """soft_delete 方法测试"""

    def test_save_original_filename为True保存文件名(self):
        """save_original_filename=True 时应保存原始文件名"""
        info = _make_torrent_info(
            name="current.torrent",
            original_filename=None,
            deleted_at=None,
        )
        info.soft_delete(save_original_filename=True)

        assert info.deleted_at is not None
        assert info.original_filename == "current.torrent"

    def test_save_original_filename为False不覆盖已有文件名(self):
        """save_original_filename=False 且已有 original_filename 时不覆盖"""
        info = _make_torrent_info(
            original_filename="existing.torrent",
            deleted_at=None,
        )
        original = info.original_filename
        info.soft_delete(save_original_filename=False)

        assert info.deleted_at is not None
        assert info.original_filename == "existing.torrent"

    def test_soft_delete不修改dr字段(self):
        """soft_delete 不应修改 dr 字段"""
        info = _make_torrent_info(dr=0, deleted_at=None)
        info.soft_delete()
        assert info.dr == 0

    def test_soft_delete设置deleted_at(self):
        """soft_delete 应设置 deleted_at 为当前时间"""
        before = datetime.now()
        info = _make_torrent_info(deleted_at=None)
        info.soft_delete()
        after = datetime.now()

        assert info.deleted_at is not None
        assert before <= info.deleted_at <= after


# ============================================================
# restore_from_recycle_bin 测试
# ============================================================

class TestRestoreFromRecycleBin:
    """restore_from_recycle_bin 方法测试"""

    def test_还原重置deleted_at和dr(self):
        """还原应重置 deleted_at 为 None，dr 为 0"""
        info = _make_torrent_info(
            deleted_at=datetime(2026, 4, 3, 14, 30, 0),
            dr=1
        )
        info.restore_from_recycle_bin()

        assert info.deleted_at is None
        assert info.dr == 0


# ============================================================
# TrackerInfo.to_dict 测试
# ============================================================

class TestTrackerInfoToDict:
    """TrackerInfo.to_dict 方法测试"""

    def test_返回包含所有字段(self):
        """to_dict 应返回包含所有字段的字典"""
        info = _make_tracker_info()
        result = info.to_dict()

        # 验证关键字段
        expected_keys = {
            "tracker_id", "torrent_info_id", "tracker_name", "tracker_url",
            "last_announce_succeeded", "last_announce_msg", "last_scrape_succeeded",
            "last_scrape_msg", "tracker_host", "status", "msg",
            "seeder_count", "leecher_count", "download_count",
            "create_time", "create_by", "update_time", "update_by",
            "dr", "version",
        }
        assert set(result.keys()) == expected_keys

    def test_值正确映射(self):
        """所有字段值应正确映射"""
        info = _make_tracker_info(
            tracker_name="特定Tracker",
            seeder_count=99,
            status="error",
        )
        result = info.to_dict()

        assert result["tracker_name"] == "特定Tracker"
        assert result["seeder_count"] == 99
        assert result["status"] == "error"
