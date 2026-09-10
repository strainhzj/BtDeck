import { Message } from 'element-ui'
import service from '@/utils/request'
import { AxiosAdapter, AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'

/**
 * 幂等 GET 瞬态失败自动重试（mobile-ux-fixes 2026-09）回归：
 * - GET 网络错误 / 502/503/504 → 静默重试一次：首次失败不弹 toast，重试成功
 *   调用方无感拿到 200 信封
 * - 重试用尽仍失败 → 才走网络错误节流 toast（一次）
 * - POST 不重试、超时（ECONNABORTED）不重试、404 等确定性失败不重试
 * 集成方式与 request-auth.spec 相同：注入 axios adapter 构造失败/成功序列。
 */

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
  getUserId: jest.fn(() => ''),
  setUserId: jest.fn(),
  removeUserId: jest.fn(),
  getStorage: jest.fn(),
  setStorage: jest.fn()
}))

const mockMessage = Message as jest.MockedFunction<typeof Message>

describe('幂等 GET 瞬态失败重试（注入 axios adapter）', () => {
  const http = service as unknown as AxiosInstance
  let adapter: jest.Mock

  const envelope200 = { status: 'success', msg: 'ok', code: '200', data: { ok: true } }

  // 自定义 adapter 的响应必须携带真实 config：axios 不回填 response.config，
  // 丢 config 会同时丢 _transientRetried 防循环标记
  const respond = (status: number, data: unknown, config: AxiosRequestConfig): AxiosResponse => ({
    data,
    status,
    statusText: '',
    headers: {},
    config
  })

  const rejectWithStatus = (status: number, config: AxiosRequestConfig): Promise<never> => {
    const response = respond(status, {}, config)
    return Promise.reject(
      Object.assign(new Error(`Request failed with status code ${status}`), {
        config,
        response,
        isAxiosError: true
      })
    )
  }

  const rejectWithNetworkError = (config: AxiosRequestConfig): Promise<never> =>
    Promise.reject(
      Object.assign(new Error('Network Error'), {
        config,
        request: {},
        isAxiosError: true
      })
    )

  const rejectWithTimeout = (config: AxiosRequestConfig): Promise<never> =>
    Promise.reject(
      Object.assign(new Error('timeout of 20000ms exceeded'), {
        config,
        request: {},
        code: 'ECONNABORTED',
        isAxiosError: true
      })
    )

  beforeAll(() => {
    adapter = jest.fn()
    http.defaults.adapter = adapter as unknown as AxiosAdapter
  })

  beforeEach(() => {
    adapter.mockReset()
    mockMessage.mockClear()
  })

  it('GET 503：静默重试一次成功——不弹 toast，调用方拿到 200 信封', async() => {
    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => {
      if (adapter.mock.calls.length === 1) {
        return rejectWithStatus(503, cfg)
      }
      return respond(200, envelope200, cfg)
    })

    const res = await service({ url: '/torrents/getList', method: 'get' })

    expect(adapter).toHaveBeenCalledTimes(2)
    expect(res.code).toBe('200')
    expect(mockMessage).not.toHaveBeenCalled()
  })

  it('GET 网络错误（无响应）：重试一次成功——不弹 toast', async() => {
    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => {
      if (adapter.mock.calls.length === 1) {
        return rejectWithNetworkError(cfg)
      }
      return respond(200, envelope200, cfg)
    })

    const res = await service({ url: '/torrents/active-torrents', method: 'get' })

    expect(adapter).toHaveBeenCalledTimes(2)
    expect(res.code).toBe('200')
    expect(mockMessage).not.toHaveBeenCalled()
  })

  it('GET 网络错误重试用尽：以网络错误拒绝且只弹一次节流 toast', async() => {
    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => rejectWithNetworkError(cfg))

    await expect(service({ url: '/torrents/getList', method: 'get' })).rejects.toMatchObject({
      code: '0'
    })

    // 首次失败静默 + 重试失败归一化 → toast 只在最终失败后弹一次
    expect(adapter).toHaveBeenCalledTimes(2)
    expect(mockMessage).toHaveBeenCalledTimes(1)
  })

  it('POST 503：写操作绝不重试', async() => {
    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => rejectWithStatus(503, cfg))

    await expect(service({ url: '/torrents/duplicates', method: 'post', data: {} })).rejects.toBeTruthy()

    expect(adapter).toHaveBeenCalledTimes(1)
  })

  it('GET 超时（ECONNABORTED）：不重试（20s 已过长，重试只会翻倍等待）', async() => {
    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => rejectWithTimeout(cfg))

    await expect(service({ url: '/torrents/getList', method: 'get' })).rejects.toBeTruthy()

    // 只验证不重试；toast 次数不断言——上一用例刚以同文案弹过节流 toast（3s 窗口）
    expect(adapter).toHaveBeenCalledTimes(1)
  })

  it('GET 404：确定性失败不重试', async() => {
    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => rejectWithStatus(404, cfg))

    await expect(service({ url: '/torrents/not-exist', method: 'get' })).rejects.toBeTruthy()

    expect(adapter).toHaveBeenCalledTimes(1)
  })
})
