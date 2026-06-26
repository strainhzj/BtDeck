from typing import List

from pydantic import BaseModel, Field


class Tracker(BaseModel):
    host: str = Field(description="tracker地址", examples=["1.1.1.1"])
    last_announce_result: str = Field(description="最后一次请求状态", examples=["Success"])
    last_scrape_result: str = Field(description="最后一次请求结果", examples=["Could not connect to tracker"])


class ModifyTrackerRequest(BaseModel):
    torrent_id_list: List[int] = Field(description="需要修改的种子idlist,取torrent_id", examples=["1.1.1.1"])
    downloader_id: str = Field(description="下载器id", examples=["d2f6192e-b197-4632-b4eb-bb7604446c07"])
    trackers: str = Field(description="tracker地址,多个以;分隔", examples=["d2f6192e-b197-4632-b4eb-bb7604446c07"])
