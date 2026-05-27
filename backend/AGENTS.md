# AGENTS.md - BTDeck 后端项目

> **项目**: BTDeck 后端服务
> **技术栈**: Python 3.11+ | FastAPI 0.115.0 | SQLAlchemy 2.0.15 | SQLite
> **更新**: 2026-05-27

---

## 项目定位

BTDeck 后端提供统一的 BitTorrent 客户端管理 API，支持 qBittorrent、Transmission 多下载器接入。

---

## 启动工作流

开始任何工作前，按顺序执行：

```
1. 阅读 AGENTS.md（本文件）
2. 阅读 CLAUDE.md（后端技术约束）
3. 阅读 docs/constraints/（详细规范）
4. 阅读 feature_list.json（功能状态）
5. 阅读 PROGRESS.md（会话上下文）
6. 运行 ./scripts/init.sh（验证环境）
```

---

## 工作规则

### 1. API 响应格式统一（强制）

所有 API 必须使用统一响应格式，分页字段名严格固定为 `list`/`total`/`pageSize`。

详见 `docs/constraints/api-response-format.md`

### 2. 数据库迁移管理（强制）

所有 Schema 变更必须通过 Alembic 管理，应用启动时自动执行迁移。

详见 `docs/constraints/database-migration.md`

### 3. 下载器连接管理（强制）

必须使用 `app.state.store` 缓存中的客户端连接，严禁重复创建。

详见 `docs/constraints/downloader-connection.md`

### 4. 代码复用优先

优先复用现有代码和类，仅在必要时创建新的。检查相似度 >50% 可扩展现有代码。

详见 `docs/constraints/code-reuse.md`

### 5. 跨环境数据库一致性（强制）

确保所有环境数据库结构一致，每次启动前检查版本。

详见 `docs/constraints/database-consistency.md`

### 6. 验证优先

完成定义：
- [ ] 实现完成
- [ ] 代码检查通过（mypy + black + flake8）
- [ ] 相关测试通过
- [ ] API 文档更新（如有新端点）
- [ ] PROGRESS.md 更新
- [ ] feature_list.json 更新

---

## 功能模块索引

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

---

## 项目结构

```
BtDeck/
├── app/
│   ├── api/endpoints/   # API路由（30+端点文件）
│   ├── models/          # 数据库模型（10+模型）
│   ├── schemas/         # Pydantic模型
│   ├── services/        # 业务逻辑（25+服务）
│   ├── downloader/      # 下载器适配器
│   │   └── adapters/    # qBittorrent/Transmission适配
│   ├── startup/         # 启动生命周期
│   ├── utils/           # 工具函数
│   └── main.py          # 应用入口
├── alembic/             # 数据库迁移
├── config/              # 配置（app.db SQLite）
├── tests/               # 测试套件
├── scripts/             # 工具脚本
├── pytest.ini           # 测试配置
└── requirements.txt     # Python依赖
```

---

## 验证命令

```bash
# 环境验证
./scripts/init.sh

# 代码质量（全量）
mypy app/ && black --check app/ && flake8 app/

# 运行测试
pytest

# 启动服务
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 5001
```

---

## 必需文件

| 文件 | 用途 | 更新频率 |
|------|------|----------|
| `AGENTS.md` | 后端工作流（本文件） | 稳定 |
| `CLAUDE.md` | 后端技术约束 | 稳定 |
| `feature_list.json` | 功能状态追踪 | 每次会话 |
| `PROGRESS.md` | 会话进度日志 | 每次会话 |
| `session-handoff.md` | 会话交接模板 | 每次会话结束 |
| `scripts/init.sh` | 环境验证脚本 | 稳定 |

### 约束文档（`docs/constraints/`）

| 文件 | 约束内容 | 适用场景 |
|------|----------|----------|
| `api-response-format.md` | API 统一响应格式、分页字段名强制规范 | 编写/修改任何 API 接口时 |
| `code-reuse.md` | 代码复用优先原则、扩展判断标准 | 创建新函数/类前 |
| `database-migration.md` | Alembic 迁移管理、Schema 变更流程 | 修改数据库模型时 |
| `database-consistency.md` | 跨环境数据库一致性保障、版本检查 | 部署/切换环境时 |
| `downloader-connection.md` | 下载器客户端缓存使用规范、禁止新建连接 | 涉及下载器操作的接口 |

---

## 会话结束清单

```
1. 更新 PROGRESS.md（记录完成的工作和决策）
2. 更新 feature_list.json（更新功能状态）
3. 填写 session-handoff.md（交接信息）
4. 验证仓库状态（./scripts/init.sh 通过）
5. Git 提交（仅在用户要求时，在 BtDeck/ 目录内执行）
```

---

**最后更新**: 2026-05-27
