# BtDeck 代码路线图

> BtDeck —— 统一管理多种 BitTorrent 客户端（qBittorrent / Transmission）的全栈 Web 应用（FastAPI + Vue 2 + TypeScript）。
> 本路线图是对**源码结构的有证据索引**，按"由粗到细"分三层渐进式披露，用于快速定位模块职责、调用关系与架构约定。

---

## 模块路由

```
BtDeck/
├── backend/          ← FastAPI 后端（Python 3.11+）
│   ├── app-root/        包根入口（main/factory/database/exception_handlers …）
│   ├── api/             HTTP 路由层（37 endpoints + schemas + models + responseVO）
│   ├── services/        业务服务层 + 下载器/标签适配器（含 ratio/search 运行时、异步删除条目占用与查询排除）
│   ├── core/            基础设施（config / path_mapping / file_ops …）+ ⚠ 含 4 个孤儿文件（torrent_operations 已重写为 ratio 工具但仍 0 引用）
│   ├── contracts/ ✨    前后端共享机器可读契约（v1.0.6.27 新增：advanced_search JSON + 加载器）
│   ├── data-models/     ORM 模型 + repositories + schemas + 枚举 + 默认数据
│   ├── tasks/           定时任务 + scheduler + 后台任务
│   ├── domain/          领域目录（downloader / torrents / tracker / auth / user）
│   └── infra/           utils + startup + migrations + alembic（18 个 revision，最新增加种子错误原因列）
├── frontend/         ← Vue 2.6 + TypeScript 前端
│   ├── entry/           应用入口（main.ts / router.ts / permission.ts / App.vue）
│   ├── api/             axios API 封装（13 个领域模块）
│   ├── views/           页面视图（13 个 view 模块，Options API + class-component 并存）
│   ├── store/           Vuex（index.ts 空壳 + 5 个 getModule 自注册 module）
│   ├── components-layout/  通用组件（LucideIcon / PageSizeCombobox / AdvancedSearchWorkspace）+ 布局骨架
│   └── utils-types/     工具 / 类型 / 常量 / 指令（v1.0.6.36 新增 clipboard 剪贴板回退）
├── deploy/           ← 多部署模式（Docker / PyInstaller / Inno Setup / fpm；v1.0.6.28 Dockerfile 镜像源参数化）
├── tests/            ← 测试（backend pytest 141 个 test_*.py + frontend Jest 43 个 test suite）
└── perspectives/     ← 跨切专题（调用链 / 约定 / 风险 / 测试覆盖）
```

## 功能域速查（第一层直达）

> 按功能词直达源文件，无需逐层翻页。定位时先在 `docs/roadmap/` 下 `Grep -i <功能词>` 命中本表行，再读对应源文件（路径相对 `frontend/src` / `backend/app`）。

| 功能域（含检索词） | 前端入口 | 后端入口 |
|------|---------|---------|
| 孤儿文件管理 orphan | `views/orphan-files/index.vue`、`api/orphan-files.ts`（硬链接副本数量列，可点击查看位置） | `api/endpoints/orphan_files.py`；`services/orphan_file_service.py` / `orphan_scanner.py` / `orphan_quarantine.py` / `orphan_manifest.py` / `orphan_lease.py` / `orphan_lifecycle_service.py` / `orphan_notification.py` / `orphan_purge_job_service.py`（实时硬链接副本计数 + 配置目录内按需定位 + 清理/彻底删除活动项占用）；`models/orphan_file.py`；`tasks/scheduler/orphan_*_task.py` |
| 种子管理 torrent | `views/torrents/`（index.vue、TraditionalView.vue）、`api/torrents.ts` | `api/endpoints/torrent_crud.py` / `torrents.py` / `torrents_async.py` / `torrent_deletion.py` / `torrent_status.py` / `torrent_location.py` / `torrent_speed.py` / `torrent_sync.py`；Transmission 同步会持久化/清除错误原因，并把 Tracker announce/scrape 统计归一为 0–4 状态码，避免“已联系失败”误显示为“未联系”；列表名称 tooltip 与 Tracker 卡片展示 `errorReason`；同步统一走缓存下载器客户端、短事务与可续跑 cursor；`services/deletion_task_manager.py`（活动删除 ID 占用）/ `torrent_crud_service.py` / `torrent_batch_add_service.py` / `torrent_deletion_service.py` / `torrent_location_service.py` |
| 下载器管理 downloader | `views/downloader/`、`api/downloader.ts` | `api/endpoints/downloader*.py`；`services/downloader_adapters/` / `downloader_api_runtime.py` / `downloader_capabilities_manager.py` / `downloader_settings_manager.py` / `path_maintenance_service.py`；`models/downloader*.py` |
| Tracker 管理 tracker | `views/tracker/`、`api/tracker.ts` | `api/endpoints/tracker*.py`；`services/reannounce_service.py` |
| 任务/定时任务 task cron | `views/tasks/index.vue`、`api/tasks.ts`（outcome/stale 展示 helper 由实例方法暴露给模板；查看日志保留可见任务筛选，清空后立即恢复全部日志） | `api/endpoints/tasks.py` / `cron_tasks.py`；`tasks/`（scheduler） |
| 审计日志 audit | `views/logs/audit.vue`、`api/audit-logs.ts` | `api/endpoints/audit_logs.py`；`services/audit_service.py` / `audit_service_sync.py` |
| 回收站 recycle | `views/recycle-bin/index.vue`（搜索区复用孤儿文件管理页 UI）、`api/recycle-bin.ts` | `api/endpoints/recycle_bin.py`；`services/recycle_bin_service.py` |
| 通知中心 notification | `layout/components/NotificationDrawer/`、`api/notification.ts`、`store/modules/notification.ts` | `api/endpoints/notifications.py`；`services/notification_service.py`；`models/notification.py` |
| 查询模板 query-template | `views/query-templates/`（行操作为 Lucide 极简按钮） | `api/endpoints/advanced_search.py`；`services/advanced_search.py`；`models/search_template.py` |
| 标签管理 tag | 下载器页 TagManagementTab | `api/endpoints/tag_management.py`；`services/tag_service.py` / `tag_sync_service.py` / `tag_adapters/`；`models/torrent_tags.py` |
| 高级搜索 advanced-search | `components/torrents/AdvancedSearchWorkspace.vue`（左侧已保存搜索选择/创建/更新/删除）+ Builder（契约过滤操作符；下载器显示 nickname/提交稳定 ID；超级做种三态；包含/排除模式原样传输）+ 两种种子视图 | `api/endpoints/advanced_search.py`；`services/advanced_search.py`（20 字段；`error` 复用列表语义；Tracker 否定走 `NOT EXISTS`；文本字面匹配、标签完整 token、空值严格补集、回收站排除）/ `sqlite_search_runtime.py` |
| 种子转移 seed-transfer | — | `api/endpoints/seed_transfer.py`；`services/seed_transfer_service.py`；`models/seed_transfer_audit_log.py` |
| 重复种子 duplicate | `views/torrents/index.vue` / `TraditionalView.vue`（绿色查询开关，筛选/排序/分页期间保持）+ `components/torrents/QuickDeleteDuplicatesDialog.vue` | `api/endpoints/duplicate_torrents.py`（默认添加时间倒序、活动快照与侧栏筛选）/ `duplicate_quick_delete.py`；`services/duplicate_quick_delete_service.py` |
| 种子备份 torrent-backup | `views/torrents/FileManagement.vue`、`api/torrents.ts` / `api/torrents-backup.ts` | `api/endpoints/torrent_backup.py`（列表单次批量解析当前下载器 nickname，不逐行请求）；`services/torrent_file_backup_manager.py`；`models/torrent_file_backup.py` |
| 仪表盘 dashboard | `views/dashboard/index.vue`、`api/dashboard.ts` | `api/endpoints/dashboard.py`；`services/dashboard_service.py` |
| 速度计划/设置 speed-schedule | `views/settings/index.vue` | `api/endpoints/downloader_settings.py`；`services/speed_schedule_service.py` |

---

## 分支说明

| 分支 | 一句话职责 | 链接 |
|------|-----------|------|
| **backend** | FastAPI 后端总览与跨分支依赖骨架 | [backend/README.md](./backend/README.md) |
| ↳ app-root | `backend/app/` 包根 8 文件：应用工厂、DB 引擎、异常处理、配置入口、版本、桌面/WebSocket main | [backend/app-root.md](./backend/app-root.md) |
| ↳ api | HTTP 路由层（37 个 endpoints + schemas + models + responseVO） | [backend/api/README.md](./backend/api/README.md) |
| ↳ services | 业务服务层 + downloader_adapters + tag_adapters | [backend/services/README.md](./backend/services/README.md) |
| ↳ core | 基础设施（config/path_mapping/file_ops/tracker_*），⚠ 含 4 个 0 引用孤儿文件 | [backend/core/README.md](./backend/core/README.md) |
| ↳ contracts ✨v1.0.6.27 | 前后端共享机器可读契约（advanced_search JSON + Python 加载器，单一真相源） | [backend/contracts/README.md](./backend/contracts/README.md) |
| ↳ data-models | ORM 模型 + repositories + schemas + enums + 默认数据种子 | [backend/data-models/README.md](./backend/data-models/README.md) |
| ↳ tasks | 定时任务（cron）+ scheduler + 后台任务管理 | [backend/tasks/README.md](./backend/tasks/README.md) |
| ↳ domain | 领域目录：downloader / torrents / tracker / auth / user | [backend/domain/README.md](./backend/domain/README.md) |
| ↳ infra | utils（audit_logger/encryption/log_sanitizer）+ startup + migrations + alembic | [backend/infra/README.md](./backend/infra/README.md) |
| **frontend** | Vue 2 + TypeScript 前端总览与分支索引 | [frontend/README.md](./frontend/README.md) |
| ↳ entry | 应用入口：Vue 实例化 / 路由 / 路由守卫 / 根组件 | [frontend/entry/README.md](./frontend/entry/README.md) |
| ↳ api | axios 封装的 13 个领域 API 模块 | [frontend/api/README.md](./frontend/api/README.md) |
| ↳ views | 13 个页面视图模块（⚠ class-component 与 Options API 并存） | [frontend/views/README.md](./frontend/views/README.md) |
| ↳ store | Vuex store（空壳 index + 5 个自注册 module） | [frontend/store/README.md](./frontend/store/README.md) |
| ↳ components-layout | 通用组件（Pagination/Breadcrumb/ThemeSwitcher/LucideIcon/PageSizeCombobox…）+ layout 骨架 | [frontend/components-layout/README.md](./frontend/components-layout/README.md) |
| ↳ utils-types | utils / types / constants / directive | [frontend/utils-types/README.md](./frontend/utils-types/README.md) |
| **deploy** | 多部署模式分叉：Docker Compose / PyInstaller 单机包 / Inno Setup / fpm | [deploy/README.md](./deploy/README.md) |
| **tests** | 后端 pytest（141 个 test_*.py，按子目录组织）+ 前端 Jest（43 个 test suite） | [tests/README.md](./tests/README.md) |
| **perspectives** | 跨切专题索引（架构调用链 / 约定 / 风险 / 测试覆盖） | [perspectives/README.md](./perspectives/README.md) |

---

## 阅读层级

- **第一层（本文件）**：模块路由，只看分支职责与导航。
- **第二层（各分支 README.md）**：该分支的文件清单表（文件名 / 行数 / 一句话职责 / 链接）+ 依赖关系。
- **第三层（源文件 .md）**：单个源文件的类/函数索引与方法签名详情（固定四节模板）。
  - 本次已完成样例：[backend/api/endpoints/torrent_crud.md](./backend/api/endpoints/torrent_crud.md)
  - 其余源文件第三层待后续按"模式 B（补充）"增量补齐。

---

## 相关文档（双向链接 ⇄）

| 文档 | 关系 | 路径 |
|------|------|------|
| 项目 README | ⇄ 快速开始 / 技术栈总览 | [../../README.md](../../README.md) |
| 根 CLAUDE.md | ⇄ 全栈协同约束 | [../../CLAUDE.md](../../CLAUDE.md) |
| 根 AGENTS.md | ⇄ 全栈工作流路由层 | [../../AGENTS.md](../../AGENTS.md) |
| 后端 CLAUDE.md | ⇄ 后端技术约束 | [../../backend/CLAUDE.md](../../backend/CLAUDE.md) |
| 前端 CLAUDE.md | ⇄ 前端技术约束 | [../../frontend/CLAUDE.md](../../frontend/CLAUDE.md) |
| 架构深度分析 | 调用链详述来源（配置/迁移双轨、定时任务隔离） | [../../backend/docs/architecture-deep-dive.md](../../backend/docs/architecture-deep-dive.md) |
| 架构独立审查 | 对深度分析的 review | [../../backend/docs/architecture-review.md](../../backend/docs/architecture-review.md) |
| 后端约束集 | API 响应格式 / 数据库迁移 / 下载器连接等 6 条 | [../../backend/docs/constraints/](../../backend/docs/constraints/) |
| 前端约束集 | Options API / 公共变量 / 异步上下文等 6 条 | [../../frontend/docs/constraints/](../../frontend/docs/constraints/) |

> 路线图遵循"单一真相"原则：架构论述、约束条款已在上述文档中存在的，本路线图只放**索引 + 链接**，不复制全文。详见 [perspectives/README.md](./perspectives/README.md)。

---

## 元信息

| 项目 | 值 |
|------|-----|
| 生成日期 | 2026-07-25（首次）/ 2026-07-30（增量更新：v1.0.6.25~32）/ 2026-08-04（增量更新：v1.0.6.33~36）/ 2026-08-06（增量更新：v1.0.6.37）/ 2026-08-09（异步操作占用）/ 2026-08-11（同步阻塞修复、孤儿硬链接与 UI/重复查询修复）/ 2026-08-12（种子文件、任务日志、高级搜索与错误原因修复） |
| 来源 | 首次新建（`docs/roadmap/` 此前不存在）；后续按源码变更增量同步 |
| 分析范围 | backend/app/* + frontend/src/* + deploy + tests（全栈） |
| 行号依据 | 全部由当前源码 grep / Read 实测，禁止沿用历史文档行号 |
| 覆盖深度 | 第一层（全部）+ 第二层（全部 15 个分支，含 v1.0.6.27 新增 contracts）+ 第三层（2 个：torrent_crud.py、orphan_file_service.py） |
| 模板版本 | 后端 Python 四节；前端 Vue/TS 四节（适配 Options API + class-component 并存） |
| 本次新增 | 2026-08-12：种子文件列表批量返回当前下载器 nickname 并统一筛选 UI；任务日志操作按钮、任务筛选清空交互修复；高级搜索除调整按钮/组间 AND/OR 与统一 `error` 语义外，完成全字段审计：修复 Tracker 多行否定、SQL 通配符、标签 token、下载器改名、超级做种三态、NULL 补集、字段级空值操作符与回收站泄漏；Transmission 错误原因同步展示及 Tracker 状态码归一化，未联系/发送中不再归类为错误。 |
