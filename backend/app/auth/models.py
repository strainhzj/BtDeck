# app/auth/models.py
from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)  # SM4加密后的密码
    two_factor_secret = Column(String, nullable=True)  # 2FA密钥
    two_factor_flag = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """refresh token 持久化记录（双令牌体系，verified-bugfix-remediation W6-1）。

    - token 本体不落库：仅存 SHA-256 哈希（防盗库直接使用）
    - 使用即轮换：/auth/refresh 换发新 token 时旧记录置 revoked_at
    - 登出撤销：/users/logout 撤销该用户全部未过期记录
    """

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    token_hash = Column(String(64), unique=True, index=True)  # SHA-256 hex
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)


class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String)
    ip_address = Column(String)
    user_agent = Column(String, nullable=True)
    success = Column(Boolean)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


class Config(Base):
    __tablename__ = "configs"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True)
    value = Column(String)
    description = Column(String, nullable=True)
