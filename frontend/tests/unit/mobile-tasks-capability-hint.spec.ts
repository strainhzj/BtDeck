/**
 * 移动定时任务页主机形态降级提示测试（dual-mode-client Phase 4 批次 C）。
 *
 * 锁定：仅 android-server 形态（scheduled_tasks=degraded）显示省电延迟提示条；
 * desktop/加载失败不显示（兜底不惊扰）。
 */
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import MobileTasks from '@/views/mobile/tasks.vue'
import {
  PlatformCapabilitiesData,
  resetPlatformCapabilityCache,
  setPlatformCapabilityCacheForTesting
} from '@/api/platform-capabilities'

jest.mock('@/api/tasks', () => ({
  getTaskList: jest.fn().mockResolvedValue({ list: [], total: 0 }),
  executeTask: jest.fn(),
  updateTask: jest.fn(),
  interruptTask: jest.fn(),
  deleteTasks: jest.fn(),
  getTaskOutcomeMeta: jest.fn(() => null),
  isTaskDataStale: jest.fn(() => false),
  getStaleTooltipText: jest.fn(() => '')
}))

jest.mock('@/api/platform-capabilities', () => {
  const actual = jest.requireActual('@/api/platform-capabilities')
  return {
    ...actual,
    loadPlatformCapabilities: jest.fn(() => Promise.resolve(null))
  }
})

const { loadPlatformCapabilities } = jest.requireMock('@/api/platform-capabilities')

const localVue = createLocalVue()
localVue.use(ElementUI)

function androidData(): PlatformCapabilitiesData {
  return {
    platform: 'android-server',
    capabilities: {
      scheduled_tasks: { label: '定时任务调度', level: 'degraded', note: '省电下不保证准点' }
    },
    degradedCount: 1,
    unsupportedCount: 0
  }
}

function mountTasks(): Wrapper<Vue> {
  return mount(MobileTasks, {
    localVue,
    stubs: { 'm-pull-indicator': true }
  })
}

async function flushAsync(wrapper: Wrapper<Vue>): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  await wrapper.vm.$nextTick()
  await wrapper.vm.$nextTick()
}

beforeEach(() => {
  resetPlatformCapabilityCache()
  jest.clearAllMocks()
})

describe('移动任务页降级提示条', () => {
  it('android-server（scheduled_tasks=degraded）显示提示', async() => {
    (loadPlatformCapabilities as jest.Mock).mockImplementationOnce(() => {
      setPlatformCapabilityCacheForTesting(androidData())
      return Promise.resolve(androidData())
    })
    const wrapper = mountTasks()
    await flushAsync(wrapper)
    expect(wrapper.find('.m-capability-hint').exists()).toBe(true)
    expect(wrapper.text()).toContain('省电策略')
  })

  it('desktop 形态不显示提示', async() => {
    (loadPlatformCapabilities as jest.Mock).mockImplementationOnce(() => {
      setPlatformCapabilityCacheForTesting({
        platform: 'desktop',
        capabilities: {},
        degradedCount: 0,
        unsupportedCount: 0
      })
      return Promise.resolve(null)
    })
    const wrapper = mountTasks()
    await flushAsync(wrapper)
    expect(wrapper.find('.m-capability-hint').exists()).toBe(false)
  })

  it('矩阵加载失败不显示提示（兜底静默）', async() => {
    (loadPlatformCapabilities as jest.Mock).mockResolvedValueOnce(null)
    const wrapper = mountTasks()
    await flushAsync(wrapper)
    expect(wrapper.find('.m-capability-hint').exists()).toBe(false)
  })
})
