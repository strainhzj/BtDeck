# frontend/views — 页面视图

> 13 个业务模块 + 404.vue。⚠ **以 class-component 为主**（53 个），仅 3 处 Options API（技术债候选）。

## 模块总览

| 模块 | 文件数 | 总行数 | 主入口 | 范式 |
|------|--------|--------|--------|------|
| torrents | 20 | 11,143 | `index.vue`（2,539 行） | class-component（全部） |
| downloader | 14 | 8,409 | `index.vue`（824 行） | class-component（全部） |
| tracker | 12 | 5,357 | 4 个并列页面 | class-component（11）+ ⚠ 1 Options API |
| tasks | 1 | 2,419 | `index.vue` | class-component |
| logs | 1 | 1,116 | `audit.vue` | class-component |
| recycle-bin | 1 | 1,179 | `index.vue` | ⚠ **Options API** |
| settings | 1 | 992 | `index.vue` | class-component |
| dashboard | 1 | 955 | `index.vue` | class-component |
| login | 1 | 534 | `index.vue` | class-component |
| query-templates | 2 | 544 | `index.vue`（v1.0.5 新增） | class-component |
| orphan-files | 1 | 475 | `index.vue` | class-component |
| nested | 7 | 140 | 菜单演示 | class-component |
| tree | 1 | 80 | `index.vue` | class-component |
| 404.vue（顶层） | 1 | 340 | `404.vue` | class-component |

## torrents/ 详情（最大模块，20 个文件）

| 文件 | 行数 | 范式 | 一句话职责 |
|------|------|------|-----------|
| `index.vue` | 2539 | class（`TorrentsManagement`，L642 `@Component`，L656 `extends mixins(TorrentBatchMixin)`） | 种子管理主入口（列表模式） |
| `TraditionalView.vue` | 2557 | class（L847 `extends mixins(TorrentBatchMixin)`） | 传统表格视图 |
| `TorrentViewSwitcher.vue` | 106 | class | 视图模式切换器（列表/传统） |
| `FileManagement.vue` | 812 | class（L312 `extends Vue`） | 种子文件管理（选择/优先级） |
| `components/TorrentAddDialog.vue` | 801 | class | 添加种子对话框 |
| `components/BatchTransferDialog.vue` | 629 | class | 批量转移对话框 |
| `components/TrackerOperationDialog.vue` | 457 | class | Tracker 操作对话框 |
| `components/TransferDialog.vue` | 430 | class | 转移对话框 |
| `components/TrackerDetailCard.vue` | 394 | class | Tracker 详情卡片 |
| `components/SetLocationDialog.vue` | 342 | class | 设置保存位置对话框 |
| `components/GlobalReplaceTrackerDialog.vue` | 254 | class | 全局替换 Tracker 对话框 |
| `components/TorrentDetailDialog.vue` | 163 | class | 种子详情对话框 |
| `components/BatchOperationDialog.vue` | 148 | class | 批量操作对话框 |
| `components/SearchTemplateDialog.vue` | 93 | class | 搜索模板选择对话框 |
| `mixins/torrentBatch.ts` | 299 | class-based Mixin | 批量操作薄封装层（注入 API/绑定 this/统一文案） |
| `utils/torrentBatch.ts` | 896 | util（纯函数） | 批量操作纯函数集合（可单测） |
| `utils/traditionalTorrentIdentity.ts` | 107 | util | 任务行标识（infoId + downloaderId + hash） |
| `utils/traditionalStatusFilter.ts` | 46 | util | 传统视图状态筛选 |
| `utils/traditionalVirtualList.ts` | 57 | util | 传统视图虚拟滚动窗口计算 |
| `utils/traditionalPagination.ts` | 18 | util | 传统视图分页常量与归一化 |

## downloader/ 详情（14 个文件）

| 文件 | 行数 | 范式 | 一句话职责 |
|------|------|------|-----------|
| `index.vue` | 824 | class（`DownloaderManager`） | 下载器管理主入口 |
| `components/DownloaderSettingsDialog.vue` | 1512 | class | 设置总对话框（聚合多 Tab） |
| `components/PathMappingTab.vue` | 989 | class | 路径映射 Tab（本地↔远程） |
| `components/TagManagementTab.vue` | 1049 | class | 标签管理 Tab |
| `components/DownloaderPathMaintenance.vue` | 819 | class | 下载器路径管理面板 |
| `components/SpeedSettingsTab.vue` | 712 | class | 速度限制 Tab |
| `components/AdvancedSettingsTab.vue` | 529 | class | 高级设置 Tab |
| `components/TemplateSelectionDialog.vue` | 499 | class | 下载器模板选择对话框 |
| `components/BasicSettingsTab.vue` | 423 | class | 基础设置 Tab |
| `components/DownloaderCard.vue` | 438 | class | 单个下载器卡片 |
| `components/DownloaderDialog.vue` | 335 | class | 下载器新增/编辑对话框 |
| `components/PathManagementTab.vue` | 168 | class | 路径管理 Tab |
| `types.ts` | 346 | util | 下载器模块 TS 类型定义 |
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
| `tasks/index.vue` | 2419 | `TaskManage` | 任务管理主页（CRUD + 调度/Cron/Python 类选择） |
| `logs/audit.vue` | 1116 | `AuditLogs` | 审计日志查询/筛选/分页 |
| `recycle-bin/index.vue` | 1179 | ⚠ Options API（`RecycleBin`，L374） | 回收站，删除任务恢复/彻底删除/分页筛选 |
| `settings/index.vue` | 992 | `Settings` | 全局设置页 |
| `dashboard/index.vue` | 955 | `Dashboard` | 仪表盘聚合统计卡片 |
| `query-templates/index.vue` | 272 | `QueryTemplates`（v1.0.5） | 查询模板列表主入口 |
| `query-templates/components/QueryTemplateDialog.vue` | 272 | class | 查询模板新增/编辑对话框 |
| `login/index.vue` | 534 | `Login` | 登录页 |
| `orphan-files/index.vue` | 475 | `OrphanFiles` | 孤立文件清理/回收 |
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

- 本次未产出 views 第三层（建议优先级：`torrents/index.vue` 2539 行主入口、`TraditionalView.vue` 2557 行）
