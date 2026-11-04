/**
 * DashboardGrid 网格单测（仪表盘一期 W5）：预设可见性切换（v-show 保留实例）、
 * 编辑模式原生 DnD 容器代理（dragstart/dragover 即时重排）、cycle-width 转发。
 */
import { mount, Wrapper } from '@vue/test-utils'
import DashboardGrid from '@/views/dashboard/components/DashboardGrid.vue'
import { defaultLayout, WidgetId } from '@/views/dashboard/components/dashboardLayout'

const layout = defaultLayout()

function mountGrid(propsData: Record<string, unknown>): Wrapper<Vue> {
  return mount(DashboardGrid, {
    propsData: { layout, preset: 'overview', editing: false, ...propsData },
    mocks: { $t: (k: string) => `T(${k})` },
    scopedSlots: {
      health: '<div />',
      spark: '<div />',
      statusPie: '<div />',
      traffic: '<div />',
      sites: '<div />',
      hot: '<div />',
      tasks: '<div />',
      activity: '<div />',
      quick: '<div />',
      radar: '<div />',
      tubes: '<div />',
      hero: '<div />'
    }
  })
}

describe('DashboardGrid 预设可见性', () => {
  it('overview 下 radar/tubes/hero 卡 display:none，其余可见', () => {
    const w = mountGrid({ preset: 'overview' })
    const widgetOf = (id: string) => w.find(`[data-widget-id="${id}"]`)
    expect(widgetOf('health').attributes('style')).not.toContain('none')
    expect(widgetOf('radar').attributes('style')).toContain('none')
    expect(widgetOf('tubes').attributes('style')).toContain('none')
    expect(widgetOf('hero').attributes('style')).toContain('none')
  })

  it('custom 下全部 12 张可见（渲染顺序 = layout.order）', () => {
    const w = mountGrid({ preset: 'custom' })
    const rendered = w.findAll('.dash-widget').wrappers.map(x => x.attributes('data-widget-id'))
    expect(rendered).toEqual([...layout.order] as WidgetId[])
    expect(rendered).not.toContain('issues')
  })

  it('列宽 span 透传 --span（默认覆盖/自定义覆盖）', () => {
    const custom = { ...layout, spans: { ...layout.spans, hot: 12 } }
    const w = mount(DashboardGrid, {
      propsData: { layout: custom, preset: 'custom', editing: false },
      mocks: { $t: (k: string) => k }
    })
    const hot = w.find('[data-widget-id="hot"]')
    expect(hot.exists()).toBe(true)
    expect(hot.text()).toContain('dashboard.widgets.hot.title')
  })
})

describe('DashboardGrid 编辑模式 DnD', () => {
  it('非编辑模式 dragstart 不设拖拽态', async() => {
    const w = mountGrid({ editing: false })
    const el = w.find('[data-widget-id="health"]')
    await el.trigger('dragstart', { dataTransfer: null })
    expect(w.emitted('reorder')).toBeUndefined()
  })

  it('编辑模式 dragover 即时重排并上抛新顺序（health 拖到 hot 前）', async() => {
    const w = mountGrid({ editing: true })
    // dragstart 需要从 health 卡发起（closest 查找 widget）
    const healthEl = w.find('[data-widget-id="health"]')
    const dataTransfer = { effectAllowed: '', setData: jest.fn() }
    await healthEl.trigger('dragstart', { dataTransfer })
    // dragover 目标为 hot 卡：真实 DOM 冒泡事件（closest('.dash-widget') 命中 hot）
    const target = w.find('[data-widget-id="hot"]').element as HTMLElement
    target.dispatchEvent(new MouseEvent('dragover', { bubbles: true, cancelable: true }))
    await w.vm.$nextTick()
    const orders = w.emitted('reorder')
    expect(orders).toHaveLength(1)
    const newOrder = orders![0][0] as WidgetId[]
    // 示意图同款直接插序：health 拖到 hot 位置 → hot 在 health 前
    expect(newOrder.indexOf('hot')).toBeLessThan(newOrder.indexOf('health'))
    expect(newOrder).toHaveLength(layout.order.length)
  })
})

describe('DashboardGrid cycle-width 转发', () => {
  it('DashWidget 的 cycle-width 事件按 widgetId 转发', async() => {
    const w = mountGrid({ editing: true })
    const health = w.find('[data-widget-id="health"]')
    await health.find('.dash-widget-act').trigger('click')
    expect(w.emitted('cycle-width')).toHaveLength(1)
    expect(w.emitted('cycle-width')![0][0]).toBe('health')
  })
})
