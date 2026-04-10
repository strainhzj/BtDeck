# -*- coding: utf-8 -*-
"""
Tracker Reannounce Config 站点配置CRUD单元测试

测试 tracker_reannounce_config 的所有操作：
- CRUD: 创建、查询、更新、删除
- 域名匹配模式验证
- 自动检测域名
- 边界情况：重复域名、空数据、无效参数
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from typing import List, Optional


# ==================== 辅助工具 ====================

class _FakeConfig:
    """轻量级配置对象，避免 ORM 依赖"""
    def __init__(
        self,
        id_="cfg-001",
        domain_pattern="tracker.example.com",
        domain_display_name="Example Tracker",
        interval_minutes=30,
        enabled=True,
        last_announce_time=None,
        create_time=None,
        update_time=None,
        dr=0,
    ):
        self.id_ = id_
        self.domain_pattern = domain_pattern
        self.domain_display_name = domain_display_name
        self.interval_minutes = interval_minutes
        self.enabled = enabled
        self.last_announce_time = last_announce_time
        self.create_time = create_time or datetime(2026, 1, 1, 12, 0, 0)
        self.update_time = update_time or datetime(2026, 1, 1, 12, 0, 0)
        self.dr = dr

    def to_dict(self):
        return {
            "id_": self.id_,
            "domain_pattern": self.domain_pattern,
            "domain_display_name": self.domain_display_name,
            "interval_minutes": self.interval_minutes,
            "enabled": self.enabled,
            "last_announce_time": self.last_announce_time,
        }


def make_config(**kwargs):
    return _FakeConfig(**kwargs)


def make_configs_batch(count):
    return [
        make_config(
            id_=f"cfg-{i:03d}",
            domain_pattern=f"tracker{i}.example.com",
            domain_display_name=f"Tracker {i}",
        )
        for i in range(count)
    ]


# ==================== Fixtures ====================

@pytest.fixture
def mock_db():
    db = MagicMock()
    return db


# ==================== 测试：CRUD基本操作 ====================

class TestConfigCRUD:
    """站点配置CRUD测试"""

    def test_create_config_success(self, mock_db):
        """创建配置成功"""
        from app.core.reannounce_config_operations import create_config

        config_data = {
            "domain_pattern": "tracker.example.com",
            "domain_display_name": "Example Tracker",
            "interval_minutes": 30,
            "enabled": True,
        }

        # Mock db.add + db.commit + db.refresh
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        result = create_config(mock_db, config_data)

        assert mock_db.add.called
        assert mock_db.commit.called

    def test_create_config_without_domain_fails(self, mock_db):
        """创建配置时缺少域名应失败"""
        from app.core.reannounce_config_operations import create_config

        config_data = {
            "domain_display_name": "No Domain",
            "interval_minutes": 30,
        }

        result = create_config(mock_db, config_data)
        # 应返回错误结果
        assert not result.success or mock_db.rollback.called

    def test_get_config_by_id(self, mock_db):
        """按ID查询配置"""
        from app.core.reannounce_config_operations import get_config

        fake_config = make_config()
        mock_db.query.return_value.filter.return_value.first.return_value = fake_config

        result = get_config(mock_db, "cfg-001")

        assert mock_db.query.called

    def test_get_config_not_found(self, mock_db):
        """查询不存在的配置"""
        from app.core.reannounce_config_operations import get_config

        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = get_config(mock_db, "cfg-not-exist")

        # 应返回 not_found 结果
        assert not result.success

    def test_get_all_configs(self, mock_db):
        """查询所有配置"""
        from app.core.reannounce_config_operations import get_configs

        configs = make_configs_batch(5)
        # mock query chain: db.query(X).filter(X.dr == 0).all()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.all.return_value = configs
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        result = get_configs(mock_db)

        assert result.success
        assert result.total_count == 5

    def test_update_config_success(self, mock_db):
        """更新配置成功"""
        from app.core.reannounce_config_operations import update_config

        fake_config = make_config()
        mock_db.query.return_value.filter.return_value.first.return_value = fake_config
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        result = update_config(mock_db, "cfg-001", {
            "interval_minutes": 60,
            "enabled": False,
        })

        assert mock_db.commit.called

    def test_update_config_not_found(self, mock_db):
        """更新不存在的配置"""
        from app.core.reannounce_config_operations import update_config

        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = update_config(mock_db, "cfg-not-exist", {
            "interval_minutes": 60,
        })

        assert not result.success

    def test_delete_config_success(self, mock_db):
        """软删除配置成功"""
        from app.core.reannounce_config_operations import delete_config

        fake_config = make_config()
        mock_db.query.return_value.filter.return_value.first.return_value = fake_config
        mock_db.commit = MagicMock()

        result = delete_config(mock_db, "cfg-001")

        assert mock_db.commit.called

    def test_delete_config_not_found(self, mock_db):
        """删除不存在的配置"""
        from app.core.reannounce_config_operations import delete_config

        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = delete_config(mock_db, "cfg-not-exist")

        assert not result.success

    def test_get_enabled_configs(self, mock_db):
        """查询所有启用的配置"""
        from app.core.reannounce_config_operations import get_enabled_configs

        enabled_configs = make_configs_batch(3)
        mock_db.query.return_value.filter.return_value.all.return_value = enabled_configs

        result = get_enabled_configs(mock_db)

        assert result.success
        assert result.total_count == 3


# ==================== 测试：域名匹配 ====================

class TestDomainMatching:
    """测试域名匹配逻辑"""

    def test_exact_domain_match(self):
        """精确域名匹配"""
        from app.core.reannounce_config_operations import match_domain

        config = make_config(domain_pattern="tracker.example.com")

        assert match_domain("tracker.example.com", config) is True

    def test_exact_domain_no_match(self):
        """精确域名不匹配"""
        from app.core.reannounce_config_operations import match_domain

        config = make_config(domain_pattern="tracker.example.com")

        assert match_domain("other.tracker.com", config) is False

    def test_wildcard_domain_match(self):
        """通配符域名匹配 (% 为通配符)"""
        from app.core.reannounce_config_operations import match_domain

        config = make_config(domain_pattern="%.example.com")

        assert match_domain("tracker.example.com", config) is True
        assert match_domain("sub.example.com", config) is True

    def test_wildcard_prefix_match(self):
        """通配符前缀匹配"""
        from app.core.reannounce_config_operations import match_domain

        config = make_config(domain_pattern="%.openwebtorrent.%")

        assert match_domain("tracker.openwebtorrent.com", config) is True
        assert match_domain("tracker.openwebtorrent.net", config) is True

    def test_empty_domain_pattern(self):
        """空域名模式不应匹配"""
        from app.core.reannounce_config_operations import match_domain

        config = make_config(domain_pattern="")

        assert match_domain("tracker.example.com", config) is False

    def test_empty_input_domain(self):
        """空输入域名不应匹配"""
        from app.core.reannounce_config_operations import match_domain

        config = make_config(domain_pattern="tracker.example.com")

        assert match_domain("", config) is False
        assert match_domain(None, config) is False


# ==================== 测试：自动检测域名 ====================

class TestAutoDetectDomains:
    """测试自动检测 tracker 域名功能"""

    def test_detect_from_tracker_urls(self):
        """从tracker URL列表中提取域名"""
        from app.core.reannounce_config_operations import extract_domains_from_trackers

        tracker_urls = [
            "http://tracker.example.com/announce",
            "udp://tracker2.example.com:6969/announce",
            "https://sub.tracker3.net/announce?key=123",
            "http://tracker.example.com/announce2",  # 重复域名
        ]

        domains = extract_domains_from_trackers(tracker_urls)

        assert "tracker.example.com" in domains
        assert "tracker2.example.com" in domains
        assert "sub.tracker3.net" in domains
        assert len(domains) == 3  # 去重后3个

    def test_detect_empty_list(self):
        """空tracker列表"""
        from app.core.reannounce_config_operations import extract_domains_from_trackers

        domains = extract_domains_from_trackers([])
        assert domains == []

    def test_detect_invalid_urls(self):
        """无效URL应被安全跳过"""
        from app.core.reannounce_config_operations import extract_domains_from_trackers

        tracker_urls = [
            "not-a-valid-url",
            "",
            "http://",
            "udp://tracker.valid.com/announce",
        ]

        domains = extract_domains_from_trackers(tracker_urls)

        assert "tracker.valid.com" in domains
        assert len(domains) == 1

    def test_detect_ipv4_address(self):
        """IP地址格式的tracker"""
        from app.core.reannounce_config_operations import extract_domains_from_trackers

        tracker_urls = [
            "http://192.168.1.1:6969/announce",
        ]

        domains = extract_domains_from_trackers(tracker_urls)

        assert "192.168.1.1" in domains

    def test_detect_with_port(self):
        """带端口的tracker域名应去掉端口"""
        from app.core.reannounce_config_operations import extract_domains_from_trackers

        tracker_urls = [
            "udp://tracker.example.com:6969/announce",
            "http://tracker.example.com:8080/announce",
        ]

        domains = extract_domains_from_trackers(tracker_urls)

        # 同一域名不同端口应合并
        assert "tracker.example.com" in domains
        assert len(domains) == 1


# ==================== 测试：间隔验证 ====================

class TestIntervalValidation:
    """测试汇报间隔的验证逻辑"""

    @pytest.mark.parametrize(
        "interval, expected_valid",
        [
            (1, True),       # 最小有效值
            (5, True),       # 常见值
            (30, True),      # 默认值
            (60, True),      # 1小时
            (1440, True),    # 24小时（最大合理值）
            (0, False),      # 无效：0
            (-1, False),     # 无效：负数
            (None, False),   # 无效：None
        ],
        ids=["1分钟", "5分钟", "30分钟", "60分钟", "24小时", "0", "负数", "None"],
    )
    def test_interval_validation(self, interval, expected_valid):
        """汇报间隔值验证"""
        from app.core.reannounce_config_operations import validate_interval

        result = validate_interval(interval)
        assert result == expected_valid
