/**
 * BitTorrent管理器类型定义统一导出文件
 *
 * 本文件作为类型定义的统一入口，提供BTDeckTypes命名空间
 * 遵循类型集中管理原则，避免类型定义分散在各个组件文件中
 *
 * @author btpManager开发团队
 * @version 1.0.0
 */

// 导入各个模块的类型定义
import * as ApiTypes from './api'
import * as ScheduledTasksTypes from './scheduled-tasks'
import * as TaskLogsTypes from './task-logs'
import * as ComponentsTypes from './components'
import * as CommonTypes from './common'

// BTDeckTypes命名空间 - 统一的类型管理入口
export namespace BTDeckTypes {
  // 重新导出API相关类型
  export import ApiResponse = ApiTypes.ApiResponse
  export import PaginationParams = ApiTypes.PaginationParams
  export import PaginatedResponse = ApiTypes.PaginatedResponse
  export import RequestConfig = ApiTypes.RequestConfig
  export import ErrorResponse = ApiTypes.ErrorResponse

  // 重新导出定时任务相关类型
  export import TaskType = ScheduledTasksTypes.TaskType
  export import TaskStatus = ScheduledTasksTypes.TaskStatus
  export import ScheduledTask = ScheduledTasksTypes.ScheduledTask
  export import TaskCreateRequest = ScheduledTasksTypes.TaskCreateRequest
  export import TaskUpdateRequest = ScheduledTasksTypes.TaskUpdateRequest
  export import TaskDeleteRequest = ScheduledTasksTypes.TaskDeleteRequest
  export import TaskListRequest = ScheduledTasksTypes.TaskListRequest
  export import TaskListResponse = ScheduledTasksTypes.TaskListResponse
  export import TaskExecuteRequest = ScheduledTasksTypes.TaskExecuteRequest
  export import TaskTypeOption = ScheduledTasksTypes.TaskTypeOption
  export import CronValidationResult = ScheduledTasksTypes.CronValidationResult
  export import CronValidationRequest = ScheduledTasksTypes.CronValidationRequest

  // 重新导出任务日志相关类型
  export import TaskLog = TaskLogsTypes.TaskLog
  export import TaskLogListRequest = TaskLogsTypes.TaskLogListRequest
  export import TaskLogListResponse = TaskLogsTypes.TaskLogListResponse
  export import TaskLogDeleteRequest = TaskLogsTypes.TaskLogDeleteRequest
  export import TaskLogStatistics = TaskLogsTypes.TaskLogStatistics
  export import TaskLogStatisticsResponse = TaskLogsTypes.TaskLogStatisticsResponse
  export import TaskLogCleanupRequest = TaskLogsTypes.TaskLogCleanupRequest
  export import TaskLogExportRequest = TaskLogsTypes.TaskLogExportRequest
  export import TaskLogDetail = TaskLogsTypes.TaskLogDetail

  // 重新导出组件相关类型
  export import TableColumn = ComponentsTypes.TableColumn
  export import FormRule = ComponentsTypes.FormRule
  export import FormRules = ComponentsTypes.FormRules
  export import PaginationConfig = ComponentsTypes.PaginationConfig
  export import SearchFormConfig = ComponentsTypes.SearchFormConfig
  export import ActionButton = ComponentsTypes.ActionButton
  export import StatisticCard = ComponentsTypes.StatisticCard
  export import ScriptValidationResult = ComponentsTypes.ScriptValidationResult
  export import ValidationError = ComponentsTypes.ValidationError
  export import ValidationWarning = ComponentsTypes.ValidationWarning
  export import TASK_STATUS_OPTIONS = ComponentsTypes.TASK_STATUS_OPTIONS
  export import TASK_TYPE_OPTIONS = ComponentsTypes.TASK_TYPE_OPTIONS

  // 重新导出通用工具类型
  export import KeyValuePair = CommonTypes.KeyValuePair
  export import Partial = CommonTypes.Partial
  export import Required = CommonTypes.Required
  export import Pick = CommonTypes.Pick
  export import Omit = CommonTypes.Omit
  export import DeepReadonly = CommonTypes.DeepReadonly
  export import DeepPartial = CommonTypes.DeepPartial
  export import ID = CommonTypes.ID
  export import Timestamp = CommonTypes.Timestamp
  export import DateFormat = CommonTypes.DateFormat
  export import SortDirection = CommonTypes.SortDirection
  export import SortConfig = CommonTypes.SortConfig
  export import UploadFile = CommonTypes.UploadFile
  export import SelectOption = CommonTypes.SelectOption
  export import TreeNode = CommonTypes.TreeNode
  export import Color = CommonTypes.Color
  export import Size = CommonTypes.Size
  export import Position = CommonTypes.Position
  export import Align = CommonTypes.Align
  export import Callback = CommonTypes.Callback
  export import CallbackWithParam = CommonTypes.CallbackWithParam
  export import AsyncCallback = CommonTypes.AsyncCallback
  export import AsyncCallbackWithParam = CommonTypes.AsyncCallbackWithParam
  export import EventHandler = CommonTypes.EventHandler
  export import AsyncEventHandler = CommonTypes.AsyncEventHandler
  export import ValidatorFunction = CommonTypes.ValidatorFunction
  export import FormatterFunction = CommonTypes.FormatterFunction
  export import TransformerFunction = CommonTypes.TransformerFunction
}

// 直接导出所有类型，方便解构使用
export * from './api'
export * from './scheduled-tasks'
export * from './task-logs'
export * from './components'
export * from './common'

// 默认导出命名空间
export default BTDeckTypes

/**
 * 使用示例：
 *
 * // 方式1：命名空间导入
 * import { BTDeckTypes } from '@/types'
 * const taskList: BTDeckTypes.ScheduledTask[] = []
 *
 * // 方式2：解构导入
 * import { ScheduledTask, TaskLog, ApiResponse } from '@/types'
 * const task: ScheduledTask = { ... }
 * const response: ApiResponse<ScheduledTask> = { ... }
 *
 * // 方式3：默认导入
 * import BTDeckTypes from '@/types'
 * const task: BTDeckTypes.ScheduledTask = { ... }
 *
 * // 类型使用示例：
 * interface TaskManagementState {
 *   taskList: BTDeckTypes.ScheduledTask[]
 *   loading: boolean
 *   queryParams: BTDeckTypes.TaskListRequest
 * }
 */