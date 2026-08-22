import { Message } from 'element-ui'
import { refreshAccessToken } from '@/api/users'
import { getRefreshToken, setRefreshToken, getUserId, removeRefreshToken, removeToken } from '@/utils/cookies'
import service, { redirectToLogin, trySilentRefresh } from '@/utils/request'
import { resetRefreshState } from '@/utils/token-refresh'
import { UserModule } from '@/store/modules/user'
import { ApiError } from '@/types/api'
import { AxiosAdapter, AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'

/**
 * 双密钥 401 链路回归（W6 伴随修复 + 跨标签竞态修复）：
 * - redirectToLogin：hash 模式跳转（redirect 携带 hash 内真实路由）、
 *   3 秒防抖窗口自动复位（跳转受挫后可自愈，不再永久吞 401）、
 *   ExpireSession 语义（清 access 不清共享 refresh cookie）
 * - trySilentRefresh 三态：无 refresh token→rejected / 刷新成功（轮换持久化）→renewed /
 *   业务码 401→rejected / 网络错误（ApiError code '0'）→transient
 * - 401 拦截器集成（注入 axios adapter）：静默续期重放携带新 Bearer、
 *   重放仍 401 登出且不二次刷新（防循环）、无 refresh 直接登出（保留 refresh cookie）、
 *   /auth/refresh 自身 401 豁免（不跳转不递归刷新）、HTTP 200 业务码 401 同链路、
 *   definite 失败 + cookie 被他标签轮换 → 追新值再刷后重放、
 *   transient 失败 → 不登出不清 token 原请求以网络错误拒绝
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
const mockRemoveRefreshToken = removeRefreshToken as jest.MockedFunction<typeof removeRefreshToken>
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

/** 网络层失败（无 HTTP 响应）经拦截器归一化后的 ApiError 形态 */
const networkApiError = new ApiError('网络连接失败，请检查网络连接', { code: '0', httpStatus: 0 })

beforeEach(() => {
  // 先复位会话（内部会调用 cookies mock 的 remove*），再清调用记录——
  // 否则"未被调用"断言会吃到复位期间的调用
  UserModule.ResetToken()
  jest.clearAllMocks()
  // clearAllMocks 只清调用记录：Once 队列与粘性实现需显式复位，
  // 防上一用例（尤其失败早退）残留的 Once 值顶掉本用例的设置
  mockRefresh.mockReset()
  ;(getRefreshToken as jest.Mock).mockReset()
  ;(getUserId as jest.Mock).mockReturnValue('')
  resetRefreshState()
  clock += 60_000
  jest.spyOn(Date, 'now').mockImplementation(() => clock)
  window.location.hash = ''
})

afterEach(() => {
  jest.restoreAllMocks()
})

describe('redirectToLogin', () => {
  it('hash 模式跳转：redirect 携带 hash 内真实路由，清空内存 access token 但保留共享 cookie（refresh 与 access 均不清）并给出过期提示', () => {
    UserModule.SetToken('stale-access')
    window.location.hash = '#/torrents?page=2'

    redirectToLogin()

    expect(mockMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'warning' }))
    expect(UserModule.token).toBe('')
    // 共享 cookie 全保留（F6 级联防护）：删共享 access cookie 会经他标签
    // syncTokenFromCookie 的"cookie 空 + 内存有 token"判据级联误杀正常标签
    expect(removeToken).not.toHaveBeenCalled()
    expect(mockRemoveRefreshToken).not.toHaveBeenCalled()
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

describe('trySilentRefresh（三态）', () => {
  it('无 refresh token → rejected 且不发刷新请求', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('')

    await expect(trySilentRefresh()).resolves.toMatchObject({ status: 'rejected' })
    expect(mockRefresh).not.toHaveBeenCalled()
  })

  it('刷新成功 → renewed，且新令牌对写入内存与 cookie（后端使用即轮换）', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('old-refresh')
    mockRefresh.mockResolvedValue(refreshSuccessEnvelope)
    UserModule.SetToken('expired-access')

    await expect(trySilentRefresh()).resolves.toMatchObject({ status: 'renewed' })

    expect(mockRefresh).toHaveBeenCalledWith('old-refresh')
    expect(UserModule.token).toBe('new-access')
    expect(mockSetRefreshToken).toHaveBeenCalledWith('new-refresh')
  })

  it('刷新被后端明确拒绝（ApiError 401，拦截器归一化后的真实失败形态）→ rejected（cookie 未变不重试）', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('dead-refresh')
    mockRefresh.mockRejectedValue(new ApiError('已撤销', { code: '401', httpStatus: 200 }))

    await expect(trySilentRefresh()).resolves.toMatchObject({ status: 'rejected' })
    expect(mockRefresh).toHaveBeenCalledTimes(1)
  })

  it('刷新响应缺 access_token（直透的异常信封）→ transient（契约异常保留现场）', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('dead-refresh')
    mockRefresh.mockResolvedValue(refreshFailEnvelope)

    await expect(trySilentRefresh()).resolves.toMatchObject({ status: 'transient' })
    expect(mockRefresh).toHaveBeenCalledTimes(1)
  })

  it('刷新网络失败（ApiError code 0）→ transient 携带原始错误，交调用方保留现场', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('old-refresh')
    mockRefresh.mockRejectedValue(networkApiError)

    await expect(trySilentRefresh()).resolves.toMatchObject({ status: 'transient' })
    // 网络类失败不重试（重试只会重复失败）
    expect(mockRefresh).toHaveBeenCalledTimes(1)
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

  it('重放仍 401：登出跳转且不二次刷新（防循环），redirect 保留当前路由；refresh cookie 不被清除（ExpireSession）', async() => {
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
    // 跨标签竞态加固：会话过期登出不得清共享 refresh cookie
    expect(mockRemoveRefreshToken).not.toHaveBeenCalled()
    expect(window.location.hash).toBe(`#/login?redirect=${encodeURIComponent('/torrents')}`)
  })

  it('无 refresh token 的 401：不刷新不重放，直接登出跳转（refresh cookie 同样保留）', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('')
    UserModule.SetToken('expired-access')

    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => rejectWith401(cfg))

    await expect(service({ url: '/dashboard/stats', method: 'get' })).rejects.toMatchObject({
      code: '401'
    })

    expect(mockRefresh).not.toHaveBeenCalled()
    expect(adapter).toHaveBeenCalledTimes(1)
    expect(UserModule.token).toBe('')
    expect(mockRemoveRefreshToken).not.toHaveBeenCalled()
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

  it('definite 失败 + cookie 被他标签轮换：追新值二次刷新成功后重放，携带新 Bearer', async() => {
    UserModule.SetToken('expired-access')
    // 首刷（旧值）被后端明确拒绝（拦截器归一化后的 ApiError 形态）；
    // 此后他标签轮换成功写入新 cookie，第二刷（新值）成功
    mockRefresh
      .mockRejectedValueOnce(new ApiError('已撤销', { code: '401', httpStatus: 200 }))
      .mockResolvedValueOnce(refreshSuccessEnvelope)
    // 读取序列：首次读取(旧) → definite 后重读(新) → 第二轮循环读取(新)
    ;(getRefreshToken as jest.Mock)
      .mockReturnValueOnce('old-refresh')
      .mockReturnValueOnce('rotated-refresh')
      .mockReturnValueOnce('rotated-refresh')

    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => {
      if (adapter.mock.calls.length === 1) {
        return rejectWith401(cfg)
      }
      return respond(200, envelope200, cfg)
    })

    const res = await service({ url: '/torrents/list', method: 'get' })

    expect(mockRefresh).toHaveBeenNthCalledWith(1, 'old-refresh')
    expect(mockRefresh).toHaveBeenNthCalledWith(2, 'rotated-refresh')
    expect(adapter).toHaveBeenCalledTimes(2)
    expect(authHeaderOf(1)).toBe('Bearer new-access')
    expect(res.code).toBe('200')
    expect(window.location.hash).toBe('')
  })

  it('续期瞬时网络失败：不登出、不清 token、不跳转，原请求以网络错误拒绝（会话保留待自愈）', async() => {
    (getRefreshToken as jest.Mock).mockReturnValue('old-refresh')
    mockRefresh.mockRejectedValue(networkApiError)
    UserModule.SetToken('expired-access')

    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => rejectWith401(cfg))

    await expect(service({ url: '/torrents/list', method: 'get' })).rejects.toMatchObject({
      code: '0',
      httpStatus: 0
    })

    // 会话现场完整保留：内存 token 不变、无登出跳转、cookie 未清
    expect(UserModule.token).toBe('expired-access')
    expect(window.location.hash).toBe('')
    expect(mockRemoveRefreshToken).not.toHaveBeenCalled()
    expect(adapter).toHaveBeenCalledTimes(1)
  })

  it('续期瞬时失败后单飞复位：下一个请求 401 可再次续期成功并重放（自愈闭环）', async() => {
    UserModule.SetToken('expired-access')
    ;(getRefreshToken as jest.Mock).mockReturnValue('old-refresh')
    mockRefresh
      .mockRejectedValueOnce(networkApiError) // 第一次：网络抖动
      .mockResolvedValueOnce(refreshSuccessEnvelope) // 第二次：网络恢复

    let adapterCall = 0
    adapter.mockImplementation(async(cfg: AxiosRequestConfig) => {
      adapterCall++
      // 首请求与自愈后的第二请求都先 401，续期成功后各自重放成功
      if (adapterCall === 1 || adapterCall === 2) {
        return rejectWith401(cfg)
      }
      return respond(200, envelope200, cfg)
    })

    // 第一次：续期网络失败，原请求被拒但会话保留
    await expect(service({ url: '/torrents/list', method: 'get' })).rejects.toMatchObject({
      code: '0'
    })

    // 第二次：网络恢复后自愈——续期成功、重放成功、令牌更新
    const res = await service({ url: '/dashboard/stats', method: 'get' })

    expect(res.code).toBe('200')
    expect(mockRefresh).toHaveBeenCalledTimes(2)
    expect(UserModule.token).toBe('new-access')
    expect(window.location.hash).toBe('')
  })

  it('网络错误 toast 节流：3 秒窗口内同文案只弹一次（断网+1秒轮询不洪泛），窗口过后恢复提醒', async() => {
    UserModule.SetToken('valid-access')

    // 无 response 的网络层错误（request 已发出）：统一走"网络连接失败"提示
    const networkFailure = (cfg: AxiosRequestConfig): Promise<never> =>
      Promise.reject(Object.assign(new Error('Network Error'), { config: cfg, isAxiosError: true, request: {} }))

    adapter.mockImplementation((cfg: AxiosRequestConfig) => networkFailure(cfg))

    await expect(service({ url: '/torrents/speed', method: 'get' })).rejects.toMatchObject({ code: '0' })
    await expect(service({ url: '/torrents/speed', method: 'get' })).rejects.toMatchObject({ code: '0' })
    await expect(service({ url: '/torrents/speed', method: 'get' })).rejects.toMatchObject({ code: '0' })

    // 3 秒窗口内三次失败只弹一次，模拟断网下 1 秒级速度轮询不再堆叠弹窗
    expect(mockMessage).toHaveBeenCalledTimes(1)
    expect(mockMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', message: '网络连接失败，请检查网络连接' })
    )

    // 窗口过后恢复提醒（长故障下仍能周期性告知用户）
    clock += 3_001
    await expect(service({ url: '/torrents/speed', method: 'get' })).rejects.toMatchObject({ code: '0' })
    expect(mockMessage).toHaveBeenCalledTimes(2)
  })
})
