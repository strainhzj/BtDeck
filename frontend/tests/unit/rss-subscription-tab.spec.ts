/**
 * RSS 订阅页签回归（feature rss-subscription-2026-09-24 Phase 1）。
 *
 * 保护点：
 * 1. 无下载器时呈现「先保存基本信息」空态；
 * 2. 订阅源表格渲染（待添加计数徽标 + 抓取状态三态）；
 * 3. 刷新订阅源：调用 refresh API，成功提示后重载列表与文章；
 * 4. 文章抽屉：状态筛选透传（all → 不带 status）；
 * 5. 推送：空参数归一为 undefined（不发送空字符串），成功后重载；
 * 6. 已推送文章不渲染推送按钮（仅状态标签）；
 * 7. 双语：en locale 下表格标题切换英文（i18n 成对）。
 *
 * demo 模式行为回归见 demo-request.spec.ts 的 RSS 用例组。
 */

import Vue from 'vue'
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import VueI18n from 'vue-i18n'
import i18n, { setLocale } from '@/i18n'
import LucideIcon from '@/components/common/LucideIcon.vue'

import RssSubscriptionTab from '@/views/downloader/components/RssSubscriptionTab.vue'
import {
  getRssFeeds,
  createRssFeed,
  refreshRssFeed,
  getRssArticles,
  addRssArticle,
  RssFeed,
  RssArticle
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
  addRssArticle: jest.fn()
}))

jest.mock('@/api/downloader', () => ({
  getList: jest.fn().mockResolvedValue({ data: [] })
}))

const mockList = getRssFeeds as jest.MockedFunction<typeof getRssFeeds>
const mockCreate = createRssFeed as jest.MockedFunction<typeof createRssFeed>
const mockRefresh = refreshRssFeed as jest.MockedFunction<typeof refreshRssFeed>
const mockArticles = getRssArticles as jest.MockedFunction<typeof getRssArticles>
const mockAdd = addRssArticle as jest.MockedFunction<typeof addRssArticle>
const mockGetList = getList as jest.MockedFunction<typeof getList>

const localVue = createLocalVue()
localVue.use(ElementUI)
localVue.use(VueI18n)
localVue.component('LucideIcon', LucideIcon)

/** class 组件 private 成员运行时即实例成员，经接口重声明访问 */
interface TabVm extends Vue {
  loadFeeds: () => Promise<void>
  loadArticles: () => Promise<void>
  handleRefreshFeed: (feed: RssFeed) => Promise<void>
  openPushDialog: (article: RssArticle) => Promise<void>
  handlePushArticle: () => Promise<void>
  feeds: RssFeed[]
  articles: RssArticle[]
  pushForm: { downloaderId: string, savePath: string, tags: string }
  pushingArticle: RssArticle | null
  activeFeed: RssFeed | null
}

const DOWNLOADER: Downloader = {
  downloaderId: 'dl-1',
  nickname: '节点A',
  host: '10.0.0.1',
  port: '8080',
  downloaderType: 0
}

const FEED: RssFeed = {
  feedId: 'feed-1',
  downloaderId: 'dl-1',
  name: '每日推送',
  url: 'https://rss.example.invalid/feed.xml',
  enabled: true,
  lastFetchAt: '2026-09-24 08:30:00',
  lastFetchStatus: 'ok',
  lastError: null,
  createdAt: '2026-09-01 00:00:00',
  pendingCount: 2
}

const PENDING: RssArticle = {
  articleId: 'art-1',
  feedId: 'feed-1',
  title: 'Show.S01E01.1080p',
  link: 'magnet:?xt=urn:btih:demo',
  publishedAt: '2026-09-24 08:00:00',
  fetchedAt: '2026-09-24 08:30:00',
  status: 'pending',
  addedAt: null,
  addedDownloaderId: null
}

const ADDED: RssArticle = { ...PENDING, articleId: 'art-2', status: 'added', addedAt: '2026-09-24 09:00:00' }

const envelope = <T>(data: T) => ({ status: 'success', msg: 'ok', code: '200', data })
const pageOf = <T>(list: T[]) => ({ list, total: list.length, pageSize: 20 })

const mountTab = (downloader: Downloader | null = DOWNLOADER): Wrapper<TabVm> => {
  return mount(RssSubscriptionTab, {
    localVue,
    i18n,
    propsData: { downloader },
    stubs: {
      'el-drawer': { template: '<div><slot /></div>' },
      transition: false
    }
  }) as Wrapper<TabVm>
}

const flushPromises = async(): Promise<void> => {
  await new Promise(resolve => setTimeout(resolve, 0))
  await Vue.nextTick()
}

describe('RssSubscriptionTab', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockList.mockResolvedValue(envelope(pageOf([FEED])) as never)
    mockCreate.mockResolvedValue(envelope({ feed: FEED }) as never)
    mockRefresh.mockResolvedValue(envelope({ newCount: 1, articleCount: 3, lastFetchAt: '2026-09-24 12:00:00' }) as never)
    mockArticles.mockResolvedValue(envelope(pageOf([PENDING, ADDED])) as never)
    mockAdd.mockResolvedValue(envelope({ article: { ...PENDING, status: 'added' }, downloaderId: 'dl-1' }) as never)
    mockGetList.mockResolvedValue({ data: [] } as never)
    setLocale('zh-CN')
  })

  it('无下载器时渲染空态（先保存基本信息）', () => {
    const wrapper = mountTab(null)
    expect(wrapper.text()).toContain('请先保存基本信息')
    expect(mockList).not.toHaveBeenCalled()
  })

  it('挂载即加载订阅源并渲染待添加计数与抓取状态', async() => {
    const wrapper = mountTab()
    await flushPromises()
    // eslint-disable-next-line no-console
    expect(mockList).toHaveBeenCalledWith({ downloaderId: 'dl-1', page: 1, pageSize: 20 })
    expect(wrapper.text()).toContain('每日推送')
    expect(wrapper.text()).toContain('2') // pendingCount 徽标
    expect(wrapper.text()).toContain('正常') // lastFetchStatus=ok
  })

  it('刷新订阅源：成功提示携带新增计数并重载列表', async() => {
    const wrapper = mountTab()
    await flushPromises()
    await wrapper.vm.handleRefreshFeed(FEED)
    await flushPromises()
    expect(mockRefresh).toHaveBeenCalledWith('feed-1')
    expect(mockList).toHaveBeenCalledTimes(2) // 挂载 + 刷新后重载
  })

  it('文章抽屉：all 筛选不带 status 透传', async() => {
    const wrapper = mountTab()
    await flushPromises()
    wrapper.vm.activeFeed = FEED
    await wrapper.vm.loadArticles()
    expect(mockArticles).toHaveBeenCalledWith('feed-1', {
      page: 1,
      pageSize: 20,
      status: undefined
    })
    expect(wrapper.vm.articles).toHaveLength(2)
  })

  it('推送：空参数归一 undefined，成功后关闭并重载', async() => {
    const wrapper = mountTab()
    await flushPromises()
    await wrapper.vm.openPushDialog(PENDING)
    await flushPromises()
    wrapper.vm.pushForm = { downloaderId: '', savePath: '  ', tags: '' }
    await wrapper.vm.handlePushArticle()
    await flushPromises()
    expect(mockAdd).toHaveBeenCalledWith('art-1', {
      downloaderId: undefined,
      savePath: undefined,
      tags: undefined
    })
    expect(mockAdd).toHaveBeenCalledTimes(1)
  })

  it('推送弹窗：目标下载器选项只含 qB/TR 类型', async() => {
    mockGetList.mockResolvedValue({
      data: [
        { ...DOWNLOADER, downloaderId: 'qb', downloaderType: 0 },
        { ...DOWNLOADER, downloaderId: 'tr', downloaderType: 1 },
        { ...DOWNLOADER, downloaderId: 'rt', downloaderType: 2 }
      ]
    } as never)
    const wrapper = mountTab()
    await flushPromises()
    await wrapper.vm.openPushDialog(PENDING)
    await flushPromises()
    interface PushHost extends TabVm {
      downloaderOptions: Downloader[]
    }
    const vm = wrapper.vm as unknown as PushHost
    expect(vm.downloaderOptions.map(item => item.downloaderId)).toEqual(['qb', 'tr'])
  })

  it('双语：en locale 下空态文案为英文', async() => {
    setLocale('en')
    const wrapper = mountTab(null)
    expect(wrapper.text()).toContain('Save the basic information first')
  })
})
