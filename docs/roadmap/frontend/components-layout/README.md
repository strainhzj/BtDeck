# frontend/components-layout — 通用组件与布局骨架

> 通用可复用组件（22 个 .vue）+ 布局骨架（layout/ 下 8 个 .vue + 1 mixin）。除特别标注的 Options API 外均为 class-component。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/components-layout/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

### components/ — 通用组件

#### components/common/（4 个 .vue + 2 测试）✨v1.0.6.28

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 品牌 Logo app-logo | `AppLogo.vue` | Vue 2 Logo 统一封装：`full` 为 D 形 mark + `BtDeck` 字标，另有 `mark`/`micro` 光学尺寸与 `brand`/`inverse` 色调；移动头部使用反白微型版，按 `BASE_URL` 解析 public 品牌资源 |
| 品牌 Logo 单测 app-logo-test | `__tests__/AppLogo.spec.ts` | 覆盖完整、标准、微缩及反白资源选择契约 |
| Lucide 图标 lucide | `LucideIcon.vue` | 轻量 Vue 2 包装器（`LucideIcon extends Vue`）统一渲染 Lucide 图标；静态具名 import 保 tree-shake，stroke 跟随 `currentColor`，`size`/`strokeWidth` prop 透传；v1.0.6 控制室重绘后承载侧栏/顶栏/通知/主题/工作区图标 |
| Lucide 单测 lucide-icon-test | `__tests__/LucideIcon.spec.ts` | LucideIcon 单测，覆盖共享注册表、尺寸/线宽透传、未知图标降级及下载器/导航新增图标真实 SVG 渲染 |
| PWA 更新提示 refresh-prompt | `RefreshPrompt.vue` | 监听 Service Worker 更新事件，提供用户确认后刷新提示（桌面/移动布局共用）；✨2026-09-19 遗留清扫：三条文案走 common.pwa.*（发现新版本/立即刷新/暂不刷新 aria） |
| Demo 模式提示 demo-banner | `DemoModeBanner.vue` | Demo 构建固定顶部提示“数据为本地模拟”，提供本地 store 重置并刷新当前页面 |

> v1.0.6.28 引入 `lucide@^1.27.0` 依赖（`package.json`）。设计动机：高级搜索标签选择器重塑需要大量细粒度图标，统一基础设施避免各组件各自 import SVG；v1.0.6.31 起列头排序图标亦复用同一包装器。

#### 顶层 + 单件目录

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Monaco 编辑器 monaco | `MonacoEditor.vue` | Monaco 代码编辑器通用封装（`MonacoEditor extends Vue`，L12） |
| 批量按钮 batch-button | `BatchButton/index.vue` | 批量操作按钮（含下拉菜单） |
| 批量按钮测试 batch-button-test | `BatchButton/__tests__/BatchButton.spec.ts` | BatchButton 回归测试：提供 `lucide-icon`/`lucide-size` props 时用 LucideIcon 渲染、未提供时回退 el-icon、disabled 抑制点击 |
| 面包屑 breadcrumb | `Breadcrumb/index.vue` | 面包屑导航（标题经 `routeTitle()`：titleKey 双语键优先，双语 P1） |
| 可折叠面板 collapsible-panel | `CollapsiblePanel.vue` | 通用可折叠面板（management-panel 风格标题区 + Lucide 折叠箭头，`aria-expanded`/`aria-controls` 无障碍）：折叠状态按 `storageKey` prop 经 getStorage/setStorage 持久化 |
| 侧边栏折叠 hamburger | `Hamburger/index.vue` | 侧边栏折叠按钮 |
| 分页 pagination | `Pagination/index.vue` | 分页组件封装 |
| 主题切换 theme-switcher | `ThemeSwitcher/index.vue` | 主题切换器（明/暗），触发器与选项图标统一使用 Lucide |

#### components/tasks/（3 个文件，任务专用组件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Cron 编辑器 cron | `CronEditor.vue` | Cron 表达式可视化编辑器（`CronEditor`）；✨2026-09-20 双语 P6-4a：模板选择/自定义表达式/可视化配置/执行预览/校验消息/内置模板 13 项展示全量走 tasks.cronEditor.* 键；内置模板身份 key 化（key??name，中文 name/description 字段移除），category 中文值保留为数据身份（筛选/CSS 类/tag 映射，白名单治理） |
| Python 类选择器 python-class | `PythonClassSelector.vue` | Python 类/方法选择器（`PythonClassSelector`）；✨2026-09-20 双语 P6-4a：预定义类树改由后端 type-config pythonClasses 驱动（getTaskTypeConfig 零调用→接线，~170 行硬编码假类树删除——BackupTask 等类后端不存在选择必失败；后端中文描述 Q02 原文透传，参数字典归一化兼容 string/object），快捷模板由真实类前 6 派生；UI 文案全量走 tasks.pythonSelector.* 键 |
| 任务 Monaco 编辑器 tasks-monaco | `MonacoEditor.vue` | 任务专用 Monaco 编辑器（含 Python 高亮）；✨2026-09-20 双语 P6-4a：降级告警/重试/本地启发式消息走 tasks.monaco.* 键；死字段删除（中文标识符 代码语法正确/可以正常执行 与 write-only 的 syntaxStatus/executionStatus） |

#### components/torrents/（11 个 .vue + 2 个业务 .ts + 7 个测试）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 高级搜索构建 advanced-search | `AdvancedSearchBuilder.vue`（1289 行） | 高级搜索条件构建器（`AdvancedSearchBuilder`）；“添加条件”居中、组间 AND/OR 位于卡片外；下载器显示 nickname/提交稳定 ID、超级做种三态、`getTemplateGroupsSnapshot()` 提供校验后快照；✨2026-09-06 字段分组/操作符过滤/值摘要/预览文本/动态候选加载/模板归一化下沉共享层 `advancedSearchFields.ts`（方法保留为同签名代理，行为不变），768px 断点保留（桌面窄窗口；`/m/search` 已改用移动专用组件），预览与保存模板对话框经 `advanced-search-dialog` 窄屏压宽；2026-09-21 P3-2 双语：外壳（条件组默认名/按钮/包含排除/逻辑描述/预览/保存模板）走 search.builder.* |
| 高级搜索工作区 saved-search | `AdvancedSearchWorkspace.vue`（624 行） | 两种种子视图共用的高级搜索工作区（`AdvancedSearchWorkspace`）：左侧加载高级模板并支持选择回填、搜索、新建、覆盖更新与删除，右侧复用 Builder；✨2026-09-06 起 `/m/search` 不再整页复用（移动端改用 `views/mobile/components/MobileAdvancedSearch.vue`，仅桌面两视图使用）；2026-09-21 P3-2 双语：侧栏/管理提示/确认框走 search.workspace.*，预设名按 preset_key 本地化，应用模板时预设内置组名按稳定组 id 入口翻译（仅 Builder 内存态，不改库） |
| 高级搜索共享层 advanced-search-fields | `advancedSearchFields.ts`（509 行）✨2026-09-06 | 桌面 Builder 与移动端构建器共享的字段配置与展示层：字段五分组常量、`getOperatorGroupsForField()` 按契约+matchMode 过滤操作符、`describeCondition()` 摘要卡文案、`normalizeLoadedGroups()` 模板归一化（原 Builder 私有逻辑下沉）、`loadAdvancedSearchDynamicOptions()` 分类/标签/下载器并发拉取（allSettled 部分失败静默降级） |；2026-09-21 P3-1 双语：searchFieldLabel/searchOperatorLabel 按稳定字段 code/操作符 value 取键（操作符展示名单源=契约 labelEn），分组标题/摘要/预览/归一化错误 i18n，FIELD_SECTIONS 改 labelKey；2026-09-21 P3-2 新增系统预设展示映射 `presetDisplayName`/`presetDisplayDescription`/`presetGroupName`（按 preset_key/预设组稳定 id 翻译，未识别保留原文，Q01/Q02）
| 条件值输入 condition-value | `ConditionValueInput.vue`（889 行） | 搜索条件值输入（`ConditionValueInput`）；状态/下载器使用不可创建多选，空值操作符显示“无需填写”，`currentFieldOptions` 为超级做种提供是/否/不支持三态下拉；日期范围定宽类化（桌面 180px 不变），768px 下两个时间选择器弹性对分整行（窄屏防溢出）；✨2026-09-06 起被移动端条件编辑弹层（ConditionEditSheet）同源复用；2026-09-21 P3-2 双语：placeholder/范围标签/布尔与正则开关走 search.valueInput.*，兑底选项 getter 化（超级做种三态与共享层同源） |
| 高级多选 advanced-multiselect | `AdvancedMultiSelect.vue` | 高级多选下拉（`AdvancedMultiSelect` class）；v1.0.6.29 改 32px 紧凑触发器 + 点击浮层，保留搜索/创建/已选区/虚拟滚动/快捷操作与 Lucide 图标；v1.0.6.30/31 增加常驻清空按钮并修复多选字段点击无响应；2026-08-15 新增 `placeholder` prop 定制未选提示语（种子页筛选下拉：下载器/种子状态/tracker） |；2026-09-21 P3-1 双语（common.multiSelect，分隔符示例绕开 vue-i18n 竖线按 locale 常量直出）
| 高级搜索状态 advanced-search-state | `advancedSearchState.ts`（741 行）✨v1.0.6.28 | 高级搜索可复用状态/纯逻辑；兼容旧模板的多选、标签 token 与超级做种布尔值；构建请求时保留正操作符和独立 `mode`，空值操作符发送 `null`，避免排除模式双重取反；2026-09-21 P3-2 校验消息 52 处 translate 化（search.validation.*，zh 输出与原内联逐字节一致；`buildAdvancedSearchParams` 回退组名保持内联中文——属 API 载荷非展示文案，T01 两语言 groups 一致） |
| 紧凑表格视图 compact-table | `CompactTable.vue` | ⚠ **Options API**（L301 `export default {`，`CompactTable`）：紧凑表格视图 |
| 重复种子检测 duplicate | `DuplicateTorrentsDialog.vue` | 重复种子检测对话框 |；2026-09-21 P3-1 双语
| 大小过滤 size-range | `SizeRangeFilter.vue` | 种子大小范围过滤器（`SizeRangeFilter` class）；2026-09-21 P3-2 双语：标签/占位/快捷预设 label 改 search.sizeRange.*（预设 key 化） |
| 虚拟滚动 virtual-scroll | `VirtualScrollList.vue` | 虚拟滚动列表（`VirtualScrollList` class） |
| 过滤组 filter-group | `FilterGroup.vue` | 过滤条件组容器（`FilterGroup` class） |
| 分页组合框 page-size | `PageSizeCombobox.vue` ✨v1.0.6.30 | 共享分页组合框（20/50/100/500/1000 预设 + 1–100000 自定义输入；被列表/传统两视图复用，统一每页数量交互） |；2026-09-21 P3-1 双语（common.pageSize）
| 搜索组件测试 search-test | `__tests__/*.spec.ts`（7 个） | AdvancedMultiSelect（性能 466 + 单元 578）/ AdvancedSearchBuilder（686）/ AdvancedSearchWorkspace（389）/ ConditionValueInput（245）/ FilterGroup（97）/ QuickDeleteDuplicatesDialog（176），共 2637 行 |

> ⚠ `CompactTable.vue` 是全仓库 3 处 Options API 之一（技术债候选）。

### layout/ — 布局骨架

#### 顶层

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 布局根容器 layout | `index.vue` | 布局根容器（Sidebar + Navbar + AppMain 组合） |

#### layout/components/

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| barrel 导出 layout-index | `index.ts` | barrel 导出 AppMain/Navbar/Sidebar |
| 主内容区 app-main | `AppMain.vue` | 主内容区 `<router-view>` 容器 |
| 顶栏 navbar | `Navbar/index.vue` | 顶栏（面包屑/反馈/通知/语言切换/用户菜单，壳层文案走 `$t`）；语言下拉选项为语言自名常量（i18n/types `LOCALE_AUTONYMS`），切换走 AppModule.SetLanguage 并显式刷新 document.title；品牌锚点由侧边栏统一承载，交互图标使用 Lucide |
| 侧边栏 sidebar | `Sidebar/index.vue` | 侧边栏容器（基于路由生成菜单），展开态使用完整 Logo、折叠态使用 `mark` 图标，菜单/折叠控制使用 Lucide；✨2026-09-19 遗留清扫：底部「移动版」入口与展开/收起按钮文案+aria 走 navigation.sidebar.* |
| 菜单项 sidebar-item | `Sidebar/SidebarItem.vue` | 单个菜单项（递归子菜单）；标题经 `routeTitle()` 双语键优先（双语 P1）；路由 meta icon 与子菜单箭头由 LucideIcon 渲染；桌面折叠态按 `.submenu-label`/`.submenu-chevron` 语义类隐藏文字与箭头，显式保留根节点为 `span` 的 `.menu-icon`，避免多子菜单父图标被误隐藏 |
| 菜单项链接 sidebar-item-link | `Sidebar/SidebarItemLink.vue` | 菜单项链接包装（外链/内链分流） |
| 通知抽屉 notification-drawer | `NotificationDrawer/index.vue` | 通知抽屉容器 + 详情弹窗；内容 Markdown-lite 渲染抽至 `utils/notification-markdown.ts`（与移动通知详情 `views/mobile/notifications.vue` 共用，两端一致）；标题、筛选、加载、空状态与关闭动作统一使用 Lucide；✨2026-09-21 双语 P4（E03）：详情标题/正文经 `utils/notification-display` 事件本地化（未知事件原文兜底），详情类型标签/全部已读/详情时间 locale 化 |
| 通知项 notification-item | `NotificationDrawer/NotificationItem.vue` | 单条通知项；列表摘要经共享 `plainNotificationContent` 剥离 Markdown 记号（与移动列表同源，未打开详情不裸露记号），标题/摘要经 `utils/notification-display` 事件本地化（双语 P4/E03），详情入口使用 Lucide |

> 注意：`components/index.ts` 只 re-export `AppMain/Navbar/Sidebar`，**未导出 NotificationDrawer**（需直接路径 import）。

#### layout/mixin/

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 响应式 mixin resize | `resize.ts` | class-based Mixin（`vue-property-decorator`）：响应式监听窗口宽度，写入 `AppModule.device` |

> layout 下**无 `permission.ts`**（路由守卫在 `src/permission.ts`，见 [entry/README.md](../entry/README.md)）。`resize.ts` 被 `Navbar/index.vue` 等通过 `mixins(ResizeMixin)` 消费。

---

## 关键观察

- **范式分布**：本分支仍以 class-component 为主；`components/torrents/CompactTable.vue` 是本分支唯一的 Options API（全仓库 3 处之一）
- **Monaco Editor 双版本**：`components/MonacoEditor.vue`（通用）与 `components/tasks/MonacoEditor.vue`（任务专用，含 Python 高亮）
- **测试覆盖**：`components/torrents/__tests__/` 有 7 个测试文件（2637 行），覆盖 AdvancedMultiSelect / AdvancedSearchBuilder / AdvancedSearchWorkspace / ConditionValueInput / FilterGroup / QuickDeleteDuplicatesDialog；状态/下载器多选、稳定 ID、超级做种三态、空值控件、按钮视觉与多条件组均有回归守卫

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`CronEditor.vue` 1269 行、`AdvancedSearchBuilder.vue` 1397 行、`AdvancedSearchWorkspace.vue` 609 行）
