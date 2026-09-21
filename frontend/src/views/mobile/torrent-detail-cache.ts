/**
 * 种子详情快照缓存（移动端）：
 * 列表页点击卡片时写入整行数据，详情页优先用它立即渲染（含 trackerInfo
 * 等列表行自带字段）；内存级、单条、不持久化——刷新/直达 URL 时为空，
 * 详情页走 getList（downloader_id + name_like）回查兜底。
 * take 语义：取走即清空，防止下次直达详情时渲染到上一次的旧种子。
 */
import { Torrent } from '@/api/torrents'

let cached: Torrent | null = null

export function setCachedTorrent(torrent: Torrent | null): void {
  cached = torrent
}

export function takeCachedTorrent(): Torrent | null {
  const snapshot = cached
  cached = null
  return snapshot
}
