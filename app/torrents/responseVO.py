from typing import Any, List
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict
from app.torrents.trackerVO import TrackerInfoVO


def alias_camel(snake_name: str) -> str:
    """将snake_case转换为camelCase"""
    parts = snake_name.split('_')
    return parts[0] + ''.join(word.capitalize() for word in parts[1:])


class TorrentInfoVO(BaseModel):
    """种子信息VO，支持前端snake_case命名和后端camelCase序列化"""
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=alias_camel,
        from_attributes=True  # 支持ORM对象转换
    )

    # 基础字段 - 使用snake_case定义，自动转换为camelCase输出
    info_id: str | None = Field(None, description="主键", example="0573620f-d38f-4aa9-bc6e-cde655282176")
    downloader_id: str | None = Field(None, description="所属下载器主键", example="d2f6192e-b197-4632-b4eb-bb7604446c07")
    downloader_name: str | None = Field(None, description="所属下载器名称", example="tr1")
    torrent_id: str | None = Field(None, description="下载器中的主键", example="1")
    hash: str | None = Field(None, description="种子哈希值", example="47f130f4ec8cf6685a87d5816fb4a7d4e43bef86")
    name: str | None = Field(None, description="种子名称", example="The Matrix Trilogy 1999-2003 CEE Blu-ray 1080p VC-1 TrueHD 5.1-DIY@HDSky")
    save_path: str | None = Field(None, description="种子文件保存路径", example="/Downloads/lpan/Downloads")
    size: int | None = Field(None, description="种子大小(字节)", example="134002221056")
    status: str | None = Field(None, description="状态", example="seeding")
    torrent_file: str | None = Field(None, description="种子文件路径", example="/config/torrents/47f130f4ec8cf6685a87d5816fb4a7d4e43bef86.torrent")
    added_date: datetime | None = Field(None, description="添加时间")
    completed_date: datetime | None = Field(None, description="完成时间")
    ratio: str | None = Field(None, description="做种比率", example="0.1048")
    ratio_limit: str | None = Field(None, description="比率限制", example="2.0")
    tags: str | None = Field(None, description="标签", example="下载")
    category: str | None = Field(None, description="分类", example="下载")
    super_seeding: str | None = Field(None, description="超级做种模式", example="否")
    enabled: bool | None = Field(None, description="是否启用", example=True)

    # Tracker信息字段
    tracker_name: str | None = Field("", description="tracker服务器名称", example="")
    tracker_url: str | None = Field("", description="tracker地址", example="")
    last_announce_succeeded: str | None = Field("", description="最后一次announce是否成功", example="")
    last_announce_msg: str | None = Field("", description="最后一次announce消息", example="")
    last_scrape_succeeded: str | None = Field("", description="最后一次scrape是否成功", example="")
    tracker_info: List[TrackerInfoVO] | None = Field(default_factory=list, description="tracker信息列表")

    # 计算属性 - 兼容前端显示需求
    progress: float | None = Field(None, description="下载进度(百分比)", example=75.5)
    state: str | None = Field(None, description="状态描述", example="下载中")
    download_speed: int | None = Field(None, description="下载速度(B/s)", example=1048576)
    upload_speed: int | None = Field(None, description="上传速度(B/s)", example=524288)
    peers: int | None = Field(None, description="连接的peer数量", example=10)
    seeds: int | None = Field(None, description="连接的seed数量", example=5)

    @classmethod
    def from_orm(cls, obj) -> 'TorrentInfoVO':
        """从ORM对象创建VO实例"""
        return cls.model_validate(obj)
