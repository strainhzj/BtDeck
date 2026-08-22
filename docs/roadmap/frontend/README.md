# frontend 分支 — Vue 2 + TypeScript 前端

> Vue 2.6.12 + TypeScript + Element UI + Vuex + axios。本分支是 BtDeck 的 Web 前端，通过 nginx 反代后端 FastAPI。
> 定位方式：`Grep -i <功能词> docs/roadmap/frontend/README.md`，命中行即含子分支 + 职责，无需 Read 全文。

## 关键词速查

| 关键词 | 子分支 | 一句话职责 |
|--------|--------|-----------|
| 应用入口 entry | [entry/](./entry/README.md) | 应用入口（main.ts / router.ts / permission.ts / App.vue / registerServiceWorker.ts / shims-vue.d.ts，6 文件） |
| API 封装 api axios | [api/](./api/README.md) | axios 封装的 12 个领域 API 模块 |
| 页面视图 view | [views/](./views/README.md) | 13 个页面视图模块 + 404.vue（⚠ 以 class-component 为主，仅 3 处 Options API） |
| Vuex 状态 store | [store/](./store/README.md) | Vuex（index.ts 空壳 + 5 个 module，双轨注册） |
| 通用组件/布局 component layout | [components-layout/](./components-layout/README.md) | 通用组件 22 个 .vue + layout 骨架 8 个 .vue + mixin；同内容排查复用种子列表视图，不设独立弹窗 |
| 工具/类型/常量/指令 utils types | [utils-types/](./utils-types/README.md) | utils 13 + types 8 + constants 1 + directive 1 |

---

## 关键架构事实（实测）

### 1. 组件范式：class-component 为主

- **class-component**（`export default class` + `@Component`）：src 下 `.vue` 仍以该范式为主；同内容排查直接复用两种现有种子视图
- **Options API**（`export default {`，无装饰器）：全仓库仅 **3 处** .vue（技术债候选）
  - `views/recycle-bin/index.vue`（L369）
  - `views/tracker/reannounce-config.vue`（L299）
  - `components/torrents/CompactTable.vue`（L301）

> `.vue` 总数实测 88（class 85 + Options 3），class-component 占比 85/88 ≈ 96.6%。

> ⚠ 注意：根目录 `frontend/CLAUDE.md` 与 `AGENTS.md` 约束写的是"必须使用 Options API，禁止 Composition API 和 `<script setup>`"，但**实际代码库以 class-component 为主**。这是文档/代码漂移点，路线图如实记录，详见 [../perspectives/risks.md](../perspectives/risks.md)。

### 2. Vuex store 双轨注册

- `app` / `user` / `notification` / `viewMode`：走 `vuex-module-decorators`（`@Module({dynamic:true, store})` + `getModule`）
- `downloaderSettings`：走传统 `namespaced: true` Module（`export default`）

### 3. axios 封装

所有 API 模块统一 `import request from '@/utils/request'`。`request.ts` 定义：
- `ApiEnvelope<T>`（status/msg/code/data）—— 与后端 `CommonResponse` 对齐
- 请求拦截器注入 `Authorization: Bearer`
- 响应拦截器处理 blob / 成功码(200/206/207) / 业务错误 / 网络错误 / HTTP 错误
- 401 防抖重定向登录

### 4. 路由守卫分离

- 路由表在 `src/router.ts`（349 行，含部署后旧 chunk 一次恢复；`/settings` 父路由 redirect → `/settings/index`，与守卫改动原子交付）
- 守卫逻辑在独立 `src/permission.ts`（`router.beforeEach`），由 `main.ts` L37 `import '@/permission'` 触发副作用注册

---

## 调用链骨架

```
main.ts (L67 new Vue)
  ├─ import '@/permission'     # 注册路由守卫（副作用）
  ├─ router (src/router.ts)     # 路由表
  ├─ store (src/store/index.ts) # Vuex 空壳 + 动态注册
  └─ App.vue                    # 根组件 → <router-view/>
        ↓
  layout/index.vue              # 布局骨架（Sidebar + Navbar + AppMain）
        ↓
  views/*/*.vue                 # 业务页面
        ↓
  api/*.ts → utils/request.ts → axios → 后端 /api/v1/*
```

## 关键约定（仅索引，详见约束文档）

- **API 响应格式**：分页字段固定 `list/total/pageSize` → [../../frontend/docs/constraints/api-response-format.md](../../frontend/docs/constraints/api-response-format.md)
- **公共变量先行** → [../../frontend/docs/constraints/common-variables.md](../../frontend/docs/constraints/common-variables.md)
- **Vue 异步操作 this 上下文** → [../../frontend/docs/constraints/vue-async-context.md](../../frontend/docs/constraints/vue-async-context.md)
- **环境变量配置一致性** → [../../frontend/docs/constraints/environment-consistency.md](../../frontend/docs/constraints/environment-consistency.md)
- **列表排序逻辑约束** → [../../frontend/docs/constraints/list-sorting.md](../../frontend/docs/constraints/list-sorting.md)
