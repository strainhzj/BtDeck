import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import i18n from '@/i18n'
import FormCheckbox from '../FormCheckbox.vue'
import LucideIcon from '../LucideIcon.vue'

/**
 * FormCheckbox 单测
 *
 * 覆盖：
 * - v-model 契约：change 时 emit input/change（true/false 翻转）
 * - 视觉态：.is-checked 类与 value 同步；disabled 忽略交互
 * - 插槽 label 文本渲染；原生 input 承载键盘/读屏语义（视觉隐藏仍在 DOM）
 */
const localVue = createLocalVue()
localVue.component('LucideIcon', LucideIcon)

describe('FormCheckbox 全自定义复选框', () => {
  const mountCheckbox = (propsData: Record<string, unknown> = {}): Wrapper<Vue> =>
    mount(FormCheckbox, {
      localVue,
      i18n,
      propsData,
      slots: { default: '跳过校验' }
    })

  it('默认未选中；value=true 渲染 is-checked 类', () => {
    const wrapper = mountCheckbox({ value: false })
    expect(wrapper.find('label.is-checked').exists()).toBe(false)
    wrapper.destroy()

    const checked = mountCheckbox({ value: true })
    expect(checked.find('label.is-checked').exists()).toBe(true)
    checked.destroy()
  })

  it('切换原生 input 触发 input(true) 与 change(true)；再切回 false', async() => {
    const wrapper = mountCheckbox({ value: false })
    const input = wrapper.find('input[type="checkbox"]')
    // jsdom 不会因派发 change 而翻转 checked，需手动置位（真实浏览器由点击翻转）
    ;(input.element as HTMLInputElement).checked = true
    await input.trigger('change')
    expect(wrapper.emitted('input')).toEqual([[true]])
    expect(wrapper.emitted('change')).toEqual([[true]])
    wrapper.destroy()

    const checked = mountCheckbox({ value: true })
    const checkedInput = checked.find('input[type="checkbox"]')
    ;(checkedInput.element as HTMLInputElement).checked = false
    await checkedInput.trigger('change')
    expect(checked.emitted('input')).toEqual([[false]])
    checked.destroy()
  })

  it('disabled：不 emit', async() => {
    const wrapper = mountCheckbox({ value: false, disabled: true })
    await wrapper.find('input[type="checkbox"]').trigger('change')
    expect(wrapper.emitted('input')).toBeUndefined()
    expect(wrapper.find('label.is-disabled').exists()).toBe(true)
    wrapper.destroy()
  })

  it('插槽 label 渲染 + 原生 input 保留（视觉隐藏承载键盘/读屏）', () => {
    const wrapper = mountCheckbox({ value: false })
    expect(wrapper.find('.form-checkbox__label').text()).toBe('跳过校验')
    const input = wrapper.find('input[type="checkbox"]')
    expect(input.exists()).toBe(true)
    expect(input.classes()).toContain('form-checkbox__input')
    wrapper.destroy()
  })
})
