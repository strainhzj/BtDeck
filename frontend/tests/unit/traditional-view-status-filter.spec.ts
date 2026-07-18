import {
  buildTraditionalStatusFilterItems,
  getTraditionalStatusFilterValue,
  resolveTraditionalStatusFilterSelection,
  TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE
} from '@/views/torrents/utils/traditionalStatusFilter'

describe('TraditionalView 状态过滤器', () => {
  it('将“活动中”放在“全部”和“做种中”之间', () => {
    const items = buildTraditionalStatusFilterItems([
      { icon: '⬆️', label: '做种中', value: 'seeding' },
      { icon: '⬇️', label: '下载中', value: 'downloading' }
    ])

    expect(items.slice(0, 3).map(item => item.label)).toEqual([
      '全部',
      '活动中',
      '做种中'
    ])
  })

  it('选择“活动中”时启用 active_only 并清除普通状态', () => {
    const selection = resolveTraditionalStatusFilterSelection(
      TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE
    )

    expect(selection).toEqual({ status: [], showActiveOnly: true })
    expect(getTraditionalStatusFilterValue(selection.status, selection.showActiveOnly))
      .toBe(TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE)
  })

  it('选择普通状态或“全部”时关闭 active_only', () => {
    const seeding = resolveTraditionalStatusFilterSelection('seeding')
    expect(seeding).toEqual({ status: ['seeding'], showActiveOnly: false })
    expect(getTraditionalStatusFilterValue(seeding.status, seeding.showActiveOnly)).toBe('seeding')

    const all = resolveTraditionalStatusFilterSelection('')
    expect(all).toEqual({ status: [], showActiveOnly: false })
    expect(getTraditionalStatusFilterValue(all.status, all.showActiveOnly)).toBe('')
  })
})
