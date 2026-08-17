# frontend/entry — 应用入口

> Vue 应用实例化、路由表、路由守卫、根组件。`src/` 顶层 6 个文件。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/entry/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| 应用入口 main | `main.ts` | 应用入口：初始化主题、注册插件、清退历史 Workbox、双令牌会话监听（`initSessionWatch`）、挂载 #app（`new Vue(...)`） |
| 路由表 router | `router.ts` | 路由表（default export）+ `router.push` 修补 + 部署后旧 chunk 一次恢复 |
| 路由守卫 permission | `permission.ts` | 全局路由守卫：token 判断、access token 过期主动续期/登出（`isTokenExpired`+`trySilentRefresh`）、白名单、NProgress、页面标题（`router.beforeEach` / `afterEach`） |
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

## router.ts 路由表（L27-270）

| 路径 | 组件 | 行号 |
|------|------|------|
| `/login` | `@/views/login/index.vue` | L29 |
| `/404` | `@/views/404.vue` | L34 |
| `/` → `/dashboard`（Layout） | `@/views/dashboard/index.vue` | L39 |
| `/downloader` | `@/views/downloader/index.vue` | L53 |
| `/torrents`（4 children） | TorrentViewSwitcher / TraditionalView / FileManagement / index(detail) | L68 |
| `/tasks` | `@/views/tasks/index.vue` | L115 |
| `/tracker`（4 children） | keywords-board / keywords-search / reannounce-config / test | L130 |
| `/logs/audit` | `@/views/logs/audit.vue` | L185 |
| `/recycle-bin` | `@/views/recycle-bin/index.vue` | L205 |
| `/orphan-files` | `@/views/orphan-files/index.vue` | L220 |
| `/settings` | `@/views/settings/index.vue` | L235 |
| `/query-templates` | `@/views/query-templates/index.vue` | L250 |
| `*` | redirect `/404` | L265 |

文件末尾 L278-304 自定义 `router.push` 捕获 `NavigationDuplicated`；L307-317 的 `router.onError` 在旧 runtime 请求已下线路由 chunk 时触发一次整页版本恢复，并对重复失败显示手动刷新提示。

## permission.ts 关键（L1-95）

- L11 `whiteList = ['/login']`（仅登录页白名单）
- L13 `router.beforeEach`：
  - L21-33 会话主动过期检查：`isTokenExpired(UserModule.token)` 为真先 `trySilentRefresh()`，失败 `ResetToken()` 跳登录（不依赖 API 401 被动触发）
  - L35 若 `UserModule.token` 存在：访问 `/login` 重定向；否则若 `roles.length===0` 调 `UserModule.GetUserInfo()`（L53），失败 `ResetToken()` 跳登录
  - L48-50 防御性检查：token 空字符串抛错
- L70-79 无 token：白名单放行，否则跳登录带 redirect
- L89 `router.afterEach`：结束 NProgress + 设 `document.title`（默认 'BtDeck'）

> **守卫不在 router.ts**：router.ts 只导出 `router` 实例；守卫逻辑由 `permission.ts` 通过 `router.beforeEach` 注册，由 `main.ts` L37 `import '@/permission'` 触发副作用。

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`router.ts` 路由表 + `permission.ts` 守卫机制）
