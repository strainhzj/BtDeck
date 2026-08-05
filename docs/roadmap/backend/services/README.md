# backend/services — 业务服务层

> 业务逻辑层，承接 endpoint 调用，向下依赖 core 基础设施与 ORM 模型。包含两个适配器子包（下载器适配器、标签适配器）。
> 定位方式：`Grep -i <功能词> docs/roadmap/backend/services/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

### services/ 根（38 个文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 高级搜索 advanced-search ratio | `advanced_search.py` | 高级搜索服务（ORM 查询引擎，13 字段；v1.0.6.25 起 4 个 ratio 操作符 + `app.contracts` 校验；正则经 `sqlite_search_runtime` 受限执行防 ReDoS） |
| 异步删除 async-deletion | `async_deletion_executor.py` | 异步批量删除执行器（超时/跳过失败/计数） |
| 审计日志 audit | `audit_service.py` / `audit_service_sync.py` | 审计日志异步/同步服务（记录/查询/归档，不阻塞主业务） |
| 仪表盘 dashboard | `dashboard_service.py` | `DashboardService`：仪表盘聚合数据 |
| 删除任务删除管理 deletion-task | `deletion_task_manager.py` | 内存任务管理器（异步批量删除任务生命周期） |
| 下载器 RPC downloader-rpc | `downloader_api_runtime.py` | 下载器 RPC 调用隔离层（三 lane 线程池隔离 qB/Transmission） |
| 下载器能力 downloader-capability | `downloader_capabilities_manager.py` | 下载器能力配置 CRUD 与同步 |
| 下载器设置 downloader-setting | `downloader_settings_manager.py` | 下载器设置统一管理器 |
| 通知 notification | `notification_service.py` | 通知服务（CRUD + 版本更新检查） |
| 孤儿文件管理 orphan | `orphan_file_service.py` | 孤儿文件管理（扫描/清理/隔离/恢复/彻底删除/中断恢复）；canonical_path 稳定身份；v1.0.6.34~36 大分页/真全选/忽视过滤；`get_orphan_list_grouped` 按直接父目录聚合分页（SQLite 自定义函数 `bt_orphan_parent_dir`，见 `orphan_folder_grouping.py`） |
| 孤儿 lease orphan-lease | `orphan_lease.py` | 孤儿文件操作跨进程 lease（扫描/预览/清理互斥） |
| 孤儿生命周期 orphan-lifecycle | `orphan_lifecycle_service.py` | `OrphanCurrentCandidate` 表生命周期推进（事务化状态落库） |
| 孤儿 manifest orphan-manifest | `orphan_manifest.py` | 有效路径筛选、严格下载器映射、扫描/清理共用实时 manifest |
| 孤儿通知 orphan-notify | `orphan_notification.py` | 孤儿扫描完成通知（幂等 dedupe_key） |
| 孤儿彻底删除 orphan-purge | `orphan_purge_job_service.py` | 隔离区彻底删除持久化任务（原子领取/串行执行/重启恢复/幂等补偿） |
| 孤儿隔离区 orphan-quarantine | `orphan_quarantine.py` | 孤儿隔离区管理（移入→保留期→物理删除），仅 `os.rmdir` 回收空目录 |
| 孤儿扫描 orphan-scanner | `orphan_scanner.py` | 孤儿文件扫描器（未映射路径记录并跳过） |
| 路径映射验证 path-mapping | `path_mapping_validation.py` | 路径映射目录验证（free_space 探测/磁盘空间/现有种子路径取证/有界 stat） |
| 路径维护 path-maintenance | `path_maintenance_service.py` | 下载器路径维护服务（默认/活跃路径） |
| Tracker 重宣告 reannounce | `reannounce_service.py` | Tracker Reannounce 核心服务（API 与定时任务共用） |
| 回收站 recycle-bin | `recycle_bin_service.py` | 回收站服务（列表/还原/清理/批量/记录） |
| 种子转移 seed-transfer | `seed_transfer_service.py` | 种子转移（备份读种子→加到目标→轮询验证） |
| 分时段限速 speed-schedule | `speed_schedule_service.py` | 分时段限速服务 |
| 搜索正则运行时 sqlite-search | `sqlite_search_runtime.py` | 高级搜索有界正则运行时（单次 match 10ms / 总预算 2s 双重熔断防 ReDoS） |
| 同步写库 sync-db | `sync_db_write.py` | 同步任务 DB 写入治理（变更检测+批量 upsert+串行化） |
| 标签 tag | `tag_service.py` / `tag_sync_service.py` | 标签管理业务（同步/异步）；同步服务直接走缓存 |
| 配置模板 template | `template_service.py` | 配置模板服务（CRUD/验证/应用/冲突检测） |
| 批量添加种子 batch-add | `torrent_batch_add_service.py` | 异步批量添加种子（暂存 .torrent→逐个异步 add→通知）；自 `torrent_crud` 抽取 |
| 种子 DB CRUD torrent-crud | `torrent_crud_service.py` | 种子 DB CRUD 服务（26 个模块级函数，无类；ratio/ratio_limit 规范化） |
| 种子按等级删除 torrent-delete-level | `torrent_deletion_by_level.py` | 种子按等级删除（L1 删任务+数据/L2 保数据/L3 移回收站/L4 加标签） |
| 种子删除策略 torrent-delete | `torrent_deletion_service.py` | 种子删除服务（抽象基类 + 各下载器策略） |
| 种子备份 torrent-backup | `torrent_file_backup_manager.py` | 种子文件备份管理（协调 Repository 与文件操作） |
| 种子路径修改 torrent-location | `torrent_location_service.py` | 种子保存路径修改（参数验证→取适配器→调 SDK） |
| 种子元数据 hydrate torrent-meta | `torrent_metadata.py` | Torrent 元数据 hydrate（缓存连接补齐展示，不二次建连） |
| ratio 规范化 torrent-ratio | `torrent_ratio_values.py` | ratio/ratio_limit 规范化（三态枚举 value/explicit_null/unavailable） |

### downloader_adapters/ 子包（6 个文件）

下载器适配器：种子删除 + 种子位置修改，按 qB/Transmission 分别实现。

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 删除适配器基类 delete-base | `location_base.py` | 种子位置修改适配器抽象基类 |
| qB 删除适配器 qb-delete | `qbittorrent.py` | `QBittorrentDeleteAdapter` |
| qB 位置适配器 qb-location | `qbittorrent_location.py` | qBittorrent 位置修改适配器 |
| Transmission 删除适配器 tr-delete | `transmission.py` | `TransmissionDeleteAdapter`（强制缓存连接） |
| Transmission 位置适配器 tr-location | `transmission_location.py` | Transmission 位置修改适配器 |

### tag_adapters/ 子包（6 个文件）

标签适配器：统一 qB（category + tag）/ Transmission（仅 tag）标签操作。

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 标签适配器基类 tag-base | `base.py` | 标签适配器抽象基类 |
| 标签降级 tag-fallback | `fallback_handler.py` | 标签降级策略（Transmission 不支持分类时降级为标签） |
| qB 标签适配器 qb-tag | `qbittorrent_adapter.py` | qBittorrent 标签适配器（category + tag） |
| 标签工厂 tag-factory | `tag_adapter_factory.py` | 标签适配器工厂（按下载器类型创建） |
| Transmission 标签适配器 tr-tag | `transmission_adapter.py` | Transmission 标签适配器（仅 tag） |

---

## 关键模式

- **适配器模式**：`downloader_adapters` 与 `tag_adapters` 都遵循"抽象基类 → qB/Transmission 两实现 → 工厂创建"三件套
- **同步/异步双版本**：`audit_service.py`（异步）+ `audit_service_sync.py`（同步）；`tag_service.py` 内部支持两种调用；`cron_crud.py` + `cron_crud_async.py`（在 tasks 分支）
- **模块级函数 vs 类**：`torrent_crud_service.py`（26 个函数无类）与 `torrent_metadata.py`（23 个函数无类）是有意写成工具函数集合，与 `DashboardService` 等类风格并存
- **契约驱动（v1.0.6.27）**：`advanced_search.py` 不再硬编码操作符/字段语义，而是 import `app.contracts.advanced_search` 做请求期校验 + `sqlite_search_runtime` 做有界正则执行
- **三态值规范化（v1.0.6.25）**：`torrent_ratio_values.py` 用 `RatioValueState` 枚举区分"有限值/下载器明确无限制/数据缺失"

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`orphan_file_service.py` 2482 行、`torrent_deletion_by_level.py` 1670 行、`advanced_search.py` 1311 行）
