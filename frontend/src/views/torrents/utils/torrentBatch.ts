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
  activeSpeedMap: Record<string, ActiveSpeed>
): number | null {
  if (!torrent || !torrent.hash) {
    return null
  }
  const active = activeSpeedMap[torrent.hash]
  if (active) {
    return type === 'download' ? active.downloadSpeed : active.uploadSpeed
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
  activeSpeedMap: Record<string, ActiveSpeed>
): any[] {
  if (!list || list.length === 0) return []
  return [...list]
    .filter(item => item && item.hash)
    .sort((a, b) => {
      const aSpeed = getTorrentSpeed(a, 'download', activeSpeedMap) ||
                     getTorrentSpeed(a, 'upload', activeSpeedMap) || 0
      const bSpeed = getTorrentSpeed(b, 'download', activeSpeedMap) ||
                     getTorrentSpeed(b, 'upload', activeSpeedMap) || 0
      const aActive = aSpeed > 0 ? 1 : 0
      const bActive = bSpeed > 0 ? 1 : 0
      if (aActive !== bActive) return bActive - aActive
      if (aActive === 1) return bSpeed - aSpeed
      return 0
    })
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

