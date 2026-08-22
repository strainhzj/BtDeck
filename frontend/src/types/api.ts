/**
 * API通用类型定义
 * 统一管理API请求和响应的类型定义
 */

// 通用API响应格式
export interface ApiResponse<T = any> {
  code: string      // 状态码 (200:成功, 401:未认证, 403:权限不足, 422:参数错误, 500:服务器错误)
  msg: string       // 接口返回信息
  data: T          // 接口返回的数据对象
  status: 'success' | 'error'  // 接口返回状态描述
}

// 分页请求参数
export interface PaginationParams {
  page?: number     // 当前页码
  limit?: number    // 每页大小
  skip?: number     // 跳过记录数
}

// 分页响应数据
export interface PaginatedResponse<T> {
  list: T[]        // 数据列表
  total: number     // 总记录数
  page: number      // 当前页码
  size: number      // 每页大小
  pages?: number    // 总页数
}

// HTTP请求配置
export interface RequestConfig {
  timeout?: number   // 请求超时时间
  headers?: Record<string, string>  // 自定义请求头
  showError?: boolean  // 是否显示错误提示
  showSuccess?: boolean // 是否显示成功提示
}

// 错误响应类型
export interface ErrorResponse {
  code: string
  msg: string
  status: 'error'
  details?: any   // 错误详细信息
  timestamp?: string
  path?: string
}

/**
 * 统一 API 错误对象。
 *
 * 业务代码 catch 后永远拿到 ApiError，无需再区分 axios 原始 error 的
 * e.msg / e.message / e.response.data.msg 三种读取方式。
 *
 * 设计要点（向后兼容）：
 * - extends Error：保证 e.message 与 instanceof Error 继续可用
 *   （存量代码大量依赖 catch (e) { e.message }）
 * - msg getter：兼容存量 e.msg 读取（约 18 个文件）
 * - response getter：兼容存量 e.response.data.msg 读取（约 15 个文件），
 *   并保留 status 供 FileManagement.vue 等依赖 e.response.status 的分支使用
 *
 * 详见审计修复 PLANS/v1.0.5-audit.md P0-1。
 */
export class ApiError extends Error {
  /** 业务码（与后端 CommonResponse.code 同值，如 '401'/'422'/'500'） */
  readonly code: string
  /** 真实 HTTP 状态码（业务码 401 但 HTTP 200 时仍为 200） */
  readonly httpStatus: number
  /** 原始 axios response 引用（供需要 response.config/request 的场景使用） */
  readonly rawResponse?: any
  /** 原始 axios request 引用 */
  readonly rawRequest?: any

  constructor(
    message: string,
    options: {
      code: string
      httpStatus: number
      rawResponse?: any
      rawRequest?: any
    }
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = options.code
    this.httpStatus = options.httpStatus
    this.rawResponse = options.rawResponse
    this.rawRequest = options.rawRequest

    // 维持原型链（TS 编译到 ES5 时 extends Error 的已知问题）
    Object.setPrototypeOf(this, ApiError.prototype)
  }

  /** 兼容存量 e.msg 读取 */
  get msg(): string {
    return this.message
  }

  /**
   * 兼容存量 e.response.data.msg 与 e.response.status 读取。
   * 伪造一个最小 response 形态，让链式容错代码（e?.response?.data?.msg）
   * 自然回退到 e.message。
   */
  get response(): { status: number, data: { code: string, msg: string } } {
    return {
      status: this.httpStatus,
      data: { code: this.code, msg: this.message }
    }
  }
}