import {
  ADVANCED_SEARCH_FIELDS,
  ADVANCED_SEARCH_MAX_REGEX_CONDITIONS,
  ADVANCED_SEARCH_MAX_REGEX_PATTERN_LENGTH,
  ADVANCED_SEARCH_NEGATED_OPERATORS,
  ADVANCED_SEARCH_OPERATOR_MAPPING,
  ADVANCED_SEARCH_REVERSE_OPERATOR_MAPPING,
  AdvancedSearchFieldKind
} from '@/contracts/advancedSearch.generated'
import { translate } from '@/i18n'

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
  | null
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

const EXACT_MULTI_SELECT_FIELDS = new Set([
  'status',
  'category',
  'downloader_name'
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function finiteNonNegative(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new AdvancedSearchValidationError(translate('search.validation.mustBeFinite', { label }))
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
    throw new AdvancedSearchValidationError(translate('search.validation.invalidUnit', { label }))
  }
  return value * multiplier
}

function validLocalDate(value: unknown, label: string): string {
  if (typeof value !== 'string') {
    throw new AdvancedSearchValidationError(translate('search.validation.mustBeLocalDate', { label }))
  }
  const match = LOCAL_DATE_PATTERN.exec(value)
  if (!match) {
    throw new AdvancedSearchValidationError(translate('search.validation.invalidFormat', { label }))
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
    throw new AdvancedSearchValidationError(translate('search.validation.invalidDate', { label }))
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
  if (operator === 'is_null' || operator === 'is_not_null') return null
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
  throw new AdvancedSearchValidationError(translate('search.validation.tplValueStructure'))
}

function legacyNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  throw new AdvancedSearchValidationError(translate('search.validation.tplNumber'))
}

export function normalizeLoadedConditionValue(
  field: string,
  fieldKind: AdvancedSearchFieldKind,
  operator: string,
  value: unknown
): AdvancedSearchConditionValue {
  if (operator === 'is_null' || operator === 'is_not_null') return null
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
    throw new AdvancedSearchValidationError(translate('search.validation.tplMultiSelect'))
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
  if (field === 'super_seeding') {
    if (value === true || value === 'true' || value === 1 || value === '1') {
      return '1'
    }
    if (
      value === false ||
      value === 'false' ||
      value === 0 ||
      value === '0'
    ) {
      return '0'
    }
    if (value === 'unsupported' || value === 'unknown') {
      return 'unsupported'
    }
    throw new AdvancedSearchValidationError(translate('search.validation.tplSuperSeeding'))
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
    throw new AdvancedSearchValidationError(translate('search.validation.tplBoolean'))
  }
  if (typeof value !== 'string') {
    throw new AdvancedSearchValidationError(translate('search.validation.tplText'))
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
      translate('search.validation.tplUnknownOperator', {
        operator: operator || translate('search.validation.notSelected')
      })
    )
  }
  if (field === 'tags') {
    if (
      frontendOperator === 'equals' ||
      frontendOperator === 'contains' ||
      frontendOperator === 'in'
    ) {
      return 'contains_any'
    }
    if (
      frontendOperator === 'not_equals' ||
      frontendOperator === 'not_contains' ||
      frontendOperator === 'not_in'
    ) {
      return 'not_contains_any'
    }
  }
  if (EXACT_MULTI_SELECT_FIELDS.has(field)) {
    if (
      frontendOperator === 'equals' ||
      frontendOperator === 'contains_any' ||
      frontendOperator === 'contains_all'
    ) {
      frontendOperator = 'in'
    } else if (
      frontendOperator === 'not_equals' ||
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
      translate('search.validation.unknownOperator', {
        operator: frontendOperator || translate('search.validation.notSelected')
      })
    )
  }
  if (mode === 'include') return backendOperator
  const negated = ADVANCED_SEARCH_NEGATED_OPERATORS[backendOperator]
  if (!negated) {
    throw new AdvancedSearchValidationError(
      translate('search.validation.operatorNoExclude', { operator: frontendOperator })
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
  if (operator === 'is_null' || operator === 'is_not_null') return null

  if (field === 'size' && operator === 'between') {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError(translate('search.validation.sizeRangeStructure'))
    }
    const min = nullableFiniteNonNegative(value.min, translate('search.validation.labelMinSize'))
    const max = nullableFiniteNonNegative(value.max, translate('search.validation.labelMaxSize'))
    if (min === null && max === null) {
      throw new AdvancedSearchValidationError(translate('search.validation.sizeRangeOneBound'))
    }
    const minUnit = typeof value.minUnit === 'string' ? value.minUnit : 'GB'
    const maxUnit = typeof value.maxUnit === 'string' ? value.maxUnit : 'GB'
    if (
      min !== null &&
      max !== null &&
      sizeInBytes(min, minUnit, translate('search.validation.labelMinSize')) >
        sizeInBytes(max, maxUnit, translate('search.validation.labelMaxSize'))
    ) {
      throw new AdvancedSearchValidationError(translate('search.validation.sizeRangeMinMax'))
    }
    return {
      min: min === null ? null : `${min} ${minUnit}`,
      max: max === null ? null : `${max} ${maxUnit}`
    }
  }

  if (field === 'size') {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError(translate('search.validation.sizeStructure'))
    }
    const numeric = finiteNonNegative(value.value, translate('search.validation.labelTorrentSize'))
    const unit = typeof value.unit === 'string' ? value.unit : 'GB'
    sizeInBytes(numeric, unit, translate('search.validation.labelTorrentSize'))
    return `${numeric} ${unit}`
  }

  if (operator === 'regex') {
    if (
      !isRecord(value) ||
      typeof value.pattern !== 'string' ||
      typeof value.caseSensitive !== 'boolean'
    ) {
      throw new AdvancedSearchValidationError(translate('search.validation.regexStructure'))
    }
    if (!value.pattern) {
      throw new AdvancedSearchValidationError(translate('search.validation.regexEmpty'))
    }
    if (value.pattern.length > ADVANCED_SEARCH_MAX_REGEX_PATTERN_LENGTH) {
      throw new AdvancedSearchValidationError(
        translate('search.validation.regexTooLong', { max: ADVANCED_SEARCH_MAX_REGEX_PATTERN_LENGTH })
      )
    }
    try {
      // Browser-side syntax feedback; backend remains authoritative.
      new RegExp(value.pattern)
    } catch (_error) {
      throw new AdvancedSearchValidationError(translate('search.validation.regexSyntax'))
    }
    return {
      pattern: value.pattern,
      caseSensitive: value.caseSensitive
    }
  }

  if (operator === 'last_days') {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError(translate('search.validation.lastDaysStructure'))
    }
    const days = value.days
    if (
      typeof days !== 'number' ||
      !Number.isInteger(days) ||
      days < 1 ||
      days > 36500
    ) {
      throw new AdvancedSearchValidationError(translate('search.validation.lastDaysRange'))
    }
    return { days }
  }

  if (
    operator === 'date_range' ||
    (operator === 'between' && fieldKind === 'date')
  ) {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError(translate('search.validation.dateRangeStructure'))
    }
    const start =
      value.start === null || value.start === ''
        ? null
        : validLocalDate(value.start, translate('search.validation.labelStartDate'))
    const end =
      value.end === null || value.end === ''
        ? null
        : validLocalDate(value.end, translate('search.validation.labelEndDate'))
    if (start === null && end === null) {
      throw new AdvancedSearchValidationError(translate('search.validation.dateRangeOneBound'))
    }
    if (
      start !== null &&
      end !== null &&
      localDateTimestamp(start, false) > localDateTimestamp(end, true)
    ) {
      throw new AdvancedSearchValidationError(translate('search.validation.dateRangeOrder'))
    }
    return { start, end }
  }

  if (operator === 'between') {
    if (!isRecord(value)) {
      throw new AdvancedSearchValidationError(translate('search.validation.numberRangeStructure'))
    }
    const min = nullableFiniteNonNegative(value.min, translate('search.validation.labelMinValue'))
    const max = nullableFiniteNonNegative(value.max, translate('search.validation.labelMaxValue'))
    if (min === null && max === null) {
      throw new AdvancedSearchValidationError(translate('search.validation.numberRangeOneBound'))
    }
    if (min !== null && max !== null && min > max) {
      throw new AdvancedSearchValidationError(translate('search.validation.numberRangeMinMax'))
    }
    return { min, max }
  }

  if (fieldKind === 'number') {
    return finiteNonNegative(value, translate('search.validation.labelNumber'))
  }

  if (fieldKind === 'date') {
    return validLocalDate(value, translate('search.validation.labelDate'))
  }

  if (fieldKind === 'multiSelect') {
    if (
      !Array.isArray(value) ||
      value.length === 0 ||
      value.some(item => typeof item !== 'string' || !item.trim())
    ) {
      throw new AdvancedSearchValidationError(translate('search.validation.multiSelectOneValue'))
    }
    return value.map(item => item.trim())
  }

  if (fieldKind === 'boolean') {
    if (typeof value !== 'boolean') {
      throw new AdvancedSearchValidationError(translate('search.validation.boolRequired'))
    }
    return value ? '1' : '0'
  }

  if (typeof value !== 'string' || !value.trim()) {
    throw new AdvancedSearchValidationError(translate('search.validation.valueRequired'))
  }
  return value
}

export function buildAdvancedSearchParams(
  groups: AdvancedSearchGroupState[]
): AdvancedSearchBuilderParams {
  if (!Array.isArray(groups) || groups.length === 0) {
    throw new AdvancedSearchValidationError(translate('search.validation.groupsRequired'))
  }

  let regexCount = 0
  const groupsData: SearchGroupPayload[] = groups.map((group, groupIndex) => {
    if (group.logic !== 'and' && group.logic !== 'or') {
      throw new AdvancedSearchValidationError(
        translate('search.validation.groupLogicInvalid', { index: groupIndex + 1 })
      )
    }
    if (!Array.isArray(group.conditions) || group.conditions.length === 0) {
      throw new AdvancedSearchValidationError(
        translate('search.validation.groupNoConditions', { index: groupIndex + 1 })
      )
    }
    const conditions = group.conditions.map((condition, conditionIndex) => {
      const field = ADVANCED_SEARCH_FIELDS[condition.field]
      if (!field) {
        throw new AdvancedSearchValidationError(
          translate('search.validation.condNoField', {
            group: groupIndex + 1,
            cond: conditionIndex + 1
          })
        )
      }
      if (
        condition.mode === 'exclude' &&
        !operatorSupportsExclude(condition.operator)
      ) {
        throw new AdvancedSearchValidationError(
          translate('search.validation.condNoExclude', { operator: condition.operator })
        )
      }
      const backendOperator = resolveBackendOperator(
        condition.operator,
        'include'
      )
      if (!field.operators.includes(backendOperator)) {
        throw new AdvancedSearchValidationError(
          translate('search.validation.fieldNoOperator', {
            field: condition.field,
            operator: condition.operator
          })
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
      // 回退组名进入 API 载荷（groups[].name），属业务参数而非展示文案：
      // 保持内联中文与后端预设组名同一语义层（T01 两语言 groups 完全一致）。
      name: group.name || `条件组${groupIndex + 1}`,
      logic: group.logic,
      conditions,
      conditions_count: conditions.length
    }
  })

  if (regexCount > ADVANCED_SEARCH_MAX_REGEX_CONDITIONS) {
    throw new AdvancedSearchValidationError(
      translate('search.validation.regexTooMany', { max: ADVANCED_SEARCH_MAX_REGEX_CONDITIONS })
    )
  }

  const betweenGroupLogics: Array<'and' | 'or'> = []
  for (let index = 0; index < groups.length - 1; index++) {
    const betweenLogic = groups[index].betweenGroupLogic
    if (betweenLogic !== 'and' && betweenLogic !== 'or') {
      throw new AdvancedSearchValidationError(
        translate('search.validation.missingBetweenLogic', { index: index + 1 })
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
