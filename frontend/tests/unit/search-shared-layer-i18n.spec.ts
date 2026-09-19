/**
 * 高级搜索共享层双语契约（desktop-bilingual-20260918.p3，验收矩阵 T01 子集）。
 *
 * 钉死四条约束：
 * 1. 契约源双标签完整：每个操作符 label/labelEn 非空，labelEn 为英文字符
 *    （操作符展示名唯一来源 = 后端契约 json，不在语言包内复制）；
 * 2. 展示名按稳定值映射：getOperatorLabel / searchOperatorLabel 按 locale
 *    取 label/labelEn，绝不用中文匹配；
 * 3. 字段/分组/摘要/预览文本两语言输出正确（zh-CN 输出与历史内联中文逐字一致）；
 * 4. 语言切换不改变业务参数：相同条件组在两种语言下 buildAdvancedSearchParams
 *    产出完全一致的 groups JSON（operator/value/mode 均为稳定值）。
 */
import { ADVANCED_SEARCH_OPERATOR_GROUPS } from '@/contracts/advancedSearch.generated'
import { buildAdvancedSearchParams } from '@/components/torrents/advancedSearchState'
import type { AdvancedSearchGroupState } from '@/components/torrents/advancedSearchState'
import {
  buildGroupsQueryText,
  describeCondition,
  getOperatorGroupsForField,
  getOperatorLabel,
  getSearchFieldInfo,
  getSearchFieldOptions,
  normalizeLoadedGroups,
  searchFieldLabel
} from '@/components/torrents/advancedSearchFields'
import i18n, { setLocale } from '@/i18n'

const originalLocale = i18n.locale

afterAll(() => {
  setLocale(originalLocale as 'zh-CN' | 'en')
})

describe('契约源双标签完整（label/labelEn 成对）', () => {
  it('每个操作符都有非空 label 与 labelEn，且 labelEn 为 ASCII 英文', () => {
    const operators = Object.values(ADVANCED_SEARCH_OPERATOR_GROUPS).flat()
    expect(operators.length).toBeGreaterThanOrEqual(20)
    for (const op of operators) {
      expect(op.label.trim().length).toBeGreaterThan(0)
      expect(op.labelEn.trim().length).toBeGreaterThan(0)
      // labelEn 必须是英文（不含 CJK），防止“英文键复制中文”
      expect(/^[\x20-\x7E]+$/.test(op.labelEn)).toBe(true)
    }
  })

  it('同组内 value 唯一，跨组同 value 的英文标签可不同（date/number 语义差异）', () => {
    for (const [group, ops] of Object.entries(ADVANCED_SEARCH_OPERATOR_GROUPS)) {
      const values = ops.map(op => op.value)
      expect(new Set(values).size).toBe(values.length)
      // date 组的 greater_than 是“晚于/After”而非“大于”
      if (group === 'date') {
        const after = ops.find(op => op.value === 'greater_than')
        expect(after?.labelEn).toBe('After')
      }
    }
  })
})

describe('操作符展示名按 locale 解析（稳定值映射，禁中文匹配）', () => {
  it('zh-CN 返回中文 label，en 返回契约 labelEn', () => {
    setLocale('zh-CN')
    expect(getOperatorLabel('contains')).toBe('包含')
    setLocale('en')
    expect(getOperatorLabel('contains')).toBe('Contains')
    expect(getOperatorLabel('last_days')).toBe('Last N days')
    setLocale('zh-CN')
    expect(getOperatorLabel('last_days')).toBe('最近N天')
  })

  it('操作符分组标题随语言切换', () => {
    setLocale('zh-CN')
    expect(getOperatorGroupsForField('name')[0].label).toBe('基本操作')
    setLocale('en')
    expect(getOperatorGroupsForField('name')[0].label).toBe('Basic operators')
    // 分组内容始终按稳定 backendValue 过滤，不随语言漂移
    const zhOps = getOperatorGroupsForField('name')[0].operators.map(o => o.backendValue)
    setLocale('zh-CN')
    const enOps = getOperatorGroupsForField('name')[0].operators.map(o => o.backendValue)
    expect(enOps).toEqual(zhOps)
  })
})

describe('字段与摘要文本两语言输出', () => {
  it('字段展示名按稳定字段 code 取键', () => {
    const tags = getSearchFieldInfo('tags')
    expect(tags).toBeDefined()
    setLocale('zh-CN')
    expect(searchFieldLabel(tags!)).toBe('标签')
    setLocale('en')
    expect(searchFieldLabel(tags!)).toBe('Tags')
  })

  it('条件摘要包含字段名/操作符/值与排除后缀', () => {
    const condition = {
      id: 'c1',
      field: 'tags',
      operator: 'contains_any',
      value: ['movie'],
      mode: 'exclude' as const
    }
    setLocale('zh-CN')
    expect(describeCondition(condition)).toBe('标签 包含任意 movie（排除）')
    setLocale('en')
    expect(describeCondition(condition)).toBe('Tags Contains any movie (excluded)')
  })

  it('空值与无限制区间摘要两语言', () => {
    // is_null：操作符展示名与空值摘要均为「未设置」，既有行为保留（不做去重语义变更）
    setLocale('zh-CN')
    expect(
      describeCondition({ id: 'c1', field: 'completed_date', operator: 'is_null', value: null, mode: 'include' })
    ).toBe('完成时间 未设置 未设置')
    setLocale('en')
    expect(
      describeCondition({ id: 'c1', field: 'completed_date', operator: 'is_null', value: null, mode: 'include' })
    ).toBe('Completed date Not set Not set')
  })

  it('预览文本（含条件组回退名）两语言', () => {
    const groups: AdvancedSearchGroupState[] = [
      {
        id: 'g1',
        logic: 'and',
        conditions: [
          { id: 'c1', field: 'name', operator: 'contains', value: '4K', mode: 'include' }
        ]
      }
    ]
    setLocale('zh-CN')
    expect(buildGroupsQueryText(groups)).toBe('【条件组1】(包含: 种子名称 包含 4K)')
    setLocale('en')
    expect(buildGroupsQueryText(groups)).toBe('【Group 1】(Include: Torrent name Contains 4K)')
    expect(buildGroupsQueryText([])).toBe('No search conditions')
  })

  it('静态值候选（超级做种三态）随语言解析，值恒为稳定码', () => {
    const dynamic = { categoryOptions: [], tagOptions: [], downloaderOptions: [] }
    setLocale('zh-CN')
    expect(getSearchFieldOptions('super_seeding', dynamic)).toEqual([
      { label: '是', value: '1' },
      { label: '否', value: '0' },
      { label: '不支持', value: 'unsupported' }
    ])
    setLocale('en')
    expect(getSearchFieldOptions('super_seeding', dynamic)).toEqual([
      { label: 'Yes', value: '1' },
      { label: 'No', value: '0' },
      { label: 'Unsupported', value: 'unsupported' }
    ])
  })

  it('状态字段候选展示名走共享状态文本，value 为稳定状态码', () => {
    const dynamic = { categoryOptions: [], tagOptions: [], downloaderOptions: [] }
    setLocale('zh-CN')
    const zh = getSearchFieldOptions('status', dynamic)
    expect(zh).toContainEqual(expect.objectContaining({ label: '做种中', value: 'seeding' }))
    setLocale('en')
    const en = getSearchFieldOptions('status', dynamic)
    expect(en).toContainEqual(expect.objectContaining({ label: 'Seeding', value: 'seeding' }))
    expect(en.map(o => o.value)).toEqual(zh.map(o => o.value))
  })

  it('模板归一化错误消息本地化', () => {
    setLocale('zh-CN')
    expect(() => normalizeLoadedGroups([{ id: 'g1', logic: 'and', conditions: [] }])).toThrow(
      '模板条件组1没有有效条件'
    )
    setLocale('en')
    expect(() => normalizeLoadedGroups([{ id: 'g1', logic: 'and', conditions: [] }])).toThrow(
      'Template group 1 has no valid conditions'
    )
  })
})

describe('语言切换不改变业务参数（T01 搜索参数不变性）', () => {
  const makeGroups = (): AdvancedSearchGroupState[] => [
    {
      id: 'g1',
      name: '',
      logic: 'and',
      betweenGroupLogic: 'and',
      editing: false,
      conditions: [
        { id: 'c1', field: 'name', operator: 'contains', value: '4K', mode: 'include' },
        { id: 'c2', field: 'tags', operator: 'contains_any', value: ['movie', 'tv'], mode: 'exclude' },
        { id: 'c3', field: 'size', operator: 'between', value: { min: 1, max: null, minUnit: 'GB', maxUnit: 'GB' }, mode: 'include' },
        { id: 'c4', field: 'status', operator: 'in', value: ['seeding', 'paused'], mode: 'include' },
        { id: 'c5', field: 'added_date', operator: 'last_days', value: { days: 7 }, mode: 'include' }
      ]
    }
  ]

  it('两种语言下 buildAdvancedSearchParams 的 groups 完全一致', () => {
    setLocale('zh-CN')
    const zhParams = buildAdvancedSearchParams(makeGroups())
    setLocale('en')
    const enParams = buildAdvancedSearchParams(makeGroups())

    expect(enParams.groups).toBe(zhParams.groups)
    const parsed = JSON.parse(enParams.groups)
    expect(parsed[0].conditions).toEqual([
      expect.objectContaining({ field: 'name', operator: 'contains', value: '4K', mode: 'include' }),
      expect.objectContaining({ field: 'tags', operator: 'contains_any', value: ['movie', 'tv'], mode: 'exclude' }),
      expect.objectContaining({ field: 'size', operator: 'between' }),
      expect.objectContaining({ field: 'status', operator: 'in', value: ['seeding', 'paused'] }),
      expect.objectContaining({ field: 'added_date', operator: 'last_days', value: { days: 7 } })
    ])
  })

  it('归一化后的条件组（含历史 contains→contains_any 升级）在两语言下等价', () => {
    const legacy = (): AdvancedSearchGroupState[] => [
      {
        id: 'g1',
        logic: 'and',
        conditions: [
          { id: 'c1', field: 'tags', operator: 'contains', value: '电影, 音乐', mode: 'include' }
        ]
      } as AdvancedSearchGroupState
    ]
    setLocale('zh-CN')
    const zh = JSON.stringify(normalizeLoadedGroups(legacy()).map(g => g.conditions))
    setLocale('en')
    const en = JSON.stringify(normalizeLoadedGroups(legacy()).map(g => g.conditions))
    expect(en).toBe(zh)
    expect(JSON.parse(en)[0]).toEqual([
      expect.objectContaining({ operator: 'contains_any', value: ['电影', '音乐'] })
    ])
  })
})
