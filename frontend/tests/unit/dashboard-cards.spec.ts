/**
 * 数据卡单测（仪表盘一期 W5）：实例健康 / 热门种子 / 定时任务 / 站点分布 /
 * 状态环形——数据渲染、空态、排序口径与决策 #4（无 ratio）防线。
 */
import { shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import InstanceHealthCard from '@/views/dashboard/components/InstanceHealthCard.vue'
import HotTorrentsCard from '@/views/dashboard/components/HotTorrentsCard.vue'
import CronTaskCard from '@/views/dashboard/components/CronTaskCard.vue'
import SiteBarsCard from '@/views/dashboard/components/SiteBarsCard.vue'
import StatusDonutCard from '@/views/dashboard/components/StatusDonutCard.vue'
import { DownloaderListItem } from '@/types/dashboard'
import { ActiveTorrentSpeed } from '@/api/torrents'
import { ScheduledTask } from '@/api/tasks'
import { StatusBuckets } from '@/types/dashboard'

const mockT = (k: string, params?: Record<string, unknown>) =>
  params && 'count' in params ? `${k}(${params.count})` : k

function mountCard(C: typeof Vue, propsData: Record<string, unknown>): Wrapper<Vue> {
  return shallowMount((C as unknown) as typeof Vue, { propsData, mocks: { $t: mockT } })
}

describe('InstanceHealthCard 实例健康', () => {
  const dl = (over: Partial<DownloaderListItem>): DownloaderListItem =>
    ({
      downloader_id: 'd1',
      nickname: 'qb-main',
      downloader_type: 0,
      status: 'online',
      downloading: 2,
      seeding: 80,
      paused: 0,
      download_speed: 1024,
      upload_speed: 512,
      ...over
    } as DownloaderListItem)

  it('渲染昵称/在线 pill/速度/下载做种计数', () => {
    const w = mountCard(InstanceHealthCard, { list: [dl({})] })
    expect(w.text()).toContain('qb-main')
    expect(w.find('.dash-status-pill').classes()).toContain('st-online')
    expect(w.text()).toContain('1.00 KB/s')
    expect(w.text()).toContain('dashboard.widgets.health.dlCount(2)')
  })

  it('健康环推导（决策 #4 无 ratio）：在线有速度 success / 在线零速 warning / 离线灰', () => {
    const w = mountCard(InstanceHealthCard, {
      list: [dl({}), dl({ downloader_id: 'd2', nickname: 'zero', download_speed: 0, upload_speed: 0 }), dl({ downloader_id: 'd3', nickname: 'off', status: 'offline' })]
    })
    const strokes = w.findAll('circle[stroke-dasharray]').wrappers.map(c => c.attributes('stroke'))
    expect(strokes[0]).toContain('--color-success')
    expect(strokes[1]).toContain('--color-warning')
    expect(strokes[2]).toContain('--color-text-quaternary')
  })

  it('空列表显示空态', () => {
    const w = mountCard(InstanceHealthCard, { list: [] })
    expect(w.find('.dash-empty').exists()).toBe(true)
  })
})

describe('HotTorrentsCard 热门种子', () => {
  const tor = (hash: string, dls: number, uls: number, name?: string): ActiveTorrentSpeed =>
    ({ hash, name, downloadSpeed: dls, uploadSpeed: uls, progress: 50, num_seeds: 0, num_leechs: 0 } as ActiveTorrentSpeed)

  it('按下载+上传之和排序 Top5', () => {
    const w = mountCard(HotTorrentsCard, {
      torrents: [
        tor('a', 100, 0, 'a.iso'),
        tor('b', 500, 500, 'b.iso'),
        tor('c', 200, 10, 'c.iso'),
        tor('d', 10, 0, 'd.iso'),
        tor('e', 60, 60, 'e.iso'),
        tor('f', 30, 30, 'f.iso')
      ]
    })
    const names = w.findAll('.dash-tor-row .dash-ellip').wrappers.map(n => n.text())
    // b(1000) > c(210) > e(120) > a(100) > f(60)，d(10) 截断
    expect(names).toEqual(['b.iso', 'c.iso', 'e.iso', 'a.iso', 'f.iso'])
    expect(w.findAll('.dash-tor-rank')).toHaveLength(5)
  })

  it('name 缺失回退 hash 前缀', () => {
    const w = mountCard(HotTorrentsCard, { torrents: [tor('abcdef1234567890', 10, 0)] })
    expect(w.text()).toContain('abcdef123456')
  })

  it('空列表空态', () => {
    const w = mountCard(HotTorrentsCard, { torrents: [] })
    expect(w.find('.dash-empty').exists()).toBe(true)
  })
})

describe('CronTaskCard 定时任务', () => {
  const task = (id: number, enabled: boolean, name: string): ScheduledTask =>
    ({
      taskId: id,
      taskName: name,
      taskCode: `c${id}`,
      taskStatus: 0,
      taskType: 0,
      executor: 'echo',
      enabled,
      lastExecuteTime: null,
      lastExecuteDuration: null,
      cronPlan: '0 * * * *',
      taskStatusName: '',
      taskTypeName: '',
      createTime: '',
      updateTime: ''
    } as unknown as ScheduledTask)

  it('启用优先排序并截断 6 行，余量渲染 more 行', () => {
    const tasks = [
      ...Array.from({ length: 4 }, (_, i) => task(i + 1, false, `off-${i}`)),
      ...Array.from({ length: 5 }, (_, i) => task(10 + i, true, `on-${i}`))
    ]
    const w = mountCard(CronTaskCard, { tasks })
    const rows = w.findAll('.dash-rowline')
    expect(rows).toHaveLength(6)
    // 前 5 行启用在前
    for (let i = 0; i < 5; i += 1) {
      expect(rows.at(i).find('.dash-status-pill').classes()).toContain('st-online')
    }
    expect(w.text()).toContain('dashboard.widgets.tasks.more(3)')
  })

  it('空列表空态', () => {
    const w = mountCard(CronTaskCard, { tasks: [] })
    expect(w.find('.dash-empty').exists()).toBe(true)
  })
})

describe('SiteBarsCard 站点分布', () => {
  it('EChart option：host 降序类目轴 + other 显示名 + 每行计数 label', () => {
    const w = mountCard(SiteBarsCard, {
      buckets: [
        { host: 'a.example.com', count: 100 },
        { host: 'b.example.com', count: 50 },
        { host: 'other', count: 10 }
      ]
    })
    const echart = w.find('[data-testid="site-bars"]')
    expect(echart.exists()).toBe(true)
    const option = (echart.props('option') || {}) as {
      xAxis: unknown
      yAxis: { data: string[] }
      series: Array<{ data: Array<{ value: number, label?: { formatter?: () => string } }> }>
    }
    // inverse 类目轴：数组顺序即展示顺序（已按后端降序传入）
    expect(option.yAxis.data).toEqual(['a.example.com', 'b.example.com', 'dashboard.widgets.sites.other'])
    expect(option.series[0].data.map(d => d.value)).toEqual([100, 50, 10])
    expect(option.series[0].data[2].label?.formatter?.()).toBe('10')
  })

  it('空列表空态（不渲染 EChart 容器）', () => {
    const w = mountCard(SiteBarsCard, { buckets: [] })
    expect(w.find('.dash-empty').exists()).toBe(true)
    expect(w.find('[data-testid="site-bars"]').exists()).toBe(false)
  })
})

describe('StatusDonutCard 状态分布', () => {
  const zero: StatusBuckets = { error: 0, downloading: 0, seeding: 0, paused: 0, other: 0 }

  it('渲染中心总数与五桶图例计数', () => {
    const w = mountCard(StatusDonutCard, {
      buckets: { ...zero, seeding: 100, downloading: 20, error: 5 }
    })
    expect(w.find('.donut-total').text()).toBe('125')
    const legend = w.findAll('.dash-legend .item')
    expect(legend).toHaveLength(5)
    expect(legend.at(0).text()).toContain('dashboard.widgets.statusPie.seeding 100')
    expect(legend.at(3).text()).toContain('dashboard.widgets.statusPie.error 5')
  })

  it('全零桶：图例仍渲染五项（图表 option 由 EChart 空态承载）', () => {
    const w = mountCard(StatusDonutCard, { buckets: zero })
    expect(w.find('.donut-total').text()).toBe('0')
    expect(w.findAll('.dash-legend .item')).toHaveLength(5)
  })
})
