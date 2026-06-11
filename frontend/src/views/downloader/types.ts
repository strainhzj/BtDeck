/**
 * 下载器管理模块 - TypeScript 类型定义
 */

/**
 * 下载器基本信息
 *
 * ⚠️ 字段命名规范：后端API返回使用驼峰命名（camelCase）
 * - isSearch（不是 is_search）
 * - downloaderType（不是 downloader_type）
 * - downloaderId（不是 downloader_id）
 */
export interface Downloader {
  downloaderId: string     // 下载器ID（主要ID字段）
  nickname: string          // 下载器名称
  host: string              // 主机地址（可能包含端口，如 "192.168.1.1:8080"）
  port: string              // 端口（字符串类型，后端返回字符串）
  username?: string         // 用户名（getList接口不返回）
  password?: string         // 密码（getList接口不返回）
  is_ssl?: '0' | '1'        // 是否SSL（detail接口返回，getList接口返回 isSearch）
  isSearch?: '0' | '1' | null   // 是否启用搜索（驼峰命名，后端返回）
  downloaderType: number    // 下载器类型（数字枚举：0=qbittorrent, 1=transmission，驼峰命名）
  downloaderTypeName?: 'qbittorrent' | 'transmission'  // 下载器类型名称（用于显示，匹配后端字段）
  enabled?: '0' | '1' | null     // 是否启用（可能为null）
  status?: string           // 下载器状态
  version?: string          // 下载器版本（用户填写，可选）
  connectStatus?: string    // 连接状态（"1"=在线, "0"=离线）
  path_mapping_rules?: string  // 路径映射规则配置（多行文本，格式：源路径{#**#}目标路径）
  torrentSavePath?: string  // 种子保存目录路径（应用运行环境可直接访问的绝对路径）
  // 兼容旧字段名（可选）
  id?: string               // 主键（值与downloaderId相同）
  is_search?: '0' | '1'     // 保留用于兼容（优先使用isSearch）
  downloader_type?: number  // 保留用于兼容（优先使用downloaderType）
}

/**
 * 下载器实时状态
 */
export interface DownloaderStatus {
  delay?: number            // 延迟(ms)
  upload_speed?: string     // 上传速度（后端返回带单位的字符串，如 "1.5 MB/s"）
  download_speed?: string   // 下载速度（后端返回带单位的字符串，如 "41.37 MB/s"）
  downloading_count?: number // 下载中数量（后端未实现，降级显示）
  seeding_count?: number    // 做种中数量（后端未实现，降级显示）
  online?: boolean          // 在线状态（通过API调用成功/失败判断）
  last_online?: string      // 最后在线时间（后端未实现，降级显示）
  connection_status?: 'success' | 'error'  // 连接状态
  connection_msg?: string   // 连接状态消息
}

/**
 * 下载器卡片展示数据（合并基本信息和状态）
 */
export interface DownloaderCardData {
  info: Downloader
  status: DownloaderStatus
}

/**
 * 表单数据（新增/编辑）
 */
export interface DownloaderFormData {
  id?: string
  nickname: string
  host: string
  port: number
  username: string
  password: string
  is_ssl: '0' | '1'
  is_search: '0' | '1'
  downloader_type: 0 | 1  // 下载器类型（数字枚举：0=qbittorrent, 1=transmission）
  enabled: '0' | '1'
  path_mapping_rules?: string  // 路径映射规则配置（多行文本）
  torrent_save_path?: string  // 种子保存目录路径（应用运行环境可直接访问的绝对路径）
}

/**
 * API 响应类型
 */
export interface DownloaderListResponse {
  code: string
  msg: string
  data: Downloader[]
  status: string
}

export interface DownloaderDetailResponse {
  code: string
  msg: string
  data: Downloader[]
  status: string
}

export interface DownloaderStatusResponse {
  code: string
  msg: string
  data: DownloaderStatus[]
  status: string
}

export interface TestConnectionResponse {
  code: string
  msg: string
  data: {
    success: boolean
    delay?: number
    message: string
  }
  status: string
}

/**
 * 下载器在线状态枚举
 */
export enum OnlineStatus {
  ONLINE = 'online',       // 在线
  OFFLINE = 'offline',     // 离线
  TESTING = 'testing'      // 测试中
}

/**
 * 下载器类型枚举（数字）
 * 统一使用 @/utils/downloaderType.ts 的 DOWNLOADER_TYPE
 * 0 = qBittorrent, 1 = Transmission
 */
// 重新导出工具函数的枚举供其他模块使用
export { DOWNLOADER_TYPE, DOWNLOADER_TYPE_NAME, downloaderTypeToString, downloaderStringToType, getDownloaderTypeLabel } from '@/utils/downloaderType'


// ============================================================
// 下载器设置管理相关类型
// ============================================================

/**
 * 下载器设置配置
 */
export interface DownloaderSettings {
  downloader_id: string
  username?: string
  password?: string
  override_local?: boolean  // 是否覆盖下载器本地配置

  // 速度设置 (驼峰命名,匹配后端API)
  dlSpeedLimit?: number      // 下载速度限制 (数值含义取决于 dlSpeedUnit)
  ulSpeedLimit?: number      // 上传速度限制 (数值含义取决于 ulSpeedUnit)
  dlSpeedUnit?: 0 | 1       // 下载速度单位: 0: KB/s, 1: MB/s
  ulSpeedUnit?: 0 | 1       // 上传速度单位: 0: KB/s, 1: MB/s

  // 兼容旧字段名(保留用于向后兼容)
  download_speed_limit?: number  // @deprecated 使用 dlSpeedLimit
  upload_speed_limit?: number    // @deprecated 使用 ulSpeedLimit
  speed_unit?: 0 | 1            // @deprecated 使用 dlSpeedUnit/ulSpeedUnit

  // 高级设置 - qBittorrent
  max_connections?: number
  max_connections_per_torrent?: number
  max_uploads?: number
  max_uploads_per_torrent?: number
  max_download_slots?: number
  max_upload_slots?: number

  // 高级设置 - Transmission
  download_queue_enabled?: boolean
  download_queue_size?: number
  seed_queue_enabled?: boolean
  seed_queue_size?: number
  idle_seeding_limit_enabled?: boolean
  idle_seeding_limit?: number

  // 其他高级选项
  dht_enabled?: boolean
  lsd_enabled?: boolean
  utp_enabled?: boolean

  // 路径映射配置
  path_mapping?: PathMappingConfig

  // 分时段限速规则
  schedule_rules?: SpeedScheduleRule[]
}

/**
 * 下载器能力信息
 *
 * 后端返回的嵌套结构：
 * {
 *   downloaderId: string,
 *   downloaderType: 0 | 1,
 *   downloaderTypeName: string,
 *   capabilities: {
 *     supports_speed_scheduling: boolean,
 *     connectionLimits: boolean,
 *     queueSettings: boolean,
 *     ...
 *   }
 * }
 */
export interface DownloaderCapabilities {
  downloader_id: string
  downloader_type: 0 | 1  // 0 = qBittorrent, 1 = Transmission
  // 能力字段（从嵌套的 capabilities 对象中读取）
  supports_speed_scheduling?: boolean  // 是否支持分时段限速
  supports_connection_limits?: boolean
  supports_queue_management?: boolean
  supports_path_mapping?: boolean
  supports_advanced_options?: boolean
}

/**
 * 分时段速度规则
 */
export interface SpeedScheduleRule {
  id?: number | string
  sort_order?: number
  start_time: string  // HH:mm 格式
  end_time: string    // HH:mm 格式
  weekdays: number[]  // 0-6, 0=周一, 6=周日
  download: {
    enabled: boolean
    speed_limit: number
    speed_unit: 0 | 1
  }
  upload: {
    enabled: boolean
    speed_limit: number
    speed_unit: 0 | 1
  }
  enabled?: boolean
}

/**
 * 模板信息
 */
export interface SettingTemplate {
  id: string
  name: string
  description: string
  downloader_type: 0 | 1 | 2  // 0=qbittorrent, 1=transmission, 2=both
  is_system_default: boolean
  created_by?: string
  created_at?: string
  updated_at?: string

  // 配置内容（JSON 格式）
  settings: DownloaderSettings
  schedule_rules?: SpeedScheduleRule[]

  // Transmission 路径映射
  path_mapping?: Record<string, string>
}

/**
 * 模板列表响应
 */
export interface TemplateListResponse {
  code: string
  msg: string
  data: {
    total: number
    page: number
    pageSize: number
    list: SettingTemplate[]
  }
  status: string
}

/**
 * 模板详情响应
 */
export interface TemplateDetailResponse {
  code: string
  msg: string
  data: SettingTemplate
  status: string
}

/**
 * 应用模板请求
 */
export interface ApplyTemplateRequest {
  template_id: string
  downloader_id: string
  override_local?: boolean
}

// ============================================================
// 路径映射相关类型
// ============================================================

/**
 * 映射类型枚举
 */
export type MappingType = 'local' | 'docker' | 'nas' | 'wsl' | 'network'

/**
 * 映射类型选项（用于下拉选择）
 */
export interface MappingTypeOption {
  value: MappingType
  label: string
  description: string
  placeholder: string
}

/**
 * 路径映射项
 */
export interface PathMappingItem {
  name: string                    // 映射名称
  internal: string                // 内部路径（下载器内）
  external: string                // 外部路径（主机）
  description?: string            // 映射描述
  mapping_type: MappingType       // 映射类型
}

/**
 * 路径映射配置
 */
export interface PathMappingConfig {
  mappings: PathMappingItem[]
  default_mapping?: string         // 默认映射名称（可选，自动使用第一个）
}

/**
 * 路径映射测试响应
 */
export interface PathMappingTestResponse {
  valid: boolean
  message: string
  backend_validation: {
    json_format_valid: boolean
    structure_valid: boolean
    fields_complete: boolean
    no_path_conflicts: boolean
    errors: string[]
  }
  frontend_validation?: null
}
