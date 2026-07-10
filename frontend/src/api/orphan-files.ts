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
}

/**
 * 扫描结果摘要
 */
export interface ScanResult {
  scan_id: string
  scan_time?: string
  scan_type?: string
  total_paths_scanned?: number
  total_files_scanned?: number
  total_orphans?: number
  total_orphan_size?: number
  status: string
  error?: string
  message?: string
}

/**
 * 最新扫描批次结果
 */
export interface LatestScanResult {
  scan_id: string
  scan_time: string
  scan_type: string
  total_paths_scanned: number
  total_files_scanned: number
  total_orphans: number
  total_orphan_size: number
  status: string
  error_message: string | null
  operator: string | null
}

/**
 * 清理预览结果
 */
export interface CleanupPreviewResult {
  total_count: number
  total_size: number
  items: Array<{
    id: number
    file_path: string
    file_size: number
  }>
}

/**
 * 清理执行结果
 */
export interface CleanupResult {
  success_count: number
  failed_count: number
  failed_list: Array<{
    id: number
    file_path: string
    reason: string
  }>
  total_size: number
}

/**
 * 标准API响应格式
 */
export interface ApiResponse<T = any> {
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
}

export interface CleanupRequest {
  orphan_ids: number[]
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
export function triggerScan(): Promise<ApiResponse<ScanResult>> {
  return request({
    url: '/orphan-files/scan',
    method: 'post'
  }) as unknown as Promise<ApiResponse<ScanResult>>
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
 * 手动清理选中的孤儿文件
 */
export function cleanupOrphans(data: CleanupRequest): Promise<ApiResponse<CleanupResult>> {
  return request({
    url: '/orphan-files/cleanup',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<CleanupResult>>
}
