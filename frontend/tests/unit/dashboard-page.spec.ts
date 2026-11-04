/**
 * 仪表盘主页 index.vue 状态机单测（仪表盘一期 W5）。
 *
 * 覆盖：预设四档切换与 custom 自动进入编辑模式、编辑按钮切换、
 * 恢复默认清持久化、localStorage roundtrip（最后保存者生效）、
 * KPI 行恒显网格外（KPI 卡 4 张 + 编辑模式仍渲染）。
 */
import { shallowMount, createLocalVue, Wrapper } from '@vue/test-utils'
import VueI18n from 'vue-i18n'
import Dashboard from '@/views/dashboard/index.vue'
import { getDashboardData } from '@/api/dashboard'
import { getActiveTorrents } from '@/api/torrents'
import { getTaskList } from '@/api/tasks'
import { getReportsSpeedHistory } from '@/api/reports'
import { STORAGE_KEY } from '@/views/dashboard/components/dashboardLayout'
import { DashboardData } from '@/types/dashboard'
import i18n from '@/i18n'

const localVue = createLocalVue()
// 双语先例（batch-transfer-dialog.spec）：挂载安装 i18n 单例提供真实 $t
localVue.use(VueI18n)

jest.mock('@/api/dashboard', () => ({ getDashboardData: jest.fn() }))
jest.mock('@/api/torrents', () => ({ getActiveTorrents: jest.fn() }))
jest.mock('@/api/tasks', () => ({ getTaskList: jest.fn() }))
jest.mock('@/api/reports', () => ({ getReportsSpeedHistory: jest.fn() }))

const makeData = (): DashboardData =>
  ({
    downloaders: { total: 1, online: 1, offline: 0 },
    torrents: {
      active: 10,
      downloading: 2,
      seeding: 8,
      paused: 0,
      statusBuckets: { error: 0, downloading: 2, seeding: 8, paused: 0, other: 0 },
      siteBuckets: [{ host: 'a.example.com', count: 5 }]
    },
    tasks: { total: 3, running: 0, stopped: 3, enabled: 2 },
    system: { uptime: 100, uptime_display: '1分钟', version: 'x', total_download_speed: 0, total_upload_speed: 0 },
    downloader_list: [],
    activities: []
  } as DashboardData)

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve()
  }
}

function mountPage(): Wrapper<Vue> {
  return shallowMount(Dashboard, {
    localVue,
    i18n,
    mocks: {
      $router: { push: jest.fn().mockResolvedValue(undefined) }
    }
  })
}

describe('views/dashboard/index.vue 布局状态机', () => {
  beforeEach(() => {
    window.localStorage.clear()
    jest.mocked(getDashboardData).mockReset()
    jest.mocked(getDashboardData).mockResolvedValue({ code: '200', status: 'success', msg: 'ok', data: makeData() } as never)
    jest.mocked(getActiveTorrents).mockResolvedValue({ code: '200', status: 'success', msg: 'ok', data: [] } as never)
    jest.mocked(getTaskList).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: { list: [] }
    } as never)
    jest.mocked(getReportsSpeedHistory).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: { range: '24h', series: [], samplingActive: true, firstSampleAt: null }
    } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
    window.localStorage.clear()
  })

  it('默认 overview + 非编辑；KPI 行恒 4 张在网格外', async() => {
    const w = mountPage()
    await flush()
    expect(w.find('.dash-page--editing').exists()).toBe(false)
    expect(w.findAllComponents({ name: 'KpiCard' })).toHaveLength(4)
    // 默认无自定义 → 不写持久化（首次进入交互后才写入）
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
    w.destroy()
  })

  it('切换 focus 预设持久化 preset；custom 自动进入编辑模式', async() => {
    const w = mountPage()
    await flush()
    const segButtons = w.findAll('.dash-seg button')
    expect(segButtons).toHaveLength(4)
    await segButtons.at(1).trigger('click') // focus
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) as string).preset).toBe('focus')
    expect(w.find('.dash-page--editing').exists()).toBe(false)
    await segButtons.at(3).trigger('click') // custom
    expect(w.find('.dash-page--editing').exists()).toBe(true)
    await segButtons.at(0).trigger('click') // 回 overview 退出编辑
    expect(w.find('.dash-page--editing').exists()).toBe(false)
    w.destroy()
  })

  it('编辑按钮切换编辑态并把预设切到 custom；恢复默认清持久化回 overview', async() => {
    const w = mountPage()
    await flush()
    await w.find('[data-testid="edit-layout-btn"]').trigger('click')
    expect(w.find('.dash-page--editing').exists()).toBe(true)
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) as string).preset).toBe('custom')
    await w.find('[data-testid="reset-layout-btn"]').trigger('click')
    expect(w.find('.dash-page--editing').exists()).toBe(false)
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
    w.destroy()
  })

  it('进入页面恢复持久化布局（custom 持久化不自动恢复编辑模式）', async() => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ order: ['hero', 'health'], spans: { hero: 12 }, preset: 'custom' })
    )
    const w = mountPage()
    await flush()
    expect(w.find('.dash-page--editing').exists()).toBe(false)
    // 恢复的顺序：Grid props order 首项 hero（shallowMount 下内部 widget stub）
    const grid = w.findComponent({ name: 'DashboardGrid' })
    expect((grid.props('layout') as { order: string[] }).order.slice(0, 2)).toEqual(['hero', 'health'])
    w.destroy()
  })

  it('cycle-width 事件更新 span 并持久化（6→8 循环档位）', async() => {
    const w = mountPage()
    await flush()
    w.findComponent({ name: 'DashboardGrid' }).vm.$emit('cycle-width', 'health')
    await w.vm.$nextTick()
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) as string)
    expect(saved.spans.health).toBe(8)
    w.destroy()
  })

  it('reorder 事件更新顺序并持久化', async() => {
    const w = mountPage()
    await flush()
    const newOrder = ['hot', 'health']
    w.findComponent({ name: 'DashboardGrid' }).vm.$emit('reorder', newOrder)
    await w.vm.$nextTick()
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) as string)
    expect(saved.order.slice(0, 2)).toEqual(newOrder)
    const grid = w.findComponent({ name: 'DashboardGrid' })
    expect((grid.props('layout') as { order: string[] }).order.slice(0, 2)).toEqual(newOrder)
    w.destroy()
  })

  it('进入大屏按钮跳 /dashboard/screen', async() => {
    const w = mountPage()
    await flush()
    const push = (w.vm as unknown as { $router: { push: jest.Mock } }).$router.push
    await w.find('[data-testid="enter-screen-btn"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/dashboard/screen')
    w.destroy()
  })
})
