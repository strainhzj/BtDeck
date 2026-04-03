# -*- coding: utf-8 -*-
"""
TemplateService 的单元测试

测试 validate_template / _validate_days_of_week / normalize_schedule_time 方法。
所有 DB 相关依赖通过 mock 隔离。
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import time


class TestNormalizeScheduleTime:
    """normalize_schedule_time 函数测试"""

    def test_valid_hhmm_format(self):
        """标准 HH:MM 格式应原样返回"""
        from app.services.template_service import normalize_schedule_time
        assert normalize_schedule_time("08:30") == "08:30"

    def test_valid_hhmmss_format(self):
        """HH:MM:SS 格式应截断为 HH:MM"""
        from app.services.template_service import normalize_schedule_time
        assert normalize_schedule_time("08:30:45") == "08:30"

    def test_time_object(self):
        """datetime.time 对象应格式化为 HH:MM"""
        from app.services.template_service import normalize_schedule_time
        assert normalize_schedule_time(time(14, 5)) == "14:05"

    def test_invalid_string_raises(self):
        """无效字符串应抛出 ValueError"""
        from app.services.template_service import normalize_schedule_time
        with pytest.raises(ValueError, match="invalid schedule time"):
            normalize_schedule_time("25:00")

    def test_non_time_non_string_raises(self):
        """非字符串非时间类型应抛出 ValueError"""
        from app.services.template_service import normalize_schedule_time
        with pytest.raises(ValueError, match="invalid schedule time"):
            normalize_schedule_time(12345)

    def test_empty_string_raises(self):
        """空字符串应抛出 ValueError"""
        from app.services.template_service import normalize_schedule_time
        with pytest.raises(ValueError, match="invalid schedule time"):
            normalize_schedule_time("")


class TestValidateTemplate:
    """TemplateService.validate_template 测试"""

    @pytest.fixture
    def service(self):
        """创建 TemplateService 实例，db 为 mock"""
        from app.services.template_service import TemplateService
        return TemplateService(db=MagicMock())

    def _valid_config(self, **overrides):
        """生成一个有效的模板配置"""
        config = {
            "dl_speed_limit": 1024,
            "ul_speed_limit": 512,
            "speed_unit": 0,
        }
        config.update(overrides)
        return config

    def test_valid_minimal_config(self, service):
        """最简有效配置应通过验证"""
        ok, msg = service.validate_template(self._valid_config(), downloader_type=0)
        assert ok is True
        assert msg == ""

    def test_missing_dl_speed_limit(self, service):
        """缺少 dl_speed_limit 应失败"""
        config = self._valid_config()
        del config["dl_speed_limit"]
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "dl_speed_limit" in msg

    def test_missing_ul_speed_limit(self, service):
        """缺少 ul_speed_limit 应失败"""
        config = self._valid_config()
        del config["ul_speed_limit"]
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "ul_speed_limit" in msg

    def test_missing_speed_unit(self, service):
        """缺少 speed_unit 应失败"""
        config = self._valid_config()
        del config["speed_unit"]
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "speed_unit" in msg

    def test_negative_dl_speed(self, service):
        """负的下载速度应失败"""
        ok, msg = service.validate_template(self._valid_config(dl_speed_limit=-1), downloader_type=0)
        assert ok is False
        assert "下载速度" in msg

    def test_negative_ul_speed(self, service):
        """负的上传速度应失败"""
        ok, msg = service.validate_template(self._valid_config(ul_speed_limit=-1), downloader_type=0)
        assert ok is False
        assert "上传速度" in msg

    def test_invalid_speed_unit(self, service):
        """无效速度单位（非 0/1）应失败"""
        ok, msg = service.validate_template(self._valid_config(speed_unit=5), downloader_type=0)
        assert ok is False
        assert "速度单位" in msg

    def test_valid_schedule_rules(self, service):
        """有效的分时段规则应通过"""
        config = self._valid_config(schedule_rules=[
            {"start_time": "08:00", "end_time": "18:00", "days_of_week": "01234"}
        ])
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is True

    def test_schedule_rules_missing_time(self, service):
        """分时段规则缺少时间字段应失败"""
        config = self._valid_config(schedule_rules=[
            {"days_of_week": "01234"}  # 缺少 start_time / end_time
        ])
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "时间字段" in msg

    def test_schedule_rules_missing_days_of_week(self, service):
        """分时段规则缺少 days_of_week 应失败"""
        config = self._valid_config(schedule_rules=[
            {"start_time": "08:00", "end_time": "18:00"}
        ])
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "days_of_week" in msg

    def test_schedule_rules_invalid_days_format(self, service):
        """days_of_week 格式无效应失败"""
        config = self._valid_config(schedule_rules=[
            {"start_time": "08:00", "end_time": "18:00", "days_of_week": "abc"}
        ])
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "days_of_week" in msg

    def test_advanced_settings_qbittorrent_valid(self, service):
        """qBittorrent 高级配置有效值应通过"""
        config = self._valid_config(advanced_settings={
            "max_connec": 100, "max_numconn": 50, "max_uploads": 20
        })
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is True

    def test_advanced_settings_qbittorrent_negative_value(self, service):
        """qBittorrent 高级配置负值应失败"""
        config = self._valid_config(advanced_settings={"max_connec": -1})
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "max_connec" in msg

    def test_advanced_settings_transmission_valid(self, service):
        """Transmission 高级配置有效值应通过"""
        config = self._valid_config(advanced_settings={
            "peer-limit-global": 200, "peer-limit-per-torrent": 50
        })
        ok, msg = service.validate_template(config, downloader_type=1)
        assert ok is True

    def test_advanced_settings_transmission_negative(self, service):
        """Transmission 高级配置负值应失败"""
        config = self._valid_config(advanced_settings={"peer-limit-global": -5})
        ok, msg = service.validate_template(config, downloader_type=1)
        assert ok is False
        assert "peer-limit-global" in msg

    def test_advanced_settings_not_dict(self, service):
        """advanced_settings 不是字典应失败"""
        config = self._valid_config(advanced_settings="not-a-dict")
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "对象" in msg


class TestValidateDaysOfWeek:
    """TemplateService._validate_days_of_week 测试"""

    @pytest.fixture
    def service(self):
        from app.services.template_service import TemplateService
        return TemplateService(db=MagicMock())

    def test_valid_single_day(self, service):
        """单个有效日期数字应通过"""
        assert service._validate_days_of_week("0") is True

    def test_valid_multiple_days(self, service):
        """多个有效日期数字应通过"""
        assert service._validate_days_of_week("01234") is True

    def test_valid_all_days(self, service):
        """0-6 全部日期应通过"""
        assert service._validate_days_of_week("0123456") is True

    def test_empty_string(self, service):
        """空字符串应失败"""
        assert service._validate_days_of_week("") is False

    def test_too_long_string(self, service):
        """超过 7 位应失败"""
        assert service._validate_days_of_week("01234567") is False

    def test_out_of_range_digit(self, service):
        """包含 7/8/9 等超范围数字应失败"""
        assert service._validate_days_of_week("789") is False

    def test_duplicate_digits(self, service):
        """重复数字应失败"""
        assert service._validate_days_of_week("001") is False

    def test_non_digit_chars(self, service):
        """非数字字符应失败"""
        assert service._validate_days_of_week("abc") is False

    def test_none_value(self, service):
        """None 值应失败"""
        assert service._validate_days_of_week(None) is False


# ==================== CRUD 操作测试 ====================

class _FakeTemplate:
    """轻量级模拟 SettingTemplate ORM 对象"""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "测试模板")
        self.description = kwargs.get("description", "描述")
        self.downloader_type = kwargs.get("downloader_type", 0)
        self.template_config = kwargs.get("template_config", '{"dl_speed_limit": 1024, "ul_speed_limit": 512, "speed_unit": 0}')
        self.path_mapping = kwargs.get("path_mapping", None)
        self.is_system_default = kwargs.get("is_system_default", False)
        self.created_by = kwargs.get("created_by", 1)
        self.created_at = kwargs.get("created_at", None)
        self.updated_at = kwargs.get("updated_at", None)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "downloader_type": self.downloader_type,
            "template_config": self.template_config,
            "path_mapping": self.path_mapping,
            "is_system_default": self.is_system_default,
            "created_by": self.created_by,
        }


def _make_mock_db(template=None, templates=None):
    """创建 mock db 和 query 链"""
    db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter_by.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.first.return_value = template
    mock_query.all.return_value = templates or []
    db.query.return_value = mock_query
    return db, mock_query


def _valid_create_data(**overrides):
    """生成有效的创建模板数据"""
    data = {
        "name": "测试模板",
        "description": "测试描述",
        "downloader_type": 0,
        "template_config": {
            "dl_speed_limit": 1024,
            "ul_speed_limit": 512,
            "speed_unit": 0,
        },
    }
    data.update(overrides)
    return data


class TestCreateTemplate:
    """TemplateService.create_template 测试"""

    def test_创建成功(self):
        """正常创建模板应成功"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(name="测试模板")
        db, mock_query = _make_mock_db(template=None)  # 名称不存在

        # 模拟 db.add/commit/refresh
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        # name 查询返回 None（名称不存在）
        # 但后续需要 query(SettingTemplate).filter_by(name=...).first() 返回 None
        mock_query.filter_by.return_value.first.return_value = None

        service = TemplateService(db=db)
        result = service.create_template(user_id=1, data=_valid_create_data())

        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_名称为空抛出异常(self):
        """模板名称为空应抛出 ValueError"""
        from app.services.template_service import TemplateService

        db = MagicMock()
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="模板名称"):
            service.create_template(user_id=1, data=_valid_create_data(name=""))

    def test_名称过长抛出异常(self):
        """模板名称超过100字符应抛出"""
        from app.services.template_service import TemplateService

        db = MagicMock()
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="模板名称"):
            service.create_template(user_id=1, data=_valid_create_data(name="x" * 101))

    def test_描述过长抛出异常(self):
        """模板描述超过500字符应抛出"""
        from app.services.template_service import TemplateService

        db = MagicMock()
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="模板描述"):
            service.create_template(user_id=1, data=_valid_create_data(description="x" * 501))

    def test_无效下载器类型抛出异常(self):
        """无效下载器类型应抛出"""
        from app.services.template_service import TemplateService

        db = MagicMock()
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="下载器类型"):
            service.create_template(user_id=1, data=_valid_create_data(downloader_type=2))

    def test_模板配置为空抛出异常(self):
        """模板配置为空应抛出"""
        from app.services.template_service import TemplateService

        db = MagicMock()
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="模板配置"):
            service.create_template(user_id=1, data=_valid_create_data(template_config=None))

    def test_名称已存在抛出异常(self):
        """模板名称已存在应抛出"""
        from app.services.template_service import TemplateService

        existing = _FakeTemplate(name="测试模板")
        db, mock_query = _make_mock_db(template=existing)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="已存在"):
            service.create_template(user_id=1, data=_valid_create_data())

    def test_模板配置验证失败抛出异常(self):
        """模板配置验证失败应抛出"""
        from app.services.template_service import TemplateService

        db, mock_query = _make_mock_db(template=None)
        mock_query.filter_by.return_value.first.return_value = None
        service = TemplateService(db=db)

        bad_config = _valid_create_data(
            template_config={"ul_speed_limit": 512, "speed_unit": 0}  # 缺少 dl_speed_limit
        )
        with pytest.raises(ValueError, match="模板配置验证失败"):
            service.create_template(user_id=1, data=bad_config)

    def test_包含路径映射(self):
        """包含路径映射时应正确处理"""
        from app.services.template_service import TemplateService

        db, mock_query = _make_mock_db(template=None)
        mock_query.filter_by.return_value.first.return_value = None
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        service = TemplateService(db=db)
        data = _valid_create_data(path_mapping={"source": "/downloads", "target": "/media"})
        result = service.create_template(user_id=1, data=data)

        db.add.assert_called_once()

    def test_路径映射非字典抛出异常(self):
        """路径映射不是字典应抛出"""
        from app.services.template_service import TemplateService

        db, mock_query = _make_mock_db(template=None)
        mock_query.filter_by.return_value.first.return_value = None
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="路径映射"):
            service.create_template(user_id=1, data=_valid_create_data(path_mapping="not-a-dict"))


class TestUpdateTemplate:
    """TemplateService.update_template 测试"""

    def test_更新名称成功(self):
        """更新模板名称应成功"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=1)
        db = MagicMock()

        # 第一次 query().filter_by(id=...).first() → 返回模板
        # 第二次 query().filter(name=..., id!=...).first() → 返回 None（无重名）
        mock_filter_query = MagicMock()
        mock_filter_query.first.return_value = None

        mock_filterby_query = MagicMock()
        mock_filterby_query.first.return_value = template

        mock_base_query = MagicMock()
        mock_base_query.filter_by.return_value = mock_filterby_query
        mock_base_query.filter.return_value = mock_filter_query

        db.query.return_value = mock_base_query
        db.commit = MagicMock()
        db.refresh = MagicMock()

        service = TemplateService(db=db)
        result = service.update_template(template_id=1, user_id=1, data={"name": "新名称"})

        db.commit.assert_called_once()

    def test_模板不存在抛出异常(self):
        """更新不存在的模板应抛出"""
        from app.services.template_service import TemplateService

        db, mock_query = _make_mock_db(template=None)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="模板不存在"):
            service.update_template(template_id=999, user_id=1, data={"name": "新名称"})

    def test_系统模板不可修改(self):
        """系统默认模板不能修改"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(is_system_default=True, created_by=1)
        db, mock_query = _make_mock_db(template=template)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="系统默认模板"):
            service.update_template(template_id=1, user_id=1, data={"name": "新名称"})

    def test_无权修改他人模板(self):
        """修改他人模板应抛出"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=2)
        db, mock_query = _make_mock_db(template=template)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="无权修改"):
            service.update_template(template_id=1, user_id=1, data={"name": "新名称"})

    def test_没有更新字段抛出异常(self):
        """空更新数据应抛出"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=1)
        db, mock_query = _make_mock_db(template=template)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="没有要更新的字段"):
            service.update_template(template_id=1, user_id=1, data={})

    def test_更新描述成功(self):
        """更新模板描述应成功"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=1)
        db, mock_query = _make_mock_db(template=template)
        db.commit = MagicMock()
        db.refresh = MagicMock()

        service = TemplateService(db=db)
        result = service.update_template(template_id=1, user_id=1, data={"description": "新描述"})

        db.commit.assert_called_once()

    def test_更新下载器类型成功(self):
        """更新下载器类型应成功"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=1)
        db, mock_query = _make_mock_db(template=template)
        db.commit = MagicMock()
        db.refresh = MagicMock()

        service = TemplateService(db=db)
        result = service.update_template(template_id=1, user_id=1, data={"downloader_type": 1})

        db.commit.assert_called_once()


class TestDeleteTemplate:
    """TemplateService.delete_template 测试"""

    def test_删除成功(self):
        """正常删除模板应成功"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=1)
        db, mock_query = _make_mock_db(template=template)
        db.delete = MagicMock()
        db.commit = MagicMock()

        service = TemplateService(db=db)
        result = service.delete_template(template_id=1, user_id=1)

        assert result is True
        db.delete.assert_called_once_with(template)

    def test_模板不存在抛出异常(self):
        """删除不存在的模板应抛出"""
        from app.services.template_service import TemplateService

        db, mock_query = _make_mock_db(template=None)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="模板不存在"):
            service.delete_template(template_id=999, user_id=1)

    def test_系统模板不可删除(self):
        """系统默认模板不能删除"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(is_system_default=True, created_by=1)
        db, mock_query = _make_mock_db(template=template)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="系统默认模板"):
            service.delete_template(template_id=1, user_id=1)

    def test_无权删除他人模板(self):
        """删除他人模板应抛出"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=2)
        db, mock_query = _make_mock_db(template=template)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="无权删除"):
            service.delete_template(template_id=1, user_id=1)


class TestGetTemplate:
    """TemplateService.get_template 测试"""

    def test_获取成功(self):
        """获取模板详情应成功"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=1)
        db, mock_query = _make_mock_db(template=template)

        service = TemplateService(db=db)
        result = service.get_template(template_id=1, user_id=1)

        assert result["name"] == "测试模板"

    def test_模板不存在抛出异常(self):
        """获取不存在的模板应抛出"""
        from app.services.template_service import TemplateService

        db, mock_query = _make_mock_db(template=None)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="模板不存在"):
            service.get_template(template_id=999)

    def test_无权访问他人模板(self):
        """访问他人的非系统模板应抛出"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=2, is_system_default=False)
        db, mock_query = _make_mock_db(template=template)
        service = TemplateService(db=db)

        with pytest.raises(ValueError, match="无权访问"):
            service.get_template(template_id=1, user_id=1)

    def test_系统模板任何人可访问(self):
        """系统默认模板任何人可访问"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=0, is_system_default=True)
        db, mock_query = _make_mock_db(template=template)
        service = TemplateService(db=db)

        result = service.get_template(template_id=1, user_id=999)
        assert result["name"] == "测试模板"

    def test_无user_id时可访问(self):
        """不指定 user_id 时不检查权限"""
        from app.services.template_service import TemplateService

        template = _FakeTemplate(created_by=2)
        db, mock_query = _make_mock_db(template=template)
        service = TemplateService(db=db)

        result = service.get_template(template_id=1, user_id=None)
        assert result is not None


class TestListTemplates:
    """TemplateService.list_templates 测试"""

    def test_无过滤返回全部(self):
        """无过滤条件应返回全部模板"""
        from app.services.template_service import TemplateService

        templates = [_FakeTemplate(id=1), _FakeTemplate(id=2)]
        db, mock_query = _make_mock_db(templates=templates)

        service = TemplateService(db=db)
        result = service.list_templates()

        assert len(result) == 2

    def test_按下载器类型过滤(self):
        """按下载器类型过滤"""
        from app.services.template_service import TemplateService

        templates = [_FakeTemplate(id=1, downloader_type=0)]
        db, mock_query = _make_mock_db(templates=templates)

        service = TemplateService(db=db)
        result = service.list_templates(filters={"downloader_type": 0})

        assert len(result) == 1

    def test_按系统默认过滤(self):
        """按系统默认模板过滤"""
        from app.services.template_service import TemplateService

        templates = [_FakeTemplate(id=1, is_system_default=True)]
        db, mock_query = _make_mock_db(templates=templates)

        service = TemplateService(db=db)
        result = service.list_templates(filters={"is_system_default": True})

        assert len(result) == 1

    def test_空列表(self):
        """无模板应返回空列表"""
        from app.services.template_service import TemplateService

        db, mock_query = _make_mock_db(templates=[])

        service = TemplateService(db=db)
        result = service.list_templates()

        assert result == []
