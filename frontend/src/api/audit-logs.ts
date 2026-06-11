import request from '@/utils/request'

/**
 * 审计日志查询请求
 */
export interface AuditLogQueryRequest {
  torrent_info_id?: string
  operation_type?: string
  operator?: string
  downloader_id?: string
  start_time?: string
  end_time?: string
  operation_result?: string
  ip_address?: string
  request_id?: string
  session_id?: string
  page?: number
  page_size?: number
}

/**
 * 审计日志查询响应
 */
export interface AuditLogQueryResponse {
  total: number
  page: number
  pageSize: number
  list: AuditLogItem[]
}

/**
 * 审计日志项
 */
export interface AuditLogItem {
  log_id: string
  torrent_info_id: string | null
  operation_type: string
  operation_detail: string
  old_value: string | null
  new_value: string | null
  operator: string
  operation_time: string
  operation_result: string
  error_message: string | null
  downloader_id: string | null
  create_time: string
  ip_address: string | null
  user_agent: string | null
  request_id: string | null
  session_id: string | null
}

/**
 * 审计日志统计响应
 */
export interface AuditLogStatisticsResponse {
  total_count: number
  operation_type_stats: Record<string, number>
  operator_stats: Record<string, number>
  result_stats: Record<string, number>
}

/**
 * 操作类型响应
 */
export interface OperationTypesResponse {
  operation_types: OperationTypeItem[]
  total: number
}

/**
 * 操作类型项
 */
export interface OperationTypeItem {
  value: string
  display_name: string
  category: string
}

/**
 * 导出请求
 */
export interface AuditLogExportRequest {
  torrent_info_id?: string
  operation_type?: string
  operator?: string
  downloader_id?: string
  start_time?: string
  end_time?: string
  operation_result?: string
  export_format: 'csv' | 'excel'
  max_rows: number
}

/**
 * 导出响应
 */
export interface AuditLogExportResponse {
  file_path: string
  file_name: string
  record_count: number
  file_format: string
}

/**
 * 归档请求
 */
export interface AuditLogArchiveRequest {
  end_time: string
  archive_path?: string
}

/**
 * 归档响应
 */
export interface AuditLogArchiveResponse {
  success: boolean
  archived_count: number
  archive_path: string | null
  message: string
}

/**
 * 查询审计日志
 */
export function queryAuditLogs(params: AuditLogQueryRequest) {
  return request<AuditLogQueryResponse>({
    url: '/audit-logs/query',
    method: 'post',
    data: params
  })
}

/**
 * 获取审计日志统计
 */
export function getAuditLogStatistics(params?: { start_time?: string, end_time?: string }) {
  return request<AuditLogStatisticsResponse>({
    url: '/audit-logs/statistics',
    method: 'get',
    params
  })
}

/**
 * 获取操作类型列表
 */
export function getOperationTypes() {
  return request<OperationTypesResponse>({
    url: '/audit-logs/operation-types',
    method: 'get'
  })
}

/**
 * 导出审计日志
 */
export function exportAuditLogs(data: AuditLogExportRequest) {
  return request<AuditLogExportResponse>({
    url: '/audit-logs/export',
    method: 'post',
    data
  })
}

/**
 * 归档审计日志
 */
export function archiveAuditLogs(data: AuditLogArchiveRequest) {
  return request<AuditLogArchiveResponse>({
    url: '/audit-logs/archive',
    method: 'post',
    data
  })
}

/**
 * 下载导出文件
 */
export function downloadExportFile(fileName: string) {
  return `/api/audit-logs/download-export/${fileName}`
}
