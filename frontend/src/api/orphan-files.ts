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
 * 文件夹聚合行（后端 group_by_folder=true 时返回，仅前端展示用，不提交后端）
 *
 * 折叠模式下，同一直接父目录下 ≥2 个孤儿文件聚合为一行；单文件（cnt=1）
 * 由后端直接返回 OrphanFileItem（无 _is_folder），保持原样。
 * 删除/忽视等操作始终展开为子文件 id 逐个提交，本类型不影响后端语义。
 * 字段与后端 get_orphan_list_grouped 返回的 OrphanFolderRow DTO 对齐（snake_case）。
 */
export interface OrphanFolderRow {
  /** 类型标记，用于列模板分支与 isFolderRow 类型守卫 */
  _is_folder: true
  /** row-key 用稳定身份，形如 'folder:<folder_path>' */
  folder_key: string
  /** 直接父目录路径 */
  folder_path: string
  /** 子文件数 */
  child_count: number
  /** 子文件列表（含完整 OrphanFileItem 字段） */
  children: OrphanFileItem[]
  /** 子文件 id 列表，用于展开提交 */
  child_ids: number[]
  /** 子文件大小合计 */
  total_size: number
  /** 子文件最近修改时间 */
  latest_mtime: string | null
  /** 子文件下载器名一致则该名，否则 null（渲染"多个"） */
  downloader_name: string | null
  /** 聚合状态：全部待清理 */
  all_pending: boolean
  /** 聚合状态：全部已忽视 */
  all_ignored: boolean
  /** 聚合状态：全部已清理 */
  all_deleted: boolean
  /** 子文件中是否含低置信度项 */
  has_low_confidence: boolean
}

/** 表格行：文件行或文件夹聚合行 */
export type OrphanTableRow = OrphanFileItem | OrphanFolderRow

/**
 * 分页响应格式（符合项目规范）
 * ⚠️ 必须使用 pageSize 和 list，严禁使用其他变体
 */
export interface OrphanListResponse {
  total: number
  page: number
  pageSize: number
  /**
   * 列表数据：扁平模式为 OrphanFileItem[]；group_by_folder=true 的折叠模式为
   * OrphanFolderRow（≥2 文件聚合）与 OrphanFileItem（单文件原样）的混合数组。
   */
  list: OrphanTableRow[]
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
  /** 大批量全选时仅返回前 200 条预览明细，计数与大小仍覆盖全部。 */
  items_truncated?: boolean
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
  task_id: string | null
  operation_type: 'cleanup'
  status: 'pending' | 'running' | 'completed' | 'partial' | 'failed' | 'already_running'
  scan_id: string | null
  total_count: number
  requested_count?: number
  accepted_count?: number
  skipped_count?: number
  skipped_items?: number[]
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
  path_like?: string
  // status/confidence 支持逗号分隔多值（后端 OR 并集过滤），故用 string 而非单值联合类型
  status?: string
  confidence?: string
  /** 按文件夹（直接父目录）聚合分页：true 时同目录≥2 文件折叠为文件夹行 */
  group_by_folder?: boolean
}

export interface OrphanSelectionFilters {
  downloader_id?: string
  path_like?: string
  path_prefix?: string
  status?: string
  confidence?: string
}

export interface OrphanSelectionPayload {
  orphan_ids?: number[]
  select_all?: boolean
  excluded_orphan_ids?: number[]
  filters?: OrphanSelectionFilters
}

export interface CleanupRequest extends OrphanSelectionPayload {
  scan_id: string
}

export interface IgnoreRequest extends OrphanSelectionPayload {
  scan_id?: string
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

/** 忽视操作结果；逐项失败原因必须保留给页面展示。 */
export interface IgnoreResult {
  rejected?: boolean
  error?: string
  success_count: number
  failed_count: number
  failed_list: CleanupFailedItem[]
}

/**
 * 设置/取消孤儿文件的忽视态
 *
 * 被忽视的孤儿受保护：定时任务不自动删除，手动清理也被拒绝，但仍可在列表查询。
 */
export function setIgnored(data: IgnoreRequest): Promise<ApiResponse<IgnoreResult>> {
  return request({
    url: '/orphan-files/ignore',
    method: 'post',
    data: data,
    timeout: 120000
  }) as unknown as Promise<ApiResponse<IgnoreResult>>
}

// ==================== 左匹配（前缀）快捷操作 ====================

export interface PrefixMatchPreviewRequest {
  path_prefix: string
  scan_id: string
}

/**
 * 左匹配预览成功结果。范围严格限定 status=pending（排除已忽视/已清理）。
 * low_confidence_count>0 时前端应在二次确认中追加低置信度误判警告。
 */
export interface PrefixMatchPreviewSuccess {
  rejected?: false
  count: number
  total_size: number
  low_confidence_count: number
  /** 命中文件路径样本（最多 10 条），供未来扩展展示。 */
  sample_paths: string[]
}

/**
 * 左匹配预览拒绝结果：scan 过期或最新扫描未完成（与 cleanup 同样新鲜度门禁）。
 */
export interface PrefixMatchPreviewRejected {
  rejected: true
  reason: string
  count: 0
  total_size: 0
  low_confidence_count: 0
  sample_paths: []
}

export type PrefixMatchPreviewResult = PrefixMatchPreviewSuccess | PrefixMatchPreviewRejected

/**
 * 左匹配（前缀）预览：统计以 path_prefix 开头的“待清理”孤儿文件数与大小。
 *
 * 与 cleanup 共用新鲜度门禁，stale 时返回 rejected=true。前端快捷操作
 * （快捷删除/快捷忽视）先用本接口拿命中数做二次确认，再复用 cleanup/ignore 执行。
 */
export function prefixMatchPreview(
  data: PrefixMatchPreviewRequest
): Promise<ApiResponse<PrefixMatchPreviewResult>> {
  return request({
    url: '/orphan-files/prefix-match-preview',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<PrefixMatchPreviewResult>>
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
  mtime: string | null
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
  task_id: string | null
  status: 'pending' | 'running' | 'completed' | 'partial' | 'failed' | 'already_running'
  total_count: number
  requested_count?: number
  accepted_count?: number
  skipped_count?: number
  skipped_items?: string[]
  purged_count: number
  failed_count: number
  failed_list: QuarantineFailedItem[]
  error_message: string | null
  created_at: string | null
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
