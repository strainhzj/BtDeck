/**
 * 任务日志相关类型定义
 * 统一管理任务日志的业务类型定义
 */

import { ApiResponse, PaginationParams, PaginatedResponse } from './api'
import { TaskType } from './scheduled-tasks'

// 任务日志基础信息
export interface TaskLog {
  logId: number                        // 日志ID
  taskId: number                       // 关联任务ID
  taskName: string                     // 任务名称
  taskType: TaskType                   // 任务类型
  startTime: string                    // 开始时间
  endTime?: string                     // 结束时间
  duration?: number                    // 执行耗时(秒)
  success: boolean                     // 是否成功
  logDetail: string                    // 日志详情
  createTime: string                   // 创建时间
}

// 任务日志查询参数
export interface TaskLogListRequest extends PaginationParams {
  taskName?: string                    // 任务名称筛选
  taskId?: number                      // 任务ID筛选
  taskType?: TaskType                  // 任务类型筛选
  logContent?: string                  // 日志内容筛选
  success?: boolean                    // 执行结果筛选
  startTime?: string                   // 开始时间筛选
  endTime?: string                     // 结束时间筛选
}

// 任务日志列表响应
export type TaskLogListResponse = ApiResponse<PaginatedResponse<TaskLog>>

// 任务日志删除请求
export interface TaskLogDeleteRequest {
  logIds?: number[]                     // 要删除的日志ID列表
  taskId?: number                      // 按任务删除
  beforeDate?: string                  // 删除指定日期之前的日志
  logLevel?: string                    // 按日志级别删除
}

// 任务日志统计信息
export interface TaskLogStatistics {
  totalLogs: number                    // 总日志数
  successLogs: number                  // 成功日志数
  failedLogs: number                   // 失败日志数
  todayLogs: number                    // 今日日志数
  storageUsage: number                 // 存储使用量(字节)
  last7Days: number[]                  // 最近7天日志数量
  logLevels: Record<string, number>     // 各级别日志数量
}

// 任务日志统计响应
export type TaskLogStatisticsResponse = ApiResponse<TaskLogStatistics>

// 任务日志清理请求
export interface TaskLogCleanupRequest {
  days?: number                        // 保留天数
  keepSuccess?: boolean                // 是否保留成功日志
  keepError?: boolean                  // 是否保留错误日志
}

// 任务日志导出参数
export interface TaskLogExportRequest extends TaskLogListRequest {
  format?: 'csv' | 'json' | 'txt'     // 导出格式
  includeHeaders?: boolean             // 是否包含表头
}

// 日志详情弹窗数据
export interface TaskLogDetail {
  log: TaskLog                         // 日志信息
  formattedDuration?: string           // 格式化的执行时长
  formattedLogDetail?: string          // 格式化的日志内容
}