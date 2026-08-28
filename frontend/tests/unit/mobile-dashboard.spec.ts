/**
 * 移动仪表盘契约（Phase 4 M1）：卡片化展示 /dashboard 数据 + 下拉刷新。
 * 锁定字段映射（torrents/downloaders/system/downloader_list，曾误用
 * torrent_stats/downloader_stats/system_stats 导致全 0）、bytes/s 速度换算、
 * 已暂停统计贯通与下载器卡片穿透 /m/downloader。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileDashboard from '@/views/mobile/dashboard.vue'
import { getDashboardData } from '@/api/dashboard'
import { DashboardData } from '@/types/dashboard'

jest.mock('@/api/dashboard', () => ({
  getDashboardData: jest.fn()
}))

// paused 取 3 用于验证渲染契约（读到字段即显示）；真实后端该值恒为 0
// （dashboard_stats 任务暂不统计 paused，后端已知限制）
const makeData = (): DashboardData => ({
  downloaders: { total: 4, online: 3, offline: 1 },
  torrents: { active: 105, downloading: 2, seeding: 100, paused: 3 },
  tasks: { total: 5, running: 1, stopped: 4 },
  system: {
    uptime: 905,
    uptime_display: '15分钟',
    version: '1.0.6',
    total_download_speed: 0,
    total_upload_speed: 286720
  },
  downloader_list: [
    {
      downloader_id: 'd1',
      nickname: 'qb-main',
      downloader_type: 0,
      status: 'online',
      downloading: 2,
      seeding: 80,
      paused: 6,
      download_speed: 0,
      upload_speed: 1024
    },
    {
      downloader_id: 'd2',
      nickname: 'tr-batch',
      downloader_type: 1,
      status: 'offline',
      downloading: 0,
      seeding: 20,
      paused: 1,
      download_speed: 0,
      upload_speed: 0
    }
  ],
  activities: []
})

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileDashboard, {
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
      $router: { push: jest.fn(), replace: jest.fn().mockResolvedValue(undefined) }
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileDashboard', () => {
  beforeEach(() => {
    jest.mocked(getDashboardData).mockReset()
    jest.mocked(getDashboardData).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: makeData()
    } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('挂载即拉取并按正确字段渲染统计卡片（曾误读 torrent_stats/downloader_stats 全 0）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(getDashboardData).toHaveBeenCalledTimes(1)
    const cards = wrapper.findAll('.m-card-value')
    expect(cards.length).toBe(4)
    expect(cards.at(0).text()).toBe('2')
    expect(cards.at(1).text()).toBe('100')
    expect(cards.at(2).text()).toBe('3')
    expect(cards.at(3).text()).toBe('3/4')
  })

  it('速度按 bytes/s 换算：286720 B/s 显示 280.00 KB/s，0 显示 0 B/s（曾把 bytes/s 当 KB/s 错 1024 倍）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('280.00 KB/s')
    expect(wrapper.text()).toContain('0 B/s')
    expect(wrapper.text()).not.toContain('280.00 MB/s')
  })

  it('下载器卡片渲染 downloader_list（曾误用 downloaders 统计对象致区块永不渲染）：徽标/类型/计数/速度/离线态与页脚元信息', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const cards = wrapper.findAll('.m-dl-card')
    expect(cards.length).toBe(2)
    expect(cards.at(0).text()).toContain('qb-main')
    expect(cards.at(0).text()).toContain('qBittorrent')
    expect(cards.at(0).text()).toContain('80')
    expect(cards.at(0).text()).toContain('6')
    expect(cards.at(0).text()).toContain('1.00 KB/s')
    expect(cards.at(0).find('.m-dl-badge.online').exists()).toBe(true)
    expect(cards.at(1).text()).toContain('tr-batch')
    expect(cards.at(1).text()).toContain('Transmission')
    expect(cards.at(1).text()).toContain('离线')
    expect(cards.at(1).find('.m-dl-badge.offline').exists()).toBe(true)
    expect(wrapper.text()).toContain('v1.0.6')
    expect(wrapper.text()).toContain('15分钟')
  })

  it('穿透：点击下载器卡片（或键盘 Enter）进入 /m/downloader', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    await wrapper.findAll('.m-dl-card').at(0).trigger('click')
    const vm = wrapper.vm as any
    expect(vm.$router.push).toHaveBeenCalledWith('/m/downloader')
    await wrapper.findAll('.m-dl-card').at(1).trigger('keypress.enter')
    expect(vm.$router.push).toHaveBeenCalledTimes(2)
  })

  it('下载器卡片统计结构精确锁定：在线卡五列值（下载中/做种/暂停/双向速度）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const values = wrapper.findAll('.m-dl-card').at(0).findAll('.m-dl-stat-value')
    expect(values.length).toBe(5)
    expect(values.at(0).text()).toBe('2')
    expect(values.at(1).text()).toBe('80')
    expect(values.at(2).text()).toBe('6')
    expect(values.at(3).text()).toBe('↓0 B/s')
    expect(values.at(4).text()).toBe('↑1.00 KB/s')
  })

  it('离线下载器卡：速度列替换为"离线"占位，不渲染速度文本', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const offlineCard = wrapper.findAll('.m-dl-card').at(1)
    expect(offlineCard.text()).toContain('离线')
    expect(offlineCard.text()).not.toContain('B/s')
  })

  it('源码契约：不再引用 torrent_stats/downloader_stats/system_stats 错误字段', () => {
    const source = require('fs').readFileSync(require('path').resolve(__dirname, '../../src/views/mobile/dashboard.vue'), 'utf-8')
    expect(source).not.toContain('torrent_stats')
    expect(source).not.toContain('downloader_stats')
    expect(source).not.toContain('system_stats')
    // vue-jest 用 buble 转译模板 render，不认 ?. / ??（M3 已踩坑），兜底须收敛到 computed
    const templateBlock = source.slice(source.indexOf('<template>'), source.lastIndexOf('</template>'))
    expect(templateBlock).not.toContain('?.')
    expect(templateBlock).not.toContain('??')
  })

  it('接口失败时提示错误并停留在空态', async() => {
    jest.mocked(getDashboardData).mockRejectedValue(new Error('boom') as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.$message.error).toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无数据')
    wrapper.destroy()
  })

  it('旧错误契约负例：响应只含 torrent_stats/downloader_stats/system_stats 旧键时必须显示 0，不得误读（原始 bug 直接锁死）', async() => {
    jest.mocked(getDashboardData).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: {
        torrent_stats: { active: 9, downloading: 9, seeding: 9, paused: 9 },
        downloader_stats: { total: 9, online: 9, offline: 0 },
        system_stats: {
          uptime: 1,
          uptime_display: '1分钟',
          version: '9.9.9',
          total_download_speed: 999,
          total_upload_speed: 999
        },
        downloader_list: []
      }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const cards = wrapper.findAll('.m-card-value')
    expect(cards.at(0).text()).toBe('0')
    expect(cards.at(1).text()).toBe('0')
    expect(cards.at(2).text()).toBe('0')
    expect(cards.at(3).text()).toBe('0/0')
    expect(wrapper.text()).toContain('0 B/s')
    expect(wrapper.text()).not.toContain('9.9.9')
    expect(wrapper.text()).not.toContain('9/9')
  })

  it('信封契约：code 非 200 或 data 缺失时停留空态，不渲染 0 假数据也不误报错误', async() => {
    jest.mocked(getDashboardData).mockResolvedValue({
      code: '500',
      status: 'error',
      msg: '获取失败',
      data: null
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('暂无数据')
    const vm = wrapper.vm as any
    expect(vm.$message.error).not.toHaveBeenCalled()
    expect(vm.data).toBeNull()

    jest.mocked(getDashboardData).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: null
    } as never)
    await vm.load()
    await flushLifecycle()
    expect(wrapper.text()).toContain('暂无数据')
    expect(vm.data).toBeNull()
  })

  it('刷新链路：下拉刷新 onPullRefresh 重新拉取并渲染新值（silent 不置 loading）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(getDashboardData).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.m-refresh').exists()).toBe(false)

    const updated = makeData()
    updated.system.total_upload_speed = 1572864
    jest.mocked(getDashboardData).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: updated
    } as never)
    const vm = wrapper.vm as any
    await vm.onPullRefresh()
    await flushLifecycle()
    expect(getDashboardData).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('1.50 MB/s')
    expect(wrapper.text()).not.toContain('280.00 KB/s')
    // 下拉刷新走 silent：不整页切换到"加载中…"占位
    expect(vm.loading).toBe(false)
  })

  it('15s 自动刷新静默：loadActiveSpeed 不置 loading 且重新拉取', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.loadActiveSpeed()
    await flushLifecycle()
    expect(getDashboardData).toHaveBeenCalledTimes(2)
    expect(vm.loading).toBe(false)
  })

  it('下载器空列表：显示"去添加下载器"CTA，点击直达 /m/downloader?create=1', async() => {
    const empty = makeData()
    empty.downloader_list = []
    empty.downloaders = { total: 0, online: 0, offline: 0 }
    jest.mocked(getDashboardData).mockResolvedValue({
      code: '200',
      status: 'success',
      msg: 'ok',
      data: empty
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('还没有下载器')
    expect(wrapper.text()).toContain('去添加下载器')
    const vm = wrapper.vm as any
    vm.goAddDownloader()
    expect(wrapper.vm.$router.replace).toHaveBeenCalledWith({ path: '/m/downloader', query: { create: '1' } })
  })

  it('formatSpeedDisplay 方法契约（bytes/s 语义）：缺失 -- / 0→0 B/s / KB 与 MB 换算', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.formatSpeedDisplay(null)).toBe('--')
    expect(vm.formatSpeedDisplay(undefined)).toBe('--')
    expect(vm.formatSpeedDisplay(0)).toBe('0 B/s')
    expect(vm.formatSpeedDisplay(1024)).toBe('1.00 KB/s')
    expect(vm.formatSpeedDisplay(286720)).toBe('280.00 KB/s')
    expect(vm.formatSpeedDisplay(1572864)).toBe('1.50 MB/s')
  })

  it('data 为空时 computed 兜底：downloaderList 空数组、统计归零、system 显示占位', async() => {
    jest.mocked(getDashboardData).mockResolvedValue({
      code: '500',
      status: 'error',
      msg: 'x',
      data: null
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.downloaderList).toEqual([])
    expect(vm.torrentStats).toEqual({ active: 0, downloading: 0, seeding: 0, paused: 0 })
    expect(vm.downloaderStats).toEqual({ total: 0, online: 0, offline: 0 })
    expect(vm.systemStats.version).toBe('-')
    expect(vm.systemStats.uptime_display).toBe('-')
  })
})
