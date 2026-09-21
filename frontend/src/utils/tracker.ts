/**
 * Tracker 管理相关的工具函数（P6-3 双语化同步收敛）。
 *
 * 双语边界：
 * - extractErrorMessage 的 data.msg/error/detail/message 原文透传（后端原始数据，E03）；
 * - getLanguageLabel 已登记语言码走 tracker.lang.* 键，未登记码原文回退（Q02）；
 * - parseJSON 抛出的内部异常消息不进入用户提示（调用方捕获后仅日志）；
 * - 死代码清理（2026-09-19 P6-3）：KEYWORD_TYPE_OPTIONS / getKeywordTypeLabel /
 *   PRIORITY_RANGE / getPriorityTagType / getOccurrenceCountTagType / formatDateTime /
 *   downloadJSON / validateKeywordData 均为零生产消费方导出，随双语化删除（不为其落键）。
 */
import i18n from '@/i18n'
import { translate } from '@/i18n'
import { DEFAULT_LOCALE } from '@/i18n/types'

/** tracker 语言包内已登记键存在性检查（键名动态拼接，无法走静态枚举门禁，故此处自检） */
function hasKey(key: string): boolean {
  return i18n.te(key) || i18n.te(key, DEFAULT_LOCALE)
}

/**
 * 池子类型显示名（关键词看板/搜索/列表弹窗/快捷操作弹窗同源消费）
 * @param poolType - 池子类型（'candidate' | 'ignored' | 'success' | 'failed' 或其它原始值）
 * @returns 当前语言的池子名；未登记类型原文回退（Q02）
 */
export function poolLabel(poolType: string): string {
  const key = `tracker.pools.${poolType}`
  return hasKey(key) ? (i18n.t(key) as string) : poolType
}

/**
 * 池子下拉选项列表（排除指定池子；标签随语言切换响应式）
 * @param excludePoolTypes - 需要排除的池子类型
 */
export function poolOptions(excludePoolTypes: string[] = []): { value: string, label: string }[] {
  return (['candidate', 'ignored', 'success', 'failed'] as string[])
    .filter(poolType => !excludePoolTypes.includes(poolType))
    .map(poolType => ({ value: poolType, label: poolLabel(poolType) }))
}

/**
 * 获取语言的显示名
 * @param language - 语言代码（如 'zh_CN', 'en_US'；空串表示通用）
 * @returns 当前语言的显示名，未登记的语言码原文回退（Q02）
 */
export function getLanguageLabel(language: string): string {
  const key = language ? `tracker.lang.${language}` : 'tracker.lang.generic'
  return hasKey(key) ? (i18n.t(key) as string) : language
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
 * 从错误对象中提取用户友好的错误信息（Tracker 管理域共享）
 * @param error 错误对象
 * @param defaultMessage 默认错误消息（调用方传翻译键值；缺省走 tracker.errors.operationFailed）
 * @returns 用户友好的错误消息（后端 msg/message/detail 原文透传）
 */
export function extractErrorMessage(error: any, defaultMessage?: string): string {
  const fallback = defaultMessage ?? translate('tracker.errors.operationFailed')
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
        return translate('tracker.errors.validationFailed', { message: validationErrors })
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

  return fallback
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
