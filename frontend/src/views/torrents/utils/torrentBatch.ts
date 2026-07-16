/**
 * 种子批量操作纯函数集合（防回归基础设施 v2）
 *
 * 设计目标：把列表模式（index.vue）与传统模式（TraditionalView.vue）中
 * 逐行重复的批量逻辑抽成可单测的纯函数，消除「改一处忘一处」的回归风险。
 *
 * 对应 bug：
 *   - groupTorrentsByDownloader / deleteTorrentsBatch → Bug#1（计数）、Bug#4（删除参数）
 *   - runBatchAction → Bug#2（文案语义：区分种子数与下载器组数）
 *   - sortByActive → Bug#7（排序键：速度 > 0 而非「在 map 中」）
 *   - resetSelection → Bug#8（选中状态重置）
 *
 * 纯函数原则：API 依赖通过参数注入，模块顶部不 import API 层（避免单测时
 * 拉入 element-ui 的 ESM 链导致 jest 解析失败）。mixin 调用时传入真实 API。
 * tests/unit/torrent-batch.spec.ts 直接注入 mock 单测，无需挂载 Vue 组件。
 *
 * 注意：getTorrentId/getDownloaderId 内联实现，不依赖 @/utils/formatters，
 * 否则会因 formatters.ts 既存的 TorrentStatus.COMPLETED TS 错误阻塞 ts-jest 编译。
 */
import type { ApiResponse } from '@/api/torrents'

// ============ 类型定义 ============

interface ActiveSpeed {
  downloadSpeed: number
  uploadSpeed: number
  progress: number
}

interface TemplateCondition {
  field: string
  operator: string
  value: any
  mode?: 'include' | 'exclude'
  index?: number
}

interface TemplateConditionGroup {
  id?: string
  name?: string
  logic?: string
  betweenGroupLogic?: 'and' | 'or'
  conditions: TemplateCondition[]
}

interface SelectionState {
  multipleSelection: any[]
  selectAll: boolean
  isIndeterminate: boolean
}

export interface BatchDeleteResult {
  successCount: number
  failCount: number
  errors: string[]
  deletedTorrents: any[]
}

export interface BatchActionResult {
  /** 成功的下载器组数（不是种子数） */
  succeeded: number
  /** 失败的下载器组数 */
  failed: number
  /** 操作的种子总数 */
  total: number
  /** 涉及的下载器总数 */
  downloaderCount: number
  /** 失败下载器的错误信息（供调用方拼装提示） */
  errors: string[]
}

type BatchApiFn = (params: { downloader_id: string, hashes: string[] }) => Promise<ApiResponse<any>>

/** 单种子删除 API 签名（deleteTorrents） */
type DeleteApiFn = (params: {
  info_id: string
  downloader_id: string
  delete_data: number
  id_recycle: number
}) => Promise<ApiResponse<any>>

// ============ 内联工具函数（不依赖 formatters，避免 ts-jest 编译牵连） ============

/** 安全获取种子 ID：兼容 infoId / info_id / hash */
function getTorrentId(torrent: any): string {
  if (!torrent) return ''
  return torrent.infoId || torrent.info_id || torrent.hash || ''
}

/** 安全获取下载器 ID：兼容 downloaderId / downloader_id */
function getDownloaderId(torrent: any): string {
  if (!torrent) return ''
  return torrent.downloaderId || torrent.downloader_id || ''
}

// ============ 纯函数 ============

/**
 * 按下载器 ID 分组种子（对齐 index.vue:696 / TraditionalView.vue:995）
 * 防回归 Bug#1/Bug#4：分组逻辑单点维护。
 */
export function groupTorrentsByDownloader(torrents: any[]): Record<string, any[]> {
  const groups: Record<string, any[]> = {}
  torrents.forEach(torrent => {
    // 空值检查，防止 torrent 对象为 null/undefined
    if (!torrent) {
      console.warn('跳过空种子对象')
      return
    }

    const downloaderId = torrent?.downloader_id || torrent?.downloaderId

    // 如果无法获取下载器 ID，跳过该种子
    if (!downloaderId) {
      console.warn('种子缺少下载器ID，跳过:', torrent)
      return
    }

    if (!groups[downloaderId]) {
      groups[downloaderId] = []
    }
    groups[downloaderId].push(torrent)
  })
  return groups
}

/**
 * 批量删除种子内部逻辑（对齐 index.vue:1829 / TraditionalView.vue:1024）
 * 逐种子按 info_id 调用 deleteFn，使用 Promise.all 并行。
 * 防回归 Bug#1（计数按种子数而非字符串长度）、Bug#4（参数用 info_id/delete_data/id_recycle）。
 * @param torrents 要删除的种子列表
 * @param deleteData 是否删除数据文件 (0: 仅删种子, 1: 同时删数据)
 * @param deleteFn 删除 API（注入，便于单测 mock；生产传 deleteTorrents）
 * @returns 成功数 / 失败数 / 错误信息列表 / 成功删除的种子列表
 */
export async function deleteTorrentsBatch(
  torrents: any[],
  deleteData: number,
  deleteFn: DeleteApiFn
): Promise<BatchDeleteResult> {
  let successCount = 0
  let failCount = 0
  const errors: string[] = []
  const deletedTorrents: any[] = []

  const deletePromises = torrents.map(async(torrent) => {
    try {
      const infoId = getTorrentId(torrent)
      const downloaderId = getDownloaderId(torrent)

      await deleteFn({
        info_id: infoId,
        downloader_id: downloaderId,
        delete_data: deleteData,
        id_recycle: 1
      })
      return { success: true, torrent }
    } catch (error: any) {
      const errorMsg = error?.response?.data?.msg ??
                       error?.message ??
                       '删除失败'
      return { success: false, error: errorMsg }
    }
  })

  const results = await Promise.all(deletePromises)
  results.forEach((result) => {
    if (result.success) {
      successCount++
      if (result.torrent) {
        deletedTorrents.push(result.torrent)
      }
    } else {
      failCount++
      if (result.error) {
        errors.push(result.error)
      }
    }
  })

  return { successCount, failCount, errors, deletedTorrents }
}

/**
 * 批量操作通用骨架（分组 + 并行 + allSettled 统计）
 * 防回归 Bug#2：明确区分「下载器组数」与「种子数」，文案不再把下载器数当种子数。
 * 适用于 resume / pause / recheck 三类按下载器分组的批量操作。
 * @param torrents 选中的种子列表
 * @param apiFn 批量 API（resumeTorrents / pauseTorrents / recheckTorrents）
 * @returns 统计结果（调用方据此拼装提示文案）
 */
export async function runBatchAction(
  torrents: any[],
  apiFn: BatchApiFn
): Promise<BatchActionResult> {
  const groups = groupTorrentsByDownloader(torrents)

  const promises = Object.entries(groups).map(([downloaderId, groupTorrents]) => {
    const hashes = groupTorrents.map(t => t.hash)
    return apiFn({ downloader_id: downloaderId, hashes })
  })

  const responses = await Promise.allSettled(promises)

  const succeeded = responses.filter(r => r.status === 'fulfilled').length
  const failed = responses.filter(r => r.status === 'rejected').length
  const total = torrents.length
  const downloaderCount = Object.keys(groups).length

  // 收集失败原因（rejected 结果无 value，需从 reason 提取）
  const errors: string[] = []
  responses.forEach(r => {
    if (r.status === 'rejected') {
      const reason = (r as PromiseRejectedResult).reason
      const msg = reason?.response?.data?.msg ?? reason?.message ?? '操作失败'
      errors.push(msg)
    }
  })

  return { succeeded, failed, total, downloaderCount, errors }
}

/**
 * 获取种子的实时显示速度（对齐 index.vue:2168）
 * 优先使用轮询数据，降级使用静态数据。
 */
export function getTorrentSpeed(
  torrent: any,
  type: 'download' | 'upload',
  activeSpeedMap: Record<string, ActiveSpeed>,
  snapshotReady = false
): number | null {
  if (!torrent || !torrent.hash) {
    return null
  }
  const active = activeSpeedMap[torrent.hash]
  if (active) {
    return type === 'download' ? active.downloadSpeed : active.uploadSpeed
  }
  if (snapshotReady) {
    return 0
  }
  return type === 'download' ? (torrent.downloadSpeed ?? null) : (torrent.uploadSpeed ?? null)
}

/**
 * 按活跃度排序（对齐 index.vue:2155 / TraditionalView.vue sortedList）
 * 防回归 Bug#7：排序键必须是「速度 > 0」而非「在 activeSpeedMap 中」。
 * 原 bug 只判 `!!activeSpeedMap[hash]`，导致后端返回的 0 速度活跃种子被错误置顶。
 * @returns 新数组（不修改原数组），活跃种子在前；活跃种子内部按速度降序
 */
export function sortByActive(
  list: any[],
  activeSpeedMap: Record<string, ActiveSpeed>,
  snapshotReady = false
): any[] {
  if (!list || list.length === 0) return []
  return [...list]
    .filter(item => item && item.hash)
    .sort((a, b) => {
      const aSpeed = getTorrentSpeed(a, 'download', activeSpeedMap, snapshotReady) ||
                     getTorrentSpeed(a, 'upload', activeSpeedMap, snapshotReady) || 0
      const bSpeed = getTorrentSpeed(b, 'download', activeSpeedMap, snapshotReady) ||
                     getTorrentSpeed(b, 'upload', activeSpeedMap, snapshotReady) || 0
      const aActive = aSpeed > 0 ? 1 : 0
      const bActive = bSpeed > 0 ? 1 : 0
      if (aActive !== bActive) return bActive - aActive
      if (aActive === 1) return bSpeed - aSpeed
      return 0
    })
}

/**
 * 根据实时速度快照派生当前可见列表。
 *
 * 注意：本函数历史上承担两个职责——
 *   1. sortByActive：活跃种子优先排序（始终生效）。
 *   2. showActiveOnly 客户端过滤（按 dl>0 || ul>0 筛选）。
 * "仅显示活动种子"已下沉为后端 active_only 原生过滤（list/total 口径一致），
 * 调用方现在统一传 showActiveOnly=false，关闭第 2 项职责，仅保留排序。
 * 下方过滤分支作为能力保留（不删除），以防未来需要前端兜底时复用。
 */
export function deriveVisibleTorrentList(
  sourceList: any[],
  activeSpeedMap: Record<string, ActiveSpeed>,
  snapshotReady: boolean,
  showActiveOnly: boolean
): any[] {
  const sorted = sortByActive(sourceList, activeSpeedMap, snapshotReady)
  const snapshotHasData = Object.keys(activeSpeedMap).length > 0
  if (!showActiveOnly || !snapshotReady || !snapshotHasData) {
    return sorted
  }
  return sorted.filter(item => {
    const downloadSpeed = getTorrentSpeed(item, 'download', activeSpeedMap, true) || 0
    const uploadSpeed = getTorrentSpeed(item, 'upload', activeSpeedMap, true) || 0
    return downloadSpeed > 0 || uploadSpeed > 0
  })
}

// ============ 速度快照构建（loadActiveSpeed 可测纯函数层） ============
// 防回归：index.vue 与 TraditionalView.vue 的 loadActiveSpeed 逐字重复，
// 其中「何时置 speedSnapshotReady=true」是 commit 466e18c 修复的 bug 根因所在
// （后端 code='200' data=[] 时空数组是 truthy，仍置 ready=true）。此纯函数把
// 状态计算抽出，消除两视图同步维护负担，并提供可单测入口。副作用（更新 this.list
// 命中项速度 + 写 this.activeSpeedMap/ready）留给视图层应用。

/** 速度快照条目（与视图内联类型一致） */
export interface SpeedSnapshotEntry {
  downloadSpeed: number
  uploadSpeed: number
  progress: number
}

/** 列表种子命中快照后的速度更新（供视图层应用到 this.list） */
export interface SpeedUpdate {
  hash: string
  downloadSpeed: number
  uploadSpeed: number
  progress: number
}

/** buildSpeedSnapshot 实际读取的种子字段（ActiveTorrentSpeed 的结构子集）。
 * 仅声明本函数依赖的字段，避免要求调用方/测试提供未使用的 num_seeds/num_leechs，
 * 同时保留字段级类型安全（downloadSpeed: number 而非 any）。
 * hash 设为可选：本函数职责之一就是过滤缺 hash 的无效条目，入参须容忍非法输入。 */
interface ActiveTorrentSpeedInput {
  hash?: string
  downloadSpeed?: number
  uploadSpeed?: number
  progress?: number
}

/** buildSpeedSnapshot 的计算结果（视图据此更新 activeSpeedMap / speedSnapshotReady / list） */
export interface SpeedSnapshotResult {
  /** 是否应把 speedSnapshotReady 置为 true（code='200' 且 data truthy） */
  ready: boolean
  /** 新的 activeSpeedMap（ready=false 时为 null，视图应保留旧值） */
  activeSpeedMap: Record<string, SpeedSnapshotEntry> | null
  /** 命中列表项的速度更新（视图遍历应用到 this.list） */
  updates: SpeedUpdate[]
  /** 有效种子数（调试日志用） */
  count: number
}

interface ActiveSnapshotResponseData {
  activeSnapshotReady?: boolean
}

/**
 * 判断活动列表响应是否要求先刷新速度快照。只有显式的 206 + ready=false 才触发，
 * 避免把其他业务 206 或普通列表请求误判为重试信号。
 */
export function needsActiveSnapshotRefresh(
  res: ApiResponse<ActiveSnapshotResponseData> | null | undefined,
  activeOnly: boolean
): boolean {
  return Boolean(
    activeOnly &&
    res &&
    res.code === '206' &&
    res.data &&
    res.data.activeSnapshotReady === false
  )
}

/**
 * 从 active-torrents 接口响应计算速度快照状态（纯函数，无副作用）。
 *
 * 契约锁定（commit 466e18c）：
 * - code='200' 且 data truthy（含空数组 []）→ ready=true，activeSpeedMap 可能为空 {}。
 *   空数组是 truthy，故空 data 仍置 ready=true——这是 deriveVisibleTorrentList
 *   空快照保护所依赖的前提。若此处改成「data.length>0 才 ready」，会导致
 *   「用户真零活动种子」时过滤永远不生效（另一个回归）。
 * - code≠'200' 或 data falsy → ready=false，activeSpeedMap=null（视图不更新）。
 *
 * 注意：原视图 loadActiveSpeed 对缺 hash 的条目会 console.warn，本纯函数不打 warn
 *（纯函数无副作用，调试噪声降级为静默跳过）。
 *
 * @param res getActiveTorrents() 的响应
 * @returns 快照计算结果
 */
export function buildSpeedSnapshot(
  res: ApiResponse<ActiveTorrentSpeedInput[] | null> | null | undefined
): SpeedSnapshotResult {
  if (!res || res.code !== '200' || !res.data) {
    return { ready: false, activeSpeedMap: null, updates: [], count: 0 }
  }
  const map: Record<string, SpeedSnapshotEntry> = {}
  const updates: SpeedUpdate[] = []
  const torrents = res.data || []
  torrents.forEach((t) => {
    if (!t || !t.hash) {
      // 防御性检查：跳过缺 hash 的无效种子（原视图会 console.warn，纯函数静默跳过）
      return
    }
    const downloadSpeed = t.downloadSpeed ?? 0
    const uploadSpeed = t.uploadSpeed ?? 0
    const progress = t.progress ?? 0
    map[t.hash] = { downloadSpeed, uploadSpeed, progress }
    updates.push({ hash: t.hash, downloadSpeed, uploadSpeed, progress })
  })
  return { ready: true, activeSpeedMap: map, updates, count: Object.keys(map).length }
}

/**
 * 重置批量选中状态（对齐 TraditionalView.vue getList 后的清理）
 * 防回归 Bug#8：分页/筛选切换后，新数据全部 checked:false，
 * 必须同步重置 multipleSelection / selectAll / isIndeterminate，
 * 否则用户在加载期间点击批量操作会误伤已不在当前视图的旧选中项。
 */
export function resetSelection(state: SelectionState): void {
  state.multipleSelection = []
  state.selectAll = false
  state.isIndeterminate = false
}

// ============ Tracker 状态判断（统一两视图语义分歧） ============

/** Tracker Announce/Scrape 成功状态值（后端 torrent_status.py 枚举的中文值） */
const TRACKER_SUCCESS_VALUES = new Set(['工作中', 'success', 'true'])

/**
 * 判断 Tracker 的 Announce/Scrape 是否成功（统一两视图语义）
 * 防回归 P0-D：列表模式只认 '工作中'，传统模式认 '工作中'|'success'|true，分歧。
 * 此处统一为：'工作中' | 'success' | true 视为成功。
 */
export function isTrackerAnnounceSuccess(status: string | boolean | undefined | null): boolean {
  if (status === undefined || status === null) return false
  if (typeof status === 'boolean') return status
  return TRACKER_SUCCESS_VALUES.has(String(status))
}

/** Tracker 失败状态值 */
const TRACKER_FAIL_VALUES = new Set(['工作失败', '已禁用', '超时', '已清除', 'failed', 'false'])

/**
 * 获取 Tracker 状态样式类名（供模板 :class 使用）
 * 成功 → working（绿）；失败 → error（红）；其它 → neutral（灰）
 */
export function getTrackerStatusClass(status: string | boolean | undefined | null): string {
  if (isTrackerAnnounceSuccess(status)) return 'tracker-status-working'
  if (typeof status === 'string' && TRACKER_FAIL_VALUES.has(status)) return 'tracker-status-error'
  return 'tracker-status-neutral'
}

// ============ 下载器同源校验（消除转移/改路径的重复校验） ============

export interface SameDownloaderResult {
  /** 是否通过（所有种子属于同一下载器且都有下载器ID） */
  ok: boolean
  /** 失败原因（ok=false 时有值），供 $message 提示 */
  reason: string
}

/**
 * 校验选中的种子是否都属于同一下载器（批量转移/修改路径前置校验）
 * 防回归 P0-E：列表模式 handleBatchTransfer/handleBatchSetLocation 各有一份
 * 几乎逐字相同的校验逻辑（~10行），此处统一为单点纯函数。
 */
export function assertSameDownloader(torrents: any[]): SameDownloaderResult {
  const downloaderIds = new Set(
    torrents.map(t => getDownloaderId(t)).filter(id => id !== '' && id !== undefined && id !== null)
  )

  if (downloaderIds.has('') || torrents.some(t => !getDownloaderId(t))) {
    return { ok: false, reason: '选中种子缺少下载器信息，请刷新后重试' }
  }
  if (downloaderIds.size > 1) {
    return { ok: false, reason: '选中的种子必须属于同一下载器' }
  }
  return { ok: true, reason: '' }
}

// ============ 高级搜索请求构造（解析 condition_groups，纯函数） ============

export interface AdvancedSearchRequestResult {
  /** 构造好的请求体（成功时）；失败时为 null */
  request: any | null
  /** 解析失败原因（调用方据此 $message.error）；成功时为 null */
  error: string | null
}

const ADVANCED_OPERATOR_MAPPING: Record<string, string> = {
  contains: 'contains',
  not_contains: 'not_contains',
  equals: 'eq',
  not_equals: 'ne',
  starts_with: 'starts_with',
  ends_with: 'ends_with',
  regex: 'regex',
  greater_than: 'gt',
  less_than: 'lt',
  greater_equal: 'gte',
  less_equal: 'lte',
  between: 'between',
  last_days: 'last_days',
  date_range: 'date_range',
  in: 'in',
  not_in: 'not_in',
  contains_any: 'contains_any',
  contains_all: 'contains_all',
  not_contains_any: 'not_contains_any',
  not_contains_all: 'not_contains_all'
}

const ADVANCED_FIELD_TYPES: Record<string, 'text' | 'number' | 'date' | 'select' | 'multiSelect' | 'boolean'> = {
  name: 'text',
  save_path: 'text',
  content_path: 'text',
  hash: 'text',
  size: 'number',
  progress: 'number',
  download_speed: 'number',
  upload_speed: 'number',
  ratio: 'number',
  ratio_limit: 'number',
  status: 'select',
  downloader_id: 'select',
  category: 'select',
  tags: 'multiSelect',
  tracker_url: 'text',
  tracker_msg: 'text',
  added_date: 'date',
  completed_date: 'date',
  super_seeding: 'boolean'
}

function convertAdvancedOperatorForBackend(operator: string): string {
  return ADVANCED_OPERATOR_MAPPING[operator] || operator
}

function formatAdvancedParamValue(condition: TemplateCondition): any {
  if (condition.field === 'size' && condition.operator === 'between') {
    const value = condition.value
    if (value && typeof value === 'object' && value.min !== undefined && value.max !== undefined) {
      return {
        min: value.min !== null ? `${value.min} ${value.minUnit || 'GB'}` : null,
        max: value.max !== null ? `${value.max} ${value.maxUnit || 'GB'}` : null
      }
    }
    return condition.value
  }

  if (condition.field === 'size' && condition.operator !== 'between') {
    const value = condition.value
    if (value && typeof value === 'object' && value.value !== undefined) {
      return value.value !== null ? `${value.value} ${value.unit || 'GB'}` : null
    }
    return condition.value
  }

  switch (ADVANCED_FIELD_TYPES[condition.field]) {
    case 'date':
      if (condition.value && typeof condition.value === 'object') {
        return JSON.stringify(condition.value)
      }
      return condition.value
    case 'number':
      return Number(condition.value)
    case 'multiSelect':
      return Array.isArray(condition.value) ? condition.value.join(',') : condition.value
    case 'boolean':
      return condition.value ? '1' : '0'
    default:
      return condition.value
  }
}

function buildAdvancedSearchParamsFromTemplateGroups(groups: TemplateConditionGroup[]): any {
  const groupsData = groups.map((group, groupIndex) => {
    const conditions = (group.conditions || [])
      .filter(condition => condition.field && condition.operator && condition.value !== null)
      .map((condition, conditionIndex) => ({
        field: condition.field,
        operator: convertAdvancedOperatorForBackend(condition.operator),
        value: formatAdvancedParamValue(condition),
        mode: condition.mode,
        index: condition.index ?? conditionIndex
      }))

    return {
      id: group.id,
      name: group.name || `条件组 ${groupIndex + 1}`,
      logic: group.logic || 'and',
      conditions,
      conditions_count: conditions.length
    }
  }).filter(group => group.conditions_count > 0)

  const betweenGroupLogics = []
  for (let i = 0; i < groups.length - 1; i++) {
    betweenGroupLogics.push(groups[i].betweenGroupLogic || 'and')
  }

  return {
    complex_search: true,
    groups_count: groups.length,
    groups: JSON.stringify(groupsData),
    between_group_logics: JSON.stringify(betweenGroupLogics)
  }
}

/**
 * 把 AdvancedSearchBuilder 输出的 searchParams 解析为高级搜索 API 请求体。
 * 防回归 P1-F：列表模式 performAdvancedSearch 含 ~85 行解析逻辑（JSON.parse groups、
 * between_group_logics 类型校验、条件组回填），复制到传统模式 = 两份要同步维护。
 * 此处抽为纯函数（无 API、无 UI），两视图各自只保留「调 API + 设 list/total + 提示」。
 *
 * @param searchParams AdvancedSearchBuilder emit 的 search 事件参数（含 groups/between_group_logics/name/...）
 * @param sortByFallback 默认排序字段（蛇形，如 'added_date'）
 * @param limit 每页条数
 */
export function buildAdvancedSearchRequest(
  searchParams: any,
  sortByFallback: string,
  limit: number
): AdvancedSearchRequestResult {
  let conditionGroups: any[] = []
  let betweenGroupLogics: string[] = []

  // 解析条件组（JSON 字符串）
  if (searchParams.groups) {
    try {
      const groupsData = JSON.parse(searchParams.groups)
      conditionGroups = groupsData.map((group: any) => ({
        logic: group.logic?.toUpperCase() || 'AND',
        conditions: group.conditions.map((cond: any) => ({
          field: cond.field,
          operator: cond.operator,
          value: cond.value
        }))
      }))
    } catch (e) {
      console.error('解析groups参数失败:', e)
      return { request: null, error: '搜索条件格式错误' }
    }
  }

  // 解析组间逻辑关系（类型校验：必须是字符串数组）
  if (searchParams.between_group_logics) {
    try {
      const parsed = JSON.parse(searchParams.between_group_logics)
      if (Array.isArray(parsed)) {
        betweenGroupLogics = parsed
          .filter((item: any) => typeof item === 'string')
          .map((logic: string) => logic.toUpperCase())
      } else {
        console.warn('between_group_logics不是数组类型，使用默认值')
        betweenGroupLogics = []
      }
    } catch (e) {
      console.error('解析between_group_logics参数失败:', e)
      betweenGroupLogics = []
    }
  }

  const request: any = {
    page: 1,
    limit,
    sort_by: searchParams.sort_by || sortByFallback,
    sort_order: (searchParams.sort_order || 'desc') as 'asc' | 'desc'
  }

  // 无条件组时，回退到简单字段
  if (conditionGroups.length === 0) {
    if (searchParams.name) request.name = searchParams.name
    if (searchParams.downloader_id) request.downloader_id = searchParams.downloader_id
    if (searchParams.status) request.status = searchParams.status
    if (searchParams.tags) request.tags = searchParams.tags
    if (searchParams.category) request.category = searchParams.category
  }

  // 有条件组时，附带组间逻辑
  if (conditionGroups.length > 0) {
    request.condition_groups = conditionGroups
    if (betweenGroupLogics.length > 0) {
      request.between_group_logics = betweenGroupLogics
    }
  }

  return { request, error: null }
}

export function buildAdvancedSearchRequestFromTemplateGroups(
  groups: TemplateConditionGroup[],
  sortBy: string,
  sortOrder: 'asc' | 'desc' = 'desc',
  limit = 20
): AdvancedSearchRequestResult {
  const searchParams = {
    ...buildAdvancedSearchParamsFromTemplateGroups(groups),
    sort_by: sortBy,
    sort_order: sortOrder
  }
  return buildAdvancedSearchRequest(searchParams, sortBy, limit)
}

// ============ 4 等级删除（纯函数层，无副作用，可单测） ============
// 防回归 P2-I：列表模式 4 等级删除 ~250 行含 API/轮询/loading/UI 提示耦合，
// 此处把无副作用的「构造请求」与「解析结果」抽为纯函数。
// API 调用 + $loading 遮罩 + 轮询（带 Vue 实例依赖）留在 mixin 入口层。

export const DELETE_LEVEL_NAMES: Record<number, string> = {
  4: '标记为待删除',
  3: '移至回收站',
  2: '删除任务（保留数据）',
  1: '完全删除'
}

/**
 * 构造 4 等级删除请求参数（异步批量接口 + 同步接口共用结构）
 * @param torrents 要删除的种子列表
 * @param level 删除等级 (1-4)
 * @param operator 操作人
 */
export function buildDeleteLevelRequest(
  torrents: any[],
  level: number,
  operator = 'admin'
): { torrent_info_ids: string[], delete_level: number, operator: string } {
  return {
    torrent_info_ids: torrents.map(t => getTorrentId(t)),
    delete_level: level,
    operator
  }
}

/**
 * 根据等级生成二次确认提示文案
 */
export function buildDeleteConfirmMessage(level: number, count: number): string {
  const levelName = DELETE_LEVEL_NAMES[level] || '删除'
  if (count > 1) {
    return `确定要将选中的 ${count} 个种子${levelName}吗？`
  }
  return (level === 1 || level === 3)
    ? `警告：此操作将${levelName}，是否继续？`
    : `确定要将种子${levelName}吗？`
}

/** 解析异步批量删除任务结果，返回结构化的提示信息（供调用方 $message/$notify） */
export interface ParsedDeleteTaskResult {
  /** 成功数 */
  successCount: number
  /** 失败数 */
  failedCount: number
  /** 提示类型：success/warning/error */
  type: 'success' | 'warning' | 'error'
  /** 主提示文案 */
  message: string
  /** 失败项详情（前5个名称），供 $notify 展开；无则 null */
  failedDetail: string | null
}

/**
 * 解析异步批量删除任务结果（completed/failed/partial）
 * @param taskData 后端返回的任务数据 { status, total_count, success_count, failed_count, failed_items, error_message }
 * @param list 当前种子列表（用于反查失败项名称，注意用 list 不用 tableData）
 */
export function parseDeleteTaskResult(taskData: any, list: any[]): ParsedDeleteTaskResult {
  const { status, success_count, failed_count, failed_items, error_message } = taskData

  if (status === 'completed') {
    return {
      successCount: success_count,
      failedCount: 0,
      type: 'success',
      message: `批量删除完成，成功删除 ${success_count} 个种子`,
      failedDetail: null
    }
  }

  if (status === 'failed') {
    return {
      successCount: 0,
      failedCount: failed_count,
      type: 'error',
      message: `批量删除失败：${error_message || '未知错误'}`,
      failedDetail: null
    }
  }

  // partial：部分成功
  let failedDetail: string | null = null
  if (failed_items && failed_items.length > 0) {
    const failedNames = failed_items.slice(0, 5).map((item: any) => {
      const torrent = list.find((t: any) => getTorrentId(t) === item.info_id)
      return torrent?.name || item.info_id
    }).join('、')
    failedDetail = failed_items.length <= 5
      ? `以下种子删除失败：${failedNames}`
      : `以下种子删除失败：${failedNames} 等${failed_items.length}个`
  }

  return {
    successCount: success_count,
    failedCount: failed_count,
    type: 'warning',
    message: `批量删除部分完成：成功 ${success_count} 个，失败 ${failed_count} 个`,
    failedDetail
  }
}

/** 解析同步删除响应（处理降级 + 部分成功 + 成功计数） */
export interface ParsedSyncDeleteResult {
  type: 'success' | 'warning'
  message: string
  /** 降级详情（等级3备份失败降级为等级4），供 $notify；无则 null */
  downgradeDetail: string | null
}

/**
 * 解析同步删除接口响应（deleteTorrentsWithLevel）
 * 处理等级3降级、部分成功、各等级成功计数。
 * @param data 响应数据
 * @param level 删除等级
 */
export function parseSyncDeleteResponse(data: any, level: number): ParsedSyncDeleteResult {
  let downgradeDetail: string | null = null

  // 等级3降级处理
  if (level === 3 && data?.level4_downgraded && data.level4_downgraded.length > 0) {
    const downgraded = data.level4_downgraded
    const names = (downgraded.length <= 5 ? downgraded : downgraded.slice(0, 5))
      .map((d: any) => d.torrent_name).join('、')
    downgradeDetail = downgraded.length <= 5
      ? `以下种子备份失败，已降级为等级4：${names}`
      : `以下种子备份失败，已降级为等级4：${names} 等${downgraded.length}个`
  }

  // 统计各等级成功数
  const successCount =
    (data?.level1_success?.length || 0) +
    (data?.level2_success?.length || 0) +
    (data?.level3_success?.length || 0) +
    (data?.level4_success?.length || 0)

  // 有降级时不显示成功消息（已在 downgradeDetail 提示）
  if (downgradeDetail) {
    return { type: 'warning', message: `已将 ${data.level4_downgraded.length} 个种子降级为等级4删除（备份失败）`, downgradeDetail }
  }

  // 部分失败
  if (data?.failed && data.failed.length > 0) {
    return { type: 'warning', message: `删除完成：失败 ${data.failed.length} 个`, downgradeDetail: null }
  }

  // 完全成功
  if (level === 3) {
    const level3Count = data?.level3_success?.length || 0
    return {
      type: 'success',
      message: level3Count > 0 ? `等级3删除成功 ${level3Count} 个` : `删除完成，成功 ${successCount} 个`,
      downgradeDetail: null
    }
  }
  return { type: 'success', message: `等级${level}删除完成，成功 ${successCount} 个`, downgradeDetail: null }
}



