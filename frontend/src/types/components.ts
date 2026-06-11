/**
 * Vue组件相关类型定义
 * 统一管理组件Props和事件类型定义
 */

import { TaskType, TaskStatus } from './scheduled-tasks'

// 表格列配置
export interface TableColumn {
  prop: string                         // 属性名
  label: string                        // 显示标签
  width?: number                       // 列宽度
  minWidth?: number                    // 最小宽度
  align?: 'left' | 'center' | 'right' // 对齐方式
  sortable?: boolean                   // 是否可排序
  resizable?: boolean                  // 是否可调整大小
  showOverflowTooltip?: boolean        // 是否显示溢出提示
  fixed?: boolean | 'left' | 'right'  // 固定列位置
}

// 表单验证规则
export interface FormRule {
  required?: boolean                   // 是否必填
  message?: string                     // 错误信息
  trigger?: 'blur' | 'change' | ['blur', 'change']  // 触发方式
  min?: number                         // 最小长度
  max?: number                         // 最大长度
  pattern?: RegExp                     // 正则表达式
  validator?: (rule: any, value: any, callback: any) => void  // 自定义验证器
}

// 表单验证规则集合
export type FormRules = Record<string, FormRule | FormRule[]>

// 分页组件配置
export interface PaginationConfig {
  currentPage: number                  // 当前页码
  pageSize: number                     // 每页大小
  pageSizes?: number[]                 // 可选页面大小
  total: number                        // 总记录数
  layout?: string                      // 布局
  background?: boolean                 // 是否显示背景色
}

// 搜索表单配置
export interface SearchFormConfig {
  label: string                        // 表单项标签
  prop: string                         // 表单项属性名
  type: 'input' | 'select' | 'date-range' | 'date-picker'  // 表单项类型
  placeholder?: string                 // 占位文本
  options?: Array<{                    // 选项列表
    label: string
    value: any
    disabled?: boolean
  }>
  clearable?: boolean                  // 是否可清空
  multiple?: boolean                   // 是否多选
  format?: string                      // 日期格式
  valueFormat?: string                 // 日期值格式
}

// 操作按钮配置
export interface ActionButton {
  type: 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'text'  // 按钮类型
  label: string                        // 按钮文本
  icon?: string                        // 图标
  disabled?: boolean                   // 是否禁用
  loading?: boolean                    // 是否加载中
  plain?: boolean                      // 是否朴素按钮
  size?: 'large' | 'medium' | 'small' | 'mini'  // 按钮尺寸
  action: (row?: any) => void          // 点击事件处理函数
  show?: (row?: any) => boolean        // 是否显示条件
}

// 统计卡片数据
export interface StatisticCard {
  title: string                        // 标题
  value: number | string              // 数值
  icon: string                         // 图标
  color: string                        // 颜色
  suffix?: string                      // 后缀
  prefix?: string                      // 前缀
  precision?: number                   // 小数位数
  formatter?: (value: number) => string  // 格式化函数
}

// 任务状态标签映射
export const TASK_STATUS_OPTIONS = [
  { label: '等待运行', value: TaskStatus.WAITING, type: 'info' },
  { label: '运行中', value: TaskStatus.RUNNING, type: 'warning' },
  { label: '空闲', value: TaskStatus.SUCCESS, type: 'success' },
  { label: '失败', value: TaskStatus.FAILED, type: 'danger' },
  { label: '暂停', value: TaskStatus.PAUSED, type: 'info' }
]

// 任务类型选项映射
export const TASK_TYPE_OPTIONS = [
  { label: 'shell脚本', value: TaskType.SHELL, icon: 'el-icon-document' },
  { label: 'cmd脚本', value: TaskType.BATCH, icon: 'el-icon-document-copy' },
  { label: 'powershell脚本', value: TaskType.POWERSHELL, icon: 'el-icon-setting' },
  { label: 'python脚本', value: TaskType.PYTHON, icon: 'el-icon-cpu' },
  { label: 'python内部类', value: TaskType.PYTHON_INTERNAL, icon: 'el-icon-connection' }
]

// 脚本验证结果
export interface ScriptValidationResult {
  valid: boolean                       // 是否有效
  errors: ValidationError[]            // 错误列表
  warnings: ValidationWarning[]       // 警告列表
  summary: string                      // 摘要信息
}

// 验证错误信息
export interface ValidationError {
  line: number                         // 行号
  column: number                       // 列号
  message: string                      // 错误信息
  severity: 'error' | 'warning'        // 严重程度
  code?: string                        // 错误代码
}

// 验证警告信息
export interface ValidationWarning {
  line: number                         // 行号
  column: number                       // 列号
  message: string                      // 警告信息
  code?: string                        // 警告代码
}