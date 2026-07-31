import {
  STATUS_OPTIONS,
  STATUS_TEXT_MAP,
  STATUS_ICON_MAP,
  getStatusText,
  getStatusIcon
} from '../status-config'

/**
 * status-config 回归测试
 *
 * 背景：本次「emoji → Lucide 图标」改造对 status-config 做了三处语义变更：
 *   1. StatusOption 新增必填 icon 字段（Lucide 图标名）；
 *   2. STATUS_OPTIONS.label 去掉 emoji 前缀，变为纯文本；
 *   3. STATUS_ICON_MAP / getStatusIcon 从存/返回 emoji 改为存/返回 Lucide 图标名，
 *      fallback 由 '❓' 改为 'help-circle'。
 *
 * 这些契约被 index.vue / TraditionalView / AdvancedMultiSelect / FilterGroup 等多处
 * 直接消费（模板里 <LucideIcon :name="getStatusIcon(status)">），任一回退都会导致
 * 图标渲染失败（LucideIcon 找不到 name → 空占位）。本 spec 守住这些不变量。
 */

// 常见 emoji 前缀字符（覆盖箭头/表情/几何符号等），用于断言 label 不再带 emoji
const EMOJI_PATTERN = /[\u2190-\u21FF\u2300-\u27FF\u2B00-\u2BFF\u{1F000}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u

describe('status-config —— emoji→Lucide 改造契约', () => {
  describe('STATUS_OPTIONS', () => {
    it('每个选项都必须提供 icon 字段（Lucide 图标名）', () => {
      STATUS_OPTIONS.forEach(opt => {
        expect(opt.icon).toBeTruthy()
        expect(typeof opt.icon).toBe('string')
        expect(opt.icon.length).toBeGreaterThan(0)
      })
    })

    it('label 应为纯文本，不含 emoji 前缀', () => {
      STATUS_OPTIONS.forEach(opt => {
        expect(opt.label).not.toMatch(EMOJI_PATTERN)
      })
    })

    it('每个 value 都有对应的 STATUS_ICON_MAP 条目且图标名一致', () => {
      STATUS_OPTIONS.forEach(opt => {
        expect(STATUS_ICON_MAP[opt.value]).toBe(opt.icon)
      })
    })

    it('STATUS_ICON_MAP 不再存 emoji，全部为 Lucide 图标名（非空白、无 emoji）', () => {
      Object.entries(STATUS_ICON_MAP).forEach(([, name]) => {
        expect(typeof name).toBe('string')
        expect(name.length).toBeGreaterThan(0)
        expect(name).not.toMatch(EMOJI_PATTERN)
      })
    })
  })

  describe('getStatusIcon', () => {
    it('已知状态返回对应的 Lucide 图标名（与 STATUS_ICON_MAP 一致）', () => {
      Object.entries(STATUS_ICON_MAP).forEach(([status, name]) => {
        expect(getStatusIcon(status)).toBe(name)
      })
    })

    it('未知状态 fallback 为 help-circle（而非旧 emoji ❓）', () => {
      // 这是本次改造的关键不变量：fallback 必须是合法 Lucide 图标名，
      // 否则 <LucideIcon :name="getStatusIcon(未知)"> 会渲染 missing 占位。
      expect(getStatusIcon('non-existent-status')).toBe('help-circle')
      expect(getStatusIcon('')).toBe('help-circle')
    })

    it('fallback 不再返回 emoji', () => {
      expect(getStatusIcon('unknown')).not.toMatch(EMOJI_PATTERN)
    })
  })

  describe('getStatusText（未受本次改造影响，守住纯文本不变量）', () => {
    it('每个 STATUS_OPTIONS 都有对应的纯文本 getStatusText', () => {
      STATUS_OPTIONS.forEach(opt => {
        const text = getStatusText(opt.value)
        expect(text).toBe(STATUS_TEXT_MAP[opt.value])
        expect(text).not.toMatch(EMOJI_PATTERN)
      })
    })
  })

  describe('STATUS_OPTIONS 全集（守住六态不被意外增删）', () => {
    it('应恰好包含六个状态值', () => {
      const values = STATUS_OPTIONS.map(o => o.value)
      expect(values).toEqual(
        expect.arrayContaining([
          'seeding',
          'downloading',
          'paused',
          'queuedDL',
          'error',
          'checking'
        ])
      )
      expect(STATUS_OPTIONS).toHaveLength(6)
    })
  })
})
