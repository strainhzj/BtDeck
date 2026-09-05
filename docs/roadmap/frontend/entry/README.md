# frontend/entry — 应用入口

> Vue 应用实例化、路由表、路由守卫、根组件。`src/` 顶层 6 个文件。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/entry/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 应用入口 main | `main.ts` | 应用入口：初始化主题、注册插件、Demo 会话旁路、清退历史 Workbox、双令牌会话监听（`initSessionWatch`）、挂载 #app（`new Vue(...)`） |
| 路由表 router | `router.ts` | 路由表（default export）+ `router.push` 修补 + 部署后旧 chunk 一次恢复 |
| 路由守卫 permission | `permission.ts` | 全局路由守卫：token 判断、access token 过期主动续期三态分流（`isTokenExpired`+`trySilentRefresh`：renewed 放行 / rejected `ExpireSession` 登出 / transient 中止导航保留会话）、GetUserInfo 瞬时错误分流（`isTransientError`：网络 '0' 与业务 5xx 均中止保留会话；连续 3 次中止逃生回落登出防持久故障卡死，afterEach 清零）、白名单、NProgress、页面标题（`router.beforeEach` / `afterEach`） |
| 根组件 app | `App.vue` | 根组件（class-component），在 `<router-view />` 外挂载 Demo 模式提示条 |
| PWA 注册 service-worker | `registerServiceWorker.ts` | 历史 PWA 注册助手；当前 `main.ts` 不导入，启动逻辑会清退旧注册 |
| TS 声明 shims-vue | `shims-vue.d.ts` | 为 .vue 文件提供 TS 模块声明（`declare module '*.vue'`） |

---

## main.ts 关键（L1-89）

- L28-31：先 `initTheme()` 再 import 其它（主题早期初始化）
- L46 `Vue.use(ElementUI)`
- L52-55 `Vue.use(SvgIcon, {tagName:'svg-icon', ...})`
- L59 `Vue.directive('waves', waves)`
- L72 `retireLegacyServiceWorkers()` 只清退根作用域旧注册与 BtDeck Workbox cache
- L65-66 Demo 模式初始化固定脱敏会话；真实模式仍在 L78 启用 `initSessionWatch()` 双令牌会话监听
- L82-83 初始异步路由成功后清理 chunk 恢复 query
- router.ts L7 `Vue.use(Router)`；store/index.ts L8 `Vue.use(Vuex)`
- L85-89：`new Vue({ router, store, render: (h) => h(App) }).$mount('#app')`

## router.ts 路由表（L30-368，文件共 452 行）

| 路径 | 组件 | 行号 |
|------|------|------|
| `/login` | `@/views/login/index.vue` | L32 |
| `/404` | `@/views/404.vue` | L37 |
| `/m/login` | `@/views/mobile/login.vue` | L43 |
| `/m`（MobileLayout，redirect → `/m/dashboard`，L49-51；13 children） | dashboard / downloader / torrents(+detail) / search / query-templates(redirect→`/m/search`) / recycle-bin / logs / downloader-settings / tracker×2 / tasks / orphan-files / notifications / settings | L53-141 |
| `/` → `/dashboard`（Layout） | `@/views/dashboard/index.vue` | L144 |
| `/downloader` | `@/views/downloader/index.vue` | L159 |
| `/torrents`（4 children，redirect → `/torrents/index`） | TorrentViewSwitcher / TraditionalView / FileManagement / index(detail) | L173 |
| `/tasks` | `@/views/tasks/index.vue` | L218 |
| `/tracker`（4 children） | keywords-board / keywords-search / reannounce-config / test | L232 |
| `/task-logs` | redirect `/tasks?tab=logs` | L277 |
| `/logs/audit` | `@/views/logs/audit.vue` | L284 |
| `/recycle-bin` | `@/views/recycle-bin/index.vue` | L303 |
| `/orphan-files` | `@/views/orphan-files/index.vue` | L317 |
| `/settings`（redirect → `/settings/index`） | `@/views/settings/index.vue` | L332 |
| `/query-templates` | `@/views/query-templates/index.vue` | L349 |
| `*` | redirect `/404` | L364 |

> `/m/query-templates` 移动查询模板页已裁撤（仅保留高级搜索）：路由表保留深链 redirect 到 `/m/search`；`/m/settings`（L137）整页复用桌面设置组件（双因素认证 + 修改密码）。

文件末尾 L380-437 自定义 `router.push`（及 `router.replace`）捕获 `NavigationFailure`（守卫改道/中止/重复导航不再作为异常上抛）；L441 的 `router.onError` 在旧 runtime 请求已下线路由 chunk 时触发一次整页版本恢复，并对重复失败显示手动刷新提示。

## permission.ts 关键（L1-268）

- L15 `loginPaths = ['/login', '/m/login']`（双模式登录白名单）
- L24 `uiModeRedirectPath()`（UI 模式分流，认证前执行）：移动模式访问已移动化桌面顶层页（含 `/settings` 与裁撤后的 `/query-templates`）经 `toMobilePath()` 落对应 `/m/*` 页；桌面模式访问 `/m/*` 回对应桌面页（`/m/torrents`→`/torrents`、`/m/settings`→`/settings`，其余落 `/dashboard`）
- L56 强制改密拦截（安全修复 W9 + 死锁修复）：`forceChangeAllowedPaths = ['/settings/index', '/settings', '/m/settings']`（放行白名单，含移动设置页）+ `isForceChangeBlocked()` 判定 + `forceChangeTargetPath()` 按当前 UI 模式选落点（移动 `/m/settings`、桌面 `/settings/index`）+ `forceChangeRedirect()`（L70）重定向 `?forceChange=1` 并弹 ElementUI `Message.warning("请先修改密码…")`（3 秒节流防堆叠——拦截重定向回同一路径时设置页不重新挂载，点其它菜单的反馈只能由守卫给）
- L89 `isTransientError`（ApiError 网络 '0' 与业务 5xx 瞬时失败判定）+ L97 `abortNavigation`：`next(false)` 中止导航 + 网络波动提示 + 手动 `NProgress.done()`（中止导航 afterEach 不触发，进度条须手动收尾），保留令牌与会话现场
- L130 `router.beforeEach`：
  - L145-168 会话主动过期检查三态分流：`isTokenExpired(UserModule.token)` 为真先 `trySilentRefresh()`——续期成功继续导航；transient 网络抖动不杀会话（roles 已有放行自愈 / roles 空中止导航，连续中止 3 次回落登出）；rejected `ExpireSession()` 跳登录（保留 refresh cookie，防跨标签轮换竞态）
  - L142 若 `UserModule.token` 存在：访问登录页重定向；否则若 `roles.length===0` 调 `UserModule.GetUserInfo()`（L191），**成功后同样检查强制改密标志拦截**（闭合登录后/F5 后首导航放行缺口），失败分流——瞬时失败中止导航，其余 `ExpireSession()` 跳登录（全部经 `loginPathForMode` 按模式选登录页）
  - L210-221 roles 已就绪分支：`isForceChangeBlocked()` 拦截一切非改密页导航（事故前白名单写父路径 `/settings`，落点内容区空白 + 真实路径又被弹回 = 死锁）
- L231-240 无 token：白名单放行，否则跳登录带 redirect
- L259-267 `router.afterEach`：结束 NProgress、清零瞬时中止计数并设 `document.title`（默认 'BtDeck'）

> **守卫不在 router.ts**：router.ts 只导出 `router` 实例；守卫逻辑由 `permission.ts` 通过 `router.beforeEach` 注册，由 `main.ts` L37 `import '@/permission'` 触发副作用。
> **标志双通道下发**：`mustChangePassword` 由登录响应与 `/user/info`（后端 cuser.py）下发，store `GetUserInfo` 同步（字段缺失不覆盖，防滚动部署误清）。

> Demo 分支：`permission.ts` L142 起在 `VUE_APP_DEMO_MODE=true` 时注入本地会话并跳过真实认证；`App.vue` L22 挂载 `DemoModeBanner`。

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`router.ts` 路由表 + `permission.ts` 守卫机制）
