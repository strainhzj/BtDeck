# backend/core — 基础设施层

> 全局基础设施：配置、路径映射、数据库结果封装、文件操作、Tracker 判断等。⚠ 本目录混有真正的核心基础设施与若干**0 引用孤儿文件**，需区分对待。

## 文件清单（20 个）

| 文件 | 行数 | 顶层符号 | 引用数 | 一句话职责 |
|------|------|---------|--------|-----------|
| `__init__.py` | 0 | — | — | 空包标识（跳过） |
| `background_task_manager.py` | 202 | 3 | 1 | 后台任务管理器（内存态，单机部署） |
| `config.py` | 236 | 4 | **28** | 🔵 全局配置 `Settings`（BaseSettings），含 frozen/docker/secret-key 判定 |
| `database_result.py` | 148 | 2 | 11 | 🔵 统一 DB 操作返回格式 `DatabaseResult[T]`（泛型） |
| `db_backup.py` | 96 | 2 | 1 | alembic upgrade 前对 `app.db` 物理备份（Level-2 回滚兜底） |
| `downloader.py` | 29 | 1 | **0** | ⚠️ **孤儿**：遗留下载器依赖桩（`from app.downloader import models` 已失效） |
| `file_operations.py` | 1474 | 1 | 4 | 文件操作服务（`.waiting-delete` 标记文件创建/删除/批量+回滚，回收站用） |
| `filename_utils.py` | 140 | 1 | 3 | 文件名清理（非法字符/长度，给种子备份文件名） |
| `init_schema_from_production.py` | 146 | 3 | **0** | ⚠️ **孤儿/已下线**：从生产 DB schema 反向建库的灾备脚本，main.py 不再调用 |
| `json_parser.py` | 127 | 3 | 4 | 异常安全 JSON 解析（吞 JSONDecodeError） |
| `migration.py` | 194 | 4 | 3 | 🔵 数据库迁移统一入口 `migrate_database()`（空库建表/增量升级/幽灵版本救援） |
| `path_mapping.py` | 898 | 3 | 10 | 🔵 下载器内/外路径双向映射（Docker/NAS/权限隔离） |
| `reannounce_config_operations.py` | 348 | 13 | 2 | `tracker_reannounce_config` 表 CRUD + 域名匹配 |
| `security.py` | 263 | 7 | **0** | ⚠️ **孤儿**：Tracker 信息安全解密（密钥管理+安全日志），无任何引用 |
| `torrent_file_backup.py` | 503 | 1 | 3 | 种子文件备份服务（从下载器备份目录拷贝到项目备份目录） |
| `torrent_operations.py` | 235 | 8 | **0** | ⚠️ **孤儿**：标准化 torrent DB 操作（DatabaseResult 重构版），未启用 |
| `torrent_status_mapper.py` | 113 | 1 | 6 | 统一 qb/transmission 种子状态映射 |
| `tracker_judgment.py` | 415 | 2 | 2 | Tracker 状态判断引擎（关键词池，失败优先策略） |
| `tracker_mapper.py` | 301 | 7 | 2 | qb/transmission tracker 状态统一映射 + 关键词池判断集成 |
| `tracker_operations.py` | 292 | 10 | **0** | ⚠️ **孤儿**：标准化 tracker DB 操作（DatabaseResult 重构版），未启用 |

> 引用数 = `backend/app/` 范围内 `from app.core.<mod>` / `import app.core.<mod>` 的 .py 文件数（排除自身）。🔵 = 基础设施型（高频引用）；⚠️ = 孤儿/低使用。

---

## ⚠ 孤儿/低使用文件清单（引用数 ≤ 1）

### 0 引用（确认孤儿，建议清理或归档）

| 文件 | 行数 | 问题 |
|------|------|------|
| `core/security.py` | 263 | Tracker 解密模块（`TrackerDecryptionKeyManager` 等）完全未接入，与 `app.auth.security`、`app.utils.encryption` 功能重叠 |
| `core/downloader.py` | 29 | 自身 `from app.downloader import models` 指向不存在的包，已失效 |
| `core/torrent_operations.py` | 235 | DatabaseResult 重构产物，被 `torrent_metadata.py`（services 层）等取代 |
| `core/tracker_operations.py` | 292 | DatabaseResult 重构产物，被 `services/orphan_*`、`services/reannounce_service` 等取代 |
| `core/init_schema_from_production.py` | 146 | 文件头自述"已下线"，main.py 不再调用 |

### 1 引用（边缘模块）

| 文件 | 引用方 |
|------|--------|
| `core/db_backup.py` | 仅 `core/migration.py:29` |
| `core/background_task_manager.py` | 仅 `api/endpoints/torrent_sync.py:24` |

> 详见 [../../perspectives/risks.md](../../perspectives/risks.md) "孤儿文件" 章节。

---

## 基础设施型文件（高频引用，业务核心）

| 文件 | 引用数 | 角色 |
|------|--------|------|
| `config.py` | 28 | 全局配置入口（`settings` / `is_frozen` / `ROOT_PATH`） |
| `database_result.py` | 11 | `DatabaseResult[T]` 通用查询封装 |
| `path_mapping.py` | 10 | `PathMappingService` / `PathMappingConverter` / `UnifiedPathMappingService`（L39/L446/L716） |
| `torrent_status_mapper.py` | 6 | 状态映射 |
| `file_operations.py` | 4 | 回收站文件标记 |
| `json_parser.py` | 4 | JSON 解析 |
| `migration.py` | 3 | DB 迁移入口 |

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`path_mapping.py` 898 行 / `file_operations.py` 1474 行 / `config.py` 236 行）
