# 桌面路由 / 弹窗 / 状态清单（P0）

> 生成：2026-09-18；依据 `frontend/src/router.ts`（HEAD 42b81f9）与逐视图静态扫描。
> 移动端 `/m/*` 全部排除（另行立项）；共享组件对移动中文的回归要求见主计划 C01。

## 1. 桌面路由总表

| 路由 | 视图文件 | 标题（现值） | 能力门控 | 批次 | 备注 |
|---|---|---|---|---|---|
| `/login` | `views/login/index.vue` | — | — | **M1** | 含 2FA 登录、错误提示 |
| `/404` | `views/404.vue` | — | — | **M1** | 兜底 `*` → `/404` |
| `/dashboard` | `views/dashboard/index.vue` | 首页 | — | **M1** | 图表图例/tooltip 在内 |
| `/downloader/index` | `views/downloader/index.vue` | 下载器管理 | — | **M1** | 新增/编辑/测试/状态/同步 |
| `/torrents/index` | `views/torrents/TorrentViewSwitcher.vue` | 种子列表 | — | **M1** | 切换器 + 默认视图（详见 §2） |
| `/torrents/detail/:hash` | `views/torrents/index.vue` | 种子详情 | — | **M1** | 页面即详情（非弹窗），含 Tracker 卡片 |
| `/settings/index` | `views/settings/index.vue` | 系统设置 | — | **M1 partial** | 5 页签拆分见 §2.4；强制改密守卫落点（permission.ts 允许 `/settings/index`、`/settings`、`/m/settings`） |
| `/query-templates/index` | `views/query-templates/index.vue` | 查询模板 | — | **M1** | 含 4 个系统预设展示 |
| `/recycle-bin/index` | `views/recycle-bin/index.vue` | 回收站 | `level3_recycle` | **M1** | 查看/恢复/永久删除 |
| `/torrents/traditional` | `views/torrents/TraditionalView.vue` | 种子列表（传统模式） | — | M2 | hidden，切换器入口 |
| `/torrents/file-management` | `views/torrents/FileManagement.vue` | 种子文件管理 | `torrent_backup` | M2 | |
| `/tasks/index`（含 `/task-logs` 重定向 `?tab=logs`） | `views/tasks/index.vue` | 定时任务 | — | M2 | 任务页 391 处命中，全站最大文案源 |
| `/tracker/keywords-board` | `views/tracker/keywords-board.vue` | 关键词看板 | — | M2 | |
| `/tracker/keywords-search` | `views/tracker/keywords-search.vue` | 关键词搜索 | — | M2 | hidden |
| `/tracker/reannounce-config` | `views/tracker/reannounce-config.vue` | 汇报配置 | — | M2 | |
| `/tracker/test` | `views/tracker/test.vue` | 测试工具 | — | M2 | |
| `/logs/audit` | `views/logs/audit.vue` | 操作日志 | — | M2 | 96 处命中；历史审计文本不改写 |
| `/orphan-files/index` | `views/orphan-files/index.vue` | 孤儿文件 | `orphan_files` | M2 | 337 处命中；隔离/恢复/清理语义高风险（R06） |

壳层（所有 M1 路由可达，必译）：`layout/index.vue`、`Navbar`（含退出登录、语言入口落点）、`Sidebar/SidebarItem*`、`Breadcrumb`（`components/Breadcrumb`）、`AppMain`、`NotificationDrawer`（`index.vue` + `NotificationItem.vue`，M1=壳层+核心任务通知可理解，全部系统通知类型 M2）、`Pagination`、`BatchButton`、`ThemeSwitcher`、`Hamburger`、`CollapsiblePanel`、`components/common/`（AppLogo / DemoModeBanner / RefreshPrompt / LucideIcon）。

路由 meta.title 本身是文案（`router.ts` 71 处命中 navigation 组），面包屑与侧栏消费该字段——P1 需把标题改为键或按 `route.name` 映射（方案见 copy-catalog.md §4）。

## 2. M1 页面 × 弹窗 / 状态明细

### 2.1 登录 / 会话（auth）
- `views/login/index.vue`：登录表单 + 2FA 验证码输入；错误提示（`login.py`：429 尝试过多 / 401 用户名或密码错误 / 400 请填写两步验证码 / 401 验证码错误 / 500 系统异常）；无 el-dialog。
- `permission.ts`：强制改密改道（`mustChangePassword` → `/settings/index`）；`utils/request.ts` 401 静默续期 + 三态分流 + 3 秒防抖跳转；刷新 token 失效文案（login.py refresh 分支）。
- 退出登录：Navbar 下拉「退出登录」+ `store` 登出动作提示。

### 2.2 下载器管理（downloader）
- `views/downloader/index.vue`：卡片列表（`DownloaderCard.vue`，M1：状态/在线离线/同步时间）；新增/编辑走 `DownloaderSettingsDialog.vue`（10 个 el-dialog 块，**partial**：基础连接页签 M1，高级设置/限速/标签/路径/映射页签 M2——页面签拆分清单 P2 前补齐）；`TemplateSelectionDialog.vue`（设置模板，M2）；测试连接成功/失败提示（`msg="用户名或密码错误"` 等，见 error-contract.md §3）。
- 状态：列表空态、加载、离线徽标（「离线」dashboard/卡片共用）。

### 2.3 种子列表 + 详情（torrent）
- `TorrentViewSwitcher.vue`：默认/传统视图切换壳（传统视图本体 M2）。
- 默认视图 = `views/torrents/index.vue`（310 处命中，单文件最大 M1 文案源）：
  - 筛选与搜索：`AdvancedSearchWorkspace` / `AdvancedSearchBuilder`（5 个 el-dialog 块）/ `AdvancedMultiSelect` / `FilterGroup` / `ConditionValueInput` / `SizeRangeFilter` / `PageSizeCombobox` / `CompactTable`（98 处）。
  - 行内操作与批量：`BatchButton`、开始/暂停/校验等下拉命令；批量操作 `BatchOperationDialog.vue`。
  - 四级删除：`mixins/torrentBatch.ts`（el-dropdown command → `$confirm`，level 1 用 `type:'error'`）+ `utils/torrentBatch.ts` `buildDeleteConfirmMessage()`（确认消息构建器，97 处命中文件）。**桌面无独立 DeleteLevelDialog**（移动端才有 `mobile/components/DeleteLevelDialog.vue`）。
  - 去重快速删除：`QuickDeleteDuplicatesDialog.vue`（M1 候选，见 §3 待定项）；`DuplicateTorrentsDialog.vue`（重复扫描入口，M1 候选）。
  - Tracker 卡片：`TrackerDetailCard.vue`（73 处，含媒体库页签）+ `TrackerOperationDialog.vue`（批量添加/修改 Tracker）+ 汇报（reannounce）——M1「Tracker 异常状态、原始详情、常用汇报」范围。
  - 状态：v-loading、空态、错误 tooltip（`mixins/errorTooltipDismiss.ts`）、列宽提示文案、速度轮询（`mixins/speedPolling.ts`）。
- 添加种子：`TorrentAddDialog.vue`（自定义 modal 非 el-dialog；含「跳过校验」复选框）。
- 详情页共用上述种子页组件（`TorrentDetailDialog.vue` 2 处 el-dialog 亦在链路）。

### 2.4 系统设置（settings，partial）
5 个页签：`双因素认证(2fa)` / `修改密码(password)` = **M1**；`MCP 服务(mcp)` / `MoviePilot(moviepilot)`（`McpSettingsPanel.vue`、`MoviePilotPanel.vue`）= **M2**；`状态诊断(diagnosis)` = 待定（见 §3）。首次登录强制改密落在「修改密码」页签，英文用户 A01 验收即此路径。

### 2.5 查询模板（search）
- `views/query-templates/index.vue` + `QueryTemplateDialog.vue`：列表/新建/编辑/删除/应用；系统预设行展示（名称/描述的翻译映射见 system-content.md §2）。

### 2.6 回收站（recycleBin）
- `views/recycle-bin/index.vue`（123 处命中）：列表/筛选/恢复/彻底删除/清空；6 个 el-dialog 块；v-loading×2；降级与部分失败语义高风险（R03/R05）。

## 3. M1 边界待定项（需用户拍板，不阻塞 P0 记录）

| 项 | 建议 | 理由 |
|---|---|---|
| `QuickDeleteDuplicatesDialog` / `DuplicateTorrentsDialog` | **M1**（倾向） | 属「常用批量操作」；从默认列表一键可达 |
| `SetLocationDialog`（修改路径）/ `TransferDialog` / `BatchTransferDialog` | **M2** | 主计划矩阵「复杂转移」M2；桌面默认视图未暴露 |
| `GlobalReplaceTrackerDialog` | **M2** | 属 Tracker 管理深功能，非「常用汇报」 |
| settings `状态诊断` 页签 | **M1**（倾向） | 排障自洽性；英文用户遇连接问题需读懂诊断 |
| `DownloaderSettingsDialog` 页签级拆分 | P2 前补齐 | 「接入必需部分」的精确页签清单 |

## 4. 口径与已知偏差

- 弹窗计数 = `el-dialog` 出现次数（含嵌套确认框），非独立弹窗数；`$confirm/$alert/$prompt` 另计（torrents/index.vue 6 处、settings 2 处、query-templates 1 处、NotificationDrawer 4 处等）。
- 空态/加载态扫描仅覆盖 `el-empty`/`v-loading`；自定义空态组件（如 CompactTable 内置）以页面实测为准，P1 落键时逐页补扫。
- 移动端复用的共享组件（`TrackerDetailCard`、`TorrentAddDialog`、`TransferDialog`、`SetLocationDialog`、`GlobalReplaceTrackerDialog`、`DownloaderSettingsDialog`）改动后必须回归移动中文（C01），已在主计划约束，无需在此重复枚举。
