# app/auth/models.py
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    password: Mapped[Optional[str]] = mapped_column(String)  # bcrypt 哈希（存量旧格式为 AES-ECB 密文，登录时自动升级）
    two_factor_secret: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 2FA密钥
    two_factor_flag: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    # 首次登录/默认口令强制改密标志（安全修复 W9）
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """refresh token 持久化记录（双令牌体系，verified-bugfix-remediation W6-1）。

    - token 本体不落库：仅存 SHA-256 哈希（防盗库直接使用）
    - 使用即轮换：/auth/refresh 换发新 token 时旧记录置 revoked_at
    - 登出撤销：/users/logout 撤销该用户全部未过期记录
    """

    __tablename__ = "refresh_tokens"

    # v1.0.8 任务3.4 对拍归位：nullable=False 对齐迁移链 a8b9c0d1e2f3（链侧即
    # NOT NULL；metadata 声明漂移会使 PG 基线建成可空列）；id 不建索引（链无，
    # PK 已覆盖——index=True 会生成链不存在的 ix_refresh_tokens_id）
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=False, index=True)
    token_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )  # SHA-256 hex
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class LoginLog(Base):
    __tablename__ = "login_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String)
    ip_address: Mapped[Optional[str]] = mapped_column(String)
    user_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    success: Mapped[Optional[bool]] = mapped_column(Boolean)
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Config(Base):
    __tablename__ = "configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[Optional[str]] = mapped_column(String, unique=True)
    value: Mapped[Optional[str]] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
