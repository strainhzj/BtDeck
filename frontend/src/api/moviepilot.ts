import request from '@/utils/request'
import type { ApiEnvelope } from '@/utils/request'

/**
 * MoviePilot 集成 API（moviepilot-integration）。
 *
 * - 设置/实例为管理面（principal 认证）；关联查询供种子详情「媒体库」页签
 *   与设置页反查卡消费；
 * - 全局开关保存携带 expectedRevision 做 CAS，冲突返回 HTTP 409
 *   （ApiError.code === '409'），组件侧应提示并重新加载；
 * - 分页数据统一为 { total, page, pageSize, list }（仓库响应契约）。
 */

/** 关联状态：linked=已映射可定位任务；unmapped=有 hash 未配映射；unassociated=无 hash */
export type MoviePilotAssociationStatus = 'linked' | 'unmapped' | 'unassociated'

export interface MoviePilotSettingsPayload {
  schemaVersion: number
  enabled: boolean
  revision: number
  updatedAt: string | null
  updatedBy: string | null
}

export interface MoviePilotSettingsData {
  settings: MoviePilotSettingsPayload
  protocolVersion: number
}

export interface MoviePilotInstance {
  id: number
  instanceId: string
  name: string
  enabled: boolean
  protocolVersion: number | null
  pluginVersion: string | null
  moviepilotVersion: string | null
  /** MoviePilot 下载器名 → BtDeck downloader_id */
  downloaderMapping: Record<string, string>
  boundUsername: string | null
  lastHandshakeAt: string | null
  lastSyncAt: string | null
  lastSyncStats: {
    inserted?: number
    updated?: number
    skipped?: number
    failed?: number
  }
  syncedHistoryCount: number
  lastError: string | null
  createdAt: string | null
  updatedAt: string | null
}

export interface MoviePilotInstancePage {
  total: number
  page: number
  pageSize: number
  list: MoviePilotInstance[]
}

/** 反查结果回带的任务快照（linked 且任务在 torrent_info 中存在时非空） */
export interface MoviePilotTaskSnapshot {
  infoId: string
  name: string | null
  status: string | null
  downloaderId: string
  downloaderName: string | null
  savePath: string | null
  size: number | null
}

/** 一条整理历史关联（正向/反查共用形态；反查额外带 task） */
export interface MoviePilotAssociationItem {
  id: number
  instanceId: string
  instanceName: string | null
  historyId: number
  srcStorage: string | null
  srcPath: string | null
  destStorage: string | null
  destPath: string | null
  transferMode: string | null
  mediaType: string | null
  title: string | null
  year: string | null
  seasons: string | null
  episodes: string | null
  tmdbId: number | null
  doubanId: string | null
  mpDownloader: string | null
  downloadHash: string | null
  btDownloaderId: string | null
  associationStatus: MoviePilotAssociationStatus
  status: boolean | null
  errmsg: string | null
  recordedAt: string | null
  task?: MoviePilotTaskSnapshot | null
}

export interface MoviePilotAssociationPage {
  total: number
  page: number
  pageSize: number
  list: MoviePilotAssociationItem[]
}

export type MoviePilotReverseMode = 'src' | 'dest' | 'both'

/** 读取集成全局开关 */
export function getMoviePilotSettings(): Promise<ApiEnvelope<MoviePilotSettingsData>> {
  return request<ApiEnvelope<MoviePilotSettingsData>>({
    url: '/moviepilot/settings',
    method: 'get'
  })
}

/** 更新全局开关（revision CAS；冲突 HTTP 409 → ApiError.code === '409'） */
export function updateMoviePilotSettings(payload: {
  enabled: boolean
  expectedRevision: number
}): Promise<ApiEnvelope<{ settings: MoviePilotSettingsPayload }>> {
  return request<ApiEnvelope<{ settings: MoviePilotSettingsPayload }>>({
    url: '/moviepilot/settings',
    method: 'put',
    data: payload
  })
}

/** 已注册实例列表（分页；数量少，默认一页取全） */
export function getMoviePilotInstances(
  page = 1,
  pageSize = 100
): Promise<ApiEnvelope<MoviePilotInstancePage>> {
  return request<ApiEnvelope<MoviePilotInstancePage>>({
    url: '/moviepilot/instances',
    method: 'get',
    params: { page, pageSize }
  })
}

/** 更新实例（名称/启用/下载器映射；未提供字段保持不变） */
export function updateMoviePilotInstance(
  instanceId: string,
  payload: {
    name?: string
    enabled?: boolean
    downloaderMapping?: Record<string, string>
  }
): Promise<ApiEnvelope<MoviePilotInstance>> {
  return request<ApiEnvelope<MoviePilotInstance>>({
    url: `/moviepilot/instances/${encodeURIComponent(instanceId)}`,
    method: 'put',
    data: payload
  })
}

/** 删除实例及其历史镜像（不可恢复，组件侧须二次确认） */
export function deleteMoviePilotInstance(
  instanceId: string
): Promise<ApiEnvelope<{ instanceId: string, deletedHistories: number }>> {
  return request<ApiEnvelope<{ instanceId: string, deletedHistories: number }>>({
    url: `/moviepilot/instances/${encodeURIComponent(instanceId)}`,
    method: 'delete'
  })
}

/** 正向：种子任务 (downloaderId, hash) → 整理历史 */
export function getTorrentMoviePilotAssociations(
  downloaderId: string,
  hash: string,
  page = 1,
  pageSize = 50
): Promise<ApiEnvelope<MoviePilotAssociationPage>> {
  return request<ApiEnvelope<MoviePilotAssociationPage>>({
    url: '/moviepilot/associations',
    method: 'get',
    params: { downloaderId, hash, page, pageSize }
  })
}

/** 反向：媒体/源路径 → 关联历史与任务快照 */
export function reverseMoviePilotAssociations(
  path: string,
  mode: MoviePilotReverseMode = 'both',
  page = 1,
  pageSize = 50
): Promise<ApiEnvelope<MoviePilotAssociationPage>> {
  return request<ApiEnvelope<MoviePilotAssociationPage>>({
    url: '/moviepilot/associations/reverse',
    method: 'get',
    params: { path, mode, page, pageSize }
  })
}
