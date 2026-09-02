import type { AxiosRequestConfig } from 'axios'
import { ApiError } from '@/types/api'
import { demoSession, emitDemoReset } from '@/demo/config'
import {
  demoStore,
  DemoDownloaderInput,
  DemoPageParams,
  DemoTemplateInput,
  DemoTorrentQuery
} from '@/demo/demo-store'
import {
  DemoApiEnvelope,
  DemoDashboardData,
  DemoDownloader,
  DemoOrphanFile,
  DemoTorrent
} from '@/demo/types'

export type DemoRequestConfig = AxiosRequestConfig & {
  data?: unknown
  params?: unknown
}

export type DemoRequestClient = <T = DemoApiEnvelope<unknown>>(config: DemoRequestConfig) => Promise<T>

type DemoRecord = Record<string, unknown>

const isRecord = (value: unknown): value is DemoRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const asRecord = (value: unknown): DemoRecord => isRecord(value) ? value : {}

const asString = (value: unknown, fallback = ''): string => {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return fallback
}

const containsTextValue = (value: string | null | undefined, query: string | undefined): boolean =>
  !query || Boolean(value && value.toLowerCase().includes(query.toLowerCase()))

const asNumber = (value: unknown, fallback = 0): number => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }
  return fallback
}

const asBoolean = (value: unknown, fallback = false): boolean => {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') return ['1', 'true', 'yes'].includes(value.toLowerCase())
  return fallback
}

const asStringArray = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map(item => asString(item)).filter(Boolean)
  if (typeof value === 'string') return value.split(',').map(item => item.trim()).filter(Boolean)
  return []
}

const asStringFilter = (value: unknown): string | string[] | undefined => {
  if (Array.isArray(value)) return asStringArray(value)
  if (typeof value === 'string' && value.includes(',')) return asStringArray(value)
  if (typeof value === 'string' && value) return value
  return undefined
}

const normalizePath = (url: string): string => {
  const withoutQuery = url.split('?')[0] || '/'
  const withoutOrigin = withoutQuery.replace(/^https?:\/\/[^/]+/i, '')
  const withoutApiPrefix = withoutOrigin.replace(/^\/api\/v1(?=\/|$)/, '')
  return withoutApiPrefix.startsWith('/') ? withoutApiPrefix : `/${withoutApiPrefix}`
}

const readInput = (config: DemoRequestConfig): DemoRecord => ({
  ...asRecord(config.params),
  ...asRecord(config.data)
})

const success = <T>(data: T, msg = 'Demo 数据已就绪'): DemoApiEnvelope<T> => ({
  status: 'success',
  msg,
  code: '200',
  data
})

const unsupported = (method: string, path: string): DemoApiEnvelope<DemoRecord> => success(
  { demo: true, supported: false, method, path },
  'Demo 模式：该操作仅提供本地展示结果，未执行真实副作用'
)

const demoBlob = (path: string): Blob => new Blob([
  `BtDeck Demo export\npath=${path}\nstate=${demoSession.stateVersion}\n`
], { type: 'text/plain;charset=utf-8' })

const extractPathId = (path: string, prefix: string): string =>
  decodeURIComponent(path.slice(prefix.length).replace(/^\//, '').split('/')[0] || '')

type DemoDownloaderPayload = DemoDownloader & {
  id: string
  type: string
  is_ssl: '0' | '1'
  is_search: '0' | '1'
  downloader_type: 0 | 1
  username: string
  isSsl: '0' | '1'
  isSearch: '0' | '1'
  torrentSavePath: string
  pathMappingRules: string
}

const toDownloaderPayload = (item: DemoDownloader): DemoDownloaderPayload => ({
  ...item,
  id: item.downloaderId,
  type: item.downloaderTypeName,
  is_ssl: item.port === '443' ? '1' : '0',
  is_search: item.isSearch,
  downloader_type: item.downloaderType,
  username: 'demo-user',
  isSsl: item.port === '443' ? '1' : '0',
  isSearch: item.isSearch,
  torrentSavePath: `/demo/${item.downloaderId}/downloads`,
  pathMappingRules: ''
})

const toDownloaderInput = (input: DemoRecord): DemoDownloaderInput => ({
  id: asString(input.id) || undefined,
  nickname: asString(input.nickname) || undefined,
  host: asString(input.host) || undefined,
  port: input.port === undefined ? undefined : asString(input.port),
  downloaderType: asNumber(input.downloaderType, asNumber(input.downloader_type, 0)) === 1 ? 1 : 0,
  isSearch: asString(input.isSearch || input.is_search) === '0' ? '0' : '1',
  isSsl: asString(input.isSsl || input.is_ssl) === '1' ? '1' : '0',
  enabled: input.enabled === undefined ? undefined : asBoolean(input.enabled) ? '1' : '0'
})

const toTorrentPayload = (item: DemoTorrent): DemoTorrent & {
  info_id: string
  downloader_id: string
  downloader_name: string
  torrent_id: string
  save_path: string
  added_date: string
  completed_date: string | null
  download_speed: number
  upload_speed: number
  download_complete: boolean
  ratio_limit: number | null
  tracker_info: DemoTorrent['trackerInfo']
} => ({
  ...item,
  info_id: item.infoId,
  downloader_id: item.downloaderId,
  downloader_name: item.downloaderName,
  torrent_id: item.torrentId,
  save_path: item.savePath,
  added_date: item.addedDate,
  completed_date: item.completedDate,
  download_speed: item.downloadSpeed,
  upload_speed: item.uploadSpeed,
  download_complete: item.downloadComplete,
  ratio_limit: item.ratioLimit,
  tracker_info: item.trackerInfo
})

const toPageParams = (input: DemoRecord): DemoPageParams => ({
  page: asNumber(input.page, 1),
  pageSize: asNumber(input.pageSize, asNumber(input.page_size, asNumber(input.limit, 10))),
  page_size: asNumber(input.page_size, 0) || undefined,
  limit: asNumber(input.limit, 0) || undefined,
  search: asString(input.search) || undefined
})

const toTorrentQuery = (input: DemoRecord): DemoTorrentQuery => {
  const pageSize = asNumber(input.pageSize, asNumber(input.page_size, asNumber(input.limit, 10)))
  const skip = asNumber(input.skip, 0)
  return {
    ...toPageParams(input),
    page: input.page === undefined ? Math.floor(skip / pageSize) + 1 : asNumber(input.page, 1),
    pageSize,
    name: asString(input.name) || undefined,
    name_like: asString(input.name_like) || undefined,
    downloader_id: asStringFilter(input.downloader_id),
    status: asStringFilter(input.status),
    category: asString(input.category) || asString(input.category_like) || undefined,
    tags: asString(input.tags) || asString(input.tags_like) || undefined,
    tracker_domain: asStringFilter(input.tracker_domain),
    showActiveOnly: asBoolean(input.showActiveOnly) || asBoolean(input.active_only),
    active_only: asBoolean(input.active_only),
    sort_by: asString(input.sort_by) || undefined,
    sort_order: asString(input.sort_order) === 'asc' ? 'asc' : 'desc'
  }
}

const toTemplateInput = (input: DemoRecord): DemoTemplateInput => ({
  name: asString(input.name) || undefined,
  description: input.description === null ? null : asString(input.description) || undefined,
  conditions: isRecord(input.conditions) ? input.conditions as unknown as DemoTemplateInput['conditions'] : undefined,
  is_public: input.is_public === undefined ? undefined : asBoolean(input.is_public)
})

const buildDownloaderSettings = (downloaderId: string): DemoRecord => ({
  downloader_id: downloaderId,
  username: 'demo-user',
  override_local: false,
  dlSpeedLimit: 0,
  ulSpeedLimit: 0,
  dlSpeedUnit: 1,
  ulSpeedUnit: 1,
  enableSchedule: false,
  max_connections: 200,
  max_connections_per_torrent: 50,
  dht_enabled: true,
  lsd_enabled: true,
  utp_enabled: true,
  path_mapping: { mappings: [] },
  schedule_rules: []
})

const buildTaskResult = (taskId: number, action: string): DemoRecord => ({
  success: true,
  demo: true,
  task_id: taskId,
  action,
  message: 'Demo 模式：仅更新本地状态'
})

const KEYWORD_POOL_TYPES = ['candidate', 'ignored', 'success', 'failed'] as const
type DemoKeywordPool = typeof KEYWORD_POOL_TYPES[number]

const asKeywordPool = (value: unknown): DemoKeywordPool => {
  const candidate = asString(value)
  return (KEYWORD_POOL_TYPES as readonly string[]).includes(candidate)
    ? candidate as DemoKeywordPool
    : 'candidate'
}

const toOrphanQuery = (input: DemoRecord) => ({
  ...toPageParams(input),
  is_ignored: input.is_ignored === undefined ? undefined : asBoolean(input.is_ignored),
  confidence: asStringFilter(input.confidence),
  status: asStringFilter(input.status),
  downloader_id: asStringFilter(input.downloader_id),
  path_like: asString(input.path_like) || undefined,
  hardlink_copies: asString(input.hardlink_copies) === 'located' ? 'located' as const : undefined
})

const buildDemoOrphanScan = (scanId = 'demo-scan-001'): DemoRecord => {
  const files = demoStore.snapshot().orphanFiles
  const activeFiles = files.filter(item => !item.is_deleted)
  return {
    scan_id: scanId,
    scan_time: '2026-09-02T03:00:00+08:00',
    scan_type: 'demo',
    total_paths_scanned: 3,
    total_files_scanned: files.length,
    total_orphans: activeFiles.length,
    total_orphan_size: activeFiles.reduce((total, item) => total + item.file_size, 0),
    status: 'completed',
    error_message: null,
    operator: '演示管理员',
    details_mode: 'snapshot',
    new_orphans: 2,
    known_orphans: 1,
    resolved_orphans: 0,
    cleanup_review_required: false,
    cleanup_reviewed_at: null,
    cleanup_reviewed_by: null,
    cleanup_review_note: null,
    created_at: '2026-09-02T03:00:00+08:00'
  }
}

const buildDemoOrphanContext = (): DemoRecord => {
  const files = demoStore.snapshot().orphanFiles
  const remaining = files.filter(item => !item.is_deleted)
  const pending = remaining.filter(item => !item.is_ignored)
  const scan = buildDemoOrphanScan()
  return {
    latest_attempt: scan,
    display_scan: scan,
    remaining_count: remaining.length,
    remaining_size: remaining.reduce((total, item) => total + item.file_size, 0),
    ignored_count: remaining.filter(item => item.is_ignored).length,
    cleanup_allowed: pending.length > 0,
    cleanup_block_reason: pending.length > 0 ? null : '当前没有可清理的待处理文件'
  }
}

const matchesOrphanSelection = (item: DemoOrphanFile, filters: DemoRecord): boolean => {
  const statuses = asStringArray(filters.status)
  const statusMatch = statuses.length === 0 || statuses.some(status =>
    status === 'pending' ? !item.is_ignored && !item.is_deleted
      : status === 'ignored' ? item.is_ignored && !item.is_deleted
        : status === 'deleted' ? item.is_deleted
          : false
  )
  const downloaderIds = asStringArray(filters.downloader_id)
  return statusMatch &&
    (downloaderIds.length === 0 || downloaderIds.includes(item.downloader_id || '')) &&
    (!filters.path_like || item.file_path.includes(asString(filters.path_like))) &&
    (!filters.path_prefix || item.file_path.startsWith(asString(filters.path_prefix))) &&
    (!filters.confidence || asStringArray(filters.confidence).includes(item.confidence)) &&
    (asString(filters.hardlink_copies) !== 'located' || (item.hardlink_copy_count || 0) > 0)
}

const getSelectedOrphans = (input: DemoRecord): DemoOrphanFile[] => {
  const files = demoStore.snapshot().orphanFiles
  const ids = Array.isArray(input.orphan_ids) ? input.orphan_ids.map(item => asNumber(item)) : []
  if (ids.length > 0) return files.filter(item => ids.includes(item.id))
  if (!asBoolean(input.select_all)) return []
  const filters = isRecord(input.filters) ? input.filters : input
  const excluded = new Set(Array.isArray(input.excluded_orphan_ids)
    ? input.excluded_orphan_ids.map(item => asNumber(item))
    : [])
  return files.filter(item => !excluded.has(item.id) && matchesOrphanSelection(item, filters))
}

const buildOrphanCleanupJob = (input: DemoRecord): DemoRecord => {
  const selected = getSelectedOrphans(input)
  const result = demoStore.cleanupOrphanFiles(selected.map(item => item.id))
  const taskId = result.success_count > 0 ? 'demo-orphan-cleanup-001' : null
  return {
    task_id: taskId,
    operation_type: 'cleanup',
    status: result.failed_count > 0 ? 'partial' : 'completed',
    scan_id: asString(input.scan_id) || 'demo-scan-001',
    total_count: selected.length,
    requested_count: selected.length,
    accepted_count: result.success_count,
    skipped_count: 0,
    skipped_items: [],
    success_count: result.success_count,
    purged_count: result.success_count,
    failed_count: result.failed_count,
    failed_list: result.failed_list,
    total_size: result.total_size,
    error_message: null,
    created_at: '2026-09-02T10:05:00+08:00',
    started_at: '2026-09-02T10:05:00+08:00',
    completed_at: '2026-09-02T10:05:01+08:00'
  }
}

const handleDemoRequest = (config: DemoRequestConfig): unknown => {
  const method = (config.method || 'get').toUpperCase()
  const path = normalizePath(asString(config.url, '/'))
  const input = readInput(config)

  if (path === '/demo/reset' && method === 'POST') {
    demoStore.reset()
    emitDemoReset()
    return success({ reset: true, stateVersion: demoSession.stateVersion }, 'Demo 数据已重置')
  }

  if (path === '/demo/error') {
    throw new ApiError('Demo 模式模拟业务错误', { code: '422', httpStatus: 200 })
  }

  if (config.responseType === 'blob') return demoBlob(path)

  if (path === '/auth/login' && method === 'POST') {
    return success([{
      access_token: demoSession.token,
      refresh_token: '',
      token_type: 'bearer',
      user_id: demoSession.userId
    }], 'Demo 登录已模拟完成')
  }
  if (path === '/auth/refresh' && method === 'POST') {
    return success([{ access_token: demoSession.token, refresh_token: '' }], 'Demo 续期已模拟完成')
  }
  if (path === '/users/info' && method === 'GET') return success({ user: demoStore.snapshot().user })
  if (path === '/users/logout' && method === 'POST') return success({ success: true, demo: true }, 'Demo 已退出本地会话')

  if (path === '/dashboard' && method === 'GET') {
    return success<DemoDashboardData>(demoStore.getDashboardData())
  }

  if (path === '/downloader/getList') {
    const enabled = input.enabled === undefined ? undefined : asBoolean(input.enabled)
    return success(demoStore.listDownloaders({ enabled }).map(toDownloaderPayload))
  }
  if (path.startsWith('/downloader/detail/') && method === 'GET') {
    const item = demoStore.getDownloader(extractPathId(path, '/downloader/detail/'))
    return success(item ? [toDownloaderPayload(item)] : [])
  }
  if (path === '/downloader/getStatusAll' && method === 'GET') {
    return success(demoStore.listDownloaderStatuses().map(item => ({
      ...item,
      connectStatus: item.connectStatus === '1' ? 'connected' : 'error',
      downloadSpeed: `${Math.round(item.downloadSpeed / 1024 / 1024)} MB/s`,
      uploadSpeed: `${Math.round(item.uploadSpeed / 1024 / 1024)} MB/s`
    })))
  }
  if (path.startsWith('/downloader/getStatus/') && method === 'GET') {
    const id = extractPathId(path, '/downloader/getStatus/')
    const item = demoStore.listDownloaderStatuses().find(status => status.id === id)
    return success(item || { id, connectStatus: 'error', delay: null })
  }
  if (path.startsWith('/downloader/test/') && method === 'POST') {
    const id = extractPathId(path, '/downloader/test/')
    const item = demoStore.getDownloader(id)
    return success({
      success: item?.status === 'online',
      delay: item?.delay || undefined,
      message: item?.status === 'online' ? 'Demo 节点连接成功' : 'Demo 节点离线，未执行真实连接测试'
    })
  }
  if (path === '/downloader/add' && method === 'POST') {
    return success(toDownloaderPayload(demoStore.createDownloader(toDownloaderInput(input))), 'Demo 下载器已添加到本地展示')
  }
  if (path.startsWith('/downloader/update/') && method === 'POST') {
    const id = extractPathId(path, '/downloader/update/')
    const item = demoStore.updateDownloader(id, toDownloaderInput(input))
    return success(item ? toDownloaderPayload(item) : { success: false, demo: true }, 'Demo 下载器已更新')
  }
  if (path.startsWith('/downloader/delete/') && method === 'DELETE') {
    const id = extractPathId(path, '/downloader/delete/')
    return success({ success: demoStore.deleteDownloader(id), demo: true }, 'Demo 下载器已从本地展示移除')
  }
  if (path === '/torrents/sync-single' && method === 'POST') {
    const downloaderId = asString(input.downloader_id, 'demo-downloader-001')
    return success({
      task_id: `demo-sync-${downloaderId}`,
      downloader_id: downloaderId,
      nickname: demoStore.getDownloader(downloaderId)?.nickname || 'Demo 节点',
      status: 'pending',
      query_url: '/demo/sync-status',
      message: 'Demo 模式：同步任务仅在本地模拟'
    })
  }
  if (path.startsWith('/torrents/sync-status/') && method === 'GET') {
    return success({
      task_id: extractPathId(path, '/torrents/sync-status/'),
      task_type: 'demo_sync',
      downloader_id: 'demo-downloader-001',
      downloader_nickname: 'Demo 节点 A',
      status: 'success',
      created_at: '2026-09-02T10:00:00+08:00',
      started_at: '2026-09-02T10:00:01+08:00',
      finished_at: '2026-09-02T10:00:02+08:00',
      progress: 100,
      result: { status: 'success', message: 'Demo 同步完成' },
      error: null,
      execution_time: 1000
    })
  }
  if (path.startsWith('/downloaders/') && path.endsWith('/settings')) {
    const downloaderId = path.split('/')[2] || 'demo-downloader-001'
    return success(buildDownloaderSettings(downloaderId), 'Demo 设置已加载')
  }
  if (path.startsWith('/downloaders/') && path.includes('/settings/')) {
    return success({ success: true, demo: true }, 'Demo 模式：设置操作仅在本地展示')
  }
  if (path.startsWith('/downloader/') && path.endsWith('/path-mapping') && method === 'GET') {
    return success({ mappings: [] }, 'Demo 路径映射已加载')
  }
  if (path.startsWith('/downloader/') && path.endsWith('/path-mapping/test')) {
    return success({ success: true, message: 'Demo 路径映射校验通过，未读取真实文件系统' })
  }
  if (path.startsWith('/downloaders/') && path.endsWith('/capabilities')) {
    const downloaderId = path.split('/')[2] || 'demo-downloader-001'
    return success({
      downloader_id: downloaderId,
      downloader_type: 0,
      supports_speed_scheduling: true,
      supports_connection_limits: true,
      supports_queue_management: true,
      supports_path_mapping: true,
      supports_advanced_options: true
    })
  }
  if (path === '/setting-templates' || path.startsWith('/setting-templates/')) {
    if (method === 'GET') return success({ total: 0, page: 1, pageSize: 10, list: [] })
    return success({ success: true, demo: true }, 'Demo 模式：设置模板操作仅在本地展示')
  }

  if (path === '/torrents/getList' || path === '/advanced-search/advanced-search') {
    const page = demoStore.listTorrents(toTorrentQuery(input))
    return success({ ...page, list: page.list.map(toTorrentPayload) })
  }
  if (path === '/torrents/tracker-domains' && method === 'GET') return success(demoStore.getTrackerDomains())
  if (path === '/torrents/active-torrents' && method === 'GET') {
    const items = demoStore.snapshot().torrents.filter(item => item.downloadSpeed > 0 || item.uploadSpeed > 0)
    return success(items.map(item => ({
      hash: item.hash,
      downloaderId: item.downloaderId,
      downloader_id: item.downloaderId,
      downloadSpeed: item.downloadSpeed,
      uploadSpeed: item.uploadSpeed,
      progress: item.progress,
      status: item.status,
      downloadComplete: item.downloadComplete,
      download_complete: item.downloadComplete,
      num_seeds: item.num_seeds,
      num_leechs: item.num_leechs
    })))
  }
  if (path === '/torrents/runtime-state/reconcile' && method === 'POST') {
    const requested = Array.isArray(input.items) ? input.items.filter(isRecord) : []
    const found = requested.map(item => demoStore.getTorrent(asString(item.hash))).filter((item): item is DemoTorrent => Boolean(item))
    return success({
      list: found.map(item => ({
        hash: item.hash,
        downloaderId: item.downloaderId,
        downloadSpeed: item.downloadSpeed,
        uploadSpeed: item.uploadSpeed,
        progress: item.progress,
        status: item.status,
        downloadComplete: item.downloadComplete,
        num_seeds: item.num_seeds,
        num_leechs: item.num_leechs
      })),
      missing: requested.filter(item => !demoStore.getTorrent(asString(item.hash)))
    })
  }
  if (path === '/torrents/pause' || path === '/torrents/resume' || path === '/torrents/recheck') {
    const status = path.endsWith('/pause') ? 'paused' : path.endsWith('/resume') ? 'downloading' : 'checking'
    const changed = demoStore.updateTorrentState(asStringArray(input.hashes), status)
    return success({ success: true, updated_count: changed.length, demo: true }, 'Demo 种子状态已更新')
  }
  if (path === '/torrents/delete' || path === '/torrents/delete-with-level') {
    const identifiers = path.endsWith('/delete')
      ? asStringArray(input.info_id)
      : asStringArray(input.torrent_info_ids)
    const deleteLevel = path.endsWith('/delete')
      ? asNumber(input.id_recycle, 0) === 1 ? 3 : 4
      : asNumber(input.delete_level, 4)
    return success(demoStore.deleteTorrents(identifiers, deleteLevel), 'Demo 删除操作已完成')
  }
  if (path === '/torrents/delete-batch-async' && method === 'POST') {
    const identifiers = asStringArray(input.torrent_info_ids)
    const result = demoStore.deleteTorrents(identifiers, asNumber(input.delete_level, 4))
    return success({
      task_id: null,
      total_count: identifiers.length,
      requested_count: identifiers.length,
      accepted_count: result.success_count,
      skipped_count: result.failed_count,
      skipped_info_ids: [],
      delete_level: asNumber(input.delete_level, 4)
    }, 'Demo 批量删除任务已模拟完成')
  }
  if (path.startsWith('/torrents/delete-batch-status/') && method === 'GET') {
    const taskId = extractPathId(path, '/torrents/delete-batch-status/')
    return success({ task_id: taskId, status: 'completed', total_count: 0, requested_count: 0, accepted_count: 0, skipped_count: 0, skipped_info_ids: [], success_count: 0, failed_count: 0, results: [], failed_items: [] })
  }
  if (path === '/advanced-search/search-templates') {
    if (method === 'GET') return success(demoStore.listTemplates())
    if (method === 'POST') return success(demoStore.createTemplate(toTemplateInput(input)), 'Demo 模板已创建')
  }
  if (path.startsWith('/advanced-search/search-templates/')) {
    const suffix = path.slice('/advanced-search/search-templates/'.length)
    const templateId = suffix.split('/')[0]
    if (suffix.endsWith('/apply') && method === 'POST') {
      const template = demoStore.applyTemplate(templateId)
      return success(template ? {
        id: template.id,
        name: template.name,
        description: template.description,
        conditions: template.conditions
      } : null, 'Demo 模板已应用')
    }
    if (method === 'PUT') return success(demoStore.updateTemplate(templateId, toTemplateInput(input)), 'Demo 模板已更新')
    if (method === 'DELETE') return success({ success: demoStore.deleteTemplate(templateId), demo: true }, 'Demo 模板已删除')
  }
  if (path === '/advanced-search/search-preview') {
    const page = demoStore.listTorrents(toTorrentQuery(input))
    return success({ total: page.total, list: page.list.map(toTorrentPayload) })
  }
  if (path === '/torrents/duplicates') return success({ total: 0, groups: [] })
  if (path.includes('/torrents/duplicates/')) return success({ success: true, demo: true }, 'Demo 重复种子操作已模拟完成')
  if (path.startsWith('/tracker/') || path.startsWith('/torrent-status/')) {
    return success({ success: true, demo: true }, 'Demo Tracker 操作已降级为本地反馈')
  }
  if (path.startsWith('/torrents/transfer') || path === '/torrents/set-location') {
    return success({ success: true, demo: true }, 'Demo 模式：操作未访问真实下载器')
  }
  if (path === '/torrents/backup') return success({ total: demoStore.snapshot().backups.length, page: 1, pageSize: 20, list: demoStore.snapshot().backups })

  if (path === '/notifications' && method === 'GET') {
    const page = demoStore.getNotifications({
      ...toPageParams(input),
      type: asString(input.type) || undefined,
      is_read: input.is_read === undefined ? undefined : asBoolean(input.is_read)
    })
    return success(page)
  }
  if (path === '/notifications/unread-count' && method === 'GET') return success({ count: demoStore.getUnreadNotificationCount() })
  if (path === '/notifications/mark-read' || path === '/notifications/mark-unread') {
    const item = demoStore.markNotification(asNumber(input.notification_id), path.endsWith('mark-read'))
    return success(item || { success: false, demo: true }, 'Demo 通知状态已更新')
  }
  if (path === '/notifications/read-all') return success({ count: demoStore.markAllNotificationsRead() }, 'Demo 通知已全部标记为已读')
  if (path.startsWith('/notifications/') && method === 'DELETE') {
    return success({ success: demoStore.deleteNotification(asNumber(extractPathId(path, '/notifications/'))), demo: true }, 'Demo 通知已删除')
  }

  if (path === '/tracker-keywords' && method === 'GET') return success(demoStore.listTrackerKeywords({ ...toPageParams(input), keyword_type: asString(input.keyword_type) || undefined }))
  if (path === '/tracker-keywords' && method === 'POST') {
    return success(demoStore.createTrackerKeyword({
      keyword_type: asKeywordPool(input.keyword_type),
      keyword: asString(input.keyword) || undefined,
      language: asString(input.language) || undefined,
      priority: input.priority === undefined ? undefined : asNumber(input.priority),
      enabled: input.enabled === undefined ? undefined : asBoolean(input.enabled),
      category: asString(input.category) || undefined,
      description: asString(input.description) || undefined
    }), 'Demo 关键词已创建')
  }
  if (path === '/tracker-keywords/pool' && method === 'GET') {
    const poolType = asKeywordPool(input.pool_type)
    return success(demoStore.listPoolKeywords(poolType, {
      ...toPageParams(input),
      keyword: asString(input.keyword) || undefined
    }))
  }
  if (path === '/tracker-keywords/pool/statistics' && method === 'GET') {
    const keywords = demoStore.snapshot().trackerKeywords
    return success({
      candidate_count: keywords.filter(item => item.keyword_type === 'candidate').length,
      ignored_count: keywords.filter(item => item.keyword_type === 'ignored').length,
      success_count: keywords.filter(item => item.keyword_type === 'success').length,
      failed_count: keywords.filter(item => item.keyword_type === 'failed').length
    })
  }
  if (path === '/tracker-keywords/pool/search-all' && method === 'GET') {
    const requestedPools = asStringArray(input.pool_types)
    const keywords = demoStore.snapshot().trackerKeywords.filter(item =>
      (requestedPools.length === 0 || requestedPools.includes(item.keyword_type)) &&
      containsTextValue(item.keyword, asString(input.keyword) || undefined)
    )
    const page = Math.max(1, asNumber(input.page, 1))
    const pageSize = Math.max(1, asNumber(input.page_size, asNumber(input.pageSize, 20)))
    const start = (page - 1) * pageSize
    const poolLabels: Record<DemoKeywordPool, string> = {
      candidate: '候选池',
      ignored: '忽略池',
      success: '成功池',
      failed: '失败池'
    }
    return success({
      total: keywords.length,
      page,
      pageSize,
      list: keywords.slice(start, start + pageSize).map(item => ({
        keyword_id: item.keyword_id,
        keyword: item.keyword,
        pool_type: item.keyword_type,
        pool_label: poolLabels[item.keyword_type],
        create_time: item.create_time
      }))
    })
  }
  if (path === '/tracker-keywords/pool/prefix-match-preview' && method === 'POST') {
    const matches = demoStore.prefixMatchTrackerKeywords(asKeywordPool(input.pool_type), asString(input.prefix))
    return success({
      count: matches.length,
      sample_keywords: matches.slice(0, 10).map(item => item.keyword),
      keyword_ids: matches.map(item => item.keyword_id)
    })
  }
  if (path === '/tracker-keywords/move' && method === 'POST') {
    const item = demoStore.moveTrackerKeyword(asString(input.keyword_id), asKeywordPool(input.target_pool))
    return success({ success: Boolean(item), keyword: item, demo: true }, 'Demo 关键词已移动')
  }
  if (path === '/tracker-keywords/batch-move' && method === 'POST') {
    const ids = asStringArray(input.keyword_ids)
    const targetPool = asKeywordPool(input.target_pool)
    const successCount = ids.filter(id => Boolean(demoStore.moveTrackerKeyword(id, targetPool))).length
    return success({ success_count: successCount, failed_count: ids.length - successCount, results: [] }, 'Demo 关键词批量移动已完成')
  }
  if (path === '/tracker-keywords/batch' && method === 'POST') {
    const keywords = Array.isArray(input.keywords) ? input.keywords.filter(isRecord) : []
    const created = keywords.map(item => demoStore.createTrackerKeyword({
      keyword_type: asKeywordPool(item.keyword_type),
      keyword: asString(item.keyword),
      language: asString(item.language) || undefined,
      priority: item.priority === undefined ? undefined : asNumber(item.priority),
      enabled: item.enabled === undefined ? undefined : asBoolean(item.enabled),
      category: asString(item.category) || undefined,
      description: asString(item.description) || undefined
    }))
    return success({ success_count: created.length, failed_count: 0, keyword_ids: created.map(item => item.keyword_id) }, 'Demo 关键词批量导入已完成')
  }
  if (path === '/tracker-keywords/batch/delete' && method === 'POST') {
    const ids = asStringArray(input.keyword_ids)
    const successCount = ids.filter(id => demoStore.deleteTrackerKeyword(id)).length
    return success({ success_count: successCount, failed_count: ids.length - successCount }, 'Demo 关键词批量删除已完成')
  }
  if (path.startsWith('/tracker-keywords/') && method === 'GET') {
    const item = demoStore.snapshot().trackerKeywords.find(keyword =>
      keyword.keyword_id === extractPathId(path, '/tracker-keywords/'))
    return success(item || null)
  }
  if (path.startsWith('/tracker-keywords/') && method === 'PUT') {
    const item = demoStore.updateTrackerKeyword(extractPathId(path, '/tracker-keywords/'), {
      keyword_type: input.keyword_type === undefined ? undefined : asKeywordPool(input.keyword_type),
      keyword: input.keyword === undefined ? undefined : asString(input.keyword),
      language: input.language === undefined ? undefined : asString(input.language),
      priority: input.priority === undefined ? undefined : asNumber(input.priority),
      enabled: input.enabled === undefined ? undefined : asBoolean(input.enabled),
      category: input.category === undefined ? undefined : asString(input.category),
      description: input.description === undefined ? undefined : asString(input.description)
    })
    return success(item || { success: false, demo: true }, 'Demo 关键词已更新')
  }
  if (path.startsWith('/tracker-keywords/') && method === 'DELETE') {
    return success({ success: demoStore.deleteTrackerKeyword(extractPathId(path, '/tracker-keywords/')), demo: true }, 'Demo 关键词已删除')
  }
  if (path === '/tracker-messages' && method === 'GET') return success(demoStore.listTrackerMessages({ ...toPageParams(input), keyword_type: asString(input.keyword_type) || undefined }))
  if (path === '/tracker-messages/statistics') {
    const messages = demoStore.snapshot().trackerMessages
    return success({
      total: messages.length,
      unprocessed: messages.filter(item => !item.is_processed).length,
      success: messages.filter(item => item.keyword_type === 'success').length,
      failure: messages.filter(item => item.keyword_type === 'failed').length
    })
  }
  if (path === '/tracker-test/match' && method === 'POST') return success({
    result: 'success',
    matched_keywords: demoStore.snapshot().trackerKeywords.filter(item => item.keyword_type === 'success'),
    unmatched_reason: undefined
  }, 'Demo 匹配测试已完成，未访问外部 Tracker')
  if (path === '/tracker-messages/batch/delete' || path === '/tracker-messages/batch/add-to-pool') {
    const ids = asStringArray(input.log_ids)
    return success({ success_count: ids.length, failed_count: 0, processed_count: ids.length }, 'Demo Tracker 消息操作已完成')
  }
  if (path.startsWith('/tracker-messages/') && method === 'GET') {
    const item = demoStore.snapshot().trackerMessages.find(message =>
      message.log_id === extractPathId(path, '/tracker-messages/'))
    return success(item || null)
  }
  if (path.startsWith('/tracker-messages/')) return success({ success: true, demo: true }, 'Demo Tracker 消息已更新')
  if (path === '/tracker-reannounce/configs' && method === 'GET') return success(demoStore.listReannounceConfigs(toPageParams(input)))
  if (path.startsWith('/tracker-reannounce/')) return success({ success: true, demo: true }, 'Demo Tracker 数据已更新')

  if (path === '/cronTasks/list' || path === '/cronTasks/logs') {
    return success(path.endsWith('/logs') ? demoStore.listTaskLogs(toPageParams(input)) : demoStore.listTasks(toPageParams(input)))
  }
  if (path === '/cronTasks/logs/statistics') {
    const totalLogs = demoStore.snapshot().taskLogs.length
    const successLogs = demoStore.snapshot().taskLogs.filter(log => log.success).length
    return success({
      total_logs: totalLogs,
      success_logs: successLogs,
      error_logs: totalLogs - successLogs,
      storage_usage: 0,
      last_7_days: [0, 0, 0, 1, 0, 1, 0],
      log_levels: { info: totalLogs },
      totalLogs,
      successLogs,
      failedLogs: totalLogs - successLogs,
      todayLogs: totalLogs
    })
  }
  if (path === '/cronTasks/validation/cron' && method === 'POST') return success({
    valid: true,
    message: 'Demo Cron 表达式有效',
    executionTimes: {
      nextExecutionTime: '2026-09-02T11:00:00+08:00',
      executionTimes: []
    }
  })
  if (path === '/cronTasks/validation/script' && method === 'POST') return success({
    valid: true,
    errors: [],
    message: 'Demo 脚本校验通过，未执行脚本'
  })
  if (path === '/cronTasks/validation/python-class' && method === 'POST') return success({
    valid: true,
    exists: true,
    classInfo: {
      className: 'DemoTask',
      module: 'btdeck.demo',
      description: '仅用于演示表单校验的本地类信息',
      methods: ['run'],
      parameters: {}
    },
    message: 'Demo 类路径仅作展示'
  })
  if (path === '/cronTasks/config/task-types' && method === 'GET') return success({
    taskTypes: [
      { value: 0, label: 'Shell', icon: 'terminal', description: '演示 Shell 任务', language: 'shell', fileExtension: '.sh' },
      { value: 3, label: 'Python', icon: 'code', description: '演示 Python 任务', language: 'python', fileExtension: '.py' },
      { value: 4, label: 'Python 内部类', icon: 'box', description: '演示内部任务类', language: 'python' }
    ],
    pythonClasses: []
  })
  if (path === '/cronTasks/cleanup/preview' && method === 'POST') {
    const items = demoStore.snapshot().recycleBin
    const level3Items = items.slice(0, 1).map(item => ({ name: item.name, size: Number((item.size / 1024 / 1024 / 1024).toFixed(2)) }))
    const level4Items = items.slice(1).map(item => ({ name: item.name, size: Number((item.size / 1024 / 1024 / 1024).toFixed(2)) }))
    return success({
      level3_count: level3Items.length,
      level4_count: level4Items.length,
      total_count: items.length,
      total_size_gb: Number((items.reduce((total, item) => total + item.size, 0) / 1024 / 1024 / 1024).toFixed(2)),
      level3_items: level3Items,
      level4_items: level4Items
    }, 'Demo 清理预览已生成')
  }
  if (path === '/cronTasks/add' && method === 'POST') {
    return success(demoStore.createTask({
      task_name: asString(input.task_name),
      task_code: asString(input.task_code),
      task_type: asNumber(input.task_type, 0),
      executor: asString(input.executor),
      cron_plan: asString(input.cron_plan),
      enabled: input.enabled === undefined ? undefined : asBoolean(input.enabled),
      description: asString(input.description) || undefined
    }), 'Demo 任务已创建')
  }
  if (path.startsWith('/cronTasks/') && method === 'GET') {
    const taskId = asNumber(extractPathId(path, '/cronTasks/'))
    return success(demoStore.getTask(taskId))
  }
  if (/^\/cronTasks\/\d+$/.test(path) && method === 'PUT') {
    const taskId = asNumber(extractPathId(path, '/cronTasks/'))
    return success(demoStore.updateTaskDefinition(taskId, {
      task_name: input.task_name === undefined ? undefined : asString(input.task_name),
      task_code: input.task_code === undefined ? undefined : asString(input.task_code),
      task_type: input.task_type === undefined ? undefined : asNumber(input.task_type),
      executor: input.executor === undefined ? undefined : asString(input.executor),
      cron_plan: input.cron_plan === undefined ? undefined : asString(input.cron_plan),
      enabled: input.enabled === undefined ? undefined : asBoolean(input.enabled),
      description: input.description === undefined ? undefined : asString(input.description)
    }), 'Demo 任务已更新')
  }
  if (/^\/cronTasks\/\d+$/.test(path) && method === 'DELETE') {
    const taskId = asNumber(extractPathId(path, '/cronTasks/'))
    return success({ success: demoStore.deleteTask(taskId), demo: true }, 'Demo 任务已删除')
  }
  if (path.startsWith('/cronTasks/') && ['POST', 'PUT', 'DELETE'].includes(method)) {
    const parts = path.split('/').filter(Boolean)
    const taskId = asNumber(parts[1])
    const action = parts[2] || ''
    if (['start', 'pause', 'resume', 'interrupt'].includes(action)) {
      demoStore.updateTask(taskId, action as 'start' | 'pause' | 'resume' | 'interrupt')
    }
    return success(buildTaskResult(taskId, action || method), 'Demo 任务操作已模拟完成')
  }

  if (path === '/audit-logs/query' && method === 'POST') return success(demoStore.listAuditLogs(toPageParams(input)))
  if (path === '/audit-logs/statistics') return success({ total_count: demoStore.snapshot().auditLogs.length, operation_type_stats: { PAUSE: 1, LOGIN: 1, REANNOUNCE: 1 }, operator_stats: { '演示管理员': demoStore.snapshot().auditLogs.length }, result_stats: { success: 2, partial: 1 } })
  if (path === '/audit-logs/operation-types') return success({ operation_types: [{ value: 'PAUSE', display_name: '暂停', category: 'torrent' }, { value: 'LOGIN', display_name: '进入 Demo', category: 'system' }], total: 2 })
  if (path === '/audit-logs/export') return success({
    file_path: '/demo/exports/btdeck-demo-audit.txt',
    file_name: 'btdeck-demo-audit.txt',
    record_count: demoStore.snapshot().auditLogs.length,
    file_format: asString(input.export_format, 'txt')
  }, 'Demo 导出结果已生成')
  if (path === '/audit-logs/archive') return success({
    success: true,
    archived_count: demoStore.snapshot().auditLogs.length,
    archive_path: '/demo/archives/btdeck-demo-audit.json',
    message: 'Demo 模式仅生成归档结果，不写入本地磁盘'
  }, 'Demo 审计日志归档已模拟完成')

  if (path === '/recycle/bin' && method === 'GET') return success(demoStore.listRecycleBin(toPageParams(input)))
  if (path === '/recycle/restore' || path === '/recycle/restore-manual') return success(demoStore.restoreRecycleItems(asStringArray(input.torrent_ids || input.torrent_id)), 'Demo 回收站恢复已模拟完成')
  if (path === '/recycle/cleanup-preview') return success({ total_count: demoStore.snapshot().recycleBin.length, total_size: demoStore.snapshot().recycleBin.reduce((total, item) => total + item.size, 0), torrent_list: demoStore.snapshot().recycleBin })
  if (path === '/recycle/cleanup') return success(demoStore.cleanupRecycleItems(asStringArray(input.torrent_ids)), 'Demo 回收站清理已模拟完成')

  if (path === '/orphan-files/latest' && method === 'GET') return success(buildDemoOrphanScan())
  if (path === '/orphan-files/list' || path === '/orphan-files/folders/children') {
    const page = demoStore.listOrphanFiles(toOrphanQuery(input))
    return path.endsWith('/children')
      ? success(page)
      : success({ ...page, scan_context: buildDemoOrphanContext() })
  }
  if (path === '/orphan-files/hardlink-copies' && method === 'POST') {
    const ids = Array.isArray(input.orphan_ids) ? input.orphan_ids.map(item => asNumber(item)) : []
    const files = demoStore.snapshot().orphanFiles.filter(item => ids.includes(item.id))
    const items = files.map(item => ({
      orphan_id: item.id,
      file_path: item.file_path,
      copy_count: item.hardlink_copy_count,
      found_count: item.hardlink_copy_count || 0,
      unlocated_count: 0,
      copies: (item.hardlink_copy_count || 0) > 0 ? [`${item.file_path}.demo-copy`] : [],
      scanned_at: '2026-09-02T03:05:00+08:00',
      pending_scan: false,
      result_truncated: false,
      error: null
    }))
    return success({
      requested_count: ids.length,
      resolved_count: files.length,
      missing_orphan_ids: ids.filter(id => !files.some(item => item.id === id)),
      total_copy_count: items.reduce((total, item) => total + (item.copy_count || 0), 0),
      total_found_count: items.reduce((total, item) => total + item.found_count, 0),
      total_unlocated_count: 0,
      unknown_count: 0,
      scanned_count: items.length,
      pending_scan_count: 0,
      search_error: null,
      items
    }, 'Demo 硬链接副本位置已加载')
  }
  if (path === '/orphan-files/hardlink-copies/delete' && method === 'POST') {
    const orphanId = asNumber(input.orphan_id)
    const copyPaths = asStringArray(input.copy_paths)
    return success({
      orphan_id: orphanId,
      file_path: demoStore.getOrphanFile(orphanId)?.file_path || null,
      copy_count: Math.max(0, (demoStore.getOrphanFile(orphanId)?.hardlink_copy_count || 0) - copyPaths.length),
      success_count: copyPaths.length,
      failed_count: 0,
      failed_list: []
    }, 'Demo 硬链接副本删除已模拟完成')
  }
  if (path === '/orphan-files/scan' && method === 'POST') return success({
    scan_id: 'demo-scan-local',
    task_id: 'demo-orphan-scan-task-001',
    status: 'running',
    accepted: true
  }, 'Demo 扫描任务已提交，未读取真实文件系统')
  if (path.startsWith('/orphan-files/scans/') && path.endsWith('/guardrail-review') && method === 'POST') {
    return success(buildDemoOrphanScan(extractPathId(path, '/orphan-files/scans/').replace(/\/guardrail-review$/, '')), 'Demo 扫描复核已记录')
  }
  if (path.startsWith('/orphan-files/scans/') && method === 'GET') {
    return success(buildDemoOrphanScan(extractPathId(path, '/orphan-files/scans/')))
  }
  if (path === '/orphan-files/cleanup-preview' && method === 'POST') {
    const selected = getSelectedOrphans(input).filter(item => !item.is_deleted && !item.is_ignored)
    const items = selected.slice(0, 200).map(item => ({ id: item.id, file_path: item.file_path, file_size: item.file_size }))
    return success({
      rejected: false,
      total_count: selected.length,
      total_size: selected.reduce((total, item) => total + item.file_size, 0),
      low_confidence_count: selected.filter(item => item.confidence === 'low').length,
      items,
      items_truncated: selected.length > items.length
    }, 'Demo 孤儿文件清理预览已生成')
  }
  if (path === '/orphan-files/cleanup' && method === 'POST') return success(buildOrphanCleanupJob(input), 'Demo 孤儿文件清理任务已模拟完成')
  if (path.startsWith('/orphan-files/cleanup-jobs/') && method === 'GET') {
    return success({
      ...buildOrphanCleanupJob({ orphan_ids: [], scan_id: 'demo-scan-001' }),
      task_id: extractPathId(path, '/orphan-files/cleanup-jobs/')
    })
  }
  if (path === '/orphan-files/ignore') {
    const selected = getSelectedOrphans(input)
    const ignored = asBoolean(input.ignored)
    const failedList: Array<{ id: number, file_path?: string, reason: string }> = []
    let successCount = 0
    selected.forEach(item => {
      if (item.is_deleted) {
        failedList.push({ id: item.id, file_path: item.file_path, reason: '已清理文件不可修改' })
        return
      }
      if (demoStore.setOrphanIgnored(item.id, ignored)) successCount += 1
    })
    return success({ success_count: successCount, failed_count: failedList.length, failed_list: failedList }, 'Demo 孤儿文件状态已更新')
  }
  if (path === '/orphan-files/prefix-match-preview' && method === 'POST') {
    const prefix = asString(input.path_prefix)
    const filters = { ...input, status: 'pending', path_prefix: prefix }
    const matches = demoStore.snapshot().orphanFiles.filter(item =>
      item.file_path.startsWith(prefix) && matchesOrphanSelection(item, filters)
    )
    return success({
      rejected: false,
      count: matches.length,
      total_size: matches.reduce((total, item) => total + item.file_size, 0),
      low_confidence_count: matches.filter(item => item.confidence === 'low').length,
      sample_paths: matches.slice(0, 10).map(item => item.file_path)
    })
  }
  if (path === '/orphan-files/quarantine' && method === 'GET') return success({ total: 0, page: asNumber(input.page, 1), pageSize: asNumber(input.page_size, 20), list: [] })
  if (path === '/orphan-files/restore' && method === 'POST') return success({ restored_count: 0, failed_count: 0, failed_list: [] }, 'Demo 隔离区恢复已模拟完成')
  if (path === '/orphan-files/purge' && method === 'POST') return success({ task_id: null, status: 'completed', total_count: 0, purged_count: 0, failed_count: 0, failed_list: [], error_message: null, created_at: null, started_at: null, completed_at: null }, 'Demo 隔离区清理已模拟完成')
  if (path.startsWith('/orphan-files/purge-jobs/') && method === 'GET') return success({ task_id: extractPathId(path, '/orphan-files/purge-jobs/'), status: 'completed', total_count: 0, purged_count: 0, failed_count: 0, failed_list: [], error_message: null, created_at: null, started_at: null, completed_at: null })
  if (path.startsWith('/orphan-files/')) return success({ success: true, demo: true }, 'Demo 文件操作未执行真实文件系统副作用')

  if (path === '/tags/categories') return success(demoStore.getCategories().map((name, index) => ({ id: index + 1, name })))
  if (path === '/tags/tags' || path === '/tags/all') return success(demoStore.getTags())
  if (path.startsWith('/tags/')) return success({ success: true, demo: true }, 'Demo 标签操作已模拟完成')
  if (path === '/platform/capabilities') return success({ demo: true, capabilities: [] })
  if (path.startsWith('/user/')) return success({ success: true, demo: true }, 'Demo 模式：账户安全操作未执行')

  return unsupported(method, path)
}

export const demoRequest: DemoRequestClient = <T = DemoApiEnvelope<unknown>>(
  config: DemoRequestConfig
): Promise<T> => {
  try {
    return Promise.resolve(handleDemoRequest(config) as T)
  } catch (error) {
    return Promise.reject(error)
  }
}

export default demoRequest
