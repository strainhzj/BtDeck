import {
  ADVANCED_SEARCH_FIELDS,
  ADVANCED_SEARCH_MAX_REGEX_CONDITIONS,
  ADVANCED_SEARCH_MAX_REGEX_PATTERN_LENGTH,
  ADVANCED_SEARCH_NEGATED_OPERATORS,
  ADVANCED_SEARCH_OPERATOR_MAPPING,
  ADVANCED_SEARCH_REVERSE_OPERATOR_MAPPING,
  AdvancedSearchFieldKind
} from '@/contracts/advancedSearch.generated'

export interface NumberRangeValue {
  min: number | null
  max: number | null
}

export interface SizeRangeValue extends NumberRangeValue {
  minUnit: string
  maxUnit: string
}

export interface SizeValue {
  value: number | null
  unit: string
}

export interface DateRangeValue {
  start: string | null
  end: string | null
}

export interface LastDaysValue {
  days: number | null
}

export interface RegexValue {
  pattern: string
  caseSensitive: boolean
}

export interface WireRangeValue {
  min: number | string | null
  max: number | string | null
}

export type AdvancedSearchConditionValue =
  | null
  | string
  | number
  | boolean
  | string[]
  | NumberRangeValue
  | SizeRangeValue
  | SizeValue
  | DateRangeValue
  | LastDaysValue
  | RegexValue

export interface AdvancedSearchConditionState {
  id: string
  field: string
  operator: string
  value: AdvancedSearchConditionValue
  mode: 'include' | 'exclude'
}

export interface AdvancedSearchGroupState {
  id: string
  name?: string
  logic: 'and' | 'or'
  betweenGroupLogic?: 'and' | 'or'
  editing?: boolean
  conditions: AdvancedSearchConditionState[]
}

export interface AdvancedSearchTemplateDraft {
  id: string
  name: string
  description: string
  isDefault: boolean
  conditions: AdvancedSearchGroupState[]
  createdTime: string
}

export type AdvancedSearchWireValue =
  | string
  | number
  | string[]
  | WireRangeValue
  | DateRangeValue
  | LastDaysValue
  | RegexValue

export class AdvancedSearchValidationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AdvancedSearchValidationError'
  }
}

interface SearchConditionPayload {
  field: string
  operator: string
  value: AdvancedSearchWireValue
  mode: 'include' | 'exclude'
  index: number
}

interface SearchGroupPayload {
  id: string
  name: string
  logic: 'and' | 'or'
  conditions: SearchConditionPayload[]
  conditions_count: number
}

export interface AdvancedSearchBuilderParams {
  complex_search: true
  groups_count: number
  groups: string
  between_group_logics: string
}

const SIZE_MULTIPLIERS: Readonly<Record<string, number>> = Object.freeze({
  B: 1,
  KB: 1024,
  MB: 1024 ** 2,
  GB: 1024 ** 3,
  TB: 1024 ** 4
})

const LOCAL_DATE_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2}))?$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function finiteNonNegative(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new AdvancedSearchValidationError(`${label}必须是有限的非负数`)
  }
  return value
}

function nullableFiniteNonNegative(
  value: unknown,
  label: string
): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }
  return finiteNonNegative(value, label)
}

function sizeInBytes(value: number, unit: string, label: string): number {
  const multiplier = SIZE_MULTIPLIERS[unit]
  if (!multiplier) {
    throw new AdvancedSearchValidationError(`${label}的单位无效`)
  }
  return value * multiplier
}

function validLocalDate(value: unknown, label: string): string {
  if (typeof value !== 'string') {
    throw new AdvancedSearchValidationError(`${label}必须是本地日期字符串`)
  }
  const match = LOCAL_DATE_PATTERN.exec(value)
  if (!match) {
    throw new AdvancedSearchValidationError(`${label}格式无效`)
  }
  const [, year, month, day, hour = '00', minute = '00', second = '00'] =
    match
  const parsed = new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second)
  )
  if (
    parsed.getFullYear() !== Number(year) ||
    parsed.getMonth() !== Number(month) - 1 ||
    parsed.getDate() !== Number(day) ||
    parsed.getHours() !== Number(hour) ||
    parsed.getMinutes() !== Number(minute) ||
    parsed.getSeconds() !== Number(second)
  ) {
    throw new AdvancedSearchValidationError(`${label}不是有效日期`)
  }
  return value
}

function localDateTimestamp(value: string, endOfDay: boolean): number {
  const match = LOCAL_DATE_PATTERN.exec(value)
  if (!match) return Number.NaN
  const [, year, month, day, rawHour, rawMinute, rawSecond] = match
  const dateOnly = rawHour === undefined
  return new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    dateOnly && endOfDay ? 23 : Number(rawHour || 0),
    dateOnly && endOfDay ? 59 : Number(rawMinute || 0),
    dateOnly && endOfDay ? 59 : Number(rawSecond || 0)
  ).getTime()
}

export function defaultConditionValue(
  field: string,
  fieldKind: AdvancedSearchFieldKind | undefined,
  operator: string
): AdvancedSearchConditionValue {
  if (!field || !fieldKind) return null
  if (field === 'size') {
    return operator === 'between'
      ? { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
      : { value: null, unit: 'GB' }
  }
  if (operator === 'regex') {
    return { pattern: '', caseSensitive: false }
  }
  if (operator === 'last_days') {
    return { days: null }
  }
  if (
    operator === 'date_range' ||
    (operator === 'between' && fieldKind === 'date')
  ) {
    return { start: null, end: null }
  }
  if (operator === 'between') {
    return { min: null, max: null }
  }
  if (fieldKind === 'multiSelect') {
    return []
  }
  return null
}

/**
 * The parent builder owns every structural state transition. The child input
 * only mirrors this value and emits user edits.
 */
export function transitionConditionValue(
  field: string,
  fieldKind: AdvancedSearchFieldKind | undefined,
  operator: string
): AdvancedSearchConditionValue {
  return defaultConditionValue(field, fieldKind, operator)
}

function parseStructuredValue(value: unknown): Record<string, unknown> {
  if (isRecord(value)) return value
  if (typeof value === 'string') {
    try {
      const parsed: unknown = JSON.parse(value)
      if (isRecord(parsed)) return parsed
    } catch (_error) {
      // Report one stable validation error below.
    }
  }
  throw new AdvancedSearchValidationError('模板中的条件值结构无效')
}

function legacyNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  throw new AdvancedSearchValidationError('模板中的数值无效')
}

export function normalizeLoadedConditionValue(
  field: string,
  fieldKind: AdvancedSearchFieldKind,
  operator: string,
  value: unknown
): AdvancedSearchConditionValue {
  if (value === null || value === undefined) {
    return defaultConditionValue(field, fieldKind, operator)
  }
  if (fieldKind === 'multiSelect') {
    if (Array.isArray(value)) {
      return value.map(item => String(item).trim()).filter(Boolean)
    }
    if (typeof value === 'string') {
      return value.split(',').map(item => item.trim()).filter(Boolean)
    }
    throw new AdvancedSearchValidationError('模板中的多选值无效')
  }
  if (field === 'size') {
    if (operator === 'between') {
      const range = parseStructuredValue(value)
      return {
        min: legacyNumber(range.min),
        max: legacyNumber(range.max),
        minUnit: typeof range.minUnit === 'string' ? range.minUnit : 'GB',
        maxUnit: typeof range.maxUnit === 'string' ? range.maxUnit : 'GB'
      }
    }
    if (typeof value === 'number') {
      return { value, unit: 'GB' }
    }
    const size = parseStructuredValue(value)
    return {
      value: legacyNumber(
        Object.prototype.hasOwnProperty.call(size, 'value')
          ? size.value
          : size.min
      ),
      unit: typeof size.unit === 'string'
        ? size.unit
        : typeof size.minUnit === 'string'
          ? size.minUnit
          : 'GB'
    }
  }
  if (operator === 'regex') {
    if (typeof value === 'string' && !value.trim().startsWith('{')) {
      return { pattern: value, caseSensitive: false }
    }
    const regexValue = parseStructuredValue(value)
    return {
      pattern:
        typeof regexValue.pattern === 'string' ? regexValue.pattern : '',
      caseSensitive: Boolean(regexValue.caseSensitive)
    }
  }
  if (operator === 'last_days') {
    if (typeof value === 'number') return { days: value }
    const lastDays = parseStructuredValue(value)
    return { days: legacyNumber(lastDays.days) }
  }
  if (
    operator === 'date_range' ||
    (operator === 'between' && fieldKind === 'date')
  ) {
    const range = parseStructuredValue(value)
    return {
      start: typeof range.start === 'string' ? range.start : null,
      end: typeof range.end === 'string' ? range.end : null
    }
  }
  if (operator === 'between') {
    const range = parseStructuredValue(value)
    return {
      min: legacyNumber(range.min),
      max: legacyNumber(range.max)
    }
  }
  if (fieldKind === 'number') {
    return legacyNumber(value)
  }
  if (fieldKind === 'boolean') {
    if (value === true || value === 'true' || value === 1 || value === '1') {
      return true
    }
    if (
      value === false ||
      value === 'false' ||
      value === 0 ||
      value === '0'
    ) {
      return false
    }
    throw new AdvancedSearchValidationError('模板中的布尔值无效')
  }
  if (typeof value !== 'string') {
    throw new AdvancedSearchValidationError('模板中的文本值无效')
  }
  return value
}

export function normalizeLoadedOperator(
  field: string,
  operator: string
): string {
  let frontendOperator = ADVANCED_SEARCH_OPERATOR_MAPPING[operator]
    ? operator
    : ADVANCED_SEARCH_REVERSE_OPERATOR_MAPPING[operator]
  if (!frontendOperator) {
    throw new AdvancedSearchValidationError(
      `模板包含未知操作符：${operator || '未选择'}`
    )
  }
  if (field === 'category' || field === 'downloader_name') {
    if (
      frontendOperator === 'contains_any' ||
      frontendOperator === 'contains_all'
    ) {
      frontendOperator = 'in'
    } else if (
      frontendOperator === 'not_contains_any' ||
      frontendOperator === 'not_contains_all'
    ) {
      frontendOperator = 'not_in'
    }
  }
  return frontendOperator
}

export function resolveBackendOperator(
  frontendOperator: string,
  mode: 'include' | 'exclude'
): string {
  const backendOperator = ADVANCED_SEARCH_OPERATOR_MAPPING[frontendOperator]
  if (!backendOperator) {
    throw new AdvancedSearchValidationError(
      `未知搜索操作符：${frontendOperator || '未选择'}`
    )
  }
  if (mode === 'include') return backendOperator
  const negated = ADVANCED_SEARCH_NEGATED_OPERATORS[backendOperator]
  if (!negated) {
    throw new AdvancedSearchValidationError(
      `操作符“${frontendOperator}”不支持排除模式`
    )
  }
  return negated
}

export function operatorSupportsExclude(frontendOperator: string): boolean {
  const backendOperator = ADVANCED_SEARCH_OPERATOR_MAPPING[frontendOperator]
  return Boolean(
    backendOperator && ADVANCED_SEARCH_NEGATED_OPERATORS[backendOperator]
  )
}

export function formatConditionValue(
  field: string,
  fieldKind: AdvancedSearchFieldKind,
  operator: string,
  value: unknown
): AdvancedSearchWireValue {
  if (field === 'size' && operator === 'between') {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError('种子大小范围结构无效')
    }
    const min = nullableFiniteNonNegative(value.min, '最小大小')
    const max = nullableFiniteNonNegative(value.max, '最大大小')
    if (min === null && max === null) {
      throw new AdvancedSearchValidationError('大小范围至少填写一个边界')
    }
    const minUnit = typeof value.minUnit === 'string' ? value.minUnit : 'GB'
    const maxUnit = typeof value.maxUnit === 'string' ? value.maxUnit : 'GB'
    if (
      min !== null &&
      max !== null &&
      sizeInBytes(min, minUnit, '最小大小') >
        sizeInBytes(max, maxUnit, '最大大小')
    ) {
      throw new AdvancedSearchValidationError('大小范围最小值不能大于最大值')
    }
    return {
      min: min === null ? null : `${min} ${minUnit}`,
      max: max === null ? null : `${max} ${maxUnit}`
    }
  }

  if (field === 'size') {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError('种子大小结构无效')
    }
    const numeric = finiteNonNegative(value.value, '种子大小')
    const unit = typeof value.unit === 'string' ? value.unit : 'GB'
    sizeInBytes(numeric, unit, '种子大小')
    return `${numeric} ${unit}`
  }

  if (operator === 'regex') {
    if (
      !isRecord(value) ||
      typeof value.pattern !== 'string' ||
      typeof value.caseSensitive !== 'boolean'
    ) {
      throw new AdvancedSearchValidationError('正则条件结构无效')
    }
    if (!value.pattern) {
      throw new AdvancedSearchValidationError('正则表达式不能为空')
    }
    if (value.pattern.length > ADVANCED_SEARCH_MAX_REGEX_PATTERN_LENGTH) {
      throw new AdvancedSearchValidationError(
        `正则表达式不能超过${ADVANCED_SEARCH_MAX_REGEX_PATTERN_LENGTH}个字符`
      )
    }
    try {
      // Browser-side syntax feedback; backend remains authoritative.
      new RegExp(value.pattern)
    } catch (_error) {
      throw new AdvancedSearchValidationError('正则表达式语法无效')
    }
    return {
      pattern: value.pattern,
      caseSensitive: value.caseSensitive
    }
  }

  if (operator === 'last_days') {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError('最近天数结构无效')
    }
    const days = value.days
    if (
      typeof days !== 'number' ||
      !Number.isInteger(days) ||
      days < 1 ||
      days > 36500
    ) {
      throw new AdvancedSearchValidationError('最近天数必须是1到36500的整数')
    }
    return { days }
  }

  if (
    operator === 'date_range' ||
    (operator === 'between' && fieldKind === 'date')
  ) {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError('日期范围结构无效')
    }
    const start =
      value.start === null || value.start === ''
        ? null
        : validLocalDate(value.start, '开始日期')
    const end =
      value.end === null || value.end === ''
        ? null
        : validLocalDate(value.end, '结束日期')
    if (start === null && end === null) {
      throw new AdvancedSearchValidationError('日期范围至少填写一个边界')
    }
    if (
      start !== null &&
      end !== null &&
      localDateTimestamp(start, false) > localDateTimestamp(end, true)
    ) {
      throw new AdvancedSearchValidationError('开始日期不能晚于结束日期')
    }
    return { start, end }
  }

  if (operator === 'between') {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError('数值范围结构无效')
    }
    const min = nullableFiniteNonNegative(value.min, '最小值')
    const max = nullableFiniteNonNegative(value.max, '最大值')
    if (min === null && max === null) {
      throw new AdvancedSearchValidationError('数值范围至少填写一个边界')
    }
    if (min !== null && max !== null && min > max) {
      throw new AdvancedSearchValidationError('最小值不能大于最大值')
    }
    return { min, max }
  }

  if (fieldKind === 'number') {
    return finiteNonNegative(value, '数值')
  }

  if (fieldKind === 'date') {
    return validLocalDate(value, '日期')
  }

  if (fieldKind === 'multiSelect') {
    if (
      !Array.isArray(value) ||
      value.length === 0 ||
      value.some(item => typeof item !== 'string' || !item.trim())
    ) {
      throw new AdvancedSearchValidationError('多选条件至少选择一个有效值')
    }
    return value.map(item => item.trim())
  }

  if (fieldKind === 'boolean') {
    if (typeof value !== 'boolean') {
      throw new AdvancedSearchValidationError('布尔条件必须明确选择是或否')
    }
    return value ? '1' : '0'
  }

  if (typeof value !== 'string' || !value.trim()) {
    throw new AdvancedSearchValidationError('条件值不能为空')
  }
  return value
}

export function buildAdvancedSearchParams(
  groups: AdvancedSearchGroupState[]
): AdvancedSearchBuilderParams {
  if (!Array.isArray(groups) || groups.length === 0) {
    throw new AdvancedSearchValidationError('至少需要一个条件组')
  }

  let regexCount = 0
  const groupsData: SearchGroupPayload[] = groups.map((group, groupIndex) => {
    if (group.logic !== 'and' && group.logic !== 'or') {
      throw new AdvancedSearchValidationError(
        `条件组${groupIndex + 1}的组内逻辑无效`
      )
    }
    if (!Array.isArray(group.conditions) || group.conditions.length === 0) {
      throw new AdvancedSearchValidationError(
        `条件组${groupIndex + 1}至少需要一个条件`
      )
    }
    const conditions = group.conditions.map((condition, conditionIndex) => {
      const field = ADVANCED_SEARCH_FIELDS[condition.field]
      if (!field) {
        throw new AdvancedSearchValidationError(
          `条件组${groupIndex + 1}第${conditionIndex + 1}项未选择有效字段`
        )
      }
      const backendOperator = resolveBackendOperator(
        condition.operator,
        condition.mode
      )
      if (!field.operators.includes(backendOperator)) {
        throw new AdvancedSearchValidationError(
          `字段“${condition.field}”不支持操作符“${condition.operator}”`
        )
      }
      const payload: SearchConditionPayload = {
        field: condition.field,
        operator: backendOperator,
        value: formatConditionValue(
          condition.field,
          field.kind,
          condition.operator,
          condition.value
        ),
        mode: condition.mode,
        index: conditionIndex
      }
      if (payload.operator === 'regex') regexCount += 1
      return payload
    })
    return {
      id: group.id,
      name: group.name || `条件组${groupIndex + 1}`,
      logic: group.logic,
      conditions,
      conditions_count: conditions.length
    }
  })

  if (regexCount > ADVANCED_SEARCH_MAX_REGEX_CONDITIONS) {
    throw new AdvancedSearchValidationError(
      `正则条件最多允许${ADVANCED_SEARCH_MAX_REGEX_CONDITIONS}个`
    )
  }

  const betweenGroupLogics: Array<'and' | 'or'> = []
  for (let index = 0; index < groups.length - 1; index++) {
    const betweenLogic = groups[index].betweenGroupLogic
    if (betweenLogic !== 'and' && betweenLogic !== 'or') {
      throw new AdvancedSearchValidationError(
        `条件组${index + 1}缺少有效的组间逻辑`
      )
    }
    betweenGroupLogics.push(betweenLogic)
  }

  return {
    complex_search: true,
    groups_count: groupsData.length,
    groups: JSON.stringify(groupsData),
    between_group_logics: JSON.stringify(betweenGroupLogics)
  }
}
