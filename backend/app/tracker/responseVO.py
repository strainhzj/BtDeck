from pydantic import Field, ConfigDict
from pydantic.main import BaseModel


class TrackerInfoVO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trackerId: str | None = Field(
        None, alias="trackerId", description="主键", examples=["1d4af008-5b82-44f6-873e-acb9c8737153"]
    )
    torrentInfoId: str | None = Field(
        None, alias="torrentInfoId", description="关联种子主键", examples=["cf36ef63-8b37-4e2c-a062-fe9b3e353331"]
    )
    trackerName: str | None = Field(
        default=None, alias="trackerName", description="tracker名称", examples=["springsunday"]
    )
    trackerUrl: str | None = Field(
        None,
        alias="trackerUrl",
        description="tracker地址",
        examples=["http://on.springsunday.net/announce.php?passkey="],
    )
    lastAnnounceSucceeded: str | None = Field(
        None, alias="lastAnnounceSucceeded", description="请求结果", examples=["1"]
    )
    lastAnnounceMsg: str | None = Field(
        None, alias="lastAnnounceMsg", description="tracker最后一次请求信息", examples=["Success"]
    )
    lastScrapeSucceeded: str | None = Field(
        default=None, alias="lastScrapeSucceeded", description="汇报结果", examples=["1"]
    )
    lastScrapeMsg: str | None = Field(
        default=None, alias="lastScrapeMsg", description="", examples=["tracker最后一次汇报信息"]
    )
