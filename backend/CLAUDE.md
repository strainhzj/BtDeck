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

所有 Schema 变更必须通过 Alembic 管理，应用启动时自动执行迁移。
**四轨治理后（v1.0.5-db-governance），Alembic 是唯一的 schema 来源**，已删除 create_all / schema 快照 / 原生 SQL 建表。

**当前迁移链**（2026-06-21）：
```
e2a02abcf912 (base, 21表) → d0e58437af70 (+tracker_reannounce_config)
  → a0ada9774936 (+notification) → 95ef8bd8b47a (+search_templates, head)
```
- 24 张业务表（+ alembic_version），单 head，无分叉
- 历史幽灵版本 `9aea25308aff` 由 `KNOWN_GHOST_VERSIONS` 自动救援
- 迁移前自动备份（`config/app.db.pre-migration-*`，保留 3 份）

**表/字段变更操作**：
```bash
# 1. 改 ORM 模型（app/models/*.py）
# 2. 生成迁移
DATABASE_PATH=<临时库> alembic revision --autogenerate -m "描述"
# 3. 补 docstring 可回滚性标注（【可回滚】/【受限回滚】/【不可回滚】）
# 4. 审查迁移文件（upgrade + downgrade 对称）
# 5. 测试
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
# 6. 提交（模型 + 迁移文件一起）
```

→ [详细规范](./docs/constraints/database-migration.md)
→ [回滚操作指南](./docs/operations/rollback-guide.md)

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
# 启动服务（启动时自动 migrate_database + init_db）
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001

# 数据库迁移（四轨治理后统一流程）
DATABASE_PATH=<临时库路径> alembic revision --autogenerate -m "描述"  # 生成迁移
alembic upgrade head          # 应用迁移
alembic current               # 查看当前版本
alembic heads                 # 确认单 head（应只有 1 个）
alembic history               # 查看迁移链

# 代码检查
mypy app/ && black app/ && flake8 app/
python scripts/lint_btdeck.py  # 含迁移可回滚性标注检查（BTD401）
```

## 服务端口

- API: http://localhost:5001
- WebSocket: ws://localhost:5002
- API文档: http://localhost:5001/docs
