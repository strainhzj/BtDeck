# tests — 测试

> 后端 pytest（147 个 test_*.py，按子目录组织；另有 conftest.py/__init__.py 等支持文件）+ 前端 Jest（44 个 spec）。测试覆盖矩阵见 [../perspectives/test-coverage.md](../perspectives/test-coverage.md)。
> 定位方式：`Grep -i <功能词> docs/roadmap/tests/README.md`，命中行即含测试入口 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件/目录 | 一句话职责 |
|--------|-----------|-----------|
| 全局 fixture conftest | `backend/tests/conftest.py` | pytest 全局 fixture（DB session、测试客户端、种子数据等） |
| 架构约束测试 arch-constraint | `backend/tests/test_architecture_constraints.py` | 架构约束测试（防退化，自动检测反模式） |
| panic 验证 panic | `backend/tests/panic_fixes_verification.py` | panic 修复验证脚本 |
| API 层测试 api | `backend/tests/api/` | API 层测试（49 个 test_*.py，对应 app/api/；同内容列表筛选、组合条件、活动删除/活动快照、稳定行级分页、大页关联预取及旧端点移除回归） |
| 认证测试 auth | `backend/tests/auth/` | 认证测试（对应 app/auth/） |
| 基础设施测试 core | `backend/tests/core/` | 基础设施测试（对应 app/core/） |
| 下载器测试 downloader | `backend/tests/downloader/` | 下载器测试（对应 app/downloader/） |
| 端点集成测试 endpoints | `backend/tests/endpoints/` | 端点集成测试（对应 app/api/endpoints/） |
| 枚举测试 enums | `backend/tests/enums/` | 枚举测试（对应 app/enums/） |
| 模型测试 models | `backend/tests/models/` | ORM 模型测试（对应 app/models/） |
| 仓储测试 repositories | `backend/tests/repositories/` | 仓储测试（对应 app/repositories/） |
| 服务层测试 services | `backend/tests/services/` | 服务层测试（42 个，含孤儿后台扫描调度器与 tag_adapters） |
| 跨层争用测试 integration | `backend/tests/integration/` | 4 个真实文件 SQLite 回归；含 120100 条孤儿生命周期争用与状态接口延迟 |
| 定时任务测试 tasks | `backend/tests/tasks/` | 定时任务测试（对应 app/tasks/） |
| 工具测试 utils | `backend/tests/utils/` | 工具测试（对应 app/utils/） |
| 前端 jest 测试 jest | `frontend/tests/unit/` | 33 个 Jest 单元测试（同内容排查由两视图组件及跨视图状态用例覆盖；TrackerDetailCard 运行时契约单独覆盖） |
| 组件内嵌测试 component-test | `frontend/src/components/torrents/__tests__/` + `components/common/__tests__/` | 搜索/多选/已保存高级搜索组件单测（7 spec 共 2263 行）+ LucideIcon.spec.ts（185 行） |

## backend/tests/（147 个 test_*.py + 支持文件）

### 顶层

| 文件 | 用途 |
|------|------|
| `__init__.py` | 包标识 |
| `conftest.py` | pytest 全局 fixture（DB session、测试客户端、种子数据等） |
| `panic_fixes_verification.py` | panic 修复验证脚本 |
| `test_architecture_constraints.py` | 架构约束测试（如禁止某些反模式） |

### 子目录（按源码分支镜像）

| 子目录 | 对应源码分支 | 说明 |
|--------|-------------|------|
| `api/` | `app/api/` | API 层测试 |
| `auth/` | `app/auth/` | 认证测试 |
| `core/` | `app/core/` | 基础设施测试 |
| `downloader/` | `app/downloader/` | 下载器测试 |
| `endpoints/` | `app/api/endpoints/` | 端点集成测试 |
| `enums/` | `app/enums/` | 枚举测试 |
| `models/` | `app/models/` | ORM 模型测试 |
| `repositories/` | `app/repositories/` | 仓储测试 |
| `services/` | `app/services/` | 服务层测试 |
| `services/tag_adapters/` | `app/services/tag_adapters/` | 标签适配器测试 |
| `tasks/` | `app/tasks/` | 定时任务测试 |
| `utils/` | `app/utils/` | 工具测试 |

### 运行命令

```bash
cd backend && pytest                          # 全量
cd backend && pytest tests/services/ -v       # 按目录
cd backend && pytest tests/api/               # API 层（48 个 test_*.py）
```

## frontend/tests/

| 子目录 | 说明 |
|--------|------|
| `unit/` | jest 单元测试 |

- `deployment-recovery.spec.ts`：覆盖部署后 JS/CSS chunk 错误识别、一次恢复、防刷新循环、历史 Workbox 清退和 nginx 缓存契约。
- `file-management-contract.spec.ts`：覆盖备份列表当前 nickname、单次列表加载与 management-page 筛选区契约。
- `torrent-error-reason-ui.spec.ts`：覆盖两种种子视图名称 tooltip 与 Tracker 卡片错误原因展示。
- `torrent-list-view-component.spec.ts` / `traditional-view-component.spec.ts`：覆盖 Tracker 主域名选项加载、多选参数转换、错误单种快捷入口发送 `single_error_only`、同内容快捷入口发送 `same_content_only`，筛选、排序、分页大小、翻页与刷新持续复用列表查询，以及重复查询/高级搜索/模板切换和显式退出清理模式；静态契约锁定列表/传统父模板均调用同一个 `TrackerDetailCard.vue` 并分别传入 `list`/`traditional` layout，锁定共享组件的完整弹框骨架、列结构、状态语义和 `_tracker-table.scss` 视觉样式；`torrent-view-switcher.spec.ts` 守卫跨视图保留错误单种模式。
- `tracker-detail-card.spec.ts`：运行时验证列表/传统视图共用的 TrackerDetailCard 完整弹框骨架（标题、关闭按钮、页签、内容区）、五列结构、snake/camel 字段兼容、错误提示、中性状态、单条汇报事件和 loading 状态。

### 组件内嵌测试

部分组件有内嵌 `__tests__/`：
- `frontend/src/components/torrents/__tests__/`（7 个 spec，2612 行）
  - `AdvancedMultiSelect.performance.spec.ts`（466 行，性能测试）
  - `AdvancedMultiSelect.spec.ts`（571 行）
  - `AdvancedSearchBuilder.spec.ts`（684 行）
  - `AdvancedSearchWorkspace.spec.ts`（389 行）
  - `ConditionValueInput.spec.ts`（243 行）
  - `FilterGroup.spec.ts`（89 行）
  - `QuickDeleteDuplicatesDialog.spec.ts`（170 行）
- `frontend/src/components/common/__tests__/` ✨v1.0.6.28
  - `LucideIcon.spec.ts`（185 行）

### 运行命令

```bash
cd frontend && npm run test:unit    # jest
```

---

## 测试覆盖观察

- **后端测试组织良好**：当前实测 147 个 test_*.py，按源码分支镜像组织（api/auth/core/downloader/endpoints/integration/...），与路线图分支划分一致
- **路径映射验证防退化**：`tests/api/test_path_mapping_validation.py` 覆盖 Transmission、qBittorrent、缓存不可用、外部路径缺失与多映射整体失败
- **v1.0.6.25~28 测试加固**：ratio 迁移与高级搜索是重点 —— `test_ratio_data_diagnostics.py` / `test_torrent_ratio_values.py` / `test_advanced_search_regression.py`（2130 行）/ `test_advanced_search_models_strict.py`（161 行）/ `test_sqlite_search_runtime.py` / `test_advanced_search_pagination.py` / `test_torrent_metadata.py`
- **前端契约守卫测试**：`operator-contract.spec.ts`（338 行，前后端操作符契约一致性）+ `field-types-consistency.spec.ts`（字段类型一致性）是本次新增的防退化机制
- **2026-08-13 最新提交回归**：新增 `test_tracker_status_policy.py` 的 30 个纯函数契约用例，直接守卫 `625c1e3d` 新增的 Working 空消息证据、非空消息优先、announce/scrape 双消息、精确/部分匹配、未知保留与失败聚合；并复跑 `test_tracker_status_sync.py`、`test_torrent_tracker_status_judge.py` 的 115 个既有集成回归。
- **2026-08-12 回归**：除错误原因/Tracker 状态/nickname 用例外，`test_advanced_search_regression.py` + 严格模型测试覆盖 Tracker 多行否定/软删除、SQL 通配符字面量、逗号/分号标签 token、回收站排除、下载器改名、超级做种三态、空值白名单；新增跨字段 include/exclude 全集分区与五个空值字段分区矩阵。`test_torrent_tracker_status_judge.py` 以 36 组 zimiao 双 Tracker 顺序/下载器类型/空消息矩阵守卫种子级 Working 恢复；`test_tracker_status_sync.py` 再覆盖行级 Working 空消息清理、未知逐行保留、announce/scrape 状态边界与双消息、幂等、跨种子 host 隔离及最新 zimiao 359 行快照形态；`test_sync_coordinator.py` 锁定原始 Tracker 同步成功后才运行行级判断。迁移测试覆盖重复升级、自定义计划/描述、逻辑删除及 downgrade 精确保护；前端契约和模板请求转换逐字段守卫正操作符 + `mode=exclude`。
- **2026-08-14 迁移恢复回归**：`test_orphan_migration_production_shape.py` 使用真实文件 SQLite/WAL 和重复扫描明细验证残留 batch 临时表恢复、canonical_path 索引回填及超量清理门禁；`test_startup_migration_guard.py` 保证迁移失败不会继续 seed、孤儿对账或调度器启动。
- **前端测试集中在核心组件**：`components/torrents/` 的搜索/多选组件有完整单测（含性能测试），其他组件测试覆盖较薄
- **孤儿文件回归**：`test_orphan_hardlink_detection.py` 覆盖 `st_nlink - 1`、多 inode 单轮路径定位/重复 ID 去重、不可访问目录未定位数、扫描失败降级与清理删除诊断；2026-08-15 起位置定位改为 `collect_runtime_accessible_roots` 整体收集运行环境可访问同文件系统根（覆盖映射目录外副本）；`test_orphan_files_api.py` 守卫 1~5000 项请求边界；`orphan-files.spec.ts`（当前定向 81 项）覆盖数量链接、文件夹批量查询、位置弹框、复制路径、过期响应隔离及异常提示，并额外守卫扁平/文件夹模式展开列动态切换、普通文件行展开标记与懒加载事件、子表隐藏表头但保留可见数据/选择事件；任务/查询状态测试继续覆盖重复提交、混合跳过与终态释放
- **种子备份补偿回归（2026-08-15）**：`test_torrent_file_backup_reconcile.py` 守卫 info/full 同步后 `reconcile_missing_backups` 的限量批次、幂等收敛、qB 纯 hash 与 Transmission `name.hash.torrent` 源文件名、逻辑删除墓碑不自动重建及源目录不可用一次性上报；`test_db_migration.py` 新增 `b6e1c4d9a2f7` UUID 类型升级/降级用例（含不可无损转换数据时 downgrade 拒绝回滚）；`torrent-list-view-component.spec.ts` 守卫种子页三个筛选下拉提示语
- **架构约束测试**：`test_architecture_constraints.py` 是防退化机制（自动检测反模式）
- 详细覆盖矩阵（源文件 ↔ 测试文件对应）见 [../perspectives/test-coverage.md](../perspectives/test-coverage.md)

## 第三层详情

- 测试分支通常不需要第三层方法签名详情；如需要，可对 `conftest.py`（fixture 体系）做专项分析。
