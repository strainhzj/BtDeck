/**
 * 维护独立通道回归（database-migration-ui W4-1，PLANS §11 T21）。
 *
 * 保护点：
 * 1. 独立 axios 实例：不经过 request.ts 拦截器（mock axios.create 验证请求
 *    只走 create 返回的实例），无共享 token 注入；
 * 2. 维护 token 仅内存：登录后不落 localStorage/sessionStorage、不进 URL；
 * 3. 401（HTTP 与业务码两种形态）派发订阅回调、退订生效；不跳转登录页、
 *    不触发普通会话注销/refresh（refreshAccessToken/cookie 写零调用）、不弹 toast；
 * 4. 503 静默：单次请求（无重试）、无 toast、以 ApiError 拒绝；
 * 5. /maintenance/status 宽松映射：已知字段收敛、未知字段进 extra。
 */

import axios from 'axios'
import { Message } from 'element-ui'
import { refreshAccessToken } from '@/api/users'
import {
  setToken,
  removeToken,
  setRefreshToken,
  removeRefreshToken
} from '@/utils/cookies'
import {
  maintenanceLogin,
  maintenanceRequest,
  getMaintenanceStatus,
  subscribeAuthExpired,
  clearMaintenanceToken,
  getMaintenanceToken,
  mapMaintenanceStatusData,
  MaintenanceAuthData
} from '@/utils/maintenance-client'
import { ApiError } from '@/types/api'

/**
 * axios.create 的 mock：工厂内闭包构造实例（避免模块导入期 TDZ），
 * 经 default 导出的附加属性 __instance 暴露给测试（单实例：模块级
 * create 结果即通道实例）。
 */
jest.mock('axios', () => {
  const request = jest.fn()
  const instance = { request }
  const create = jest.fn(() => instance)
  return { __esModule: true, default: { create, __instance: instance } }
})

jest.mock('element-ui', () => ({ Message: jest.fn() }))

jest.mock('@/api/users', () => ({
  login: jest.fn(),
  logout: jest.fn(),
  getUserInfo: jest.fn(),
  refreshAccessToken: jest.fn(),
  changePassword: jest.fn()
}))

jest.mock('@/utils/cookies', () => ({
  getToken: jest.fn(),
  setToken: jest.fn(),
  removeToken: jest.fn(),
  getRefreshToken: jest.fn(),
  setRefreshToken: jest.fn(),
  removeRefreshToken: jest.fn(),
  getUserId: jest.fn(),
  setUserId: jest.fn(),
  removeUserId: jest.fn(),
  getStorage: jest.fn(),
  setStorage: jest.fn()
}))

interface MockAxiosStatic {
  create: jest.Mock
  __instance: { request: jest.Mock }
}

const mockAxios = axios as unknown as MockAxiosStatic
const mockRequest = mockAxios.__instance.request
const mockRefresh = refreshAccessToken as jest.MockedFunction<typeof refreshAccessToken>
const mockSetToken = setToken as jest.MockedFunction<typeof setToken>
const mockRemoveToken = removeToken as jest.MockedFunction<typeof removeToken>
const mockSetRefreshToken = setRefreshToken as jest.MockedFunction<typeof setRefreshToken>
const mockRemoveRefreshToken = removeRefreshToken as jest.MockedFunction<typeof removeRefreshToken>
const mockMessage = Message as jest.MockedFunction<typeof Message>

function envelope<T>(data: T, code = '200'): { status: string, msg: string, code: string, data: T } {
  return { status: 'success', msg: 'ok', code, data }
}

function httpError(status: number, data?: unknown): {
  response: { status: number, data: unknown }
  request: unknown
  message: string
} {
  return {
    response: { status, data: data ?? { status: 'error', msg: 'err', code: String(status) } },
    request: {},
    message: `Request failed with status code ${status}`
  }
}

function httpOk<T>(data: T): { data: unknown, status: number } {
  return { data: envelope(data), status: 200 }
}

/** 清空浏览器持久化存储，验证"token 仅内存"时排除用例间噪声 */
function clearWebStorage(): void {
  window.localStorage.clear()
  window.sessionStorage.clear()
}

beforeEach(() => {
  mockRequest.mockReset()
  // 注意：不清 create 调用记录——通道实例在模块导入期创建（仅一次），
  // beforeEach 里 mockClear 会抹掉该记录导致"create 调用一次"断言失效
  mockRefresh.mockReset()
  mockMessage.mockReset()
  clearMaintenanceToken()
  clearWebStorage()
})

describe('独立 axios 实例', () => {
  it('通道实例由 axios.create 创建，且所有请求仅走该实例', async() => {
    expect(mockAxios.create).toHaveBeenCalledTimes(1)
    mockRequest.mockResolvedValue(httpOk({ state: 'FROZEN' }))
    await getMaintenanceStatus()
    expect(mockRequest).toHaveBeenCalledTimes(1)
    const config = mockRequest.mock.calls[0][0] as { url: string, method: string }
    expect(config.url).toBe('/maintenance/status')
    expect(config.method).toBe('get')
  })
})

describe('maintenanceLogin', () => {
  it('POST /maintenance/auth（username/password/twofa_code）并内存持有 token', async() => {
    const auth: MaintenanceAuthData = { maintenanceToken: 'mt-abc-123', tokenType: 'bearer', expiresIn: 300 }
    mockRequest.mockResolvedValue(httpOk(auth))
    await expect(maintenanceLogin('admin', 'pw', '654321')).resolves.toEqual(auth)

    const loginConfig = mockRequest.mock.calls[0][0] as {
      url: string
      method: string
      data: Record<string, unknown>
      headers?: Record<string, string>
    }
    expect(loginConfig.url).toBe('/maintenance/auth')
    expect(loginConfig.method).toBe('post')
    expect(loginConfig.data).toEqual({ username: 'admin', password: 'pw', twofa_code: '654321' })
    // 登录前无维护 token：不注入 Authorization
    expect(loginConfig.headers?.Authorization).toBeUndefined()
    expect(getMaintenanceToken()).toBe('mt-abc-123')
  })

  it('twofa 缺省序列化为 null（后端 Optional 契约）', async() => {
    mockRequest.mockResolvedValue(httpOk({ maintenanceToken: 'mt-1', tokenType: 'bearer', expiresIn: 60 }))
    await maintenanceLogin('admin', 'pw')
    const config = mockRequest.mock.calls[0][0] as { data: { twofa_code: string | null } }
    expect(config.data.twofa_code).toBeNull()
  })

  it('凭据错误（业务 401）以 ApiError 拒绝：不派发 auth expired、不写 token', async() => {
    const expired = jest.fn()
    const unsub = subscribeAuthExpired(expired)
    try {
      mockRequest.mockResolvedValue({
        status: 200,
        data: {
          status: 'error',
          msg: 'maintenance auth failed',
          code: '401',
          data: { reasonCode: 'MAINTENANCE_AUTH_INVALID' }
        }
      })
      await expect(maintenanceLogin('admin', 'bad')).rejects.toBeInstanceOf(ApiError)
      expect(expired).not.toHaveBeenCalled()
      expect(getMaintenanceToken()).toBeNull()
    } finally {
      unsub()
    }
  })

  it('token 仅内存：登录成功后不落 localStorage/sessionStorage、不进 URL', async() => {
    const hrefBefore = window.location.href
    const tokenValue = 'mt-only-memory-xyz'
    mockRequest.mockResolvedValue(httpOk({ maintenanceToken: tokenValue, tokenType: 'bearer', expiresIn: 300 }))
    await maintenanceLogin('admin', 'pw')

    const persisted = [
      ...Object.entries(window.localStorage),
      ...Object.entries(window.sessionStorage)
    ]
    expect(persisted).toHaveLength(0)
    expect(window.location.href).toBe(hrefBefore)
    expect(window.location.search).not.toContain(tokenValue)
    expect(window.location.hash).not.toContain(tokenValue)
  })
})

describe('maintenanceRequest：认证注入', () => {
  it('无 token 时不注入 Authorization 头', async() => {
    mockRequest.mockResolvedValue(httpOk({ ok: true }))
    await maintenanceRequest('post', '/maintenance/probe', { a: 1 })
    const config = mockRequest.mock.calls[0][0] as { headers: Record<string, string>, data: unknown }
    expect(config.headers).toEqual({})
  })

  it('登录后注入 Authorization: Bearer <maintenanceToken>，数据体原样透传', async() => {
    mockRequest.mockResolvedValueOnce(httpOk({ maintenanceToken: 'mt-bearer-1', tokenType: 'bearer', expiresIn: 60 }))
    await maintenanceLogin('admin', 'pw')

    mockRequest.mockResolvedValueOnce(httpOk({ state: 'DRAINING' }))
    await maintenanceRequest('post', '/database/migration/status', { ping: true })
    const config = mockRequest.mock.calls[1][0] as { headers: Record<string, string>, data: unknown }
    expect(config.headers).toEqual({ Authorization: 'Bearer mt-bearer-1' })
    expect(config.data).toEqual({ ping: true })
  })

  it('信封解包：成功返回 data 体（而非整个信封）', async() => {
    mockRequest.mockResolvedValue(httpOk({ value: 42 }))
    await expect(maintenanceRequest<{ value: number }>('get', '/maintenance/probe')).resolves.toEqual({ value: 42 })
  })

  it('业务错误（HTTP 200 + code 409）以 ApiError 拒绝', async() => {
    mockRequest.mockResolvedValue({
      status: 200,
      data: { status: 'error', msg: 'not in maintenance mode', code: '409', data: { reasonCode: 'NOT_MAINTENANCE' } }
    })
    const err = await maintenanceRequest('get', '/maintenance/status').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('409')
    expect((err as ApiError).msg).toBe('not in maintenance mode')
  })
})

describe('401：订阅派发与普通会话零触碰', () => {
  it('HTTP 401 → 派发全部在册订阅；退订方不再收到', async() => {
    const calls: string[] = []
    const unsubA = subscribeAuthExpired(() => calls.push('a'))
    subscribeAuthExpired(() => calls.push('b'))
    try {
      mockRequest.mockRejectedValueOnce(httpError(401, {
        status: 'error', msg: 'maintenance token invalid', code: '401', data: { reasonCode: 'MAINTENANCE_TOKEN_INVALID' }
      }))
      await expect(maintenanceRequest('get', '/maintenance/status')).rejects.toBeInstanceOf(ApiError)
      expect(calls).toEqual(['a', 'b'])

      unsubA()
      calls.length = 0
      mockRequest.mockRejectedValueOnce(httpError(401))
      await expect(maintenanceRequest('get', '/maintenance/status')).rejects.toBeInstanceOf(ApiError)
      expect(calls).toEqual(['b'])
    } finally {
      unsubA()
    }
  })

  it('业务码 401（HTTP 200 信封）同样派发订阅', async() => {
    const expired = jest.fn()
    const unsub = subscribeAuthExpired(expired)
    try {
      mockRequest.mockResolvedValue({
        status: 200,
        data: { status: 'error', msg: 'maintenance token invalid', code: '401', data: null }
      })
      await expect(maintenanceRequest('get', '/maintenance/status')).rejects.toBeInstanceOf(ApiError)
      expect(expired).toHaveBeenCalledTimes(1)
    } finally {
      unsub()
    }
  })

  it('401 后不刷新令牌、不清普通会话、不跳转、不弹 toast', async() => {
    const hrefBefore = window.location.href
    const expired = jest.fn()
    const unsub = subscribeAuthExpired(expired)
    try {
      mockRequest.mockRejectedValueOnce(httpError(401))
      await expect(maintenanceRequest('get', '/maintenance/status')).rejects.toBeInstanceOf(ApiError)

      expect(mockRefresh).not.toHaveBeenCalled()
      expect(mockSetToken).not.toHaveBeenCalled()
      expect(mockRemoveToken).not.toHaveBeenCalled()
      expect(mockSetRefreshToken).not.toHaveBeenCalled()
      expect(mockRemoveRefreshToken).not.toHaveBeenCalled()
      expect(mockMessage).not.toHaveBeenCalled()
      expect(window.location.href).toBe(hrefBefore)
    } finally {
      unsub()
    }
  })
})

describe('503 与网络错误：静默通道', () => {
  it('503 单次请求即拒（无重试）、无 toast、ApiError.code === 503', async() => {
    mockRequest.mockRejectedValue(httpError(503, {
      status: 'error', msg: 'maintenance barrier', code: '503', data: { reasonCode: 'IN_MAINTENANCE' }
    }))
    const err = await maintenanceRequest('get', '/maintenance/status').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('503')
    expect((err as ApiError).httpStatus).toBe(503)
    expect(mockRequest).toHaveBeenCalledTimes(1)
    expect(mockMessage).not.toHaveBeenCalled()
  })

  it('网络层错误（无响应）归一化 code 0，同样静默', async() => {
    mockRequest.mockRejectedValue({ request: {}, message: 'Network Error' })
    const err = await maintenanceRequest('get', '/maintenance/status').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('0')
    expect((err as ApiError).httpStatus).toBe(0)
    expect(mockMessage).not.toHaveBeenCalled()
    expect(mockRequest).toHaveBeenCalledTimes(1)
  })
})

describe('getMaintenanceStatus：宽松映射', () => {
  it('已知字段收敛、后端扩展字段（heldReason/activeLeases/…）进 extra', async() => {
    mockRequest.mockResolvedValue(httpOk({
      state: 'FROZEN',
      heldReason: 'migration',
      attemptId: 'att-9',
      activeLeases: 2,
      cancelRequested: false,
      bootRecovery: null
    }))
    const status = await getMaintenanceStatus()
    expect(status).toEqual({
      reasonCode: undefined,
      state: 'FROZEN',
      attemptId: 'att-9',
      epoch: undefined,
      extra: {
        heldReason: 'migration',
        activeLeases: 2,
        cancelRequested: false,
        bootRecovery: null
      }
    })
  })

  it('携带 Bearer 与 GET /maintenance/status；reasonCode 纯映射可复用于错误载荷', async() => {
    mockRequest.mockResolvedValueOnce(httpOk({ maintenanceToken: 'mt-map', tokenType: 'bearer', expiresIn: 60 }))
    await maintenanceLogin('admin', 'pw')

    mockRequest.mockResolvedValueOnce(httpOk({ state: 'PREPARING', attemptId: 'att-1', epoch: 'epoch-1' }))
    const status = await getMaintenanceStatus()
    expect(status.state).toBe('PREPARING')
    expect(status.epoch).toBe('epoch-1')
    const config = mockRequest.mock.calls[1][0] as { url: string, method: string, headers: Record<string, string> }
    expect(config.url).toBe('/maintenance/status')
    expect(config.method).toBe('get')
    expect(config.headers['Authorization']).toBe('Bearer mt-map')

    // 错误载荷形态（reasonCode 缺省可选）同样可映射
    const mapped = mapMaintenanceStatusData({ reasonCode: 'NOT_MAINTENANCE', state: 'IDLE' })
    expect(mapped.reasonCode).toBe('NOT_MAINTENANCE')
    expect(mapped.extra).toEqual({})
  })
})
