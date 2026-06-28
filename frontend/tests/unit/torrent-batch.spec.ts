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
  getTorrentSpeed,
  isTrackerAnnounceSuccess,
  getTrackerStatusClass,
  assertSameDownloader,
  buildAdvancedSearchRequest,
  buildDeleteLevelRequest,
  buildDeleteConfirmMessage,
  parseDeleteTaskResult,
  parseSyncDeleteResponse
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

describe('P1-F - buildAdvancedSearchRequest', () => {
  it('解析 condition_groups（JSON字符串）并构造请求体', () => {
    const searchParams = {
      groups: JSON.stringify([
        { logic: 'and', conditions: [{ field: 'name', operator: 'like', value: 'test' }] }
      ]),
      sort_by: 'size',
      sort_order: 'asc'
    }
    const { request, error } = buildAdvancedSearchRequest(searchParams, 'added_date', 20)
    expect(error).toBeNull()
    expect(request).not.toBeNull()
    expect(request.condition_groups).toHaveLength(1)
    expect(request.condition_groups[0].logic).toBe('AND') // logic 转大写
    expect(request.condition_groups[0].conditions[0]).toEqual({ field: 'name', operator: 'like', value: 'test' })
    expect(request.sort_by).toBe('size')
    expect(request.sort_order).toBe('asc')
    expect(request.limit).toBe(20)
    expect(request.page).toBe(1)
  })

  it('解析 between_group_logics（过滤非字符串、转大写）', () => {
    const searchParams = {
      groups: JSON.stringify([
        { logic: 'and', conditions: [{ field: 'a', operator: 'eq', value: '1' }] },
        { logic: 'or', conditions: [{ field: 'b', operator: 'eq', value: '2' }] }
      ]),
      between_group_logics: JSON.stringify(['and', 123, 'or', null, 'AND'])
    }
    const { request } = buildAdvancedSearchRequest(searchParams, 'added_date', 20)
    // 过滤掉 123/null，保留字符串，转大写
    expect(request.between_group_logics).toEqual(['AND', 'OR', 'AND'])
  })

  it('between_group_logics 非数组时使用默认空数组', () => {
    const searchParams = {
      groups: JSON.stringify([{ logic: 'and', conditions: [{ field: 'a', operator: 'eq', value: '1' }] }]),
      between_group_logics: JSON.stringify('not-an-array')
    }
    const { request } = buildAdvancedSearchRequest(searchParams, 'added_date', 20)
    // 单元素字符串解析后是 'not-an-array'（字符串），不是数组，走默认 []
    // 但 'not-an-array' JSON.parse 后是字符串本身，isArray=false → 不附 between_group_logics
    expect(request.between_group_logics).toBeUndefined()
  })

  it('无条件组时回退到简单字段', () => {
    const searchParams = {
      name: 'ubuntu',
      status: 'downloading',
      category: 'iso'
    }
    const { request } = buildAdvancedSearchRequest(searchParams, 'added_date', 50)
    expect(request.condition_groups).toBeUndefined()
    expect(request.name).toBe('ubuntu')
    expect(request.status).toBe('downloading')
    expect(request.category).toBe('iso')
    expect(request.limit).toBe(50)
  })

  it('sort_by 缺失时用 fallback', () => {
    const { request } = buildAdvancedSearchRequest({}, 'added_date', 20)
    expect(request.sort_by).toBe('added_date')
    expect(request.sort_order).toBe('desc') // 默认
  })

  it('groups JSON 格式错误 → 返回 error', () => {
    const searchParams = { groups: '{invalid json' }
    const { request, error } = buildAdvancedSearchRequest(searchParams, 'added_date', 20)
    expect(request).toBeNull()
    expect(error).toBe('搜索条件格式错误')
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

