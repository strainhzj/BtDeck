import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import i18n from '@/i18n'
import FormAutocomplete from '../FormAutocomplete.vue'
import LucideIcon from '../LucideIcon.vue'
import type { FormAutocompleteSuggestion } from '../formControls'

/**
 * FormAutocomplete 单测
 *
 * 覆盖：
 * - 输入透传：input 事件 emit 原文并展开浮层
 * - 建议渲染：聚焦展开；无建议时浮层保持隐藏
 * - 选择：点击建议 emit input(value)+select；Enter 选择高亮项
 * - 键盘：↓ 移动高亮、Esc 关闭
 * - invalid/mono 修饰类
 */
const localVue = createLocalVue()
localVue.component('LucideIcon', LucideIcon)

const SUGGESTIONS: FormAutocompleteSuggestion[] = [
  { value: '/data/movies' },
  { value: '/data/tv' },
  { value: '/downloads' }
]

const mountAutocomplete = (propsData: Record<string, unknown>): Wrapper<Vue> =>
  mount(FormAutocomplete, {
    localVue,
    i18n,
    propsData: { suggestions: SUGGESTIONS, ...propsData },
    attachTo: document.body
  })

const q = (selector: string): HTMLElement | null =>
  document.querySelector(selector) as HTMLElement | null

const isDropdownVisible = (): boolean => {
  const dropdown = q('.form-autocomplete__dropdown')
  return Boolean(dropdown && dropdown.style.display !== 'none')
}

describe('FormAutocomplete 全自定义自动补全输入', () => {
  let wrapper: Wrapper<Vue>

  afterEach(() => {
    wrapper?.destroy()
  })

  it('输入透传：input 事件发出原文并展开浮层', async() => {
    wrapper = mountAutocomplete({ value: '' })
    const input = wrapper.find('input.form-autocomplete__input')
    ;(input.element as HTMLInputElement).value = '/data'
    await input.trigger('input')
    expect(wrapper.emitted('input')).toEqual([['/data']])
    await Vue.nextTick()
    expect(isDropdownVisible()).toBe(true)
  })

  it('聚焦展开建议；无建议时浮层隐藏', async() => {
    wrapper = mountAutocomplete({ value: '/data' })
    await wrapper.find('input.form-autocomplete__input').trigger('focus')
    await Vue.nextTick()
    expect(isDropdownVisible()).toBe(true)
    expect(document.querySelectorAll('.form-autocomplete__suggestion')).toHaveLength(3)

    wrapper.destroy()
    wrapper = mountAutocomplete({ value: '', suggestions: [] })
    await wrapper.find('input.form-autocomplete__input').trigger('focus')
    await Vue.nextTick()
    expect(isDropdownVisible()).toBe(false)
  })

  it('点击建议：emit input(建议值) 与 select(建议项)，随后收起', async() => {
    wrapper = mountAutocomplete({ value: '' })
    await wrapper.find('input.form-autocomplete__input').trigger('focus')
    await Vue.nextTick()

    ;(document.querySelectorAll('.form-autocomplete__suggestion')[1] as HTMLElement).click()
    await Vue.nextTick()
    expect(wrapper.emitted('input')).toEqual([['/data/tv']])
    expect(wrapper.emitted('select')).toEqual([[SUGGESTIONS[1]]])
    expect(isDropdownVisible()).toBe(false)
  })

  it('键盘：初始无高亮，↓ 进入首项并逐项下移、Enter 选中高亮项、Esc 收起', async() => {
    wrapper = mountAutocomplete({ value: '' })
    const input = wrapper.find('input.form-autocomplete__input')
    await input.trigger('focus')
    await Vue.nextTick()
    let items = document.querySelectorAll('.form-autocomplete__suggestion')
    // 初始无高亮（对齐 el-autocomplete）
    expect(items[0].className).not.toContain('is-highlighted')

    input.trigger('keydown', { key: 'ArrowDown' })
    await Vue.nextTick()
    items = document.querySelectorAll('.form-autocomplete__suggestion')
    expect(items[0].className).toContain('is-highlighted')

    input.trigger('keydown', { key: 'ArrowDown' })
    await Vue.nextTick()
    expect(document.querySelectorAll('.form-autocomplete__suggestion')[1].className)
      .toContain('is-highlighted')

    input.trigger('keydown', { key: 'Enter' })
    await Vue.nextTick()
    expect(wrapper.emitted('input')).toEqual([['/data/tv']])
    expect(wrapper.emitted('select')).toEqual([[SUGGESTIONS[1]]])
    expect(isDropdownVisible()).toBe(false)

    // Esc：重新点击输入框展开后收起（选中后输入框已持焦点，focus 事件不再触发，靠 click 重开）
    await input.trigger('click')
    await Vue.nextTick()
    expect(isDropdownVisible()).toBe(true)
    input.trigger('keydown', { key: 'Escape' })
    await Vue.nextTick()
    expect(isDropdownVisible()).toBe(false)
  })

  it('invalid/mono 修饰类透传', () => {
    wrapper = mountAutocomplete({ value: '', invalid: true, mono: true })
    expect(wrapper.find('.form-autocomplete.is-invalid').exists()).toBe(true)
    expect(wrapper.find('.form-autocomplete.is-mono').exists()).toBe(true)
  })

  it('默认建议行渲染 value 文本（未提供作用域插槽时）', async() => {
    wrapper = mountAutocomplete({ value: '' })
    await wrapper.find('input.form-autocomplete__input').trigger('focus')
    await Vue.nextTick()
    expect(
      document.querySelectorAll('.form-autocomplete__suggestion-text')[0].textContent
    ).toBe('/data/movies')
  })
})
