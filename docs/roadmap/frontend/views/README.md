# frontend/views — 页面视图

> 13 个业务模块 + 404.vue。⚠ **以 class-component 为主**（当前实测 74 个，含子组件/mixin，2026-09-21 重测）；views 分支仅 2 处 Options API（原第 3 处 CompactTable.vue 已于 2026-09-20 P6-5 删除）。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/views/README.md`，命中行即含模块入口 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 主入口 | 一句话职责 |
|--------|--------|-----------|
| 种子管理 torrent | `torrents/index.vue` | 种子管理（最大模块 25 文件）：列表/传统两视图支持 Tracker 主机域名多选和错误单种排查；同 Hash/错误单种快捷操作均直接切换当前表格数据源，复用筛选、排序和行级分页并可退出；两视图共用高级搜索工作区、Tracker 完整详情弹框与状态语义；错误原因 tooltip 滚动主动收起，查询期间全屏蒙版锁定页面滚动；双模式可调列宽（ColumnResizeMixin 拖拽 + localStorage 持久化，qBittorrent 风格严格列宽，手柄样式全局见 styles/torrent-column-resize.scss）；实时速度 200/206 快照按 downloader_id+hash 合并，终态证据强制 100%，连续未命中任务低频核验；新活动复合键与批量添加完成信号均可触发权威列表自愈刷新 |；2026-09-21 P3-1 双语：筛选/排查条/工具栏/列头/分页/列设置/视图切换与操作反馈（删除确认与结果链路留 P5），columnSettings 去 label 改键渲染
| 下载器 downloader | `downloader/index.vue` | 下载器节点控制室（16 文件）：状态摘要/筛选操作台/节点矩阵/轮询遥测/响应式动效；手动同步按钮在后台任务终态前保持占用，与移动页共用 `sync-task.ts` 跟踪真实结果；✨2026-09-18 桌面双语 P2：页面文案/图例/空态/卡片/设置弹窗 basic 页签全量 i18n 化；✨2026-09-19 遗留清扫：控制台操作反馈 17 条键化（测试连接三态/同步链路/启停/删除确认走 downloader.msg.*，禁 response.msg 中文兜底）；✨2026-09-19 P6-2：设置弹窗页签骨架与速度/高级/路径管理/路径映射/路径维护/标签/模板八子树全量键化（含键化数据数组与 template-presets 预设展示映射），BasicSettingsTab.vue 死代码删除；✨2026-09-21 移动表单顺序：连接配置卡 ≤780 折单列时地址上移至端口上方（flex column + el-row display:contents + col-* order 重排，卡片水平内边距 12px→4px 补偿 gutter；桌面双列不变） |
| Tracker tracker | `tracker/`（4 并列页面） | Tracker 关键词看板/关键词搜索/连通性测试/重宣告配置（13 文件；12 class + ⚠ 1 Options API）；✨2026-09-20 双语 P6-3：全域全量 i18n（错误展示接 apiErrorMessage/apiResponseMessage） |
| 任务管理 tasks | `tasks/index.vue` | 任务管理主页（CRUD + 调度/Cron/Python 类选择）；outcome/stale 模块 helper 经实例方法暴露给 Vue 模板；任务日志统计摘要可折叠并按页签独立 localStorage 持久化；任务日志使用项目标准按钮，查看日志后显示任务筛选，清空恢复全部日志；✨2026-09-20 双语 P6-4a：模板/脚本全量走 tasks.* 键（任务状态展示按 taskStatus 码位、类型名按 taskType 码位、分页分片键、危险确认「不可恢复」明示），错误展示接 apiErrorMessage/apiResponseMessage |
| 审计日志 logs | `logs/audit.vue` | 审计日志查询/筛选/分页；✨2026-09-20 双语 P6-4b 全量 i18n（筛选/操作栏/统计/表头/详情与归档弹窗；操作类型 19 项按稳定 value 键化双形态（短标签/筛选长标签）；错误展示接 apiResponseMessage/apiErrorMessage） |
| 回收站 recycle-bin | `recycle-bin/index.vue` | ⚠ Options API：回收站（删除任务恢复/彻底删除/分页筛选）；路由由 `level3_recycle` 能力门控；✨2026-09-19 双语 P5 全量双语（recycleBin 模块 78 键：筛选/工具栏/表格/清理预览/手动上传弹窗/危险确认链路/三态结果；错误展示走 apiErrorMessage/apiResponseMessage 禁中文 msg 直读） |
| 设置 settings | `settings/index.vue` | 全局设置页；改密成功后 ResetToken 终结会话并跳登录（后端已撤销全部 refresh token）；2FA 二维码缺失（Pillow 不可用信封）时降级手动录入块（secret+复制+TOTP 参数，2026-09-04）；✨2026-09-18 桌面双语 P2：2FA/改密/诊断页签文案全量 i18n 化；✨2026-09-22 dev1.0.7 合入：新增 MCP 服务与 MoviePilot 页签（自治面板；213bafa 双语化后中文硬编码清零），移除主机能力页签（282f494）；✨2026-09-23 UI 重构：页签改左侧垂直导航（窄屏/移动复用时切顶部横排），各页签卡片壳/标题/描述统一继承 `styles/settings-panel.scss` |
| 仪表盘 dashboard | `dashboard/index.vue` | 仪表盘聚合统计卡片 |；2026-09-21 P3-1 双语（卡片/状态/快捷操作/aria + 本地化日期）
| 登录 login | `login/index.vue` | 登录页；✨2026-09-18 桌面双语 P2：表单/校验/消息 i18n 化；✨2026-09-21 语言切换改 Navbar 同款下拉胶囊（languages 图标+当前语言+chevron），与主题切换收进右上角 topbar flex 容器（根除旧 52px 魔法偏移与主题胶囊重叠；动作源 SetLanguage 不变） |
| 查询模板 query-templates | `query-templates/index.vue` | 查询模板列表 + 新增/编辑对话框；行操作收敛为带 tooltip/ARIA 的 Lucide 极简图标按钮；✨2026-09-23 菜单归入种子管理组（`/torrents/query-templates`，位于种子列表与种子文件管理之间，旧顶层深链 redirect 兑底） |
| 孤儿文件 orphan-files | `orphan-files/index.vue` | 扫描提交后轮询轻量状态；桌面端保留稳定明细/硬链接/隔离流程，路由与移动页由 `orphan_files` 能力门控；✨2026-09-20 双语 P6-4b 全量 i18n（双页签/统计/扫描状态 alert/筛选/工具栏/两种表格/隔离区/副本位置/清理确认/快捷操作弹窗；状态与置信度按稳定码位；E01 拒绝/部分失败明细转 console；错误展示接契约入口） |
| 嵌套路由 nested | `nested/*`（7 文件） | 嵌套路由菜单演示 |
| 树形演示 tree | `tree/index.vue` | 树形组件演示页 |
| 404 页面 404 | `404.vue` | 404 页面 |

## torrents/ 详情（最大模块，24 个文件）

| 文件 | 一句话职责 |
|------|-----------|
| `index.vue` | 种子管理主入口（列表模式，class L946，extends mixins(TorrentBatchMixin, SpeedPollingMixin, ColumnResizeMixin, TorrentErrorTooltipDismissMixin, TrackerDetailDataMixin)）；展示可配置的“辅种数量”列，兼容 camel/snake 字段并在缺失时显示1；Tracker 主域名筛选、错误单种提示和快捷入口；✨2026-08-20 展示对齐判定：状态列叠加红色“Tracker异常”标签（`showTrackerErrorTag`，error 状态不重复打）、错误原因 tooltip 走共享回退链；✨2026-08-27 筛选命中可视化：`getList()` L1209 追加 `tracker_domain`/`single_error_only` 并沿用当前页 `skip/limit`，响应后 `console.debug('[tracker-filter]')` 观察日志（共享 `countMatchedTrackerRows` 统计命中标记行）；✨2026-08-27 交互修复：L277 查询蒙版全屏锁滚动、L549 错误 tooltip 接入滚动收起 mixin；Tracker 完整详情弹框 L670 调用共享 `components/TrackerDetailCard.vue`，由组件统一标题、关闭按钮、页签、内容区、列结构、状态语义、reannounce 事件、命中行高亮及 `styles/_tracker-table.scss` 视觉样式；✨2026-08-29 速度快照支持 206 增量，按复合键更新 status/progress，连续完整快照未命中时调用 runtime-state/reconcile；✨2026-08-30 `loadActiveSpeed()` L2535 发现新未展示复合键时串行 `getList()` 并重放同轮速度，`handleBatchAddCompleted()` L2213 对后台添加完成再拉表补速；✨2026-09-06 终态整表刷新循环根修：`applySpeedUpdates()` L2498 转移判定（前态在赋值前捕获，稳态完成证据不再报告）+ 两触发点（L2616 主快照/L2545 reconcile）接 `TerminalReloadTracker` 复合键去重（防 DB 同步滞后窗口每秒 getList 循环），筛选/模板/排查模式切换处 `clear()`（`loadActiveSpeed()` 现 L2563、`getList()` 现 L1219）；✨2026-09-19 双语 P5：本地四级删除链路（handleDeleteCommand/executeDeleteByLevel/callDeleteWithLevelAPI/pollDeleteTaskStatus/handleDeleteTaskResult/handleDeleteResponse ~340 行）与 legacy 双问删除死代码删除，模板两处删除命令改挂 mixin 的 handleDeleteByLevelCommand/handleBatchDeleteByLevelCommand |
| `TraditionalView.vue` | 传统表格视图（extends mixins(TorrentBatchMixin, SpeedPollingMixin, ColumnResizeMixin, TorrentErrorTooltipDismissMixin)，L1017）；展示可配置的“辅种数量”列并保留虚拟表格/分页路径；✨2026-08-20 展示对齐判定：状态列叠加红色“Tracker异常”标签（col-status 加宽 90→145px、表 min-width 1435px），状态图标 title 同步提示；Tracker 主域名过滤 L271、快捷入口命令分发 L1973；✨2026-08-27 筛选命中可视化：`getList()` L1357 响应后输出 `[tracker-filter]` 观察日志（共享 `countMatchedTrackerRows`）；✨2026-08-27 交互修复：L309 查询蒙版全屏锁滚动、L561 错误 tooltip 接入滚动收起 mixin；Tracker 完整详情弹框 L746 调用共享 `components/TrackerDetailCard.vue`，由组件统一标题、关闭按钮、页签、内容区、列结构、状态语义、reannounce 事件、命中行高亮及 `styles/_tracker-table.scss` 视觉样式；✨2026-08-29 速度快照支持 206 增量，按 downloader_id+hash 更新终态，连续未命中时调用 runtime-state/reconcile；✨2026-08-30 `loadActiveSpeed()` L1559 与 `handleBatchAddCompleted()` L1983 同列表模式完成成员自愈；✨2026-09-06 终态整表刷新循环根修（同列表模式）：`applySpeedUpdates()` L1505 转移判定 + 两触发点（L1628 主快照/L1553 reconcile）接 `TerminalReloadTracker` 去重并追加 `!activeAdvancedSearchRequest` 门控（终态触发不再静默退出高级搜索模式；`loadActiveSpeed()` 现 L1577、`getList()` 现 L1364）；✨2026-09-19 双语 P5：legacy 双问删除死代码（handleDelete/performSingleDelete）删除；✨2026-09-19 双语 P6-1：模板/脚本全量 i18n（工具栏/表头/筛选面板/分页分片/列设置 labelKey 12 列/状态筛选 localizedStatusOptions/四级删除菜单与确认框同键/操作与搜索反馈全量走键，错误展示接 apiResponseMessage） |
| `../mobile/torrents.vue` | 移动种子列表；✨2026-08-30 `loadActiveSpeed()` 发现新活动复合键时调用 `reload()`，列表落行后立即应用同轮进度与速度；✨2026-09-05 验收修复：删除改走四级（`components/DeleteLevelDialog.vue` + `deleteTorrentsWithLevel`）、`reload()` 原子替换（在途期间保留旧列表消除塌陷闪烁）、downloading 筛选终态整页刷新按 hash 去重（`terminalReloadedHashes`，防库内状态滞后时的 10s reload 循环）、无限滚动改 `mixins/window-infinite-scroll.ts`（window 驱动；Element v-infinite-scroll 被从不内滚的 .mobile-content 误判恒在底部，页面打开自动连发请求拉满 total，真栈实测 65s/74 次 getList）；✨2026-09-10 快捷操作下拉（查找重复任务 `getDuplicateTorrents` skip/limit→page/pageSize 换算 + 辅种/错误单种排查 `same_content_only`/`single_error_only` + 快捷删重弹窗）与模式横幅、tracker 域名候选懒加载（首展筛选面板才拉）、getList 携带 `with_trackers=false` 瘦身、卡片 `content-visibility:auto` 长列表减负；✨2026-09-12 操作补强：卡片元信息行补辅种数量（缺失回退 1，>1 主题色强调）、卡片操作补「转移」（复用桌面 `TransferDialog`，`seedTransferAvailable` 能力矩阵 fail-closed 门控）与「修改路径」（`SetLocationDialog` 单行形态，行经 `normalizeTorrent` 补齐 camelCase）；快捷操作补全局组——添加种子（`TorrentAddDialog`，`downloaderRawList` 原始行）/Tracker操作/Tracker汇报/全局替换（`GlobalReplaceTrackerDialog`）；Tracker操作与汇报移动端无多选，改先选下载器（原生按钮选择器弹窗）再执行——汇报走 `reannounceByDownloader`/空 id=`reannounceAll`（确认框明示范围），操作经 `scopeDownloader` 进 `TrackerOperationDialog` 按下载器触发模式——提交走 by-downloader 端点由服务端解析该下载器全部种子（无种子列表 URL 上限），`openTrackerOperationByDownloader` 仅 getList `limit:1` 轻取 total 作范围计数（探测失败省略计数）；五桌面弹窗懒加载 + `custom-class="m-reuse-dialog"` ≤768 收窄（94vw、体高 64vh 内滚）；✨2026-09-12（续）转移/修改路径两弹窗改组件内自治适配（自有 custom-class + 组件内媒体块，页级透传移除，m-reuse-dialog 仅余 Tracker操作/全局替换）；顺带根修下载器选项映射 `d.id`→`downloader_id ?? d.id`（后端 DownloaderSimpleVO 只返回 downloader_id，旧映射筛选值恒 undefined） |
| `../mobile/torrent-detail.vue` | 移动种子详情页（快照缓存 + getList 回查 + 5s 活跃轮询）；✨2026-09-05 删除改走四级（与列表页共用 `components/DeleteLevelDialog.vue`，成功后返回列表） |
| `../mobile/components/DeleteLevelDialog.vue` | 移动四级删除对话框（2026-09-05 新增）：四个等级选项（4 标记待删除/3 回收站/2 删任务保数据/1 完全删除）+ 桌面同款文案二次确认（等级1 error 级），确认后 emit confirm(level)；配套 `../mobile/delete-level.ts` 导出成功提示文案 |
| `../mobile/rss.vue` ✨2026-09-24 P2 | 移动 RSS 统一管理页（/m/rss，入口在移动下载器页工具区）：下载器切换选择器 + 整页复用桌面 `RssSubscriptionTab`（组件内含 ≤780 适配；与设置弹窗页签多入口并存） |
| `../mobile/notifications.vue` | 移动通知列表：无限滚动分页追加（按 id 去重防跨页重复）+ 30s 静默刷新（已翻页只同步角标）；✨2026-09-05 无限滚动改 `mixins/window-infinite-scroll.ts`（与种子页同源失控根修）；✨2026-09-08 顶部“全部已读”操作复用 `/notifications/read-all`，未读摘要取 Vuex 角标与已加载列表较大值，`markAllVersion` 防并发旧列表响应回写未读状态 |
| `../mobile/mixins/window-infinite-scroll.ts` | 移动 window 驱动无限滚动 mixin（2026-09-05 新增）：window scroll + isNearViewportBottom/maybeLoadMore，子类覆写 infiniteDisabled/loadMore；替代 Element v-infinite-scroll（其容器判定在 min-height:100vh 布局下恒为"在底部"，immediate 观察器致自动连发请求拉满 total） |
| `../mobile/search.vue` | 移动高级搜索页（`MobileSearch` L87，248 行）：✨2026-09-06 方案三移动原生重构——不再整页复用桌面 `AdvancedSearchWorkspace`，改挂移动构建器（摘要卡+底部弹层）；search 事件 → `buildAdvancedSearchRequest` → POST advancedSearch，下拉刷新双分支（已搜过重放/未搜过刷新候选）保留；搜索完成后 `scrollToResults()` L143 自动滚动定位结果锚点（scroll-margin-top 让开吸顶头部，jsdom 无 scrollIntoView 静默跳过） |
| `../mobile/components/MobileAdvancedSearch.vue` | 移动高级搜索构建器（`MobileAdvancedSearch` L354，1232 行，2026-09-06 新增）：已保存搜索横滑胶囊（同源 `getSearchTemplates({is_public:true})` 过滤 source=advanced、点击应用）+ ⚙ 管理抽屉（保存更改/删除，权限语义同桌面 L479）+ 条件组摘要卡（`describeCondition` 一行文案、点击弹 `ConditionEditSheet` 编辑、✕ 删除）+ 组内/组间 AND/OR 分段钮 + 吸底“执行搜索”玻璃浮条（避开悬浮 Tab 栏，次要操作收进 ⋯ 菜单）；字段/操作符/校验/请求构造与桌面共享 `components/torrents/advancedSearchFields.ts`，对外 onSearch()/refreshFieldOptions()/applyTemplateGroups()/resetConditions() 与桌面工作区同签名 |
| `../mobile/components/ConditionEditSheet.vue` | 移动单条条件编辑底部弹层（`ConditionEditSheet` L139，336 行，2026-09-06 新增）：el-drawer btt（76% 高、内容行主题色强调、40px 触控目标）；打开时克隆条件为草稿、确认才回写；字段/操作符/值联动与桌面同源（`onFieldChange()` L194 重置语义一致），值输入复用 `ConditionValueInput` |
| `../../styles/_tracker-table.scss` | `components/TrackerDetailCard.vue` 使用的 Tracker 详情表格视觉 mixin（位于 `src/styles/`）：紧凑字号/间距、状态色、URL 截断和操作列冻结；✨2026-08-27 新增 `tracker-row-matched` 命中行浅主色高亮（sticky 操作列同色跟随、hover 让位）与 `tracker-matched-tag`「命中筛选」标签 |
| `TorrentViewSwitcher.vue` | 视图模式切换器（列表/传统），共享状态含 `showingDuplicates` / `showingSameContent` / `showingSingleErrors`（L60–62、L86–89），切换视图不丢失查询模式 |
| `FileManagement.vue` | 种子文件备份管理（`FileManagement` L310）；路由由 `torrent_backup` 能力门控，Android 主服务端隐藏入口；✨2026-09-19 双语 P6-1：页面/筛选/表格/详情与导入弹窗/删除确认全量走 fileManagement.* 键 |
| `components/TorrentAddDialog.vue` | 添加种子对话框；✨2026-08-30 在 202 返回后由 `watchBatchCompletion()` L226 保存 `task_id`，`pollBatchCompletions()` L247 轮询既有系统完成通知并发出 `batch-complete`；10 分钟超时兜底刷新，销毁时清理计时器；✨2026-09-12 新增「跳过校验」复选框（默认关，`form.skip_hash_check` 透传 addTorrentsBatch——qB 对保存路径已有数据的种子强制 CheckingDL 校验，勾选跳过直接做种；关闭弹窗重置回安全默认；仅 qB 生效，TR 的 add_args 无校验跳过参数）；同批 ≤768 移动端适配（自定义 modal 非 el-dialog，m-reuse-dialog 覆盖不适用——overlay 顶铆+自身可滚接管 85vh、dialog 全宽 !important 压制内联 600px、底部双钮 44px 等宽、文件移除钮 36px 触控） |；2026-09-21 P3-1 双语（含跳过校验策略提示与校验消息）
| `components/BatchTransferDialog.vue` | 批量转移对话框；✨2026-09-19 双语 P6-1：文案/校验/结果三态走 transfer.* 键 |
| `components/TrackerOperationDialog.vue` | Tracker 操作对话框；✨2026-08-20 修复 announce 状态判断（原 `=== 'True'` 字面量对中文状态文本恒显“异常”，改用共享 `isTrackerAnnounceSuccess`）；✨2026-09-12 新增可选 `scopeDownloader` prop（`{id,name,total?}`，默认 null 保持桌面行为）——传入时切换为按下载器触发模式：范围行/标题/提交按钮文案换口径（含 total 计数），添加/修改提交走 `addTrackerByDownloader`/`modifyTrackerByDownloader`（服务端解析种子范围，成功提示带成功/失败计数）；模板 `?.` 改 buble 兼容写法（组件首次可被 jest 挂载） |；2026-09-21 P3-2 双语：页签/范围/校验（规则 getter 化）/标题/提交提示走 tracker.operation.*（zh 输出与原内联逐字节一致）
| `components/TransferDialog.vue` | 转移对话框；桌面两种种子视图与详情页按 `seed_transfer` 能力隐藏入口；✨2026-09-12 组件内自治 ≤768 移动适配——自有 `custom-class="transfer-dialog"` + 非 scoped 媒体块（94vw !important 压内联 600px、体 64vh 内滚；嵌套删除确认 `transfer-delete-confirm` 88vw，append-to-body 脱离组件树故须非 scoped）+ scoped 块（label-width 120px 表单标签上堆、底部双钮 44px 等宽、路径建议行 36px 触控）；复验批扩 UI 移动化（头部/关闭钮 36px 触控/圆角/padding/间距收敛、复选框触控行、长路径折行、删除确认 icon 收敛） |
| `components/TrackerDetailCard.vue` | 列表/传统视图共用的 Tracker 完整详情弹框：标题、关闭按钮、Tracker/文件/Peers 页签、内容区、错误原因提示、Tracker 名称与 URL、Announce/Scrape 状态、汇报按钮及统一状态语义；✨2026-08-27 命中可视化：`matched_domain`（snake/camel 双读）命中行加 `tracker-row-matched` 高亮与「命中筛选」标签（tooltip 显示命中域名）；通过 `layout` 仅控制两种定位方式；✨2026-09-06 文件/Peers 页签实现：数据经 `files-state`/`peers-state` props 聚合传入（卡片仍零 API 调用），文件表格（名称省略/`formatFileSize`/`el-progress` 细条 clamp 0~100）与 Peers 表格（地址/客户端/进度/双速度，0 速兜底 `-`），loading/错误/空三态 + 更新失败保留旧数据的 stale 提示，超 1000 行 computed 截断并提示总数，刷新按钮 `$emit('refresh', tab)`；✨2026-09-06（第二批）文件页签三列排序（列头按钮循环 升序→降序→还原，先筛选后排序互不禁用）+文件名模糊搜索框（大小写不敏感、no-match 态工具条常驻可改关键词、计数/截断提示随命中数更新，父级清数据时视图态复位）；顶部整行收起条 `.tracker-collapse-bar` L10（2026-09-06 用户反馈由底部上移至 Tracker详情标题之上；chevron 方向随布局取收起方向 list↑/traditional↓、与右上角关闭按钮同 `close` 事件，卡片总高 240px/移动端 180px 不变）；✨2026-09-09 新增「媒体库」页签（`media-state` props 聚合 MoviePilot 整理关联：标题/季集/整理方式/媒体库与源路径/实例，整理失败标记，三态+stale 同文件页签） |；2026-09-21 P3-2 双语：标题/表头/页签/占位三态/计数拼接/命中标签走 tracker.detail.*（页签 label 按内置 value 映射，后端 announce/scrape 原始诊断保留原文，876 行）
| `components/SetLocationDialog.vue` | 设置保存位置对话框；✨2026-09-12 根节点 div 包裹根修（透传的 custom-class 经 $attrs 落到外层 div，650px 恒怼手机屏）——el-dialog 升为模板根 + 自有 `custom-class="set-location-dialog"`；同批 ≤768 自治适配（非 scoped 媒体块 94vw/64vh 内滚 + scoped 标签上堆/44px 按钮/路径建议触控，契约 spec 钉死 el-dialog 落位防回退）；复验批扩 UI 移动化（头部/关闭钮 36px 触控/圆角/padding/间距收敛、复选框触控行、当前路径 tag 折行） |
| `components/GlobalReplaceTrackerDialog.vue` | 全局替换 Tracker 对话框；✨2026-09-19 双语 P6-1：危险警告/表单/校验/示例走 tracker.replace.* 键，成功与失败提示复用 torrent.msg.globalReplace*（失败经 apiResponseMessage 按 reasonCode 本地化） |
| `components/TorrentDetailDialog.vue` | 种子详情对话框 |；2026-09-21 P3-2 双语：描述项/Tracker 表/按钮走 torrent.detail.*（转移弹窗本体属 P6 未动，仅译入口按钮）
| `components/BatchOperationDialog.vue` | 批量操作对话框 |；2026-09-21 P3-1 双语
| `components/SearchTemplateDialog.vue` | 搜索模板选择对话框 |；2026-09-21 P3-2 双语：页签/表单/提示走 search.templateDialog.*
| `mixins/torrentBatch.ts` | 批量操作薄封装层；异步删除处理占用跳过统计、提交即刷新与无任务短路；✨2026-09-19 双语 P5：四级删除链路单点收敛（index.vue 本地重复链路删除改挂本 mixin），确认/轮询/降级/文件缺失提示全量 i18n（torrent.deleteLevel.*），错误提示走 apiResponseMessage（reasonCode 优先） |
| `mixins/columnResize.ts` | 列宽拖拽 mixin（列表/传统两视图共用）：th 右缘手柄拖拽调宽、mouseup 一次性写入 localStorage（key 由子类覆写 `columnWidthStorageKey`，默认宽度覆写 `defaultColumnWidths`）；双击恢复单列默认、`resetColumnWidths` 供列设置菜单整体重置；拖拽中 body 加 `column-resizing` 全局光标，beforeDestroy 成对解绑 |
| `mixins/speedPolling.ts` | 实时速度轮询 mixin：两视图重复的 1 秒链式轮询单点维护（`loadActiveSpeed` 由子类实现），暂停/销毁期间在途请求不再重启定时器，后台标签页停止轮询、恢复可见先补一次刷新 |
| `mixins/detailTabsData.ts` | TrackerDetailCard 文件/Peers 页签数据 mixin（class mixin L56，子类提供 `currentRow`/`activeDetailTab`）：文件按 `downloader_id:hash` 键控懒加载一次+手动刷新，Peers 切入立即拉取并 5s 链式轮询（L171，请求完成后再 arm 不堆叠）；`@Watch` 页签切换与 `currentRow` 三向（置空停轮询清数据/换种子失效缓存/卸载 beforeDestroy 兜底），请求序号+当前键双重守卫丢弃过期响应，信封 404 自动停轮询（兜住列表模式删除当前种子未清 currentRow 缺口）；⚠️ visibility handler 必须方法内建闭包——类字段箭头在 vue-class-component 字段默认值共享下捕获幽灵 this（2026-09-06 实证）；✨2026-09-09 新增 media 页签分支（MoviePilot 关联：`getTorrentMoviePilotAssociations` 键控懒加载同文件页签骨架、空列表为合法业务态不重拉、`TrackerDetailTabValue` 扩 'media'） |；2026-09-21 P3-2 错误兜底文案 translate 化（tracker.detail.files/peers.loadFailed）
| `mixins/errorTooltipDismiss.ts` | 错误原因 tooltip 收起 mixin（50 行）：window 捕获阶段监听 scroll/wheel，滚动时关闭两视图 `torrentErrorTooltips` 引用；beforeDestroy 成对解绑，避免全局监听残留 |
| `utils/torrentBatch.ts` | 批量操作纯函数集合（可单测）；✨2026-08-20 展示对齐判定新增共享 helper：`hasTrackerError` L747、`showTrackerErrorTag` L768（error 状态不打标）、`getTorrentErrorReason` L778（errorReason → tracker 消息 → 兜底回退链，两视图委托调用）；✨2026-08-27 新增 `countMatchedTrackerRows` L757（统计含 tracker 域名筛选命中标记的行数，供两视图 `[tracker-filter]` 观察日志）；✨2026-08-29 新增 `buildSpeedSnapshot` L636 的 200/206 增量合并与终态归一、`collectRuntimeStateReconcileCandidates` L551 的复合键连续未命中候选收敛；✨2026-08-30 新增 `RuntimeListMembershipTracker` L358 / `refresh()` L432，以完整快照建立分页外基线、206 增量合并并串行触发权威列表刷新；✨2026-09-11 新键判定加 30s 滞回宽限（`REAPPEAR_GRACE_MS` L349）：键掉出快照后宽限内再出现判为快照抖动不触发刷新，超宽限回归才重判新键，lastSeenAt 仅完整快照轮回收防泄漏；✨2026-09-06 新增 `TerminalReloadTracker` L471（终态整表刷新按 downloader_id+hash 复合键去重，缺 downloaderId 退化 hash 键有界双触发）与 `isTorrentRowEffectivelyComplete` L623（行级终态保守谓词：完成证据优先、折叠后状态仅 completed/seeding 命中，刻意不等于 reconcile 候选口径反向），供两视图 `applySpeedUpdates` 转移判定与终态触发门控 |；2026-09-21 P3-2 Tracker 异常展示段（getTorrentErrorReason 兜底文案）translate 化走 tracker.errorReason.*；✨2026-09-19 双语 P5：删除链路纯函数 i18n（buildDeleteConfirmMessage 按等级独立成键/parseDeleteTaskResult/parseSyncDeleteResponse/buildFileMissingDetail，名称拼接 common.listSeparator 随语言切换），deleteTorrentsBatch 死封装删除（零生产消费方） |
| `utils/traditionalTorrentIdentity.ts` | 任务行标识（infoId + downloaderId + hash） |
| `utils/traditionalStatusFilter.ts` | 传统视图状态筛选；P6-5 双语：固定项（全部/活动中）文案改由调用方传入（TraditionalView 按 torrent.list.filters.* 键翻译） |
| `utils/traditionalVirtualList.ts` | 传统视图虚拟滚动窗口计算 |
| `utils/traditionalPagination.ts` | 传统视图分页常量与归一化 |
| `utils/__tests__/traditionalStatusFilter.spec.ts` | traditionalStatusFilter 回归测试：钉死「全部/活动中」固定项 icon 为 Lucide 图标名（emoji→Lucide 改造契约）并覆盖三个状态筛选映射函数 |

> 重复种子快捷删除对话框不在本模块内：组件实际位于 `src/components/torrents/QuickDeleteDuplicatesDialog.vue`（见 components-layout 分支）。

## downloader/ 详情（16 个文件）

| 文件 | 一句话职责 |
|------|-----------|
| `index.vue` | 下载器节点控制室主入口（`DownloaderManager`）：聚合状态摘要、筛选操作台、节点矩阵、轮询遥测和响应式动效；`handleSync()` L772 只将 sync-single 返回视为“已受理”，由任务跟踪器在真实终态提示成功/部分/失败/取消并释放占用 |
| `sync-task.ts` | 下载器手动同步共享跟踪器；`buildSyncTaskNotice()` L30 统一终态文案（P6-5 双语：downloader.sync.* 四态 + detailSuffix，桌面/移动同源），`trackSyncTaskStatus()` L54 以 1s 间隔轮询，支持取消、10 分钟超时与连续查询错误上限 |
| `../mobile/downloader.vue` | 移动下载器页；`syncOne()` L198 同样区分“任务已受理”与真实后台终态，任务进行期禁用所有同步按钮，组件销毁时取消轮询；✨2026-09-10 新增/编辑弃用旧 6 字段弹窗，统一跳 `/m/downloader/settings/:id|new`（DownloaderSettingsDialog 整页承载全部页签） |
| `../rss/index.vue` ✨2026-09-24 P2 | RSS 统一管理页（/downloader/rss 子菜单，跨下载器）：下载器选择器（qB/TR 过滤）+ 复用 `RssSubscriptionTab`（多入口共享实现；keepAlive）；navigation.titleKey rssManagement |
| `components/DownloaderSettingsDialog.vue` | 新增/编辑共用的顶层配置工作区，聚合基础、速度、路径、标签与 RSS 订阅 Tab（✨2026-09-24 新增 rssSubscription 页签，`rssTabAvailable` 门控类型 0/1，rTorrent 待适配后放开；✨2026-09-24 P2 页签内容组件升级为双模式壳，与 `/downloader/rss` 统一页共享实现）；新增模式锁定依赖节点 ID 的页签；✨2026-09-10 `:tab-position` 响应式（≤780 顶部横向页签带文字，宽屏仍左列）；✨2026-09-18 桌面双语 P2：basic 页签（连接/认证/测试/开关/存储/路径映射）i18n 化 |
| `components/PathMappingTab.vue` | 高密度双向路径映射 Tab（本地↔远程），含刷新、测试、增删改与空状态 |
| `components/TagManagementTab.vue` | 标签/分类检索、过滤、排序、同步与维护工作台 |
| `components/RssSubscriptionTab.vue` ✨2026-09-24（P2 重构模式壳） | RSS 工作台：Phase 1 源表格/enabled 开关/抓取状态三态/待添加计数 + 新增编辑源弹窗 + 文章抽屉 + 推送参数弹窗；Phase 2（feature rss-subscription-phase2-2026-09-24）重构为双模式壳——qB 顶部模式单选（btdeck/qb_native，切换走确认弹窗；qbNativeAvailable 能力键门控）+ qb_native 渲染 `RssQbNativePanel`、引擎模式渲染源表格 + `RssRulesPanel`（TR 恒引擎模式不显示模式区）；LucideIcon 走全局注册（本地 components 不再注册）；≤780 抽屉全宽适配 |
| `components/RssRulesPanel.vue` ✨2026-09-24 P2 | 引擎自动下载规则面板：规则表格（include/exclude 关键词标签化/作用源/目标下载器/enabled 开关/累计推送）+ 新增编辑弹窗（名称/关键词/正则开关/feed 多选空=全部/目标下载器/savePath/tags）+ 匹配预览抽屉（只读，含源名与截断提示）；保存响应 backfill 计数转译推送/跳过/失败提示 |
| `components/RssQbNativePanel.vue` ✨2026-09-24 P2 | qB 原生 RSS 面板（qB 为事实源透传）：el-tree 源树（未读徽标 + 文章/刷新/改址 MessageBox.prompt/整源已读/删除）+ qB 规则表格与编辑弹窗（mustContain/mustNotContain/affectedFeeds/savePath/category/addPaused）+ 命中预览弹窗（按源分组）+ 偏好卡（白名单四键：两开关+两数值边界）+ 文章抽屉（仅未读过滤/单篇已读/链接外跳） |
| `components/DownloaderPathManagement.vue` | 下载器路径资产管理面板（筛选、状态、刷新、增删改） |
| `components/SpeedSettingsTab.vue` | 全局与分时段速度策略工作台 |
| `components/AdvancedSettingsTab.vue` | 兼容保留的高级设置 Tab，应用图标已迁移 Lucide |
| `components/TemplateSelectionDialog.vue` | 高密度模板选择对话框，含自定义标题、加载与空状态 |
| ~~`components/BasicSettingsTab.vue`~~ | 基础设置 Tab；2026-09-19 P6-2 死代码删除（内容已并入 DownloaderSettingsDialog basic 页签） |
| `components/DownloaderCard.vue` | 单节点遥测卡片，集中展示连接、吞吐、任务、延迟与全部管理动作；✨2026-09-18 桌面双语 P2：卡片文案/aria i18n 化 |
| ~~`components/DownloaderDialog.vue`~~ | 旧 6 字段新增/编辑对话框；2026-09-10 删除（桌面与移动均已统一走 DownloaderSettingsDialog） |
| `components/PathManagementTab.vue` | 路径映射/路径资产双视图容器 |
| `types.ts` | 下载器模块 TS 类型定义 |
| `settings.ts` | 分时段开关/调度规则类型片段 |
| `connection.ts` | 连接测试前置判定 `hasCompleteConnectionInfo`：凭据齐全才允许发起测试，编辑态密码可留空（由后端复用已存加密密码） |
| `path-mapping-rules.ts` | 路径映射规则纯函数 `generateExternalPathFromRules`：按 `source{#**#}target` 规则文本（最长优先匹配）从内部路径生成外部路径 |

## tracker/ 详情（13 个文件）

| 文件 | 一句话职责 |
|------|-----------|
| `reannounce-config.vue` | ⚠ **Options API**（L299 `export default {`）：重新宣告配置页；✨2026-09-20 双语 P6-3：模板/表单/批量编辑浮窗/危险确认链路全量走 reannounce.* 键（校验规则消息随语言切换），批量部分失败明细转 console（E01），错误展示接 apiResponseMessage/apiErrorMessage |
| `keywords-board.vue` | 关键词看板主页面（`TrackerKeywordsBoard`）；✨2026-09-20 双语 P6-3：池名走共享 poolLabel（label 字段移除）、拖拽移动/删除/候选池门禁提示全量走键 |
| `test.vue` | Tracker 连通性测试页（关键词匹配判断测试）；✨2026-09-20 双语 P6-3：输入/结果/历史/时间线（timeline.* 含高亮标记结构）/复制/添加关键词 prompt 全量走键，res.msg 直读改 apiResponseMessage |
| `keywords-search.vue` | 关键词搜索页（`KeywordsSearchPage`）；✨2026-09-20 双语 P6-3：筛选/表格/操作全量走键；不再直显后端中文 pool_label 字段（getPoolLabel 本地化） |
| `components/KeywordListModal.vue` | 关键词列表弹窗（搜索框右侧含快捷操作入口）；✨2026-09-20 双语 P6-3：搜索/时间排序筛选/批量操作/移动删除链路全量走键，池名走 poolLabel/poolOptions |
| `components/ImportKeywordsDialog.vue` | 批量导入关键词对话框；✨2026-09-20 双语 P6-3：上传/文本输入/进度/取消/成功统计全量走键 |
| `components/AddKeywordDialog.vue` | 添加关键词对话框；✨2026-09-20 双语 P6-3：表单/校验/结果全量走键，错误展示接 apiResponseMessage（移动端复用面 zh 零回归） |
| `components/KeywordCard.vue` | 单个关键词卡片；✨2026-09-20 双语 P6-3：类型标签/元信息走 keywordCard.* 键，语言名走 getLanguageLabel（tracker.lang.*） |
| `components/KeywordTagCard.vue` | 关键词标签卡片（无文案，纳入审计面） |
| `components/KeywordQuickActionDialog.vue` | 关键词快捷操作（左匹配）对话框，看板与详情弹窗共用（预览→二次确认→批量删除/移动）；✨2026-09-20 双语 P6-3：POOL_LABELS 中文常量删除（poolLabel 共享）、确认文案/门禁提示全量走键，预览失败接 apiResponseMessage、catch 接 apiErrorMessage |
| `components/ApiLogViewer.vue` | API 调用日志查看器；✨2026-09-20 双语 P6-3：标题/展开收起走 apiLog.* 键 |
| `components/MatchTimeline.vue` | 匹配时间线组件；✨2026-09-20 双语 P6-3：标题走 timeline.* 键（步骤数据由 test.vue 传入已本地化） |
| `components/TestResultSummary.vue` | 测试结果汇总；✨2026-09-20 双语 P6-3：结果标签与描述走 resultSummary.* 键 |

## 其余单文件模块

| 模块/文件 | 职责 |
|-----------|------|
| `tasks/index.vue` | 任务管理主页（`TaskManage` L1002）：任务日志统计摘要使用 `btdeck_task_log_stats_collapsed` 持久化折叠状态；`handleViewLogs` L1316 记录可见任务筛选，`resetLogQuery` L1901 / `clearLogTaskFilter` L1917 清除 task_id 并立即查询全部日志；导出/过期清理为标准 Element 按钮；✨2026-09-20 双语 P6-4a：双页签/筛选/工具栏/表格/操作菜单/任务表单（清理配置/高级配置/启用开关）/执行详情/清理预览/日志清理弹窗全量走键；getStatusName 改收 row 按 taskStatus 码位本地化（未知码回退后端原文 Q02）、getTaskTypeName/getLogTaskTypeName 按 taskType 码位；taskTypeOptions 键化（labelKey）+ taskOptions 死数组删除 |
| `logs/audit.vue` | 审计日志查询/筛选/分页（`AuditLogs` L585）；v1.0.6.36 操作日志布局优化（剪贴板回退复制/导出归档入口对齐）；✨2026-09-20 双语 P6-4b：全量文案走 auditLogs.* 键；操作类型 19 项键化数据驱动（OPERATION_GROUPS L509 + 短标签 operationType/筛选长标签 operationTypeFull 双形态，未知值回退原文 Q02）；错误展示接 apiResponseMessage/apiErrorMessage（response.msg 直读清零） |
| `recycle-bin/index.vue` | ⚠ Options API（`RecycleBin`，L374）：回收站，L14 搜索区复用 management-panel/filter UI，支持 Enter、清空与重置 |
| `settings/index.vue` | 全局设置页（`Settings`；✨2026-09-09 新增 MoviePilot 页签；2026-09-22 合入 MCP 服务页签并移除主机能力页签；✨2026-09-23 UI 重构：页签改左侧垂直导航带 Lucide 图标（shield-check/key-round/plug-zap/clapperboard/activity），tabPosition 按 resize 监听在 ≤768px 切回顶部横排（mounted 内创建箭头捕获 vm 代理，参照 PageSizeCombobox 模式），各页签卡片壳/标题/描述统一 @extend `styles/settings-panel.scss` 占位符，表单收窄 480px 行宽） |
| `settings/components/McpSettingsPanel.vue` | MCP 服务配置面板（W1；全局/能力开关+CAS+kill switch 横幅；2026-09-09 补记漂移；✨2026-09-22 双语 213bafa 后硬编码清零 + W5 服务密钥卡：端点/认证头提示、三态引导 absent/unreadable、掩码+复制（clipboard util）、危险确认 rotate 409 重载、明文仅组件内存；capDescription 按 locale 取 descriptionEn；✨2026-09-23 卡片壳/标题/描述改继承 settings-panel.scss 统一规范） |
| `settings/components/MoviePilotPanel.vue` ✨2026-09-09 | MoviePilot 集成面板：全局开关 CAS（409 自动重载）、实例卡片（启用开关/删除二次确认/同步统计与错误）、MP→BtDeck 下载器映射内联编辑（保存触发后端重解析）、路径反查卡（任务快照/未关联标签）；demo 只读占位；移动端经包装自动同源；中文硬编码待双语另立项；✨2026-09-23 卡片壳/标题/描述改继承 settings-panel.scss 统一规范（宽度 760→960px） |
| `../../styles/settings-panel.scss` ✨2026-09-23 | 系统设置页签卡片壳统一规范（位于 `src/styles/`，SCSS 占位符不产出 CSS）：`%settings-card`（960px 宽/xl 内边距/xl 圆角/md 阴影）、`%settings-card-title`（20px/700 + 渐变竖条 accent）、`%settings-card-description`（14px/1.6）；消费方 settings/index.vue + McpSettingsPanel + MoviePilotPanel 经 `@extend` 继承 |
| `dashboard/index.vue` | 仪表盘聚合统计卡片（`Dashboard`）：系统状态卡显示所有下载器上传/下载速度之和，下载器状态卡显示各自下载/上传速度 |
| `query-templates/index.vue` | 查询模板列表主入口（`QueryTemplates` L188）；L111 行操作使用 play/pencil/trash Lucide 图标与紧凑按钮样式；✨2026-09-23 路由归入 `/torrents/query-templates`（菜单在种子管理组内） |；2026-09-21 P3-2 双语：页头/筛选/列头/删除确认走 queryTemplate.list.*，系统预设名称/描述按 preset_key 本地化（presetDisplayName/presetDisplayDescription），formatTime 按 getLocale 本地化日期
| `query-templates/components/QueryTemplateDialog.vue` | 查询模板新增/编辑对话框；✨2026-08-27 simple 表单补 Tracker 域名多选（AdvancedMultiSelect，options 懒加载 `/torrents/tracker-domains`，编辑回填 + buildConditions 写入，修复模板保存丢失 tracker 筛选） |；2026-09-21 P3-2 双语：表单/状态选项（复用 torrent.status.*）/排序选项/提示走 queryTemplate.dialog.*（校验规则 getter 化）
| `login/index.vue` | 登录页（`Login`）：使用 D 形 mark + `BtDeck` 字标的 `AppLogo` 横向完整品牌 Logo；桌面/移动登录入口统一品牌资源 |
| `orphan-files/index.vue` | 孤儿文件管理（`OrphanFiles` L948）；统计摘要使用 `btdeck_orphan_file_stats_collapsed` 持久化折叠状态；仅文件夹模式注册展开列，子表隐藏重复表头；`loadFolderChildren` L1232 仅展开时加载子页，`startScanPolling` L1861 轮询后台扫描，`dismissLargeScanReminder` L1295 关闭超量提醒；保留硬链接定位、清理/忽视/隔离恢复；✨2026-09-20 双语 P6-4b：全量文案走 orphanFiles.* 键（危险链路三要素保留）；状态/置信度按稳定码位（status/confidenceTag，与筛选选项同源）；扫描上下文 cleanup_block_reason/error_message 后端数据原文透传（{reason} 槽位 + 本地键兑底）；E01 拒绝/部分失败明细转 console、计数键提示；200 信息态按 task_id 分支提示；错误展示接契约入口（msg 直读清零） |
| `404.vue` | 404 页面（`Page404`） |
| `nested/*`（7 文件） | 嵌套路由菜单演示（menu1/menu2） |
| `tree/index.vue` | 树形组件演示页（`Tree`） |

---

## mobile/ 详情（移动页子系统，✨2026-09-21 补录）

> 移动子系统与桌面共用 API 层与共享层（sync-task/notification-markdown/ui-mode 等）；路由按 `utils/ui-mode.ts` 解析结果分流。已有行覆盖的文件见上方 torrents/downloader 详情表的 `../mobile/*` 行。

| 文件 | 一句话职责 |
|------|-----------|
| `dashboard.vue` | 移动仪表盘（380 行）：复用桌面 /dashboard API 的卡片化展示 + 下拉刷新 |
| `downloader-settings.vue` | 移动下载器设置页（109 行）：整页复用桌面 DownloaderSettingsDialog（fullscreen 近似形态），覆盖基本/速度（含分时段调度）/路径维护/标签管理全部能力 |
| `login.vue` | 移动登录页（153 行，`MobileLogin extends WideViewport`） |
| `logs.vue` | 移动审计日志（309 行）：复用 /audit-logs 查询与操作类型 API 的卡片流，操作类型/结果/种子名称筛选与分页加载；导出与统计保留桌面版承载 |
| `orphan-files.vue` | 移动孤儿文件（730 行）：双 Tab（孤儿文件/隔离区）与桌面同构；清理走桌面同款两段式（cleanupPreview → cleanupOrphans） |
| `recycle-bin.vue` | 移动回收站（284 行）：卡片列表 + 单条恢复/彻底删除（降低误触；批量与手动上传保留桌面承载） |
| `settings.vue` | 移动系统设置页（38 行）：包装桌面 settings/index.vue（2FA/改密/强制改密同源同逻辑） |
| `tasks.vue` | 移动定时任务（429 行）：任务卡片流 + 启用筛选/名称过滤；立即执行/启停（PUT 部分更新）/中断/删除，最近结果六态 |
| `tracker-keywords.vue` | 移动 Tracker 关键词看板（368 行）：四池切换 + 卡片流；桌面拖拽移池改关键词卡片下拉「移动到X池」 |
| `tracker-keywords-search.vue` | 移动关键词全局搜索（296 行）：复用 searchAllPools 全池检索，关键词/池子/时间/排序筛选 |
| `components/PullIndicator.vue` | 移动下拉刷新指示条（52 行）：拉动高度随 distance 增长（封顶 80px），刷新中固定 36px；状态由 pull-to-refresh mixin 提供 |
| `mixins/pull-to-refresh.ts` | 移动端下拉刷新 mixin（152 行）：手写轻量 touch 下拉（Element UI 无移动组件），仅当滚动容器在顶部时触发 |
| `mixins/wide-viewport.ts` | 宽视口检测 mixin（60 行）：显式偏好 mobile 时宽视口仍停留移动版（ui-mode 原则：偏好优先于视口；2026-09-12 桌面版出口回归修复） |
| `torrent-detail-cache.ts` | 种子详情快照缓存（20 行）：列表页点击卡片写入整行，详情页优先立即渲染（含 trackerInfo） |
| `torrent-status.ts` | 移动端种子状态展示共享映射（49 行）：列表卡片与详情页两页共用（桌面端在 views/torrents 各组件内自持） |

---

## ⚠ Options API 技术债（全仓库仅 2 处）

| 文件 | 行号 | 说明 |
|------|------|------|
| `recycle-bin/index.vue` | L374 `export default {` | 回收站页面 |
| `tracker/reannounce-config.vue` | L300 `export default {` | Tracker 重宣告配置页 |

> 详见 [../../perspectives/risks.md](../../perspectives/risks.md) "文档/代码漂移" 章节。

## 第三层详情

- 本次未产出 views 第三层（建议优先级：`torrents/index.vue` 3018 行主入口、`TraditionalView.vue` 2732 行）
