import request from '@/utils/request'

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
  request({
    url: '/torrents/sync-single',
    method: 'post',
    data: { downloader_id: downloaderId }
  })

// ============================================================
// 下载器设置管理相关 API
// ============================================================

/**
 * 获取下载器设置
 */
export const getDownloaderSettings = (downloaderId: string) =>
  request({
    url: `/downloaders/${downloaderId}/settings`,
    method: 'get'
  })

/**
 * 更新下载器设置
 */
export const updateDownloaderSettings = (downloaderId: string, data: any) =>
  request({
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
  request({
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
  request({
    url: `/downloaders/${downloaderId}/settings/apply`,
    method: 'post'
  })

/**
 * 获取下载器能力信息
 */
export const getDownloaderCapabilities = (downloaderId: string) =>
  request({
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
  request({
    url: '/setting-templates',
    method: 'get',
    params
  })

/**
 * 获取模板详情
 */
export const getTemplateDetail = (templateId: string) =>
  request({
    url: `/setting-templates/${templateId}`,
    method: 'get'
  })

/**
 * 创建模板
 */
export const createTemplate = (data: any) =>
  request({
    url: '/setting-templates',
    method: 'post',
    data
  })

/**
 * 更新模板
 */
export const updateTemplate = (templateId: string, data: any) =>
  request({
    url: `/setting-templates/${templateId}`,
    method: 'put',
    data
  })

/**
 * 删除模板
 */
export const deleteTemplate = (templateId: string) =>
  request({
    url: `/setting-templates/${templateId}`,
    method: 'delete'
  })

/**
 * 应用模板到下载器
 */
export const applyTemplate = (templateId: string, data: ApplyTemplateRequest) =>
  request({
    url: `/setting-templates/${templateId}/apply`,
    method: 'post',
    data
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
export const testPathMapping = (downloaderId: string, pathMapping: any) =>
  request({
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
