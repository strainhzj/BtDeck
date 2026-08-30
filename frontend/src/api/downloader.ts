import request from '@/utils/request'
import type { ApiEnvelope } from '@/utils/request'
import type {
  ApplyTemplateRequest,
  DownloaderCapabilities,
  DownloaderSettings,
  PathMappingConfig,
  PathMappingTestResponse,
  SettingTemplate,
  TemplateDetailResponse,
  TemplateListResponse
} from '@/views/downloader/types'

export type SyncTaskState = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'

export interface SyncTaskSubmission {
  task_id: string
  downloader_id: string
  nickname: string
  status: 'pending' | 'running'
  query_url: string
  message: string
}

export interface SyncTaskExecutionResult {
  status?: string
  message?: string
  outcome?: string
  run_id?: string
  duration_ms?: number
}

export interface SyncTaskStatusData {
  task_id: string
  task_type: string
  downloader_id: string
  downloader_nickname: string
  status: SyncTaskState
  created_at: string
  started_at: string | null
  finished_at: string | null
  progress: number
  result: SyncTaskExecutionResult | null
  error: string | null
  execution_time: number | null
}

export const getList = (data?: any) =>
  request({
    url: '/downloader/getList',
    method: 'post',
    data
  })

export const getDetail = (id: string) =>
  request({
    url: '/downloader/detail/' + id,
    method: 'get',
  })

export const getStatus = (id: string) =>
  request({
    url: '/downloader/getStatus/'+ id,
    method: 'get',
  })

/**
 * 批量获取所有在线下载器的状态
 * @returns 返回所有在线下载器的状态数组
 */
export const getStatusAll = () =>
  request({
    url: '/downloader/getStatusAll',
    method: 'get',
  })

export const addDownloader = (data: object) =>
  request({
    url: '/downloader/add',
    method: 'post',
    data
  })

export const upDownloader = (data: {id:string}) =>
  request({
    url: '/downloader/update/' + data.id,
    method: 'post',
    data
  })

export const deleteDownloader = (id: string) =>
  request({
    url: '/downloader/delete/' + id,
    method: 'delete',
  })

// 测试下载器连接
export const testConnection = (id: string) =>
  request({
    url: '/downloader/test/' + id,
    method: 'post',
  })

// 同步单个下载器种子
export const syncDownloader = (downloaderId: string) =>
  request<ApiEnvelope<SyncTaskSubmission>>({
    url: '/torrents/sync-single',
    method: 'post',
    data: { downloader_id: downloaderId }
  })

// 查询单个下载器异步种子同步任务状态
export const getSyncTaskStatus = (taskId: string) =>
  request<ApiEnvelope<SyncTaskStatusData>>({
    url: `/torrents/sync-status/${encodeURIComponent(taskId)}`,
    method: 'get'
  })

// ============================================================
// 下载器设置管理相关 API
// ============================================================

/**
 * 获取下载器设置
 */
export const getDownloaderSettings = (downloaderId: string) =>
  request<ApiEnvelope<DownloaderSettings>>({
    url: `/downloaders/${downloaderId}/settings`,
    method: 'get'
  })

/**
 * 更新下载器设置
 */
export const updateDownloaderSettings = (downloaderId: string, data: any) =>
  request<ApiEnvelope<DownloaderSettings>>({
    url: `/downloaders/${downloaderId}/settings`,
    method: 'put',
    data
  })

/**
 * 更新分时段限速规则排序
 */
export const reorderSpeedScheduleRules = (downloaderId: string, data: { rule_ids: number[] }) =>
  request({
    url: `/downloaders/${downloaderId}/settings/rules/reorder`,
    method: 'put',
    data
  })

/**
 * 测试下载器设置连接
 * @param downloaderId 下载器ID
 * @param data 连接测试参数（主机、端口、用户名、密码等）
 */
export const testDownloaderSettings = (downloaderId: string, data?: {
  host: string
  port: number
  username: string
  password?: string
  downloader_type: number
  is_ssl?: string
}) =>
  request<ApiEnvelope<unknown>>({
    url: `/downloaders/${downloaderId}/settings/test`,
    method: 'post',
    data
  })

/**
 * 应用下载器设置到下载器客户端
 * @param downloaderId 下载器ID
 * @description 将保存的配置(速度限制、高级设置等)应用到下载器客户端
 */
export const applyDownloaderSettings = (downloaderId: string) =>
  request<ApiEnvelope<DownloaderSettings>>({
    url: `/downloaders/${downloaderId}/settings/apply`,
    method: 'post'
  })

/**
 * 获取下载器能力信息
 */
export const getDownloaderCapabilities = (downloaderId: string) =>
  request<ApiEnvelope<DownloaderCapabilities>>({
    url: `/downloaders/${downloaderId}/capabilities`,
    method: 'get'
  })

// ============================================================
// 模板管理相关 API
// ============================================================

/**
 * 获取模板列表
 */
export const getTemplateList = (params?: any) =>
  request<TemplateListResponse>({
    url: '/setting-templates',
    method: 'get',
    params
  })

/**
 * 获取模板详情
 */
export const getTemplateDetail = (templateId: string) =>
  request<TemplateDetailResponse>({
    url: `/setting-templates/${templateId}`,
    method: 'get'
  })

/**
 * 创建模板
 */
export const createTemplate = (data: any) =>
  request<ApiEnvelope<SettingTemplate>>({
    url: '/setting-templates',
    method: 'post',
    data
  })

/**
 * 更新模板
 */
export const updateTemplate = (templateId: string, data: any) =>
  request<ApiEnvelope<SettingTemplate>>({
    url: `/setting-templates/${templateId}`,
    method: 'put',
    data
  })

/**
 * 删除模板
 */
export const deleteTemplate = (templateId: string) =>
  request<ApiEnvelope<unknown>>({
    url: `/setting-templates/${templateId}`,
    method: 'delete'
  })

/**
 * 应用模板到下载器
 *
 * 对齐后端 POST /setting-templates/{template_id}/apply/{downloader_id}：
 * - template_id、downloader_id 进 URL path 参数
 * - body 只传 apply_path_mapping（是否同时应用路径映射）
 *
 * 审计依据：backend/docs/style-and-contract-audit.md 第5节 apply 双重不匹配。
 */
export const applyTemplate = (
  templateId: string,
  downloaderId: string,
  options?: ApplyTemplateRequest
) =>
  request<ApiEnvelope<DownloaderSettings>>({
    url: `/setting-templates/${templateId}/apply/${downloaderId}`,
    method: 'post',
    data: options ?? {}
  })

// ============================================================
// 路径映射相关 API
// ============================================================

/**
 * 获取下载器的路径映射配置
 */
export const getPathMappings = (downloaderId: string) =>
  request({
    url: `/downloader/${downloaderId}/path-mapping`,
    method: 'get'
  })

/**
 * 测试路径映射配置
 */
export const testPathMapping = (downloaderId: string, pathMapping: PathMappingConfig) =>
  request<ApiEnvelope<PathMappingTestResponse>>({
    url: `/downloader/${downloaderId}/path-mapping/test`,
    method: 'post',
    data: { path_mapping: pathMapping }
  })

// ============================================================
// 下载器路径维护相关 API (种子转移功能)
// ============================================================

/**
 * 获取下载器路径列表
 * @param downloaderId 下载器ID
 * @param pathType 路径类型过滤（可选）：default 或 active
 * @param isEnabled 是否启用过滤（可选）
 */
export const getDownloaderPaths = (
  downloaderId: string,
  pathType?: string,
  isEnabled?: boolean
) =>
  request({
    url: `/downloaders/${downloaderId}/paths`,
    method: 'get',
    params: {
      path_type: pathType,
      is_enabled: isEnabled
    }
  })

/**
 * 添加下载器路径
 * @param downloaderId 下载器ID
 * @param data 路径数据
 */
export const addDownloaderPath = (
  downloaderId: string,
  data: {
    path_type: string
    path_value: string
    is_enabled: boolean
  }
) =>
  request({
    url: `/downloaders/${downloaderId}/paths`,
    method: 'post',
    data
  })

/**
 * 更新下载器路径
 * @param downloaderId 下载器ID
 * @param pathId 路径ID
 * @param data 更新数据
 */
export const updateDownloaderPath = (
  downloaderId: string,
  pathId: number,
  data: {
    path_value?: string
    is_enabled?: boolean
  }
) =>
  request({
    url: `/downloaders/${downloaderId}/paths/${pathId}`,
    method: 'put',
    data
  })

/**
 * 删除下载器路径
 * @param downloaderId 下载器ID
 * @param pathId 路径ID
 */
export const deleteDownloaderPath = (downloaderId: string, pathId: number) =>
  request({
    url: `/downloaders/${downloaderId}/paths/${pathId}`,
    method: 'delete'
  })
