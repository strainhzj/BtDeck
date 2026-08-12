# tests — 测试

> 后端 pytest（141 个 test_*.py，按子目录组织；另有 conftest.py/__init__.py 等支持文件）+ 前端 Jest（43 个 test suite）。测试覆盖矩阵见 [../perspectives/test-coverage.md](../perspectives/test-coverage.md)。
> 定位方式：`Grep -i <功能词> docs/roadmap/tests/README.md`，命中行即含测试入口 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件/目录 | 一句话职责 |
|--------|-----------|-----------|
| 全局 fixture conftest | `backend/tests/conftest.py` | pytest 全局 fixture（DB session、测试客户端、种子数据等） |
| 架构约束测试 arch-constraint | `backend/tests/test_architecture_constraints.py` | 架构约束测试（防退化，自动检测反模式） |
| panic 验证 panic | `backend/tests/panic_fixes_verification.py` | panic 修复验证脚本 |
| API 层测试 api | `backend/tests/api/` | API 层测试（48 个 test_*.py，对应 app/api/） |
| 认证测试 auth | `backend/tests/auth/` | 认证测试（对应 app/auth/） |
| 基础设施测试 core | `backend/tests/core/` | 基础设施测试（对应 app/core/） |
| 下载器测试 downloader | `backend/tests/downloader/` | 下载器测试（对应 app/downloader/） |
| 端点集成测试 endpoints | `backend/tests/endpoints/` | 端点集成测试（对应 app/api/endpoints/） |
| 枚举测试 enums | `backend/tests/enums/` | 枚举测试（对应 app/enums/） |
| 模型测试 models | `backend/tests/models/` | ORM 模型测试（对应 app/models/） |
| 仓储测试 repositories | `backend/tests/repositories/` | 仓储测试（对应 app/repositories/） |
| 服务层测试 services | `backend/tests/services/` | 服务层测试（对应 app/services/，含 tag_adapters/） |
| 定时任务测试 tasks | `backend/tests/tasks/` | 定时任务测试（对应 app/tasks/） |
| 工具测试 utils | `backend/tests/utils/` | 工具测试（对应 app/utils/） |
| 前端 jest 测试 jest | `frontend/tests/unit/` | 32 个 Jest 单元测试（新增文件管理 nickname/UI 与种子错误原因展示契约） |
| 组件内嵌测试 component-test | `frontend/src/components/torrents/__tests__/` + `components/common/__tests__/` | 搜索/多选/已保存高级搜索组件单测（7 spec 共 2584 行）+ LucideIcon.spec.ts（185 行） |

## backend/tests/（141 个 test_*.py + 支持文件）

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

### 组件内嵌测试

部分组件有内嵌 `__tests__/`：
- `frontend/src/components/torrents/__tests__/`（7 个 spec，2584 行）
  - `AdvancedMultiSelect.performance.spec.ts`（466 行，性能测试）
  - `AdvancedMultiSelect.spec.ts`（571 行）
  - `AdvancedSearchBuilder.spec.ts`（685 行）
  - `AdvancedSearchWorkspace.spec.ts`（389 行）
  - `ConditionValueInput.spec.ts`（200 行）
  - `FilterGroup.spec.ts`（97 行）
  - `QuickDeleteDuplicatesDialog.spec.ts`（176 行）
- `frontend/src/components/common/__tests__/` ✨v1.0.6.28
  - `LucideIcon.spec.ts`（185 行）

### 运行命令

```bash
cd frontend && npm run test:unit    # jest
```

---

## 测试覆盖观察

- **后端测试组织良好**：159 个 .py（其中 141 个 test_*.py）按源码分支镜像组织（api/auth/core/downloader/endpoints/...），与路线图分支划分一致
- **路径映射验证防退化**：`tests/api/test_path_mapping_validation.py` 覆盖 Transmission、qBittorrent、缓存不可用、外部路径缺失与多映射整体失败
- **v1.0.6.25~28 测试加固**：ratio 迁移与高级搜索是本次新增覆盖的重点 —— `test_ratio_data_diagnostics.py` / `test_torrent_ratio_values.py` / `test_advanced_search_regression.py`（1770 行）/ `test_advanced_search_models_strict.py` / `test_sqlite_search_runtime.py` / `test_advanced_search_pagination.py` / `test_torrent_metadata.py`
- **前端契约守卫测试**：`operator-contract.spec.ts`（v1.0.6.26，前后端操作符契约一致性）+ `field-types-consistency.spec.ts`（字段类型一致性）是本次新增的防退化机制
- **2026-08-12 回归**：`test_transmission_error_sync.py` 覆盖错误文本持久化、恢复清空、新旧 RPC 与 legacy/async 状态写库，`test_tracker_migration.py` 覆盖手动 Tracker 新增/修改，`test_torrent_tracker_status_judge.py` 覆盖真实 SQLite 批量判定，`test_torrent_backup_review.py` 覆盖 nickname 单查询批量解析；前端文件管理/错误原因契约与 Builder 多条件组、状态中性边界共同防退化
- **前端测试集中在核心组件**：`components/torrents/` 的搜索/多选组件有完整单测（含性能测试），其他组件测试覆盖较薄
- **孤儿文件回归**：`test_orphan_hardlink_detection.py` 覆盖 `st_nlink - 1`、多 inode 单轮路径定位/重复 ID 去重、范围外未定位数、扫描失败降级与清理删除诊断；`test_orphan_files_api.py` 守卫 1~5000 项请求边界；`orphan-files.spec.ts` 覆盖数量链接、文件夹批量查询、位置弹框、复制路径、过期响应隔离及异常提示；任务/查询状态测试继续覆盖重复提交、混合跳过与终态释放
- **架构约束测试**：`test_architecture_constraints.py` 是防退化机制（自动检测反模式）
- 详细覆盖矩阵（源文件 ↔ 测试文件对应）见 [../perspectives/test-coverage.md](../perspectives/test-coverage.md)

## 第三层详情

- 测试分支通常不需要第三层方法签名详情；如需要，可对 `conftest.py`（fixture 体系）做专项分析。
