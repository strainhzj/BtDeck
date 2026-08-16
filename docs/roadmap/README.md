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
│   └── infra/           utils + startup + migrations + alembic（20 个 revision，最新孤儿后台扫描与稳定明细迁移）
├── frontend/         ← Vue 2.6 + TypeScript 前端
│   ├── entry/           应用入口（main.ts / router.ts / permission.ts / App.vue）
│   ├── api/             axios API 封装（12 个领域模块）
│   ├── views/           页面视图（13 个 view 模块，Options API + class-component 并存）
│   ├── store/           Vuex（index.ts 空壳 + 5 个 getModule 自注册 module）
│   ├── components-layout/  通用组件（LucideIcon / PageSizeCombobox / AdvancedSearchWorkspace）+ 布局骨架
│   └── utils-types/     工具 / 类型 / 常量 / 指令（v1.0.6.36 新增 clipboard 剪贴板回退）
├── deploy/           ← 多部署模式（Docker / PyInstaller / Inno Setup / fpm；v1.0.6.28 Dockerfile 镜像源参数化）
├── tests/            ← 测试（backend pytest 145 个 test_*.py + frontend Jest 44 个 spec）
└── perspectives/     ← 跨切专题（调用链 / 约定 / 风险 / 测试覆盖）
```

## 功能域速查（第一层直达）

> 按功能词直达源文件，无需逐层翻页。定位时先在 `docs/roadmap/` 下 `Grep -i <功能词>` 命中本表行，再读对应源文件（路径相对 `frontend/src` / `backend/app`）。

| 功能域（含检索词） | 前端入口 | 后端入口 |
|------|---------|---------|
| 孤儿文件管理 orphan | `views/orphan-files/index.vue`、`api/orphan-files.ts`（后台扫描轮询；文件夹展开后懒加载/独立分页；仅可见文件实时统计硬链接；快捷操作+筛选区一键"已定位副本"筛选读预扫描结果；副本位置弹窗行级删除副本——$confirm 二次确认、就地刷新行副本数（located 筛选时整页刷新）、seq 快照防迟到重查覆盖；超量批次显示可关闭提醒） | `api/endpoints/orphan_files.py`；`services/orphan_scan_job_service.py` / `orphan_file_service.py` / `orphan_scanner.py` / `orphan_lifecycle_service.py` / `orphan_quarantine.py` / `orphan_manifest.py` / `orphan_lease.py` / `orphan_notification.py` / `orphan_purge_job_service.py`（持久化后台 scan_id、稳定明细复用、分批生命周期事务、超量提醒字段与通用实时清理安全校验、`hardlink-copies/delete` 副本删除端点）；`models/orphan_file.py`；`tasks/scheduler/orphan_*_task.py` |
| 种子管理 torrent | `views/torrents/`（index.vue、TraditionalView.vue、`components/TrackerDetailCard.vue`）、`api/torrents.ts`；两视图按已同步 Tracker 主机域名筛选，快捷操作排查错误且全局同名同大小内容唯一的单种；Tracker 完整详情弹框（标题/关闭/页签/内容区）由共享组件统一，表格视觉由 `_tracker-table.scss` 统一 | `api/endpoints/torrent_crud.py` / `torrents.py` / `torrents_async.py` / `torrent_deletion.py` / `torrent_status.py` / `torrent_location.py` / `torrent_speed.py` / `torrent_sync.py`；`getList` 支持 `tracker_domain` / `single_error_only`，域名来自 TrackerInfo 定时同步数据；Transmission 同步会持久化/清除错误原因，并把 Tracker announce/scrape 统计归一为 0–4 状态码，避免“已联系失败”误显示为“未联系”；列表名称 tooltip 与 Tracker 卡片展示 `errorReason`；同步统一走缓存下载器客户端、短事务与可续跑 cursor；`services/deletion_task_manager.py`（活动删除 ID 占用）/ `torrent_crud_service.py` / `torrent_batch_add_service.py` / `torrent_deletion_service.py` / `torrent_location_service.py` |
| 错误单种排查 single-error torrent | `views/torrents/index.vue` / `TraditionalView.vue`（快捷操作、Tracker 主机域名多选和可退出排查提示） | `torrent_crud.py:get_torrents` + `torrent_helpers.py:get_torrent_infos`（`single_error_only`：错误且全局同名同大小内容唯一；同一任务的多个 Tracker 服务不影响唯一性） |
| 下载器管理 downloader | `views/downloader/`、`api/downloader.ts` | `api/endpoints/downloader*.py`；`services/downloader_adapters/` / `downloader_api_runtime.py` / `downloader_capabilities_manager.py` / `downloader_settings_manager.py` / `path_maintenance_service.py`；`models/downloader*.py` |
| Tracker 管理 tracker | `views/tracker/`、`api/tracker.ts` | `api/endpoints/tracker*.py`；`services/reannounce_service.py` |
| 任务/定时任务 task cron | `views/tasks/index.vue`、`api/tasks.ts`（outcome/stale 展示 helper 由实例方法暴露给模板；查看日志保留可见任务筛选，清空后立即恢复全部日志） | `api/endpoints/tasks.py` / `cron_tasks.py`；`tasks/`（scheduler） |
| 审计日志 audit | `views/logs/audit.vue`、`api/audit-logs.ts` | `api/endpoints/audit_logs.py`；`services/audit_service.py` / `audit_service_sync.py` |
| 回收站 recycle | `views/recycle-bin/index.vue`（搜索区复用孤儿文件管理页 UI）、`api/recycle-bin.ts` | `api/endpoints/recycle_bin.py`；`services/recycle_bin_service.py` |
| 通知中心 notification | `layout/components/NotificationDrawer/`、`api/notification.ts`、`store/modules/notification.ts` | `api/endpoints/notifications.py`；`services/notification_service.py`；`models/notification.py` |
| 查询模板 query-template | `views/query-templates/`（行操作为 Lucide 极简按钮） | `api/endpoints/advanced_search.py`；`services/advanced_search.py`；`models/search_template.py` |
| 标签管理 tag | 下载器页 TagManagementTab | `api/endpoints/tag_management.py`；`services/tag_service.py` / `tag_sync_service.py` / `tag_adapters/`；`models/torrent_tags.py` |
| 高级搜索 advanced-search | `components/torrents/AdvancedSearchWorkspace.vue`（左侧已保存搜索选择/创建/更新/删除）+ Builder（契约过滤操作符；下载器显示 nickname/提交稳定 ID；超级做种三态；包含/排除模式原样传输）+ 两种种子视图 | `api/endpoints/advanced_search.py`；`services/advanced_search.py`（20 字段；`error` 复用列表语义；Tracker 否定走 `NOT EXISTS`；文本字面匹配、标签完整 token、空值严格补集、回收站排除）/ `sqlite_search_runtime.py` |
| 种子转移 seed-transfer | — | `api/endpoints/seed_transfer.py`；`services/seed_transfer_service.py`（成功后立即落库目标行/源行 dr=1，审计含 IP）；`models/seed_transfer_audit_log.py` |
| 重复种子/同内容排查 duplicate same-content inspection | `views/torrents/index.vue` / `TraditionalView.vue`（同 Hash 开关 + 快捷操作“同内容异常排查”；当前表格内筛选/排序/分页并可退出）+ `components/torrents/QuickDeleteDuplicatesDialog.vue` | `api/endpoints/duplicate_torrents.py`（同 Hash 重复查询）/ `duplicate_quick_delete.py`；`torrent_crud.py:get_torrents` + `torrent_helpers.py:get_torrent_infos`（`same_content_only`：同名同大小且不同规范化 Hash，复用列表分页）/ `services/duplicate_quick_delete_service.py` |
| 种子备份 torrent-backup | `views/torrents/FileManagement.vue`、`api/torrents.ts` / `api/torrents-backup.ts` | `api/endpoints/torrent_backup.py`（列表单次批量解析当前下载器 nickname，不逐行请求）；`services/torrent_file_backup_manager.py`；`models/torrent_file_backup.py` |
| 仪表盘 dashboard | `views/dashboard/index.vue`、`api/dashboard.ts` | `api/endpoints/dashboard.py`；`services/dashboard_service.py` |
| 速度计划/设置 speed-schedule | `views/settings/index.vue` | `api/endpoints/downloader_settings.py`；`services/speed_schedule_service.py` |

---

## 分支说明

| 分支 | 一句话职责 | 链接 |
|------|-----------|------|
| **backend** | FastAPI 后端总览与跨分支依赖骨架 | [backend/README.md](./backend/README.md) |
| ↳ app-root | `backend/app/` 包根 8 文件：应用工厂、DB 引擎、异常处理、配置入口、版本、桌面/WebSocket main | [backend/app-root.md](./backend/app-root.md) |
| ↳ api | HTTP 路由层（38 个 endpoints + schemas + models + responseVO） | [backend/api/README.md](./backend/api/README.md) |
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
| **tests** | 后端 pytest（145 个 test_*.py，按子目录组织）+ 前端 Jest（44 个 spec） | [tests/README.md](./tests/README.md) |
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
| 生成日期 | 2026-07-25（首次）/ 2026-07-30（增量更新：v1.0.6.25~32）/ 2026-08-04（增量更新：v1.0.6.33~36）/ 2026-08-06（增量更新：v1.0.6.37）/ 2026-08-09（异步操作占用）/ 2026-08-11（同步阻塞修复、孤儿硬链接与 UI/重复查询修复）/ 2026-08-12（种子文件、任务日志、高级搜索、错误原因及 Tracker 判断修复）/ 2026-08-13（孤儿扫描 12 万级后台化）/ 2026-08-14（大库迁移中断恢复、启动 fail-fast、孤儿文件页面视图模式与嵌套表头修复、Tracker 主域名筛选与错误单种排查及卡片样式统一）/ 2026-08-15（种子文件备份补偿、孤儿副本整体定位与筛选下拉提示语；同日副本定位改为定时预扫描落库；第三批：located 副本筛选 + 预扫描范围收紧）/ 2026-08-16（副本位置弹窗行级删除副本）/ 2026-08-16（第二批：进度精度舍入、转移后立即落库目标行、手动操作审计补 IP） |
| 来源 | 首次新建（`docs/roadmap/` 此前不存在）；后续按源码变更增量同步 |
| 分析范围 | backend/app/* + frontend/src/* + deploy + tests（全栈） |
| 行号依据 | 全部由当前源码 grep / Read 实测，禁止沿用历史文档行号 |
| 覆盖深度 | 第一层（全部）+ 第二层（全部 15 个分支，含 v1.0.6.27 新增 contracts）+ 第三层（2 个：torrent_crud.py、orphan_file_service.py） |
| 模板版本 | 后端 Python 四节；前端 Vue/TS 四节（适配 Options API + class-component 并存） |
| 本次新增 | 2026-08-12：种子文件、任务日志、高级搜索、Transmission 错误原因与 Tracker 共享判定策略回归。2026-08-13：同内容排查改为列表分页；孤儿扫描后台化、稳定明细复用、生命周期短事务、文件夹懒加载/可见文件硬链接及 >50000 双复核门禁。2026-08-14：补齐 SQLite batch 中断恢复、canonical_path 索引回填、真实 1.02 GB 旧库升级、迁移失败启动 fail-fast、孤儿文件页面视图模式/嵌套表头回归及模式切换/普通行展开保护；超量扫描改为可关闭提醒并移除复核清理门禁；Tracker 主域名筛选（实测域名提取低于 1 秒，无需内存缓存）、错误单种全局唯一排查与列表/传统 Tracker 完整详情弹框共享（标题/关闭/页签/内容区）及 `_tracker-table.scss` 视觉样式统一；新增 TrackerDetailCard 运行时回归测试。2026-08-15：info/full 同步后 `reconcile_missing_backups` 限量增量补齐缺失种子文件备份（修复 6 月初 info-only 拆分后备份停更）；`torrent_file_backup.downloader_id` Integer→String(36) UUID 对齐（迁移 `b6e1c4d9a2f7`，downgrade 拒绝破坏性回滚）；孤儿副本定位改 `collect_runtime_accessible_roots` 按目标 `st_dev` 整体收集运行环境可访问挂载根；`AdvancedMultiSelect` 新增 `placeholder` prop，种子页筛选下拉提示语改为"请选择下载器/请选择种子状态/请选择tracker"。2026-08-15（第二批）：副本定位从点击实时遍历改为定时任务 `orphan_hardlink_copy_scan`（每日 04:00）后台预扫描——新表 `orphan_hardlink_copy_result`（按 `(device_id, inode_id)` 唯一，device_id 字符串适配 Windows 无符号卷号）+ 单行 keyset 游标表（迁移 `c8d9e0f1a2b3`，当前 head）；`hardlink-copies` 端点只读库（保留廉价 stat 复核总数，未覆盖返回 pending_scan）；性能护栏：stat 限量 2000/轮、遍历限量 200 inode/轮、单调时钟预算 300s（os.walk 目录间检查）、单 inode 路径上限 100、结果保留 30 天、分批短事务写库、heavy_sync 互斥登记；`find_hardlink_paths_bounded` 提供带预算遍历。2026-08-15（第三批）：孤儿列表/文件夹子项新增 `hardlink_copies=located` 筛选（快捷操作"筛选已定位副本"一键切换 + 筛选区复选框；SQL 为候选 `(device_id, inode)` CAST join 结果表 `found_count>1`，含源路径口径与弹框一致）；预扫描 `_stat_window` 候选范围收紧为 `status=candidate` 且未忽视（已忽视/隔离/清除不再消耗 stat 预算，即线上 stat_failed 主因），取消忽视/隔离恢复后自动回到扫描范围。2026-08-16：副本位置弹窗新增行级「删除副本」——新端点 `POST /orphan-files/hardlink-copies/delete`（`orphan_files.py:341`）+ 服务 `delete_hardlink_copies`（`orphan_file_service.py:871`）：仅移除指向同一 inode 的其它路径链接（源文件与数据保留），逐路径 fail-closed（维护租约、候选 status=candidate/operation_state=stable 门禁、源 stat 身份、预扫描结果行存在、共享 inode 拒绝集、种子目录白名单 `collect_torrent_directory_whitelist` 全量加载、copies 原始字符串成员判定、隔离区/回收站标记与符号链接拒绝），tombstone 三段式删除（rename→身份复核→remove，复核失败回滚），成功后 setattr payload 同步结果行并 commit 后写审计（新枚举 `orphan_hardlink_copy_delete`，三处登记）；前端 $confirm(type=error) 二次确认、`$set/$delete` 行级删除态、删除后就地刷新行副本数（located 筛选时整页刷新）、seq 快照+弹窗可见双重校验防迟到重查覆盖、重查保留旧数据仅局部遮罩。状态类拒绝一律 200+failed_list（`{copy_path, reason}`）。 | 2026-08-16（第二批）：①`torrents_async._normalize_progress_value` 统一 round(2)（8 处同步写路径汇聚点，存量脏值下次同步自愈）；②`seed_transfer_service` 验证成功后 `_upsert_target_torrent_row` 立即落库目标下载器行（字段对齐 info-only 同步 insert dict，(hash,downloader_id) WHERE dr=0 唯一索引保证与后续同步同一条），delete_source 成功源行 dr=1（同步删除语义），source==target 服务层防御；③转移与孤儿 5 项手动操作审计补提交端 IP——同步端点（hardlink-copies/delete、restore、ignore、transfer）经 extract_audit_info_from_request 直接透传，后台任务链（cleanup、purge）经 orphan_purge_job 新列 ip_address（迁移 ab68fe061d5b，串接 ff42d3402df5）持久化后 execute_job 透传；5 个孤儿服务函数 ip_address 形参+4 处租约递归+5 处审计调用点；4 个提交入口全加参；EXPECTED_HEAD/REV_HEAD 三处测试常量与 database-migration.md HEAD 标注同步（原文档标 c8d9e0f1a2b3 已过期 5 个版本）。
