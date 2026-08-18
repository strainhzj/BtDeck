# frontend/store — Vuex 状态管理

> Vuex 3 + TypeScript。⚠ **双轨注册**：4 个 module 用 `vuex-module-decorators` 动态注册，1 个用传统 namespaced Module。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/store/README.md`，命中行即含文件 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 文件 | 一句话职责 |
|--------|------|-----------|
| store 空壳 index | `index.ts` | 先建空 store，由各 module 动态注册（L17 注释明示） |
| 用户认证 user | `modules/user.ts` | 用户认证（Login/LogOut/GetUserInfo/ResetToken/SetToken 双令牌/SetTwoFactorFlag/SetMustChangePassword/ExpireSession 被动登出保留 refresh cookie；GetUserInfo 网络错误 ApiError 原样上抛供守卫分流）；`@Module` 动态注册 |
| 下载器设置 downloader-settings | `modules/downloaderSettings.ts` | ⚠ 传统 `namespaced: true` Module（`export default`）：下载器设置/能力/模板 CRUD（fetchSettings/updateSettings/fetchTemplates/applyTemplate 等） |
| 通知抽屉 notification | `modules/notification.ts` | 通知抽屉（ToggleDrawer/FetchUnreadCount/MarkAsRead 等）；`@Module` 动态注册 |
| 应用 UI app | `modules/app.ts` | 应用 UI 状态（ToggleSideBar/CloseSideBar/ToggleDevice）；`@Module` 动态注册 |
| 视图模式 view-mode | `modules/viewMode.ts` | 视图模式（setViewMode/toggleFilterPanel）；`@Module` 动态注册 |

---

## index.ts 关键（L1-18）

- L8 `Vue.use(Vuex)`
- L17-18 注释：`Declare empty store first, dynamically register all modules later.`
- 导出 `IRootState` 接口（声明 `app / user / notification / viewMode` 四个子树，⚠ 不含 `downloaderSettings`）

## 各 module 主要 @Action

### user.ts（L33 `@Module`）
`Login`（L111，缺 refresh_token 时清残留 cookie）、`ResetToken`（L146）、`SetToken`（L69，续期后内存+cookie 同步）、`SetTwoFactorFlag`、`SetMustChangePassword`、`GetUserInfo`、`LogOut`（L239，容忍空 token）

### notification.ts（L23 `@Module`）
`ToggleDrawer`、`FetchUnreadCount`、`FetchNotifications`、`RefreshNotifications`、`MarkAsRead`、`MarkAllAsRead`、`MarkAsUnread`、`DeleteNotification`

### app.ts（L18 `@Module`）
`ToggleSideBar`、`CloseSideBar`、`ToggleDevice`

### viewMode.ts（L15 `@Module`）
`setViewMode`、`toggleFilterPanel`、`setFilterPanelCollapsed`

### downloaderSettings.ts（⚠ 传统 Module，L42）
actions（无装饰器，L119+）：`fetchSettings`、`updateSettings`、`fetchCapabilities`、`testSettings`、`fetchTemplates`、`fetchTemplateDetail`、`createTemplate`、`updateTemplate`、`deleteTemplate`、`applyTemplate`
getters（L344+）：`getSettingsById`、`getCapabilitiesById`、`getTemplatesByType`、`getSystemTemplates`、`getUserTemplates`、`isLoading`、`getError`

---

## 双轨注册说明

| 模式 | 文件 | 注册机制 |
|------|------|---------|
| 装饰器动态注册 | app / user / notification / viewMode | `@Module({ dynamic: true, store })` + 结尾 `export const XxxModule = getModule(Xxx)` |
| 传统 namespaced | downloaderSettings | `export default downloaderSettingsModule`（state/mutations/actions/getters 对象），由调用方注册 |

> `downloaderSettings` 不在 `IRootState` 类型声明中，且注册路径与其他 4 个不同——这是双轨制的副作用，组件中使用时需注意类型与访问方式差异。

## 第三层详情

- 本分支第三层待后续会话按模式 B 补齐（建议优先级：`user.ts` 认证流程、`downloaderSettings.ts` 双轨制样本）
