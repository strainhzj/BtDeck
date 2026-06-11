/**
 * 通用工具类型定义
 * 提供通用的工具函数类型和扩展类型
 */

// 基础的键值对类型
export type KeyValuePair<T = any> = Record<string, T>

// 可选的部分类型
export type Partial<T> = {
  [P in keyof T]?: T[P]
}

// 必需的部分类型
export type Required<T> = {
  [P in keyof T]-?: T[P]
}

// 选择性Pick类型
export type Pick<T, K extends keyof T> = {
  [P in K]: T[P]
}

// 排除性Omit类型
export type Omit<T, K extends keyof T> = Pick<T, Exclude<keyof T, K>>

// 深度只读类型
export type DeepReadonly<T> = {
  readonly [P in keyof T]: T[P] extends object ? DeepReadonly<T[P]> : T[P]
}

// 深度Partial类型
export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P]
}

// ID类型
export type ID = number | string

// 时间戳类型
export type Timestamp = number | string

// 日期格式类型
export type DateFormat = 'YYYY-MM-DD' | 'YYYY-MM-DD HH:mm:ss' | 'MM/DD/YYYY' | 'DD/MM/YYYY'

// 排序方向
export type SortDirection = 'asc' | 'desc'

// 排序配置
export interface SortConfig {
  field: string                        // 排序字段
  direction: SortDirection              // 排序方向
}

// 文件上传相关类型
export interface UploadFile {
  name: string                         // 文件名
  size: number                         // 文件大小
  type: string                         // MIME类型
  lastModified: number                  // 最后修改时间
  uid?: string                         // 唯一标识
  status?: 'ready' | 'uploading' | 'success' | 'error'  // 上传状态
  percent?: number                     // 上传进度
  response?: any                       // 服务器响应
  url?: string                         // 文件URL
}

// 选择选项类型
export interface SelectOption<T = any> {
  label: string                        // 显示文本
  value: T                             // 值
  disabled?: boolean                   // 是否禁用
  icon?: string                        // 图标
  description?: string                 // 描述
}

// 树形节点类型
export interface TreeNode<T = any> {
  id: ID                               // 节点ID
  label: string                        // 显示文本
  children?: TreeNode<T>[]            // 子节点
  data?: T                             // 节点数据
  disabled?: boolean                   // 是否禁用
  expanded?: boolean                   // 是否展开
  selected?: boolean                   // 是否选中
  level?: number                       // 节点层级
  parentId?: ID                        // 父节点ID
}

// 颜色类型
export type Color = string

// 尺寸类型
export type Size = 'large' | 'medium' | 'small' | 'mini'

// 位置类型
export type Position = 'top' | 'right' | 'bottom' | 'left'

// 对齐方式
export type Align = 'start' | 'center' | 'end' | 'stretch'

// 回调函数类型
export type Callback<T = void> = () => T
export type CallbackWithParam<P, T = void> = (param: P) => T
export type AsyncCallback<T = void> = () => Promise<T>
export type AsyncCallbackWithParam<P, T = void> = (param: P) => Promise<T>

// 事件处理器类型
export type EventHandler<T = Event> = (event: T) => void
export type AsyncEventHandler<T = Event> = (event: T) => Promise<void>

// 验证函数类型
export type ValidatorFunction = (rule: any, value: any, callback: (error?: string | Error) => void) => void

// 格式化函数类型
export type FormatterFunction<T = any, R = string> = (value: T) => R

// 转换函数类型
export type TransformerFunction<T = any, R = any> = (value: T) => R

// 条件类型辅助函数
export type IsNever<T> = [T] extends [never] ? true : false
export type IsAny<T> = 0 extends 1 & T ? true : false
export type IsUnknown<T> = IsNever<T> extends true ? false : IsAny<T> extends true ? true : unknown extends T ? true : false

// 工具类型：获取数组元素类型
export type ArrayElement<T> = T extends (infer U)[] ? U : never

// 工具类型：获取函数返回值类型
export type ReturnType<T> = T extends (...args: any[]) => infer R ? R : never

// 工具类型：获取函数参数类型
export type Parameters<T> = T extends (...args: infer P) => any ? P : never

// 工具类型：构造函数类型
export type Constructor<T = {}> = new (...args: any[]) => T

// 工具类型：Promise值类型
export type UnwrapPromise<T> = T extends Promise<infer U> ? U : T