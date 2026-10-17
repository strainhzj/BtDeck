import {
  DemoActivity,
  DemoAuditLog,
  DemoBackup,
  DemoDownloader,
  DemoFixtureBundle,
  DemoMcpCapabilityMeta,
  DemoMoviePilotAssociation,
  DemoMoviePilotInstance,
  DemoNotification,
  DemoOrphanFile,
  DemoQueryTemplate,
  DemoRecycleItem,
  DemoRssFeed,
  DemoRssRule,
  DemoRssMode,
  DemoQbRssNode,
  DemoQbRssArticle,
  DemoQbRssRule,
  DemoQbRssPreferences,
  DemoTask,
  DemoTaskLog,
  DemoTorrent,
  DemoTracker,
  DemoTrackerKeyword,
  DemoTrackerMessage,
  DemoTrackerReannounceConfig,
  DemoUser
} from '@/demo/types'

export const DEMO_TIME = '2026-09-02T10:00:00+08:00'
const DEMO_YESTERDAY = '2026-09-01T18:30:00+08:00'

/** 与 makeTorrent 同一规则推导 demo 种子 hash，供 MoviePilot 关联镜像引用 */
const demoTorrentHash = (infoId: string): string =>
  infoId.replace(/[^a-z0-9]/gi, '').padEnd(40, '0').slice(0, 40)

export const DEMO_USER: DemoUser = {
  userId: 'demo-user-001',
  name: '演示管理员',
  roles: ['admin'],
  avatar: '',
  introduction: 'BtDeck 静态展示账号',
  twoFactorFlag: '0',
  mustChangePassword: false
}

export const DEMO_TRACKERS: DemoTracker[] = [
  {
    trackerId: 'demo-tracker-001',
    trackerName: 'Demo Tracker Alpha',
    trackerUrl: 'https://tracker-alpha.example.invalid/announce',
    trackerHost: 'tracker-alpha.example.invalid',
    trackerStatus: 'working',
    lastAnnounceSucceeded: 'success',
    lastAnnounceMsg: '演示数据：汇报成功',
    lastScrapeSucceeded: 'success',
    lastScrapeMsg: '演示数据：抓取成功',
    seederCount: 128,
    leecherCount: 24,
    downloadCount: 486
  },
  {
    trackerId: 'demo-tracker-002',
    trackerName: 'Demo Tracker Beta',
    trackerUrl: 'https://tracker-beta.example.invalid/announce',
    trackerHost: 'tracker-beta.example.invalid',
    trackerStatus: 'warning',
    lastAnnounceSucceeded: 'warning',
    lastAnnounceMsg: '演示数据：响应较慢',
    lastScrapeSucceeded: 'success',
    lastScrapeMsg: '演示数据：抓取成功',
    seederCount: 46,
    leecherCount: 9,
    downloadCount: 162
  }
]

const makeTorrent = (input: Partial<DemoTorrent> & Pick<DemoTorrent, 'infoId' | 'name' | 'status'>): DemoTorrent => ({
  infoId: input.infoId,
  downloaderId: input.downloaderId || 'demo-downloader-001',
  downloaderName: input.downloaderName || '实验室节点 A',
  torrentId: input.torrentId || `torrent-${input.infoId}`,
  hash: input.hash || demoTorrentHash(input.infoId),
  name: input.name,
  savePath: input.savePath || '/demo/library',
  size: input.size || 0,
  status: input.status,
  errorReason: input.errorReason || null,
  hasTrackerError: input.hasTrackerError || false,
  torrentFile: input.torrentFile || 'demo.torrent',
  auxiliarySeedCount: input.auxiliarySeedCount || 0,
  addedDate: input.addedDate || DEMO_YESTERDAY,
  completedDate: input.completedDate || null,
  ratio: input.ratio ?? 0,
  ratioLimit: input.ratioLimit ?? 2,
  tags: input.tags || '演示,媒体',
  category: input.category || '演示资源',
  superSeeding: input.superSeeding || false,
  enabled: input.enabled ?? true,
  trackerInfo: input.trackerInfo || DEMO_TRACKERS,
  progress: input.progress ?? 0,
  state: input.state || input.status,
  downloadSpeed: input.downloadSpeed || 0,
  uploadSpeed: input.uploadSpeed || 0,
  downloadComplete: input.downloadComplete || false,
  peers: input.peers || 0,
  seeds: input.seeds || 0,
  num_seeds: input.num_seeds || input.seeds || 0,
  num_leechs: input.num_leechs || input.peers || 0
})

/** RSS 订阅源 demo fixture（feature rss-subscription-2026-09-24；域名 example.invalid，链接为演示占位） */

/** 引擎自动下载规则（Phase 2 demo） */
export const DEMO_RSS_RULES: DemoRssRule[] = [
  {
    ruleId: 'demo-rss-rule-001',
    downloaderId: 'demo-downloader-001',
    name: '剧集 1080p 追更',
    enabled: true,
    includeKeywords: 'Show,1080p',
    excludeKeywords: 'Repack',
    useRegex: false,
    targetDownloaderId: null,
    savePath: '/downloads/shows',
    tags: 'rss,shows',
    feedIds: [],
    matchCount: 12,
    lastMatchedAt: '2026-09-24 08:30:00'
  },
  {
    ruleId: 'demo-rss-rule-002',
    downloaderId: 'demo-downloader-001',
    name: '纪录片合集',
    enabled: false,
    includeKeywords: 'Documentary',
    excludeKeywords: null,
    useRegex: false,
    targetDownloaderId: 'demo-downloader-002',
    savePath: null,
    tags: null,
    feedIds: ['demo-rss-feed-001'],
    matchCount: 0,
    lastMatchedAt: null
  }
]

/** RSS 模式（Phase 2 demo：qB 演示切换） */
export const DEMO_RSS_MODES: DemoRssMode[] = []

/** qB 原生 RSS 源树（Phase 2 demo 固定形态） */
export const DEMO_QB_RSS_TREE: DemoQbRssNode[] = [
  {
    type: 'folder',
    name: '剧集',
    path: '剧集',
    children: [
      {
        type: 'feed',
        name: '周一剧组',
        path: '剧集\\周一剧组',
        articleCount: 2,
        unreadCount: 1
      },
      { type: 'folder', name: '待整理', path: '剧集\\待整理', children: [] }
    ]
  },
  {
    type: 'feed',
    name: 'Weekly Bundle',
    path: 'Weekly Bundle',
    articleCount: 1,
    unreadCount: 1
  }
]

/** qB 原生文章（按源路径索引） */
export const DEMO_QB_RSS_ARTICLES: Record<string, DemoQbRssArticle[]> = {
  '剧集\\周一剧组': [
    {
      articleId: 'demo-qb-article-001',
      title: 'Drama.S02E03.1080p.WEB-DL',
      link: 'https://qb.example.invalid/torrents/drama-s02e03.torrent',
      published: '2026-09-24 09:00:00',
      isRead: false
    },
    {
      articleId: 'demo-qb-article-002',
      title: 'Drama.S02E02.1080p.WEB-DL',
      link: 'https://qb.example.invalid/torrents/drama-s02e02.torrent',
      published: '2026-09-23 09:00:00',
      isRead: true
    }
  ],
  'Weekly Bundle': [
    {
      articleId: 'demo-qb-article-003',
      title: 'Weekly.Pack.2026-09-24',
      link: 'magnet:?xt=urn:btih:demow001demow001demow001demow001demow0',
      published: '2026-09-24 07:30:00',
      isRead: false
    }
  ]
}

/** qB 原生下载规则（Phase 2 demo） */
export const DEMO_QB_RSS_RULES: DemoQbRssRule[] = [
  {
    name: '剧集自动下载',
    enabled: true,
    mustContain: 'Drama',
    mustNotContain: 'Repack',
    affectedFeeds: ['剧集\\周一剧组'],
    savePath: '/tv/drama',
    assignedCategory: 'tv',
    addPaused: false
  }
]

/** qB RSS 偏好（Phase 2 demo） */
export const DEMO_QB_RSS_PREFERENCES: DemoQbRssPreferences = {
  rssProcessingEnabled: true,
  rssAutoDownloadingEnabled: true,
  rssRefreshInterval: 30,
  rssMaxArticlesPerFeed: 100
}

export const DEMO_RSS_FEEDS: DemoRssFeed[] = [
  {
    feedId: 'demo-rss-feed-001',
    downloaderId: 'demo-downloader-001',
    name: '每日剧集推送',
    url: 'https://rss.example.invalid/daily-shows.xml',
    enabled: true,
    lastFetchAt: '2026-09-24 08:30:00',
    lastFetchStatus: 'ok',
    lastError: null,
    articles: [
      {
        articleId: 'demo-rss-article-001',
        feedId: 'demo-rss-feed-001',
        title: 'Show.S01E01.1080p.WEB-DL',
        link: 'magnet:?xt=urn:btih:demo0001demo0001demo0001demo0001demo0001',
        publishedAt: '2026-09-24 08:00:00',
        fetchedAt: '2026-09-24 08:30:00',
        status: 'pending',
        addedAt: null
      },
      {
        articleId: 'demo-rss-article-002',
        feedId: 'demo-rss-feed-001',
        title: 'Show.S01E02.1080p.WEB-DL',
        link: 'magnet:?xt=urn:btih:demo0002demo0002demo0002demo0002demo0002',
        publishedAt: '2026-09-23 08:00:00',
        fetchedAt: '2026-09-24 08:30:00',
        status: 'added',
        addedAt: '2026-09-24 09:10:00'
      }
    ]
  },
  {
    feedId: 'demo-rss-feed-002',
    downloaderId: 'demo-downloader-002',
    name: '开源镜像更新',
    url: 'https://rss.example.invalid/distro-releases.xml',
    enabled: true,
    lastFetchAt: '2026-09-23 22:00:00',
    lastFetchStatus: 'failed',
    lastError: 'HTTP 503',
    articles: []
  }
]

export const DEMO_DOWNLOADERS: DemoDownloader[] = [
  {
    downloaderId: 'demo-downloader-001',
    nickname: '实验室节点 A',
    host: 'node-a.example.invalid',
    port: '443',
    downloaderType: 0,
    downloaderTypeName: 'qbittorrent',
    isSearch: '1',
    enabled: '1',
    status: 'online',
    version: '演示版本 5.0',
    connectStatus: '1',
    delay: 18,
    downloadSpeed: 18 * 1024 * 1024,
    uploadSpeed: 2 * 1024 * 1024,
    downloadingCount: 2,
    seedingCount: 3,
    pausedCount: 1
  },
  {
    downloaderId: 'demo-downloader-002',
    nickname: '家庭节点 B',
    host: 'node-b.example.invalid',
    port: '443',
    downloaderType: 1,
    downloaderTypeName: 'transmission',
    isSearch: '0',
    enabled: '1',
    status: 'online',
    version: '演示版本 4.0',
    connectStatus: '1',
    delay: 32,
    downloadSpeed: 7 * 1024 * 1024,
    uploadSpeed: 1024 * 1024,
    downloadingCount: 1,
    seedingCount: 2,
    pausedCount: 0
  },
  {
    downloaderId: 'demo-downloader-003',
    nickname: '归档节点 C',
    host: 'node-c.example.invalid',
    port: '443',
    downloaderType: 0,
    downloaderTypeName: 'qbittorrent',
    isSearch: '0',
    enabled: '1',
    status: 'offline',
    version: '演示版本 4.6',
    connectStatus: '0',
    delay: null,
    downloadSpeed: 0,
    uploadSpeed: 0,
    downloadingCount: 0,
    seedingCount: 0,
    pausedCount: 2
  }
]

export const DEMO_TORRENTS: DemoTorrent[] = [
  makeTorrent({
    infoId: 'demo-info-001',
    name: '演示纪录片：蓝色星球',
    status: 'downloading',
    size: 48 * 1024 * 1024 * 1024,
    progress: 68.4,
    downloadSpeed: 12 * 1024 * 1024,
    uploadSpeed: 1024 * 1024,
    peers: 18,
    seeds: 64,
    num_seeds: 64,
    num_leechs: 18,
    category: '纪录片',
    tags: '演示,高清'
  }),
  makeTorrent({
    infoId: 'demo-info-002',
    name: '演示电影：晨雾中的城市',
    status: 'seeding',
    size: 8 * 1024 * 1024 * 1024,
    progress: 100,
    completedDate: DEMO_YESTERDAY,
    ratio: 2.36,
    downloadComplete: true,
    uploadSpeed: 3 * 1024 * 1024,
    peers: 7,
    seeds: 82,
    num_seeds: 82,
    num_leechs: 7,
    category: '电影',
    downloaderId: 'demo-downloader-002',
    downloaderName: '家庭节点 B'
  }),
  makeTorrent({
    infoId: 'demo-info-003',
    name: '演示音乐：夜航日志',
    status: 'paused',
    size: 2 * 1024 * 1024 * 1024,
    progress: 43.2,
    ratio: 0.42,
    peers: 0,
    seeds: 21,
    num_seeds: 21,
    num_leechs: 0,
    category: '音乐',
    tags: '演示,音乐',
    downloaderId: 'demo-downloader-002',
    downloaderName: '家庭节点 B'
  }),
  makeTorrent({
    infoId: 'demo-info-004',
    name: '演示软件：设计工具包',
    status: 'error',
    size: 16 * 1024 * 1024 * 1024,
    progress: 12,
    errorReason: '演示数据：Tracker 暂时不可用',
    hasTrackerError: true,
    ratio: 0.08,
    peers: 2,
    seeds: 0,
    num_seeds: 0,
    num_leechs: 2,
    category: '软件',
    tags: '演示,待处理'
  }),
  makeTorrent({
    infoId: 'demo-info-005',
    name: '演示课程：前端工程实践',
    status: 'completed',
    size: 24 * 1024 * 1024 * 1024,
    progress: 100,
    completedDate: '2026-08-31T12:15:00+08:00',
    ratio: 1.28,
    downloadComplete: true,
    peers: 1,
    seeds: 33,
    num_seeds: 33,
    num_leechs: 1,
    category: '课程',
    tags: '演示,学习',
    downloaderId: 'demo-downloader-001',
    downloaderName: '实验室节点 A'
  }),
  makeTorrent({
    infoId: 'demo-info-006',
    name: '演示动画：纸飞机计划',
    status: 'checking',
    size: 12 * 1024 * 1024 * 1024,
    progress: 99,
    ratio: 0.96,
    peers: 0,
    seeds: 12,
    num_seeds: 12,
    num_leechs: 0,
    category: '动画',
    tags: '演示,检查中',
    downloaderId: 'demo-downloader-001',
    downloaderName: '实验室节点 A'
  }),
  makeTorrent({
    infoId: 'demo-info-007',
    name: '演示影像：山谷信号',
    status: 'queuedDL',
    size: 36 * 1024 * 1024 * 1024,
    progress: 0,
    ratio: 0,
    peers: 0,
    seeds: 14,
    num_seeds: 14,
    num_leechs: 0,
    category: '影像',
    tags: '演示,队列',
    downloaderId: 'demo-downloader-003',
    downloaderName: '归档节点 C'
  }),
  makeTorrent({
    infoId: 'demo-info-008',
    name: '演示剧集：远方信件',
    status: 'seeding',
    size: 22 * 1024 * 1024 * 1024,
    progress: 100,
    completedDate: '2026-08-28T16:00:00+08:00',
    ratio: 3.02,
    downloadComplete: true,
    uploadSpeed: 512 * 1024,
    peers: 4,
    seeds: 56,
    num_seeds: 56,
    num_leechs: 4,
    category: '剧集',
    tags: '演示,连续剧',
    downloaderId: 'demo-downloader-002',
    downloaderName: '家庭节点 B'
  }),
  makeTorrent({
    infoId: 'demo-info-009',
    name: '演示资料：摄影素材集',
    status: 'downloading',
    size: 72 * 1024 * 1024 * 1024,
    progress: 27.5,
    downloadSpeed: 5 * 1024 * 1024,
    uploadSpeed: 256 * 1024,
    peers: 12,
    seeds: 29,
    num_seeds: 29,
    num_leechs: 12,
    category: '素材',
    tags: '演示,摄影'
  })
]

export const DEMO_NOTIFICATIONS: DemoNotification[] = [
  {
    id: 1,
    type: 'system',
    title: '欢迎使用 BtDeck 演示模式',
    content: '当前页面展示的是本地模拟数据，所有操作不会连接真实下载器或写入后端。',
    priority: 'info',
    is_read: false,
    extra_data: null,
    created_at: DEMO_TIME,
    read_at: null
  },
  {
    id: 2,
    type: 'version_update',
    title: 'Demo 流程已准备就绪',
    content: '可从仪表盘开始查看节点、筛选种子并体验暂停/恢复与查询模板交互。',
    priority: 'info',
    is_read: false,
    extra_data: null,
    created_at: DEMO_YESTERDAY,
    read_at: null
  },
  {
    id: 3,
    type: 'system',
    title: '归档节点需要注意',
    content: '这是演示中的离线节点，用于展示异常状态和降级提示。',
    priority: 'warning',
    is_read: true,
    extra_data: null,
    created_at: '2026-08-30T09:20:00+08:00',
    read_at: '2026-08-30T09:30:00+08:00'
  }
]

const SIMPLE_TEMPLATE = (name: string, description: string, status: string[], id: string): DemoQueryTemplate => ({
  id,
  user_id: 'demo-user-001',
  name,
  description,
  conditions: {
    source: 'simple',
    version: 1,
    listQuery: {
      name_like: '',
      category_like: '',
      tags_like: '',
      downloader_id: [],
      status,
      tracker_domain: [],
      showActiveOnly: false,
      sort_by: 'added_date',
      sort_order: 'desc'
    }
  },
  is_default: id === 'demo-template-001',
  is_public: true,
  usage_count: id === 'demo-template-001' ? 24 : 8,
  created_time: DEMO_YESTERDAY,
  updated_time: null
})

export const DEMO_QUERY_TEMPLATES: DemoQueryTemplate[] = [
  SIMPLE_TEMPLATE('正在下载', '展示当前有下载速度的演示种子。', ['downloading'], 'demo-template-001'),
  SIMPLE_TEMPLATE('待处理项目', '集中查看暂停、错误和检查中的任务。', ['paused', 'error', 'checking'], 'demo-template-002'),
  {
    ...SIMPLE_TEMPLATE('高分享率', '展示已完成且分享率较高的内容。', ['seeding', 'completed'], 'demo-template-003'),
    is_default: false,
    conditions: {
      source: 'advanced',
      version: 1,
      condition_groups: [{
        logic: 'AND',
        conditions: [{ field: 'ratio', operator: 'greater_than', value: 1 }]
      }]
    }
  }
]

export const DEMO_TASKS: DemoTask[] = [
  {
    taskId: 1,
    taskName: 'Tracker 状态同步（演示）',
    taskCode: 'demo_tracker_sync',
    taskStatus: 2,
    taskType: 4,
    executor: 'DemoTrackerSyncTask',
    enabled: true,
    lastExecuteTime: DEMO_YESTERDAY,
    lastExecuteDuration: 1260,
    cronPlan: '*/15 * * * *',
    taskStatusName: '空闲',
    taskTypeName: 'Python 内部类',
    createTime: '2026-08-20T09:00:00+08:00',
    updateTime: DEMO_YESTERDAY,
    description: '静态演示任务，不会执行真实同步。',
    lastOutcome: 'success',
    lastSuccessfulDataAt: DEMO_YESTERDAY,
    lastAttemptAt: DEMO_YESTERDAY,
    lastSkipReason: null,
    lastRunId: 'demo-run-001',
    freshnessSeconds: 5400,
    stale: false
  },
  {
    taskId: 2,
    taskName: '孤儿文件扫描（演示）',
    taskCode: 'demo_orphan_scan',
    taskStatus: 0,
    taskType: 4,
    executor: 'DemoOrphanScanTask',
    enabled: true,
    lastExecuteTime: '2026-08-31T03:00:00+08:00',
    lastExecuteDuration: 8420,
    cronPlan: '0 3 * * 0',
    taskStatusName: '等待运行',
    taskTypeName: 'Python 内部类',
    createTime: '2026-08-20T09:10:00+08:00',
    updateTime: '2026-08-31T03:00:00+08:00',
    description: '静态演示任务，不会读取本地文件系统。',
    lastOutcome: 'partial',
    lastSuccessfulDataAt: '2026-08-31T03:00:00+08:00',
    lastAttemptAt: '2026-08-31T03:00:00+08:00',
    lastSkipReason: null,
    lastRunId: 'demo-run-002',
    freshnessSeconds: 111600,
    stale: true
  },
  {
    taskId: 3,
    taskName: '备份报告（演示）',
    taskCode: 'demo_backup_report',
    taskStatus: 2,
    taskType: 0,
    executor: 'echo demo',
    enabled: false,
    lastExecuteTime: '2026-08-29T22:00:00+08:00',
    lastExecuteDuration: 320,
    cronPlan: '0 22 * * *',
    taskStatusName: '空闲',
    taskTypeName: 'Shell',
    createTime: '2026-08-18T15:30:00+08:00',
    updateTime: '2026-08-29T22:00:00+08:00',
    description: '静态演示任务，导出结果仅在浏览器内生成。',
    lastOutcome: 'no_action',
    lastSuccessfulDataAt: '2026-08-29T22:00:00+08:00',
    lastAttemptAt: '2026-08-29T22:00:00+08:00',
    lastSkipReason: null,
    lastRunId: 'demo-run-003',
    freshnessSeconds: 200000,
    stale: false
  }
]

export const DEMO_TASK_LOGS: DemoTaskLog[] = [
  {
    logId: 1,
    taskId: 1,
    taskName: 'Tracker 状态同步（演示）',
    taskType: 4,
    startTime: DEMO_YESTERDAY,
    endTime: '2026-09-01T18:30:01+08:00',
    duration: 1260,
    success: true,
    logDetail: 'Demo Mode：模拟完成 3 个节点状态刷新。',
    createTime: DEMO_YESTERDAY,
    outcome: 'success',
    skipReason: null
  },
  {
    logId: 2,
    taskId: 2,
    taskName: '孤儿文件扫描（演示）',
    taskType: 4,
    startTime: '2026-08-31T03:00:00+08:00',
    endTime: '2026-08-31T03:00:08+08:00',
    duration: 8420,
    success: true,
    logDetail: 'Demo Mode：模拟扫描 3 个脱敏路径，发现 2 个待处理文件。',
    createTime: '2026-08-31T03:00:08+08:00',
    outcome: 'partial',
    skipReason: null
  }
]

export const DEMO_AUDIT_LOGS: DemoAuditLog[] = [
  {
    log_id: 'demo-audit-001',
    torrent_info_id: 'demo-info-001',
    operation_type: 'PAUSE',
    operation_detail: '暂停演示种子',
    old_value: 'downloading',
    new_value: 'paused',
    operator: '演示管理员',
    operation_time: DEMO_TIME,
    operation_result: 'success',
    error_message: null,
    downloader_id: 'demo-downloader-001',
    create_time: DEMO_TIME,
    ip_address: null,
    user_agent: null,
    request_id: null,
    session_id: null,
    torrent_name: '演示纪录片：蓝色星球',
    downloader_name: '实验室节点 A'
  },
  {
    log_id: 'demo-audit-002',
    torrent_info_id: null,
    operation_type: 'LOGIN',
    operation_detail: '进入 Demo Mode',
    old_value: null,
    new_value: 'local-demo-session',
    operator: '演示管理员',
    operation_time: DEMO_YESTERDAY,
    operation_result: 'success',
    error_message: null,
    downloader_id: null,
    create_time: DEMO_YESTERDAY,
    ip_address: null,
    user_agent: null,
    request_id: null,
    session_id: null,
    torrent_name: null,
    downloader_name: null
  },
  {
    log_id: 'demo-audit-003',
    torrent_info_id: 'demo-info-004',
    operation_type: 'REANNOUNCE',
    operation_detail: 'Tracker 操作已降级为本地模拟',
    old_value: null,
    new_value: null,
    operator: '演示管理员',
    operation_time: '2026-08-31T11:20:00+08:00',
    operation_result: 'partial',
    error_message: 'Demo Mode 不访问外部 Tracker',
    downloader_id: 'demo-downloader-001',
    create_time: '2026-08-31T11:20:00+08:00',
    ip_address: null,
    user_agent: null,
    request_id: null,
    session_id: null,
    torrent_name: '演示软件：设计工具包',
    downloader_name: '实验室节点 A'
  }
]

export const DEMO_RECYCLE_BIN: DemoRecycleItem[] = [
  {
    info_id: 'demo-recycle-001',
    name: '演示旧项目：归档副本',
    size: 4 * 1024 * 1024 * 1024,
    save_path: '/demo/recycle',
    deleted_at: '2026-08-30T14:20:00+08:00',
    downloader_name: '实验室节点 A',
    downloader_id: 'demo-downloader-001',
    torrent_id: 'demo-recycle-torrent-001',
    hash: 'demo-recycle-hash-001'
  },
  {
    info_id: 'demo-recycle-002',
    name: '演示下载：待确认文件',
    size: 720 * 1024 * 1024,
    save_path: '/demo/recycle',
    deleted_at: '2026-08-29T10:10:00+08:00',
    downloader_name: '家庭节点 B',
    downloader_id: 'demo-downloader-002',
    torrent_id: 'demo-recycle-torrent-002',
    hash: 'demo-recycle-hash-002'
  }
]

export const DEMO_ORPHAN_FILES: DemoOrphanFile[] = [
  {
    id: 1,
    scan_id: 'demo-scan-001',
    file_path: '/demo/library/未关联文件-A.bin',
    file_size: 860 * 1024 * 1024,
    hardlink_copy_count: 0,
    mtime: DEMO_YESTERDAY,
    downloader_id: 'demo-downloader-001',
    confidence: 'high',
    canonical_path: '/demo/library/未关联文件-A.bin',
    downloader_name: '实验室节点 A',
    is_ignored: false,
    ignored_at: null,
    ignored_by: null,
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: DEMO_YESTERDAY
  },
  {
    id: 2,
    scan_id: 'demo-scan-001',
    file_path: '/demo/archive/待确认文件-B.iso',
    file_size: 2300 * 1024 * 1024,
    hardlink_copy_count: 1,
    mtime: '2026-08-28T08:40:00+08:00',
    downloader_id: 'demo-downloader-003',
    confidence: 'low',
    canonical_path: '/demo/archive/待确认文件-B.iso',
    downloader_name: '归档节点 C',
    is_ignored: false,
    ignored_at: null,
    ignored_by: null,
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: '2026-08-28T08:40:00+08:00'
  },
  {
    id: 3,
    scan_id: 'demo-scan-001',
    file_path: '/demo/archive/已忽视文件-C.txt',
    file_size: 32 * 1024,
    hardlink_copy_count: null,
    mtime: '2026-08-27T17:15:00+08:00',
    downloader_id: 'demo-downloader-003',
    confidence: 'high',
    canonical_path: '/demo/archive/已忽视文件-C.txt',
    downloader_name: '归档节点 C',
    is_ignored: true,
    ignored_at: '2026-08-28T09:00:00+08:00',
    ignored_by: '演示管理员',
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: '2026-08-27T17:15:00+08:00'
  }
]

export const DEMO_TRACKER_KEYWORDS: DemoTrackerKeyword[] = [
  {
    keyword_id: 'demo-keyword-001',
    keyword_type: 'candidate',
    keyword: '演示关键词',
    language: 'zh-CN',
    priority: 10,
    enabled: true,
    category: '媒体',
    description: '演示候选关键词',
    create_time: DEMO_YESTERDAY,
    update_time: DEMO_YESTERDAY
  },
  {
    keyword_id: 'demo-keyword-002',
    keyword_type: 'success',
    keyword: '高质量演示',
    language: 'zh-CN',
    priority: 20,
    enabled: true,
    category: '质量',
    description: '演示成功关键词',
    create_time: '2026-08-30T10:00:00+08:00',
    update_time: '2026-08-30T10:00:00+08:00'
  },
  {
    keyword_id: 'demo-keyword-003',
    keyword_type: 'ignored',
    keyword: '临时演示',
    language: 'zh-CN',
    priority: 5,
    enabled: false,
    category: '过滤',
    description: '演示忽略关键词',
    create_time: '2026-08-28T10:00:00+08:00',
    update_time: '2026-08-28T10:00:00+08:00'
  }
]

export const DEMO_TRACKER_MESSAGES: DemoTrackerMessage[] = [
  {
    log_id: 'demo-message-001',
    tracker_host: 'tracker-alpha.example.invalid',
    msg: '演示数据：请求频率较高',
    first_seen: DEMO_YESTERDAY,
    last_seen: DEMO_TIME,
    occurrence_count: 4,
    is_processed: false,
    keyword_type: 'failed',
    sample_torrents: ['演示纪录片：蓝色星球'],
    sample_urls: [],
    create_time: DEMO_YESTERDAY,
    update_time: DEMO_TIME
  },
  {
    log_id: 'demo-message-002',
    tracker_host: 'tracker-beta.example.invalid',
    msg: '演示数据：连接成功',
    first_seen: '2026-08-30T12:00:00+08:00',
    last_seen: '2026-08-30T12:05:00+08:00',
    occurrence_count: 1,
    is_processed: true,
    keyword_type: 'success',
    sample_torrents: ['演示电影：晨雾中的城市'],
    sample_urls: [],
    create_time: '2026-08-30T12:05:00+08:00',
    update_time: '2026-08-30T12:05:00+08:00'
  }
]

export const DEMO_TRACKER_REANNOUNCE_CONFIGS: DemoTrackerReannounceConfig[] = [
  {
    config_id: 'demo-config-001',
    domain_pattern: 'tracker-alpha.example.invalid',
    domain_display_name: 'Demo Tracker Alpha',
    interval_minutes: 30,
    enabled: true,
    last_reannounce_time: DEMO_YESTERDAY,
    create_time: '2026-08-20T10:00:00+08:00',
    update_time: DEMO_YESTERDAY
  },
  {
    config_id: 'demo-config-002',
    domain_pattern: 'tracker-beta.example.invalid',
    domain_display_name: 'Demo Tracker Beta',
    interval_minutes: 60,
    enabled: false,
    last_reannounce_time: '2026-08-31T10:30:00+08:00',
    create_time: '2026-08-20T10:10:00+08:00',
    update_time: '2026-08-31T10:30:00+08:00'
  }
]

export const DEMO_BACKUPS: DemoBackup[] = [
  {
    id: 1,
    info_hash: 'demo-backup-hash-001',
    task_name: '演示纪录片：蓝色星球',
    torrent_name: '演示纪录片：蓝色星球',
    downloader_id: 1,
    file_path: '/demo/backups/demo-001.torrent',
    created_at: DEMO_YESTERDAY,
    updated_at: DEMO_YESTERDAY,
    uploader_username: '演示管理员'
  },
  {
    id: 2,
    info_hash: 'demo-backup-hash-002',
    task_name: '演示课程：前端工程实践',
    torrent_name: '演示课程：前端工程实践',
    downloader_id: 1,
    file_path: '/demo/backups/demo-002.torrent',
    created_at: '2026-08-30T16:00:00+08:00',
    updated_at: '2026-08-30T16:00:00+08:00',
    uploader_username: '演示管理员'
  }
]

/** MCP 能力目录（镜像后端 contracts.py CAPABILITY_CATALOG 六项，只读元数据） */
export const DEMO_MCP_CATALOG: DemoMcpCapabilityMeta[] = [
  {
    code: 'torrent.advanced_search',
    tool: 'torrent_advanced_search',
    risk: 'read',
    description: '按字段白名单条件高级查询种子（脱敏摘要，默认省略种子 hash）。',
    descriptionEn: 'Advanced torrent search by whitelisted field conditions (redacted summary; torrent hash omitted by default).',
    defaultEnabled: false,
    requiresConfirm: false,
    requiresIdempotencyKey: false
  },
  {
    code: 'torrent.mark_pending_delete',
    tool: 'torrent_mark_pending_delete',
    risk: 'write',
    description: '为下载器与数据库中的种子添加 pending_delete 标签；仅添加标签，不删除任务或文件。',
    descriptionEn: 'Add the pending_delete tag to torrents in the downloader and the database; tagging only, no tasks or files are deleted.',
    defaultEnabled: false,
    requiresConfirm: true,
    requiresIdempotencyKey: true
  },
  {
    code: 'torrent.add',
    tool: 'torrent_add_file',
    risk: 'high',
    description: '添加 .torrent 种子文件（仅二进制内容，不接受磁力/URL/服务器路径）。',
    descriptionEn: 'Add a .torrent seed file (binary content only; magnet links, URLs, and server paths are rejected).',
    defaultEnabled: false,
    requiresConfirm: true,
    requiresIdempotencyKey: true
  },
  {
    code: 'search_template.create',
    tool: 'advanced_search_template_create',
    risk: 'write',
    description: '创建高级查询组合/查询模板（模板归属认证主体）。',
    descriptionEn: 'Create an advanced-search condition group / query template (owned by the authenticated principal).',
    defaultEnabled: false,
    requiresConfirm: true,
    requiresIdempotencyKey: true
  },
  {
    code: 'dashboard.read',
    tool: 'dashboard_get',
    risk: 'read',
    description: '读取仪表盘聚合数据（脱敏聚合，无下载器地址与审计敏感字段）。',
    descriptionEn: 'Read dashboard aggregates (redacted; no downloader addresses or audit-sensitive fields).',
    defaultEnabled: false,
    requiresConfirm: false,
    requiresIdempotencyKey: false
  },
  {
    code: 'cron.trigger',
    tool: 'cron_task_trigger',
    risk: 'high',
    description: '立即触发一个内置定时任务（仅白名单 task_code）。',
    descriptionEn: 'Trigger a built-in scheduled task immediately (allowlisted task_code only).',
    defaultEnabled: false,
    requiresConfirm: true,
    requiresIdempotencyKey: true
  }
]

export const DEMO_MCP_SETTINGS: DemoFixtureBundle['mcpSettings'] = {
  schemaVersion: 1,
  enabled: true,
  capabilities: {
    'torrent.advanced_search': true,
    'torrent.mark_pending_delete': false,
    'torrent.add': false,
    'search_template.create': false,
    'dashboard.read': true,
    'cron.trigger': false
  },
  revision: 2,
  updatedAt: DEMO_YESTERDAY,
  updatedBy: '演示管理员',
  forceDisabled: false
}

/**
 * demo 专用服务密钥（格式对齐真实 btdmcp_ + 43 位 base64url，仅演示用；
 * demo 面板「刷新」返回同形新值，不进任何真实认证链）。
 */
export const DEMO_MCP_API_KEY = 'btdmcp_' + 'demo'.repeat(10) + 'Key'

export const DEMO_MCP_APIKEY: DemoFixtureBundle['mcpApiKey'] = {
  status: 'active',
  exists: true,
  revision: 1,
  createdAt: DEMO_YESTERDAY,
  createdBy: '演示管理员',
  updatedAt: DEMO_YESTERDAY,
  updatedBy: '演示管理员',
  keyPrefix: 'btdmcp_',
  key: DEMO_MCP_API_KEY
}

export const DEMO_MOVIEPILOT_SETTINGS: DemoFixtureBundle['moviepilotSettings'] = {
  schemaVersion: 1,
  enabled: true,
  revision: 1,
  updatedAt: '2026-08-30T09:00:00+08:00',
  updatedBy: '演示管理员'
}

export const DEMO_MOVIEPILOT_INSTANCES: DemoMoviePilotInstance[] = [
  {
    id: 1,
    instanceId: 'demo-mp-instance-001',
    name: '家庭媒体库',
    enabled: true,
    protocolVersion: 1,
    pluginVersion: '1.2.0',
    moviepilotVersion: 'v2.4.0',
    downloaderMapping: {
      '家庭 qBittorrent': 'demo-downloader-001',
      '家庭 Transmission': 'demo-downloader-002'
    },
    boundUsername: 'mp_demo_bot',
    lastHandshakeAt: DEMO_YESTERDAY,
    lastSyncAt: DEMO_TIME,
    lastSyncStats: { inserted: 1, updated: 2, skipped: 0, failed: 0 },
    syncedHistoryCount: 3,
    lastError: null,
    createdAt: '2026-08-20T09:00:00+08:00',
    updatedAt: DEMO_TIME
  },
  {
    id: 2,
    instanceId: 'demo-mp-instance-002',
    name: '实验同步节点',
    enabled: false,
    protocolVersion: 1,
    pluginVersion: '1.1.3',
    moviepilotVersion: 'v2.3.8',
    downloaderMapping: {},
    boundUsername: 'mp_lab_bot',
    lastHandshakeAt: '2026-08-28T15:00:00+08:00',
    lastSyncAt: null,
    lastSyncStats: {},
    syncedHistoryCount: 0,
    lastError: '演示数据：实例已禁用，插件握手被拒绝（403）',
    createdAt: '2026-08-28T15:00:00+08:00',
    updatedAt: '2026-08-29T10:00:00+08:00'
  }
]

export const DEMO_MOVIEPILOT_ASSOCIATIONS: DemoMoviePilotAssociation[] = [
  {
    id: 1,
    instanceId: 'demo-mp-instance-001',
    instanceName: '家庭媒体库',
    historyId: 101,
    srcStorage: '本地下载',
    srcPath: '/demo/downloads/晨雾中的城市.mkv',
    destStorage: '媒体库',
    destPath: '/demo/media/电影/晨雾中的城市 (2025)/晨雾中的城市.mkv',
    transferMode: 'link',
    mediaType: '电影',
    title: '晨雾中的城市',
    year: '2025',
    seasons: null,
    episodes: null,
    tmdbId: 100001,
    doubanId: null,
    mpDownloader: '家庭 Transmission',
    downloadHash: demoTorrentHash('demo-info-002'),
    btDownloaderId: 'demo-downloader-002',
    associationStatus: 'linked',
    status: true,
    errmsg: null,
    recordedAt: DEMO_YESTERDAY
  },
  {
    id: 2,
    instanceId: 'demo-mp-instance-001',
    instanceName: '家庭媒体库',
    historyId: 102,
    srcStorage: '归档下载',
    srcPath: '/demo/archive/蓝色星球S01E01.mkv',
    destStorage: '媒体库',
    destPath: '/demo/media/剧集/蓝色星球/Season 1/蓝色星球S01E01.mkv',
    transferMode: 'copy',
    mediaType: '电视剧',
    title: '蓝色星球',
    year: null,
    seasons: 'S01',
    episodes: 'E01',
    tmdbId: null,
    doubanId: '352001',
    mpDownloader: '归档 qBittorrent',
    downloadHash: demoTorrentHash('demo-info-001'),
    btDownloaderId: null,
    associationStatus: 'unmapped',
    status: true,
    errmsg: null,
    recordedAt: '2026-08-31T20:10:00+08:00'
  },
  {
    id: 3,
    instanceId: 'demo-mp-instance-001',
    instanceName: '家庭媒体库',
    historyId: 103,
    srcStorage: '本地下载',
    srcPath: null,
    destStorage: '媒体库',
    destPath: '/demo/media/电影/远方来信/远方来信.mkv',
    transferMode: 'move',
    mediaType: '电影',
    title: '远方来信',
    year: '2024',
    seasons: null,
    episodes: null,
    tmdbId: null,
    doubanId: null,
    mpDownloader: null,
    downloadHash: null,
    btDownloaderId: null,
    associationStatus: 'unassociated',
    status: true,
    errmsg: null,
    recordedAt: '2026-08-30T11:40:00+08:00'
  }
]

export const DEMO_ACTIVITIES: DemoActivity[] = [
  { time: '刚刚', source: '种子', action: '演示纪录片：蓝色星球正在下载', type: 'torrent' },
  { time: '10 分钟前', source: '下载器', action: '实验室节点 A 状态正常', type: 'downloader' },
  { time: '昨天', source: '查询模板', action: '“正在下载”模板被应用 3 次', type: 'system' },
  { time: '昨天', source: 'Tracker', action: 'Demo Tracker Alpha 完成一次模拟汇报', type: 'tracker' }
]

export const DEMO_FIXTURE_BUNDLE: DemoFixtureBundle = {
  user: DEMO_USER,
  downloaders: DEMO_DOWNLOADERS,
  torrents: DEMO_TORRENTS,
  notifications: DEMO_NOTIFICATIONS,
  queryTemplates: DEMO_QUERY_TEMPLATES,
  rssFeeds: DEMO_RSS_FEEDS,
  rssRules: DEMO_RSS_RULES,
  rssModes: DEMO_RSS_MODES,
  qbRssTree: DEMO_QB_RSS_TREE,
  qbRssArticles: DEMO_QB_RSS_ARTICLES,
  qbRssRules: DEMO_QB_RSS_RULES,
  qbRssPreferences: DEMO_QB_RSS_PREFERENCES,
  qbRssReadArticleIds: [],
  tasks: DEMO_TASKS,
  taskLogs: DEMO_TASK_LOGS,
  auditLogs: DEMO_AUDIT_LOGS,
  recycleBin: DEMO_RECYCLE_BIN,
  orphanFiles: DEMO_ORPHAN_FILES,
  trackerKeywords: DEMO_TRACKER_KEYWORDS,
  trackerMessages: DEMO_TRACKER_MESSAGES,
  trackerReannounceConfigs: DEMO_TRACKER_REANNOUNCE_CONFIGS,
  backups: DEMO_BACKUPS,
  mcpSettings: DEMO_MCP_SETTINGS,
  mcpApiKey: DEMO_MCP_APIKEY,
  moviepilotSettings: DEMO_MOVIEPILOT_SETTINGS,
  moviepilotInstances: DEMO_MOVIEPILOT_INSTANCES,
  moviepilotAssociations: DEMO_MOVIEPILOT_ASSOCIATIONS,
  categories: ['纪录片', '电影', '音乐', '软件', '课程', '动画', '影像', '剧集', '素材'],
  tags: ['演示', '高清', '音乐', '待处理', '学习', '检查中', '队列', '连续剧', '摄影'],
  trackerDomains: ['tracker-alpha.example.invalid', 'tracker-beta.example.invalid']
}

export default DEMO_FIXTURE_BUNDLE

// =============================================================================
// 统计报表 fixtures（statistics-reports W7）
//
// 口径说明：报表聚合（五桶/根前缀/去端口/均值排除 NULL 等）属后端域逻辑，
// Demo 侧不做二次实现——除速度历史（程序化假曲线）与年度报告（年份参数化）
// 外均为静态 fixture（PLANS/statistics-reports.md §4.6"推导不了的静态 fixture
// 注明"）。空态形态单独成组（DEMO_REPORT_*_EMPTY）供空态演示。
// =============================================================================

import {
  BadgesSummary,
  GuardianSummary,
  RatioRankItem,
  ReportsFunSummaryData,
  ReportsFunYearlyData,
  ReportsOverviewData,
  ReportsSeedingData,
  ReportsTrendsData,
  ReportsTrackersData,
  SpeedHistory,
  SpeedRange,
  TrendsPeriod
} from '@/types/reports'

const GB = 1024 ** 3
const TB = 1024 ** 4

export const DEMO_REPORT_OVERVIEW: ReportsOverviewData = {
  totals: { count: 128, sizeBytes: 42.6 * TB, avgSizeBytes: (42.6 * TB) / 128, recycleBinSizeBytes: 640 * GB },
  largest: [
    { hash: 'demo0001', name: 'Demo 蓝光合集 4K REMUX', sizeBytes: 320 * GB },
    { hash: 'demo0002', name: 'Demo 剧集全集 1080p', sizeBytes: 186 * GB },
    { hash: 'demo0003', name: 'Demo 音乐无损合集', sizeBytes: 96 * GB }
  ],
  statusDist: [
    { bucket: 'seeding', count: 86, sizeBytes: 30.2 * TB },
    { bucket: 'downloading', count: 12, sizeBytes: 4.1 * TB },
    { bucket: 'paused', count: 18, sizeBytes: 5.3 * TB },
    { bucket: 'error', count: 9, sizeBytes: 2.4 * TB },
    { bucket: 'other', count: 3, sizeBytes: 0.6 * TB }
  ],
  categories: [
    { name: 'movies', count: 52, sizeBytes: 22.8 * TB },
    { name: 'tv', count: 34, sizeBytes: 12.9 * TB },
    { name: '', count: 42, sizeBytes: 6.9 * TB }
  ],
  tags: [
    { name: 'HD', count: 48, sizeBytes: 18.2 * TB },
    { name: '做种中', count: 30, sizeBytes: 9.6 * TB }
  ],
  paths: [
    { path: '/downloads/movies', count: 58, sizeBytes: 24.7 * TB },
    { path: '/downloads/tv', count: 40, sizeBytes: 11.8 * TB },
    { path: '/downloads', count: 30, sizeBytes: 6.1 * TB }
  ],
  downloaders: [
    {
      downloaderId: 'demo-dl-001',
      nickname: 'Demo qB 主力',
      type: 0,
      removed: false,
      count: 80,
      sizeBytes: 26.5 * TB,
      statusDist: [
        { bucket: 'seeding', count: 60, sizeBytes: 20.1 * TB },
        { bucket: 'downloading', count: 8, sizeBytes: 3.2 * TB },
        { bucket: 'paused', count: 12, sizeBytes: 3.2 * TB }
      ]
    },
    {
      downloaderId: 'demo-dl-removed',
      nickname: '已退役节点',
      type: 1,
      removed: true,
      count: 48,
      sizeBytes: 16.1 * TB,
      statusDist: [{ bucket: 'seeding', count: 48, sizeBytes: 16.1 * TB }]
    }
  ],
  liveSpeed: {
    totalDownloadSpeed: 18 * 1024 * 1024,
    totalUploadSpeed: 42 * 1024 * 1024,
    items: [
      { downloaderId: 'demo-dl-001', nickname: 'Demo qB 主力', online: true, downloadSpeed: 18 * 1024 * 1024, uploadSpeed: 42 * 1024 * 1024 },
      { downloaderId: 'demo-dl-002', nickname: 'Demo TR 辅种', online: false, downloadSpeed: 0, uploadSpeed: 0 }
    ]
  }
}

export const DEMO_REPORT_OVERVIEW_EMPTY: ReportsOverviewData = {
  totals: { count: 0, sizeBytes: 0, avgSizeBytes: 0, recycleBinSizeBytes: 0 },
  largest: [],
  statusDist: [],
  categories: [],
  tags: [],
  paths: [],
  downloaders: [],
  liveSpeed: { totalDownloadSpeed: 0, totalUploadSpeed: 0, items: [] }
}

export const DEMO_REPORT_ADDED: ReportsTrendsData['added'] = [
  { key: '2026-04', count: 18, sizeBytes: 6.2 * TB },
  { key: '2026-05', count: 26, sizeBytes: 9.8 * TB },
  { key: '2026-06', count: 31, sizeBytes: 11.4 * TB },
  { key: '2026-07', count: 22, sizeBytes: 7.9 * TB },
  { key: '2026-08', count: 35, sizeBytes: 14.2 * TB },
  { key: '2026-09', count: 12, sizeBytes: 4.6 * TB }
]

export const DEMO_REPORT_COMPLETED: ReportsTrendsData['completed'] = [
  { key: '2026-05', count: 14, sizeBytes: 5.4 * TB },
  { key: '2026-06', count: 19, sizeBytes: 7.2 * TB },
  { key: '2026-07', count: 16, sizeBytes: 6.1 * TB },
  { key: '2026-08', count: 24, sizeBytes: 9.3 * TB }
]

export const DEMO_REPORT_AGE_BUCKETS: ReportsTrendsData['ageBuckets'] = [
  { name: 'under7d', count: 12, sizeBytes: 4.2 * TB },
  { name: 'to30d', count: 35, sizeBytes: 12.6 * TB },
  { name: 'to90d', count: 44, sizeBytes: 14.1 * TB },
  { name: 'to180d', count: 22, sizeBytes: 7.8 * TB },
  { name: 'to1y', count: 10, sizeBytes: 3.1 * TB },
  { name: 'over1y', count: 3, sizeBytes: 0.5 * TB },
  { name: 'unknown', count: 2, sizeBytes: 0.3 * TB }
]

export const DEMO_REPORT_SEEDING: ReportsSeedingData = {
  ratioBuckets: [
    { bucket: '<0.5', count: 18, sizeBytes: 9.8 * TB },
    { bucket: '0.5-1', count: 24, sizeBytes: 8.2 * TB },
    { bucket: '1-2', count: 30, sizeBytes: 10.1 * TB },
    { bucket: '2-5', count: 22, sizeBytes: 7.4 * TB },
    { bucket: '5-10', count: 9, sizeBytes: 4.2 * TB },
    { bucket: '10+', count: 5, sizeBytes: 2.9 * TB }
  ],
  ratioNullCount: 20,
  slackers: [
    { hash: 'demo0004', name: 'Demo 白嫖大片 A', sizeBytes: 210 * GB, ratio: 0.08 },
    { hash: 'demo0005', name: 'Demo 白嫖剧集 B', sizeBytes: 168 * GB, ratio: 0.21 },
    { hash: 'demo0006', name: 'Demo 摸鱼包 C', sizeBytes: 96 * GB, ratio: 0.42 }
  ],
  auxiliary: {
    totalTorrents: 128,
    crossSeedCount: 46,
    crossSeedRate: 46 / 128,
    top10: [
      { hash: 'demo0007', name: 'Demo 辅种王（8 站辅种）', auxiliarySeedCount: 8, sizeBytes: 58 * GB },
      { hash: 'demo0008', name: 'Demo 辅种亚军（5 站辅种）', auxiliarySeedCount: 5, sizeBytes: 41 * GB }
    ]
  }
}

export const DEMO_REPORT_TRACKERS: ReportsTrackersData = {
  sites: [
    { host: 'hd-alpha.example.invalid', count: 58, sizeBytes: 18.2 * TB },
    { host: 'hd-beta.example.invalid', count: 40, sizeBytes: 12.6 * TB },
    { host: 'pt-gamma.example.invalid', count: 22, sizeBytes: 6.8 * TB }
  ],
  health: [
    { host: 'hd-alpha.example.invalid', errorRate: 0.03, affectedCount: 2 },
    { host: 'hd-beta.example.invalid', errorRate: 0.18, affectedCount: 7 },
    { host: 'pt-gamma.example.invalid', errorRate: 0.62, affectedCount: 14 }
  ],
  supplyDemand: [
    { host: 'hd-alpha.example.invalid', avgSeeders: 86.4, avgLeechers: 12.2, avgDownloads: 4210.5, count: 58 },
    { host: 'hd-beta.example.invalid', avgSeeders: 44.8, avgLeechers: 6.9, avgDownloads: 1832.0, count: 40 },
    { host: 'pt-gamma.example.invalid', avgSeeders: 9.6, avgLeechers: 2.1, avgDownloads: 355.0, count: 22 }
  ]
}

const DEMO_BADGES: BadgesSummary = {
  uploadedBytes: 14.6 * TB,
  currentTier: 'gold',
  nextTier: 'platinum',
  nextTierAtTB: 50,
  equivalents: { movies: 1792, blurays: 358, tvSeasons: 478 }
}

const DEMO_GUARDIAN: GuardianSummary = {
  fireCount: 7,
  totalConsidered: 96,
  excludedCount: 32,
  top10: [
    { hash: 'demo0009', name: 'Demo 独苗火种（1 seeder）', sizeBytes: 22 * GB, minSeeders: 1 },
    { hash: 'demo0010', name: 'Demo 双苗火种（2 seeder）', sizeBytes: 18 * GB, minSeeders: 2 }
  ]
}

const DEMO_SHAME: RatioRankItem[] = [
  { hash: 'demo0004', name: 'Demo 白嫖大片 A', ratio: 0.08, sizeBytes: 210 * GB },
  { hash: 'demo0005', name: 'Demo 白嫖剧集 B', ratio: 0.21, sizeBytes: 168 * GB }
]

const DEMO_PRIDE: RatioRankItem[] = [
  { hash: 'demo0011', name: 'Demo 慈善标兵 A', ratio: 168.4, sizeBytes: 42 * GB },
  { hash: 'demo0012', name: 'Demo 慈善标兵 B', ratio: 96.2, sizeBytes: 88 * GB }
]

export const DEMO_REPORT_FUN_SUMMARY: ReportsFunSummaryData = {
  guardian: DEMO_GUARDIAN,
  badges: DEMO_BADGES,
  shame: DEMO_SHAME,
  pride: DEMO_PRIDE
}

/** 年度报告：年份参数化静态模板（2024–当前年均可呈现，无数据年份给零值形态） */
export function demoReportsYearly(year: number): ReportsFunYearlyData {
  const has = year >= 2024 && year <= 2026
  return {
    year,
    yearAdded: has ? { count: 36 + (2026 - year) * 12, sizeBytes: (14.2 - (2026 - year) * 3.6) * TB } : { count: 0, sizeBytes: 0 },
    busiestMonth: has ? { key: `${year}-08`, count: 14 } : null,
    busiestDay: has ? { key: `${year}-08-16`, count: 5 } : null,
    topSite: has ? { host: 'hd-alpha.example.invalid', sizeBytes: 5.8 * TB } : null,
    elder: has
      ? { hash: 'demo0013', name: 'Demo 元老种（开服第一播）', addedDate: `${year}-01-12 09:20:00`, seedingDays: 300 + (2026 - year) * 365 }
      : null,
    fireCount: has ? 7 : 0,
    uploadEstimate: DEMO_BADGES
  }
}

/** 速度历史假曲线：24h 纯分钟级采样太密，取 15 分钟粒度（96 点）；7d/30d hourly */
export function demoReportsSpeedHistory(range: SpeedRange, downloaderId?: string): SpeedHistory {
  const now = Date.now()
  const stepMs = range === '24h' ? 15 * 60 * 1000 : 60 * 60 * 1000
  const count = range === '24h' ? 96 : range === '7d' ? 168 : 720
  const series = [
    { id: 'demo-dl-001', name: 'Demo qB 主力', baseDown: 14, baseUp: 38 },
    { id: 'demo-dl-002', name: 'Demo TR 辅种', baseDown: 4, baseUp: 12 }
  ]
    .filter(item => !downloaderId || item.id === downloaderId)
    .map(item => ({
      downloaderId: item.id,
      nickname: item.name,
      removed: false,
      points: Array.from({ length: count }, (_, i) => {
        const t = i / count
        // 白天高峰 / 夜间低谷的双峰曲线（demo 观感）
        const wave = 0.55 + 0.45 * Math.sin(t * Math.PI * 4)
        return {
          ts: new Date(now - (count - i) * stepMs).toISOString().slice(0, 19).replace('T', ' '),
          downloadSpeed: Math.round(item.baseDown * wave * 1024 * 1024),
          uploadSpeed: Math.round(item.baseUp * wave * 1024 * 1024),
          online: true
        }
      })
    }))
  return { range, series, samplingActive: true, firstSampleAt: new Date(now - 30 * 86400 * 1000).toISOString().slice(0, 19).replace('T', ' ') }
}

/** Demo trends 视图数据（period 仅影响键形：week 形态由 month 键演示性重排） */
export function demoReportsTrends(period: TrendsPeriod, limit: number): ReportsTrendsData {
  const added = period === 'week' ? DEMO_REPORT_ADDED.map(row => ({ ...row, key: row.key.replace(/^(\d{4})-(\d{2})$/, (_, y: string, m: string) => `${y}-${String(Math.floor(Number(m) / 4)).padStart(2, '0')}`) })) : DEMO_REPORT_ADDED
  return {
    added: added.slice(-limit),
    completed: DEMO_REPORT_COMPLETED.slice(-limit),
    ageBuckets: DEMO_REPORT_AGE_BUCKETS,
    speedHistory: demoReportsSpeedHistory('24h')
  }
}
