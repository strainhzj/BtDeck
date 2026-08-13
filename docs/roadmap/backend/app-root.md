# backend/app-root — 包根入口文件

> `backend/app/` 包根 10 个文件（非子包），承担应用工厂、DB 引擎、异常处理、版本、多种入口。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/app-root.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 配置兼容 config-compat | `config.py` | 兼容层：旧代码 `from app.config import settings` 转发到 `app.core.config` |
| DB 引擎 database | `database.py` | 数据库引擎与会话工厂（`get_db` / `get_async_db` / `init_db` / `init_config_file` / `merge_configs` / `_apply_sqlite_pragmas`） |
| 桌面端 desktop | `desktop_main.py` | 桌面端入口（pywebview）；`initialize_app_data()`(L31) 初始化配置并在迁移失败时拒绝启动后台 API |
| 异常处理 exception | `exception_handlers.py` | 全局异常处理器：把 `HTTPException` / `RequestValidationError` / 未捕获异常统一归一化为 `CommonResponse` |
| 应用工厂 factory | `factory.py` | FastAPI 应用工厂（`create_app` + 路由/静态/CORS/lifespan 配置） |
| 启动入口 main | `main.py` | 后端启动入口：Docker import `app` 后由 lifespan 初始化；直接运行路径（L140-163）执行配置/迁移，迁移失败时不进入 `Server.run()` |
| 版本 version | `version.py` | 版本信息集中管理（`get_version_info` / `get_current_version` / `get_version_content` / `VERSION_HISTORY` 常量） |
| WebSocket websocket | `websocket_main.py` | WebSocket 服务独立入口，单独跑 uvicorn on `settings.WS_PORT` |
| YAML 配置 yaml | `yamlConfig.py` | `Yaml` 配置类（点表示法访问嵌套配置，封装 pyyaml） |

---

## 关键调用关系

```
启动入口
  ├─ Docker:    btdeck_startup.sh → uvicorn app.main:app
  ├─ 桌面:      desktop_main.py → 启动子进程跑 main.py
  └─ WebSocket: websocket_main.py（独立服务，端口 WS_PORT）

main.py
  ├─→ app.factory.app  (uvicorn 导入时加载 ASGI app)
  └─→ __main__ 直跑路径：init_config_file() → migrate_database() → Server.run()

factory.py:create_app(configure_routes)
  ├─→ CORSMiddleware 注册（校验 ALLOWED_HOSTS 不含 "*"）
  ├─→ app.exception_handlers.register_exception_handlers(app)
  ├─→ app.startup.lifecycle.lifespan（init_db / 后台任务 / 下载器初始化）
  └─→ app.startup.routers_initializer.init_routers(app)
        └─→ app.api.api.api_router (prefix=API_V1_STR)
```

## 注意事项

- **入口分散**：`main.py`（uvicorn 配置 + 直跑路径早期迁移）、`factory.py`（app 工厂 + 路由/SPA fallback）、`btdeck_startup.sh`（Docker 入口）三处都对"如何启动"有发言权。详见 [../perspectives/risks.md](../perspectives/risks.md)。
- **双 SPA fallback**：Docker 部署用 nginx（`frontend/nginx.conf`），PyInstaller 单机打包用 `factory.py:_mount_frontend_static`。
- **`main.py` 无 app 实例**：app 来自 `from app.factory import app`，业务路由在 factory 中通过 `init_routers` 挂载，main.py 只负责 uvicorn server 配置。
