import { createLocalVue, shallowMount } from '@vue/test-utils'
import Vue from 'vue'
import ElementUI from 'element-ui'
import fs from 'fs'
import path from 'path'
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
  inputType: string
  currentFieldOptions: FieldOption[]
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

  // status/category/downloader_name 都与 tags 共用 multiSelect 分支。
  it.each([
    ['status', categoryOptions],
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

  // 四个字段共用同一段 multiSelect 模板，统一守住值回写链路。
  it.each([
    ['status', 'in', categoryOptions, 'movie'],
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

  it('状态 multiSelect 在空 fieldOptions 时不崩溃且禁止创建自定义状态', () => {
    const multiWrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'status',
        operator: 'in',
        value: [],
        fieldOptions: []
      },
      stubs: { 'advanced-multi-select': AdvancedMultiSelect }
    })
    const multi = multiWrapper.findComponent(AdvancedMultiSelect)
    expect(multi.props('options')).toEqual([])
    expect(multi.props('allowCreate')).toBe(false)
    multiWrapper.destroy()
  })

  it('handleChange 触发后向父级 emit input 与 change 事件', () => {
    const wrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'status',
        operator: 'in',
        value: ['downloading'],
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
    expect(inputEvents?.[0][0]).toEqual(['downloading'])

    wrapper.destroy()
  })

  it('状态字段把带图标选项完整透传给 AdvancedMultiSelect', () => {
    const iconOptions = [
      { label: '做种中', value: 'seeding', icon: 'trending-up' },
      { label: '错误', value: 'error', icon: 'alert-triangle' },
      { label: '无图标', value: 'none' }
    ]
    const wrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'status',
        operator: 'in',
        value: [],
        fieldOptions: iconOptions
      },
      stubs: { 'advanced-multi-select': AdvancedMultiSelect }
    })

    const multi = wrapper.findComponent(AdvancedMultiSelect)
    expect(multi.props('options')).toEqual(iconOptions)
    expect(multi.props('allowCreate')).toBe(false)

    wrapper.destroy()
  })

  it('未设置操作符隐藏值输入并显示无需填写提示', () => {
    const wrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'ratio_limit',
        operator: 'is_null',
        value: null
      }
    })
    const vm = wrapper.vm as unknown as ConditionValueInputVm

    expect(vm.inputType).toBe('none')
    expect(wrapper.find('.condition-value-input__empty').text()).toBe('无需填写')
    expect(wrapper.find('el-input-stub').exists()).toBe(false)

    wrapper.destroy()
  })

  it('超级做种渲染是、否、不支持三态单选', () => {
    const wrapper = shallowMount(ConditionValueInput, {
      localVue,
      propsData: {
        field: 'super_seeding',
        operator: 'equals',
        value: 'unsupported'
      },
      stubs: {
        'el-select': true,
        'el-option': true
      }
    })
    const vm = wrapper.vm as unknown as ConditionValueInputVm

    expect(vm.inputType).toBe('select')
    expect(vm.currentFieldOptions).toEqual([
      { label: '是', value: '1' },
      { label: '否', value: '0' },
      { label: '不支持', value: 'unsupported' }
    ])

    wrapper.destroy()
  })
})

/**
 * 移动端数字输入防裁切源码契约（2026-08-28 UX 改造回归）。
 *
 * 构建器断点内把条件行字号 12→14px 后，100px 定宽的数字框末位
 * （如 "0.00"）被步进按钮裁切——移动端媒体查询将两类数字输入加宽至 130px。
 * 纯 CSS 行为 jsdom 无法断言，锁源码字符串（范式同 field-types-consistency.spec.ts）。
 */
describe('移动端数字输入防裁切（源码契约）', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../ConditionValueInput.vue'), 'utf8')
  const mediaIndex = source.indexOf('@media (max-width: 768px)')
  const baseBlock = source.slice(0, mediaIndex)
  const mediaBlock = source.slice(mediaIndex)

  it('断点内范围/单值两类数字输入一并加宽至 130px（逗号选择器缺一即红）', () => {
    expect(mediaIndex).toBeGreaterThan(0)
    expect(mediaBlock).toMatch(
      /\.size-range-input \.size-input-wrapper \.size-number-input,\s*\.size-with-unit-input \.size-number-input\s*\{[^}]*width:\s*130px\s*;/
    )
  })

  it('桌面基准宽度不变：范围 100px、单值 120px', () => {
    expect(baseBlock).toMatch(/\.size-number-input\s*\{[^}]*width:\s*100px\s*;/)
    expect(baseBlock).toMatch(/\.size-number-input\s*\{[^}]*width:\s*120px\s*;/)
  })
})
