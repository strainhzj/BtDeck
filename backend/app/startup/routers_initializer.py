from fastapi import FastAPI

from app.core.config import settings


def init_routers(app: FastAPI):
    """
    初始化路由
    """
    from app.api.api import api_router
    # from app.api import router
    # from app.api.servarr import arr_router
    # from app.api.servcookie import cookie_router
    # API路由
    app.include_router(api_router, prefix=settings.API_V1_STR)
    # app.include_router(router.router, prefix="/api/public")
    # Radarr、Sonarr路由
    # app.include_router(arr_router, prefix="/api/v3")
    # CookieCloud路由
    # app.include_router(cookie_router, prefix="/cookiecloud")
