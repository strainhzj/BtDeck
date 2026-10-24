/**
 * 趣味报告沉浸页测试（statistics-reports W6，PLANS/statistics-reports.md §6）。
 *
 * 覆盖：
 * - 沉浸层约束（决策 10）：根元素即覆盖层（fixed + z-index 1200——>1001 盖
 *   sidebar、<2001 不压 Element Message）；
 * - route query 状态恢复（?mode=&year=&slide=，重挂载后进度不丢）；
 * - 子模式切换（战报/年度报告）与年份交互写回 query；
 * - 翻页交互（边界禁用 + 键盘步进）。
 */

jest.mock('@/api/reports', () => ({
  getReportsFunSummary: jest.fn(),
  getReportsFunYearly: jest.fn()
}))

import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import VueI18n from 'vue-i18n'
import Vue from 'vue'
import i18n from '@/i18n'
import { getReportsFunSummary, getReportsFunYearly } from '@/api/reports'
import { ReportsFunSummaryData, ReportsFunYearlyData } from '@/types/reports'
import StatisticsFunReport from '../fun-report/index.vue'

const localVue = createLocalVue()
localVue.use(VueI18n)
localVue.use(ElementUI)

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const summaryFixture: ReportsFunSummaryData = {
  guardian: {
    fireCount: 6,
    totalConsidered: 40,
    excludedCount: 3,
    top10: [{ hash: 'h1', name: '最后的火种', sizeBytes: 1024 ** 3, minSeeders: 1 }]
  },
  badges: {
    uploadedBytes: 2 * 1024 ** 4,
    currentTier: 'silver',
    nextTier: 'gold',
    nextTierAtTB: 10,
    equivalents: { movies: 256, blurays: 51, tvSeasons: 68 }
  },
  shame: [{ hash: 's1', name: '白嫖一号', ratio: 0.05, sizeBytes: 1 }],
  pride: [{ hash: 'p1', name: '慈善一号', ratio: 42, sizeBytes: 1 }]
}

const yearlyFixture: ReportsFunYearlyData = {
  year: 2025,
  yearAdded: { count: 36, sizeBytes: 5 * 1024 ** 4 },
  busiestMonth: { key: '2025-03', count: 12 },
  busiestDay: { key: '2025-03-05', count: 4 },
  topSite: { host: 'tracker.example.com', sizeBytes: 3 * 1024 ** 4 },
  elder: { hash: 'e1', name: '元老种', addedDate: '2024-06-01 00:00:00', seedingDays: 400 },
  fireCount: 6,
  uploadEstimate: summaryFixture.badges
}

const mockRouter = {
  replace: jest.fn().mockResolvedValue(undefined),
  push: jest.fn().mockResolvedValue(undefined)
}

function mountFun(query: Record<string, string> = {}): Wrapper<Vue> {
  return mount(StatisticsFunReport, {
    localVue,
    i18n,
    mocks: { $route: { query }, $router: mockRouter }
  })
}

describe('趣味报告沉浸页（决策 10 约束）', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(getReportsFunSummary as jest.Mock).mockReset().mockResolvedValue({ code: '200', status: 'success', msg: '', data: summaryFixture })
    ;(getReportsFunYearly as jest.Mock).mockReset().mockResolvedValue({ code: '200', status: 'success', msg: '', data: yearlyFixture })
  })

  describe('沉浸层 z-index 与根元素约束', () => {
    it('根元素即覆盖层：根节点带覆盖层类且无外包 wrapper', () => {
      const wrapper = mountFun()
      expect(wrapper.element.classList.contains('fun-report')).toBe(true)
      wrapper.destroy()
    })

    it('源码契约：.fun-report 根规则 position:fixed + z-index:1200（>1001 盖 sidebar，<2001 不压 Element 弹层）', () => {
      // vue-jest 不注入 SFC 样式（getComputedStyle 拿不到），改用源码文本契约钉住决策 10 不变量
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const fs = require('fs')
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const path = require('path')
      const source = fs.readFileSync(
        path.resolve(__dirname, '../fun-report/index.vue'),
        'utf-8'
      )
      const rootRule = source.match(/\.fun-report\s*\{[^}]*\}/)?.[0] ?? ''
      expect(rootRule).toMatch(/position:\s*fixed/)
      const zMatch = rootRule.match(/z-index:\s*(\d+)/)
      const z = zMatch ? parseInt(zMatch[1], 10) : NaN
      expect(z).toBe(1200)
      expect(z).toBeGreaterThan(1001)
      expect(z).toBeLessThan(2001)
    })
  })

  describe('战报模式（24/25/27）', () => {
    it('默认渲染战报：三卡片 + 火种数 + 勋章档位 + 双榜', async() => {
      const wrapper = mountFun()
      await flush()
      expect(getReportsFunSummary).toHaveBeenCalledTimes(1)
      const panel = wrapper.find('[data-testid="battle-panel"]')
      expect(panel.exists()).toBe(true)
      expect(wrapper.text()).toContain('火种守护者')
      expect(wrapper.text()).toContain('6')
      expect(wrapper.text()).toContain('银')
      expect(wrapper.text()).toContain('白嫖一号')
      expect(wrapper.text()).toContain('慈善一号')
      wrapper.destroy()
    })

    it('切换到年度报告：写回 query（mode=yearly + slide 重置 1）', async() => {
      const wrapper = mountFun()
      await flush()
      await wrapper.find('[data-testid="mode-yearly"]').trigger('click')
      expect(mockRouter.replace).toHaveBeenCalledWith({
        query: expect.objectContaining({ mode: 'yearly', slide: '1' })
      })
      wrapper.destroy()
    })
  })

  describe('年度报告（26）与 route query 状态恢复', () => {
    it('重挂载后进度不丢：?mode=yearly&year=2025&slide=4 → 第 4/8 页与年份高亮恢复', async() => {
      const wrapper = mountFun({ mode: 'yearly', year: '2025', slide: '4' })
      await flush()
      expect(getReportsFunYearly).toHaveBeenCalledWith(2025)
      expect(wrapper.find('[data-testid="yearly-panel"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('第 4 / 8 页')
      expect(wrapper.find('[data-year="2025"]').classes()).toContain('year-picker__item--active')
      // 第 4 页内容：体积占比最高站点
      expect(wrapper.text()).toContain('tracker.example.com')
      wrapper.destroy()
    })

    it('非法 slide/year 落默认（第 1 页 / 今年）', async() => {
      const wrapper = mountFun({ mode: 'yearly', slide: '99', year: '1999' })
      await flush()
      expect(wrapper.text()).toContain('第 1 / 8 页')
      wrapper.destroy()
    })

    it('翻页交互：next/prev 写回 query；边界禁用', async() => {
      const wrapper = mountFun({ mode: 'yearly' })
      await flush()
      const prev = wrapper.find('[data-testid="slide-prev"]')
      const next = wrapper.find('[data-testid="slide-next"]')
      expect(prev.attributes('disabled')).toBeTruthy() // 第 1 页禁用上一页
      await next.trigger('click')
      expect(mockRouter.replace).toHaveBeenCalledWith({ query: expect.objectContaining({ slide: '2' }) })
      wrapper.destroy()

      const tail = mountFun({ mode: 'yearly', slide: '8' })
      await flush()
      expect(tail.find('[data-testid="slide-next"]').attributes('disabled')).toBeTruthy()
      tail.destroy()
    })

    it('键盘左右步进翻页', async() => {
      const wrapper = mountFun({ mode: 'yearly', slide: '3' })
      await flush()
      await wrapper.find('[data-testid="fun-report-overlay"]').trigger('keydown.right')
      expect(mockRouter.replace).toHaveBeenCalledWith({ query: expect.objectContaining({ slide: '4' }) })
      mockRouter.replace.mockClear()
      await wrapper.find('[data-testid="fun-report-overlay"]').trigger('keydown.left')
      expect(mockRouter.replace).toHaveBeenCalledWith({ query: expect.objectContaining({ slide: '2' }) })
      wrapper.destroy()
    })

    it('年份切换：year 写回 query 且 slide 重置 1', async() => {
      const wrapper = mountFun({ mode: 'yearly', year: '2025', slide: '5' })
      await flush()
      await wrapper.find('[data-year="2024"]').trigger('click')
      expect(mockRouter.replace).toHaveBeenCalledWith({
        query: expect.objectContaining({ year: '2024', slide: '1' })
      })
      wrapper.destroy()
    })
  })

  it('关闭返回统计总览', async() => {
    const wrapper = mountFun()
    await flush()
    await wrapper.find('[data-testid="fun-report-close"]').trigger('click')
    expect(mockRouter.push).toHaveBeenCalledWith('/statistics/overview')
    wrapper.destroy()
  })

  it('空数据：年度面板显示空态占位', async() => {
    (getReportsFunYearly as jest.Mock).mockResolvedValue({ code: '200', status: 'success', msg: '', data: null })
    const wrapper = mountFun({ mode: 'yearly' })
    await flush()
    await Vue.nextTick()
    expect(wrapper.text()).toContain('暂无数据')
    wrapper.destroy()
  })
})
