# frontend/components-layout — 通用组件与布局骨架

> 通用可复用组件（17 个 .vue）+ 布局骨架（layout/ 下 8 个 .vue + 1 mixin）。全部 class-component。

## components/ — 通用组件

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

### components/torrents/（8 个 .vue + 4 个测试）

| 文件 | 行数 | 范式 | 一句话职责 |
|------|------|------|-----------|
| `AdvancedSearchBuilder.vue` | 1533 | class（`AdvancedSearchBuilder`） | 高级搜索条件构建器 |
| `ConditionValueInput.vue` | 1007 | class（`ConditionValueInput`） | 搜索条件值输入（按字段类型切换控件） |
| `AdvancedMultiSelect.vue` | 908 | class（`AdvancedMultiSelect`） | 高级多选下拉（搜索/分组） |
| `CompactTable.vue` | 838 | ⚠ **Options API**（L301 `export default {`，`CompactTable`） | 紧凑表格视图 |
| `DuplicateTorrentsDialog.vue` | 404 | class | 重复种子检测对话框 |
| `SizeRangeFilter.vue` | 358 | class（`SizeRangeFilter`） | 种子大小范围过滤器 |
| `VirtualScrollList.vue` | 242 | class（`VirtualScrollList`） | 虚拟滚动列表 |
| `FilterGroup.vue` | 90 | class（`FilterGroup`） | 过滤条件组容器 |
| `__tests__/*.spec.ts`（4 个） | 1484 总 | 测试 | AdvancedMultiSelect（性能+单元）/ AdvancedSearchBuilder / ConditionValueInput 单测 |

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
- **测试覆盖**：`components/torrents/__tests__/` 有 4 个测试文件（1484 行），覆盖 AdvancedMultiSelect / AdvancedSearchBuilder / ConditionValueInput

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`CronEditor.vue` 1269 行、`AdvancedSearchBuilder.vue` 1533 行）
