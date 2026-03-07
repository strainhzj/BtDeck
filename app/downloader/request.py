from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from app.api.schemas.path_mapping import PathMappingConfig


class RequestDownloader(BaseModel):
    host: str = Field(description="下载器主机地址", example="1.1.1.1")
    nickname: str = Field(description="下载器别名", example="qb")
    username: str = Field(description="下载器登录用户名", example="admin")
    password: str = Field(description="下载器登录密码", example="admin")
    is_search: bool = Field(description="是否启用搜索的下载器标识，0表示停用，1表示启用", example=True)
    downloader_type: int = Field(description="下载器类型(0=qBittorrent, 1=Transmission)", example=0)
    enabled: bool = Field(description="下载器启用标识，0表示停用，1表示启用", example=True)
    port: int | None = Field(None, description="端口", example=1)
    is_ssl: bool = Field(description="是否https，0表示否，1表示是", example=True)

    # 新增: 路径映射配置
    path_mapping: Optional[PathMappingConfig] = Field(
        None,
        description="路径映射配置(JSON对象或已解析的对象)"
    )

    # 新增: 路径映射规则（多行文本格式）
    path_mapping_rules: Optional[str] = Field(
        None,
        description="路径映射规则配置（多行文本，格式：源路径{#**#}目标路径）"
    )

    # 新增: 种子保存目录
    torrent_save_path: Optional[str] = Field(
        None,
        description="种子保存目录路径（应用运行环境可直接访问的绝对路径）",
        max_length=500
    )

    @field_validator('is_search', 'enabled', 'is_ssl', mode='before')
    @classmethod
    def convert_str_to_bool(cls, v, info):
        """将字符串 "0"/"1" 转换为布尔值

        Args:
            v: 输入值，可能是字符串或布尔值
            info: 字段验证信息

        Returns:
            bool: 转换后的布尔值

        Raises:
            ValueError: 如果输入值不是 "0", "1" 或布尔值
        """
        # 如果已经是布尔值，直接返回
        if isinstance(v, bool):
            return v

        # 如果是字符串，进行转换
        if isinstance(v, str):
            if v == "1":
                return True
            elif v == "0":
                return False

        # 其他情况抛出错误
        field_name = info.field_name
        raise ValueError(f'{field_name} 必须是 "0"、"1" 或布尔值，当前值: {v}')


class ListDownloader(BaseModel):
    downloader_id: str | None = Field(None, description="下载器数据id，用于精确查询", example="1")
    host: str | None = Field(None, description="下载器主机地址", example="1.1.1.1")
    nickname: str | None = Field(None, description="下载器别名", example="qb")
    is_search: str | None = Field(None, description="是否启用搜索的下载器标识，0表示停用，1表示启用", example="1")
    downloader_type: int | None = Field(None, description="下载器类型(0=qBittorrent, 1=Transmission)", example=0)
    enabled: str | None = Field(None, description="下载器启用标识，0表示停用，1表示启用", example="1")


class UpdateDownloader(BaseModel):
    host: str | None = Field(None, description="下载器主机地址", example="1.1.1.1")
    nickname: str | None = Field(None, description="下载器别名", example="qb")
    username: str | None = Field(None, description="下载器登录用户名", example="admin")
    password: str | None = Field(None, description="新密码（不修改请留空）", example="")
    old_password: str | None = Field(None, description="原密码（修改密码或用户名时必填）", example="")
    is_search: bool = Field(description="是否启用搜索的下载器标识，0表示停用，1表示启用", example=True)
    enabled: bool = Field(description="下载器启用标识，0表示停用，1表示启用", example=True)
    downloader_type: int | None = Field(None, description="下载器类型(0=qBittorrent, 1=Transmission)", example=0)
    port: int | None = Field(None, description="端口", example=1)
    is_ssl: bool = Field(description="是否https，0表示否，1表示是", example=True)

    # 新增: 路径映射配置
    path_mapping: Optional[PathMappingConfig] = Field(
        None,
        description="路径映射配置(更新时可选)"
    )

    # 新增: 路径映射规则（多行文本格式）
    path_mapping_rules: Optional[str] = Field(
        None,
        description="路径映射规则配置（多行文本，格式：源路径{#**#}目标路径）"
    )

    # 新增: 种子保存目录
    torrent_save_path: Optional[str] = Field(
        None,
        description="种子保存目录路径（应用运行环境可直接访问的绝对路径）",
        max_length=500
    )

    @field_validator('is_search', 'enabled', 'is_ssl', mode='before')
    @classmethod
    def convert_str_to_bool(cls, v, info):
        """将字符串 "0"/"1" 转换为布尔值

        Args:
            v: 输入值，可能是字符串或布尔值
            info: 字段验证信息

        Returns:
            bool: 转换后的布尔值

        Raises:
            ValueError: 如果输入值不是 "0", "1" 或布尔值
        """
        # ✅ 修复：如果是 None，返回默认值 False
        if v is None:
            return False

        # 如果已经是布尔值，直接返回
        if isinstance(v, bool):
            return v

        # 如果是字符串，进行转换
        if isinstance(v, str):
            if v == "1":
                return True
            elif v == "0":
                return False

        # 其他情况抛出错误
        field_name = info.field_name
        raise ValueError(f'{field_name} 必须是 "0"、"1" 或布尔值，当前值: {v}')


class DownloaderCheckVO(BaseModel):
    nickname: str | None = Field(None, description="下载器别名", example="qb")
    client: Any = Field(None, description="下载器客户端")
    fail_time: int = Field(0, description="校验失败次数", example=0)
    # 添加额外的字段以供同步任务使用
    downloader_id: str | None = Field(None, description="下载器ID", example="1")
    host: str | None = Field(None, description="下载器主机", example="127.0.0.1")
    port: int | None = Field(None, description="下载器端口", example=8080)
    username: str | None = Field(None, description="下载器用户名", example="admin")
    password: str | None = Field(None, description="下载器密码", example="admin123")
    downloader_type: int | None = Field(None, description="下载器类型(0=qBittorrent, 1=Transmission)", example=0)
    torrent_save_path: Optional[str] = Field(None, description="torrent_save_path")

    # 实时状态字段（缓存使用）
    upload_speed: float | None = Field(None, description="上传速度(KB/s)", example=1024.5)
    download_speed: float | None = Field(None, description="下载速度(KB/s)", example=2048.7)
    downloading_count: int | None = Field(None, description="下载中种子数量", example=5)
    seeding_count: int | None = Field(None, description="做种中种子数量", example=10)
    delay: float | None = Field(None, description="网络延迟(毫秒)", example=15.5)
    is_online: bool | None = Field(False, description="是否在线（基于端口连通性）", example=True)
    last_update: float | None = Field(None, description="最后更新时间戳", example=1234567890.123)

    # 种子统计缓存（支持增量更新）
    stats_cache: Any = Field(None, description="种子统计缓存管理器（TorrentStatsCache 实例）")
