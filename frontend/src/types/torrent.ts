/**
 * 种子管理相关类型定义
 * 统一管理所有接口和枚举类型
 */

/**
 * 种子状态枚举
 * 对应后端QBITTORRENT_STATUS_MAP映射后的统一状态
 */
export enum TorrentStatus {
  SEEDING = 'seeding',           // 做种中（包含stalledUP, seeding, queuedUP）
  DOWNLOADING = 'downloading',   // 下载中（包含downloading, stalledDL）
  PAUSED = 'paused',             // 已暂停（包含pausedDL, pausedUP, paused）
  QUEUEDDL = 'queuedDL',         // 下载队列
  ERROR = 'error',               // 错误
  CHECKING = 'checking'          // 检查中（包含checkingDL, checkingUP）
}

/**
 * 种子信息接口
 */
export interface Torrent {
  // 主要标识字段
  hash: string
  infoId?: string
  info_id?: string

  // 下载器相关
  downloaderId: string
  downloader_id?: string
  downloaderName: string
  downloader_name?: string

  // 种子基本信息
  torrentId: string
  torrent_id?: string
  name: string
  savePath: string
  save_path?: string
  size: number
  category?: string
  tags?: string

  // 状态信息
  status: TorrentStatus | string
  state?: string | null

  // 进度信息(可能为null)
  progress?: number | null
  ratio: string
  ratioLimit: string
  ratio_limit?: string

  // 时间信息
  addedDate: number | string
  added_date?: string
  completedDate?: number | string | null
  completed_date?: string | null

  // 速度信息(可能为null)
  downloadSpeed?: number | null
  download_speed?: number | null
  uploadSpeed?: number | null
  upload_speed?: number | null
  num_seeds?: number | null
  num_leechs?: number | null

  // 连接信息(可能为null)
  peers?: number | null
  seeds?: number | null

  // 超级做种
  superSeeding: boolean | string
  super_seeding?: boolean | string

  // 启用状态
  enabled: boolean

  // Tracker信息(可能为null)
  trackerName?: string
  tracker_name?: string
  trackerUrl?: string
  tracker_url?: string
  lastAnnounceSucceeded?: string
  last_announce_succeeded?: string
  lastAnnounceMsg?: string
  last_announce_msg?: string
  lastScrapeSucceeded?: string
  last_scrape_succeeded?: string
  lastScrapeMsg?: string
  last_scrape_msg?: string
  trackerInfo?: TrackerInfo[]
  tracker_info?: TrackerInfo[]

  // 删除增强功能字段（新增）
  deletedAt?: string | null
  deleted_at?: string | null
  originalFilename?: string | null
  original_filename?: string | null

  // UI状态(前端添加)
  checked?: boolean
}

/**
 * Tracker信息接口
 */
export interface TrackerInfo {
  trackerId?: string
  tracker_id?: string
  trackerName?: string
  tracker_name?: string
  trackerUrl?: string
  tracker_url?: string
  lastAnnounceSucceeded?: string
  last_announce_succeeded?: string
  lastAnnounceMsg?: string
  last_announce_msg?: string
  lastAnnounceTime?: number
  last_announce_time?: number
  lastScrapeSucceeded?: string
  last_scrape_succeeded?: string
  lastScrapeMsg?: string
  last_scrape_msg?: string
  lastScrapeTime?: number
  last_scrape_time?: number
  peers?: number
  seeds?: number
  leeches?: number
  timesDownloaded?: number
}

/**
 * 下载器信息接口
 */
export interface Downloader {
  id: string
  id_?: string
  nickname: string
  type: string
  downloader_type?: string
  host: string
  port: number
  username?: string
  password?: string
  enabled?: boolean
  lastConnection?: string
  last_connection?: string
  // 路径映射配置（新增）
  pathMapping?: string | null
  path_mapping?: string | null
}

/**
 * 分页响应接口
 */
export interface PaginatedResponse<T> {
  total: number
  page: number
  pageSize: number
  list: T[]
}

/**
 * API响应接口
 */
export interface ApiResponse<T = any> {
  code: string
  msg: string
  data: T
  status: string
}

/**
 * 种子列表查询参数
 */
export interface TorrentListParams {
  downloader_id?: string
  downloader_name_like?: string
  name_like?: string
  save_path_like?: string
  size_min?: string
  size_max?: string
  added_date_min?: string
  added_date_max?: string
  completed_date_min?: string
  completed_date_max?: string
  tags_like?: string
  category_like?: string
  tracker_like?: string
  status?: string
  skip?: number
  limit?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

/**
 * 高级搜索请求参数
 */
export interface AdvancedSearchParams {
  page: number
  limit: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'

  // 基础过滤条件
  downloader_id?: string
  downloader_name?: string
  name?: string
  tags?: string
  category?: string
  status?: string

  // 数值范围过滤
  size_min?: string
  size_max?: string
  ratio_min?: number
  ratio_max?: number

  // 日期范围过滤
  added_date_min?: string
  added_date_max?: string
  completed_date_min?: string
  completed_date_max?: string

  // 高级搜索条件组
  condition_groups?: ConditionGroup[]

  // 多选排除字段
  status_multi?: MultiSelectField
  category_multi?: MultiSelectField
  tags_multi?: MultiSelectField
  downloader_multi?: MultiSelectField
}

/**
 * 条件组
 */
export interface ConditionGroup {
  logic: 'AND' | 'OR'
  conditions: Condition[]
}

/**
 * 搜索条件
 */
export interface Condition {
  field: string
  operator: string
  value: any
}

/**
 * 多选字段
 */
export interface MultiSelectField {
  mode: 'include' | 'exclude'
  value: string | string[]
  separator?: string
}

/**
 * 种子操作请求
 */
export interface TorrentActionRequest {
  hashes: string[]
}

/**
 * 删除种子请求
 */
export interface TorrentDeleteRequest {
  info_id: string
  downloader_id: string
  delete_data: number
  id_recycle: number
}

/**
 * 添加种子请求
 */
export interface TorrentAddRequest {
  torrent_file: File | string
  downloader_id: string
  save_path: string
  category?: string
  tags?: string
  paused?: boolean
  skip_hash_check?: boolean
  is_sequential_download?: boolean
  is_first_last_piece_priority?: boolean
  upload_limit?: number | string
  download_limit?: number | string
  added_date?: number
}

/**
 * Tracker操作请求
 */
export interface TrackerOperationRequest {
  torrentInfoIds: string
  trackers: string
}

/**
 * 列设置项
 */
export interface ColumnSetting {
  key: string
  label: string
  visible: boolean
  minWidth?: number
  width?: number
}

/**
 * 用户偏好设置
 */
export interface UserPreferences {
  theme: string
  columnsVisibility: Record<string, boolean>
  searchMode: 'simple' | 'advanced'
  pageSize: number
}

/**
 * 批量操作结果
 */
export interface BatchOperationResult {
  successCount: number
  failCount: number
  failedItems?: Array<{
    item: any
    error: string
  }>
}

/**
 * 种子统计信息
 */
export interface TorrentStats {
  total: number
  downloading: number
  completed: number
  paused: number
  seeding: number
  error: number
  totalSize: number
}

/**
 * 审计日志操作类型枚举（新增）
 */
export enum AuditOperationType {
  CREATE = 'CREATE',
  UPDATE = 'UPDATE',
  DELETE_LEVEL_1 = 'DELETE_LEVEL_1',  // 删除任务和数据
  DELETE_LEVEL_2 = 'DELETE_LEVEL_2',  // 删除任务保留数据
  DELETE_LEVEL_3 = 'DELETE_LEVEL_3',  // 回收站
  DELETE_LEVEL_4 = 'DELETE_LEVEL_4',  // 待删除标签
  RESTORE = 'RESTORE',                // 还原
  TRACKER_UPDATE = 'TRACKER_UPDATE',  // 更新tracker
  TAG_UPDATE = 'TAG_UPDATE',          // 更新标签
  CATEGORY_UPDATE = 'CATEGORY_UPDATE' // 更新分类
}

/**
 * 审计日志操作结果枚举（新增）
 */
export enum AuditOperationResult {
  SUCCESS = 'success',
  FAILED = 'failed',
  PARTIAL = 'partial'
}

/**
 * 种子审计日志接口（新增）
 */
export interface TorrentAuditLog {
  logId: string
  log_id?: string
  torrentInfoId: string
  torrent_info_id?: string
  operationType: AuditOperationType | string
  operation_type?: string
  operationDetail?: string
  operation_detail?: string
  oldValue?: string
  old_value?: string
  newValue?: string
  new_value?: string
  operator: string
  operationTime: string
  operation_time?: string
  operationResult: AuditOperationResult | string
  operation_result?: string
  errorMessage?: string | null
  error_message?: string | null
  downloaderId: string
  downloader_id?: string
  createTime: string
  create_time?: string
}

/**
 * 审计日志查询参数（新增）
 */
export interface AuditLogQueryParams {
  torrent_info_id?: string
  operation_type?: string
  operator?: string
  downloader_id?: string
  operation_time_min?: string
  operation_time_max?: string
  skip?: number
  limit?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

/**
 * 删除等级枚举（新增）
 */
export enum DeleteLevel {
  LEVEL_1 = 1,  // 删除任务和数据
  LEVEL_2 = 2,  // 删除任务保留数据
  LEVEL_3 = 3,  // 回收站
  LEVEL_4 = 4   // 待删除标签
}

/**
 * 删除请求参数（新增）
 */
export interface DeleteRequest {
  infoIds: string[]
  info_ids?: string[]
  deleteLevel: DeleteLevel
  delete_level?: number
  reason?: string
}

/**
 * 回收站查询参数（新增）
 */
export interface RecycleBinQueryParams {
  downloader_id?: string
  name_like?: string
  deleted_date_min?: string
  deleted_date_max?: string
  skip?: number
  limit?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

/**
 * 还原请求参数（新增）
 */
export interface RestoreRequest {
  infoIds: string[]
  info_ids?: string[]
  newSavePath?: string
  new_save_path?: string
}

/**
 * 清理预览结果（新增）
 */
export interface CleanupPreview {
  totalCount: number
  total_size: number
  level3Count: number
  level4Count: number
  items?: Array<{
    infoId: string
    name: string
    level: number
    size: number
  }>
}

/**
 * 清理请求参数（新增）
 */
export interface CleanupRequest {
  level3: boolean
  level4: boolean
  previewOnly: boolean
  preview_only?: boolean
}
