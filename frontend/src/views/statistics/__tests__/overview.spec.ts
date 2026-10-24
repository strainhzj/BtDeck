/**
 * 统计·总览页渲染测试（statistics-reports W5）。
 *
 * - mock @/api/reports + stub EChart（图表本体已有专项 EChart.spec）；
 * - 覆盖：数字卡渲染 / 五桶饼图与各条形 option 派生 / 双维度切换重建 option /
 *   空数据空态 / 30s 轮询定时器挂卸。
 */

jest.mock('@/api/reports', () => ({
  getReportsOverview: jest.fn()
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
import { getReportsOverview } from '@/api/reports'
import { ReportsOverviewData } from '@/types/reports'
import StatisticsOverview from '../overview/index.vue'

const localVue = createLocalVue()
localVue.use(VueI18n)
localVue.use(ElementUI)

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const overviewFixture: ReportsOverviewData = {
  totals: { count: 42, sizeBytes: 1024 ** 4, avgSizeBytes: 1024 ** 4 / 42, recycleBinSizeBytes: 1024 ** 3 },
  largest: [{ hash: 'h1', name: '最大种子', sizeBytes: 500 * 1024 ** 3 }],
  statusDist: [
    { bucket: 'seeding', count: 30, sizeBytes: 1 },
    { bucket: 'error', count: 2, sizeBytes: 1 }
  ],
  categories: [{ name: 'movies', count: 10, sizeBytes: 2 }],
  tags: [{ name: 'tag-a', count: 5, sizeBytes: 2 }],
  paths: [{ path: '/downloads', count: 42, sizeBytes: 3 }],
  downloaders: [
    { downloaderId: 'dl-1', nickname: 'qb', type: 0, removed: false, count: 40, sizeBytes: 1, statusDist: [{ bucket: 'seeding', count: 40, sizeBytes: 1 }] }
  ],
  liveSpeed: {
    totalDownloadSpeed: 1024 * 100,
    totalUploadSpeed: 1024 * 200,
    items: [{ downloaderId: 'dl-1', nickname: 'qb', online: true, downloadSpeed: 1024 * 100, uploadSpeed: 1024 * 200 }]
  }
}

function mountPage(): Wrapper<Vue> {
  return mount(StatisticsOverview, { localVue, i18n })
}

function chartOptions(wrapper: Wrapper<Vue>): Array<Record<string, unknown> | null> {
  return wrapper.findAllComponents({ name: 'EChart' }).wrappers.map((w) => w.props('option'))
}

describe('统计·总览页', () => {
  beforeEach(() => {
    (getReportsOverview as jest.Mock).mockReset().mockResolvedValue({ code: '200', status: 'success', msg: '', data: overviewFixture })
  })

  it('渲染标题、数字卡与实时速度卡', async() => {
    const wrapper = mountPage()
    await flush()
    expect(wrapper.text()).toContain('库存总览')
    const values = wrapper.findAll('[data-testid="stat-card-value"]').wrappers.map((w) => w.text())
    expect(values).toContain('42')
    // 回收站体积卡存在
    expect(wrapper.findAll('[data-testid="stat-card"]').length).toBeGreaterThanOrEqual(6)
    wrapper.destroy()
  })

  it('派生全部图表 option（五桶饼图/TOP10/分类/标签/目录/下载器）', async() => {
    const wrapper = mountPage()
    await flush()
    const options = chartOptions(wrapper)
    expect(options.length).toBe(6)
    // 五桶饼图
    expect((options[0]?.series as Array<{ data: Array<{ value: number }> }>)[0].data.map((d) => d.value)).toEqual([30, 2])
    // 全部非空
    options.forEach((o) => expect(o).not.toBeNull())
    wrapper.destroy()
  })

  it('双维度切换：分类/标签 option 随 dimension 重建', async() => {
    const wrapper = mountPage()
    await flush()
    const vm = wrapper.vm as unknown as { dimension: 'count' | 'size' }
    const countData = chartOptions(wrapper)[2]
    expect((countData?.series as Array<{ data: number[] }>)[0].data).toEqual([10])
    vm.dimension = 'size'
    await Vue.nextTick()
    const sizeData = chartOptions(wrapper)[2]
    expect((sizeData?.series as Array<{ data: number[] }>)[0].data).toEqual([2])
    wrapper.destroy()
  })

  it('空数据空态：全部图表 option 为 null', async() => {
    (getReportsOverview as jest.Mock).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: '',
      data: {
        ...overviewFixture,
        largest: [],
        statusDist: [],
        categories: [],
        tags: [],
        paths: [],
        downloaders: []
      }
    })
    const wrapper = mountPage()
    await flush()
    chartOptions(wrapper).forEach((o) => expect(o).toBeNull())
    wrapper.destroy()
  })

  it('30s 轮询：挂载启动 interval，销毁清理', async() => {
    const setIntervalSpy = jest.spyOn(window, 'setInterval')
    const clearIntervalSpy = jest.spyOn(window, 'clearInterval')
    const wrapper = mountPage()
    await flush()
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 30000)
    wrapper.destroy()
    expect(clearIntervalSpy).toHaveBeenCalled()
    setIntervalSpy.mockRestore()
    clearIntervalSpy.mockRestore()
  })
})
