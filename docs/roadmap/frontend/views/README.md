# frontend/views — 页面视图

> 13 个业务模块 + 404.vue。⚠ **以 class-component 为主**（53 个），仅 3 处 Options API（技术债候选）。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/views/README.md`，命中行即含模块入口 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 主入口 | 一句话职责 |
|--------|--------|-----------|
| 种子管理 torrent | `torrents/index.vue` | 种子管理（最大模块 20 文件）：列表/传统两视图保留同 Hash 重复查询；快捷操作“同内容异常排查”直接切换当前表格到 `same_content_only` 数据源，复用筛选、排序和行级分页并可退出；两视图仍共用高级搜索工作区 |
| 下载器 downloader | `downloader/index.vue` | 下载器节点控制室（14 文件）：状态摘要/筛选操作台/节点矩阵/轮询遥测/响应式动效 |
| Tracker tracker | `tracker/`（4 并列页面） | Tracker 关键词看板/关键词搜索/连通性测试/重宣告配置（12 文件；11 class + ⚠ 1 Options API） |
| 任务管理 tasks | `tasks/index.vue` | 任务管理主页（CRUD + 调度/Cron/Python 类选择）；outcome/stale 模块 helper 经实例方法暴露给 Vue 模板；任务日志使用项目标准按钮，查看日志后显示任务筛选，清空恢复全部日志 |
| 审计日志 logs | `logs/audit.vue` | 审计日志查询/筛选/分页 |
| 回收站 recycle-bin | `recycle-bin/index.vue` | ⚠ Options API：回收站（删除任务恢复/彻底删除/分页筛选），搜索区采用孤儿文件页同款 management-panel/filter 结构 |
| 设置 settings | `settings/index.vue` | 全局设置页 |
| 仪表盘 dashboard | `dashboard/index.vue` | 仪表盘聚合统计卡片 |
| 登录 login | `login/index.vue` | 登录页 |
| 查询模板 query-templates | `query-templates/index.vue` | 查询模板列表 + 新增/编辑对话框；行操作收敛为带 tooltip/ARIA 的 Lucide 极简图标按钮 |
| 孤儿文件 orphan-files | `orphan-files/index.vue` | 扫描提交后轮询轻量状态；文件夹展开时懒加载并独立分页，仅当前可见文件实时统计硬链接；超量批次显示路径映射/样本复核入口 |
| 嵌套路由 nested | `nested/*`（7 文件） | 嵌套路由菜单演示 |
| 树形演示 tree | `tree/index.vue` | 树形组件演示页 |
| 404 页面 404 | `404.vue` | 404 页面 |

## torrents/ 详情（最大模块，20 个文件）

| 文件 | 一句话职责 |
|------|-----------|
| `index.vue` | 种子管理主入口（列表模式，class L842）；同内容提示/退出 L71、快捷入口 L192、命令分发 L1186；`getList()` L1038 追加 `same_content_only` 并沿用当前页 `skip/limit` |
| `components/QuickDeleteDuplicatesDialog.vue` | 重复种子快捷删除；提交后触发父列表刷新，nullable task_id 时仅提示而不轮询 |
| `TraditionalView.vue` | 传统表格视图（extends mixins(TorrentBatchMixin)，L890）；同内容提示/退出 L212、快捷入口 L203、命令分发 L1724；`getList()` L1175 追加列表筛选并保留虚拟表格/分页路径 |
| `TorrentViewSwitcher.vue` | 视图模式切换器（列表/传统），共享状态含 `showingDuplicates` / `showingSameContent`（L60–61、L86–87），切换视图不丢失查询模式 |
| `FileManagement.vue` | 种子文件管理（`FileManagement` L310）：筛选区复用 `management-page` 项目样式；`getBackupDownloaderName` L682 优先展示列表批量返回的当前 downloader nickname，不逐行动态请求 |
| `components/TorrentAddDialog.vue` | 添加种子对话框 |
| `components/BatchTransferDialog.vue` | 批量转移对话框 |
| `components/TrackerOperationDialog.vue` | Tracker 操作对话框 |
| `components/TransferDialog.vue` | 转移对话框 |
| `components/TrackerDetailCard.vue` | Tracker 详情卡片 |
| `components/SetLocationDialog.vue` | 设置保存位置对话框 |
| `components/GlobalReplaceTrackerDialog.vue` | 全局替换 Tracker 对话框 |
| `components/TorrentDetailDialog.vue` | 种子详情对话框 |
| `components/BatchOperationDialog.vue` | 批量操作对话框 |
| `components/SearchTemplateDialog.vue` | 搜索模板选择对话框 |
| `mixins/torrentBatch.ts` | 批量操作薄封装层；异步删除处理占用跳过统计、提交即刷新与无任务短路 |
| `utils/torrentBatch.ts` | 批量操作纯函数集合（可单测） |
| `utils/traditionalTorrentIdentity.ts` | 任务行标识（infoId + downloaderId + hash） |
| `utils/traditionalStatusFilter.ts` | 传统视图状态筛选 |
| `utils/traditionalVirtualList.ts` | 传统视图虚拟滚动窗口计算 |
| `utils/traditionalPagination.ts` | 传统视图分页常量与归一化 |

## downloader/ 详情（14 个文件）

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

## tracker/ 详情（12 个文件）

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
| `tasks/index.vue` | 任务管理主页（`TaskManage` L997）：`handleViewLogs` L1311 记录可见任务筛选，`resetLogQuery` L1896 / `clearLogTaskFilter` L1912 清除 task_id 并立即查询全部日志；导出/过期清理为标准 Element 按钮 |
| `logs/audit.vue` | 审计日志查询/筛选/分页（`AuditLogs`）；v1.0.6.36 操作日志布局优化（剪贴板回退复制/导出归档入口对齐） |
| `recycle-bin/index.vue` | ⚠ Options API（`RecycleBin`，L369）：回收站，L14 搜索区复用 management-panel/filter UI，支持 Enter、清空与重置 |
| `settings/index.vue` | 全局设置页（`Settings`） |
| `dashboard/index.vue` | 仪表盘聚合统计卡片（`Dashboard`）：系统状态卡显示所有下载器上传/下载速度之和，下载器状态卡显示各自下载/上传速度 |
| `query-templates/index.vue` | 查询模板列表主入口（`QueryTemplates` L188）；L111 行操作使用 play/pencil/trash Lucide 图标与紧凑按钮样式 |
| `query-templates/components/QueryTemplateDialog.vue` | 查询模板新增/编辑对话框 |
| `login/index.vue` | 登录页（`Login`） |
| `orphan-files/index.vue` | 孤儿文件管理（`OrphanFiles` L896）；`loadFolderChildren` L1149 仅展开时加载子页，`startScanPolling` L1639 轮询后台扫描，`handleGuardrailReview` L1685 记录双确认复核；保留硬链接定位、清理/忽视/隔离恢复 |
| `404.vue` | 404 页面（`Page404`） |
| `nested/*`（7 文件） | 嵌套路由菜单演示（menu1/menu2） |
| `tree/index.vue` | 树形组件演示页（`Tree`） |

---

## ⚠ Options API 技术债（全仓库仅 3 处）

| 文件 | 行号 | 说明 |
|------|------|------|
| `recycle-bin/index.vue` | L369 `export default {` | 回收站页面 |
| `tracker/reannounce-config.vue` | L299 `export default {` | Tracker 重宣告配置页 |
| `components/torrents/CompactTable.vue` | L301 `export default {` | 紧凑表格视图（在 components 分支） |

> 详见 [../../perspectives/risks.md](../../perspectives/risks.md) "文档/代码漂移" 章节。

## 第三层详情

- 本次未产出 views 第三层（建议优先级：`torrents/index.vue` 2807 行主入口、`TraditionalView.vue` 2583 行）
