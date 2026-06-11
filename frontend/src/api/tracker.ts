/* eslint-disable camelcase */
import request from '@/utils/request'

// ==================== 类型定义 ====================

/**
 * Tracker关键词配置
 */
export interface TrackerKeyword {
  keyword_id: string
  keyword_type: 'candidate' | 'ignored' | 'success' | 'failed'
  keyword: string
  language: string
  priority: number
  enabled: boolean
  category?: string
  description?: string
  create_time?: string
  update_time?: string
}

/**
 * 关键词列表查询参数
 */
export interface TrackerKeywordListParams {
  keyword_type?: 'candidate' | 'ignored' | 'success' | 'failed'
  language?: string
  enabled?: boolean
  keyword?: string
  page?: number
  pageSize?: number  // ✅ 修复：使用驼峰命名 pageSize
}

/**
 * 关键词创建/更新请求
 */
export interface TrackerKeywordRequest {
  keyword_type: 'candidate' | 'ignored' | 'success' | 'failed'
  keyword: string
  language?: string
  priority?: number
  enabled?: boolean
  category?: string
  description?: string
}

/**
 * 批量添加关键词请求
 */
export interface BatchAddKeywordsRequest {
  keywords: TrackerKeywordRequest[]
}

/**
 * 批量删除关键词请求
 */
export interface BatchDeleteKeywordsRequest {
  keyword_ids: string[]
}

/**
 * Tracker消息日志
 */
export interface TrackerMessageLog {
  log_id: string
  tracker_host: string
  msg: string
  first_seen: string
  last_seen: string
  occurrence_count: number
  is_processed: boolean
  keyword_type?: 'success' | 'failed'
  sample_torrents?: any
  sample_urls?: any
  create_time?: string
  update_time?: string
}

/**
 * 消息记录列表查询参数
 */
export interface TrackerMessageLogListParams {
  tracker_host?: string
  msg?: string
  is_processed?: boolean
  keyword_type?: 'success' | 'failed'
  first_seen_min?: string
  first_seen_max?: string
  page?: number
  pageSize?: number  // ✅ 修复：使用驼峰命名 pageSize
}

/**
 * 消息记录更新请求
 */
export interface TrackerMessageLogUpdateRequest {
  is_processed?: boolean
  keyword_type?: 'success' | 'failed'
}

/**
 * 批量删除消息记录请求
 */
export interface BatchDeleteMessagesRequest {
  log_ids: string[]
}

/**
 * 批量添加到关键词池请求
 */
export interface BatchAddToKeywordsRequest {
  log_ids: string[]
  keyword_type: 'success' | 'failed'
  language?: string
  priority?: number
  enabled?: boolean
}

/**
 * 测试匹配请求
 */
export interface TestMatchRequest {
  tracker_host: string
  msg: string
}

/**
 * 测试匹配响应
 */
export interface TestMatchResponse {
  result: 'success' | 'failed'
  matched_keywords: TrackerKeyword[]
  unmatched_reason?: string
}

/**
 * API响应格式
 */
export interface ApiResponse<T = any> {
  code: string
  msg: string
  data: T
  status: string
}

/**
 * 分页列表响应
 */
export interface PaginatedResponse<T> {
  total: number
  page: number
  pageSize: number  // 修复：使用后端返回的pageSize字段
  list: T[]         // 修复：使用后端返回的list字段
}

// ==================== 关键词管理API ====================

/**
 * 获取关键词列表
 */
export function getKeywordList(params?: TrackerKeywordListParams): Promise<ApiResponse<PaginatedResponse<TrackerKeyword>>> {
  return request({
    url: '/tracker-keywords',
    method: 'get',
    params
  }) as unknown as Promise<ApiResponse<PaginatedResponse<TrackerKeyword>>>
}

/**
 * 获取关键词详情
 */
export function getKeywordDetail(keywordId: string): Promise<ApiResponse<TrackerKeyword>> {
  return request({
    url: `/tracker-keywords/${keywordId}`,
    method: 'get'
  }) as unknown as Promise<ApiResponse<TrackerKeyword>>
}

/**
 * 创建关键词
 */
export function createKeyword(data: TrackerKeywordRequest): Promise<ApiResponse<TrackerKeyword>> {
  return request({
    url: '/tracker-keywords',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<TrackerKeyword>>
}

/**
 * 更新关键词
 */
export function updateKeyword(keywordId: string, data: TrackerKeywordRequest): Promise<ApiResponse<TrackerKeyword>> {
  return request({
    url: `/tracker-keywords/${keywordId}`,
    method: 'put',
    data
  }) as unknown as Promise<ApiResponse<TrackerKeyword>>
}

/**
 * 删除关键词
 */
export function deleteKeyword(keywordId: string): Promise<ApiResponse<any>> {
  return request({
    url: `/tracker-keywords/${keywordId}`,
    method: 'delete'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 批量添加关键词
 */
export function batchAddKeywords(data: BatchAddKeywordsRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/tracker-keywords/batch',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 批量删除关键词
 */
export function batchDeleteKeywords(data: BatchDeleteKeywordsRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/tracker-keywords/batch/delete',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<any>>
}

// ==================== 消息记录管理API ====================

/**
 * 获取消息记录列表
 */
export function getMessageLogList(params?: TrackerMessageLogListParams): Promise<ApiResponse<PaginatedResponse<TrackerMessageLog>>> {
  return request({
    url: '/tracker-messages',
    method: 'get',
    params
  }) as unknown as Promise<ApiResponse<PaginatedResponse<TrackerMessageLog>>>
}

/**
 * 获取消息记录详情
 */
export function getMessageLogDetail(logId: string): Promise<ApiResponse<TrackerMessageLog>> {
  return request({
    url: `/tracker-messages/${logId}`,
    method: 'get'
  }) as unknown as Promise<ApiResponse<TrackerMessageLog>>
}

/**
 * 更新消息记录
 */
export function updateMessageLog(logId: string, data: TrackerMessageLogUpdateRequest): Promise<ApiResponse<TrackerMessageLog>> {
  return request({
    url: `/tracker-messages/${logId}`,
    method: 'put',
    data
  }) as unknown as Promise<ApiResponse<TrackerMessageLog>>
}

/**
 * 删除消息记录
 */
export function deleteMessageLog(logId: string): Promise<ApiResponse<any>> {
  return request({
    url: `/tracker-messages/${logId}`,
    method: 'delete'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 批量删除消息记录
 */
export function batchDeleteMessages(data: BatchDeleteMessagesRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/tracker-messages/batch/delete',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 批量添加到关键词池
 */
export function batchAddToKeywords(data: BatchAddToKeywordsRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/tracker-messages/batch/add-to-pool',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 获取消息统计信息
 */
export function getMessageStatistics(): Promise<ApiResponse<{
  total: number
  unprocessed: number
  success: number
  failure: number
}>> {
  return request({
    url: '/tracker-messages/statistics',
    method: 'get'
  }) as unknown as Promise<ApiResponse<{
    total: number
    unprocessed: number
    success: number
    failure: number
  }>>
}

// ==================== 测试工具API ====================

/**
 * 测试匹配
 */
export function testMatch(data: TestMatchRequest): Promise<ApiResponse<TestMatchResponse>> {
  return request({
    url: '/tracker-test/match',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<TestMatchResponse>>
}

// ==================== 池子管理API ====================

/**
 * 池子类型
 */
export type PoolType = 'candidate' | 'ignored' | 'success' | 'failed'

/**
 * 池子关键词项（用于看板展示）
 */
export interface PoolKeyword {
  keyword_id: string
  keyword: string
  pool_type: PoolType
  create_time?: string
}

/**
 * 获取池子关键词列表（用于看板）
 */
export interface GetPoolKeywordsParams {
  pool_type: PoolType
  keyword?: string
  page?: number
  page_size?: number
}

export function getPoolKeywords(params: GetPoolKeywordsParams): Promise<ApiResponse<PaginatedResponse<PoolKeyword>>> {
  return request({
    url: '/tracker-keywords/pool',
    method: 'get',
    params
  }) as unknown as Promise<ApiResponse<PaginatedResponse<PoolKeyword>>>
}

/**
 * 移动关键词到指定池子
 */
export interface MoveKeywordToPoolRequest {
  keyword_id: string
  target_pool: PoolType
}

export function moveKeywordToPool(data: MoveKeywordToPoolRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/tracker-keywords/move',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 批量移动关键词到指定池子
 */
export interface BatchMoveKeywordsRequest {
  keyword_ids: string[]
  target_pool: PoolType
}

export function batchMoveKeywords(data: BatchMoveKeywordsRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/tracker-keywords/batch-move',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 获取所有池子的统计信息
 */
export interface PoolStatistics {
  candidate_count: number
  ignored_count: number
  success_count: number
  failed_count: number
}

export function getPoolStatistics(): Promise<ApiResponse<PoolStatistics>> {
  return request({
    url: '/tracker-keywords/pool/statistics',
    method: 'get'
  }) as unknown as Promise<ApiResponse<PoolStatistics>>
}

/**
 * 全局搜索参数
 */
export interface SearchAllPoolsParams {
  keyword?: string
  pool_types?: string  // 逗号分隔的池子类型，如 "candidate,success"
  time_range?: string  // today/week/month
  sort_by?: string  // time_desc/time_asc/name_asc
  page?: number
  page_size?: number
}

/**
 * 搜索结果项
 */
export interface SearchResultItem {
  keyword_id: string
  keyword: string
  pool_type: PoolType
  pool_label: string
  create_time: string
}

/**
 * 全局搜索所有池子的关键词
 */
export function searchAllPools(params?: SearchAllPoolsParams): Promise<ApiResponse<PaginatedResponse<SearchResultItem>>> {
  return request({
    url: '/tracker-keywords/pool/search-all',
    method: 'get',
    params
  }) as unknown as Promise<ApiResponse<PaginatedResponse<SearchResultItem>>>
}

// ==================== Tracker汇报配置API ====================

/**
 * Tracker汇报配置
 */
export interface TrackerReannounceConfig {
  config_id: string
  domain_pattern: string
  domain_display_name: string
  interval_minutes: number
  enabled: boolean
  last_reannounce_time?: string
  create_time?: string
  update_time?: string
}

/**
 * 汇报配置列表查询参数
 */
export interface ReannounceConfigListParams {
  domain_display_name?: string
  enabled?: boolean
  page?: number
  pageSize?: number  // ✅ 修复：使用驼峰命名 pageSize
}

/**
 * 创建汇报配置请求
 */
export interface CreateReannounceConfigRequest {
  domain_pattern: string
  domain_display_name?: string
  interval_minutes: number
  enabled: boolean
}

/**
 * 更新汇报配置请求
 */
export interface UpdateReannounceConfigRequest {
  domain_pattern?: string
  domain_display_name?: string
  interval_minutes?: number
  enabled?: boolean
}

/**
 * 自动检测域名响应
 */
export interface AutoDetectDomainsResponse {
  detected: number
  created: number
  configs: TrackerReannounceConfig[]
}

/**
 * 获取汇报配置列表
 */
export function getReannounceConfigs(params?: ReannounceConfigListParams): Promise<ApiResponse<PaginatedResponse<TrackerReannounceConfig>>> {
  return request({
    url: '/tracker-reannounce/configs',
    method: 'get',
    params
  }) as unknown as Promise<ApiResponse<PaginatedResponse<TrackerReannounceConfig>>>
}

/**
 * 创建汇报配置
 */
export function createReannounceConfig(data: CreateReannounceConfigRequest): Promise<ApiResponse<TrackerReannounceConfig>> {
  return request({
    url: '/tracker-reannounce/configs',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<TrackerReannounceConfig>>
}

/**
 * 更新汇报配置
 */
export function updateReannounceConfig(configId: string, data: UpdateReannounceConfigRequest): Promise<ApiResponse<TrackerReannounceConfig>> {
  return request({
    url: `/tracker-reannounce/configs/${configId}`,
    method: 'put',
    data
  }) as unknown as Promise<ApiResponse<TrackerReannounceConfig>>
}

/**
 * 删除汇报配置
 */
export function deleteReannounceConfig(configId: string): Promise<ApiResponse<any>> {
  return request({
    url: `/tracker-reannounce/configs/${configId}`,
    method: 'delete'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 自动检测域名
 */
export function autoDetectDomains(): Promise<ApiResponse<AutoDetectDomainsResponse>> {
  return request({
    url: '/tracker-reannounce/configs/auto-detect',
    method: 'post'
  }) as unknown as Promise<ApiResponse<AutoDetectDomainsResponse>>
}

// ==================== 批量更新类型 ====================

/**
 * 批量更新汇报配置项
 */
export interface BatchUpdateReannounceConfigItem {
  config_id: string
  domain_pattern?: string
  domain_display_name?: string
  interval_minutes?: number
  enabled?: boolean
}

/**
 * 批量更新结果项
 */
export interface BatchUpdateResultItem {
  config_id: string
  success: boolean
  message?: string
}

/**
 * 批量更新响应
 */
export interface BatchUpdateResponse {
  success_count: number
  failed_count: number
  results: BatchUpdateResultItem[]
}

/**
 * 批量更新汇报配置
 */
export function batchUpdateReannounceConfigs(data: BatchUpdateReannounceConfigItem[]): Promise<ApiResponse<BatchUpdateResponse>> {
  return request({
    url: '/tracker-reannounce/configs/batch',
    method: 'put',
    data: { items: data }
  }) as unknown as Promise<ApiResponse<BatchUpdateResponse>>
}
