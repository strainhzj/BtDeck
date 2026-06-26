from pydantic import BaseModel, Field, ConfigDict


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    oldPassword: str = Field(alias="old_password", description="旧密码，用base64编码", examples=["YWRtaW4="])
    newPassword: str = Field(alias="new_password", description="新密码，用base64编码", examples=["YWRtaW4x"])
    userId: str = Field(alias="user_id", description="用户id", examples=["1"])


class TwofactorVerifyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    userId: str = Field(description="用户id", examples=["1"])
    twofaFlag: str = Field(description="启用标识，1启用2fa，0停用", examples=["1"])
    twoFactorCode: str | None = Field(None, description="2fa验证码", examples=["1"])
    password: str | None = Field(None, description="当前密码（停用2FA时需要验证）", examples=["123456"])


class VerifyPasswordFor2FARequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    userId: str = Field(description="用户id", examples=["1"])
    password: str = Field(description="当前密码", examples=["123456"])
