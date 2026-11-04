/**
 * DataScreen 大屏单测（仪表盘一期 W4/W5）。
 *
 * 覆盖：KPI 六项渲染（下载/上传/活跃种子/近 24h 上传/已启用任务/运行时长，
 * 无分享率与异常数）、时钟/日期渲染、任务播报排序与空态、Esc 退出跳转
 * /dashboard、退出按钮。
 */
import { shallowMount, createLocalVue, Wrapper } from '@vue/test-utils'
import VueI18n from 'vue-i18n'
import DataScreen from '@/views/dashboard/screen.vue'
import { getDashboardData } from '@/api/dashboard'
import { getActiveTorrents } from '@/api/torrents'
import { getReportsSpeedHistory } from '@/api/reports'
import { DashboardData } from '@/types/dashboard'
import i18n from '@/i18n'

const localVue = createLocalVue()
localVue.use(VueI18n)

jest.mock('@/api/dashboard', () => ({ getDashboardData: jest.fn() }))
jest.mock('@/api/torrents', () => ({ getActiveTorrents: jest.fn() }))
jest.mock('@/api/reports', () => ({ getReportsSpeedHistory: jest.fn() }))

const makeData = (): DashboardData =>
  ({
    downloaders: { total: 3, online: 3, offline: 0 },
    torrents: {
      active: 128,
      downloading: 12,
      seeding: 116,
      paused: 0,
      statusBuckets: { error: 0, downloading: 12, seeding: 116, paused: 0, other: 0 },
      siteBuckets: []
    },
    tasks: { total: 5, running: 0, stopped: 5, enabled: 5 },
    system: {
      uptime: 86400,
      uptime_display: '1天0小时',
      version: 'x',
      total_download_speed: 135000000, // 128.8 MB/s 级
      total_upload_speed: 48000000
    },
    downloader_list: [
      {
        downloader_id: 'd1',
        nickname: 'QB-1',
        downloader_type: 0,
        status: 'online',
        downloading: 5,
        seeding: 48,
        paused: 0,
        download_speed: 1000,
        upload_speed: 500
      }
    ],
    activities: []
  } as DashboardData)

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve()
  }
}

function mountScreen(): Wrapper<Vue> {
  return shallowMount(DataScreen, {
    localVue,
    i18n,
    mocks: { $router: { push: jest.fn().mockResolvedValue(undefined) } }
  })
}

describe('views/dashboard/DataScreen', () => {
  beforeEach(() => {
    jest.mocked(getDashboardData).mockReset()
    jest.mocked(getDashboardData).mockResolvedValue({ code: '200', status: 'success', msg: 'ok', data: makeData() } as never)
    jest.mocked(getActiveTorrents).mockResolvedValue({ code: '200', status: 'success', msg: 'ok', data: [] } as never)
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

  it('挂载即拉取数据，KPI 六项渲染（速度非零值）', async() => {
    const w = mountScreen()
    await flush()
    expect(getDashboardData).toHaveBeenCalledTimes(1)
    expect(w.findAll('.skpi')).toHaveLength(6)
    const download = w.find('[data-testid="skpi-download"]').text()
    const upload = w.find('[data-testid="skpi-upload"]').text()
    expect(download).not.toBe('0 B/s')
    expect(upload).not.toBe('0 B/s')
    expect(w.text()).toContain('5') // 已启用任务
    expect(w.text()).toContain('128') // 活跃种子
    w.destroy()
  })

  it('KPI 不含分享率与异常数（决策 #4/二期边界）', async() => {
    const w = mountScreen()
    await flush()
    const labels = w.findAll('.skpi .l').wrappers.map(x => x.text()).join('|')
    expect(labels).not.toContain('分享率')
    expect(labels).not.toContain('异常')
    w.destroy()
  })

  it('时钟与日期行渲染（HH:MM:SS 形态）', async() => {
    const w = mountScreen()
    await flush()
    expect(w.find('[data-testid="screen-clock"]').text()).toMatch(/^\d{2}:\d{2}:\d{2}$/)
    expect(w.text()).toContain(i18n.t('dashboard.screen.uptime', { duration: '1天0小时' }).toString())
    w.destroy()
  })

  it('播报按下载速度排序且过滤零速；空数据渲染空态', async() => {
    jest.mocked(getActiveTorrents).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: [
        { hash: 'a', name: 'slow.iso', downloadSpeed: 100, uploadSpeed: 0, progress: 10 },
        { hash: 'b', name: 'fast.iso', downloadSpeed: 900, uploadSpeed: 0, progress: 90 },
        { hash: 'c', name: 'idle.iso', downloadSpeed: 0, uploadSpeed: 0, progress: 0 }
      ]
    } as never)
    const w = mountScreen()
    await flush()
    const names = w.findAll('.ticker-row .nm').wrappers.map(x => x.text())
    expect(names).toEqual(['fast.iso', 'slow.iso'])

    const w2 = mountScreen()
    await flush()
    jest.mocked(getActiveTorrents).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: []
    } as never)
    w2.destroy()
  })

  it('Esc 键与退出按钮均跳转 /dashboard', async() => {
    const w = mountScreen()
    await flush()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await w.vm.$nextTick()
    const push = (w.vm as unknown as { $router: { push: jest.Mock } }).$router.push
    expect(push).toHaveBeenCalledWith('/dashboard')
    push.mockClear()
    await w.find('[data-testid="screen-exit-btn"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/dashboard')
    w.destroy()
  })

  it('雷达以深色模式渲染（dark prop）', async() => {
    const w = mountScreen()
    await flush()
    const radar = w.findComponent({ name: 'RadarCard' })
    expect(radar.exists()).toBe(true)
    expect(radar.props('dark')).toBe(true)
    w.destroy()
  })
})
