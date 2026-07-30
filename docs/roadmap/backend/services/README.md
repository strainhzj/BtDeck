# backend/services — 业务服务层

> 业务逻辑层，承接 endpoint 调用，向下依赖 core 基础设施与 ORM 模型。包含两个适配器子包（下载器适配器、标签适配器）。

## services/ 根（35 个文件）

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `__init__.py` | 3 | 0 class, 0 def | 包初始化（空 `__all__`） |
| `advanced_search.py` | 1311 | 3 class, 0 def | 高级搜索服务（ORM 查询引擎，13 字段搜索；v1.0.6.25 起支持 4 个 ratio 操作符 + 通过 `app.contracts` 做操作符契约校验；正则经 `sqlite_search_runtime` 受限执行） |
| `async_deletion_executor.py` | 154 | 1 class, 0 def | 异步批量删除执行器（超时/跳过失败/计数） |
| `audit_service.py` | 665 | 1 class, 2 def | 审计日志异步服务（记录/查询/归档，不阻塞主业务） |
| `audit_service_sync.py` | 479 | 1 class, 1 def | 审计日志同步服务 |
| `dashboard_service.py` | 178 | 1 class, 0 def | `DashboardService`：仪表盘聚合数据 |
| `deletion_task_manager.py` | 223 | 3 class, 1 def | 内存任务管理器（异步批量删除任务生命周期） |
| `downloader_api_runtime.py` | 433 | 4 class, 2 def | 下载器 RPC 调用隔离层（三 lane 线程池隔离 qB/Transmission） |
| `downloader_capabilities_manager.py` | 359 | 1 class, 0 def | 下载器能力配置 CRUD 与同步 |
| `downloader_settings_manager.py` | 369 | 1 class, 1 def | 下载器设置统一管理器（封装 qB/Transmission 设置包装类） |
| `notification_service.py` | 226 | 1 class, 0 def | 通知服务（CRUD + 版本更新检查） |
| `orphan_file_service.py` | 1339 | 1 class, 0 def | 孤儿文件管理（失败扫描回退读模型/剩余量统计/清理预览/手动自动清理/中断恢复/超期清理） |
| `orphan_lease.py` | 259 | 2 class, 8 def | 孤儿文件操作跨进程 lease（扫描/预览/清理互斥） |
| `orphan_lifecycle_service.py` | 227 | 1 class, 0 def | `OrphanCurrentCandidate` 表生命周期推进（仅稳定候选可清理，支持事务化状态落库） |
| `orphan_manifest.py` | 284 | 3 class, 1 def | 孤儿文件扫描/清理共用 manifest 构建器 |
| `orphan_notification.py` | 129 | 0 class, 3 def | 孤儿扫描完成通知（幂等 dedupe_key） |
| `orphan_quarantine.py` | 250 | 0 class, 8 def | 孤儿隔离区管理（移入 → 保留期 → 物理删除） |
| `orphan_scanner.py` | 739 | 3 class, 1 def | 孤儿文件扫描器（扫描下载器磁盘找不在种子清单中的文件） |
| `path_maintenance_service.py` | 552 | 1 class, 0 def | 下载器路径维护服务（默认/活跃路径） |
| `reannounce_service.py` | 239 | 0 class, 5 def | Tracker Reannounce 核心服务（API 与定时任务共用） |
| `recycle_bin_service.py` | 783 | 1 class, 0 def | 回收站服务（列表/还原/清理/批量/记录） |
| `seed_transfer_service.py` | 721 | 1 class, 0 def | 种子转移（备份读种子 → 加到目标 → 轮询验证） |
| `speed_schedule_service.py` | 155 | 1 class, 0 def | 分时段限速服务 |
| `sqlite_search_runtime.py` ✨v1.0.6.27 | 100 | 1 class, 8 def | 高级搜索有界正则运行时（`RegexSearchTimeout`、`validate_regex_pattern`、threading.local 状态隔离、单次 match 10ms / 查询总预算 2s 双重熔断，防 ReDoS） |
| `sync_db_write.py` | 183 | 0 class, 5 def | 同步任务 DB 写入治理（变更检测 + 批量 upsert + 串行化） |
| `tag_service.py` | 809 | 1 class, 0 def | 标签管理业务（支持同步/异步两种调用） |
| `tag_sync_service.py` | 669 | 1 class, 0 def | 标签同步服务（去 DB 查询，直接走缓存） |
| `template_service.py` | 690 | 1 class, 1 def | 配置模板服务（CRUD/验证/应用/冲突检测） |
| `torrent_crud_service.py` | 686 | 0 class, 26 def | 种子 DB CRUD 服务（模块级函数集合，无类；v1.0.6.25 起写入时通过 `torrent_ratio_values` 规范化 ratio/ratio_limit） |
| `torrent_deletion_by_level.py` | 1670 | 1 class, 0 def | 种子按等级删除（L1 删任务+数据 / L2 保数据 / L3 移回收站 / L4 加标签） |
| `torrent_deletion_service.py` | 621 | 8 class, 0 def | 种子删除服务（抽象基类 + 各下载器策略） |
| `torrent_file_backup_manager.py` | 544 | 1 class, 0 def | 种子文件备份管理（协调 Repository 与文件操作） |
| `torrent_location_service.py` | 295 | 1 class, 0 def | 种子保存路径修改（参数验证 → 取适配器 → 调 SDK） |
| `torrent_metadata.py` | 614 | 0 class, 23 def | Torrent 元数据 hydrate（缓存连接补齐 DB 行展示，不二次建连） |
| `torrent_ratio_values.py` ✨v1.0.6.25 | 150 | 3 class, 4 def | ratio/ratio_limit 规范化（`RatioValueState` 三态枚举 value/explicit_null/unavailable + `NormalizedRatioValue`/`RatioNormalizationStats`；区分"下载器明确无限制 -1/-2"与"数据缺失"，避免瞬时下载器故障清空已存值） |

## downloader_adapters/ 子包（6 个文件）

下载器适配器：种子删除 + 种子位置修改两类适配器，按 qB/Transmission 分别实现。

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `__init__.py` | 9 | 0 class, 0 def | 导出 `QBittorrentDeleteAdapter` / `TransmissionDeleteAdapter` |
| `location_base.py` | 50 | 1 class | 种子位置修改适配器抽象基类 |
| `qbittorrent.py` | 510 | 1 class | `QBittorrentDeleteAdapter`（删除适配器） |
| `qbittorrent_location.py` | 89 | 1 class | qBittorrent 位置修改适配器 |
| `transmission.py` | 505 | 1 class | `TransmissionDeleteAdapter`（强制缓存连接） |
| `transmission_location.py` | 82 | 1 class | Transmission 位置修改适配器 |

## tag_adapters/ 子包（6 个文件）

标签适配器：统一 qB（category + tag 双类型）/ Transmission（仅 tag）的标签操作接口。

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `__init__.py` | 21 | 0 class, 0 def | 模块说明（适配器模式统一标签/分类） |
| `base.py` | 258 | 1 class | 标签适配器抽象基类 |
| `fallback_handler.py` | 353 | 1 class | 标签降级策略（Transmission 不支持分类时降级为标签） |
| `qbittorrent_adapter.py` | 515 | 1 class | qBittorrent 标签适配器（category + tag） |
| `tag_adapter_factory.py` | 165 | 1 class | 标签适配器工厂（按下载器类型创建实例） |
| `transmission_adapter.py` | 607 | 1 class | Transmission 标签适配器（仅 tag） |

---

## 关键模式

- **适配器模式**：`downloader_adapters` 与 `tag_adapters` 都遵循"抽象基类 → qB/Transmission 两实现 → 工厂创建"三件套
- **同步/异步双版本**：`audit_service.py`（异步）+ `audit_service_sync.py`（同步）；`tag_service.py` 内部支持两种调用；`cron_crud.py` + `cron_crud_async.py`（在 tasks 分支）
- **模块级函数 vs 类**：`torrent_crud_service.py`（26 个函数无类）与 `torrent_metadata.py`（23 个函数无类）是有意写成工具函数集合，与 `DashboardService` 等类风格并存
- **契约驱动（v1.0.6.27）**：`advanced_search.py` 不再硬编码操作符/字段语义，而是 import `app.contracts.advanced_search`（`SUPPORTED_SEARCH_OPERATORS` / `allowed_operators_for_field`）做请求期校验 + `sqlite_search_runtime` 做有界正则执行，两套防护把"前端可选但后端不支持"与"恶意/超长正则 ReDoS"分别拦截在请求期与执行期
- **三态值规范化（v1.0.6.25）**：`torrent_ratio_values.py` 用 `RatioValueState` 枚举（value/explicit_null/unavailable）区分"有限值 / 下载器明确无限制 / 数据缺失"，配合 CHECK 约束（见 `alembic/versions/8f4c2d1a9b7e_ratio_value_constraints.py`）实现 ratio 列从 String→Float 的治本迁移

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`torrent_deletion_by_level.py` 1670 行、`orphan_file_service.py` 1339 行、`advanced_search.py` 1311 行）
