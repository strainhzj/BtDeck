import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import Component from 'vue-class-component'
import ColumnResizeMixin from '@/views/torrents/mixins/columnResize'

/**
 * ColumnResizeMixin 契约回归（列表模式/传统模式共用）：
 * - 默认宽度打底、localStorage 已存值覆盖、损坏数据回退默认
 * - 拖拽（mousedown → mousemove → mouseup）按位移更新并夹取 [40, 600]
 * - mouseup 才写一次 localStorage；双击手柄恢复单列默认；resetColumnWidths 全部重置
 * - document 监听与 body.column-resizing 类随拖拽结束/组件销毁成对清理
 */
const STORAGE_KEY = 'btdeck_test_column_widths'

@Component({
  name: 'ColumnResizeHarness',
  template: '<div class="column-resize-harness" />'
})
class ColumnResizeHarness extends ColumnResizeMixin {
  protected columnWidthStorageKey = STORAGE_KEY
  protected defaultColumnWidths: Record<string, number> = {
    size: 100,
    status: 145
  }
}

const localVue = createLocalVue()

/** 派发 document 级鼠标事件（mixin 拖拽会话监听在 document 上） */
const dispatchMouse = (type: 'mousemove' | 'mouseup', clientX: number) => {
  document.dispatchEvent(new MouseEvent(type, { clientX, bubbles: true }))
}

const mousedownOnHandle = (wrapper: Wrapper<ColumnResizeHarness>, key: string, clientX: number) => {
  (wrapper.vm as unknown as {
    startColumnResize: (key: string, event: MouseEvent) => void
  }).startColumnResize(key, new MouseEvent('mousedown', { clientX, buttons: 1, bubbles: true }))
}

const readStorage = (): Record<string, number> =>
  JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') as Record<string, number>

describe('ColumnResizeMixin 列宽拖拽', () => {
  let wrapper: Wrapper<ColumnResizeHarness>

  beforeEach(() => {
    localStorage.clear()
    document.body.classList.remove('column-resizing')
  })

  afterEach(() => {
    if (wrapper && wrapper.exists()) {
      wrapper.destroy()
    }
    localStorage.clear()
    document.body.classList.remove('column-resizing')
  })

  it('无存储时以默认宽度初始化，未登记列键不产生宽度样式', () => {
    wrapper = mount(ColumnResizeHarness, { localVue })
    const vm = wrapper.vm as unknown as {
      columnWidths: Record<string, number>
      columnWidthStyle: (key: string) => Record<string, string>
    }
    expect(vm.columnWidths).toEqual({ size: 100, status: 145 })
    expect(vm.columnWidthStyle('size')).toEqual({ width: '100px' })
    expect(vm.columnWidthStyle('name')).toEqual({})
  })

  it('localStorage 已存值覆盖默认；损坏 JSON 静默回退默认', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ size: 260 }))
    wrapper = mount(ColumnResizeHarness, { localVue })
    let vm = wrapper.vm as unknown as { columnWidths: Record<string, number> }
    expect(vm.columnWidths).toEqual({ size: 260, status: 145 })

    wrapper.destroy()
    localStorage.setItem(STORAGE_KEY, '{not-valid-json')
    wrapper = mount(ColumnResizeHarness, { localVue })
    vm = wrapper.vm as unknown as { columnWidths: Record<string, number> }
    expect(vm.columnWidths).toEqual({ size: 100, status: 145 })
  })

  it('拖拽按位移更新宽度并夹取到 [40, 600]，mouseup 时写入一次存储', () => {
    wrapper = mount(ColumnResizeHarness, { localVue })
    const vm = wrapper.vm as unknown as { columnWidths: Record<string, number> }

    mousedownOnHandle(wrapper, 'size', 200)
    expect(document.body.classList.contains('column-resizing')).toBe(true)

    dispatchMouse('mousemove', 250)
    expect(vm.columnWidths.size).toBe(150)
    expect(readStorage()).toEqual({}) // 拖拽中不落盘

    dispatchMouse('mousemove', 2000) // 100 + 1800 → 夹取上限 600
    expect(vm.columnWidths.size).toBe(600)

    dispatchMouse('mousemove', -5000) // 100 - 5200 → 夹取下限 40
    expect(vm.columnWidths.size).toBe(40)

    dispatchMouse('mouseup', -5000)
    expect(readStorage()).toEqual({ size: 40, status: 145 })
    expect(document.body.classList.contains('column-resizing')).toBe(false)
  })

  it('存储中的越界值加载时同样夹取', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ size: 9999, status: 5 }))
    wrapper = mount(ColumnResizeHarness, { localVue })
    const vm = wrapper.vm as unknown as { columnWidths: Record<string, number> }
    expect(vm.columnWidths.size).toBe(600)
    expect(vm.columnWidths.status).toBe(40)
  })

  it('双击手柄恢复单列默认并持久化', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ size: 300, status: 300 }))
    wrapper = mount(ColumnResizeHarness, { localVue })
    const vm = wrapper.vm as unknown as {
      columnWidths: Record<string, number>
      handleColumnResizeDblclick: (key: string) => void
    }
    vm.handleColumnResizeDblclick('size')
    expect(vm.columnWidths).toEqual({ size: 100, status: 300 })
    expect(readStorage()).toEqual({ size: 100, status: 300 })
  })

  it('resetColumnWidths 全部恢复默认', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ size: 500, status: 500 }))
    wrapper = mount(ColumnResizeHarness, { localVue })
    const vm = wrapper.vm as unknown as {
      columnWidths: Record<string, number>
      resetColumnWidths: () => void
    }
    vm.resetColumnWidths()
    expect(vm.columnWidths).toEqual({ size: 100, status: 145 })
    expect(readStorage()).toEqual({ size: 100, status: 145 })
  })

  it('组件销毁时清理 document 监听与 body 拖拽态类', () => {
    wrapper = mount(ColumnResizeHarness, { localVue })
    const removeSpy = jest.spyOn(document, 'removeEventListener')

    mousedownOnHandle(wrapper, 'size', 100)
    wrapper.destroy()

    const removedTypes = removeSpy.mock.calls.map(call => call[0])
    expect(removedTypes).toContain('mousemove')
    expect(removedTypes).toContain('mouseup')
    expect(document.body.classList.contains('column-resizing')).toBe(false)
    removeSpy.mockRestore()
  })

  it('sumColumnWidths 汇总当前列宽（表级 min-width 计算输入）', () => {
    wrapper = mount(ColumnResizeHarness, { localVue })
    const vm = wrapper.vm as unknown as { sumColumnWidths: (keys: string[]) => number }
    expect(vm.sumColumnWidths(['size', 'status'])).toBe(245)
    expect(vm.sumColumnWidths(['size', 'unknown-key'])).toBe(100)
  })
})
