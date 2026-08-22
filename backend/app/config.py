# 兼容层：旧代码仍可使用 `from app.config import settings`。
# 配置唯一来源是 app.core.config，避免 JWT、CORS 等安全配置出现双轨默认值。
from app.core.config import Settings, settings

__all__ = ["Settings", "settings"]
