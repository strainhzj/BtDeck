/**
 * EChart 封装生命周期与 import 竞态测试（statistics-reports W4）。
 *
 * - mock echarts 四模块（core/charts/components/renderers），钉住 use 注册面
 *   与 init 调用；
 * - stub ResizeObserver（jsdom 无实现）；
 * - 组件持有模块级 echarts 加载 promise 缓存 → 逐例 jest.resetModules() 后
 *   重新 require 组件保证隔离；mock 句柄经 globalThis 跨模块重置存活
 *   （jest.mock 工厂禁止引用外层变量，globalThis 在允许清单内）；
 * - 覆盖：mounted 后 init + 首个 option 应用；option 引用变化经浅比较重
 *   setOption（notMerge）；import 未就绪前 set option 的竞态（import 完成
 *   后立即应用）；beforeDestroy dispose + disconnect；空态插槽；loading 面。
 */

interface Mocks {
  setOption: jest.Mock
  resize: jest.Mock
  dispose: jest.Mock
  showLoading: jest.Mock
  hideLoading: jest.Mock
  init: jest.Mock
  use: jest.Mock
}

jest.mock('echarts/core', () => {
  const g = globalThis as unknown as { __echartsMocks?: Mocks }
  if (!g.__echartsMocks) {
    const setOption = jest.fn()
    const resize = jest.fn()
    const dispose = jest.fn()
    const showLoading = jest.fn()
    const hideLoading = jest.fn()
    const init = jest.fn(() => ({ setOption, resize, dispose, showLoading, hideLoading }))
    const use = jest.fn()
    g.__echartsMocks = { setOption, resize, dispose, showLoading, hideLoading, init, use }
  }
  return { __esModule: true, init: g.__echartsMocks.init, use: g.__echartsMocks.use, __mocks: g.__echartsMocks }
})
jest.mock('echarts/charts', () => ({
  __esModule: true,
  BarChart: { name: 'BarChart' },
  LineChart: { name: 'LineChart' },
  PieChart: { name: 'PieChart' },
  ScatterChart: { name: 'ScatterChart' }
}))
jest.mock('echarts/components', () => ({
  __esModule: true,
  GridComponent: { name: 'GridComponent' },
  TooltipComponent: { name: 'TooltipComponent' },
  LegendComponent: { name: 'LegendComponent' },
  DataZoomComponent: { name: 'DataZoomComponent' },
  TitleComponent: { name: 'TitleComponent' }
}))
jest.mock('echarts/renderers', () => ({ __esModule: true, CanvasRenderer: { name: 'CanvasRenderer' } }))

import { mount, createLocalVue, Wrapper } from '@vue/test-utils'
import Vue from 'vue'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const echartsMocks = () => (globalThis as any).__echartsMocks as Mocks

const localVue = createLocalVue()

class ResizeObserverStub {
  observe(): void {
    /* spy 替身 */
  }

  unobserve(): void {
    /* spy 替身 */
  }

  disconnect(): void {
    /* spy 替身 */
  }
}

const flushPromises = () => new Promise((resolve) => setTimeout(resolve, 0))

/** 逐例重置模块后重新取组件类（组件模块级 echarts 缓存随重置归零） */
function freshEChart(): typeof Vue {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const mod = require('../EChart.vue')
  return mod.default
}

function mountChart(propsData: Record<string, unknown>, slots?: Record<string, string>): Wrapper<Vue> {
  const EChart = freshEChart()
  return mount(EChart, { localVue, propsData, slots })
}

const makeOption = (data: number[] = [1, 2]): Record<string, unknown> => ({
  series: [{ type: 'bar', data }],
  xAxis: { type: 'category' }
})

describe('EChart 组件（echarts 按需懒加载封装）', () => {
  beforeEach(() => {
    jest.resetModules()
    // 触发 mock 工厂执行，确保 globalThis 句柄存在（resetModules 不清除 globalThis）
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    require('echarts/core')
    const m = echartsMocks()
    m.setOption.mockClear()
    m.resize.mockClear()
    m.dispose.mockClear()
    m.showLoading.mockClear()
    m.hideLoading.mockClear()
    m.init.mockClear()
    m.use.mockClear()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(global as any).ResizeObserver = ResizeObserverStub
  })

  it('mounted 后动态 import 完成即 init 并应用首个 option', async() => {
    const m = echartsMocks()
    const wrapper = mountChart({ option: makeOption(), height: 240 })
    await flushPromises()
    expect(m.init).toHaveBeenCalledTimes(1)
    expect(m.use).toHaveBeenCalledTimes(1)
    // 注册面：4 图表 + 5 组件 + 1 渲染器
    const registered = m.use.mock.calls[0][0] as Array<{ name: string }>
    expect(registered.map((x) => x.name).sort()).toEqual(
      [
        'BarChart',
        'CanvasRenderer',
        'DataZoomComponent',
        'GridComponent',
        'LegendComponent',
        'LineChart',
        'PieChart',
        'ScatterChart',
        'TitleComponent',
        'TooltipComponent'
      ].sort()
    )
    expect(m.setOption).toHaveBeenCalledWith(makeOption(), { notMerge: true })
    expect(wrapper.find('[data-testid="echart-empty"]').exists()).toBe(false)
    expect(wrapper.attributes('style')).toContain('height: 240px')
    wrapper.destroy()
  })

  it('import 竞态：option 在 import 完成前就绪 → init 后立即应用', async() => {
    const m = echartsMocks()
    const wrapper = mountChart({ option: null })
    // import 仍在途时传入 option（refs 已挂载、chart 未 init）
    await wrapper.setProps({ option: makeOption([9]) })
    await flushPromises()
    expect(m.setOption).toHaveBeenCalledWith(makeOption([9]), { notMerge: true })
    wrapper.destroy()
  })

  it('option 引用变化经浅比较触发 setOption；顶层值同引用的新对象不重渲染', async() => {
    const m = echartsMocks()
    const wrapper = mountChart({ option: makeOption() })
    await flushPromises()
    expect(m.setOption).toHaveBeenCalledTimes(1)
    // 新引用不同内容（新 series 数组）→ 应用
    await wrapper.setProps({ option: makeOption([7, 8, 9]) })
    expect(m.setOption).toHaveBeenCalledTimes(2)
    // 新顶层对象但 series/xAxis 同引用（浅层键值一致）→ 跳过
    const same = makeOption([7, 8, 9])
    await wrapper.setProps({ option: same })
    expect(m.setOption).toHaveBeenCalledTimes(3)
    await wrapper.setProps({ option: { ...same } })
    expect(m.setOption).toHaveBeenCalledTimes(3)
    wrapper.destroy()
  })

  it('空态：option 为空或无 series 显示占位插槽', async() => {
    const m = echartsMocks()
    const wrapper = mountChart({ option: null, emptyText: '暂无数据' }, { empty: '<span data-testid="custom-empty">自定义空态</span>' })
    await flushPromises()
    expect(m.setOption).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="custom-empty"]').exists()).toBe(true)
    // 无 series 的 option 同样空态
    await wrapper.setProps({ option: { series: [] } })
    expect(wrapper.find('[data-testid="custom-empty"]').exists()).toBe(true)
    wrapper.destroy()
  })

  it('loading 面切换 showLoading/hideLoading', async() => {
    const m = echartsMocks()
    const wrapper = mountChart({ option: makeOption(), loading: false })
    await flushPromises()
    expect(m.hideLoading).toHaveBeenCalled()
    await wrapper.setProps({ loading: true })
    expect(m.showLoading).toHaveBeenCalled()
    wrapper.destroy()
  })

  it('beforeDestroy：dispose 实例并断开 ResizeObserver', async() => {
    const m = echartsMocks()
    const observeSpy = jest.spyOn(ResizeObserverStub.prototype, 'observe')
    const disconnectSpy = jest.spyOn(ResizeObserverStub.prototype, 'disconnect')
    const wrapper = mountChart({ option: makeOption() })
    await flushPromises()
    expect(observeSpy).toHaveBeenCalled()
    wrapper.destroy()
    expect(m.dispose).toHaveBeenCalledTimes(1)
    expect(disconnectSpy).toHaveBeenCalled()
  })

  it('多实例共享单次 echarts 加载（模块级 promise 缓存）', async() => {
    const m = echartsMocks()
    const w1 = mountChart({ option: makeOption() })
    const w2 = mountChart({ option: makeOption() })
    await flushPromises()
    expect(m.use).toHaveBeenCalledTimes(1) // 模块注册仅一次
    expect(m.init).toHaveBeenCalledTimes(2) // 各自实例 init
    w1.destroy()
    w2.destroy()
  })
})
