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

  it('select 分支：field=category 时用 mount 渲染出与 fieldOptions 数量一致的 el-option', () => {
    const wrapper = mount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'category',
        operator: 'equals',
        value: null,
        fieldOptions: categoryOptions
      },
      // stub 掉 multiSelect 子树，避免不走该分支时被深渲染
      stubs: {
        'advanced-multi-select': true
      }
    })

    // 模板里 select 分支：v-for="option in fieldOptions" 直接渲染 el-option
    // 用 findAll({ name: 'ElOption' }) 数组件实例（不受下拉是否展开影响）
    const optionComponents = wrapper.findAll({ name: 'ElOption' })
    expect(optionComponents.length).toBe(categoryOptions.length)
    // 第一个 option 的 label/value 与 fieldOptions 对齐
    expect(optionComponents.at(0).props('label')).toBe('电影')
    expect(optionComponents.at(0).props('value')).toBe('movie')

    wrapper.destroy()
  })

  it('multiSelect 分支：field=tags 时把 fieldOptions 透传给 AdvancedMultiSelect 的 options prop', () => {
    const wrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'tags',
        operator: 'contains_any',
        value: [],
        fieldOptions: tagOptions
      },
      stubs: {
        // 浅渲染下用 stub 占位，但 props 仍会传递，可断言透传
        'advanced-multi-select': AdvancedMultiSelect
      }
    })

    // 直接断言子组件收到的 options prop 与传入一致（不依赖渲染产物）
    const multi = wrapper.findComponent(AdvancedMultiSelect)
    expect(multi.exists()).toBe(true)
    expect(multi.props('options')).toEqual(tagOptions)

    wrapper.destroy()
  })

  it('空 fieldOptions 时 select 与 multiSelect 分支均不崩溃', () => {
    // select 空选项
    const selectWrapper = mount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'category',
        operator: 'equals',
        value: null,
        fieldOptions: []
      },
      stubs: { 'advanced-multi-select': true }
    })
    expect(selectWrapper.findAll({ name: 'ElOption' }).length).toBe(0)
    selectWrapper.destroy()

    // multiSelect 空选项
    const multiWrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'tags',
        operator: 'contains_any',
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
        field: 'category',
        operator: 'equals',
        value: 'movie',
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
    // emit 的载荷应等于当前 inputValue（来自 value='movie' 经 normalize 后）
    expect(inputEvents?.[0][0]).toBe('movie')

    wrapper.destroy()
  })
})
