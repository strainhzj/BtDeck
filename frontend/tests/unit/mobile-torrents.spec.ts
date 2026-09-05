/**
 * 移动种子页契约（Phase 4 M1 + 简单搜索迁入）：
 * - 简单搜索自移动高级搜索页迁入：筛选面板（name/下载器/状态/tracker 域）
 *   → getList 透传 name_like/downloader_id/status/tracker_domain；
 * - 查询模板页已裁撤（仅保留高级搜索）：m2 模板缓存回填链路移除；
 * - 下拉刷新带当前筛选重载；空态区分「暂无种子/没有匹配的种子」。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import MobileTorrents from '@/views/mobile/torrents.vue'
import {
  getTorrentList,
  getTrackerDomains,
  getActiveTorrents,
  reconcileRuntimeTorrentStates
} from '@/api/torrents'
import { getList as getDownloaderList } from '@/api/downloader'

jest.mock('@/api/torrents', () => ({
  getTorrentList: jest.fn(),
  getTrackerDomains: jest.fn(),
  getActiveTorrents: jest.fn(),
  reconcileRuntimeTorrentStates: jest.fn(),
  pauseTorrents: jest.fn(),
  resumeTorrents: jest.fn(),
  deleteTorrentsWithLevel: jest.fn()
}))

jest.mock('@/api/downloader', () => ({
  getList: jest.fn()
}))

jest.mock('@/views/mobile/torrent-detail-cache', () => ({
  setCachedTorrent: jest.fn(),
  takeCachedTorrent: jest.fn()
}))

const listTorrent = {
  infoId: 'i1',
  downloaderId: 'd1',
  downloaderName: 'qb',
  torrentId: 't1',
  hash: 'abc',
  name: '列表种子',
  savePath: '/x',
  size: 1024,
  status: 'seeding',
  torrentFile: '/t',
  addedDate: '2026-08-01T00:00:00',
  completedDate: null,
  ratio: 1,
  ratioLimit: null,
  tags: '',
  category: '',
  superSeeding: false,
  enabled: true,
  progress: 100
}

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileTorrents, {
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
      $confirm: jest.fn().mockResolvedValue('confirm'),
      $router: { push: jest.fn().mockResolvedValue(undefined), replace: jest.fn().mockResolvedValue(undefined) }
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileTorrents', () => {
  beforeEach(() => {
    jest.mocked(getTorrentList).mockReset()
    jest.mocked(getTorrentList).mockResolvedValue({ code: '200', data: { list: [listTorrent], total: 1 } } as never)
    jest.mocked(getTrackerDomains).mockReset()
    jest.mocked(getTrackerDomains).mockResolvedValue({ code: '200', data: ['tracker.example.com'] } as never)
    jest.mocked(getDownloaderList).mockReset()
    jest.mocked(getDownloaderList).mockResolvedValue({ code: '200', data: [{ id: 'd1', nickname: 'QB' }] } as never)
    jest.mocked(getActiveTorrents).mockReset()
    jest.mocked(getActiveTorrents).mockResolvedValue({ code: '200', data: [] } as never)
    jest.mocked(reconcileRuntimeTorrentStates).mockReset()
    jest.mocked(reconcileRuntimeTorrentStates).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: { list: [], missing: [] }
    } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('初始加载：无筛选条件透传 getList，筛选面板默认收起', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(getTorrentList).toHaveBeenCalledWith(expect.objectContaining({
      skip: 0,
      limit: 20,
      sort_by: 'added_date',
      sort_order: 'desc'
    }))
    expect(getTorrentList).not.toHaveBeenCalledWith(expect.objectContaining({ name_like: expect.anything() }))
    expect(vm.filtersExpanded).toBe(false)
    expect(wrapper.text()).toContain('列表种子')
  })

  it('筛选选项加载：下载器昵称与 Tracker 域候选', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.downloaderOptions).toEqual([{ label: 'QB', value: 'd1' }])
    expect(vm.trackerDomainOptions).toEqual(['tracker.example.com'])
  })

  it('工具栏「筛选」按钮展开/收起面板', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    wrapper.find('.m-toolbar-filter').trigger('click')
    await Vue.nextTick()
    expect(vm.filtersExpanded).toBe(true)
    expect(wrapper.find('.m-torrents-filters').exists()).toBe(true)
    wrapper.find('.m-toolbar-filter').trigger('click')
    await Vue.nextTick()
    expect(vm.filtersExpanded).toBe(false)
  })

  it('简单搜索：四类字段透传 getList 并重载', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.filters = { name: '命中', downloaders: ['d1'], statuses: ['seeding'], trackerDomains: ['tracker.example.com'] }
    jest.mocked(getTorrentList).mockClear()
    await vm.runFilters()
    expect(getTorrentList).toHaveBeenCalledWith(expect.objectContaining({
      name_like: '命中',
      downloader_id: ['d1'],
      status: ['seeding'],
      tracker_domain: ['tracker.example.com'],
      skip: 0
    }))
  })

  it('重置：清空筛选并按空条件重载', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.filters = { name: '旧条件', downloaders: ['d1'], statuses: [], trackerDomains: [] }
    await vm.resetFilters()
    expect(vm.filters).toEqual({ name: '', downloaders: [], statuses: [], trackerDomains: [] })
    expect(getTorrentList).toHaveBeenLastCalledWith(expect.objectContaining({
      skip: 0,
      sort_by: 'added_date'
    }))
    const calls = jest.mocked(getTorrentList).mock.calls
    const lastArgs = calls.slice(-1)[0]?.[0]
    expect(lastArgs).toBeTruthy()
    if (lastArgs) {
      expect(lastArgs.name_like).toBeUndefined()
      expect(lastArgs.downloader_id).toBeUndefined()
    }
  })

  it('空态区分：无筛选显示「暂无种子」，有筛选显示「没有匹配的种子」', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({ code: '200', data: { list: [], total: 0 } } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('暂无种子')
    const vm = wrapper.vm as any
    vm.filters = { name: '无命中', downloaders: [], statuses: [], trackerDomains: [] }
    await vm.runFilters()
    await Vue.nextTick()
    expect(wrapper.text()).toContain('没有匹配的种子')
    expect(wrapper.text()).not.toContain('暂无种子')
  })

  it('下拉刷新：带当前筛选重载列表', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.filters = { name: '命中', downloaders: [], statuses: ['seeding'], trackerDomains: [] }
    jest.mocked(getTorrentList).mockClear()
    await vm.onPullRefresh()
    expect(getTorrentList).toHaveBeenCalledWith(expect.objectContaining({
      name_like: '命中',
      status: ['seeding'],
      skip: 0
    }))
  })

  it('加载更多：skip 递增拼接列表', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({ code: '200', data: { list: [listTorrent], total: 2 } } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    await (wrapper.vm as any).loadMore()
    expect(getTorrentList).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 1 }))
    expect((wrapper.vm as any).list.length).toBe(2)
  })

  it('筛选选项加载失败静默：不弹错不阻塞列表', async() => {
    jest.mocked(getDownloaderList).mockRejectedValue(new Error('network') as never)
    jest.mocked(getTrackerDomains).mockRejectedValue(new Error('network') as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.downloaderOptions).toEqual([])
    expect(vm.trackerDomainOptions).toEqual([])
    // 列表照常加载（选项失败不阻塞）
    expect(getTorrentList).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.$message.error).not.toHaveBeenCalled()
  })

  it('getList 网络异常：提示错误且列表停留空态', async() => {
    jest.mocked(getTorrentList).mockRejectedValue(new Error('网络连接失败') as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith('网络连接失败')
    expect(wrapper.text()).toContain('暂无种子')
    // loading 复位（加载更多按钮可再次触发）
    expect((wrapper.vm as any).loading).toBe(false)
  })

  it('getList 信封非 200：不渲染假数据不误报错误', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({ code: '500', msg: '服务内部错误' } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('暂无种子')
    expect((wrapper.vm as any).list).toEqual([])
    // fetchPage 对非 200 信封静默（无 res.msg 分支），不弹 $message.error
    expect(wrapper.vm.$message.error).not.toHaveBeenCalled()
  })

  it('筛选生效后加载更多：skip 按过滤后列表递增并拼接', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({ code: '200', data: { list: [listTorrent], total: 3 } } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.filters = { name: '命中', downloaders: [], statuses: ['seeding'], trackerDomains: [] }
    jest.mocked(getTorrentList).mockClear()
    await vm.runFilters()
    await vm.loadMore()
    const calls = jest.mocked(getTorrentList).mock.calls
    expect(calls.length).toBe(2)
    const loadMoreCall = calls[1]
    expect(loadMoreCall).toBeTruthy()
    if (loadMoreCall) {
      const args = loadMoreCall[0]
      // 加载更多请求仍携带筛选条件（过滤后列表不被重置为全量），skip 按已加载条数递增
      expect(args).toEqual(expect.objectContaining({ name_like: '命中', status: ['seeding'] }))
      expect(args && args.skip).toBe(1)
    }
    expect(vm.list.length).toBe(2)
    expect(vm.total).toBe(3)
  })

  it('工具栏筛选计数徽标：四类筛选计数与清零', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.activeFilterCount).toBe(0)
    vm.filters = { name: 'x', downloaders: ['d1'], statuses: ['paused'], trackerDomains: ['a.com'] }
    expect(vm.activeFilterCount).toBe(4)
    await vm.resetFilters()
    expect(vm.activeFilterCount).toBe(0)
  })

  it('源码契约：简单搜索迁入落位（四字段），模板缓存链路禁回流', () => {
    const fs = require('fs') as typeof import('fs')
    const source = fs.readFileSync('src/views/mobile/torrents.vue', 'utf-8')
    expect(source).toContain('name_like')
    expect(source).toContain('downloader_id')
    expect(source).toContain('tracker_domain')
    // 查询模板页已裁撤：m2 模板缓存回填链路禁回流
    expect(source).not.toContain('m2-template-cache')
    expect(source).not.toContain('takeAppliedTemplateConditions')
    // 防回流：不再使用单一状态筛选（被多选状态取代）
    expect(source).not.toContain('statusFilter')
  })

  // ============ 2026-08-28 UX 增强：速度轮询 / 无限滚动 / 乐观状态 / 空态 CTA ============

  it('挂载不触发速度轮询（startSpeedPolling(false) 首轮延迟一个周期）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(getActiveTorrents).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('速度轮询合并：活跃行写入速度/进度，未命中行速度清零防冻结', async() => {
    const idleTorrent = { ...listTorrent, infoId: 'i2', hash: 'def', name: '停止的种子', downloadSpeed: 512, uploadSpeed: 0 }
    jest.mocked(getTorrentList).mockResolvedValue({
      code: '200',
      data: { list: [listTorrent, idleTorrent], total: 2 }
    } as never)
    jest.mocked(getActiveTorrents).mockResolvedValue({
      code: '200',
      data: [{ hash: 'abc', downloaderId: 'd1', downloadSpeed: 2048, uploadSpeed: 1024, progress: 55 }]
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.loadActiveSpeed()
    const active = vm.list.find((t: any) => t.hash === 'abc')
    const idle = vm.list.find((t: any) => t.hash === 'def')
    expect(active.downloadSpeed).toBe(2048)
    expect(active.uploadSpeed).toBe(1024)
    expect(active.progress).toBe(55)
    // active 接口只含速度>0 的种子：未命中的 def 行旧速度必须清零
    expect(idle.downloadSpeed).toBe(0)
    expect(idle.uploadSpeed).toBe(0)
    wrapper.destroy()
  })

  it('完整快照出现新的未展示复合键时重载列表，并立即展示同轮进度与速度', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any

    jest.mocked(getActiveTorrents).mockResolvedValue({ code: '200', data: [] } as never)
    await vm.loadActiveSpeed()
    jest.mocked(getTorrentList).mockClear()

    const newlyAdded = {
      ...listTorrent,
      infoId: 'new-info', torrentId: 'new-torrent', hash: 'new-hash',
      name: '刚入库种子', status: 'downloading', progress: 0,
      downloadSpeed: 0, uploadSpeed: 0
    }
    jest.mocked(getTorrentList).mockResolvedValue({
      code: '200', data: { list: [newlyAdded], total: 1 }
    } as never)
    jest.mocked(getActiveTorrents).mockResolvedValue({
      code: '200', data: [{
        hash: 'new-hash', downloader_id: 'd1',
        downloadSpeed: 16384, uploadSpeed: 256, progress: 48,
        status: 'downloading'
      }]
    } as never)

    await vm.loadActiveSpeed()

    expect(getTorrentList).toHaveBeenCalledTimes(1)
    expect(vm.list).toHaveLength(1)
    expect(vm.list[0]).toEqual(expect.objectContaining({
      hash: 'new-hash', name: '刚入库种子', progress: 48,
      downloadSpeed: 16384, uploadSpeed: 256
    }))
    wrapper.destroy()
  })

  it('连续两个完整快照未命中后核验零速终态，并把下载中行收敛到100%', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({
      code: '200',
      data: {
        list: [{ ...listTorrent, status: 'downloading', progress: 99, completedDate: null }],
        total: 1
      }
    } as never)
    jest.mocked(reconcileRuntimeTorrentStates).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: {
        list: [{
          hash: 'abc', downloader_id: 'd1', downloadSpeed: 0, uploadSpeed: 0,
          progress: 99, status: 'seeding', downloadComplete: true
        }],
        missing: []
      }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any

    await vm.loadActiveSpeed()
    expect(reconcileRuntimeTorrentStates).not.toHaveBeenCalled()
    await vm.loadActiveSpeed()

    expect(reconcileRuntimeTorrentStates).toHaveBeenCalledWith([
      { downloader_id: 'd1', hash: 'abc' }
    ])
    expect(vm.list[0]).toEqual(expect.objectContaining({
      status: 'seeding', progress: 100, downloadComplete: true,
      downloadSpeed: 0, uploadSpeed: 0
    }))
    wrapper.destroy()
  })

  it('下载中筛选启用时，终态核验完成后重新拉表移除不再匹配的行', async() => {
    jest.mocked(getTorrentList)
      .mockResolvedValueOnce({
        code: '200',
        data: { list: [{ ...listTorrent, status: 'downloading', progress: 99 }], total: 1 }
      } as never)
      .mockResolvedValueOnce({ code: '200', data: { list: [], total: 0 } } as never)
    jest.mocked(reconcileRuntimeTorrentStates).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: {
        list: [{ hash: 'abc', downloader_id: 'd1', progress: 100, status: 'seeding', downloadComplete: true }],
        missing: []
      }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.filters.statuses = ['downloading']

    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()

    expect(getTorrentList).toHaveBeenCalledTimes(2)
    expect(vm.list).toEqual([])
    wrapper.destroy()
  })

  it('终态整页刷新去重：库内状态滞后时同一完成种子只触发一次 reload（防 10s 循环）', async() => {
    // DB 恒返回 downloading 行（同步滞后场景）：终态证据只来自 reconcile 响应。
    // 每次调用返回新鲜对象——applySpeedUpdates 会原地改行数据，真实后端每响应
    // 均为新 JSON，共享引用会让 reload 拿回已突变的行、失真复现不到滞后循环
    jest.mocked(getTorrentList).mockImplementation(() =>
      Promise.resolve({
        code: '200',
        data: { list: [{ ...listTorrent, status: 'downloading', progress: 99 }], total: 1 }
      }) as never
    )
    jest.mocked(reconcileRuntimeTorrentStates).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: {
        list: [{ hash: 'abc', downloader_id: 'd1', progress: 100, status: 'seeding', downloadComplete: true }],
        missing: []
      }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.filters.statuses = ['downloading']
    jest.mocked(getTorrentList).mockClear()

    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    // 第 2 轮 reconcile 带回终态：首次触发整页 reload
    expect(getTorrentList).toHaveBeenCalledTimes(1)
    // reload 后行回到列表（DB 仍标 downloading）：后续轮询再次 reconcile，但同一
    // hash 已去重——不得再触发 reload（修复前此处每 10s 循环一次）
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(getTorrentList).toHaveBeenCalledTimes(1)
    // 筛选条件变化清空去重集合：重新建立终态处理上下文（滞后场景允许再刷新一次）
    await vm.runFilters()
    jest.mocked(getTorrentList).mockClear()
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(getTorrentList).toHaveBeenCalledTimes(1)
    wrapper.destroy()
  })

  it('刷新原子替换：reload 在途期间旧列表保留（不塌陷清空）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.list).toHaveLength(1)
    let resolveFetch: (value: unknown) => void = () => undefined
    jest.mocked(getTorrentList).mockImplementation(() => new Promise<any>(resolve => {
      resolveFetch = resolve
    }))
    const reloading = vm.reload()
    await Vue.nextTick()
    // 请求返回前旧数据必须保留（修复前 list=[] 整列塌陷、滚动跳顶）
    expect(vm.list).toHaveLength(1)
    resolveFetch({ code: '200', data: { list: [], total: 0 } })
    await reloading
    expect(vm.list).toEqual([])
    wrapper.destroy()
  })

  it('卡片速度行：速度>0 渲染 ↓/↑ 文本，零速度不渲染', async() => {
    jest.mocked(getActiveTorrents).mockResolvedValue({
      code: '200',
      data: [{ hash: 'abc', downloaderId: 'd1', downloadSpeed: 2048, uploadSpeed: 1024, progress: 100 }]
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.loadActiveSpeed()
    await vm.$nextTick()
    const speedRow = wrapper.find('.m-torrent-speed')
    expect(speedRow.exists()).toBe(true)
    expect(speedRow.text()).toContain('↓')
    expect(speedRow.text()).toContain('↑')
    expect(speedRow.text()).toContain('2.00 KB/s')
    wrapper.destroy()
  })

  it('暂停/恢复乐观状态：成功后行 status 立即更新（不整表 reload）', async() => {
    const { pauseTorrents, resumeTorrents } = jest.requireMock('@/api/torrents') as {
      pauseTorrents: jest.Mock
      resumeTorrents: jest.Mock
    }
    pauseTorrents.mockResolvedValue({ code: '200' })
    resumeTorrents.mockResolvedValue({ code: '200' })
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.pause(vm.list[0])
    expect(vm.list[0].status).toBe('paused')
    await vm.resume(vm.list[0])
    expect(vm.list[0].status).toBe('downloading')
    // 乐观更新不整表重拉（保住无限滚动已加载页）
    expect(getTorrentList).toHaveBeenCalledTimes(1)
    wrapper.destroy()
  })

  it('空态 CTA：无下载器显示"去添加下载器"，点击直达 /m/downloader?create=1', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({ code: '200', data: { list: [], total: 0 } } as never)
    jest.mocked(getDownloaderList).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const cta = wrapper.find('.m-empty-cta')
    expect(cta.exists()).toBe(true)
    expect(wrapper.text()).toContain('先添加下载器')
    await cta.trigger('click')
    expect(wrapper.vm.$router.replace).toHaveBeenCalledWith({ path: '/m/downloader', query: { create: '1' } })
    wrapper.destroy()
  })

  it('空态区分：有下载器零种子显示桌面版引导而非 CTA', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({ code: '200', data: { list: [], total: 0 } } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.find('.m-empty-cta').exists()).toBe(false)
    expect(wrapper.text()).toContain('桌面版')
    wrapper.destroy()
  })

  it('源码契约：无限滚动指令绑定与旧"加载更多"按钮移除', () => {
    const fs = require('fs') as typeof import('fs')
    const source = fs.readFileSync('src/views/mobile/torrents.vue', 'utf-8')
    expect(source).toContain('v-infinite-scroll="loadMore"')
    expect(source).toContain(':infinite-scroll-disabled="infiniteDisabled"')
    expect(source).toContain(':infinite-scroll-distance="60"')
    expect(source).not.toContain('加载更多（')
    expect(source).toContain('m-backtop')
  })

  it('返回顶部浮标：按 window scrollY 阈值显隐（实际滚动容器是 window）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    // 布局事实：.mobile-content 不内部滚动（min-height:100vh 被撑高），window 才是滚动容器
    const original = window.scrollY
    Object.defineProperty(window, 'scrollY', { value: 700, configurable: true, writable: true })
    vm.onListScroll()
    expect(vm.showBackTop).toBe(true)
    Object.defineProperty(window, 'scrollY', { value: 100, configurable: true, writable: true })
    vm.onListScroll()
    expect(vm.showBackTop).toBe(false)
    Object.defineProperty(window, 'scrollY', { value: original, configurable: true, writable: true })
    wrapper.destroy()
  })

  it('源码契约：滚动监听与回滚目标为 window（.mobile-content 不产生内部滚动）', () => {
    const fs = require('fs') as typeof import('fs')
    const source = fs.readFileSync('src/views/mobile/torrents.vue', 'utf-8')
    expect(source).toContain("window.addEventListener('scroll', this.onListScroll")
    expect(source).toContain('window.scrollY || document.documentElement.scrollTop')
    expect(source).toContain('window.scrollTo({ top: 0, behavior: \'smooth\' })')
  })

  // ============ 悬浮玻璃浮标源码契约（2026-08-28 质感升级回归保护） ============

  it('源码契约：浮标为轻微圆角方块 + 玻璃三件套（50% 全圆/实色白回归即红）', () => {
    const fs = require('fs') as typeof import('fs')
    const source = fs.readFileSync('src/views/mobile/torrents.vue', 'utf-8')
    const backtopRule = source.slice(
      source.indexOf('.m-backtop {'),
      source.indexOf('@supports not (backdrop-filter: blur(12px))')
    )
    // 轻微圆角方块（--radius-lg 12px），不得回退 50% 全圆
    expect(backtopRule).toContain('border-radius: var(--radius-lg, 12px)')
    expect(backtopRule).not.toContain('50%')
    // 与悬浮 Tab 栏（底距 8 + 高 56 = 顶边 64）保持净空：80 ≥ 64 + 12
    expect(backtopRule).toContain('bottom: calc(80px + env(safe-area-inset-bottom))')
    // 玻璃三件套与 Tab 栏同源（前缀齐全），描边/投影走主题变量
    expect(backtopRule).toContain('background: var(--glass-bg')
    expect(backtopRule).toContain('\n  backdrop-filter: blur(var(--glass-blur, 12px))')
    expect(backtopRule).toContain('\n  -webkit-backdrop-filter: blur(var(--glass-blur, 12px))')
    expect(backtopRule).toContain('border: var(--glass-border')
    expect(backtopRule).toContain('box-shadow: var(--shadow-md')
    // 层级：浮标（9）必须在 Tab 栏（10）之下
    expect(backtopRule).toContain('z-index: 9')
  })

  it('源码契约：浮标 @supports 降级为主题变量实色，条件必须字面量（防 var() 恒真坑）', () => {
    const fs = require('fs') as typeof import('fs')
    const source = fs.readFileSync('src/views/mobile/torrents.vue', 'utf-8')
    // 字面量条件（同 Tab 栏契约，勿内嵌 var()）
    expect(source).toContain('@supports not (backdrop-filter: blur(12px)) {')
    const fallback = source.slice(
      source.indexOf('@supports not (backdrop-filter: blur(12px))'),
      source.indexOf('.m-empty-title')
    )
    expect(fallback).toContain('.m-backtop')
    expect(fallback).toContain('background: var(--color-bg-primary, #FFFFFF)')
    expect(fallback).toContain('border: 1px solid var(--color-border-primary, #E5E7EB)')
  })

  // ============ 2026-09-05 四级删除（与桌面删除下拉同语义） ============

  it('卡片删除：打开四级删除对话框并记住目标行（不再直发回收站删除）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.remove(vm.list[0])
    expect(vm.deleteDialogVisible).toBe(true)
    expect(vm.deleteTarget).toEqual(expect.objectContaining({ infoId: 'i1' }))
    const { deleteTorrentsWithLevel } = jest.requireMock('@/api/torrents') as { deleteTorrentsWithLevel: jest.Mock }
    expect(deleteTorrentsWithLevel).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('四级删除确认：按等级调 delete-with-level，成功后提示并整页刷新', async() => {
    const { deleteTorrentsWithLevel } = jest.requireMock('@/api/torrents') as { deleteTorrentsWithLevel: jest.Mock }
    deleteTorrentsWithLevel.mockResolvedValue({ code: '200', data: { success_count: 1 } })
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.remove(vm.list[0])
    jest.mocked(getTorrentList).mockClear()
    await vm.confirmDelete(4)
    expect(deleteTorrentsWithLevel).toHaveBeenCalledWith({
      torrent_info_ids: ['i1'],
      delete_level: 4
    })
    expect(wrapper.vm.$message.success).toHaveBeenCalledWith('已标记为待删除')
    // 删除后整页重载（移除已删行）
    expect(getTorrentList).toHaveBeenCalledTimes(1)
    expect(vm.deleteTarget).toBe(null)
    wrapper.destroy()
  })

  it('四级删除等级1：走完全删除语义（infoId 透传、busy 复位）', async() => {
    const { deleteTorrentsWithLevel } = jest.requireMock('@/api/torrents') as { deleteTorrentsWithLevel: jest.Mock }
    deleteTorrentsWithLevel.mockResolvedValue({ code: '200', data: { success_count: 1 } })
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.remove(vm.list[0])
    await vm.confirmDelete(1)
    expect(deleteTorrentsWithLevel).toHaveBeenCalledWith({
      torrent_info_ids: ['i1'],
      delete_level: 1
    })
    expect(wrapper.vm.$message.success).toHaveBeenCalledWith('已完全删除')
    expect(vm.busyKey).toBe('')
    wrapper.destroy()
  })

  it('四级删除失败：错误提示且 busy 复位、不整页刷新', async() => {
    const { deleteTorrentsWithLevel } = jest.requireMock('@/api/torrents') as { deleteTorrentsWithLevel: jest.Mock }
    deleteTorrentsWithLevel.mockRejectedValue(new Error('下载器连接失败') as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.remove(vm.list[0])
    jest.mocked(getTorrentList).mockClear()
    await vm.confirmDelete(3)
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith('下载器连接失败')
    expect(vm.busyKey).toBe('')
    expect(getTorrentList).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('源码契约：删除走 DeleteLevelDialog + deleteTorrentsWithLevel（旧回收站单删禁回流）', () => {
    const fs = require('fs') as typeof import('fs')
    const source = fs.readFileSync('src/views/mobile/torrents.vue', 'utf-8')
    expect(source).toContain('m-delete-level-dialog')
    expect(source).toContain('deleteTorrentsWithLevel')
    expect(source).not.toContain('deleteTorrents({')
    expect(source).not.toContain('id_recycle')
  })
})
