# test-coverage — 测试覆盖矩阵

> 源文件 ↔ 测试文件覆盖矩阵（按子目录组织）。仅统计文件级对应，不评估覆盖率百分比。

## 后端测试分布（共 96 个 test_*.py）

| 测试目录 | test 文件数 | 对应源码分支 | 覆盖评估 |
|---------|------------|-------------|---------|
| `tests/api/` | 34 | `app/api/` | ✅ 覆盖良好（34 文件对 41 源文件） |
| `tests/services/` | 20 | `app/services/` | 🟡 部分覆盖（20 对 45，集中在 orphan/advanced_search/reannounce） |
| `tests/tasks/` | 12 | `app/tasks/` | 🟡 部分覆盖（12 对 32） |
| `tests/core/` | 11 | `app/core/` | 🟡 部分覆盖（11 对 20，集中在 db_governance/migration/tracker_mapper） |
| `tests/models/` | 6 | `app/models/` | 🟡 部分覆盖（6 对 16） |
| `tests/utils/` | 3 | `app/utils/` | ✅ 全覆盖（3 对 3） |
| `tests/auth/` | 3 | `app/auth/` | ✅ 覆盖良好（3 对 5） |
| `tests/enums/` | 2 | `app/enums/` | ✅ 全覆盖（2 对 2） |
| `tests/downloader/` | 1 | `app/downloader/` | ⚠ 薄弱（1 对 9） |
| `tests/endpoints/` | 1 | `app/api/endpoints/` | ⚠ 薄弱（1 对 35，仅 `test_active_only_filter.py`） |
| `tests/repositories/` | 1 | `app/repositories/` | ⚠ 薄弱（1 对 3） |
| `tests/services/tag_adapters/` | 1 | `app/services/tag_adapters/` | ⚠ 薄弱（1 对 6，仅 `test_tag_adapter_factory.py`） |
| `tests/` 顶层 | 1 | 全局 | `test_architecture_constraints.py`（架构约束防退化） |

> 合计：34+20+12+11+6+3+3+2+1+1+1+1+1 = **96** 个 test_*.py（外加 conftest.py / __init__.py / panic_fixes_verification.py 等 16 个支持文件，全 .py 共 112）。

> 注：`tests/api/`（34 文件）主要覆盖 `app/api/` 顶层与 schemas，与 `tests/endpoints/`（1 文件，覆盖 `app/api/endpoints/` 35 个端点）分工。端点集成测试是明显薄弱点。

### 关键源文件测试覆盖抽样

| 源文件 | 测试文件 | 状态 |
|--------|---------|------|
| `app/api/endpoints/torrent_crud.py` | （无直接测试，仅 `test_active_only_filter.py` 间接覆盖 getList 的 active_only） | ⚠ 未直接覆盖 |
| `app/services/advanced_search.py` | `test_advanced_search.py` + `test_advanced_search_batching.py` | ✅ |
| `app/services/orphan_scanner.py` | `test_orphan_scanner.py` | ✅ |
| `app/services/reannounce_service.py` | `test_reannounce_service.py` + `test_reannounce_config.py` | ✅ |
| `app/core/database_result.py` | `test_database_result.py` | ✅ |
| `app/core/migration.py` | `test_db_migration.py` + `test_db_rollback_scenarios.py` | ✅ |
| `app/core/path_mapping.py` | （未发现直接测试） | ⚠ 未覆盖 |
| `app/core/file_operations.py`（1474 行） | （未发现直接测试） | ⚠ 未覆盖 |

## 前端测试分布

### `frontend/tests/unit/`（14 个 spec）

| 测试文件 | 覆盖范围 |
|---------|---------|
| `api-contracts.spec.ts` | API 契约一致性 |
| `downloader-settings.spec.ts` | 下载器设置 store |
| `error-normalize.spec.ts` | `utils/error-normalize.ts` |
| `filter-group-accessibility.spec.ts` | FilterGroup 可访问性 |
| `lint-vuex-action.spec.ts` | Vuex action 规范 |
| `management-pages-ui.spec.ts` | 管理页面 UI |
| `shared-utils.spec.ts` | 共享工具 |
| `store-modules.spec.ts` | Vuex modules |
| `torrent-batch.spec.ts` | `views/torrents/utils/torrentBatch.ts` |
| `traditional-torrent-identity.spec.ts` | `views/torrents/utils/traditionalTorrentIdentity.ts` |
| `traditional-view-component.spec.ts` | 传统视图组件 |
| `traditional-view-pagination.spec.ts` | `views/torrents/utils/traditionalPagination.ts` |
| `traditional-view-status-filter.spec.ts` | `views/torrents/utils/traditionalStatusFilter.ts` |
| `traditional-view-virtual-list.spec.ts` | `views/torrents/utils/traditionalVirtualList.ts` |

### 组件内嵌测试 `frontend/src/components/torrents/__tests__/`（4 个 spec，1484 行）

| 测试文件 | 行数 | 覆盖组件 |
|---------|------|---------|
| `AdvancedMultiSelect.performance.spec.ts` | 466 | `AdvancedMultiSelect.vue`（性能测试） |
| `AdvancedMultiSelect.spec.ts` | 348 | `AdvancedMultiSelect.vue` |
| `AdvancedSearchBuilder.spec.ts` | 506 | `AdvancedSearchBuilder.vue` |
| `ConditionValueInput.spec.ts` | 164 | `ConditionValueInput.vue` |

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
