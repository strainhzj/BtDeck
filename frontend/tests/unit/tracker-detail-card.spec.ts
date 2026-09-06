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

const InputStub = localVue.extend({
  name: 'ElInputStub',
  props: {
    value: String
  },
  template: '<input class="el-input-stub" :value="value" @input="$emit(\'input\', $event.target.value)" />'
})

// 需要读取 percentage 的用例（clamp 契约）：布尔 stub 不保留 props 声明，须显式声明
const ProgressStub = localVue.extend({
  name: 'ElProgressStub',
  props: {
    percentage: Number
  },
  template: '<div class="el-progress-stub" :data-percentage="percentage" />'
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
      'el-progress': ProgressStub,
      'el-input': InputStub
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

describe('TrackerDetailCard 顶部收起条（与关闭按钮等效）', () => {
  let wrapper: Wrapper<Vue>

  afterEach(() => {
    wrapper?.destroy()
  })

  it('收起条存在、位于卡片最顶部且点击 emit close（与右上角关闭按钮同一事件）', async() => {
    wrapper = mountCard([], '', { visible: true, torrentName: '收起条种子' })

    const bar = wrapper.find('.tracker-collapse-bar')
    expect(bar.exists()).toBe(true)
    expect(bar.attributes('title')).toBe('收起详情')
    expect(bar.attributes('aria-label')).toBe('收起详情')
    // 收起条位于卡片最顶部（Tracker详情标题之上，而非底部）
    expect(bar.element).toBe(wrapper.find('.tracker-detail-card').element.firstElementChild)

    await bar.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)

    // 与右上角关闭按钮发出同一 close 事件
    await wrapper.find('.tracker-close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)
  })

  it('收起条箭头随布局取收起方向：list 向上折叠，traditional 向下折叠', () => {
    const iconNameAt = (w: Wrapper<Vue>): string | null =>
      w.find('.tracker-collapse-bar').element.querySelector('[name]')?.getAttribute('name') ?? null

    wrapper = mountCard([], '', { visible: true })
    expect(iconNameAt(wrapper)).toBe('chevron-up')

    wrapper.destroy()
    wrapper = mountCard([], '', { visible: true, layout: 'traditional' })
    expect(iconNameAt(wrapper)).toBe('chevron-down')
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

    const headers = wrapper.findAll('thead th').wrappers.map(header => header.text().trim())
    expect(headers).toHaveLength(3)
    expect(headers[0]).toContain('文件名')
    expect(headers[1]).toContain('大小')
    expect(headers[2]).toContain('进度')
    // 三列均为可排序按钮（未激活时中性指示符）
    expect(wrapper.findAll('.tracker-sort-btn')).toHaveLength(3)
    expect(wrapper.findAll('.tracker-sort-indicator').wrappers.map(i => i.text())).toEqual(['⇅', '⇅', '⇅'])
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

  it('进度换算 clamp：负值/超 1/非数值分别兜底 0/100/0（el-progress percentage 校验器强制 0~100）', () => {
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'files',
      filesState: {
        list: [
          { name: 'neg', size: 1, progress: -0.5 },
          { name: 'over', size: 1, progress: 1.5 },
          { name: 'bad', size: 1, progress: Number.NaN }
        ],
        loading: false,
        error: ''
      }
    })
    expect(wrapper.findAll('.tracker-progress-text').wrappers.map(item => item.text())).toEqual([
      '0%',
      '100%',
      '0%'
    ])
    expect(wrapper.findAll('.el-progress-stub').wrappers.map(bar => bar.attributes('data-percentage'))).toEqual(['0', '100', '0'])
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

describe('TrackerDetailCard 文件页签排序与搜索', () => {
  let wrapper: Wrapper<Vue>

  const SORT_FILES = [
    { name: 'dir/c.bin', size: 300, progress: 0.2 },
    { name: 'dir/a.iso', size: 100, progress: 0.8 },
    { name: 'readme.txt', size: 50, progress: 1 }
  ]

  const mountFiles = (list: any[] = SORT_FILES) => {
    wrapper = mountCard([], '', {
      visible: true,
      activeTab: 'files',
      filesState: { list, loading: false, error: '' }
    })
  }

  const rowNames = () => wrapper.findAll('tbody tr').wrappers.map(row => row.find('.tracker-cell-ellipsis').text())
  const sortButtons = () => wrapper.findAll('.tracker-sort-btn')

  afterEach(() => {
    wrapper?.destroy()
  })

  it('文件名列头排序循环：升序→降序→还原原始顺序，指示符与激活态联动', async() => {
    mountFiles()
    const nameBtn = sortButtons().at(0)

    await nameBtn.trigger('click')
    expect(rowNames()).toEqual(['dir/a.iso', 'dir/c.bin', 'readme.txt'])
    expect(nameBtn.classes()).toContain('active')
    expect(nameBtn.find('.tracker-sort-indicator').text()).toBe('↑')

    await nameBtn.trigger('click')
    expect(rowNames()).toEqual(['readme.txt', 'dir/c.bin', 'dir/a.iso'])
    expect(nameBtn.find('.tracker-sort-indicator').text()).toBe('↓')

    await nameBtn.trigger('click')
    expect(rowNames()).toEqual(['dir/c.bin', 'dir/a.iso', 'readme.txt'])
    expect(nameBtn.classes()).not.toContain('active')
    expect(nameBtn.find('.tracker-sort-indicator').text()).toBe('⇅')
  })

  it('大小与进度列排序（数值语义，非字符串比较）', async() => {
    mountFiles()

    await sortButtons().at(1).trigger('click')
    expect(rowNames()).toEqual(['readme.txt', 'dir/a.iso', 'dir/c.bin'])

    await sortButtons().at(1).trigger('click')
    expect(rowNames()).toEqual(['dir/c.bin', 'dir/a.iso', 'readme.txt'])

    // 进度降序：1 > 0.8 > 0.2（若按字符串比较 0.2 会排在 0.8 前）
    await sortButtons().at(2).trigger('click')
    await sortButtons().at(2).trigger('click')
    expect(rowNames()).toEqual(['readme.txt', 'dir/a.iso', 'dir/c.bin'])
  })

  it('搜索框模糊过滤文件名（大小写不敏感）并更新计数文本；清空恢复全量', async() => {
    mountFiles([{ name: 'DIR/A.ISO', size: 1, progress: 0 }, { name: 'b.mkv', size: 2, progress: 0 }])

    await wrapper.find('.el-input-stub').setValue('a.i')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(rowNames()).toEqual(['DIR/A.ISO'])
    expect(wrapper.find('.tracker-detail-count').text()).toBe('命中 1 / 2 个文件')

    await wrapper.find('.el-input-stub').setValue('')
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.find('.tracker-detail-count').text()).toBe('共 2 个文件')
  })

  it('搜索无命中时显示 no-match 占位并回显关键词；恢复命中后回到表格', async() => {
    mountFiles()

    await wrapper.find('.el-input-stub').setValue('zzz')
    expect(wrapper.find('.tracker-placeholder').text()).toBe('未找到匹配 "zzz" 的文件')
    expect(wrapper.find('table').exists()).toBe(false)

    await wrapper.find('.el-input-stub').setValue('readme')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.find('.tracker-placeholder').exists()).toBe(false)
  })

  it('筛选不禁用排序：搜索命中子集上排序仍生效', async() => {
    mountFiles()

    await wrapper.find('.el-input-stub').setValue('dir')
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(rowNames()).toEqual(['dir/c.bin', 'dir/a.iso'])

    await sortButtons().at(1).trigger('click')
    expect(rowNames()).toEqual(['dir/a.iso', 'dir/c.bin'])
  })

  it('截断提示随搜索命中数更新（命中 1100 个 → 仅显示前 1000）', async() => {
    const bigList = Array.from({ length: 1100 }, (_, i) => ({
      name: `x${i}.bin`,
      size: 1,
      progress: 0
    }))
    mountFiles(bigList)
    // 无搜索：全量截断提示
    expect(wrapper.find('.tracker-truncate-note').text()).toBe('共 1100 个文件，仅显示前 1000 个')

    await wrapper.find('.el-input-stub').setValue('x')
    expect(wrapper.find('.tracker-truncate-note').text()).toBe('命中 1100 个文件，仅显示前 1000 个')
    expect(wrapper.find('.tracker-detail-count').text()).toBe('命中 1100 / 1100 个文件')

    // 命中数降到阈值内则不再提示
    await wrapper.find('.el-input-stub').setValue('x1099')
    expect(wrapper.find('.tracker-truncate-note').exists()).toBe(false)
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
  })

  it('父级清空数据时复位搜索与排序（换种子不带陈旧视图态）', async() => {
    mountFiles()
    await wrapper.find('.el-input-stub').setValue('dir')
    await sortButtons().at(1).trigger('click')

    await wrapper.setProps({
      filesState: { list: [], loading: false, error: '' }
    })
    await wrapper.vm.$nextTick()

    // 新一批数据注入后：无搜索词（全部可见）、无激活排序
    await wrapper.setProps({
      filesState: {
        list: [{ name: 'new.txt', size: 9, progress: 1 }, { name: 'old.bin', size: 1, progress: 0 }],
        loading: false,
        error: ''
      }
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.tracker-detail-count').text()).toBe('共 2 个文件')
    expect(rowNames()).toEqual(['new.txt', 'old.bin'])
    expect(sortButtons().at(1).classes()).not.toContain('active')
  })
})
