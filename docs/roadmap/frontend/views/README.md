# frontend/views — 页面视图

> 13 个业务模块 + 404.vue。⚠ **以 class-component 为主**（53 个），仅 3 处 Options API（技术债候选）。

## 模块总览

| 模块 | 文件数 | 总行数 | 主入口 | 范式 |
|------|--------|--------|--------|------|
| torrents | 20 | 11,189 | `index.vue`（2,662 行） | class-component（全部） |
| downloader | 14 | 11,277 | `index.vue`（1,644 行） | class-component（全部） |
| tracker | 12 | 5,357 | 4 个并列页面 | class-component（11）+ ⚠ 1 Options API |
| tasks | 1 | 2,408 | `index.vue` | class-component |
| logs | 1 | 1,266 | `audit.vue` | class-component |
| recycle-bin | 1 | 1,179 | `index.vue` | ⚠ **Options API** |
| settings | 1 | 992 | `index.vue` | class-component |
| dashboard | 1 | 955 | `index.vue` | class-component |
| login | 1 | 534 | `index.vue` | class-component |
| query-templates | 2 | 544 | `index.vue`（v1.0.5 新增） | class-component |
| orphan-files | 1 | 1,543 | `index.vue` | class-component |
| nested | 7 | 140 | 菜单演示 | class-component |
| tree | 1 | 80 | `index.vue` | class-component |
| 404.vue（顶层） | 1 | 340 | `404.vue` | class-component |

## torrents/ 详情（最大模块，20 个文件）

| 文件 | 行数 | 范式 | 一句话职责 |
|------|------|------|-----------|
| `index.vue` | 2662 | class（`TorrentsManagement`，L652 `@Component`，L666 `extends mixins(TorrentBatchMixin)`） | 种子管理主入口（列表模式）；v1.0.6.30 接入共享 `PageSizeCombobox` + 5 列头服务端排序（首次降序/同字段切换升降序），高级搜索标题在 v1.0.6.29 收紧为 16px 图标 + 15px 文字 |
| `TraditionalView.vue` | 2458 | class（L847 `extends mixins(TorrentBatchMixin)`） | 传统表格视图；v1.0.6.30 复用共享 `PageSizeCombobox`（保留原分页状态/虚拟滚动/重复任务），v1.0.6.31 在“分类/标签”与“添加时间”之间新增保存路径列（兼容 `savePath/save_path`） |
| `TorrentViewSwitcher.vue` | 106 | class | 视图模式切换器（列表/传统） |
| `FileManagement.vue` | 812 | class（L312 `extends Vue`） | 种子文件管理（选择/优先级） |
| `components/TorrentAddDialog.vue` | 801 | class | 添加种子对话框 |
| `components/BatchTransferDialog.vue` | 629 | class | 批量转移对话框 |
| `components/TrackerOperationDialog.vue` | 457 | class | Tracker 操作对话框 |
| `components/TransferDialog.vue` | 430 | class | 转移对话框 |
| `components/TrackerDetailCard.vue` | 394 | class | Tracker 详情卡片 |
| `components/SetLocationDialog.vue` | 342 | class | 设置保存位置对话框 |
| `components/GlobalReplaceTrackerDialog.vue` | 254 | class | 全局替换 Tracker 对话框 |
| `components/TorrentDetailDialog.vue` | 171 | class | 种子详情对话框 |
| `components/BatchOperationDialog.vue` | 148 | class | 批量操作对话框 |
| `components/SearchTemplateDialog.vue` | 93 | class | 搜索模板选择对话框 |
| `mixins/torrentBatch.ts` | 299 | class-based Mixin | 批量操作薄封装层（注入 API/绑定 this/统一文案） |
| `utils/torrentBatch.ts` | 905 | util（纯函数） | 批量操作纯函数集合（可单测） |
| `utils/traditionalTorrentIdentity.ts` | 107 | util | 任务行标识（infoId + downloaderId + hash） |
| `utils/traditionalStatusFilter.ts` | 46 | util | 传统视图状态筛选 |
| `utils/traditionalVirtualList.ts` | 57 | util | 传统视图虚拟滚动窗口计算 |
| `utils/traditionalPagination.ts` | 18 | util | 传统视图分页常量与归一化 |

## downloader/ 详情（14 个文件）

| 文件 | 行数 | 范式 | 一句话职责 |
|------|------|------|-----------|
| `index.vue` | 1644 | class（`DownloaderManager`） | 下载器节点控制室主入口；聚合状态摘要、筛选操作台、节点矩阵、轮询遥测和响应式动效 |
| `components/DownloaderSettingsDialog.vue` | 2215 | class | 新增/编辑共用的顶层配置工作区，聚合基础、速度、路径和标签 Tab；新增模式锁定依赖节点 ID 的页签 |
| `components/PathMappingTab.vue` | 1097 | class | 高密度双向路径映射 Tab（本地↔远程），含刷新、测试、增删改与空状态 |
| `components/TagManagementTab.vue` | 1219 | class | 标签/分类检索、过滤、排序、同步与维护工作台 |
| `components/DownloaderPathManagement.vue` | 959 | class | 下载器路径资产管理面板（筛选、状态、刷新、增删改） |
| `components/SpeedSettingsTab.vue` | 906 | class | 全局与分时段速度策略工作台 |
| `components/AdvancedSettingsTab.vue` | 512 | class | 兼容保留的高级设置 Tab，应用图标已迁移 Lucide |
| `components/TemplateSelectionDialog.vue` | 744 | class | 高密度模板选择对话框，含自定义标题、加载与空状态 |
| `components/BasicSettingsTab.vue` | 405 | class | 兼容保留的基础设置 Tab，应用图标已迁移 Lucide |
| `components/DownloaderCard.vue` | 692 | class | 单节点遥测卡片，集中展示连接、吞吐、任务、延迟与全部管理动作 |
| `components/DownloaderDialog.vue` | 335 | class | 下载器新增/编辑对话框 |
| `components/PathManagementTab.vue` | 174 | class | 路径映射/路径资产双视图容器 |
| `types.ts` | 363 | util | 下载器模块 TS 类型定义 |
| `settings.ts` | 12 | util | 分时段开关/调度规则类型片段 |

## tracker/ 详情（12 个文件）

| 文件 | 行数 | 范式 | 一句话职责 |
|------|------|------|-----------|
| `reannounce-config.vue` | 845 | ⚠ **Options API**（L299 `export default {`） | 重新宣告配置页 |
| `keywords-board.vue` | 808 | class（`TrackerKeywordsBoard`） | 关键词看板主页面 |
| `test.vue` | 827 | class | Tracker 连通性测试页 |
| `keywords-search.vue` | 693 | class（`KeywordsSearchPage`） | 关键词搜索页 |
| `components/KeywordListModal.vue` | 619 | class | 关键词列表弹窗 |
| `components/ImportKeywordsDialog.vue` | 567 | class | 批量导入关键词对话框 |
| `components/AddKeywordDialog.vue` | 278 | class | 添加关键词对话框 |
| `components/KeywordCard.vue` | 134 | class | 单个关键词卡片 |
| `components/KeywordTagCard.vue` | 128 | class | 关键词标签卡片 |
| `components/ApiLogViewer.vue` | 184 | class | API 调用日志查看器 |
| `components/MatchTimeline.vue` | 121 | class | 匹配时间线组件 |
| `components/TestResultSummary.vue` | 114 | class | 测试结果汇总 |

## 其余单文件模块

| 模块/文件 | 行数 | class name | 职责 |
|-----------|------|-----------|------|
| `tasks/index.vue` | 2408 | `TaskManage` | 任务管理主页（CRUD + 调度/Cron/Python 类选择） |
| `logs/audit.vue` | 1266 | `AuditLogs` | 审计日志查询/筛选/分页；v1.0.6.36 操作日志布局优化（剪贴板回退复制/导出归档入口对齐） |
| `recycle-bin/index.vue` | 1179 | ⚠ Options API（`RecycleBin`，L374） | 回收站，删除任务恢复/彻底删除/分页筛选 |
| `settings/index.vue` | 992 | `Settings` | 全局设置页 |
| `dashboard/index.vue` | 955 | `Dashboard` | 仪表盘聚合统计卡片 |
| `query-templates/index.vue` | 272 | `QueryTemplates`（v1.0.5） | 查询模板列表主入口 |
| `query-templates/components/QueryTemplateDialog.vue` | 272 | class | 查询模板新增/编辑对话框 |
| `login/index.vue` | 534 | `Login` | 登录页 |
| `orphan-files/index.vue` | 1543 | `OrphanFiles` | 孤儿文件扫描/筛选/清理/忽视/隔离恢复；内部滚动固定表头并采用可视窗口渲染大页（v1.0.6.34~36 真全选/固定表头/大分页交互优化），忽视展示逐项失败原因；彻底删除只提交后台任务 |
| `404.vue` | 340 | `Page404` | 404 页面 |
| `nested/*`（7 文件） | 140 | class | 嵌套路由菜单演示（menu1/menu2） |
| `tree/index.vue` | 80 | `Tree` | 树形组件演示页 |

---

## ⚠ Options API 技术债（全仓库仅 3 处）

| 文件 | 行号 | 说明 |
|------|------|------|
| `recycle-bin/index.vue` | L374 `export default {` | 回收站页面 |
| `tracker/reannounce-config.vue` | L299 `export default {` | Tracker 重宣告配置页 |
| `components/torrents/CompactTable.vue` | L301 `export default {` | 紧凑表格视图（在 components 分支） |

> 详见 [../../perspectives/risks.md](../../perspectives/risks.md) "文档/代码漂移" 章节。

## 第三层详情

- 本次未产出 views 第三层（建议优先级：`torrents/index.vue` 2504 行主入口、`TraditionalView.vue` 2561 行）
