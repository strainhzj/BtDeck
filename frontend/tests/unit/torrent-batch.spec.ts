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
  deriveVisibleTorrentList,
  resetSelection,
  getTorrentSpeed,
  isTrackerAnnounceSuccess,
  getTrackerStatusClass,
  hasTrackerError,
  showTrackerErrorTag,
  getTorrentErrorReason,
  countMatchedTrackerRows,
  assertSameDownloader,
  buildAdvancedSearchRequest,
  buildAdvancedSearchRequestFromTemplateGroups,
  buildDeleteLevelRequest,
  buildDeleteConfirmMessage,
  parseDeleteTaskResult,
  parseSyncDeleteResponse,
  buildSpeedSnapshot,
  needsActiveSnapshotRefresh
} from '@/views/torrents/utils/torrentBatch'
import type { AdvancedSearchRequest } from '@/api/torrents'

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

describe('snapshot aware active sorting', () => {
  it('snapshot ready miss does not fallback to stale static speed', () => {
    const list = [
      { hash: 'old-active', downloadSpeed: 999, uploadSpeed: 0 },
      { hash: 'current-active', downloadSpeed: 0, uploadSpeed: 0 }
    ]
    const activeSpeedMap = {
      'current-active': { downloadSpeed: 10, uploadSpeed: 0, progress: 20 }
    }
    const sorted = sortByActive(list, activeSpeedMap, true)
    expect(sorted.map(t => t.hash)).toEqual(['current-active', 'old-active'])
  })

  it('previous active torrent does not stay pinned after dropping from next snapshot', () => {
    const list = [
      { hash: 'previous-active', downloadSpeed: 500, uploadSpeed: 0 },
      { hash: 'next-active', downloadSpeed: 0, uploadSpeed: 0 }
    ]
    const nextSnapshotMap = {
      'next-active': { downloadSpeed: 20, uploadSpeed: 0, progress: 30 }
    }
    const sorted = sortByActive(list, nextSnapshotMap, true)
    expect(sorted.map(t => t.hash)).toEqual(['next-active', 'previous-active'])
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

describe('snapshot aware speed and visible list derivation', () => {
  it('allows static fallback before snapshot ready and returns 0 after ready miss', () => {
    const torrent = { hash: 'h1', downloadSpeed: 20, uploadSpeed: 10 }
    expect(getTorrentSpeed(torrent, 'download', {}, false)).toBe(20)
    expect(getTorrentSpeed(torrent, 'upload', {}, false)).toBe(10)
    expect(getTorrentSpeed(torrent, 'download', {}, true)).toBe(0)
    expect(getTorrentSpeed(torrent, 'upload', {}, true)).toBe(0)
  })

  it('deriveVisibleTorrentList does not mutate source and returns a sorted copy', () => {
    const source = [
      { hash: 'a', downloadSpeed: 0, uploadSpeed: 0 },
      { hash: 'b', downloadSpeed: 100, uploadSpeed: 0 }
    ]
    const original = [...source]
    const visible = deriveVisibleTorrentList(source, {}, false, false)
    expect(visible).not.toBe(source)
    expect(visible.map(t => t.hash)).toEqual(['b', 'a'])
    expect(source).toEqual(original)
  })

  it('showActiveOnly does not clear list while snapshot is not ready', () => {
    const source = [
      { hash: 'a', downloadSpeed: 0, uploadSpeed: 0 },
      { hash: 'b', downloadSpeed: 100, uploadSpeed: 0 }
    ]
    const visible = deriveVisibleTorrentList(source, {}, false, true)
    expect(visible.map(t => t.hash)).toEqual(['b', 'a'])
  })

  it('showActiveOnly keeps only speed greater than 0 after snapshot ready', () => {
    const source = [
      { hash: 'old-active', downloadSpeed: 999, uploadSpeed: 0 },
      { hash: 'active', downloadSpeed: 0, uploadSpeed: 0 },
      { hash: 'inactive', downloadSpeed: 0, uploadSpeed: 0 }
    ]
    const activeSpeedMap = {
      active: { downloadSpeed: 0, uploadSpeed: 5, progress: 40 }
    }
    const visible = deriveVisibleTorrentList(source, activeSpeedMap, true, true)
    expect(visible.map(t => t.hash)).toEqual(['active'])
  })

  it('showActiveOnly drops seeds not in snapshot even if they have static speed', () => {
    // 防回归：snapshotReady=true 时 getTorrentSpeed 优先用快照，未命中返回 0，
    // 即「未命中 + 静态速度>0」的种子也应被过滤剔除（静态速度被忽略）。
    // 若有人把过滤条件误改成 >= 0 或漏掉 ! 取反，此 case 会假绿之外的回归不被发现。
    const source = [
      { hash: 'has-static-speed', downloadSpeed: 999, uploadSpeed: 0 },
      { hash: 'no-static-speed', downloadSpeed: 0, uploadSpeed: 0 }
    ]
    // 快照只含一个无关 hash，source 两个种子都未命中
    const activeSpeedMap = {
      'other-hash': { downloadSpeed: 0, uploadSpeed: 5, progress: 40 }
    }
    const visible = deriveVisibleTorrentList(source, activeSpeedMap, true, true)
    expect(visible).toEqual([])
  })

  it('showActiveOnly does not clear list when speed snapshot is empty', () => {
    // 防回归：后端返回 code=200 data=[]（无在线下载器/超时/暂无活动种子）时，
    // speedSnapshotReady 仍为 true 但 activeSpeedMap 为空。此时不应把列表清空，
    // 否则用户勾选“仅显示活动种子”后看到列表变空（功能失效）。
    // 空快照语义是“拿不到速度数据”，应降级为只排序不过滤，保留全部种子。
    const source = [
      { hash: 'a', downloadSpeed: 0, uploadSpeed: 0 },
      { hash: 'b', downloadSpeed: 100, uploadSpeed: 0 }
    ]
    const visible = deriveVisibleTorrentList(source, {}, true, true)
    // 空快照下 sortByActive 无法识别速度（snapshotReady=true 使未命中项返回 0），
    // 故保持源顺序且不过滤——关键断言是“不空、不丢种子”，顺序不作为契约。
    expect(visible.map(t => t.hash).sort()).toEqual(['a', 'b'])
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

// ============ P0-D：Tracker 状态判断契约（统一两视图语义） ============

describe('P0-D - isTrackerAnnounceSuccess / getTrackerStatusClass', () => {
  it('识别成功状态：工作中 / success / true', () => {
    expect(isTrackerAnnounceSuccess('工作中')).toBe(true)
    expect(isTrackerAnnounceSuccess('success')).toBe(true)
    expect(isTrackerAnnounceSuccess(true)).toBe(true)
  })

  it('识别非成功状态', () => {
    expect(isTrackerAnnounceSuccess('工作失败')).toBe(false)
    expect(isTrackerAnnounceSuccess('已禁用')).toBe(false)
    expect(isTrackerAnnounceSuccess('false')).toBe(false)
    expect(isTrackerAnnounceSuccess(false)).toBe(false)
    expect(isTrackerAnnounceSuccess(undefined)).toBe(false)
    expect(isTrackerAnnounceSuccess(null)).toBe(false)
    expect(isTrackerAnnounceSuccess('')).toBe(false)
  })

  it('getTrackerStatusClass 返回正确样式类', () => {
    expect(getTrackerStatusClass('工作中')).toBe('tracker-status-working')
    expect(getTrackerStatusClass(true)).toBe('tracker-status-working')
    expect(getTrackerStatusClass('未联系')).toBe('tracker-status-neutral')
    expect(getTrackerStatusClass('发送中')).toBe('tracker-status-neutral')
    expect(getTrackerStatusClass(false)).toBe('tracker-status-neutral')
    expect(getTrackerStatusClass('false')).toBe('tracker-status-error')
    expect(getTrackerStatusClass('工作失败')).toBe('tracker-status-error')
    expect(getTrackerStatusClass('已禁用')).toBe('tracker-status-error')
    expect(getTrackerStatusClass('超时')).toBe('tracker-status-error')
    expect(getTrackerStatusClass('未知状态')).toBe('tracker-status-neutral')
    expect(getTrackerStatusClass(undefined)).toBe('tracker-status-neutral')
  })

  it('防回归：列表模式只认"工作中"的旧分歧已统一（success/true 也算成功）', () => {
    // 原 index.vue 只认 '工作中'；原 TraditionalView 认 '工作中'|'success'|true
    // 统一后两者都算成功，避免两视图行为分歧
    expect(isTrackerAnnounceSuccess('success')).toBe(true)
    expect(isTrackerAnnounceSuccess(true)).toBe(true)
  })
})

// ============ 展示对齐判定：Tracker 异常标签与错误原因回退链 ============

describe('hasTrackerError / showTrackerErrorTag / getTorrentErrorReason', () => {
  it('hasTrackerError 兼容 camelCase 与 snake_case，缺省视为无异常', () => {
    expect(hasTrackerError({ status: 'seeding' } as never)).toBe(false)
    expect(hasTrackerError({ status: 'seeding', hasTrackerError: true } as never)).toBe(true)
    expect(hasTrackerError({ status: 'seeding', has_tracker_error: true } as never)).toBe(true)
    expect(hasTrackerError(null)).toBe(false)
    expect(hasTrackerError(undefined)).toBe(false)
  })

  it('showTrackerErrorTag：error 状态已有徽标不重复打，其余状态叠加标签', () => {
    expect(showTrackerErrorTag({ status: 'seeding', hasTrackerError: true } as never)).toBe(true)
    expect(showTrackerErrorTag({ status: 'error', hasTrackerError: true } as never)).toBe(false)
    expect(showTrackerErrorTag({ status: 'seeding', hasTrackerError: false } as never)).toBe(false)
  })

  it('getTorrentErrorReason 回退链：errorReason → tracker 消息 → 兜底提示', () => {
    const base = { status: 'seeding' }
    expect(getTorrentErrorReason({ ...base, errorReason: '403' } as never)).toBe('403')
    expect(
      getTorrentErrorReason({
        ...base,
        hasTrackerError: true,
        lastAnnounceMsg: 'You cannot seed the same torrent'
      } as never)
    ).toBe('Tracker 宣告失败：You cannot seed the same torrent')
    expect(getTorrentErrorReason({ ...base, hasTrackerError: true } as never)).toBe(
      'Tracker 宣告失败，详见 Tracker 标签页'
    )
    expect(getTorrentErrorReason({ ...base } as never)).toBe('')
  })

  it('getTorrentErrorReason 优先读 snake_case 字段（后端 duplicates 端点）', () => {
    expect(
      getTorrentErrorReason({ status: 'seeding', error_reason: 'Torrent not exists' } as never)
    ).toBe('Torrent not exists')
    expect(
      getTorrentErrorReason({
        status: 'seeding',
        has_tracker_error: true,
        last_announce_msg: '失败'
      } as never)
    ).toBe('Tracker 宣告失败：失败')
  })

  it('error 状态种子不打标签但 tooltip 错误原因仍可用', () => {
    const torrent = { status: 'error', hasTrackerError: true, lastAnnounceMsg: 'You cannot seed' } as never

    expect(showTrackerErrorTag(torrent)).toBe(false)
    expect(getTorrentErrorReason(torrent)).toBe('Tracker 宣告失败：You cannot seed')
    // errorReason 仍是最高优先级（整种 error 的显示语义不变）
    expect(
      getTorrentErrorReason({ status: 'error', hasTrackerError: true, errorReason: '403' } as never)
    ).toBe('403')
  })
})

// ============ tracker 域名筛选命中标记契约 ============

describe('countMatchedTrackerRows - tracker 域名筛选命中标记统计', () => {
  it('统计含 matched_domain / matchedDomain 的 tracker 行所在种子数，snake/camel 双读', () => {
    const torrents = [
      {
        tracker_info: [
          { tracker_url: 'https://a.example/announce', matched_domain: 'a.example' },
          { tracker_url: 'https://b.example/announce' }
        ]
      },
      { trackerInfo: [{ trackerUrl: 'https://b.example/announce' }] },
      {
        trackerInfo: [
          { trackerUrl: 'https://c.example/announce', matchedDomain: 'c.example' },
          { trackerUrl: 'https://d.example/announce', matchedDomain: 'd.example' }
        ]
      },
      {}
    ] as never[]

    // 第 1/3 行命中（第 3 行两个 tracker 都带标记也只计 1 行），第 2/4 行不命中
    expect(countMatchedTrackerRows(torrents)).toBe(2)
  })

  it('空 tracker 列表与 null/undefined 种子不计数、不抛错', () => {
    expect(countMatchedTrackerRows([])).toBe(0)
    expect(countMatchedTrackerRows([null, undefined])).toBe(0)
    expect(countMatchedTrackerRows([{ tracker_info: [] }, { trackerInfo: [] }] as never[])).toBe(0)
  })
})

// ============ P0-E：下载器同源校验契约 ============

describe('P0-E - assertSameDownloader', () => {
  it('所有种子同一下载器 → ok', () => {
    const torrents = [
      { hash: 'h1', downloader_id: 'dl1' },
      { hash: 'h2', downloaderId: 'dl1' } // 驼峰变体
    ]
    const r = assertSameDownloader(torrents)
    expect(r.ok).toBe(true)
    expect(r.reason).toBe('')
  })

  it('跨多个下载器 → 不通过', () => {
    const torrents = [
      { hash: 'h1', downloader_id: 'dl1' },
      { hash: 'h2', downloader_id: 'dl2' }
    ]
    const r = assertSameDownloader(torrents)
    expect(r.ok).toBe(false)
    expect(r.reason).toContain('同一')
  })

  it('存在缺下载器ID的种子 → 不通过', () => {
    const torrents = [
      { hash: 'h1', downloader_id: 'dl1' },
      { hash: 'h2' } // 缺 downloader_id
    ]
    const r = assertSameDownloader(torrents)
    expect(r.ok).toBe(false)
    expect(r.reason).toContain('缺少下载器信息')
  })

  it('空列表 → 通过（边界，由调用方决定是否拦截空选）', () => {
    expect(assertSameDownloader([]).ok).toBe(true)
  })

  it('兼容 downloader_id 与 downloaderId 两种字段', () => {
    const torrents = [
      { hash: 'h1', downloader_id: 'dl1' },
      { hash: 'h2', downloaderId: 'dl1' }
    ]
    expect(assertSameDownloader(torrents).ok).toBe(true)
  })
})

// ============ P1-F：高级搜索请求构造契约 ============

function requireAdvancedRequest(
  request: AdvancedSearchRequest | null
): AdvancedSearchRequest {
  expect(request).not.toBeNull()
  if (!request) throw new Error('expected a valid advanced-search request')
  return request
}

describe('P1-F - buildAdvancedSearchRequest', () => {
  it('解析 condition_groups（JSON字符串）并构造请求体', () => {
    const searchParams = {
      groups: JSON.stringify([
        { logic: 'and', conditions: [{ field: 'name', operator: 'contains', value: 'test' }] }
      ]),
      between_group_logics: JSON.stringify([]),
      sort_by: 'size',
      sort_order: 'asc'
    }
    const result = buildAdvancedSearchRequest(searchParams, 'added_date', 20)
    const request = requireAdvancedRequest(result.request)
    const conditionGroups = request.condition_groups || []
    expect(result.error).toBeNull()
    expect(conditionGroups).toHaveLength(1)
    expect(conditionGroups[0].logic).toBe('AND')
    expect(conditionGroups[0].conditions[0]).toEqual({
      field: 'name',
      operator: 'contains',
      value: 'test'
    })
    expect(request.sort_by).toBe('size')
    expect(request.sort_order).toBe('asc')
    expect(request.limit).toBe(20)
    expect(request.page).toBe(1)
  })

  it('解析精确数量的 between_group_logics 并转大写', () => {
    const searchParams = {
      groups: JSON.stringify([
        { logic: 'and', conditions: [{ field: 'name', operator: 'eq', value: 'one' }] },
        { logic: 'or', conditions: [{ field: 'status', operator: 'eq', value: 'paused' }] }
      ]),
      between_group_logics: JSON.stringify(['and'])
    }
    const result = buildAdvancedSearchRequest(searchParams, 'added_date', 20)
    const request = requireAdvancedRequest(result.request)
    expect(request.between_group_logics).toEqual(['AND'])
  })

  it('保留显式 exclude 模式并省略默认 include 模式', () => {
    const result = buildAdvancedSearchRequest({
      groups: JSON.stringify([
        {
          logic: 'and',
          conditions: [
            { field: 'ratio', operator: 'lte', value: 2, mode: 'exclude' },
            { field: 'name', operator: 'contains', value: 'test', mode: 'include' }
          ]
        }
      ]),
      between_group_logics: JSON.stringify([])
    }, 'added_date', 20)
    const request = requireAdvancedRequest(result.request)
    expect(request.condition_groups?.[0].conditions).toEqual([
      { field: 'ratio', operator: 'lte', value: 2, mode: 'exclude' },
      { field: 'name', operator: 'contains', value: 'test' }
    ])
  })

  it('拒绝未知条件模式，避免静默退化为 include', () => {
    const result = buildAdvancedSearchRequest({
      groups: JSON.stringify([
        {
          logic: 'and',
          conditions: [
            { field: 'ratio', operator: 'lte', value: 2, mode: 'unexpected' }
          ]
        }
      ]),
      between_group_logics: JSON.stringify([])
    }, 'added_date', 20)

    expect(result.request).toBeNull()
    expect(result.error).toContain('模式无效')
  })

  it('between_group_logics 非数组时明确拒绝', () => {
    const searchParams = {
      groups: JSON.stringify([{ logic: 'and', conditions: [{ field: 'name', operator: 'eq', value: 'one' }] }]),
      between_group_logics: JSON.stringify('not-an-array')
    }
    const { request, error } = buildAdvancedSearchRequest(searchParams, 'added_date', 20)
    expect(request).toBeNull()
    expect(error).toContain('组间逻辑数量')
  })

  it('无条件组时不回退为另一种查询语义', () => {
    const { request, error } = buildAdvancedSearchRequest(
      {},
      'added_date',
      50
    )
    expect(request).toBeNull()
    expect(error).toContain('搜索条件必须是JSON字符串')
  })

  it('sort_by 缺失时用 fallback', () => {
    const result = buildAdvancedSearchRequest({
      groups: JSON.stringify([
        { logic: 'and', conditions: [{ field: 'name', operator: 'eq', value: 'one' }] }
      ]),
      between_group_logics: JSON.stringify([])
    }, 'added_date', 20)
    const request = requireAdvancedRequest(result.request)
    expect(request.sort_by).toBe('added_date')
    expect(request.sort_order).toBe('desc')
  })

  it('groups JSON 格式错误 → 返回 error', () => {
    const searchParams = { groups: '{invalid json' }
    const { request, error } = buildAdvancedSearchRequest(searchParams, 'added_date', 20)
    expect(request).toBeNull()
    expect(error).toBe('搜索条件不是有效JSON')
  })
})

describe('buildAdvancedSearchRequestFromTemplateGroups', () => {
  it('converts template groups with AdvancedSearchBuilder operator and value semantics', () => {
    const groups = [
      {
        logic: 'and',
        betweenGroupLogic: 'or' as const,
        conditions: [
          { field: 'name', operator: 'equals', value: 'ubuntu', mode: 'include' as const },
          { field: 'size', operator: 'greater_than', value: { value: 1.5, unit: 'GB' }, mode: 'include' as const },
          { field: 'tags', operator: 'contains_any', value: ['linux', 'iso'], mode: 'exclude' as const },
          { field: 'super_seeding', operator: 'equals', value: true, mode: 'include' as const }
        ]
      },
      {
        logic: 'or',
        conditions: [
          {
            field: 'added_date',
            operator: 'date_range',
            value: { start: '2026-01-01', end: '2026-01-31' },
            mode: 'include' as const
          }
        ]
      }
    ]

    const result = buildAdvancedSearchRequestFromTemplateGroups(groups, 'size', 'asc', 30)
    const request = requireAdvancedRequest(result.request)
    const conditionGroups = request.condition_groups || []

    expect(result.error).toBeNull()
    expect(request.sort_by).toBe('size')
    expect(request.sort_order).toBe('asc')
    expect(request.limit).toBe(30)
    expect(conditionGroups).toHaveLength(2)
    expect(request.between_group_logics).toEqual(['OR'])
    expect(conditionGroups[0].logic).toBe('AND')
    expect(conditionGroups[0].conditions).toEqual([
      { field: 'name', operator: 'eq', value: 'ubuntu' },
      { field: 'size', operator: 'gt', value: '1.5 GB' },
      { field: 'tags', operator: 'contains_any', value: ['linux', 'iso'], mode: 'exclude' },
      { field: 'super_seeding', operator: 'eq', value: '1' }
    ])
    expect(conditionGroups[1].conditions[0]).toEqual({
      field: 'added_date',
      operator: 'date_range',
      value: { start: '2026-01-01', end: '2026-01-31' }
    })
  })

  it('keeps exclude mode and positive operators through template-to-request conversion', () => {
    const result = buildAdvancedSearchRequestFromTemplateGroups([
      {
        logic: 'and',
        conditions: [
          { field: 'ratio', operator: 'gt', value: 2, mode: 'exclude' },
          { field: 'completed_date', operator: 'is_null', value: 'legacy', mode: 'include' },
          { field: 'category', operator: 'in', value: ['电影'], mode: 'exclude' },
          { field: 'tags', operator: 'contains_any', value: ['movie'], mode: 'exclude' },
          { field: 'status', operator: 'in', value: ['error'], mode: 'exclude' },
          { field: 'downloader_name', operator: 'in', value: ['d1'], mode: 'exclude' },
          { field: 'super_seeding', operator: 'eq', value: 'unsupported', mode: 'exclude' },
          { field: 'tracker_url', operator: 'contains', value: 'azusa', mode: 'exclude' }
        ]
      }
    ], 'added_date', 'desc', 20)
    const request = requireAdvancedRequest(result.request)

    expect(result.error).toBeNull()
    expect(request.condition_groups?.[0].conditions).toEqual([
      { field: 'ratio', operator: 'gt', value: 2, mode: 'exclude' },
      { field: 'completed_date', operator: 'is_null', value: null },
      { field: 'category', operator: 'in', value: ['电影'], mode: 'exclude' },
      { field: 'tags', operator: 'contains_any', value: ['movie'], mode: 'exclude' },
      { field: 'status', operator: 'in', value: ['error'], mode: 'exclude' },
      { field: 'downloader_name', operator: 'in', value: ['d1'], mode: 'exclude' },
      { field: 'super_seeding', operator: 'eq', value: 'unsupported', mode: 'exclude' },
      { field: 'tracker_url', operator: 'contains', value: 'azusa', mode: 'exclude' }
    ])
  })

  it('preserves each independent connector when three template groups become a request', () => {
    const result = buildAdvancedSearchRequestFromTemplateGroups([
      {
        logic: 'and',
        betweenGroupLogic: 'or',
        conditions: [{ field: 'name', operator: 'contains', value: 'one' }]
      },
      {
        logic: 'or',
        betweenGroupLogic: 'and',
        conditions: [{ field: 'status', operator: 'in', value: ['error'] }]
      },
      {
        logic: 'and',
        conditions: [{ field: 'tracker_url', operator: 'contains', value: 'azusa' }]
      }
    ], 'added_date', 'desc', 20)
    const request = requireAdvancedRequest(result.request)

    expect(result.error).toBeNull()
    expect(request.condition_groups?.map(group => group.logic)).toEqual([
      'AND',
      'OR',
      'AND'
    ])
    expect(request.between_group_logics).toEqual(['OR', 'AND'])
  })

  it('does not pass raw builder condition_groups directly to backend', () => {
    const groups = [
      {
        logic: 'and',
        conditions: [
          {
            field: 'size',
            operator: 'between',
            value: { min: 1, max: 2, minUnit: 'GB', maxUnit: 'TB' },
            mode: 'include' as const
          }
        ]
      }
    ]

    const result = buildAdvancedSearchRequestFromTemplateGroups(groups, 'added_date', 'desc', 20)
    const request = requireAdvancedRequest(result.request)
    const conditionGroups = request.condition_groups || []

    expect(conditionGroups[0].conditions[0]).toEqual({
      field: 'size',
      operator: 'between',
      value: { min: '1 GB', max: '2 TB' }
    })
    expect(conditionGroups[0].conditions[0]).not.toHaveProperty('mode')
    expect(conditionGroups[0].conditions[0]).not.toHaveProperty('index')
  })
})

// ============ P2-I：4 等级删除纯函数契约 ============

describe('P2 - buildDeleteLevelRequest', () => {
  it('构造请求参数（info_ids + level + operator）', () => {
    const torrents = [{ info_id: 'i1' }, { info_id: 'i2' }]
    const req = buildDeleteLevelRequest(torrents, 4)
    expect(req.torrent_info_ids).toEqual(['i1', 'i2'])
    expect(req.delete_level).toBe(4)
    expect(req.operator).toBe('admin')
  })

  it('支持自定义 operator', () => {
    const req = buildDeleteLevelRequest([{ info_id: 'i1' }], 1, 'user01')
    expect(req.operator).toBe('user01')
  })
})

describe('P2 - buildDeleteConfirmMessage', () => {
  it('批量删除带数量', () => {
    expect(buildDeleteConfirmMessage(4, 5)).toContain('5 个种子')
  })

  it('等级1/3 单个删除用警告语气', () => {
    const msg1 = buildDeleteConfirmMessage(1, 1)
    const msg3 = buildDeleteConfirmMessage(3, 1)
    expect(msg1).toContain('警告')
    expect(msg3).toContain('警告')
  })

  it('等级2/4 单个删除用普通语气', () => {
    expect(buildDeleteConfirmMessage(2, 1)).not.toContain('警告')
    expect(buildDeleteConfirmMessage(4, 1)).not.toContain('警告')
  })
})

describe('P2 - parseDeleteTaskResult', () => {
  const list = [
    { info_id: 'i1', name: '种子A' },
    { info_id: 'i2', name: '种子B' }
  ]

  it('completed → success 提示', () => {
    const r = parseDeleteTaskResult({
      status: 'completed', success_count: 5, failed_count: 0, failed_items: []
    }, list)
    expect(r.type).toBe('success')
    expect(r.message).toContain('5')
    expect(r.failedDetail).toBeNull()
  })

  it('failed → error 提示，带 error_message', () => {
    const r = parseDeleteTaskResult({
      status: 'failed', success_count: 0, failed_count: 3, error_message: '下载器离线'
    }, list)
    expect(r.type).toBe('error')
    expect(r.message).toContain('下载器离线')
  })

  it('partial → warning 提示 + failedDetail（用 list 反查名称）', () => {
    const r = parseDeleteTaskResult({
      status: 'partial',
      success_count: 2,
      failed_count: 1,
      failed_items: [{ info_id: 'i1' }]
    }, list)
    expect(r.type).toBe('warning')
    expect(r.failedDetail).toContain('种子A') // 从 list 反查到名称
  })

  it('partial 失败项超5个 → failedDetail 带"等N个"', () => {
    const failedItems = Array.from({ length: 7 }, (_, i) => ({ info_id: `i${i}` }))
    const r = parseDeleteTaskResult({
      status: 'partial', success_count: 0, failed_count: 7, failed_items: failedItems
    }, [])
    expect(r.failedDetail).toContain('等7个')
  })
})

describe('P2 - parseSyncDeleteResponse', () => {
  it('等级3降级 → warning + downgradeDetail', () => {
    const data = {
      level4_downgraded: [{ torrent_name: '种子X' }, { torrent_name: '种子Y' }],
      level3_success: []
    }
    const r = parseSyncDeleteResponse(data, 3)
    expect(r.type).toBe('warning')
    expect(r.downgradeDetail).toContain('种子X')
    expect(r.downgradeDetail).toContain('降级为等级4')
  })

  it('完全成功（等级2）→ success', () => {
    const data = { level2_success: [{}, {}] }
    const r = parseSyncDeleteResponse(data, 2)
    expect(r.type).toBe('success')
    expect(r.message).toContain('2')
  })

  it('部分失败 → warning', () => {
    const data = { level2_success: [{}], failed: [{}, {}] }
    const r = parseSyncDeleteResponse(data, 2)
    expect(r.type).toBe('warning')
    expect(r.message).toContain('失败 2')
  })

  it('防回归：用 list 反查而非 tableData（parseDeleteTaskResult）', () => {
    // 子代理整体-N：index.vue 用 this.tableData，传统模式没有该字段。
    // 纯函数接收 list 参数，不依赖任何视图实例字段。
    const r = parseDeleteTaskResult({
      status: 'partial', success_count: 0, failed_count: 1,
      failed_items: [{ info_id: 'i1' }]
    }, [{ info_id: 'i1', name: '查到了' }])
    expect(r.failedDetail).toContain('查到了')
  })
})

// ============ commit 466e18c：速度快照构建契约 ============
// 锁定 loadActiveSpeed 抽出的 buildSpeedSnapshot 纯函数。
// 核心：空数组 [] 是 truthy，code='200' + data=[] 时仍 ready=true——这是
// deriveVisibleTorrentList 空快照保护所依赖的前提。

describe('commit 466e18c - buildSpeedSnapshot 速度快照构建', () => {
  it('code=200 + 非空 data → ready=true，map 按 hash 填充', () => {
    const res = {
      code: '200', status: 'success', msg: 'ok', data: [
        { hash: 'h1', downloadSpeed: 100, uploadSpeed: 0, progress: 50, num_seeds: 1, num_leechs: 0 },
        { hash: 'h2', downloadSpeed: 0, uploadSpeed: 30, progress: 80, num_seeds: 0, num_leechs: 2 }
      ]
    }
    const r = buildSpeedSnapshot(res)
    expect(r.ready).toBe(true)
    expect(r.count).toBe(2)
    expect(r.activeSpeedMap).toEqual({
      h1: { downloadSpeed: 100, uploadSpeed: 0, progress: 50 },
      h2: { downloadSpeed: 0, uploadSpeed: 30, progress: 80 }
    })
    expect(r.updates.map(u => u.hash)).toEqual(['h1', 'h2'])
  })

  it('code=200 + 空数组 data → ready=true 但 map 为空（锁定 commit 466e18c 前提）', () => {
    // 关键：后端返回 code=200 data=[]（无下载器/超时/无活动），空数组是 truthy，
    // 仍置 ready=true。若此处改成 data.length>0 才 ready，会导致「真零活动种子」
    // 时过滤永远不生效（另一个回归）。此 case 锁定当前契约。
    const res = { code: '200', status: 'success', msg: '暂无在线下载器', data: [] }
    const r = buildSpeedSnapshot(res)
    expect(r.ready).toBe(true)
    expect(r.activeSpeedMap).toEqual({})
    expect(r.updates).toEqual([])
    expect(r.count).toBe(0)
  })

  it('code≠200（如 500）→ ready=false，不提供新 map（视图保留旧值）', () => {
    const res = { code: '500', status: 'error', msg: '失败', data: null }
    const r = buildSpeedSnapshot(res)
    expect(r.ready).toBe(false)
    expect(r.activeSpeedMap).toBeNull()
    expect(r.updates).toEqual([])
  })

  it('code=206（部分下载器失败）→ ready=false，视图保留旧速度快照', () => {
    const res = {
      code: '206',
      status: 'partial',
      msg: '部分失败',
      data: [{ hash: 'partial', downloadSpeed: 10, uploadSpeed: 0, progress: 5 }]
    }
    const r = buildSpeedSnapshot(res)
    expect(r.ready).toBe(false)
    expect(r.activeSpeedMap).toBeNull()
    expect(r.updates).toEqual([])
  })

  it('data 为 null → ready=false', () => {
    const res = { code: '200', status: 'success', msg: 'ok', data: null }
    const r = buildSpeedSnapshot(res)
    expect(r.ready).toBe(false)
    expect(r.activeSpeedMap).toBeNull()
  })

  it('响应为 null/undefined → ready=false（不抛异常）', () => {
    expect(buildSpeedSnapshot(null).ready).toBe(false)
    expect(buildSpeedSnapshot(undefined).ready).toBe(false)
  })

  it('跳过缺 hash 的无效种子条目', () => {
    const res = {
      code: '200', status: 'success', msg: 'ok', data: [
        { hash: 'h1', downloadSpeed: 100, uploadSpeed: 0, progress: 0 },
        { downloadSpeed: 50 } // 缺 hash，应跳过
      ]
    }
    const r = buildSpeedSnapshot(res)
    expect(r.ready).toBe(true)
    expect(r.count).toBe(1)
    // ready=true 时 activeSpeedMap 必非空，用断言+索引替代 non-null 断言
    expect(r.activeSpeedMap).not.toBeNull()
    expect(Object.keys(r.activeSpeedMap as Record<string, any>)).toEqual(['h1'])
  })

  it('缺失速度字段用 0 兜底（不产生 undefined）', () => {
    const res = {
      code: '200', status: 'success', msg: 'ok', data: [
        { hash: 'h1' } // 缺所有速度字段
      ]
    }
    const r = buildSpeedSnapshot(res)
    const map = r.activeSpeedMap as Record<string, any>
    expect(map['h1']).toEqual({ downloadSpeed: 0, uploadSpeed: 0, progress: 0 })
    expect(r.updates[0]).toEqual({ hash: 'h1', downloadSpeed: 0, uploadSpeed: 0, progress: 0 })
  })

  it('同 hash 按 downloader_id 构建独立速度键，同时保留旧 hash map 契约', () => {
    const res = {
      code: '200', status: 'success', msg: 'ok', data: [
        { hash: 'same', downloader_id: 'dl-a', downloadSpeed: 100, uploadSpeed: 0, progress: 10 },
        { hash: 'same', downloader_id: 'dl-b', downloadSpeed: 200, uploadSpeed: 0, progress: 20 }
      ]
    }
    const r = buildSpeedSnapshot(res)

    expect(r.activeSpeedMap).toEqual({
      same: { downloadSpeed: 200, uploadSpeed: 0, progress: 20 }
    })
    expect(r.torrentSpeedMap).toEqual({
      'speed:dl-a:same': { downloadSpeed: 100, uploadSpeed: 0, progress: 10 },
      'speed:dl-b:same': { downloadSpeed: 200, uploadSpeed: 0, progress: 20 }
    })
    expect(r.updates.map(update => update.downloaderId)).toEqual(['dl-a', 'dl-b'])
    expect(r.count).toBe(2)
  })
})

describe('active_only 206 前端握手', () => {
  const partialResponse = {
    code: '206',
    status: 'partial',
    msg: 'snapshot not ready',
    data: { activeSnapshotReady: false }
  }

  it('活动筛选收到显式 206/ready=false 时要求刷新并重试', () => {
    expect(needsActiveSnapshotRefresh(partialResponse, true)).toBe(true)
  })

  it('非活动列表不会被同一响应误触发', () => {
    expect(needsActiveSnapshotRefresh(partialResponse, false)).toBe(false)
  })

  it('200 权威空集和无 ready 标志的 206 都不触发', () => {
    expect(needsActiveSnapshotRefresh({
      code: '200', status: 'success', msg: 'ok', data: { activeSnapshotReady: true }
    }, true)).toBe(false)
    expect(needsActiveSnapshotRefresh({
      code: '206', status: 'partial', msg: 'other partial', data: {}
    }, true)).toBe(false)
  })
})

