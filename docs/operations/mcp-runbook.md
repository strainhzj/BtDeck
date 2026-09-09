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
- **日志允许面**（`app.mcp` logger）：capability/principal/revision/结果码；
  上游异常文本（下载器 msg、正则超时文本）只进服务端 `logger.warning`，不进响应与审计。
- **失败排查**：响应稳定错误码（见 §6）；`RUNTIME_NOT_READY`=store/调度器未就绪或关闭中，
  属预期启动窗口行为，不要在就绪前重试风暴。

## 6. 错误码速查（对齐 HTTP 语义）

| MCP 码 | HTTP | 常见原因 |
|---|---|---|
| `SERVICE_DISABLED` | 503 | 全局关 / kill switch |
| `CAPABILITY_DISABLED` | 404 | 能力关（含缓存旧定义直调） |
| `AUTH_*` / `PASSWORD_CHANGE_REQUIRED` | 401/403 | 认证矩阵 |
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
