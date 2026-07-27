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
})
