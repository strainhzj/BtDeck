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
import type {
  AdvancedSearchRequest,
  ApiResponse,
  QueryTemplateConditionGroup,
  Torrent
} from '@/api/torrents'
import {
  AdvancedSearchConditionValue,
  AdvancedSearchGroupState,
  AdvancedSearchValidationError,
  buildAdvancedSearchParams,
  normalizeLoadedConditionValue,
  normalizeLoadedOperator
} from '@/components/torrents/advancedSearchState'
import { ADVANCED_SEARCH_FIELDS } from '@/contracts/advancedSearch.generated'
import {
  getTorrentDownloaderId,
  getTorrentHashIdentity,
  getTorrentSpeedIdentity
} from './traditionalTorrentIdentity'
import type { TorrentIdentityLike } from './traditionalTorrentIdentity'

// ============ 类型定义 ============

interface ActiveSpeed {
  downloadSpeed: number
  uploadSpeed: number
  progress: number
  status?: string
  downloadComplete?: boolean
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
  const hash = getTorrentHashIdentity(torrent)
  const active = activeSpeedMap[getTorrentSpeedIdentity(torrent)] ||
                 activeSpeedMap[`hash:${hash}`] ||
                 activeSpeedMap[torrent.hash]
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
  const active: Array<{ torrent: (typeof list)[number], speed: number }> = []
  const inactive: typeof list = []

  // 一次线性分桶，非活动任务保持服务端顺序；只对通常很小的活动子集排序。
  // 大分页下复杂度由 O(N log N) 降为 O(N + A log A)。
  list.forEach(torrent => {
    if (!torrent || !torrent.hash) return
    const speed = getTorrentSpeed(torrent, 'download', activeSpeedMap, snapshotReady) ||
                  getTorrentSpeed(torrent, 'upload', activeSpeedMap, snapshotReady) || 0
    if (speed > 0) {
      active.push({ torrent, speed })
    } else {
      inactive.push(torrent)
    }
  })

  active.sort((a, b) => b.speed - a.speed)
  return active.map(entry => entry.torrent).concat(inactive)
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
  status?: string
  downloadComplete?: boolean
}

/** 列表种子命中快照后的速度更新（供视图层应用到 this.list） */
export interface SpeedUpdate {
  hash: string
  downloaderId?: string
  downloadSpeed: number
  uploadSpeed: number
  progress: number
  status?: string
  downloadComplete?: boolean
}

/** buildSpeedSnapshot 实际读取的种子字段（ActiveTorrentSpeed 的结构子集）。
 * 仅声明本函数依赖的字段，避免要求调用方/测试提供未使用的 num_seeds/num_leechs，
 * 同时保留字段级类型安全（downloadSpeed: number 而非 any）。
 * hash 设为可选：本函数职责之一就是过滤缺 hash 的无效条目，入参须容忍非法输入。 */
interface ActiveTorrentSpeedInput {
  hash?: string
  downloaderId?: string
  downloader_id?: string
  downloadSpeed?: number
  uploadSpeed?: number
  progress?: number
  status?: string
  state?: string
  downloadComplete?: boolean
  download_complete?: boolean
}

/** buildSpeedSnapshot 的计算结果（视图据此更新 activeSpeedMap / speedSnapshotReady / list） */
export interface SpeedSnapshotResult {
  /** 是否应把 speedSnapshotReady 置为 true（完整 code='200' 快照） */
  ready: boolean
  /** 响应是否为可应用的部分快照（code='206'）；视图应合并而非清空旧值。 */
  partial: boolean
  /** 新的 activeSpeedMap（无效响应时为 null，视图应保留旧值） */
  activeSpeedMap: Record<string, SpeedSnapshotEntry> | null
  /** 按 downloader_id + hash 建立的精确映射，供可能出现同 hash 的传统列表使用。 */
  torrentSpeedMap: Record<string, SpeedSnapshotEntry> | null
  /** 命中列表项的速度更新（视图遍历应用到 this.list） */
  updates: SpeedUpdate[]
  /** 有效种子数（调试日志用） */
  count: number
}

interface ActiveSnapshotResponseData {
  activeSnapshotReady?: boolean
}

const TERMINAL_RUNTIME_STATUSES = new Set([
  'completed',
  'seeding',
  'stalledup',
  'queuedup',
  'uploading',
  'forcedup',
  'pausedup',
  'checkingup',
  'seed pending'
])

const RECONCILE_RUNTIME_STATUSES = new Set([
  'downloading',
  'queuedDl',
  'queuedDL',
  'stalledDL',
  'checking',
  'checkingDL',
  'metadl',
  'forcedmetadl',
  'allocating',
  'forceddl',
  // normalizeTorrent 将缺少状态的旧记录归一为 unknown；仍允许它们进入
  // 低频核验，避免旧数据永远没有机会收敛到完成态。
  'unknown'
].map(status => status.toLowerCase()))

function normalizeSnapshotNumber(value: unknown, fallback = 0): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function normalizeSnapshotProgress(value: unknown): number {
  return Math.max(0, Math.min(100, Math.round(normalizeSnapshotNumber(value) * 100) / 100))
}

function isRuntimeComplete(status: unknown, progress: number, explicitComplete: unknown): boolean {
  if (explicitComplete === true || progress >= 100) return true
  // 新后端明确返回 false 时优先相信下载器证据；否则旧服务端的 seeding/
  // pausedUP 等终态仍可通过状态回退识别。
  if (explicitComplete === false) return false
  return typeof status === 'string' && TERMINAL_RUNTIME_STATUSES.has(status.trim().toLowerCase())
}

function isRuntimeReconcileCandidate(torrent: TorrentIdentityLike & {
  status?: unknown
  state?: unknown
  progress?: unknown
  downloadComplete?: unknown
  download_complete?: unknown
  completedDate?: unknown
  completed_date?: unknown
}): boolean {
  const progress = normalizeSnapshotProgress(torrent.progress)
  if (
    progress >= 100 ||
    torrent.downloadComplete === true ||
    torrent.download_complete === true ||
    torrent.completedDate ||
    torrent.completed_date
  ) return false
  const status = String(torrent.status || torrent.state || '').trim().toLowerCase()
  // 兼容旧列表没有 status 的情况，但不把已暂停/错误/做种任务纳入低频补查。
  return !status || RECONCILE_RUNTIME_STATUSES.has(status)
}

export interface RuntimeStateReconcileCandidate {
  downloader_id: string
  hash: string
}

export interface RuntimeStateReconcileCandidatesResult {
  candidates: RuntimeStateReconcileCandidate[]
  misses: Record<string, number>
}

/**
 * 根据完整速度快照收敛“消失但仍显示下载中”的列表行。
 * 连续 threshold 次未命中才触发一次低频服务端核验，并以复合键去重。
 */
export function collectRuntimeStateReconcileCandidates<T extends TorrentIdentityLike>(
  torrents: T[],
  updates: SpeedUpdate[],
  previousMisses: Record<string, number> = {},
  threshold = 2,
  maxCandidates = 100
): RuntimeStateReconcileCandidatesResult {
  const observedIdentities = new Set<string>()
  const observedWithoutDownloader = new Set<string>()
  updates.forEach(update => {
    const hash = getTorrentHashIdentity(update)
    if (update.downloaderId && hash) {
      observedIdentities.add(`speed:${String(update.downloaderId).trim()}:${hash}`)
    } else if (hash) {
      observedWithoutDownloader.add(hash)
    }
  })

  const nextMisses: Record<string, number> = {}
  const candidates: RuntimeStateReconcileCandidate[] = []
  torrents.forEach(torrent => {
    const identity = getTorrentSpeedIdentity(torrent)
    const hash = getTorrentHashIdentity(torrent)
    const downloaderId = getTorrentDownloaderId(torrent)
    if (!identity || !hash || !downloaderId) return
    const observed = observedIdentities.has(identity) || observedWithoutDownloader.has(hash)
    if (observed || !isRuntimeReconcileCandidate(torrent as T & {
      status?: unknown
      state?: unknown
      progress?: unknown
      downloadComplete?: unknown
      download_complete?: unknown
      completedDate?: unknown
      completed_date?: unknown
    })) {
      return
    }

    const count = (previousMisses[identity] || 0) + 1
    if (count >= threshold && candidates.length < maxCandidates) {
      candidates.push({ downloader_id: downloaderId, hash })
      nextMisses[identity] = 0
    } else {
      nextMisses[identity] = count
    }
  })

  return { candidates, misses: nextMisses }
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
 * 契约：
 * - code='200' 且 data 为数组（含空数组 []）→ ready=true，activeSpeedMap 可能为空 {}。
 *   空数组是 truthy，故空 data 仍置 ready=true——这是 deriveVisibleTorrentList
 *   空快照保护所依赖的前提。若此处改成「data.length>0 才 ready」，会导致
 *   「用户真零活动种子」时过滤永远不生效（另一个回归）。
 * - code='206' 且 data 为数组 → partial=true，返回可应用的增量 map，但 ready=false；
 *   视图必须合并而不能清空上一次完整快照。
 * - 其它 code 或 data 非数组 → ready=false、partial=false、map=null。
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
  if (!res || (res.code !== '200' && res.code !== '206') || !Array.isArray(res.data)) {
    return {
      ready: false,
      partial: false,
      activeSpeedMap: null,
      torrentSpeedMap: null,
      updates: [],
      count: 0
    }
  }
  const partial = res.code === '206'
  const map: Record<string, SpeedSnapshotEntry> = {}
  const torrentSpeedMap: Record<string, SpeedSnapshotEntry> = {}
  const updates: SpeedUpdate[] = []
  const torrents = res.data || []
  torrents.forEach((t) => {
    if (!t || !t.hash) {
      // 防御性检查：跳过缺 hash 的无效种子（原视图会 console.warn，纯函数静默跳过）
      return
    }
    const downloadSpeed = normalizeSnapshotNumber(t.downloadSpeed)
    const uploadSpeed = normalizeSnapshotNumber(t.uploadSpeed)
    const rawStatus = typeof t.status === 'string'
      ? t.status.trim()
      : (typeof t.state === 'string' ? t.state.trim() : '')
    const progress = normalizeSnapshotProgress(t.progress)
    const explicitComplete = t.downloadComplete !== undefined
      ? t.downloadComplete
      : t.download_complete
    const downloadComplete = isRuntimeComplete(rawStatus, progress, explicitComplete)
    const statusLower = rawStatus.toLowerCase()
    const status = downloadComplete && (!statusLower || statusLower === 'downloading' || statusLower === 'queueddl')
      ? 'completed'
      : rawStatus
    const speed: SpeedSnapshotEntry = {
      downloadSpeed,
      uploadSpeed,
      progress: downloadComplete ? 100 : progress,
      ...(status ? { status } : {}),
      ...(downloadComplete ? { downloadComplete: true } : {})
    }
    const downloaderId = getTorrentDownloaderId(t)
    map[t.hash] = speed
    torrentSpeedMap[getTorrentSpeedIdentity(t)] = speed
    updates.push({
      hash: t.hash,
      ...(downloaderId ? { downloaderId } : {}),
      downloadSpeed,
      uploadSpeed,
      progress: downloadComplete ? 100 : progress,
      ...(status ? { status } : {}),
      ...(downloadComplete ? { downloadComplete: true } : {})
    })
  })
  return {
    ready: !partial,
    partial,
    activeSpeedMap: map,
    torrentSpeedMap,
    updates,
    count: Object.keys(torrentSpeedMap).length
  }
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

// ============ Tracker 异常展示（展示对齐判定） ============

/** 种子是否被判定任务标记为整种 tracker 错误（camelCase 优先，snake 兼容） */
export function hasTrackerError(torrent: Torrent | null | undefined): boolean {
  if (!torrent) return false
  const value = torrent.hasTrackerError !== undefined ? torrent.hasTrackerError : torrent.has_tracker_error
  return value === true
}

/**
 * 统计本页含 tracker 域名筛选命中标记（后端 matched_domain）的行数。
 * 供两视图 getList 观察日志汇总，与后端 [tracker-domain-filter] debug 日志对账。
 */
export function countMatchedTrackerRows(torrents: Array<Torrent | null | undefined>): number {
  return torrents.filter(torrent => {
    const trackers = torrent?.trackerInfo ?? torrent?.tracker_info ?? []
    return trackers.some(tracker => !!(tracker.matched_domain || tracker.matchedDomain))
  }).length
}

/**
 * 状态列是否显示"Tracker异常"标签：
 * status='error' 已有"错误"徽标不重复打；其余状态（如做种中）叠加红色小标签。
 */
export function showTrackerErrorTag(torrent: Torrent | null | undefined): boolean {
  if (!torrent) return false
  return hasTrackerError(torrent) && torrent.status !== 'error'
}

/**
 * 名称列 tooltip 的错误原因回退链：
 * errorReason → Tracker 宣告失败消息聚合（lastAnnounceMsg）→ 兜底提示。
 * 与"Tracker异常"标签同源（hasTrackerError），保证 error 筛选命中的行必有可见错误信息。
 */
export function getTorrentErrorReason(torrent: Torrent | null | undefined): string {
  if (!torrent) return ''
  const errorReason = torrent.errorReason || torrent.error_reason || ''
  if (errorReason) return errorReason
  if (!hasTrackerError(torrent)) return ''
  const announceMsg = torrent.lastAnnounceMsg || torrent.last_announce_msg || ''
  return announceMsg ? `Tracker 宣告失败：${announceMsg}` : 'Tracker 宣告失败，详见 Tracker 标签页'
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
  request: AdvancedSearchRequest | null
  /** 解析失败原因（调用方据此 $message.error）；成功时为 null */
  error: string | null
}

interface AdvancedSearchParamsInput {
  groups?: unknown
  between_group_logics?: unknown
  sort_by?: unknown
  sort_order?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseJsonString(value: unknown, label: string): unknown {
  if (typeof value !== 'string') {
    throw new AdvancedSearchValidationError(`${label}必须是JSON字符串`)
  }
  try {
    return JSON.parse(value) as unknown
  } catch (_error) {
    throw new AdvancedSearchValidationError(`${label}不是有效JSON`)
  }
}

function parseConditionGroups(value: unknown): NonNullable<
  AdvancedSearchRequest['condition_groups']
> {
  const parsed = parseJsonString(value, '搜索条件')
  if (!Array.isArray(parsed) || parsed.length === 0) {
    throw new AdvancedSearchValidationError('至少需要一个条件组')
  }
  return parsed.map((rawGroup, groupIndex) => {
    if (!isRecord(rawGroup)) {
      throw new AdvancedSearchValidationError(
        `条件组${groupIndex + 1}结构无效`
      )
    }
    const logic = String(rawGroup.logic).toUpperCase()
    if (logic !== 'AND' && logic !== 'OR') {
      throw new AdvancedSearchValidationError(
        `条件组${groupIndex + 1}逻辑无效`
      )
    }
    if (!Array.isArray(rawGroup.conditions) || rawGroup.conditions.length === 0) {
      throw new AdvancedSearchValidationError(
        `条件组${groupIndex + 1}至少需要一个条件`
      )
    }
    const conditions = rawGroup.conditions.map(
      (rawCondition, conditionIndex) => {
        if (!isRecord(rawCondition)) {
          throw new AdvancedSearchValidationError(
            `条件组${groupIndex + 1}第${conditionIndex + 1}项结构无效`
          )
        }
        const field = rawCondition.field
        const operator = rawCondition.operator
        if (
          typeof field !== 'string' ||
          !ADVANCED_SEARCH_FIELDS[field] ||
          typeof operator !== 'string' ||
          !ADVANCED_SEARCH_FIELDS[field].operators.includes(operator)
        ) {
          throw new AdvancedSearchValidationError(
            `条件组${groupIndex + 1}第${conditionIndex + 1}项契约无效`
          )
        }
        if (!Object.prototype.hasOwnProperty.call(rawCondition, 'value')) {
          throw new AdvancedSearchValidationError(
            `条件组${groupIndex + 1}第${conditionIndex + 1}项缺少值`
          )
        }
        const rawMode = rawCondition.mode
        if (
          rawMode !== undefined &&
          rawMode !== 'include' &&
          rawMode !== 'exclude'
        ) {
          throw new AdvancedSearchValidationError(
            `条件组${groupIndex + 1}第${conditionIndex + 1}项模式无效`
          )
        }
        const mode: 'include' | 'exclude' = rawMode === 'exclude'
          ? 'exclude'
          : 'include'
        const condition = { field, operator, value: rawCondition.value }
        return mode === 'exclude' ? { ...condition, mode } : condition
      }
    )
    return { logic, conditions }
  })
}

function parseBetweenGroupLogics(
  value: unknown,
  groupCount: number
): Array<'AND' | 'OR'> {
  const parsed = parseJsonString(value, '组间逻辑')
  if (!Array.isArray(parsed) || parsed.length !== groupCount - 1) {
    throw new AdvancedSearchValidationError(
      '组间逻辑数量必须等于条件组数量减一'
    )
  }
  return parsed.map((item, index) => {
    const logic = typeof item === 'string' ? item.toUpperCase() : ''
    if (logic !== 'AND' && logic !== 'OR') {
      throw new AdvancedSearchValidationError(
        `第${index + 1}个组间逻辑无效`
      )
    }
    return logic
  })
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
  searchParams: AdvancedSearchParamsInput,
  sortByFallback: string,
  limit: number
): AdvancedSearchRequestResult {
  try {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100000) {
      throw new AdvancedSearchValidationError('分页大小无效')
    }
    const conditionGroups = parseConditionGroups(searchParams.groups)
    const betweenGroupLogics = parseBetweenGroupLogics(
      searchParams.between_group_logics,
      conditionGroups.length
    )
    const sortBy =
      typeof searchParams.sort_by === 'string' && searchParams.sort_by
        ? searchParams.sort_by
        : sortByFallback
    const sortOrder = searchParams.sort_order === undefined
      ? 'desc'
      : searchParams.sort_order
    if (sortOrder !== 'asc' && sortOrder !== 'desc') {
      throw new AdvancedSearchValidationError('排序方向无效')
    }
    return {
      request: {
        page: 1,
        limit,
        sort_by: sortBy,
        sort_order: sortOrder,
        condition_groups: conditionGroups,
        between_group_logics: betweenGroupLogics
      },
      error: null
    }
  } catch (error) {
    const message = error instanceof AdvancedSearchValidationError
      ? error.message
      : '搜索条件格式错误'
    return { request: null, error: message }
  }
}

export function buildAdvancedSearchRequestFromTemplateGroups(
  groups: QueryTemplateConditionGroup[],
  sortBy: string,
  sortOrder: 'asc' | 'desc' = 'desc',
  limit = 20
): AdvancedSearchRequestResult {
  try {
    const normalizedGroups: AdvancedSearchGroupState[] = groups.map(
      (group, groupIndex) => {
        const logic = String(group.logic).toLowerCase()
        if (logic !== 'and' && logic !== 'or') {
          throw new AdvancedSearchValidationError(
            `模板条件组${groupIndex + 1}逻辑无效`
          )
        }
        if (!Array.isArray(group.conditions) || group.conditions.length === 0) {
          throw new AdvancedSearchValidationError(
            `模板条件组${groupIndex + 1}没有条件`
          )
        }
        const betweenGroupLogic = group.betweenGroupLogic
        if (
          groupIndex < groups.length - 1 &&
          betweenGroupLogic !== 'and' &&
          betweenGroupLogic !== 'or'
        ) {
          throw new AdvancedSearchValidationError(
            `模板条件组${groupIndex + 1}缺少组间逻辑`
          )
        }
        return {
          id: group.id || `template-group-${groupIndex + 1}`,
          name: group.name,
          logic,
          betweenGroupLogic,
          conditions: group.conditions.map((condition, conditionIndex) => {
            const field = ADVANCED_SEARCH_FIELDS[condition.field]
            if (!field) {
              throw new AdvancedSearchValidationError(
                `模板包含未知字段：${condition.field}`
              )
            }
            const operator = normalizeLoadedOperator(
              condition.field,
              condition.operator
            )
            return {
              id: `template-condition-${groupIndex + 1}-${conditionIndex + 1}`,
              field: condition.field,
              operator,
              value: normalizeLoadedConditionValue(
                condition.field,
                field.kind,
                operator,
                condition.value
              ) as AdvancedSearchConditionValue,
              mode: condition.mode === 'exclude' ? 'exclude' : 'include'
            }
          })
        }
      }
    )
    const searchParams = {
      ...buildAdvancedSearchParams(normalizedGroups),
      sort_by: sortBy,
      sort_order: sortOrder
    }
    return buildAdvancedSearchRequest(searchParams, sortBy, limit)
  } catch (error) {
    const message = error instanceof AdvancedSearchValidationError
      ? error.message
      : '模板搜索条件格式错误'
    return { request: null, error: message }
  }
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
  /** 文件缺失详情（等级3未找到种子文件，跳过文件操作直接入回收站），供 $notify；无则 null */
  fileMissingDetail: string | null
}

/**
 * 解析异步批量删除任务结果（completed/failed/partial）
 * @param taskData 后端返回的任务数据 { status, total_count, success_count, failed_count, failed_items, error_message, results }
 * @param list 当前种子列表（用于反查失败项名称，注意用 list 不用 tableData）
 */
export function parseDeleteTaskResult(taskData: any, list: any[]): ParsedDeleteTaskResult {
  const { status, success_count, failed_count, failed_items, error_message, results } = taskData

  const missing = extractFileMissingFromResults(results)
  const fileMissingDetail = missing.length > 0 ? buildFileMissingDetail(missing) : null

  if (status === 'completed') {
    return {
      successCount: success_count,
      failedCount: 0,
      type: 'success',
      message: missing.length > 0
        ? `批量删除完成，成功删除 ${success_count} 个种子（其中 ${missing.length} 个未找到文件，已跳过文件操作）`
        : `批量删除完成，成功删除 ${success_count} 个种子`,
      failedDetail: null,
      fileMissingDetail
    }
  }

  if (status === 'failed') {
    return {
      successCount: 0,
      failedCount: failed_count,
      type: 'error',
      message: `批量删除失败：${error_message || '未知错误'}`,
      failedDetail: null,
      fileMissingDetail: null
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
    failedDetail,
    fileMissingDetail
  }
}

/** 解析同步删除响应（处理降级 + 文件缺失 + 部分成功 + 成功计数） */
export interface ParsedSyncDeleteResult {
  type: 'success' | 'warning'
  message: string
  /** 降级详情（等级3备份失败降级为等级4），供 $notify；无则 null */
  downgradeDetail: string | null
  /** 文件缺失详情（等级3未找到种子文件，跳过文件操作直接入回收站），供 $notify；无则 null */
  fileMissingDetail: string | null
}

/** 等级3删除成功但未找到种子文件的条目（后端 level3_file_missing / 异步 results 提取） */
interface FileMissingItem {
  torrent_id: string
  torrent_name: string
}

/**
 * 构造等级3"未找到种子文件"提醒文案（已跳过文件操作，种子直接移入回收站）
 * @param missing 文件缺失条目列表
 */
function buildFileMissingDetail(missing: FileMissingItem[]): string {
  const names = (missing.length <= 5 ? missing : missing.slice(0, 5))
    .map(item => item.torrent_name || item.torrent_id)
    .join('、')
  const suffix = missing.length <= 5 ? '' : ` 等${missing.length}个`
  return `以下种子未找到文件，已跳过文件操作直接移入回收站：${names}${suffix}`
}

/**
 * 从异步删除任务 results（每项 {info_id, result}）提取等级3文件缺失条目
 */
function extractFileMissingFromResults(results: unknown): FileMissingItem[] {
  if (!Array.isArray(results)) return []
  return results
    .filter((item): item is { info_id: string, result: { file_missing?: boolean, torrent_name?: string } } => {
      const result = (item as { result?: { file_missing?: boolean } })?.result
      return Boolean(result?.file_missing)
    })
    .map(item => ({
      torrent_id: item.info_id || '',
      torrent_name: item.result?.torrent_name || ''
    }))
}

/**
 * 解析同步删除接口响应（deleteTorrentsWithLevel）
 * 处理等级3降级、文件缺失提醒、部分成功、各等级成功计数。
 * @param data 响应数据
 * @param level 删除等级
 */
export function parseSyncDeleteResponse(data: any, level: number): ParsedSyncDeleteResult {
  let downgradeDetail: string | null = null
  let fileMissingDetail: string | null = null

  // 等级3降级处理
  if (level === 3 && data?.level4_downgraded && data.level4_downgraded.length > 0) {
    const downgraded = data.level4_downgraded
    const names = (downgraded.length <= 5 ? downgraded : downgraded.slice(0, 5))
      .map((d: any) => d.torrent_name).join('、')
    downgradeDetail = downgraded.length <= 5
      ? `以下种子备份失败，已降级为等级4：${names}`
      : `以下种子备份失败，已降级为等级4：${names} 等${downgraded.length}个`
  }

  // 等级3文件缺失：未找到种子文件，已跳过文件操作直接移入回收站
  if (level === 3 && Array.isArray(data?.level3_file_missing) && data.level3_file_missing.length > 0) {
    fileMissingDetail = buildFileMissingDetail(data.level3_file_missing as FileMissingItem[])
  }

  // 统计各等级成功数
  const successCount =
    (data?.level1_success?.length || 0) +
    (data?.level2_success?.length || 0) +
    (data?.level3_success?.length || 0) +
    (data?.level4_success?.length || 0)

  // 有降级时不显示成功消息（已在 downgradeDetail 提示）
  if (downgradeDetail) {
    return {
      type: 'warning',
      message: `已将 ${data.level4_downgraded.length} 个种子降级为等级4删除（备份失败）`,
      downgradeDetail,
      fileMissingDetail
    }
  }

  // 部分失败
  if (data?.failed && data.failed.length > 0) {
    return { type: 'warning', message: `删除完成：失败 ${data.failed.length} 个`, downgradeDetail: null, fileMissingDetail }
  }

  // 完全成功
  if (level === 3) {
    const level3Count = data?.level3_success?.length || 0
    const missingCount = fileMissingDetail ? data.level3_file_missing.length : 0
    return {
      type: 'success',
      message: missingCount > 0
        ? `等级3删除成功 ${level3Count} 个（其中 ${missingCount} 个未找到文件，已跳过文件操作）`
        : (level3Count > 0 ? `等级3删除成功 ${level3Count} 个` : `删除完成，成功 ${successCount} 个`),
      downgradeDetail: null,
      fileMissingDetail
    }
  }
  return { type: 'success', message: `等级${level}删除完成，成功 ${successCount} 个`, downgradeDetail: null, fileMissingDetail }
}



