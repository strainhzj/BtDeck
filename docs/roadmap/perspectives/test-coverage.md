# test-coverage — 测试覆盖矩阵

> 源文件 ↔ 测试文件覆盖矩阵（按子目录组织）。仅统计文件级对应，不评估覆盖率百分比。

## 后端测试分布（共 180 个 test_*.py）

| 测试目录 | test 文件数 | 对应源码分支 | 覆盖评估 |
|---------|------------|-------------|---------|
| `tests/api/` | 63 | `app/api/` | ✅ 覆盖良好；异步删除、孤儿任务、重复查询及同内容只读排查均有 API 回归 |
| `tests/services/` | 50 | `app/services/` | 🟡 中等；含删除/孤儿持久化占用、孤儿后台扫描调度与稳定明细回归（不含下方 tag_adapters 子目录） |
| `tests/tasks/` | 18 | `app/tasks/` | 🟡 部分覆盖（18 对 34） |
| `tests/core/` | 21 | `app/core/` | 🟡 中等；新增大库迁移恢复与 lifecycle fail-fast 回归 |
| `tests/models/` | 6 | `app/models/` | 🟡 部分覆盖（6 对 21） |
| `tests/utils/` | 5 | `app/utils/` | ✅ 覆盖良好（5 对 5） |
| `tests/auth/` | 5 | `app/auth/` | ✅ 覆盖良好（5 对 7） |
| `tests/enums/` | 2 | `app/enums/` | ✅ 全覆盖（2 对 2） |
| `tests/downloader/` | 1 | `app/downloader/` | ⚠ 薄弱（1 对 9） |
| `tests/endpoints/` | 1 | `app/api/endpoints/` | ⚠ 薄弱（1 对 37，仅 `test_active_only_filter.py`） |
| `tests/architecture/` | 1 | 全局架构 | 架构约束防退化（异步端点下载器调用 AST 扫描） |
| `tests/integration/` | 4 | 跨层链路 | SQLite 同步争用、120100 条孤儿生命周期与 API 响应性 |
| `tests/repositories/` | 1 | `app/repositories/` | ⚠ 薄弱（1 对 4） |
| `tests/services/tag_adapters/` | 1 | `app/services/tag_adapters/` | ⚠ 薄弱（1 对 6，仅 `test_tag_adapter_factory.py`） |
| `tests/` 顶层 | 1 | 全局 | `test_architecture_constraints.py`（架构约束防退化） |

> 合计：当前实测 **180** 个 test_*.py。

> 注：`tests/api/`（63 文件）覆盖 `app/api/` 顶层、schemas 与部分端点集成行为；`tests/endpoints/` 另有 1 文件。

### v1.0.6.25~32 新增后端测试

| 新增测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/core/test_ratio_data_diagnostics.py` | 158 | `app/core/ratio_data_diagnostics.py` |
| `tests/services/test_torrent_ratio_values.py` | 179 | `app/services/torrent_ratio_values.py` |
| `tests/services/test_advanced_search_regression.py` | 2130 | `app/services/advanced_search.py`（真实 SQLite 完备回归：状态真值表、Tracker `NOT EXISTS`/软删除、字面文本、标签 token、稳定下载器 ID/改名、超级做种三态、回收站/NULL 补集及跨字段正反分区矩阵） |
| `tests/services/test_advanced_search_models_strict.py` | 161 | `app/api/models/advanced_search.py`（字段级操作符白名单、模板 include/exclude、旧标签与超级做种值归一） |
| `tests/services/test_sqlite_search_runtime.py` | 27 | `app/services/sqlite_search_runtime.py`（正则熔断） |
| `tests/api/test_advanced_search_pagination.py` | 139 | `app/api/endpoints/advanced_search.py`（分页） |
| `tests/services/test_torrent_metadata.py` | 100 | `app/services/torrent_metadata.py` |
| `tests/api/test_path_mapping_validation.py` | 301 | `app/api/endpoints/downloader.py` + `app/services/path_mapping_validation.py` |

### v1.0.6.33~36 新增后端测试

| 新增测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/core/test_path_mapping_unicode.py` | 553 | `app/core/path_mapping.py`（路径映射 unicode：空格/中文边界） |
| `tests/api/test_torrent_batch_add_api.py` | 116 | `app/api/endpoints/torrent_crud.py` + `app/services/torrent_batch_add_service.py`（异步批量添加） |
| `tests/api/test_downloader_path_mapping_update.py` | 141 | `app/api/endpoints/downloader.py` + `app/api/schemas/path_mapping.py`（设置稳定化后的路径映射更新） |

### 2026-08-09 异步操作占用回归

| 测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/services/test_deletion_task_manager.py` | 143 | 种子删除 ID 并发原子占用、终态释放、大集合 JSON 查询排除 |
| `tests/services/test_orphan_purge_job_service.py` | 470 | 孤儿清理/彻底删除持久化占用、混合跳过与并发提交 |
| `tests/services/test_orphan_query_state.py` | 349 | 活动任务隐藏，失败终态后重新可见 |
| `tests/api/test_duplicate_quick_delete_api.py` | 322 | 快捷删除重复提交与混合接受 |

### 2026-08-12 种子文件、错误原因与搜索交互回归

| 测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/api/test_transmission_error_sync.py` | 394 | Transmission 错误状态/原因提取、FULL/INFO-ONLY 持久化、原因变化检测、恢复清空、旧 RPC 兼容及 legacy/async Tracker 0–4 状态写入 |
| `tests/api/test_tracker_migration.py` | 730 | qB/Transmission Tracker 手动新增、修改、删除路径；Transmission announce/scrape 独立状态码持久化 |
| `tests/services/test_tracker_status_sync.py` | 972 | Tracker 行级 Working + `None`/空白消息历史 error 恢复；announce/scrape 状态边界、非空关键词优先、未知逐行保留、双消息、幂等、host 跨种子隔离及 zimiao 359 行快照形态 |
| `tests/services/test_sync_coordinator.py` | 1039 | 统一同步协调、准入/取消/检查点/观测；活动运行 phase/last-progress 与阶段事件；Tracker 原始同步成功后才调用行级状态同步，失败时跳过并锁定调用顺序；Tracker 下载器级硬超时、部分成功与关闭开关；info/full 同步后调用备份增量补偿（full 同样触发、tracker 不触发、补偿失败不阻断信息同步） |
| `tests/tasks/test_torrent_tracker_status_judge.py` | 546 | qB/Transmission 未联系/发送中为中性；Working + `None`/空白消息明确正常；zimiao 双 Tracker 顺序/类型/空消息矩阵；非空关键词优先、软删除隔离、真实 SQLite 批量更新、独立 Cron 错峰与重任务互斥 |
| `tests/api/test_torrent_backup_review.py` | 188 | 备份列表当前下载器 nickname 单查询批量解析及序列化 |
| `tests/api/test_torrents_async_info_budget.py` | 626 | INFO-ONLY 请求 `errorString` 并批量写入 `error_reason` |
| `tests/models/test_torrent_models.py` | 348 | `TorrentInfo.error_reason` 字段全集与值映射 |

### 2026-08-13 最新提交回归加固

| 测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/core/test_tracker_status_policy.py` | 105 | `app/core/tracker_status_policy.py`：Working 空消息正常证据、非空消息优先、announce/scrape 双消息、精确/部分关键词匹配、未知保留及错误状态聚合 |

### 2026-08-14 Tracker 筛选与错误单种排查回归

| 测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/api/test_torrent_list_api.py` | 858 | `torrent_crud.py` + `torrent_helpers.py`：Tracker 主机域名去端口筛选、同步域名列表排序、错误状态与全局同名同大小唯一性；Tracker 多服务不改变任务唯一性 |

### 2026-08-15 备份补偿与副本整体定位回归

| 测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/services/test_orphan_hardlink_copy_scan.py` | 742 | `orphan_hardlink_scan_service.py` + `orphan_quarantine.py::find_hardlink_paths_bounded`：过期 deadline 部分结果+budget_exceeded、单目标路径截断不影响其它目标、无界对等、walk 限量 deferral、游标推进/回绕、幂等更新、保留期清理、单链接轮不遍历、stat 预算停止保进度、受控时钟中途截止/截断优先级、resolved/无指针跳过、新鲜度排序、budget 落行、任务注册/heavy_sync/护栏默认值契约与 execute 包装器 |
| `tests/services/test_torrent_file_backup_reconcile.py` | 162 | `torrent_file_backup_manager.py`：`reconcile_missing_backups` 限量批次、幂等收敛、qB/Transmission 常见源文件名、逻辑删除墓碑不再自动重建与源目录不可用一次性上报 |

### 2026-08-26 Tracker 状态同步健壮性回归加固

| 测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/api/test_torrents_async_tracker_budget.py` | 765 | `app/api/endpoints/torrents_async.py`：有界队列预算、producer 哨兵重试、全部哨兵丢失时 worker 轮询自愈、取消后的 producer/worker 子任务清理及稳定顺序 |
| `tests/services/test_sync_coordinator.py` | 1039 | `app/services/sync_coordinator.py`：Tracker 原始同步、行级状态同步顺序、下载器级硬超时/部分成功/关闭开关及取消语义 |
| `tests/downloader/test_auth_client_timeout.py` | 143 | `app/downloader/initialization.py`：qB/Transmission 客户端请求超时、scheme 归一、关闭 SDK 探测与 urllib3 重试，以及缓存客户端实际构造参数 |

### 2026-08-30 下载器手动同步异步生命周期回归

| 测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/core/test_background_task_manager.py` | 96 | `app/core/background_task_manager.py`：pending/running 原子占用、结构化 failed 结果终态映射、runner 执行期强引用与完成释放 |
| `tests/api/test_sync_governance_integration.py` | 313 | `app/api/endpoints/torrent_sync.py`：sync-single 立即返回 task_id、真实后台运行、同下载器重复提交 409，且仅调用一次 `SyncCoordinator(full/manual)` |
| `frontend/tests/unit/downloader-sync-task.spec.ts` | 134 | `api/downloader.ts` + `views/downloader/sync-task.ts`：pending/running 轮询、success/partial/failed/cancelled 终态文案、销毁取消与连续查询失败上限 |
| `frontend/tests/unit/downloader-control-room-ui.spec.ts` / `mobile-downloader.spec.ts` / `api-contracts.spec.ts` | 166 / 237 / 974 | 桌面与移动同步占用保持到真实终态、task_id 跟踪、状态查询 URL 编码契约 |

### 关键源文件测试覆盖抽样

| 源文件 | 测试文件 | 状态 |
|--------|---------|------|
| `app/api/endpoints/torrent_crud.py` / `torrent_helpers.py` | `test_torrent_list_api.py`（858 行） | ✅ 普通列表及 `same_content_only` 组合筛选、Tracker 主机域名筛选与域名列表、`single_error_only` 全局唯一错误单种、无效成员排除、活动删除/活动快照、复合主键稳定行级分页、大页绑定安全、当前页关联预取、软删除/回收站排除与 camelCase 响应 |
| `app/api/endpoints/duplicate_torrents.py` | `tests/api/test_duplicate_torrents_api.py`（1479 行，40 用例） | ✅ 默认添加时间倒序、安全列排序、非法排序拒绝、完整重复组筛选、活动快照/空快照、分页与元数据回填 |
| `app/api/endpoints/torrent_backup.py` | `tests/api/test_torrent_backup_review.py`（188 行） | ✅ 当前 nickname 批量查询、空列表跳过查询与序列化 |
| `app/api/endpoints/torrents_async.py` / `torrent_sync.py` / `torrent_helpers.py` | `test_transmission_error_sync.py` + `test_torrents_async_info_budget.py` + `test_torrent_list_api.py` | ✅ Transmission 错误原因全链路、恢复清空、Tracker 状态归一与 camelCase 响应 |
| `app/core/torrent_status_mapper.py` | `tests/core/test_torrent_status_mapper.py` + `tests/api/test_transmission_error_sync.py` | ✅ 状态判定与安全错误文本提取 |
| `app/services/advanced_search.py` | `test_advanced_search.py` + `test_advanced_search_regression.py`（2130 行）+ `test_advanced_search_models_strict.py`（161 行） | ✅✅ 重度覆盖（20 字段审计、活动/回收站排除、普通列表一致的 `error`、关系/文本/标签/空值/三态/稳定 ID 与跨字段正反分区） |
| `app/tasks/scheduler/torrent_tracker_status_judge.py` | `test_torrent_tracker_status_judge.py` + `test_heavy_task_db_write_governance.py` | ✅ 状态码+关键词联合判定、Working 空消息恢复正常、zimiao 双 Tracker 聚合、软删除隔离、独立 Cron 错峰、重任务互斥与批量查询治理 |
| `app/core/tracker_status_policy.py` / `app/services/tracker_status_sync.py` | `test_tracker_status_policy.py` + `test_tracker_status_sync.py` + `test_torrent_tracker_status_judge.py` | ✅ 共享状态/关键词证据语义直接契约、行级 Working 空消息恢复、未知保留、双消息聚合、幂等及 host 隔离 |
| `app/services/deletion_task_manager.py` | `test_deletion_task_manager.py` + 删除 API/快捷删除 API 测试 | ✅ 原子占用、终态释放、大集合排除 |
| `app/services/orphan_scan_job_service.py` / `orphan_lifecycle_service.py` / `orphan_file_service.py` | `test_orphan_scan_job_service.py`（232 行）+ `test_orphan_lifecycle.py` + `test_orphan_folder_grouping.py` + `test_orphan_scan_120k_regression.py`（315 行） | ✅ 后台 scan_id 提交/恢复/兼容复核记录、稳定明细复用、分批生命周期、文件夹懒加载；真实文件 SQLite WAL/NullPool 覆盖 120100 条争用与状态 API 延迟 |
| `app/services/orphan_purge_job_service.py` / `orphan_quarantine.py` / `orphan_hardlink_scan_service.py` | `test_orphan_purge_job_service.py` + `test_orphan_query_state.py` + `test_orphan_hardlink_detection.py` + `test_orphan_hardlink_copy_scan.py` + `test_orphan_files_api.py` | ✅ 持久化占用、查询可见性、可见文件硬链接副本计数；副本位置自 2026-08-15 起由定时预扫描落库（性能护栏与只读契约回归） |
| `app/services/torrent_ratio_values.py` | `test_torrent_ratio_values.py` | ✅（v1.0.6.25 新增） |
| `app/services/sqlite_search_runtime.py` | `test_sqlite_search_runtime.py` | ✅（v1.0.6.27 新增） |
| `app/services/path_mapping_validation.py` | `test_path_mapping_validation.py` | ✅（v1.0.6.32 新增，10 个用例） |
| `app/core/ratio_data_diagnostics.py` | `test_ratio_data_diagnostics.py` | ✅（v1.0.6.27 新增） |
| `app/services/orphan_scanner.py` | `test_orphan_scanner.py` | ✅ |
| `app/services/reannounce_service.py` | `test_reannounce_service.py` + `test_reannounce_config.py` | ✅ |
| `app/core/database_result.py` | `test_database_result.py` | ✅ |
| `app/core/migration.py` / `startup/lifecycle.py` / `7b2c9d4e6f10` / `b6e1c4d9a2f7` / `c8d9e0f1a2b3` | `test_db_migration.py` + `test_db_rollback_scenarios.py` + `test_orphan_migration_production_shape.py` + `test_startup_migration_guard.py` | ✅ 单 head；覆盖 batch 中断恢复/缺原表拒绝、canonical_path 索引回填、历史超量提醒标记、真实文件 WAL 大数据升级与任意模式启动 fail-fast；`b6e1c4d9a2f7` 备份下载器 ID UUID 类型升级保留 UUID/索引/外键，含不可无损转换数据时 downgrade 拒绝回滚；`c8d9e0f1a2b3` 副本预扫描两表可建可回滚、device_id 字符串列与身份唯一约束 |
| `app/core/path_mapping.py` | （未发现直接测试） | ⚠ 未覆盖 |
| `app/core/file_operations.py`（1474 行） | （未发现直接测试） | ⚠ 未覆盖 |

### 2026-08-29 实时终态收敛回归

| 新增/扩展测试文件 | 覆盖源文件 | 覆盖内容 |
|------------|-----------|---------|
| `tests/api/test_torrent_speed_regression.py`（1012 行） | `app/api/endpoints/torrent_speed.py` | TTL 补查退避/恢复、超过 20 条任务的公平轮转、完成移除；qB/Transmission 完成状态矩阵、100% 优先级、异常进度与错误终态 |
| `tests/api/test_active_torrents_endpoint.py`（632 行） | `app/api/endpoints/torrent_speed.py` | status/downloadComplete 契约；“下载中有速度→零速完成”两轮闭环强制 100%、响应前同步与 TTL 移除；206 仍交付健康下载器终态；核验 list/missing |
| `tests/endpoints/test_active_only_filter.py`（601 行） | `app/api/endpoints/torrent_speed.py` | 终态证据同步进度 100、状态与 completed_date；完成时间/完成状态/100% 三种数据库证据分别阻止异步旧快照回退 |

## 前端测试分布

### `frontend/tests/unit/`（78 个 spec）

| 测试文件 | 覆盖范围 |
|---------|---------|
| `api-contracts.spec.ts` ✨2026-08-29 | API 契约一致性；回收站响应类型源码锁定；终态核验 POST `/torrents/runtime-state/reconcile` 按 downloader_id+hash 复合键提交 `{items}` |
| `clipboard.spec.ts` ✨v1.0.6.36 | `utils/clipboard.ts`（剪贴板复制回退：Clipboard API / execCommand 降级） |
| `column-resize-mixin.spec.ts` | 表格列宽调整 mixin 契约 |
| `column-resize-regression.spec.ts` | 列宽调整回归 |
| `downloader-settings.spec.ts` | 下载器设置 store |
| `downloader-control-room-ui.spec.ts` ✨v1.0.6.30 | 下载器控制室 UI（节点矩阵/筛选操作台/遥测卡片交互） |
| `downloader-regressions.spec.ts` ✨v1.0.6.33 | 下载器设置工作流回归 |
| `deployment-recovery.spec.ts` | 部署后 chunk 一次恢复、刷新循环门禁、历史 Workbox 清退与 nginx 缓存契约 |
| `error-normalize.spec.ts` | `utils/error-normalize.ts` |
| `file-management-contract.spec.ts` ✨2026-08-12 | `FileManagement.vue` + `api/torrents.ts`：当前 nickname、无逐行动态请求、统一管理页筛选 UI |
| `field-types-consistency.spec.ts` ✨v1.0.6.27 | 高级搜索字段类型前后端一致性 |
| `filter-group-accessibility.spec.ts` | FilterGroup 可访问性 |
| `lint-vuex-action.spec.ts` | Vuex action 规范 |
| `management-pages-ui.spec.ts` | 管理页面 UI；回收站搜索区与查询模板 Lucide 极简行操作契约 |
| `mobile-dashboard.spec.ts` ✨2026-08-26 | 移动仪表盘：字段映射契约（torrents/downloaders/system，旧键负例锁死）、bytes/s 速度换算、下载器卡片与穿透 /m/downloader、已暂停统计展示 |
| `mobile-downloader.spec.ts` ✨2026-08-24 | 移动下载器监控页：卡片/在线徽标/测试连接 data.success 契约 |
| `mobile-downloader-settings.spec.ts` ✨2026-08-24 | 移动下载器设置页：整页复用桌面 DownloaderSettingsDialog 的挂载与返回 |
| `mobile-logs.spec.ts` ✨2026-08-24 | 移动审计日志：结果筛选值契约（success/failed/partial）与三态展示 |
| `mobile-notifications.spec.ts` ✨2026-08-27 | 移动通知中心：摘要剥离 Markdown 记号纯文本三行截断（共享 plainNotificationContent）、点击详情同源渲染（共享 notification-markdown）、查看即已读+角标联动、失败明细/Release 链接、源码契约禁裸文本直渲 |
| `mobile-orphan-files.spec.ts` ✨2026-08-24 | 移动孤儿文件双 Tab：扫描轮询/清理两段式/忽视/隔离区恢复与立即清除 |
| `mobile-query-templates.spec.ts` ✨2026-08-24 | 移动查询模板：应用按来源分流（简单→/m/torrents，高级→/m/search）、系统模板只可应用不可删除 |
| `mobile-recycle-bin.spec.ts` ✨2026-08-27 | 移动回收站：卡片列表/名称搜索/单条恢复与彻底删除、载荷必须传 info_id（≠torrent_id 契约锁）、守卫按 info_id、失败提示展示 reason 与兜底、按钮禁用态契约、源码契约锁定 |
| `mobile-search.spec.ts` ✨2026-08-26 | 移动高级搜索：复用桌面 AdvancedSearchWorkspace（已保存搜索同源）、简单搜索迁出负例锁死、高级模板回填执行/简单模板转种子页、下拉刷新重放 |
| `mobile-shell.spec.ts` ✨2026-08-26 | 移动布局壳导航、抽屉、通知角标、滑动手势、主题色及反白微型 Logo 契约 |
| `mobile-tasks.spec.ts` ✨2026-08-24 | 移动定时任务：卡片六态 outcome、启停/立即执行/中断/删除 |
| `mobile-torrent-detail.spec.ts` ✨2026-08-24 | 移动种子详情：列表快照缓存立即渲染、速度轮询、删除后返回刷新 |
| `mobile-torrents.spec.ts` ✨2026-08-30 | 移动种子页简单搜索（自搜索页迁入）、筛选/刷新/空态；连续两个完整快照未命中后核验零速终态并收敛到 100%，下载中筛选启用时重新拉表移除不匹配行；新活动复合键未展示时重载列表并立即应用同轮进度与速度 |
| `mobile-tracker-keywords.spec.ts` ✨2026-08-24 | 移动关键词看板：四池 Tab 计数、卡片移池/删除、候选池禁添加 |
| `mobile-tracker-keywords-search.spec.ts` ✨2026-08-24 | 移动关键词全池搜索：同字段集检索与 ?keyword= 初始词 |
| `notification-drawer-detail.spec.ts` ✨2026-08-27 | 桌面通知渲染：detailHtml 必须委托 utils/notification-markdown（源码契约禁内联转换回流）、NotificationItem 列表摘要共享纯文本化（禁模板直塞原始 content）、handleView 未读自动已读、失败明细/Release 链接、未读数轮询启停 |
| `notification-markdown.spec.ts` ✨2026-08-27 | `utils/notification-markdown.ts`：Markdown-lite 分块渲染（标题/列表/粗体/行内代码/分隔线/CRLF/转义防注入）、摘要纯文本化 plainNotificationContent（记号剥离/语法严格性/分隔线丢弃/跨行内联合并/不做 HTML 转义）与失败明细目标回退链，桌面/移动同源行为锁 |
| `pwa-manifest.spec.ts` ✨2026-08-26 | 完整 `BtDeck` 字标、微型 mark 资源、favicon/PWA manifest 与图标生成源契约 |
| `operator-contract.spec.ts`（338 行）✨v1.0.6.26 | 高级搜索生成契约守卫；覆盖标签旧模板、三态、五个可空字段/非空字段矩阵及跨字段 `mode=exclude` 不预翻转操作符 |
| `orphan-files.spec.ts` | 孤儿后台扫描轮询、超量复核、文件夹展开懒加载/子页选择、可见文件硬链接、清理/隔离工作流，以及扁平/文件夹模式展开列切换、普通行展开保护、子表表头/数据/选择事件契约 |
| `page-size-combobox.spec.ts` ✨v1.0.6.30 | 共享 `PageSizeCombobox`：默认预设、受控输入、公共事件、ARIA 展开态与 `focusInput()` |
| `permission-force-change-deadlock.spec.ts` ✨2026-08-18 | `permission.ts`+`router.ts` 真实路由死锁回归（生产事故修复锚定） |
| `permission-guard.spec.ts` ✨2026-08-17 | `permission.ts` 守卫真实路由导航五分支 |
| `pull-to-refresh.spec.ts` ✨2026-08-24 | 下拉刷新 mixin：阻尼/阈值/滚动容器判定与横向主导中止（与 Tab 滑动互斥） |
| `quick-delete-duplicates-dialog.spec.ts` | 重复种子快捷删除 nullable task_id、跳过提示与父列表刷新 |
| `refresh-prompt.spec.ts` ✨2026-08-25 | `RefreshPrompt.vue` PWA 更新提示：SW updated 事件、确认刷新 postMessage SKIP_WAITING |
| `request-auth.spec.ts` ✨2026-08-17 | `utils/request.ts` 401 全链路 |
| `router-navigation-failure.spec.ts` | 路由导航失败（重复导航/重定向中止）处理契约 |
| `session.spec.ts` ✨2026-08-17 | `utils/session.ts`：JWT exp 过期判定、hash 登录跳转 URL 构造、cookie→内存快照回同步 |
| `shared-utils.spec.ts` | 共享工具 |
| `sidebar-collapse-lucide.spec.ts` ✨2026-08-29 | `layout/components/Sidebar/SidebarItem.vue`：真实 Element UI/Lucide 组件与实际 SCSS 回归；种子管理/Tracker 管理多子菜单折叠仅隐藏语义标题/箭头并保留父图标，兼顾展开态、单子项与选择器防退化 |
| `sidebar-mobile-entry.spec.ts` ✨2026-08-24 | 桌面侧栏「移动版」入口：写显式偏好并跳 /m/dashboard |
| `store-modules.spec.ts` | Vuex modules |
| `store-user.spec.ts` ✨2026-08-16 | `store/modules/user.ts` 双令牌存储 |
| `speed-polling.spec.ts` | 种子速度轮询契约 |
| `tasks-sync-freshness.spec.ts` | 定时任务 outcome/stale helper 的模板实例可访问性与同步新鲜度展示契约 |
| `tasks-lucide-migration.spec.ts` | 定时任务页 Lucide 图标迁移守卫 |
| `token-refresh.spec.ts` ✨2026-08-16 | `utils/token-refresh.ts`：401 单飞刷新编排 |
| `torrent-add-dialog.spec.ts` ✨2026-08-30 | `views/torrents/components/TorrentAddDialog.vue`：202 响应 task_id 跟踪、完成通知精确匹配并发出 `batch-complete`、销毁清理轮询计时器 |
| `torrent-batch.spec.ts`（1496 行）✨2026-08-30 | `views/torrents/utils/torrentBatch.ts`（含“未联系”中性样式、模板到请求排除模式/正操作符端到端守卫；200/206 速度快照、终态状态矩阵、显式 false/100% 优先级、异常数值钳制、同 hash 复合键隔离、核验排除集与 100 项上限；运行态列表成员首次完整快照基线、206 增量、刷新重建基线及并发单飞） |
| `torrent-error-reason-ui.spec.ts` ✨2026-08-27 | `torrents/index.vue` + `TraditionalView.vue`：名称 tooltip、滚动收起接线、查询全屏锁滚动蒙版与 Tracker 卡片错误原因 |
| `torrent-error-tooltip-dismiss.spec.ts` ✨2026-08-27 | `mixins/errorTooltipDismiss.ts`：监听参数、数组/单例/空 ref、window/非冒泡滚动、销毁重挂载及真实 Element UI Tooltip 滚轮关闭闭环（7 例） |
| `torrent-loading-mask.spec.ts` ✨2026-08-27 | Element UI 2.15.13 真实 Loading 指令：fullscreen mask 挂 body、lock/unlock、隐藏状态与加载中销毁清理 |
| `torrent-list-view-component.spec.ts` ✨2026-08-30 | 列表视图异步删除与分页/排序、Tracker 筛选、错误单种/同内容数据源；连续完整快照未命中后核验零速终态并把主列表行收敛到 100%；数据库已入库但页面未展示的新活动键触发拉表并补同轮速度，批量添加完成信号再次刷新 |
| `torrent-view-switcher.spec.ts` | 列表/传统模式往返时保留查询/分页/选择状态 |
| `tracker-detail-card.spec.ts` | 共用 TrackerDetailCard 运行时回归 |
| `tracker-operation-dialog-contract.spec.ts` | Tracker 操作对话框契约 |
| `traditional-torrent-identity.spec.ts` | `views/torrents/utils/traditionalTorrentIdentity.ts` |
| `traditional-view-component.spec.ts` ✨2026-08-30 | 传统视图组件、Tracker 主域名过滤与快捷入口、共用 TrackerDetailCard；终态核验按 downloader_id+hash 精确更新同 hash 任务，missing 下载器不串写；新增未展示活动键自愈拉表与批量添加完成刷新 |
| `traditional-view-pagination.spec.ts` | `views/torrents/utils/traditionalPagination.ts` |
| `traditional-view-status-filter.spec.ts` | `views/torrents/utils/traditionalStatusFilter.ts` |
| `traditional-view-virtual-list.spec.ts` | `views/torrents/utils/traditionalVirtualList.ts` |
| `ui-mode.spec.ts` ✨2026-08-23 | `utils/ui-mode.ts`：偏好持久化(auto/mobile/desktop)+视口判定(768px)+模式合成+登录分流 |
| `user-store-must-change-password.spec.ts` ✨2026-08-16（2026-08-18 扩展） | 强制改密标志的 store 状态流转 |
| `settings-change-password.spec.ts` ✨2026-08-18 | `views/settings/index.vue` 改密流程（W9 死锁修复组件侧） |
| `settings-twofa-manual-entry.spec.ts` ✨2026-09-04 | `views/settings/index.vue` 2FA 二维码缺失降级手动录入（secret+复制+重置+源码契约） |
| `advanced-search-contract.spec.ts` ✨2026-09-04 | `scripts/generate-advanced-search-contract.js` 行尾规范化（LF/CRLF 检出双形态 current、内容变异双形态 stale、纯 LF 写出、幂等） |
| `batch-transfer-dialog.spec.ts` | 种子转移对话框契约 |
| `collapsible-panel.spec.ts` | 通用折叠面板（W8） |
| `keyword-list-modal.spec.ts` ✨2026-08-16 | Tracker 关键词列表弹窗与快捷操作入口 |
| `keyword-quick-action-dialog.spec.ts` ✨2026-08-16 | 关键词快捷删除/移动：preview→确认→执行→emit success |
| `keywords-board.spec.ts` ✨2026-08-16 | 关键词看板：快捷操作打开对话框与成功后精准刷新 |

### 组件内嵌测试 `frontend/src/components/torrents/__tests__/`（7 个 spec，2637 行）

| 测试文件 | 行数 | 覆盖组件 |
|---------|------|---------|
| `AdvancedMultiSelect.performance.spec.ts` | 466 | `AdvancedMultiSelect.vue`（性能测试） |
| `AdvancedMultiSelect.spec.ts` | 578 | `AdvancedMultiSelect.vue`（含 v1.0.6.29 紧凑触发器、v1.0.6.30/31 清空按钮与点击响应回归） |
| `AdvancedSearchBuilder.spec.ts` | 686 | `AdvancedSearchBuilder.vue`（按钮/组间层级、字段操作符过滤、下载器稳定 ID、超级做种三态与空值选项） |
| `AdvancedSearchWorkspace.spec.ts` | 389 | `AdvancedSearchWorkspace.vue`（高级配置列表/回填/创建/覆盖更新/删除与权限、单次重置和异步竞态隔离） |
| `ConditionValueInput.spec.ts` | 245 | `ConditionValueInput.vue`（状态/下载器不可创建多选、空值无需输入、超级做种三态） |
| `FilterGroup.spec.ts` | 97 | `FilterGroup.vue` |
| `QuickDeleteDuplicatesDialog.spec.ts` | 176 | `QuickDeleteDuplicatesDialog.vue` |

### 其他组件内嵌测试

| 测试文件 | 行数 | 覆盖组件/模块 |
|---------|------|---------|
| `components/common/__tests__/AppLogo.spec.ts` | 16 | `AppLogo.vue` 的 full/mark/micro 与 brand/inverse 资源选择 |
| `components/common/__tests__/LucideIcon.spec.ts` | 185 | `LucideIcon.vue`（含 v1.0.6.31 新增排序图标） |
| `components/BatchButton/__tests__/BatchButton.spec.ts` | 90 | `BatchButton.vue` |
| `constants/__tests__/status-config.spec.ts` | 102 | `constants/status-config.ts` |
| `views/torrents/utils/__tests__/traditionalStatusFilter.spec.ts` | 86 | `views/torrents/utils/traditionalStatusFilter.ts` |

---

## 覆盖薄弱点（建议优先补测试）

| 优先级 | 目标 | 原因 |
|--------|------|------|
| P1 | `app/api/endpoints/` 37 个端点（仅 1 个测试） | 端点是业务入口，集成测试严重不足 |
| P1 | `app/core/file_operations.py`（1474 行，回收站核心） | 0 直接测试 |
| P1 | `app/core/path_mapping.py`（932 行，10 处引用） | 0 直接测试 |
| P2 | `app/downloader/`（9 文件，仅 1 测试） | 含 2071 行 initialization.py |
| P2 | `app/services/tag_adapters/`（6 文件，仅 1 测试） | — |
| P2 | `app/repositories/`（3 文件，仅 1 测试） | — |

## 相关文档

- 测试组织总览 → [../tests/README.md](../tests/README.md)
