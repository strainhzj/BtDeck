/**
 * 移动关键词全局搜索契约（Phase 4 M3）：searchAllPools 全池检索；
 * 筛选字段与桌面搜索页同集（keyword/pool_types/time_range/sort_by）；
 * 卡片移动/删除复用 moveKeywordToPool/deleteKeyword。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileTrackerKeywordsSearch from '@/views/mobile/tracker-keywords-search.vue'
import { searchAllPools, moveKeywordToPool, deleteKeyword } from '@/api/tracker'

jest.mock('@/api/tracker', () => ({
  searchAllPools: jest.fn(),
  moveKeywordToPool: jest.fn(),
  deleteKeyword: jest.fn()
}))

const mockedResults = [
  { keyword_id: 'k1', keyword: '老男孩', pool_type: 'candidate', pool_label: '候选池', create_time: '2026-08-01T10:00:00' },
  { keyword_id: 'k2', keyword: '海贼王', pool_type: 'success', pool_label: '成功池', create_time: '2026-08-02T11:00:00' }
]

const mountPage = (query: Record<string, string> = {}): Wrapper<Vue> =>
  shallowMount(MobileTrackerKeywordsSearch, {
    mocks: {
      $route: { path: '/m/tracker/keywords-search', query },
      $router: { push: jest.fn(), replace: jest.fn() },
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
      $confirm: jest.fn().mockResolvedValue('confirm')
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileTrackerKeywordsSearch', () => {
  beforeEach(() => {
    jest.mocked(searchAllPools).mockReset()
    jest.mocked(searchAllPools).mockResolvedValue({
      code: '200',
      data: { total: 2, page: 1, pageSize: 20, list: mockedResults }
    } as never)
    jest.mocked(moveKeywordToPool).mockReset()
    jest.mocked(moveKeywordToPool).mockResolvedValue({ code: '200' } as never)
    jest.mocked(deleteKeyword).mockReset()
    jest.mocked(deleteKeyword).mockResolvedValue({ code: '200' } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('渲染结果卡片：关键词 + 池徽标 + 时间', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('老男孩')
    expect(wrapper.text()).toContain('海贼王')
    expect(wrapper.text()).toContain('候选池')
    expect(wrapper.text()).toContain('成功池')
  })

  it('路由 ?keyword= 初始关键词透传检索', async() => {
    mountPage({ keyword: '老男孩' })
    await flushLifecycle()
    expect(searchAllPools).toHaveBeenCalledWith(expect.objectContaining({ keyword: '老男孩' }))
  })

  it('筛选透传：池子（逗号拼接）/时间/排序与桌面同字段集', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.keyword = '王'
    vm.selectedPools = ['candidate', 'success']
    vm.timeRange = 'today'
    vm.sortBy = 'name_asc'
    await vm.reload()
    expect(searchAllPools).toHaveBeenLastCalledWith(expect.objectContaining({
      keyword: '王',
      pool_types: 'candidate,success',
      time_range: 'today',
      sort_by: 'name_asc'
    }))
  })

  it('移动：moveKeywordToPool 后刷新；原地移动短路不调 API', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.handleMove(mockedResults[0], 'success')
    await flushLifecycle()
    expect(moveKeywordToPool).toHaveBeenCalledWith({ keyword_id: 'k1', target_pool: 'success' })
    // 原地移动（目标池=当前池）直接短路
    jest.mocked(moveKeywordToPool).mockClear()
    await vm.handleMove(mockedResults[1], 'success')
    expect(moveKeywordToPool).not.toHaveBeenCalled()
  })

  it('删除：$confirm 确认后调 deleteKeyword 并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.confirmDelete(mockedResults[0])
    await flushLifecycle()
    expect(wrapper.vm.$confirm).toHaveBeenCalled()
    expect(deleteKeyword).toHaveBeenCalledWith('k1')
  })

  it('分页：加载更多递增页码', async() => {
    jest.mocked(searchAllPools).mockResolvedValue({
      code: '200',
      data: { total: 40, page: 1, pageSize: 20, list: mockedResults }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.loadMore()
    expect(searchAllPools).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
  })
})
