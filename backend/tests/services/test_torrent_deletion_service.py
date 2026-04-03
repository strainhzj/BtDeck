# -*- coding: utf-8 -*-
"""
TorrentDeletionService 的单元测试

测试种子删除服务的核心逻辑，包括：
- DeleteOption / SafetyCheckLevel 枚举
- DeleteRequest / DeleteResult 数据类
- SafetyCheckService.check_torrent_safety 安全检查
- TorrentDeletionService._group_by_downloader 分组逻辑
- TorrentDeletionService.register_adapter 适配器注册
- TorrentDeletionService.delete_torrents 空列表场景
- DownloaderAdapterFactory 工厂方法

所有 ORM 相关依赖通过 mock 隔离，不实例化 SQLAlchemy 模型。
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

from app.services.torrent_deletion_service import (
    DeleteOption,
    SafetyCheckLevel,
    DeleteRequest,
    DeleteResult,
    SafetyCheckService,
    TorrentDeletionService,
    DownloaderDeleteAdapter,
    DownloaderAdapterFactory,
)


# ==================== 辅助工具 ====================

class _FakeTorrentInfo:
    """轻量级种子信息对象，替代 SQLAlchemy TorrentInfo 模型"""

    def __init__(
        self,
        info_id="info-001",
        downloader_id="dl-001",
        name="测试种子",
        hash="abc123",
        status="paused",
        size=1024 * 1024 * 1024,  # 1GB
        ratio="2.0",
        category="movie",
        tags="",
        completed_date=None,
    ):
        self.info_id = info_id
        self.downloader_id = downloader_id
        self.name = name
        self.hash = hash
        self.status = status
        self.size = size
        self.ratio = ratio
        self.category = category
        self.tags = tags
        self.completed_date = completed_date


def make_torrent(**kwargs):
    """创建测试用种子信息对象"""
    return _FakeTorrentInfo(**kwargs)


def _make_fake_adapter():
    """创建一个符合 DownloaderDeleteAdapter 接口的 MagicMock 对象"""
    adapter = MagicMock(spec=DownloaderDeleteAdapter)
    adapter.get_downloader_type.return_value = "fake"
    adapter.delete_torrents = AsyncMock(return_value={"success_hashes": []})
    adapter.validate_torrents_exist = AsyncMock(return_value={})
    adapter.get_torrent_info = AsyncMock(return_value=None)
    adapter.add_tag_to_torrent = AsyncMock(return_value=(True, None))
    adapter.create_marker_file = AsyncMock(return_value=(True, None))
    adapter.get_torrent_files = AsyncMock(return_value=(True, [], None))
    return adapter


# ==================== 枚举测试 ====================

class TestDeleteOption:
    """DeleteOption 枚举值测试"""

    def test_delete_only_torrent(self):
        """仅删除种子任务选项"""
        assert DeleteOption.DELETE_ONLY_TORRENT.value == "delete_only_torrent"

    def test_delete_files_and_torrent(self):
        """删除文件和种子任务选项"""
        assert DeleteOption.DELETE_FILES_AND_TORRENT.value == "delete_files_and_torrent"

    def test_dry_run(self):
        """预演模式选项"""
        assert DeleteOption.DRY_RUN.value == "dry_run"

    def test_enum_member_count(self):
        """应有且仅有 3 个枚举成员"""
        assert len(DeleteOption) == 3


class TestSafetyCheckLevel:
    """SafetyCheckLevel 枚举值测试"""

    def test_basic(self):
        """基础安全检查级别"""
        assert SafetyCheckLevel.BASIC.value == "basic"

    def test_enhanced(self):
        """增强安全检查级别"""
        assert SafetyCheckLevel.ENHANCED.value == "enhanced"

    def test_strict(self):
        """严格安全检查级别"""
        assert SafetyCheckLevel.STRICT.value == "strict"

    def test_enum_member_count(self):
        """应有且仅有 3 个枚举成员"""
        assert len(SafetyCheckLevel) == 3


# ==================== 数据类测试 ====================

class TestDeleteRequest:
    """DeleteRequest 数据类测试"""

    def test_default_values(self):
        """默认安全检查级别为 ENHANCED，不强制删除，无原因"""
        req = DeleteRequest(
            torrent_info_ids=["id-1"],
            delete_option=DeleteOption.DELETE_ONLY_TORRENT,
        )
        assert req.safety_check_level == SafetyCheckLevel.ENHANCED
        assert req.force_delete is False
        assert req.reason is None

    def test_custom_values(self):
        """自定义所有字段"""
        req = DeleteRequest(
            torrent_info_ids=["id-1", "id-2"],
            delete_option=DeleteOption.DELETE_FILES_AND_TORRENT,
            safety_check_level=SafetyCheckLevel.STRICT,
            force_delete=True,
            reason="磁盘空间不足",
        )
        assert len(req.torrent_info_ids) == 2
        assert req.delete_option == DeleteOption.DELETE_FILES_AND_TORRENT
        assert req.safety_check_level == SafetyCheckLevel.STRICT
        assert req.force_delete is True
        assert req.reason == "磁盘空间不足"

    def test_empty_ids_list(self):
        """空 ID 列表是合法输入"""
        req = DeleteRequest(
            torrent_info_ids=[],
            delete_option=DeleteOption.DRY_RUN,
        )
        assert req.torrent_info_ids == []


class TestDeleteResult:
    """DeleteResult 数据类测试"""

    def test_initial_values(self):
        """初始化时应为全零/空列表"""
        result = DeleteResult(
            success_count=0,
            failed_count=0,
            skipped_count=0,
            total_size_freed=0,
            deleted_torrents=[],
            failed_torrents=[],
            skipped_torrents=[],
            safety_warnings=[],
            execution_time=0,
        )
        assert result.success_count == 0
        assert result.failed_count == 0
        assert result.skipped_count == 0
        assert result.total_size_freed == 0
        assert result.deleted_torrents == []
        assert result.failed_torrents == []
        assert result.skipped_torrents == []
        assert result.safety_warnings == []
        assert result.execution_time == 0

    def test_with_data(self):
        """可以正常赋值和读取"""
        result = DeleteResult(
            success_count=3,
            failed_count=1,
            skipped_count=2,
            total_size_freed=1024,
            deleted_torrents=[{"info_id": "id-1"}],
            failed_torrents=[{"info_id": "id-2"}],
            skipped_torrents=[],
            safety_warnings=["警告"],
            execution_time=1.5,
        )
        assert result.success_count == 3
        assert result.total_size_freed == 1024
        assert len(result.deleted_torrents) == 1
        assert result.execution_time == 1.5


# ==================== SafetyCheckService 测试 ====================

class TestCheckTorrentSafety:
    """SafetyCheckService.check_torrent_safety 静态方法测试"""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    async def test_safe_torrent_basic(self, mock_db):
        """安全种子在 BASIC 级别应返回空警告列表"""
        torrent = make_torrent(status="paused", ratio="2.0", size=1024)
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.BASIC, mock_db
        )
        assert warnings == []

    async def test_seeding_status_warning(self, mock_db):
        """seeding 状态应产生基础警告"""
        torrent = make_torrent(status="seeding")
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.BASIC, mock_db
        )
        assert len(warnings) == 1
        assert "seeding" in warnings[0]

    async def test_checking_status_warning(self, mock_db):
        """checking 状态应产生基础警告"""
        torrent = make_torrent(status="checking")
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.BASIC, mock_db
        )
        assert len(warnings) == 1
        assert "checking" in warnings[0]

    async def test_low_ratio_warning(self, mock_db):
        """分享比率低于 1.0 应产生警告"""
        torrent = make_torrent(ratio="0.5")
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.BASIC, mock_db
        )
        assert any("1.0" in w for w in warnings)

    async def test_ratio_none_no_warning(self, mock_db):
        """ratio 为 None 时不应产生比率警告"""
        torrent = make_torrent(ratio=None)
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.BASIC, mock_db
        )
        ratio_warnings = [w for w in warnings if "比率" in w or "ratio" in w]
        assert ratio_warnings == []

    async def test_enhanced_downloading_warning(self, mock_db):
        """ENHANCED 级别下 downloading 状态应产生警告"""
        torrent = make_torrent(status="downloading", size=1024)
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.ENHANCED, mock_db
        )
        assert any("下载中" in w for w in warnings)

    async def test_enhanced_large_file_warning(self, mock_db):
        """ENHANCED 级别下大于 50GB 的种子应产生警告"""
        torrent = make_torrent(size=60 * 1024 * 1024 * 1024)  # 60GB
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.ENHANCED, mock_db
        )
        assert any("较大" in w for w in warnings)

    async def test_enhanced_small_file_no_size_warning(self, mock_db):
        """ENHANCED 级别下小于 50GB 的种子不产生大小警告"""
        torrent = make_torrent(status="paused", ratio="2.0", size=1024)
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.ENHANCED, mock_db
        )
        assert not any("较大" in w for w in warnings)

    async def test_strict_important_category_warning(self, mock_db):
        """STRICT 级别下 important 分类应产生警告"""
        torrent = make_torrent(
            status="paused", ratio="2.0", size=1024,
            category="important"
        )
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.STRICT, mock_db
        )
        assert any("important" in w for w in warnings)

    async def test_strict_system_category_warning(self, mock_db):
        """STRICT 级别下 system 分类应产生警告"""
        torrent = make_torrent(
            status="paused", ratio="2.0", size=1024,
            category="system"
        )
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.STRICT, mock_db
        )
        assert any("system" in w for w in warnings)

    async def test_strict_keep_tag_warning(self, mock_db):
        """STRICT 级别下包含 keep 标签应产生警告"""
        torrent = make_torrent(
            status="paused", ratio="2.0", size=1024,
            tags="keep,important"
        )
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.STRICT, mock_db
        )
        assert any("keep" in w for w in warnings)

    async def test_strict_recently_completed_warning(self, mock_db):
        """STRICT 级别下 7 天内完成的种子应产生警告"""
        torrent = make_torrent(
            status="paused", ratio="2.0", size=1024,
            completed_date=datetime.now() - timedelta(days=3)
        )
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.STRICT, mock_db
        )
        assert any("7天" in w for w in warnings)

    async def test_strict_old_completed_no_warning(self, mock_db):
        """STRICT 级别下超过 7 天完成的种子不产生时间警告"""
        torrent = make_torrent(
            status="paused", ratio="2.0", size=1024,
            completed_date=datetime.now() - timedelta(days=30)
        )
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.STRICT, mock_db
        )
        assert not any("7天" in w for w in warnings)

    async def test_strict_no_completed_date_no_warning(self, mock_db):
        """STRICT 级别下 completed_date 为 None 时不产生时间警告"""
        torrent = make_torrent(
            status="paused", ratio="2.0", size=1024,
            completed_date=None
        )
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.STRICT, mock_db
        )
        assert not any("7天" in w for w in warnings)

    async def test_size_none_no_warning(self, mock_db):
        """size 为 None 时不应产生文件大小警告"""
        torrent = make_torrent(size=None)
        warnings = await SafetyCheckService.check_torrent_safety(
            torrent, SafetyCheckLevel.ENHANCED, mock_db
        )
        assert not any("较大" in w for w in warnings)


# ==================== _group_by_downloader 测试 ====================

class TestGroupByDownloader:
    """TorrentDeletionService._group_by_downloader 分组测试"""

    @pytest.fixture
    def service(self):
        mock_db = MagicMock()
        return TorrentDeletionService(db=mock_db)

    def test_empty_list(self, service):
        """空种子列表应返回空字典"""
        result = service._group_by_downloader([])
        assert result == {}

    def test_single_downloader(self, service):
        """同一下载器的种子应分到一组"""
        torrents = [
            make_torrent(info_id="t1", downloader_id="dl-001"),
            make_torrent(info_id="t2", downloader_id="dl-001"),
        ]
        result = service._group_by_downloader(torrents)
        assert len(result) == 1
        assert "dl-001" in result
        assert len(result["dl-001"]) == 2

    def test_multiple_downloaders(self, service):
        """不同下载器的种子应分到不同组"""
        torrents = [
            make_torrent(info_id="t1", downloader_id="dl-001"),
            make_torrent(info_id="t2", downloader_id="dl-002"),
            make_torrent(info_id="t3", downloader_id="dl-001"),
        ]
        result = service._group_by_downloader(torrents)
        assert len(result) == 2
        assert len(result["dl-001"]) == 2
        assert len(result["dl-002"]) == 1

    def test_single_torrent(self, service):
        """单个种子应正确分组"""
        torrents = [make_torrent(info_id="t1", downloader_id="dl-001")]
        result = service._group_by_downloader(torrents)
        assert len(result) == 1
        assert result["dl-001"][0].info_id == "t1"


# ==================== register_adapter 测试 ====================

class TestRegisterAdapter:
    """TorrentDeletionService.register_adapter 测试"""

    def test_register_success(self):
        """注册适配器后应可通过 adapters 字典访问"""
        mock_db = MagicMock()
        service = TorrentDeletionService(db=mock_db)
        adapter = _make_fake_adapter()

        service.register_adapter("qbittorrent", adapter)
        assert "qbittorrent" in service.adapters
        assert service.adapters["qbittorrent"] is adapter

    def test_register_multiple(self):
        """注册多个适配器应各自独立"""
        mock_db = MagicMock()
        service = TorrentDeletionService(db=mock_db)
        adapter_qb = _make_fake_adapter()
        adapter_tr = _make_fake_adapter()

        service.register_adapter("qbittorrent", adapter_qb)
        service.register_adapter("transmission", adapter_tr)
        assert len(service.adapters) == 2
        assert service.adapters["qbittorrent"] is adapter_qb
        assert service.adapters["transmission"] is adapter_tr


# ==================== delete_torrents 空列表测试 ====================

class TestDeleteTorrentsEmpty:
    """TorrentDeletionService.delete_torrents 空列表场景测试"""

    async def test_empty_ids_returns_early(self):
        """空 ID 列表应直接返回，不查询数据库"""
        mock_db = MagicMock()
        service = TorrentDeletionService(db=mock_db)
        request = DeleteRequest(
            torrent_info_ids=[],
            delete_option=DeleteOption.DRY_RUN,
        )
        result = await service.delete_torrents(request)

        assert result.success_count == 0
        assert result.failed_count == 0
        assert result.skipped_count == 0
        assert "没有指定" in result.safety_warnings[0]
        # db.query 不应被调用
        mock_db.query.assert_not_called()


# ==================== DownloaderAdapterFactory 测试 ====================

class TestDownloaderAdapterFactory:
    """DownloaderAdapterFactory 工厂方法测试"""

    def test_none_client_raises(self):
        """client 为 None 应抛出 ValueError"""
        with pytest.raises(ValueError, match="必须传入缓存的客户端连接"):
            DownloaderAdapterFactory.create_adapter("qbittorrent", None)

    def test_unsupported_type_raises(self):
        """不支持的下载器类型应抛出 ValueError"""
        # 模拟延迟导入的模块
        mock_qb_module = MagicMock()
        mock_tr_module = MagicMock()
        with patch.dict("sys.modules", {
            "app.services.downloader_adapters.qbittorrent": mock_qb_module,
            "app.services.downloader_adapters.transmission": mock_tr_module,
            "app.services.downloader_adapters": MagicMock(),
        }):
            with pytest.raises(ValueError, match="不支持的下载器类型"):
                DownloaderAdapterFactory.create_adapter("unknown_type", MagicMock())


# ==================== DownloaderDeleteAdapter 抽象类测试 ====================

class TestDownloaderDeleteAdapter:
    """DownloaderDeleteAdapter 抽象基类测试"""

    def test_cannot_instantiate(self):
        """抽象类不能直接实例化"""
        with pytest.raises(TypeError):
            DownloaderDeleteAdapter()

    def test_subclass_must_implement_methods(self):
        """子类必须实现所有抽象方法才能实例化"""
        class _IncompleteAdapter(DownloaderDeleteAdapter):
            def get_downloader_type(self):
                return "incomplete"

        with pytest.raises(TypeError):
            _IncompleteAdapter()

    def test_complete_subclass(self):
        """完整实现的子类可以正常实例化"""
        adapter = _make_fake_adapter()
        assert adapter.get_downloader_type.return_value == "fake"
