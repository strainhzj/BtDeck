# CLAUDE.md - BTDeck后端项目

为Claude Code提供后端开发指导，专注于FastAPI + Python技术栈。

## 技术栈

- **Python**: 3.11+ | **FastAPI**: 0.115.0 | **SQLAlchemy**: 2.0.15
- **数据库**: SQLite | **认证**: JWT + OAuth2 + TOTP

## 核心约束

### 1. API响应格式规范（强制）

所有API接口必须使用统一响应格式，分页数据严禁修改字段名。

→ [详细规范](./docs/constraints/api-response-format.md)

### 2. 数据库迁移管理（强制）

所有Schema变更必须通过Alembic管理，应用启动时自动执行迁移。

→ [详细规范](./docs/constraints/database-migration.md)

### 3. 下载器客户端连接管理（强制）

必须使用`app.state.store`缓存中的客户端连接，严禁重复创建。

→ [详细规范](./docs/constraints/downloader-connection.md)

### 4. 跨环境数据库一致性（强制）

确保所有环境数据库结构一致，每次启动前检查版本。

→ [详细规范](./docs/constraints/database-consistency.md)

### 5. 代码复用优先

优先复用现有代码和类，仅在必要时创建新的。

→ [详细规范](./docs/constraints/code-reuse.md)

## 功能模块

### 通知中心

- **模型**: `app/models/notification.py` — `Notification` (表名 `notification`)
- **服务**: `app/services/notification_service.py` — `NotificationService`
- **路由**: `app/api/endpoints/notifications.py` — 前缀 `/notifications`
- **API端点**:
  - `GET /notifications` — 分页列表（支持 `type`、`is_read` 过滤）
  - `GET /notifications/unread-count` — 未读数量
  - `PUT /notifications/{id}/read` — 标记已读
  - `PUT /notifications/read-all` — 全部已读
  - `DELETE /notifications/{id}` — 删除通知
- **通知类型枚举**: `version_update` / `system`
- **版本检查**: 启动时通过 `NotificationService.check_version_update()` 查询 GitHub Release API
- **约束**: 通知是单向信箱模式，仅系统写入，用户只读。新通知通过直接 INSERT 到 `notification` 表并设置 `is_read=False`。

## 项目结构

```
BtDeck/
├── app/
│   ├── api/          # API路由
│   ├── models/       # 数据库模型
│   ├── schemas/      # Pydantic模型
│   ├── services/     # 业务逻辑
│   └── main.py       # 应用入口
├── alembic/          # 数据库迁移
└── config/app.db     # SQLite数据库
```

## 开发命令

```bash
# 启动服务
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001

# 数据库迁移
alembic revision --autogenerate -m "描述"
alembic upgrade head

# 代码检查
mypy app/ && black app/ && flake8 app/
```

## 服务端口

- API: http://localhost:5001
- WebSocket: ws://localhost:5002
- API文档: http://localhost:5001/docs
