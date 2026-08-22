/**
 * Runtime contract guard for advanced search.
 *
 * The backend JSON is the single source. The frontend imports generated
 * values, and these tests execute the same conversion/validation functions
 * used by AdvancedSearchBuilder and template application.
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'

import {
  ADVANCED_SEARCH_FIELDS,
  ADVANCED_SEARCH_NEGATED_OPERATORS,
  ADVANCED_SEARCH_OPERATOR_GROUPS,
  ADVANCED_SEARCH_OPERATOR_MAPPING
} from '@/contracts/advancedSearch.generated'
import {
  AdvancedSearchValidationError,
  buildAdvancedSearchParams,
  formatConditionValue,
  normalizeLoadedConditionValue,
  normalizeLoadedOperator,
  resolveBackendOperator,
  transitionConditionValue
} from '@/components/torrents/advancedSearchState'

interface BackendContract {
  fields: Record<string, { kind: string, operators: string[] }>
  operatorGroups: Record<
    string,
    Array<{ value: string, label: string, backendValue: string }>
  >
  negatedOperators: Record<string, string>
}

const backendContract = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      '../../../backend/app/contracts/advanced_search_contract.json'
    ),
    'utf8'
  )
) as BackendContract

describe('高级搜索运行时契约', () => {
  test('生成的字段、操作符组和排除映射与后端 JSON 完全一致', () => {
    expect(ADVANCED_SEARCH_FIELDS).toEqual(backendContract.fields)
    expect(ADVANCED_SEARCH_OPERATOR_GROUPS).toEqual(
      backendContract.operatorGroups
    )
    expect(ADVANCED_SEARCH_NEGATED_OPERATORS).toEqual(
      backendContract.negatedOperators
    )
  })

  test('状态字段使用多选契约并兼容旧模板的单值 equals', () => {
    expect(ADVANCED_SEARCH_FIELDS.status.kind).toBe('multiSelect')
    expect(normalizeLoadedOperator('status', 'equals')).toBe('in')
    expect(normalizeLoadedOperator('status', 'ne')).toBe('not_in')
    expect(
      normalizeLoadedConditionValue('status', 'multiSelect', 'in', 'paused')
    ).toEqual(['paused'])
  })

  test('历史标签标量操作符归一化为完整 token 多选语义', () => {
    expect(normalizeLoadedOperator('tags', 'contains')).toBe('contains_any')
    expect(normalizeLoadedOperator('tags', 'ne')).toBe('not_contains_any')
    expect(
      normalizeLoadedConditionValue(
        'tags',
        'multiSelect',
        'contains_any',
        '辅种'
      )
    ).toEqual(['辅种'])
  })

  test('每个 UI 操作符都显式映射，且至少被一个字段允许', () => {
    const operators = Object.values(ADVANCED_SEARCH_OPERATOR_GROUPS).flat()
    expect(operators.length).toBeGreaterThanOrEqual(20)

    for (const operator of operators) {
      expect(operator.backendValue).toBeTruthy()
      expect(
        Object.values(ADVANCED_SEARCH_FIELDS).some(field =>
          field.operators.includes(operator.backendValue)
        )
      ).toBe(true)
      expect(
        ADVANCED_SEARCH_OPERATOR_MAPPING[operator.value]
      ).toBe(operator.backendValue)
      expect(operator).not.toHaveProperty('fallback')
    }
  })

  test('所有排除映射可逆，且字段允许原操作符时也允许反操作符', () => {
    for (const [operator, negated] of Object.entries(
      ADVANCED_SEARCH_NEGATED_OPERATORS
    )) {
      expect(ADVANCED_SEARCH_NEGATED_OPERATORS[negated]).toBe(operator)
      for (const field of Object.values(ADVANCED_SEARCH_FIELDS)) {
        if (field.operators.includes(operator)) {
          expect(field.operators).toContain(negated)
        }
      }
    }
  })

  test('未知操作符和不可排除操作符不会降级', () => {
    expect(() => resolveBackendOperator('unknown', 'include')).toThrow(
      AdvancedSearchValidationError
    )
    expect(() => resolveBackendOperator('regex', 'exclude')).toThrow(
      '不支持排除模式'
    )
  })

  test('父状态机执行 scalar/range/list 的确定性转换', () => {
    expect(transitionConditionValue('size', 'number', 'between')).toEqual({
      min: null,
      max: null,
      minUnit: 'GB',
      maxUnit: 'GB'
    })
    expect(transitionConditionValue('size', 'number', 'equals')).toEqual({
      value: null,
      unit: 'GB'
    })
    expect(transitionConditionValue('ratio', 'number', 'between')).toEqual({
      min: null,
      max: null
    })
    expect(transitionConditionValue('category', 'multiSelect', 'in')).toEqual(
      []
    )
  })

  test('格式化保留单边区间，拒绝 NaN、空区间和静默数组包装', () => {
    expect(
      formatConditionValue('ratio', 'number', 'between', {
        min: 1,
        max: null
      })
    ).toEqual({ min: 1, max: null })
    expect(() =>
      formatConditionValue('ratio', 'number', 'equals', Number.NaN)
    ).toThrow('有限的非负数')
    expect(() =>
      formatConditionValue('ratio', 'number', 'between', {
        min: null,
        max: null
      })
    ).toThrow('至少填写一个边界')
    expect(() =>
      formatConditionValue('category', 'multiSelect', 'in', 'movie')
    ).toThrow('至少选择一个有效值')
    expect(
      formatConditionValue('added_date', 'date', 'date_range', {
        start: '2026-01-01 12:00:00',
        end: '2026-01-01'
      })
    ).toEqual({
      start: '2026-01-01 12:00:00',
      end: '2026-01-01'
    })
  })

  test('构建协议保留排除模式，由后端对正向操作符取严格补集', () => {
    const params = buildAdvancedSearchParams([
      {
        id: 'g1',
        logic: 'and',
        conditions: [
          {
            id: 'c1',
            field: 'tags',
            operator: 'contains_any',
            value: ['movie'],
            mode: 'exclude'
          },
          {
            id: 'c2',
            field: 'added_date',
            operator: 'date_range',
            value: { start: '2026-01-01', end: null },
            mode: 'include'
          }
        ]
      }
    ])
    const groups = JSON.parse(params.groups) as Array<{
      conditions: Array<{ operator: string, value: unknown }>
    }>

    expect(groups[0].conditions).toEqual([
      expect.objectContaining({
        operator: 'contains_any',
        value: ['movie'],
        mode: 'exclude'
      }),
      expect.objectContaining({
        operator: 'date_range',
        value: { start: '2026-01-01', end: null }
      })
    ])
    expect(groups[0].conditions[0]).not.toEqual(
      expect.objectContaining({ operator: 'not_contains_any' })
    )
  })

  test('超级做种使用是、否、不支持三态并兼容历史布尔模板', () => {
    expect(ADVANCED_SEARCH_FIELDS.super_seeding).toEqual({
      kind: 'select',
      operators: ['eq', 'ne']
    })
    expect(
      normalizeLoadedConditionValue(
        'super_seeding',
        'select',
        'equals',
        false
      )
    ).toBe('0')
    expect(
      formatConditionValue(
        'super_seeding',
        'select',
        'equals',
        'unsupported'
      )
    ).toBe('unsupported')
  })

  test('无值操作符不要求输入，并按字段契约限制可见范围', () => {
    expect(
      formatConditionValue('ratio_limit', 'number', 'is_null', null)
    ).toBeNull()
    expect(ADVANCED_SEARCH_FIELDS.ratio_limit.operators).toContain('is_null')
    expect(ADVANCED_SEARCH_FIELDS.category.operators).toContain('is_not_null')
    expect(ADVANCED_SEARCH_FIELDS.name.operators).not.toContain('is_null')
  })

  test.each([
    ['completed_date', 'date', 'is_null'],
    ['completed_date', 'date', 'is_not_null'],
    ['ratio', 'number', 'is_null'],
    ['ratio', 'number', 'is_not_null'],
    ['ratio_limit', 'number', 'is_null'],
    ['ratio_limit', 'number', 'is_not_null'],
    ['tags', 'multiSelect', 'is_null'],
    ['tags', 'multiSelect', 'is_not_null'],
    ['category', 'multiSelect', 'is_null'],
    ['category', 'multiSelect', 'is_not_null']
  ] as const)(
    '可空字段 %s/%s 在状态转换与序列化时始终使用 null',
    (field, kind, operator) => {
      expect(ADVANCED_SEARCH_FIELDS[field].operators).toContain(operator)
      expect(transitionConditionValue(field, kind, operator)).toBeNull()
      expect(
        formatConditionValue(field, kind, operator, '历史残留值')
      ).toBeNull()
    }
  )

  test.each([
    ['name', 'text'],
    ['size', 'number'],
    ['status', 'multiSelect'],
    ['added_date', 'date'],
    ['downloader_name', 'multiSelect'],
    ['super_seeding', 'select'],
    ['tracker_url', 'text'],
    ['enabled', 'boolean']
  ] as const)(
    '非空字段 %s/%s 不会意外继承未设置操作符',
    (field) => {
      expect(ADVANCED_SEARCH_FIELDS[field].operators).not.toContain('is_null')
      expect(ADVANCED_SEARCH_FIELDS[field].operators).not.toContain(
        'is_not_null'
      )
    }
  )

  test.each([
    ['name', 'text', 'contains', 'Avatar'],
    ['ratio', 'number', 'greater_than', 2],
    ['completed_date', 'date', 'equals', '2026-03-01'],
    ['category', 'multiSelect', 'in', ['电影']],
    ['tags', 'multiSelect', 'contains_any', ['movie']],
    ['status', 'multiSelect', 'in', ['error']],
    ['downloader_name', 'multiSelect', 'in', ['d1']],
    ['super_seeding', 'select', 'equals', 'unsupported'],
    ['tracker_url', 'text', 'contains', 'azusa']
  ] as const)(
    '排除模式矩阵保留正向操作符：%s/%s',
    (field, kind, operator, value) => {
      const conditionValue: string | number | string[] = Array.isArray(value)
        ? value.map(item => String(item))
        : value as string | number
      const params = buildAdvancedSearchParams([
        {
          id: 'g1',
          logic: 'and',
          conditions: [
            {
              id: 'c1',
              field,
              operator,
              value: conditionValue,
              mode: 'exclude'
            }
          ]
        }
      ])
      const groups = JSON.parse(params.groups) as Array<{
        conditions: Array<{
          operator: string
          value: unknown
          mode: string
        }>
      }>
      const expectedOperator = ADVANCED_SEARCH_OPERATOR_MAPPING[operator]
      if (!expectedOperator) throw new Error(`missing operator: ${operator}`)

      expect(ADVANCED_SEARCH_FIELDS[field].kind).toBe(kind)
      expect(groups[0].conditions[0]).toEqual(
        expect.objectContaining({
          operator: expectedOperator,
          mode: 'exclude'
        })
      )
      expect(groups[0].conditions[0].operator).not.toBe(
        ADVANCED_SEARCH_NEGATED_OPERATORS[expectedOperator]
      )
    }
  )
})
