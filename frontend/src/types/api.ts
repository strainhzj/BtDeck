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