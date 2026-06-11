/**
 * Tracker管理相关的工具函数和常量
 */

/**
 * 语言代码到中文标签的映射
 */
export const LANGUAGE_LABELS: Record<string, string> = {
  'zh_CN': '中文',
  'en_US': '英文',
  'ru_RU': '俄语',
  'ja_JP': '日语',
  '': '通用'
}

/**
 * 关键词类型选项
 */
export const KEYWORD_TYPE_OPTIONS = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failure' }
]

/**
 * 优先级范围配置
 */
export const PRIORITY_RANGE = {
  MIN: 1,
  MAX: 1000,
  DEFAULT: 100,
  HIGH: 800,  // 高优先级阈值
  MEDIUM: 500 // 中优先级阈值
}

/**
 * 获取语言的中文标签
 * @param language - 语言代码（如 'zh_CN', 'en_US'）
 * @returns 语言的中文标签，如果未找到则返回原语言代码
 */
export function getLanguageLabel(language: string): string {
  return LANGUAGE_LABELS[language] || language
}

/**
 * 获取关键词类型的标签
 * @param keywordType - 关键词类型（'success' | 'failure'）
 * @returns 关键词类型的中文标签
 */
export function getKeywordTypeLabel(keywordType: 'success' | 'failure'): string {
  return keywordType === 'success' ? '成功' : '失败'
}

/**
 * 获取优先级标签类型（用于Element UI的Tag组件）
 * @param priority - 优先级数值
 * @returns Element UI的Tag类型
 */
export function getPriorityTagType(priority: number): 'success' | 'warning' | 'info' | 'danger' {
  if (priority >= PRIORITY_RANGE.HIGH) {
    return 'danger'
  } else if (priority >= PRIORITY_RANGE.MEDIUM) {
    return 'warning'
  } else {
    return 'info'
  }
}

/**
 * 获取出现次数标签类型（用于Element UI的Tag组件）
 * @param count - 出现次数
 * @returns Element UI的Tag类型
 */
export function getOccurrenceCountTagType(count: number): 'success' | 'warning' | 'info' | 'danger' {
  if (count >= 50) {
    return 'danger'
  } else if (count >= 20) {
    return 'warning'
  } else {
    return 'info'
  }
}

/**
 * 防抖函数
 * @param func - 需要防抖的函数
 * @param delay - 延迟时间（毫秒）
 * @returns 防抖后的函数
 */
export function debounce<T extends(...args: any[]) => any>(
  func: T,
  delay = 300
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  return function(this: any, ...args: Parameters<T>) {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }

    timeoutId = setTimeout(() => {
      func.apply(this, args)
    }, delay)
  }
}

/**
 * 格式化日期时间为本地字符串
 * @param dateString - ISO格式的日期字符串
 * @returns 格式化后的日期时间字符串
 */
export function formatDateTime(dateString: string): string {
  if (!dateString) return '-'

  try {
    const date = new Date(dateString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
  } catch (error) {
    console.error('日期格式化失败:', error)
    return dateString
  }
}

export function extractErrorMessage(error: any, defaultMessage = '操作失败'): string {
  const data = error && error.response && error.response.data

  if (data) {
    if (data.msg) {
      return data.msg
    }

    if (data.error) {
      return data.error
    }

    if (Array.isArray(data.detail)) {
      const validationErrors = data.detail.map((err: any) => {
        const loc = Array.isArray(err.loc) ? err.loc.join('.') : ''
        const msg = err.msg || ''
        return loc ? `${loc} : ${msg}` : msg
      }).join('; ')
      if (validationErrors) {
        return `参数验证失败: ${validationErrors}`
      }
    } else if (data.detail) {
      return data.detail
    }

    if (data.message) {
      return data.message
    }
  }

  if (error && error.message) {
    return error.message
  }

  return defaultMessage
}

/**
 * 下载JSON文件
 * @param data - 要下载的数据
 * @param filename - 文件名（不包含扩展名）
 */
export function downloadJSON(data: any, filename: string): void {
  try {
    const json = JSON.stringify(data, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${filename}_${new Date().getTime()}.json`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('下载失败:', error)
    throw new Error('下载失败')
  }
}

/**
 * 解析JSON字符串
 * @param jsonString - JSON字符串
 * @returns 解析后的对象
 * @throws 如果JSON格式不正确
 */
export function parseJSON<T = any>(jsonString: string): T {
  try {
    return JSON.parse(jsonString)
  } catch (error) {
    console.error('JSON解析失败:', error)
    throw new Error('JSON格式不正确')
  }
}

/**
 * 验证关键词数据
 * @param data - 关键词数据
 * @returns 验证结果和错误消息
 */
export function validateKeywordData(data: any): { valid: boolean, errors: string[] } {
  const errors: string[] = []

  if (!data.keyword_type || !['success', 'failure'].includes(data.keyword_type)) {
    errors.push('关键词类型必须是success或failure')
  }

  if (!data.keyword || typeof data.keyword !== 'string') {
    errors.push('关键词内容必须是非空字符串')
  } else if (data.keyword.length > 200) {
    errors.push('关键词内容不能超过200个字符')
  }

  if (data.priority !== undefined) {
    const priority = Number(data.priority)
    if (isNaN(priority) || priority < 1 || priority > 1000) {
      errors.push('优先级必须是1-1000之间的数字')
    }
  }

  return {
    valid: errors.length === 0,
    errors
  }
}
