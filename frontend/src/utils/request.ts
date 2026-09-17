import axios, { AxiosRequestConfig } from 'axios'
import { Message } from 'element-ui'
import { UserModule } from '@/store/modules/user'
import { setRefreshToken, getRefreshToken } from '@/utils/cookies'
import { refreshAccessToken } from '@/api/users'
import { refreshTokensOnce, type TokenPair, type RefreshOutcome } from '@/utils/token-refresh'
import { buildLoginRedirectTarget } from '@/utils/session'
import { ApiError } from '@/types/api'
import { isDemoMode } from '@/demo/config'
import { demoRequest } from '@/demo/demo-request'
import {
  SUCCESS_CODES,
  isLoginRequest,
  buildBusinessError,
  buildNetworkError,
  buildHttpError,
  pickErrorPayload
} from '@/utils/error-normalize'

const service = axios.create({
  baseURL: process.env.VUE_APP_BASE_API,
  timeout: 20000
})

/** Axios 响应拦截器已解包 response.data；此类型让调用方看到真实业务响应。 */
export interface ApiEnvelope<T = unknown> {
  status: string
  msg: string
  code: string
  data: T
}

export interface RequestClient {
  <T = ApiEnvelope<unknown>>(config: AxiosRequestConfig): Promise<T>
  get<T = ApiEnvelope<unknown>>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = ApiEnvelope<unknown>>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  put<T = ApiEnvelope<unknown>>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T>
  delete<T = ApiEnvelope<unknown>>(url: string, config?: AxiosRequestConfig): Promise<T>
  /** 兼容需要注入 Axios adapter 的集成测试与调试工具。 */
  defaults: typeof service.defaults
}

/**
 * 登出跳转防抖窗口（毫秒）。
 * 时间窗到期自动复位：跳转因故受挫（bfcache 后退恢复等）后，后续 401
 * 仍能再次触发登出，不会像永久标志那样把会话失效静默吞掉。
 */
const REDIRECT_DEBOUNCE_MS = 3000

let redirectDebounceUntil = 0

/**
 * 网络错误 toast 节流窗口（毫秒）。断网 + 1 秒级速度轮询会让每个失败请求
 * 都弹独立 Message（拦截器是唯一弹窗点，组件 catch 均静默），洪泛淹没界面；
 * 与 redirectToLogin 防抖同窗口惯例：窗口到期自然复位，长故障下仍能周期提醒。
 */
const NETWORK_TOAST_THROTTLE_MS = 3000

let lastNetworkToast: { message: string, at: number } | null = null

/** 网络错误提示节流：窗口内同文案只弹一次，不同文案不受影响 */
function notifyNetworkError(message: string): void {
  const now = Date.now()
  if (lastNetworkToast && lastNetworkToast.message === message && now - lastNetworkToast.at < NETWORK_TOAST_THROTTLE_MS) {
    return
  }
  lastNetworkToast = { message, at: now }
  Message({ message, type: 'error', duration: 5 * 1000 })
}

/**
 * 调试模式开关
 * 通过环境变量 VUE_APP_DEBUG_MODE 控制
 * 默认关闭，设置为 true 时会打印 API 请求调试信息（不包含敏感数据）
 */
const DEBUG_MODE = process.env.VUE_APP_DEBUG_MODE === 'true'

/**
 * 安全的 token 脱敏函数
 * 只显示前 10 个字符和后 10 个字符，中间用 * 替代
 * @param token - JWT token 字符串
 * @returns 脱敏后的 token 字符串
 */
function maskToken(token: string): string {
  if (!token || token.length <= 20) {
    return '****'
  }
  return `${token.substring(0, 10)}...${token.substring(token.length - 10)}`
}

/**
 * 触发登出跳转（带 3 秒防抖窗口，避免并发 401 重复跳转）。
 *
 * 路由为 hash 模式：真实路由在 location.hash 内，pathname 恒为部署根，
 * 跳转目标必须走 hash URL——否则 redirect 参数退化为 '/'，且整页跳转
 * 依赖服务器对 /login 路径的 SPA 回退（无回退的部署会 404 并卡死防抖）。
 */
export function redirectToLogin(): void {
  const now = Date.now()
  if (now < redirectDebounceUntil) {
    return
  }
  redirectDebounceUntil = now + REDIRECT_DEBOUNCE_MS
  Message({ message: '登录状态已过期，请重新登录', type: 'warning', duration: 3000 })
  // ExpireSession 保留共享 cookie（access + refresh）：多标签共享 cookie 下，
  // "确证死亡"判定存在他标签轮换未落盘的时序残余——清共享 cookie 会把有效
  // 令牌一并杀死（access cookie 被删还会经 syncTokenFromCookie 级联误杀
  // 正常工作的标签）。死 token 残留无害，重登录时 Login 覆盖
  UserModule.ExpireSession()
  window.location.href = buildLoginRedirectTarget(window.location.hash, window.location.pathname)
}

// ====== 401 静默续期（双令牌体系 W6-1） ======

/** 刷新依赖注入（独立于 axios 层，便于单测 token-refresh 编排） */
const refreshDeps = {
  doRefresh: async(refreshToken: string): Promise<TokenPair> => {
    const res = await refreshAccessToken(refreshToken)
    const item = res.data && res.data[0]
    if (!item || !item.access_token) {
      throw new Error('刷新响应缺少 access_token')
    }
    return {
      accessToken: item.access_token,
      // 后端使用即轮换：优先用新 refresh token，缺失时沿用旧值
      refreshToken: item.refresh_token || refreshToken
    }
  },
  // 直接读 cookie 而非 store：getModule 访问器不代理未装饰的普通方法
  // （UserModule.getRefreshTokenValue 在运行时不存在，会让整个续期链路抛 TypeError）
  getRefreshToken: () => getRefreshToken() || '',
  saveTokens: (pair: TokenPair) => {
    UserModule.SetToken(pair.accessToken)
    setRefreshToken(pair.refreshToken)
  },
  // 后端明确拒绝（业务码 401 或 HTTP 401）才判死；网络断连/超时/5xx 为瞬时
  isDefiniteFailure: (err: unknown): boolean => err instanceof ApiError && err.code === '401'
}

/**
 * 主动续期入口（守卫/会话监听使用，W6 伴随修复）：
 * 返回三态结果——renewed（已更新令牌）/ rejected（血统确证死亡）/
 * transient（网络抖动等瞬时失败，保留会话现场）。
 */
export async function trySilentRefresh(): Promise<RefreshOutcome> {
  return refreshTokensOnce(refreshDeps)
}

/**
 * 401 统一处理：先尝试静默续期并重放原请求一次，失败按三态分流。
 * 登录/refresh 请求豁免（isLoginRequest）；已重放过的请求不再续期（防循环）。
 */
async function handleUnauthorized(config: AxiosRequestConfig, fallbackError: unknown): Promise<never> {
  const retried = (config as AxiosRequestConfig & { _retried?: boolean })._retried
  if (!retried && !isLoginRequest(config)) {
    const outcome = await trySilentRefresh()
    if (outcome.status === 'renewed') {
      (config as AxiosRequestConfig & { _retried?: boolean })._retried = true
      // 重放原请求：请求拦截器会自动携带新 token，响应拦截器继续解包/归一化
      const retryResult = await service.request(config)
      return retryResult as never
    }
    if (outcome.status === 'transient') {
      // 网络抖动/服务端瞬时错误：不清 token、不跳转，原请求以刷新失败的
      // 网络错误拒绝（toast 已由拦截器网络分支弹出），下个请求/导航自愈
      return Promise.reject(outcome.error)
    }
  }
  redirectToLogin()
  return Promise.reject(fallbackError)
}

// ====== 幂等 GET 瞬态失败自动重试（mobile-ux-fixes 2026-09） ======

/**
 * 重试触发窗口（毫秒）。高负载（全量同步/多客户端轮询）下的网络错误与网关
 * 502/503/504 多为瞬态，稍候重发即可恢复。
 */
const TRANSIENT_RETRY_DELAY_MS = 800

/** 视为瞬态可重试的网关/服务端状态码（404/5xx 其它属确定性失败，不重试） */
const TRANSIENT_RETRY_STATUSES = new Set([502, 503, 504])

/** 与 401 重放的 _retried 同思路：标记防重试循环 */
type TransientRetryConfig = AxiosRequestConfig & { _transientRetried?: boolean }

/**
 * 幂等 GET 瞬态失败重试资格：仅 GET（写操作绝不重放）；网络层错误（请求已
 * 发出但无响应）或 HTTP 502/503/504 触发；超时（ECONNABORTED，timeout 已
 * 20s）不重试——重试只会把等待翻倍；每个请求最多重试一次。
 *
 * 这是高负载失败（伴侣模式红色 toast）的对症缓解：重试期间静默（不弹网络
 * 错误提示），重试用尽仍失败才走节流 toast；负载根源（单 Worker 串行 IO）
 * 由后端另行治理。
 */
function isTransientRetryEligible(error: unknown): boolean {
  const err = error as {
    config?: TransientRetryConfig
    request?: unknown
    response?: { status?: number }
    code?: string
  }
  const config = err.config
  if (!config || config._transientRetried) return false
  if (String(config.method || '').toLowerCase() !== 'get') return false
  if (err.code === 'ECONNABORTED') return false
  if (err.response) {
    const status = err.response.status
    return status !== undefined && TRANSIENT_RETRY_STATUSES.has(status)
  }
  // 请求已发出但无响应 = 网络层错误；仅构建阶段失败（无 request）不可重试
  return Boolean(err.request)
}

async function retryTransientRequest(config: TransientRetryConfig): Promise<never> {
  config._transientRetried = true
  await new Promise((resolve) => { setTimeout(resolve, TRANSIENT_RETRY_DELAY_MS) })
  return await service.request(config) as never
}

// Request interceptors
service.interceptors.request.use(
  (config) => {
    // 仅在调试模式开启时输出调试信息
    if (DEBUG_MODE) {
      console.log('=== API请求调试信息 ===')
      console.log('请求URL:', config.url)
      console.log('请求方法:', config.method)
      console.log('UserModule.token状态:', UserModule.token ? '✅ 已获取token' : '❌ 未获取到token')
    }

    if (UserModule.token) {
      // 认证契约收敛：只发送 Authorization: Bearer。
      // 后端 dependencies.py 已兼容读取 Bearer，移除冗余的 x-access-token。
      config.headers['Authorization'] = `Bearer ${UserModule.token}`
      if (DEBUG_MODE) {
        console.log('✅ token已设置到请求头（脱敏）:', maskToken(UserModule.token))
      }
    } else if (DEBUG_MODE) {
      console.warn('⚠️ 警告: token为空，请求可能未携带认证信息')
    }

    if (DEBUG_MODE) {
      // 不打印完整请求头，避免泄露其他敏感信息
      console.log('========================')
    }

    return config
  },
  (error) => {
    console.error('❌ 请求拦截器错误:', error)
    return Promise.reject(error)
  }
)

// Response interceptors
service.interceptors.response.use(
  (response) => {
    // blob 响应直接返回原始 data，不解析 code 字段
    if (response.config.responseType === 'blob') {
      return response.data
    }

    const res = response.data

    // 成功响应（含业务级部分成功/需确认）
    if (res && SUCCESS_CODES.has(res.code)) {
      // 207 保留部分成功的 warning 提示（业务依赖此行为）
      if (res.code === '207') {
        Message({
          message: res.msg || '部分操作成功',
          type: 'warning',
          duration: 5 * 1000
        })
      }
      return res
    }

    // 业务错误：HTTP 200 但 code 非 2xx 成功
    const apiError = buildBusinessError(res, response.status, response)

    // 认证失败：先尝试静默续期+重放，失败才跳登录（登录/refresh 请求豁免）
    if (apiError.code === '401' && !isLoginRequest(response.config)) {
      return handleUnauthorized(response.config, apiError)
    }

    return Promise.reject(apiError)
  },
  (error) => {
    // 幂等 GET 瞬态失败（网络错误/502/503/504）：静默重试一次，成功即无感返回；
    // 重试用尽的失败会带 _transientRetried 标记再次进入本分支走下方归一化
    if (isTransientRetryEligible(error)) {
      return retryTransientRequest((error as { config: TransientRetryConfig }).config)
    }

    // 无 response：网络层错误（请求未发出/无响应）
    if (!error.response) {
      const message = error.request
        ? '网络连接失败，请检查网络连接'
        : error.message || '网络错误'
      // 网络层错误显示统一提示（业务错误不弹框，交给业务代码）；
      // 3 秒同文案节流防轮询洪泛
      notifyNetworkError(message)
      return Promise.reject(buildNetworkError(message, error.request))
    }

    // HTTP 错误：服务器返回了 4xx/5xx
    const httpStatus = error.response.status
    const apiError = buildHttpError(
      pickErrorPayload(error.response.data),
      httpStatus,
      error.response,
      error.request
    )

    // 认证失败：先尝试静默续期+重放，失败才跳登录（登录/refresh 请求豁免）
    if (httpStatus === 401 && !isLoginRequest(error.config)) {
      return handleUnauthorized(error.config, apiError)
    }

    return Promise.reject(apiError)
  }
)

const requestClient = (<T = ApiEnvelope<unknown>>(config: AxiosRequestConfig): Promise<T> => {
  if (isDemoMode()) {
    return demoRequest<T>(config)
  }
  return service.request(config) as unknown as Promise<T>
}) as RequestClient

// 保留旧默认导出作为 Axios 实例时可观察到的 defaults 引用；真实模式仍由
// service.request 执行，Demo 模式只在上面的分流函数内返回本地 Promise。
requestClient.defaults = service.defaults

requestClient.get = <T = ApiEnvelope<unknown>>(url: string, config?: AxiosRequestConfig): Promise<T> =>
  requestClient<T>({ ...(config || {}), url, method: 'get' })

requestClient.post = <T = ApiEnvelope<unknown>>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> => requestClient<T>({ ...(config || {}), url, method: 'post', data })

requestClient.put = <T = ApiEnvelope<unknown>>(
  url: string,
  data?: unknown,
  config?: AxiosRequestConfig
): Promise<T> => requestClient<T>({ ...(config || {}), url, method: 'put', data })

requestClient.delete = <T = ApiEnvelope<unknown>>(url: string, config?: AxiosRequestConfig): Promise<T> =>
  requestClient<T>({ ...(config || {}), url, method: 'delete' })

export default requestClient
