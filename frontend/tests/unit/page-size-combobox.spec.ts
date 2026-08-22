import Vue from 'vue'
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'

import PageSizeCombobox from '@/components/torrents/PageSizeCombobox.vue'

const localVue = createLocalVue()

interface PageSizeComboboxProps {
  value?: string
  pageSize?: number
  expanded?: boolean
  options?: number[]
  controlsId?: string
}

interface PageSizeComboboxVm extends Vue {
  focusInput(): void
}

function mountCombobox(
  propsData: PageSizeComboboxProps = {},
  attachTo?: HTMLElement
): Wrapper<Vue> {
  return mount(PageSizeCombobox, {
    localVue,
    attachTo,
    propsData: {
      value: '20',
      pageSize: 20,
      ...propsData
    }
  })
}

describe('PageSizeCombobox regressions', () => {
  let wrapper: Wrapper<Vue> | undefined
  let host: HTMLElement | undefined

  afterEach(() => {
    wrapper?.destroy()
    host?.remove()
    wrapper = undefined
    host = undefined
  })

  it('keeps the shared presets and collapsed combobox accessibility contract', () => {
    wrapper = mountCombobox({ controlsId: 'page-size-regression-options' })

    const combobox = wrapper.find('.page-size-combobox')
    const input = wrapper.find('.page-size-input')
    const toggle = wrapper.find('.page-size-toggle')
    const options = wrapper.find('.page-size-options')

    expect(combobox.attributes()).toEqual(expect.objectContaining({
      role: 'combobox',
      'aria-haspopup': 'listbox',
      'aria-controls': 'page-size-regression-options',
      'aria-expanded': 'false'
    }))
    expect(input.attributes()).toEqual(expect.objectContaining({
      type: 'text',
      inputmode: 'numeric',
      'aria-label': '每页数量'
    }))
    expect(toggle.classes()).toContain('el-icon-arrow-up')
    expect(toggle.attributes('aria-label')).toBe('展开分页大小选项')
    expect(options.attributes('id')).toBe('page-size-regression-options')
    expect((options.element as HTMLElement).style.display).toBe('none')
    expect(wrapper.findAll('.page-size-options button').wrappers.map(option => option.text()))
      .toEqual(['20', '50', '100', '500', '1000'])
  })

  it('emits controlled input, focus, blur, apply, toggle and preset selection events', async() => {
    host = document.createElement('div')
    document.body.appendChild(host)
    wrapper = mountCombobox({}, host)
    const input = wrapper.find('.page-size-input')

    await input.setValue('500')
    await input.trigger('focus')
    await wrapper.setProps({ value: '500' })
    await input.trigger('keyup', { key: 'Enter', keyCode: 13 })
    await input.trigger('blur')
    await wrapper.find('.page-size-toggle').trigger('click')
    await wrapper.findAll('.page-size-options button').at(4).trigger('click')

    expect(wrapper.emitted().input).toEqual([['500']])
    expect(wrapper.emitted().focus).toEqual([[]])
    expect(wrapper.emitted().apply).toEqual([['500']])
    expect(wrapper.emitted().blur).toEqual([[]])
    expect(wrapper.emitted().toggle).toEqual([[]])
    expect(wrapper.emitted().select).toEqual([[{ value: '1000' }]])
  })

  it('reflects expanded and selected state through classes and ARIA', () => {
    wrapper = mountCombobox({
      value: '500',
      pageSize: 500,
      expanded: true,
      controlsId: 'expanded-page-size-options'
    })

    const combobox = wrapper.find('.page-size-combobox')
    const toggle = wrapper.find('.page-size-toggle')
    const options = wrapper.find('.page-size-options')
    const selectedOption = wrapper.find('.page-size-options button[aria-selected="true"]')

    expect(combobox.attributes('aria-expanded')).toBe('true')
    expect(toggle.classes()).toContain('el-icon-arrow-down')
    expect(toggle.attributes()).toEqual(expect.objectContaining({
      'aria-label': '收起分页大小选项',
      'aria-expanded': 'true'
    }))
    expect((options.element as HTMLElement).style.display).not.toBe('none')
    expect(selectedOption.text()).toBe('500')
  })

  it('focusInput moves keyboard focus to the numeric input', () => {
    host = document.createElement('div')
    document.body.appendChild(host)
    wrapper = mountCombobox({}, host)

    const vm = wrapper.vm as PageSizeComboboxVm
    const input = wrapper.find('.page-size-input')
    vm.focusInput()

    expect(document.activeElement).toBe(input.element)
  })
})

describe('PageSizeCombobox append-to-body teleport', () => {
  // 守护本次修复：appendToBody=true 时展开把下拉 teleport 到 document.body
  // （position:fixed 绕开父级 overflow 裁剪），关闭时还原到原父级。
  // 关键回归点：prop 必须声明 type:Boolean，否则裸属性 append-to-body 传入空字符串
  // （falsy）导致 teleport 不生效——这正是线上"下拉被遮挡"的根因。
  let wrapper: Wrapper<Vue> | undefined

  afterEach(() => {
    wrapper?.destroy()
    wrapper = undefined
  })

  it('append-to-body=true 展开时把下拉挪到 document.body 并加 floating class', async() => {
    wrapper = mount(PageSizeCombobox, {
      localVue,
      attachTo: document.body,
      propsData: {
        value: '20',
        pageSize: 20,
        appendToBody: true,
        controlsId: 'teleport-options'
      }
    })
    const optionsEl = wrapper.find('.page-size-options').element as HTMLElement

    // 初始：下拉仍在组件根内
    expect(optionsEl.parentElement).toBe(wrapper.find('.page-size-combobox').element)

    // 展开 → teleport 到 body
    await wrapper.setProps({ expanded: true })
    await wrapper.vm.$nextTick()
    expect(optionsEl.parentElement).toBe(document.body)
    expect(optionsEl.classList.contains('page-size-options--floating')).toBe(true)

    // 关闭 → 还原到原父级，清除 floating 态
    await wrapper.setProps({ expanded: false })
    await wrapper.vm.$nextTick()
    expect(optionsEl.parentElement).toBe(wrapper.find('.page-size-combobox').element)
    expect(optionsEl.classList.contains('page-size-options--floating')).toBe(false)
  })

  it('append-to-body=false（默认）展开时下拉留在原父级，不 teleport', async() => {
    wrapper = mount(PageSizeCombobox, {
      localVue,
      attachTo: document.body,
      propsData: {
        value: '20',
        pageSize: 20,
        // appendToBody 默认 false
        controlsId: 'no-teleport-options'
      }
    })
    const optionsEl = wrapper.find('.page-size-options').element as HTMLElement
    const comboboxEl = wrapper.find('.page-size-combobox').element

    await wrapper.setProps({ expanded: true })
    await wrapper.vm.$nextTick()

    // 默认不下拉到 body（保持旧行为，回归守护）
    expect(optionsEl.parentElement).toBe(comboboxEl)
    expect(optionsEl.parentElement).not.toBe(document.body)
    expect(optionsEl.classList.contains('page-size-options--floating')).toBe(false)
  })
})
