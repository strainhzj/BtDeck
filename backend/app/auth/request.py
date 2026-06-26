from pydantic import BaseModel, Field


# 定义请求体模型类
class UserLogin(BaseModel):
    username: str = Field(description="必填，登录用户名", examples=["admin"])
    password: str = Field(description="必填，登录密码，用base64编码", examples=["admin"])
    twofa_code: str | None = Field(None, description="2fa验证验证码，非必填，若设置了会在后端验证", examples=["842698"])
