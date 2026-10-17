/**
 * 统计·做种页渲染测试（statistics-reports W5）。
 *
 * - ratio 直方图 + NULL 计数展示；slackers 散点/表；辅种卡与 TOP10 条形；
 * - 空数据空态。
 */

jest.mock('@/api/reports', () => ({
  getReportsSeeding: jest.fn()
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
import { getReportsSeeding } from '@/api/reports'
import { ReportsSeedingData } from '@/types/reports'
import StatisticsSeeding from '../seeding/index.vue'

const localVue = createLocalVue()
localVue.use(VueI18n)
localVue.use(ElementUI)

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const seedingFixture: ReportsSeedingData = {
  ratioBuckets: [
    { bucket: '<0.5', count: 3, sizeBytes: 1 },
    { bucket: '0.5-1', count: 0, sizeBytes: 0 },
    { bucket: '1-2', count: 5, sizeBytes: 1 },
    { bucket: '2-5', count: 0, sizeBytes: 0 },
    { bucket: '5-10', count: 0, sizeBytes: 0 },
    { bucket: '10+', count: 1, sizeBytes: 1 }
  ],
  ratioNullCount: 7,
  slackers: [
    { hash: 'h1', name: '摸鱼一号', sizeBytes: 2048 ** 3, ratio: 0.2 },
    { hash: 'h2', name: '摸鱼二号', sizeBytes: 1024 ** 3, ratio: 0.4 }
  ],
  auxiliary: {
    totalTorrents: 20,
    crossSeedCount: 5,
    crossSeedRate: 0.25,
    top10: [{ hash: 'h3', name: '辅种王', auxiliarySeedCount: 9, sizeBytes: 1 }]
  }
}

function mountPage(): Wrapper<Vue> {
  return mount(StatisticsSeeding, { localVue, i18n })
}

describe('统计·做种页', () => {
  beforeEach(() => {
    (getReportsSeeding as jest.Mock).mockReset().mockResolvedValue({ code: '200', status: 'success', msg: '', data: seedingFixture })
  })

  it('渲染标题、NULL 计数与辅种率卡', async() => {
    const wrapper = mountPage()
    await flush()
    expect(wrapper.text()).toContain('做种')
    expect(wrapper.text()).toContain('7') // ratioNullCount
    expect(wrapper.text()).toContain('25.0%') // 辅种率
    wrapper.destroy()
  })

  it('三图表 option 派生（ratio 柱/slackers 散点/辅种条）+ slackers 表', async() => {
    const wrapper = mountPage()
    await flush()
    const options = wrapper.findAllComponents({ name: 'EChart' }).wrappers.map((w) => w.props('option'))
    expect(options.length).toBe(3)
    const ratioData = (options[0]?.series as Array<{ data: number[] }>)[0].data
    expect(ratioData).toEqual([3, 0, 5, 0, 0, 1])
    const scatter = (options[1]?.series as Array<{ data: Array<[number, number, string]> }>)[0].data
    expect(scatter[0]).toEqual([2048 ** 3, 0.2, '摸鱼一号'])
    expect(wrapper.findAll('.el-table__row').length).toBe(2)
    wrapper.destroy()
  })

  it('空数据空态：全图表 null', async() => {
    (getReportsSeeding as jest.Mock).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: '',
      data: {
        ratioBuckets: seedingFixture.ratioBuckets.map((b) => ({ ...b, count: 0 })),
        ratioNullCount: 0,
        slackers: [],
        auxiliary: { totalTorrents: 0, crossSeedCount: 0, crossSeedRate: 0, top10: [] }
      }
    })
    const wrapper = mountPage()
    await flush()
    wrapper.findAllComponents({ name: 'EChart' }).wrappers.forEach((w) => {
      expect(w.props('option')).toBeNull()
    })
    expect(wrapper.findAll('.el-table__row').length).toBe(0)
    wrapper.destroy()
  })
})
