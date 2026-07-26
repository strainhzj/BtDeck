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

  test('构建协议会落实排除语义并保留对象 value', () => {
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
        operator: 'not_contains_any',
        value: ['movie']
      }),
      expect.objectContaining({
        operator: 'date_range',
        value: { start: '2026-01-01', end: null }
      })
    ])
  })
})
