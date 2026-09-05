/**
 * Demo Mode 的共享契约。
 *
 * 这些类型只描述脱敏的本地演示数据，不代表后端数据库模型。
 * API 层仍然沿用 { status, msg, code, data } 信封以及 list/total/pageSize
 * 分页字段，便于真实模式与 Demo 模式共用现有页面和 API 函数签名。
 */

export type DemoRouteCategory = 'core' | 'extended' | 'readonly' | 'disabled'

export interface DemoRouteDefinition {
  path: string
  title: string
  category: DemoRouteCategory
  summary: string
}

export interface DemoApiEnvelope<T> {
  status: string
  msg: string
  code: string
  data: T
}

export interface DemoPage<T> {
  total: number
  page: number
  pageSize: number
  list: T[]
}

export interface DemoUser {
  userId: string
  name: string
  roles: string[]
  avatar: string
  introduction: string
  twoFactorFlag: string
  mustChangePassword: boolean
}

export interface DemoDownloader {
  downloaderId: string
  nickname: string
  host: string
  port: string
  downloaderType: 0 | 1
  downloaderTypeName: 'qbittorrent' | 'transmission'
  isSearch: '0' | '1'
  enabled: '0' | '1'
  status: 'online' | 'offline'
  version: string
  connectStatus: '1' | '0'
  delay: number | null
  downloadSpeed: number
  uploadSpeed: number
  downloadingCount: number
  seedingCount: number
  pausedCount: number
}

export interface DemoTracker {
  trackerId: string
  trackerName: string
  trackerUrl: string
  trackerHost: string
  trackerStatus: 'working' | 'warning' | 'error'
  lastAnnounceSucceeded: string
  lastAnnounceMsg: string
  lastScrapeSucceeded: string
  lastScrapeMsg: string
  seederCount: number
  leecherCount: number
  downloadCount: number
}

export interface DemoTorrent {
  infoId: string
  downloaderId: string
  downloaderName: string
  torrentId: string
  hash: string
  name: string
  savePath: string
  size: number
  status: string
  errorReason: string | null
  hasTrackerError: boolean
  torrentFile: string
  auxiliarySeedCount: number
  addedDate: string
  completedDate: string | null
  ratio: number | null
  ratioLimit: number | null
  tags: string
  category: string
  superSeeding: boolean
  enabled: boolean
  trackerInfo: DemoTracker[]
  progress: number
  state: string
  downloadSpeed: number
  uploadSpeed: number
  downloadComplete: boolean
  peers: number
  seeds: number
  num_seeds: number
  num_leechs: number
}

export interface DemoActivity {
  time: string
  source: string
  action: string
  type: 'torrent' | 'tracker' | 'tag' | 'downloader' | 'scheduled_task' | 'system'
}

export interface DemoDashboardData {
  downloaders: {
    total: number
    online: number
    offline: number
  }
  torrents: {
    active: number
    downloading: number
    seeding: number
    paused: number
  }
  tasks: {
    total: number
    running: number
    stopped: number
  }
  system: {
    uptime: number
    uptime_display: string
    version: string
    total_download_speed: number
    total_upload_speed: number
  }
  downloader_list: Array<{
    downloader_id: string
    nickname: string
    downloader_type: 0 | 1
    status: 'online' | 'offline'
    downloading: number
    seeding: number
    paused: number
    download_speed: number
    upload_speed: number
  }>
  activities: DemoActivity[]
}

export interface DemoNotification {
  id: number
  type: 'version_update' | 'system'
  title: string
  content: string
  priority: 'info' | 'warning' | 'error'
  is_read: boolean
  extra_data: null
  created_at: string
  read_at: string | null
}

export interface DemoQueryTemplateConditions {
  source: 'simple' | 'advanced'
  version: number
  listQuery?: {
    name_like: string
    category_like: string
    tags_like: string
    downloader_id: string[]
    status: string[]
    tracker_domain: string[]
    showActiveOnly: boolean
    sort_by: string
    sort_order: 'asc' | 'desc'
  }
  condition_groups?: Array<{
    logic: 'AND' | 'OR'
    conditions: Array<{
      field: string
      operator: string
      value: string | number | boolean
    }>
  }>
}

export interface DemoQueryTemplate {
  id: string
  user_id: string
  name: string
  description: string | null
  conditions: DemoQueryTemplateConditions
  is_default: boolean
  is_public: boolean
  usage_count: number
  created_time: string
  updated_time: string | null
}

export interface DemoTask {
  taskId: number
  taskName: string
  taskCode: string
  taskStatus: number
  taskType: number
  executor: string
  enabled: boolean
  lastExecuteTime: string | null
  lastExecuteDuration: number | null
  cronPlan: string
  taskStatusName: string
  taskTypeName: string
  createTime: string
  updateTime: string
  description: string
  lastOutcome: 'success' | 'partial' | 'skipped' | 'failed' | 'no_action' | 'cancelled' | null
  lastSuccessfulDataAt: string | null
  lastAttemptAt: string | null
  lastSkipReason: string | null
  lastRunId: string | null
  freshnessSeconds: number | null
  stale: boolean
}

export interface DemoTaskLog {
  logId: number
  taskId: number
  taskName: string
  taskType: number
  startTime: string
  endTime: string
  duration: number
  success: boolean
  logDetail: string
  createTime: string
  outcome: 'success' | 'partial' | 'skipped' | 'failed' | 'no_action' | 'cancelled'
  skipReason: string | null
}

export interface DemoAuditLog {
  log_id: string
  torrent_info_id: string | null
  operation_type: string
  operation_detail: string
  old_value: string | null
  new_value: string | null
  operator: string
  operation_time: string
  operation_result: string
  error_message: string | null
  downloader_id: string | null
  create_time: string
  ip_address: null
  user_agent: null
  request_id: null
  session_id: null
  torrent_name: string | null
  downloader_name: string | null
}

export interface DemoRecycleItem {
  info_id: string
  name: string
  size: number
  save_path: string
  deleted_at: string
  downloader_name: string
  downloader_id: string
  torrent_id: string
  hash: string
}

export interface DemoOrphanFile {
  id: number
  scan_id: string
  file_path: string
  file_size: number
  hardlink_copy_count: number | null
  mtime: string | null
  downloader_id: string | null
  confidence: 'high' | 'low'
  canonical_path: string | null
  downloader_name: string | null
  is_ignored: boolean
  ignored_at: string | null
  ignored_by: string | null
  is_deleted: boolean
  deleted_at: string | null
  deleted_by: string | null
  created_at: string | null
}

export interface DemoTrackerKeyword {
  keyword_id: string
  keyword_type: 'candidate' | 'ignored' | 'success' | 'failed'
  keyword: string
  language: string
  priority: number
  enabled: boolean
  category: string
  description: string
  create_time: string
  update_time: string
}

export interface DemoTrackerMessage {
  log_id: string
  tracker_host: string
  msg: string
  first_seen: string
  last_seen: string
  occurrence_count: number
  is_processed: boolean
  keyword_type: 'success' | 'failed'
  sample_torrents: string[]
  sample_urls: string[]
  create_time: string
  update_time: string
}

export interface DemoTrackerReannounceConfig {
  config_id: string
  domain_pattern: string
  domain_display_name: string
  interval_minutes: number
  enabled: boolean
  last_reannounce_time: string
  create_time: string
  update_time: string
}

export interface DemoBackup {
  id: number
  info_hash: string
  task_name: string
  torrent_name: string
  downloader_id: number
  file_path: string
  created_at: string
  updated_at: string
  uploader_username: string
}

export interface DemoFixtureBundle {
  user: DemoUser
  downloaders: DemoDownloader[]
  torrents: DemoTorrent[]
  notifications: DemoNotification[]
  queryTemplates: DemoQueryTemplate[]
  tasks: DemoTask[]
  taskLogs: DemoTaskLog[]
  auditLogs: DemoAuditLog[]
  recycleBin: DemoRecycleItem[]
  orphanFiles: DemoOrphanFile[]
  trackerKeywords: DemoTrackerKeyword[]
  trackerMessages: DemoTrackerMessage[]
  trackerReannounceConfigs: DemoTrackerReannounceConfig[]
  backups: DemoBackup[]
  categories: string[]
  tags: string[]
  trackerDomains: string[]
}

export const DEMO_ACCESS_TOKEN = 'btdeck-demo-access-token'
export const DEMO_USER_ID = 'demo-user-001'
export const DEMO_STATE_VERSION = 'demo-state-v1'
export const DEMO_SPEED_TICK_INTERVAL = 5000

/**
 * Demo 首屏路由矩阵。扩展页面仍然可以打开，但其不可模拟动作必须通过
 * demoRequest 返回可读的本地结果或降级提示，不得调用真实后端。
 */
export const DEMO_ROUTE_MATRIX: DemoRouteDefinition[] = [
  { path: '/dashboard', title: '仪表盘', category: 'core', summary: '统计卡片、节点状态、活动时间线' },
  { path: '/downloader/index', title: '下载器', category: 'core', summary: '节点矩阵、筛选、连接测试、同步反馈' },
  { path: '/torrents/index', title: '种子列表', category: 'core', summary: '筛选、分页、排序、视图切换、详情与状态操作' },
  { path: '/torrents/traditional', title: '种子传统视图', category: 'core', summary: '与列表视图共享 Demo 种子状态' },
  { path: '/torrents/detail/:hash', title: '种子详情', category: 'core', summary: '详情、Tracker、文件和 Peers 的静态展示' },
  { path: '/query-templates/index', title: '查询模板', category: 'core', summary: '新增、编辑、应用、删除均只更新本地状态' },
  { path: 'notification-drawer', title: '通知中心', category: 'core', summary: '未读角标、详情、已读/未读、删除' },
  { path: '/tracker/*', title: 'Tracker 管理', category: 'extended', summary: '关键词、消息、汇报配置使用脱敏静态数据' },
  { path: '/tasks/index', title: '定时任务', category: 'extended', summary: '任务、日志与校验结果静态展示' },
  { path: '/logs/audit', title: '操作日志', category: 'extended', summary: '审计记录分页、筛选与本地导出' },
  { path: '/recycle-bin/index', title: '回收站', category: 'readonly', summary: '列表、恢复、清理均为本地模拟' },
  { path: '/orphan-files/index', title: '孤儿文件', category: 'readonly', summary: '扫描、筛选、清理预览为本地状态机' },
  { path: '/settings/index', title: '系统设置', category: 'readonly', summary: '显示 Demo 状态，密码/二因素不执行' },
  { path: '/torrents/file-management', title: '种子文件管理', category: 'readonly', summary: '文件选择可预览，上传/导入不产生后端副作用' },
  { path: '/login', title: '桌面登录', category: 'disabled', summary: 'Demo 构建提供进入演示入口，不执行真实认证' },
  { path: '/m/login', title: '移动登录', category: 'disabled', summary: 'Demo 构建提供进入演示入口，不执行真实认证' }
]

export const DEMO_DISABLED_CAPABILITIES = [
  '真实下载器连接、同步与速度上报',
  '真实数据库写入、认证、改密与二因素认证',
  '真实 Tracker 网络测试与重宣告',
  '真实文件系统扫描、上传、备份导入与物理删除',
  '真实 Cron/脚本执行和外部导出副作用'
] as const
