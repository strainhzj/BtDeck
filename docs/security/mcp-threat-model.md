# MCP 服务与可选能力开放——威胁模型

> **Feature**: `mcp-service-capabilities-2026-08-28`
> **版本**: W0 初版（2026-09-08），随 W1~W4 各波次增补实证细节
> **上游文档**: 实施计划 `PLANS/mcp-service-capabilities.md`（§4 架构决策 / §5 门禁 / §9 回滚）
> **契约单一事实源**: `backend/app/mcp/contracts.py`（能力目录、脱敏数据字典、预算）、`backend/app/mcp/errors.py`（稳定错误码）

---

## 1. 范围与系统边界

MCP 服务与 FastAPI 同进程，挂载于 SPA fallback 之前，共享 lifespan、`app.state.store`、
数据库会话工厂与定时任务执行器。本模型覆盖：MCP 客户端 → 传输层 → 挂载点 →
统一认证 → 能力门禁 → 六项工具 → 协议无关 service → DB / 下载器缓存 / Cron 执行器。

不覆盖（显式出界）：HTTP endpoint 既有攻击面（已有门禁）、下载器自身安全、
客户端 LLM 的提示词处理（仅约束服务端输出面，见 §5）。

```text
信任边界 A（网络）      信任边界 B（进程内协议适配）   信任边界 C（领域边界）
┌──────────┐   streamable HTTP   ┌──────────────────┐          ┌─────────────┐
│ MCP 客户端│ ═════════════════▶ │ 传输层(Bearer 提取)│          │ 共用 service │
│ (含 LLM) │                    │ 全局开关/能力门禁   │ ───────▶ │ DB/store/cron│
└──────────┘                    │ 认证内核(principal)│          └─────────────┘
      ▲                         │ 脱敏 DTO/泄漏扫描  │
      └──── 脱敏后领域结果 ◀──── └──────────────────┘
```

选型结论（W0 探针实证，计划 §10.4）：官方 `mcp` SDK（1.30.0）+ streamable HTTP
stateless 模式。fastmcp 2.14.3 因打包摩擦（未声明依赖/元数据/隐藏导入连环补救）落选。

## 2. 资产与敏感数据

敏感数据类型、来源字段与输出策略以 `backend/app/mcp/contracts.py` 的
`REDACTION_DATA_DICTIONARY` 为准（tracker URL/消息、绝对路径、下载器凭据、
种子 hash、审计元数据、自由文本错误、**MCP 服务密钥**、日志面工具载荷）。其中
`TrackerMessageLog.msg`（2048 长原始消息）与 `sample_urls`（原始 tracker URL 列表）
是计划 §10.1-6 点名的新泄漏面，已纳入字典并受 `tests/mcp/test_contracts.py` 锚定。

**MCP 服务密钥（W5，2026-09-22）**：`configs.mcp.apikey.v1` 行的
`keyEncrypted`（SM4 可逆密文）与 `keyHash`（SHA-256）。威胁面与下载器密码
同构：**获得「app.db + yaml `security.secret_key`」者可离线还原密钥明文**
（见 `docs/security/key-rotation-runbook.md`）。缓解：哈希为认证唯一事实源
（密文损坏不影响认证、只影响查看）；控制面查看/刷新均需 active 认证用户；
查看（active）与刷新全量审计；密钥列入脱敏字典与泄漏扫描 canary
（`btdmcp_` 格式）；明文不驻留 principal/日志/审计/浏览器存储。残留风险：
多用户场景任意 active 用户可 rotate（归属漂移可经审计追溯，见 E1 现状缺口）。

## 3. STRIDE 矩阵

| # | 威胁 | 信任边界 | 缓解措施 | 门禁 | W0 现状 |
|---|------|----------|----------|------|---------|
| S1 | 伪装认证主体（伪造/过期 token、参数携带 user_id/operator） | A→B | 统一 token→principal 内核；校验用户存在/启用/强制改密；主体字段一律拒绝（`FORBIDDEN_ARGUMENTS`） | G3 | principal 内核已存在（`app/auth/principal.py`），MCP 接线在 W2 |
| S3 | 服务密钥盗用/重放（W5） | A→B | `btdmcp_` 前缀路由 + SHA-256 恒定比对；归属用户状态全链校验；无效/损坏统一 `AUTH_API_KEY_INVALID`；rotate 即失效（无宽限期）；查看/刷新审计；密钥入脱敏 canary | G3/G11 | W5 落地（`app/services/mcp_apikey_service.py`） |
| E3 | 服务密钥泄露（W5：db+secret_key 离线还原、UI 肩窥、日志/审计误记） | B→A | SM4 密文+哈希分离（认证不依赖可逆副本）；审计明细禁记密钥；日志禁记密钥；明文仅组件内存；泄露响应=rotate（§7） | G5/G11 | W5 落地；残留：可逆副本同构下载器密码风险（key-rotation-runbook） |
| S2 | 关闭的能力被调用（缓存旧工具定义直调/别名绕过） | B | 发现与执行双门禁：disabled 不入 tools/list；call 侧按目录正名复核，未知名即拒 | G2 | 目录与正名查找已固化（contracts），运行时门禁 W2 |
| T1 | 配置篡改（并发写竞态、降级攻击关掉脱敏） | C | revision CAS（409）；`schemaVersion` 未知即 fail-closed；首版无脱敏关闭选项 | G1/G2 | 配置服务 W1 |
| T2 | 工具结果被篡改绕过脱敏（异常路径/旁路序列化） | B→A | 显式 allowlist DTO + 最终序列化前统一 sanitizer + 泄漏扫描器；MCP 不序列化既有 VO/ORM/异常对象 | G5 | 字典与输出 allowlist 已固化，运行时 W2 |
| R1 | 抵赖写操作（否认标记/添加/触发） | C | 三类写操作强制审计（真实 principal + 幂等键 + 逐项结果）；审计 ID 可返回 | G7/G11 | 契约已要求 confirm/幂等/审计，实现 W3 |
| I1 | 敏感数据泄漏（tracker passkey、绝对路径、下载器凭据、种子 hash） | B→A | §2 字典全量强制；错误与日志同面适用；嵌套 canary + URL 编码 + camel/snake 变异测试 | G5 | 字典固化 + 测试锚定；运行时扫描 W2，变异 W4 |
| I2 | 大结果拖垮进程/客户端（DoS 变体） | B | pageSize≤200、响应≤1MiB 不截断、timeout/正则预算、上传 10/64MiB、批量≤100 | G6/G8 | 预算常量固化（contracts），运行时 W2/W3 |
| D1 | 服务关闭/未就绪期间的调用（可用性语义滥用） | B | `RUNTIME_NOT_READY`/`SERVICE_DISABLED` 稳定拒绝；不自行创建连接或第二调度器 | G9 | 错误码已固化，运行时 W2 |
| D2 | Cron 白名单外任务触发（脚本任务/任意命令） | C | 仅显式 task_code 白名单；task_type 一律不作为放行依据；禁止改任务定义/启停 | G8 | 契约固化；allowlist 数据源 W3 |
| E1 | 权限提升（低权限用户开能力、控制面越权） | B/C | 控制面要求活跃认证用户；模型无角色字段不伪造 RBAC，引入角色后收紧管理员 | G3 | 现状缺口 §4-1 |
| E2 | 上传恶意种子文件（伪造 bencode/路径穿越名） | C | bencode/info hash/扩展名/空文件校验；只收内容不收路径；大小双上限 | G8 | 契约固化，实现 W3 |

## 4. W0 时点现状缺口（实施期风险登记）

1. **HTTP 侧认证未接内核（G3 缺口，计划 §10.1-3）**：`app/auth/dependencies.py` 的
   `require_authenticated_user`/`get_current_user` 均不校验 `is_active`/
   `must_change_password`（仅登录时拦截）。`app/auth/principal.py` 内核已补齐校验，
   但 HTTP 侧尚未接线。W2 接入时明确范围与强制改密例外，HTTP 既有语义不破坏。
2. **configs 表无版本化 JSON 先例**：`mcp.runtime.v1` 是首个版本化 JSON 键，
   W1 seed/CAS 自建模式；损坏/未知版本必须 fail-closed 到全局关闭。
3. **`torrents_async.py` 目录位置技术债**：4510 行 0 路由文件留在 endpoints/ 下，
   本 feature 不迁移（计划 §3），但 G0 静态扫描范围与之解耦。
4. **SDK 传递依赖新增**：官方 `mcp` 1.30.0 入生产 requirements 属 W4 批次；
   G10 要求四制品（EXE/DEB/RPM/Docker）黑盒验证后才能移出 BLOCKED。
   两 spec 的 `fastmcp` 排除条目保持有效（防御性瘦身清单，选型未选它）。
5. **Cron allowlist 数据源**：`trigger_task_by_code` 当前用整个内置注册表，
   尚非 MCP 专用白名单；W3 收窄为显式 task_code 列表。
6. **服务密钥无角色约束（W5，E1 同族）**：控制面查看/刷新与 settings 端点同门禁
   （任意 active 非强制改密用户），多用户场景下密钥归属可被他人 rotate 漂移
   （`previousOwner/rotatedBy` 入审计可追溯）。与 §4-1 同口径：不伪造 RBAC，
   引入角色后收紧为管理员权限。

## 5. Prompt 注入面分析

MCP 工具是程序化 JSON-RPC 调用，服务端无 LLM；注入风险集中在**客户端 LLM 消费
工具输出**的场景（攻击者控制的种子元数据携带诱导指令文本）。

| 注入面 | 攻击者可控度 | 服务端缓解 |
|--------|--------------|-----------|
| 种子名称/模板名称（输出字段） | 高（下载的种子可任意命名） | 输出为结构化 DTO 字段，字段名语义中性（`name`），服务端文案永不拼接"请执行/请访问"式祈使句；客户端将字段值视为数据非指令属客户端责任（文档声明） |
| Tracker 域名（输出字段） | 中 | 域名归一化（去 scheme/path/query/userinfo/passkey）后仅剩 hostname，注入载荷空间大幅收窄 |
| Tracker 状态（输出字段） | 低 | 仅 working/error/unknown 枚举 + 安全计数，无自由文本 |
| 错误文案（输出） | 低 | 稳定错误码 + 固定默认文案，不透传上游异常文本 |
| 工具描述（输出） | 无 | 固定文案常量，不含动态内容 |
| 工具参数（输入） | 高（客户端侧） | 输入经严格 schema + 白名单校验；值不进入任何提示词拼装；`user_id`/`operator` 携带即拒（同时防主体伪造 S1） |
| task_code / 状态码等枚举输入 | 无 | 封闭枚举 |

W4 门禁将包含 prompt 注入载荷回归（计划 §6 W4），用真实注入样例验证输出面无
祈使句拼接、枚举字段不受载荷影响。

## 6. 门禁与威胁映射

G0（架构边界，防 S2/T2 旁路）→ G1（默认关闭，防 T1）→ G2（发现/执行双门禁，防 S2）→
G3（统一认证，防 S1/E1）→ G4（共用 service，防 T2 逻辑分叉）→ G5（脱敏，防 I1）→
G6（查询预算，防 I2）→ G7（写操作确认/幂等/审计，防 R1）→ G8（Cron/上传安全，防
D2/E2）→ G9（运行时与关闭语义，防 D1）→ G10（依赖与制品，收口 §4-4）→
G11（观测/回滚/发布证据，防 T1/R1 残留）。门禁片段 schema 与汇聚器见
`release/schemas/mcp-gate-fragment.schema.json`、`scripts/release/aggregate_mcp_gates.py`
（fail-closed：PASS 必须带非空 evidence；缺失=NOT_RUN=BLOCKED）。

## 7. 回滚与紧急处置（引用计划 §9）

1. 首选 `BTDECK_MCP_FORCE_DISABLED=True` + 重启（最高优先级，UI 不可覆盖）。
2. 或认证设置 API 置 `enabled=false`（W1 后可用），立即阻断新调用。
3. 代码回滚前保留 `configs.mcp.runtime.v1`；旧版本忽略该键。
4. 敏感数据泄漏按安全事件处置：全局关闭 → 轮换疑似暴露 token/passkey →
   保留脱敏后审计 ID；不在工单/日志复制原始泄漏值。
5. W5 服务密钥疑似泄露：`POST /api/v1/mcp/apikey/rotate`（或设置页刷新）立即使
   旧密钥失效；`configs.mcp.apikey.v1` 行可随代码回滚废弃（旧版本忽略该键）。
   若 `security.secret_key` 已轮换：存量密钥密文不可解密 ⇒ 查看置 `unreadable`
   （认证仍有效），rotate 生成新密钥即自愈（key-rotation-runbook 第二节）。
5. 已提交的下载器/Cron 副作用不因关服自动回滚，按各领域既有审计与补偿流程处理。

## 8. 变更记录

- 2026-09-08 W0 初版：STRIDE 矩阵、现状缺口、prompt 注入面、门禁映射、回滚引用。
- 2026-09-22 W5：资产表补 MCP 服务密钥（可逆密文+哈希分离）；STRIDE 增 S3（密钥
  盗用/重放）与 E3（密钥泄露）；现状缺口增第 6 条（无角色约束）；回滚增密钥泄露
  处置与 secret_key 轮换联动。
