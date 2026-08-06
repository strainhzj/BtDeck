import { createLocalVue, mount } from '@vue/test-utils'
import ElementUI from 'element-ui'
import BatchButton from '../index.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'

/**
 * BatchButton 回归测试
 *
 * 背景：批量操作工具栏图标从 el-icon 迁移 lucide，BatchButton 新增 lucide-icon /
 * lucide-size props（提供时用 LucideIcon 渲染，否则回退 el-icon）。
 * 本 spec 守住「lucide 渲染 / 向后兼容 el-icon / disabled 抑制点击」契约，
 * 防止后续批量工具栏图标迁移出现回归。
 */

const localVue = createLocalVue()
localVue.use(ElementUI)

describe('BatchButton', () => {
  let logSpy: jest.SpyInstance
  let warnSpy: jest.SpyInstance
  let errorSpy: jest.SpyInstance

  beforeEach(() => {
    // Element UI 在 jsdom 下会输出一些无害的尺寸/动画告警，静音以保持输出干净
    logSpy = jest.spyOn(console, 'log').mockImplementation(() => undefined)
    warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    logSpy.mockRestore()
    warnSpy.mockRestore()
    errorSpy.mockRestore()
  })

  it('提供 lucide-icon 时渲染 LucideIcon（name 透传，不渲染 el-icon）', () => {
    const wrapper = mount(BatchButton, {
      localVue,
      propsData: { lucideIcon: 'play', tooltip: '开始' }
    })
    const icon = wrapper.findComponent(LucideIcon)
    expect(icon.exists()).toBe(true)
    expect(icon.props('name')).toBe('play')
    expect(wrapper.find('i.el-icon-play').exists()).toBe(false)
  })

  it('lucide-icon 在圆形按钮下也渲染（不受 slot 隐藏影响）', () => {
    const wrapper = mount(BatchButton, {
      localVue,
      propsData: { lucideIcon: 'trash', tooltip: '删除', circle: true }
    })
    expect(wrapper.findComponent(LucideIcon).exists()).toBe(true)
  })

  it('lucide-size 可配置图标尺寸', () => {
    const wrapper = mount(BatchButton, {
      localVue,
      propsData: { lucideIcon: 'settings', lucideSize: 20, tooltip: '设置' }
    })
    const icon = wrapper.findComponent(LucideIcon)
    expect(icon.props('size')).toBe(20)
  })

  it('未提供 lucide-icon 时向后兼容 el-icon', () => {
    const wrapper = mount(BatchButton, {
      localVue,
      propsData: { icon: 'el-icon-delete', tooltip: '删除' }
    })
    expect(wrapper.findComponent(LucideIcon).exists()).toBe(false)
    expect(wrapper.find('i.el-icon-delete').exists()).toBe(true)
  })

  it('disabled 时不触发 click 事件', async() => {
    const wrapper = mount(BatchButton, {
      localVue,
      propsData: { icon: 'el-icon-delete', tooltip: '删除', disabled: true }
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('click')).toBeUndefined()
  })

  it('点击触发 click 事件', async() => {
    const wrapper = mount(BatchButton, {
      localVue,
      propsData: { icon: 'el-icon-delete', tooltip: '删除' }
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })
})
