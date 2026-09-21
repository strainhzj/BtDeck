# MCP 服务与可选能力开放实施计划

> **Feature ID**: `mcp-service-capabilities-2026-08-28`
> **状态**: 已规划，经 2026-09-05 基线复核修订（§10），W0 待启动
> **规划日期**: 2026-08-28（2026-09-05 复核）
> **范围**: 后端同进程 MCP 服务、实例级开关、逐能力开放、统一鉴权、敏感数据脱敏、设置 UI、测试与交付制品
> **原则**: 默认拒绝；服务关闭或能力未启用时不可发现、不可调用；任何门禁失败或证据缺失均不得开放

---

## 1. 目标

在不复制 HTTP endpoint 业务逻辑的前提下，为 BtDeck 增加与 FastAPI 同进程、共享
`app.state.store`、数据库会话工厂和定时任务执行器的 MCP 服务。首批预置以下 6 项能力：

1. 种子高级查询。
2. 等级 4 操作（语义为给下载器和数据库种子添加 `pending_delete` 标签，不删除任务或文件）。
3. 添加 `.torrent` 种子文件。
4. 创建高级查询组合/查询模板。
5. 获取仪表盘数据。
6. 立即触发现有定时任务。

同时提供实例级全局开关和逐能力开关。管理员可以只开启需要的能力；关闭能力必须从
MCP 工具发现结果中消失，并在服务端执行入口再次拒绝缓存客户端的旧调用。

---

## 2. 已核验基线

| 能力 | 当前复用度（2026-09-05 复核实测） | 实施判断 |
|------|------------|----------|
| 高级查询 | `app/services/advanced_search.py:971` `AdvancedSearchService(db: Session)` 同步会话；`search_torrents(request, user_id) -> Dict`（:989） | 可直接复用业务核心；MCP 需限制返回规模并转换为脱敏 DTO |
| 创建查询模板 | 同文件 `create_search_template(request, user_id) -> Dict`（:1120） | 可直接复用业务核心；用户 ID 必须来自认证主体 |
| 仪表盘 | `app/services/dashboard_service.py:18` `DashboardService(db: AsyncSession, app)` 直接探测 `app.state.store`（:38-40） | 小改：改为注入运行时上下文/store，不让工具自行导入全局 app；注意与高级查询的同步会话差异 |
| 等级 4 | `app/services/torrent_deletion_by_level.py:46` `(db, request: Optional[Request] = None)` 已部分解耦但多路径仍 `raise ValueError`（:95 等 6 处）；`async_deletion_executor.py:31` 仍必传 Request | 中改：以 store + AuditContext 替换 FastAPI Request；保留部分成功语义 |
| Cron 触发 | `app/tasks/cron_executor.py:1054` `start_task_immediately(task_id) -> bool`（enabled/运行中前检 :1063-1075）；`CronTask.task_code` unique（`app/tasks/cron_models.py:17`，模型不在 app/models/）；内置注册表 `app/data/default_scheduled_tasks.py` + 资源准入 `app/tasks/task_profiles.py` | 中改：task_code 已存在；补策略前检、审计和 run_id/accepted 结果 |
| 添加种子 | 单种主体仍内联 `app/api/endpoints/torrent_crud.py:138`（嵌套函数 :208/:252/:441）；批量 `torrent_batch_add_service.py` 依赖 `UploadFile`（:16/:58）与 `app.state`（:99/:335） | 必须先抽协议无关 service，再由 HTTP/MCP 共用 |

核验环境：根 `./init.sh --ci` 通过；高级搜索/模板/仪表盘 46 项、等级删除/添加 57 项、
Cron 安全与执行器 36 项，共 139 项定向回归通过。当前仓库没有 MCP 实现或依赖声明，
且 PyInstaller 规格显式排除了 `fastmcp`，交付制品接入必须单独过门禁。

---

## 3. 明确不做

- 不让 MCP 调用现有 HTTP endpoint，也不复制 endpoint 业务代码。
- 不新增模块级下载器客户端；所有实时操作继续只使用 `app.state.store`。
- 首版不提供关闭脱敏或返回原始 Tracker URL/消息/绝对路径的选项。
- 首版不开放任意 Shell、CMD、PowerShell、Python 脚本任务，即使
  `BTDECK_ALLOW_CUSTOM_SCRIPTS=True`。
- 首版不引入长期 MCP API Key；复用现有短期访问 JWT，并把纯 token 认证内核收敛为
  HTTP/MCP 共用函数。
- 不在本 feature 内整体迁移 `torrents_async.py`；其目录归位作为独立技术债处理。

---

## 4. 架构决策

### 4.1 同进程与挂载顺序

MCP ASGI 应用挂载到同一个 FastAPI 进程和 lifespan，显式注入父应用运行时上下文。
挂载必须发生在 SPA catch-all 之前；禁止工具通过 `from app.main/factory import app` 获取全局实例。

```text
HTTP endpoint ─┐
               ├─> protocol-independent services ─> DB / app.state.store / cron executor
MCP tool ──────┘

HTTP settings API ─> McpSettingsService ─> configs(mcp.runtime.v1)
                                         └─> atomic runtime snapshot
                                                   ├─> transport global gate
                                                   ├─> tools/list filter
                                                   └─> tools/call recheck
```

下载器缓存尚未初始化、调度器尚未启动或应用正在关闭时，相关工具必须返回稳定的
`RUNTIME_NOT_READY`，不得自行创建下载器连接或第二个调度器。

### 4.2 配置持久化与动态生效

复用现有 `configs(key, value, description)` 表，不新增重复配置表。使用唯一键
`mcp.runtime.v1` 保存版本化 JSON：

```json
{
  "schemaVersion": 1,
  "enabled": false,
  "capabilities": {
    "torrent.advanced_search": false,
    "torrent.mark_pending_delete": false,
    "torrent.add": false,
    "search_template.create": false,
    "dashboard.read": false,
    "cron.trigger": false
  },
  "revision": 0,
  "updatedAt": null,
  "updatedBy": null
}
```

约束：

- 记录缺失、JSON 损坏、schemaVersion 未知、字段缺失均 fail-closed：全局关闭且全部能力关闭。
- `PUT /mcp/settings` 必须携带 `expectedRevision`，单事务比较并递增 revision，冲突返回 409。
- 配置提交后原子替换内存快照；下一次 `tools/list` 和 `tools/call` 立即使用新 revision，无需重启。
- 全局关闭后立即拒绝新会话和新调用；正在执行的读取可完成，已进入提交阶段的写操作必须完成
  审计/回滚收尾，不能强杀到不一致状态。
- 增加只读环境紧急开关 `BTDECK_MCP_FORCE_DISABLED=True`。该开关优先级最高，UI 不得覆盖。
- 控制面仅允许数据库中仍存在、`is_active=True` 且 `must_change_password=False` 的认证用户操作；
  当前模型无角色字段，不伪造不存在的 RBAC。未来引入角色后再收紧为管理员权限。

### 4.3 预置能力目录

| capability code | 工具建议名 | 风险 | 默认 | 额外门禁 |
|-----------------|------------|------|------|----------|
| `torrent.advanced_search` | `torrent_advanced_search` | 只读 | 关闭 | 字段白名单、分页/响应预算、脱敏 DTO |
| `torrent.mark_pending_delete` | `torrent_mark_pending_delete` | 写入下载器+DB | 关闭 | `confirm=true`、最多 100 项、逐项结果、幂等键 |
| `torrent.add` | `torrent_add_file` | 外部副作用 | 关闭 | 文件大小/类型限制、禁止服务器路径、幂等键、审计 |
| `search_template.create` | `advanced_search_template_create` | DB 写入 | 关闭 | 用户所有权、严格条件校验、`is_public=false` 默认 |
| `dashboard.read` | `dashboard_get` | 只读 | 关闭 | 仅脱敏聚合数据，不返回下载器地址或审计敏感字段 |
| `cron.trigger` | `cron_task_trigger` | 高风险执行 | 关闭 | 内置任务白名单、稳定 task_code、确认、审计、run_id |

当全局服务开启但未启用任何能力时，MCP 可以初始化但 `tools/list` 返回空列表。能力关闭时：

1. 不出现在工具发现结果。
2. 已缓存工具定义的客户端直接调用时返回 `CAPABILITY_DISABLED`。
3. 不能通过别名、旧版本工具名或批量入口绕过。

### 4.4 统一认证

- 抽取纯函数/服务 `authenticate_access_token(token, db) -> AuthenticatedPrincipal`，统一现有
  `require_authenticated_user` 与 `get_current_user` 的差异。
- MCP transport 只负责从授权 metadata/header 提取 Bearer token；service 不接收 FastAPI Request。
- principal 至少包含 `user_id`、`username`、`is_active`、`must_change_password`。
- token 缺失、过期、登录密钥不一致、用户不存在/禁用、强制改密中均拒绝。
- 工具参数中的 `user_id/operator` 一律忽略或拒绝，操作者只能来自 principal。

### 4.5 敏感数据最小化与脱敏

MCP 不直接序列化现有 TorrentInfoVO、TrackerInfoVO、ORM 对象或异常对象。每个工具必须输出
显式 allowlist DTO，并在最终序列化前经过统一 sanitizer 和泄漏扫描器。

| 数据类型 | MCP 输出策略 |
|----------|--------------|
| Tracker URL | 仅返回规范化 hostname/domain；移除 scheme、端口以外路径、query、fragment、userinfo、passkey/token |
| Tracker 消息 | 不返回原始 announce/scrape 文本；只返回 `working/error/unknown` 等规范状态和安全计数 |
| 绝对保存路径/种子文件路径 | 不返回原值；仅返回不含盘符、UNC、挂载根和父目录的 `pathDisplay`，或省略 |
| 下载器连接信息 | 只允许 ID、nickname、类型、在线状态和聚合速度；host/port/username/password/cookie/token 永不输出 |
| 种子 Hash | 高级查询默认省略；跨工具关联使用 `info_id`，确需诊断时只返回不可逆短指纹 |
| 审计信息 | IP、User-Agent、session/request token 不进入 MCP 业务响应 |
| 自由文本错误 | 先移除 URL 凭据、passkey/token、绝对路径和客户端异常细节，再映射为稳定错误码 |

高级查询与查询模板的 MCP 输入也受隐私契约限制：Tracker 只允许域名条件，不接受含 `/`、`?`、
`#`、`@`、userinfo 或 passkey 的完整 URL；不开放原始 tracker message 条件。HTTP 现有能力保持不变，
协议适配层把安全域名条件映射到共用 service。

日志同样适用脱敏：禁止记录完整工具参数、返回 payload、原始 Tracker URL/消息、上传内容和绝对路径。
允许记录 capability code、principal ID、配置 revision、耗时、行数、结果码和审计 ID。

### 4.6 查询与响应预算

- MCP 高级查询 `pageSize` 默认 20、最大 200；不沿用 HTTP 的 100000 上限。
- 序列化响应默认硬上限 1 MiB；超限返回 `RESULT_TOO_LARGE` 并提示缩小查询，不截断到不合法 JSON。
- 查询 timeout、正则预算继续复用现有高级搜索保护；工具层增加总耗时门禁。
- 明确排除软删除、回收站和活动删除任务，保持与现有 service 一致。

### 4.7 写操作安全

所有写操作必须具有 `confirm=true`、幂等键、逐项结果和审计记录。MCP 返回的是领域结果，不使用
HTTP `CommonResponse`，但稳定错误码必须能与 HTTP 业务语义对齐。

等级 4：

- 工具名和描述明确“仅添加 `pending_delete` 标签，不删除文件/任务”。
- 下载器成功但 DB 更新失败必须返回 `partial`，保留 `db_update_success=false`，不得折叠为成功。

添加种子：

- 首版只接受 `.torrent` 二进制内容/受控 MCP resource，不接受磁力链接、URL 或服务器本地路径。
- 默认单文件最大 10 MiB、可配置但硬上限 64 MiB；校验 bencode、info hash、扩展名和空文件。
- 必须先抽取 `TorrentAddService`，HTTP `/torrent/add` 与 MCP 共用；下载器调用继续走现有调度/超时治理。

Cron：

- 首版仅允许显式 MCP allowlist 中的内置 `task_code`；task_type 0～3 永不开放。
- 任务必须 enabled、未运行、通过执行器策略检查；返回 `accepted`、`task_code`、`run_id`，不伪报完成。
- 禁止 MCP 修改任务定义、executor、cron 表达式或启停状态。

---

## 5. 强制实现门禁

以下门禁全部为 blocking。`FAIL`、`NOT_RUN`、`INDETERMINATE` 或证据缺失均阻止 MCP 能力进入发布制品。
G1、G2、G3、G5、G7、G8 不允许豁免。

| Gate | 门禁 | PASS 条件 | 最低证据 |
|------|------|-----------|----------|
| G0 | 架构与边界 | MCP 与 FastAPI 同进程；挂载早于 SPA fallback；工具不调用 endpoint/不新建下载器客户端 | 架构约束测试 + import 扫描 |
| G1 | 默认关闭 | 配置缺失/损坏/未知版本/首次安装/升级均为全局关+能力全关；环境 kill switch 生效 | 默认值、迁移升级、损坏配置、重启矩阵 |
| G2 | 逐能力发现与执行双门禁 | disabled 工具不出现在 list；缓存直调也拒绝；配置 revision 热更新无重启生效 | 6 能力参数化测试 + 并发切换测试 |
| G3 | 认证与控制面 | JWT、用户存在/启用/强制改密校验统一；伪造 user/operator 无效 | HTTP/MCP 认证矩阵 + 负向测试 |
| G4 | Service 共用 | HTTP/MCP 调同一业务 service；service 不接收 Request/UploadFile/CommonResponse | AST/import 守卫 + 等价契约测试 |
| G5 | 数据最小化与脱敏 | Tracker/passkey/token/绝对路径/下载器凭据在响应、错误、日志中零泄漏 | 嵌套 canary、URL 编码、camel/snake、异常文本、变异测试 |
| G6 | 查询预算 | pageSize≤200、响应≤1MiB、timeout/正则预算生效，超限 fail-closed | 边界、超时、超大结果和资源基准 |
| G7 | 写操作确认与幂等 | 三类写操作必须确认、幂等、逐项结果、审计；等级4部分成功不丢失 | 重放/并发/部分失败/审计契约测试 |
| G8 | Cron 与上传安全 | Cron 仅内置 allowlist；脚本永拒；上传无路径入口且通过大小/bencode/类型校验 | 命令注入、路径穿越、伪 torrent、超限、脚本任务负测 |
| G9 | 运行时与关闭语义 | store/scheduler 未就绪稳定拒绝；关闭后无新调用；在途写操作完成一致性收尾 | lifespan、启停并发、优雅关闭测试 |
| G10 | 依赖与制品 | MCP 依赖锁定；PyInstaller 不再排除所选运行时；EXE/DEB/RPM/Docker 均验证开关和工具清单 | 制品内依赖清单 + 黑盒 smoke |
| G11 | 观测、回滚与发布 | 配置变更和工具写操作可审计、日志脱敏；kill switch/回滚演练通过 | gate report、审计样本、故障注入和回滚记录 |

---

## 6. 实施波次

### W0：架构、威胁模型与运行时选择

- 固化工具 schema、错误码、风险分级、能力目录和脱敏数据字典。
- 选择并锁定 MCP SDK/transport，验证与 FastAPI lifespan、PyInstaller 和现有依赖兼容。
- 建立 G0～G11 自动门禁骨架和负向变异清单。

预期文件：

- `backend/app/mcp/contracts.py`
- `backend/app/mcp/errors.py`
- `backend/tests/mcp/test_architecture_constraints.py`
- `docs/security/mcp-threat-model.md`

### W1：配置控制面、能力目录与设置 UI

- 复用 `configs` 表实现 `McpSettingsService`、revision CAS、默认 seed 和 atomic snapshot。
- 新增认证配置 API；设置页增加全局开关、6 项能力开关、风险说明和环境强制关闭提示。
- 移动设置页复用桌面组件，不复制逻辑。

预期文件：

- `backend/app/services/mcp_settings_service.py`
- `backend/app/api/endpoints/mcp_settings.py`
- `backend/app/data/default_mcp_settings.py`
- `backend/app/api/api.py`
- `backend/app/core/config.py`
- `frontend/src/api/mcp-settings.ts`
- `frontend/src/views/settings/components/McpSettingsPanel.vue`
- `frontend/src/views/settings/index.vue`
- `backend/tests/api/test_mcp_settings.py`
- `frontend/tests/unit/mcp-settings.spec.ts`

### W2：同进程服务、统一认证与隐私边界

- MCP app 在 SPA fallback 前挂载并绑定父应用 RuntimeContext。
- 收敛 token→principal 认证内核；所有工具调用先过全局/能力/认证三重门禁。
- 实现显式 DTO、Tracker 域名归一、路径/自由文本 sanitizer 和最终泄漏扫描器。

预期文件：

- `backend/app/mcp/server.py`
- `backend/app/mcp/runtime.py`
- `backend/app/mcp/catalog.py`
- `backend/app/mcp/auth.py`
- `backend/app/mcp/redaction.py`
- `backend/app/factory.py`
- `backend/app/auth/dependencies.py`
- `backend/tests/mcp/test_auth.py`
- `backend/tests/mcp/test_redaction.py`
- `backend/tests/mcp/test_capability_gates.py`

### W3：六项工具按风险接入

1. 高级查询、查询模板、仪表盘。
2. 等级 4 标记、Cron 触发。
3. 抽取统一 TorrentAddService 后接入添加种子。

预期文件：

- `backend/app/mcp/tools/torrents.py`
- `backend/app/mcp/tools/search_templates.py`
- `backend/app/mcp/tools/dashboard.py`
- `backend/app/mcp/tools/cron.py`
- `backend/app/services/torrent_add_service.py`
- `backend/app/services/torrent_deletion_by_level.py`
- `backend/app/services/dashboard_service.py`
- `backend/app/tasks/cron_executor.py`
- `backend/app/api/endpoints/torrent_crud.py`
- `backend/tests/mcp/test_tools_*.py`

### W4：等价、制品与上线演练

- 为六项能力建立 HTTP service/MCP 领域结果等价测试。
- 对关闭/部分开启/全开启、配置损坏、重启、并发切换、store 未就绪和 kill switch 做矩阵验证。
- 修正 requirements、Docker 与 PyInstaller 配置；对 EXE/DEB/RPM/Docker 做外部黑盒验证。
- 完成脱敏 canary 变异、工具发现缓存绕过、prompt 注入载荷和回滚演练。

预期文件：

- `backend/requirements.txt`
- `deploy/requirements-windows-package.txt`
- `deploy/requirements-linux-package.txt`
- `deploy/btdeck.spec`
- `deploy/btdeck-windows.spec`
- `backend/Dockerfile`
- `scripts/release/contract_runner.py`
- `backend/tests/release/`
- `docs/operations/mcp-runbook.md`

---

## 7. 测试矩阵

必须至少覆盖：

- 全局开关：缺失、false、true、环境强制关闭、损坏 JSON、未知 schemaVersion。
- 每项能力：单独开启、任意组合、全部关闭、全部开启；list 与 call 同时验证。
- 配置并发：旧 revision 409、原子快照、关闭竞态、重启恢复。
- 认证：无 token、伪造、过期、旧登录密钥、缺 user_id、用户不存在/禁用、强制改密。
- 脱敏：Tracker path/query/passkey、URL 编码 passkey、announce/scrape 消息、Windows/UNC/Linux 路径、
  下载器凭据、异常文本、嵌套集合、camelCase/snake_case、日志捕获。
- 查询：0/1/200/201 pageSize、1 MiB 边界、正则超时、软删除与活动删除排除。
- 等级 4：重复提交、下载器失败、DB 失败部分成功、审计失败、100 项上限。
- 添加：空文件、伪 bencode、错误扩展名、10 MiB 默认/64 MiB 硬上限、路径穿越名、重复 info hash、
  qB/TR 成功/超时、幂等重放。
- Cron：不存在、禁用、运行中、内置 allowlist、脚本类型、恶意 executor、重复触发、run_id 与审计。
- 生命周期：MCP 先于 store 就绪、服务关闭、应用 shutdown、在途读写。
- 制品：源码、Docker、Windows/Linux 打包环境中的默认关闭、部分能力发现和脱敏 smoke。

---

## 8. 完成定义

本 feature 仅在以下条件全部满足时可标记 done：

- G0～G11 全部 PASS，禁止以“暂未运行”替代证据。
- 6 项能力可分别开关，默认全部关闭；全局开关关闭时无 MCP 调用可执行。
- Tracker/passkey/token/绝对路径/下载器凭据在 MCP 响应、错误和日志中零泄漏。
- HTTP 与 MCP 共用同一 service，未引入 endpoint-to-endpoint 调用或第二套下载器连接。
- 相关 mypy/black/flake8/pytest、前端 lint/typecheck/build、根 `./init.sh` 全部通过。
- EXE/DEB/RPM/Docker 发布制品完成默认关闭、部分能力和脱敏黑盒验证。
- `feature_list.json` 写入逐 gate evidence，`progress.md`、`session-handoff.md`、API/MCP 文档和
  `docs/roadmap/` 随源码最终同步。

---

## 9. 回滚与紧急处置

1. 首选设置 `BTDECK_MCP_FORCE_DISABLED=True` 并重启，强制覆盖数据库配置。
2. 或通过认证设置 API 将 `enabled=false`，立即阻止新调用。
3. 回滚代码前保留 `configs.mcp.runtime.v1`；旧版本忽略该键，不影响启动。
4. 若发现敏感数据泄漏，按安全事件处理：立即全局关闭、轮换疑似暴露 token/passkey、保留脱敏后的
   审计 ID，不在工单/日志复制原始泄漏值。
5. 已提交的下载器/Cron 副作用不以关闭服务作为自动回滚手段，按各领域既有审计和补偿流程处理。

---

## 10. 2026-09-05 基线复核与 W0 代码调整计划

> 复核环境：dev @ 9ccd12f。核心架构判断（六能力复用面、SPA fallback 挂载顺序、
> 默认关闭、仓库零 MCP 依赖、两 spec 显式排除 fastmcp）全部成立；以下为漂移修正与
> W0 启动批次。**按批次纪律：本节经确认后才动代码。**

### 10.1 漂移修正（原计划与新实测的差异）

1. **文件名**：高级查询服务是 `app/services/advanced_search.py`（`advanced_search_service.py`
   不存在）。G4 的 AST/import 守卫须按实际文件名定位。
2. **同步/异步双会话**：`AdvancedSearchService(db: Session)` 同步、
   `DashboardService(db: AsyncSession, app)` 异步——MCP runtime 的会话工厂必须同时供给
   两套（原计划未覆盖，W2 runtime 设计新增约束）。
3. **认证现状是净新增而非"收敛"**：`app/auth/dependencies.py` 中
   `require_authenticated_user`（:83，纯 token 不查 DB）与 `get_current_user`（:102，查 DB）
   **均不校验 `is_active`/`must_change_password`**（is_active 仅 login.py:169 登录时拦截）；
   `AuthenticatedUserInfo`（:22-33）也不含这两个字段。W2 `authenticate_access_token(token, db)`
   需补齐用户状态校验，威胁模型须记录"现状无服务端强制改密拦截"。
4. **configs 无版本化 JSON 先例**：表模型 `app/auth/models.py:57`（key/value/description）
   成立，但现有唯一使用是标量 `cookie_expire_minutes`（database.py:202）；
   `mcp.runtime.v1` 是首个版本化 JSON 键，W1 seed/CAS 设计自建模式。
5. **Cron 资料定位**：模型在 `app/tasks/cron_models.py`（非 app/models/）；task_code 注册表
   在 `app/data/default_scheduled_tasks.py` + `app/tasks/task_profiles.py`。
   task_type 已扩展至 6（5=清理回收站、6=审计日志导出，cron_models.py 注释滞后），
   G8 allowlist 表述需明确 4/5/6 归类：仅按显式 task_code 白名单放行，类型不作为放行依据。
6. **脱敏字典补新泄漏面**：`TrackerMessageLog.msg`（torrents/models.py:415，2048 长原始消息）
   与 `sample_urls`（:421，原始 tracker URL 列表）是原计划未点名的泄漏源，纳入 W0 数据字典。
7. **Python 版本矩阵修正**：Docker/Linux 3.11、Windows 桌面打包 3.12.4、Android Chaquopy
   3.12（非"3.11 桌面 + 3.12 Android"）。SDK 需同时兼容 3.11/3.12 +
   fastapi 0.115.6 + starlette 0.41.3，并在两个 spec（btdeck.spec:212、
   btdeck-windows.spec:279 的 `excludes=['fastmcp', …]`）上评估解除路径。
8. **测试落点**：`backend/tests/` 已 238 个文件、根级已有 `test_architecture_constraints.py`；
   新增 `tests/mcp/test_architecture_constraints.py` 时需处理 pytest 同名模块收集
   （加 `__init__.py` 或改名 `test_mcp_architecture_constraints.py`，W0 实测定夺）。

### 10.2 W0 批次实施清单（代码调整计划，待确认）

**目标**：不动业务代码，交付"契约 + 探针 + 门禁骨架"，使 W1~W4 可以按 G0~G11 逐门推进。

| # | 交付物 | 内容要点 |
|---|--------|----------|
| 1 | `backend/app/mcp/contracts.py` | 6 工具 schema（输入/输出 allowlist DTO）、capability 目录（§4.3 表）、错误码枚举、脱敏数据字典（含 10.1-6 新泄漏面） |
| 2 | `backend/app/mcp/errors.py` | 稳定错误码：`RUNTIME_NOT_READY`/`CAPABILITY_DISABLED`/`SERVICE_DISABLED`/`RESULT_TOO_LARGE`/`AUTH_REQUIRED`/`AUTH_USER_INACTIVE`/`PASSWORD_CHANGE_REQUIRED` 等，与 HTTP 业务语义对齐表 |
| 3 | SDK 兼容探针 `backend/tests/mcp/test_sdk_compatibility.py`（或独立探针脚本） | 在 fastapi 0.115.6 + starlette 0.41.3 下验证所选 MCP SDK 的 ASGI 挂载、lifespan 共存、PyInstaller onefile import；3.11/3.12 双版本；产出选型结论写入本节 |
| 4 | `backend/tests/mcp/test_mcp_architecture_constraints.py` | G0 骨架：静态扫描禁 `from app.main/factory import app`、禁 MCP→HTTP endpoint 调用、禁新建下载器客户端；处理 10.1-8 同名问题 |
| 5 | `docs/security/mcp-threat-model.md` | 威胁模型：STRIDE + 现状缺口（10.1-3 认证无状态校验）+ prompt 注入面 + 回滚预案引用 §9 |
| 6 | G0~G11 门禁骨架 | `backend/tests/release/` 增 mcp gate 占位（fail-closed：NOT_RUN 即红），对齐 release-gate DAG 语义 |

**W0 明确不做**：不引入生产 requirements 变更（SDK 只进 dev/探针环境，W4 才锁定进
requirements 与 spec）；不改 `app/auth/`、`app/factory.py`、任何业务 service；
不做设置 UI。

**W0 完成判据**：契约/错误码/目录/数据字典评审通过；探针给出 SDK 选型结论
（含 PyInstaller 可行性）；G0 静态门禁在当前无实现代码基线上绿；
threat-model 评审通过。此后按 W1（配置控制面）→ W2（挂载/认证/脱敏）→
W3（六工具三批）→ W4（等价/制品/演练）推进，每批过对应门禁并回填 evidence。

### 10.3 对 W1~W4 的既定修正（沿用原计划，按 10.1 修订）

- W1：`mcp.runtime.v1` seed 按"首个版本化 JSON 键"自建迁移模式（复用 Alembic 纪律）。
- W2：runtime 同时暴露 `session_factory`（同步）与 `async_session_factory`；认证内核
  `authenticate_access_token(token, db)` 净新增并补 `is_active`/`must_change_password` 校验，
  `AuthenticatedUserInfo` 扩展字段（HTTP 侧不改变现有语义，避免牵动 4466 项测试）。
- W3：cron.trigger allowlist 数据源改 `default_scheduled_tasks.py` + `task_profiles.py`；
  task_type 4/5/6 一律不作为放行依据，仅显式 task_code 白名单。
- W4：制品矩阵按 10.1-7 的真实 Python 版本（3.11 Docker/Linux、3.12 Windows 打包）验证。

