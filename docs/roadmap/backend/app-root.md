# backend/app-root — 包根入口文件

> `backend/app/` 包根 10 个文件（非子包），承担应用工厂、DB 引擎、异常处理、版本、多种入口。

## 文件清单

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `__init__.py` | 0 | — | 空包标识（跳过） |
| `config.py` | 5 | 0 class, 0 def | 兼容层：旧代码 `from app.config import settings` 转发到 `app.core.config` |
| `database.py` | 435 | 0 class, 6 def | 数据库引擎与会话工厂（`get_db` / `get_async_db` / `init_db` / `init_config_file` / `merge_configs` / `_apply_sqlite_pragmas`） |
| `desktop_main.py` | 103 | 0 class, 7 def | 桌面端入口（pywebview），日志配置 + 子进程启停后台 API |
| `exception_handlers.py` | 237 | 0 class, 8 def | 全局异常处理器：把 `HTTPException` / `RequestValidationError` / 未捕获异常统一归一化为 `CommonResponse` |
| `factory.py` | 117 | 0 class, 4 def | FastAPI 应用工厂（`create_app` + 路由/静态/CORS/lifespan 配置） |
| `main.py` | 95 | 0 class, 0 def | 后端启动入口：配置 uvicorn server（单进程），执行 `init_config_file` + `migrate_database` 后 `Server.run()` |
| `version.py` | 161 | 0 class, 5 def | 版本信息集中管理（`get_version_info` / `get_current_version` / `get_version_content` / `VERSION_HISTORY` 常量） |
| `websocket_main.py` | 22 | 0 class, 0 def | WebSocket 服务独立入口，单独跑 uvicorn on `settings.WS_PORT` |
| `yamlConfig.py` | 92 | 1 class, 0 def | `Yaml` 配置类（点表示法访问嵌套配置，封装 pyyaml） |

---

## 关键调用关系

```
启动入口
  ├─ Docker:    btdeck_startup.sh → uvicorn app.main:app
  ├─ 桌面:      desktop_main.py → 启动子进程跑 main.py
  └─ WebSocket: websocket_main.py（独立服务，端口 WS_PORT）

main.py
  ├─→ app.database.init_config_file()
  ├─→ app.core.migration.migrate_database()
  └─→ app.factory.app  (uvicorn 加载的 ASGI app)

factory.py:create_app(configure_routes)
  ├─→ CORSMiddleware 注册（校验 ALLOWED_HOSTS 不含 "*"）
  ├─→ app.exception_handlers.register_exception_handlers(app)
  ├─→ app.startup.lifecycle.lifespan（init_db / 后台任务 / 下载器初始化）
  └─→ app.startup.routers_initializer.init_routers(app)
        └─→ app.api.api.api_router (prefix=API_V1_STR)
```

## 注意事项

- **入口分散**：`main.py`（uvicorn 配置 + 早期迁移）、`factory.py`（app 工厂 + 路由/SPA fallback）、`btdeck_startup.sh`（Docker 入口，再配置 uvicorn）三处都对"如何启动"有发言权。详见 [../perspectives/risks.md](../perspectives/risks.md)。
- **双 SPA fallback**：Docker 部署用 nginx（`frontend/nginx.conf`），PyInstaller 单机打包用 `factory.py:_mount_frontend_static`。
- **`main.py` 无 app 实例**：app 来自 `from app.factory import app`，业务路由在 factory 中通过 `init_routers` 挂载，main.py 只负责 uvicorn server 配置。
