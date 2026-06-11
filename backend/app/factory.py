import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.startup.lifecycle import lifespan


def _get_frontend_dist_path() -> Path | None:
    """获取前端静态文件目录路径（PyInstaller 打包模式或开发模式）"""
    candidates = [
        # PyInstaller 打包后，frontend_dist 在 _MEIPASS 临时目录中
        Path(sys._MEIPASS) / "frontend_dist" if hasattr(sys, '_MEIPASS') else None,
        # 开发模式：项目根目录下的 frontend/dist
        settings.ROOT_PATH / "frontend" / "dist",
        # PyInstaller 打包后可执行文件同级的 frontend_dist
        Path(sys.executable).parent / "frontend_dist",
    ]
    for path in candidates:
        if path and path.exists() and path.is_dir():
            index_html = path / "index.html"
            if index_html.exists():
                return path
    return None


def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用实例。
    """
    _app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan
    )

    # 配置 CORS 中间件
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 内嵌前端静态文件服务（PyInstaller 打包模式）
    frontend_path = _get_frontend_dist_path()
    if frontend_path:
        # 挂载静态资源目录（JS/CSS/图片等）
        _app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="static_assets")

        # Vue Router history mode fallback：非 API 路由返回 index.html
        @_app.get("/{path:path}")
        async def serve_frontend(path: str):
            """前端路由 fallback"""
            file_path = frontend_path / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_path / "index.html"))

    return _app


# 创建 FastAPI 应用实例
app = create_app()
