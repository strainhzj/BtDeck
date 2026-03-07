from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class TrackerInfoVO(BaseModel):
    """Tracker信息VO对象，使用驼峰命名法"""
    model_config = ConfigDict(populate_by_name=True)

    tracker_id: Optional[str] = Field(None, description="tracker数据主键", example="t1")
    tracker_name: Optional[str] = Field(None, description="tracker名称字符串", example="tracker.example.com")
    tracker_url: Optional[str] = Field(None, description="tracker地址字符串", example="http://tracker.example.com:2710/announce")
    last_announce_succeeded: Optional[str] = Field(None, description="announce状态字符串", example="1")
    last_announce_msg: Optional[str] = Field(None, description="announce消息字符串", example="Success")
    last_scrape_succeeded: Optional[str] = Field(None, description="scrape状态字符串", example="1")
    last_scrape_msg: Optional[str] = Field(None, description="scrape消息字符串", example="Success")

    def __init__(self, tracker_id=None, tracker_name=None, tracker_url=None,
                 last_announce_succeeded=None, last_announce_msg=None,
                 last_scrape_succeeded=None, last_scrape_msg=None, **kwargs):
        super().__init__(
            tracker_id=tracker_id,
            tracker_name=tracker_name,
            tracker_url=tracker_url,
            last_announce_succeeded=last_announce_succeeded,
            last_announce_msg=last_announce_msg,
            last_scrape_succeeded=last_scrape_succeeded,
            last_scrape_msg=last_scrape_msg,
            **kwargs
        )