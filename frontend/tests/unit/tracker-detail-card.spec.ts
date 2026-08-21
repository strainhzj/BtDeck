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
      'el-button': ButtonStub
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
