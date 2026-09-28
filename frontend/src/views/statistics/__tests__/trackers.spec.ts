/**
 * 统计·Tracker 页渲染测试（statistics-reports W5）。
 *
 * - D14 站点条形 / D15 健康表（errorRate 进度条 + 受影响种子）/ D16 散点 + 表；
 * - 空数据空态与口径脚注。
 */

jest.mock('@/api/reports', () => ({
  getReportsTrackers: jest.fn()
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
import i18n from '@/i18n'
import { getReportsTrackers } from '@/api/reports'
import { ReportsTrackersData } from '@/types/reports'
import StatisticsTrackers from '../trackers/index.vue'

const localVue = createLocalVue()
localVue.use(VueI18n)
localVue.use(ElementUI)

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const trackersFixture: ReportsTrackersData = {
  sites: [{ host: 'tracker.example.com', count: 30, sizeBytes: 1024 ** 3 }],
  health: [
    { host: 'bad.example.com', errorRate: 0.6, affectedCount: 8 },
    { host: 'good.example.com', errorRate: 0.05, affectedCount: 1 }
  ],
  supplyDemand: [{ host: 'tracker.example.com', avgSeeders: 12.5, avgLeechers: 3.2, avgDownloads: 100, count: 20 }]
}

function mountPage(): Wrapper<Vue> {
  return mount(StatisticsTrackers, { localVue, i18n })
}

describe('统计·Tracker 页', () => {
  beforeEach(() => {
    (getReportsTrackers as jest.Mock).mockReset().mockResolvedValue({ code: '200', status: 'success', msg: '', data: trackersFixture })
  })

  it('渲染标题、健康榜表与冷热表', async() => {
    const wrapper = mountPage()
    await flush()
    expect(wrapper.text()).toContain('Tracker')
    // 两张 el-table（健康 + 冷热）
    expect(wrapper.findAll('.el-table').length).toBe(2)
    expect(wrapper.text()).toContain('bad.example.com')
    expect(wrapper.text()).toContain('good.example.com')
    // 受影响种子列值
    expect(wrapper.text()).toContain('8')
    wrapper.destroy()
  })

  it('两图表 option 派生（站点条形/冷热散点）', async() => {
    const wrapper = mountPage()
    await flush()
    const options = wrapper.findAllComponents({ name: 'EChart' }).wrappers.map((w) => w.props('option'))
    expect(options.length).toBe(2)
    const siteY = (options[0]?.yAxis as { data: string[] }).data
    expect(siteY).toEqual(['tracker.example.com'])
    const scatter = (options[1]?.series as Array<{ data: Array<[number, number, string]> }>)[0].data
    expect(scatter[0]).toEqual([12.5, 3.2, 'tracker.example.com'])
    wrapper.destroy()
  })

  it('渲染口径脚注（跨站重复体积 + 计数积累）', async() => {
    const wrapper = mountPage()
    await flush()
    const notes = wrapper.find('[data-testid="caliber-notes"]')
    expect(notes.exists()).toBe(true)
    expect(notes.text()).toContain('重复计入')
    wrapper.destroy()
  })

  it('空数据空态', async() => {
    (getReportsTrackers as jest.Mock).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: '',
      data: { sites: [], health: [], supplyDemand: [] }
    })
    const wrapper = mountPage()
    await flush()
    wrapper.findAllComponents({ name: 'EChart' }).wrappers.forEach((w) => {
      expect(w.props('option')).toBeNull()
    })
    expect(wrapper.findAll('.el-table').length).toBe(0)
    wrapper.destroy()
  })
})
