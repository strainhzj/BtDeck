import request from '@/utils/request'
import type { ApiEnvelope } from '@/utils/request'

/**
 * MCP 服务配置控制面 API（mcp-service-capabilities W1）。
 *
 * 单一事实源在后端：能力目录元数据（工具名/风险分级/说明）随 GET 下发，
 * 前端不维护能力文案副本。revision 用于 PUT 的 CAS 前提，冲突返回
 * HTTP 409（ApiError.code === '409'），组件侧应提示并重新加载。
 */

/** 能力风险分级（与后端 contracts.py §4.3 一致） */
export type McpCapabilityRisk = 'read' | 'write' | 'high'

export interface McpCapabilityMeta {
  /** 能力码（配置键），如 torrent.advanced_search */
  code: string
  /** MCP 工具名（展示用），如 torrent_advanced_search */
  tool: string
  risk: McpCapabilityRisk
  description: string
  defaultEnabled: boolean
  requiresConfirm: boolean
  requiresIdempotencyKey: boolean
}

export interface McpSettingsPayload {
  schemaVersion: number
  /** 存储意图：全局开关存储值（kill switch 下不等于生效值） */
  enabled: boolean
  capabilities: Record<string, boolean>
  revision: number
  updatedAt: string | null
  updatedBy: string | null
  /** 环境紧急开关 BTDECK_MCP_FORCE_DISABLED 覆盖态（只读，UI 不可覆盖） */
  forceDisabled: boolean
  /** 生效态：enabled && !forceDisabled，唯一允许被消费的开关口径 */
  effectiveEnabled: boolean
}

export interface McpSettingsData {
  settings: McpSettingsPayload
  catalog: McpCapabilityMeta[]
}

export interface McpSettingsUpdatePayload {
  enabled: boolean
  capabilities: Record<string, boolean>
  expectedRevision: number
}

/** 读取 MCP 配置（生效态 + 能力目录元数据） */
export function getMcpSettings(): Promise<ApiEnvelope<McpSettingsData>> {
  return request<ApiEnvelope<McpSettingsData>>({
    url: '/mcp/settings',
    method: 'get'
  })
}

/** 更新 MCP 配置（revision CAS；冲突 HTTP 409 → ApiError.code === '409'） */
export function updateMcpSettings(
  payload: McpSettingsUpdatePayload
): Promise<ApiEnvelope<McpSettingsData>> {
  return request<ApiEnvelope<McpSettingsData>>({
    url: '/mcp/settings',
    method: 'put',
    data: payload
  })
}
