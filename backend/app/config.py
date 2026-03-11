# app/config.py
import os
from pydantic import Field
from typing import Optional
from dotenv import load_dotenv

# 兼容新旧版本pydantic
try:
    from pydantic_settings import BaseSettings
except ImportError:
    try:
        from pydantic import BaseSettings
    except ImportError:
        # 如果都不存在，创建一个简单的BaseSettings类
        class BaseSettings:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

load_dotenv()


class Settings(BaseSettings):
    PROJECT_NAME: str = "btdeck"
    DATABASE_NAME: str = "app.db"
    SECRET_KEY: str = Field(default=os.getenv("SECRET_KEY", "YM4nwx3QBbZ227i5itqf"))
    SM4_KEY: Optional[str] = None  # 将在应用启动时生成
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 600
    ALGORITHM: str = "HS256"

    model_config = {"env_file": ".env"}


settings = Settings()
