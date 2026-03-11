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
