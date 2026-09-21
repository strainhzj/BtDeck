/**
 * 移动端种子状态展示共享映射（列表卡片与详情页复用，避免两处重复维护）。
 * 桌面端状态映射在 views/torrents 各组件内自持；移动端两页共用这一份。
 */

export interface StatusOption {
  label: string
  value: string
}

export const TORRENT_STATUS_OPTIONS: StatusOption[] = [
  { label: '下载中', value: 'downloading' },
  { label: '做种中', value: 'seeding' },
  { label: '已暂停', value: 'paused' },
  { label: '错误', value: 'error' }
]

export function torrentStatusLabel(status: string): string {
  const found = TORRENT_STATUS_OPTIONS.find((opt) => opt.value === status)
  return found ? found.label : status
}

export function torrentStatusTagType(status: string): string {
  switch (status) {
    case 'downloading':
      return 'primary'
    case 'seeding':
      return 'success'
    case 'paused':
      return 'info'
    case 'error':
      return 'danger'
    default:
      return 'warning'
  }
}

/** 紧凑大小展示（移动卡片/详情）：大值取整、小值 1 位小数 */
export function formatTorrentSize(bytes: number): string {
  if (!bytes || bytes <= 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`
}
