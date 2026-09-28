/**
 * 统计·趋势页渲染测试（statistics-reports W5）。
 *
 * - period（month/week）切换重新拉取趋势；
 * - B9 range（24h/7d/30d）切换独立拉取速度历史；
 * - 空数据空态 + 口径脚注渲染。
 */

jest.mock('@/api/reports', () => ({
  getReportsTrends: jest.fn(),
  getReportsSpeedHistory: jest.fn()
}))

jest.mock('@/components/charts/EChart.vue', () => ({
  name: 'EChart',
  props: ['option', 'height', 'loading', 'emptyText'],
  render(this: { option: unknown }, h: (tag: string, data?: object) => Vue): Vue {
    return h('div', { class: 'echart-stub', attrs: { 'data-empty': String(this.option === null) } })
  }
}))

import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import VueI18n from 'vue-i18n'
import Vue from 'vue'
import i18n from '@/i18n'
import { getReportsSpeedHistory, getReportsTrends } from '@/api/reports'
import { ReportsTrendsData, SpeedHistory } from '@/types/reports'
import StatisticsTrends from '../trends/index.vue'

const localVue = createLocalVue()
localVue.use(VueI18n)
localVue.use(ElementUI)

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const trendsFixture: ReportsTrendsData = {
  added: [{ key: '2026-08', count: 12, sizeBytes: 1024 ** 3 }],
  completed: [{ key: '2026-08', count: 5, sizeBytes: 512 ** 3 }],
  ageBuckets: [
    { name: 'under7d', count: 3, sizeBytes: 1 },
    { name: 'to30d', count: 4, sizeBytes: 1 },
    { name: 'to90d', count: 0, sizeBytes: 0 },
    { name: 'to180d', count: 0, sizeBytes: 0 },
    { name: 'to1y', count: 0, sizeBytes: 0 },
    { name: 'over1y', count: 0, sizeBytes: 0 },
    { name: 'unknown', count: 2, sizeBytes: 1 }
  ],
  speedHistory: emptySpeedHistory('24h')
}

function emptySpeedHistory(range: '24h' | '7d' | '30d'): SpeedHistory {
  return { range, series: [], samplingActive: true, firstSampleAt: null }
}

function speedFixture(range: '24h' | '7d' | '30d'): SpeedHistory {
  return {
    range,
    series: [
      {
        downloaderId: 'dl-1',
        nickname: 'qb',
        removed: false,
        points: [
          { ts: '2026-09-25 10:00:00', downloadSpeed: 1024, uploadSpeed: 2048, online: true },
          { ts: '2026-09-25 10:01:00', downloadSpeed: 0, uploadSpeed: 0, online: false }
        ]
      }
    ],
    samplingActive: true,
    firstSampleAt: '2026-09-24 00:00:00'
  }
}

function mountPage(): Wrapper<Vue> {
  return mount(StatisticsTrends, { localVue, i18n })
}

function chartOptions(wrapper: Wrapper<Vue>): Array<Record<string, unknown> | null> {
  return wrapper.findAllComponents({ name: 'EChart' }).wrappers.map((w) => w.props('option'))
}

describe('统计·趋势页', () => {
  beforeEach(() => {
    (getReportsTrends as jest.Mock).mockReset().mockResolvedValue({ code: '200', status: 'success', msg: '', data: trendsFixture })
    ;(getReportsSpeedHistory as jest.Mock).mockReset().mockResolvedValue({ code: '200', status: 'success', msg: '', data: speedFixture('24h') })
  })

  it('渲染标题与四个图表面（新增/完成/库龄/速度）', async() => {
    const wrapper = mountPage()
    await flush()
    expect(wrapper.text()).toContain('趋势')
    const options = chartOptions(wrapper)
    expect(options.length).toBe(4)
    options.slice(0, 3).forEach((o) => expect(o).not.toBeNull())
    // 速度历史多系列：每下载器上/下行两条折线
    const speedSeries = options[3]?.series as Array<{ name: string }>
    expect(speedSeries.map((s) => s.name)).toEqual(['qb ↓', 'qb ↑'])
    wrapper.destroy()
  })

  it('period 切换为 week 时重新拉取趋势', async() => {
    const wrapper = mountPage()
    await flush()
    expect(getReportsTrends).toHaveBeenCalledWith('month', 12)
    const vm = wrapper.vm as unknown as { period: 'month' | 'week' }
    vm.period = 'week'
    await Vue.nextTick()
    await flush()
    expect(getReportsTrends).toHaveBeenCalledWith('week', 12)
    wrapper.destroy()
  })

  it('速度 range 切换为 7d 时独立拉取速度历史', async() => {
    const wrapper = mountPage()
    await flush()
    expect(getReportsSpeedHistory).toHaveBeenCalledWith('24h')
    const vm = wrapper.vm as unknown as { speedRange: '24h' | '7d' | '30d' }
    vm.speedRange = '7d'
    await Vue.nextTick()
    await flush()
    expect(getReportsSpeedHistory).toHaveBeenCalledWith('7d')
    wrapper.destroy()
  })

  it('首个样本时间存在时渲染采样启动脚注', async() => {
    const wrapper = mountPage()
    await flush()
    const notes = wrapper.find('[data-testid="caliber-notes"]')
    expect(notes.exists()).toBe(true)
    expect(notes.text()).toContain('2026-09-24 00:00:00')
    wrapper.destroy()
  })

  it('空数据空态：速度无样本时图表 option 为 null', async() => {
    (getReportsSpeedHistory as jest.Mock).mockResolvedValue({ code: '200', status: 'success', msg: '', data: emptySpeedHistory('24h') })
    const wrapper = mountPage()
    await flush()
    const options = chartOptions(wrapper)
    expect(options[3]).toBeNull()
    wrapper.destroy()
  })
})
