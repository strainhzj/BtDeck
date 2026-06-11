import axios from 'axios'
import Message from 'element-ui/packages/message'
import { UserModule } from '@/store/modules/user'

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
      config.headers['x-access-token'] = UserModule.token
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
    // 特殊处理：blob类型响应直接返回，不解析code字段
    if (response.config.responseType === 'blob') {
      return response.data
    }

    const res = response.data

    // 成功响应
    if (res.code === '200') {
      return res
    }

    // 处理部分成功的状态 (207 Multi-Status)
    if (res.code === '207') {
      // 部分成功的情况，显示警告消息而不是错误
      Message({
        message: res.msg || '部分操作成功',
        type: 'warning',
        duration: 5 * 1000
      })
      return res
    }

    // 认证错误 - 判断是否为登录接口
    if (res.code === '401') {
      const isLoginRequest = response.config.url?.includes('/login')

      // 登录接口401：仅返回错误，不触发跳转逻辑
      if (isLoginRequest) {
        return Promise.reject(new Error(res.msg || '认证失败'))
      }

      // 非登录接口401：防抖，只处理一次
      if (!isRedirectingToLogin) {
        isRedirectingToLogin = true
        UserModule.ResetToken()
        // 跳转到登录页，携带当前路径以便登录后返回
        window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
      }

      return Promise.reject(new Error(res.msg || '认证失败'))
    }

    // 🔧 修复：移除其他业务错误的自动弹框，让业务代码统一处理
    // 包括：403、404、422、500 及其他业务错误
    return Promise.reject(new Error(res.msg || '操作失败'))
  },
  (error) => {
    // 处理HTTP层面错误
    let errorMessage = '网络错误'

    if (error.response) {
      // 服务器响应了错误状态码
      switch (error.response.status) {
        case 401:
          errorMessage = '认证失败，请重新登录'
          if (!isRedirectingToLogin) {
            isRedirectingToLogin = true
            UserModule.ResetToken()
            window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`
          }
          break
        default:
          // 🔧 修复：除 401 外的所有 HTTP 错误都不显示弹框，让业务代码统一处理
          return Promise.reject(error)
      }
    } else if (error.request) {
      // 请求已发出但没有收到响应
      errorMessage = '网络连接失败，请检查网络连接'
    } else {
      // 其他错误
      errorMessage = error.message || '未知错误'
    }

    // 🔧 修复：只显示网络层面的错误（非业务错误）
    Message({
      message: errorMessage,
      type: 'error',
      duration: 5 * 1000
    })

    return Promise.reject(error)
  }
)

export default service
