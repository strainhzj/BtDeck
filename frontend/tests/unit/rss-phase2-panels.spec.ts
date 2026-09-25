/* eslint-disable @typescript-eslint/no-explicit-any */
// RSS Phase 2 组件回归（feature rss-subscription-phase2-2026-09-24）：
// 模式切换壳（qB 显示双模式/TR 隐藏）+ 引擎规则面板 + qB 原生面板。
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import Vue from 'vue'
import VueI18n from 'vue-i18n'
import i18n from '@/i18n'
import LucideIcon from '@/components/common/LucideIcon.vue'

import RssSubscriptionTab from '@/views/downloader/components/RssSubscriptionTab.vue'
import RssRulesPanel from '@/views/downloader/components/RssRulesPanel.vue'
import RssQbNativePanel from '@/views/downloader/components/RssQbNativePanel.vue'
import {
  getRssFeeds,
  getRssMode,
  updateRssMode,
  getRssRules,
  createRssRule,
  updateRssRule,
  deleteRssRule,
  previewRssRule,
  getQbRssFeeds,
  getQbRssRules,
  getQbRssPreferences,
  getQbRssArticles,
  markQbRssRead,
  RssFeed,
  RssRule,
  RssQbNode
} from '@/api/rss'
import { getList } from '@/api/downloader'
import { Downloader } from '@/views/downloader/types'

jest.mock('@/api/rss', () => ({
  getRssFeeds: jest.fn(),
  createRssFeed: jest.fn(),
  updateRssFeed: jest.fn(),
  deleteRssFeed: jest.fn(),
  refreshRssFeed: jest.fn(),
  getRssArticles: jest.fn(),
  addRssArticle: jest.fn(),
  getRssMode: jest.fn(),
  updateRssMode: jest.fn(),
  getRssRules: jest.fn(),
  createRssRule: jest.fn(),
  updateRssRule: jest.fn(),
  deleteRssRule: jest.fn(),
  previewRssRule: jest.fn(),
  getQbRssFeeds: jest.fn(),
  addQbRssFeed: jest.fn(),
  addQbRssFolder: jest.fn(),
  updateQbRssFeedUrl: jest.fn(),
  deleteQbRssItem: jest.fn(),
  moveQbRssItem: jest.fn(),
  refreshQbRssItem: jest.fn(),
  markQbRssRead: jest.fn(),
  getQbRssArticles: jest.fn(),
  getQbRssRules: jest.fn(),
  setQbRssRule: jest.fn(),
  renameQbRssRule: jest.fn(),
  deleteQbRssRule: jest.fn(),
  getQbRssMatching: jest.fn(),
  getQbRssPreferences: jest.fn(),
  updateQbRssPreferences: jest.fn()
}))

jest.mock('@/api/downloader', () => ({
  getList: jest.fn().mockResolvedValue({ data: [] })
}))

const mockGetMode = getRssMode as jest.MockedFunction<typeof getRssMode>
const mockUpdateMode = updateRssMode as jest.MockedFunction<typeof updateRssMode>
const mockListFeeds = getRssFeeds as jest.MockedFunction<typeof getRssFeeds>
const mockListRules = getRssRules as jest.MockedFunction<typeof getRssRules>
const mockCreateRule = createRssRule as jest.MockedFunction<typeof createRssRule>
const mockUpdateRule = updateRssRule as jest.MockedFunction<typeof updateRssRule>
const mockDeleteRule = deleteRssRule as jest.MockedFunction<typeof deleteRssRule>
const mockPreview = previewRssRule as jest.MockedFunction<typeof previewRssRule>
const mockQbFeeds = getQbRssFeeds as jest.MockedFunction<typeof getQbRssFeeds>
const mockQbRules = getQbRssRules as jest.MockedFunction<typeof getQbRssRules>
const mockQbPrefs = getQbRssPreferences as jest.MockedFunction<typeof getQbRssPreferences>
const mockQbArticles = getQbRssArticles as jest.MockedFunction<typeof getQbRssArticles>
const mockQbMarkRead = markQbRssRead as jest.MockedFunction<typeof markQbRssRead>
const mockGetList = getList as jest.MockedFunction<typeof getList>

const localVue = createLocalVue()
localVue.use(ElementUI)
localVue.use(VueI18n)
localVue.component('LucideIcon', LucideIcon)

const envelope = <T>(data: T) => ({ status: 'success', msg: 'ok', code: '200', data })
const pageOf = <T>(list: T[]) => ({ list, total: list.length, pageSize: 20 })

const QB_DOWNLOADER: Downloader = {
  downloaderId: 'dl-qb',
  nickname: 'qB 节点',
  host: '10.0.0.1',
  port: '8080',
  downloaderType: 0
}

const TR_DOWNLOADER: Downloader = { ...QB_DOWNLOADER, downloaderId: 'dl-tr', nickname: 'TR 节点', downloaderType: 1 }

const FEEDS: RssFeed[] = [
  {
    feedId: 'feed-1',
    downloaderId: 'dl-qb',
    name: '每日推送',
    url: 'https://rss.example.invalid/feed.xml',
    enabled: true,
    lastFetchAt: null,
    lastFetchStatus: 'ok',
    lastError: null,
    createdAt: null,
    pendingCount: 0,
    refreshIntervalMinutes: null
  }
]

const RULE: RssRule = {
  ruleId: 'rule-1',
  downloaderId: 'dl-qb',
  name: '剧集 1080p',
  enabled: true,
  includeKeywords: 'Show,1080p',
  excludeKeywords: 'Repack',
  useRegex: false,
  targetDownloaderId: null,
  savePath: '/tv',
  tags: 'rss',
  feedIds: [],
  matchCount: 3,
  lastMatchedAt: null,
  createdAt: null
}

const QB_TREE: RssQbNode[] = [
  {
    type: 'folder',
    name: '剧集',
    path: '剧集',
    children: [
      { type: 'feed', name: '周一组', path: '剧集\\周一组', articleCount: 2, unreadCount: 1 }
    ]
  },
  { type: 'feed', name: 'Weekly', path: 'Weekly', articleCount: 1, unreadCount: 1 }
]

interface TabVm extends Vue {
  mode: string
  qbNativeAvailable: boolean
  loadMode: () => Promise<void>
  handleSwitchMode: (value: string | number | boolean | undefined) => void
  isEngineMode: boolean
}

interface RulesVm extends Vue {
  rules: RssRule[]
  dialogVisible: boolean
  loadRules: () => Promise<void>
  openCreateDialog: () => void
  openEditDialog: (rule: RssRule) => void
  handleSubmit: () => Promise<void>
  handleToggleEnabled: (rule: RssRule, value: boolean) => Promise<void>
  openPreview: (rule: RssRule) => Promise<void>
  previewArticles: { articleId: string, feedName: string | null }[]
}

interface QbVm extends Vue {
  treeData: RssQbNode[]
  rules: { name: string }[]
  loadAll: () => void
  openArticles: (node: RssQbNode) => void
  articles: { articleId: string, isRead: boolean }[]
  onlyUnread: boolean
  loadArticles: () => Promise<void>
}

const flushPromises = async(): Promise<void> => {
  await new Promise(resolve => setTimeout(resolve, 0))
  await Vue.nextTick()
}

beforeEach(() => {
  jest.clearAllMocks()
  mockGetMode.mockResolvedValue(envelope({ mode: 'btdeck', qbNativeAvailable: true }) as any)
  mockListFeeds.mockResolvedValue(envelope(pageOf(FEEDS)) as any)
  mockListRules.mockResolvedValue(envelope(pageOf([RULE])) as any)
  mockQbFeeds.mockResolvedValue(envelope({ list: QB_TREE }) as any)
  mockQbRules.mockResolvedValue(
    envelope({
      list: [{ name: '剧集自动下载', enabled: true, mustContain: 'Drama', affectedFeeds: ['剧集\\周一组'] }],
      total: 1
    }) as any
  )
  mockQbPrefs.mockResolvedValue(
    envelope({
      preferences: {
        rssProcessingEnabled: true,
        rssAutoDownloadingEnabled: false,
        rssRefreshInterval: 30,
        rssMaxArticlesPerFeed: 50
      }
    }) as any
  )
  mockGetList.mockResolvedValue({ data: [] } as any)
})

// ==============================================================================
// 模式壳（RssSubscriptionTab）
// ==============================================================================

describe('RssSubscriptionTab Phase 2 模式壳', () => {
  const mountTab = (downloader: Downloader): Wrapper<TabVm> =>
    mount(RssSubscriptionTab, {
      localVue,
      i18n,
      propsData: { downloader },
      stubs: { 'el-drawer': { template: '<div><slot /></div>' }, transition: false }
    }) as Wrapper<TabVm>

  it('qB 下载器显示模式选择区并加载模式', async() => {
    const wrapper = mountTab(QB_DOWNLOADER)
    await flushPromises()
    expect(mockGetMode).toHaveBeenCalledWith('dl-qb')
    expect(wrapper.find('.mode-section').exists()).toBe(true)
    expect((wrapper.vm as TabVm).mode).toBe('btdeck')
    wrapper.destroy()
  })

  it('TR 下载器不显示模式选择区（恒引擎模式）', async() => {
    mockGetMode.mockClear()
    const wrapper = mountTab(TR_DOWNLOADER)
    await flushPromises()
    expect(wrapper.find('.mode-section').exists()).toBe(false)
    expect(mockGetMode).not.toHaveBeenCalled()
    expect((wrapper.vm as TabVm).isEngineMode).toBe(true)
    wrapper.destroy()
  })

  it('qb_native 模式下渲染 qB 原生面板并隐藏引擎区', async() => {
    mockGetMode.mockResolvedValue(envelope({ mode: 'qb_native', qbNativeAvailable: true }) as any)
    const wrapper = mountTab(QB_DOWNLOADER)
    await flushPromises()
    expect(wrapper.findComponent(RssQbNativePanel).exists()).toBe(true)
    expect(wrapper.findComponent(RssRulesPanel).exists()).toBe(false)
    expect(wrapper.find('.feed-table').exists()).toBe(false)
    wrapper.destroy()
  })

  it('btdeck 模式下渲染引擎区与规则面板', async() => {
    const wrapper = mountTab(QB_DOWNLOADER)
    await flushPromises()
    expect(wrapper.findComponent(RssQbNativePanel).exists()).toBe(false)
    expect(wrapper.findComponent(RssRulesPanel).exists()).toBe(true)
    expect(wrapper.find('.feed-table').exists()).toBe(true)
    wrapper.destroy()
  })

  it('切换模式走确认弹窗并调用 updateRssMode', async() => {
    const wrapper = mountTab(QB_DOWNLOADER)
    await flushPromises()
    mockUpdateMode.mockResolvedValue(envelope({ mode: 'qb_native', frozenHint: true }) as any)
    const vm = wrapper.vm as TabVm
    const messageBoxConfirm = jest.spyOn((ElementUI as any).MessageBox, 'confirm').mockResolvedValue('confirm' as any)
    vm.handleSwitchMode('qb_native')
    await flushPromises()
    expect(mockUpdateMode).toHaveBeenCalledWith('dl-qb', 'qb_native')
    expect(vm.mode).toBe('qb_native')
    messageBoxConfirm.mockRestore()
    wrapper.destroy()
  })
})

// ==============================================================================
// 引擎规则面板（RssRulesPanel）
// ==============================================================================

describe('RssRulesPanel', () => {
  const mountPanel = (): Wrapper<RulesVm> =>
    mount(RssRulesPanel, {
      localVue,
      i18n,
      propsData: { downloader: QB_DOWNLOADER },
      stubs: { 'el-drawer': { template: '<div><slot /></div>' }, transition: false }
    }) as Wrapper<RulesVm>

  it('加载并渲染规则表格（关键词标签/作用域/累计推送）', async() => {
    const wrapper = mountPanel()
    await flushPromises()
    expect(mockListRules).toHaveBeenCalledWith({ downloaderId: 'dl-qb', page: 1, pageSize: 20 })
    expect(wrapper.text()).toContain('剧集 1080p')
    expect(wrapper.text()).toContain('1080p')
    expect((wrapper.vm as RulesVm).rules).toHaveLength(1)
    wrapper.destroy()
  })

  it('创建规则：弹窗表单 → createRssRule 载荷含回填计数提示', async() => {
    mockCreateRule.mockResolvedValue(
      envelope({ rule: RULE, backfill: { matched: 2, pushed: 2, failed: 0, skippedMode: 0 } }) as any
    )
    const wrapper = mountPanel()
    await flushPromises()
    const vm = wrapper.vm as RulesVm
    vm.openCreateDialog()
    await Vue.nextTick()
    expect(vm.dialogVisible).toBe(true)
    ;(vm as any).form.name = '新规则'
    ;(vm as any).form.includeKeywords = 'Show,1080p'
    await vm.handleSubmit()
    await flushPromises()
    expect(mockCreateRule).toHaveBeenCalledWith(
      'dl-qb',
      expect.objectContaining({ name: '新规则', includeKeywords: 'Show,1080p', useRegex: false, feedIds: [] })
    )
    wrapper.destroy()
  })

  it('更新规则（编辑弹窗预填 + 显式 null 语义字段）', async() => {
    mockUpdateRule.mockResolvedValue(
      envelope({ rule: RULE, backfill: { matched: 0, pushed: 0, failed: 0, skippedMode: 0 } }) as any
    )
    const wrapper = mountPanel()
    await flushPromises()
    const vm = wrapper.vm as RulesVm
    vm.openEditDialog(RULE)
    await Vue.nextTick()
    await vm.handleSubmit()
    await flushPromises()
    expect(mockUpdateRule).toHaveBeenCalledWith(
      'rule-1',
      expect.objectContaining({ name: '剧集 1080p', excludeKeywords: 'Repack', targetDownloaderId: null })
    )
    wrapper.destroy()
  })

  it('启用开关走 updateRssRule({enabled})', async() => {
    mockUpdateRule.mockResolvedValue(
      envelope({ rule: { ...RULE, enabled: false }, backfill: { matched: 0, pushed: 0, failed: 0, skippedMode: 0 } }) as any
    )
    const wrapper = mountPanel()
    await flushPromises()
    const vm = wrapper.vm as RulesVm
    await vm.handleToggleEnabled(RULE, false)
    expect(mockUpdateRule).toHaveBeenCalledWith('rule-1', { enabled: false })
    wrapper.destroy()
  })

  it('匹配预览只读加载（previewRssRule，不改推送状态）', async() => {
    mockPreview.mockResolvedValue(
      envelope({
        list: [
          { articleId: 'a1', feedId: 'feed-1', title: 'Show.S01E02.1080p', link: 'magnet:?x', publishedAt: null, fetchedAt: null, status: 'pending', addedAt: null, addedDownloaderId: null, addedRuleId: null, feedName: '每日推送' }
        ],
        total: 1,
        pageSize: 50,
        truncated: false
      }) as any
    )
    const wrapper = mountPanel()
    await flushPromises()
    const vm = wrapper.vm as RulesVm
    await vm.openPreview(RULE)
    await flushPromises()
    expect(mockPreview).toHaveBeenCalledWith('rule-1')
    expect(vm.previewArticles).toHaveLength(1)
    expect(vm.previewArticles[0].feedName).toBe('每日推送')
    expect(mockCreateRule).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('删除规则走确认弹窗（取消不调接口）', async() => {
    const wrapper = mountPanel()
    await flushPromises()
    const confirmSpy = jest.spyOn((ElementUI as any).MessageBox, 'confirm').mockRejectedValue('cancel')
    ;(wrapper.vm as any).handleDeleteRule(RULE)
    await flushPromises()
    expect(mockDeleteRule).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
    wrapper.destroy()
  })
})

// ==============================================================================
// qB 原生面板（RssQbNativePanel）
// ==============================================================================

describe('RssQbNativePanel', () => {
  const mountQb = (): Wrapper<QbVm> =>
    mount(RssQbNativePanel, {
      localVue,
      i18n,
      propsData: { downloader: QB_DOWNLOADER },
      stubs: { 'el-drawer': { template: '<div><slot /></div>' }, transition: false }
    }) as Wrapper<QbVm>

  it('加载源树/规则/偏好三区块', async() => {
    const wrapper = mountQb()
    await flushPromises()
    expect(mockQbFeeds).toHaveBeenCalledWith('dl-qb')
    expect(mockQbRules).toHaveBeenCalledWith('dl-qb')
    expect(mockQbPrefs).toHaveBeenCalledWith('dl-qb')
    expect((wrapper.vm as QbVm).treeData).toEqual(QB_TREE)
    expect(wrapper.text()).toContain('剧集自动下载')
    wrapper.destroy()
  })

  it('文章抽屉：打开加载 qB 文章（onlyUnread 过滤）', async() => {
    mockQbArticles.mockResolvedValue(
      envelope({
        list: [{ articleId: 'qa1', title: 'Drama.S02E03', link: 'https://x/1.torrent', published: '2026-09-24 09:00:00', isRead: false }],
        total: 1,
        unreadCount: 1
      }) as any
    )
    const wrapper = mountQb()
    await flushPromises()
    const vm = wrapper.vm as QbVm
    const feedNode = (QB_TREE[0].children || [])[0]
    expect(feedNode).toBeTruthy()
    vm.openArticles(feedNode)
    await flushPromises()
    expect(mockQbArticles).toHaveBeenCalledWith('dl-qb', '剧集\\周一组', false)
    expect(vm.articles).toHaveLength(1)
    vm.onlyUnread = true
    await vm.loadArticles()
    expect(mockQbArticles).toHaveBeenLastCalledWith('dl-qb', '剧集\\周一组', true)
    wrapper.destroy()
  })

  it('单篇已读走 markQbRssRead(path, articleId)', async() => {
    mockQbMarkRead.mockResolvedValue(envelope({}) as any)
    const wrapper = mountQb()
    await flushPromises()
    const vm = wrapper.vm as QbVm
    const feedNode = (QB_TREE[0].children || [])[0]
    expect(feedNode).toBeTruthy()
    vm.openArticles(feedNode)
    await flushPromises()
    await (wrapper.vm as any).handleMarkRead(feedNode, 'qa1')
    expect(mockQbMarkRead).toHaveBeenCalledWith('dl-qb', '剧集\\周一组', 'qa1')
    wrapper.destroy()
  })
})
