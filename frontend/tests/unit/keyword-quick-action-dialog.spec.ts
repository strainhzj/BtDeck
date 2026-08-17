/**
 * 关键词快捷操作对话框（KeywordQuickActionDialog）单元测试
 *
 * 覆盖从关键词看板 keywords-board.vue 抽取出的快捷操作（左匹配）逻辑：
 * - 打开重置状态（源池 ignored → 默认目标 success）
 * - 空前缀校验、源池为空门禁、源==目标门禁
 * - 快捷删除：preview → 二次确认 → batchDeleteKeywords 用 keyword_ids → emit success(targetPool=null)
 * - 快捷移动：preview → 选目标池 → 二次确认 → batchMoveKeywords 用 keyword_ids+target_pool → emit success(targetPool)
 * - 取消二次确认保留对话框与前缀、预览失败报错、0 命中提示
 * - availableTargetPools 排除 candidate 与源池
 */
import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import KeywordQuickActionDialog from '@/views/tracker/components/KeywordQuickActionDialog.vue'
import {
  ApiResponse,
  batchDeleteKeywords,
  batchMoveKeywords,
  keywordPrefixMatchPreview,
  KeywordPrefixMatchPreviewResult,
  PoolType
} from '@/api/tracker'

jest.mock('@/api/tracker', () => ({
  batchDeleteKeywords: jest.fn(),
  batchMoveKeywords: jest.fn(),
  keywordPrefixMatchPreview: jest.fn()
}))

const localVue = createLocalVue()
localVue.directive('loading', {})

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

interface DialogVm {
  actionType: 'delete' | 'move'
  targetPool: PoolType
  prefix: string
  loading: boolean
  availableTargetPools: { value: PoolType, label: string }[]
  handleConfirm(): Promise<void>
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

function mountDialog(props: Record<string, unknown> = {}): Wrapper<Vue> {
  return shallowMount(KeywordQuickActionDialog, {
    localVue,
    propsData: {
      visible: true,
      sourcePool: 'success',
      sourcePoolLabel: '成功池',
      ...props
    },
    mocks: {
      $message: message,
      $confirm: confirm
    },
    stubs: {
      'el-dialog': true,
      'el-alert': true,
      'el-input': true,
      'el-select': true,
      'el-option': true,
      'el-button': true,
      'el-tooltip': true,
      'el-radio-group': true,
      'el-radio-button': true
    }
  })
}

function viewModel(wrapper: Wrapper<Vue>): DialogVm {
  return wrapper.vm as unknown as DialogVm
}

describe('keyword quick action dialog (prefix match)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockBatchDeleteKeywords.mockResolvedValue({ code: '200', msg: 'ok', status: 'success', data: null })
    mockBatchMoveKeywords.mockResolvedValue({ code: '200', msg: 'ok', status: 'success', data: null })
    confirm.mockClear()
    confirm.mockImplementation((..._args: unknown[]) => Promise.resolve())
  })

  it('打开时重置状态，源池 ignored 时默认目标池为 success', async() => {
    const wrapper = mountDialog({ visible: false, sourcePool: 'ignored' })
    wrapper.setProps({ visible: true })
    await flushLifecycle()
    const vm = viewModel(wrapper)
    expect(vm.actionType).toBe('delete')
    expect(vm.prefix).toBe('')
    expect(vm.targetPool).toBe('success')
  })

  it('提供操作类型切换（删除/移动到其它池），默认删除', async() => {
    const wrapper = mountDialog()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    expect(wrapper.find('.quick-action-type-group').exists()).toBe(true)
    expect(vm.actionType).toBe('delete')

    vm.actionType = 'move'
    expect(vm.actionType).toBe('move')
  })

  it('非 ignored 源池默认目标池为 ignored', async() => {
    const wrapper = mountDialog()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    expect(vm.targetPool).toBe('ignored')
  })

  it('availableTargetPools 排除 candidate 与源池', async() => {
    const wrapper = mountDialog({ sourcePool: 'success' })
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const targets = vm.availableTargetPools.map(t => t.value)
    expect(targets).not.toContain('candidate')
    expect(targets).not.toContain('success')
    expect(targets).toContain('ignored')
    expect(targets).toContain('failed')
  })

  it('空前缀提示警告且不发预览', async() => {
    const wrapper = mountDialog()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    await vm.handleConfirm()

    expect(message.warning).toHaveBeenCalled()
    expect(mockPreview).not.toHaveBeenCalled()
  })

  it('源池为空时提示且不发预览', async() => {
    const wrapper = mountDialog({ sourcePoolCount: 0 })
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.prefix = 'test'

    await vm.handleConfirm()

    expect(message.warning).toHaveBeenCalledWith('该池没有关键词')
    expect(mockPreview).not.toHaveBeenCalled()
  })

  it('0 命中提示并保留对话框', async() => {
    const wrapper = mountDialog()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.prefix = 'nomatch'
    mockPreview.mockResolvedValueOnce(previewSuccess(0, []))

    await vm.handleConfirm()

    expect(message.info).toHaveBeenCalledWith('没有匹配的关键词')
    expect(wrapper.emitted('update:visible')).toBeFalsy()
    expect(wrapper.emitted('success')).toBeFalsy()
  })

  it('快捷删除：preview→二次确认→batchDeleteKeywords 用 keyword_ids→emit success(targetPool=null)', async() => {
    const wrapper = mountDialog()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.prefix = 'test'
    mockPreview.mockResolvedValueOnce(previewSuccess(2, ['kw-1', 'kw-2']))

    await vm.handleConfirm()

    expect(mockPreview).toHaveBeenCalledWith({ pool_type: 'success', prefix: 'test' })
    expect(confirm).toHaveBeenCalled()
    expect(mockBatchDeleteKeywords).toHaveBeenCalledWith({ keyword_ids: ['kw-1', 'kw-2'] })
    expect(mockBatchMoveKeywords).not.toHaveBeenCalled()
    const payloads = wrapper.emitted('success')
    expect(payloads).toBeTruthy()
    expect(payloads && payloads[0][0]).toEqual({ sourcePool: 'success', targetPool: null })
  })

  it('快捷移动：preview→选目标池→batchMoveKeywords→emit success(targetPool)', async() => {
    const wrapper = mountDialog()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.actionType = 'move'
    vm.targetPool = 'failed'
    vm.prefix = 'test'
    mockPreview.mockResolvedValueOnce(previewSuccess(3, ['kw-1', 'kw-2', 'kw-3']))

    await vm.handleConfirm()

    expect(mockBatchMoveKeywords).toHaveBeenCalledWith({ keyword_ids: ['kw-1', 'kw-2', 'kw-3'], target_pool: 'failed' })
    expect(mockBatchDeleteKeywords).not.toHaveBeenCalled()
    const payloads = wrapper.emitted('success')
    expect(payloads && payloads[0][0]).toEqual({ sourcePool: 'success', targetPool: 'failed' })
  })

  it('取消二次确认保留对话框与前缀', async() => {
    const wrapper = mountDialog()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.prefix = '/data/leak/'
    mockPreview.mockResolvedValueOnce(previewSuccess(2, ['kw-1', 'kw-2']))
    confirm.mockImplementationOnce(() => Promise.reject(new Error('cancel')))

    await vm.handleConfirm()

    expect(mockBatchDeleteKeywords).not.toHaveBeenCalled()
    expect(mockBatchMoveKeywords).not.toHaveBeenCalled()
    expect(vm.prefix).toBe('/data/leak/')
    expect(vm.loading).toBe(false)
    expect(wrapper.emitted('success')).toBeFalsy()
  })

  it('预览接口失败时报错且保留对话框', async() => {
    const wrapper = mountDialog()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.prefix = 'test'
    mockPreview.mockRejectedValueOnce(new Error('网络错误'))

    await vm.handleConfirm()

    expect(message.error).toHaveBeenCalled()
    expect(wrapper.emitted('success')).toBeFalsy()
    expect(mockBatchDeleteKeywords).not.toHaveBeenCalled()
  })

  it('二次确认文案附带 sample 供核对', async() => {
    const wrapper = mountDialog()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.prefix = 'test'
    mockPreview.mockResolvedValueOnce(previewSuccess(2, ['kw-1', 'kw-2'], ['test-001', 'test-002']))

    await vm.handleConfirm()

    const confirmText = String(confirm.mock.calls[0][0])
    expect(confirmText).toContain('2')
    expect(confirmText).toContain('test-001')
    expect(confirmText).toContain('test-002')
  })
})
