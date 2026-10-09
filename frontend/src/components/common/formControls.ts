/**
 * 表单级自定义控件共享类型（FormSelect / FormAutocomplete）
 *
 * 独立成 .ts 模块而非从 .vue 具名导出：ts-jest / tsc 对 *.vue 的模块 shim
 * 只声明默认导出，具名导入类型会报 TS2614（既有 spec 均本地重声明的根因）。
 */

export type FormSelectBadgeTone = 'neutral' | 'info' | 'success' | 'warning'

/** FormSelect 通用选项；富选项行（徽章/状态点）由 badge/status 字段机会渲染 */
export interface FormSelectOption {
  value: string
  label: string
  /** 右侧徽章文本（如下载器类型 qB/TR）；空则不渲染 */
  badge?: string
  badgeTone?: FormSelectBadgeTone
  /** 状态点（online=绿 / offline=灰）；缺省不渲染 */
  status?: 'online' | 'offline'
}

/** FormAutocomplete 自动补全建议项：value 之外的字段由宿主自行扩展并经作用域插槽消费 */
export interface FormAutocompleteSuggestion {
  value: string
}
