# frontend/components-layout — 通用组件与布局骨架

> 通用可复用组件（19 个 .vue）+ 布局骨架（layout/ 下 8 个 .vue + 1 mixin）。全部 class-component。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/components-layout/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

### components/ — 通用组件

#### components/common/（1 个 .vue + 1 测试）✨v1.0.6.28

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Lucide 图标 lucide | `LucideIcon.vue` | 轻量 Vue 2 包装器（`LucideIcon extends Vue`）统一渲染 Lucide 图标；静态具名 import 保 tree-shake，stroke 跟随 `currentColor`，`size`/`strokeWidth` prop 透传；v1.0.6 控制室重绘后承载侧栏/顶栏/通知/主题/工作区图标 |
| Lucide 单测 lucide-icon-test | `__tests__/LucideIcon.spec.ts` | LucideIcon 单测，覆盖共享注册表、尺寸/线宽透传、未知图标降级及下载器/导航新增图标真实 SVG 渲染 |

> v1.0.6.28 引入 `lucide@^1.27.0` 依赖（`package.json`）。设计动机：高级搜索标签选择器重塑需要大量细粒度图标，统一基础设施避免各组件各自 import SVG；v1.0.6.31 起列头排序图标亦复用同一包装器。

#### 顶层 + 单件目录

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Monaco 编辑器 monaco | `MonacoEditor.vue` | Monaco 代码编辑器通用封装（`MonacoEditor extends Vue`，L12） |
| 批量按钮 batch-button | `BatchButton/index.vue` | 批量操作按钮（含下拉菜单） |
| 面包屑 breadcrumb | `Breadcrumb/index.vue` | 面包屑导航 |
| 侧边栏折叠 hamburger | `Hamburger/index.vue` | 侧边栏折叠按钮 |
| 分页 pagination | `Pagination/index.vue` | 分页组件封装 |
| 主题切换 theme-switcher | `ThemeSwitcher/index.vue` | 主题切换器（明/暗），触发器与选项图标统一使用 Lucide |

#### components/tasks/（3 个文件，任务专用组件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| Cron 编辑器 cron | `CronEditor.vue` | Cron 表达式可视化编辑器（`CronEditor`） |
| Python 类选择器 python-class | `PythonClassSelector.vue` | Python 类/方法选择器（`PythonClassSelector`） |
| 任务 Monaco 编辑器 tasks-monaco | `MonacoEditor.vue` | 任务专用 Monaco 编辑器（含 Python 高亮） |

#### components/torrents/（9 个 .vue + 1 个 .ts + 4 个测试）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 高级搜索构建 advanced-search | `AdvancedSearchBuilder.vue` | 高级搜索条件构建器（`AdvancedSearchBuilder` class）；v1.0.6.29 收紧正文/控件字号、组与条件间距，底部动作统一 small；状态逻辑位于 `advancedSearchState.ts` |
| 条件值输入 condition-value | `ConditionValueInput.vue` | 搜索条件值输入（按字段类型切换控件，`ConditionValueInput` class）；v1.0.6.28 起接入新的多选/标签控件 |
| 高级多选 advanced-multiselect | `AdvancedMultiSelect.vue` | 高级多选下拉（`AdvancedMultiSelect` class）；v1.0.6.29 改 32px 紧凑触发器 + 点击浮层，保留搜索/创建/已选区/虚拟滚动/快捷操作与 Lucide 图标；v1.0.6.30/31 增加常驻清空按钮并修复多选字段点击无响应 |
| 高级搜索状态 advanced-search-state | `advancedSearchState.ts` ✨v1.0.6.28 | 高级搜索可复用状态/纯逻辑（class-based store 无 .vue，从组件抽取的可单测模块，便于复用到传统视图） |
| 紧凑表格视图 compact-table | `CompactTable.vue` | ⚠ **Options API**（L301 `export default {`，`CompactTable`）：紧凑表格视图 |
| 重复种子检测 duplicate | `DuplicateTorrentsDialog.vue` | 重复种子检测对话框 |
| 大小过滤 size-range | `SizeRangeFilter.vue` | 种子大小范围过滤器（`SizeRangeFilter` class） |
| 虚拟滚动 virtual-scroll | `VirtualScrollList.vue` | 虚拟滚动列表（`VirtualScrollList` class） |
| 过滤组 filter-group | `FilterGroup.vue` | 过滤条件组容器（`FilterGroup` class） |
| 分页组合框 page-size | `PageSizeCombobox.vue` ✨v1.0.6.30 | 共享分页组合框（20/50/100/500/1000 预设 + 1–100000 自定义输入；被列表/传统两视图复用，统一每页数量交互） |
| 搜索组件测试 search-test | `__tests__/*.spec.ts`（4 个） | AdvancedMultiSelect（性能 466 + 单元 477）/ AdvancedSearchBuilder（609）/ ConditionValueInput（189）单测（共 1741 行） |

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
| 顶栏 navbar | `Navbar/index.vue` | 顶栏（折叠按钮/面包屑/反馈/通知/用户菜单），应用图标统一使用 Lucide |
| 侧边栏 sidebar | `Sidebar/index.vue` | 侧边栏容器（基于路由生成菜单），折叠控制使用 Lucide |
| 菜单项 sidebar-item | `Sidebar/SidebarItem.vue` | 单个菜单项（递归子菜单）；路由 meta icon 与子菜单箭头由 LucideIcon 渲染 |
| 菜单项链接 sidebar-item-link | `Sidebar/SidebarItemLink.vue` | 菜单项链接包装（外链/内链分流） |
| 通知抽屉 notification-drawer | `NotificationDrawer/index.vue` | 通知抽屉容器；标题、筛选、加载、空状态与关闭动作统一使用 Lucide |
| 通知项 notification-item | `NotificationDrawer/NotificationItem.vue` | 单条通知项，详情入口使用 Lucide |

> 注意：`components/index.ts` 只 re-export `AppMain/Navbar/Sidebar`，**未导出 NotificationDrawer**（需直接路径 import）。

#### layout/mixin/

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 响应式 mixin resize | `resize.ts` | class-based Mixin（`vue-property-decorator`）：响应式监听窗口宽度，写入 `AppModule.device` |

> layout 下**无 `permission.ts`**（路由守卫在 `src/permission.ts`，见 [entry/README.md](../entry/README.md)）。`resize.ts` 被 `Navbar/index.vue` 等通过 `mixins(ResizeMixin)` 消费。

---

## 关键观察

- **范式分布**：本分支 28 个文件中，27 个为 class-component；`components/torrents/CompactTable.vue` 是唯一的 Options API（全仓库 3 处之一）
- **Monaco Editor 双版本**：`components/MonacoEditor.vue`（通用）与 `components/tasks/MonacoEditor.vue`（任务专用，含 Python 高亮）
- **测试覆盖**：`components/torrents/__tests__/` 有 4 个测试文件（1741 行），覆盖 AdvancedMultiSelect / AdvancedSearchBuilder / ConditionValueInput

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`CronEditor.vue` 1269 行、`AdvancedSearchBuilder.vue` 1373 行）
