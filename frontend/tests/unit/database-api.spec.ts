/**
 * 数据库迁移 API 契约回归（database-migration-ui W4-1）。
 *
 * 保护点：
 * 1. 各函数 URL/method/payload 序列化与后端 database.py 契约逐字段一致
 *    （动作组载荷 snake_case：attempt_id/epoch/state_version/ownership_nonce…）；
 * 2. 成功响应原样透传 ApiEnvelope（status/msg/code/data），组件按 data 体消费；
 * 3. 失败统一以 ApiError 拒绝（request 层归一化后直达调用方，无二次包装）。
 */

import request from '@/utils/request'
import type { ApiEnvelope } from '@/utils/request'
import {
  getDatabaseStatus,
  getMigrationStatus,
  getTargetReadiness,
  testConnection,
  startMigration,
  provideCredentials,
  cancelMigration,
  leaveMigration,
  discardTarget,
  switchDatabase,
  clearActivation,
  DatabaseStatusData,
  MigrationStatusData,
  ReadinessData,
  TestConnectionData,
  SwitchCommitData,
  DiscardTargetData,
  PgFormInput
} from '@/api/database'
import { ApiError } from '@/types/api'

jest.mock('@/utils/request', () => ({
  __esModule: true,
  default: jest.fn()
}))

const mockRequest = request as jest.MockedFunction<typeof request>

function envelope<T>(data: T, code = '200'): ApiEnvelope<T> {
  return { status: 'success', msg: 'ok', code, data }
}

const STATUS: DatabaseStatusData = {
  effective: {
    source: 'active',
    dialect: 'postgresql',
    sqlitePath: null,
    postgresql: {
      host: 'db.local',
      port: 5432,
      user: 'btdeck',
      database: 'btdeck',
      schema: 'public',
      sslmode: 'verify-full',
      sslRootCert: '/etc/ssl/ca.pem',
      poolSize: 10,
      maxOverflow: 20,
      poolTimeout: 30
    },
    generation: 'gen-1',
    expectedDatabaseId: 'db-uuid-1',
    receiptAttemptId: 'att-1'
  },
  control: { deploymentId: 'dep-1', generation: 'gen-1', restartPending: false },
  hosting: { hosting: 'docker', optIn: true, pid1Self: false, autoRestartCapable: true, hint: null }
}

const MIGRATION: MigrationStatusData = {
  attemptId: 'att-1',
  phase: 'importing',
  epoch: 'epoch-7',
  stateVersion: 3,
  commitPhase: null,
  workerGeneration: 2,
  needsCredentials: false,
  restartPending: false,
  detail: { progress: { phase: 'copy', done: 120, total: 300 }, target: { dialect: 'postgresql' } }
}

const READINESS: ReadinessData = {
  attemptId: 'att-1',
  phase: 'ready_to_switch',
  readyToSwitch: true,
  needsCredentials: false
}

const TEST_CONN: TestConnectionData = {
  dialect: 'postgresql',
  reachable: true,
  serverVersion: '16.4',
  versionOk: true,
  targetEmpty: true,
  sslmode: 'verify-full'
}

const SWITCH: SwitchCommitData = {
  prepared: {
    attemptId: 'att-1',
    mode: 'B',
    commitPhase: 'NONE',
    candidateDigest: 'sha256:aaa',
    priorDigest: 'sha256:bbb',
    restartPending: false
  },
  commit: {
    attemptId: 'att-1',
    mode: 'B',
    commitPhase: 'COMMITTED',
    generation: 'gen-2',
    configPublished: true,
    restartScheduled: true,
    restartHint: null
  }
}

const DISCARD: DiscardTargetData = {
  authorized: true,
  plan: { objects: 3, tables: ['t1', 't2'] },
  note: '授权核验通过；清理由维护流程在目标连接执行'
}

const PG_TARGET: PgFormInput = {
  host: 'db.local',
  port: 5433,
  user: 'btdeck',
  password: 'secret-pw',
  database: 'btdeck2',
  schema: 'public',
  sslmode: 'verify-ca',
  ssl_root_cert: '/etc/ssl/ca.pem',
  pool_size: 8,
  max_overflow: 10,
  pool_timeout: 15
}

beforeEach(() => {
  mockRequest.mockReset()
})

describe('database api：只读组', () => {
  it('getDatabaseStatus → GET /database/status 且信封原样透传', async() => {
    const env = envelope(STATUS)
    mockRequest.mockResolvedValue(env)
    await expect(getDatabaseStatus()).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledTimes(1)
    expect(mockRequest).toHaveBeenCalledWith({ url: '/database/status', method: 'get' })
  })

  it('getMigrationStatus → GET /database/migration/status', async() => {
    const env = envelope(MIGRATION)
    mockRequest.mockResolvedValue(env)
    await expect(getMigrationStatus()).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({ url: '/database/migration/status', method: 'get' })
  })

  it('getTargetReadiness → GET /database/target-readiness', async() => {
    const env = envelope(READINESS)
    mockRequest.mockResolvedValue(env)
    await expect(getTargetReadiness()).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({ url: '/database/target-readiness', method: 'get' })
  })
})

describe('database api：testConnection', () => {
  it('sqlite 载荷序列化 snake_case（sqlite_path）', async() => {
    const env = envelope<TestConnectionData>({ dialect: 'sqlite', reachable: true, writable: true })
    mockRequest.mockResolvedValue(env)
    await expect(
      testConnection({ dialect: 'sqlite', sqlite_path: '/srv/btdeck/data/btdeck.db' })
    ).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({
      url: '/database/test-connection',
      method: 'post',
      data: { dialect: 'sqlite', sqlite_path: '/srv/btdeck/data/btdeck.db' }
    })
  })

  it('postgresql 载荷完整透传 PgFormInput（含 ssl_root_cert/pool_*）', async() => {
    const env = envelope(TEST_CONN)
    mockRequest.mockResolvedValue(env)
    await expect(
      testConnection({ dialect: 'postgresql', postgresql: PG_TARGET })
    ).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({
      url: '/database/test-connection',
      method: 'post',
      data: { dialect: 'postgresql', postgresql: PG_TARGET }
    })
  })
})

describe('database api：动作组（snake_case CAS 载荷）', () => {
  it('startMigration → POST /database/migration/start（direction/target/password/source）', async() => {
    const env = envelope(MIGRATION)
    mockRequest.mockResolvedValue(env)
    const payload = {
      direction: 'sqlite-to-pg' as const,
      target: PG_TARGET,
      password: 'secret-pw',
      source: { dialect: 'sqlite', path: '/srv/btdeck/data/btdeck.db' }
    }
    await expect(startMigration(payload)).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({
      url: '/database/migration/start',
      method: 'post',
      data: payload
    })
  })

  it('provideCredentials → POST /database/migration/credentials（attempt_id/target）', async() => {
    const env = envelope(MIGRATION)
    mockRequest.mockResolvedValue(env)
    const payload = { attempt_id: 'att-1', password: 'secret-pw', target: PG_TARGET }
    await expect(provideCredentials(payload)).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({
      url: '/database/migration/credentials',
      method: 'post',
      data: payload
    })
  })

  it('cancelMigration → POST /database/migration/cancel（CAS + reason）', async() => {
    const env = envelope(MIGRATION)
    mockRequest.mockResolvedValue(env)
    const payload = { attempt_id: 'att-1', epoch: 'epoch-7', state_version: 3, reason: '用户取消' }
    await expect(cancelMigration(payload)).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({
      url: '/database/migration/cancel',
      method: 'post',
      data: payload
    })
  })

  it('leaveMigration → POST /database/migration/leave（CAS；reason 缺省不注入键）', async() => {
    const env = envelope(MIGRATION)
    mockRequest.mockResolvedValue(env)
    await expect(
      leaveMigration({ attempt_id: 'att-1', epoch: 'epoch-7', state_version: 3 })
    ).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({
      url: '/database/migration/leave',
      method: 'post',
      data: { attempt_id: 'att-1', epoch: 'epoch-7', state_version: 3 }
    })
  })

  it('discardTarget → POST /database/migration/discard-target（ownership 双确认四元组）', async() => {
    const env = envelope(DISCARD)
    mockRequest.mockResolvedValue(env)
    const payload = {
      attempt_id: 'att-1',
      ownership_nonce: 'nonce-abc',
      database_id: 'db-uuid-1',
      confirm_token: 'confirm-token-xyz'
    }
    await expect(discardTarget(payload)).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({
      url: '/database/migration/discard-target',
      method: 'post',
      data: payload
    })
  })

  it('switchDatabase → POST /database/migration/switch（CAS + mode）', async() => {
    const env = envelope(SWITCH)
    mockRequest.mockResolvedValue(env)
    const payload = { attempt_id: 'att-1', epoch: 'epoch-7', state_version: 3, mode: 'B' as const }
    await expect(switchDatabase(payload)).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({
      url: '/database/migration/switch',
      method: 'post',
      data: payload
    })
  })

  it('clearActivation → POST /database/activation/clear（CAS）', async() => {
    const plan = { kind: 'HANDOFF_SAME_DB', handoffAttemptId: 'handoff/uuid-1' }
    const env = envelope<Record<string, unknown>>(plan)
    mockRequest.mockResolvedValue(env)
    const payload = { attempt_id: 'att-1', epoch: 'epoch-7', state_version: 3 }
    await expect(clearActivation(payload)).resolves.toBe(env)
    expect(mockRequest).toHaveBeenCalledWith({
      url: '/database/activation/clear',
      method: 'post',
      data: payload
    })
  })
})

describe('database api：错误通道', () => {
  it('request 层 ApiError 原样拒绝（统一 ApiError，无二次包装）', async() => {
    const conflict = new ApiError('状态冲突：已有迁移在进行', { code: '409', httpStatus: 409 })
    const unauthorized = new ApiError('token验证失败', { code: '401', httpStatus: 200 })
    mockRequest.mockRejectedValueOnce(conflict)
    await expect(startMigration({ direction: 'sqlite-to-pg', target: PG_TARGET, password: 'x' }))
      .rejects.toBe(conflict)
    mockRequest.mockRejectedValueOnce(unauthorized)
    await expect(getDatabaseStatus()).rejects.toBe(unauthorized)
  })

  it('部分成功/受理信封（207/202）同样原样透传，由组件分支消费', async() => {
    const partial = envelope<MigrationStatusData>(MIGRATION, '207')
    mockRequest.mockResolvedValue(partial)
    await expect(provideCredentials({ attempt_id: 'att-1', password: 'x', target: PG_TARGET }))
      .resolves.toBe(partial)
  })
})
