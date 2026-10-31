import request from '@/utils/request'
import type { ApiEnvelope } from '@/utils/request'

/**
 * 数据库迁移控制面 API（database-migration-ui W4-1）。
 *
 * 后端契约（backend/app/api/endpoints/database.py，PLANS §8）：
 * - 所有端点挂 `/api/v1/database` 前缀，响应为统一 CommonResponse 信封；
 * - 普通态=普通管理员认证；维护态=维护 token（见 utils/maintenance-client.ts，
 *   维护页内的调用方应改走维护通道注入 Bearer）；
 * - 动作组载荷字段为 snake_case（attempt_id/epoch/state_version 等），
 *   与后端 Pydantic 模型逐字段对齐；
 * - CAS 冲突（状态被并发修改）后端返回 HTTP 409 → ApiError.code === '409'，
 *   组件侧应提示并重新拉取 /migration/status。
 */

/** 数据库方言（后端 test-connection/start 契约仅接受这两个字面量） */
export type DatabaseDialect = 'sqlite' | 'postgresql'

/** 迁移方向（后端 pattern ^(sqlite-to-pg|pg-to-sqlite)$） */
export type MigrationDirection = 'sqlite-to-pg' | 'pg-to-sqlite'

/** 切换提交模式（§7：A=同库交接引导 / B=发布受管配置并重启） */
export type SwitchMode = 'A' | 'B'

/** PG 连接参数（脱敏视图；状态接口下发，无密码字段） */
export interface PgMasked {
  host: string
  port: number
  user: string
  database: string
  schema: string
  sslmode: string
  sslRootCert: string | null
  poolSize: number
  maxOverflow: number
  poolTimeout: number
}

/** 当前生效数据库配置摘要（§9：展示有效实况，不把 env 当实况） */
export interface EffectiveSummary {
  /** 配置来源：active（受管）| env */
  source: string
  dialect: string
  sqlitePath: string | null
  postgresql: PgMasked | null
  generation: string | null
  expectedDatabaseId: string | null
  receiptAttemptId: string | null
}

/** 受管控制面摘要（journal control 节；无受管配置时整体为 null） */
export interface DatabaseControlSummary {
  deploymentId?: string | null
  generation?: string | null
  restartPending: boolean
}

/** 托管重启能力探测（restart_adapter.hosting_capability()） */
export interface HostingCapabilityData {
  hosting: string
  optIn: boolean
  pid1Self: boolean
  autoRestartCapable: boolean
  /** 结构化提示码（P7 V01-F01：前端按码本地化；capable 时为 null） */
  hintCode?: string | null
  /** 后端中文原文，仅作 hintCode 未覆盖时的回退展示 */
  hint: string | null
}

/** GET /database/status 数据体 */
export interface DatabaseStatusData {
  effective: EffectiveSummary
  control: DatabaseControlSummary | null
  hosting: HostingCapabilityData
}

/** 管线进度（IMPORTING/VERIFYING 等阶段的 {phase, done, total}） */
export interface MigrationProgress {
  phase: string
  done: number
  total: number
}

/** GET /migration/status 数据体（manager.status().as_dict()；脱敏，无凭据） */
export interface MigrationStatusData {
  attemptId: string | null
  /** idle|preparing|draining|frozen|importing|verifying|ready_to_switch|cancelling|cancelled|failed|held|committed */
  phase: string
  epoch: string
  stateVersion: number
  commitPhase: string | null
  workerGeneration: number
  needsCredentials: boolean
  restartPending: boolean
  detail?: {
    progress?: MigrationProgress
    /** 目标摘要（manifest 视图；结构随后端版本演进，收敛为宽类型） */
    target?: Record<string, unknown>
  }
}

/** GET /target-readiness 数据体（只读就绪面；switch 前全量复核仍在管理器） */
export interface ReadinessData {
  attemptId: string | null
  phase: string
  readyToSwitch: boolean
  needsCredentials: boolean
}

/** POST /test-connection 数据体（探测结果三态由字段组合表达） */
export interface TestConnectionData {
  dialect: string
  reachable: boolean
  /** PG 探测下发（如 16.4）；SQLite 探测不下发 */
  serverVersion?: string
  /** PG major >= 16 */
  versionOk?: boolean
  /** PG 目标 schema 是否为空库 */
  targetEmpty?: boolean
  /** PG 实际协商出的 TLS 档位 */
  sslmode?: string
  /** SQLite 目标父目录可写性 */
  writable?: boolean
}

/** §7.2 prepare_switch 结果（switch 响应 data.prepared） */
export interface SwitchPreparedData {
  attemptId: string
  mode: string
  commitPhase: string
  candidateDigest: string
  priorDigest: string
  restartPending: boolean
}

/** §7.2 commit_switch 结果（switch 响应 data.commit） */
export interface SwitchCommitResultData {
  attemptId: string
  mode: string
  commitPhase: string
  generation: string
  configPublished: boolean
  restartScheduled: boolean
  restartHint: string | null
}

/** POST /migration/switch 数据体（prepared + commit 两段一次下发） */
export interface SwitchCommitData {
  prepared: SwitchPreparedData
  commit: SwitchCommitResultData
}

/** POST /migration/discard-target 数据体（§6.5 授权+计划；实际清理由维护流程执行） */
export interface DiscardTargetData {
  authorized: boolean
  plan: Record<string, unknown>
  note: string
}

/**
 * PG 目标表单输入（snake_case 与后端 pg_params_from_mapping 契约一致）。
 * 必填五项 + 可选项（缺省由后端补全：public/prefer/10/20/30）。
 */
export interface PgFormInput {
  host: string
  port: number
  user: string
  password: string
  database: string
  schema?: string
  /** 五档 TLS：disable|allow|prefer|require|verify-ca|verify-full */
  sslmode?: string
  /** verify-ca/verify-full 必填（CA 证书路径） */
  ssl_root_cert?: string | null
  pool_size?: number
  max_overflow?: number
  pool_timeout?: number
}

/** POST /test-connection 载荷（显式目标；不建 schema、不保存密码） */
export interface TestConnectionPayload {
  dialect: DatabaseDialect
  sqlite_path?: string
  postgresql?: PgFormInput
}

/** POST /migration/start 载荷（单飞行；source 为源描述可选节） */
export interface MigrationStartPayload {
  direction: MigrationDirection
  target: PgFormInput
  password: string
  source?: Record<string, unknown>
}

/** POST /migration/credentials 载荷（NEEDS_CREDENTIALS 恢复；只收绑定目标凭据） */
export interface CredentialsPayload {
  attempt_id: string
  password: string
  target: PgFormInput
}

/** 维护态 CAS 前提（cancel/leave/switch/clear 共用；后端 CasRequest） */
export interface MigrationCasPayload {
  attempt_id: string
  epoch: string
  state_version: number
  reason?: string
}

/** POST /migration/discard-target 载荷（§6.5 ownership + 双确认） */
export interface DiscardTargetPayload {
  attempt_id: string
  ownership_nonce: string
  database_id: string
  confirm_token: string
}

/** POST /migration/switch 载荷（CAS + mode） */
export interface SwitchPayload extends MigrationCasPayload {
  mode: SwitchMode
}

/** 当前有效库/配置来源/托管能力（脱敏） */
export function getDatabaseStatus(): Promise<ApiEnvelope<DatabaseStatusData>> {
  return request<ApiEnvelope<DatabaseStatusData>>({
    url: '/database/status',
    method: 'get'
  })
}

/** attempt/phase/epoch/stateVersion/可用动作（不含凭据） */
export function getMigrationStatus(): Promise<ApiEnvelope<MigrationStatusData>> {
  return request<ApiEnvelope<MigrationStatusData>>({
    url: '/database/migration/status',
    method: 'get'
  })
}

/** 只读就绪面（readyToSwitch 不构成 switch 的越权凭据） */
export function getTargetReadiness(): Promise<ApiEnvelope<ReadinessData>> {
  return request<ApiEnvelope<ReadinessData>>({
    url: '/database/target-readiness',
    method: 'get'
  })
}

/** 显式目标连通/版本/TLS/权限探测（只读；PG16+ / 目标空库 / SQLite 可写） */
export function testConnection(payload: TestConnectionPayload): Promise<ApiEnvelope<TestConnectionData>> {
  return request<ApiEnvelope<TestConnectionData>>({
    url: '/database/test-connection',
    method: 'post',
    data: payload
  })
}

/** 发起迁移（关准入→排空→冻结→快照；冲突 ApiError.code === '409'） */
export function startMigration(payload: MigrationStartPayload): Promise<ApiEnvelope<MigrationStatusData>> {
  return request<ApiEnvelope<MigrationStatusData>>({
    url: '/database/migration/start',
    method: 'post',
    data: payload
  })
}

/** NEEDS_CREDENTIALS 恢复：重输绑定目标凭据（不临时换目标） */
export function provideCredentials(payload: CredentialsPayload): Promise<ApiEnvelope<MigrationStatusData>> {
  return request<ApiEnvelope<MigrationStatusData>>({
    url: '/database/migration/credentials',
    method: 'post',
    data: payload
  })
}

/** 请求协作取消（先 CANCELLING，worker ACK 前不报 CANCELLED） */
export function cancelMigration(payload: MigrationCasPayload): Promise<ApiEnvelope<MigrationStatusData>> {
  return request<ApiEnvelope<MigrationStatusData>>({
    url: '/database/migration/cancel',
    method: 'post',
    data: payload
  })
}

/** 安全放弃回源（须已安全停止且未 COMMITTED；先撤销资格+推进 epoch） */
export function leaveMigration(payload: MigrationCasPayload): Promise<ApiEnvelope<MigrationStatusData>> {
  return request<ApiEnvelope<MigrationStatusData>>({
    url: '/database/migration/leave',
    method: 'post',
    data: payload
  })
}

/** §6.5 目标清理授权（ownership_nonce + confirm_token 双确认；返回授权计划） */
export function discardTarget(payload: DiscardTargetPayload): Promise<ApiEnvelope<DiscardTargetData>> {
  return request<ApiEnvelope<DiscardTargetData>>({
    url: '/database/migration/discard-target',
    method: 'post',
    data: payload
  })
}

/** §7.2 提交切换（PREPARED→COMMITTED→发布→RESTART_PENDING；幂等） */
export function switchDatabase(payload: SwitchPayload): Promise<ApiEnvelope<SwitchCommitData>> {
  return request<ApiEnvelope<SwitchCommitData>>({
    url: '/database/migration/switch',
    method: 'post',
    data: payload
  })
}

/**
 * §7.3 同库受控交接（HANDOFF_SAME_DB 计划；异库目标拒绝——引导新迁移）。
 * 计划结构（kind/handoffAttemptId/currentActive/steps/confirmToken…）随后端
 * 版本演进，收敛为 Record<string, unknown>，字段消费由 W4 组件按需收窄。
 */
export function clearActivation(payload: MigrationCasPayload): Promise<ApiEnvelope<Record<string, unknown>>> {
  return request<ApiEnvelope<Record<string, unknown>>>({
    url: '/database/activation/clear',
    method: 'post',
    data: payload
  })
}
