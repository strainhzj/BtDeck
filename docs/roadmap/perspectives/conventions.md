# conventions — 代码约定索引

> 本文件只放约定索引表，**不复制条款全文**。所有约定的权威定义在后端/前端 `docs/constraints/` 与 `CLAUDE.md`。

## 后端约定

| 约定 | 权威文档 | 路线图内典型证据 |
|------|---------|----------------|
| API 响应格式（`CommonResponse[T]`，分页固定 `list/total/pageSize`） | [../../backend/docs/constraints/api-response-format.md](../../backend/docs/constraints/api-response-format.md) | `app/api/responseVO.py:CommonResponse`；`torrent_crud.py:814` |
| 数据库迁移（Schema 变更走 Alembic，启动自动执行） | [../../backend/docs/constraints/database-migration.md](../../backend/docs/constraints/database-migration.md) | `backend/alembic/env.py` + `app/migrations/database_migrator.py` 双轨 |
| 下载器连接（复用 `app.state.store` 缓存，禁止重复创建） | [../../backend/docs/constraints/downloader-connection.md](../../backend/docs/constraints/downloader-connection.md) | `torrent_crud.py:155` `get_snapshot()` |
| 跨环境数据库一致性 | [../../backend/docs/constraints/database-consistency.md](../../backend/docs/constraints/database-consistency.md) | — |
| 同步任务 DB 写入治理（变更检测 + 批量 upsert + 串行化） | [../../backend/docs/constraints/sync-db-write-governance.md](../../backend/docs/constraints/sync-db-write-governance.md) | `app/services/sync_db_write.py` + `app/tasks/resource_guard.py` |
| 代码复用（相似度 >50% 必须扩展） | [../../backend/docs/constraints/code-reuse.md](../../backend/docs/constraints/code-reuse.md) | ⚠ `torrent_crud.py` 单添加/批量添加违反此约定（见 [risks.md](./risks.md)） |

## 前端约定

| 约定 | 权威文档 | 路线图内典型证据 |
|------|---------|----------------|
| API 响应格式（分页固定 `list/total/pageSize`） | [../../frontend/docs/constraints/api-response-format.md](../../frontend/docs/constraints/api-response-format.md) | `utils/request.ts:19` `ApiEnvelope<T>` |
| 公共变量先行 | [../../frontend/docs/constraints/common-variables.md](../../frontend/docs/constraints/common-variables.md) | `constants/status-config.ts` `STATUS_OPTIONS` |
| Vue 异步操作 this 上下文 | [../../frontend/docs/constraints/vue-async-context.md](../../frontend/docs/constraints/vue-async-context.md) | — |
| 环境变量配置一致性 | [../../frontend/docs/constraints/environment-consistency.md](../../frontend/docs/constraints/environment-consistency.md) | `utils/request.ts:13` `process.env.VUE_APP_BASE_API` |
| 列表排序逻辑约束 | [../../frontend/docs/constraints/list-sorting.md](../../frontend/docs/constraints/list-sorting.md) | — |
| 代码复用 | [../../frontend/docs/constraints/code-reuse.md](../../frontend/docs/constraints/code-reuse.md) | — |

## 全栈约定（根 CLAUDE.md / AGENTS.md）

| 约定 | 权威文档 |
|------|---------|
| 全栈统一仓库，Git 操作在根目录 | [../../CLAUDE.md](../../CLAUDE.md) / [../../AGENTS.md](../../AGENTS.md) |
| 交互模式（开始前提假设、遇疑提问） | [../../CLAUDE.md](../../CLAUDE.md) |

---

## ⚠ 文档/代码漂移点

> 以下约定在权威文档中声明，但实际代码有出入。路线图如实记录，不照抄文档错误。

| 声明 | 实际 | 差距 |
|------|------|------|
| 前端"必须使用 Options API，禁止 Composition API 和 `<script setup>`"（`AGENTS.md` 第 5 条、`frontend/CLAUDE.md`） | 实际 src 下 **81 个**文件用 **class-component**（`@Component` + `export default class`，含 2 个 .ts mixin），仅 3 个 `.vue` 用 Options API | 详见 [risks.md](./risks.md) "文档/代码漂移" |

> class-component 属于 `vue-class-component` + `vue-property-decorator`，既不是 Composition API 也不是传统 Options API，是第三种范式。约束文档的措辞与实际代码范式不一致。
