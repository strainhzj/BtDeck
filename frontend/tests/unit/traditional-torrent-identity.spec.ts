import {
  buildTorrentSpeedTargetIndex,
  getTraditionalTorrentRowKey,
  resolveTorrentSpeedTargets
} from '@/views/torrents/utils/traditionalTorrentIdentity'
import { getTorrentSpeed, sortByActive } from '@/views/torrents/utils/torrentBatch'

describe('traditional torrent identity and large-list performance contracts', () => {
  it('distinguishes the same hash on different downloaders and resolves exact speed targets', () => {
    const first = { infoId: 'info-a', downloaderId: 'dl-a', hash: 'same-hash' }
    const second = { infoId: 'info-b', downloaderId: 'dl-b', hash: 'same-hash' }
    const index = buildTorrentSpeedTargetIndex([first, second])

    expect(getTraditionalTorrentRowKey(first)).not.toBe(getTraditionalTorrentRowKey(second))
    expect(resolveTorrentSpeedTargets(index, {
      hash: 'same-hash',
      downloaderId: 'dl-b'
    })).toEqual([second])
    expect(resolveTorrentSpeedTargets(index, { hash: 'same-hash' })).toEqual([first, second])
  })

  it('supports a 100000-row index and keeps active-first sorting linear for inactive rows', () => {
    const torrents = Array.from({ length: 100000 }, (_, index) => ({
      infoId: `info-${index}`,
      downloaderId: `dl-${index % 4}`,
      hash: `hash-${index}`
    }))
    const targetIndex = buildTorrentSpeedTargetIndex(torrents)
    const activeTorrent = torrents[98765]
    const activeSpeedMap = {
      [`speed:${activeTorrent.downloaderId}:${activeTorrent.hash}`]: {
        downloadSpeed: 1024,
        uploadSpeed: 0,
        progress: 50
      }
    }

    expect(Object.keys(targetIndex.byIdentity)).toHaveLength(100000)
    expect(resolveTorrentSpeedTargets(targetIndex, {
      hash: activeTorrent.hash,
      downloaderId: activeTorrent.downloaderId
    })).toEqual([activeTorrent])

    const sorted = sortByActive(torrents, activeSpeedMap, true)
    expect(sorted).toHaveLength(100000)
    expect(sorted[0]).toBe(activeTorrent)
    expect(sorted[1]).toBe(torrents[0])
    expect(sorted[2]).toBe(torrents[1])
    expect(torrents[0].infoId).toBe('info-0')
  })

  it('reads legacy snapshots without downloader_id from the hash fallback key', () => {
    const torrent = { downloaderId: 'dl-a', hash: 'same-hash' }
    const legacyMap = {
      'hash:same-hash': { downloadSpeed: 64, uploadSpeed: 0, progress: 10 }
    }

    expect(getTorrentSpeed(torrent, 'download', legacyMap, true)).toBe(64)
  })
})
