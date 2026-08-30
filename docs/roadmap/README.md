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
│   └── infra/           utils + startup + migrations + alembic（29 个 revision，最新 orphan Schema 漂移修复）
├── frontend/         ← Vue 2.6 + TypeScript 前端
│   ├── entry/           应用入口（main.ts / router.ts / permission.ts / App.vue）
│   ├── api/             axios API 封装（12 个领域模块）
│   ├── views/           页面视图（13 个 view 模块，Options API + class-component 并存）
│   ├── store/           Vuex（index.ts 空壳 + 4 个 getModule 自注册 + downloaderSettings 传统 namespaced）
│   ├── components-layout/  通用组件（AppLogo / LucideIcon / PageSizeCombobox / AdvancedSearchWorkspace）+ 布局骨架
│   └── utils-types/     工具 / 类型 / 常量 / 指令（v1.0.6.36 新增 clipboard 剪贴板回退）
├── android/          ← 伴侣模式 App（dual-mode-client Phase 2 MVP：向导/服务器 profile/健康检查/同源 WebView）
├── deploy/           ← 多部署模式（Docker / PyInstaller / Inno Setup / fpm；v1.0.6.28 Dockerfile 镜像源参数化）
├── tests/            ← 测试（backend/tests pytest 180 个 test_*.py + frontend Jest 84 个 spec）
└── perspectives/     ← 跨切专题（docs/roadmap/perspectives：调用链 / 约定 / 风险 / 测试覆盖）
```

## 功能域速查（第一层直达）

> 按功能词直达源文件，无需逐层翻页。定位时先在 `docs/roadmap/` 下 `Grep -i <功能词>` 命中本表行，再读对应源文件（路径相对 `frontend/src` / `backend/app`）。

| 功能域（含检索词） | 前端入口 | 后端入口 |
|------|---------|---------|
| 孤儿文件管理 orphan | `views/orphan-files/index.vue`、`api/orphan-files.ts`（后台扫描轮询；文件夹展开后懒加载/独立分页；仅可见文件实时统计硬链接；快捷操作+筛选区一键"已定位副本"筛选读预扫描结果；副本位置弹窗行级删除副本——$confirm 二次确认、就地刷新行副本数（located 筛选时整页刷新）、seq 快照防迟到重查覆盖；超量批次显示可关闭提醒） | `api/endpoints/orphan_files.py`；`services/orphan_scan_job_service.py` / `orphan_file_service.py` / `orphan_scanner.py` / `orphan_lifecycle_service.py` / `orphan_quarantine.py` / `orphan_manifest.py` / `orphan_lease.py` / `orphan_notification.py` / `orphan_purge_job_service.py`（持久化后台 scan_id、稳定明细复用、分批生命周期事务、超量提醒字段与通用实时清理安全校验、`hardlink-copies/delete` 副本删除端点）；`models/orphan_file.py`；`tasks/scheduler/orphan_*_task.py` |
| 种子管理 torrent | `views/torrents/`（index.vue、TraditionalView.vue、`components/TrackerDetailCard.vue`、`mixins/errorTooltipDismiss.ts`）、`api/torrents.ts`；两视图按已同步 Tracker 主机域名筛选，快捷操作排查错误且全局同名同大小内容唯一的单种；新增“辅种数量”列，数量由种子信息同步任务计算，删除/转移后增量校正；Tracker 完整详情弹框（标题/关闭/页签/内容区）由共享组件统一，表格视觉由 `_tracker-table.scss` 统一；错误原因 tooltip 在滚轮/滚动时主动收起，列表查询使用全屏锁滚动蒙版；实时速度快照支持 200/206，携带 status/downloadComplete，完成证据强制进度 100，三种视图按 downloader_id+hash 收敛终态；运行态新复合键触发一次权威列表重拉，批量添加完成信号兜底首次刷新早于入库的竞态 | `api/endpoints/torrent_crud.py` / `torrents.py` / `torrents_async.py` / `torrent_deletion.py` / `torrent_status.py` / `torrent_location.py` / `torrent_speed.py` / `torrent_sync.py`；`getList` 支持 `tracker_domain` / `single_error_only`，域名来自 TrackerInfo 定时同步数据；Transmission 同步会持久化/清除错误原因，并把 Tracker announce/scrape 统计归一为 0–4 状态码，避免“已联系失败”误显示为“未联系”；列表名称 tooltip 与 Tracker 卡片展示 `errorReason`；同步统一走缓存下载器客户端、短事务与可续跑 cursor，并全局按 `name + size` 校正辅种数量；`torrent_speed.py` TTL 补查按下载器轮转并提供 `/runtime-state/reconcile` 复合键终态核验；`services/auxiliary_seed_count_service.py` / `deletion_task_manager.py` / `torrent_crud_service.py` / `torrent_batch_add_service.py` / `torrent_deletion_service.py` / `torrent_location_service.py` |
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
| 种子转移 seed-transfer | — | `api/endpoints/seed_transfer.py`；`services/seed_transfer_service.py`（成功后立即落库目标行/源行 dr=1，并增量维护辅种数量，审计含 IP）；`models/seed_transfer_audit_log.py` |
| 重复种子/同内容排查 duplicate same-content inspection | `views/torrents/index.vue` / `TraditionalView.vue`（同 Hash 开关 + 快捷操作“辅种异常排查”；当前表格内筛选/排序/分页并可退出）+ `components/torrents/QuickDeleteDuplicatesDialog.vue` | `api/endpoints/duplicate_torrents.py`（同 Hash 重复查询）/ `duplicate_quick_delete.py`；`torrent_crud.py:get_torrents` + `torrent_helpers.py:get_torrent_infos`（`same_content_only`：同名同大小且不同规范化 Hash，复用列表分页；v1.0.6.40 起状态/Tracker 仅组内显示过滤，不参与成组判定）/ `services/duplicate_quick_delete_service.py` |
| 种子备份 torrent-backup | `views/torrents/FileManagement.vue`、`api/torrents.ts` / `api/torrents-backup.ts` | `api/endpoints/torrent_backup.py`（列表单次批量解析当前下载器 nickname，不逐行请求）；`services/torrent_file_backup_manager.py`；`models/torrent_file_backup.py` |
| 仪表盘 dashboard | `views/dashboard/index.vue`、`api/dashboard.ts` | `api/endpoints/dashboard.py`；`services/dashboard_service.py` |
| 速度计划/设置 speed-schedule | `views/settings/index.vue` | `api/endpoints/downloader_settings.py`；`services/speed_schedule_service.py` |

---

## 分支说明

| 分支 | 一句话职责 | 链接 |
|------|-----------|------|
| **backend** | FastAPI 后端总览与跨分支依赖骨架 | [backend/README.md](./backend/README.md) |
| ↳ app-root | `backend/app/` 包根 8 文件：应用工厂、DB 引擎、异常处理、配置入口、版本、桌面/WebSocket main | [backend/app-root.md](./backend/app-root.md) |
| ↳ desktop-companion | 桌面伴侣 profile、LAN 策略、健康检查、Windows DPAPI 凭据与 pywebview 会话恢复 | [backend/desktop-companion.md](./backend/desktop-companion.md) |
| ↳ api | HTTP 路由层（37 个 endpoints + schemas + models + responseVO） | [backend/api/README.md](./backend/api/README.md) |
| ↳ services | 业务服务层 + downloader_adapters + tag_adapters | [backend/services/README.md](./backend/services/README.md) |
| ↳ core | 基础设施（config/path_mapping/file_ops/tracker_*），⚠ 含 4 个 0 引用孤儿文件 | [backend/core/README.md](./backend/core/README.md) |
| ↳ contracts ✨v1.0.6.27 | 前后端共享机器可读契约（advanced_search JSON + Python 加载器，单一真相源） | [backend/contracts/README.md](./backend/contracts/README.md) |
| ↳ data-models | ORM 模型 + repositories + schemas + enums + 默认数据种子 | [backend/data-models/README.md](./backend/data-models/README.md) |
| ↳ tasks | 定时任务（cron）+ scheduler + 后台任务管理 | [backend/tasks/README.md](./backend/tasks/README.md) |
| ↳ domain | 领域目录：downloader / torrents / tracker / auth / user | [backend/domain/README.md](./backend/domain/README.md) |
| ↳ infra | utils（audit_logger/encryption/log_sanitizer/connectivity）+ startup + migrations + alembic | [backend/infra/README.md](./backend/infra/README.md) |
| **android** ✨2026-08-23 | 伴侣模式 App（Kotlin；不含 Python，服务端壳是 Phase 3） | [android-companion.md](./android-companion.md) / [../android/README.md](../../android/README.md) |
| **frontend** | Vue 2 + TypeScript 前端总览与分支索引 | [frontend/README.md](./frontend/README.md) |
| ↳ entry | 应用入口：Vue 实例化 / 路由 / 路由守卫 / 根组件 | [frontend/entry/README.md](./frontend/entry/README.md) |
| ↳ api | axios 封装的 12 个领域 API 模块 | [frontend/api/README.md](./frontend/api/README.md) |
| ↳ views | 13 个页面视图模块（⚠ class-component 与 Options API 并存） | [frontend/views/README.md](./frontend/views/README.md) |
| ↳ store | Vuex store（空壳 index + 5 个自注册 module） | [frontend/store/README.md](./frontend/store/README.md) |
| ↳ components-layout | 通用组件（AppLogo/Pagination/Breadcrumb/ThemeSwitcher/LucideIcon/PageSizeCombobox…）+ layout 骨架 | [frontend/components-layout/README.md](./frontend/components-layout/README.md) |
| ↳ utils-types | utils / types / constants / directive | [frontend/utils-types/README.md](./frontend/utils-types/README.md) |
| **deploy** | 多部署模式分叉：Docker Compose / PyInstaller 单机包 / Inno Setup / Android APK / fpm；含根目录统一构建入口 | [deploy/README.md](./deploy/README.md) |
| **tests** | 后端 pytest（180 个 test_*.py，按子目录组织）+ 前端 Jest（84 个 spec） | [tests/README.md](./tests/README.md) |
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
| 生成日期 | 2026-07-25（首次）/ 2026-07-30（增量更新：v1.0.6.25~32）/ 2026-08-04（增量更新：v1.0.6.33~36）/ 2026-08-06（增量更新：v1.0.6.37）/ 2026-08-09（异步操作占用）/ 2026-08-11（同步阻塞修复、孤儿硬链接与 UI/重复查询修复）/ 2026-08-12（种子文件、任务日志、高级搜索、错误原因及 Tracker 判断修复）/ 2026-08-13（孤儿扫描 12 万级后台化）/ 2026-08-14（大库迁移中断恢复、启动 fail-fast、孤儿文件页面视图模式与嵌套表头修复、Tracker 主域名筛选与错误单种排查及卡片样式统一）/ 2026-08-15（种子文件备份补偿、孤儿副本整体定位与筛选下拉提示语；同日副本定位改为定时预扫描落库；第三批：located 副本筛选 + 预扫描范围收紧）/ 2026-08-16（副本位置弹窗行级删除副本）/ 2026-08-16（第二批：进度精度舍入、转移后立即落库目标行、手动操作审计补 IP）/ 2026-08-17（双密钥会话过期登出与重登录生效修复） / 2026-08-18（W9 强制改密路由死锁修复）/ 2026-08-18（第二批：同内容排查状态/Tracker 改组内显示筛选）/ 2026-08-18（第三批：跨标签令牌续期竞态修复——三态续期/ExpireSession 保留 refresh cookie/守卫网络错误分流/后端原子轮换）/ 2026-08-18（第四批：令牌机制对抗审计修复——升级密钥补齐/业务 401 改码/refresh_tokens 清理任务/SECRET_KEY YAML 持久化/跨标签级联根修/5xx 瞬时逃生/审计下载 blob/网络 toast 节流/el-upload 401 引导）/ 2026-08-20（第二批：展示对齐判定——Tracker 异常可见化与 Announce 状态覆写）/ 2026-08-23（安卓适配 Phase 1：统一 TCP probe 与依赖瘦身）/ 2026-08-23（第二批：Phase 2 伴侣模式 MVP 脚手架 + health version 字段）/ 2026-08-26（`BtDeck` 效果图字标与 App 微型图标）/ 2026-08-27（种子错误 tooltip 滚动收起与查询全屏锁定蒙版）/ 2026-08-27（第四批：Windows EXE/安装包品牌图标）/ 2026-08-27（EXE/APK 构建脚本）/ 2026-08-28（移动端 UX 增强）/ 2026-08-29（种子实时终态收敛与部分快照容错）/ 2026-08-30（种子列表成员自愈与批量添加完成刷新）|
| 2026-08-20 增量 | 新增 `auxiliary_seed_count` 数据链路、种子信息同步全量校正、删除/转移/还原增量维护，以及两种种子列表视图字段；同步 Alembic head `975dad435c03` 与相关测试入口 |
| 2026-08-20 增量（第二批） | 展示对齐判定：新增 `core/tracker_keyword_map.py` 共享关键词池加载器（判定任务 `_load_keywords` 委托复用）；`tracker_status_policy.py` 新增 `tracker_message_failed`/`tracker_display_failed`（与判定任务中性码语义一致）；`torrent_helpers.py`/`duplicate_torrents.py` announce/scrape 展示文本按失败池覆写 + VO 透传 `has_tracker_error` + duplicates error 筛选口径对齐（OR has_tracker_error）；前端 `torrentBatch.ts` 新增 hasTrackerError/showTrackerErrorTag/getTorrentErrorReason 共享 helper，两视图状态列叠加红色 Tracker异常 标签 |
| 2026-08-21 增量 | 任务日志与孤儿文件页统计摘要接入全局 `CollapsiblePanel`，分别以 `btdeck_task_log_stats_collapsed` / `btdeck_orphan_file_stats_collapsed` 持久化折叠状态；前端管理页契约测试扩展为 14 项 |
| 2026-08-22 增量 | roadmap 全量对账刷新（基准 HEAD 348c700）：补记 04c8ec6 mypy 清零/ORM Mapped 迁移批次（143 个后端文件行号整体漂移）；汇总计数实测重校（endpoints 37、alembic 28 个 revision/head `975dad435c03`、后端测试 180、前端 spec 59、api 模块 12、store 4+1 拆分）；清理 7 条失效条目、补录 29 个漏列文件（含 5 个新 revision）；第三层两文档行为描述重写（批种添加 202 后台化、孤儿副本数快照列、`call_downloader_api` 统一下载器调用） |
| 2026-08-23 增量（同步资源观测） | `resource_guard` 记录 heavy_sync holder 的 task/run/phase/进程信息并补充 wait_timeout 诊断；`cron_executor` 增加 Python 内部类生命周期心跳/超时告警；`sync_coordinator` 暴露阶段耗时与最近进度；新增 92 项针对性回归覆盖中的资源 holder 与生命周期观测用例 |
| 2026-08-23 增量（tracker_sync 异常边界观测） | `tracker_sync_task`、`sync_coordinator` 与 qB/TR tracker-only 路径补充下载器阶段、异常类型、traceback、错误计数和 `event=sync_error`（含是否继续执行）；有错误的结果汇总提升为 warning；新增 82 项定向回归覆盖 |
| 2026-08-25 增量（定时任务停止治理） | cron_executor 超时强制终止（`CRON_TASK_TIMEOUT_ENFORCE` 默认开，`TaskExecutionTimeoutError` 穿透兜底、任务体 TimeoutError 以 `_TaskBodyTimeoutError` 包装区分，timeout<=0 归一不强制）；interrupt 真取消（协程句柄自登记 + cancel 等收尾 + `outcome=cancelled`/success=True 落库）；`update_task_freshness` MissingGreenlet 根修（`onupdate=func.now()` postfetch 过期 → commit 后 `db.refresh`）；心跳停滞告警（`SYNC_TASK_PROGRESS_STALL_WARNING_SECONDS`，progress_stalled 入白名单）+ faulthandler 全线程栈自动转储；认证检查一次性 qb/tr 客户端补 requests 超时；interrupt 端点补审计（`SCHEDULED_TASK_INTERRUPT` 枚举 + 前端 audit.vue 映射）。测试：TestTimeoutEnforcement/TestInterruptRunningInstance/freshness 真实会话共 9 新例，相关套件 461 passed |
| 2026-08-23 增量（孤儿 Schema 漂移自愈） | 新增 Alembic 修复迁移 `c1d2e3f4a5b6`：针对版本号已到 `975dad435c03` 但 `orphan_current_candidate.current_detail_id` 缺失的存量库，后端重启自动补列/回填/索引；健康库幂等 no-op；新增迁移回归测试 |
| 来源 | 首次新建（`docs/roadmap/` 此前不存在）；后续按源码变更增量同步 |
| 分析范围 | backend/app/* + frontend/src/* + deploy + tests（全栈） |
| 2026-08-26 增量 | 前端 Logo 按效果图收口：完整横版改为绿色 D 形轨道、三条深色甲板线与 `Bt` 绿/`Deck` 深色字标，移除实验编号/中文说明；移动头部及 PWA/Apple/Android/favicons 全部使用绿色底反白 `micro` 光学版，生成脚本同步输出横版 PNG |
| 2026-08-26 增量 | 伴侣凭据记忆：Android `CredentialVault`（Keystore AES-GCM）与桌面 `desktop_companion/credentials.py`（Windows DPAPI），profile 增加 username；WebView/pywebview 切换时先隔离旧 cookie，再用一次性同源登录恢复 access/refresh token；新增 Android/桌面回归覆盖。 |
| 2026-08-27 增量 | 移动端三项调整：①移动查询模板页 `/m/query-templates` 裁撤（仅保留高级搜索，深链 redirect 至 `/m/search`，`m2-template-cache.ts` 与种子页/搜索页模板回填链路移除）；②高级搜索条件组移动适配：`AdvancedSearchBuilder.vue` 内联定宽全部类化 + 768px 断点强化（选择器铺满/组头换行/AND/OR 标签避让/对话框窄屏压宽），`ConditionValueInput.vue` 日期范围窄屏弹性对分；③新增 `/m/settings` 移动设置页（整页复用桌面设置组件），守卫强制改密落点/放行白名单按 UI 模式分流（移动落 `/m/settings`），`toMobilePath('/settings')` 映射补齐；entry 分支路由表与守卫行号全量重测 |
| 2026-08-27 增量（第二批） | Tracker 域名筛选命中可视化：`torrent_helpers.py` 保留 EXISTS/ANY 语义，入口统一归一域名后 SQL（like `escape` 字面量化）与 Python 谓词 `tracker_row_matches_domains` 同口径过滤，VO `tracker_info[].matched_domain` 标记命中行；`tracker_like` 空结果改返回空列表；前端 TrackerDetailCard 命中行高亮+「命中筛选」标签（`_tracker-table.scss`）、两视图 `[tracker-filter]` 观察日志（共享 `countMatchedTrackerRows`）、后端 `[tracker-domain-filter]`/`[tracker-filter]`/`[torrent-list]` debug 锚点；查询模板 simple 表单补 Tracker 域名多选（修复保存丢失 tracker 筛选）；torrents 视图分支与 torrent_crud 三层 md 同步 |
| 2026-08-27 增量（第三批） | 两种桌面种子视图接入 `mixins/errorTooltipDismiss.ts`：错误原因 tooltip 禁止进入浮层，并在捕获阶段滚动/滚轮时调用 `hide()` 收起；`listLoading` 改用 `v-loading.fullscreen.lock` 覆盖整个视口并锁定页面滚动；回归加固为 mixin/真实 Element UI Tooltip、真实 Loading DOM 行为、双视图 directive binding + 异常复位三层保护，前端 Jest 实测 84 suites / 1169 tests。 |
| 2026-08-27 增量（第四批） | Windows 发行图标修复：`generate-pwa-icons.py` 将品牌 `micro` mark 输出为 16~256px 多尺寸 ICO；`btdeck-windows.spec` 显式嵌入该 ICO，使 EXE 与 pywebview 运行窗口/任务栏使用项目 Logo；`btdeck.iss` 安装器、卸载项及三类快捷方式统一复用；打包契约新增 3 项回归。 |
| 2026-08-27 增量（构建脚本） | 新增 `deploy/build-android.bat`：相对仓库路径解析、Gradle/JDK/SDK 检查、严格/LAN 双 debug APK 构建、JVM 单测、产物复制与 `apksigner`/`aapt2` 校验；新增根 `build-packages.bat` 统一调用既有 Windows EXE 链和 Android 链，并支持按目标/变体选择。 |
| 2026-08-28 增量（移动端 UX 增强） | `views/torrents/mixins/speedPolling.ts` 增量扩展 `speedPollIntervalMs`/`startSpeedPolling(immediate)`（桌面默认行为零变化，移动端复用为通用 visibility 门控轮询）；`layout/mobile/index.vue` 四 Tab 加 LucideIcon（house/hard-drive/download/bell）、二级页 header ←（固定回退映射 replace：详情→种子/设置→下载器/关键词搜索→看板/其余→仪表盘）与汉堡并存、标题用 meta.title、汉堡触控区 44×44、60s 未读轮询 document.hidden 门控；`views/mobile/torrents.vue` 10s 速度轮询（复用 torrentBatch `buildSpeedSnapshot` + traditionalTorrentIdentity 精确合并，ready 未命中行清零防冻结）、卡片速度行（>0 才渲染+min-width 防抖）、`v-infinite-scroll` 无限滚动+尾部计数、返回顶部浮标、暂停/恢复乐观状态更新、空态 CTA（无下载器→`/m/downloader?create=1`，downloader.vue mounted 解析直达新增弹窗）；`dashboard.vue` 15s/`notifications.vue` 30s 静默自动刷新（silent 不置 loading）、通知按 id 去重分页追加+静默刷新翻页互斥（已翻页只同步未读角标）、下载器空态 CTA、两页移除 m-refresh；`torrent-detail.vue` 手写 setInterval 迁移 SpeedPollingMixin（5s+后台暂停）并移除底部冗余返回排；`tasks.vue` 删除按钮 margin-left:auto 分隔；`pull-to-refresh.ts` 手势内滚动回顶重置起点防指示条跳变。测试：speed-polling 9 / mobile-shell 31 / mobile-torrents 21 / mobile-notifications 17 / mobile-dashboard 15 / mobile-torrent-detail 7 / mobile-downloader 11 / pull-to-refresh 9，前端全量 84 suites / 1216 tests；e2e mobile-interactions 修正查询模板存量失效断言并新增二级页返回/Tab 图标用例；提交后验证抓出返回顶部两处缺陷（滚动容器实为 window 而非 .mobile-content；箭头函数类字段 this 指向 vue-class-component 收集后丢弃的实例致数据写入静默失效）并改为 window 监听 + prototype 方法。 |
| 2026-08-29 增量（种子实时终态收敛） | `backend/app/api/endpoints/torrent_speed.py` 补充 qB/Transmission 状态与 `downloadComplete`，完成态强制进度 100 并同步数据库；TTL 补查按下载器轮转、退避且确认完成后移除；新增 `/torrents/runtime-state/reconcile` 复合键终态核验。`frontend/src/views/torrents/utils/torrentBatch.ts` 支持 206 部分快照、终态归一和连续未命中候选；列表、传统、移动三视图按 `downloader_id + hash` 更新并在核验后刷新状态筛选。 |
| 2026-08-29 增量（桌面折叠侧栏 Lucide） | `SidebarItem.vue` 将折叠态从广泛隐藏 `el-submenu__title` 直接子 `span` 改为仅隐藏 `.submenu-label`/`.submenu-chevron`，显式保留 Lucide `.menu-icon`；修复种子管理与 Tracker 管理因多子菜单进入 `el-submenu` 分支后父图标消失。新增真实组件 + 实际 SCSS 回归 `sidebar-collapse-lucide.spec.ts`。 |
| 2026-08-30 增量（种子列表成员自愈） | `RuntimeListMembershipTracker` 以首个完整活动快照建立分页外基线，随后仅对新出现且未展示的 `downloader_id + hash` 触发串行权威列表刷新，并立即重放同轮速度；206 仅增量合并基线。`TorrentAddDialog.vue` 在 202 返回后按 `task_id` 轮询既有完成通知，列表/传统视图收到 `batch-complete` 后再次拉表并补一次速度；覆盖首次刷新早于数据库写入，以及零速度、暂停或瞬间完成无法由活动快照发现的新增种子。 |
| 行号依据 | 全部由当前源码 grep / Read 实测，禁止沿用历史文档行号 |
| 覆盖深度 | 第一层（全部）+ 第二层（全部 15 个分支，含 v1.0.6.27 新增 contracts）+ 第三层（2 个：torrent_crud.py、orphan_file_service.py） |
| 模板版本 | 后端 Python 四节；前端 Vue/TS 四节（适配 Options API + class-component 并存） |
| 本次新增 | 2026-08-12：种子文件、任务日志、高级搜索、Transmission 错误原因与 Tracker 共享判定策略回归。2026-08-13：同内容排查改为列表分页；孤儿扫描后台化、稳定明细复用、生命周期短事务、文件夹懒加载/可见文件硬链接及 >50000 双复核门禁。2026-08-14：补齐 SQLite batch 中断恢复、canonical_path 索引回填、真实 1.02 GB 旧库升级、迁移失败启动 fail-fast、孤儿文件页面视图模式/嵌套表头回归及模式切换/普通行展开保护；超量扫描改为可关闭提醒并移除复核清理门禁；Tracker 主域名筛选（实测域名提取低于 1 秒，无需内存缓存）、错误单种全局唯一排查与列表/传统 Tracker 完整详情弹框共享（标题/关闭/页签/内容区）及 `_tracker-table.scss` 视觉样式统一；新增 TrackerDetailCard 运行时回归测试。2026-08-15：info/full 同步后 `reconcile_missing_backups` 限量增量补齐缺失种子文件备份（修复 6 月初 info-only 拆分后备份停更）；`torrent_file_backup.downloader_id` Integer→String(36) UUID 对齐（迁移 `b6e1c4d9a2f7`，downgrade 拒绝破坏性回滚）；孤儿副本定位改 `collect_runtime_accessible_roots` 按目标 `st_dev` 整体收集运行环境可访问挂载根；`AdvancedMultiSelect` 新增 `placeholder` prop，种子页筛选下拉提示语改为"请选择下载器/请选择种子状态/请选择tracker"。2026-08-15（第二批）：副本定位从点击实时遍历改为定时任务 `orphan_hardlink_copy_scan`（每日 04:00）后台预扫描——新表 `orphan_hardlink_copy_result`（按 `(device_id, inode_id)` 唯一，device_id 字符串适配 Windows 无符号卷号）+ 单行 keyset 游标表（迁移 `c8d9e0f1a2b3`，当前 head）；`hardlink-copies` 端点只读库（保留廉价 stat 复核总数，未覆盖返回 pending_scan）；性能护栏：stat 限量 2000/轮、遍历限量 200 inode/轮、单调时钟预算 300s（os.walk 目录间检查）、单 inode 路径上限 100、结果保留 30 天、分批短事务写库、heavy_sync 互斥登记；`find_hardlink_paths_bounded` 提供带预算遍历。2026-08-15（第三批）：孤儿列表/文件夹子项新增 `hardlink_copies=located` 筛选（快捷操作"筛选已定位副本"一键切换 + 筛选区复选框；SQL 为候选 `(device_id, inode)` CAST join 结果表 `found_count>1`，含源路径口径与弹框一致）；预扫描 `_stat_window` 候选范围收紧为 `status=candidate` 且未忽视（已忽视/隔离/清除不再消耗 stat 预算，即线上 stat_failed 主因），取消忽视/隔离恢复后自动回到扫描范围。2026-08-16：副本位置弹窗新增行级「删除副本」——新端点 `POST /orphan-files/hardlink-copies/delete`（`orphan_files.py:341`）+ 服务 `delete_hardlink_copies`（`orphan_file_service.py:871`）：仅移除指向同一 inode 的其它路径链接（源文件与数据保留），逐路径 fail-closed（维护租约、候选 status=candidate/operation_state=stable 门禁、源 stat 身份、预扫描结果行存在、共享 inode 拒绝集、种子目录白名单 `collect_torrent_directory_whitelist` 全量加载、copies 原始字符串成员判定、隔离区/回收站标记与符号链接拒绝），tombstone 三段式删除（rename→身份复核→remove，复核失败回滚），成功后 setattr payload 同步结果行并 commit 后写审计（新枚举 `orphan_hardlink_copy_delete`，三处登记）；前端 $confirm(type=error) 二次确认、`$set/$delete` 行级删除态、删除后就地刷新行副本数（located 筛选时整页刷新）、seq 快照+弹窗可见双重校验防迟到重查覆盖、重查保留旧数据仅局部遮罩。状态类拒绝一律 200+failed_list（`{copy_path, reason}`）。 | 2026-08-16（第二批）：①`torrents_async._normalize_progress_value` 统一 round(2)（8 处同步写路径汇聚点，存量脏值下次同步自愈）；②`seed_transfer_service` 验证成功后 `_upsert_target_torrent_row` 立即落库目标下载器行（字段对齐 info-only 同步 insert dict，(hash,downloader_id) WHERE dr=0 唯一索引保证与后续同步同一条），delete_source 成功源行 dr=1（同步删除语义），source==target 服务层防御；③转移与孤儿 5 项手动操作审计补提交端 IP——同步端点（hardlink-copies/delete、restore、ignore、transfer）经 extract_audit_info_from_request 直接透传，后台任务链（cleanup、purge）经 orphan_purge_job 新列 ip_address（迁移 ab68fe061d5b，串接 ff42d3402df5）持久化后 execute_job 透传；5 个孤儿服务函数 ip_address 形参+4 处租约递归+5 处审计调用点；4 个提交入口全加参；EXPECTED_HEAD/REV_HEAD 三处测试常量与 database-migration.md HEAD 标注同步（原文档标 c8d9e0f1a2b3 已过期 5 个版本）。 2026-08-17：双密钥会话修复——新增 `utils/session.ts`（JWT exp 主动过期判定 + hash 模式登录跳转 URL 构造 + cookie→内存令牌回同步 + visibilitychange/focus 会话监听）；`request.ts` redirectToLogin 改 hash 感知跳转（3 秒防抖窗口自动复位 + 过期 toast）并导出 `trySilentRefresh`；`permission.ts` 守卫前置主动过期检查（过期先续期、失败直接登出，不再依赖 API 401 被动触发）；`user.ts` LogOut 容忍空 token（登出按钮任何状态可用）+ Login 缺 refresh_token 清残留 cookie；`FileManagement.vue` 上传头改响应式 `UserModule.token` + `Authorization: Bearer`（续期/重登录后上传立即携带新令牌）；新增 `session.spec.ts` 并同步 store-user 用例。 2026-08-18：W9 强制改密死锁修复——守卫重定向目标/白名单改真实页面子路由 /settings/index（原父路径落点内容区空白、真实路径被弹回形成死锁）；`/settings` 父路由补 redirect（与守卫改动原子交付，单发会无限循环）；守卫 GetUserInfo 分支补首导航拦截；后端 `/user/info`（cuser.py）实时下发 `mustChangePassword` + 前端 store GetUserInfo 同步（字段缺失不覆盖防滚动部署误清）；settings 页改密成功清 forceChange query。回归：permission-force-change-deadlock.spec（6 用例）+ user-store-must-change-password 扩展 + /users/info 两态。 2026-08-18（第二批）：同内容排查语义修订（v1.0.6.40）——`torrent_helpers.py` 将 tracker/tracker_domain/status 三类行级筛选收进 `_apply_row_display_filters` 闭包：普通列表原位应用行为不变；`same_content_only` 模式延后至分组 join 后仅过滤组内显示行，分组候选集不含这三类筛选（生产案例：20 副本同内容组仅 1 条 error，同内容+status=error 由 0→1）；新增 status/tracker 显示级 API 用例两组，专用套件 11 passed、普通列表回归 35 passed。 2026-08-18（第三批）：跨标签令牌续期竞态修复——`token-refresh.ts` 重写为三态结果（renewed/rejected/transient，`isDefiniteFailure` 仅后端明确 401 判死）+ definite 失败后重读 cookie 追他标签轮换新值有限重试（上限 3）；`request.ts` handleUnauthorized 三分支（renewed 重放/rejected 登出/transient 保留现场）+ redirectToLogin 改用 ExpireSession；`user.ts` 新增 ExpireSession（被动登出保留共享 refresh cookie，防竞态误杀他标签有效令牌）+ GetUserInfo 网络错误 ApiError 原样上抛；`permission.ts` 守卫三态分流 + GetUserInfo 网络错误 `abortNavigation`（next(false) + 手动 NProgress.done 防悬挂）；settings 改密成功 ResetToken 终结会话跳登录；后端 `/auth/refresh` 条件 UPDATE 原子轮换（rowcount=0 即 401，消除并发双成功）。测试：token-refresh 8 用例、request-auth 13、permission-guard 8、settings-change-password 4、后端 test_auth_refresh +1（撤销时间不被覆盖），前端全量 861 passed。 2026-08-18（第四批）：令牌机制对抗审计修复（两轮审计+计划独立审查，v1.0.6.41）——后端：`database.py` init_config_file 对已存在配置缺失才补 login_status_secret/jwt_secret_key（升级 500 炸弹 + 重启杀会话双修，不轮换已有值）；`config.py` `_default_secret_key` 回退链 env→YAML jwt_secret_key→随机 + `_default_config_dir` 引导期共享路径 + 生产护栏条件化放宽（仅 env 与 YAML 均无才拒启）；`login.py` verify_secret 改 `utils.get_login_secret()`；`cuser.py` 业务 401 改码 8 处（2FA 输入错误 400×7、/info 兜底 500×1，保留 token 缺陷 401 两处自愈语义）；新增 `auth/token_cleanup.py` + `refresh_token_cleanup_task.py`（每日 04:30，保留 30 天，种子经 init_db 增量块存量库生效，无迁移）；`auth/utils.py` 缓存条件 total_seconds；config.yaml.example jwt_secret_key 仅注释占位。前端：`user.ts` ExpireSession 保留共享 access cookie（跨标签级联误杀根修，主动登出传播不破坏）+ GetUserInfo 5xx 原样上抛；`permission.ts` isTransientError 扩 5xx + 连续 3 次瞬时中止逃生回落登出（防持久故障首载卡死且 /login 不可达）+ afterEach 清零；`request.ts` 网络错误 toast 3 秒同文案节流；`audit-logs.ts`/`audit.vue` 下载改 axios blob（修前缀/凭证/拦截器三重损坏）；`FileManagement.vue` el-upload 401 续期引导。测试：后端全量 3826 passed/7 skipped（新增 test_init_config_file/test_cuser_business_codes/test_token_cleanup/test_refresh_token_cleanup_task + test_security_config_defaults 扩 9 用例）；前端全量 872 passed；mypy 零新增、black/flake8/eslint/init.sh 通过。
