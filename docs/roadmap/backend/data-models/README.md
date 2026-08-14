# backend/data-models — ORM + 仓储 + Schemas + 默认数据 + 枚举

> 数据层统一索引：SQLAlchemy ORM 模型、Repository（数据访问层）、Pydantic schemas、默认数据种子、枚举。本分支目录分散在 `app/` 多个子目录，统一在此索引。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/data-models/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

### models/ — ORM 模型（17 个根 .py + response/ 子目录 2 个 = 19 个）

| 关键词 | 文件 | 表名 / 一句话职责 |
|--------|------|-------------------|
| 模型导出 models-init | `__init__.py` | **有实质内容**：集中导出所有模型 + 常量（见下方说明） |
| 下载器能力 model capability | `downloader_capabilities.py` | `downloader_capabilities`：下载器能力配置 |
| 能力 VO capability-vo | `downloader_capabilities_vo.py` | 下载器能力响应 VO（Pydantic） |
| 路径维护 model path-maintenance | `downloader_path_maintenance.py` | `downloader_path_maintenance`：默认/在用路径 |
| 下载器设置 model downloader-setting | `downloader_settings.py` | `downloader_settings` + `SpeedUnitEnum` |
| 枚举 model enums | `enums.py` | `SpeedUnitEnum`、`ScheduleDayOfWeekEnum`（⚠ 与 downloader_settings.py 重复定义） |
| 通知模型 model notification | `notification.py` | `notification`：系统单向通知信箱 |
| 孤儿模型 model orphan | `orphan_file.py` | `orphan_scan_result`（后台状态、增量统计、超量提醒与兼容复核字段）/ `orphan_file`（稳定明细）/ `orphan_current_candidate`（`current_detail_id` 指针）/ `orphan_operation_lease` |
| 孤儿清理任务 model orphan-purge | `orphan_purge_job.py` | `orphan_purge_job`：隔离区彻底删除持久化任务状态与通知送达标记 |
| 搜索模板 model search-template | `search_template.py` | `search_templates`：搜索模板 |
| 种子转移审计 model seed-transfer-audit | `seed_transfer_audit_log.py` | `seed_transfer_audit_log`：种子转移审计日志 |
| 配置模板 model template | `setting_templates.py` | `setting_templates` + `DownloaderTypeEnum` |
| 模板 VO template-vo | `setting_templates_vo.py` | 配置模板响应 VO |
| 限速规则 model speed-schedule | `speed_schedule_rules.py` | `speed_schedule_rules`：分时段限速规则 |
| 删除审计 model deletion-audit | `torrent_deletion_audit_log.py` | `torrent_deletion_audit_log`：种子删除审计日志 |
| 备份记录 model torrent-backup | `torrent_file_backup.py` | `torrent_file_backup`：种子文件本地存储记录 |
| 标签模型 model torrent-tag | `torrent_tags.py` | `torrent_tags` + `torrent_tag_relations` |
| 看板模型 model dashboard | `response/dashboard.py` | 7 个看板 Pydantic 模型（`DownloaderStats`/`TorrentStats`/`TaskStats`/`DashboardData` 等） |

### models/__init__.py 实质导出

枚举：`DownloaderTypeEnum`、`SpeedUnitEnum`、`ScheduleDayOfWeekEnum`
模型：`DownloaderSetting`、`SettingTemplate`、`SpeedScheduleRule`、`TorrentTag`、`TorrentTagRelation`、`TorrentDeletionAuditLog`、`TorrentFileBackup`、`DownloaderPathMaintenance`、`SeedTransferAuditLog`
常量：`OPERATOR_SYSTEM_SCHEDULER`、`OPERATOR_RECYCLE_BIN_CLEANER`、`DELETION_STATUS_*`(3)、`CALLER_SOURCE_*`(3)、`DOWNLOADER_TYPE_*`(2)、`TRANSFER_STATUS_*`(2) 等

### repositories/ — 数据访问层（3 个 Repository + `__init__.py` = 4 个 .py）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 标签仓储异步 async-tag-repo | `async_torrent_tag_repository.py` | `AsyncTorrentTagRepository`：标签仓储异步版（供定时任务/异步 Service） |
| 备份仓储 backup-repo | `torrent_file_backup_repository.py` | `TorrentFileBackupRepository`：种子文件备份 CRUD |
| 标签仓储同步 sync-tag-repo | `torrent_tag_repository.py` | `TorrentTagRepository`：标签仓储同步版 |

### schemas/ — Pydantic schemas（8 个文件，无 `__init__.py`）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 认证 schema auth | `auth.py` | 认证 schema（User/Token/2FA/LoginResponse/Config） |
| 下载器设置 schema downloader-setting | `downloader_settings.py` | 下载器设置/模板/限速规则 CRUD schema（Base/Create/Update/InDB/Response 全套） |
| 重复检测 schema duplicate | `duplicate_detection.py` | 重复检测请求/响应（含 `TaskStatus` 枚举） |
| 种子转移 schema seed-transfer | `seed_transfer.py` | 种子转移请求/响应（单条 + 批量） |
| 标签 schema tag | `tag_schemas.py` | 标签管理全套 schema |
| JWT schema token | `token.py` | `Token`、`TokenPayload`（JWT 最小模型） |
| 备份 schema torrent-backup | `torrent_backup.py` | 种子文件备份 API schema |
| 种子路径 schema torrent-location | `torrent_location.py` | 修改种子保存路径请求/响应 |

### data/ — 默认数据种子（4 个文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 默认任务种子 default-tasks | `default_scheduled_tasks.py` | 11 个系统默认定时任务种子；Tracker 状态同步为 `10,40 * * * *`，独立状态判断为 `20,50 * * * *`（见下方清单） |
| 默认搜索模板 default-search | `default_search_templates.py` | 4 个预设搜索查询模板（v1.0.5）幂等初始化 |
| 默认配置模板 default-templates | `default_templates.py` | 5 个下载器配置模板（qb 标准/高性能、trans 标准/高性能、夜间不限速） |
| 默认关键词 default-keywords | `default_tracker_keywords.py` | Tracker 关键词池默认数据（成功/失败/忽略池） |

`default_scheduled_tasks.py` 提供的 11 个 task_code（行号实测）：
`cached_downloader_sync`(L41)、`TRACKER_MESSAGE_LOGGER`(L58)、`downloader_path_scan`(L75)、`Tag_Data_Sync`(L92)、`TORRENT_TRACKER_STATUS_JUDGE`(L109)、`torrent_info_sync_ac608e4d`(L126)、`tracker_sync_598b784c`(L143)、`tracker_reannounce`(L160)、`orphan_scan_cleanup`(L177)、`orphan_quarantine_purge`(L194)、`orphan_notification_retry`(L211)

### enums/

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Tracker 状态枚举 tracker-status | `tracker_status.py` | `QBittorrentTrackerStatus`、`TransmissionTrackerStatus` + `get_tracker_status_text()` 中文映射 |

---

## 关键观察

- **ORM 模型分布**：核心业务表（TorrentInfo / TrackerInfo 等）在 [domain/torrents/models.py](../domain/README.md)；下载器/能力/路径/设置/标签/审计/孤儿等表集中在 `app/models/`
- **Repository 模式仅局部应用**：只有 `torrent_tag` 和 `torrent_file_backup` 走了 Repository，其余 ORM 直接在 services 层操作
- **枚举重复定义**：`SpeedUnitEnum` 同时存在于 `models/downloader_settings.py` 和 `models/enums.py`
- **Pydantic 模型分散**：`app/schemas/`（8 个）+ `app/api/schemas/`（3 个）+ `app/api/models/`（1 个）+ 各 domain 目录的 `*VO.py`，无统一入口

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐
