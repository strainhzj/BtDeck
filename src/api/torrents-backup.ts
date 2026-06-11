/* eslint-disable camel_case */
import request from '@/utils/request'

/**
 * 种子文件备份记录
 */
export interface TorrentBackup {
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

/**
 * 分页请求参数
 */
export interface BackupListParams {
  page: number
  pageSize: number
  downloader_id?: number | null
  search?: string
  startTime?: string
  endTime?: string
}

/**
 * 标准分页响应格式（强制规范）
 */
export interface BackupPaginatedResponse {
  total: number
  page: number
  pageSize: number
  list: TorrentBackup[]
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
 * 导入失败项
 */
export interface ImportFailedItem {
  filename: string
  reason: string
}

/**
 * 导入响应数据
 */
export interface ImportResponseData {
  success_count?: number
  failed_count?: number
  failed_items?: ImportFailedItem[]
}

/**
 * 获取种子文件备份列表
 * @param params 查询参数
 * @returns 备份列表（分页格式）
 */
export function getBackupList(params: BackupListParams): Promise<ApiResponse<BackupPaginatedResponse>> {
  return request({
    url: '/torrents/backup',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResponse<BackupPaginatedResponse>>
}

/**
 * 删除种子文件备份
 * @param infoHash 种子info_hash
 * @returns 删除结果
 */
export function deleteBackup(infoHash: string): Promise<ApiResponse<void>> {
  return request({
    url: `/torrents/backup/${infoHash}`,
    method: 'delete'
  }) as unknown as Promise<ApiResponse<void>>
}

/**
 * 种子文件备份去重
 * @returns 去重结果
 */
export function deduplicateBackups(): Promise<ApiResponse<any>> {
  return request({
    url: '/torrents/backup/deduplicate',
    method: 'post'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 导入种子文件备份
 * @param downloaderId 目标下载器ID
 * @param formData 包含文件的FormData
 * @returns 导入结果
 */
export function importBackups(downloaderId: number, formData: FormData): Promise<ApiResponse<ImportResponseData>> {
  return request({
    url: `/torrents/backup/import?downloader_id=${downloaderId}`,
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  }) as unknown as Promise<ApiResponse<ImportResponseData>>
}

/**
 * 获取导出URL（用于前端直接创建下载链接）
 * @param infoHashes 逗号分隔的info_hash列表
 * @returns 完整的导出URL
 */
export function getExportUrl(infoHashes: string): string {
  const baseUrl = process.env.VUE_APP_BASE_API || ''
  return `${baseUrl}/torrents/backup/export?info_hashes=${encodeURIComponent(infoHashes)}`
}

/**
 * 获取下载URL（用于前端直接创建下载链接）
 * @param infoHash 单个种子的info_hash
 * @returns 完整的下载URL
 */
export function getDownloadUrl(infoHash: string): string {
  const baseUrl = process.env.VUE_APP_BASE_API || ''
  return `${baseUrl}/torrents/backup/download/${infoHash}`
}

/**
 * 获取上传URL（用于el-upload组件）
 * @param downloaderId 目标下载器ID
 * @returns 完整的上传URL
 */
export function getUploadUrl(downloaderId: number): string {
  const baseUrl = process.env.VUE_APP_BASE_API || ''
  return `${baseUrl}/torrents/backup/import?downloader_id=${downloaderId}`
}
