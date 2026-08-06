/**
 * 关键词列表弹窗（KeywordListModal）单元测试
 *
 * 覆盖快捷操作（左匹配）入口：
 * - 搜索框右侧显示快捷操作按钮
 * - openQuickAction 以当前池子作为源池打开对话框
 * - handleQuickActionSuccess 通知父组件刷新并重载列表
 */
import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import KeywordListModal from '@/views/tracker/components/KeywordListModal.vue'
import { ApiResponse, getPoolKeywords, GetPoolKeywordsParams, PaginatedResponse, PoolKeyword, PoolType } from '@/api/tracker'

jest.mock('@/api/tracker', () => ({
  getPoolKeywords: jest.fn(),
  deleteKeyword: jest.fn(),
  moveKeywordToPool: jest.fn(),
  batchDeleteKeywords: jest.fn(),
  batchMoveKeywords: jest.fn()
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

interface ModalVm {
  quickActionVisible: boolean
  quickActionSourcePool: PoolType | ''
  openQuickAction(): void
  handleQuickActionSuccess(): void
  loadData(): Promise<void>
}

function poolResponse(count: number): ApiResponse<PaginatedResponse<PoolKeyword>> {
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

function mountModal(poolType = 'candidate'): Wrapper<Vue> {
  return shallowMount(KeywordListModal, {
    localVue,
    propsData: {
      visible: true,
      poolType,
      keywords: []
    },
    mocks: {
      $message: message,
      $confirm: confirm
    },
    stubs: {
      'el-dialog': true,
      'el-checkbox': true,
      'el-input': true,
      'el-select': true,
      'el-option': true,
      'el-pagination': true,
      'el-empty': true,
      'el-button': true,
      'el-dropdown': true,
      'el-dropdown-menu': true,
      'el-dropdown-item': true,
      'el-tooltip': {
        // 渲染 default slot，便于断言搜索框右侧按钮
        render(this: any, h: any) {
          return h('span', this.$slots.default)
        }
      },
      'lucide-icon': true
    }
  })
}

function viewModel(wrapper: Wrapper<Vue>): ModalVm {
  return wrapper.vm as unknown as ModalVm
}

describe('keyword list modal quick action entry', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetPoolKeywords.mockImplementation((params: GetPoolKeywordsParams) => Promise.resolve(poolResponse(0)))
  })

  it('搜索框右侧显示快捷操作按钮', async() => {
    const wrapper = mountModal()
    await flushLifecycle()

    const btn = wrapper.find('.search-bar .quick-action-btn')
    expect(btn.exists()).toBe(true)
  })

  it('openQuickAction 以当前池子作为源池打开对话框', async() => {
    const wrapper = mountModal('failed')
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.openQuickAction()

    expect(vm.quickActionVisible).toBe(true)
    expect(vm.quickActionSourcePool).toBe('failed')
  })

  it('handleQuickActionSuccess 通知父组件刷新并重载列表', async() => {
    const wrapper = mountModal()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const loadDataSpy = jest.spyOn(vm, 'loadData')

    vm.handleQuickActionSuccess()

    expect(wrapper.emitted('refresh')).toBeTruthy()
    expect(loadDataSpy).toHaveBeenCalled()
  })
})
