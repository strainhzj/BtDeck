# test-coverage — 测试覆盖矩阵

> 源文件 ↔ 测试文件覆盖矩阵（按子目录组织）。仅统计文件级对应，不评估覆盖率百分比。

## 后端测试分布（共 141 个 test_*.py）

| 测试目录 | test 文件数 | 对应源码分支 | 覆盖评估 |
|---------|------------|-------------|---------|
| `tests/api/` | 48 | `app/api/` | ✅ 覆盖良好；异步删除、孤儿任务与重复查询筛选/排序/活动快照均有 API 回归 |
| `tests/services/` | 40 | `app/services/` | 🟡 中等；新增删除任务占用、孤儿持久化占用与查询状态回归（不含下方 tag_adapters 子目录） |
| `tests/tasks/` | 13 | `app/tasks/` | 🟡 部分覆盖（13 对 32） |
| `tests/core/` | 16 | `app/core/` | 🟡 中等 |
| `tests/models/` | 6 | `app/models/` | 🟡 部分覆盖（6 对 16） |
| `tests/utils/` | 4 | `app/utils/` | ✅ 覆盖良好 |
| `tests/auth/` | 3 | `app/auth/` | ✅ 覆盖良好（3 对 5） |
| `tests/enums/` | 2 | `app/enums/` | ✅ 全覆盖（2 对 2） |
| `tests/downloader/` | 1 | `app/downloader/` | ⚠ 薄弱（1 对 9） |
| `tests/endpoints/` | 1 | `app/api/endpoints/` | ⚠ 薄弱（1 对 35，仅 `test_active_only_filter.py`） |
| `tests/architecture/` | 1 | 全局架构 | 架构约束防退化 |
| `tests/integration/` | 3 | 跨层链路 | SQLite 同步争用与 API 响应性 |
| `tests/repositories/` | 1 | `app/repositories/` | ⚠ 薄弱（1 对 3） |
| `tests/services/tag_adapters/` | 1 | `app/services/tag_adapters/` | ⚠ 薄弱（1 对 6，仅 `test_tag_adapter_factory.py`） |
| `tests/` 顶层 | 1 | 全局 | `test_architecture_constraints.py`（架构约束防退化） |

> 合计：当前实测 **141** 个 test_*.py；支持文件计入后全 `.py` 共 159 个。

> 注：`tests/api/`（48 文件）覆盖 `app/api/` 顶层、schemas 与部分端点集成行为；`tests/endpoints/` 另有 1 文件。

### v1.0.6.25~32 新增后端测试

| 新增测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/core/test_ratio_data_diagnostics.py` | 158 | `app/core/ratio_data_diagnostics.py` |
| `tests/services/test_torrent_ratio_values.py` | 179 | `app/services/torrent_ratio_values.py` |
| `tests/services/test_advanced_search_regression.py` | 1770 | `app/services/advanced_search.py`（完备回归，含 tracker URL + `error`/`has_tracker_error` 组合条件及 basic/eq/ne/in/not_in 真值表） |
| `tests/services/test_advanced_search_models_strict.py` | 128 | `app/api/models/advanced_search.py`（Pydantic 严格模式） |
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
| `tests/services/test_orphan_purge_job_service.py` | 387 | 孤儿清理/彻底删除持久化占用、混合跳过与并发提交 |
| `tests/services/test_orphan_query_state.py` | 339 | 活动任务隐藏，失败终态后重新可见 |
| `tests/api/test_duplicate_quick_delete_api.py` | 322 | 快捷删除重复提交与混合接受 |

### 2026-08-12 种子文件、错误原因与搜索交互回归

| 测试文件 | 行数 | 覆盖源文件 |
|------------|------|-----------|
| `tests/api/test_transmission_error_sync.py` | 394 | Transmission 错误状态/原因提取、FULL/INFO-ONLY 持久化、原因变化检测、恢复清空、旧 RPC 兼容及 legacy/async Tracker 0–4 状态写入 |
| `tests/api/test_tracker_migration.py` | 730 | qB/Transmission Tracker 手动新增、修改、删除路径；Transmission announce/scrape 独立状态码持久化 |
| `tests/tasks/test_torrent_tracker_status_judge.py` | 207 | qB/Transmission 未联系/发送中为中性，明确失败与混合未知聚合，以及真实 SQLite 批量更新 |
| `tests/api/test_torrent_backup_review.py` | 188 | 备份列表当前下载器 nickname 单查询批量解析及序列化 |
| `tests/api/test_torrents_async_info_budget.py` | 626 | INFO-ONLY 请求 `errorString` 并批量写入 `error_reason` |
| `tests/models/test_torrent_models.py` | 348 | `TorrentInfo.error_reason` 字段全集与值映射 |

### 关键源文件测试覆盖抽样

| 源文件 | 测试文件 | 状态 |
|--------|---------|------|
| `app/api/endpoints/torrent_crud.py` | （无直接测试，仅 `test_active_only_filter.py` 间接覆盖 getList 的 active_only） | ⚠ 未直接覆盖 |
| `app/api/endpoints/duplicate_torrents.py` | `tests/api/test_duplicate_torrents_api.py`（1439 行，40 用例） | ✅ 默认添加时间倒序、安全列排序、非法排序拒绝、完整重复组筛选、活动快照/空快照、分页与元数据回填 |
| `app/api/endpoints/torrent_backup.py` | `tests/api/test_torrent_backup_review.py`（188 行） | ✅ 当前 nickname 批量查询、空列表跳过查询与序列化 |
| `app/api/endpoints/torrents_async.py` / `torrent_sync.py` / `torrent_helpers.py` | `test_transmission_error_sync.py` + `test_torrents_async_info_budget.py` + `test_torrent_list_api.py` | ✅ Transmission 错误原因全链路、恢复清空、Tracker 状态归一与 camelCase 响应 |
| `app/core/torrent_status_mapper.py` | `tests/core/test_torrent_status_mapper.py` + `tests/api/test_transmission_error_sync.py` | ✅ 状态判定与安全错误文本提取 |
| `app/services/advanced_search.py` | `test_advanced_search.py` + `test_advanced_search_regression.py`（1770 行）+ `test_advanced_search_models_strict.py` | ✅✅ 重度覆盖（含活动删除排除、basic/eq/ne/in/not_in 与普通列表一致的 `error` 语义） |
| `app/tasks/scheduler/torrent_tracker_status_judge.py` | `test_torrent_tracker_status_judge.py` + `test_heavy_task_db_write_governance.py` | ✅ 未联系/发送中中性语义、明确失败/未知聚合与批量查询治理 |
| `app/services/deletion_task_manager.py` | `test_deletion_task_manager.py` + 删除 API/快捷删除 API 测试 | ✅ 原子占用、终态释放、大集合排除 |
| `app/services/orphan_purge_job_service.py` / `orphan_file_service.py` / `orphan_quarantine.py` | `test_orphan_purge_job_service.py` + `test_orphan_query_state.py` + `test_orphan_hardlink_detection.py` + `test_orphan_files_api.py` | ✅ 持久化占用、查询可见性与硬链接副本计数/位置回归 |
| `app/services/torrent_ratio_values.py` | `test_torrent_ratio_values.py` | ✅（v1.0.6.25 新增） |
| `app/services/sqlite_search_runtime.py` | `test_sqlite_search_runtime.py` | ✅（v1.0.6.27 新增） |
| `app/services/path_mapping_validation.py` | `test_path_mapping_validation.py` | ✅（v1.0.6.32 新增，10 个用例） |
| `app/core/ratio_data_diagnostics.py` | `test_ratio_data_diagnostics.py` | ✅（v1.0.6.27 新增） |
| `app/services/orphan_scanner.py` | `test_orphan_scanner.py` | ✅ |
| `app/services/reannounce_service.py` | `test_reannounce_service.py` + `test_reannounce_config.py` | ✅ |
| `app/core/database_result.py` | `test_database_result.py` | ✅ |
| `app/core/migration.py` | `test_db_migration.py` + `test_db_rollback_scenarios.py` | ✅（v1.0.6.27 扩展 ratio 迁移用例） |
| `app/core/path_mapping.py` | （未发现直接测试） | ⚠ 未覆盖 |
| `app/core/file_operations.py`（1474 行） | （未发现直接测试） | ⚠ 未覆盖 |

## 前端测试分布

### `frontend/tests/unit/`（32 个 spec）

| 测试文件 | 覆盖范围 |
|---------|---------|
| `api-contracts.spec.ts` | API 契约一致性 |
| `clipboard.spec.ts` ✨v1.0.6.36 | `utils/clipboard.ts`（剪贴板复制回退：Clipboard API / execCommand 降级） |
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
| `operator-contract.spec.ts` ✨v1.0.6.26 | 高级搜索操作符前后端契约守卫（与 `app/contracts/advanced_search_contract.json` 镜像） |
| `orphan-files.spec.ts` | 孤儿清理/彻底删除工作流；硬链接副本数量链接、批量位置弹框、复制、过期响应隔离与异常提示 |
| `page-size-combobox.spec.ts` ✨v1.0.6.30 | 共享 `PageSizeCombobox`：默认预设、受控输入、公共事件、ARIA 展开态与 `focusInput()` |
| `shared-utils.spec.ts` | 共享工具 |
| `store-modules.spec.ts` | Vuex modules |
| `torrent-batch.spec.ts` | `views/torrents/utils/torrentBatch.ts`（含“未联系”中性样式） |
| `torrent-error-reason-ui.spec.ts` ✨2026-08-12 | `torrents/index.vue` + `TraditionalView.vue`：名称 tooltip 与 Tracker 卡片错误原因 |
| `quick-delete-duplicates-dialog.spec.ts` | 重复种子快捷删除 nullable task_id、跳过提示与父列表刷新 |
| `tasks-sync-freshness.spec.ts` | 定时任务 outcome/stale helper 的模板实例可访问性与同步新鲜度展示契约 |
| `torrent-list-view-component.spec.ts` ✨v1.0.6.30 | 列表视图异步删除与分页/排序；重复查询开关在筛选、排序、切页和活动筛选期间保持 |
| `torrent-view-switcher.spec.ts` | 列表/传统模式往返时保留重复查询开关、查询条件、分页和选择状态 |
| `traditional-torrent-identity.spec.ts` | `views/torrents/utils/traditionalTorrentIdentity.ts` |
| `traditional-view-component.spec.ts` | 传统视图组件；重复查询保持分类/标签/活动筛选、排序、分页大小与刷新数据源 |
| `traditional-view-pagination.spec.ts` | `views/torrents/utils/traditionalPagination.ts` |
| `traditional-view-status-filter.spec.ts` | `views/torrents/utils/traditionalStatusFilter.ts` |
| `traditional-view-virtual-list.spec.ts` | `views/torrents/utils/traditionalVirtualList.ts` |

### 组件内嵌测试 `frontend/src/components/torrents/__tests__/`（7 个 spec，2584 行）

| 测试文件 | 行数 | 覆盖组件 |
|---------|------|---------|
| `AdvancedMultiSelect.performance.spec.ts` | 466 | `AdvancedMultiSelect.vue`（性能测试） |
| `AdvancedMultiSelect.spec.ts` | 571 | `AdvancedMultiSelect.vue`（含 v1.0.6.29 紧凑触发器、v1.0.6.30/31 清空按钮与点击响应回归） |
| `AdvancedSearchBuilder.spec.ts` | 685 | `AdvancedSearchBuilder.vue`（添加条件居中/主次配色、组间 AND/OR 位于卡片外、三组顺序及删除收敛守卫） |
| `AdvancedSearchWorkspace.spec.ts` | 389 | `AdvancedSearchWorkspace.vue`（高级配置列表/回填/创建/覆盖更新/删除与权限、单次重置和异步竞态隔离） |
| `ConditionValueInput.spec.ts` | 200 | `ConditionValueInput.vue`（状态与下载器共用不可创建的 AdvancedMultiSelect） |
| `FilterGroup.spec.ts` | 97 | `FilterGroup.vue` |
| `QuickDeleteDuplicatesDialog.spec.ts` | 176 | `QuickDeleteDuplicatesDialog.vue` |

### 组件内嵌测试 `frontend/src/components/common/__tests__/`（1 个 spec，v1.0.6.28）

| 测试文件 | 行数 | 覆盖组件 |
|---------|------|---------|
| `LucideIcon.spec.ts` | 185 | `LucideIcon.vue`（含 v1.0.6.31 新增排序图标） |

---

## 覆盖薄弱点（建议优先补测试）

| 优先级 | 目标 | 原因 |
|--------|------|------|
| P1 | `app/api/endpoints/` 35 个端点（仅 1 个测试） | 端点是业务入口，集成测试严重不足 |
| P1 | `app/core/file_operations.py`（1474 行，回收站核心） | 0 直接测试 |
| P1 | `app/core/path_mapping.py`（898 行，10 处引用） | 0 直接测试 |
| P2 | `app/downloader/`（9 文件，仅 1 测试） | 含 1999 行 initialization.py |
| P2 | `app/services/tag_adapters/`（6 文件，仅 1 测试） | — |
| P2 | `app/repositories/`（3 文件，仅 1 测试） | — |

## 相关文档

- 测试组织总览 → [../tests/README.md](../tests/README.md)
