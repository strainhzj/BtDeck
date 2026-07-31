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
  icon?: string
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

  // tags / category / downloader_name 三个字段共用同一段 multiSelect 模板，
  // 同一个回写 bug 也同时影响它们，故参数化覆盖三者。
  it.each([
    ['tags', 'contains_any', tagOptions, 'tag1'],
    ['category', 'in', categoryOptions, 'movie'],
    ['downloader_name', 'in', categoryOptions, 'movie']
  ] as const)(
    'multiSelect 选择后 inputValue 被正确回写并向上 emit（field=%s）',
    async(field, operator, options, pickValue) => {
      // 回归保护：原先 multiSelect 分支用 :value + @input 绑定，而 handleInput()
      // 丢弃子组件 emit 的 input 载荷，直接 emitChange() 把旧的空数组往上抛，
      // 导致下一 tick watcher 把 selectedItems 重置为空（点击无反应、不报错）。
      // 改用 v-model 后，子组件 input 载荷会自动回写 inputValue，链条修复。
      const wrapper = shallowMount(ConditionValueInput, {
        localVue,
        propsData: {
          field,
          operator,
          value: [],
          fieldOptions: options
        },
        stubs: {
          'advanced-multi-select': AdvancedMultiSelect
        }
      })
      const vm = wrapper.vm as unknown as ConditionValueInputVm
      const multi = wrapper.findComponent(AdvancedMultiSelect)

      // 模拟真实点击：AdvancedMultiSelect 选中某项后 emitValue 会先 emit('input', values)
      // 再 emit('change', {...})。v-model 借 input 载荷回写 inputValue，change 触发向上 emit。
      multi.vm.$emit('input', [pickValue])
      multi.vm.$emit('change', { values: [pickValue], mode: 'include', count: 1 })
      await wrapper.vm.$nextTick()

      // inputValue 应被回写为新值（而非被旧空数组覆盖重置）——这是 bug 的核心回归点
      expect(vm.inputValue).toEqual([pickValue])
      // 向父级 emit 的最后一个 input / change 事件载荷应携带选中的值
      const inputEvents = wrapper.emitted('input')
      const changeEvents = wrapper.emitted('change')
      expect(inputEvents?.[inputEvents.length - 1][0]).toEqual([pickValue])
      expect(changeEvents?.[changeEvents.length - 1][0]).toEqual([pickValue])

      wrapper.destroy()
    }
  )

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

  // ============================================================
  // 回归：emoji→Lucide 改造——select 分支 el-option 内渲染图标
  // 背景：本次改造给 FieldOption 加了可选 icon，并在 el-option 默认 slot 内放
  // <LucideIcon v-if="option.icon">。:label 仍是纯文本（el-select 触发器/过滤用）。
  // 不变量：带 icon 的 option 下拉项内出现真实 svg；无 icon 时不出现。
  // ============================================================
  it('select 分支：带 icon 的 fieldOptions 在 el-option 内渲染 LucideIcon', () => {
    const iconOptions = [
      { label: '做种中', value: 'seeding', icon: 'trending-up' },
      { label: '错误', value: 'error', icon: 'alert-triangle' },
      { label: '无图标', value: 'none' }
    ]
    const wrapper = mount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'status',
        operator: 'equals',
        value: null,
        fieldOptions: iconOptions
      },
      stubs: { 'advanced-multi-select': true }
    })

    const options = wrapper.findAll({ name: 'ElOption' })
    expect(options).toHaveLength(3)
    // 前两项 el-option 内应渲染真实 LucideIcon svg（el-option 用默认 slot）
    const svgs = wrapper.findAll('.el-select-dropdown__item svg, .ams__option-label svg, option svg, svg')
    expect(svgs.length).toBeGreaterThanOrEqual(2)
    // 不应有 missing 占位
    expect(wrapper.find('.lucide-icon--missing').exists()).toBe(false)
    // 各 option 的 :label 仍是纯文本（不被图标污染）
    expect(options.at(0).props('label')).toBe('做种中')

    wrapper.destroy()
  })
})
