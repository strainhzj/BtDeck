# frontend/entry — 应用入口

> Vue 应用实例化、路由表、路由守卫、根组件。`src/` 顶层 6 个文件。

## 文件清单

| 文件 | 行数 | 顶层符号 | 一句话职责 |
|------|------|---------|-----------|
| `main.ts` | 71 | `new Vue(...)` | 应用入口：初始化主题、注册插件、清退历史 Workbox、挂载 #app |
| `router.ts` | 318 | `router` (default export) | 路由表 + `router.push` 修补 + 部署后旧 chunk 一次恢复 |
| `permission.ts` | 70 | `router.beforeEach` / `router.afterEach` | 全局路由守卫：token 判断、白名单、NProgress、页面标题 |
| `App.vue` | 31 | `App` 组件（class-component） | 根组件，仅 `<div id="app"><router-view /></div>` |
| `registerServiceWorker.ts` | 32 | 条件 `register` | 历史 PWA 注册助手；当前 `main.ts` 不导入，启动逻辑会清退旧注册 |
| `shims-vue.d.ts` | 4 | `declare module '*.vue'` | 为 .vue 文件提供 TS 模块声明 |

---

## main.ts 关键（L1-71）

- L28-31：先 `initTheme()` 再 import 其它（主题早期初始化）
- L45 `Vue.use(ElementUI)`
- L49-53 `Vue.use(SvgIcon, {tagName:'svg-icon', ...})`
- L56 `Vue.directive('waves', waves)`
- L62 `retireLegacyServiceWorkers()` 只清退根作用域旧注册与 BtDeck Workbox cache
- L65 初始异步路由成功后清理 chunk 恢复 query
- router.ts L7 `Vue.use(Router)`；store/index.ts L8 `Vue.use(Vuex)`
- L67-71：`new Vue({ router, store, render: (h) => h(App) }).$mount('#app')`

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

## permission.ts 关键（L1-70）

- L9 `whiteList = ['/login']`（仅登录页白名单）
- L11 `router.beforeEach`：
  - L16 若 `UserModule.token` 存在：访问 `/login` 重定向；否则若 `roles.length===0` 调 `UserModule.GetUserInfo()`（L36），失败 `ResetToken()` 跳登录
  - L31-33 防御性检查：token 空字符串抛错
- L51-60 无 token：白名单放行，否则跳登录带 redirect
- L64 `router.afterEach`：结束 NProgress + 设 `document.title`（默认 'BtDeck'）

> **守卫不在 router.ts**：router.ts 只导出 `router` 实例；守卫逻辑由 `permission.ts` 通过 `router.beforeEach` 注册，由 `main.ts` L37 `import '@/permission'` 触发副作用。

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`router.ts` 路由表 + `permission.ts` 守卫机制）
