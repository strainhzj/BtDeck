from fastapi import FastAPI

from app.core.config import settings


def init_routers(app: FastAPI):
    """
    初始化路由
    """
    from app.api.api import api_router
    from app.api.endpoints.health import router as health_router

    # 旧 app.api.router 归档文件已删除（P2-3 清理），禁止在生产入口重新挂载。
    # from app.api.servarr import arr_router
    # from app.api.servcookie import cookie_router
    # 根路径基础健康检查：Docker/Compose 不依赖 /api/v1 前缀，也不需要认证。
    app.include_router(health_router)
    # API路由
    app.include_router(api_router, prefix=settings.API_V1_STR)
    # Radarr、Sonarr路由
    # app.include_router(arr_router, prefix="/api/v3")
    # CookieCloud路由
    # app.include_router(cookie_router, prefix="/cookiecloud")
