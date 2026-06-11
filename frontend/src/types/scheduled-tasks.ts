/**
 * 定时任务相关类型定义
 * 统一管理定时任务的业务类型定义
 */

import { ApiResponse, PaginationParams, PaginatedResponse } from './api'

// 任务类型枚举
export enum TaskType {
  SHELL = 0,           // shell脚本
  BATCH = 1,           // cmd脚本
  POWERSHELL = 2,      // powershell脚本
  PYTHON = 3,          // python脚本
  PYTHON_INTERNAL = 4, // python内部类
  CLEANUP = 5          // 清理回收站任务
}

// 任务状态枚举
export enum TaskStatus {
  WAITING = 0,    // 等待运行
  RUNNING = 1,    // 运行中
  SUCCESS = 2,    // 空闲/成功
  FAILED = 3,     // 失败
  PAUSED = 4      // 暂停
}

// 定时任务基础信息
export interface ScheduledTask {
  taskId: number                      // 任务ID
  taskName: string                    // 任务名称
  taskCode: string                    // 任务编码
  taskType: TaskType                  // 任务类型
  taskTypeName: string                // 任务类型名称
  executor: string                    // 执行脚本内容或路径
  cronPlan: string                    // Cron表达式
  enabled: boolean                    // 是否启用
  taskStatus: TaskStatus              // 任务状态
  taskStatusName: string              // 任务状态名称
  lastExecuteTime?: string            // 上次执行时间
  lastExecuteDuration?: number        // 上次执行耗时(秒)
  createTime: string                  // 创建时间
  updateTime: string                  // 更新时间
  description?: string                // 任务描述
  timeoutSeconds?: number             // 超时时间(秒)
  maxRetryCount?: number              // 最大重试次数
  retryInterval?: number              // 重试间隔(秒)
}

// 任务创建请求
export interface TaskCreateRequest {
  taskName: string                     // 任务名称
  taskCode: string                     // 任务编码
  taskType: TaskType                   // 任务类型
  executor: string                     // 执行脚本内容
  cronPlan: string                     // Cron表达式
  enabled: boolean                     // 是否启用
  description?: string                 // 任务描述
  timeoutSeconds?: number              // 超时时间(秒)
  maxRetryCount?: number               // 最大重试次数
  retryInterval?: number               // 重试间隔(秒)
}

// 任务更新请求
export interface TaskUpdateRequest {
  taskId: number                       // 任务ID
  taskName?: string                    // 任务名称
  taskCode?: string                    // 任务编码
  taskType?: TaskType                  // 任务类型
  executor?: string                    // 执行脚本内容
  cronPlan?: string                    // Cron表达式
  enabled?: boolean                    // 是否启用
  description?: string                 // 任务描述
  timeoutSeconds?: number              // 超时时间(秒)
  maxRetryCount?: number               // 最大重试次数
  retryInterval?: number               // 重试间隔(秒)
}

// 任务删除请求
export interface TaskDeleteRequest {
  taskIds: number[]                     // 要删除的任务ID列表
}

// 任务查询参数
export interface TaskListRequest extends PaginationParams {
  taskName?: string                    // 任务名称筛选
  taskCode?: string                    // 任务编码筛选
  taskType?: TaskType                  // 任务类型筛选
  enabled?: boolean                    // 启用状态筛选
  taskStatus?: TaskStatus              // 任务状态筛选
}

// 任务列表响应
export type TaskListResponse = ApiResponse<PaginatedResponse<ScheduledTask>>

// 任务执行请求
export interface TaskExecuteRequest {
  taskId: number                       // 要执行的任务ID
}

// 任务类型选项
export interface TaskTypeOption {
  value: TaskType                      // 任务类型值
  label: string                        // 显示标签
  icon: string                         // 图标
  description: string                  // 描述
  language: string                     // 脚本语言
  fileExtension?: string               // 文件扩展名
}

// Cron验证结果
export interface CronValidationResult {
  valid: boolean                       // 是否有效
  nextExecutions: string[]             // 下几次执行时间
  description?: string                 // 描述信息
  error?: string                       // 错误信息
}

// Cron验证请求
export interface CronValidationRequest {
  expression: string                   // Cron表达式
}

// ========== 清理任务相关类型 ==========

// 清理任务配置
export interface CleanupTaskConfig {
  cleanup_level_3: boolean   // 是否清理等级3（回收站）
  cleanup_level_4: boolean   // 是否清理等级4（待删除标签）
  days_threshold: number    // 天数阈值（1-365）
}

// 清理预览响应
export interface CleanupPreviewResponse {
  level3_count: number      // 等级3种子数量
  level4_count: number      // 等级4种子数量
  total_count: number       // 总数量
  total_size_gb: number     // 总大小（GB）- 注意：后端只有这个字段
  level3_items: CleanupItem[]  // 等级3种子列表
  level4_items: CleanupItem[]  // 等级4种子列表
  error?: string            // 错误信息
}

// 清理项信息
export interface CleanupItem {
  info_id: string           // 种子ID
  name: string              // 种子名称
  size: number              // 种子大小
  deleted_at?: string       // 删除时间（等级3）
  tags?: string             // 标签（等级4）
  save_path: string         // 保存路径
}

// 清理执行响应
export interface CleanupExecuteResponse {
  level3_cleaned: number    // 等级3清理数量
  level4_cleaned: number    // 等级4清理数量
  total_size_freed: number  // 释放的总空间（字节）
  errors: string[]          // 错误列表
}

// 清理任务请求
export interface CleanupTaskRequest {
  cleanup_level_3: boolean
  cleanup_level_4: boolean
  days_threshold: number
}
