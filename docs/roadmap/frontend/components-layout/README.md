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
| PWA 更新提示 refresh-prompt | `RefreshPrompt.vue` | 监听 Service Worker 更新事件，提供用户确认后刷新提示（桌面/移动布局共用） |
| Demo 模式提示 demo-banner | `DemoModeBanner.vue` | Demo 构建固定顶部提示“数据为本地模拟”，提供本地 store 重置并刷新当前页面 |

> v1.0.6.28 引入 `lucide@^1.27.0` 依赖（`package.json`）。设计动机：高级搜索标签选择器重塑需要大量细粒度图标，统一基础设施避免各组件各自 import SVG；v1.0.6.31 起列头排序图标亦复用同一包装器。

#### 顶层 + 单件目录

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Monaco 编辑器 monaco | `MonacoEditor.vue` | Monaco 代码编辑器通用封装（`MonacoEditor extends Vue`，L12） |
| 批量按钮 batch-button | `BatchButton/index.vue` | 批量操作按钮（含下拉菜单） |
| 批量按钮测试 batch-button-test | `BatchButton/__tests__/BatchButton.spec.ts` | BatchButton 回归测试：提供 `lucide-icon`/`lucide-size` props 时用 LucideIcon 渲染、未提供时回退 el-icon、disabled 抑制点击 |
| 面包屑 breadcrumb | `Breadcrumb/index.vue` | 面包屑导航 |
| 可折叠面板 collapsible-panel | `CollapsiblePanel.vue` | 通用可折叠面板（management-panel 风格标题区 + Lucide 折叠箭头，`aria-expanded`/`aria-controls` 无障碍）：折叠状态按 `storageKey` prop 经 getStorage/setStorage 持久化 |
| 侧边栏折叠 hamburger | `Hamburger/index.vue` | 侧边栏折叠按钮 |
| 分页 pagination | `Pagination/index.vue` | 分页组件封装 |
| 主题切换 theme-switcher | `ThemeSwitcher/index.vue` | 主题切换器（明/暗），触发器与选项图标统一使用 Lucide |

#### components/tasks/（3 个文件，任务专用组件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Cron 编辑器 cron | `CronEditor.vue` | Cron 表达式可视化编辑器（`CronEditor`） |
| Python 类选择器 python-class | `PythonClassSelector.vue` | Python 类/方法选择器（`PythonClassSelector`） |
| 任务 Monaco 编辑器 tasks-monaco | `MonacoEditor.vue` | 任务专用 Monaco 编辑器（含 Python 高亮） |

#### components/torrents/（11 个 .vue + 1 个业务 .ts + 7 个测试）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 高级搜索构建 advanced-search | `AdvancedSearchBuilder.vue`（1481 行） | 高级搜索条件构建器（`AdvancedSearchBuilder` L423）；“添加条件”居中、组间 AND/OR 位于卡片外；L582 下载器显示 nickname/提交稳定 ID，L787 超级做种三态，`getOperatorGroups()` L809 按字段契约过滤操作符；`getTemplateGroupsSnapshot()` L993 提供校验后快照；内联定宽全部类化 + 768px 断点强化（选择器铺满/组头换行/AND/OR 标签避让，`/m/search` 移动适配），预览与保存模板对话框经 `advanced-search-dialog` 窄屏压宽 |
| 高级搜索工作区 saved-search | `AdvancedSearchWorkspace.vue` | 两种种子视图共用的高级搜索工作区（`AdvancedSearchWorkspace` L156）：左侧加载高级模板并支持选择回填、搜索、新建、覆盖更新与删除（L232–385），右侧复用 Builder；`/m/search` 整页复用（移动端查询模板页裁撤后模板能力收敛于此） |
| 条件值输入 condition-value | `ConditionValueInput.vue`（878 行） | 搜索条件值输入（`ConditionValueInput` L351）；状态/下载器使用不可创建多选，空值操作符显示“无需填写”，`currentFieldOptions` L494 为超级做种提供是/否/不支持三态下拉；日期范围定宽类化（桌面 180px 不变），768px 下两个时间选择器弹性对分整行（窄屏防溢出） |
| 高级多选 advanced-multiselect | `AdvancedMultiSelect.vue` | 高级多选下拉（`AdvancedMultiSelect` class）；v1.0.6.29 改 32px 紧凑触发器 + 点击浮层，保留搜索/创建/已选区/虚拟滚动/快捷操作与 Lucide 图标；v1.0.6.30/31 增加常驻清空按钮并修复多选字段点击无响应；2026-08-15 新增 `placeholder` prop 定制未选提示语（种子页筛选下拉：下载器/种子状态/tracker） |
| 高级搜索状态 advanced-search-state | `advancedSearchState.ts`（728 行）✨v1.0.6.28 | 高级搜索可复用状态/纯逻辑；L284/L403 兼容旧模板的多选、标签 token 与超级做种布尔值；L638 构建请求时保留正操作符和独立 `mode`，空值操作符发送 `null`，避免排除模式双重取反 |
| 紧凑表格视图 compact-table | `CompactTable.vue` | ⚠ **Options API**（L301 `export default {`，`CompactTable`）：紧凑表格视图 |
| 重复种子检测 duplicate | `DuplicateTorrentsDialog.vue` | 重复种子检测对话框 |
| 大小过滤 size-range | `SizeRangeFilter.vue` | 种子大小范围过滤器（`SizeRangeFilter` class） |
| 虚拟滚动 virtual-scroll | `VirtualScrollList.vue` | 虚拟滚动列表（`VirtualScrollList` class） |
| 过滤组 filter-group | `FilterGroup.vue` | 过滤条件组容器（`FilterGroup` class） |
| 分页组合框 page-size | `PageSizeCombobox.vue` ✨v1.0.6.30 | 共享分页组合框（20/50/100/500/1000 预设 + 1–100000 自定义输入；被列表/传统两视图复用，统一每页数量交互） |
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
| 顶栏 navbar | `Navbar/index.vue` | 顶栏（面包屑/反馈/通知/用户菜单）；品牌锚点由侧边栏统一承载，交互图标使用 Lucide |
| 侧边栏 sidebar | `Sidebar/index.vue` | 侧边栏容器（基于路由生成菜单），展开态使用完整 Logo、折叠态使用 `mark` 图标，菜单/折叠控制使用 Lucide |
| 菜单项 sidebar-item | `Sidebar/SidebarItem.vue` | 单个菜单项（递归子菜单）；路由 meta icon 与子菜单箭头由 LucideIcon 渲染；桌面折叠态按 `.submenu-label`/`.submenu-chevron` 语义类隐藏文字与箭头，显式保留根节点为 `span` 的 `.menu-icon`，避免多子菜单父图标被误隐藏 |
| 菜单项链接 sidebar-item-link | `Sidebar/SidebarItemLink.vue` | 菜单项链接包装（外链/内链分流） |
| 通知抽屉 notification-drawer | `NotificationDrawer/index.vue` | 通知抽屉容器 + 详情弹窗；内容 Markdown-lite 渲染抽至 `utils/notification-markdown.ts`（与移动通知详情 `views/mobile/notifications.vue` 共用，两端一致）；标题、筛选、加载、空状态与关闭动作统一使用 Lucide |
| 通知项 notification-item | `NotificationDrawer/NotificationItem.vue` | 单条通知项；列表摘要经共享 `plainNotificationContent` 剥离 Markdown 记号（与移动列表同源，未打开详情不裸露记号），详情入口使用 Lucide |

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
