/**
 * Tracker 关键词看板（keywords-board）单元测试
 *
 * 重点覆盖快捷操作（左匹配）：
 * - 打开/关闭对话框、空前缀校验、源池为空门禁、源==目标门禁
 * - 快捷删除：preview → 二次确认 → batchDeleteKeywords 用 keyword_ids → 精准刷新源池
 * - 快捷移动：preview → 选目标池 → 二次确认 → batchMoveKeywords 用 keyword_ids+target_pool → 精准刷新
 * - 取消二次确认保留对话框与前缀、预览失败报错、0 命中提示
 *
 * 装配对齐 orphan-files.spec.ts：shallowMount + 整体 jest.mock('@/api/tracker') + stub Element 组件。
 */
import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import KeywordsBoard from '@/views/tracker/keywords-board.vue'
import {
  ApiResponse,
  batchDeleteKeywords,
  batchMoveKeywords,
  GetPoolKeywordsParams,
  getPoolKeywords,
  keywordPrefixMatchPreview,
  KeywordPrefixMatchPreviewResult,
  PaginatedResponse,
  PoolKeyword,
  PoolType
} from '@/api/tracker'

jest.mock('@/api/tracker', () => ({
  getPoolKeywords: jest.fn(),
  deleteKeyword: jest.fn(),
  moveKeywordToPool: jest.fn(),
  batchDeleteKeywords: jest.fn(),
  batchMoveKeywords: jest.fn(),
  keywordPrefixMatchPreview: jest.fn()
}))

const localVue = createLocalVue()
localVue.directive('loading', {})

const mockGetPoolKeywords = getPoolKeywords as jest.MockedFunction<typeof getPoolKeywords>
const mockBatchDeleteKeywords = batchDeleteKeywords as jest.MockedFunction<typeof batchDeleteKeywords>
const mockBatchMoveKeywords = batchMoveKeywords as jest.MockedFunction<typeof batchMoveKeywords>
const mockPreview = keywordPrefixMatchPreview as jest.MockedFunction<typeof keywordPrefixMatchPreview>

const message = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
  info: jest.fn()
}
const confirm = jest.fn((..._args: unknown[]) => Promise.resolve())

// 看板 VM 类型（只暴露测试用到的成员）
interface KeywordsBoardVm {
  quickActionDialogVisible: boolean
  quickActionType: 'delete' | 'move' | null
  quickActionSourcePool: PoolType | ''
  quickActionTargetPool: PoolType
  quickActionPrefix: string
  quickActionLoading: boolean
  pools: { type: string, count: number, keywords: unknown[] }[]
  handleQuickAction(sourcePool: string): void
  handleQuickActionCancel(): void
  handleQuickActionConfirm(): Promise<void>
  loadPoolData(poolType: string): Promise<void>
  get availableTargetPools(): { value: PoolType, label: string }[]
}

function poolResponse(poolType: PoolType, count: number): ApiResponse<PaginatedResponse<PoolKeyword>> {
  return {
    code: '200',
    msg: 'ok',
    status: 'success',
    data: { list: [] as PoolKeyword[], total: count, page: 1, pageSize: 20 }
  }
}

function previewSuccess(count: number, keywordIds: string[], samples?: string[]): ApiResponse<KeywordPrefixMatchPreviewResult> {
  return {
    code: '200',
    msg: 'ok',
    status: 'success',
    data: {
      count,
      sample_keywords: samples || keywordIds.slice(0, 5),
      keyword_ids: keywordIds
    }
  }
}

async function flushLifecycle(): Promise<void> {
  for (let index = 0; index < 15; index += 1) {
    await Promise.resolve()
  }
  await localVue.nextTick()
}

function mountView(): Wrapper<Vue> {
  return shallowMount(KeywordsBoard, {
    localVue,
    mocks: {
      $message: message,
      $confirm: confirm
    },
    stubs: {
      'el-button': true,
      'el-dialog': true,
      'el-alert': true,
      'el-input': true,
      'el-select': true,
      'el-option': true,
      'el-tooltip': true,
      'lucide-icon': true
    }
  })
}

function viewModel(wrapper: Wrapper<Vue>): KeywordsBoardVm {
  return wrapper.vm as unknown as KeywordsBoardVm
}

describe('keywords board quick action (prefix match)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // mounted 会并发调 4 次 getPoolKeywords，给默认 resolved 值
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => {
      const counts: Record<PoolType, number> = { candidate: 0, ignored: 0, success: 0, failed: 0 }
      return Promise.resolve(poolResponse(params.pool_type, counts[params.pool_type]))
    })
    mockBatchDeleteKeywords.mockResolvedValue({ code: '200', msg: 'ok', status: 'success', data: null })
    mockBatchMoveKeywords.mockResolvedValue({ code: '200', msg: 'ok', status: 'success', data: null })
    confirm.mockClear()
    confirm.mockImplementation((..._args: unknown[]) => Promise.resolve())
  })

  it('handleQuickAction 打开对话框并重置前缀、记录源池', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.quickActionPrefix = '旧前缀'

    vm.handleQuickAction('success')

    expect(vm.quickActionDialogVisible).toBe(true)
    expect(vm.quickActionPrefix).toBe('')
    expect(vm.quickActionSourcePool).toBe('success')
    expect(vm.quickActionType).toBe('delete')
    // 源池 success 非 ignored，默认目标应为 ignored
    expect(vm.quickActionTargetPool).toBe('ignored')
  })

  it('源池为 ignored 时默认目标池为 success', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('ignored')
    expect(vm.quickActionTargetPool).toBe('success')
  })

  it('handleQuickActionCancel 关闭对话框', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('success')
    vm.handleQuickActionCancel()

    expect(vm.quickActionDialogVisible).toBe(false)
  })

  it('空前缀提示警告且不发请求', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('success')
    await vm.handleQuickActionConfirm()

    expect(message.warning).toHaveBeenCalled()
    expect(mockPreview).not.toHaveBeenCalled()
  })

  it('源池为空时提示且不发请求', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('success')
    vm.quickActionPrefix = 'test'
    // success 池 count 为 0（beforeEach 默认）
    await vm.handleQuickActionConfirm()

    expect(message.warning).toHaveBeenCalledWith('该池没有关键词')
    expect(mockPreview).not.toHaveBeenCalled()
  })

  it('0 命中提示并保留对话框', async() => {
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => {
      // 让 success 池有数据，通过源池为空门禁
      const counts: Record<PoolType, number> = { candidate: 0, ignored: 0, success: 5, failed: 0 }
      return Promise.resolve(poolResponse(params.pool_type, counts[params.pool_type]))
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('success')
    vm.quickActionPrefix = 'nomatch'
    mockPreview.mockResolvedValueOnce(previewSuccess(0, []))

    await vm.handleQuickActionConfirm()

    expect(message.info).toHaveBeenCalledWith('没有匹配的关键词')
    expect(vm.quickActionDialogVisible).toBe(true)
  })

  it('快捷删除：preview→二次确认→batchDeleteKeywords 用 keyword_ids→精准刷新源池', async() => {
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => {
      const counts: Record<PoolType, number> = { candidate: 0, ignored: 0, success: 10, failed: 0 }
      return Promise.resolve(poolResponse(params.pool_type, counts[params.pool_type]))
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const loadPoolDataSpy = jest.spyOn(vm, 'loadPoolData')

    vm.handleQuickAction('success')
    vm.quickActionPrefix = 'test'
    mockPreview.mockResolvedValueOnce(previewSuccess(2, ['kw-1', 'kw-2']))

    await vm.handleQuickActionConfirm()

    // 预览调用参数：pool_type=源池 success，prefix=test
    expect(mockPreview).toHaveBeenCalledWith({ pool_type: 'success', prefix: 'test' })
    // 二次确认被调用
    expect(confirm).toHaveBeenCalled()
    // 批量删除用 keyword_ids
    expect(mockBatchDeleteKeywords).toHaveBeenCalledWith({ keyword_ids: ['kw-1', 'kw-2'] })
    expect(mockBatchMoveKeywords).not.toHaveBeenCalled()
    // 精准刷新：仅源池 success（非 4 池全刷）
    expect(loadPoolDataSpy).toHaveBeenCalledWith('success')
    expect(loadPoolDataSpy).not.toHaveBeenCalledWith('failed')
    expect(vm.quickActionDialogVisible).toBe(false)
  })

  it('快捷移动：preview→选目标池→batchMoveKeywords 用 keyword_ids+target_pool→精准刷新源+目标', async() => {
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => {
      const counts: Record<PoolType, number> = { candidate: 0, ignored: 0, success: 10, failed: 0 }
      return Promise.resolve(poolResponse(params.pool_type, counts[params.pool_type]))
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const loadPoolDataSpy = jest.spyOn(vm, 'loadPoolData')

    vm.handleQuickAction('success')
    vm.quickActionType = 'move'
    vm.quickActionTargetPool = 'failed'
    vm.quickActionPrefix = 'test'
    mockPreview.mockResolvedValueOnce(previewSuccess(3, ['kw-1', 'kw-2', 'kw-3']))

    await vm.handleQuickActionConfirm()

    expect(mockBatchMoveKeywords).toHaveBeenCalledWith({ keyword_ids: ['kw-1', 'kw-2', 'kw-3'], target_pool: 'failed' })
    expect(mockBatchDeleteKeywords).not.toHaveBeenCalled()
    // 精准刷新：源池 + 目标池
    expect(loadPoolDataSpy).toHaveBeenCalledWith('success')
    expect(loadPoolDataSpy).toHaveBeenCalledWith('failed')
  })

  it('availableTargetPools 排除 candidate 与源池', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.quickActionSourcePool = 'success'
    const targets = vm.availableTargetPools.map(t => t.value)
    expect(targets).not.toContain('candidate')
    expect(targets).not.toContain('success')
    expect(targets).toContain('ignored')
    expect(targets).toContain('failed')
  })

  it('取消二次确认保留对话框与前缀', async() => {
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => {
      const counts: Record<PoolType, number> = { candidate: 0, ignored: 0, success: 10, failed: 0 }
      return Promise.resolve(poolResponse(params.pool_type, counts[params.pool_type]))
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('success')
    vm.quickActionPrefix = '/data/leak/'
    mockPreview.mockResolvedValueOnce(previewSuccess(2, ['kw-1', 'kw-2']))
    confirm.mockImplementationOnce(() => Promise.reject(new Error('cancel')))

    await vm.handleQuickActionConfirm()

    // 用户取消：不执行删除/移动
    expect(mockBatchDeleteKeywords).not.toHaveBeenCalled()
    expect(mockBatchMoveKeywords).not.toHaveBeenCalled()
    // 保留对话框与前缀
    expect(vm.quickActionDialogVisible).toBe(true)
    expect(vm.quickActionPrefix).toBe('/data/leak/')
    // loading 复位
    expect(vm.quickActionLoading).toBe(false)
  })

  it('预览接口失败时报错且保留对话框', async() => {
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => {
      const counts: Record<PoolType, number> = { candidate: 0, ignored: 0, success: 10, failed: 0 }
      return Promise.resolve(poolResponse(params.pool_type, counts[params.pool_type]))
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('success')
    vm.quickActionPrefix = 'test'
    mockPreview.mockRejectedValueOnce(new Error('网络错误'))

    await vm.handleQuickActionConfirm()

    expect(message.error).toHaveBeenCalled()
    expect(vm.quickActionDialogVisible).toBe(true)
    expect(mockBatchDeleteKeywords).not.toHaveBeenCalled()
  })

  it('二次确认文案附带 sample 供核对', async() => {
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => {
      const counts: Record<PoolType, number> = { candidate: 0, ignored: 0, success: 10, failed: 0 }
      return Promise.resolve(poolResponse(params.pool_type, counts[params.pool_type]))
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('success')
    vm.quickActionPrefix = 'test'
    mockPreview.mockResolvedValueOnce(previewSuccess(2, ['kw-1', 'kw-2'], ['test-001', 'test-002']))

    await vm.handleQuickActionConfirm()

    const confirmText = String(confirm.mock.calls[0][0])
    expect(confirmText).toContain('2')
    expect(confirmText).toContain('test-001')
    expect(confirmText).toContain('test-002')
  })
})
