/* eslint-disable camelcase */
import request from '@/utils/request'

// ========== 类型定义 ==========

/**
 * 回收站种子项
 */
export interface RecycleBinItem {
  info_id: string
  name: string
  size: number
  save_path: string
  deleted_at: string
  downloader_name: string
  downloader_id?: string
  torrent_id?: string
  hash?: string
}

/**
 * 分页响应格式（符合项目规范）
 * ⚠️ 必须使用 pageSize 和 list，严禁使用其他变体
 */
export interface RecycleBinPaginatedResponse {
  total: number
  page: number
  pageSize: number // ✅ 必须使用驼峰命名
  list: RecycleBinItem[] // ✅ 必须使用list
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

/**
 * 还原请求参数
 */
export interface RestoreRequest {
  torrent_ids: string[]
}

/**
 * 还原响应数据
 */
export interface RestoreResponse {
  success_count: number
  failed_count: number
  skipped_count: number
  success_list: Array<{
    torrent_id: string
    name: string
  }>
  failed_list: Array<{
    torrent_id: string
    name: string
    error: string
  }>
}

/**
 * 清理预览请求参数
 */
export interface CleanupPreviewRequest {
  days: number
}

/**
 * 清理预览响应数据
 */
export interface CleanupPreviewResponse {
  total_count: number
  total_size: number
  torrent_list: RecycleBinItem[]
}

/**
 * 手动清理请求参数
 */
export interface CleanupRequest {
  torrent_ids: string[]
}

/**
 * 清理响应数据
 */
export interface CleanupResponse {
  success_count: number
  failed_count: number
  success_list: Array<{
    torrent_id: string
    name: string
  }>
  failed_list: Array<{
    torrent_id: string
    name: string
    error: string
  }>
}

/**
 * 手动还原请求参数（FormData格式）
 */
export interface ManualRestoreRequest {
  torrent_id: string
  torrent_file: File
}

/**
 * 回收站列表查询参数
 */
export interface RecycleBinListParams {
  page: number
  page_size: number
  search?: string
}

// ========== API接口函数 ==========

/**
 * 查询回收站列表
 * @param params 查询参数
 * @returns 回收站列表数据
 */
export function getRecycleBinList(params: RecycleBinListParams): Promise<ApiResponse<RecycleBinPaginatedResponse>> {
  return request({
    url: '/recycle/bin',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResponse<RecycleBinPaginatedResponse>>
}

/**
 * 批量还原种子
 * @param data 还原请求参数
 * @returns 还原结果
 */
export function restoreTorrents(data: RestoreRequest): Promise<ApiResponse<RestoreResponse>> {
  return request({
    url: '/recycle/restore',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<RestoreResponse>>
}

/**
 * 手动上传种子文件还原
 * @param data 手动还原请求参数（FormData格式）
 * @returns 还原结果
 */
export function restoreTorrentWithFile(data: ManualRestoreRequest): Promise<ApiResponse<RestoreResponse>> {
  const formData = new FormData()
  formData.append('torrent_id', data.torrent_id)
  formData.append('torrent_file', data.torrent_file)

  return request({
    url: '/recycle/restore-manual',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  }) as unknown as Promise<ApiResponse<RestoreResponse>>
}

/**
 * 清理预览
 * @param data 清理预览请求参数
 * @returns 预览数据
 */
export function cleanupPreview(data: CleanupPreviewRequest): Promise<ApiResponse<CleanupPreviewResponse>> {
  return request({
    url: '/recycle/cleanup-preview',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<CleanupPreviewResponse>>
}

/**
 * 手动清理回收站种子
 * @param data 清理请求参数
 * @returns 清理结果
 */
export function manualCleanup(data: CleanupRequest): Promise<ApiResponse<CleanupResponse>> {
  return request({
    url: '/recycle/cleanup',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<CleanupResponse>>
}
