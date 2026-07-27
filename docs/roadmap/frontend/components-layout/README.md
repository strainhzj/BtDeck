# frontend/components-layout — 通用组件与布局骨架

> 通用可复用组件（18 个 .vue）+ 布局骨架（layout/ 下 8 个 .vue + 1 mixin）。全部 class-component。

## components/ — 通用组件

### components/common/（1 个 .vue + 1 测试）✨v1.0.6.28

| 文件 | 行数 | class name | 一句话职责 |
|------|------|-----------|-----------|
| `LucideIcon.vue` | 152 | `LucideIcon extends Vue`（`@Component` + `vue-property-decorator`） | 轻量 Vue 2 包装器，统一渲染 Lucide 图标；静态具名 import 用到的图标（webpack 5 + sideEffects tree-shake，只打包所用图标，避免 ~2000 图标集入包）；stroke 跟随 `currentColor`，`size`/`strokeWidth` 通过 prop 透传。在 `main.ts:44` 全局注册 `Vue.component('LucideIcon', ...)` |
| `__tests__/LucideIcon.spec.ts` | 70 | — | LucideIcon 单测 |

> v1.0.6.28 引入 `lucide@^1.27.0` 依赖（`package.json`）。设计动机：高级搜索标签选择器重塑需要大量细粒度图标，统一基础设施避免各组件各自 import SVG。

### 顶层 + 单件目录

| 文件 | 行数 | class name | 一句话职责 |
|------|------|-----------|-----------|
| `MonacoEditor.vue` | 120 | `MonacoEditor extends Vue`（L12） | Monaco 代码编辑器通用封装 |
| `BatchButton/index.vue` | 100 | class | 批量操作按钮（含下拉菜单） |
| `Breadcrumb/index.vue` | 105 | class | 面包屑导航 |
| `Hamburger/index.vue` | 37 | class | 侧边栏折叠按钮 |
| `Pagination/index.vue` | 80 | class | 分页组件封装 |
| `ThemeSwitcher/index.vue` | 162 | class | 主题切换器（明/暗） |

### components/tasks/（3 个文件，任务专用组件）

| 文件 | 行数 | class name | 一句话职责 |
|------|------|-----------|-----------|
| `CronEditor.vue` | 1269 | `CronEditor` | Cron 表达式可视化编辑器 |
| `PythonClassSelector.vue` | 1357 | `PythonClassSelector` | Python 类/方法选择器 |
| `MonacoEditor.vue` | 658 | class | 任务专用 Monaco 编辑器（含 Python 高亮） |

### components/torrents/（8 个 .vue + 1 个 .ts + 4 个测试）

| 文件 | 行数 | 范式 | 一句话职责 |
|------|------|------|-----------|
| `AdvancedSearchBuilder.vue` | 1373 | class（`AdvancedSearchBuilder`） | 高级搜索条件构建器；v1.0.6.29 收紧正文/控件字号、组与条件间距，底部动作统一 small；状态逻辑位于 `advancedSearchState.ts` |
| `ConditionValueInput.vue` | 837 | class（`ConditionValueInput`） | 搜索条件值输入（按字段类型切换控件）；v1.0.6.28 起接入新的多选/标签控件（行数 1007→837） |
| `AdvancedMultiSelect.vue` | 1377 | class（`AdvancedMultiSelect`） | 高级多选下拉；v1.0.6.29 改为 32px 紧凑触发器 + 点击浮层，保留搜索/创建/已选区/虚拟滚动/快捷操作与 Lucide 图标 |
| `advancedSearchState.ts` ✨v1.0.6.28 | 674 | class-based store（无 .vue） | 高级搜索可复用状态/纯逻辑（从组件抽取的可单测模块，减少组件体积、便于复用到传统视图） |
| `CompactTable.vue` | 838 | ⚠ **Options API**（L301 `export default {`，`CompactTable`） | 紧凑表格视图 |
| `DuplicateTorrentsDialog.vue` | 404 | class | 重复种子检测对话框 |
| `SizeRangeFilter.vue` | 358 | class（`SizeRangeFilter`） | 种子大小范围过滤器 |
| `VirtualScrollList.vue` | 242 | class（`VirtualScrollList`） | 虚拟滚动列表 |
| `FilterGroup.vue` | 90 | class（`FilterGroup`） | 过滤条件组容器 |
| `__tests__/*.spec.ts`（4 个） | 1621 总 | 测试 | AdvancedMultiSelect（性能 466 + 单元 403）/ AdvancedSearchBuilder（609）/ ConditionValueInput（143）单测 |

> ⚠ `CompactTable.vue` 是全仓库 3 处 Options API 之一（技术债候选）。

## layout/ — 布局骨架

### 顶层

| 文件 | 行数 | class name | 一句话职责 |
|------|------|-----------|-----------|
| `index.vue` | 174 | class | 布局根容器（Sidebar + Navbar + AppMain 组合） |

### layout/components/

| 文件 | 行数 | class name | 一句话职责 |
|------|------|-----------|-----------|
| `index.ts` | 3 | — | barrel 导出 AppMain/Navbar/Sidebar |
| `AppMain.vue` | 25 | class | 主内容区 `<router-view>` 容器 |
| `Navbar/index.vue` | 316 | class | 顶栏（折叠按钮/面包屑/用户菜单/通知入口） |
| `Sidebar/index.vue` | 227 | class | 侧边栏容器（基于路由生成菜单） |
| `Sidebar/SidebarItem.vue` | 237 | class | 单个菜单项（递归子菜单） |
| `Sidebar/SidebarItemLink.vue` | 30 | class | 菜单项链接包装（外链/内链分流） |
| `NotificationDrawer/index.vue` | 519 | class | 通知抽屉容器 |
| `NotificationDrawer/NotificationItem.vue` | 187 | class | 单条通知项 |

> 注意：`components/index.ts` 只 re-export `AppMain/Navbar/Sidebar`，**未导出 NotificationDrawer**（需直接路径 import）。

### layout/mixin/

| 文件 | 行数 | 范式 | 一句话职责 |
|------|------|------|-----------|
| `resize.ts` | 55 | class-based Mixin（`vue-property-decorator`） | 响应式监听窗口宽度，写入 `AppModule.device` |

> layout 下**无 `permission.ts`**（路由守卫在 `src/permission.ts`，见 [entry/README.md](../entry/README.md)）。`resize.ts` 被 `Navbar/index.vue` 等通过 `mixins(ResizeMixin)` 消费。

---

## 关键观察

- **范式分布**：本分支 27 个文件中，26 个为 class-component；`components/torrents/CompactTable.vue` 是唯一的 Options API（全仓库 3 处之一）
- **Monaco Editor 双版本**：`components/MonacoEditor.vue`（通用）与 `components/tasks/MonacoEditor.vue`（任务专用，含 Python 高亮）
- **测试覆盖**：`components/torrents/__tests__/` 有 4 个测试文件（1621 行），覆盖 AdvancedMultiSelect / AdvancedSearchBuilder / ConditionValueInput

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`CronEditor.vue` 1269 行、`AdvancedSearchBuilder.vue` 1373 行）
