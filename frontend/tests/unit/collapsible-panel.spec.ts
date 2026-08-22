import { shallowMount, createLocalVue } from '@vue/test-utils'
import CollapsiblePanel from '@/components/CollapsiblePanel.vue'
import { getStorage, setStorage } from '@/utils/cookies'

/**
 * 通用可折叠面板回归（verified-bugfix-remediation W8-1）：
 * - 折叠态按 storageKey 持久化（'1'=折叠 / '0'=展开）
 * - 未设置存储值时回退 defaultCollapsed（默认展开）
 * - 多实例键隔离（互不干扰）
 * - a11y：aria-expanded / aria-controls
 */

jest.mock('@/utils/cookies', () => ({
  getStorage: jest.fn(),
  setStorage: jest.fn()
}))

const mockGetStorage = getStorage as jest.MockedFunction<typeof getStorage>
const mockSetStorage = setStorage as jest.MockedFunction<typeof setStorage>

const localVue = createLocalVue()

function mountPanel(props: Record<string, unknown> = {}) {
  return shallowMount(CollapsiblePanel, {
    localVue,
    propsData: {
      title: '测试面板',
      ...props
    }
  })
}

const collapsedOf = (wrapper: ReturnType<typeof mountPanel>) =>
  (wrapper.vm as unknown as { isCollapsed: boolean }).isCollapsed

describe('CollapsiblePanel 折叠与持久化', () => {
  beforeEach(() => {
    mockGetStorage.mockClear()
    mockSetStorage.mockClear()
  })

  it('无 storageKey 时默认展开且不写存储', () => {
    const wrapper = mountPanel()
    expect(collapsedOf(wrapper)).toBe(false)
    expect(mockGetStorage).not.toHaveBeenCalled()
    expect(mockSetStorage).not.toHaveBeenCalled()
  })

  it('storageKey 未设置（null）时回退 defaultCollapsed', () => {
    mockGetStorage.mockReturnValue(null)
    const wrapper = mountPanel({ storageKey: 'btdeck_test_panel', defaultCollapsed: true })
    expect(collapsedOf(wrapper)).toBe(true)
  })

  it('storageKey 显式 \'1\' 时恢复折叠态', () => {
    mockGetStorage.mockReturnValue('1')
    const wrapper = mountPanel({ storageKey: 'btdeck_test_panel' })
    expect(collapsedOf(wrapper)).toBe(true)
  })

  it('storageKey 显式 \'0\' 时保持展开', () => {
    mockGetStorage.mockReturnValue('0')
    const wrapper = mountPanel({ storageKey: 'btdeck_test_panel' })
    expect(collapsedOf(wrapper)).toBe(false)
  })

  it('点击切换折叠并持久化（\'1\'/\'0\'）', async() => {
    mockGetStorage.mockReturnValue(null)
    const wrapper = mountPanel({ storageKey: 'btdeck_test_panel' })
    const button = wrapper.find('.collapsible-panel__toggle')
    expect(button.attributes('aria-expanded')).toBe('true')

    await button.trigger('click')
    expect(collapsedOf(wrapper)).toBe(true)
    expect(mockSetStorage).toHaveBeenCalledWith('btdeck_test_panel', '1')
    expect(button.attributes('aria-expanded')).toBe('false')

    await button.trigger('click')
    expect(collapsedOf(wrapper)).toBe(false)
    expect(mockSetStorage).toHaveBeenLastCalledWith('btdeck_test_panel', '0')
  })

  it('折叠时内容区隐藏（v-show）', async() => {
    mockGetStorage.mockReturnValue(null)
    const wrapper = mountPanel({ storageKey: 'btdeck_test_panel' })
    const content = wrapper.find('.collapsible-panel__content')
    expect(content.isVisible()).toBe(true)

    await wrapper.find('.collapsible-panel__toggle').trigger('click')
    expect(wrapper.find('.collapsible-panel__content').isVisible()).toBe(false)
  })

  it('多实例 storageKey 互不干扰', () => {
    mockGetStorage.mockImplementation((key: string) => (key === 'btdeck_panel_a' ? '1' : null))
    const a = mountPanel({ storageKey: 'btdeck_panel_a' })
    const b = mountPanel({ storageKey: 'btdeck_panel_b' })
    expect(collapsedOf(a)).toBe(true)
    expect(collapsedOf(b)).toBe(false)
  })
})
