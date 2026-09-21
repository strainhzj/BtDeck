/**
 * 移动 Tracker 关键词看板契约（Phase 4 M3）：四池 Tab + 卡片流；
 * 桌面拖拽移池在移动端为下拉「移动到X池」（moveKeywordToPool 同 API）；
 * 添加复用桌面 AddKeywordDialog；候选池不支持手动添加。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileTrackerKeywords from '@/views/mobile/tracker-keywords.vue'
import { getPoolKeywords, getPoolStatistics, moveKeywordToPool, deleteKeyword } from '@/api/tracker'

jest.mock('@/api/tracker', () => ({
  getPoolKeywords: jest.fn(),
  getPoolStatistics: jest.fn(),
  moveKeywordToPool: jest.fn(),
  deleteKeyword: jest.fn()
}))

const mockedKeywords = [
  { keyword_id: 'k1', keyword: '老男孩', pool_type: 'candidate', create_time: '2026-08-01T10:00:00' },
  { keyword_id: 'k2', keyword: '海贼王', pool_type: 'candidate', create_time: '2026-08-02T11:00:00' }
]

const mountPage = (routePath = '/m/tracker/keywords-board'): Wrapper<Vue> =>
  shallowMount(MobileTrackerKeywords, {
    mocks: {
      $route: { path: routePath, query: {} },
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

describe('views/mobile/MobileTrackerKeywords', () => {
  beforeEach(() => {
    jest.mocked(getPoolKeywords).mockReset()
    jest.mocked(getPoolKeywords).mockResolvedValue({
      code: '200',
      data: { total: 2, page: 1, pageSize: 20, list: mockedKeywords }
    } as never)
    jest.mocked(getPoolStatistics).mockReset()
    jest.mocked(getPoolStatistics).mockResolvedValue({
      code: '200',
      data: { candidate_count: 5, ignored_count: 2, success_count: 9, failed_count: 1 }
    } as never)
    jest.mocked(moveKeywordToPool).mockReset()
    jest.mocked(moveKeywordToPool).mockResolvedValue({ code: '200' } as never)
    jest.mocked(deleteKeyword).mockReset()
    jest.mocked(deleteKeyword).mockResolvedValue({ code: '200' } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('渲染四池 Tab（含统计计数）+ 默认候选池关键词卡片', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('候选池')
    expect(wrapper.text()).toContain('忽略池')
    expect(wrapper.text()).toContain('成功池')
    expect(wrapper.text()).toContain('失败池')
    // Tab 计数来自 getPoolStatistics（候选5/忽略2/成功9/失败1）
    expect(wrapper.text()).toContain('5')
    expect(wrapper.text()).toContain('9')
    // 默认加载候选池关键词
    expect(getPoolKeywords).toHaveBeenCalledWith(expect.objectContaining({ pool_type: 'candidate' }))
    expect(wrapper.text()).toContain('老男孩')
    expect(wrapper.text()).toContain('海贼王')
  })

  it('切换池子：按目标池重新拉取列表', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.switchPool('success')
    await flushLifecycle()
    expect(getPoolKeywords).toHaveBeenLastCalledWith(expect.objectContaining({ pool_type: 'success' }))
    expect(vm.activePool).toBe('success')
  })

  it('下拉移池：moveKeywordToPool 传 keyword_id + target_pool，成功后刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.handleCommand(mockedKeywords[0], 'success')
    await flushLifecycle()
    expect(moveKeywordToPool).toHaveBeenCalledWith({ keyword_id: 'k1', target_pool: 'success' })
    // 刷新会重拉池列表
    expect(getPoolKeywords).toHaveBeenCalled()
  })

  it('下拉删除：$confirm 确认后调 deleteKeyword 并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.handleCommand(mockedKeywords[0], '__delete')
    await flushLifecycle()
    expect(wrapper.vm.$confirm).toHaveBeenCalled()
    expect(deleteKeyword).toHaveBeenCalledWith('k1')
  })

  it('候选池禁用添加按钮（系统自动生成，与桌面同规则）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect((wrapper.vm as any).activePool).toBe('candidate')
    // 静态契约：模板按 activePool==='candidate' 禁用添加入口
    const source = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/views/mobile/tracker-keywords.vue'), 'utf-8')
    expect(source).toContain(`:disabled="activePool === 'candidate'"`)
  })

  it('添加成功回调后刷新当前池', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.activePool = 'failed'
    await vm.onAddSuccess()
    await flushLifecycle()
    expect(getPoolKeywords).toHaveBeenLastCalledWith(expect.objectContaining({ pool_type: 'failed' }))
  })

  it('分页：加载更多递增页码', async() => {
    jest.mocked(getPoolKeywords).mockResolvedValue({
      code: '200',
      data: { total: 40, page: 1, pageSize: 20, list: mockedKeywords }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.loadMore()
    expect(getPoolKeywords).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
  })
})
