import { shallowMount, mount, createLocalVue } from '@vue/test-utils'
import ElementUI from 'element-ui'
import AdvancedMultiSelect from '../AdvancedMultiSelect.vue'

// 创建本地Vue实例
const localVue = createLocalVue()
localVue.use(ElementUI)

// 选项接口
interface SelectOption {
  value: string | number
  label: string
  count?: number
  type?: string
  category?: string
  [key: string]: any
}

describe('AdvancedMultiSelect组件', () => {
  let wrapper: any

  // 测试数据
  const mockOptions: SelectOption[] = [
    { value: 1, label: '选项1', count: 10 },
    { value: 2, label: '选项2', count: 5 },
    { value: 3, label: '选项3', type: 'custom' },
    { value: 4, label: 'Test Option', category: 'test' },
    { value: 'alpha', label: 'Alpha' },
    { value: 'beta', label: 'Beta' },
    { value: 'gamma', label: 'Gamma' }
  ]

  beforeEach(() => {
    wrapper = shallowMount(AdvancedMultiSelect, {
      localVue,
      propsData: {
        options: mockOptions,
        value: []
      },
      stubs: {
        'virtual-scroll-list': true,
        'el-input': true,
        'el-select': true,
        'el-checkbox': true,
        'el-button': true,
        'el-tabs': true,
        'el-tab-pane': true,
        'el-radio-group': true,
        'el-radio-button': true,
        'el-tag': true,
        'el-collapse': true,
        'el-collapse-item': true,
        'el-switch': true,
        'el-input-number': true
      }
    })
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.destroy()
    }
  })

  describe('基础功能测试', () => {
    it('应该正确渲染组件', () => {
      expect(wrapper.exists()).toBe(true)
      expect(wrapper.find('.advanced-multi-select').exists()).toBe(true)
    })

    it('应该正确显示搜索框', () => {
      const searchInput = wrapper.find('el-input-stub')
      expect(searchInput.exists()).toBe(true)
      expect(searchInput.attributes('placeholder')).toBe('搜索选项...')
    })

    it('小数据量应该使用普通列表', () => {
      expect(wrapper.vm.useVirtualScroll).toBe(false)
      expect(wrapper.find('.normal-list').exists()).toBe(true)
      expect(wrapper.find('virtual-scroll-list-stub').exists()).toBe(false)
    })
  })

  describe('选项选择功能测试', () => {
    it('应该能正确选择单个选项', async() => {
      const option = mockOptions[0]
      wrapper.vm.toggleOption(option)

      expect(wrapper.vm.selectedItems).toHaveLength(1)
      expect(wrapper.vm.selectedItems[0]).toEqual(option)
      expect(wrapper.vm.isSelected(option)).toBe(true)
    })

    it('应该能正确取消选择选项', async() => {
      const option = mockOptions[0]

      // 先选择
      wrapper.vm.toggleOption(option)
      expect(wrapper.vm.isSelected(option)).toBe(true)

      // 再取消选择
      wrapper.vm.toggleOption(option)
      expect(wrapper.vm.isSelected(option)).toBe(false)
      expect(wrapper.vm.selectedItems).toHaveLength(0)
    })

    it('应该能选择多个选项', async() => {
      const option1 = mockOptions[0]
      const option2 = mockOptions[1]

      wrapper.vm.toggleOption(option1)
      wrapper.vm.toggleOption(option2)

      expect(wrapper.vm.selectedItems).toHaveLength(2)
      expect(wrapper.vm.isSelected(option1)).toBe(true)
      expect(wrapper.vm.isSelected(option2)).toBe(true)
    })
  })

  describe('搜索过滤功能测试', () => {
    it('应该能根据关键词过滤选项', async() => {
      wrapper.setData({ searchKeyword: '选项' })
      await wrapper.vm.$nextTick()

      const filteredOptions = wrapper.vm.filteredOptions
      expect(filteredOptions).toHaveLength(3) // 选项1、选项2 和选项3
      expect(filteredOptions.every((opt: SelectOption) =>
        opt.label.includes('选项')
      )).toBe(true)
    })

    it('应该能根据英文字母过滤选项', async() => {
      wrapper.setData({ searchKeyword: 'Test' })
      await wrapper.vm.$nextTick()

      const filteredOptions = wrapper.vm.filteredOptions
      expect(filteredOptions).toHaveLength(1)
      expect(filteredOptions[0].label).toBe('Test Option')
    })

    it('搜索功能应该不区分大小写且不重复同一选项', async() => {
      wrapper.setData({ searchKeyword: 'test' })
      await wrapper.vm.$nextTick()

      const filteredOptions = wrapper.vm.filteredOptions
      // 同一选项的 label 与 category 都命中时仍只返回一次
      expect(filteredOptions).toHaveLength(1)
      expect(filteredOptions[0].label).toBe('Test Option')
    })
  })

  describe('多选模式功能测试', () => {
    it('应该能在包含模式和排除模式之间切换', async() => {
      expect(wrapper.vm.selectedMode).toBe('include')

      wrapper.setData({ selectedMode: 'exclude' })
      expect(wrapper.vm.selectedMode).toBe('exclude')
    })

    it('包含模式应该正确选中选项', async() => {
      wrapper.setData({ selectedMode: 'include' })
      const option = mockOptions[0]
      wrapper.vm.toggleOption(option)

      expect(wrapper.vm.isSelected(option)).toBe(true)
    })
  })

  describe('输入框模式功能测试', () => {
    it('应该能正确解析逗号分隔的输入', () => {
      const testInput = '选项1,选项2,选项3'
      const result = wrapper.vm.parseInputBySeparators(testInput)

      expect(result).toEqual(['选项1', '选项2', '选项3'])
    })

    it('应该能正确解析分号分隔的输入', () => {
      const testInput = 'alpha;beta;gamma'
      const result = wrapper.vm.parseInputBySeparators(testInput)

      expect(result).toEqual(['alpha', 'beta', 'gamma'])
    })

    it('应该能正确解析空格分隔的输入', () => {
      const testInput = 'one two three'
      const result = wrapper.vm.parseInputBySeparators(testInput)

      expect(result).toEqual(['one', 'two', 'three'])
    })

    it('应该能正确处理混合分隔符', () => {
      const testInput = '选项1, 选项2;选项3 选项4'
      const result = wrapper.vm.parseInputBySeparators(testInput)

      expect(result).toEqual(['选项1', '选项2', '选项3', '选项4'])
    })

    it('应该能正确处理空输入', () => {
      const result1 = wrapper.vm.parseInputBySeparators('')
      const result2 = wrapper.vm.parseInputBySeparators('   ')
      const result3 = wrapper.vm.parseInputBySeparators(null as any)

      expect(result1).toEqual([])
      expect(result2).toEqual([])
      expect(result3).toEqual([])
    })

    it('应该能正确去除重复项', () => {
      const testInput = '选项1,选项2,选项1,选项3,选项2'
      const result = wrapper.vm.parseInputBySeparators(testInput)

      expect(result).toEqual(['选项1', '选项2', '选项3'])
    })
  })

  describe('快速操作功能测试', () => {
    it('应该能选择所有可见选项', async() => {
      wrapper.setData({ searchKeyword: '选项' })
      await wrapper.vm.$nextTick()

      wrapper.vm.selectAllVisible()

      const filteredOptions = wrapper.vm.filteredOptions
      expect(wrapper.vm.selectedItems).toHaveLength(filteredOptions.length)
    })

    it('应该能取消选择所有可见选项', async() => {
      // 先选择一些选项
      wrapper.setData({ searchKeyword: '选项' })
      await wrapper.vm.$nextTick()
      wrapper.vm.selectAllVisible()

      expect(wrapper.vm.selectedItems.length).toBeGreaterThan(0)

      // 再取消选择
      wrapper.vm.deselectAllVisible()
      expect(wrapper.vm.selectedItems).toHaveLength(0)
    })

    it('应该能选择所有选项', () => {
      wrapper.vm.selectAll()
      expect(wrapper.vm.selectedItems).toHaveLength(mockOptions.length)
    })

    it('应该能清空所有选择', () => {
      wrapper.vm.selectAll()
      expect(wrapper.vm.selectedItems).toHaveLength(mockOptions.length)

      wrapper.vm.deselectAll()
      expect(wrapper.vm.selectedItems).toHaveLength(0)
    })
  })

  describe('键盘导航功能测试', () => {
    it('应该能正确初始化高亮索引', () => {
      expect(wrapper.vm.highlightedIndex).toBe(-1)
    })

    it('应该能正确检查键盘高亮状态', () => {
      wrapper.setData({ highlightedIndex: 1 })
      expect(wrapper.vm.isKeyboardHighlighted(1)).toBe(true)
      expect(wrapper.vm.isKeyboardHighlighted(0)).toBe(false)
    })

    it('应该能处理鼠标进入事件', () => {
      wrapper.vm.handleMouseEnter(2)
      expect(wrapper.vm.highlightedIndex).toBe(2)
    })
  })

  describe('性能优化测试', () => {
    it('应该能正确设置虚拟滚动状态', async() => {
      // 小于阈值的数据量
      wrapper.setProps({ options: mockOptions.slice(0, 5) })
      await wrapper.vm.$nextTick()
      expect(wrapper.vm.useVirtualScroll).toBe(false)

      // 大于阈值的数据量
      const largeOptions = Array.from({ length: 15000 }, (_, i) => ({
        value: i,
        label: `选项${i}`,
        count: Math.floor(Math.random() * 100)
      }))

      wrapper.setProps({ options: largeOptions })
      await wrapper.vm.$nextTick()
      expect(wrapper.vm.useVirtualScroll).toBe(true)
    })

    it('应该能正确缓存搜索结果', async() => {
      wrapper.setData({ searchKeyword: '选项' })
      await wrapper.vm.$nextTick()

      const firstCall = wrapper.vm.filteredOptions
      const secondCall = wrapper.vm.filteredOptions

      expect(firstCall).toBe(secondCall) // 应该是同一个引用，说明使用了缓存
    })
  })

  describe('组件生命周期测试', () => {
    it('应该正确初始化选中项', async() => {
      wrapper.setProps({ value: [1, 3] })
      await wrapper.vm.$nextTick()

      expect(wrapper.vm.selectedItems).toHaveLength(2)
      expect(wrapper.vm.selectedItems[0].value).toBe(1)
      expect(wrapper.vm.selectedItems[1].value).toBe(3)
    })

    it('应该正确清理定时器', () => {
      const clearTimeoutSpy = jest.spyOn(window, 'clearTimeout')

      wrapper.vm.searchDebounceTimer = 123
      wrapper.destroy()

      expect(clearTimeoutSpy).toHaveBeenCalledWith(123)
      clearTimeoutSpy.mockRestore()
    })
  })

  describe('事件发射测试', () => {
    it('应该在值改变时发射input事件', async() => {
      const option = mockOptions[0]

      wrapper.vm.toggleOption(option)

      // 检查是否发射了input事件
      const emitted = wrapper.emitted().input
      expect(emitted).toBeTruthy()
      expect(emitted[0][0]).toEqual([option.value])
    })

    it('应该在值改变时发射change事件', async() => {
      const option = mockOptions[0]

      wrapper.vm.toggleOption(option)

      const emitted = wrapper.emitted().change
      expect(emitted).toBeTruthy()
      expect(emitted[0][0]).toEqual({
        values: [option.value],
        mode: wrapper.vm.selectedMode,
        count: 1
      })
    })
  })

  describe('重塑后 UI 行为测试', () => {
    it('默认应渲染紧凑触发器而不是把选择面板撑开条件行', () => {
      const trigger = wrapper.find('.ams__trigger')

      expect(trigger.exists()).toBe(true)
      expect(trigger.attributes('aria-haspopup')).toBe('listbox')
      expect(trigger.find('.ams__trigger-label').text()).toBe('请选择')
      expect(wrapper.vm.panelVisible).toBe(false)
    })

    it('未选择时应支持由父组件定制提示语', async() => {
      await wrapper.setProps({ placeholder: '请选择下载器' })

      expect(wrapper.find('.ams__trigger-label').text()).toBe('请选择下载器')
      expect(wrapper.vm.triggerLabel).toBe('请选择下载器')
    })

    it('紧凑触发器应展示首个选项与选中数量', async() => {
      wrapper.setProps({ value: [1, 2] })
      await wrapper.vm.$nextTick()

      expect(wrapper.find('.ams__trigger-label').text()).toBe('选项1 等 2 项')
      expect(wrapper.find('.ams__trigger-count').text()).toBe('2')
    })

    it('trigger 常驻清空按钮:有值时可清空、不打开浮层、无值时不渲染', async() => {
      // 无选中项时不渲染清空按钮
      expect(wrapper.find('.ams__trigger-clear').exists()).toBe(false)

      // 选中两项
      wrapper.vm.toggleOption(mockOptions[0])
      wrapper.vm.toggleOption(mockOptions[1])
      await wrapper.vm.$nextTick()

      const clearBtn = wrapper.find('.ams__trigger-clear')
      expect(clearBtn.exists()).toBe(true)
      expect(clearBtn.attributes('aria-label')).toBe('清空已选条件值')

      // 确保浮层处于关闭态,验证 .stop 是否真能阻止 popover toggle
      wrapper.setData({ panelVisible: false })

      await clearBtn.trigger('click')

      // 清空生效
      expect(wrapper.vm.selectedItems).toHaveLength(0)
      // @click.stop 阻断了外层 el-popover 的 trigger="click",浮层未被打开
      expect(wrapper.vm.panelVisible).toBe(false)
      // 向上 emit 的载荷正确清空
      const inputEvents = wrapper.emitted('input')
      expect(inputEvents?.[inputEvents.length - 1][0]).toEqual([])
      const changeEvents = wrapper.emitted('change')
      expect(changeEvents?.[changeEvents.length - 1][0]).toMatchObject({
        values: [],
        count: 0
      })
    })

    it('清空按钮支持键盘 Enter/Space 触发并具备 a11y 属性', async() => {
      wrapper.vm.toggleOption(mockOptions[0])
      await wrapper.vm.$nextTick()

      const clearBtn = wrapper.find('.ams__trigger-clear')
      // 用 span+role 模拟 button,必须显式提供 role 与 tabindex 才能被键盘/读屏识别
      expect(clearBtn.attributes('role')).toBe('button')
      expect(clearBtn.attributes('tabindex')).toBe('0')

      // Enter 触发清空
      wrapper.setData({ panelVisible: false })
      await clearBtn.trigger('keypress', { key: 'Enter' })
      expect(wrapper.vm.selectedItems).toHaveLength(0)
      expect(wrapper.vm.panelVisible).toBe(false)

      // Space 同样触发清空
      wrapper.vm.toggleOption(mockOptions[1])
      await wrapper.vm.$nextTick()
      const clearBtnAgain = wrapper.find('.ams__trigger-clear')
      wrapper.setData({ panelVisible: false })
      await clearBtnAgain.trigger('keypress', { key: ' ' })
      expect(wrapper.vm.selectedItems).toHaveLength(0)
    })

    it('浮层已打开时点击清空:清空生效但浮层保持打开(.stop 仅阻断 toggle)', async() => {
      wrapper.vm.toggleOption(mockOptions[0])
      wrapper.vm.toggleOption(mockOptions[2])
      await wrapper.vm.$nextTick()

      const clearBtn = wrapper.find('.ams__trigger-clear')
      // 模拟浮层已经打开的状态(用户先点开了 trigger,再点 trigger 上的 ✕)
      wrapper.setData({ panelVisible: true })

      await clearBtn.trigger('click')

      // 清空生效
      expect(wrapper.vm.selectedItems).toHaveLength(0)
      // .stop 阻断的是 popover 的 doToggle(切换),而非强制关闭:
      // 浮层保持打开,符合"清空后继续在浮层里选择"的语义
      expect(wrapper.vm.panelVisible).toBe(true)
    })

    it('已选区应前置渲染（在选项列表之前）', () => {
      // 已选区与选项列表都应存在；且已选区在 DOM 序中先于选项列表
      const selected = wrapper.find('.ams__selected')
      const options = wrapper.find('.ams__options')
      expect(selected.exists()).toBe(true)
      expect(options.exists()).toBe(true)
      const html = wrapper.html()
      const selectedPos = html.indexOf('ams__selected')
      const optionsPos = html.indexOf('ams__options')
      expect(selectedPos).toBeGreaterThanOrEqual(0)
      expect(optionsPos).toBeGreaterThanOrEqual(0)
      expect(selectedPos).toBeLessThan(optionsPos)
    })

    it('含/排除胶囊切换应改变 selectedMode 并发射 selected-mode-change', async() => {
      expect(wrapper.vm.selectedMode).toBe('include')

      wrapper.vm.setSelectedMode('exclude')
      await wrapper.vm.$nextTick()

      expect(wrapper.vm.selectedMode).toBe('exclude')
      const emitted = wrapper.emitted('selected-mode-change')
      expect(emitted).toBeTruthy()
      expect(emitted[0][0]).toBe('exclude')
    })

    it('排除模式 chip 应使用排除态样式', async() => {
      wrapper.setData({ selectedMode: 'exclude' })
      wrapper.vm.toggleOption(mockOptions[0])
      await wrapper.vm.$nextTick()

      const chip = wrapper.find('.ams__chip')
      expect(chip.exists()).toBe(true)
      expect(chip.classes()).toContain('is-exclude')
    })
  })

  // ============================================================
  // 回归：emoji→Lucide 改造——选项/已选 chip 装饰图标契约
  // 背景：本次改造给 SelectOption 加了可选 icon 字段，并在 option-label / chip-label
  // 前渲染 <LucideIcon>。关键不变量：icon 仅作装饰，
  //   ① 不应污染搜索匹配（optionExists 仍走纯文本 label）；
  //   ② 不应污染 triggerLabel 拼接（"X 等 N 项"）；
  //   ③ 有 icon 时 chip/option 内出现 LucideIcon 真实 svg，无 icon 时不出现。
  // 任一被破坏都会导致下拉项图标丢失或搜索/选中行为错乱。
  // ============================================================
  describe('选项装饰图标（icon 字段）', () => {
    const iconOptions: SelectOption[] = [
      { value: 'a', label: '做种中', icon: 'trending-up' },
      { value: 'b', label: '下载中', icon: 'trending-down' },
      { value: 'c', label: '无图标项' }
    ]

    const buildWrapper = (props: Record<string, unknown> = {}) =>
      mount(AdvancedMultiSelect, {
        localVue,
        propsData: { options: iconOptions, value: [], ...props },
        stubs: {
          'virtual-scroll-list': true,
          'el-popover': true,
          'el-input': true,
          'el-tooltip': true
        }
      })

    it('getOptionIcon 应返回 option.icon；无该字段时返回 undefined', () => {
      const w = buildWrapper()
      const vm = w.vm as any
      expect(vm.getOptionIcon(iconOptions[0])).toBe('trending-up')
      expect(vm.getOptionIcon(iconOptions[2])).toBeUndefined()
      w.destroy()
    })

    it('带 icon 的普通列表选项应渲染 LucideIcon 真实 svg（非 missing 占位）', () => {
      const w = buildWrapper()
      const labels = w.findAll('.ams__option-label')
      // 小数据量走普通列表，iconOptions 3 项全部渲染
      expect(labels.length).toBeGreaterThanOrEqual(2)
      // 前两项有 icon → 各含一个真实 svg
      const firstSvg = labels.at(0).find('svg')
      expect(firstSvg.exists()).toBe(true)
      expect(labels.at(0).find('.lucide-icon--missing').exists()).toBe(false)
      // 第三项无 icon → 不渲染 svg
      const allLabels = w.findAll('.ams__option-label')
      let noIconSvgFound = false
      for (let i = 0; i < allLabels.length; i++) {
        if (allLabels.at(i).text().includes('无图标项') && allLabels.at(i).find('svg').exists()) {
          noIconSvgFound = true
        }
      }
      expect(noIconSvgFound).toBe(false)
      w.destroy()
    })

    it('选中带 icon 的选项后，chip 内应渲染 LucideIcon svg', async() => {
      const w = buildWrapper()
      const vm = w.vm as any
      vm.toggleOption(iconOptions[0])
      await w.vm.$nextTick()

      const chip = w.find('.ams__chip')
      expect(chip.exists()).toBe(true)
      expect(chip.find('svg').exists()).toBe(true)
      expect(chip.text()).toContain('做种中')
      w.destroy()
    })

    it('triggerLabel 拼接仍走纯文本 label，不被 icon 干扰（"X 等 N 项"）', async() => {
      const w = buildWrapper()
      const vm = w.vm as any
      vm.toggleOption(iconOptions[0])
      vm.toggleOption(iconOptions[1])
      await w.vm.$nextTick()
      // triggerLabel 形如 "做种中 等 2 项"，不含图标名
      const trigger = vm.triggerLabel as string
      expect(trigger).toBe('做种中 等 2 项')
      expect(trigger).not.toContain('trending')
      w.destroy()
    })

    it('搜索匹配仍走纯文本 label（optionExists 不因 icon 失效）', () => {
      const w = buildWrapper()
      const vm = w.vm as any
      // label 命中
      expect(vm.optionExists('做种中')).toBe(true)
      // 图标名不是 label，不应被误判为已存在
      expect(vm.optionExists('trending-up')).toBe(false)
      w.destroy()
    })
  })
})
