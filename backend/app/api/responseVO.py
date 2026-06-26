from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional

T = TypeVar("T")


class CommonResponse(BaseModel, Generic[T]):
    status: Optional[str] = Field(None, description="返回接口调用结果", examples=["success"])
    msg: Optional[str] = Field(None, description="返回接口调用信息", examples=["接口调用成功"])
    code: Optional[str] = Field(None, description="返回接口调用结果编码", examples=["200"])
    data: Optional[T] = Field(None, description="返回数据集")

    model_config = {"arbitrary_types_allowed": True}
