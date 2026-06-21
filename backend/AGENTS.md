# AGENTS.md - BtDeck 后端（端规则指针）

> **技术栈**: Python 3.11+ | FastAPI 0.115.0 | SQLAlchemy 2.0.15 | SQLite
> **更新**: 2026-06-18

本文件是后端规则指针。**全栈工作流、Git 规范、功能状态、进度日志统一在根目录**（`../AGENTS.md`、`../feature_list.json`、`../progress.md`），本文件不再重复，亦不回指根目录工作流。

---

## 后端工作流入口

后端开发时，按顺序：

```text
1. 先读 ../AGENTS.md（全栈工作流与跨端规则）
2. 读本文件（后端模块索引 + 约束入口）
3. 读 CLAUDE.md（后端技术约束）
4. 读 docs/constraints/（后端详细规范）
5. 读 ../feature_list.json（全栈功能状态，后端任务 file 前缀 app/）
6. 读 ../progress.md（全栈进度日志）
7. 运行 ../init.sh 或 ./scripts/init.sh（环境验证）
```

> 注：全栈启动工作流的权威定义在 `../AGENTS.md`，本处仅给出后端视角的入口指引。

---

## 后端工作规则（强制）

### 1. API 响应格式统一

分页字段名严格固定为 `list`/`total`/`pageSize`。详见 `docs/constraints/api-response-format.md`

### 2. 数据库迁移管理

所有 Schema 变更通过 Alembic 管理，应用启动时自动执行迁移。详见 `docs/constraints/database-migration.md`

### 3. 下载器连接管理

必须使用 `app.state.store` 缓存中的客户端连接，严禁重复创建。详见 `docs/constraints/downloader-connection.md`

### 4. 跨环境数据库一致性

确保所有环境数据库结构一致，每次启动前检查版本。详见 `docs/constraints/database-consistency.md`

### 5. 代码复用优先

优先复用现有代码和类，相似度 >50% 可扩展现有代码。详见 `docs/constraints/code-reuse.md`

---

## 后端功能模块索引

| 模块 | 模型 | 服务 | 路由端点 |
|------|------|------|----------|
| 种子管理 | - | `torrent_crud_service.py` | `torrent_crud.py` |
| 种子速度 | - | - | `torrent_speed.py` |
| 种子同步 | - | - | `torrent_sync.py` |
| 种子删除 | - | `torrent_deletion_service.py` | `torrent_deletion.py` |
| 种子备份 | `torrent_file_backup.py` | `torrent_file_backup_manager.py` | `torrent_backup.py` |
| 种子位置 | - | `torrent_location_service.py` | `torrent_location.py` |
| 种子标签 | `torrent_tags.py` | `tag_service.py`/`tag_sync_service.py` | `tag_management.py` |
| 下载器管理 | - | - | `downloader.py` |
| 下载器设置 | - | `downloader_settings_manager.py` | `downloader_settings.py` |
| 下载器能力 | `downloader_capabilities.py` | `downloader_capabilities_manager.py` | `downloader_capabilities.py` |
| 路径维护 | - | `path_maintenance_service.py` | `downloader_path_maintenance.py` |
| Tracker | - | - | `tracker.py`/`tracker_test.py`/`tracker_reannounce.py` |
| Tracker关键词 | - | - | `tracker_keywords.py`/`tracker_keywords_pools.py` |
| 回收站 | - | `recycle_bin_service.py` | `recycle_bin.py` |
| 通知中心 | `notification.py` | `notification_service.py` | `notifications.py` |
| 种子转移 | - | `seed_transfer_service.py` | `seed_transfer.py` |
| 仪表盘 | - | `dashboard_service.py` | `dashboard.py` |
| 审计日志 | `seed_transfer_audit_log.py`/`torrent_deletion_audit_log.py` | `audit_service.py` | `audit_logs.py` |
| 设置模板 | `setting_templates.py` | `template_service.py` | `setting_templates.py` |
| 速度调度 | `speed_schedule_rules.py` | `speed_schedule_service.py` | - |
| 定时任务 | - | - | `cron_tasks.py` |
| 高级搜索 | - | - | `advanced_search.py` |
| **查询模板 (v1.0.5)** | `query_template.py` (待建) | `query_template_service.py` (待建) | `query_templates.py` (待建) |

> 跨端模块（前后端协同）的总览见 `../AGENTS.md` 功能模块索引。

---

## 后端项目结构

```text
backend/
├── app/
│   ├── api/endpoints/   # API路由（30+端点文件）
│   ├── api/api.py       # 集中式路由注册（include_router）
│   ├── models/          # 数据库模型
│   ├── auth/models.py   # User 模型（注意：不在 models/ 目录）
│   ├── schemas/         # Pydantic模型
│   ├── services/        # 业务逻辑（25+服务）
│   ├── data/            # 初始数据（default_xxx.py，由 init_db 调用）
│   ├── downloader/      # 下载器适配器
│   ├── startup/         # 启动生命周期
│   ├── database.py      # init_db() 统一初始化入口
│   └── main.py          # 应用入口
├── alembic/             # 数据库迁移
├── config/              # 配置（app.db SQLite）
├── tests/               # 测试套件
├── scripts/init.sh      # 端环境验证（支持 --ci）
└── requirements.txt
```

---

## 后端验证命令

```bash
# 端环境验证（默认：安装依赖 + 验证）
./scripts/init.sh

# 端环境验证（轻量，不安装依赖，被根 init.sh 调用）
./scripts/init.sh --ci

# 代码质量
mypy app/ && black --check app/ && flake8 app/

# 测试
pytest

# 启动（启动时自动 migrate_database + init_db）
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001

# 数据库迁移（四轨治理后统一流程，详见 docs/constraints/database-migration.md）
# 改模型后用临时库生成迁移，避免污染开发库 alembic_version
DATABASE_PATH=/tmp/autogen.db alembic upgrade head
DATABASE_PATH=/tmp/autogen.db alembic revision --autogenerate -m "描述"
alembic upgrade head
alembic heads  # 确认单 head
```

---

## 后端约束文档（`docs/constraints/`）

| 文件 | 适用场景 |
|------|----------|
| `api-response-format.md` | 编写/修改任何 API 接口时 |
| `code-reuse.md` | 创建新函数/类前 |
| `database-migration.md` | 修改数据库模型时 |
| `database-consistency.md` | 部署/切换环境时 |
| `downloader-connection.md` | 涉及下载器操作的接口 |

---

**最后更新**: 2026-06-18
