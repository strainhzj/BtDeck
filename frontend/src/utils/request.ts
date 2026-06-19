import axios from 'axios'
import Message from 'element-ui/packages/message'
import { UserModule } from '@/store/modules/user'
import {
  SUCCESS_CODES,
  isLoginRequest,
  buildBusinessError,
  buildNetworkError,
  buildHttpError
} from '@/utils/error-normalize'

const service = axios.create({
  baseURL: process.env.VUE_APP_BASE_API,
  timeout: 20000
})

/** 防止并发401重复弹窗/跳转 */
let isRedirectingToLogin = false

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
 * 触发登录跳转（带防抖，避免并发 401 重复跳转）。
 */
function redirectToLogin(): void {
  if (!isRedirectingToLogin) {
    isRedirectingToLogin = true
    UserModule.ResetToken()
    window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
  }
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

    // 认证失败：非登录接口触发跳转
    if (apiError.code === '401' && !isLoginRequest(response.config)) {
      redirectToLogin()
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
      error.response.data?.detail,
      httpStatus,
      error.response,
      error.request
    )

    // 认证失败跳转（登录接口豁免）
    if (httpStatus === 401 && !isLoginRequest(error.config)) {
      redirectToLogin()
    }

    return Promise.reject(apiError)
  }
)

export default service
