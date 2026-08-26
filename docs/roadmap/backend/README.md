# backend 分支 — FastAPI 后端总览

> Python 3.11+ / FastAPI 0.115 / SQLAlchemy + SQLite（异步 + 同步双引擎）。本分支是 BtDeck 的服务端，含 HTTP API、WebSocket、定时任务调度、ORM、数据迁移与下载器/Tracker 业务逻辑。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/README.md`，命中行即含子分支 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 子分支/文件 | 一句话职责 |
|--------|------------|-----------|
| 包根入口 app-root | [app-root.md](./app-root.md) | `backend/app/` 包根 8 文件（应用工厂、DB 引擎、异常处理、版本、入口） |
| 桌面伴侣 desktop-companion | [desktop-companion.md](./desktop-companion.md) | `app/desktop_companion/`：服务器 profile/健康检查/内嵌 pywebview；用户名随 profile 保存，密码由 Windows DPAPI 保险库存储，首屏同源脚本恢复登录会话 |
| HTTP 路由 api | [api/README.md](./api/README.md) | HTTP 路由层 43 文件（endpoints 37 + models 1 + schemas 3 + api.py + responseVO.py，不计 `__init__.py`） |
| 业务服务 services | [services/README.md](./services/README.md) | 业务服务层 57 文件（services 47 + downloader_adapters 5 + tag_adapters 5，不计 `__init__.py`） |
| 基础设施 core | [core/README.md](./core/README.md) | 基础设施 23 文件（⚠ 含 4 个 0 引用孤儿；`torrent_operations.py` 已重写为 ratio 工具但仍 0 引用） |
| 前后端契约 contracts | [contracts/README.md](./contracts/README.md) | 前后端共享机器可读契约 3 文件（advanced_search JSON + 加载器）✨v1.0.6.27 |
| 数据层 data-models | [data-models/README.md](./data-models/README.md) | 数据层 37 文件（ORM 18 + response 2 + repositories 3 + schemas 8 + data 4 + enums 2） |
| 定时任务 tasks | [tasks/README.md](./tasks/README.md) | 定时任务 33 文件（tasks 14 + scheduler 16 + scheduler/torrent_sync 3，不计 `__init__.py`） |
| 领域 domain | [domain/README.md](./domain/README.md) | 领域目录 27 文件（downloader 9 + torrents 9 + tracker 1 + auth 7 + user 1） |
| 横切基础设施 infra | [infra/README.md](./infra/README.md) | 横切基础设施（含 Alembic 29 个 revision；当前 head `c1d2e3f4a5b6`） |

---

## 跨分支依赖骨架（自顶向下）

```
入口层    app/main.py ─┐
                      ├─→ app/factory.py:create_app ─┬─→ app/startup/lifecycle.py:lifespan
                      │                              ├─→ app/exception_handlers.py
                      │                              └─→ app/api/api.py:api_router
                      │                                    ↓
路由层    app/api/endpoints/*.py ─────────────────────────┘
                      ↓
服务层    app/services/*.py ──── app/services/{downloader,tag}_adapters/*.py
                      ↓
核心层    app/core/{config,path_mapping,database_result,migration}.py   ← 基础设施
                      ↓
数据层    app/models/*.py (ORM) ← app/repositories/*.py ← app/database.py (引擎)
                      ↑                                  ↑
                      │                                  │ 前后端共享契约
领域层    app/{downloader,torrents,tracker,auth,user}/*.py  app/contracts/*.json（advanced_search 等）
                      ↑
                      │
迁移层    app/migrations/database_migrator.py  ⚡ 应用层数据/字段迁移（运行时）
          backend/alembic/                    ⚡ schema 版本迁移（revision）
```

## 关键骨架型依赖（被高频 import）

| 模块 | 被引用文件数 | 角色 |
|------|------------|------|
| `app.database` | **98** | DB 引擎与会话工厂（同步 + 异步） |
| `app.services.*` | 73 | 业务服务层 |
| `app.auth.dependencies`（`require_authenticated_user`） | 29 | FastAPI 认证依赖 |
| `app.core.config` | 40 | 全局配置 `Settings` |
| `app.api.responseVO.CommonResponse` | — | 统一响应信封 |
| `app.core.database_result` | 11 | `DatabaseResult` 泛型封装 |
| `app.core.path_mapping` | 10 | 下载器路径双向映射 |

详见 [perspectives/architecture.md](../perspectives/architecture.md) 的调用链索引。

---

## 关键约定（仅索引，详见约束文档）

- **API 响应格式**：所有接口必须返回 `CommonResponse[T]`，分页字段固定为 `list/total/pageSize` → [../../backend/docs/constraints/api-response-format.md](../../backend/docs/constraints/api-response-format.md)
- **数据库迁移**：schema 变更必须走 Alembic；应用启动时自动执行 → [../../backend/docs/constraints/database-migration.md](../../backend/docs/constraints/database-migration.md)
- **下载器连接**：必须复用 `app.state.store` 缓存中的客户端连接，禁止重复创建 → [../../backend/docs/constraints/downloader-connection.md](../../backend/docs/constraints/downloader-connection.md)
- **代码复用**：相似度 >50% 必须扩展现有代码 → [../../backend/docs/constraints/code-reuse.md](../../backend/docs/constraints/code-reuse.md)

## 技术债提示

- `app/core/` 含 5 个 0 引用孤儿文件（security.py / downloader.py / torrent_operations.py / tracker_operations.py / init_schema_from_production.py）→ 见 [core/README.md](./core/README.md) 与 [../perspectives/risks.md](../perspectives/risks.md)
- 应用层迁移（`app/migrations/`）与 schema 迁移（`alembic/`）双轨并存 → 详见 [../../backend/docs/architecture-deep-dive.md](../../backend/docs/architecture-deep-dive.md) "二、数据库迁移双轨"
- 入口分散：`main.py`（uvicorn 配置）、`factory.py`（app 工厂）、`btdeck_startup.sh`（Docker 入口）三处对启动有发言权 → 见 [../perspectives/risks.md](../perspectives/risks.md)
