# backend/core — 基础设施层

> 全局基础设施：配置、路径映射、数据库结果封装、文件操作、Tracker 判断等。⚠ 本目录混有真正的核心基础设施与若干**0 引用孤儿文件**，需区分对待。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/core/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 后台任务 background-task | `background_task_manager.py` | 后台任务管理器（内存态，单机部署）；`create_task_if_idle()` L109 原子占用下载器 pending/running 任务，`start_task_runner()` L140 保留 asyncio runner 强引用并消费异常，`execute_task()` L215 把结构化 failed/cancelled 结果映射为真实终态 |
| 全局配置 config | `config.py` | 🔵 全局配置 `Settings`（BaseSettings），含 frozen/docker/secret-key 判定 |
| DB 结果封装 database-result | `database_result.py` | 🔵 统一 DB 操作返回格式 `DatabaseResult[T]`（泛型） |
| 迁移备份 db-backup | `db_backup.py` | alembic upgrade 前对 `app.db` 物理备份（Level-2 回滚兜底）；v1.0.6.27 起新增 `list_pre_migration_backups` 列举历史备份，供 ratio 迁移诊断/回滚使用 |
| 下载器桩 downloader-stub | `downloader.py` | ⚠️ **孤儿**：遗留下载器依赖桩（`from app.downloader import models` 已失效） |
| 文件操作 file-operations | `file_operations.py` | 文件操作服务（`.waiting-delete` 标记文件创建/删除/批量+回滚，回收站用） |
| 文件名清理 filename | `filename_utils.py` | 文件名清理（非法字符/长度，给种子备份文件名） |
| 灾备建库 init-schema | `init_schema_from_production.py` | ⚠️ **孤儿/已下线**：从生产 DB schema 反向建库的灾备脚本，main.py 不再调用 |
| JSON 解析 json-parser | `json_parser.py` | 异常安全 JSON 解析（吞 JSONDecodeError） |
| DB 迁移入口 migration | `migration.py` | 🔵 数据库迁移统一入口 `migrate_database()`（L145，空库/增量/幽灵救援、升级后 head 校验与显式成功状态）；应用启动遇失败一律 fail-fast |
| 路径映射 path-mapping | `path_mapping.py` | 🔵 下载器内/外路径双向映射（Docker/NAS/权限隔离） |
| ratio 诊断 ratio-diagnostics | `ratio_data_diagnostics.py` ✨v1.0.6.27 | 🔵 ratio 列迁移只读诊断：统计 `torrent_info.ratio`/`ratio_limit` 的 null/zero/positive/invalid 分布、列举 pre-migration 备份、生成回滚所需 checksum；被 `scripts/ratio_migration_report.py` 消费 |
| Reannounce 配置 reannounce-config | `reannounce_config_operations.py` | `tracker_reannounce_config` 表 CRUD + 域名匹配 |
| 解密孤儿 security | `security.py` | ⚠️ **孤儿**：Tracker 信息安全解密（密钥管理+安全日志），无任何引用 |
| 启动约束 startup-guard | `startup_guard.py` | 🔵 SQLite 单 Worker 启动约束（fail-fast）：`detect_backend`/`validate_worker_count`/`validate_scheduler_scope` 纯函数校验 WORKERS=1 与调度器进程范围，被 main.py、lifecycle.py、health.py、orphan_purge_job_service.py 引用 |
| 种子文件备份 torrent-file-backup | `torrent_file_backup.py` | 种子文件备份服务（从下载器备份目录拷贝到项目备份目录） |
| ratio 工具孤儿 ratio-tools | `torrent_operations.py` | ⚠️ **孤儿（内容已重写但未接线）**：v1.0.6.27 起内容已重写为 ratio/ratio_limit 工具，但**生产路径未 import**（实际生效的是 `app/services/torrent_ratio_values.py`） |
| 状态映射 status-mapper | `torrent_status_mapper.py` ✨2026-08-16 | 统一 qb/transmission 种子状态映射；qB 映射表补齐新种子初始态（metaDL/forcedMetaDL/allocating→downloading、forcedDL→downloading、forcedUP→seeding、missingFiles→error、checkingResumeData→checkingDL，moving 有意不映射），`resolve_transmission_status` L112 判定错误状态，`extract_transmission_error_reason` L147 安全提取 errorString（warning/恢复返回空） |
| Tracker 判断 tracker-judgment | `tracker_judgment.py` | Tracker 状态判断引擎（关键词池，失败优先策略） |
| Tracker 映射 tracker-mapper | `tracker_mapper.py` | qb/transmission tracker 状态统一映射 + 关键词池判断集成；`resolve_transmission_tracker_status_code()` L120 将布尔统计/联系状态归一为项目 0–4 状态码 |
| Tracker 联合判定 tracker-status-policy | `tracker_status_policy.py` ✨2026-08-12 | Tracker 行级同步与种子级判断共享纯函数：L43 以非空消息优先、Working 空消息兜底构造证据，L69 聚合为明确正常/全部失败/未知保留；✨2026-08-20 展示对齐判定：`tracker_message_failed()` L78 单消息精确命中失败池、`tracker_display_failed()` L90 按判定任务中性码语义（qb==1/tr∈{0,1} 残留消息不采信）裁决展示覆写，`FAILED_DISPLAY_TEXT` L13 与两套枚举 code=3 文本一致 |
| Tracker 关键词池加载 tracker-keyword-map | `tracker_keyword_map.py` ✨2026-08-20 | `load_active_keyword_map()` L19 加载 failed/success/ignored 三池为 `{keyword: type}`（first-wins，异常返回空池降级）；种子级判定任务与展示覆写共用同一映射保证口径一致 |
| Tracker 操作孤儿 tracker-operations | `tracker_operations.py` | ⚠️ **孤儿**：标准化 tracker DB 操作（DatabaseResult 重构版），未启用 |

> 🔵 = 基础设施型（高频引用）；⚠️ = 孤儿/低使用。各文件的引用统计详见下方"孤儿/低使用"与"基础设施型"两节。

---

## ⚠ 孤儿/低使用文件清单（引用数 ≤ 1）

### 0 引用（确认孤儿，建议清理或归档）

| 文件 | 行数 | 问题 |
|------|------|------|
| `core/security.py` | 258 | Tracker 解密模块（`TrackerDecryptionKeyManager` 等）完全未接入，与 `app.auth.security`、`app.utils.encryption` 功能重叠 |
| `core/downloader.py` | 29 | 自身 `from app.downloader import models` 指向不存在的包，已失效 |
| `core/torrent_operations.py` | 250 | v1.0.6.27 重写为 ratio 工具但**仍未接线**（生产用 `app/services/torrent_ratio_values.py`）；存在"两份 ratio 规范化逻辑"风险，建议合并或删除 |
| `core/tracker_operations.py` | 292 | DatabaseResult 重构产物，被 `services/orphan_*`、`services/reannounce_service` 等取代 |
| `core/init_schema_from_production.py` | 146 | 文件头自述"已下线"，main.py 不再调用 |

### 1~2 引用（边缘模块）

| 文件 | 引用方 |
|------|--------|
| `core/db_backup.py` | `core/migration.py` + `core/ratio_data_diagnostics.py`（v1.0.6.27 起从 1 引用升为 2） |
| `core/ratio_data_diagnostics.py` | `scripts/ratio_migration_report.py` + `tests/core/test_ratio_data_diagnostics.py` |
| `core/background_task_manager.py` | 仅 `api/endpoints/torrent_sync.py:23`；手动下载器同步的原子防重、并发限制、runner 生命周期与查询终态均由该单例承载 |

> 详见 [../../perspectives/risks.md](../../perspectives/risks.md) "孤儿文件" 章节。

---

## 基础设施型文件（高频引用，业务核心）

| 文件 | 引用数 | 角色 |
|------|--------|------|
| `config.py` | 40 | 全局配置入口（`settings` / `is_frozen` / `ROOT_PATH`） |
| `database_result.py` | 11 | `DatabaseResult[T]` 通用查询封装 |
| `path_mapping.py` | 10 | `PathMappingService` / `PathMappingConverter` / `UnifiedPathMappingService`（L39/L446/L716） |
| `torrent_status_mapper.py` | 6 | 状态映射 |
| `file_operations.py` | 4 | 回收站文件标记 |
| `json_parser.py` | 4 | JSON 解析 |
| `migration.py` | 3 | DB 迁移入口：迁移前验证备份、保留未来版本回滚路径、升级后校验 head 并向生命周期返回成功状态 |
| `ratio_data_diagnostics.py` | 2 | ratio 迁移只读诊断 + 回滚 checksum（v1.0.6.27） |
| `db_backup.py` | 2 | alembic upgrade 前物理备份 + 历史备份列举（v1.0.6.27 升级） |

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`path_mapping.py` 932 行 / `file_operations.py` 1474 行 / `config.py` 423 行）
