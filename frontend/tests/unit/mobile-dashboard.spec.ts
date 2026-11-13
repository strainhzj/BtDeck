/**
 * 移动仪表盘二期单测（dashboard-mobile-2026-11）。
 *
 * 覆盖：一期桌面卡片族复用（4 KPI + 8 widget 卡挂载与 props 映射）、
 * D1 活跃种子 3s 轮询（SpeedPollingMixin 与桌面一致）、下拉刷新全量并发
 * 不闪 loading、热门种子「查看全部」跳转、下载器空态 CTA（有/无清单两态）、
 * beforeDestroy 定时器全清理（3 低频 interval + 轮询链 setTimeout）。
 */
import { shallowMount, createLocalVue, Wrapper } from '@vue/test-utils'
import Vue, { VNode, CreateElement } from 'vue'
import VueI18n from 'vue-i18n'
import MobileDashboard from '@/views/mobile/dashboard.vue'
import InstanceHealthCard from '@/views/dashboard/components/InstanceHealthCard.vue'
import { getDashboardData } from '@/api/dashboard'
import { getActiveTorrents, ActiveTorrentSpeed } from '@/api/torrents'
import { getTaskList } from '@/api/tasks'
import { getReportsSpeedHistory } from '@/api/reports'
import { DashboardData, DownloaderListItem } from '@/types/dashboard'
import i18n from '@/i18n'

const localVue = createLocalVue()
// 双语先例（dashboard-page.spec）：挂载安装 i18n 单例提供真实 $t
localVue.use(VueI18n)

jest.mock('@/api/dashboard', () => ({ getDashboardData: jest.fn() }))
jest.mock('@/api/torrents', () => ({ getActiveTorrents: jest.fn() }))
jest.mock('@/api/tasks', () => ({ getTaskList: jest.fn() }))
jest.mock('@/api/reports', () => ({ getReportsSpeedHistory: jest.fn() }))

const makeData = (): DashboardData =>
  ({
    downloaders: { total: 0, online: 0, offline: 0 },
    torrents: {
      active: 10,
      downloading: 2,
      seeding: 8,
      paused: 0,
      statusBuckets: { error: 0, downloading: 2, seeding: 8, paused: 0, other: 0 },
      siteBuckets: [{ host: 'a.example.com', count: 5 }]
    },
    tasks: { total: 3, running: 0, stopped: 3, enabled: 2 },
    system: { uptime: 100, uptime_display: '1分钟', version: 'x', total_download_speed: 286720, total_upload_speed: 1024 },
    downloader_list: [],
    activities: []
  } as DashboardData)

const TORRENTS: ActiveTorrentSpeed[] = [
  { hash: 'a', name: 'a.iso', downloadSpeed: 100, uploadSpeed: 0, progress: 50, num_seeds: 1, num_leechs: 1 },
  { hash: 'b', name: 'b.iso', downloadSpeed: 0, uploadSpeed: 40, progress: 80, num_seeds: 1, num_leechs: 1 }
]

const TASK = {
  taskId: 1,
  taskName: '同步任务',
  taskCode: 'c1',
  taskStatus: 0,
  taskType: 0,
  executor: 'echo',
  enabled: true,
  lastExecuteTime: null,
  lastExecuteDuration: null,
  cronPlan: '0 * * * *',
  taskStatusName: '',
  taskTypeName: '',
  createTime: ''
}

const DL: DownloaderListItem = {
  downloader_id: 'd1',
  nickname: 'qb-main',
  downloader_type: 0,
  status: 'online',
  downloading: 2,
  seeding: 80,
  paused: 0,
  download_speed: 1024,
  upload_speed: 512
}

/** DashWidget 透传 stub：shallowMount 默认 stub 不渲染 slot，卡片须真实挂载才能断言 props */
const DashWidgetPassthrough = Vue.extend({
  name: 'DashWidget',
  render(h: CreateElement): VNode {
    return h('div', { class: 'dw-passthrough' }, this.$slots.default)
  }
})

/**
 * KpiCard 交互 stub：渲染 value/foot/default 三个 slot + 转发 $listeners 到根元素——
 * 评审修复防线：真实页面点击导航链路与速度双列渲染（默认 slot）须在页面级可断言。
 */
const KpiCardInteractive = Vue.extend({
  name: 'KpiCard',
  props: { clickable: { type: [Boolean, String], default: false } },
  render(this: { $listeners: Record<string, Function>, $slots: Record<string, VNode[] | undefined> }, h: CreateElement): VNode {
    return h('div', { class: 'kpi-stub', on: this.$listeners }, [
      h('div', { class: 'dash-kpi-value' }, this.$slots.value),
      h('div', { class: 'dash-kpi-foot' }, this.$slots.foot),
      h('div', { class: 'dash-kpi-extra' }, this.$slots.default)
    ])
  }
})

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve()
  }
}

function mountPage(): Wrapper<Vue> {
  return shallowMount(MobileDashboard, {
    localVue,
    i18n,
    stubs: { DashWidget: DashWidgetPassthrough, KpiCard: KpiCardInteractive, InstanceHealthCard: InstanceHealthCard },
    mocks: {
      $message: { error: jest.fn(), success: jest.fn(), warning: jest.fn() },
      $router: {
        push: jest.fn().mockResolvedValue(undefined),
        replace: jest.fn().mockResolvedValue(undefined)
      }
    }
  })
}

describe('views/mobile/dashboard.vue 移动仪表盘二期', () => {
  beforeEach(() => {
    jest.mocked(getDashboardData).mockReset()
    jest.mocked(getDashboardData).mockResolvedValue({ code: '200', status: 'success', msg: 'ok', data: makeData() } as never)
    jest.mocked(getActiveTorrents).mockReset()
    jest.mocked(getActiveTorrents).mockResolvedValue({ code: '200', status: 'success', msg: 'ok', data: TORRENTS } as never)
    jest.mocked(getTaskList).mockReset()
    jest.mocked(getTaskList).mockResolvedValue({ code: '200', status: 'success', msg: 'ok', data: { list: [TASK] } } as never)
    jest.mocked(getReportsSpeedHistory).mockReset()
    jest.mocked(getReportsSpeedHistory).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: { range: '24h', series: [], samplingActive: true, firstSampleAt: null }
    } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('首载：loading 提示 → 4 KPI + 8 widget 卡挂载，props 对齐一期桌面语义', async() => {
    const w = mountPage()
    expect(w.find('.m-hint').exists()).toBe(true)
    await flush()
    expect(w.find('.m-hint').exists()).toBe(false)
    expect(w.findAllComponents({ name: 'KpiCard' })).toHaveLength(4)
    expect(w.findAll('.dw-passthrough')).toHaveLength(8)
    expect(w.findComponent({ name: 'StatusDonutCard' }).props('buckets')).toEqual(makeData().torrents.statusBuckets)
    expect(w.findComponent({ name: 'HeroPulseCard' }).props('downloading')).toBe(2)
    expect(w.findComponent({ name: 'HeroPulseCard' }).props('activeTorrents')).toHaveLength(2)
    expect(w.findComponent({ name: 'SiteBarsCard' }).props('buckets')).toEqual([{ host: 'a.example.com', count: 5 }])
    expect(w.findComponent({ name: 'HotTorrentsCard' }).props('torrents')).toHaveLength(2)
    expect(w.findComponent({ name: 'CronTaskCard' }).props('tasks')).toHaveLength(1)
    expect(w.findComponent({ name: 'DailyTrafficCard' }).props('loading')).toBe(false)
    expect((w.vm as unknown as { hasData: boolean }).hasData).toBe(true)
    w.destroy()
  })

  it('D1：活跃种子轮询 3s（SpeedPollingMixin，首轮延迟一周期防双发）', async() => {
    const setTimeoutSpy = jest.spyOn(window, 'setTimeout')
    const w = mountPage()
    await flush()
    expect(setTimeoutSpy.mock.calls.filter(c => c[1] === 3000)).toHaveLength(1)
    setTimeoutSpy.mockRestore()
    w.destroy()
  })

  it('下拉刷新：四个数据源并发各 +1 次，不闪 loading', async() => {
    const w = mountPage()
    await flush()
    expect(getDashboardData).toHaveBeenCalledTimes(1)
    const vm = w.vm as unknown as { onPullRefresh(): Promise<void> }
    await vm.onPullRefresh()
    expect(getDashboardData).toHaveBeenCalledTimes(2)
    expect(getActiveTorrents).toHaveBeenCalledTimes(2)
    expect(getTaskList).toHaveBeenCalledTimes(2)
    expect(getReportsSpeedHistory).toHaveBeenCalledTimes(2)
    expect(w.find('.m-hint').exists()).toBe(false)
    w.destroy()
  })

  it('热门种子卡「查看全部种子」跳 /m/torrents', async() => {
    const w = mountPage()
    await flush()
    await w.find('.m-view-all').trigger('click')
    expect((w.vm.$router as unknown as { push: jest.Mock }).push).toHaveBeenCalledWith('/m/torrents')
    w.destroy()
  })

  it('系统速度 KPI 渲染双列数值（默认 slot 契约，评审修复：KpiCard 此前无出口致恒空白）', async() => {
    const w = mountPage()
    await flush()
    const speedCard = w.findAll('.kpi-stub').at(3)
    expect(speedCard.find('.dash-kpi-extra .dash-kpi-dual').exists()).toBe(true)
    expect(speedCard.text()).toContain('280.00 KB/s')
    expect(speedCard.text()).toContain('1.00 KB/s')
    w.destroy()
  })

  it('KPI 点击穿透：下载器/种子/任务三卡导航（评审修复：裸 clickable 空串经 Boolean 转换生效）', async() => {
    const w = mountPage()
    await flush()
    const push = (w.vm.$router as unknown as { push: jest.Mock }).push
    await w.findAll('.kpi-stub').at(0).trigger('click')
    expect(push).toHaveBeenCalledWith('/m/downloader')
    await w.findAll('.kpi-stub').at(1).trigger('click')
    expect(push).toHaveBeenCalledWith('/m/torrents')
    await w.findAll('.kpi-stub').at(2).trigger('click')
    expect(push).toHaveBeenCalledWith('/m/tasks')
    w.destroy()
  })

  it('下载器行点击/回车进入 /m/downloader（评审修复：恢复旧页穿透语义）', async() => {
    jest.mocked(getDashboardData).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: { ...makeData(), downloader_list: [DL] }
    } as never)
    const w = mountPage()
    await flush()
    const row = w.find('.dash-rowline')
    expect(row.attributes('role')).toBe('button')
    await row.trigger('click')
    expect((w.vm.$router as unknown as { push: jest.Mock }).push).toHaveBeenCalledWith('/m/downloader')
    await row.trigger('keypress', { key: 'Enter' })
    expect((w.vm.$router as unknown as { push: jest.Mock }).push).toHaveBeenCalledTimes(2)
    w.destroy()
  })

  it('首屏解耦：traffic 失败不阻塞主数据渲染（评审修复：慢辅助接口不再阻塞整页）', async() => {
    jest.mocked(getReportsSpeedHistory).mockRejectedValue(new Error('slow'))
    const w = mountPage()
    await flush()
    expect(w.find('.m-kpi-grid').exists()).toBe(true)
    expect(w.find('.m-widget-stack').exists()).toBe(true)
    expect((w.vm as unknown as { hasData: boolean }).hasData).toBe(true)
    w.destroy()
  })

  it('回前台补刷：dashboard/tasks/traffic 立即刷新，活跃种子由 mixin resume 补（评审修复）', async() => {
    const hiddenSpy = jest.spyOn(document, 'hidden', 'get').mockReturnValue(false)
    const w = mountPage()
    await flush()
    jest.mocked(getDashboardData).mockClear()
    jest.mocked(getActiveTorrents).mockClear()
    jest.mocked(getTaskList).mockClear()
    jest.mocked(getReportsSpeedHistory).mockClear()
    hiddenSpy.mockReturnValue(true)
    document.dispatchEvent(new Event('visibilitychange'))
    await flush()
    expect(getDashboardData).not.toHaveBeenCalled()
    hiddenSpy.mockReturnValue(false)
    document.dispatchEvent(new Event('visibilitychange'))
    await flush()
    expect(getDashboardData).toHaveBeenCalledTimes(1)
    expect(getTaskList).toHaveBeenCalledTimes(1)
    expect(getReportsSpeedHistory).toHaveBeenCalledTimes(1)
    expect(getActiveTorrents).toHaveBeenCalledTimes(1)
    hiddenSpy.mockRestore()
    w.destroy()
  })

  it('下载器空态：健康卡不渲染，CTA 直达 /m/downloader?create=1', async() => {
    const w = mountPage()
    await flush()
    expect(w.findComponent({ name: 'InstanceHealthCard' }).exists()).toBe(false)
    expect(w.find('.m-empty-cta').exists()).toBe(true)
    await w.find('.m-cta-btn').trigger('click')
    expect((w.vm.$router as unknown as { replace: jest.Mock }).replace).toHaveBeenCalledWith({
      path: '/m/downloader',
      query: { create: '1' }
    })
    w.destroy()
  })

  it('下载器非空：InstanceHealthCard 渲染且空态 CTA 不出现', async() => {
    jest.mocked(getDashboardData).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: { ...makeData(), downloader_list: [DL] }
    } as never)
    const w = mountPage()
    await flush()
    expect(w.findComponent({ name: 'InstanceHealthCard' }).exists()).toBe(true)
    expect(w.find('.m-empty-cta').exists()).toBe(false)
    w.destroy()
  })

  it('信封契约：code 非 200 停留空态不误报错误（旧页契约移植），网络失败才 toast', async() => {
    jest.mocked(getDashboardData).mockResolvedValue({ code: '500', status: 'error', msg: 'boom', data: null } as never)
    const w = mountPage()
    await flush()
    expect((w.vm as unknown as { hasData: boolean }).hasData).toBe(false)
    const messageError = (w.vm.$message as unknown as { error: jest.Mock }).error
    expect(messageError).not.toHaveBeenCalled()
    w.destroy()
  })

  it('首载网络失败：提示错误且落空态', async() => {
    jest.mocked(getDashboardData).mockRejectedValue(new Error('network down'))
    const w = mountPage()
    await flush()
    expect((w.vm.$message as unknown as { error: jest.Mock }).error).toHaveBeenCalled()
    expect((w.vm as unknown as { hasData: boolean }).hasData).toBe(false)
    w.destroy()
  })

  it('销毁：三个低频定时器 + 轮询链 setTimeout 全清理', async() => {
    const clearIntSpy = jest.spyOn(window, 'clearInterval')
    const clearTimeoutSpy = jest.spyOn(window, 'clearTimeout')
    const w = mountPage()
    await flush()
    w.destroy()
    expect(clearIntSpy).toHaveBeenCalledTimes(3)
    expect(clearTimeoutSpy).toHaveBeenCalled()
    clearIntSpy.mockRestore()
    clearTimeoutSpy.mockRestore()
  })
})
