import { DEMO_ACTIVITIES, DEMO_FIXTURE_BUNDLE } from '@/demo/fixtures'
import {
  DemoActivity,
  DemoAuditLog,
  DemoDashboardData,
  DemoDownloader,
  DemoFixtureBundle,
  DemoNotification,
  DemoOrphanFile,
  DemoPage,
  DemoQueryTemplate,
  DemoQueryTemplateConditions,
  DemoRecycleItem,
  DemoTask,
  DemoTaskLog,
  DemoTorrent,
  DemoTracker,
  DemoTrackerKeyword,
  DemoTrackerMessage,
  DemoTrackerReannounceConfig
} from '@/demo/types'

export interface DemoPageParams {
  page?: number
  pageSize?: number
  page_size?: number
  limit?: number
  search?: string
}

export interface DemoTorrentQuery extends DemoPageParams {
  name?: string
  name_like?: string
  downloader_id?: string | string[]
  status?: string | string[]
  category?: string
  tags?: string
  tracker_domain?: string | string[]
  showActiveOnly?: boolean
  active_only?: boolean
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface DemoTemplateInput {
  name?: string
  description?: string | null
  conditions?: DemoQueryTemplateConditions
  is_public?: boolean
}

export interface DemoDownloaderInput {
  id?: string
  nickname?: string
  host?: string
  port?: string | number
  downloaderType?: 0 | 1
  downloader_type?: 0 | 1
  isSearch?: '0' | '1'
  is_search?: '0' | '1'
  isSsl?: '0' | '1'
  is_ssl?: '0' | '1'
  enabled?: '0' | '1'
}

export interface DemoTrackerKeywordInput {
  keyword_type?: DemoTrackerKeyword['keyword_type']
  keyword?: string
  language?: string
  priority?: number
  enabled?: boolean
  category?: string
  description?: string
}

export interface DemoTaskInput {
  task_name?: string
  task_code?: string
  task_type?: number
  executor?: string
  cron_plan?: string
  enabled?: boolean
  description?: string
  timeout_seconds?: number
  max_retry_count?: number
  retry_interval?: number
}

export interface DemoOrphanQuery extends DemoPageParams {
  is_ignored?: boolean
  confidence?: string | string[]
  status?: string | string[]
  downloader_id?: string | string[]
  path_like?: string
  hardlink_copies?: 'located'
}

export interface DemoStoreState extends DemoFixtureBundle {
  activities: DemoActivity[]
}

export interface DemoDeleteResult {
  success_count: number
  failed_count: number
  skipped_count: number
  success_list: Array<{ torrent_id: string, torrent_name: string }>
  failed_list: Array<{ torrent_id: string, torrent_name?: string, reason: string }>
}

export interface DemoOrphanCleanupResult {
  success_count: number
  failed_count: number
  failed_list: Array<{ id: number, file_path?: string, reason: string }>
  total_size: number
}

export type DemoRestoreResult = DemoDeleteResult

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

const normalizePage = (value: number | undefined, fallback: number): number => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 1) return fallback
  return Math.floor(value)
}

const normalizePageSize = (params: DemoPageParams): number => normalizePage(
  params.pageSize || params.page_size || params.limit,
  10
)

const paginate = <T>(items: T[], params: DemoPageParams): DemoPage<T> => {
  const page = normalizePage(params.page, 1)
  const pageSize = normalizePageSize(params)
  const start = (page - 1) * pageSize
  return {
    total: items.length,
    page,
    pageSize,
    list: clone(items.slice(start, start + pageSize))
  }
}

const toArray = (value: string | string[] | undefined): string[] => {
  if (Array.isArray(value)) return value.filter(Boolean)
  if (typeof value === 'string') return value.split(',').map(item => item.trim()).filter(Boolean)
  return []
}

const containsText = (value: string | null | undefined, query: string | undefined): boolean =>
  !query || Boolean(value && value.toLowerCase().includes(query.toLowerCase()))

const matchesAny = (value: string, filter: string | string[] | undefined): boolean => {
  const values = toArray(filter)
  return values.length === 0 || values.includes(value)
}

const isActiveTorrent = (torrent: DemoTorrent): boolean =>
  ['downloading', 'queuedDL', 'checking', 'seeding'].includes(torrent.status)

const makeDefaultConditions = (): DemoQueryTemplateConditions => ({
  source: 'simple',
  version: 1,
  listQuery: {
    name_like: '',
    category_like: '',
    tags_like: '',
    downloader_id: [],
    status: [],
    tracker_domain: [],
    showActiveOnly: false,
    sort_by: 'added_date',
    sort_order: 'desc'
  }
})

export class DemoStore {
  private state: DemoStoreState

  public constructor(seed: DemoFixtureBundle = DEMO_FIXTURE_BUNDLE) {
    this.state = {
      ...clone(seed),
      activities: clone(DEMO_ACTIVITIES)
    }
  }

  public reset(): void {
    this.state = {
      ...clone(DEMO_FIXTURE_BUNDLE),
      activities: clone(DEMO_ACTIVITIES)
    }
  }

  public snapshot(): DemoStoreState {
    return clone(this.state)
  }

  public getDashboardData(): DemoDashboardData {
    const online = this.state.downloaders.filter(item => item.status === 'online').length
    const activeTorrents = this.state.torrents.filter(isActiveTorrent)
    const downloading = this.state.torrents.filter(item => item.status === 'downloading').length
    const seeding = this.state.torrents.filter(item => item.status === 'seeding').length
    const paused = this.state.torrents.filter(item => item.status === 'paused').length
    const runningTasks = this.state.tasks.filter(item => item.taskStatus === 1).length

    return {
      downloaders: {
        total: this.state.downloaders.length,
        online,
        offline: this.state.downloaders.length - online
      },
      torrents: {
        active: activeTorrents.length,
        downloading,
        seeding,
        paused
      },
      tasks: {
        total: this.state.tasks.length,
        running: runningTasks,
        stopped: this.state.tasks.length - runningTasks
      },
      system: {
        uptime: 86400,
        uptime_display: '1 天 00:00:00',
        version: 'v1.0.6-demo',
        total_download_speed: this.state.torrents.reduce((total, item) => total + item.downloadSpeed, 0),
        total_upload_speed: this.state.torrents.reduce((total, item) => total + item.uploadSpeed, 0)
      },
      downloader_list: this.state.downloaders.map(item => ({
        downloader_id: item.downloaderId,
        nickname: item.nickname,
        downloader_type: item.downloaderType,
        status: item.status,
        downloading: item.downloadingCount,
        seeding: item.seedingCount,
        paused: item.pausedCount,
        download_speed: item.downloadSpeed,
        upload_speed: item.uploadSpeed
      })),
      activities: clone(this.state.activities)
    }
  }

  public listDownloaders(params: { enabled?: boolean } = {}): DemoDownloader[] {
    const items = params.enabled === undefined
      ? this.state.downloaders
      : this.state.downloaders.filter(item => (item.enabled === '1') === params.enabled)
    return clone(items)
  }

  public getDownloader(id: string): DemoDownloader | null {
    const item = this.state.downloaders.find(downloader => downloader.downloaderId === id)
    return item ? clone(item) : null
  }

  public createDownloader(input: DemoDownloaderInput): DemoDownloader {
    const nextId = `demo-downloader-local-${this.state.downloaders.length + 1}`
    const downloaderType = input.downloaderType ?? input.downloader_type ?? 0
    const isSearch = input.isSearch ?? input.is_search ?? '1'
    const item: DemoDownloader = {
      downloaderId: nextId,
      nickname: input.nickname || '新建 Demo 节点',
      host: input.host || 'new-node.example.invalid',
      port: String(input.port || '8080'),
      downloaderType,
      downloaderTypeName: downloaderType === 1 ? 'transmission' : 'qbittorrent',
      isSearch,
      enabled: input.enabled ?? '1',
      status: 'online',
      version: '演示版本',
      connectStatus: '1',
      delay: 24,
      downloadSpeed: 0,
      uploadSpeed: 0,
      downloadingCount: 0,
      seedingCount: 0,
      pausedCount: 0
    }
    this.state.downloaders.unshift(item)
    this.appendActivity('下载器', `已添加 Demo 下载器：${item.nickname}`, 'downloader')
    return clone(item)
  }

  public updateDownloader(id: string, input: DemoDownloaderInput): DemoDownloader | null {
    const item = this.state.downloaders.find(downloader => downloader.downloaderId === id)
    if (!item) return null
    if (input.nickname !== undefined) item.nickname = input.nickname
    if (input.host !== undefined) item.host = input.host
    if (input.port !== undefined) item.port = String(input.port)
    if (input.downloaderType !== undefined || input.downloader_type !== undefined) {
      const downloaderType = input.downloaderType ?? input.downloader_type ?? item.downloaderType
      item.downloaderType = downloaderType
      item.downloaderTypeName = downloaderType === 1 ? 'transmission' : 'qbittorrent'
    }
    if (input.isSearch !== undefined || input.is_search !== undefined) {
      item.isSearch = input.isSearch ?? input.is_search ?? item.isSearch
    }
    if (input.enabled !== undefined) item.enabled = input.enabled
    this.appendActivity('下载器', `已更新 Demo 下载器：${item.nickname}`, 'downloader')
    return clone(item)
  }

  public deleteDownloader(id: string): boolean {
    const item = this.state.downloaders.find(downloader => downloader.downloaderId === id)
    if (!item) return false
    this.state.downloaders = this.state.downloaders.filter(downloader => downloader.downloaderId !== id)
    this.appendActivity('下载器', `已移除 Demo 下载器：${item.nickname}`, 'downloader')
    return true
  }

  public listDownloaderStatuses(): Array<{
    id: string
    delay: number | null
    uploadSpeed: number
    downloadSpeed: number
    downloadingCount: number
    seedingCount: number
    connectStatus: '1' | '0'
  }> {
    return this.state.downloaders.map(item => ({
      id: item.downloaderId,
      delay: item.delay,
      uploadSpeed: item.uploadSpeed,
      downloadSpeed: item.downloadSpeed,
      downloadingCount: item.downloadingCount,
      seedingCount: item.seedingCount,
      connectStatus: item.connectStatus
    }))
  }

  public listTorrents(query: DemoTorrentQuery = {}): DemoPage<DemoTorrent> {
    let items = this.state.torrents.filter(item =>
      containsText(item.name, query.name || query.name_like || query.search) &&
      matchesAny(item.downloaderId, query.downloader_id) &&
      matchesAny(item.status, query.status) &&
      containsText(item.category, query.category) &&
      containsText(item.tags, query.tags) &&
      (!query.tracker_domain || toArray(query.tracker_domain).length === 0 ||
        item.trackerInfo.some(tracker => toArray(query.tracker_domain).includes(tracker.trackerHost))) &&
      (!(query.showActiveOnly || query.active_only) || isActiveTorrent(item))
    )

    if (query.sort_by) {
      const sortOrder = query.sort_order === 'asc' ? 1 : -1
      items = [...items].sort((left, right) => {
        const leftValue = query.sort_by === 'name'
          ? left.name
          : query.sort_by === 'size'
            ? left.size
            : query.sort_by === 'ratio'
              ? (left.ratio ?? 0)
              : query.sort_by === 'status'
                ? left.status
                : left.addedDate
        const rightValue = query.sort_by === 'name'
          ? right.name
          : query.sort_by === 'size'
            ? right.size
            : query.sort_by === 'ratio'
              ? (right.ratio ?? 0)
              : query.sort_by === 'status'
                ? right.status
                : right.addedDate
        return (leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0) * sortOrder
      })
    }

    return paginate(items, query)
  }

  public getTorrent(identifier: string): DemoTorrent | null {
    const item = this.state.torrents.find(torrent =>
      torrent.hash === identifier || torrent.infoId === identifier || torrent.torrentId === identifier
    )
    return item ? clone(item) : null
  }

  public getTrackerDomains(): string[] {
    return clone(this.state.trackerDomains)
  }

  public listTrackers(): DemoTracker[] {
    const trackerMap = new Map<string, DemoTracker>()
    this.state.torrents.forEach(torrent => torrent.trackerInfo.forEach(tracker => trackerMap.set(tracker.trackerId, tracker)))
    return clone(Array.from(trackerMap.values()))
  }

  public updateTorrentState(hashes: string[], status: 'paused' | 'downloading' | 'checking'): DemoTorrent[] {
    const hashSet = new Set(hashes)
    const changed: DemoTorrent[] = []
    this.state.torrents.forEach(torrent => {
      if (!hashSet.has(torrent.hash)) return
      torrent.status = status
      torrent.state = status
      torrent.enabled = status !== 'paused'
      if (status === 'paused' || status === 'checking') torrent.downloadSpeed = 0
      if (status === 'downloading' && torrent.downloadSpeed === 0) torrent.downloadSpeed = 2 * 1024 * 1024
      changed.push(torrent)
    })
    if (changed.length > 0) {
      this.appendActivity('种子', `${status === 'paused' ? '已暂停' : status === 'checking' ? '已重新检查' : '已恢复'} ${changed.length} 个 Demo 种子`, 'torrent')
    }
    return clone(changed)
  }

  public deleteTorrents(identifiers: string[], deleteLevel: number): DemoDeleteResult {
    const selected = this.state.torrents.filter(item => identifiers.includes(item.infoId) || identifiers.includes(item.hash))
    const successList = selected.map(item => ({ torrent_id: item.torrentId, torrent_name: item.name }))
    if (deleteLevel === 3) {
      selected.forEach(item => {
        if (this.state.recycleBin.some(recycled => recycled.info_id === item.infoId)) return
        this.state.recycleBin.unshift({
          info_id: item.infoId,
          name: item.name,
          size: item.size,
          save_path: item.savePath,
          deleted_at: '2026-09-02T10:05:00+08:00',
          downloader_name: item.downloaderName,
          downloader_id: item.downloaderId,
          torrent_id: item.torrentId,
          hash: item.hash
        })
      })
    }
    if (deleteLevel === 3 || deleteLevel === 4) {
      const selectedIds = new Set(selected.map(item => item.infoId))
      this.state.torrents = this.state.torrents.filter(item => !selectedIds.has(item.infoId))
    }
    this.appendActivity('种子', `Demo 删除操作完成：${successList.length} 个`, 'torrent')
    return {
      success_count: successList.length,
      failed_count: identifiers.length - successList.length,
      skipped_count: 0,
      success_list: clone(successList),
      failed_list: []
    }
  }

  public getNotifications(params: DemoPageParams & { type?: string, is_read?: boolean } = {}): DemoPage<DemoNotification> {
    const items = this.state.notifications.filter(item =>
      (!params.type || item.type === params.type) &&
      (params.is_read === undefined || item.is_read === params.is_read) &&
      containsText(item.title, params.search)
    )
    return paginate(items, params)
  }

  public getUnreadNotificationCount(): number {
    return this.state.notifications.filter(item => !item.is_read).length
  }

  public markNotification(id: number, isRead: boolean): DemoNotification | null {
    const item = this.state.notifications.find(notification => notification.id === id)
    if (!item) return null
    item.is_read = isRead
    item.read_at = isRead ? '2026-09-02T10:05:00+08:00' : null
    return clone(item)
  }

  public markAllNotificationsRead(): number {
    let count = 0
    this.state.notifications.forEach(item => {
      if (!item.is_read) {
        item.is_read = true
        item.read_at = '2026-09-02T10:05:00+08:00'
        count += 1
      }
    })
    return count
  }

  public deleteNotification(id: number): boolean {
    const originalLength = this.state.notifications.length
    this.state.notifications = this.state.notifications.filter(item => item.id !== id)
    return this.state.notifications.length !== originalLength
  }

  public listTemplates(): DemoQueryTemplate[] {
    return clone(this.state.queryTemplates)
  }

  public getTemplate(id: string): DemoQueryTemplate | null {
    const item = this.state.queryTemplates.find(template => template.id === id)
    return item ? clone(item) : null
  }

  public createTemplate(input: DemoTemplateInput): DemoQueryTemplate {
    const id = `demo-template-local-${this.state.queryTemplates.length + 1}`
    const template: DemoQueryTemplate = {
      id,
      user_id: 'demo-user-001',
      name: input.name || '未命名 Demo 模板',
      description: input.description || null,
      conditions: clone(input.conditions || makeDefaultConditions()),
      is_default: false,
      is_public: input.is_public !== false,
      usage_count: 0,
      created_time: '2026-09-02T10:05:00+08:00',
      updated_time: null
    }
    this.state.queryTemplates.unshift(template)
    return clone(template)
  }

  public updateTemplate(id: string, input: DemoTemplateInput): DemoQueryTemplate | null {
    const template = this.state.queryTemplates.find(item => item.id === id)
    if (!template) return null
    if (input.name !== undefined) template.name = input.name
    if (input.description !== undefined) template.description = input.description
    if (input.conditions !== undefined) template.conditions = clone(input.conditions)
    if (input.is_public !== undefined) template.is_public = input.is_public
    template.updated_time = '2026-09-02T10:05:00+08:00'
    return clone(template)
  }

  public deleteTemplate(id: string): boolean {
    const originalLength = this.state.queryTemplates.length
    this.state.queryTemplates = this.state.queryTemplates.filter(item => item.id !== id)
    return this.state.queryTemplates.length !== originalLength
  }

  public applyTemplate(id: string): DemoQueryTemplate | null {
    const template = this.state.queryTemplates.find(item => item.id === id)
    if (!template) return null
    template.usage_count += 1
    return clone(template)
  }

  public listTasks(params: DemoPageParams = {}): DemoPage<DemoTask> {
    return paginate(this.state.tasks, params)
  }

  public createTask(input: DemoTaskInput): DemoTask {
    const taskId = this.state.tasks.reduce((max, task) => Math.max(max, task.taskId), 0) + 1
    const taskType = input.task_type ?? 0
    const task: DemoTask = {
      taskId,
      taskName: input.task_name || '新建 Demo 任务',
      taskCode: input.task_code || `demo_task_${taskId}`,
      taskStatus: 2,
      taskType,
      executor: input.executor || 'echo demo',
      enabled: input.enabled !== false,
      lastExecuteTime: null,
      lastExecuteDuration: null,
      cronPlan: input.cron_plan || '0 * * * *',
      taskStatusName: '空闲',
      taskTypeName: taskType === 4 ? 'Python 内部类' : taskType === 3 ? 'Python' : 'Shell',
      createTime: '2026-09-02T10:05:00+08:00',
      updateTime: '2026-09-02T10:05:00+08:00',
      description: input.description || '静态演示任务，不会执行真实脚本。',
      lastOutcome: null,
      lastSuccessfulDataAt: null,
      lastAttemptAt: null,
      lastSkipReason: null,
      lastRunId: null,
      freshnessSeconds: null,
      stale: false
    }
    this.state.tasks.unshift(task)
    this.appendActivity('定时任务', `已创建 Demo 任务：${task.taskName}`, 'scheduled_task')
    return clone(task)
  }

  public updateTaskDefinition(taskId: number, input: DemoTaskInput): DemoTask | null {
    const task = this.state.tasks.find(item => item.taskId === taskId)
    if (!task) return null
    if (input.task_name !== undefined) task.taskName = input.task_name
    if (input.task_code !== undefined) task.taskCode = input.task_code
    if (input.task_type !== undefined) task.taskType = input.task_type
    if (input.executor !== undefined) task.executor = input.executor
    if (input.cron_plan !== undefined) task.cronPlan = input.cron_plan
    if (input.enabled !== undefined) task.enabled = input.enabled
    if (input.description !== undefined) task.description = input.description
    task.updateTime = '2026-09-02T10:05:00+08:00'
    return clone(task)
  }

  public deleteTask(taskId: number): boolean {
    const originalLength = this.state.tasks.length
    this.state.tasks = this.state.tasks.filter(task => task.taskId !== taskId)
    return this.state.tasks.length !== originalLength
  }

  public getTask(taskId: number): DemoTask | null {
    const item = this.state.tasks.find(task => task.taskId === taskId)
    return item ? clone(item) : null
  }

  public listTaskLogs(params: DemoPageParams & { task_id?: number } = {}): DemoPage<DemoTaskLog> {
    const items = params.task_id === undefined
      ? this.state.taskLogs
      : this.state.taskLogs.filter(log => log.taskId === params.task_id)
    return paginate(items, params)
  }

  public updateTask(taskId: number, action: 'start' | 'pause' | 'resume' | 'interrupt'): DemoTask | null {
    const task = this.state.tasks.find(item => item.taskId === taskId)
    if (!task) return null
    if (action === 'start' || action === 'resume') {
      task.taskStatus = 1
      task.taskStatusName = '运行中'
      task.lastOutcome = 'success'
    } else {
      task.taskStatus = 2
      task.taskStatusName = '空闲'
      if (action === 'interrupt') task.lastOutcome = 'cancelled'
    }
    task.lastAttemptAt = '2026-09-02T10:05:00+08:00'
    return clone(task)
  }

  public listAuditLogs(params: DemoPageParams & { operation_type?: string } = {}): DemoPage<DemoAuditLog> {
    const items = this.state.auditLogs.filter(item =>
      !params.operation_type || item.operation_type === params.operation_type
    )
    return paginate(items, params)
  }

  public listRecycleBin(params: DemoPageParams): DemoPage<DemoRecycleItem> {
    return paginate(this.state.recycleBin.filter(item => containsText(item.name, params.search)), params)
  }

  public restoreRecycleItems(identifiers: string[]): DemoRestoreResult {
    const selected = this.state.recycleBin.filter(item => identifiers.includes(item.info_id) || identifiers.includes(item.torrent_id))
    this.state.recycleBin = this.state.recycleBin.filter(item => !selected.includes(item))
    return {
      success_count: selected.length,
      failed_count: identifiers.length - selected.length,
      skipped_count: 0,
      success_list: selected.map(item => ({ torrent_id: item.torrent_id, torrent_name: item.name })),
      failed_list: []
    }
  }

  public cleanupRecycleItems(identifiers: string[]): DemoDeleteResult {
    return this.restoreRecycleItems(identifiers)
  }

  public listOrphanFiles(params: DemoOrphanQuery = {}): DemoPage<DemoOrphanFile> {
    const statuses = toArray(params.status)
    const items = this.state.orphanFiles.filter(item => {
      const statusMatches = statuses.length === 0 || statuses.some(status =>
        status === 'pending' ? !item.is_ignored && !item.is_deleted
          : status === 'ignored' ? item.is_ignored && !item.is_deleted
            : status === 'deleted' ? item.is_deleted
              : false
      )
      return (
        (params.is_ignored === undefined || item.is_ignored === params.is_ignored) &&
        (statuses.length === 0 || statusMatches) &&
        matchesAny(item.confidence, params.confidence) &&
        matchesAny(item.downloader_id || '', params.downloader_id) &&
        containsText(item.file_path, params.path_like || params.search) &&
        (params.hardlink_copies !== 'located' || (item.hardlink_copy_count || 0) > 0)
      )
    })
    return paginate(items, params)
  }

  public getOrphanFile(id: number): DemoOrphanFile | null {
    const item = this.state.orphanFiles.find(file => file.id === id)
    return item ? clone(item) : null
  }

  public setOrphanIgnored(id: number, ignored: boolean): DemoOrphanFile | null {
    const item = this.state.orphanFiles.find(file => file.id === id)
    if (!item) return null
    item.is_ignored = ignored
    item.ignored_at = ignored ? '2026-09-02T10:05:00+08:00' : null
    item.ignored_by = ignored ? 'demo-user-001' : null
    return clone(item)
  }

  public cleanupOrphanFiles(ids: number[]): DemoOrphanCleanupResult {
    const requested = new Set(ids)
    const successList: Array<{ id: number, file_path: string, file_size: number }> = []
    const failedList: Array<{ id: number, file_path?: string, reason: string }> = []
    this.state.orphanFiles.forEach(item => {
      if (!requested.has(item.id)) return
      if (item.is_deleted) {
        failedList.push({ id: item.id, file_path: item.file_path, reason: '文件已清理' })
        return
      }
      if (item.is_ignored) {
        failedList.push({ id: item.id, file_path: item.file_path, reason: '已忽视文件受保护' })
        return
      }
      item.is_deleted = true
      item.deleted_at = '2026-09-02T10:05:00+08:00'
      item.deleted_by = 'demo-user-001'
      successList.push({ id: item.id, file_path: item.file_path, file_size: item.file_size })
    })
    return {
      success_count: successList.length,
      failed_count: failedList.length + Math.max(0, ids.length - successList.length - failedList.length),
      failed_list: failedList,
      total_size: successList.reduce((total, item) => total + item.file_size, 0)
    }
  }

  public listTrackerKeywords(params: DemoPageParams & { keyword_type?: string } = {}): DemoPage<DemoTrackerKeyword> {
    const items = this.state.trackerKeywords.filter(item =>
      (!params.keyword_type || item.keyword_type === params.keyword_type) &&
      containsText(item.keyword, params.search)
    )
    return paginate(items, params)
  }

  public listPoolKeywords(
    poolType: DemoTrackerKeyword['keyword_type'],
    params: DemoPageParams & { keyword?: string } = {}
  ): DemoPage<{ keyword_id: string, keyword: string, pool_type: DemoTrackerKeyword['keyword_type'], create_time: string }> {
    const items = this.state.trackerKeywords
      .filter(item => item.keyword_type === poolType && containsText(item.keyword, params.keyword || params.search))
      .map(item => ({
        keyword_id: item.keyword_id,
        keyword: item.keyword,
        pool_type: item.keyword_type,
        create_time: item.create_time
      }))
    return paginate(items, params)
  }

  public createTrackerKeyword(input: DemoTrackerKeywordInput): DemoTrackerKeyword {
    const id = `demo-keyword-local-${this.state.trackerKeywords.length + 1}`
    const keyword: DemoTrackerKeyword = {
      keyword_id: id,
      keyword_type: input.keyword_type || 'candidate',
      keyword: input.keyword || '新建 Demo 关键词',
      language: input.language || 'zh-CN',
      priority: input.priority ?? 10,
      enabled: input.enabled !== false,
      category: input.category || '演示',
      description: input.description || '静态演示关键词，不连接外部 Tracker。',
      create_time: '2026-09-02T10:05:00+08:00',
      update_time: '2026-09-02T10:05:00+08:00'
    }
    this.state.trackerKeywords.unshift(keyword)
    return clone(keyword)
  }

  public updateTrackerKeyword(id: string, input: DemoTrackerKeywordInput): DemoTrackerKeyword | null {
    const keyword = this.state.trackerKeywords.find(item => item.keyword_id === id)
    if (!keyword) return null
    if (input.keyword_type !== undefined) keyword.keyword_type = input.keyword_type
    if (input.keyword !== undefined) keyword.keyword = input.keyword
    if (input.language !== undefined) keyword.language = input.language
    if (input.priority !== undefined) keyword.priority = input.priority
    if (input.enabled !== undefined) keyword.enabled = input.enabled
    if (input.category !== undefined) keyword.category = input.category
    if (input.description !== undefined) keyword.description = input.description
    keyword.update_time = '2026-09-02T10:05:00+08:00'
    return clone(keyword)
  }

  public deleteTrackerKeyword(id: string): boolean {
    const originalLength = this.state.trackerKeywords.length
    this.state.trackerKeywords = this.state.trackerKeywords.filter(item => item.keyword_id !== id)
    return this.state.trackerKeywords.length !== originalLength
  }

  public moveTrackerKeyword(id: string, targetPool: DemoTrackerKeyword['keyword_type']): DemoTrackerKeyword | null {
    return this.updateTrackerKeyword(id, { keyword_type: targetPool })
  }

  public prefixMatchTrackerKeywords(
    poolType: DemoTrackerKeyword['keyword_type'],
    prefix: string
  ): Array<{ keyword_id: string, keyword: string }> {
    return this.state.trackerKeywords
      .filter(item => item.keyword_type === poolType && item.keyword.startsWith(prefix))
      .map(item => ({ keyword_id: item.keyword_id, keyword: item.keyword }))
  }

  public listTrackerMessages(params: DemoPageParams & { keyword_type?: string } = {}): DemoPage<DemoTrackerMessage> {
    const items = this.state.trackerMessages.filter(item =>
      (!params.keyword_type || item.keyword_type === params.keyword_type) &&
      containsText(item.tracker_host, params.search)
    )
    return paginate(items, params)
  }

  public listReannounceConfigs(params: DemoPageParams = {}): DemoPage<DemoTrackerReannounceConfig> {
    return paginate(this.state.trackerReannounceConfigs, params)
  }

  public getCategories(): string[] {
    return clone(this.state.categories)
  }

  public getTags(): string[] {
    return clone(this.state.tags)
  }

  private appendActivity(source: string, action: string, type: DemoActivity['type']): void {
    this.state.activities.unshift({ time: '刚刚', source, action, type })
    this.state.activities = this.state.activities.slice(0, 8)
  }
}

export const demoStore = new DemoStore()
