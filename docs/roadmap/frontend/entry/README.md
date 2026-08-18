# frontend/entry — 应用入口

> Vue 应用实例化、路由表、路由守卫、根组件。`src/` 顶层 6 个文件。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/entry/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 应用入口 main | `main.ts` | 应用入口：初始化主题、注册插件、清退历史 Workbox、双令牌会话监听（`initSessionWatch`）、挂载 #app（`new Vue(...)`） |
| 路由表 router | `router.ts` | 路由表（default export）+ `router.push` 修补 + 部署后旧 chunk 一次恢复 |
| 路由守卫 permission | `permission.ts` | 全局路由守卫：token 判断、access token 过期主动续期三态分流（`isTokenExpired`+`trySilentRefresh`：renewed 放行 / rejected `ExpireSession` 登出 / transient 中止导航保留会话）、GetUserInfo 网络错误分流、白名单、NProgress、页面标题（`router.beforeEach` / `afterEach`） |
| 根组件 app | `App.vue` | 根组件（class-component），仅 `<div id="app"><router-view /></div>` |
| PWA 注册 service-worker | `registerServiceWorker.ts` | 历史 PWA 注册助手；当前 `main.ts` 不导入，启动逻辑会清退旧注册 |
| TS 声明 shims-vue | `shims-vue.d.ts` | 为 .vue 文件提供 TS 模块声明（`declare module '*.vue'`） |

---

## main.ts 关键（L1-78）

- L28-31：先 `initTheme()` 再 import 其它（主题早期初始化）
- L46 `Vue.use(ElementUI)`
- L52-55 `Vue.use(SvgIcon, {tagName:'svg-icon', ...})`
- L59 `Vue.directive('waves', waves)`
- L65 `retireLegacyServiceWorkers()` 只清退根作用域旧注册与 BtDeck Workbox cache
- L69 `initSessionWatch()` 双令牌会话监听：标签页重新可见时 cookie→内存快照回同步，他标签登出则统一跳登录
- L72 初始异步路由成功后清理 chunk 恢复 query
- router.ts L7 `Vue.use(Router)`；store/index.ts L8 `Vue.use(Vuex)`
- L74-78：`new Vue({ router, store, render: (h) => h(App) }).$mount('#app')`

## router.ts 路由表（L29-262，文件共 308 行）

| 路径 | 组件 | 行号 |
|------|------|------|
| `/login` | `@/views/login/index.vue` | L31 |
| `/404` | `@/views/404.vue` | L36 |
| `/` → `/dashboard`（Layout） | `@/views/dashboard/index.vue` | L41 |
| `/downloader` | `@/views/downloader/index.vue` | L56 |
| `/torrents`（4 children，redirect → `/torrents/index`） | TorrentViewSwitcher / TraditionalView / FileManagement / index(detail) | L70 |
| `/tasks` | `@/views/tasks/index.vue` | L114 |
| `/tracker`（4 children） | keywords-board / keywords-search / reannounce-config / test | L128 |
| `/task-logs` | `@/views/task-logs/index.vue` | L173 |
| `/logs/audit` | `@/views/logs/audit.vue` | L180 |
| `/recycle-bin` | `@/views/recycle-bin/index.vue` | L199 |
| `/orphan-files` | `@/views/orphan-files/index.vue` | L213 |
| `/settings`（redirect → `/settings/index`，L231） | `@/views/settings/index.vue` | L227 |
| `/query-templates` | `@/views/query-templates/index.vue` | L244 |
| `*` | redirect `/404` | L258 |

文件末尾 L268-293 自定义 `router.push` 捕获 `NavigationDuplicated`；L297-306 的 `router.onError` 在旧 runtime 请求已下线路由 chunk 时触发一次整页版本恢复，并对重复失败显示手动刷新提示。

## permission.ts 关键（L1-162）

- L11 `whiteList = ['/login']`（仅登录页白名单）
- L14-39 强制改密拦截（安全修复 W9 + 死锁修复）：`forceChangeAllowedPaths = ['/settings/index', '/settings']`（放行白名单，含真实改密页子路径）+ `isForceChangeBlocked()` 判定 + `forceChangeRedirect()` 重定向 `/settings/index?forceChange=1` 并弹 ElementUI `Message.warning("请先修改密码…")`（3 秒节流防堆叠——拦截重定向回同一路径时设置页不重新挂载，点其它菜单的反馈只能由守卫给）
- L43 `isTransientNetworkError`（ApiError code '0' 网络层失败判定）+ L51 `abortNavigation`：`next(false)` 中止导航 + 网络波动提示 + 手动 `NProgress.done()`（中止导航 afterEach 不触发，进度条须手动收尾），保留令牌与会话现场
- L60 `router.beforeEach`：
  - L67-96 会话主动过期检查三态分流：`isTokenExpired(UserModule.token)` 为真先 `trySilentRefresh()`——renewed 继续导航；transient 网络抖动不杀会话（roles 已有放行自愈 / roles 空中止导航）；rejected `ExpireSession()` 跳登录（保留 refresh cookie，防跨标签轮换竞态）
  - L90 若 `UserModule.token` 存在：访问 `/login` 重定向；否则若 `roles.length===0` 调 `UserModule.GetUserInfo()`（L101），**成功后 L113 同样检查强制改密标志拦截**（闭合登录后/F5 后首导航放行缺口），失败 L120-130 分流——网络错误（ApiError code '0' 原样上抛）`abortNavigation`，其余 `ExpireSession()` 跳登录
  - L131-142 roles 已就绪分支：`isForceChangeBlocked()` 拦截一切非改密页导航（事故前白名单写父路径 `/settings`，落点内容区空白 + 真实路径被弹回 = 死锁）
- L144-153 无 token：白名单放行，否则跳登录带 redirect
- L156 `router.afterEach`：结束 NProgress + 设 `document.title`（默认 'BtDeck'）

> **守卫不在 router.ts**：router.ts 只导出 `router` 实例；守卫逻辑由 `permission.ts` 通过 `router.beforeEach` 注册，由 `main.ts` L37 `import '@/permission'` 触发副作用。
> **标志双通道下发**：`mustChangePassword` 由登录响应与 `/user/info`（后端 cuser.py）下发，store `GetUserInfo` 同步（字段缺失不覆盖，防滚动部署误清）。

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`router.ts` 路由表 + `permission.ts` 守卫机制）
