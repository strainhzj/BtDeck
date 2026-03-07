from pydantic import BaseModel, Field, ConfigDict
from typing import Any, List
from app.utils.encryption import encrypt_password, decrypt_password
from app.models.setting_templates import DownloaderTypeEnum


class DownloaderSimpleVO(BaseModel):
    """下载器简单信息VO - 仅包含ID和名称"""
    model_config = ConfigDict(populate_by_name=True)

    downloader_id: str = Field(..., description="下载器ID", example="550e8400-e29b-41d4-a716-446655440000")
    nickname: str = Field(..., description="下载器名称", example="qBittorrent-01")


class DownloaderResponse(BaseModel):
    status: str | None = Field(None, description="返回接口调用结果", example="success")
    message: str | None = Field(None, description="返回接口调用信息", example="接口调用成功")
    data: list | None = Field(None, description="返回数据集", example=[])


class DownloaderListVO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(None, description="主键", example="1")
    nickname: str | None = Field(None, description="自定义名称", example="qb")
    host: str | None = Field(None, description="下载器主机", example="1.1.1.1")
    isSearch: str | None = Field(None, alias="isSearch", description="是否启用种子搜索", example="1")
    status: str | None = Field(None, description="下载器状态", example="1")  #
    enabled: str | None = Field(None, description="下载器启用状态", example="1")  #
    downloaderType: int | None = Field(None, alias="downloaderType", description="下载器类型(0=qBittorrent, 1=Transmission)", example=0)
    downloaderId: str | None = Field(None, alias="downloaderId", description="下载器ID")
    port: str | None = Field(None, description="端口")
    downloaderTypeName: str | None = Field(None, alias="downloaderTypeName", description="下载器类型名称", example="qbittorrent")
    connectStatus: str | None = Field(None, alias="connectStatus", description="连接状态(1=在线, 0=离线)", example="1")
    pathMappingRules: str | None = Field(None, alias="pathMappingRules", description="路径映射规则配置")
    torrentSavePath: str | None = Field(None, alias="torrentSavePath", description="种子保存目录路径")

    def __init__(self, downloader_id=None, nickname=None, host=None, is_search=None, status=None, enabled=None, downloader_type=None, port=None, connectStatus=None, path_mapping_rules=None, torrent_save_path=None, **kw: Any):
        # Set required fields for Pydantic compatibility
        if host is not None and port is not None:
            host_field = host + ":" + port
        elif host is not None:
            host_field = host
        else:
            host_field = None

        # 使用统一的类型转换方法
        downloader_type_int = None
        downloader_type_name = None
        if downloader_type is not None:
            # 使用枚举类的 normalize 方法统一转换
            downloader_type_int = DownloaderTypeEnum.normalize(downloader_type)
            downloader_type_name = DownloaderTypeEnum(downloader_type_int).to_name()

        # 将整数 0/1 转换为字符串 "0"/"1"（修复 Pydantic 验证错误）
        # 修复P1问题：使用精确的枚举值检查，避免将0误判
        is_search_str = str(is_search) if is_search in (0, 1) else None
        enabled_str = str(enabled) if enabled in (0, 1) else None


        super().__init__(
            id=downloader_id,
            nickname=nickname,
            host=host_field,
            isSearch=is_search_str,
            status=status,
            enabled=enabled_str,
            downloaderType=downloader_type_int,
            downloaderId=downloader_id,
            port=port,
            downloaderTypeName=downloader_type_name,
            connectStatus=connectStatus,
            pathMappingRules=path_mapping_rules,
            torrentSavePath=torrent_save_path,
            **kw
        )


class DownloaderVO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(None, description="主键", example="1")
    nickname: str | None = Field(None, description="自定义名称", example="qb")
    host: str | None = Field(None, description="下载器主机", example="1.1.1.1")
    username: str | None = Field(None, description="下载器登录用户名", example="admin")
    password: str | None = Field(None, description="下载器登录密码", example="admin")
    isSearch: str | None = Field(None, alias="isSearch", description="是否启用种子搜索", example="1")
    status: str | None = Field(None, description="下载器状态", example="1")  #
    enabled: str | None = Field(None, description="下载器启用状态", example="1")  #
    downloaderType: int | None = Field(None, alias="downloaderType", description="下载器类型(0=qBittorrent, 1=Transmission)", example=0)
    port: int | None = Field(None, description="端口", example="qbittorrent")
    isSsl: str | None = Field(None, alias="isSsl", description="是否https", example="qbittorrent")
    downloaderTypeName: str | None = Field(None, alias="downloaderTypeName", description="下载器类型名称", example="qbittorrent")
    pathMappingRules: str | None = Field(None, alias="pathMappingRules", description="路径映射规则配置")
    torrentSavePath: str | None = Field(None, alias="torrentSavePath", description="种子保存目录路径")

    def __init__(self, downloader_id, nickname, host, username, password, is_search, status, enabled, downloader_type,port,is_ssl,
                 path_mapping_rules=None, torrent_save_path=None, **kw: Any):
        # 使用统一的类型转换方法
        downloader_type_int = None
        downloader_type_name = None
        if downloader_type is not None:
            # 使用枚举类的 normalize 方法统一转换
            downloader_type_int = DownloaderTypeEnum.normalize(downloader_type)
            downloader_type_name = DownloaderTypeEnum(downloader_type_int).to_name()

        # 将整数 0/1 转换为字符串 "0"/"1"（修复 Pydantic 验证错误）
        # 修复P1问题：使用精确的枚举值检查，避免将0误判
        is_search_str = str(is_search) if is_search in (0, 1) else None
        enabled_str = str(enabled) if enabled in (0, 1) else None
        is_ssl_str = str(is_ssl) if is_ssl in (0, 1) else None
        status_str = str(status) if status in (0, 1) else None

        super().__init__(
            id=downloader_id,
            nickname=nickname,
            host=host,
            username=username,
            password=None,  # 不返回密码字段
            isSearch=is_search_str,
            status=status_str,
            enabled=enabled_str,
            downloaderType=downloader_type_int,
            port=int(port),
            isSsl=is_ssl_str,
            downloaderTypeName=downloader_type_name,
            pathMappingRules=path_mapping_rules,
            torrentSavePath=torrent_save_path,
            **kw
        )

    def get_decrypted_password(self) -> str:
        """获取解密后的密码"""
        return decrypt_password(self.password) if self.password else None

    # 兼容性属性访问器 - 支持 snake_case 命名约定
    @property
    def downloader_type(self) -> str | None:
        """获取下载器类型 (兼容 snake_case 访问)"""
        return self.downloaderType

    @property
    def is_search(self) -> str | None:
        """是否启用种子搜索 (兼容 snake_case 访问)"""
        return self.isSearch

    @property
    def is_ssl(self) -> str | None:
        """是否https (兼容 snake_case 访问)"""
        return self.isSsl


class DownloaderStatusVO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    connectStatus: str = Field(None, alias="connectStatus", description="连接状态", example="1")
    nickname: str = Field(None, description="下载器名称", example="1")
    delay: float | None = Field(None, description="延迟(毫秒)", example="3.64")
    id: str = Field(None, description="主键", example="1")
    uploadSpeed: str | None = Field(None, alias="uploadSpeed", description="上传速度(自动单位)", example="1.5")
    downloadSpeed: str | None = Field(None, alias="downloadSpeed", description="下载速度(自动单位)", example="2.3")
    downloadingCount: int | None = Field(None, alias="downloadingCount", description="下载中种子数量", example=5)
    seedingCount: int | None = Field(None, alias="seedingCount", description="做种中种子数量", example=10)
