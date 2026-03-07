from typing import List

from pydantic import BaseModel, Field

class Tracker(BaseModel):
    host: str = Field(description="tracker地址", example="1.1.1.1")
    last_announce_result: str = Field(description="最后一次请求状态", example="Success")
    last_scrape_result: str = Field(description="最后一次请求结果", example="Could not connect to tracker")

class ModifyTrackerRequest(BaseModel):
    torrent_id_list: List[int] = Field(description="需要修改的种子idlist,取torrent_id", example="1.1.1.1")
    downloader_id: str = Field(description="下载器id", example="d2f6192e-b197-4632-b4eb-bb7604446c07")
    trackers: str = Field(description="tracker地址,多个以;分隔", example="d2f6192e-b197-4632-b4eb-bb7604446c07")