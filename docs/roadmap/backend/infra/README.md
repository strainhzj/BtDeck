# backend/infra — 工具 / 启动 / 迁移

> 横切基础设施：审计日志、加密、日志脱敏、FastAPI 生命周期、应用层迁移、Alembic schema 迁移。

## utils/（3 个文件，868 行）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `audit_logger.py` | 544 | 5 | 🔵 审计日志系统：`_AuditLoggerSingleton`(L32)、`_AuditFormatter`(L282)、`_CompressingRotator`(L304 旧日志压缩)、`get_audit_logger`(L383)、`export_audit_logs_from_db_to_file`(L393) |
| `encryption.py` | 208 | 6 | 🔵 SM4 加密：`SM4Encryption`(L14) + 模块封装 `get_sm4_encryption`(L147)、`encrypt_password`(L155)、`decrypt_password`(L169)、`encrypt_tracker_url`(L183)、`decrypt_tracker_url`(L197) |
| `log_sanitizer.py` | 116 | 5 | 日志脱敏：`sanitize_ip`(L18)、`sanitize_username`(L40)、`sanitize_log_message`(L55)、`format_connection_log`(L76)、`should_sanitize`(L100) |

> 加密集中点：`utils/encryption.py`（SM4 主实现）被 `auth/security.py`、`migrations/database_migrator.py`、`downloader/qbittorrent_settings.py` 等复用。

## startup/（2 个有效文件）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `lifecycle.py` | 353 | 6 | 🔵 FastAPI `lifespan`(L166)：管理启动/关闭流程 |
| `routers_initializer.py` | 20 | 1 | `init_routers(app)`(L6) 注册全部路由 |
| `__init__.py` | 0 | — | 空文件（跳过） |

### lifecycle.py 管理的流程

**启动阶段**（`lifespan` L166 起，行号实测）：
- L20-24：`init_config_file()`（首次启动写配置）
- L54-57：`init_db()`（建库）
- L66：`await init_database_connection()`
- L69：`await update_cron_task_status()`
- L75：`await cron_executor.start()`（启动定时调度器）
- L91-92：`asyncio.create_task(startup_event(app))` → 下载器初始化（来自 `downloader.initialization`）
- L94-99：`run_dashboard_stats_loop` + `check_version_update_task`
- L102-103：`add_version_update_notification_task`

**关闭阶段**（`yield` 之后 L111-165）：逐个 `cancel()` + `await` 四个任务、`cron_executor.stop()`、`downloader_api_runtime.shutdown()`。

## migrations/ — 应用层数据迁移（3 个文件，1271 行）

⚠ 区别于 `alembic/`（schema 版本迁移）。本目录是运行时数据/字段迁移（含 SM4 加密字段升级）。

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `database_migrator.py` | 764 | 2 | 🔵 迁移总入口：`DatabaseMigrator`(L19) + `run_database_migrations()`(L756) |
| `add_torrent_progress_migration.py` | 304 | 2 | `TorrentProgressMigration`(L13) + `run_torrent_progress_migration(db_path)`(L293)：为种子新增进度字段 |
| `keyword_pools_migration.py` | 203 | 2 | `KeywordPoolsMigration`(L13) + `run_keyword_pools_migration(db_path)`(L192)：关键词分组表迁移 |

### DatabaseMigrator 核心方法（L19，实测行号）

- 入口：`__init__`(L22)、`run_migrations`(L27)
- 迁移登记表：`_create_migration_table`(L87)、`_is_migration_completed`(L100)、`_mark_migration_completed`(L112)
- 三大类别：`_migrate_field_types`(L140)、`_migrate_delete_logic`(L181)、`_migrate_encrypted_fields`(L259)
- 表结构升级：`_migrate_bt_downloaders_table`(L319)、`_migrate_torrent_info_table`(L371)、`_migrate_tracker_info_table`(L440, 带 sm4_key 解密)
- 密码/URL 加密迁移：`_encrypt_passwords`(L516)、`_encrypt_tracker_urls`(L547)、`_get_sm4_key`(L576)
- `generate_migration_sql`(L599)

## alembic/ — Schema 版本迁移

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `env.py` | 144 | 2 | Alembic 迁移环境：`run_migrations_offline`(L97) + `run_migrations_online`(L121)，处理 PyInstaller `_MEIPASS` + 集中 import 所有 ORM 模型 |
| `versions/` | — | — | **7 个** revision 文件（见下表） |

`env.py` 顶部集中 import 所有 ORM 模型（`User`/`LoginLog`/`Config`/`BtDownloaders`/`TorrentInfo`…）以确保 autogenerate 检测全部表。

### alembic/versions/（7 个迁移文件）

| 文件名 | 内容（从命名推断） |
|--------|-------------------|
| `95ef8bd8b47a_add_search_templates_table.py` | 新增搜索模板表 |
| `a0ada9774936_add_notification_table.py` | 新增通知表 |
| `b075727f7182_orphan_lifecycle.py` | 孤儿文件生命周期 |
| `c3f1a8b7d902_add_orphan_file_tables.py` | 新增孤儿文件相关表 |
| `d0e58437af70_add_tracker_reannounce_config_table.py` | 新增 Tracker 重新宣告配置表 |
| `e2a02abcf912_fix_downloader_type_to_integer.py` | 修正 downloader.type 为整型 |
| `e6d8a20c41f3_orphan_operation_journal.py` | 孤儿文件操作日志表 |

---

## 关键观察

- **迁移双轨**：`app/migrations/`（应用层数据/字段迁移，运行时执行）与 `backend/alembic/`（schema 版本管理）并存 → 详见 [../../backend/docs/architecture-deep-dive.md](../../../backend/docs/architecture-deep-dive.md) "二、数据库迁移双轨"
- **生命周期串联**：`startup/lifecycle.py` 是启动总控，串联 DB 初始化、调度器、下载器初始化、看板统计等
- **加密集中点**：`utils/encryption.py` 是 SM4 主实现，被多个领域复用

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`utils/audit_logger.py` 544 行、`migrations/database_migrator.py` 764 行）
