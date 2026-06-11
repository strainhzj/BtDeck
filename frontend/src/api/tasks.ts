/* eslint-disable camelcase */
import request from '@/utils/request'

export interface TaskParameters {
  [key: string]: any
  // 下载任务参数
  download_url?: string
  save_path?: string
  downloader_id?: string

  // 上传任务参数
  upload_path?: string
  upload_target?: string

  // 清理任务参数
  cleanup_type?: 'temp_files' | 'completed_torrents' | 'logs'
  retention_days?: number

  // 备份任务参数
  backup_source?: string
  backup_target?: string
  backup_type?: 'full' | 'incremental'

  // 自定义任务参数
  custom_script?: string
  custom_params?: Record<string, any>
}

export interface ScheduledTask {
  taskId: number
  taskName: string
  taskCode: string
  taskStatus: number // 任务状态：0等待运行，1运行中，2空闲
  taskType: number // 任务类型：0-shell，1-cmd，2-powershell，3-python，4-python内部类
  executor: string
  enabled: boolean
  lastExecuteTime: string | null
  lastExecuteDuration: number | null
  cronPlan: string
  taskStatusName: string
  taskTypeName: string
  createTime: string
  updateTime: string
  description?: string // 任务描述
  timeoutSeconds?: number // 超时时间(秒)
  maxRetryCount?: number // 最大重试次数
  retryInterval?: number // 重试间隔(秒)

  // 兼容字段，用于前端显示
  id?: number
  task_name?: string
  task_type?: string
  cron_expression?: string
  last_run_time?: string | null
  next_run_time?: string | null
  created_at?: string
  updated_at?: string
  execution_count?: number
  success_count?: number
  error_count?: number
  last_error?: string | null

  // 通知与重试配置（前端扩展字段，后端可选返回）
  notification_on_success?: boolean
  notification_on_failure?: boolean
  notification_methods?: Array<'system' | 'email' | 'webhook'>
  notification_emails?: string
  webhook_url?: string
  auto_retry?: boolean
  retry_strategy?: 'fixed' | 'linear' | 'exponential'
}

export interface TaskListData {
  total?: number
  count?: number
  total_count?: number
  list?: ScheduledTask[]
  data?: ScheduledTask[]
  items?: ScheduledTask[]
}

export interface TaskListResponse {
  status: string
  msg: string
  code: string
  data: TaskListData
}

export interface TaskCreateRequest {
  task_name: string // 任务名称
  task_code: string // 任务编码
  task_type: number // 任务类型：0-shell，1-cmd，2-powershell，3-python，4-python内部类
  executor: string // 执行脚本内容或路径
  cron_plan: string // cron表达式，格式：分 时 日 月 周
  enabled: boolean // 是否启用
  description?: string // 任务描述
  timeout_seconds?: number // 超时时间(秒)
  max_retry_count?: number // 最大重试次数
  retry_interval?: number // 重试间隔(秒)

  // 兼容字段
  taskCode?: string
  taskType?: number
  cronPlan?: string
}

export interface TaskUpdateRequest {
  id: number
  task_name?: string
  task_code?: string
  task_type?: number // 任务类型：0-shell，1-cmd，2-powershell，3-python，4-python内部类
  executor?: string
  cron_plan?: string
  description?: string
  enabled?: boolean
  timeout_seconds?: number // 超时时间(秒)
  max_retry_count?: number // 最大重试次数
  retry_interval?: number // 重试间隔(秒)
  parameters?: TaskParameters

  // 兼容字段
  taskCode?: string
  taskType?: number
  cronPlan?: string
  cron_expression?: string
}

export interface TaskDeleteRequest {
  ids: number[]
}

export interface TaskExecuteRequest {
  id: number
}

// 任务日志相关接口定义
export interface TaskLog {
  logId: number
  taskId: number
  taskName: string
  taskType: number
  startTime: string
  endTime: string
  duration: number
  success: boolean
  logDetail: string
  createTime: string  // 创建时间,与 types/task-logs.ts 保持一致

  // 兼容字段
  id?: number
  task_id?: number
  task_name?: string
  task_type?: number
  start_time?: string
  end_time?: string
  log_level?: string
  log_message?: string
}

export interface TaskLogListData {
  total?: number
  count?: number
  total_count?: number
  list?: TaskLog[]
  data?: TaskLog[]
  items?: TaskLog[]
}

export interface TaskLogListResponse {
  status: string
  msg: string
  code: string
  data: TaskLogListData
}

export interface TaskLogQueryParams {
  task_id?: number
  task_name?: string
  start_time?: string
  end_time?: string
  log_content?: string
  success?: boolean
  skip?: number
  limit?: number
}

export interface ApiResponse<T = any> {
  status: string
  msg: string
  code: string
  data: T
}

/**
 * 获取定时任务列表
 */
export function getTaskList(params?: {
  page?: number
  limit?: number
  skip?: number
  task_name?: string
  enabled?: boolean
  task_status?: number
}): Promise<ApiResponse<TaskListData>> {
  return request({
    url: '/cronTasks/list',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResponse<TaskListData>>
}

/**
 * 获取定时任务详情
 */
export function getTaskDetail(id: number): Promise<ApiResponse<ScheduledTask>> {
  return request({
    url: `/cronTasks/${id}`,
    method: 'get'
  }) as unknown as Promise<ApiResponse<ScheduledTask>>
}

/**
 * 创建定时任务
 */
export function createTask(data: TaskCreateRequest): Promise<ApiResponse<any>> {
  return request({
    url: '/cronTasks/add',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 更新定时任务
 */
export function updateTask(data: TaskUpdateRequest): Promise<ApiResponse<any>> {
  return request({
    url: `/cronTasks/${data.id}`,
    method: 'put',
    data: data
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 删除定时任务
 */
export function deleteTasks(data: TaskDeleteRequest): Promise<ApiResponse<any>> {
  // 批量删除，需要分别调用
  const promises = data.ids.map(id =>
    request({
      url: `/cronTasks/${id}`,
      method: 'delete'
    })
  )
  return Promise.all(promises).then(results => {
    // 检查每个结果
    const allSuccess = results.every((r: any) => r.status === 'success')
    const failureCount = results.filter((r: any) => r.status !== 'success').length

    return {
      status: allSuccess ? 'success' : 'error',
      msg: allSuccess ? '删除成功' : `${failureCount}个任务删除失败`,
      code: allSuccess ? '200' : '400',
      data: null
    }
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 手动执行定时任务
 */
export function executeTask(data: TaskExecuteRequest): Promise<ApiResponse<any>> {
  return request({
    url: `/cronTasks/${data.id}/start`,
    method: 'post'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 获取任务执行日志
 */
export function getTaskLogs(params?: TaskLogQueryParams): Promise<ApiResponse<TaskLogListData>> {
  return request({
    url: '/cronTasks/logs',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResponse<TaskLogListData>>
}

/**
 * 删除任务日志
 */
export function deleteTaskLogs(params?: {
  task_id?: number
  log_ids?: number[]
  before_date?: string
  log_level?: string
}): Promise<ApiResponse<any>> {
  return request({
    url: '/cronTasks/logs/delete',
    method: 'delete',
    params: params
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 导出任务日志
 */
export function exportTaskLogs(params?: TaskLogQueryParams & {
  format?: 'csv' | 'json' | 'txt'
}): Promise<Blob> {
  return request({
    url: '/cronTasks/logs/export',
    method: 'get',
    params: params,
    responseType: 'blob'
  }) as unknown as Promise<Blob>
}

/**
 * 获取日志统计信息
 */
export function getTaskLogStatistics(): Promise<ApiResponse<{
  total_logs: number
  success_logs: number
  error_logs: number
  storage_usage: number
  last_7_days: number[]
  log_levels: { [key: string]: number }
}>> {
  return request({
    url: '/cronTasks/logs/statistics',
    method: 'get'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 清理过期日志
 */
export function cleanupTaskLogs(params?: {
  days?: number
  keep_success?: boolean
  keep_error?: boolean
}): Promise<ApiResponse<any>> {
  return request({
    url: '/cronTasks/logs/cleanup',
    method: 'post',
    data: params
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 暂停任务
 */
export function pauseTask(id: number): Promise<ApiResponse<any>> {
  return request({
    url: `/cronTasks/${id}/pause`,
    method: 'post'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 恢复任务
 */
export function resumeTask(id: number): Promise<ApiResponse<any>> {
  return request({
    url: `/cronTasks/${id}/resume`,
    method: 'post'
  }) as unknown as Promise<ApiResponse<any>>
}

/**
 * 中断任务
 */
export function interruptTask(id: number): Promise<ApiResponse<any>> {
  return request({
    url: `/cronTasks/${id}/interrupt`,
    method: 'post'
  }) as unknown as Promise<ApiResponse<any>>
}

// ========== 新增的验证和配置接口 ==========

// 脚本语法验证相关接口
export interface ValidationError {
  startLineNumber: number
  startColumn: number
  endLineNumber: number
  endColumn: number
  severity: number
  message: string
}

export interface ScriptValidationRequest {
  content: string
  script_type: number // 0-shell, 1-cmd, 2-powershell, 3-python
}

export interface ScriptValidationResponse {
  valid: boolean
  errors: ValidationError[]
  message: string
}

/**
 * 校验脚本语法
 */
export function validateScriptSyntax(data: ScriptValidationRequest): Promise<ApiResponse<ScriptValidationResponse>> {
  return request({
    url: '/cronTasks/validation/script',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<ScriptValidationResponse>>
}

// Cron表达式验证相关接口
export interface CronValidationRequest {
  expression: string
}

export interface CronExecutionTime {
  nextExecutionTime: string
  previousExecutionTime?: string
  executionTimes: string[]
}

export interface CronValidationResponse {
  valid: boolean
  message: string
  description?: string
  executionTimes?: CronExecutionTime
}

/**
 * 校验Cron表达式
 */
export function validateCronExpression(data: CronValidationRequest): Promise<ApiResponse<CronValidationResponse>> {
  return request({
    url: '/cronTasks/validation/cron',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<CronValidationResponse>>
}

// Python类验证相关接口
export interface PythonClassValidationRequest {
  class_path: string // 格式：module.submodule.ClassName
}

export interface PythonClassInfo {
  className: string
  module: string
  description?: string
  methods: string[]
  parameters: Record<string, any>
}

export interface PythonClassValidationResponse {
  valid: boolean
  exists: boolean
  classInfo?: PythonClassInfo
  message: string
}

/**
 * 验证Python类路径
 */
export function validatePythonClass(data: PythonClassValidationRequest): Promise<ApiResponse<PythonClassValidationResponse>> {
  return request({
    url: '/cronTasks/validation/python-class',
    method: 'post',
    data
  }) as unknown as Promise<ApiResponse<PythonClassValidationResponse>>
}

// 任务类型配置相关接口
export interface TaskTypeOption {
  value: number
  label: string
  icon: string
  description: string
  language: string
  fileExtension?: string
}

export interface TaskTypeConfigResponse {
  taskTypes: TaskTypeOption[]
  pythonClasses: PythonClassInfo[]
}

/**
 * 获取任务类型配置
 */
export function getTaskTypeConfig(): Promise<ApiResponse<TaskTypeConfigResponse>> {
  return request({
    url: '/cronTasks/config/task-types',
    method: 'get'
  }) as unknown as Promise<ApiResponse<TaskTypeConfigResponse>>
}
