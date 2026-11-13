/**
 * KPI 行卡片壳单测（仪表盘一期 W2/W5）。
 *
 * - KpiCard：label/icon 渲染、value/foot 具名 slot、clickable 键盘可达
 *   （role=button + enter 触发）；不可点击时不挂 role/tabindex；
 * - DashWidget：标题/live 角标/presetTag 角标；编辑模式注入 draggable 与
 *   宽度按钮可见（CSS 类承载）、cycle-width 事件上抛；非编辑不抛。
 */
import { shallowMount, Wrapper } from '@vue/test-utils'
import KpiCard from '@/views/dashboard/components/KpiCard.vue'
import DashWidget from '@/views/dashboard/components/DashWidget.vue'

describe('KpiCard 壳', () => {
  const mountKpi = (propsData: Record<string, unknown>, slots?: Record<string, string>): Wrapper<Vue> =>
    shallowMount(KpiCard, {
      propsData,
      slots,
      mocks: { $t: (k: string) => k }
    })

  it('渲染 label 与 value/foot slot', () => {
    const w = mountKpi({ label: '下载器在线', icon: 'server' }, { value: '3/4', foot: '<b class="f">全部在线</b>' })
    expect(w.text()).toContain('下载器在线')
    expect(w.find('.dash-kpi-value').text()).toBe('3/4')
    expect(w.find('b.f').text()).toBe('全部在线')
  })

  it('clickable 时挂 role=button/键盘可达并上抛 click', async() => {
    const w = mountKpi({ label: 'L', icon: 'server', clickable: true, ariaLabel: 'go' })
    expect(w.attributes('role')).toBe('button')
    expect(w.attributes('aria-label')).toBe('go')
    await w.trigger('keypress.enter')
    expect(w.emitted('click')).toHaveLength(1)
  })

  it('非 clickable 不挂 role 且 click 不上抛', async() => {
    const w = mountKpi({ label: 'L', icon: 'server' })
    expect(w.attributes('role')).toBeUndefined()
    expect(w.attributes('tabindex')).toBeUndefined()
    await w.trigger('keypress.enter')
    expect(w.emitted('click')).toBeUndefined()
  })

  it('默认 slot 渲染于 foot 之后（系统速度卡双列数值区契约，2026-11-13 评审修复：此前无出口被静默丢弃）', () => {
    const w = mountKpi({ label: '系统总速度', icon: 'zap' }, { value: '<span/>', default: '<div class="dual-extra">DL/UL</div>' })
    expect(w.find('.dual-extra').exists()).toBe(true)
    expect(w.text()).toContain('DL/UL')
  })

  it('clickable 空串（模板裸属性形态）经 Boolean 转换等价 true：挂 role 并上抛 click（评审修复）', async() => {
    const w = mountKpi({ label: 'L', icon: 'server', clickable: '', ariaLabel: 'go' })
    expect(w.attributes('role')).toBe('button')
    await w.trigger('keypress.enter')
    expect(w.emitted('click')).toHaveLength(1)
  })
})

describe('DashWidget 壳', () => {
  const mountWidget = (propsData: Record<string, unknown>): Wrapper<Vue> =>
    shallowMount(DashWidget, {
      propsData: { widgetId: 'health', title: '实例健康', span: 6, ...propsData },
      slots: { default: '<div class="body-c">BODY</div>' },
      mocks: {
        $t: (k: string) => `T(${k})`
      }
    })

  it('渲染标题/data-widget-id/--span 变量与默认插槽', () => {
    const w = mountWidget({})
    expect(w.attributes('data-widget-id')).toBe('health')
    expect(w.attributes('style')).toContain('--span')
    expect(w.text()).toContain('实例健康')
    expect(w.find('.body-c').text()).toBe('BODY')
  })

  it('live widget 渲染实时角标（英文键经 $t 包装可辨）', () => {
    const w = mountWidget({ widgetId: 'spark' })
    expect(w.find('.dash-widget-tag.live').text()).toBe('T(dashboard.widgets.liveTag)')
  })

  it('pulse 归属 widget 渲染预设角标', () => {
    const w = mountWidget({ widgetId: 'radar' })
    expect(w.find('.dash-widget-tag').text()).toBe('T(dashboard.preset.pulse)')
  })

  it('编辑模式：draggable=true 且宽度按钮渲染；点击上抛 cycle-width', async() => {
    const w = mountWidget({ editing: true })
    expect(w.attributes('draggable')).toBe('true')
    const btn = w.find('.dash-widget-act')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    expect(w.emitted('cycle-width')).toHaveLength(1)
  })

  it('非编辑模式：draggable=false', () => {
    const w = mountWidget({ editing: false })
    expect(w.attributes('draggable')).toBe('false')
  })
})
