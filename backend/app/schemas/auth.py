from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    password: str


class UserInDB(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    two_factor_enabled: Optional[bool] = False


class User(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    two_factor_enabled: Optional[bool] = False


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class TwoFactorResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    userId: int = Field(alias='userId')
    code: str


class TwoFactorSetup(BaseModel):
    secret: str
    qr_code: str
    uri: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    accessToken: Optional[str] = Field(None, alias='accessToken')
    tokenType: Optional[str] = Field(None, alias='tokenType')
    requires2fa: Optional[bool] = Field(False, alias='requires2fa')
    userId: Optional[int] = Field(None, alias='userId')


class ConfigUpdate(BaseModel):
    value: str
    description: Optional[str] = None


class ConfigItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    description: Optional[str] = None
