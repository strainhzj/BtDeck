/**
 * 传统列表中的一条任务不能只用 hash 标识：同一个种子可以同时存在于多个下载器。
 * 行选择优先使用数据库 info_id，实时速度则使用 downloader_id + hash 与轻量接口对齐。
 */
export interface TorrentIdentityLike {
  infoId?: unknown
  info_id?: unknown
  downloaderId?: unknown
  downloader_id?: unknown
  hash?: unknown
}

export interface TorrentSpeedUpdateLike {
  hash: string
  downloaderId?: string
}

export interface TorrentSpeedTargetIndex<T extends TorrentIdentityLike> {
  byIdentity: Record<string, T[]>
  byHash: Record<string, T[]>
}

function normalizeIdentityPart(value: unknown): string {
  if (typeof value !== 'string' && typeof value !== 'number') return ''
  return String(value).trim()
}

function normalizeHash(value: unknown): string {
  return normalizeIdentityPart(value).toLowerCase()
}

export function getTorrentDownloaderId(torrent: TorrentIdentityLike | null | undefined): string {
  if (!torrent) return ''
  return normalizeIdentityPart(torrent.downloaderId || torrent.downloader_id)
}

export function getTorrentHashIdentity(torrent: TorrentIdentityLike | null | undefined): string {
  return torrent ? normalizeHash(torrent.hash) : ''
}

/**
 * 表格行唯一键。normalizeTorrent 会在 info_id 缺失时用 hash 兜底，因此当
 * info_id 与 hash 相同时改用下载器复合键，避免不同下载器的相同 hash 冲突。
 */
export function getTraditionalTorrentRowKey(torrent: TorrentIdentityLike | null | undefined): string {
  if (!torrent) return 'torrent::'
  const infoId = normalizeIdentityPart(torrent.infoId || torrent.info_id)
  const downloaderId = getTorrentDownloaderId(torrent)
  const hash = getTorrentHashIdentity(torrent)

  if (infoId && (infoId.toLowerCase() !== hash || !downloaderId)) {
    return `info:${infoId}`
  }
  return `torrent:${downloaderId}:${hash}`
}

/** 实时速度快照的稳定键，与 active-torrents 返回的 downloader_id + hash 对齐。 */
export function getTorrentSpeedIdentity(torrent: TorrentIdentityLike | null | undefined): string {
  if (!torrent) return ''
  const hash = getTorrentHashIdentity(torrent)
  if (!hash) return ''
  const downloaderId = getTorrentDownloaderId(torrent)
  return downloaderId ? `speed:${downloaderId}:${hash}` : `hash:${hash}`
}

/**
 * 列表替换时一次性建立索引。轮询时只做 O(活动任务数) 次键查找，避免对十万行
 * 为每条速度更新重复执行 Array.find。
 */
export function buildTorrentSpeedTargetIndex<T extends TorrentIdentityLike>(
  torrents: T[]
): TorrentSpeedTargetIndex<T> {
  const byIdentity: Record<string, T[]> = Object.create(null)
  const byHash: Record<string, T[]> = Object.create(null)

  torrents.forEach(torrent => {
    const identity = getTorrentSpeedIdentity(torrent)
    const hash = getTorrentHashIdentity(torrent)
    if (identity) {
      if (!byIdentity[identity]) byIdentity[identity] = []
      byIdentity[identity].push(torrent)
    }
    if (hash) {
      if (!byHash[hash]) byHash[hash] = []
      byHash[hash].push(torrent)
    }
  })

  return { byIdentity, byHash }
}

/**
 * 有下载器信息时只命中对应任务；旧服务端未返回 downloader_id 时按 hash 桶降级，
 * 让同 hash 的所有可见任务保持一致，而不是只误更新第一条。
 */
export function resolveTorrentSpeedTargets<T extends TorrentIdentityLike>(
  index: TorrentSpeedTargetIndex<T>,
  update: TorrentSpeedUpdateLike
): T[] {
  const hash = normalizeHash(update.hash)
  if (!hash) return []
  const downloaderId = normalizeIdentityPart(update.downloaderId)
  if (downloaderId) {
    return index.byIdentity[`speed:${downloaderId}:${hash}`] || []
  }
  return index.byHash[hash] || []
}
