import { shallowMount, createLocalVue } from '@vue/test-utils'
import Vue from 'vue'
import ElementUI from 'element-ui'
import AdvancedMultiSelect from '../AdvancedMultiSelect.vue'

// 创建本地Vue实例
const localVue = createLocalVue()
localVue.use(ElementUI)

describe('AdvancedMultiSelect性能测试', () => {
  let wrapper: any

  // 生成大量测试数据
  const generateLargeOptions = (count: number) => {
    return Array.from({ length: count }, (_, i) => ({
      value: `option_${i}`,
      label: `选项 ${i} - ${Math.random().toString(36).substring(2, 8)}`,
      count: Math.floor(Math.random() * 1000),
      type: Math.random() > 0.5 ? 'standard' : 'custom',
      category: ['work', 'personal', 'study', 'entertainment'][Math.floor(Math.random() * 4)]
    }))
  }

  beforeEach(() => {
    // 设置性能测试的超时时间
    jest.setTimeout(30000)
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.destroy()
    }
  })

  describe('大数据量渲染性能测试', () => {
    it('应该能在1000ms内渲染10,000个选项', async() => {
      const largeOptions = generateLargeOptions(10000)
      const startTime = performance.now()

      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: largeOptions,
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

      await wrapper.vm.$nextTick()

      const renderTime = performance.now() - startTime

      console.log(`渲染10,000个选项耗时: ${renderTime.toFixed(2)}ms`)

      expect(renderTime).toBeLessThan(1000)
      expect(wrapper.vm.options).toHaveLength(10000)
      expect(wrapper.vm.useVirtualScroll).toBe(true)
    })

    it('应该能在2000ms内渲染50,000个选项', async() => {
      const largeOptions = generateLargeOptions(50000)
      const startTime = performance.now()

      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: largeOptions,
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

      await wrapper.vm.$nextTick()

      const renderTime = performance.now() - startTime

      console.log(`渲染50,000个选项耗时: ${renderTime.toFixed(2)}ms`)

      expect(renderTime).toBeLessThan(2000)
      expect(wrapper.vm.options).toHaveLength(50000)
      expect(wrapper.vm.useVirtualScroll).toBe(true)
    })
  })

  describe('搜索性能测试', () => {
    it('应该能在100ms内完成10,000个选项的搜索', async() => {
      const largeOptions = generateLargeOptions(10000)

      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: largeOptions,
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

      await wrapper.vm.$nextTick()

      // 测试搜索性能
      const searchKeywords = ['选项', 'option', 'work', '选项 1', 'Option 123']

      for (const keyword of searchKeywords) {
        const startTime = performance.now()

        wrapper.setData({ searchKeyword: keyword })
        await wrapper.vm.$nextTick()

        const searchTime = performance.now() - startTime
        const filteredCount = wrapper.vm.filteredOptions.length

        console.log(`搜索关键词"${keyword}"耗时: ${searchTime.toFixed(2)}ms，结果数量: ${filteredCount}`)

        expect(searchTime).toBeLessThan(100)
      }
    })

    it('搜索结果缓存应该提高重复搜索的性能', async() => {
      const largeOptions = generateLargeOptions(10000)

      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: largeOptions,
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

      await wrapper.vm.$nextTick()

      const keyword = '选项'
      const searchTimes: number[] = []

      // 执行多次搜索，测量缓存效果
      for (let i = 0; i < 5; i++) {
        const startTime = performance.now()

        wrapper.setData({ searchKeyword: keyword })
        await wrapper.vm.$nextTick()

        const searchTime = performance.now() - startTime
        searchTimes.push(searchTime)
      }

      console.log(`搜索性能测试结果: ${searchTimes.map(t => t.toFixed(2)).join('ms, ')}`)

      // 第一次搜索应该比后续搜索慢（缓存效果）
      expect(searchTimes[0]).toBeGreaterThanOrEqual(searchTimes[1])
      expect(searchTimes[1]).toBeLessThan(50) // 缓存的搜索应该很快
    })
  })

  describe('多选操作性能测试', () => {
    it('应该能在200ms内选择1,000个选项', async() => {
      const largeOptions = generateLargeOptions(10000)

      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: largeOptions,
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

      await wrapper.vm.$nextTick()

      const startTime = performance.now()

      // 选择前1000个选项
      for (let i = 0; i < 1000; i++) {
        wrapper.vm.toggleOption(largeOptions[i])
      }

      const selectionTime = performance.now() - startTime

      console.log(`选择1,000个选项耗时: ${selectionTime.toFixed(2)}ms`)

      expect(selectionTime).toBeLessThan(200)
      expect(wrapper.vm.selectedItems).toHaveLength(1000)
    })

    it('应该能在500ms内取消选择1,000个选项', async() => {
      const largeOptions = generateLargeOptions(10000)

      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: largeOptions,
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

      await wrapper.vm.$nextTick()

      // 先选择一些选项
      wrapper.vm.selectAllVisible()

      const startTime = performance.now()

      // 清空所有选择
      wrapper.vm.deselectAll()

      const deselectionTime = performance.now() - startTime

      console.log(`清空选择耗时: ${deselectionTime.toFixed(2)}ms`)

      expect(deselectionTime).toBeLessThan(500)
      expect(wrapper.vm.selectedItems).toHaveLength(0)
    })
  })

  describe('内存使用测试', () => {
    it('应该正确清理定时器避免内存泄漏', async() => {
      const clearTimeoutSpy = jest.spyOn(window, 'clearTimeout')

      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: generateLargeOptions(10000),
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

      await wrapper.vm.$nextTick()

      // 设置一些定时器
      wrapper.vm.searchDebounceTimer = 123
      wrapper.vm.highlightedIndex = 5

      // 销毁组件
      wrapper.destroy()

      expect(clearTimeoutSpy).toHaveBeenCalledWith(123)
      clearTimeoutSpy.mockRestore()
    })

    it('应该正确清理缓存数据', async() => {
      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: generateLargeOptions(10000),
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

      await wrapper.vm.$nextTick()

      // 设置一些缓存数据
      wrapper.setData({
        filteredOptionsCache: generateLargeOptions(100),
        lastSearchKeyword: 'test',
        highlightedIndex: 10
      })

      // 销毁组件
      wrapper.destroy()

      // 验证数据是否被清理
      expect(wrapper.vm.filteredOptionsCache).toEqual([])
      expect(wrapper.vm.lastSearchKeyword).toBe('')
    })
  })

  describe('输入解析性能测试', () => {
    it('应该能在50ms内解析包含10,000个值的输入文本', () => {
      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: generateLargeOptions(10000),
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

      // 生成包含大量分隔符的输入文本
      const largeInput = Array.from({ length: 10000 }, (_, i) => `value${i}`).join(',')

      const startTime = performance.now()

      const result = wrapper.vm.parseInputBySeparators(largeInput)

      const parseTime = performance.now() - startTime

      console.log(`解析10,000个值耗时: ${parseTime.toFixed(2)}ms`)

      expect(parseTime).toBeLessThan(50)
      expect(result).toHaveLength(10000)
      expect(result[0]).toBe('value0')
      expect(result[9999]).toBe('value9999')
    })

    it('应该能正确处理复杂的分隔符组合', () => {
      wrapper = shallowMount(AdvancedMultiSelect, {
        localVue,
        propsData: {
          options: [],
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

      const complexInput = 'value1,value2;value3 value4\nvalue5\tvalue6|value7~value8'
      const expected = ['value1', 'value2', 'value3', 'value4', 'value5', 'value6', 'value7', 'value8']

      const result = wrapper.vm.parseInputBySeparators(complexInput)

      expect(result).toEqual(expected)
    })
  })
})