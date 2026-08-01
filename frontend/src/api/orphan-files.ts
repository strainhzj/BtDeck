/* eslint-disable camelcase */
import request from '@/utils/request'

// ========== 类型定义 ==========

/**
 * 孤儿文件项
 */
export interface OrphanFileItem {
  id: number
  scan_id: string
  file_path: string
  file_size: number
  mtime: string | null
  downloader_id: string | null
  confidence: OrphanConfidence
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

/**
 * 分页响应格式（符合项目规范）
 * ⚠️ 必须使用 pageSize 和 list，严禁使用其他变体
 */
export interface OrphanListResponse {
  total: number
  page: number
  pageSize: number
  list: OrphanFileItem[]
  scan_context: OrphanScanContext
}

/**
 * 数据库中持久化的扫描状态；busy 只属于触发响应，不在此联合中。
 */
export type OrphanScanRecordStatus = 'running' | 'completed' | 'failed'

/**
 * 置信度：high=在线精筛判定，low=离线降级目录粗筛判定
 */
export type OrphanConfidence = 'high' | 'low'

/**
 * 状态筛选：pending=待清理，ignored=已忽视，deleted=已清理
 */
export type OrphanStatusFilter = 'pending' | 'ignored' | 'deleted'

export interface OrphanScanRecord {
  scan_id: string
  scan_time: string
  scan_type: string
  total_paths_scanned: number
  total_files_scanned: number
  total_orphans: number
  total_orphan_size: number
  status: OrphanScanRecordStatus
  error_message: string | null
  operator: string | null
  created_at: string | null
}

/**
 * 分页接口返回的页面权威扫描上下文。
 * running 时 display_scan 为 null；failed 时可只读回退最近成功批次。
 */
export interface OrphanScanContext {
  latest_attempt: OrphanScanRecord | null
  display_scan: OrphanScanRecord | null
  remaining_count: number
  remaining_size: number
  ignored_count: number
  cleanup_allowed: boolean
  cleanup_block_reason: string | null
}

export interface OrphanScanCompletedResult {
  scan_id: string
  scan_time: string
  scan_type: string
  total_paths_scanned: number
  total_files_scanned: number
  total_orphans: number
  total_orphan_size: number
  status: 'completed'
}

export interface OrphanScanFailedResult {
  scan_id: string
  status: 'failed'
  error: string
}

export interface OrphanScanBusyResult {
  status: 'busy'
  error: string
}

export type OrphanScanTriggerResult =
  | OrphanScanCompletedResult
  | OrphanScanFailedResult
  | OrphanScanBusyResult

/**
 * 清理预览结果。后端仍会在执行时重新校验 scan_id 与安全门禁。
 */
export interface CleanupPreviewSuccess {
  rejected?: false
  total_count: number
  total_size: number
  /** 预览结果中低置信度（离线降级粗筛）文件数量；>0 时前端应警告误判风险。 */
  low_confidence_count?: number
  items: Array<{
    id: number
    file_path: string
    file_size: number
  }>
}

export interface CleanupPreviewRejected {
  rejected: true
  reason: string
  error: string
  total_count: 0
  total_size: 0
  items: []
}

export type CleanupPreviewResult = CleanupPreviewSuccess | CleanupPreviewRejected

/**
 * 清理执行结果
 */
export interface CleanupFailedItem {
  id: number
  file_path?: string
  reason: string
}

export interface CleanupSuccessResult {
  rejected?: false
  success_count: number
  failed_count: number
  failed_list: CleanupFailedItem[]
  total_size: number
}

export interface CleanupRejectedResult {
  rejected: true
  error: string
  success_count: 0
  failed_count: number
  failed_list: CleanupFailedItem[]
  total_size: 0
}

export type CleanupResult = CleanupSuccessResult | CleanupRejectedResult

/** 主动清理异步任务状态 */
export interface CleanupJobResult {
  task_id: string
  operation_type: 'cleanup'
  status: 'pending' | 'running' | 'completed' | 'partial' | 'failed'
  scan_id: string | null
  total_count: number
  success_count: number
  purged_count: number
  failed_count: number
  failed_list: CleanupFailedItem[]
  total_size: number
  error_message: string | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

// 兼容既有调用方的公开类型名。
export type LatestScanResult = OrphanScanRecord
export type ScanResult = OrphanScanTriggerResult

/**
 * 标准API响应格式
 */
export interface ApiResponse<T = unknown> {
  code: string
  msg: string
  data: T
  status: string
}

// ========== 请求参数 ==========

export interface OrphanListParams {
  page?: number
  page_size?: number
  downloader_id?: string
  min_size?: number
  path_like?: string
  status?: OrphanStatusFilter
}

export interface CleanupRequest {
  scan_id: string
  orphan_ids: number[]
}

export interface IgnoreRequest {
  scan_id?: string
  orphan_ids: number[]
  ignored: boolean
}

// ========== API 函数 ==========

/**
 * 获取最新扫描结果
 */
export function getLatestScan(): Promise<ApiResponse<LatestScanResult | null>> {
  return request({
    url: '/orphan-files/latest',
    method: 'get'
  }) as unknown as Promise<ApiResponse<LatestScanResult | null>>
}

/**
 * 分页查询孤儿文件列表
 */
export function getOrphanList(params: OrphanListParams): Promise<ApiResponse<OrphanListResponse>> {
  return request({
    url: '/orphan-files/list',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResponse<OrphanListResponse>>
}

/**
 * 手动触发扫描
 */
export function triggerScan(): Promise<ApiResponse<OrphanScanTriggerResult>> {
  return request({
    url: '/orphan-files/scan',
    method: 'post'
  }) as unknown as Promise<ApiResponse<OrphanScanTriggerResult>>
}

/**
 * 清理预览
 */
export function cleanupPreview(data: CleanupRequest): Promise<ApiResponse<CleanupPreviewResult>> {
  return request({
    url: '/orphan-files/cleanup-preview',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<CleanupPreviewResult>>
}

/**
 * 提交手动清理任务。实际清理在后台完成，终态通过通知中心送达。
 */
export function cleanupOrphans(data: CleanupRequest): Promise<ApiResponse<CleanupJobResult>> {
  return request({
    url: '/orphan-files/cleanup',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<CleanupJobResult>>
}

/** 查询主动清理任务状态；完成/失败结果同时会进入通知中心。 */
export function getCleanupJobStatus(taskId: string): Promise<ApiResponse<CleanupJobResult>> {
  return request({
    url: `/orphan-files/cleanup-jobs/${taskId}`,
    method: 'get'
  }) as unknown as Promise<ApiResponse<CleanupJobResult>>
}

/**
 * 忽视操作结果（与清理结果结构一致，便于统一处理）
 */
export type IgnoreResult = CleanupSuccessResult | CleanupRejectedResult

/**
 * 设置/取消孤儿文件的忽视态
 *
 * 被忽视的孤儿受保护：定时任务不自动删除，手动清理也被拒绝，但仍可在列表查询。
 */
export function setIgnored(data: IgnoreRequest): Promise<ApiResponse<IgnoreResult>> {
  return request({
    url: '/orphan-files/ignore',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<IgnoreResult>>
}

// ==================== 隔离区管理（恢复 / 立即彻底删除 / 列表） ====================

/**
 * 隔离区列表项
 */
export interface QuarantineItem {
  canonical_path: string
  downloader_id: string | null
  downloader_name: string | null
  quarantine_path: string | null
  quarantine_root: string | null
  quarantined_at: string | null
  /** 预计物理删除时间（隔离保留期到期） */
  purge_after: string | null
  file_size: number
  confidence: OrphanConfidence
}

export interface QuarantineListResult {
  total: number
  page: number
  pageSize: number
  list: QuarantineItem[]
}

export interface QuarantineListQuery {
  page?: number
  page_size?: number
  downloader_id?: string
  path_like?: string
}

/**
 * 隔离区操作请求（恢复 / 立即彻底删除共用）
 */
export interface QuarantineActionRequest {
  canonical_paths: string[]
}

export interface QuarantineFailedItem {
  canonical_path: string
  quarantine_path?: string | null
  reason: string
}

export interface RestoreResult {
  rejected?: boolean
  restored_count: number
  failed_count: number
  failed_list: QuarantineFailedItem[]
}

export interface PurgeResult {
  task_id: string
  status: 'pending' | 'running' | 'completed' | 'partial' | 'failed'
  total_count: number
  purged_count: number
  failed_count: number
  failed_list: QuarantineFailedItem[]
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

/**
 * 查询隔离区文件列表
 */
export function getQuarantineList(params: QuarantineListQuery): Promise<ApiResponse<QuarantineListResult>> {
  return request({
    url: '/orphan-files/quarantine',
    method: 'get',
    params
  }) as unknown as Promise<ApiResponse<QuarantineListResult>>
}

/**
 * 从隔离区恢复文件到原位置（可逆操作的逆操作）
 */
export function restoreQuarantined(data: QuarantineActionRequest): Promise<ApiResponse<RestoreResult>> {
  return request({
    url: '/orphan-files/restore',
    method: 'post',
    data: data,
    timeout: 120000
  }) as unknown as Promise<ApiResponse<RestoreResult>>
}

/**
 * 提交隔离区彻底删除任务（立即返回，结果由通知中心送达）
 */
export function purgeQuarantineNow(data: QuarantineActionRequest): Promise<ApiResponse<PurgeResult>> {
  return request({
    url: '/orphan-files/purge',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<PurgeResult>>
}

/** 查询隔离区彻底删除任务状态 */
export function getPurgeJobStatus(taskId: string): Promise<ApiResponse<PurgeResult>> {
  return request({
    url: `/orphan-files/purge-jobs/${taskId}`,
    method: 'get'
  }) as unknown as Promise<ApiResponse<PurgeResult>>
}
