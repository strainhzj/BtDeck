from pydantic import BaseModel, Field
from typing import Generic, TypeVar, Optional

T = TypeVar("T")


class CommonResponse(BaseModel, Generic[T]):
    # 注意：默认值必须用 Field(default=...) 关键字形式；mypy 对 pydantic 泛型模型
    # 不识别 Field(<positional>) 位置默认值，会把 data 误判为构造必填参数
    status: Optional[str] = Field(default=None, description="返回接口调用结果", examples=["success"])
    msg: Optional[str] = Field(default=None, description="返回接口调用信息", examples=["接口调用成功"])
    code: Optional[str] = Field(default=None, description="返回接口调用结果编码", examples=["200"])
    data: Optional[T] = Field(default=None, description="返回数据集")

    model_config = {"arbitrary_types_allowed": True}
