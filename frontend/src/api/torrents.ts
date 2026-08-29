/* eslint-disable camelcase */
import request from '@/utils/request'

export interface Torrent {
  // 主要字段 - 使用camelCase命名
  infoId: string
  info_id?: string // 蛇形命名兼容（后端数据库字段名）
  downloaderId: string
  downloader_id?: string // 蛇形命名兼容
  downloaderName: string
  downloader_name?: string // 蛇形命名兼容
  torrentId: string
  torrent_id?: string // 蛇形命名兼容
  hash: string
  name: string
  savePath: string
  save_path?: string // 蛇形命名兼容
  size: number
  status: string
  errorReason?: string | null
  error_reason?: string | null // 蛇形命名兼容
  hasTrackerError?: boolean | null
  has_tracker_error?: boolean | null // 蛇形命名兼容（tracker 判定任务标记的整种错误）
  torrentFile: string
  torrent_file?: string // 蛇形命名兼容
  auxiliarySeedCount?: number
  auxiliary_seed_count?: number // 蛇形命名兼容
  addedDate: string
  added_date?: string // 蛇形命名兼容
  completedDate: string | null
  completed_date?: string | null // 蛇形命名兼容
  ratio: number | null
  ratioLimit: number | null
  ratio_limit?: number | null // 蛇形命名兼容
  tags: string
  category: string
  superSeeding: string | boolean
  super_seeding?: string | boolean // 蛇形命名兼容
  enabled: boolean

  // Tracker相关字段
  trackerName?: string
  tracker_name?: string // 蛇形命名兼容
  trackerUrl?: string
  tracker_url?: string // 蛇形命名兼容
  lastAnnounceSucceeded?: string
  last_announce_succeeded?: string // 蛇形命名兼容
  lastAnnounceMsg?: string
  last_announce_msg?: string // 蛇形命名兼容
  lastScrapeSucceeded?: string
  last_scrape_succeeded?: string // 蛇形命名兼容
  trackerInfo?: TrackerInfo[]
  tracker_info?: TrackerInfo[] // 蛇形命名兼容

  // 实时状态字段（可能为null）
  progress?: number | null
  state?: string | null
  downloadSpeed?: number | null
  download_speed?: number | null // 蛇形命名兼容
  uploadSpeed?: number | null
  upload_speed?: number | null // 蛇形命名兼容
  downloadComplete?: boolean | null
  download_complete?: boolean | null // 蛇形命名兼容
  peers?: number | null
  seeds?: number | null
}

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
  lastScrapeSucceeded?: string
  last_scrape_succeeded?: string
  lastScrapeMsg?: string
  last_scrape_msg?: string
  // 新增字段：tracker状态（根据关键词看板判断）
  trackerStatus?: string
  tracker_status?: string
  // 新增字段：tracker主机地址
  trackerHost?: string
  tracker_host?: string
  // 新增字段：种子数量统计
  seederCount?: number | null
  seeder_count?: number | null
  leecherCount?: number | null
  leecher_count?: number | null
  downloadCount?: number | null
  download_count?: number | null
  // 命中当前 tracker 域名筛选的域名；未启用筛选或未命中时为 undefined
  matchedDomain?: string
  matched_domain?: string
}

export interface TorrentListData {
  total?: number
  count?: number
  total_count?: number
  list?: Torrent[]
  data?: Torrent[]
  items?: Torrent[]
}

export interface TorrentListResponse {
  status: string
  msg: string
  code: string
  data: Torrent[] | TorrentListData
}

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
}

/**
 * 批量添加种子请求
 */
export interface TorrentsAddBatchRequest {
  torrent_files: File[]
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
}

/**
 * 批量添加种子单个结果
 */
export interface TorrentAddBatchResultItem {
  file_name: string
  success: boolean
  info_id: string | null
  error: string | null
}

/**
 * 批量添加种子响应数据
 */
export interface TorrentAddBatchResponseData {
  total: number
  task_id?: string
  status?: 'queued' | 'completed' | 'partial' | 'failed'
  success_count?: number
  failed_count?: number
  results?: TorrentAddBatchResultItem[]
}

export interface TorrentDeleteRequest {
  info_id: string  // 必填：种子ID（单个）
  downloader_id: string  // 必填：下载器ID
  delete_data: number  // 必填：是否删除数据，1是true, 0是false
  id_recycle: number  // 必填：是否进入回收箱，1是true, 0是false
}

export interface ApiResponse<T = any> {
  status: string
  msg: string
  code: string
  data: T
}

/**
 * 获取种子列表
 */
export interface TorrentListParams {
  downloader_id?: string | string[]  // 支持单个ID或ID数组
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
  tracker_domain?: string | string[]  // Tracker主域名筛选，支持单个或多选
  status?: string | string[]  // 支持单个状态或状态数组
  active_only?: boolean  // 仅显示活动种子（实时速度>0，后端按活动集合缓存过滤）
  same_content_only?: boolean  // 仅显示同名、同大小且不同 InfoHash 的种子
  single_error_only?: boolean  // 仅显示错误且全局同内容唯一的种子
  skip?: number
  limit?: number
  sort_by?: string
  sort_order?: string
}

export type ActiveSnapshotStatus = 'not_ready' | 'expired' | 'partial' | 'ready_empty' | 'ready'

export interface TorrentListResponseData {
  list: Torrent[]
  total: number
  pageSize: number
  activeSnapshotReady?: boolean
  activeSnapshotStatus?: ActiveSnapshotStatus
}

/**
 * getList 多选参数的后端契约为逗号分隔字符串（FastAPI Optional[str]）。
 * axios 无自定义 paramsSerializer，数组会默认序列化成 `key[]=v` 形式，
 * 与后端参数名不匹配而被静默忽略——数组在此统一归一化为 join(',')，
 * 空数组剔除该键（桌面 index.vue 调用前的 join 由此成为无害冗余）。
 */
function normalizeTorrentListArrayParams(params?: TorrentListParams): TorrentListParams | undefined {
  if (!params) return params
  const normalized = { ...params }
  const multiValueKeys: Array<'downloader_id' | 'status' | 'tracker_domain'> = [
    'downloader_id',
    'status',
    'tracker_domain'
  ]
  multiValueKeys.forEach((key) => {
    const value = normalized[key]
    if (Array.isArray(value)) {
      if (value.length > 0) {
        normalized[key] = value.join(',')
      } else {
        delete normalized[key]
      }
    }
  })
  return normalized
}

export function getTorrentList(params?: TorrentListParams): Promise<ApiResponse<TorrentListResponseData>> {
  return request({
    url: '/torrents/getList',
    method: 'get',
    params: normalizeTorrentListArrayParams(params)
  }) as unknown as Promise<ApiResponse<TorrentListResponseData>>
}

/**
 * 获取已由 Tracker 同步任务采集到的 Tracker 主域名列表
 */
export function getTrackerDomains(): Promise<ApiResponse<string[]>> {
  return request({
    url: '/torrents/tracker-domains',
    method: 'get'
  }) as unknown as Promise<ApiResponse<string[]>>
}

/**
 * 添加种子
 */
export function addTorrent(data: TorrentAddRequest): Promise<ApiResponse<any>> {
  const formData = new FormData()

  // 必填字段
  formData.append('downloader_id', data.downloader_id)
  formData.append('save_path', data.save_path)
  formData.append('torrent_file', data.torrent_file)

  // 可选字段
  if (data.category) {
    formData.append('category', data.category)
  }
  if (data.tags) {
    formData.append('tags', data.tags)
  }
  if (data.paused !== undefined) {
    formData.append('paused', data.paused ? '1' : '0')
  }
  if (data.skip_hash_check !== undefined) {
    formData.append('skip_hash_check', data.skip_hash_check ? '1' : '0')
  }
  if (data.is_sequential_download !== undefined) {
    formData.append('is_sequential_download', data.is_sequential_download ? '1' : '0')
  }
  if (data.is_first_last_piece_priority !== undefined) {
    formData.append('is_first_last_piece_priority', data.is_first_last_piece_priority ? '1' : '0')
  }
  if (data.upload_limit !== undefined) {
    formData.append('upload_limit', data.upload_limit.toString())
  }
  if (data.download_limit !== undefined) {
    formData.append('download_limit', data.download_limit.toString())
  }

  return request({
    url: '/torrents/add',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 批量添加种子
 */
export function addTorrentsBatch(data: TorrentsAddBatchRequest): Promise<ApiResponse<TorrentAddBatchResponseData>> {
  const formData = new FormData()

  // 添加所有种子文件
  data.torrent_files.forEach(file => {
    formData.append('torrent_files', file)
  })

  // 必填字段
  formData.append('downloader_id', data.downloader_id)
  formData.append('save_path', data.save_path)

  // 可选字段
  if (data.category) {
    formData.append('category', data.category)
  }
  if (data.tags) {
    formData.append('tags', data.tags)
  }
  if (data.paused !== undefined) {
    formData.append('paused', data.paused ? '1' : '0')
  }
  if (data.skip_hash_check !== undefined) {
    formData.append('skip_hash_check', data.skip_hash_check ? '1' : '0')
  }
  if (data.is_sequential_download !== undefined) {
    formData.append('is_sequential_download', data.is_sequential_download ? '1' : '0')
  }
  if (data.is_first_last_piece_priority !== undefined) {
    formData.append('is_first_last_piece_priority', data.is_first_last_piece_priority ? '1' : '0')
  }
  if (data.upload_limit !== undefined) {
    formData.append('upload_limit', data.upload_limit.toString())
  }
  if (data.download_limit !== undefined) {
    formData.append('download_limit', data.download_limit.toString())
  }

  return request({
    url: '/torrents/add-batch',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  }) as unknown as Promise<ApiResponse<TorrentAddBatchResponseData>>
}

/**
 * 删除种子
 */
export function deleteTorrents(data: TorrentDeleteRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/torrents/delete',
    method: 'delete',
    params: data
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 按等级删除种子
 * @description 支持等级3(移至回收站)和等级4(标记为待删除)
 */
export interface DeleteWithLevelRequest {
  torrent_info_ids: string[]
  delete_level: number
  operator?: string
}

export function deleteTorrentsWithLevel(data: DeleteWithLevelRequest): Promise<ApiResponse<any>> {
  const params: Record<string, any> = {
    // 将数组转换为逗号分隔的字符串，避免Axios序列化为带方括号的格式
    torrent_info_ids: Array.isArray(data.torrent_info_ids) ? data.torrent_info_ids.join(',') : data.torrent_info_ids,
    delete_level: data.delete_level
  }
  if (data.operator) {
    params.operator = data.operator
  }

  return request({
    url: '/torrents/delete-with-level',
    method: 'delete',
    params: params
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 异步批量删除种子（提交任务）
 * @description 支持所有4个等级的删除，返回任务ID，需要轮询查询任务状态
 */
export interface BatchDeleteAsyncRequest {
  torrent_info_ids: string[]
  delete_level: number
  operator?: string
}

export interface BatchDeleteAsyncResponse {
  task_id: string | null
  total_count: number
  requested_count: number
  accepted_count: number
  skipped_count: number
  skipped_info_ids: string[]
  delete_level: number
}

export function deleteBatchAsync(data: BatchDeleteAsyncRequest): Promise<ApiResponse<BatchDeleteAsyncResponse>> {
  return request({
    url: '/torrents/delete-batch-async',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<BatchDeleteAsyncResponse>>
}

/**
 * 查询批量删除任务状态
 * @description 轮询此接口获取任务执行进度和结果
 */
export interface BatchDeleteStatusResponse {
  task_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'partial'
  total_count: number
  requested_count: number
  accepted_count: number
  skipped_count: number
  skipped_info_ids: string[]
  success_count: number
  failed_count: number
  error_message?: string
  created_time?: string
  started_time?: string
  completed_time?: string
  results: Array<{
    info_id: string
    result: any
  }>
  failed_items: Array<{
    info_id: string
    error: string
  }>
}

export function getBatchDeleteStatus(taskId: string): Promise<ApiResponse<BatchDeleteStatusResponse>> {
  return request({
    url: `/torrents/delete-batch-status/${taskId}`,
    method: 'get'
  }) as unknown as Promise<ApiResponse<BatchDeleteStatusResponse>>
}

/**
 * 暂停种子
 * @description 支持批量暂停多个下载器的种子，前端会自动分组调用
 */
export interface PauseTorrentsRequest {
  downloader_id: string
  hashes: string[]
}

export function pauseTorrents(params: PauseTorrentsRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/torrents/pause',
    method: 'post',
    data: params
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 恢复种子
 * @description 支持批量恢复多个下载器的种子，前端会自动分组调用
 */
export interface ResumeTorrentsRequest {
  downloader_id: string
  hashes: string[]
}

export function resumeTorrents(params: ResumeTorrentsRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/torrents/resume',
    method: 'post',
    data: params
  }) as unknown as Promise<ApiResponse<any>>
}


/**
 * 重新检查种子
 * @description 支持批量重检多个下载器的种子，前端会自动分组调用
 */
export interface RecheckTorrentsRequest {
  downloader_id: string
  hashes: string[]
}

export function recheckTorrents(params: RecheckTorrentsRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/torrents/recheck',
    method: 'post',
    data: params
  }) as unknown as Promise<ApiResponse<any>>
}


/**
 * 获取下载器列表（从缓存获取）
 */
export function getDownloaderList(params?: {
  enabled?: boolean
}): Promise<ApiResponse<DownloaderSimple[]>> {
  return request({
    url: '/downloader/getList',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResponse<DownloaderSimple[]>>
}

/**
 * 下载器简单信息接口
 */
export interface DownloaderSimple {
  downloader_id: string
  nickname: string
}

/**
 * Tracker操作相关接口参数类型
 */
export interface AddTrackerRequest {
  torrentInfoIds: string // 种子ID列表，多个用逗号分隔
  trackers: string // 多个tracker地址用分号分隔
}

export interface ReplaceTrackerRequest {
  torrentInfoIds: string // 被替换的tracker地址（注意：参数命名不准确）
  trackers: string // 替换成的tracker地址
}

export interface ModifyTrackerRequest {
  torrentInfoIds: string // 种子ID列表，多个用逗号分隔
  trackers: string // 新tracker列表，多个用分号分隔
}

/**
 * 添加tracker到种子
 * @description 向指定种子添加tracker地址，多个tracker用分号分隔
 * @param data torrentInfoIds(种子ID列表) 和 trackers(tracker地址列表)
 * @returns API响应
 */
export function addTracker(data: AddTrackerRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/tracker/addTracker',
    method: 'post',
    params: {
      torrentInfoIds: data.torrentInfoIds,
      trackers: data.trackers
    }
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 替换种子tracker地址
 * @description 根据tracker URL替换种子的tracker地址
 * @param data torrentInfoIds(被替换的tracker地址) 和 trackers(新tracker地址)
 * @returns API响应
 */
export function replaceTracker(data: ReplaceTrackerRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/tracker/replaceTracker',
    method: 'post',
    params: {
      torrentInfoIds: data.torrentInfoIds,
      trackers: data.trackers
    }
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 修改种子tracker地址
 * @description 完全替换种子的tracker列表
 * @param data torrentInfoIds(种子ID列表) 和 trackers(新tracker列表)
 * @returns API响应
 */
export function modifyTracker(data: ModifyTrackerRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/tracker/modifyTracker',
    method: 'post',
    params: {
      torrentInfoIds: data.torrentInfoIds,
      trackers: data.trackers
    }
  }) as unknown as Promise<ApiResponse<any>>
}

// ==================== 高级搜索相关接口 ====================

/**
 * 高级搜索请求参数
 */
export interface AdvancedSearchRequest {
  // 基础分页参数
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
  condition_groups?: Array<{
    logic: 'AND' | 'OR'
    conditions: Array<{
      field: string
      operator: string
      value: unknown
      mode?: 'include' | 'exclude'
    }>
  }>
  between_group_logics?: Array<'AND' | 'OR'>

  // 多选排除字段已废弃：前端 multiSelect 字段统一走 condition_groups + contains_any/contains_all
}

/**
 * 高级搜索响应数据
 */
export interface AdvancedSearchResponse {
  total: number
  page: number
  pageSize: number
  list: Torrent[]
}

/**
 * 执行高级搜索
 * @description 支持复杂条件组和AND/OR逻辑组合的高级搜索
 * @param searchParams 高级搜索参数
 * @returns 搜索结果
 */
export function advancedSearch(searchParams: AdvancedSearchRequest): Promise<ApiResponse<AdvancedSearchResponse>> {
  return request({
    url: '/advanced-search/advanced-search',
    method: 'post',
    data: searchParams
  }) as unknown as Promise<ApiResponse<AdvancedSearchResponse>>
}

// ==================== 搜索模板管理接口 ====================

/**
 * 创建搜索模板请求参数
 */
export interface CreateSearchTemplateRequest {
  name: string
  description?: string
  conditions: QueryTemplateConditions
  is_public?: boolean
}

/**
 * 更新搜索模板请求参数
 */
export interface UpdateSearchTemplateRequest {
  id: string
  name?: string
  description?: string
  conditions?: QueryTemplateConditions
  is_public?: boolean
}

/**
 * 搜索模板响应数据
 */
export interface SearchTemplate {
  id: string
  user_id: string
  name: string
  description: string | null
  conditions: QueryTemplateConditions
  is_default: boolean
  is_public: boolean
  usage_count: number
  created_time: string
  updated_time: string | null
}

/**
 * 获取搜索模板列表
 * @param params 查询参数
 * @returns 搜索模板列表
 */
export function getSearchTemplates(params?: {
  user_id?: string
  is_public?: boolean
}): Promise<ApiResponse<SearchTemplate[]>> {
  return request({
    url: '/advanced-search/search-templates',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResponse<SearchTemplate[]>>
}

/**
 * 创建搜索模板
 * @param data 模板数据
 * @returns 创建结果
 */
export function createSearchTemplate(data: CreateSearchTemplateRequest): Promise<ApiResponse<SearchTemplate>> {
  return request({
    url: '/advanced-search/search-templates',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<SearchTemplate>>
}

/**
 * 更新搜索模板
 * @param templateId 模板ID
 * @param data 更新数据
 * @returns 更新结果
 */
export function updateSearchTemplate(templateId: string, data: Omit<UpdateSearchTemplateRequest, 'id'>): Promise<ApiResponse<SearchTemplate>> {
  return request({
    url: `/advanced-search/search-templates/${templateId}`,
    method: 'put',
    data: {
      id: templateId,
      ...data
    }
  }) as unknown as Promise<ApiResponse<SearchTemplate>>
}

/**
 * 删除搜索模板
 * @param templateId 模板ID
 * @returns 删除结果
 */
export function deleteSearchTemplate(templateId: string): Promise<ApiResponse<any>> {
  return request({
    url: `/advanced-search/search-templates/${templateId}`,
    method: 'delete'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 应用搜索模板
 * @description 应用模板并执行搜索
 * @param templateId 模板ID
 * @returns 搜索结果
 */
export interface AppliedSearchTemplate {
  id: string
  name: string
  description: string | null
  conditions: QueryTemplateConditions
}

export function applySearchTemplate(templateId: string): Promise<ApiResponse<AppliedSearchTemplate>> {
  return request({
    url: `/advanced-search/search-templates/${templateId}/apply`,
    method: 'post'
  }) as unknown as Promise<ApiResponse<AppliedSearchTemplate>>
}

// ==================== v1.0.5 查询模板便捷方法 ====================

/**
 * 查询模板 conditions 结构（前端形态约定）
 * - source=simple：与 torrents/index.vue 的 listQuery 1:1 对齐
 * - source=advanced：AdvancedSearchBuilder 的 condition_groups 结构
 */
export interface QueryTemplateConditions {
  source: 'simple' | 'advanced'
  version: number
  listQuery?: {
    name_like?: string
    category_like?: string
    tags_like?: string
    downloader_id?: string[]
    status?: string[]
    tracker_domain?: string[]
    showActiveOnly?: boolean
    sort_by?: string
    sort_order?: 'asc' | 'desc'
  }
  condition_groups?: QueryTemplateConditionGroup[]
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface QueryTemplateCondition {
  id?: string
  field: string
  operator: string
  value: unknown
  mode?: 'include' | 'exclude'
  index?: number
}

export interface QueryTemplateConditionGroup {
  id?: string
  name?: string
  logic?: string
  betweenGroupLogic?: 'and' | 'or'
  conditions: QueryTemplateCondition[]
}

/**
 * 保存简单查询为模板（便捷封装）
 * @description 把 torrents 列表的 listQuery 状态封装为 source=simple 的 conditions，调用 createSearchTemplate
 * @param name 模板名称
 * @param listQuery 种子列表查询状态（index.vue 的 listQuery 对象）
 * @param options.description 模板描述
 * @param options.isPublic 是否公开
 * @returns 创建结果
 */
export function saveSimpleQueryAsTemplate(
  name: string,
  listQuery: QueryTemplateConditions['listQuery'],
  options?: { description?: string, isPublic?: boolean }
): Promise<ApiResponse<SearchTemplate>> {
  const conditions: QueryTemplateConditions = {
    source: 'simple',
    version: 1,
    listQuery: {
      name_like: listQuery?.name_like ?? '',
      category_like: listQuery?.category_like ?? '',
      tags_like: listQuery?.tags_like ?? '',
      downloader_id: listQuery?.downloader_id ? [...listQuery.downloader_id] : [],
      status: listQuery?.status ? [...listQuery.status] : [],
      tracker_domain: listQuery?.tracker_domain ? [...listQuery.tracker_domain] : [],
      showActiveOnly: listQuery?.showActiveOnly ?? false,
      sort_by: listQuery?.sort_by ?? 'added_date',
      sort_order: listQuery?.sort_order ?? 'desc'
    }
  }
  return createSearchTemplate({
    name,
    description: options?.description,
    conditions,
    is_public: options?.isPublic ?? false
  })
}

/**
 * 搜索预览
 * @description 预览搜索结果（不执行完整搜索）
 * @param params 搜索参数
 * @returns 预览结果
 */
export function previewAdvancedSearch(params: {
  name?: string
  tags?: string
  category?: string
  status?: string
  downloader_name?: string
  conditions_json?: string
  limit?: number
}): Promise<ApiResponse<AdvancedSearchResponse>> {
  return request({
    url: '/advanced-search/search-preview',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResponse<AdvancedSearchResponse>>
}

/**
 * 查询重复种子
 * @description 基于数据库查询符合条件的种子记录（宽松模式：即使没有重复也返回记录）
 * @param params 查询参数
 * @returns 重复种子列表（分页格式与getList一致）
 */
export interface DuplicateQuery {
  name_like?: string
  downloader_id?: string
  status?: string
  category_like?: string
  tags_like?: string
  active_only?: boolean
  min_size?: number
  page?: number
  pageSize?: number
  sort_by?: 'name' | 'size' | 'status' | 'ratio' | 'added_date'
  sort_order?: 'asc' | 'desc'
}

export interface DuplicateResponse {
  total: number
  page: number
  pageSize: number
  list: Torrent[]
  activeSnapshotReady?: boolean
  activeSnapshotStatus?: string
}

export function getDuplicateTorrents(params?: DuplicateQuery): Promise<ApiResponse<DuplicateResponse>> {
  return request({
    url: '/torrents/duplicates',
    method: 'post',
    data: params || {}
  }) as unknown as Promise<ApiResponse<DuplicateResponse>>
}

// ==================== 快捷删除重复种子接口 ====================

export interface QuickDeletePreviewItem {
  info_id: string
  downloader_id: string
  downloader_name: string
  name: string
  size: number | null
  status: string
  hash: string
}

export interface QuickDeletePreviewGroup {
  hash: string
  name: string
  size: number | null
  kept: QuickDeletePreviewItem[]
  to_delete: QuickDeletePreviewItem[]
  skipped: boolean
}

export interface QuickDeletePreviewResponse {
  total: number
  page: number
  pageSize: number
  total_groups: number
  total_delete: number
  skipped_groups: number
  list: QuickDeletePreviewGroup[]
}

export interface QuickDeletePreviewRequest {
  downloader_ids: string[]
  keep_downloader_ids: string[]
  page?: number
  pageSize?: number
}

export function getQuickDeleteDuplicatePreview(
  params: QuickDeletePreviewRequest
): Promise<ApiResponse<QuickDeletePreviewResponse>> {
  return request({
    url: '/torrents/duplicates/quick-delete-preview',
    method: 'post',
    data: params
  }) as unknown as Promise<ApiResponse<QuickDeletePreviewResponse>>
}

export interface QuickDeleteRequest {
  downloader_ids: string[]
  keep_downloader_ids: string[]
  delete_level?: number
  notify_on_complete?: boolean
}

export interface QuickDeleteResponse {
  task_id: string | null
  total_count: number
  requested_count: number
  accepted_count: number
  skipped_count: number
  skipped_info_ids: string[]
  delete_level: number
}

export function quickDeleteDuplicates(params: QuickDeleteRequest): Promise<ApiResponse<QuickDeleteResponse>> {
  return request({
    url: '/torrents/duplicates/quick-delete',
    method: 'post',
    data: params
  }) as unknown as Promise<ApiResponse<QuickDeleteResponse>>
}



// ==================== 种子转移相关接口 ====================

/**
 * 单个种子转移请求参数
 */
export interface SeedTransferRequest {
  source_downloader_id: string
  target_downloader_id: string
  info_hash: string
  target_path: string
  delete_source: boolean
}

/**
 * 种子转移响应数据
 */
export interface SeedTransferResponseData {
  success: boolean
  transfer_status: string
  torrent_name?: string
  source_downloader_id: string
  source_downloader_name?: string
  target_downloader_id: string
  target_downloader_name?: string
  info_hash: string
  source_path?: string
  target_path: string
  delete_source: boolean
  transfer_duration?: number
  error_message?: string | null
}

/**
 * 批量种子转移请求参数
 */
export interface SeedTransferBatchRequest {
  source_downloader_id: string
  target_downloader_id: string
  info_hashes: string[]
  target_path: string
  delete_source: boolean
}

/**
 * 批量种子转移响应数据
 */
export interface SeedTransferBatchResponseData {
  total_count: number
  success_count: number
  failed_count: number
  results: SeedTransferResponseData[]
}

/**
 * 单个种子转移
 * @description 将单个种子从源下载器转移到目标下载器
 * @param data 转移请求参数
 * @returns 转移结果
 */
export function transferSeed(data: SeedTransferRequest): Promise<ApiResponse<SeedTransferResponseData>> {
  return request({
    url: "/torrents/transfer",
    method: "post",
    data: data
  }) as unknown as Promise<ApiResponse<SeedTransferResponseData>>
}

/**
 * 批量种子转移
 * @description 将多个种子从源下载器批量转移到目标下载器
 * @param data 批量转移请求参数
 * @returns 批量转移结果
 */
export function transferSeedsBatch(data: SeedTransferBatchRequest): Promise<ApiResponse<SeedTransferBatchResponseData>> {
  return request({
    url: "/torrents/batch-transfer",
    method: "post",
    data: data
  }) as unknown as Promise<ApiResponse<SeedTransferBatchResponseData>>
}

// ==================== 下载器路径相关接口 ====================

/**
 * 下载器路径信息
 */
export interface DownloaderPath {
  id: number
  downloader_id: number
  path_type: string // "default" | "active"
  path_value: string
  is_enabled: boolean
  torrent_count: number
  last_updated_time: string
}

/**
 * 获取下载器路径列表响应数据
 */
export interface DownloaderPathsResponseData {
  downloader_id: number
  downloader_name: string
  paths: DownloaderPath[]
}

/**
 * 获取下载器路径列表
 * @description 获取指定下载器的所有路径信息（包括默认路径和在用路径）
 * @param downloaderId 下载器ID
 * @returns 路径列表
 */
export function getDownloaderPaths(downloaderId: string | number): Promise<ApiResponse<DownloaderPathsResponseData>> {
  return request({
    url: `/downloaders/${downloaderId}/paths`,
    method: "get"
  }) as unknown as Promise<ApiResponse<DownloaderPathsResponseData>>
}


// ==================== 种子文件备份管理接口 ====================

/**
 * 种子文件备份信息接口
 */
export interface TorrentBackup {
  id: number
  info_hash: string
  task_name: string
  torrent_name: string
  downloader_id: number | string
  downloader_nickname?: string | null
  file_path: string
  created_at: string
  updated_at: string
  uploader_username: string
}

/**
 * 获取种子文件备份列表请求参数
 */
export interface TorrentBackupListParams {
  page: number
  pageSize: number
  downloader_id?: number | string
}

/**
 * 种子文件备份列表响应数据
 */
export interface TorrentBackupListResponse {
  total: number
  page: number
  pageSize: number
  list: TorrentBackup[]
}

/**
 * 获取种子文件备份列表
 * @param params 查询参数
 * @returns 备份列表
 */
export function getTorrentBackupList(params: TorrentBackupListParams): Promise<ApiResponse<TorrentBackupListResponse>> {
  return request({
    url: '/torrents/backup',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResponse<TorrentBackupListResponse>>
}

/**
 * 去重种子文件备份
 * @returns 去重结果
 */
export function deduplicateTorrentBackup(): Promise<ApiResponse<any>> {
  return request({
    url: '/torrents/backup/deduplicate',
    method: 'post'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 导出种子文件备份
 * @param infoHashes Info Hash列表，逗号分隔
 * @returns 导出文件流
 */
export function exportTorrentBackup(infoHashes: string): Promise<Blob> {
  return request({
    url: '/torrents/backup/export',
    method: 'get',
    params: { info_hashes: infoHashes },
    responseType: 'blob'
  }) as unknown as Promise<Blob>
}

/**
 * 下载单个种子文件备份
 * @param infoHash Info Hash
 * @returns 种子文件流
 */
export function downloadTorrentBackup(infoHash: string): Promise<Blob> {
  return request({
    url: `/torrents/backup/download/${infoHash}`,
    method: 'get',
    responseType: 'blob'
  }) as unknown as Promise<Blob>
}

/**
 * 删除种子文件备份
 * @param infoHash Info Hash
 * @returns 删除结果
 */
export function deleteTorrentBackup(infoHash: string): Promise<ApiResponse<any>> {
  return request({
    url: `/torrents/backup/${infoHash}`,
    method: 'delete'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 导入种子文件备份
 * @param downloaderId 目标下载器ID
 * @param files 种子文件列表
 * @returns 导入结果
 */
export function importTorrentBackup(downloaderId: string, files: File[]): Promise<ApiResponse<any>> {
  if (!files || files.length === 0) {
    return Promise.reject(new Error('No files to upload'))
  }

  const formData = new FormData()
  files
    .filter(file => !!file)
    .forEach(file => {
      formData.append('files', file)
    })

  return request({
    url: `/torrents/backup/import?downloader_id=${downloaderId}`,
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 修改种子保存路径请求
 */
export interface SetLocationRequest {
  downloader_id: string
  hashes: string[]
  target_path: string
  move_files: boolean
  operator?: string
}

/**
 * 修改种子保存路径响应
 */
export interface SetLocationResponse {
  success: boolean
  moved_count: number
  failed_count: number
  error_message: string | null
}

/**
 * 修改种子保存路径
 * @param data 修改路径请求参数
 * @returns 修改结果
 */
export function setTorrentLocation(data: SetLocationRequest): Promise<ApiResponse<SetLocationResponse>> {
  return request({
    url: '/torrents/set-location',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<SetLocationResponse>>
}

// ==================== Tracker汇报API ====================

/**
 * Tracker汇报请求参数
 */
export interface ReannounceRequest {
  hashes?: string[]  // 种子hash列表
  info_ids?: string[]  // 种子info_id列表
  downloader_id?: string | number  // 下载器ID
}

/**
 * Tracker汇报响应
 */
export interface ReannounceResponse {
  success_count: number
  failed_count: number
  message: string
}

/**
 * Tracker汇报（选中种子）
 */
export function reannounceTorrents(data: ReannounceRequest): Promise<ApiResponse<ReannounceResponse>> {
  return request({
    url: '/torrent-status/reannounce',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<ReannounceResponse>>
}

/**
 * Tracker汇报（按下载器）
 */
export function reannounceByDownloader(downloaderId: string | number): Promise<ApiResponse<ReannounceResponse>> {
  return request({
    url: '/torrent-status/reannounce-by-downloader',
    method: 'post',
    data: { downloader_id: downloaderId }
  }) as unknown as Promise<ApiResponse<ReannounceResponse>>
}

/**
 * Tracker汇报（全局）
 */
export function reannounceAll(): Promise<ApiResponse<ReannounceResponse>> {
  return request({
    url: '/torrent-status/reannounce-all',
    method: 'post'
  }) as unknown as Promise<ApiResponse<ReannounceResponse>>
}

// ==================== 实时速度监控接口 ====================

/**
 * 活跃种子实时数据（包含速度和进度）
 */
export interface ActiveTorrentSpeed {
  hash: string
  downloaderId?: string
  downloader_id?: string
  downloadSpeed: number  // bytes/s
  uploadSpeed: number    // bytes/s
  progress: number       // 下载进度（百分比，0-100）
  /** 下载器归一化状态；旧服务端可能不返回，前端需兼容缺省。 */
  status?: string
  /** 与速度解耦的下载完成证据（速度为 0 时仍可能为 true）。 */
  downloadComplete?: boolean
  download_complete?: boolean
  num_seeds: number
  num_leechs: number
}

export interface RuntimeStateReconcileItem {
  downloader_id: string
  hash: string
}

export interface RuntimeStateReconcileData {
  list: ActiveTorrentSpeed[]
  missing: RuntimeStateReconcileItem[]
}

/**
 * 获取活跃种子的实时速度和进度（轻量级接口，用于1秒轮询）
 * 仅返回 downloadSpeed > 0 或 uploadSpeed > 0 的种子
 */
export function getActiveTorrents(): Promise<ApiResponse<ActiveTorrentSpeed[]>> {
  return request({
    url: '/torrents/active-torrents',
    method: 'get'
  }) as unknown as Promise<ApiResponse<ActiveTorrentSpeed[]>>
}

/**
 * 低频核验当前可见但连续未出现在速度快照中的种子。
 * 后端返回已找到的实时状态与暂未找到的复合键，missing 不代表已删除。
 */
export function reconcileRuntimeTorrentStates(
  items: RuntimeStateReconcileItem[]
): Promise<ApiResponse<RuntimeStateReconcileData>> {
  return request({
    url: '/torrents/runtime-state/reconcile',
    method: 'post',
    data: { items }
  }) as unknown as Promise<ApiResponse<RuntimeStateReconcileData>>
}
