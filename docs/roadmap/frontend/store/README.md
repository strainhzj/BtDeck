# frontend/store — Vuex 状态管理

> Vuex 3 + TypeScript。4 个 module 统一用 `vuex-module-decorators` 动态注册（2026-09-23 删除零消费的传统 namespaced 死模块 `downloaderSettings.ts`，双轨制终结）。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/store/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| store 空壳 index | `index.ts` | 先建空 store，由各 module 动态注册（L17 注释明示） |
| 用户认证 user | `modules/user.ts` | 用户认证（Login/LogOut/GetUserInfo/ResetToken/SetToken 双令牌/SetTwoFactorFlag/SetMustChangePassword/ExpireSession 被动登出保留共享 cookie——refresh 防轮换竞态、access 防跨标签级联误杀；GetUserInfo 网络 '0' 与业务 5xx ApiError 原样上抛供守卫分流）；`@Module` 动态注册 |
| 通知抽屉 notification | `modules/notification.ts` | 通知抽屉（ToggleDrawer/FetchUnreadCount/MarkAsRead 等）；`@Module` 动态注册 |
| 应用 UI app | `modules/app.ts` | 应用 UI 状态 + 界面语言（ToggleSideBar/CloseSideBar/ToggleDevice/**SetLanguage** 委托 i18n 层持久化，双语 P1）；`@Module` 动态注册 |
| 视图模式 view-mode | `modules/viewMode.ts` | 视图模式（setViewMode/toggleFilterPanel）；`@Module` 动态注册 |

---

## index.ts 关键（L1-18）

- L8 `Vue.use(Vuex)`
- L17-18 注释：`Declare empty store first, dynamically register all modules later.`
- 导出 `IRootState` 接口（声明 `app / user / notification / viewMode` 四个子树；2026-09-23 删除零消费的传统 namespaced 死模块 `downloaderSettings.ts`，双轨制终结）

## 各 module 主要 @Action

### user.ts（L33 `@Module`）
`Login`（L110，缺 refresh_token 时清残留 cookie）、`ResetToken`（L145）、`SetToken`（L69，续期后内存+cookie 同步）、`SetTwoFactorFlag`、`SetMustChangePassword`、`GetUserInfo`、`LogOut`（L281，容忍空 token）

### notification.ts（L23 `@Module`）
`ToggleDrawer`、`FetchUnreadCount`、`FetchNotifications`、`RefreshNotifications`、`MarkAsRead`、`MarkAllAsRead`、`MarkAsUnread`、`DeleteNotification`

### app.ts（L18 `@Module`）
`ToggleSideBar`、`CloseSideBar`、`ToggleDevice`、`SetLanguage`（L64，language 状态镜像 + 委托 `i18n.setLocale`）

### viewMode.ts（L15 `@Module`）
`setViewMode`、`toggleFilterPanel`、`setFilterPanelCollapsed`

---

## 注册说明

全部 4 个模块统一走 vuex-module-decorators 动态注册：`@Module({ dynamic: true, store })` + 结尾 `export const XxxModule = getModule(Xxx)`。

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先：`user.ts` 认证流程）
