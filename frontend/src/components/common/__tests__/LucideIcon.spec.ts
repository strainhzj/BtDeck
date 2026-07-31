import { mount, createLocalVue } from '@vue/test-utils'
import ElementUI from 'element-ui'
import LucideIcon from '../LucideIcon.vue'

const localVue = createLocalVue()
localVue.use(ElementUI)

describe('LucideIcon 组件', () => {
  it('已知图标应渲染 <svg>，根属性带 viewBox 且 stroke=currentColor', () => {
    const wrapper = mount(LucideIcon, {
      localVue,
      propsData: { name: 'search', size: 18 }
    })
    const svg = wrapper.find('svg')
    expect(svg.exists()).toBe(true)
    expect(svg.attributes('viewbox') ?? svg.attributes('viewBox')).toBe('0 0 24 24')
    expect(svg.attributes('stroke')).toBe('currentColor')
    wrapper.destroy()
  })

  it('size 应透传到 svg 的 width / height', () => {
    const wrapper = mount(LucideIcon, {
      localVue,
      propsData: { name: 'plus', size: 20 }
    })
    const svg = wrapper.find('svg')
    expect(svg.attributes('width')).toBe('20')
    expect(svg.attributes('height')).toBe('20')
    wrapper.destroy()
  })

  it('strokeWidth 应透传到 svg 的 stroke-width（默认 2）', () => {
    const wrapper = mount(LucideIcon, {
      localVue,
      propsData: { name: 'x', strokeWidth: 1.5 }
    })
    expect(wrapper.find('svg').attributes('stroke-width')).toBe('1.5')
    wrapper.destroy()
  })

  it('默认 strokeWidth 应为 2', () => {
    const wrapper = mount(LucideIcon, {
      localVue,
      propsData: { name: 'x' }
    })
    expect(wrapper.find('svg').attributes('stroke-width')).toBe('2')
    wrapper.destroy()
  })

  it('未知图标应回退为占位 span（不渲染 svg，不抛错）', () => {
    const wrapper = mount(LucideIcon, {
      localVue,
      propsData: { name: 'does-not-exist' }
    })
    expect(wrapper.find('svg').exists()).toBe(false)
    expect(wrapper.find('.lucide-icon--missing').exists()).toBe(true)
    wrapper.destroy()
  })

  it('已知图标应渲染至少一个子元素（path/circle/...）', () => {
    const wrapper = mount(LucideIcon, {
      localVue,
      propsData: { name: 'search' }
    })
    // Search 图标含 circle + path 子元素
    const children = wrapper.findAll('svg > *')
    expect(children.length).toBeGreaterThan(0)
    wrapper.destroy()
  })

  it.each(['arrow-up-down', 'arrow-up', 'arrow-down'])(
    '排序图标 %s 应注册并渲染 SVG',
    (name) => {
      const wrapper = mount(LucideIcon, {
        localVue,
        propsData: { name, size: 13 }
      })
      expect(wrapper.find('svg').exists()).toBe(true)
      expect(wrapper.find('.lucide-icon--missing').exists()).toBe(false)
      wrapper.destroy()
    }
  )

  // ============================================================
  // 回归：emoji→Lucide 改造新注册的图标必须全部可渲染
  // 背景：status-config / AdvancedMultiSelect / FilterGroup / index.vue /
  // TraditionalView 直接用 <LucideIcon :name="..."> 消费这些图标名。
  // 任一漏注册或拼错会静默渲染 .lucide-icon--missing 空占位（图标列空白），
  // 故在此钉死「name → 渲染真实 svg」的契约。
  // ============================================================
  it.each([
    // 状态图标（STATUS_ICON_MAP）
    'trending-up',
    'trending-down',
    'pause',
    'clock',
    'alert-triangle',
    'refresh-cw',
    'help-circle',
    // 行操作 & 按钮 & 标题图标
    'play',
    'folder-open',
    'settings',
    'bar-chart-3',
    // 分页 / 关闭
    'chevron-left',
    'chevron-right',
    'x',
    // 传统视图过滤器（traditionalStatusFilter / FilterGroup）
    'inbox',
    'activity',
    'server',
    'folder',
    'tag',
    'tags',
    'circle'
  ])('改造新注册的图标 %s 应注册并渲染真实 SVG（非 missing 占位）', (name) => {
    const wrapper = mount(LucideIcon, {
      localVue,
      propsData: { name, size: 14 }
    })
    expect(wrapper.find('svg').exists()).toBe(true)
    expect(wrapper.find('.lucide-icon--missing').exists()).toBe(false)
    wrapper.destroy()
  })
})
