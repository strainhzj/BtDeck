# backend/data-models — ORM + 仓储 + Schemas + 默认数据 + 枚举

> 数据层统一索引：SQLAlchemy ORM 模型、Repository（数据访问层）、Pydantic schemas、默认数据种子、枚举。本分支目录分散在 `app/` 多个子目录，统一在此索引。

## models/ — ORM 模型（16 个根 .py + response/ 子目录 2 个 = 18 个）

| 文件 | 行数 | 顶层 class | 表名 / 职责 |
|------|------|-----------|-------------|
| `__init__.py` | 77 | 0 | **有实质内容**：集中导出所有模型 + 常量（见下方说明） |
| `downloader_capabilities.py` | 225 | 1 | `downloader_capabilities`：下载器能力配置 |
| `downloader_capabilities_vo.py` | 98 | 1 | 下载器能力响应 VO（Pydantic） |
| `downloader_path_maintenance.py` | 167 | 1 | `downloader_path_maintenance`：默认/在用路径 |
| `downloader_settings.py` | 156 | 2 | `downloader_settings` + `SpeedUnitEnum` |
| `enums.py` | 125 | 2 | `SpeedUnitEnum`、`ScheduleDayOfWeekEnum`（⚠ 与 downloader_settings.py 重复定义） |
| `notification.py` | 98 | 1 | `notification`：系统单向通知信箱 |
| `orphan_file.py` | 392 | 4 | `orphan_scan_result` / `orphan_file` / `orphan_current_candidate` / `orphan_operation_lease` |
| `search_template.py` | 97 | 1 | `search_templates`：搜索模板 |
| `seed_transfer_audit_log.py` | 229 | 1 | `seed_transfer_audit_log`：种子转移审计日志 |
| `setting_templates.py` | 291 | 2 | `setting_templates` + `DownloaderTypeEnum` |
| `setting_templates_vo.py` | 91 | 1 | 配置模板响应 VO |
| `speed_schedule_rules.py` | 233 | 1 | `speed_schedule_rules`：分时段限速规则 |
| `torrent_deletion_audit_log.py` | 323 | 1 | `torrent_deletion_audit_log`：种子删除审计日志 |
| `torrent_file_backup.py` | 168 | 1 | `torrent_file_backup`：种子文件本地存储记录 |
| `torrent_tags.py` | 217 | 2 | `torrent_tags` + `torrent_tag_relations` |
| `response/__init__.py` | 1 | 0 | 仅 docstring（跳过） |
| `response/dashboard.py` | 67 | 7 | 7 个看板 Pydantic 模型（`DownloaderStats`/`TorrentStats`/`TaskStats`/`DashboardData` 等） |

### models/__init__.py 实质导出

枚举：`DownloaderTypeEnum`、`SpeedUnitEnum`、`ScheduleDayOfWeekEnum`
模型：`DownloaderSetting`、`SettingTemplate`、`SpeedScheduleRule`、`TorrentTag`、`TorrentTagRelation`、`TorrentDeletionAuditLog`、`TorrentFileBackup`、`DownloaderPathMaintenance`、`SeedTransferAuditLog`
常量：`OPERATOR_SYSTEM_SCHEDULER`、`OPERATOR_RECYCLE_BIN_CLEANER`、`DELETION_STATUS_*`(3)、`CALLER_SOURCE_*`(3)、`DOWNLOADER_TYPE_*`(2)、`TRANSFER_STATUS_*`(2) 等

## repositories/ — 数据访问层（3 个 Repository + `__init__.py` = 4 个 .py）

| 文件 | 行数 | 顶层 class | 职责 |
|------|------|-----------|------|
| `__init__.py` | 13 | 0 | 包 docstring |
| `async_torrent_tag_repository.py` | 355 | 1 (`AsyncTorrentTagRepository`) | 标签仓储异步版（供定时任务/异步 Service） |
| `torrent_file_backup_repository.py` | 412 | 1 (`TorrentFileBackupRepository`) | 种子文件备份 CRUD |
| `torrent_tag_repository.py` | 401 | 1 (`TorrentTagRepository`) | 标签仓储同步版 |

## schemas/ — Pydantic schemas（8 个文件，无 `__init__.py`）

| 文件 | 行数 | 顶层 class | 职责 |
|------|------|-----------|------|
| `auth.py` | 71 | 11 | 认证 schema（User/Token/2FA/LoginResponse/Config） |
| `downloader_settings.py` | 263 | 17 | 下载器设置/模板/限速规则 CRUD schema（Base/Create/Update/InDB/Response 全套） |
| `duplicate_detection.py` | 77 | 6 | 重复检测请求/响应（含 `TaskStatus` 枚举） |
| `seed_transfer.py` | 240 | 4 | 种子转移请求/响应（单条 + 批量） |
| `tag_schemas.py` | 206 | 14 | 标签管理全套 schema |
| `token.py` | 33 | 2 | `Token`、`TokenPayload`（JWT 最小模型） |
| `torrent_backup.py` | 177 | 6 | 种子文件备份 API schema |
| `torrent_location.py` | 46 | 2 | 修改种子保存路径请求/响应 |

## data/ — 默认数据种子（4 个文件）

| 文件 | 行数 | 顶层 def | 职责 |
|------|------|---------|------|
| `default_scheduled_tasks.py` | 337 | 3 | 11 个系统默认定时任务种子（见下方清单） |
| `default_search_templates.py` | 176 | 1 | 4 个预设搜索查询模板（v1.0.5）幂等初始化 |
| `default_templates.py` | 367 | 5 | 5 个下载器配置模板（qb 标准/高性能、trans 标准/高性能、夜间不限速） |
| `default_tracker_keywords.py` | 366 | 2 | Tracker 关键词池默认数据（成功/失败/忽略池） |

`default_scheduled_tasks.py` 提供的 11 个 task_code（行号实测）：
`cached_downloader_sync`(L40)、`TRACKER_MESSAGE_LOGGER`(L57)、`downloader_path_scan`(L74)、`Tag_Data_Sync`(L91)、`TORRENT_TRACKER_STATUS_JUDGE`(L108)、`torrent_info_sync_ac608e4d`(L125)、`tracker_sync_598b784c`(L142)、`tracker_reannounce`(L159)、`orphan_scan_cleanup`(L176)、`orphan_quarantine_purge`(L193)、`orphan_notification_retry`(L210)

## enums/

| 文件 | 行数 | 顶层符号 | 职责 |
|------|------|---------|------|
| `__init__.py` | 9 | 0 | 包 docstring |
| `tracker_status.py` | 117 | 3 | `QBittorrentTrackerStatus`、`TransmissionTrackerStatus` + `get_tracker_status_text()` 中文映射 |

---

## 关键观察

- **ORM 模型分布**：核心业务表（TorrentInfo / TrackerInfo 等）在 [domain/torrents/models.py](../domain/README.md)；下载器/能力/路径/设置/标签/审计/孤儿等表集中在 `app/models/`
- **Repository 模式仅局部应用**：只有 `torrent_tag` 和 `torrent_file_backup` 走了 Repository，其余 ORM 直接在 services 层操作
- **枚举重复定义**：`SpeedUnitEnum` 同时存在于 `models/downloader_settings.py` 和 `models/enums.py`
- **Pydantic 模型分散**：`app/schemas/`（8 个）+ `app/api/schemas/`（3 个）+ `app/api/models/`（1 个）+ 各 domain 目录的 `*VO.py`，无统一入口

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐
