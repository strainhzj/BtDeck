import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import type { TrackerInfo } from '@/api/torrents'
import TrackerDetailCard from '@/views/torrents/components/TrackerDetailCard.vue'

type TrackerRow = TrackerInfo & { reannouncing?: boolean }

const localVue = createLocalVue()

const AlertStub = localVue.extend({
  name: 'ElAlertStub',
  props: {
    title: String,
    description: String
  },
  template: `
    <div class="el-alert-stub">
      <span class="alert-title">{{ title }}</span>
      <span class="alert-description">{{ description }}</span>
    </div>
  `
})

const ButtonStub = localVue.extend({
  name: 'ElButtonStub',
  inheritAttrs: false,
  props: {
    loading: Boolean
  },
  template: '<button class="el-button-stub" v-bind="$attrs" :disabled="loading" v-on="$listeners"><slot /></button>'
})

interface CardOptions {
  visible?: boolean
  layout?: 'list' | 'traditional'
  activeTab?: 'tracker' | 'files' | 'peers'
  torrentName?: string
  filesState?: { list: any[], loading: boolean, error: string }
  peersState?: { list: any[], loading: boolean, error: string }
}

function mountCard(
  trackerInfo: TrackerRow[],
  errorReason = '',
  options: CardOptions = {}
): Wrapper<Vue> {
  return shallowMount(TrackerDetailCard, {
    localVue,
    propsData: {
      trackerInfo,
      errorReason,
      ...options
    },
    stubs: {
      'el-alert': AlertStub,
      'el-button': ButtonStub,
      'el-progress': true
    }
  })
}

describe('TrackerDetailCard shared view contract', () => {
  let wrapper: Wrapper<Vue>

  afterEach(() => {
    wrapper?.destroy()
  })

  it('统一渲染五列 Tracker 表格、错误提示和 snake/camel 字段', () => {
    const trackerInfo: TrackerRow[] = [
      {
        tracker_name: 'Tracker A',
        tracker_url: 'https://tracker-a.example/announce',
        last_announce_succeeded: '工作中',
        last_announce_msg: 'announce ok',
        last_scrape_succeeded: '工作失败'
      },
      {
        trackerName: 'Tracker B',
        trackerUrl: 'https://tracker-b.example/announce',
        lastAnnounceSucceeded: 'success',
        lastAnnounceMsg: 'camel announce ok',
        lastScrapeSucceeded: '未联系'
      }
    ]
    wrapper = mountCard(trackerInfo, '连接被远端拒绝', {
      visible: true,
      torrentName: '共享弹框种子'
    })

    expect(wrapper.find('.tracker-detail-card').classes()).toEqual(
      expect.arrayContaining(['tracker-detail-card--list', 'is-open'])
    )
    expect(wrapper.find('.tracker-detail-header').exists()).toBe(true)
    expect(wrapper.find('.tracker-title').text()).toContain('Tracker详情 - 共享弹框种子')
    expect(wrapper.find('.tracker-detail-tabs').text()).toContain('Tracker')
    expect(wrapper.find('.tracker-detail-tabs').text()).toContain('文件')
    expect(wrapper.find('.tracker-detail-tabs').text()).toContain('Peers')
    expect(wrapper.find('.tracker-close').exists()).toBe(true)

    expect(wrapper.findAll('thead th').wrappers.map(header => header.text().trim())).toEqual([
      'Tracker名称',
      'Announce',
      'Announce信息',
      'Scrape',
      '操作'
    ])
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)

    const firstRow = wrapper.findAll('tbody tr').at(0)
    expect(firstRow.find('td').text()).toContain('Tracker A')
    expect(firstRow.find('.tracker-url-mini').text()).toBe('https://tracker-a.example/announce')
    expect(firstRow.find('.tracker-status-working').text()).toContain('✓ 工作')
    expect(firstRow.find('.tracker-status-error').text()).toContain('✗ 工作失败')
    expect(firstRow.findAll('td').at(2).text()).toBe('announce ok')

    const secondRow = wrapper.findAll('tbody tr').at(1)
    expect(secondRow.find('.tracker-url-mini').text()).toBe('https://tracker-b.example/announce')
    expect(secondRow.find('.tracker-status-working').exists()).toBe(true)
    expect(secondRow.find('.tracker-status-neutral').exists()).toBe(true)
    expect(secondRow.findAll('td').at(2).text()).toBe('camel announce ok')

    expect(wrapper.find('.alert-title').text()).toBe('种子错误原因')
    expect(wrapper.find('.alert-description').text()).toBe('连接被远端拒绝')
  })

  it('汇报按钮透传当前 Tracker 和行号，并保留 loading 状态', async() => {
    const trackerInfo: TrackerRow[] = [
      { trackerName: '可汇报', reannouncing: false },
      { trackerName: '汇报中', reannouncing: true }
    ]
    wrapper = mountCard(trackerInfo)
    const buttons = wrapper.findAll('.el-button-stub')

    expect(buttons).toHaveLength(2)
    expect(buttons.at(1).attributes('disabled')).toBe('disabled')

    await buttons.at(0).trigger('click')

    expect(wrapper.emitted('reannounce')).toEqual([[trackerInfo[0], 0]])
    await wrapper.find('.tracker-close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('传统定位也渲染同一套标题、页签、内容区和 Tracker 表格', () => {
    wrapper = mountCard([], '', {
      visible: true,
      layout: 'traditional',
      torrentName: '传统模式种子'
    })

    expect(wrapper.find('.tracker-detail-card').classes()).toEqual(
      expect.arrayContaining(['tracker-detail-card--traditional', 'is-open'])
    )
    expect(wrapper.find('.tracker-detail-header').exists()).toBe(true)
    expect(wrapper.find('.tracker-title').text()).toContain('Tracker详情 - 传统模式种子')
    expect(wrapper.find('.tracker-close').exists()).toBe(true)
    expect(wrapper.findAll('.tracker-tab-btn')).toHaveLength(3)
    expect(wrapper.find('.tracker-detail-content').exists()).toBe(true)
    expect(wrapper.find('table.tracker-table-detail').exists()).toBe(true)
  })

  it('中性 Tracker 状态不被误标为错误，且无错误原因时不渲染告警', () => {
    wrapper = mountCard([
      {
        trackerName: '未联系 Tracker',
        lastAnnounceSucceeded: '未联系',
        lastScrapeSucceeded: '发送中'
      }
    ])

    expect(wrapper.find('.torrent-error-alert').exists()).toBe(false)
    expect(wrapper.findAll('.tracker-status-neutral')).toHaveLength(2)
    expect(wrapper.find('tbody tr').text()).toContain('✗ 未联系')
    expect(wrapper.find('tbody tr').text()).toContain('✗ 发送中')
  })

  it('tracker 域名筛选命中行高亮并显示"命中筛选"标签，未命中行不打标', () => {
    wrapper = mountCard([
      {
        tracker_name: '命中站',
        tracker_url: 'https://tracker.a.example/announce',
        matched_domain: 'tracker.a.example'
      },
      {
        trackerName: '其它站',
        trackerUrl: 'https://tracker.b.example/announce'
      },
      {
        trackerName: 'camel 命中站',
        trackerUrl: 'https://tracker.c.example/announce',
        matchedDomain: 'tracker.c.example'
      }
    ])

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(3)

    // snake_case 与 camelCase 的 matched 字段都识别
    expect(rows.at(0).classes()).toContain('tracker-row-matched')
    expect(rows.at(0).find('.tracker-matched-tag').exists()).toBe(true)
    expect(rows.at(0).find('.tracker-matched-tag').text()).toBe('命中筛选')

    expect(rows.at(2).classes()).toContain('tracker-row-matched')
    expect(rows.at(2).find('.tracker-matched-tag').text()).toBe('命中筛选')

    // 未命中行：无高亮类、无标签
    expect(rows.at(1).classes()).not.toContain('tracker-row-matched')
    expect(rows.at(1).find('.tracker-matched-tag').exists()).toBe(false)
  })

  it('展示对齐判定：Announce 文本被覆写为工作失败时显示红色失败标识与消息', () => {
    // 后端在消息命中失败关键词池时覆写 announce 文本（Transmission 200+failure
    // reason 场景），详情卡无需改动即应显示 ✗ 工作失败，而非 ✓ 工作
    wrapper = mountCard([
      {
        trackerName: '1ptba',
        trackerUrl: 'https://1ptba.com/announce',
        lastAnnounceSucceeded: '工作失败',
        lastAnnounceMsg: 'You cannot seed the same torrent in the same location from more than 1 client.',
        lastScrapeSucceeded: '工作中',
        lastScrapeMsg: ''
      }
    ])

    const announceCell = wrapper.findAll('tbody tr td').at(1)
    expect(announceCell.find('.tracker-status-error').exists()).toBe(true)
    expect(announceCell.text()).toContain('✗ 工作失败')
    expect(wrapper.findAll('tbody tr td').at(2).text()).toContain('more than 1 client')
    // scrape 列未命中失败语义，保持原文本
    expect(wrapper.findAll('tbody tr td').at(3).find('.tracker-status-working').exists()).toBe(true)
  })
})

describe('TrackerDetailCard 底部收起条（与关闭按钮等效）', () => {
  let wrapper: Wrapper<Vue>

  afterEach(() => {
    wrapper?.destroy()
  })

  it('收起条存在、占满一行且点击 emit close（与右上角关闭按钮同一事件）', async() => {
    wrapper = mountCard([], '', { visible: true, torrentName: '收起条种子' })

    const bar = wrapper.find('.tracker-collapse-bar')
    expect(bar.exists()).toBe(true)
    expect(bar.attributes('title')).toBe('收起详情')
    expect(bar.attributes('aria-label')).toBe('收起详情')

    await bar.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)

    // 与右上角关闭按钮发出同一 close 事件
    await wrapper.find('.tracker-close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)
  })
})

describe('TrackerDetailCard 文件页签', () => {
  let wrapper: Wrapper<Vue>

  afterEach(() => {
    wrapper?.destroy()
  })

  it('渲染三列文件表格：名称省略、大小格式化、进度百分比着色与计数', () => {
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'files',
      filesState: {
        list: [
          { name: 'dir/a.iso', size: 1024, progress: 0.5 },
          { name: 'dir/b.mkv', size: 0, progress: 1 }
        ],
        loading: false,
        error: ''
      }
    })

    expect(wrapper.findAll('thead th').wrappers.map(header => header.text().trim())).toEqual([
      '文件名',
      '大小',
      '进度'
    ])
    expect(wrapper.find('.tracker-detail-count').text()).toBe('共 2 个文件')

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows.at(0).text()).toContain('dir/a.iso')
    expect(rows.at(0).text()).toContain('1.00 KB')
    expect(rows.at(0).find('.tracker-progress-partial').text()).toBe('50%')
    expect(rows.at(1).find('.tracker-progress-done').text()).toBe('100%')
    // 大小为 0 显示 '-'（formatFileSize 契约）
    expect(rows.at(1).text()).toContain('-')
  })

  it('无数据三态：加载中/错误/空占位', () => {
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'files',
      filesState: { list: [], loading: true, error: '' }
    })
    expect(wrapper.find('.tracker-placeholder').text()).toBe('文件列表加载中...')
    wrapper.destroy()

    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'files',
      filesState: { list: [], loading: false, error: '下载器超时' }
    })
    expect(wrapper.find('.alert-title').text()).toBe('文件列表加载失败')
    expect(wrapper.find('.alert-description').text()).toBe('下载器超时')
    wrapper.destroy()

    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'files',
      filesState: { list: [], loading: false, error: '' }
    })
    expect(wrapper.find('.tracker-placeholder').text()).toBe('暂无文件数据')
  })

  it('有旧数据时更新失败显示非侵入提示，不覆盖上次数据', () => {
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'files',
      filesState: {
        list: [{ name: 'keep.bin', size: 8, progress: 0.1 }],
        loading: false,
        error: '连接重置'
      }
    })
    expect(wrapper.find('.tracker-stale-note').exists()).toBe(true)
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.findAll('tbody tr').at(0).text()).toContain('keep.bin')
  })

  it('超阈值截断渲染前 1000 行并显示总数提示', () => {
    const bigList = Array.from({ length: 1100 }, (_, i) => ({
      name: `f${i}.bin`,
      size: 1,
      progress: 0
    }))
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'files',
      filesState: { list: bigList, loading: false, error: '' }
    })
    expect(wrapper.findAll('tbody tr')).toHaveLength(1000)
    expect(wrapper.find('.tracker-truncate-note').text()).toBe('共 1100 个文件，仅显示前 1000 个')
  })

  it('刷新按钮 emit refresh 事件并携带当前页签', async() => {
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'files',
      filesState: {
        list: [{ name: 'a.bin', size: 1, progress: 0 }],
        loading: false,
        error: ''
      }
    })
    await wrapper.find('.el-button-stub').trigger('click')
    expect(wrapper.emitted('refresh')).toEqual([['files']])
  })
})

describe('TrackerDetailCard Peers 页签', () => {
  let wrapper: Wrapper<Vue>

  afterEach(() => {
    wrapper?.destroy()
  })

  it('渲染五列表格：地址/客户端/进度/双速度（0 速兜底 -）与轮询提示', () => {
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'peers',
      peersState: {
        list: [
          { ip: '1.2.3.4', port: 6881, client: 'qBittorrent 4.6', progress: 0.75, down_speed: 1024, up_speed: 0, flags: 'D', country: 'CN' },
          { ip: '5.6.7.8', port: 51413, client: '', progress: 0, down_speed: 0, up_speed: 2048, flags: '', country: '' }
        ],
        loading: false,
        error: ''
      }
    })

    expect(wrapper.findAll('thead th').wrappers.map(header => header.text().trim())).toEqual([
      '地址',
      '客户端',
      '进度',
      '↓速度',
      '↑速度'
    ])
    expect(wrapper.find('.tracker-detail-count').text()).toContain('共 2 个 Peers')

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows.at(0).text()).toContain('1.2.3.4:6881')
    expect(rows.at(0).text()).toContain('qBittorrent 4.6')
    expect(rows.at(0).find('.tracker-progress-partial').text()).toBe('75%')
    expect(rows.at(0).text()).toContain('1.00 KB/s')
    expect(rows.at(1).find('.tracker-cell-ellipsis').text()).toBe('5.6.7.8:51413')
    // 空 client 与 0 速兜底 '-'
    expect(rows.at(1).text()).toContain('-')
    expect(rows.at(1).find('.tracker-progress-zero').text()).toBe('0%')
  })

  it('无数据三态：加载中/错误/空占位', () => {
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'peers',
      peersState: { list: [], loading: true, error: '' }
    })
    expect(wrapper.find('.tracker-placeholder').text()).toBe('Peers 列表加载中...')
    wrapper.destroy()

    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'peers',
      peersState: { list: [], loading: false, error: '种子不存在或已被删除' }
    })
    expect(wrapper.find('.alert-title').text()).toBe('Peers 列表加载失败')
    expect(wrapper.find('.alert-description').text()).toBe('种子不存在或已被删除')
    wrapper.destroy()

    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'peers',
      peersState: { list: [], loading: false, error: '' }
    })
    expect(wrapper.find('.tracker-placeholder').text()).toBe('暂无 Peers 数据')
  })

  it('刷新按钮 emit refresh 事件并携带 peers 页签', async() => {
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'peers',
      peersState: {
        list: [
          { ip: '10.0.0.1', port: 80, client: 'x', progress: 0, down_speed: 0, up_speed: 0, flags: '', country: '' }
        ],
        loading: false,
        error: ''
      }
    })
    await wrapper.find('.el-button-stub').trigger('click')
    expect(wrapper.emitted('refresh')).toEqual([['peers']])
  })
})
