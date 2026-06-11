/**
 * 统一的状态配置文件
 * 与后端状态映射保持一致
 */

/**
 * 状态选项接口
 */
export interface StatusOption {
  /** 显示标签（带emoji） */
  label: string
  /** 状态值（映射后的统一值） */
  value: string
  /** 对应的qBittorrent原始状态（用于参考） */
  originalStates?: string[]
}

/**
 * 种子状态选项配置
 * 对应后端QBITTORRENT_STATUS_MAP映射后的状态
 */
export const STATUS_OPTIONS: StatusOption[] = [
  {
    label: '⬆️ 做种中',
    value: 'seeding',
    originalStates: ['stalledUP', 'seeding', 'queuedUP']
  },
  {
    label: '⬇️ 下载中',
    value: 'downloading',
    originalStates: ['downloading', 'stalledDL']
  },
  {
    label: '⏸️ 已暂停',
    value: 'paused',
    originalStates: ['pausedDL', 'pausedUP', 'paused']
  },
  {
    label: '⏳ 下载队列',
    value: 'queuedDL',
    originalStates: ['queuedDL']
  },
  {
    label: '⚠️ 错误',
    value: 'error',
    originalStates: ['error']
  },
  {
    label: '🔄 检查中',
    value: 'checking',
    originalStates: ['checkingDL', 'checkingUP']
  }
]

/**
 * 状态值到显示文本的映射
 */
export const STATUS_TEXT_MAP: Record<string, string> = {
  seeding: '做种中',
  downloading: '下载中',
  paused: '已暂停',
  queuedDL: '下载队列',
  error: '错误',
  checking: '检查中'
}

/**
 * 状态值到图标的映射
 */
export const STATUS_ICON_MAP: Record<string, string> = {
  seeding: '⬆️',
  downloading: '⬇️',
  paused: '⏸️',
  queuedDL: '⏳',
  error: '⚠️',
  checking: '🔄'
}

/**
 * 获取状态显示文本
 * @param status 状态值
 * @returns 显示文本
 */
export function getStatusText(status: string): string {
  return STATUS_TEXT_MAP[status] || status
}

/**
 * 获取状态图标
 * @param status 状态值
 * @returns 状态图标
 */
export function getStatusIcon(status: string): string {
  return STATUS_ICON_MAP[status] || '❓'
}

/**
 * 检查状态是否为有效状态
 * @param status 状态值
 * @returns 是否有效
 */
export function isValidStatus(status: string): boolean {
  return STATUS_OPTIONS.some(option => option.value === status)
}
