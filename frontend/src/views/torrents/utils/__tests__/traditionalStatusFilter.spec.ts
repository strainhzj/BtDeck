import {
  buildTraditionalStatusFilterItems,
  resolveTraditionalStatusFilterSelection,
  getTraditionalStatusFilterValue,
  TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE
} from '../traditionalStatusFilter'

/**
 * traditionalStatusFilter 回归测试
 *
 * 背景：本次 emoji→Lucide 改造把 buildTraditionalStatusFilterItems 注入的两个固定项
 * 「全部」「活动中」的 icon 从 emoji（📥 / ⚡）改为 Lucide 图标名（inbox / activity）。
 * 这两项被 FilterGroup 直接消费（<LucideIcon :name="item.icon">），若回退为 emoji
 * 会导致图标列渲染成 missing 占位。本 spec 钉死这两个不变量，同时覆盖既有映射函数。
 */

const EMOJI_PATTERN = /[\u2190-\u21FF\u2300-\u27FF\u2B00-\u2BFF\u{1F000}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u

const statusItems = [
  { icon: 'trending-up', label: '做种中', value: 'seeding' },
  { icon: 'pause', label: '已暂停', value: 'paused' }
]

describe('traditionalStatusFilter —— emoji→Lucide 改造契约', () => {
  describe('buildTraditionalStatusFilterItems', () => {
    const built = buildTraditionalStatusFilterItems(statusItems)

    it('应在最前方插入「全部」项，icon 为 inbox（非 emoji 📥）', () => {
      const first = built[0]
      expect(first.label).toBe('全部')
      expect(first.value).toBe('')
      expect(first.icon).toBe('inbox')
      expect(first.icon).not.toMatch(EMOJI_PATTERN)
    })

    it('应在第二位插入「活动中」项，icon 为 activity（非 emoji ⚡），value 为活动哨兵', () => {
      const second = built[1]
      expect(second.label).toBe('活动中')
      expect(second.icon).toBe('activity')
      expect(second.value).toBe(TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE)
      expect(second.icon).not.toMatch(EMOJI_PATTERN)
    })

    it('所有项的 icon 都不含 emoji（全部为 Lucide 图标名）', () => {
      built.forEach(item => {
        expect(item.icon).not.toMatch(EMOJI_PATTERN)
      })
    })

    it('后续项保持原状态项的顺序与内容不变', () => {
      expect(built.slice(2)).toEqual(statusItems)
    })
  })

  describe('resolveTraditionalStatusFilterSelection（守住既有语义）', () => {
    it('活动哨兵 → showActiveOnly=true 且 status 为空', () => {
      const r = resolveTraditionalStatusFilterSelection(TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE)
      expect(r.showActiveOnly).toBe(true)
      expect(r.status).toEqual([])
    })

    it('空值 → 既不活动也无具体状态', () => {
      const r = resolveTraditionalStatusFilterSelection('')
      expect(r).toEqual({ status: [], showActiveOnly: false })
    })

    it('具体状态值 → status 单元素数组，showActiveOnly=false', () => {
      const r = resolveTraditionalStatusFilterSelection('seeding')
      expect(r).toEqual({ status: ['seeding'], showActiveOnly: false })
    })
  })

  describe('getTraditionalStatusFilterValue（反向还原，守住既有语义）', () => {
    it('showActiveOnly 优先返回活动哨兵', () => {
      expect(getTraditionalStatusFilterValue(['seeding'], true)).toBe(TRADITIONAL_ACTIVE_STATUS_FILTER_VALUE)
    })

    it('非活动时取 status 首项', () => {
      expect(getTraditionalStatusFilterValue(['paused'], false)).toBe('paused')
    })

    it('空 status 且非活动 → 空字符串（对应「全部」）', () => {
      expect(getTraditionalStatusFilterValue([], false)).toBe('')
    })
  })
})
