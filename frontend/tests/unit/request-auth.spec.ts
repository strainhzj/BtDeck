import { Message } from 'element-ui'
import { refreshAccessToken } from '@/api/users'
import { getRefreshToken, setRefreshToken, getUserId } from '@/utils/cookies'
import service, { redirectToLogin, trySilentRefresh } from '@/utils/request'
import { resetRefreshState } from '@/utils/token-refresh'
import { UserModule } from '@/store/modules/user'
import { AxiosAdapter, AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'

/**
 * 双密钥 401 链路回归（W6 伴随修复）：
 * - redirectToLogin：hash 模式跳转（redirect 携带 hash 内真实路由）、
 *   3 秒防抖窗口自动复位（跳转受挫后可自愈，不再永久吞 401）
 * - trySilentRefresh：无 refresh token / 刷新成功（轮换持久化）/ 刷新失败
 * - 401 拦截器集成（注入 axios adapter）：静默续期重放携带新 Bearer、
 *   重放仍 401 登出且不二次刷新（防循环）、无 refresh 直接登出、
 *   /auth/refresh 自身 401 豁免（不跳转不递归刷新）、HTTP 200 业务码 401 同链路
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

const mockRefresh = refreshAccessToken as jest.MockedFunction<typeof refreshAccessToken>
const mockSetRefreshToken = setRefreshToken as jest.MockedFunction<typeof setRefreshToken>
const mockMessage = Message as jest.MockedFunction<typeof Message>

// 后端 /auth/refresh 失效语义：HTTP 200 + code 401 + data null（类型上 data
// 声明为数组，此处用运行时真实形态断言）
const refreshFailEnvelope = {
  status: 'error',
  msg: '已撤销',
  code: '401',
  data: null
} as unknown as Awaited<ReturnType<typeof refreshAccessToken>>

/** 单调递增的假时钟：redirectToLogin 防抖用 Date.now()，跨用例必须越过 3 秒窗口 */
let clock = 1_700_000_000_000

const refreshSuccessEnvelope = {
  status: 'success',
  msg: '',
  code: '200',
  data: [
    { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer', user_id: 1 }
  ]
}

beforeEach(() => {
  jest.clearAllMocks()
  resetRefreshState()
  clock += 60_000
  jest.spyOn(Date, 'now').mockImplementation(() => clock)
  ;(getUserId as jest.Mock).mockReturnValue('')
  UserModule.ResetToken()
  window.location.hash = ''
})

afterEach(() => {
  jest.restoreAllMocks()
})

describe('redirectToLogin', () => {
  it('hash 模式跳转：redirect 携带 hash 内真实路由，清空 token 并给出过期提示', () => {
    UserModule.SetToken('stale-access')
    window.location.hash = '#/torrents?page=2'

    redirectToLogin()

    expect(mockMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'warning' }))
    expect(UserModule.token).toBe('')
    expect(window.location.hash).toBe(
      `#/login?redirect=${encodeURIComponent('/torrents?page=2')}`
    )
  })

  it('3 秒防抖窗口：窗口内重复触发只跳转一次，窗口过后可再次触发（自愈）', () => {
    window.location.hash = '#/dashboard'
    redirectToLogin()
    const firstHash = window.location.hash
    expect(firstHash).toBe(`#/login?redirect=${encodeURIComponent('/dashboard')}`)

    // 窗口内：并发的第二个 401 不再重复跳转
    clock += 1_000
    redirectToLogin()
    expect(window.location.hash).toBe(firstHash)

    // 窗口外：跳转能力恢复（此前永久标志会把它永久吞掉）
    clock += 2_001
    window.location.hash = '#/settings'
    redirectToLogin()
    expect(window.location.hash).toBe(`#/login?redirect=${encodeURIComponent('/settings')}`)
  })
})

describe('trySilentRefresh', () => {
  it('无 refresh token → false 且不发刷新请求', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('')

    await expect(trySilentRefresh()).resolves.toBe(false)
    expect(mockRefresh).not.toHaveBeenCalled()
  })

  it('刷新成功 → true，且新令牌对写入内存与 cookie（后端使用即轮换）', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('old-refresh')
    mockRefresh.mockResolvedValue(refreshSuccessEnvelope)
    UserModule.SetToken('expired-access')

    await expect(trySilentRefresh()).resolves.toBe(true)

    expect(mockRefresh).toHaveBeenCalledWith('old-refresh')
    expect(UserModule.token).toBe('new-access')
    expect(mockSetRefreshToken).toHaveBeenCalledWith('new-refresh')
  })

  it('刷新响应缺 access_token（HTTP 200 + code 401）→ false 交调用方登出', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('dead-refresh')
    mockRefresh.mockResolvedValue(refreshFailEnvelope)

    await expect(trySilentRefresh()).resolves.toBe(false)
  })

  it('刷新请求本身抛错（网络/断言失败）→ false 交调用方登出', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('old-refresh')
    mockRefresh.mockRejectedValue(new Error('network'))

    await expect(trySilentRefresh()).resolves.toBe(false)
  })
})

describe('401 拦截器集成（注入 axios adapter）', () => {
  const http = service as unknown as AxiosInstance
  let adapter: jest.Mock

  const envelope401 = { status: 'error', msg: 'token验证失败', code: '401', data: null }
  const envelope200 = { status: 'success', msg: 'ok', code: '200', data: { ok: true } }

  // 自定义 adapter 的响应必须携带真实 config：axios 不回填 response.config，
  // 丢掉 config 会同时丢 _retried 防循环标记与 isLoginRequest 豁免判定
  const respond = (status: number, data: unknown, config: AxiosRequestConfig): AxiosResponse => ({
    data,
    status,
    statusText: '',
    headers: {},
    config
  })

  const rejectWith401 = (config: AxiosRequestConfig): Promise<never> => {
    const response = respond(401, envelope401, config)
    return Promise.reject(
      Object.assign(new Error('Request failed with status code 401'), {
        config,
        response,
        isAxiosError: true
      })
    )
  }

  const authHeaderOf = (callIndex: number): string => {
    const cfg = adapter.mock.calls[callIndex][0] as AxiosRequestConfig
    return String((cfg.headers as Record<string, unknown>).Authorization)
  }

  beforeAll(() => {
    adapter = jest.fn()
    http.defaults.adapter = adapter as unknown as AxiosAdapter
  })

  const armRefreshSuccess = () => {
    (getRefreshToken as jest.Mock).mockReturnValue('old-refresh')
    mockRefresh.mockResolvedValue(refreshSuccessEnvelope)
  }

  it('HTTP 401（error 分支）：静默续期后重放一次，重放请求携带新 Bearer', async() => {
    armRefreshSuccess()
    UserModule.SetToken('expired-access')

    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => {
      if (adapter.mock.calls.length === 1) {
        return rejectWith401(cfg)
      }
      return respond(200, envelope200, cfg)
    })

    const res = await service({ url: '/torrents/list', method: 'get' })

    expect(adapter).toHaveBeenCalledTimes(2)
    expect(authHeaderOf(0)).toBe('Bearer expired-access')
    expect(authHeaderOf(1)).toBe('Bearer new-access')
    expect(mockRefresh).toHaveBeenCalledTimes(1)
    expect(res.code).toBe('200')
    expect(window.location.hash).toBe('')
  })

  it('HTTP 200 + 业务码 401（success 分支）：走同一静默续期链路', async() => {
    armRefreshSuccess()
    UserModule.SetToken('expired-access')

    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => {
      if (adapter.mock.calls.length === 1) {
        return respond(200, envelope401, cfg)
      }
      return respond(200, envelope200, cfg)
    })

    const res = await service({ url: '/torrents/list', method: 'get' })

    expect(adapter).toHaveBeenCalledTimes(2)
    expect(res.code).toBe('200')
  })

  it('重放仍 401：登出跳转且不二次刷新（防循环），redirect 保留当前路由', async() => {
    armRefreshSuccess()
    UserModule.SetToken('expired-access')
    window.location.hash = '#/torrents'

    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => rejectWith401(cfg))

    await expect(service({ url: '/torrents/list', method: 'get' })).rejects.toMatchObject({
      code: '401'
    })

    expect(adapter).toHaveBeenCalledTimes(2)
    expect(mockRefresh).toHaveBeenCalledTimes(1)
    expect(UserModule.token).toBe('')
    expect(window.location.hash).toBe(`#/login?redirect=${encodeURIComponent('/torrents')}`)
  })

  it('无 refresh token 的 401：不刷新不重放，直接登出跳转', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('')
    UserModule.SetToken('expired-access')

    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => rejectWith401(cfg))

    await expect(service({ url: '/dashboard/stats', method: 'get' })).rejects.toMatchObject({
      code: '401'
    })

    expect(mockRefresh).not.toHaveBeenCalled()
    expect(adapter).toHaveBeenCalledTimes(1)
    expect(UserModule.token).toBe('')
    expect(window.location.hash).toContain('#/login?redirect=')
  })

  it('/auth/refresh 自身 401：豁免续期与登出跳转（否则会形成递归/死循环）', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('old-refresh')
    UserModule.SetToken('intact-access')
    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => rejectWith401(cfg))

    await expect(service({ url: '/auth/refresh', method: 'post' })).rejects.toMatchObject({
      code: '401'
    })

    expect(mockRefresh).not.toHaveBeenCalled()
    expect(adapter).toHaveBeenCalledTimes(1)
    expect(window.location.hash).toBe('')
    expect(UserModule.token).toBe('intact-access')
  })
})
