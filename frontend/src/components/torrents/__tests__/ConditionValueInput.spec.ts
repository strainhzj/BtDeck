import { createLocalVue, mount, shallowMount } from '@vue/test-utils'
import Vue from 'vue'
import ElementUI from 'element-ui'
import ConditionValueInput from '../ConditionValueInput.vue'
import AdvancedMultiSelect from '../AdvancedMultiSelect.vue'

/**
 * ConditionValueInput 回归测试
 *
 * 背景：该组件是 AdvancedSearchBuilder 把 fieldOptions 透传到 UI 的最后一环，
 * 改造前是 options 注入链上的最大盲点（仅在 AdvancedSearchBuilder.spec.ts 里被 stub 掉，
 * 自身零单测）。本 spec 守住「select / multiSelect 分支正确消费 fieldOptions prop」的契约。
 */

interface FieldOption {
  label: string
  value: string
}

interface ConditionValueInputVm extends Vue {
  handleInput(): void
  handleChange(): void
  inputValue: any
}

const localVue = createLocalVue()
localVue.use(ElementUI)

const categoryOptions: FieldOption[] = [
  { label: '电影', value: 'movie' },
  { label: '音乐', value: 'music' }
]

const tagOptions: FieldOption[] = [
  { label: 'tag1', value: 'tag1' },
  { label: 'tag2', value: 'tag2' }
]

describe('ConditionValueInput 字段选项透传', () => {
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

  // category/downloader_name 现在也是 multiSelect（与 tags 同分支），
  // 用 it.each 参数化覆盖三个字段，避免重复用例
  it.each([
    ['category', categoryOptions],
    ['downloader_name', categoryOptions],
    ['tags', tagOptions]
  ] as const)('multiSelect 分支：field=%s 把 fieldOptions 透传给 AdvancedMultiSelect', (field, options) => {
    const wrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field,
        operator: field === 'tags' ? 'contains_any' : 'in',
        value: [],
        fieldOptions: options
      },
      stubs: {
        // 浅渲染下用 stub 占位，但 props 仍会传递，可断言透传
        'advanced-multi-select': AdvancedMultiSelect
      }
    })

    const multi = wrapper.findComponent(AdvancedMultiSelect)
    expect(multi.exists()).toBe(true)
    expect(multi.props('options')).toEqual(options)

    wrapper.destroy()
  })

  it('空 fieldOptions 时 select 与 multiSelect 分支均不崩溃', () => {
    // select 空选项（用 status 字段——它仍是 select 类型）
    const selectWrapper = mount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'status',
        operator: 'equals',
        value: null,
        fieldOptions: []
      },
      stubs: { 'advanced-multi-select': true }
    })
    expect(selectWrapper.findAll({ name: 'ElOption' }).length).toBe(0)
    selectWrapper.destroy()

    // multiSelect 空选项（category 现在是 multiSelect）
    const multiWrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'category',
        operator: 'in',
        value: [],
        fieldOptions: []
      },
      stubs: { 'advanced-multi-select': AdvancedMultiSelect }
    })
    expect(multiWrapper.findComponent(AdvancedMultiSelect).props('options')).toEqual([])
    multiWrapper.destroy()
  })

  it('handleChange 触发后向父级 emit input 与 change 事件', () => {
    const wrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'status',
        operator: 'equals',
        value: 'downloading',
        fieldOptions: categoryOptions
      },
      stubs: {
        'el-select': true,
        'el-option': true,
        'advanced-multi-select': true
      }
    })
    const vm = wrapper.vm as unknown as ConditionValueInputVm

    vm.handleChange()

    const inputEvents = wrapper.emitted('input')
    const changeEvents = wrapper.emitted('change')
    expect(inputEvents).toHaveLength(1)
    expect(changeEvents).toHaveLength(1)
    // emit 的载荷应等于当前 inputValue（来自 value='downloading' 经 normalize 后）
    expect(inputEvents?.[0][0]).toBe('downloading')

    wrapper.destroy()
  })
})
