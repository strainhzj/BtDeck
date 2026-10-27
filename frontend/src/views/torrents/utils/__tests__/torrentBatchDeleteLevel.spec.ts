import {
  buildDeleteLevelRequest,
  collectTorrentDownloaderRefs,
  findOfflineDownloaders
} from '../torrentBatch'

/**
 * 等级1删除 · 下载器离线跳过链路回归测试
 *
 * 背景：等级1删除前经 getStatusAll 检测下载器离线，用户在追加确认中同意后，
 * 请求需携带 skip_downloader=true（后端跳过下载器调用，仅删本地记录）。
 * 本 spec 钉死三个纯函数不变量：
 * 1. buildDeleteLevelRequest 默认零变化（不带 skip_downloader，老请求格式不回归）；
 *    skipDownloader=true 时携带 skip_downloader=true。
 * 2. collectTorrentDownloaderRefs 兼容驼峰/蛇形字段、按 id 去重、name 缺失回退 id。
 * 3. findOfflineDownloaders 语义 = getStatusAll 未返回即离线。
 */

const torrents = [
  { info_id: 't1', downloader_id: 'dl-1', downloader_name: 'qbt 主力' },
  { info_id: 't2', downloaderId: 'dl-2', downloaderName: 'tr 备用' },
  // 与 t1 同下载器 → 应被去重
  { info_id: 't3', downloader_id: 'dl-1', downloader_name: 'ignored' }
]

describe('buildDeleteLevelRequest —— skip_downloader 携带契约', () => {
  it('默认不携带 skip_downloader（保持既有请求格式零变化）', () => {
    const req = buildDeleteLevelRequest(torrents, 1)
    expect(req).toEqual({
      torrent_info_ids: ['t1', 't2', 't3'],
      delete_level: 1,
      operator: 'admin'
    })
    expect('skip_downloader' in req).toBe(false)
  })

  it('skipDownloader=true 时携带 skip_downloader=true', () => {
    const req = buildDeleteLevelRequest(torrents, 1, 'admin', true)
    expect(req.skip_downloader).toBe(true)
    expect(req.torrent_info_ids).toEqual(['t1', 't2', 't3'])
  })

  it('非等级1调用不受影响（等级值原样透传）', () => {
    const req = buildDeleteLevelRequest(torrents, 4)
    expect(req.delete_level).toBe(4)
    expect('skip_downloader' in req).toBe(false)
  })
})

describe('collectTorrentDownloaderRefs —— 种子涉及下载器收集', () => {
  it('兼容驼峰/蛇形字段并按 id 去重', () => {
    const refs = collectTorrentDownloaderRefs(torrents)
    expect(refs).toEqual([
      { id: 'dl-1', name: 'qbt 主力' },
      { id: 'dl-2', name: 'tr 备用' }
    ])
  })

  it('name 缺失时回退 id；跳过空 id 与空种子', () => {
    const refs = collectTorrentDownloaderRefs([
      { downloader_id: 'dl-x' },
      null,
      { downloader_name: 'no-id' },
      {}
    ])
    expect(refs).toEqual([{ id: 'dl-x', name: 'dl-x' }])
  })

  it('空列表返回空数组', () => {
    expect(collectTorrentDownloaderRefs([])).toEqual([])
  })
})

describe('findOfflineDownloaders —— 离线判定（未在 getStatusAll 返回即离线）', () => {
  const refs = [
    { id: 'dl-1', name: 'qbt 主力' },
    { id: 'dl-2', name: 'tr 备用' }
  ]

  it('全部在线返回空数组', () => {
    expect(findOfflineDownloaders(refs, new Set(['dl-1', 'dl-2']))).toEqual([])
  })

  it('部分离线返回离线引用', () => {
    const offline = findOfflineDownloaders(refs, new Set(['dl-1']))
    expect(offline).toEqual([{ id: 'dl-2', name: 'tr 备用' }])
  })

  it('状态列表为空集时全部判为离线（getStatusAll 返回空 = 无在线下载器）', () => {
    expect(findOfflineDownloaders(refs, new Set())).toEqual(refs)
  })
})
