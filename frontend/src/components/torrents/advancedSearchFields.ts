/**
 * 高级搜索字段配置与展示共享层：桌面 AdvancedSearchBuilder 与移动端
 * MobileAdvancedSearch / ConditionEditSheet 同源消费，保证两端字段语义、
 * 操作符过滤与模板归一化行为完全一致。
 * - 字段分组/操作符分组/摘要文案/预览文本/模板归一化：纯函数；
 * - 动态候选（分类/标签/下载器）加载：两端共用同一拉取与降级语义
 *   （Promise.allSettled 部分失败静默降级，全部失败才告警）。
 * 运行时操作符语义唯一来源仍是 contracts/advancedSearch.generated.ts（后端机器契约）。
 */
import {
  ADVANCED_SEARCH_FIELDS,
  ADVANCED_SEARCH_OPERATOR_GROUPS,
  AdvancedSearchFieldKind,
  AdvancedSearchOperatorConfig
} from '@/contracts/advancedSearch.generated'
import { STATUS_OPTIONS } from '@/constants/status-config'
import { getAllCategories, getAllTags } from '@/api/tag-management'
import { getDownloaderList, DownloaderSimple } from '@/api/torrents'
import { ApiResponse } from '@/types/api'
import {
  AdvancedSearchConditionState,
  AdvancedSearchGroupState,
  AdvancedSearchValidationError,
  normalizeLoadedConditionValue,
  normalizeLoadedOperator,
  operatorSupportsExclude
} from './advancedSearchState'

// 字段定义接口（字段如何呈现与交互，区别于契约里的运算语义）
export interface SearchField {
  key: string
  label: string
  type: AdvancedSearchFieldKind
  options?: Array<{ label: string, value: string, icon?: string }>
  supportsExclude?: boolean
  /**
   * multiSelect 字段的匹配模式，决定 UI 暴露哪些操作符：
   * - 'exact'     单值精确列（status/category/downloader_name）→ in/not_in
   * - 'substring' 逗号分隔字符串列（tags）→ contains_any/not_contains_any
   * 仅对 multiSelect 类型生效；其它类型忽略。
   */
  matchMode?: 'exact' | 'substring'
}

export interface OperatorDisplayGroup {
  type: string
  label: string
  operators: readonly AdvancedSearchOperatorConfig[]
}

// 分组顺序与桌面下拉一致：高级 → 基本 → 状态 → 时间 → 比率
export const ADVANCED_SEARCH_ADVANCED_FIELDS: readonly SearchField[] = [
  { key: 'tags', label: '标签', type: 'multiSelect', supportsExclude: true, matchMode: 'substring' }, // 逗号串列：用 contains_any/not_contains_any
  { key: 'tracker_url', label: 'Tracker URL', type: 'text', supportsExclude: true },
  { key: 'tracker_msg', label: 'Tracker 信息', type: 'text', supportsExclude: true }
]

export const ADVANCED_SEARCH_BASIC_FIELDS: readonly SearchField[] = [
  { key: 'name', label: '种子名称', type: 'text', supportsExclude: true },
  { key: 'size', label: '种子大小', type: 'number', supportsExclude: true },
  { key: 'save_path', label: '保存路径', type: 'text', supportsExclude: true }
]

export const ADVANCED_SEARCH_STATUS_FIELDS: readonly SearchField[] = [
  {
    key: 'status',
    label: '状态',
    type: 'multiSelect',
    supportsExclude: true,
    matchMode: 'exact',
    options: STATUS_OPTIONS
  },
  {
    key: 'downloader_name',
    label: '下载器',
    type: 'multiSelect',
    supportsExclude: true,
    matchMode: 'exact', // 单值精确列：用 in/not_in
    options: [] // 通过 API 动态获取
  },
  {
    key: 'category',
    label: '分类',
    type: 'multiSelect',
    supportsExclude: true,
    matchMode: 'exact', // 单值精确列：用 in/not_in
    options: [] // 通过 API 动态获取
  },
  {
    key: 'super_seeding',
    label: '超级做种',
    type: 'select',
    supportsExclude: true
  }
]

export const ADVANCED_SEARCH_TIME_FIELDS: readonly SearchField[] = [
  { key: 'added_date', label: '添加时间', type: 'date', supportsExclude: true },
  { key: 'completed_date', label: '完成时间', type: 'date', supportsExclude: true }
]

export const ADVANCED_SEARCH_RATIO_FIELDS: readonly SearchField[] = [
  { key: 'ratio', label: '比率', type: 'number', supportsExclude: true },
  { key: 'ratio_limit', label: '比率限制', type: 'number', supportsExclude: true }
]

/** 字段下拉分组（移动端条件编辑弹层复用同一分组顺序与标题） */
export const ADVANCED_SEARCH_FIELD_SECTIONS: ReadonlyArray<{
  label: string
  fields: readonly SearchField[]
}> = [
  { label: '高级信息', fields: ADVANCED_SEARCH_ADVANCED_FIELDS },
  { label: '基本信息', fields: ADVANCED_SEARCH_BASIC_FIELDS },
  { label: '状态信息', fields: ADVANCED_SEARCH_STATUS_FIELDS },
  { label: '时间信息', fields: ADVANCED_SEARCH_TIME_FIELDS },
  { label: '比率信息', fields: ADVANCED_SEARCH_RATIO_FIELDS }
]

export function getAllSearchFields(): readonly SearchField[] {
  return ADVANCED_SEARCH_FIELD_SECTIONS.flatMap(section => section.fields)
}

export function getSearchFieldInfo(fieldKey: string): SearchField | undefined {
  if (!fieldKey) return undefined
  return getAllSearchFields().find(field => field.key === fieldKey)
}

/**
 * 获取字段可选操作符分组（按契约 operators 过滤；multiSelect 再按
 * matchMode 收敛：exact 只留 in/not_in + 空值判断，substring 反之）。
 */
export function getOperatorGroupsForField(fieldKey: string): OperatorDisplayGroup[] {
  const field = getSearchFieldInfo(fieldKey)
  if (!field) return []

  const groups: OperatorDisplayGroup[] = []
  const fieldType = field.type

  if (ADVANCED_SEARCH_OPERATOR_GROUPS[fieldType]) {
    const allowedOperators = ADVANCED_SEARCH_FIELDS[fieldKey]?.operators || []
    let operators = ADVANCED_SEARCH_OPERATOR_GROUPS[fieldType].filter(operator =>
      allowedOperators.includes(operator.backendValue)
    )
    // multiSelect 字段按 matchMode 过滤：
    // - exact（status/category/downloader_name 单值列）只暴露 in/not_in
    // - substring（tags 逗号串列）只暴露 contains_any/not_contains_any
    // 避免对单值列暴露 contains_*（语义错：LIKE 对精确列多余），
    // 也避免对逗号串列暴露 in（语义错：整串相等而非子串）。
    if (fieldType === 'multiSelect') {
      const exactOps = ['in', 'not_in']
      const nullOps = ['is_null', 'is_not_null']
      operators = field.matchMode === 'exact'
        ? operators.filter(op => exactOps.includes(op.value) || nullOps.includes(op.value))
        : operators.filter(op => !exactOps.includes(op.value))
    }
    groups.push({
      type: 'basic',
      label: '基本操作',
      operators
    })
  }

  return groups
}

const ALL_OPERATORS: readonly AdvancedSearchOperatorConfig[] =
  Object.values(ADVANCED_SEARCH_OPERATOR_GROUPS).flat()

export function getOperatorLabel(operator: string): string {
  const op = ALL_OPERATORS.find(o => o.value === operator)
  return op ? op.label : operator
}

function isRecordValue(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 条件值摘要（预览文本与移动端摘要卡共用同一渲染语义） */
export function describeConditionValue(condition: AdvancedSearchConditionState): string {
  const { field, operator, value } = condition
  if (value === null || value === undefined) {
    return '未设置'
  }

  // 特殊处理种子大小范围
  if (field === 'size' && operator === 'between' && isRecordValue(value)) {
    const min = value.min !== null ? `${value.min} ${value.minUnit || 'GB'}` : '无限制'
    const max = value.max !== null ? `${value.max} ${value.maxUnit || 'GB'}` : '无限制'
    return `${min} ~ ${max}`
  }

  // 特殊处理种子大小单个值（带单位）
  if (
    field === 'size' &&
    operator !== 'between' &&
    isRecordValue(value) &&
    value.value !== undefined
  ) {
    return `${value.value} ${value.unit || 'GB'}`
  }

  if (Array.isArray(value)) {
    return value.join(', ')
  }

  if (isRecordValue(value)) {
    return JSON.stringify(value)
  }

  return String(value)
}

/** 单条条件的一行摘要（移动端摘要卡主文案）：`种子名称 包含 4K（排除）` */
export function describeCondition(condition: AdvancedSearchConditionState): string {
  const field = getSearchFieldInfo(condition.field)
  if (!field) return ''
  const operatorLabel = getOperatorLabel(condition.operator)
  const valueLabel = describeConditionValue(condition)
  const modeSuffix = condition.mode === 'exclude' ? '（排除）' : ''
  return `${field.label} ${operatorLabel} ${valueLabel}${modeSuffix}`
}

/** 构建查询预览文本（桌面预览对话框与移动端共用） */
export function buildGroupsQueryText(groups: AdvancedSearchGroupState[]): string {
  if (groups.length === 0) {
    return '暂无搜索条件'
  }

  const groupQueries = groups.map((group, groupIndex) => {
    const conditionQueries = group.conditions.map(condition => {
      const field = getSearchFieldInfo(condition.field)
      if (!field) return ''

      const modeLabel = condition.mode === 'exclude' ? '排除' : '包含'

      return `${modeLabel}: ${field.label} ${getOperatorLabel(condition.operator)} ${describeConditionValue(condition)}`
    }).filter(query => query)

    if (conditionQueries.length === 0) return ''

    const groupName = group.name || `条件组${groupIndex + 1}`
    const groupLogic = group.logic.toUpperCase()
    const conditionsStr = conditionQueries.join(` ${groupLogic} `)

    return `【${groupName}】(${conditionsStr})`
  }).filter(query => query)

  if (groupQueries.length === 0) return '暂无有效搜索条件'

  if (groupQueries.length === 1) {
    return groupQueries[0]
  }

  let result = groupQueries[0]
  for (let i = 1; i < groups.length; i++) {
    const betweenLogic = (groups[i - 1].betweenGroupLogic || 'and').toUpperCase()
    result += ` ${betweenLogic} ${groupQueries[i]}`
  }

  return result
}

export function generateConditionId(): string {
  return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

/**
 * 归一化从模板加载的 conditions，兼容历史数据：
 * 1. value：multiSelect 字段若为逗号串/单值，拆成数组。
 * 2. operator：旧 contains_any/all/not_contains_any/not_contains_all
 *    若作用在单值精确列（category/downloader_name，matchMode='exact'），
 *    需转为 in/not_in（后端 IN 才对单值列正确）；substring 列（tags）保留。
 */
export function normalizeLoadedGroups(groups: AdvancedSearchGroupState[]): AdvancedSearchGroupState[] {
  for (let groupIndex = 0; groupIndex < groups.length; groupIndex++) {
    const group = groups[groupIndex]
    group.id = group.id || generateConditionId()
    group.logic = String(group.logic).toLowerCase() === 'or' ? 'or' : 'and'
    group.betweenGroupLogic =
      String(group.betweenGroupLogic).toLowerCase() === 'or' ? 'or' : 'and'
    group.editing = false
    if (!Array.isArray(group.conditions) || group.conditions.length === 0) {
      throw new AdvancedSearchValidationError(
        `模板条件组${groupIndex + 1}没有有效条件`
      )
    }
    for (const condition of group.conditions) {
      const field = getSearchFieldInfo(condition.field)
      if (!field) {
        throw new AdvancedSearchValidationError(
          `模板包含未知字段：${condition.field}`
        )
      }
      condition.id = condition.id || generateConditionId()
      condition.mode = condition.mode === 'exclude' ? 'exclude' : 'include'
      if (!Object.prototype.hasOwnProperty.call(
        ADVANCED_SEARCH_OPERATOR_GROUPS,
        field.type
      )) {
        throw new AdvancedSearchValidationError(
          `模板字段类型无效：${field.type}`
        )
      }
      condition.operator = normalizeLoadedOperator(
        condition.field,
        condition.operator
      )
      condition.value = normalizeLoadedConditionValue(
        condition.field,
        field.type,
        condition.operator,
        condition.value
      )
      if (
        condition.mode === 'exclude' &&
        !operatorSupportsExclude(condition.operator)
      ) {
        throw new AdvancedSearchValidationError(
          `模板操作符“${condition.operator}”不支持排除模式`
        )
      }
    }
  }
  return groups
}

export interface AdvancedSearchDynamicOptionSet {
  categoryOptions: Array<{ label: string, value: string }>
  tagOptions: Array<{ label: string, value: string }>
  downloaderOptions: Array<{ label: string, value: string }>
}

export interface AdvancedSearchDynamicOptions extends AdvancedSearchDynamicOptionSet {
  /** 失败的请求数（0-3）：部分失败静默降级，全部失败由调用方告警 */
  failedCount: number
  /** 首个被拒绝请求的异常（failedCount === 3 时用于提取提示） */
  firstError: unknown
}

/**
 * 并发拉取分类/标签/下载器三个字段的候选选项：
 * - Promise.allSettled：单个失败不影响其它两个填充；
 * - 每次从空开始，避免“上次成功 + 本次失败”时残留旧数据误导用户；
 * - 全部失败的告警由调用方决定（保持桌面现有 $message 行为）。
 */
export async function loadAdvancedSearchDynamicOptions(): Promise<AdvancedSearchDynamicOptions> {
  const results = await Promise.allSettled([
    getAllCategories(),
    getAllTags(),
    getDownloaderList()
  ])

  const [categoryRes, tagRes, downloaderRes] = results
  let failedCount = 0
  const options: AdvancedSearchDynamicOptionSet = {
    categoryOptions: [],
    tagOptions: [],
    downloaderOptions: []
  }

  // 分类
  if (categoryRes.status === 'fulfilled') {
    const body = categoryRes.value as ApiResponse<string[]>
    if (body.code === '200' && Array.isArray(body.data)) {
      options.categoryOptions = body.data.map(name => ({ label: name, value: name }))
    } else {
      failedCount += 1
    }
  } else {
    failedCount += 1
    console.error('获取分类失败:', categoryRes.reason)
  }

  // 标签
  if (tagRes.status === 'fulfilled') {
    const body = tagRes.value as ApiResponse<string[]>
    if (body.code === '200' && Array.isArray(body.data)) {
      options.tagOptions = body.data.map(name => ({ label: name, value: name }))
    } else {
      failedCount += 1
    }
  } else {
    failedCount += 1
    console.error('获取标签失败:', tagRes.reason)
  }

  // 下载器显示 nickname，但请求值使用稳定 downloader_id，昵称变更不影响已选条件。
  if (downloaderRes.status === 'fulfilled') {
    const body = downloaderRes.value as ApiResponse<DownloaderSimple[]>
    if (body.code === '200' && Array.isArray(body.data)) {
      options.downloaderOptions = body.data.map(d => ({ label: d.nickname, value: d.downloader_id }))
    } else {
      failedCount += 1
    }
  } else {
    failedCount += 1
    console.error('获取下载器失败:', downloaderRes.reason)
  }

  const firstRejected = results.find(r => r.status === 'rejected') as PromiseRejectedResult | undefined

  return {
    ...options,
    failedCount,
    firstError: firstRejected?.reason
  }
}

/**
 * 字段值候选：静态（status/super_seeding）优先，动态（分类/标签/下载器）
 * 由调用方注入当次拉取结果。
 */
export function getSearchFieldOptions(
  fieldKey: string,
  dynamic: AdvancedSearchDynamicOptionSet
): Array<{ label: string, value: string }> {
  const field = getSearchFieldInfo(fieldKey)

  // 如果字段本身有选项定义，直接返回
  if (field?.options && field.options.length > 0) {
    return field.options.map(option => ({ label: option.label, value: option.value }))
  }

  switch (fieldKey) {
    case 'super_seeding':
      return [
        { label: '是', value: '1' },
        { label: '否', value: '0' },
        { label: '不支持', value: 'unsupported' }
      ]

    case 'category':
      return dynamic.categoryOptions

    case 'tags':
      return dynamic.tagOptions

    case 'downloader_name':
      return dynamic.downloaderOptions

    default:
      return []
  }
}
