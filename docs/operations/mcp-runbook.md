# MCP 服务运维手册（Runbook）

> 适用版本：v1.0.7+（feature `mcp-service-capabilities-2026-08-28`）
> 计划来源：`PLANS/mcp-service-capabilities.md`；威胁模型：`docs/security/mcp-threat-model.md`
> 门禁汇总：`scripts/release/aggregate_mcp_gates.py`（12 门全 PASS 才可随发布制品出厂）

## 1. 服务概述

- **形态**：与 FastAPI 同进程的官方 `mcp` SDK（streamable HTTP，stateless）子应用，挂载于 `/mcp`
  （SPA fallback 之前；SDK 缺失的旧制品自动不挂载，行为退化为 404）。
- **默认状态**：**全局关闭 + 六能力全关**（fail-closed：配置缺失/损坏/未知 schemaVersion
  一律回落默认全关，不部分采信）。
- **认证**：与 HTTP 控制面共用同一 principal 内核（Bearer/X-Access-Token 双兼容；
  禁用/强制改密用户拒绝）。

## 2. 能力目录与风险分级

| 能力码 | 工具名 | 风险 | 说明 |
|---|---|---|---|
| `torrent.advanced_search` | `torrent_advanced_search` | read | 高级查询（脱敏 DTO） |
| `search_template.create` | `advanced_search_template_create` | write | 查询模板创建（confirm+幂等） |
| `dashboard.read` | `dashboard_get` | read | 仪表盘聚合 |
| `torrent.mark_pending_delete` | `torrent_mark_pending_delete` | write | 仅加 `pending_delete` 标签（≤100 项/次，partial 不折叠） |
| `cron.trigger` | `cron_task_trigger` | high | 内置任务白名单触发（task_type 0-3 永拒） |
| `torrent.add` | `torrent_add_file` | high | 添加 .torrent（仅 base64 二进制；10/64MiB 双上限） |

所有写/高风险工具必须 `confirm=true` + `idempotency_key`（同键重放返回首次结果）。

## 3. 开启 / 关闭（热生效，无需重启）

- **控制面**：设置页 →「MCP 服务」页签；或 `PUT /api/v1/mcp/settings`
  （携带 `expectedRevision` 做 CAS；冲突 409 后重读再提交）。
- **生效语义**：每次 `tools/list` / `tools/call` 现读配置快照，PUT 后下一次调用立即生效；
  关闭的能力从 `tools/list` 消失，缓存旧定义直调得到 `CAPABILITY_DISABLED`。
- **验证**：
  ```bash
  curl -s -X POST http://<host>:<port>/mcp/ \
    -H 'Authorization: Bearer <token>' -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
  ```

### 3.1 服务密钥（W5：外部 agent 对接）

1. 设置页 → MCP 服务 → 「服务密钥（API Key）」：`absent` 时点「生成服务密钥」，
   `active` 时密钥默认掩码，可「复制」或悬停眼睛图标查看明文。
2. 端点：`<实例 origin>/mcp/`（Streamable HTTP；无斜杠会 307）。
3. 认证头二选一：`Authorization: Bearer btdmcp_...` 或 `X-Access-Token: btdmcp_...`。
4. 「刷新服务密钥」立即使旧密钥失效（正在使用的 agent 会断联），刷新后需把新密钥
   重新配置到各 agent；刷新走 revision CAS，并发冲突返回 409，刷新页面重试。
5. 安全提示（UI 同文）：密钥以可逆加密存储于本机数据库，泄露数据库文件或实例
   配置密钥等同于泄露该密钥；明文仅在页面内存中展示，不写入浏览器存储。
6. `unreadable` 态说明实例 `security.secret_key` 已轮换（查看不可用、认证仍有效），
   刷新生成新密钥即自愈（key-rotation-runbook §2.1）。

## 4. 紧急关闭（优先级从高到低）

1. **环境 kill switch**（最高优先级，UI 不可覆盖）：
   `BTDECK_MCP_FORCE_DISABLED=True` + 重启进程 → `effectiveEnabled=false`，
   库内配置保留（重启后落库意图仍在，关闭只是覆盖）。
2. **配置热关闭**：设置页关全局开关或 `PUT enabled=false`（立即生效，无需重启）。
3. **彻底回滚**：配置层关闭即可；无需回滚代码——历史制品（无 mcp SDK）本就不挂载 `/mcp`。

## 5. 审计与观测

- **审计事件**（`TorrentAuditLog`）：
  - `mcp_tool_call`：写/高风险工具的每次调用（成功/失败/重放；读工具按设计不产生此事件）；detail 只含工具名/对象标识
    （info_id/info_hash/task_code/downloader_id）、结果码与幂等键 sha256 前 16 位——
    **不含工具参数原文、文件内容、领域 payload**。
  - `mcp_settings_update`：控制面 PUT（best-effort）。
  - `mcp_apikey_view`：服务密钥**明文查看**（仅 active 态真实披露时记录；absent/
    unreadable 读取不记，避免面板挂载噪音）；detail 只含 revision。
  - `mcp_apikey_rotate`：服务密钥生成/刷新；detail 含 `revision`/`previousOwner`/
    `rotatedBy`——**禁记密钥本体与哈希**（防泄露面）。
- **日志允许面**（`app.mcp` logger）：capability/principal/revision/结果码；
  上游异常文本（下载器 msg、正则超时文本）只进服务端 `logger.warning`，不进响应与审计。
- **失败排查**：响应稳定错误码（见 §6）；`RUNTIME_NOT_READY`=store/调度器未就绪或关闭中，
  属预期启动窗口行为，不要在就绪前重试风暴。

## 6. 错误码速查（对齐 HTTP 语义）

| MCP 码 | HTTP | 常见原因 |
|---|---|---|
| `SERVICE_DISABLED` | 503 | 全局关 / kill switch |
| `CAPABILITY_DISABLED` | 404 | 能力关（含缓存旧定义直调） |
| `AUTH_*` / `PASSWORD_CHANGE_REQUIRED` | 401/403 | 认证矩阵（`AUTH_API_KEY_INVALID`=服务密钥无效/已刷新，W5） |
| `RUNTIME_NOT_READY` | 503 | store 未就绪 / 关闭中 / MCP 先于 store |
| `CONFIRM_REQUIRED` / `IDEMPOTENCY_KEY_REQUIRED` | 428/400 | 写操作缺确认/幂等键 |
| `UPLOAD_TOO_LARGE` / `UPLOAD_INVALID_CONTENT` | 413/422 | 种子上限（默认 10MiB，env `BTDECK_MCP_TORRENT_UPLOAD_MAX_BYTES` 可调、恒 ≤64MiB）/ 伪 bencode |
| `SERVER_PATH_FORBIDDEN` | 400 | 磁力/URL/服务器路径输入 |
| `PAGE_SIZE_EXCEEDED` / `RESULT_TOO_LARGE` / `ITEM_LIMIT_EXCEEDED` | 422/413/422 | 预算 fail-closed |
| `CRON_TASK_NOT_ALLOWED` / `CRON_TASK_NOT_TRIGGERABLE` | 403/409 | 白名单外 / 任务禁用或运行中 |
| `DOWNSTREAM_FAILURE` / `INTERNAL_ERROR` | 502/500 | 下载器失败（已清洗）/ 兜底固定文案 |

## 7. 升级与降级

- 配置 schema 演进：未知 `schemaVersion`（含降级打开新库）→ fail-closed 全关；
  首次 `PUT`（`expectedRevision=0`）重建/修复配置行。
- 幂等缓存为进程内 512 LRU：重启后同键会再次执行（首版口径）；同键并发在途窗口
  不做在途去重（两次执行、负载一致），调用方应以幂等键语义消费结果。

## 8. 门禁与发布

```bash
C:/software/anaconda3/python.exe scripts/release/aggregate_mcp_gates.py \
  --fragments-dir release/build/mcp-gate-fragments --out release/build/mcp-gate-report.json
```

`verdict=READY` 需 12 门全 PASS；`NOT_RUN`/`INDETERMINATE` = `BLOCKED`（fail-closed）。
制品面（EXE/DEB/RPM/Docker）发布前须黑盒复验：默认关闭 + 部分能力发现 + 脱敏 smoke。

### 8.1 制品黑盒三段配方（2026-09-09 G10 实证流程）

对任一制品起隔离实例（临时 `CONFIG_DIR`；Windows EXE 加 `BTDECK_MODE=server` 跳模式向导）后按序验证：

1. **A 默认关闭**（免认证）：`POST /mcp/` `initialize` → `serverInfo {name: BtDeck, version: <mcp SDK 版>}`（SDK 捆载）；`tools/list` → JSON-RPC `-32000` + `data.error_code=SERVICE_DISABLED`。
2. **B 部分开启**（真实控制面链路）：`admin` 首登（默认口令 + `must_change_password=true`）→ `/api/v1/user/changePassword` 清标志（请求体必带 `userId` 字段，端点忽略其值）→ `PUT /api/v1/mcp/settings` 仅开一项能力（`expectedRevision` 取自 GET）→ 带 Bearer `tools/list` 应**只**列出该能力。
3. **C 脱敏 smoke**：预置含 canary 的种子行（tracker_url 埋 passkey、save_path 埋绝对路径、info_hash 埋 40 位哈希；制品内无 python 时用字面量 `INSERT`——注意 `torrent_info.has_tracker_error` 等列为迁移层 NOT NULL 无模型默认，字面量 SQL 必须显式补值）→ `tools/call torrent_advanced_search` → 断言 `tracker_domains` 仅规范化域名、整包响应无 canary/passkey/hash/announce 原文。

### 8.2 服务密钥黑盒配方（2026-09-22 W5 实证流程）

D 段（密钥面，接 B 段已认证会话）：

1. `GET /api/v1/mcp/apikey` → `status=absent`、无 `key` 字段；
2. `POST /api/v1/mcp/apikey/rotate {"expectedRevision":0}` → `status=active`、
   `key` 匹配 `^btdmcp_[A-Za-z0-9_-]{43}$`、`revision=1`；
3. 再次 `POST .../rotate {"expectedRevision":0}` → HTTP 409 + `data.reasonCode=
   MCP_APIKEY_CONFLICT` + `data.currentRevision=1`（并发 CAS）；
4. 带 `Authorization: Bearer <新密钥>` 请求 `POST /mcp/` `tools/list` → 与 B 段
   JWT 会话**同样的能力发现结果**（两种认证等价）；
5.  rotate 到第二把密钥后，旧密钥请求 `tools/list` → JSON-RPC `-32000` +
   `data.error_code=AUTH_API_KEY_INVALID`（旧密钥即失效）；
6. 审计页存在 `mcp_apikey_rotate`（detail 含 previousOwner/rotatedBy、无密钥本体）
   与 `mcp_apikey_view` 行。

注意事项：探测客户端 `trust_env=false`（注册表系统代理会劫持 loopback）；deb/rpm 包内二进制应先做 sha256 一致性对齐再抽测；dirty 身份（dev 构建）制品 `/health/ready` 会 503（身份门禁预期），就绪探测改用 `initialize` 握手。
