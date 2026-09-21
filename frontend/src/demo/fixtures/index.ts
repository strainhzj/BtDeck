import {
  DemoActivity,
  DemoAuditLog,
  DemoBackup,
  DemoDownloader,
  DemoFixtureBundle,
  DemoNotification,
  DemoOrphanFile,
  DemoQueryTemplate,
  DemoRecycleItem,
  DemoTask,
  DemoTaskLog,
  DemoTorrent,
  DemoTracker,
  DemoTrackerKeyword,
  DemoTrackerMessage,
  DemoTrackerReannounceConfig,
  DemoUser
} from '@/demo/types'

const DEMO_TIME = '2026-09-02T10:00:00+08:00'
const DEMO_YESTERDAY = '2026-09-01T18:30:00+08:00'

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
  hash: input.hash || `${input.infoId.replace(/[^a-z0-9]/gi, '').padEnd(40, '0').slice(0, 40)}`,
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
  tasks: DEMO_TASKS,
  taskLogs: DEMO_TASK_LOGS,
  auditLogs: DEMO_AUDIT_LOGS,
  recycleBin: DEMO_RECYCLE_BIN,
  orphanFiles: DEMO_ORPHAN_FILES,
  trackerKeywords: DEMO_TRACKER_KEYWORDS,
  trackerMessages: DEMO_TRACKER_MESSAGES,
  trackerReannounceConfigs: DEMO_TRACKER_REANNOUNCE_CONFIGS,
  backups: DEMO_BACKUPS,
  categories: ['纪录片', '电影', '音乐', '软件', '课程', '动画', '影像', '剧集', '素材'],
  tags: ['演示', '高清', '音乐', '待处理', '学习', '检查中', '队列', '连续剧', '摄影'],
  trackerDomains: ['tracker-alpha.example.invalid', 'tracker-beta.example.invalid']
}

export default DEMO_FIXTURE_BUNDLE
