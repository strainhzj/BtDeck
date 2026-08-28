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
import { getTorrentList, getTrackerDomains, getActiveTorrents } from '@/api/torrents'
import { getList as getDownloaderList } from '@/api/downloader'

jest.mock('@/api/torrents', () => ({
  getTorrentList: jest.fn(),
  getTrackerDomains: jest.fn(),
  getActiveTorrents: jest.fn(),
  pauseTorrents: jest.fn(),
  resumeTorrents: jest.fn(),
  deleteTorrents: jest.fn()
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
})
