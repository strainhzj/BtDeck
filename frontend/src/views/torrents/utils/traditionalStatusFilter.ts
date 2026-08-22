export interface StatusFilterItem {
  icon: string
  label: string
  value: string
  count?: number
}

export interface TraditionalStatusFilterSelection {
  status: string[]
  showActiveOnly: boolean
}

export const TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE = '__active__'

/**
 * 将活动筛选作为传统模式的虚拟状态项插入固定位置。
 */
export function buildTraditionalStatusFilterItems(statusItems: StatusFilterItem[]): StatusFilterItem[] {
  return [
    { icon: 'inbox', label: '全部', value: '' },
    { icon: 'activity', label: '活动中', value: TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE },
    ...statusItems
  ]
}

/**
 * 左侧状态过滤器是单选入口；活动状态继续映射到后端 active_only 参数。
 */
export function resolveTraditionalStatusFilterSelection(value: string): TraditionalStatusFilterSelection {
  const showActiveOnly = value === TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE
  return {
    status: value === '' || showActiveOnly ? [] : [value],
    showActiveOnly
  }
}

/**
 * 将内部的 status/showActiveOnly 双字段还原为左侧过滤器的单一选中值。
 */
export function getTraditionalStatusFilterValue(status: string[], showActiveOnly: boolean): string {
  if (showActiveOnly) {
    return TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE
  }

  return Array.isArray(status) ? (status[0] || '') : ''
}
