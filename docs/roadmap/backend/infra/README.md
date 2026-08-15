# backend/infra — 工具 / 启动 / 迁移

> 横切基础设施：审计日志、加密、日志脱敏、FastAPI 生命周期、应用层迁移、Alembic schema 迁移。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/infra/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

### utils/（3 个文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 审计日志 audit-logger | `audit_logger.py` | 🔵 审计日志系统：`_AuditLoggerSingleton`(L32)、`_AuditFormatter`(L282)、`_CompressingRotator`(L304 旧日志压缩)、`get_audit_logger`(L383)、`export_audit_logs_from_db_to_file`(L393) |
| SM4 加密 encryption | `encryption.py` | 🔵 SM4 加密：`SM4Encryption`(L14) + 模块封装 `get_sm4_encryption`(L147)、`encrypt_password`(L155)、`decrypt_password`(L169)、`encrypt_tracker_url`(L183)、`decrypt_tracker_url`(L197) |
| 日志脱敏 log-sanitizer | `log_sanitizer.py` | 日志脱敏：`sanitize_ip`(L18)、`sanitize_username`(L40)、`sanitize_log_message`(L55)、`format_connection_log`(L76)、`should_sanitize`(L100) |

> 加密集中点：`utils/encryption.py`（SM4 主实现）被 `auth/security.py`、`migrations/database_migrator.py`、`downloader/qbittorrent_settings.py` 等复用。

### startup/（2 个有效文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 生命周期 lifecycle | `lifecycle.py` | 🔵 FastAPI `lifespan`(L262)：迁移未完成时在 seed/对账/调度器前 fail-fast；成功后对账孤儿隔离状态、终结残留 running 并恢复 queued 扫描/清理任务 |
| 路由注册 routers | `routers_initializer.py` | `init_routers(app)`(L6) 注册全部路由 |

### lifecycle.py 管理的流程

**启动阶段**（`lifespan` L262 起，行号实测）：
- L282-290：`init_config_file()` + `yaml.reload()`（首次启动写配置并重载）
- L302-311：`migrate_database()`（任意运行模式迁移失败或未到 head 均终止）
- L314-322：`init_db()`（初始数据）；L325：`await init_database_connection()`
- L330-345：`await reconcile_orphan_file_state()`（幂等对账历史隔离候选）
- L350-364：`recover_interrupted_orphan_scans()` 将残留 running 批次标记 failed
- L370：`await update_cron_task_status()`；L381：`await cron_executor.start()`
- L396-419：创建下载器、持久化孤儿清理和 queued 扫描恢复任务

**关闭阶段**（`yield` 之后 L457 起）：取消恢复任务，关闭孤儿扫描/清理调度器、Cron、下载器 API runtime 与观测任务。

### migrations/ — 应用层数据迁移（3 个文件）

⚠ 区别于 `alembic/`（schema 版本迁移）。本目录是运行时数据/字段迁移（含 SM4 加密字段升级）。

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 迁移总入口 migrator | `database_migrator.py` | 🔵 迁移总入口：`DatabaseMigrator`(L19) + `run_database_migrations()`(L756) |
| 进度字段迁移 progress-migration | `add_torrent_progress_migration.py` | `TorrentProgressMigration`(L13) + `run_torrent_progress_migration(db_path)`(L293)：为种子新增进度字段 |
| 关键词分组迁移 keyword-pool-migration | `keyword_pools_migration.py` | `KeywordPoolsMigration`(L13) + `run_keyword_pools_migration(db_path)`(L192)：关键词分组表迁移 |

### DatabaseMigrator 核心方法（L19，实测行号）

- 入口：`__init__`(L22)、`run_migrations`(L27)
- 迁移登记表：`_create_migration_table`(L87)、`_is_migration_completed`(L100)、`_mark_migration_completed`(L112)
- 三大类别：`_migrate_field_types`(L140)、`_migrate_delete_logic`(L181)、`_migrate_encrypted_fields`(L259)
- 表结构升级：`_migrate_bt_downloaders_table`(L319)、`_migrate_torrent_info_table`(L371)、`_migrate_tracker_info_table`(L440, 带 sm4_key 解密)
- 密码/URL 加密迁移：`_encrypt_passwords`(L516)、`_encrypt_tracker_urls`(L547)、`_get_sm4_key`(L576)
- `generate_migration_sql`(L599)

### alembic/ — Schema 版本迁移

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Alembic 环境 env | `env.py` | Alembic 迁移环境：`run_migrations_offline`(L101) + `run_migrations_online`(L125)；应用内调用保留现有日志 handler，独立 CLI 仍加载 Alembic 日志；处理 PyInstaller `_MEIPASS` + 集中 import ORM |
| Alembic revisions versions | `versions/` | **22 个** revision 文件；当前 head 为 `c8d9e0f1a2b3`（见下表） |

`env.py` 顶部集中 import 所有 ORM 模型（`User`/`LoginLog`/`Config`/`BtDownloaders`/`TorrentInfo`…）以确保 autogenerate 检测全部表。

### alembic/versions/（22 个迁移文件）

| 关键词 | 文件名 | 内容（从命名推断） |
|--------|--------|-------------------|
| ratio 迁移 ratio-migration | `6132b66d14a7_ratio_columns_to_float.py` ✨v1.0.6.25/27 | ratio/ratio_limit 列从 String 迁移到 Float（治本）；v1.0.6.27 加固为"迁移前 `db_backup` 自动备份 + 历史值清洗 + CHECK 约束" |
| ratio 约束 ratio-constraint | `8f4c2d1a9b7e_ratio_value_constraints.py` ✨v1.0.6.27 | 为 ratio/ratio_limit 加 CHECK 约束 `ck_torrent_info_ratio_finite_nonnegative`（有限且非负），拒绝脏值再次入库 |
| 同步游标 sync-checkpoint | `3a4b5c6d7e8f_add_sync_checkpoints.py` | 新增同步 checkpoint 持久化表 |
| 搜索模板表 search-templates | `95ef8bd8b47a_add_search_templates_table.py` | 新增搜索模板表 |
| 通知表 notification | `a0ada9774936_add_notification_table.py` | 新增通知表 |
| 孤儿置信度 orphan-confidence | `f2a7c91b4d6e_orphan_confidence_and_resolved.py` | 增加孤儿候选置信度、已解析状态与相关索引 |
| 孤儿忽略 orphan-ignore | `a1b2c3d4e5f6_add_orphan_ignore_and_canonical_path.py` | 增加孤儿忽略与规范路径字段 |
| 孤儿生命周期 orphan-lifecycle | `b075727f7182_orphan_lifecycle.py` | 孤儿文件生命周期 |
| 孤儿表 orphan-tables | `c3f1a8b7d902_add_orphan_file_tables.py` | 新增孤儿文件相关表 |
| 孤儿清理任务表 orphan-purge-job | `c7d8e9f0a1b2_add_orphan_purge_job.py` | 新增隔离区彻底删除持久化任务表与索引（幂等、可回滚） |
| 孤儿清理任务字段 orphan-cleanup-job | `d8e9f0a1b2c3_add_orphan_cleanup_job_fields.py` | 扩展孤儿清理任务运行字段 |
| Tracker reannounce 表 reannounce-config | `d0e58437af70_add_tracker_reannounce_config_table.py` | 新增 Tracker 重新宣告配置表 |
| downloader 类型修复 downloader-type | `e2a02abcf912_fix_downloader_type_to_integer.py` | 修正 downloader.type 为整型 |
| 孤儿操作日志 orphan-journal | `e6d8a20c41f3_orphan_operation_journal.py` | 孤儿文件操作日志表 |
| 硬链接说明 hardlink-notes | `f9a1b2c3d4e5_orphan_purge_hardlink_notes.py` | 增加隔离区硬链接跳过说明字段 |
| 清理延后计数 purge-delay | `f0e1d2c3b4a5_orphan_purge_delay_count.py` | 增加到期清理因硬链接延后的累计次数 |
| 任务结果新鲜度 task-outcome | `f5e6d7c8b9a0_add_task_outcome_freshness.py` | 增加定时任务最近结果与新鲜度字段 |
| 种子错误原因 torrent-error-reason | `de898cb28172_add_torrent_error_reason.py` ✨2026-08-12 | 为 `torrent_info` 增加可空 Text `error_reason`；历史数据保持空值，upgrade/downgrade 均带列存在守卫 |
| Tracker 判断错峰 tracker-judge-stagger | `4c1d8e7a2b90_stagger_tracker_status_judge_schedule.py` ✨2026-08-12 | 将未自定义的独立状态判断 Cron 从旧计划迁到 `20,50 * * * *`，在 Tracker 同步后 10 分钟执行；upgrade/downgrade 均只命中已知系统值 |
| 孤儿后台扫描 orphan-background-scan | `7b2c9d4e6f10_orphan_scan_background_and_current_detail.py` ✨2026-08-13 | `upgrade`(L58)/`downgrade`(L224)：新增后台扫描/提醒兼容字段与 `current_detail_id`；原生加列、恢复残留 `_alembic_tmp_*`，强制 canonical_path 索引回填；历史 >50000 批次保留提醒状态，不再作为清理锁定依据 |
| 副本预扫描结果表 orphan-hardlink-results | `c8d9e0f1a2b3_add_orphan_hardlink_copy_results.py` ✨2026-08-15 | 纯增量两表：`orphan_hardlink_copy_result`（唯一身份 + scanned_at 索引）与单行游标表；downgrade 直接删表，可回滚 |
| 备份下载器 ID 类型 torrent-backup-id-type | `b6e1c4d9a2f7_fix_torrent_backup_downloader_id_type.py` ✨2026-08-15 | `upgrade`(L50)/`downgrade`(L66)：`torrent_file_backup.downloader_id` Integer→String(36)（与 `bt_downloaders` UUID 主键对齐）；幂等类型探测 + batch 临时表恢复；downgrade 遇不可无损转整数的 UUID 文本时 raise 拒绝破坏性回滚 |

> v1.0.6.27 ratio 迁移加固的相关文档：[../../docs/constraints/database-migration.md](../../../backend/docs/constraints/database-migration.md)（含 ratio 列迁移约束条款）、[../../docs/operations/rollback-guide.md](../../../backend/docs/operations/rollback-guide.md)（Level-1/2 回滚步骤）。诊断/报告工具：[app/core/ratio_data_diagnostics.py](../../../backend/app/core/ratio_data_diagnostics.py) + [scripts/ratio_migration_report.py](../../../backend/scripts/ratio_migration_report.py)。

---

## 关键观察

- **迁移双轨**：`app/migrations/`（应用层数据/字段迁移，运行时执行）与 `backend/alembic/`（schema 版本管理）并存 → 详见 [../../backend/docs/architecture-deep-dive.md](../../../backend/docs/architecture-deep-dive.md) "二、数据库迁移双轨"
- **生命周期串联**：`startup/lifecycle.py` 是启动总控，串联 DB 初始化、调度器、下载器初始化、看板统计等
- **加密集中点**：`utils/encryption.py` 是 SM4 主实现，被多个领域复用

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`utils/audit_logger.py` 544 行、`migrations/database_migrator.py` 764 行）
