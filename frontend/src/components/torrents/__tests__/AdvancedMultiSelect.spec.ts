import { shallowMount, createLocalVue } from '@vue/test-utils'
import Vue from 'vue'
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

    it('应该正确显示虚拟滚动列表', () => {
      expect(wrapper.find('virtual-scroll-list-stub').exists()).toBe(true)
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
      expect(filteredOptions).toHaveLength(2) // 选项1 和 选项2
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

    it('搜索功能应该区分大小写', async() => {
      wrapper.setData({ searchKeyword: 'test' })
      await wrapper.vm.$nextTick()

      const filteredOptions = wrapper.vm.filteredOptions
      expect(filteredOptions).toHaveLength(2) // 'test' 在 'Test Option' 和 'test' category中
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
})