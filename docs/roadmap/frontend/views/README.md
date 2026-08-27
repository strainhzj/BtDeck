# frontend/views — 页面视图

> 13 个业务模块 + 404.vue。⚠ **以 class-component 为主**（当前实测 76 个，含子组件/mixin）；views 分支仅 2 处 Options API，另 1 处技术债位于 `components/torrents/CompactTable.vue`。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/views/README.md`，命中行即含模块入口 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 主入口 | 一句话职责 |
|--------|--------|-----------|
| 种子管理 torrent | `torrents/index.vue` | 种子管理（最大模块 24 文件）：列表/传统两视图支持 Tracker 主机域名多选和错误单种排查；同 Hash/错误单种快捷操作均直接切换当前表格数据源，复用筛选、排序和行级分页并可退出；两视图共用高级搜索工作区、Tracker 完整详情弹框与状态语义；错误原因 tooltip 滚动主动收起，查询期间全屏蒙版锁定页面滚动；双模式可调列宽（ColumnResizeMixin 拖拽 + localStorage 持久化，qBittorrent 风格严格列宽，手柄样式全局见 styles/torrent-column-resize.scss） |
| 下载器 downloader | `downloader/index.vue` | 下载器节点控制室（16 文件）：状态摘要/筛选操作台/节点矩阵/轮询遥测/响应式动效 |
| Tracker tracker | `tracker/`（4 并列页面） | Tracker 关键词看板/关键词搜索/连通性测试/重宣告配置（13 文件；12 class + ⚠ 1 Options API） |
| 任务管理 tasks | `tasks/index.vue` | 任务管理主页（CRUD + 调度/Cron/Python 类选择）；outcome/stale 模块 helper 经实例方法暴露给 Vue 模板；任务日志统计摘要可折叠并按页签独立 localStorage 持久化；任务日志使用项目标准按钮，查看日志后显示任务筛选，清空恢复全部日志 |
| 审计日志 logs | `logs/audit.vue` | 审计日志查询/筛选/分页 |
| 回收站 recycle-bin | `recycle-bin/index.vue` | ⚠ Options API：回收站（删除任务恢复/彻底删除/分页筛选），搜索区采用孤儿文件页同款 management-panel/filter 结构 |
| 设置 settings | `settings/index.vue` | 全局设置页；改密成功后 ResetToken 终结会话并跳登录（后端已撤销全部 refresh token，L693） |
| 仪表盘 dashboard | `dashboard/index.vue` | 仪表盘聚合统计卡片 |
| 登录 login | `login/index.vue` | 登录页 |
| 查询模板 query-templates | `query-templates/index.vue` | 查询模板列表 + 新增/编辑对话框；行操作收敛为带 tooltip/ARIA 的 Lucide 极简图标按钮 |
| 孤儿文件 orphan-files | `orphan-files/index.vue` | 扫描提交后轮询轻量状态；统计摘要可折叠并按页签独立 localStorage 持久化；文件夹展开时懒加载并独立分页，仅当前可见文件实时统计硬链接；超量批次显示可关闭提醒，不再要求样本复核 |
| 嵌套路由 nested | `nested/*`（7 文件） | 嵌套路由菜单演示 |
| 树形演示 tree | `tree/index.vue` | 树形组件演示页 |
| 404 页面 404 | `404.vue` | 404 页面 |

## torrents/ 详情（最大模块，24 个文件）

| 文件 | 一句话职责 |
|------|-----------|
| `index.vue` | 种子管理主入口（列表模式，class L936，extends mixins(TorrentBatchMixin, SpeedPollingMixin, ColumnResizeMixin, TorrentErrorTooltipDismissMixin)）；展示可配置的“辅种数量”列，兼容 camel/snake 字段并在缺失时显示1；Tracker 主域名筛选、错误单种提示和快捷入口；✨2026-08-20 展示对齐判定：状态列叠加红色“Tracker异常”标签（`showTrackerErrorTag`，error 状态不重复打）、错误原因 tooltip 走共享回退链；✨2026-08-27 筛选命中可视化：`getList()` L1190 追加 `tracker_domain`/`single_error_only` 并沿用当前页 `skip/limit`，响应后 `console.debug('[tracker-filter]')` 观察日志（共享 `countMatchedTrackerRows` 统计命中标记行）；✨2026-08-27 交互修复：L277 查询蒙版全屏锁滚动、L549 错误 tooltip 接入滚动收起 mixin；Tracker 完整详情弹框 L670 调用共享 `components/TrackerDetailCard.vue`，由组件统一标题、关闭按钮、页签、内容区、列结构、状态语义、reannounce 事件、命中行高亮及 `styles/_tracker-table.scss` 视觉样式 |
| `TraditionalView.vue` | 传统表格视图（extends mixins(TorrentBatchMixin, SpeedPollingMixin, ColumnResizeMixin, TorrentErrorTooltipDismissMixin)，L1011）；展示可配置的“辅种数量”列并保留虚拟表格/分页路径；✨2026-08-20 展示对齐判定：状态列叠加红色“Tracker异常”标签（col-status 加宽 90→145px、表 min-width 1435px），状态图标 title 同步提示；Tracker 主域名过滤 L271、快捷入口命令分发 L1902；✨2026-08-27 筛选命中可视化：`getList()` L1342 响应后输出 `[tracker-filter]` 观察日志（共享 `countMatchedTrackerRows`）；✨2026-08-27 交互修复：L309 查询蒙版全屏锁滚动、L561 错误 tooltip 接入滚动收起 mixin；Tracker 完整详情弹框 L746 调用共享 `components/TrackerDetailCard.vue`，由组件统一标题、关闭按钮、页签、内容区、列结构、状态语义、reannounce 事件、命中行高亮及 `styles/_tracker-table.scss` 视觉样式 |
| `../styles/_tracker-table.scss` | `components/TrackerDetailCard.vue` 使用的 Tracker 详情表格视觉 mixin：紧凑字号/间距、状态色、URL 截断和操作列冻结；✨2026-08-27 新增 `tracker-row-matched` 命中行浅主色高亮（sticky 操作列同色跟随、hover 让位）与 `tracker-matched-tag`「命中筛选」标签 |
| `TorrentViewSwitcher.vue` | 视图模式切换器（列表/传统），共享状态含 `showingDuplicates` / `showingSameContent` / `showingSingleErrors`（L60–62、L86–89），切换视图不丢失查询模式 |
| `FileManagement.vue` | 种子文件管理（`FileManagement` L310）：筛选区复用 `management-page` 项目样式；`getBackupDownloaderName` L704 优先展示列表批量返回的当前 downloader nickname，不逐行动态请求 |
| `components/TorrentAddDialog.vue` | 添加种子对话框 |
| `components/BatchTransferDialog.vue` | 批量转移对话框 |
| `components/TrackerOperationDialog.vue` | Tracker 操作对话框；✨2026-08-20 修复 announce 状态判断（原 `=== 'True'` 字面量对中文状态文本恒显“异常”，改用共享 `isTrackerAnnounceSuccess`） |
| `components/TransferDialog.vue` | 转移对话框 |
| `components/TrackerDetailCard.vue` | 列表/传统视图共用的 Tracker 完整详情弹框：标题、关闭按钮、Tracker/文件/Peers 页签、内容区、错误原因提示、Tracker 名称与 URL、Announce/Scrape 状态、汇报按钮及统一状态语义；✨2026-08-27 命中可视化：`matched_domain`（snake/camel 双读）命中行加 `tracker-row-matched` 高亮与「命中筛选」标签（tooltip 显示命中域名）；通过 `layout` 仅控制两种定位方式 |
| `components/SetLocationDialog.vue` | 设置保存位置对话框 |
| `components/GlobalReplaceTrackerDialog.vue` | 全局替换 Tracker 对话框 |
| `components/TorrentDetailDialog.vue` | 种子详情对话框 |
| `components/BatchOperationDialog.vue` | 批量操作对话框 |
| `components/SearchTemplateDialog.vue` | 搜索模板选择对话框 |
| `mixins/torrentBatch.ts` | 批量操作薄封装层；异步删除处理占用跳过统计、提交即刷新与无任务短路 |
| `mixins/columnResize.ts` | 列宽拖拽 mixin（列表/传统两视图共用）：th 右缘手柄拖拽调宽、mouseup 一次性写入 localStorage（key 由子类覆写 `columnWidthStorageKey`，默认宽度覆写 `defaultColumnWidths`）；双击恢复单列默认、`resetColumnWidths` 供列设置菜单整体重置；拖拽中 body 加 `column-resizing` 全局光标，beforeDestroy 成对解绑 |
| `mixins/speedPolling.ts` | 实时速度轮询 mixin：两视图重复的 1 秒链式轮询单点维护（`loadActiveSpeed` 由子类实现），暂停/销毁期间在途请求不再重启定时器，后台标签页停止轮询、恢复可见先补一次刷新 |
| `mixins/errorTooltipDismiss.ts` | 错误原因 tooltip 收起 mixin（50 行）：window 捕获阶段监听 scroll/wheel，滚动时关闭两视图 `torrentErrorTooltips` 引用；beforeDestroy 成对解绑，避免全局监听残留 |
| `utils/torrentBatch.ts` | 批量操作纯函数集合（可单测）；✨2026-08-20 展示对齐判定新增共享 helper：`hasTrackerError` L482、`showTrackerErrorTag` L492（error 状态不打标）、`getTorrentErrorReason` L502（errorReason → tracker 消息 → 兜底回退链，两视图委托调用）；✨2026-08-27 新增 `countMatchedTrackerRows` L492（统计含 tracker 域名筛选命中标记的行数，供两视图 `[tracker-filter]` 观察日志） |
| `utils/traditionalTorrentIdentity.ts` | 任务行标识（infoId + downloaderId + hash） |
| `utils/traditionalStatusFilter.ts` | 传统视图状态筛选 |
| `utils/traditionalVirtualList.ts` | 传统视图虚拟滚动窗口计算 |
| `utils/traditionalPagination.ts` | 传统视图分页常量与归一化 |
| `utils/__tests__/traditionalStatusFilter.spec.ts` | traditionalStatusFilter 回归测试：钉死「全部/活动中」固定项 icon 为 Lucide 图标名（emoji→Lucide 改造契约）并覆盖三个状态筛选映射函数 |

> 重复种子快捷删除对话框不在本模块内：组件实际位于 `src/components/torrents/QuickDeleteDuplicatesDialog.vue`（见 components-layout 分支）。

## downloader/ 详情（16 个文件）

| 文件 | 一句话职责 |
|------|-----------|
| `index.vue` | 下载器节点控制室主入口（`DownloaderManager`）：聚合状态摘要、筛选操作台、节点矩阵、轮询遥测和响应式动效 |
| `components/DownloaderSettingsDialog.vue` | 新增/编辑共用的顶层配置工作区，聚合基础、速度、路径和标签 Tab；新增模式锁定依赖节点 ID 的页签 |
| `components/PathMappingTab.vue` | 高密度双向路径映射 Tab（本地↔远程），含刷新、测试、增删改与空状态 |
| `components/TagManagementTab.vue` | 标签/分类检索、过滤、排序、同步与维护工作台 |
| `components/DownloaderPathManagement.vue` | 下载器路径资产管理面板（筛选、状态、刷新、增删改） |
| `components/SpeedSettingsTab.vue` | 全局与分时段速度策略工作台 |
| `components/AdvancedSettingsTab.vue` | 兼容保留的高级设置 Tab，应用图标已迁移 Lucide |
| `components/TemplateSelectionDialog.vue` | 高密度模板选择对话框，含自定义标题、加载与空状态 |
| `components/BasicSettingsTab.vue` | 兼容保留的基础设置 Tab，应用图标已迁移 Lucide |
| `components/DownloaderCard.vue` | 单节点遥测卡片，集中展示连接、吞吐、任务、延迟与全部管理动作 |
| `components/DownloaderDialog.vue` | 下载器新增/编辑对话框 |
| `components/PathManagementTab.vue` | 路径映射/路径资产双视图容器 |
| `types.ts` | 下载器模块 TS 类型定义 |
| `settings.ts` | 分时段开关/调度规则类型片段 |
| `connection.ts` | 连接测试前置判定 `hasCompleteConnectionInfo`：凭据齐全才允许发起测试，编辑态密码可留空（由后端复用已存加密密码） |
| `path-mapping-rules.ts` | 路径映射规则纯函数 `generateExternalPathFromRules`：按 `source{#**#}target` 规则文本（最长优先匹配）从内部路径生成外部路径 |

## tracker/ 详情（13 个文件）

| 文件 | 一句话职责 |
|------|-----------|
| `reannounce-config.vue` | ⚠ **Options API**（L299 `export default {`）：重新宣告配置页 |
| `keywords-board.vue` | 关键词看板主页面（`TrackerKeywordsBoard`） |
| `test.vue` | Tracker 连通性测试页 |
| `keywords-search.vue` | 关键词搜索页（`KeywordsSearchPage`） |
| `components/KeywordListModal.vue` | 关键词列表弹窗（搜索框右侧含快捷操作入口） |
| `components/ImportKeywordsDialog.vue` | 批量导入关键词对话框 |
| `components/AddKeywordDialog.vue` | 添加关键词对话框 |
| `components/KeywordCard.vue` | 单个关键词卡片 |
| `components/KeywordTagCard.vue` | 关键词标签卡片 |
| `components/KeywordQuickActionDialog.vue` | 关键词快捷操作（左匹配）对话框，看板与详情弹窗共用（预览→二次确认→批量删除/移动） |
| `components/ApiLogViewer.vue` | API 调用日志查看器 |
| `components/MatchTimeline.vue` | 匹配时间线组件 |
| `components/TestResultSummary.vue` | 测试结果汇总 |

## 其余单文件模块

| 模块/文件 | 职责 |
|-----------|------|
| `tasks/index.vue` | 任务管理主页（`TaskManage` L1002）：任务日志统计摘要使用 `btdeck_task_log_stats_collapsed` 持久化折叠状态；`handleViewLogs` L1316 记录可见任务筛选，`resetLogQuery` L1901 / `clearLogTaskFilter` L1917 清除 task_id 并立即查询全部日志；导出/过期清理为标准 Element 按钮 |
| `logs/audit.vue` | 审计日志查询/筛选/分页（`AuditLogs`）；v1.0.6.36 操作日志布局优化（剪贴板回退复制/导出归档入口对齐） |
| `recycle-bin/index.vue` | ⚠ Options API（`RecycleBin`，L373）：回收站，L14 搜索区复用 management-panel/filter UI，支持 Enter、清空与重置 |
| `settings/index.vue` | 全局设置页（`Settings`） |
| `dashboard/index.vue` | 仪表盘聚合统计卡片（`Dashboard`）：系统状态卡显示所有下载器上传/下载速度之和，下载器状态卡显示各自下载/上传速度 |
| `query-templates/index.vue` | 查询模板列表主入口（`QueryTemplates` L188）；L111 行操作使用 play/pencil/trash Lucide 图标与紧凑按钮样式 |
| `query-templates/components/QueryTemplateDialog.vue` | 查询模板新增/编辑对话框；✨2026-08-27 simple 表单补 Tracker 域名多选（AdvancedMultiSelect，options 懒加载 `/torrents/tracker-domains`，编辑回填 + buildConditions 写入，修复模板保存丢失 tracker 筛选） |
| `login/index.vue` | 登录页（`Login`）：使用 D 形 mark + `BtDeck` 字标的 `AppLogo` 横向完整品牌 Logo；桌面/移动登录入口统一品牌资源 |
| `orphan-files/index.vue` | 孤儿文件管理（`OrphanFiles` L948）；统计摘要使用 `btdeck_orphan_file_stats_collapsed` 持久化折叠状态；仅文件夹模式注册展开列，子表隐藏重复表头；`loadFolderChildren` L1209 仅展开时加载子页，`startScanPolling` L1805 轮询后台扫描，`dismissLargeScanReminder` L1269 关闭超量提醒；保留硬链接定位、清理/忽视/隔离恢复 |
| `404.vue` | 404 页面（`Page404`） |
| `nested/*`（7 文件） | 嵌套路由菜单演示（menu1/menu2） |
| `tree/index.vue` | 树形组件演示页（`Tree`） |

---

## ⚠ Options API 技术债（全仓库仅 3 处）

| 文件 | 行号 | 说明 |
|------|------|------|
| `recycle-bin/index.vue` | L373 `export default {` | 回收站页面 |
| `tracker/reannounce-config.vue` | L299 `export default {` | Tracker 重宣告配置页 |
| `components/torrents/CompactTable.vue` | L301 `export default {` | 紧凑表格视图（在 components 分支） |

> 详见 [../../perspectives/risks.md](../../perspectives/risks.md) "文档/代码漂移" 章节。

## 第三层详情

- 本次未产出 views 第三层（建议优先级：`torrents/index.vue` 3018 行主入口、`TraditionalView.vue` 2732 行）
