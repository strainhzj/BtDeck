from pydantic import BaseModel, Field, ConfigDict

class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    oldPassword: str = Field(alias="old_password", description="旧密码，用base64编码", example="YWRtaW4=")
    newPassword: str = Field(alias="new_password", description="新密码，用base64编码", example="YWRtaW4x")
    userId: str = Field(alias="user_id", description="用户id", example="1")

class TwofactorVerifyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    userId: str = Field(description="用户id", example="1")
    twofaFlag: str = Field(description="启用标识，1启用2fa，0停用", example="1")
    twoFactorCode: str | None = Field(None, description="2fa验证码", example="1")
    password: str | None = Field(None, description="当前密码（停用2FA时需要验证）", example="123456")

class VerifyPasswordFor2FARequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    userId: str = Field(description="用户id", example="1")
    password: str = Field(description="当前密码", example="123456")
