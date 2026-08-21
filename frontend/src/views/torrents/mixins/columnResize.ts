/**
 * 表格列宽拖拽 Mixin
 *
 * 列表模式（index.vue）与传统模式（TraditionalView.vue）共用：
 * - th 右缘拖拽手柄调整列宽，mouseup 时一次性写入 localStorage
 * - 双击手柄恢复单列默认宽度
 * - resetColumnWidths 供列设置菜单"重置列宽"调用（全部恢复默认）
 * - 名称列等自适应列不登记宽度、不渲染手柄，自动填满剩余空间
 *
 * 子类契约（class 字段覆写，mixin created 钩子读取）：
 * - columnWidthStorageKey：localStorage key（btdeck_ 前缀；空串则不持久化）
 * - defaultColumnWidths：各列默认宽度（px）；后续新增列未存储时自动落回默认
 *
 * 防回归要点：
 * - document 级 mousemove/mouseup 用箭头函数属性绑定，保证 add/remove
 *   同一引用；beforeDestroy 成对移除，组件销毁后不再触发
 * - 拖拽中给 body 加 column-resizing 类（全局 col-resize 光标 + 禁止文本
 *   选择），mouseup/destroy 移除，异常路径不残留
 * - localStorage 只在拖拽结束/重置时写一次；读取 JSON.parse 包 try/catch，
 *   损坏数据静默回退默认值
 */
import Component from 'vue-class-component'
import { Vue } from 'vue-property-decorator'

/** 拖拽可达到的宽度边界（px）：再窄放不下表头排序图标，再宽失去屏效 */
const MIN_COLUMN_WIDTH = 40
const MAX_COLUMN_WIDTH = 600

/** 宽度夹取到合法区间；非法值（NaN/负数）回退下限 */
function clampColumnWidth(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return MIN_COLUMN_WIDTH
  return Math.min(MAX_COLUMN_WIDTH, Math.max(MIN_COLUMN_WIDTH, Math.round(value)))
}

@Component({ name: 'ColumnResizeMixin' })
export default class ColumnResizeMixin extends Vue {
  // ====== 子类覆写 ======
  protected columnWidthStorageKey = ''
  protected defaultColumnWidths: Record<string, number> = {}

  // ====== 列宽状态（模板经 columnWidthStyle 绑定到 th 内联样式） ======
  protected columnWidths: Record<string, number> = {}

  // ====== 拖拽会话状态（非响应式语义，仅拖拽期间读写） ======
  private resizingKey = ''
  private resizeStartX = 0
  private resizeStartWidth = 0
  // document 监听的绑定引用（add/remove 必须同引用；不能用类字段箭头函数——
  // vue-class-component 会把箭头字段收进 data，捕获的 this 是构造期临时实例）
  private boundColumnResizeMove: ((event: MouseEvent) => void) | null = null
  private boundColumnResizeEnd: (() => void) | null = null

  created() {
    this.initColumnWidths()
  }

  beforeDestroy() {
    this.teardownColumnResize()
  }

  /** 默认宽度打底，localStorage 已存值覆盖（只认登记过的列键） */
  private initColumnWidths() {
    const widths: Record<string, number> = { ...this.defaultColumnWidths }
    if (this.columnWidthStorageKey) {
      try {
        const raw = localStorage.getItem(this.columnWidthStorageKey)
        if (raw) {
          const saved = JSON.parse(raw) as Record<string, unknown>
          Object.keys(widths).forEach(key => {
            const value = saved[key]
            if (typeof value === 'number') {
              widths[key] = clampColumnWidth(value)
            }
          })
        }
      } catch (error) {
        console.warn('[ColumnResize] 列宽存储读取失败，使用默认值:', error)
      }
    }
    this.columnWidths = widths
  }

  private persistColumnWidths() {
    if (!this.columnWidthStorageKey) return
    try {
      localStorage.setItem(this.columnWidthStorageKey, JSON.stringify(this.columnWidths))
    } catch (error) {
      console.warn('[ColumnResize] 列宽存储写入失败:', error)
    }
  }

  /** th 宽度样式；未登记的列键返回空对象（名称列自适应） */
  protected columnWidthStyle(key: string): Record<string, string> {
    const width = this.columnWidths[key]
    return typeof width === 'number' ? { width: `${width}px` } : {}
  }

  /** 手柄 mousedown：登记拖拽会话并挂 document 监听 */
  protected startColumnResize(key: string, event: MouseEvent) {
    // 仅响应左键（buttons 位掩码），右键/中键交给浏览器默认行为
    if (!(event.buttons & 1)) return
    event.preventDefault()
    event.stopPropagation()
    this.resizingKey = key
    this.resizeStartX = event.clientX
    this.resizeStartWidth = this.columnWidths[key] ?? this.defaultColumnWidths[key] ?? MIN_COLUMN_WIDTH
    this.boundColumnResizeMove = this.onColumnResizeMove.bind(this)
    this.boundColumnResizeEnd = this.onColumnResizeEnd.bind(this)
    document.addEventListener('mousemove', this.boundColumnResizeMove)
    document.addEventListener('mouseup', this.boundColumnResizeEnd)
    document.body.classList.add('column-resizing')
  }

  private onColumnResizeMove(event: MouseEvent) {
    if (!this.resizingKey) return
    const delta = event.clientX - this.resizeStartX
    const next = clampColumnWidth(this.resizeStartWidth + delta)
    // 键已在 initColumnWidths 全量登记，直接赋值保持响应式
    this.columnWidths[this.resizingKey] = next
  }

  private onColumnResizeEnd() {
    if (this.resizingKey) {
      this.persistColumnWidths()
    }
    this.teardownColumnResize()
  }

  private teardownColumnResize() {
    this.resizingKey = ''
    if (this.boundColumnResizeMove) {
      document.removeEventListener('mousemove', this.boundColumnResizeMove)
      this.boundColumnResizeMove = null
    }
    if (this.boundColumnResizeEnd) {
      document.removeEventListener('mouseup', this.boundColumnResizeEnd)
      this.boundColumnResizeEnd = null
    }
    document.body.classList.remove('column-resizing')
  }

  /** 双击手柄：恢复单列默认宽度并立即持久化 */
  protected handleColumnResizeDblclick(key: string) {
    const fallback = this.defaultColumnWidths[key]
    if (typeof fallback !== 'number') return
    this.columnWidths[key] = fallback
    this.persistColumnWidths()
  }

  /** 列设置菜单"重置列宽"：全部恢复默认并持久化 */
  protected resetColumnWidths() {
    this.columnWidths = { ...this.defaultColumnWidths }
    this.persistColumnWidths()
  }

  /** 汇总一组列键的当前宽度（表级 min-width 计算用） */
  protected sumColumnWidths(keys: string[]): number {
    return keys.reduce((total, key) => total + (this.columnWidths[key] || 0), 0)
  }
}
