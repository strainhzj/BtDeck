/**
 * Tracker 关键词看板（keywords-board）单元测试
 *
 * 快捷操作（左匹配）的预览→执行逻辑已抽取到 KeywordQuickActionDialog 组件，
 * 其流程测试见 keyword-quick-action-dialog.spec.ts。本文件只测看板层：
 * - handleQuickAction 打开对话框并记录源池/数量
 * - 候选池卡片也显示快捷操作按钮（仅 1 个，无添加/导入/导出）
 * - 快捷操作成功后的精准刷新（删除仅源池 / 移动源+目标）
 */
import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import KeywordsBoard from '@/views/tracker/keywords-board.vue'
import {
  ApiResponse,
  getPoolKeywords,
  moveKeywordToPool,
  deleteKeyword,
  GetPoolKeywordsParams,
  PaginatedResponse,
  PoolKeyword,
  PoolType
} from '@/api/tracker'

jest.mock('@/api/tracker', () => ({
  getPoolKeywords: jest.fn(),
  deleteKeyword: jest.fn(),
  moveKeywordToPool: jest.fn()
}))

const localVue = createLocalVue()
localVue.directive('loading', {})

const mockGetPoolKeywords = getPoolKeywords as jest.MockedFunction<typeof getPoolKeywords>

const message = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
  info: jest.fn()
}
const confirm = jest.fn((..._args: unknown[]) => Promise.resolve())

// 看板 VM 类型（只暴露测试用到的成员）
interface KeywordsBoardVm {
  quickActionVisible: boolean
  quickActionSourcePool: PoolType | ''
  quickActionSourcePoolCount: number
  pools: { type: string, count: number, keywords: unknown[] }[]
  handleQuickAction(sourcePool: string): void
  handleQuickActionSuccess(payload: { sourcePool: PoolType, targetPool: PoolType | null }): Promise<void>
  loadPoolData(poolType: string): Promise<void>
}

function poolResponse(poolType: PoolType, count: number): ApiResponse<PaginatedResponse<PoolKeyword>> {
  return {
    code: '200',
    msg: 'ok',
    status: 'success',
    data: { list: [] as PoolKeyword[], total: count, page: 1, pageSize: 20 }
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
      'el-tooltip': {
        // 渲染 default slot，便于断言候选池卡片内操作按钮数量
        render(this: any, h: any) {
          return h('span', this.$slots.default)
        }
      },
      'lucide-icon': true
    }
  })
}

function viewModel(wrapper: Wrapper<Vue>): KeywordsBoardVm {
  return wrapper.vm as unknown as KeywordsBoardVm
}

describe('keywords board quick action wiring', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // mounted 会并发调 4 次 getPoolKeywords，给默认 resolved 值
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => {
      const counts: Record<PoolType, number> = { candidate: 0, ignored: 0, success: 0, failed: 0 }
      return Promise.resolve(poolResponse(params.pool_type, counts[params.pool_type]))
    })
  })

  it('handleQuickAction 打开对话框并记录源池与数量', async() => {
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => {
      const counts: Record<PoolType, number> = { candidate: 0, ignored: 0, success: 5, failed: 0 }
      return Promise.resolve(poolResponse(params.pool_type, counts[params.pool_type]))
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('success')

    expect(vm.quickActionVisible).toBe(true)
    expect(vm.quickActionSourcePool).toBe('success')
    expect(vm.quickActionSourcePoolCount).toBe(5)
  })

  it('候选池也能打开快捷操作对话框', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.handleQuickAction('candidate')

    expect(vm.quickActionVisible).toBe(true)
    expect(vm.quickActionSourcePool).toBe('candidate')
  })

  it('候选池卡片仅显示快捷操作按钮，非候选池显示 4 个操作按钮', async() => {
    const wrapper = mountView()
    await flushLifecycle()

    // 候选池：只有快捷操作（wand-sparkles）1 个按钮
    const candidateCard = wrapper.findAll('.pool-card.pool-candidate').at(0)
    expect(candidateCard.exists()).toBe(true)
    expect(candidateCard.findAll('.pool-action-btn').length).toBe(1)

    // 忽略池：添加/导入/导出 + 快捷操作共 4 个按钮
    const ignoredCard = wrapper.findAll('.pool-card.pool-ignored').at(0)
    expect(ignoredCard.findAll('.pool-action-btn').length).toBe(4)
  })

  it('快捷操作成功（删除模式）仅精准刷新源池', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const loadPoolDataSpy = jest.spyOn(vm, 'loadPoolData')

    await vm.handleQuickActionSuccess({ sourcePool: 'success', targetPool: null })

    expect(loadPoolDataSpy).toHaveBeenCalledWith('success')
    expect(loadPoolDataSpy).not.toHaveBeenCalledWith('failed')
  })

  it('快捷操作成功（移动模式）刷新源池与目标池', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const loadPoolDataSpy = jest.spyOn(vm, 'loadPoolData')

    await vm.handleQuickActionSuccess({ sourcePool: 'success', targetPool: 'failed' })

    expect(loadPoolDataSpy).toHaveBeenCalledWith('success')
    expect(loadPoolDataSpy).toHaveBeenCalledWith('failed')
  })
})
