# -*- coding: utf-8 -*-
"""
路径映射相关的Pydantic模型定义

提供类型安全的路径映射配置验证，支持前端和后端协同验证。
"""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class PathMappingItem(BaseModel):
    """单个路径映射项"""

    name: str = Field(..., description="映射名称", min_length=1, max_length=100)
    internal: str = Field(..., description="内部路径(下载器内)", min_length=1)
    external: str = Field(..., description="外部路径(主机)", min_length=1)
    description: Optional[str] = Field(None, description="映射描述", max_length=500)
    mapping_type: str = Field("local", description="映射类型: local/docker/nas/wsl/network")

    @field_validator("internal", "external")
    @classmethod
    def validate_path_format(cls, v: str, info) -> str:
        """验证路径格式基本规范"""
        if not v or not v.strip():
            raise ValueError("路径不能为空")
        # 路径标准化检查将在PathMappingService中完成
        return v.strip()

    @field_validator("mapping_type")
    @classmethod
    def validate_mapping_type(cls, v: str) -> str:
        """验证映射类型"""
        allowed_types = ["local", "docker", "nas", "wsl", "network"]
        if v not in allowed_types:
            raise ValueError(f'映射类型必须是以下之一: {", ".join(allowed_types)}')
        return v


class PathMappingConfig(BaseModel):
    """路径映射配置"""

    mappings: List[PathMappingItem] = Field(default_factory=list, description="路径映射列表")
    default_mapping: Optional[str] = Field(None, description="默认映射名称")

    @field_validator("mappings")
    @classmethod
    def validate_mappings(cls, v: List[PathMappingItem]) -> List[PathMappingItem]:
        """验证映射列表"""
        if not isinstance(v, list):
            raise ValueError("mappings必须是数组")

        # 检查映射名称唯一性
        names = [m.name for m in v]
        if len(names) != len(set(names)):
            raise ValueError("映射名称必须唯一")

        return v

    @field_validator("default_mapping")
    @classmethod
    def validate_default_mapping(cls, v: Optional[str], info) -> Optional[str]:
        """验证默认映射名称是否存在"""
        if v is not None:
            # 获取mappings列表
            mappings = info.data.get("mappings", [])
            if mappings:
                mapping_names = [m.name for m in mappings]
                if v not in mapping_names:
                    raise ValueError(f'默认映射"{v}"不存在于映射列表中')
        return v


class PathMappingTestRequest(BaseModel):
    """路径映射测试请求"""

    path_mapping: PathMappingConfig = Field(..., description="要测试的路径映射配置")


class PathDirectoryValidation(BaseModel):
    """单侧目录验证结果"""

    path: str = Field(..., description="被验证的路径")
    valid: bool = Field(..., description="目录是否可用")
    message: str = Field(..., description="验证详情")


class PathMappingCheck(BaseModel):
    """单条路径映射验证结果"""

    name: str = Field(..., description="映射名称")
    valid: bool = Field(..., description="内部与外部目录是否都可用")
    internal: PathDirectoryValidation = Field(..., description="下载器内部目录验证结果")
    external: PathDirectoryValidation = Field(
        ..., description="BtDeck 外部目录验证结果"
    )


class PathMappingBackendValidation(BaseModel):
    """后端完整验证明细"""

    json_format_valid: bool = Field(True, description="JSON格式是否有效")
    structure_valid: bool = Field(True, description="结构是否有效")
    fields_complete: bool = Field(True, description="字段是否完整")
    no_path_conflicts: bool = Field(True, description="是否不存在路径冲突")
    downloader_available: bool = Field(False, description="缓存下载器是否可用")
    internal_paths_valid: bool = Field(False, description="全部下载器内部目录是否可用")
    external_paths_valid: bool = Field(
        False, description="全部 BtDeck 外部目录是否可用"
    )
    path_checks: List[PathMappingCheck] = Field(
        default_factory=list, description="逐条映射目录验证结果"
    )
    errors: List[str] = Field(default_factory=list, description="错误列表")


class PathMappingTestResponse(BaseModel):
    """路径映射测试响应"""

    valid: bool = Field(..., description="总体验证结果")
    message: str = Field(..., description="验证结果描述")
    backend_validation: PathMappingBackendValidation = Field(
        ..., description="后端验证结果"
    )
    frontend_validation: Optional[dict[str, object]] = Field(
        None, description="前端验证结果(由前端填充)"
    )
