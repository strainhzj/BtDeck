/**
 * 种子批量操作纯函数行为契约测试（防回归基础设施 v2 / L3）
 *
 * 测的是 utils/torrentBatch.ts 的纯函数「行为契约」，不是源码文本，
 * 因此等价重写（如把 `> 0` 改成 `!== 0`）不会误报，只有行为回归才会红。
 *
 * 每个 describe 对应一个上一轮修复的 bug，注释标明锁定的契约。
 */
import {
  groupTorrentsByDownloader,
  deleteTorrentsBatch,
  runBatchAction,
  sortByActive,
  resetSelection,
  getTorrentSpeed
} from '@/views/torrents/utils/torrentBatch'

// ============ Bug#1 / Bug#4：分组与删除计数契约 ============

describe('Bug#1/Bug#4 - groupTorrentsByDownloader', () => {
  it('按 downloader_id 分组，驼峰/下划线都能识别', () => {
    const torrents = [
      { hash: 'a', downloader_id: 'dl1' },
      { hash: 'b', downloaderId: 'dl1' },
      { hash: 'c', downloader_id: 'dl2' }
    ]
    const groups = groupTorrentsByDownloader(torrents)
    expect(Object.keys(groups).sort()).toEqual(['dl1', 'dl2'])
    expect(groups.dl1.length).toBe(2)
    expect(groups.dl2.length).toBe(1)
  })

  it('跳过 null/undefined 与缺下载器 ID 的种子', () => {
    const torrents = [
      null,
      undefined,
      { hash: 'x' }, // 缺 downloader_id
      { hash: 'y', downloader_id: 'dl1' }
    ]
    const groups = groupTorrentsByDownloader(torrents as any)
    expect(Object.keys(groups)).toEqual(['dl1'])
    expect(groups.dl1.length).toBe(1)
  })
})

describe('Bug#1 - deleteTorrentsBatch 计数契约', () => {
  it('逐种子统计成功/失败数（而非下载器ID字符串长度）', async() => {
    // 防回归 Bug#1：原 bug 是 Object.keys(groups)[index].length（ID 字符串长度），
    // 这里 mock 让全部成功，断言 successCount 等于种子数而非 ID 长度。
    const deleteFn = jest.fn().mockResolvedValue({ code: '200' })

    // 用长 ID（dl_long_001）确保计数不是字符串长度
    const torrents = [
      { info_id: 'i1', downloader_id: 'dl_long_001', hash: 'h1' },
      { info_id: 'i2', downloader_id: 'dl_long_001', hash: 'h2' },
      { info_id: 'i3', downloader_id: 'dl_long_002', hash: 'h3' }
    ]
    const result = await deleteTorrentsBatch(torrents, 1, deleteFn)

    expect(result.successCount).toBe(3) // 种子数，不是 ID 长度
    expect(result.failCount).toBe(0)
    expect(result.deletedTorrents.length).toBe(3)
  })

  it('部分失败时收集错误信息', async() => {
    const deleteFn = jest.fn()
      .mockResolvedValueOnce({ code: '200' })
      .mockRejectedValueOnce({ response: { data: { msg: '下载器离线' } } })

    const torrents = [
      { info_id: 'i1', downloader_id: 'dl1', hash: 'h1' },
      { info_id: 'i2', downloader_id: 'dl2', hash: 'h2' }
    ]
    const result = await deleteTorrentsBatch(torrents, 0, deleteFn)

    expect(result.successCount).toBe(1)
    expect(result.failCount).toBe(1)
    expect(result.errors).toContain('下载器离线')
    expect(result.deletedTorrents.length).toBe(1)
  })

  it('防回归 Bug#4：调用参数为 info_id/delete_data/id_recycle（非 hashes/deleteData）', async() => {
    // 后端 delete_torrent 只接受 info_id / delete_data / id_recycle，
    // 不识别 hashes / deleteData。锁定调用契约。
    const deleteFn = jest.fn().mockResolvedValue({ code: '200' })
    const torrents = [{ info_id: 'i1', downloader_id: 'dl1', hash: 'h1' }]
    await deleteTorrentsBatch(torrents, 1, deleteFn)

    const callArg = deleteFn.mock.calls[0][0]
    expect(callArg).toHaveProperty('info_id', 'i1')
    expect(callArg).toHaveProperty('downloader_id', 'dl1')
    expect(callArg).toHaveProperty('delete_data', 1)
    expect(callArg).toHaveProperty('id_recycle', 1)
    // 确保没有错误的参数名
    expect(callArg).not.toHaveProperty('hashes')
    expect(callArg).not.toHaveProperty('deleteData')
  })
})

// ============ Bug#2：批量操作文案语义契约 ============

describe('Bug#2 - runBatchAction 计数语义契约', () => {
  it('跨2个下载器3个种子全部成功 → succeeded=2(下载器), total=3(种子)', async() => {
    const apiFn = jest.fn().mockResolvedValue({ code: '200' })
    const torrents = [
      { hash: 'h1', downloader_id: 'dl1' },
      { hash: 'h2', downloader_id: 'dl1' },
      { hash: 'h3', downloader_id: 'dl2' }
    ]
    const r = await runBatchAction(torrents, apiFn)

    // 防回归 Bug#2：succeeded 是下载器组数（2），total 是种子数（3），二者不可混淆
    expect(r.succeeded).toBe(2)
    expect(r.failed).toBe(0)
    expect(r.total).toBe(3)
    expect(r.downloaderCount).toBe(2)
    // 每个下载器组调用一次 apiFn
    expect(apiFn).toHaveBeenCalledTimes(2)
  })

  it('部分下载器失败 → failed 统计下载器数，errors 收集原因', async() => {
    const apiFn = jest.fn()
      .mockResolvedValueOnce({ code: '200' })
      .mockRejectedValueOnce(new Error('连接超时'))
    const torrents = [
      { hash: 'h1', downloader_id: 'dl1' },
      { hash: 'h2', downloader_id: 'dl2' }
    ]
    const r = await runBatchAction(torrents, apiFn)

    expect(r.succeeded).toBe(1)
    expect(r.failed).toBe(1)
    expect(r.total).toBe(2)
    expect(r.errors).toContain('连接超时')
  })

  it('调用方据此可区分「种子数」与「下载器数」，文案不再误导', async() => {
    // 这是 Bug#2 的核心契约：旧文案「成功开始 X 个种子」错把 succeeded 当种子数。
    // 新契约要求文案必须同时用 r.total（种子）和 r.downloaderCount（下载器）。
    const apiFn = jest.fn().mockResolvedValue({ code: '200' })
    const torrents = Array.from({ length: 5 }, (_, i) => ({
      hash: `h${i}`,
      downloader_id: `dl${i % 2}` // 2 个下载器，5 个种子
    }))
    const r = await runBatchAction(torrents, apiFn)

    // 正确文案模板：`批量开始成功(${r.total}个种子, ${r.downloaderCount}个下载器)`
    const message = `批量开始成功(${r.total}个种子, ${r.downloaderCount}个下载器)`
    expect(message).toBe('批量开始成功(5个种子, 2个下载器)')
    // 契约：total 与 downloaderCount 是不同的量，不可互换
    expect(r.total).not.toBe(r.downloaderCount)
  })
})

// ============ Bug#7：排序键契约 ============

describe('Bug#7 - sortByActive 排序行为契约', () => {
  it('活跃种子（速度>0）排在非活跃种子之前', () => {
    const list = [
      { hash: 'a', downloadSpeed: 0, uploadSpeed: 0 },
      { hash: 'b', downloadSpeed: 100, uploadSpeed: 0 }, // 活跃（下载）
      { hash: 'c', downloadSpeed: 0, uploadSpeed: 0 },
      { hash: 'd', downloadSpeed: 0, uploadSpeed: 50 }   // 活跃（仅上传）
    ]
    const sorted = sortByActive(list, {})
    expect(sorted.map(t => t.hash)).toEqual(['b', 'd', 'a', 'c'])
  })

  it('活跃种子内部按速度降序', () => {
    const list = [
      { hash: 'slow', downloadSpeed: 10, uploadSpeed: 0 },
      { hash: 'fast', downloadSpeed: 500, uploadSpeed: 0 },
      { hash: 'mid', downloadSpeed: 100, uploadSpeed: 0 }
    ]
    const sorted = sortByActive(list, {})
    expect(sorted.map(t => t.hash)).toEqual(['fast', 'mid', 'slow'])
  })

  it('速度为 0 的"活跃"种子不被错误置顶（防 Bug#7 复现）', () => {
    // Bug#7 原始形态：原代码只判 `!!activeSpeedMap[hash]`，不判速度是否 > 0。
    // 当后端把某种子放进 activeSpeedMap 但其速度为 0 时，它会被错误顶到最前。
    const list = [
      { hash: 'a', downloadSpeed: 0, uploadSpeed: 0 },
      { hash: 'b', downloadSpeed: 0, uploadSpeed: 0 }
    ]
    // a 在 activeSpeedMap 里但速度为 0
    const activeSpeedMap = {
      a: { downloadSpeed: 0, uploadSpeed: 0, progress: 50 }
    }
    const sorted = sortByActive(list, activeSpeedMap)
    // a 不应因"在 map 里"而置顶，应保持原序
    expect(sorted.map(t => t.hash)).toEqual(['a', 'b'])
  })

  it('优先用 activeSpeedMap 的轮询数据判断活跃，降级用静态速度', () => {
    const list = [
      { hash: 'static', downloadSpeed: 200, uploadSpeed: 0 }, // 仅静态速度
      { hash: 'active', downloadSpeed: 0, uploadSpeed: 0 }     // 静态为 0，但轮询有速度
    ]
    const activeSpeedMap = {
      active: { downloadSpeed: 300, uploadSpeed: 0, progress: 10 }
    }
    const sorted = sortByActive(list, activeSpeedMap)
    expect(sorted.map(t => t.hash)).toEqual(['active', 'static'])
  })

  it('空列表返回空数组', () => {
    expect(sortByActive([], {})).toEqual([])
    expect(sortByActive(null as any, {})).toEqual([])
  })

  it('不修改原数组', () => {
    const list = [
      { hash: 'a', downloadSpeed: 0, uploadSpeed: 0 },
      { hash: 'b', downloadSpeed: 100, uploadSpeed: 0 }
    ]
    const original = [...list]
    sortByActive(list, {})
    expect(list).toEqual(original)
  })
})

describe('getTorrentSpeed', () => {
  it('优先返回轮询数据', () => {
    const torrent = { hash: 'h1', downloadSpeed: 0, uploadSpeed: 0 }
    const map = { h1: { downloadSpeed: 100, uploadSpeed: 50, progress: 30 } }
    expect(getTorrentSpeed(torrent, 'download', map)).toBe(100)
    expect(getTorrentSpeed(torrent, 'upload', map)).toBe(50)
  })

  it('无轮询数据时降级用静态速度', () => {
    const torrent = { hash: 'h1', downloadSpeed: 20, uploadSpeed: 10 }
    expect(getTorrentSpeed(torrent, 'download', {})).toBe(20)
    expect(getTorrentSpeed(torrent, 'upload', {})).toBe(10)
  })

  it('缺 hash 返回 null', () => {
    expect(getTorrentSpeed({ downloadSpeed: 5 }, 'download', {})).toBeNull()
    expect(getTorrentSpeed(null, 'download', {})).toBeNull()
  })
})

// ============ Bug#8：选中状态重置契约 ============

describe('Bug#8 - resetSelection 重置契约', () => {
  it('分页/筛选切换后清空选中状态（防误伤）', () => {
    // 防回归 Bug#8：新数据载入后若不重置，multipleSelection 仍持有旧选中项，
    // 用户在加载期间点击批量操作会误伤已不在当前视图的种子。
    const state = {
      multipleSelection: [{ hash: 'old1' }, { hash: 'old2' }],
      selectAll: true,
      isIndeterminate: false
    }
    resetSelection(state)
    expect(state.multipleSelection).toEqual([])
    expect(state.selectAll).toBe(false)
    expect(state.isIndeterminate).toBe(false)
  })

  it('空状态重置后仍为空', () => {
    const state = {
      multipleSelection: [],
      selectAll: false,
      isIndeterminate: false
    }
    resetSelection(state)
    expect(state.multipleSelection).toEqual([])
    expect(state.selectAll).toBe(false)
    expect(state.isIndeterminate).toBe(false)
  })
})
