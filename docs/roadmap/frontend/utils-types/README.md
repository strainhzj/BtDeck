# frontend/utils-types — 工具 / 类型 / 常量 / 指令

> 横切工具层：通用工具函数、TypeScript 类型定义、常量、自定义指令。

## utils/（11 个 .ts 文件）

> 另有 `utils/empty-polyfill.js`（polyfill，.js 非 .ts，跳过）。

| 文件 | 行数 | 导出数 | 一句话职责 |
|------|------|--------|-----------|
| `formatters.ts` | 582 | 21 | 🔵 通用格式化：种子/分页/状态归一化、debounce/throttle、错误消息提取与 toast、文件大小/速度/日期/ratio/时长/百分比/相对时间格式化、`getTorrentId`/`getDownloaderId`（L571 默认导出聚合） |
| `tracker.ts` | 233 | 13 | Tracker 工具：`LANGUAGE_LABELS`/`KEYWORD_TYPE_OPTIONS`/`PRIORITY_RANGE`、语言/类型/优先级标签、`debounce`/`formatDateTime`/`extractErrorMessage`/`downloadJSON`/`parseJSON`/`validateKeywordData` |
| `theme.ts` | 157 | 12 | 主题核心：`ThemeType`/`ThemeConfig`、`THEMES`（翡翠绿/活力橙/石墨灰）、`getCurrentTheme`/`setTheme`/`toggleTheme`/`onThemeChange`/`initTheme`/`getThemeConfig`/`getAllThemes` |
| `theme-manager.ts` | 161 | 5 | 主题管理器扩展层：`ThemeConfig`（含 Rgb 调色板）、`THEMES: Record<ThemeType, ThemeConfig>`、`ThemeManager` class（L78） |
| `request.ts` | 161 | 3 | 🔵 axios 封装（详见下方） |
| `error-normalize.ts` | 135 | 7 | 🔵 错误归一化纯逻辑（无副作用，便于单测）：`SUCCESS_CODES`、`extractFromDetail`、`isLoginRequest`、`buildBusinessError`/`buildNetworkError`/`buildHttpError` |
| `deployment-recovery.ts` | 194 | 13 | 部署版本恢复：识别旧 webpack chunk 失败、一次整页切换与循环门禁、恢复 query 清理、历史根作用域 Workbox 注册/cache 清退 |
| `downloaderType.ts` | 73 | 5 | 下载器类型枚举（`DOWNLOADER_TYPE`/`DOWNLOADER_TYPE_NAME`）+ 数字↔字符串↔标签互转 |
| `cookies.ts` | 27 | 10 | sidebar status / token / userId（localStorage） + 通用 `getStorage`/`setStorage` |
| `clipboard.ts` ✨v1.0.6.36 | 45 | 1 | 剪贴板复制回退：`copyTextToClipboard` 优先 Clipboard API，HTTP/旧浏览器/权限拒绝时回退隐藏 textarea + execCommand（保证局域网部署可复制） |
| `validate.ts` | 3 | 2 | 极简校验：`isValidUsername`（硬编码 admin/editor）、`isExternal` |

### request.ts 关键（axios 封装，L1-161）

- L1 `import axios, { AxiosRequestConfig } from 'axios'`
- L3 `import { UserModule } from '@/store/modules/user'`（401 时 ResetToken）
- L13 `const service = axios.create({ baseURL: process.env.VUE_APP_BASE_API, timeout: 20000 })`
- L19-24 `export interface ApiEnvelope<T = unknown> { status; msg; code; data: T }`（与后端 `CommonResponse` 对齐）
- L26 `RequestClient` 类型
- L56 `redirectToLogin`（401 防抖）
- L65 请求拦截器：注入 `Authorization: Bearer`
- L100 响应拦截器：处理 blob / 成功码(200/206/207) / 业务错误 / 网络错误 / HTTP 错误
- L161 `export default service as unknown as RequestClient`

### error-normalize.ts 关键

- L19 `export const SUCCESS_CODES = new Set(['200', '206', '207'])`
- L33-60 `extractFromDetail`：处理 array(422)/对象 envelope/字符串/兜底四态
- L100-135 `buildBusinessError` / `buildNetworkError` / `buildHttpError` 全部返回 `ApiError`（来自 `@/types/api`）

## types/（8 个 .ts 文件）

| 文件 | 行数 | 导出数 | 一句话职责 |
|------|------|--------|-----------|
| `torrent.ts` | 492 | 29 | 🔵 种子管理类型（最大）：`TorrentStatus` enum、`Torrent`/`TrackerInfo`/`Downloader`、列表参数/响应、`AdvancedSearchParams`/`ConditionGroup`/`Condition`、`TorrentAuditLog`、`AuditOperationType`/`AuditOperationResult`/`DeleteLevel` enum、回收站/清理参数 |
| `common.ts` | 138 | 36 | 通用工具类型：`Partial/Required/Pick/Omit/DeepReadonly/DeepPartial/ReturnType/Parameters/UnwrapPromise` 等高阶类型 + `KeyValuePair/ID/Timestamp/SortConfig/UploadFile` |
| `index.ts` | 131 | 7 | 统一入口：`BTDeckTypes` 命名空间（L21-99）+ re-export api/scheduled-tasks/task-logs/components/common（⚠ 不 re-export torrent/dashboard） |
| `scheduled-tasks.ts` | 166 | 17 | 定时任务类型：`TaskType`/`TaskStatus` enum、`ScheduledTask`、CRUD 请求、清理配置/预览/执行 |
| `components.ts` | 127 | 12 | 组件类型：`TableColumn`/`FormRule`/`PaginationConfig`/`SearchFormConfig`/`ActionButton`/`StatisticCard` + `TASK_STATUS_OPTIONS`/`TASK_TYPE_OPTIONS` 常量 |
| `api.ts` | 108 | 6 | API 通用类型：`ApiResponse<T>`/`PaginationParams`/`PaginatedResponse<T>`/`RequestConfig`/`ErrorResponse`/`ApiError`（class extends Error, L63） |
| `task-logs.ts` | 76 | 9 | 任务日志类型：`TaskLog`、列表/删除/统计/清理/导出请求/详情 |
| `dashboard.ts` | 56 | 8 | 仪表盘类型：`DownloaderStats`/`TorrentStats`/`TaskStats`/`SystemStats`/`DashboardData` 等 |

## constants/

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `status-config.ts` | 104 | `StatusOption` 接口 + `STATUS_OPTIONS: StatusOption[]`（L22） | 与后端 `QBITTORRENT_STATUS_MAP` 对齐的种子状态统一选项（label/value/originalStates） |

## directive/waves/

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `waves/index.ts` | 70 | default export `waves: DirectiveOption`（L10） | 实现 `v-waves` 涟漪点击效果：`bind` 钩子监听 click，动态创建 `.waves-ripple` span 并注入 CSS keyframes（L54-70 追加 `<style>` 到 head） |

---

## 关键观察

- **axios 封装集中**：`utils/request.ts`（161 行）+ `utils/error-normalize.ts`（135 行）是所有 API 调用的底座
- **主题双文件**：`theme.ts`（核心类型与切换）+ `theme-manager.ts`（扩展调色板）分工
- **类型分散**：共享类型在 `types/`，但大量 interface 直接定义在 `api/*.ts` 内（如 `torrents.ts` 45 个 iface）
- **`types/index.ts` 不全 re-export**：`torrent` 和 `dashboard` 需直接路径 import

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`request.ts` axios 封装、`formatters.ts` 582 行工具集）
