from fastapi import FastAPI

from app.core.config import settings


def init_routers(app: FastAPI):
    """
    初始化路由
    """
    from app.api.api import api_router

    # 旧 app.api.router 归档文件已删除（P2-3 清理），禁止在生产入口重新挂载。
    # from app.api.servarr import arr_router
    # from app.api.servcookie import cookie_router
    # API路由
    app.include_router(api_router, prefix=settings.API_V1_STR)
    # Radarr、Sonarr路由
    # app.include_router(arr_router, prefix="/api/v3")
    # CookieCloud路由
    # app.include_router(cookie_router, prefix="/cookiecloud")
