# frontend/utils-types — 工具 / 类型 / 常量 / 指令

> 横切工具层：通用工具函数、TypeScript 类型定义、常量、自定义指令。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/utils-types/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

### utils/（13 个 .ts 文件）

> 另有 `utils/empty-polyfill.js`（polyfill，.js 非 .ts，跳过）。

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 格式化工具 formatters | `formatters.ts` ✨2026-08-16 | 🔵 通用格式化：种子/分页/状态归一化（`normalizeTorrentStatus` 折叠 qB 全量状态词表 metaDL/pausedDL/checkingDL 等到统一七态，未识别归 unknown）、debounce/throttle、错误消息提取与 toast、文件大小/速度/日期/ratio/时长/百分比/相对时间格式化、`getTorrentId`/`getDownloaderId`（L595 默认导出聚合） |
| Tracker 工具 tracker | `tracker.ts` | Tracker 工具：`LANGUAGE_LABELS`/`KEYWORD_TYPE_OPTIONS`/`PRIORITY_RANGE`、语言/类型/优先级标签、`debounce`/`formatDateTime`/`extractErrorMessage`/`downloadJSON`/`parseJSON`/`validateKeywordData` |
| 主题核心 theme | `theme.ts` | 主题核心：`ThemeType`/`ThemeConfig`、`THEMES`（翡翠绿/活力橙/石墨灰）、`getCurrentTheme`/`setTheme`/`toggleTheme`/`onThemeChange`/`initTheme`/`getThemeConfig`/`getAllThemes` |
| 主题管理器 theme-manager | `theme-manager.ts` | 主题管理器扩展层：`ThemeConfig`（含 Rgb 调色板）、`THEMES: Record<ThemeType, ThemeConfig>`、`ThemeManager` class（L78） |
| axios 封装 request | `request.ts` | 🔵 axios 封装（详见下方） |
| 会话维护 session | `session.ts` ✨2026-08-17 | 🔵 双令牌会话主动维护（纯逻辑为主，便于单测）：`getTokenExp`/`isTokenExpired`（JWT exp 解析，畸形不误杀）、`buildLoginRedirectTarget`（hash 模式登录跳转 URL）、`syncTokenFromCookie`（标签页可见时 cookie→内存快照回同步）、`initSessionWatch`（visibilitychange/focus 监听，他标签登出→统一跳登录） |
| 单飞刷新 token-refresh | `token-refresh.ts` ✨2026-08-18 三态 | 401 静默续期单飞编排（依赖注入纯模块）：并发 401 共享一次刷新批，三态结果（renewed/rejected/transient，`isDefiniteFailure` 判定后端明确 401 才判死），definite 失败后重读 cookie 追他标签轮换新值有限重试（上限 3 次） |
| 错误归一化 error-normalize | `error-normalize.ts` | 🔵 错误归一化纯逻辑（无副作用，便于单测）：`SUCCESS_CODES`、`extractFromDetail`、`isLoginRequest`、`buildBusinessError`/`buildNetworkError`/`buildHttpError` |
| 部署恢复 deployment-recovery | `deployment-recovery.ts` | 部署版本恢复：识别旧 webpack chunk 失败、一次整页切换与循环门禁、恢复 query 清理、历史根作用域 Workbox 注册/cache 清退 |
| 下载器类型 downloader-type | `downloaderType.ts` | 下载器类型枚举（`DOWNLOADER_TYPE`/`DOWNLOADER_TYPE_NAME`）+ 数字↔字符串↔标签互转 |
| 存储 cookies | `cookies.ts` | sidebar status / 双令牌 access+refresh token（cookie） / userId（localStorage） + 通用 `getStorage`/`setStorage` |
| 剪贴板 clipboard | `clipboard.ts` ✨v1.0.6.36 | 剪贴板复制回退：`copyTextToClipboard` 优先 Clipboard API，HTTP/旧浏览器/权限拒绝时回退隐藏 textarea + execCommand（保证局域网部署可复制） |
| 校验 validate | `validate.ts` | 极简校验：`isValidUsername`（硬编码 admin/editor）、`isExternal` |

#### request.ts 关键（axios/Demo 分流封装，L1-300）

- L20 `const service = axios.create({ baseURL: process.env.VUE_APP_BASE_API, timeout: 20000 })`
- L49 `NETWORK_TOAST_THROTTLE_MS` + L54 `notifyNetworkError`：网络错误 toast 3 秒同文案节流（断网+1 秒轮询不洪泛，窗口到期复位）
- L108 `refreshDeps`（刷新依赖注入：doRefresh 调 `/auth/refresh`，saveTokens 更新内存+cookie，`isDefiniteFailure` = ApiError code '401' 才判死）
- L90 `redirectToLogin`（导出）：hash 模式感知跳转 `/#/login?redirect=<hash内路由>`，3 秒防抖窗口自动复位 + 过期提示 toast；改用 `UserModule.ExpireSession()`（保留共享 cookie——refresh 防跨标签轮换竞态、access 防他标签 syncTokenFromCookie 级联误杀）
- L137 `trySilentRefresh`（导出）：守卫/会话监听的主动续期入口，返回三态 RefreshOutcome
- L145 `handleUnauthorized`：401 统一处理——renewed 重放一次 / rejected 登出 / transient（网络抖动）不清 token 不跳转、原请求以刷新的网络错误拒绝待自愈
- L166 请求拦截器：注入 `Authorization: Bearer`（每次现读 `UserModule.token`）
- L201 响应拦截器：处理 blob / 成功码(200/202/206/207) / 业务错误 / 网络错误（节流 toast）/ HTTP 错误
- L271-280 `requestClient`：Demo 开关打开时转本地 `demoRequest`，真实模式走 Axios；L280 保留 `service.defaults` 兼容 adapter 注入，L300 导出统一请求客户端

#### error-normalize.ts 关键

- L19 `export const SUCCESS_CODES = new Set(['200', '202', '206', '207'])`
- L33-60 `extractFromDetail`：处理 array(422)/对象 envelope/字符串/兜底四态
- L100-135 `buildBusinessError` / `buildNetworkError` / `buildHttpError` 全部返回 `ApiError`（来自 `@/types/api`）

### types/（8 个 .ts 文件）

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 种子管理类型 torrent | `torrent.ts` | 🔵 种子管理类型（最大）：`TorrentStatus` enum、`Torrent`/`TrackerInfo`/`Downloader`、列表参数/响应（含实时 `downloadComplete` 完成证据）、`AdvancedSearchParams`/`ConditionGroup`/`Condition`、`TorrentAuditLog`、`AuditOperationType`/`AuditOperationResult`/`DeleteLevel` enum、回收站/清理参数 |
| 通用工具类型 common | `common.ts` | 通用工具类型：`Partial/Required/Pick/Omit/DeepReadonly/DeepPartial/ReturnType/Parameters/UnwrapPromise` 等高阶类型 + `KeyValuePair/ID/Timestamp/SortConfig/UploadFile` |
| 统一入口 index | `index.ts` | 统一入口：`BTDeckTypes` 命名空间（L21-99）+ re-export api/scheduled-tasks/task-logs/components/common（⚠ 不 re-export torrent/dashboard） |
| 定时任务类型 scheduled-tasks | `scheduled-tasks.ts` | 定时任务类型：`TaskType`/`TaskStatus` enum、`ScheduledTask`、CRUD 请求、清理配置/预览/执行 |
| 组件类型 components | `components.ts` | 组件类型：`TableColumn`/`FormRule`/`PaginationConfig`/`SearchFormConfig`/`ActionButton`/`StatisticCard` + `TASK_STATUS_OPTIONS`/`TASK_TYPE_OPTIONS` 常量 |
| API 通用类型 api | `api.ts` | API 通用类型：`ApiResponse<T>`/`PaginationParams`/`PaginatedResponse<T>`/`RequestConfig`/`ErrorResponse`/`ApiError`（class extends Error, L63） |
| 任务日志类型 task-logs | `task-logs.ts` | 任务日志类型：`TaskLog`、列表/删除/统计/清理/导出请求/详情 |
| 仪表盘类型 dashboard | `dashboard.ts` | 仪表盘类型：`DownloaderStats`/`TorrentStats`/`TaskStats`/`SystemStats`/`DashboardData` 等 |

### constants/

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 种子状态配置 status-config | `status-config.ts` ✨2026-08-16 | 与后端 `QBITTORRENT_STATUS_MAP` 对齐的种子状态统一选项（`StatusOption` 接口 + `STATUS_OPTIONS`，label/value/originalStates）；`STATUS_TEXT_MAP`/`STATUS_ICON_MAP` 含 completed/unknown 文案与图标兜底 |
| 状态配置测试 status-config-test | `__tests__/status-config.spec.ts` | status-config 回归测试：守住 emoji→Lucide 改造契约——`StatusOption.icon` 必填 Lucide 图标名、label 纯文本无 emoji 前缀、`STATUS_ICON_MAP`/`getStatusIcon` 返回图标名并以 `help-circle` 兜底 |

### directive/waves/

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 涟漪指令 waves | `waves/index.ts` | 实现 `v-waves` 涟漪点击效果（default export `DirectiveOption`）：`bind` 钩子监听 click，动态创建 `.waves-ripple` span 并注入 CSS keyframes（L54-70 追加 `<style>` 到 head） |

---

## 关键观察

- **axios 封装集中**：`utils/request.ts`（263 行）+ `utils/error-normalize.ts`（139 行）是所有 API 调用的底座
- **主题双文件**：`theme.ts`（核心类型与切换）+ `theme-manager.ts`（扩展调色板）分工
- **类型分散**：共享类型在 `types/`，但大量 interface 直接定义在 `api/*.ts` 内（如 `torrents.ts` 54 个 interface）
- **`types/index.ts` 不全 re-export**：`torrent` 和 `dashboard` 需直接路径 import

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`request.ts` axios 封装、`formatters.ts` 606 行工具集）
