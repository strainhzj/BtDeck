/**
 * 移动高级搜索契约（Phase 4 M2）：
 * - 纯高级搜索：复用桌面 AdvancedSearchWorkspace（已保存搜索与 Web 端同源），
 *   search 事件 → buildAdvancedSearchRequest → POST advancedSearch；
 * - 简单搜索已迁至种子页（/m/torrents），本页不再有简单查询表单与 getList；
 * - 模板应用：advanced 回填工作区并执行 / simple 交回缓存转种子页；
 * - 下拉刷新：已搜索过经 workspace.onSearch 重放，未搜索过刷新字段与模板候选。
 * 工作区以轻量 stub 替身（真实组件契约由桌面侧 spec 覆盖）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import MobileSearch from '@/views/mobile/search.vue'
import { advancedSearch } from '@/api/torrents'
import { setCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import {
  setAppliedTemplateConditions,
  takeAppliedTemplateConditions
} from '@/views/mobile/m2-template-cache'

jest.mock('@/api/torrents', () => ({
  advancedSearch: jest.fn()
}))

jest.mock('@/components/torrents/AdvancedSearchWorkspace.vue', () => ({
  name: 'AdvancedSearchWorkspace',
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

const onSearchMock = jest.fn()
const refreshFieldOptionsMock = jest.fn()
const applyTemplateGroupsMock = jest.fn()

const WorkspaceStub = Vue.extend({
  name: 'AdvancedSearchWorkspaceStub',
  template: '<div class="workspace-stub" />',
  methods: {
    onSearch: onSearchMock,
    refreshFieldOptions: refreshFieldOptionsMock,
    applyTemplateGroups: applyTemplateGroupsMock
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
    stubs: { 'advanced-search-workspace': WorkspaceStub },
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
    jest.mocked(advancedSearch).mockReset()
    jest.mocked(takeAppliedTemplateConditions).mockReturnValue(null)
    onSearchMock.mockReset()
    refreshFieldOptionsMock.mockReset()
    applyTemplateGroupsMock.mockReset()
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('工作区 search 事件：经 buildAdvancedSearchRequest 组装后 POST advancedSearch', async() => {
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
    expect(wrapper.text()).toContain('搜索命中种子')
    expect(wrapper.text()).toContain('共 1 条结果')
    expect(wrapper.vm.$message.success).toHaveBeenCalled()
  })

  it('空结果显示空态提示', async() => {
    jest.mocked(advancedSearch).mockResolvedValue({
      code: '200',
      data: { list: [], total: 0, page: 1, pageSize: 20 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    const builderParams = {
      complex_search: true as const,
      groups_count: 1,
      groups: JSON.stringify([{ logic: 'AND', conditions: [{ field: 'name', operator: 'contains', value: '无命中' }] }]),
      between_group_logics: '[]'
    }
    await vm.onBuilderSearch(builderParams)
    expect(wrapper.text()).toContain('没有匹配的种子')
  })

  it('结果卡片点击：写快照缓存并进详情', async() => {
    jest.mocked(advancedSearch).mockResolvedValue({
      code: '200',
      data: { list: [resultTorrent], total: 1, page: 1, pageSize: 20 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.openDetail(resultTorrent)
    expect(setCachedTorrent).toHaveBeenCalledWith(resultTorrent)
    expect(vm.$router.push).toHaveBeenCalledWith('/m/torrents/detail/d1/abc')
  })

  it('模板应用（advanced）：回填工作区并执行 advancedSearch', async() => {
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
    expect(applyTemplateGroupsMock).toHaveBeenCalledWith(groups, { sort_by: 'added_date', sort_order: 'desc' })
    expect(advancedSearch).toHaveBeenCalledTimes(1)
    expect(vm.appliedTip).toContain('高级模板')
  })

  it('模板应用（simple）：交回缓存并转种子页（本页不执行搜索）', async() => {
    const simpleConditions = {
      source: 'simple' as const,
      version: 1,
      listQuery: { name_like: '关键词', downloader_id: ['d1'], status: ['seeding'] }
    }
    jest.mocked(takeAppliedTemplateConditions).mockReturnValue({
      templateName: '常用查询',
      conditions: simpleConditions
    })
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(setAppliedTemplateConditions).toHaveBeenCalledWith(simpleConditions, '常用查询')
    expect(vm.$router.push).toHaveBeenCalledWith('/m/torrents')
    expect(advancedSearch).not.toHaveBeenCalled()
  })

  it('下拉刷新：已搜索过经 workspace.onSearch 重放', async() => {
    jest.mocked(advancedSearch).mockResolvedValue({
      code: '200',
      data: { list: [resultTorrent], total: 1, page: 1, pageSize: 20 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    const builderParams = {
      complex_search: true as const,
      groups_count: 1,
      groups: JSON.stringify([{ logic: 'AND', conditions: [{ field: 'name', operator: 'contains', value: '命中' }] }]),
      between_group_logics: '[]'
    }
    await vm.onBuilderSearch(builderParams)
    onSearchMock.mockClear()
    await vm.onPullRefresh()
    expect(onSearchMock).toHaveBeenCalledTimes(1)
  })

  it('下拉刷新：未搜索过刷新工作区候选（不触发搜索）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.onPullRefresh()
    expect(refreshFieldOptionsMock).toHaveBeenCalledTimes(1)
    expect(onSearchMock).not.toHaveBeenCalled()
    expect(advancedSearch).not.toHaveBeenCalled()
  })

  it('advancedSearch 信封非 200：提示后端 msg', async() => {
    jest.mocked(advancedSearch).mockResolvedValue({ code: '500', msg: '搜索失败啦' } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.executeAdvanced({ complex_search: true } as never)
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith('搜索失败啦')
    expect(vm.searched).toBe(false)
    expect(vm.searching).toBe(false)
  })

  it('advancedSearch 网络异常：提示错误且 searching 复位', async() => {
    jest.mocked(advancedSearch).mockRejectedValue(new Error('网络连接失败') as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.executeAdvanced({ complex_search: true } as never)
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith('网络连接失败')
    expect(vm.searching).toBe(false)
    expect(vm.searched).toBe(false)
  })

  it('工作区 reset 事件：清空结果与搜索态', async() => {
    jest.mocked(advancedSearch).mockResolvedValue({
      code: '200',
      data: { list: [resultTorrent], total: 1, page: 1, pageSize: 20 }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.executeAdvanced({ complex_search: true } as never)
    expect(vm.searched).toBe(true)
    vm.onBuilderReset()
    expect(vm.results).toEqual([])
    expect(vm.total).toBe(0)
    expect(vm.searched).toBe(false)
  })

  it('模板应用（advanced 无效条件组）：提示格式错误且不发起搜索', async() => {
    jest.mocked(takeAppliedTemplateConditions).mockReturnValue({
      templateName: '坏模板',
      conditions: {
        source: 'advanced',
        version: 1,
        // 空条件组触发 buildAdvancedSearchRequestFromTemplateGroups 校验失败
        condition_groups: [{ logic: 'and', conditions: [] }],
        sort_by: 'added_date',
        sort_order: 'desc'
      }
    })
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.vm.$message.error).toHaveBeenCalledWith(
      expect.stringContaining('模板条件组1没有条件')
    )
    expect(advancedSearch).not.toHaveBeenCalled()
  })

  it('rerunAdvanced：工作区 ref 缺失时静默不抛错（optional 防御）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.$refs.workspace = undefined
    expect(() => vm.rerunAdvanced()).not.toThrow()
    expect(onSearchMock).not.toHaveBeenCalled()
  })

  it('源码契约：纯高级搜索（无简单表单/模式切换），复用桌面工作区同源模板', () => {
    const fs = require('fs') as typeof import('fs')
    const source = fs.readFileSync('src/views/mobile/search.vue', 'utf-8')
    expect(source).toContain('AdvancedSearchWorkspace')
    expect(source).toContain('advanced-search-workspace')
    // 简单搜索已迁种子页：禁回流
    expect(source).not.toContain('简单查询')
    expect(source).not.toContain('switchMode')
    expect(source).not.toContain('runSimpleSearch')
    expect(source).not.toContain('simpleForm')
    expect(source).not.toContain('getTorrentList')
  })
})
