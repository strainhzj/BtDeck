/**
 * 移动高级搜索契约（Phase 4 M2）：
 * - 简单查询与桌面快捷筛选同字段集（名称/下载器/状态/Tracker 域）→ getList；
 * - 高级搜索复用桌面 AdvancedSearchBuilder 的事件出口（search → build → POST）；
 * - 模板应用：simple 填表执行 / advanced 回填构建器 + FromTemplateGroups 构建；
 * - builder save-template → createSearchTemplate（source=advanced）。
 * 构建器以轻量 stub 替身（真实组件契约由其自有 spec 覆盖）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import MobileSearch from '@/views/mobile/search.vue'
import {
  getTorrentList,
  advancedSearch,
  createSearchTemplate,
  getTrackerDomains
} from '@/api/torrents'
import { getList as getDownloaderList } from '@/api/downloader'
import { setCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import { takeAppliedTemplateConditions } from '@/views/mobile/m2-template-cache'

jest.mock('@/api/torrents', () => ({
  getTorrentList: jest.fn(),
  advancedSearch: jest.fn(),
  createSearchTemplate: jest.fn(),
  getTrackerDomains: jest.fn()
}))

jest.mock('@/api/downloader', () => ({
  getList: jest.fn()
}))

jest.mock('@/components/torrents/AdvancedSearchBuilder.vue', () => ({
  name: 'AdvancedSearchBuilder',
  render: (h: (t: string) => unknown) => h('div')
}))

jest.mock('@/views/mobile/m2-template-cache', () => ({
  setAppliedTemplateConditions: jest.fn(),
  takeAppliedTemplateConditions: jest.fn().mockReturnValue(null)
}))

jest.mock('@/views/mobile/torrent-detail-cache', () => ({
  setCachedTorrent: jest.fn(),
  takeCachedTorrent: jest.fn()
}))

const applyTemplateGroupsMock = jest.fn()
const buildSearchParamsMock = jest.fn()

const BuilderStub = Vue.extend({
  name: 'AdvancedSearchBuilderStub',
  template: '<div class="builder-stub" />',
  methods: {
    applyTemplateGroups: applyTemplateGroupsMock,
    buildSearchParams: buildSearchParamsMock
  }
})

const resultTorrent = {
  infoId: 'i1',
  downloaderId: 'd1',
  downloaderName: 'qb',
  torrentId: 't1',
  hash: 'abc',
  name: '搜索命中种子',
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
  shallowMount(MobileSearch, {
    stubs: { 'advanced-search-builder': BuilderStub },
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
      $router: { push: jest.fn().mockResolvedValue(undefined), replace: jest.fn().mockResolvedValue(undefined) }
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileSearch', () => {
  beforeEach(() => {
    jest.mocked(getTorrentList).mockReset()
    jest.mocked(advancedSearch).mockReset()
    jest.mocked(createSearchTemplate).mockReset()
    jest.mocked(getTrackerDomains).mockReset()
    jest.mocked(getTrackerDomains).mockResolvedValue({ code: '200', data: ['tracker.example.com'] } as never)
    jest.mocked(getDownloaderList).mockReset()
    jest.mocked(getDownloaderList).mockResolvedValue({ code: '200', data: [{ id: 'd1', nickname: 'QB' }] } as never)
    jest.mocked(takeAppliedTemplateConditions).mockReturnValue(null)
    applyTemplateGroupsMock.mockReset()
    buildSearchParamsMock.mockReset()
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('模式切换与筛选选项加载', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.downloaderOptions).toEqual([{ label: 'QB', value: 'd1' }])
    expect(vm.trackerDomainOptions).toEqual(['tracker.example.com'])
    vm.switchMode('advanced')
    expect(vm.mode).toBe('advanced')
  })

  it('简单查询：字段透传 getList 并渲染结果卡片', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({
      code: '200',
      data: { list: [resultTorrent], total: 1 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.simpleForm = { name: '命中', downloaders: ['d1'], statuses: ['seeding'], trackerDomains: ['tracker.example.com'] }
    await vm.runSimpleSearch()
    expect(getTorrentList).toHaveBeenCalledWith(expect.objectContaining({
      name_like: '命中',
      downloader_id: ['d1'],
      status: ['seeding'],
      tracker_domain: ['tracker.example.com'],
      sort_by: 'added_date'
    }))
    expect(wrapper.text()).toContain('搜索命中种子')
    expect(wrapper.text()).toContain('共 1 条结果')
  })

  it('空结果显示空态提示', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({
      code: '200',
      data: { list: [], total: 0 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.runSimpleSearch()
    expect(wrapper.text()).toContain('没有匹配的种子')
  })

  it('结果卡片点击：写快照缓存并进详情', async() => {
    jest.mocked(getTorrentList).mockResolvedValue({
      code: '200',
      data: { list: [resultTorrent], total: 1 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.runSimpleSearch()
    vm.openDetail(resultTorrent)
    expect(setCachedTorrent).toHaveBeenCalledWith(resultTorrent)
    expect(vm.$router.push).toHaveBeenCalledWith('/m/torrents/detail/d1/abc')
  })

  it('构建器 search 事件：经 buildAdvancedSearchRequest 组装后 POST advancedSearch', async() => {
    jest.mocked(advancedSearch).mockResolvedValue({
      code: '200',
      data: { list: [resultTorrent], total: 1, page: 1, pageSize: 20 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    // 桌面构建器载荷形态（groups 为 JSON 字符串）
    const builderParams = {
      complex_search: true as const,
      groups_count: 1,
      groups: JSON.stringify([{ logic: 'AND', conditions: [{ field: 'name', operator: 'contains', value: '命中' }] }]),
      between_group_logics: '[]'
    }
    await vm.onBuilderSearch(builderParams)
    expect(advancedSearch).toHaveBeenCalledTimes(1)
    const request = jest.mocked(advancedSearch).mock.calls[0][0]
    expect(request.condition_groups).toBeTruthy()
    expect(wrapper.vm.$message.success).toHaveBeenCalled()
  })

  it('模板应用（simple）：回填表单并执行 getList', async() => {
    jest.mocked(takeAppliedTemplateConditions).mockReturnValue({
      templateName: '常用查询',
      conditions: {
        source: 'simple',
        version: 1,
        listQuery: { name_like: '关键词', downloader_id: ['d1'], status: ['seeding'] }
      }
    })
    jest.mocked(getTorrentList).mockResolvedValue({
      code: '200',
      data: { list: [resultTorrent], total: 1 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.simpleForm.name).toBe('关键词')
    expect(vm.simpleForm.downloaders).toEqual(['d1'])
    expect(getTorrentList).toHaveBeenCalledWith(expect.objectContaining({ name_like: '关键词' }))
    expect(vm.appliedTip).toContain('常用查询')
  })

  it('模板应用（advanced）：切高级模式、回填构建器并执行 advancedSearch', async() => {
    const groups = [{ conditions: [{ field: 'name', operator: 'contains', value: 'x' }], logic: 'AND' }]
    jest.mocked(takeAppliedTemplateConditions).mockReturnValue({
      templateName: '高级模板',
      conditions: { source: 'advanced', version: 1, condition_groups: groups, sort_by: 'added_date', sort_order: 'desc' }
    })
    jest.mocked(advancedSearch).mockResolvedValue({
      code: '200',
      data: { list: [resultTorrent], total: 1, page: 1, pageSize: 20 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.mode).toBe('advanced')
    expect(applyTemplateGroupsMock).toHaveBeenCalled()
    expect(advancedSearch).toHaveBeenCalledTimes(1)
  })

  it('builder save-template：转换为 createSearchTemplate（source=advanced）', async() => {
    jest.mocked(createSearchTemplate).mockResolvedValue({ code: '200' } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.onSaveTemplate({
      id: 'x',
      name: '新模板',
      description: '描述',
      isDefault: false,
      conditions: [{ conditions: [{ field: 'name', operator: 'contains', value: 'x' }] }],
      createdTime: '2026-08-24T00:00:00'
    })
    expect(createSearchTemplate).toHaveBeenCalledWith(expect.objectContaining({
      name: '新模板',
      is_public: false
    }))
    const arg = jest.mocked(createSearchTemplate).mock.calls[0][0]
    expect(arg.conditions.source).toBe('advanced')
    expect(wrapper.vm.$message.success).toHaveBeenCalled()
  })
})
