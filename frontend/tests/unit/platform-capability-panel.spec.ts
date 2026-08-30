/**
 * 主机能力矩阵面板组件测试（dual-mode-client Phase 4 批次 B）。
 *
 * 锁定：
 * - android-server 数据：14 行、形态标签、unsupported/degraded 徽标与说明展示；
 * - desktop 数据：全 supported、无说明列内容；
 * - API 失败：兜底提示且不阻断（空数据提示，不抛错）；
 * - 窄屏（<768px）走卡片分支。
 * 数据均 mock loadPlatformCapabilities（面板不自带矩阵——单一真相源在服务端）。
 */
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import PlatformCapabilityPanel from '@/components/settings/PlatformCapabilityPanel.vue'
import {
  PlatformCapabilitiesData,
  resetPlatformCapabilityCache
} from '@/api/platform-capabilities'

jest.mock('@/api/platform-capabilities', () => {
  const actual = jest.requireActual('@/api/platform-capabilities')
  return {
    ...actual,
    loadPlatformCapabilities: jest.fn()
  }
})

const { loadPlatformCapabilities } = jest.requireMock('@/api/platform-capabilities')

const localVue = createLocalVue()
localVue.use(ElementUI)

function androidServerData(): PlatformCapabilitiesData {
  const capabilities: PlatformCapabilitiesData['capabilities'] = {}
  for (let i = 0; i < 9; i++) {
    capabilities[`cap_supported_${i}`] = { label: `能力${i}`, level: 'supported' }
  }
  capabilities.custom_scripts = {
    label: '自定义脚本任务',
    level: 'unsupported',
    note: 'Android 服务端形态不提供脚本执行；内置任务类型不受影响'
  }
  capabilities.shell_capabilities = { label: '宿主 shell', level: 'unsupported', note: '无宿主 shell 契约' }
  capabilities.always_on_service = { label: '常驻服务端', level: 'unsupported', note: '临时/轻量定位' }
  capabilities.host_filesystem = { label: '宿主文件系统', level: 'degraded', note: '仅应用私有与 SAF 授权目录' }
  capabilities.scheduled_tasks = { label: '定时任务', level: 'degraded', note: '省电下不保证准点' }
  return {
    platform: 'android-server',
    capabilities,
    degradedCount: 2,
    unsupportedCount: 3
  }
}

function desktopData(): PlatformCapabilitiesData {
  const capabilities: PlatformCapabilitiesData['capabilities'] = {}
  for (let i = 0; i < 14; i++) {
    capabilities[`cap_${i}`] = { label: `能力${i}`, level: 'supported' }
  }
  return { platform: 'desktop', capabilities, degradedCount: 0, unsupportedCount: 0 }
}

function mountPanel(): Wrapper<Vue> {
  return mount(PlatformCapabilityPanel, {
    localVue,
    stubs: { transition: false }
  })
}

/** flush mounted 的 then+finally 两层微任务并等待重渲染。 */
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

describe('PlatformCapabilityPanel（android-server 形态）', () => {
  beforeEach(() => {
    (loadPlatformCapabilities as jest.Mock).mockResolvedValue(androidServerData())
  })

  it('渲染 14 行能力与形态标签', async() => {
    const wrapper = mountPanel()
    await flushAsync(wrapper)
    const html = wrapper.html()
    expect(html).toContain('Android 服务端')
    expect(wrapper.findAll('.capability-table .el-table__row').length + (html.includes('capability-cards') ? wrapper.findAll('.capability-card').length : 0)).toBeGreaterThan(0)
    expect((Object.keys(androidServerData().capabilities)).length).toBe(14)
  })

  it('unsupported 项显示 danger 徽标与降级说明', async() => {
    const wrapper = mountPanel()
    await flushAsync(wrapper)
    const html = wrapper.html()
    expect(html).toContain('不支持')
    expect(html).toContain('受限')
    expect(html).toContain('Android 服务端形态不提供脚本执行')
  })

  it('降级计数随数据展示', async() => {
    const wrapper = mountPanel()
    await flushAsync(wrapper)
    expect(wrapper.html()).toContain('降级 2 项')
    expect(wrapper.html()).toContain('不支持 3 项')
  })
})

describe('PlatformCapabilityPanel（desktop 形态）', () => {
  beforeEach(() => {
    (loadPlatformCapabilities as jest.Mock).mockResolvedValue(desktopData())
  })

  it('全部支持、无降级徽标', async() => {
    const wrapper = mountPanel()
    await flushAsync(wrapper)
    expect(wrapper.html()).toContain('桌面 / 服务器')
    expect(wrapper.find('.el-tag--danger').exists()).toBe(false)
    expect(wrapper.find('.el-tag--warning').exists()).toBe(false)
    expect(wrapper.html()).toContain('支持')
  })
})

describe('PlatformCapabilityPanel（异常兜底）', () => {
  it('API 失败显示兜底提示且不阻断', async() => {
    (loadPlatformCapabilities as jest.Mock).mockResolvedValue(null)
    const wrapper = mountPanel()
    await flushAsync(wrapper)
    expect(wrapper.html()).toContain('能力信息暂不可用')
    expect(wrapper.html()).toContain('默认按全能力展示')
  })
})

describe('PlatformCapabilityPanel（窄屏卡片分支）', () => {
  it('innerWidth<768 走卡片渲染', async() => {
    const original = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true, writable: true })
    try {
      (loadPlatformCapabilities as jest.Mock).mockResolvedValue(androidServerData())
      const wrapper = mountPanel()
      await flushAsync(wrapper)
      expect(wrapper.find('.capability-cards').exists()).toBe(true)
      expect(wrapper.find('.capability-table').exists()).toBe(false)
      expect(wrapper.findAll('.capability-card').length).toBe(14)
    } finally {
      Object.defineProperty(window, 'innerWidth', { value: original, configurable: true, writable: true })
    }
  })
})
