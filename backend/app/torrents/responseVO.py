from typing import List
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict
from app.torrents.trackerVO import TrackerInfoVO


def alias_camel(snake_name: str) -> str:
    """将snake_case转换为camelCase"""
    parts = snake_name.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class TorrentInfoVO(BaseModel):
    """种子信息VO，支持前端snake_case命名和后端camelCase序列化"""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=alias_camel, from_attributes=True  # 支持ORM对象转换
    )

    # 基础字段 - 使用snake_case定义，自动转换为camelCase输出
    info_id: str | None = Field(None, description="主键", examples=["0573620f-d38f-4aa9-bc6e-cde655282176"])
    downloader_id: str | None = Field(
        None, description="所属下载器主键", examples=["d2f6192e-b197-4632-b4eb-bb7604446c07"]
    )
    downloader_name: str | None = Field(None, description="所属下载器名称", examples=["tr1"])
    torrent_id: str | None = Field(None, description="下载器中的主键", examples=["1"])
    hash: str | None = Field(None, description="种子哈希值", examples=["47f130f4ec8cf6685a87d5816fb4a7d4e43bef86"])
    name: str | None = Field(
        None,
        description="种子名称",
        examples=["The Matrix Trilogy 1999-2003 CEE Blu-ray 1080p VC-1 TrueHD 5.1-DIY@HDSky"],
    )
    save_path: str | None = Field(None, description="种子文件保存路径", examples=["/Downloads/lpan/Downloads"])
    size: int | None = Field(None, description="种子大小(字节)", examples=["134002221056"])
    status: str | None = Field(None, description="状态", examples=["seeding"])
    error_reason: str | None = Field(None, description="下载器返回的种子错误原因")
    torrent_file: str | None = Field(
        None, description="种子文件路径", examples=["/config/torrents/47f130f4ec8cf6685a87d5816fb4a7d4e43bef86.torrent"]
    )
    auxiliary_seed_count: int = Field(1, description="辅种数量", examples=[1, 4])
    added_date: datetime | None = Field(None, description="添加时间")
    completed_date: datetime | None = Field(None, description="完成时间")
    ratio: float | None = Field(None, description="做种比率", examples=[0.1048])
    ratio_limit: float | None = Field(None, description="比率限制；NULL 表示无限制", examples=[2.0])
    tags: str | None = Field(None, description="标签", examples=["下载"])
    category: str | None = Field(None, description="分类", examples=["下载"])
    super_seeding: str | None = Field(None, description="超级做种模式", examples=["否"])
    enabled: bool | None = Field(None, description="是否启用", examples=[True])

    # Tracker信息字段
    tracker_name: str | None = Field("", description="tracker服务器名称", examples=[""])
    tracker_url: str | None = Field("", description="tracker地址", examples=[""])
    last_announce_succeeded: str | None = Field("", description="最后一次announce是否成功", examples=[""])
    last_announce_msg: str | None = Field("", description="最后一次announce消息", examples=[""])
    last_scrape_succeeded: str | None = Field("", description="最后一次scrape是否成功", examples=[""])
    tracker_info: List[TrackerInfoVO] | None = Field(default_factory=list, description="tracker信息列表")

    # 计算属性 - 兼容前端显示需求
    progress: float | None = Field(None, description="下载进度(百分比)", examples=[75.5])
    state: str | None = Field(None, description="状态描述", examples=["下载中"])
    download_speed: int | None = Field(None, description="下载速度(B/s)", examples=[1048576])
    upload_speed: int | None = Field(None, description="上传速度(B/s)", examples=[524288])
    peers: int | None = Field(None, description="连接的peer数量", examples=[10])
    seeds: int | None = Field(None, description="连接的seed数量", examples=[5])

    @classmethod
    def from_orm(cls, obj) -> "TorrentInfoVO":
        """从ORM对象创建VO实例"""
        return cls.model_validate(obj)
