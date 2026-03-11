# -*- coding: utf-8 -*-
"""
下载器设置 Pydantic Schema

用于API请求/响应序列化和数据验证
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import IntEnum

# 从 models 模块导入枚举，避免重复定义
from app.models.setting_templates import DownloaderTypeEnum


# ========== 枚举定义 ==========

class SpeedUnitEnum(IntEnum):
    """速度单位枚举"""
    KB_PER_SEC = 0  # KB/s
    MB_PER_SEC = 1  # MB/s


# ========== DownloaderSetting Schema ==========

class DownloaderSettingBase(BaseModel):
    """下载器配置基础Schema"""
    dl_speed_limit: int = Field(..., ge=0, description="全局下载速度限制，数值含义取决于 dl_speed_unit，0表示不限速", alias="dlSpeedLimit")
    ul_speed_limit: int = Field(..., ge=0, description="全局上传速度限制，数值含义取决于 ul_speed_unit，0表示不限速", alias="ulSpeedLimit")
    dl_speed_unit: SpeedUnitEnum = Field(default=SpeedUnitEnum.KB_PER_SEC, description="下载速度单位：0=KB/s, 1=MB/s", alias="dlSpeedUnit")
    ul_speed_unit: SpeedUnitEnum = Field(default=SpeedUnitEnum.KB_PER_SEC, description="上传速度单位：0=KB/s, 1=MB/s", alias="ulSpeedUnit")
    enable_schedule: bool = Field(default=False, description="是否启用分时段限速", alias="enableSchedule")
    username: Optional[str] = Field(None, max_length=100, description="下载器用户名")
    password: Optional[str] = Field(None, max_length=255, description="下载器密码（明文，后端会加密）")
    advanced_settings: Optional[Dict[str, Any]] = Field(None, description="高级配置（JSON格式）", alias="advancedSettings")
    override_local: bool = Field(default=False, description="是否覆盖下载器本地配置", alias="overrideLocal")

    class Config:
        populate_by_name = True  # 允许使用别名


class DownloaderSettingCreate(DownloaderSettingBase):
    """创建下载器配置Schema"""
    downloader_id: str = Field(..., min_length=1, description="下载器ID", alias="downloaderId")


class DownloaderSettingUpdate(BaseModel):
    """更新下载器配置Schema（所有字段可选）"""
    dl_speed_limit: Optional[int] = Field(None, ge=0, description="全局下载速度限制", alias="dlSpeedLimit")
    ul_speed_limit: Optional[int] = Field(None, ge=0, description="全局上传速度限制", alias="ulSpeedLimit")
    dl_speed_unit: Optional[SpeedUnitEnum] = Field(None, description="下载速度单位：0=KB/s, 1=MB/s", alias="dlSpeedUnit")
    ul_speed_unit: Optional[SpeedUnitEnum] = Field(None, description="上传速度单位：0=KB/s, 1=MB/s", alias="ulSpeedUnit")
    enable_schedule: Optional[bool] = Field(None, description="是否启用分时段限速", alias="enableSchedule")
    username: Optional[str] = Field(None, max_length=100, description="下载器用户名")
    password: Optional[str] = Field(None, max_length=255, description="下载器密码（明文，后端会加密）")
    advanced_settings: Optional[Dict[str, Any]] = Field(None, description="高级配置（JSON格式）", alias="advancedSettings")
    override_local: Optional[bool] = Field(None, description="是否覆盖下载器本地配置", alias="overrideLocal")

    class Config:
        populate_by_name = True


class DownloaderSettingInDB(DownloaderSettingBase):
    """数据库中的完整下载器配置Schema"""
    id: int
    downloader_id: str = Field(alias="downloaderId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class DownloaderSettingResponse(DownloaderSettingInDB):
    """API响应下载器配置Schema"""
    pass


# ========== SettingTemplate Schema ==========

class SettingTemplateBase(BaseModel):
    """配置模板基础Schema"""
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    description: Optional[str] = Field(None, max_length=500, description="模板描述")
    downloader_type: DownloaderTypeEnum = Field(..., description="下载器类型", alias="downloaderType")
    template_config: Dict[str, Any] = Field(..., description="模板配置（JSON格式）", alias="templateConfig")
    is_system_default: bool = Field(default=False, description="是否为系统默认模板", alias="isSystemDefault")

    class Config:
        populate_by_name = True


class SettingTemplateCreate(SettingTemplateBase):
    """创建配置模板Schema"""
    pass


class SettingTemplateUpdate(BaseModel):
    """更新配置模板Schema（所有字段可选）"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="模板名称")
    description: Optional[str] = Field(None, max_length=500, description="模板描述")
    downloader_type: Optional[DownloaderTypeEnum] = Field(None, description="下载器类型", alias="downloaderType")
    template_config: Optional[Dict[str, Any]] = Field(None, description="模板配置（JSON格式）", alias="templateConfig")
    is_system_default: Optional[bool] = Field(None, description="是否为系统默认模板", alias="isSystemDefault")

    class Config:
        populate_by_name = True


class SettingTemplateInDB(SettingTemplateBase):
    """数据库中的完整配置模板Schema"""
    id: int
    created_by: Optional[int] = Field(None, description="创建者用户ID", alias="createdBy")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class SettingTemplateResponse(SettingTemplateInDB):
    """API响应配置模板Schema"""
    pass


# ========== SpeedScheduleRule Schema ==========

class SpeedScheduleRuleBase(BaseModel):
    """分时段速度规则基础Schema"""
    start_time: str = Field(..., pattern=r'^\d{2}:\d{2}:\d{2}$', description="开始时间，格式：HH:MM:SS", alias="startTime")
    end_time: str = Field(..., pattern=r'^\d{2}:\d{2}:\d{2}$', description="结束时间，格式：HH:MM:SS", alias="endTime")
    dl_speed_limit: int = Field(..., ge=0, description="下载速度限制（KB/s），0表示不限速", alias="dlSpeedLimit")
    ul_speed_limit: int = Field(..., ge=0, description="上传速度限制（KB/s），0表示不限速", alias="ulSpeedLimit")
    days_of_week: str = Field(..., min_length=1, max_length=7, description="生效星期几，0=周日，1=周一，...，6=周六", alias="daysOfWeek")
    enabled: bool = Field(default=True, description="是否启用")

    class Config:
        populate_by_name = True

    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """验证时间格式"""
        try:
            h, m, s = map(int, v.split(':'))
            if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
                raise ValueError('时间格式不正确')
        except ValueError:
            raise ValueError('时间格式必须为 HH:MM:SS')
        return v

    @field_validator('end_time')
    @classmethod
    def validate_time_range(cls, v: str, info) -> str:
        """验证时间范围：结束时间必须晚于开始时间"""
        if 'start_time' in info.data:
            start_time = info.data['start_time']
            if v <= start_time:
                raise ValueError('结束时间必须晚于开始时间')
        return v

    @field_validator('days_of_week')
    @classmethod
    def validate_days_of_week(cls, v: str) -> str:
        """验证days_of_week格式"""
        if not v:
            raise ValueError('days_of_week不能为空')

        # 检查是否只包含0-6的数字
        allowed_chars = set('0123456')
        if not all(c in allowed_chars for c in v):
            raise ValueError('days_of_week只能包含0-6的数字')

        # 检查是否有重复
        if len(set(v)) != len(v):
            raise ValueError('days_of_week不能包含重复的数字')

        return v


class SpeedScheduleRuleCreate(SpeedScheduleRuleBase):
    """创建分时段速度规则Schema"""
    downloader_setting_id: int = Field(..., description="下载器配置ID", alias="downloaderSettingId")

    class Config:
        populate_by_name = True


class SpeedScheduleRuleUpdate(BaseModel):
    """更新分时段速度规则Schema（所有字段可选）"""
    start_time: Optional[str] = Field(None, pattern=r'^\d{2}:\d{2}:\d{2}$', description="开始时间", alias="startTime")
    end_time: Optional[str] = Field(None, pattern=r'^\d{2}:\d{2}:\d{2}$', description="结束时间", alias="endTime")
    dl_speed_limit: Optional[int] = Field(None, ge=0, description="下载速度限制（KB/s）", alias="dlSpeedLimit")
    ul_speed_limit: Optional[int] = Field(None, ge=0, description="上传速度限制（KB/s）", alias="ulSpeedLimit")
    days_of_week: Optional[str] = Field(None, min_length=1, max_length=7, description="生效星期几", alias="daysOfWeek")
    enabled: Optional[bool] = Field(None, description="是否启用")

    class Config:
        populate_by_name = True


class SpeedScheduleRuleInDB(SpeedScheduleRuleBase):
    """数据库中的完整分时段速度规则Schema"""
    id: int
    downloader_setting_id: int = Field(alias="downloaderSettingId")
    created_at: datetime = Field(alias="createdAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class SpeedScheduleRuleResponse(SpeedScheduleRuleInDB):
    """API响应分时段速度规则Schema"""
    pass


# ========== 组合Schema ==========

class DownloaderSettingWithRules(DownloaderSettingResponse):
    """下载器配置（包含分时段规则）"""
    speed_schedule_rules: List[SpeedScheduleRuleResponse] = Field(default=[], description="分时段速度规则列表", alias="speedScheduleRules")

    class Config:
        populate_by_name = True
