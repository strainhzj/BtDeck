import { TorrentStatus } from '@/types/torrent'

export function normalizeTorrent(torrent: any): any {
  if (!torrent) {
    return {
      hash: '',
      infoId: '',
      info_id: '',
      downloaderId: '',
      downloader_id: '',
      name: '-',
      size: 0,
      status: 'unknown',
      progress: 0,
      downloadSpeed: 0,
      uploadSpeed: 0,
      downloaderName: '-',
      ratio: 0,
      category: '',
      tags: '',
      savePath: '',
      addedDate: null
    }
  }

  return {
    // 确保必需字段存在（保持原始hash不变）
    hash: torrent.hash || '',
    infoId: torrent.infoId || torrent.info_id || torrent.hash || '',
    info_id: torrent.infoId || torrent.info_id || torrent.hash || '',
    downloaderId: torrent.downloaderId || torrent.downloader_id || '',
    downloader_id: torrent.downloaderId || torrent.downloader_id || '',
    
    // 基础信息
    name: torrent.name || '-',
    size: torrent.size || 0,
    status: normalizeTorrentStatus(torrent.status, torrent.state),
    
    // 进度和速度
    progress: torrent.progress ?? 0,
    downloadSpeed: torrent.downloadSpeed ?? 0,
    download_speed: torrent.download_speed ?? torrent.downloadSpeed ?? 0,
    uploadSpeed: torrent.uploadSpeed ?? 0,
    upload_speed: torrent.upload_speed ?? torrent.uploadSpeed ?? 0,
    
    // 下载器信息
    downloaderName: torrent.downloaderName || torrent.downloader_name || '-',
    downloader_name: torrent.downloaderName || torrent.downloader_name || '-',
    
    // 其他字段
    ratio: torrent.ratio ?? 0,
    category: torrent.category || '',
    tags: torrent.tags || '',
    savePath: torrent.savePath || torrent.save_path || '',
    save_path: torrent.savePath || torrent.save_path || '',
    addedDate: torrent.addedDate || torrent.added_date || null,
    added_date: torrent.addedDate || torrent.added_date || null,
    
    // 保留原始其他字段
    ...torrent
  }
}

export function normalizeTorrentStatus(
  status: string | TorrentStatus | null | undefined,
  state?: string | null
): TorrentStatus | 'unknown' {
  const raw = (status || state || '').toString()
  if (!raw) {
    return 'unknown'
  }

  const normalized = raw.toLowerCase()

  switch (normalized) {
    case TorrentStatus.DOWNLOADING:
      return TorrentStatus.DOWNLOADING
    case TorrentStatus.COMPLETED:
      return TorrentStatus.COMPLETED
    case TorrentStatus.PAUSED:
      return TorrentStatus.PAUSED
    case TorrentStatus.SEEDING:
      return TorrentStatus.SEEDING
    case TorrentStatus.CHECKING:
      return TorrentStatus.CHECKING
    case TorrentStatus.ERROR:
      return TorrentStatus.ERROR
    default:
      return 'unknown'
  }
}

/**
 * 统一处理分页API响应
 * 支持标准格式和降级兼容，确保代码健壮性
 * @param response API响应对象
 * @returns 标准化的分页数据 { list, total }
 */
export function normalizePaginatedResponse<T>(response: any): {
  list: T[]
  total: number
} {
  // 默认返回值
  const defaultResult = { list: [], total: 0 }

  if (!response || !response.data) {
    console.warn('API响应格式错误: 缺少data字段', response)
    return defaultResult
  }

  const data = response.data

  // 标准格式: { list, total, page, pageSize }
  if (data.list && Array.isArray(data.list)) {
    return {
      list: data.list,
      total: data.total || 0
    }
  }

  // 降级格式1: 直接是数组
  if (Array.isArray(data)) {
    return {
      list: data,
      total: data.length
    }
  }

  // 降级格式2: { data: [...] }
  if (data.data && Array.isArray(data.data)) {
    return {
      list: data.data,
      total: data.total || data.data.length
    }
  }

  // 无法识别的格式
  console.warn('API响应格式无法识别:', response)
  return defaultResult
}


/**
 * 防抖函数 - 延迟执行函数，在等待时间内再次调用则重置计时器
 * @param func 要防抖的函数
 * @param wait 等待时间(毫秒)
 * @returns 防抖后的函数
 */
export function debounce<T extends(...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null

  return function(this: any, ...args: Parameters<T>) {
    if (timeout) {
      clearTimeout(timeout)
    }

    timeout = setTimeout(() => {
      func(...args)
      timeout = null
    }, wait)
  }
}


/**
 * 从错误对象中提取用户友好的错误信息
 * @param error 错误对象
 * @returns 用户友好的错误消息
 */
export function extractErrorMessage(error: any): string {
  if (!error) return '未知错误'

  // Axios错误响应
  if (error.response) {
    const { data, status } = error.response
    
    // 后端返回的标准错误格式
    if (data && data.msg) {
      return data.msg
    }
    
    // 其他格式
    if (data && data.message) {
      return data.message
    }
    
    // HTTP状态码
    if (status) {
      const statusMessages: Record<number, string> = {
        400: '请求参数错误',
        401: '未授权，请重新登录',
        403: '无权限访问',
        404: '请求的资源不存在',
        422: '数据验证失败',
        500: '服务器内部错误',
        502: '网关错误',
        503: '服务不可用'
      }
      return statusMessages[status] || `请求失败 (${status})`
    }
  }
  
  // 网络错误
  if (error.request) {
    return '网络连接失败，请检查网络设置'
  }
  
  // 错误消息字符串
  if (error.message) {
    return error.message
  }
  
  // Error对象
  if (error instanceof Error) {
    return error.message
  }
  
  // 其他情况
  return String(error)
}

/**
 * 显示用户友好的错误提示（统一处理）
 * @param error 错误对象
 * @param defaultMessage 默认错误消息
 * @param context 错误上下文（操作名称）
 */
export function showErrorToast(
  error: any,
  defaultMessage = '操作失败',
  context?: string
): string {
  const errorMessage = extractErrorMessage(error)
  const fullMessage = context ? `${context}失败：${errorMessage}` : errorMessage
  
  // Element UI的Message组件需要通过Vue实例调用
  // 这里返回消息文本，由调用方显示
  return fullMessage || defaultMessage
}

/**
 * 节流函数 - 限制函数执行频率
 * @param func 要节流的函数
 * @param wait 等待时间(毫秒)
 * @returns 节流后的函数
 */
export function throttle<T extends(...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null
  let previous = 0

  return function(this: any, ...args: Parameters<T>) {
    const now = Date.now()

    if (now - previous > wait) {
      if (timeout) {
        clearTimeout(timeout)
        timeout = null
      }
      func(...args)
      previous = now
    } else if (!timeout) {
      timeout = setTimeout(() => {
        func(...args)
        previous = Date.now()
        timeout = null
      }, wait - (now - previous))
    }
  }
}

/**
 * 统一处理单个对象API响应
 * @param response API响应对象
 * @returns 标准化的对象数据
 */
export function normalizeObjectResponse<T>(response: any): T | null {
  if (!response || !response.data) {
    console.warn('API响应格式错误: 缺少data字段', response)
    return null
  }

  return response.data as T
}

/**
 * 安全地获取种子ID（infoId）
 * 支持多种字段名变体：infoId, info_id, hash
 * @param torrent 种子对象
 * @returns 种子ID字符串
 */
export function getTorrentId(torrent: any): string {
  if (!torrent) return ''
  return torrent.infoId || torrent.info_id || torrent.hash || ''
}

/**
 * 安全地获取下载器ID（downloaderId）
 * 支持多种字段名变体：downloaderId, downloader_id
 * @param torrent 种子对象
 * @returns 下载器ID字符串
 */
export function getDownloaderId(torrent: any): string {
  if (!torrent) return ''
  return torrent.downloaderId || torrent.downloader_id || ''
}

export function formatFileSize(size: number | null | undefined): string {
  if (!size || size === 0) return '-'

  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let index = 0
  let fileSize = size

  while (fileSize >= 1024 && index < units.length - 1) {
    fileSize /= 1024
    index++
  }

  return `${fileSize.toFixed(2)} ${units[index]}`
}

/**
 * 格式化速度
 * @param speed 速度(字节/秒)
 * @returns 格式化后的字符串,如 "1.23 MB/s" 或空字符串
 */
export function formatSpeed(speed: number | null | undefined): string {
  if (speed === null || speed === undefined || speed === 0) return ''
  return formatFileSize(speed) + '/s'
}

/**
 * 格式化日期时间
 * @param timestamp 时间戳(秒或毫秒)或日期字符串
 * @param format 格式类型: 'full' = "2024-01-28 14:30:45", 'date' = "2024-01-28", 'time' = "14:30"
 * @returns 格式化后的字符串
 */
export function formatDate(
  timestamp: number | string | null | undefined,
  format: 'full' | 'date' | 'time' = 'full'
): string {
  if (!timestamp) return '-'

  try {
    let date: Date

    // 处理数字时间戳
    if (typeof timestamp === 'number') {
      // 判断是秒还是毫秒
      if (timestamp < 10000000000) {
        date = new Date(timestamp * 1000)
      } else {
        date = new Date(timestamp)
      }
    }
    // 处理字符串时间戳
    else if (typeof timestamp === 'string') {
      const parsedTimestamp = parseInt(timestamp, 10)
      if (isNaN(parsedTimestamp)) {
        // 不是数字,尝试直接解析
        date = new Date(timestamp)
      } else {
        // 是数字字符串
        if (parsedTimestamp < 10000000000) {
          date = new Date(parsedTimestamp * 1000)
        } else {
          date = new Date(parsedTimestamp)
        }
      }
    } else {
      return '-'
    }

    // 验证日期有效性
    if (isNaN(date.getTime())) {
      return '-'
    }

    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    const seconds = String(date.getSeconds()).padStart(2, '0')

    // 根据格式返回不同字符串
    switch (format) {
      case 'date':
        return `${year}-${month}-${day}`
      case 'time':
        return `${hours}:${minutes}`
      case 'full':
      default:
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
    }
  } catch (error) {
    console.warn('日期格式化错误:', timestamp, error)
    return '-'
  }
}

/**
 * 格式化分享比率
 * @param ratio 比率数值或字符串
 * @param decimals 小数位数,默认2位
 * @returns 格式化后的字符串,如 "2.50"
 */
export function formatRatio(
  ratio: number | string | null | undefined,
  decimals = 2
): string {
  if (!ratio || ratio === '') return '-'

  const numRatio = parseFloat(ratio.toString())
  if (isNaN(numRatio)) {
    return '-'
  }

  return numRatio.toFixed(decimals)
}

/**
 * 格式化持续时间
 * @param seconds 秒数
 * @returns 格式化后的字符串,如 "1d 2h 30m 15s"
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds === 0) return '-'

  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)

  const parts: string[] = []

  if (days > 0) parts.push(`${days}d`)
  if (hours > 0) parts.push(`${hours}h`)
  if (minutes > 0) parts.push(`${minutes}m`)
  if (secs > 0 || parts.length === 0) parts.push(`${secs}s`)

  return parts.join(' ')
}

/**
 * 格式化百分比
 * @param value 数值(0-1)
 * @param decimals 小数位数,默认0位
 * @returns 格式化后的字符串,如 "75%"
 */
export function formatPercent(
  value: number | null | undefined,
  decimals = 0
): string {
  if (value === null || value === undefined) return '0%'

  const percent = value * 100
  return `${percent.toFixed(decimals)}%`
}

/**
 * 截断文本并添加省略号
 * @param text 原始文本
 * @param maxLength 最大长度
 * @returns 截断后的文本
 */
export function truncateText(
  text: string | null | undefined,
  maxLength = 50
): string {
  if (!text) return '-'

  if (text.length <= maxLength) {
    return text
  }

  return text.substring(0, maxLength) + '...'
}

/**
 * 格式化数字为千分位
 * @param num 数字
 * @returns 格式化后的字符串,如 "1,234,567"
 */
export function formatNumber(num: number | null | undefined): string {
  if (num === null || num === undefined) return '-'

  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

/**
 * 获取文件扩展名
 * @param filename 文件名
 * @returns 扩展名(包含点),如 ".torrent"
 */
export function getFileExtension(filename: string | null | undefined): string {
  if (!filename) return ''

  const lastDotIndex = filename.lastIndexOf('.')
  if (lastDotIndex === -1) {
    return ''
  }

  return filename.substring(lastDotIndex)
}

/**
 * 格式化时间差(相对时间)
 * @param timestamp 时间戳
 * @returns 相对时间描述,如 "2小时前"
 */
export function formatRelativeTime(
  timestamp: number | string | null | undefined
): string {
  if (!timestamp) return '-'

  try {
    let date: Date

    if (typeof timestamp === 'number') {
      date = timestamp < 10000000000
        ? new Date(timestamp * 1000)
        : new Date(timestamp)
    } else {
      date = new Date(timestamp)
    }

    if (isNaN(date.getTime())) {
      return '-'
    }

    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSecs = Math.floor(diffMs / 1000)
    const diffMins = Math.floor(diffSecs / 60)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffSecs < 60) {
      return '刚刚'
    } else if (diffMins < 60) {
      return `${diffMins}分钟前`
    } else if (diffHours < 24) {
      return `${diffHours}小时前`
    } else if (diffDays < 7) {
      return `${diffDays}天前`
    } else if (diffDays < 30) {
      return `${Math.floor(diffDays / 7)}周前`
    } else if (diffDays < 365) {
      return `${Math.floor(diffDays / 30)}个月前`
    } else {
      return `${Math.floor(diffDays / 365)}年前`
    }
  } catch (error) {
    console.warn('相对时间格式化错误:', timestamp, error)
    return '-'
  }
}

export default {
  formatFileSize,
  formatSpeed,
  formatDate,
  formatRatio,
  formatDuration,
  formatPercent,
  truncateText,
  formatNumber,
  getFileExtension,
  formatRelativeTime
}
