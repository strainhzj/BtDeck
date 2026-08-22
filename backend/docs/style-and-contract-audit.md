# BtDeck 前后端风格统一性与 API 契约一致性审计

审计日期：2026-06-19  
审计方式：静态扫描 `backend/app/api`、`backend/app/auth`、`frontend/src`，未运行服务，未修改业务代码。  
统计口径：后端 endpoint 按 `/api/v1` 下实际挂载路径统计；`backend/app/api/endpoints/torrents.py` 聚合进来的 `torrent_crud/status/deletion/sync/location/speed` 子路由已计入。

## 总体结论

BtDeck 当前 API 的主要问题不是单点错误，而是“历史 RPC 风格 + 新 REST 风格 + 两套认证/错误返回机制”并存。前端主体风格相对统一，77 个 Vue 组件中 74 个使用 Class Component，但 API 类型层和契约层存在明显技术债：`any` 和 `as unknown as` 使用较多，部分前端 URL 与后端实际路由不匹配，分页、字段命名、错误格式没有单一规范。

## 统计概览

### 后端 HTTP 方法分布

| 方法 | 数量 | 占比 |
|---|---:|---:|
| POST | 92 | 52.0% |
| GET | 55 | 31.1% |
| PUT | 16 | 9.0% |
| DELETE | 14 | 7.9% |
| PATCH | 0 | 0% |
| 合计 | 177 | 100% |

### 后端响应模型覆盖

| 响应模型 | endpoint 数 | 说明 |
|---|---:|---|
| `response_model=CommonResponse` | 131 | 主流模式 |
| 其他 `response_model` | 3 | 例如 `str` |
| 未声明 `response_model` | 43 | 文件流、旧接口、部分直接字典返回混在一起 |

### 前端组件风格

| 风格 | 文件数 | 占比 |
|---|---:|---:|
| Class Component | 74 | 96.1% |
| Options API | 3 | 3.9% |
| Composition API | 0 | 0% |
| `<script setup>` | 0 | 0% |

### 前端类型与调用统计

| 项 | 数量 |
|---|---:|
| `any` 出现次数 | 441 |
| 含 `any` 的 `.ts/.vue` 文件 | 66 |
| `as unknown as` 出现次数 | 100 |
| 含 `as unknown as` 的文件 | 9 |
| `request` 封装调用 | 142 |
| 直接 `axios` 调用 | 0 个业务调用，只有 `frontend/src/utils/request.ts:5` 创建实例 |
| Vuex decorator module | 3 |
| Vuex traditional module | 1 |

## 1. 后端 API 风格评估

### REST 规范性问题

| 严重程度 | 类型 | 数量/范围 | 代表位置 |
|---|---|---:|---|
| 🔴 严重 | 资源路径动词化，CRUD 动作用路径表达 | 约 40+ | `backend/app/api/endpoints/downloader.py:80`、`backend/app/api/endpoints/torrent_deletion.py:145` |
| 🔴 严重 | 同一资源存在多套入口或重复挂载 | 多处 | `backend/app/api/api.py:27`、`backend/app/api/api.py:28`、`backend/app/api/api.py:29`、`backend/app/api/api.py:66` |
| 🟡 中等 | 路径命名混用 camelCase、kebab-case、单数/复数 | 约 20+ | `backend/app/api/api.py:32`、`backend/app/api/endpoints/cuser.py:109`、`backend/app/api/endpoints/downloader.py:483` |
| 🟡 中等 | 动作型 POST 用于状态迁移/任务命令 | 约 30+ | `backend/app/api/endpoints/cron_tasks.py:698`、`backend/app/api/endpoints/torrent_status.py:64` |
| 🟢 轻微 | 文件下载/导出 endpoint 不完全 REST，但可接受 | 多处 | `backend/app/api/endpoints/audit_logs.py:382`、`backend/app/api/endpoints/torrent_backup.py:896` |

#### 🔴 RPC 风格下载器接口集中存在

- 位置：`backend/app/api/endpoints/downloader.py:80` `POST /downloader/add`
- 位置：`backend/app/api/endpoints/downloader.py:161` `POST /downloader/update/{downloader_id}`
- 位置：`backend/app/api/endpoints/downloader.py:346` `DELETE /downloader/delete/{downloader_id}`
- 位置：`backend/app/api/endpoints/downloader.py:483` `GET /downloader/getStatusAll`
- 位置：`backend/app/api/endpoints/downloader.py:1166` `GET /downloader/getList`
- 位置：`backend/app/api/endpoints/downloader.py:1252` `POST /downloader/getList`
- 影响范围：前端 `frontend/src/api/downloader.ts:3`、`:16`、`:26`、`:32`、`:39`、`:46` 已绑定这些路径，迁移会影响下载器列表、编辑、状态刷新。
- 修复建议：新增 REST v2 别名并逐步迁移，例如 `GET /downloaders`、`POST /downloaders`、`PUT /downloaders/{id}`、`DELETE /downloaders/{id}`、`GET /downloaders/{id}/status`；旧路径保留 deprecation 响应头或文档标记。

#### 🔴 种子删除路径动词滥用

- 位置：`backend/app/api/endpoints/torrent_deletion.py:145` `DELETE /torrents/delete`
- 位置：`backend/app/api/endpoints/torrent_deletion.py:384` `POST /torrents/delete/preview`
- 位置：`backend/app/api/endpoints/torrent_deletion.py:476` `POST /torrents/delete/bulk`
- 位置：`backend/app/api/endpoints/torrent_deletion.py:735` `DELETE /torrents/delete-with-level`
- 位置：`backend/app/api/endpoints/torrent_deletion.py:917` `POST /torrents/delete-batch-async`
- 影响范围：前端 `frontend/src/api/torrents.ts:314`、`:332`、`:367`、`:399` 和 `frontend/src/views/torrents/index.vue` 的批量删除流程。
- 修复建议：用资源化批处理建模：`POST /torrent-deletion-previews`、`POST /torrent-deletion-jobs`、`GET /torrent-deletion-jobs/{id}`；单个删除使用 `DELETE /torrents/{id}`。

#### 🔴 Tracker 操作是典型 RPC

- 位置：`backend/app/api/endpoints/tracker.py:31` `POST /tracker/addTracker`
- 位置：`backend/app/api/endpoints/tracker.py:155` `POST /tracker/replaceTracker`
- 位置：`backend/app/api/endpoints/tracker.py:306` `POST /tracker/modifyTracker`
- 影响范围：前端 `frontend/src/api/torrents.ts:504`、`:521`、`:538`。
- 修复建议：统一为 `POST /torrents/{id}/trackers`、`PUT /torrents/{id}/trackers/{tracker_id}`，批量替换可作为 `POST /tracker-replacement-jobs`。

#### 🔴 同一能力出现双路由入口

- 位置：`backend/app/api/api.py:29` 聚合 `/torrents`
- 位置：`backend/app/api/api.py:66` 额外挂载 `/torrent-status`
- 位置：`backend/app/api/endpoints/torrent_status.py:64` 同一函数可形成 `/torrents/pause` 和 `/torrent-status/pause`
- 影响范围：前端同时存在旧风格 `/torrents/pause`、`/torrents/resume` 和新风格 `/torrent-status/reannounce`，见 `frontend/src/api/torrents.ts:415`、`:432`、`:1106`。
- 修复建议：选定一个 canonical 路径，建议状态操作先保留 `/torrents/{id}/status` 或 `/torrent-operations`，另一套做兼容层并写入弃用计划。

#### 🟡 路径命名大小写和分隔符不统一

- 位置：`backend/app/api/api.py:32` `prefix="/cronTasks"` 使用 camelCase。
- 位置：`backend/app/api/endpoints/cuser.py:109` `/changePassword`。
- 位置：`backend/app/api/endpoints/cuser.py:170` `/2faVerifyQrCode/{user_id}`。
- 位置：`backend/app/api/endpoints/cuser.py:231` `/update2faFlg/{user_id}`。
- 影响范围：前端 `frontend/src/api/tasks.ts:206`、`frontend/src/api/users.ts:12`、`frontend/src/views/settings/index.vue:508`。
- 修复建议：统一使用 kebab-case 资源路径，例如 `/cron-tasks`、`/users/{id}/password`、`/users/{id}/two-factor/qr-code`。

## 2. HTTP 状态码使用评估

### 认证失败响应不一致

| 模式 | 位置 | 说明 |
|---|---|---|
| HTTP 200 + `CommonResponse(code="401")` | `backend/app/api/endpoints/login.py:45`、`backend/app/api/endpoints/downloader.py:37`、`backend/app/api/endpoints/tracker_test.py:39` | 主流旧模式，前端拦截器依赖 `res.code === '401'` |
| HTTP 401 + `HTTPException` | `backend/app/auth/dependencies.py:84`、`backend/app/api/endpoints/cron_tasks.py:239`、`backend/app/api/endpoints/seed_transfer.py:53`、`backend/app/api/endpoints/torrent_backup.py:93` | 新依赖或局部 helper 使用 HTTP 层状态 |

- 严重程度：🔴 严重
- 影响范围：前端 `frontend/src/utils/request.ts:76` 同时处理业务 `code=401`，`frontend/src/utils/request.ts:101` 又处理 HTTP 401；不同 endpoint 会走不同错误分支，业务代码收到的 error shape 不一致。
- 修复建议：认证失败统一为 HTTP 401，body 使用同一错误结构；短期在 `request.ts` 把 HTTP 401 的 `detail` 中 `CommonResponse` 格式解包为统一错误对象。

### 业务错误大量使用 HTTP 200 + 业务 code

- 位置：`backend/app/api/endpoints/cron_tasks.py:572` 用 `CommonResponse(code="404")` 表达不存在。
- 位置：`backend/app/api/endpoints/downloader_settings.py:390`、`:418`、`:944` 用 `CommonResponse(code="422")` 表达校验失败。
- 位置：`backend/app/api/endpoints/notifications.py:90` 用 `CommonResponse(code="404")` 表达通知不存在。
- 严重程度：🟡 中等
- 影响范围：前端必须读取 `res.code` 判断业务结果，无法利用 HTTP 客户端、网关、监控对 4xx/5xx 的标准语义。
- 修复建议：新接口使用 HTTP 4xx/5xx；兼容期内 `CommonResponse.code` 与 HTTP status 保持同值，不再出现 HTTP 200 + `code=500`。

### 直接 HTTP 500 与包装 `code=500` 并存

- 直接 HTTP 500：`backend/app/api/endpoints/tracker_keywords.py:164`、`:227`、`:374`；`backend/app/api/endpoints/audit_logs.py:412`；`backend/app/api/endpoints/torrent_backup.py:740`、`:964`。
- 包装 `code=500`：`backend/app/api/endpoints/cron_tasks.py:407`、`:454`、`:590`；`backend/app/api/endpoints/dashboard.py:38`；`backend/app/api/endpoints/downloader.py:562`。
- 严重程度：🔴 严重
- 影响范围：前端 `request.ts` 对 HTTP 500 直接 `Promise.reject(error)`，对 `code=500` 则 `new Error(res.msg)`；调用方无法稳定读取 `error.response.data.msg`。
- 修复建议：统一异常处理器，把未捕获异常转换为统一 `ErrorResponse`；业务代码只抛领域异常，不在每个 endpoint 手写 `except Exception -> CommonResponse(code=500)`。

## 3. 响应格式评估

### `CommonResponse` 覆盖率不足且存在非标准返回

- 统计：177 个 endpoint 中 131 个声明 `CommonResponse`，43 个未声明，3 个声明其他模型。
- 位置：`backend/app/api/endpoints/cuser.py:170` 返回二维码文件流，无 `CommonResponse`。
- 位置：`backend/app/api/endpoints/cuser.py:209` `response_model=str`。
- 位置：`backend/app/api/endpoints/tag_management.py:1090`、`:1132`、`:1447` 直接返回 `{"success": ..., "message": ...}`。
- 位置：`backend/app/api/endpoints/torrent_speed.py:335` 未声明响应模型。
- 严重程度：🟡 中等
- 影响范围：前端 `request.ts:62` 默认所有非 blob 响应都有 `code`；直接字典响应会进入错误分支。
- 修复建议：普通 JSON endpoint 必须返回统一 envelope；文件流/二维码/download endpoint 明确 `response_class` 并在前端调用设置 `responseType`。

### 分页字段不统一

- 位置：`frontend/src/types/api.ts:23` 统一类型定义为 `list/total/page/size`。
- 位置：`frontend/src/types/torrent.ts:158` 又定义 `total/page/pageSize/list`。
- 位置：`backend/app/api/endpoints/tracker_messages.py:78` 返回 `total/page/pageSize/list`。
- 位置：`backend/app/api/endpoints/tag_management.py:392` 返回 `total/page/pageSize/list`。
- 位置：`frontend/src/store/modules/downloaderSettings.ts:221` 请求参数使用 `pageSize`。
- 位置：`backend/app/api/endpoints/tracker_messages.py:36` 请求参数使用 `page_size`。
- 严重程度：🟡 中等
- 影响范围：分页组件、列表页、搜索页各自做适配，容易出现某接口翻页正常、另一接口页大小失效。
- 修复建议：请求统一 `page` + `limit`，响应统一 `list` + `total` + `page` + `limit`；兼容期后端同时接受 `pageSize/page_size/limit`，但只输出一种。

## 4. 前端代码风格评估

### Vue 组件风格基本统一，但有 3 个 Options API 例外

- 位置：`frontend/src/components/torrents/CompactTable.vue:299`。
- 位置：`frontend/src/views/recycle-bin/index.vue`。
- 位置：`frontend/src/views/tracker/reannounce-config.vue`。
- 严重程度：🟢 轻微
- 影响范围：局部维护成本；Class Component 项目中 Options API 的类型推断和装饰器写法不同。
- 修复建议：新代码继续禁止 `<script setup>`；上述 3 个文件若未来大改，可顺手迁回 Class Component 或明确允许 Options API 作为例外。

### `any` 使用过多

- 统计：`any` 441 次，分布在 66 个文件。
- 高风险位置：`frontend/src/views/torrents/index.vue` 46 次、`frontend/src/api/torrents.ts` 31 次、`frontend/src/api/tasks.ts` 25 次、`frontend/src/api/tracker.ts` 21 次、`frontend/src/components/torrents/CompactTable.vue` 21 次。
- 严重程度：🟡 中等
- 影响范围：API 契约漂移时 TypeScript 无法提前发现，尤其是 `response.data.list`、`taskData.total_count` 这类深层字段。
- 修复建议：先治理 `frontend/src/api/*.ts` 返回类型，禁止 API 层新增 `Promise<ApiResponse<any>>`；组件内部事件/ElementUI ref 可保留有限 `any`。

### `as unknown as` 类型断言滥用

- 统计：100 次，集中在 `frontend/src/api/torrents.ts` 36 次、`frontend/src/api/tracker.ts` 26 次、`frontend/src/api/tasks.ts` 18 次。
- 位置示例：`frontend/src/api/torrents.ts:200`、`:210`、`:257`。
- 严重程度：🟡 中等
- 影响范围：API 封装强制把 axios 返回值伪装成目标类型，掩盖响应 envelope、分页字段和错误结构不一致。
- 修复建议：给 `request` 封装加泛型 `request<T>() => Promise<ApiResponse<T>>`，API 文件不再使用双重断言。

### API 调用方式整体统一

- 位置：`frontend/src/utils/request.ts:5` 唯一 `axios.create`。
- 统计：业务层直接 axios 调用为 0，`request` 调用 142。
- 严重程度：🟢 轻微
- 影响范围：这部分是优势；token 和错误处理集中在拦截器。
- 修复建议：保持规则；为 blob/download 类型封装专用 helper，避免普通 JSON 拦截器误判。

### Vuex module 风格混用

- 位置：`frontend/src/store/modules/app.ts:18` decorator。
- 位置：`frontend/src/store/modules/user.ts:22` decorator。
- 位置：`frontend/src/store/modules/notification.ts:24` decorator。
- 位置：`frontend/src/store/modules/downloaderSettings.ts:43` traditional module。
- 严重程度：🟡 中等
- 影响范围：调用方式和类型推导不同，`downloaderSettings` 的 action/mutation 更依赖字符串常量。
- 修复建议：如果项目继续 Vue 2 + decorator，新增 store module 优先使用 decorator；或者明确 traditional module 只用于复杂字典状态。

### 组件直接改写模块状态

- 位置：`frontend/src/views/settings/index.vue:610` `(UserModule as any).twoFactorFlag = '0'`。
- 严重程度：🔴 严重
- 影响范围：绕过 mutation，破坏 Vuex 单向数据流；刷新后状态来源也不清晰。
- 修复建议：在 `user.ts` 增加 mutation/action 管理 2FA 状态，组件只 dispatch action。

## 5. 前后端 API 契约评估

### 前端调用了后端不存在或路径不一致的 endpoint

| 严重程度 | 前端位置 | 后端实际情况 | 影响范围 | 修复建议 |
|---|---|---|---|---|
| 🔴 严重 | `frontend/src/api/torrents.ts:208` `/torrents/detail/{hash}` | 后端实际为 `backend/app/api/endpoints/torrent_crud.py:757` `/torrents/torrents/{info_id}/{downloader_id}/{downloader_name}` | 种子详情接口可能 404 | 后端补 `GET /torrents/{hash}` 或前端按实际参数调用；优先修正为资源详情 |
| 🔴 严重 | `frontend/src/api/downloader.ts:196` `/setting-templates/{id}/apply` | 后端 `backend/app/api/endpoints/setting_templates.py:417` 是 `/setting-templates/{template_id}/apply/{downloader_id}` | 模板应用失败 | 前后端统一 downloader_id 放 path 还是 body |
| 🔴 严重 | `frontend/src/api/tag-management.ts:127` `/tags/batch-delete` | 后端未发现对应 endpoint | 批量删除标签失败 | 后端新增或前端移除入口 |
| 🔴 严重 | `frontend/src/api/tasks.ts:300` `/cronTasks/logs/delete` | 后端未发现对应 endpoint | 删除日志功能失败 | 后端补日志删除 API 或隐藏按钮 |
| 🔴 严重 | `frontend/src/api/tasks.ts:313` `/cronTasks/logs/export` | 后端未发现对应 endpoint | 日志导出失败 | 与 `audit-logs/export` 模式统一 |
| 🔴 严重 | `frontend/src/api/users.ts:26` `/users/logout` | 后端未发现对应 endpoint | 登出请求失败，但本地 token 可能已清 | 前端只本地登出，或后端补 revoke endpoint |

### 补充遗漏的前后端路径不匹配

| 严重程度 | 前端调用 | 后端实际情况 | 影响范围 | 修复建议 |
|---|---|---|---|---|
| 🔴 严重 | `GET /setting-templates/{template_id}` | 后端支持列表、创建、更新、删除、应用模板，但没有模板详情 `GET /{template_id}` | 模板详情或编辑前回填可能 404/405 | 后端补详情接口，或前端改为从列表缓存/列表查询中读取 |
| 🔴 严重 | `GET /tracker-messages/statistics` | 后端未发现 statistics endpoint | Tracker 消息统计入口不可用 | 后端补统计接口，或前端隐藏统计入口 |
| 🔴 严重 | `POST /cronTasks/logs/cleanup` | 后端只有 `/cronTasks/cleanup/preview` 和 `/cronTasks/cleanup/execute`，没有日志 cleanup endpoint | 定时任务日志清理失败 | 统一日志清理资源路径，或前端改用后端已有 cleanup 流程 |
| 🟡 中等 | `GET /articles` | 后端未挂载 articles 路由 | 模板遗留 API 可能误导后续开发 | 若为模板遗留，删除 `frontend/src/api/articles.ts`；若仍需文章功能，补后端路由 |

补充风险：`GET /tracker-messages/statistics` 如果位于动态详情路由 `/{log_id}` 之后或未做类型约束，可能被详情接口按 `log_id=statistics` 误接收，导致返回 422、404 或错误语义数据。该类静态路径应显式注册在动态路由前，并用类型约束避免误匹配。

`GET /setting-templates/{template_id}` 也存在相近风险：虽然当前后端没有该 GET 方法，但同一路径上已有 `PUT /{template_id}`、`DELETE /{template_id}`。如果同一 router 或聚合路由中存在更宽泛的动态路由，例如 `/{log_id}` 或其他非资源化 catch-all，模板详情调用可能被动态路由误接收，应避免在同一挂载前缀下引入含义不清的动态段。

### 参数与类型契约风险

| 严重程度 | 风险项 | 具体表现 | 影响范围 | 修复建议 |
|---|---|---|---|---|
| 🔴 严重 | `setting-templates apply` body/path 参数双重不匹配 | 前端调用 `/setting-templates/{id}/apply`，并把 `downloader_id` 放在 body；后端实际要求 `/setting-templates/{template_id}/apply/{downloader_id}`，body 只读取 `apply_path_mapping` | 模板应用请求无法命中正确路由，命中后也可能丢失必要字段 | 统一为 `POST /setting-templates/{template_id}/applications`，body 包含 `downloader_id/apply_path_mapping/override_local`；兼容期保留旧路径 |
| 🟡 中等 | `pageSize` vs `page_size` 参数名不匹配 | 前端部分查询参数使用 `pageSize`，后端 tracker 消息等接口 `Query` 参数使用 `page_size` | 页大小参数可能被忽略，列表页表现不一致 | 后端兼容接受 `pageSize/page_size/limit`，前端 API 层统一输出一种参数 |
| 🟡 中等 | 模板应用请求 body 字段不匹配 | 前端 `ApplyTemplateRequest` 包含 `template_id/downloader_id/override_local`，后端实际只从 body 读取 `apply_path_mapping` | 前端类型给出虚假的契约安全感，运行时字段被忽略 | 补 Pydantic request model，并用 OpenAPI schema 生成前端类型 |
| 🟡 中等 | 下载器类型 `string`/`int` 混用 | 后端下载器类型多处使用 `int`/`IntEnum`，前端部分类型使用 `string`、名称字段或数字型混合 | 筛选、编辑、枚举映射可能出现隐式转换问题 | 统一枚举值类型，建议 API 层使用稳定数字枚举或字符串枚举之一，并集中转换展示文案 |
| 🟢 轻微 | 日期时间格式未统一 | 后端存在 `datetime`、`isoformat()`、数据库字符串混用；前端大多只声明为 `string` | 审计日志、标签、删除记录排序和跨时区显示不稳定 | 统一为 ISO 8601 UTC 字符串，OpenAPI 标注 `format: date-time`，前端集中格式化 |

### 后端未使用 endpoint

静态扫描显示约 54 个已挂载后端 endpoint 没有在 `frontend/src` 中找到对应调用。它们不应全部直接判定为死代码，因为其中可能包括预留接口、后台任务辅助接口、下载文件接口、兼容旧入口或尚未接入 UI 的功能。但未使用 endpoint 会增加契约维护成本，也容易在重构时被误认为仍有前端依赖。

建议分三类处理：

| 分类 | 判定标准 | 处理方式 |
|---|---|---|
| 死代码 | 没有前端调用、没有测试覆盖、没有后台任务/外部调用证据 | 删除或迁移到内部模块 |
| 预留接口 | 产品规划明确但 UI 未接入 | 标注 owner、预期接入版本和契约状态 |
| 未接入 UI | 后端能力已完成但前端入口缺失 | 建立产品待办，或在文档中声明仅供外部/脚本调用 |

高风险未使用接口示例：

- `/tasks/logs`、`/tasks/statistics`：前端使用的是 `/cronTasks/logs` 和 `/cronTasks/logs/statistics`，存在双命名体系。
- `/torrent-status/pause`、`/torrent-status/resume`、`/torrent-status/recheck`：前端仍使用 `/torrents/pause`、`/torrents/resume`、`/torrents/recheck`。
- `/torrents/list`：前端使用 `/torrents/getList`。
- `/advanced-search/search-statistics`、`/advanced-search/torrents/batch-delete`：未发现前端调用。
- `/audit-logs/query`、`/audit-logs/statistics`、`/audit-logs/archive`、`/audit-logs/export`、`/audit-logs/download-export/{file_name}`：未发现当前扫描范围内调用。
- `/tags/all`、`/tags/categories`、`/tags/tags`、`/tags/torrent/{hash}/tags`、`/tags/torrent/assign`、`/tags/torrent/batch-assign`、`/tags/torrent/remove`：未发现前端调用。
- `/downloaders/{id}/paths/statistics`、`/downloaders/{id}/capabilities/reset`、`/downloaders/{id}/capabilities/sync`、`/downloaders/{id}/capabilities/delete`、`/downloaders/{id}/capabilities/put`：未发现前端调用。

### 字段命名 snake_case 与 camelCase 并存

- 位置：`backend/app/models/response/dashboard.py:59` 后端 dashboard 输出 `downloader_list`。
- 位置：`frontend/src/types/dashboard.ts:47` 前端也接受 `downloader_list`，说明该接口遵循 snake_case。
- 位置：`backend/app/api/endpoints/downloader_settings.py:395` 后端入参兼容 `dlSpeedLimit` 和 `download_speed_limit`。
- 位置：`frontend/src/views/downloader/components/SpeedSettingsTab.vue:278` 前端同时读 `enableSchedule` 和 `enable_schedule`。
- 位置：`backend/app/api/endpoints/downloader_settings.py:310` 响应又输出 `dl_speed_limit/ul_speed_limit`。
- 严重程度：🟡 中等
- 影响范围：下载器设置、速度规则、仪表盘、种子列表均可能出现双字段兼容逻辑。
- 修复建议：后端 API 层统一输出 camelCase 或 snake_case 二选一；如果保留 Python 风格 snake_case，前端类型也全部 snake_case，不再在组件里双读。

### 日期时间格式没有统一声明

- 位置：`backend/app/models/torrent_tags.py:113` 使用 `created_at.isoformat()`。
- 位置：`backend/app/models/torrent_deletion_audit_log.py:276` 使用 `created_at.isoformat()`。
- 位置：`frontend/src/types/torrent.ts:403` 仅声明 `create_time?: string`，未约束 ISO、时区或本地格式。
- 严重程度：🟢 轻微
- 影响范围：审计日志、标签、删除记录显示和排序。
- 修复建议：统一为 ISO 8601 UTC 字符串；OpenAPI schema 标注 `format: date-time`，前端集中格式化。

### 错误处理契约不稳定

- 位置：`frontend/src/utils/request.ts:62` 假设成功响应 `res.code === '200'`。
- 位置：`frontend/src/utils/request.ts:76` 处理业务 `code=401`。
- 位置：`frontend/src/utils/request.ts:101` 处理 HTTP 401。
- 位置：`backend/app/auth/dependencies.py:84` HTTPException detail 是 `CommonResponse.model_dump()`。
- 位置：`backend/app/api/endpoints/torrent_backup.py:917` HTTPException detail 是纯字符串。
- 严重程度：🔴 严重
- 影响范围：错误提示、登录跳转、调用方 catch 分支读取 `msg/detail/message` 的方式不一致。
- 修复建议：定义统一错误体：`{ code, message, details?, traceId? }`；前端拦截器归一化为 `ApiError`，业务代码不直接依赖 axios 原始 error。

### 认证契约存在双 header

- 位置：`frontend/src/utils/request.ts:41` 发送 `x-access-token`。
- 位置：`frontend/src/utils/request.ts:42` 同时发送 `Authorization: Bearer ...`。
- 位置：`backend/app/auth/dependencies.py:29` 后端优先读 `x-access-token`，再读 `Authorization`。
- 位置：`frontend/src/utils/cookies.ts:7` token 存 cookie key `vue_typescript_admin_access_token`。
- 严重程度：🟡 中等
- 影响范围：安全审计、代理日志、跨域配置；双 header 让真正契约不清晰。
- 修复建议：统一为 `Authorization: Bearer <token>`；兼容期保留读取 `x-access-token`，但前端只发送一种。

## 6. 统一方案与优先级

### P0：先冻结契约基线

1. 生成并提交 OpenAPI schema，但不要立即假设它能完整生成前端业务类型。当前大量 `response_model=CommonResponse` 没有携带业务 `data` 泛型，且仍有直接 dict 返回；应先补高频接口的 Pydantic request/response model，再从 schema 生成前端 API 类型。
2. 约定 envelope：成功 `{ code: "200", msg, data, status: "success" }` 是否继续保留；若保留，长期目标是 HTTP status 与 `code` 同步。短期应先在前端 `request.ts` 做错误归一化，把 HTTP 4xx/5xx、旧 `code=401/500` 和 `HTTPException.detail` 统一成 `ApiError`，再逐步调整后端 status。
3. 统一认证失败为 HTTP 401，但需先统一 `ApiError` 结构。登录接口当前依赖 HTTP 200 + `code=401` 表达“用户名或密码错误”，如果直接改 HTTP 401，会改变登录页错误分支和提示逻辑。

### P1：修复已知前后端不匹配

1. 处理 `/torrents/detail/{hash}`、`/setting-templates/{id}/apply`、`/tags/batch-delete`、`/cronTasks/logs/delete`、`/cronTasks/logs/export`、`/users/logout`，并补充处理 `/setting-templates/{template_id}`、`/tracker-messages/statistics`、`/cronTasks/logs/cleanup`、`/articles`。
2. 为下载/导出/blob 接口建立专用前端调用封装，避免被 JSON envelope 拦截器误处理。
3. 统一分页参数和响应字段，推荐 `page` + `limit`，响应 `list/total/page/limit`。
4. 建立一份机器生成的 API 对照表，记录后端 method/path/response_model 与前端 method/path/source line，在 CI 中检查新增 404/405、误路由和未使用 endpoint。

### P2：REST 路由渐进迁移

1. 新增 REST canonical 路由，不立即删除旧 RPC 路由。
2. 为旧路由标记 deprecated，并制定兼容期策略：至少保留一个小版本过渡期，可使用 FastAPI `deprecated=True`、`Deprecation`/`Sunset` 响应头和迁移文档提示；前端 API 层集中替换后再删除旧入口。
3. 优先迁移下载器、种子删除、tracker 操作、cronTasks 命名。

### P3：前端类型收敛

1. 改造 `request` 为泛型，移除 API 文件中的 `as unknown as`。
2. API 层禁止新增 `any` 返回类型。
3. 把 `frontend/src/views/settings/index.vue:610` 改为 Vuex mutation/action。
4. 分页字段渐进统一：后端兼容接受 `pageSize/page_size/limit`，前端 API 层先转换为单一内部字段，响应短期可保留旧字段或由适配层转换，长期只输出 `list/total/page/limit`。

## 建议目标规范

### 路径规范

- 资源名统一复数 kebab-case：`/downloaders`、`/cron-tasks`、`/tracker-keywords`。
- CRUD 不在路径中写动词。
- 批处理或长任务使用 job 资源：`POST /torrent-deletion-jobs`、`GET /torrent-deletion-jobs/{id}`。
- 状态迁移可使用子资源：`PUT /notifications/{id}/read-state`，或明确 action 资源 `POST /torrent-operations`。

### 响应规范

```json
{
  "code": "200",
  "msg": "ok",
  "status": "success",
  "data": {}
}
```

错误响应建议：

```json
{
  "code": "401",
  "msg": "Unauthorized",
  "status": "error",
  "data": null
}
```

约束：HTTP status 与 `code` 保持一致；文件流接口例外，但必须在 API 文档和前端 helper 中显式声明。

### 命名规范

- API JSON 字段二选一：全 snake_case 或全 camelCase。
- 若保持 Python/FastAPI 习惯，建议全 snake_case；前端类型同步 snake_case，组件层不再双读 `enableSchedule ?? enable_schedule`。
- 分页统一：请求 `page/limit`，响应 `list/total/page/limit`。
