import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.startup.lifecycle import lifespan
from app.startup.routers_initializer import init_routers

logger = logging.getLogger(__name__)


def _get_frontend_dist_path() -> Path | None:
    """获取前端静态文件目录路径（PyInstaller 打包模式或开发模式）"""
    candidates = [
        # PyInstaller 打包后，frontend_dist 在 _MEIPASS 临时目录中
        Path(sys._MEIPASS) / "frontend_dist" if hasattr(sys, "_MEIPASS") else None,
        # 开发模式：项目根目录下的 frontend/dist
        settings.ROOT_PATH.parent / "frontend" / "dist",
        # 兼容历史路径：backend/frontend/dist
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


def _mount_frontend_static(app: FastAPI) -> None:
    """挂载前端静态文件与 SPA fallback。"""
    if getattr(app.state, "frontend_static_mounted", False):
        return

    # 内嵌前端静态文件服务（PyInstaller 打包模式）
    frontend_path = _get_frontend_dist_path()
    if frontend_path:
        # 挂载静态资源目录（JS/CSS/图片等）
        app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="static_assets")

        # Vue Router history mode fallback：非 API 路由返回 index.html
        @app.get("/{path:path}")
        async def serve_frontend(path: str):
            """前端路由 fallback"""
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")

            file_path = frontend_path / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_path / "index.html"))

    app.state.frontend_static_mounted = True


def configure_routes_and_static(app: FastAPI) -> None:
    """按 API 路由优先、SPA fallback 最后的顺序完成路由挂载。"""
    api_module = sys.modules.get("app.api.api")
    if api_module is not None and not hasattr(api_module, "api_router"):
        # 命中此分支即代表发生循环 import：app.api.api 正在加载（半成品，尚未定义 api_router），
        # 其内部某个 endpoint 模块顶层 import 了 app.factory，触发本函数提前执行。
        # 此时业务路由无法挂载，全局 app 只剩默认路由（历史 bug：tag_aggregation 测试 404）。
        # 端点模块应在函数体内 lazy import app，而非顶层 import。
        logger.warning(
            "检测到 app.api.api 循环 import：configure_routes_and_static 早退，"
            "全局 app 未注册业务路由。请检查 endpoint 模块是否顶层 import 了 app.factory/main。"
        )
        return

    if not getattr(app.state, "api_routers_initialized", False):
        init_routers(app)
        app.state.api_routers_initialized = True

    _mount_frontend_static(app)


def create_app(configure_routes: bool = True) -> FastAPI:
    """
    创建并配置 FastAPI 应用实例。
    """
    # CORS 使用 allow_credentials=True 时不能接受通配来源，避免浏览器凭证跨域策略被误配置。
    if "*" in settings.ALLOWED_HOSTS:
        raise RuntimeError("ALLOWED_HOSTS 不允许包含 '*'，请配置明确的前端来源")

    _app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json", lifespan=lifespan)

    # 配置 CORS 中间件
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册全局异常处理器：归一化 HTTPException/422/未捕获异常为 CommonResponse
    from app.exception_handlers import register_exception_handlers

    register_exception_handlers(_app)

    if configure_routes:
        configure_routes_and_static(_app)

    return _app


# 创建 FastAPI 应用实例。
# 先暴露全局 app，再注册 API，可兼容既有端点中 `from app.factory import app` 的导入方式。
app = create_app(configure_routes=False)
configure_routes_and_static(app)
