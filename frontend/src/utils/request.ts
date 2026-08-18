import axios, { AxiosRequestConfig } from 'axios'
import { Message } from 'element-ui'
import { UserModule } from '@/store/modules/user'
import { setRefreshToken, getRefreshToken } from '@/utils/cookies'
import { refreshAccessToken } from '@/api/users'
import { refreshTokensOnce, type TokenPair, type RefreshOutcome } from '@/utils/token-refresh'
import { buildLoginRedirectTarget } from '@/utils/session'
import { ApiError } from '@/types/api'
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
}

/**
 * 登出跳转防抖窗口（毫秒）。
 * 时间窗到期自动复位：跳转因故受挫（bfcache 后退恢复等）后，后续 401
 * 仍能再次触发登出，不会像永久标志那样把会话失效静默吞掉。
 */
const REDIRECT_DEBOUNCE_MS = 3000

let redirectDebounceUntil = 0

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
  // ExpireSession 保留 refresh cookie：多标签共享 cookie 下，"确证死亡"
  // 判定存在他标签轮换未落盘的时序残余——清共享 cookie 会把有效令牌一并
  // 杀死（死 token 残留无害，重登录时 Login 覆盖）
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
    // 无 response：网络层错误（请求未发出/无响应）
    if (!error.response) {
      const message = error.request
        ? '网络连接失败，请检查网络连接'
        : error.message || '网络错误'
      // 网络层错误显示统一提示（业务错误不弹框，交给业务代码）
      Message({ message, type: 'error', duration: 5 * 1000 })
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

export default service as unknown as RequestClient
