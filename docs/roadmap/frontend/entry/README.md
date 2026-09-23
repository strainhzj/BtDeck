# frontend/entry — 应用入口

> Vue 应用实例化、路由表、路由守卫、根组件、i18n。`src/` 顶层 6 个文件 + `i18n/` 目录。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/entry/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 应用入口 main | `main.ts` | 应用入口：初始化主题、注册插件、**Element Locale 挂接 vue-i18n（L50）**、Demo 会话旁路、清退历史 Workbox、双令牌会话监听（`initSessionWatch`）、挂载 #app（`new Vue({ router, store, i18n, ... })`）；2026-09-23 死代码清理：SvgIcon/vue-svgicon 注册退出（侧栏图标已全部 Lucide 化，由 i18n-leftover-guard 契约守护） |
| 路由表 router | `router.ts` | 路由表（default export）+ `requiredCapability` 元数据（回收站/孤儿/种子备份）+ **桌面路由 `titleKey` 双语键（21 处，移动路由不带保持中文）** + `router.push` 修补 + 部署后旧 chunk 一次恢复 |
| 路由守卫 permission | `permission.ts` | 全局路由守卫：token 判断、access token 过期主动续期三态分流；加载 `/platform/capabilities` 后对受限文件系统能力 fail-closed，Android 不支持入口重定向并提示；保留 GetUserInfo 瞬时错误分流、白名单、NProgress、**页面标题（L300 走 `resolvePageTitle`：titleKey 双语键优先）** |
| 双语 i18n | `i18n/` | 双语基础设施（P1 基础 + P2 首次使用闭环）：vue-i18n@8.28.2 单例 + zh-CN/en 消息树（P1 navigation/time/el；P2 新增 auth/common/settings/downloader/errors）+ 语言解析（手动偏好>浏览器语言>默认中文，localStorage `btdeck-lang`）+ 缺译回退 + `translate/translateChoice/routeTitle/resolvePageTitle` 同源入口 + `apiErrorMessage`（P2 错误契约：reasonCode→errors.byCode 本地化，禁中文匹配）；选型与风险见 PLANS/bilingual/p1-i18n-decision.md |；2026-09-21 P3-1：新增 search/torrent/dashboard 模块与 common.multiSelect/pageSize，契约链 labelEn（38 操作符，生成器+契约守卫同步）；2026-09-21 P3-2：新增 tracker/queryTemplate 模块，search 扩 builder/workspace/valueInput/sizeRange/templateDialog/validation/presets，torrent 扩 detail；2026-09-21 P4：errors.byCode 扩 33 键（种子操作/Tracker/查询模板/添加链路）+ errors.validation（E17 422 按 pydantic type/loc 字典化），`apiErrorMessage` 集成 422 分支 + 新增 `apiResponseMessage`（resolved 业务错误响应同源入口）；2026-09-19 P5：新增 recycleBin 模块、torrent 扩 deleteLevel 子树（四级删除确认按等级独立成键）、common.listSeparator、errors.byCode 扩 14 键（删除链路/回收站，累计 72 键）；2026-09-19 遗留清扫：新增 navigation.sidebar、common.pwa、downloader.msg、settings.capability、search.requestValidation 五个子树 + auth 4 键 + errors（http 状态表/httpFallback/unknown/contextFailed/network.checkSettings），并新增 `tests/unit/i18n-leftover-guard.spec.ts` 审计门禁（已译面扫描非注释中文 + 白名单 6 条含理由 + 腐化守卫，P6 计划内文件排除）；2026-09-19 P6-1：新增 transfer/fileManagement 模块与 tracker.replace 子树、torrent 扩传统视图键；审计集扩至 35 面并新增**全仓键可达性门禁**（1280 键；动态拼接键跳过）——抓出 Navbar `navbar.*` 错前缀（应为 navigation.navbar.*，8 处文案/aria 空串）与 SizeRangeFilter `search.sizeRange.unitPlaceholder` 错路径（应为 search.valueInput.*）；2026-09-19 P6-2：downloader 模块新增 tabs/speed/advanced/pathMapping/pathMaintenance/pathManagement/tag/template 八子树（~300 键）+ template.presets（5 内置模板预设，按 preset_key 展示映射，Q02 未识别原文回退）；2026-09-20 P6-3：tracker 模块新增十五子树（~500 条），errors.byCode 扩 18 键；2026-09-20 P6-4a：新增 tasks 模块（~330 键：任务页/日志/表单/三弹窗/cronEditor/monaco/pythonSelector），errors.byCode 扩 29 键（TASKS_*，后端 cron_tasks 契约对齐）；2026-09-20 P6-4b：新增 auditLogs/orphanFiles 两模块（操作类型 19 项双形态短/长标签、危险链路三要素、扫描状态与快捷操作），errors.byCode 扩 29 键（AUDIT_LOG_* 7 + ORPHAN_* 22，后端 audit_logs/orphan_files 契约对齐）；2026-09-20 P6-5 收口：common 扩 theme（三套名/描述/切换 toast）/demo（横幅四条）/clipboard（两态）/notFound.supportComing/notifications.failureRecord·failureUnknown，downloader 扩 sync（四态终态+detailSuffix）与 store（九条 action 兑底），errors 扩 paramValidation/requestError，torrent.list.filters 扩 activeStatus；审计门禁翻转为全桌面负向排除（原正向 65 面，详 test-coverage）；2026-09-22 dev1.0.7 合入：i18n 文件取 dev 完成态，dev1.0.7 的 P1 期版本弃用（见 PLANS/merge-dev107-into-dev.md）；✨2026-09-22 W5（MCP 服务密钥）：213bafa 新增 mcp 模块（面板/风险/msg 子树）+ moviepilot 模块后，本批扩 mcp.apikey 子树（服务密钥卡 24 键：端点/认证头提示/三态引导/复制/危险确认/安全提示）与 msg 四键（generated/rotated/rotateFailed/apikeyConflict），errors.byCode 扩 2 键（mcpApiKeyConflict/mcpApiKeyInvalid，后端 reasonCode 对齐）；能力目录描述双语改由后端成对下发 descriptionEn（面板 capDescription 按 locale 选取，与 P3-1 labelEn 同模式），语言包不再维护能力描述副本 |
| 根组件 app | `App.vue` | 根组件（class-component），在 `<router-view />` 外挂载 Demo 模式提示条 |
| PWA 注册 service-worker | `registerServiceWorker.ts` | 历史 PWA 注册助手；当前 `main.ts` 不导入，启动逻辑会清退旧注册 |
| TS 声明 shims-vue | `shims-vue.d.ts` | 为 .vue 文件提供 TS 模块声明（`declare module '*.vue'`） |

---

## main.ts 关键（L1-87）

- L29-32：先 `initTheme()` 再 import 其它（主题早期初始化）
- L50 `ElementLocale.i18n(...)` 先于 L51 `Vue.use(ElementUI)`（Element 内置文案随界面语言响应式切换）
- L58 `Vue.directive('waves', waves)`
- L72 `retireLegacyServiceWorkers()` 只清退根作用域旧注册与 BtDeck Workbox cache
- L65-66 Demo 模式初始化固定脱敏会话；真实模式仍在 L78 启用 `initSessionWatch()` 双令牌会话监听
- L82-83 初始异步路由成功后清理 chunk 恢复 query
- router.ts L7 `Vue.use(Router)`；store/index.ts L8 `Vue.use(Vuex)`
- L90-95：`new Vue({ router, store, i18n, render: (h) => h(App) }).$mount('#app')`（i18n 根实例注入，组件层 $t 同一翻译源）

## router.ts 路由表（L30-390，文件共 476 行；桌面路由 meta 另含 `titleKey` 双语键，移动路由无）

| 路径 | 组件 | 行号 |
|------|------|------|
| `/login` | `@/views/login/index.vue` | L32 |
| `/404` | `@/views/404.vue` | L37 |
| `/m/login` | `@/views/mobile/login.vue` | L43 |
| `/m`（MobileLayout，redirect → `/m/dashboard`，L49-51；13 children） | dashboard / downloader / torrents(+detail) / search / query-templates(redirect→`/m/search`) / recycle-bin / logs / downloader-settings / tracker×2 / tasks / orphan-files / notifications / settings | L53-147 |
| `/` → `/dashboard`（Layout） | `@/views/dashboard/index.vue` | L150 |
| `/downloader` | `@/views/downloader/index.vue` | L160 |
| `/torrents`（5 children，redirect → `/torrents/index`；✨2026-09-23 查询模板归组，可见顺序 种子列表→查询模板→种子文件管理） | TorrentViewSwitcher / TraditionalView(hidden) / QueryTemplates / FileManagement / index(detail) | L175 |
| `/tasks` | `@/views/tasks/index.vue` | L237 |
| `/tracker`（4 children） | keywords-board / keywords-search / reannounce-config / test | L252 |
| `/task-logs` | redirect `/tasks?tab=logs` | L302 |
| `/logs/audit` | `@/views/logs/audit.vue` | L309 |
| `/recycle-bin` | `@/views/recycle-bin/index.vue` | L330 |
| `/orphan-files` | `@/views/orphan-files/index.vue` | L347 |
| `/settings`（redirect → `/settings/index`） | `@/views/settings/index.vue` | L365 |
| `/query-templates`（✨2026-09-23 归入 /torrents 组，旧顶层深链兑底） | redirect `/torrents/query-templates`（`/query-templates/index` 同目标） | L385/L390 |
| `*` | redirect `/404` | L395 |

> `/m/query-templates` 移动查询模板页已裁撤（仅保留高级搜索）：路由表保留深链 redirect 到 `/m/search`；桌面 `/query-templates` 2026-09-23 归入 `/torrents` 组（`/torrents/query-templates`），旧顶层两路径保留 redirect 兑底，移动模式经 `toMobilePath()` 精确分支落 `/m/search`；`/m/settings`（L137）整页复用桌面设置组件（双因素认证 + 修改密码）。

文件末尾 L404-463 自定义 `router.push`（及 `router.replace`）捕获 `NavigationFailure`（守卫改道/中止/重复导航不再作为异常上抛）；L465 的 `router.onError` 在旧 runtime 请求已下线路由 chunk 时触发一次整页版本恢复，并对重复失败显示手动刷新提示。

## permission.ts 关键（L1-301）

- L15 `loginPaths = ['/login', '/m/login']`（双模式登录白名单）
- L24 `uiModeRedirectPath()`（UI 模式分流，认证前执行）：移动模式访问已移动化桌面顶层页（含 `/settings`；`/torrents/query-templates` 在 `/torrents` 通配前精确拦截落 `/m/search`，旧顶层 `/query-templates*` 路径 redirect 解析后同链路）经 `toMobilePath()` 落对应 `/m/*` 页；桌面模式访问 `/m/*` 回对应桌面页（`/m/torrents`→`/torrents`、`/m/settings`→`/settings`，其余落 `/dashboard`）
- L56 强制改密拦截（安全修复 W9 + 死锁修复）：`forceChangeAllowedPaths = ['/settings/index', '/settings', '/m/settings']`（放行白名单，含移动设置页）+ `isForceChangeBlocked()` 判定 + `forceChangeTargetPath()` 按当前 UI 模式选落点（移动 `/m/settings`、桌面 `/settings/index`）+ `forceChangeRedirect()`（L70）重定向 `?forceChange=1` 并弹 ElementUI `Message.warning("请先修改密码…")`（3 秒节流防堆叠——拦截重定向回同一路径时设置页不重新挂载，点其它菜单的反馈只能由守卫给）
- L89 `isTransientError`（ApiError 网络 '0' 与业务 5xx 瞬时失败判定）+ L97 `abortNavigation`：`next(false)` 中止导航 + 网络波动提示 + 手动 `NProgress.done()`（中止导航 afterEach 不触发，进度条须手动收尾），保留令牌与会话现场
- L130 `router.beforeEach`：
  - L136 `enforceRouteCapability()`：能力接口失败时对路径映射/孤儿/备份/转移/三级删除受限入口闭锁，伴侣模式只消费远端矩阵
  - L145-168 会话主动过期检查三态分流：`isTokenExpired(UserModule.token)` 为真先 `trySilentRefresh()`——续期成功继续导航；transient 网络抖动不杀会话（roles 已有放行自愈 / roles 空中止导航，连续中止 3 次回落登出）；rejected `ExpireSession()` 跳登录（保留 refresh cookie，防跨标签轮换竞态）
  - L142 若 `UserModule.token` 存在：访问登录页重定向；否则若 `roles.length===0` 调 `UserModule.GetUserInfo()`（L191），**成功后同样检查强制改密标志拦截**（闭合登录后/F5 后首导航放行缺口），失败分流——瞬时失败中止导航，其余 `ExpireSession()` 跳登录（全部经 `loginPathForMode` 按模式选登录页）
  - L210-221 roles 已就绪分支：`isForceChangeBlocked()` 拦截一切非改密页导航（事故前白名单写父路径 `/settings`，落点内容区空白 + 真实路径又被弹回 = 死锁）
- L231-240 无 token：白名单放行，否则跳登录带 redirect
- L290 `router.afterEach`：结束 NProgress、清零瞬时中止计数；L300 设 `document.title = resolvePageTitle(to)`（L6 导入自 `@/i18n`：titleKey 双语键优先，无 titleKey 的移动路由回退中文 meta.title，均无则 'BtDeck'；语言切换后的标题刷新由切换入口显式调用，vue-i18n@8 无公开 locale 订阅 API）

> **守卫不在 router.ts**：router.ts 只导出 `router` 实例；守卫逻辑由 `permission.ts` 通过 `router.beforeEach` 注册，由 `main.ts` L37 `import '@/permission'` 触发副作用。
> **标志双通道下发**：`mustChangePassword` 由登录响应与 `/user/info`（后端 cuser.py）下发，store `GetUserInfo` 同步（字段缺失不覆盖，防滚动部署误清）。

> Demo 分支：`permission.ts` L142 起在 `VUE_APP_DEMO_MODE=true` 时注入本地会话并跳过真实认证；`App.vue` L22 挂载 `DemoModeBanner`。

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`router.ts` 路由表 + `permission.ts` 守卫机制）
