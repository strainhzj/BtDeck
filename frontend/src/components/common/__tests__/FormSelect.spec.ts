import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import i18n from '@/i18n'
import FormSelect from '../FormSelect.vue'
import LucideIcon from '../LucideIcon.vue'
import type { FormSelectOption } from '../formControls'

/**
 * FormSelect 单测
 *
 * 覆盖：
 * - 单选：展开/选择（input+change）/自动关闭；占位与回显（含选项未加载时回退原始值）
 * - 多选：chips 渲染/增删（浮层保持展开）、removeChip
 * - clearable：清空（单选 ''/多选 []）+ clear 事件
 * - filterable：query 过滤 + Enter 选择高亮项
 * - 键盘：触发器 ↓ 展开、浮层内 ↑↓ 高亮移动、Esc 关闭
 * - 点击外部收起；invalid 类透传
 *
 * 注意：展开后下拉节点被 teleport 到 document.body（FloatingDropdown mixin），
 * 相关断言需经 document 查询而非 wrapper 查询。
 */
const localVue = createLocalVue()
localVue.component('LucideIcon', LucideIcon)

const OPTIONS: FormSelectOption[] = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta', badge: 'qB', status: 'online' },
  { value: 'c', label: 'Gamma' }
]

const mountSelect = (propsData: Record<string, unknown>): Wrapper<Vue> =>
  mount(FormSelect, { localVue, i18n, propsData, attachTo: document.body })

/** v-model 宿主：事件回写后验证回显/渲染（无宿主时 prop 不回写，事件断言用 mountSelect） */
const mountSelectWithVModel = (
  propsData: Record<string, unknown>
): { host: Wrapper<Vue>, select: Wrapper<Vue> } => {
  const flags = [
    propsData.multiple ? 'multiple' : '',
    propsData.clearable ? 'clearable' : '',
    propsData.filterable ? 'filterable' : ''
  ].filter(Boolean).join(' ')
  const host = mount({
    components: { FormSelect },
    data() {
      return {
        sel: propsData.value,
        options: propsData.options,
        placeholder: (propsData.placeholder as string) || 'pick'
      }
    },
    template: `<FormSelect ref="sel" v-model="sel" :options="options" :placeholder="placeholder" ${flags} />`
  }, {
    localVue,
    i18n,
    attachTo: document.body
  })
  return { host, select: host.findComponent({ ref: 'sel' } as never) }
}

const q = (selector: string): HTMLElement | null =>
  document.querySelector(selector) as HTMLElement | null

const qAll = (selector: string): NodeListOf<HTMLElement> =>
  document.querySelectorAll(selector)

const openDropdown = async(wrapper: Wrapper<Vue>): Promise<void> => {
  await wrapper.find('.form-select__trigger').trigger('click')
  await Vue.nextTick()
}

/** 浮层展开判定：v-show 驱动，关闭态 display:none（teleport 前后均成立） */
const isDropdownVisible = (): boolean => {
  const dropdown = q('.form-select__dropdown')
  return Boolean(dropdown && dropdown.style.display !== 'none')
}

describe('FormSelect 全自定义下拉', () => {
  let wrapper: Wrapper<Vue>

  afterEach(() => {
    wrapper?.destroy()
  })

  it('单选：展开渲染选项，点击选择后 emit input/change 并自动关闭', async() => {
    const { host, select } = mountSelectWithVModel({ value: '', options: OPTIONS })
    wrapper = host
    expect(select.find('.form-select__value.is-placeholder').text()).toBe('pick')

    await select.find('.form-select__trigger').trigger('click')
    await Vue.nextTick()
    expect(isDropdownVisible()).toBe(true)
    expect(qAll('.form-select__option')).toHaveLength(3)

    qAll('.form-select__option')[1].click()
    await Vue.nextTick()
    expect(select.emitted('input')).toEqual([['b']])
    expect(select.emitted('change')).toHaveLength(1)
    expect(select.emitted('change')?.[0]?.[0]).toMatchObject({ value: 'b', label: 'Beta' })
    expect(isDropdownVisible()).toBe(false)
    // v-model 回写后回显选中项 label
    expect(select.find('.form-select__value').text()).toBe('Beta')
  })

  it('回显：选项未加载时显示原始值，不显示成空', () => {
    wrapper = mountSelect({ value: 'raw-id', options: [], placeholder: 'pick' })
    expect(wrapper.find('.form-select__value').text()).toBe('raw-id')
    wrapper.destroy()

    wrapper = mountSelect({ value: 'a', options: OPTIONS })
    expect(wrapper.find('.form-select__value').text()).toBe('Alpha')
  })

  it('多选：chips 渲染、点击选项追加/移除且浮层保持展开、chip 单独移除', async() => {
    const { host, select } = mountSelectWithVModel({ value: ['a', 'c'], options: OPTIONS, multiple: true })
    wrapper = host
    expect(select.findAll('.form-select__chip')).toHaveLength(2)
    expect(select.find('.form-select__placeholder').exists()).toBe(false)

    await select.find('.form-select__trigger').trigger('click')
    await Vue.nextTick()
    // 追加 b
    qAll('.form-select__option')[1].click()
    await Vue.nextTick()
    expect(select.emitted('input')?.[0]).toEqual([['a', 'c', 'b']])
    expect(isDropdownVisible()).toBe(true)
    // v-model 回写后再点 b：移除
    qAll('.form-select__option')[1].click()
    await Vue.nextTick()
    expect(select.emitted('input')?.[1]).toEqual([['a', 'c']])
    expect(select.findAll('.form-select__chip')).toHaveLength(2)

    // chip 上的 x 移除 a
    await select.find('.form-select__chip-remove').trigger('click')
    expect(select.emitted('input')?.[2]).toEqual([['c']])
    await Vue.nextTick()
    expect(select.findAll('.form-select__chip')).toHaveLength(1)
  })

  it('clearable：单选清空为空串、多选清空为数组，并发出 clear', async() => {
    wrapper = mountSelect({ value: 'a', options: OPTIONS, clearable: true })
    await wrapper.find('.form-select__clear').trigger('click')
    expect(wrapper.emitted('input')).toEqual([['']])
    expect(wrapper.emitted('clear')).toHaveLength(1)
    wrapper.destroy()

    wrapper = mountSelect({ value: ['a'], options: OPTIONS, clearable: true, multiple: true })
    await wrapper.find('.form-select__clear').trigger('click')
    expect(wrapper.emitted('input')).toEqual([[[]]])
    wrapper.destroy()
  })

  it('filterable：query 过滤选项，Enter 选中高亮项', async() => {
    wrapper = mountSelect({
      value: '',
      options: OPTIONS,
      filterable: true,
      placeholder: 'pick'
    })
    await openDropdown(wrapper)
    // 过滤框自动聚焦
    const filterInput = q('.form-select__filter-input') as HTMLInputElement
    expect(filterInput).not.toBeNull()

    filterInput.value = 'gam'
    filterInput.dispatchEvent(new Event('input'))
    await Vue.nextTick()
    expect(qAll('.form-select__option')).toHaveLength(1)
    expect(qAll('.form-select__option')[0].textContent).toContain('Gamma')

    filterInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await Vue.nextTick()
    expect(wrapper.emitted('input')).toEqual([['c']])
    expect(isDropdownVisible()).toBe(false)
  })

  it('键盘：触发器 ↓ 展开并高亮首项，Esc 经触发器路径关闭（非过滤模式无过滤框）', async() => {
    wrapper = mountSelect({ value: '', options: OPTIONS })
    await wrapper.find('.form-select__trigger').trigger('keydown', { key: 'ArrowDown' })
    await Vue.nextTick()
    expect(isDropdownVisible()).toBe(true)
    // 初始高亮第一项；非过滤模式无过滤框
    expect(qAll('.form-select__option')[0].className).toContain('is-highlighted')
    expect(q('.form-select__filter-input')).toBeNull()

    await wrapper.find('.form-select__trigger').trigger('keydown', { key: 'Escape' })
    expect(isDropdownVisible()).toBe(false)
  })

  it('filterable 键盘：↑↓ 循环移动高亮', async() => {
    wrapper = mountSelect({ value: '', options: OPTIONS, filterable: true })
    await openDropdown(wrapper)
    const filterInput = q('.form-select__filter-input') as HTMLInputElement

    filterInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }))
    await Vue.nextTick()
    expect(qAll('.form-select__option')[1].className).toContain('is-highlighted')

    filterInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp' }))
    await Vue.nextTick()
    // 循环：0 → ↓ → 1 → ↑ → 0
    expect(qAll('.form-select__option')[0].className).toContain('is-highlighted')
  })

  it('点击外部收起（文档级 mousedown 捕获）', async() => {
    wrapper = mountSelect({ value: '', options: OPTIONS })
    await openDropdown(wrapper)
    expect(isDropdownVisible()).toBe(true)

    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await Vue.nextTick()
    expect(isDropdownVisible()).toBe(false)
  })

  it('invalid 类透传 + 富选项行（徽章/状态点）渲染', async() => {
    wrapper = mountSelect({ value: '', options: OPTIONS, invalid: true })
    expect(wrapper.find('.form-select.is-invalid').exists()).toBe(true)

    await openDropdown(wrapper)
    const rich = qAll('.form-select__option')[1]
    expect(rich.querySelector('.form-select__badge')?.textContent).toBe('qB')
    expect(rich.querySelector('.form-select__status-dot.is-online')).not.toBeNull()
    // 无徽章选项不渲染徽章节点
    expect(qAll('.form-select__option')[0].querySelector('.form-select__badge')).toBeNull()
  })
})
