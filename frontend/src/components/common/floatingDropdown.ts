import Vue from 'vue'
import { Component, Watch } from 'vue-property-decorator'

/**
 * FloatingDropdown —— 下拉浮层定位 mixin
 *
 * 从 PageSizeCombobox 已验证的浮层方案抽取（添加种子弹窗全自定义组件化时复用）：
 * - 展开时把 ref="options" 的下拉节点 teleport 到 document.body，规避父级 overflow 裁剪；
 * - 先渲染一次测量真实高度，再 fixed 定位：下方空间不足自动向上展开，横向防溢出；
 * - scroll(capture)/resize 时 rAF 节流重定位；关闭时把节点挪回原父级再交由 Vue 卸载，
 *   避免 Vue 在错误父节点上 removeChild 报错；
 * - 文档级 mousedown 点击外部（含浮层自身之外的任意区域）自动收起。
 *
 * 使用契约：宿主组件需提供 ref="root"（触发器根元素）与 ref="options"（下拉浮层元素，v-show 驱动）。
 */
@Component
export default class FloatingDropdown extends Vue {
  /** 下拉是否展开 */
  expanded = false
  /** teleport 后节点脱离组件根，需要本地状态驱动 class */
  isFloating = false

  // 定位/清理状态（非响应式用途，放实例字段便于调试与卸载清理）
  private rafId = 0
  private originalParent: HTMLElement | null = null
  private originalNextSibling: Node | null = null
  private onScroll: ((e: Event) => void) | null = null
  private onResize: (() => void) | null = null
  private onDocMouseDown: ((e: MouseEvent) => void) | null = null

  /** 宿主展开下拉（幂等）：teleport + 全局监听 */
  protected openDropdown(): void {
    if (this.expanded) return
    this.expanded = true
    this.$nextTick(() => this.openFloating())
    this.bindGlobalListeners()
  }

  /** 宿主收起下拉（幂等）：还原节点 + 解绑 */
  protected closeDropdown(): void {
    if (!this.expanded) return
    this.expanded = false
    this.closeFloating()
    this.unbindGlobalListeners()
  }

  /** 选项数量/内容变化可能改变高度与方向判断，宿主主动通知重定位 */
  protected notifyDropdownContentChanged(): void {
    if (this.isFloating) this.scheduleUpdate()
  }

  private bindGlobalListeners(): void {
    if (this.onDocMouseDown) return
    this.onDocMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null
      if (!target) return
      const root = this.$refs.root as HTMLElement | undefined
      const options = this.$refs.options as HTMLElement | undefined
      if (root?.contains(target) || options?.contains(target)) return
      this.closeDropdown()
    }
    document.addEventListener('mousedown', this.onDocMouseDown, true)
  }

  private unbindGlobalListeners(): void {
    if (this.onDocMouseDown) {
      document.removeEventListener('mousedown', this.onDocMouseDown, true)
      this.onDocMouseDown = null
    }
  }

  @Watch('expanded')
  onExpandedChange(val: boolean): void {
    if (val) {
      // capture=true：scroll 事件不冒泡，只能在捕获阶段于 window 一层抓到所有祖先滚动容器的滚动
      this.onScroll = () => this.scheduleUpdate()
      this.onResize = () => this.scheduleUpdate()
      window.addEventListener('scroll', this.onScroll, true)
      window.addEventListener('resize', this.onResize)
    } else {
      this.unbindViewportListeners()
    }
  }

  private unbindViewportListeners(): void {
    if (this.onScroll) {
      window.removeEventListener('scroll', this.onScroll, true)
      this.onScroll = null
    }
    if (this.onResize) {
      window.removeEventListener('resize', this.onResize)
      this.onResize = null
    }
  }

  private beforeDestroy(): void {
    this.unbindViewportListeners()
    if (this.rafId) cancelAnimationFrame(this.rafId)
    this.unbindGlobalListeners()
    this.closeFloating()
  }

  /** teleport 下拉到 body 并定位 */
  private openFloating(): void {
    const optionsEl = this.$refs.options as HTMLElement | undefined
    if (!optionsEl) return

    // 记住原位置，关闭时还原（保持 vnode 树稳定，让 Vue patch 正常工作）
    this.originalParent = optionsEl.parentElement
    this.originalNextSibling = optionsEl.nextSibling

    document.body.appendChild(optionsEl)
    this.isFloating = true

    // 先渲染一次测量真实高度，再精确放置
    this.measureAndPlace()
  }

  /** 关闭：把节点挪回原父级，清除浮动态与内联定位样式 */
  private closeFloating(): void {
    const optionsEl = this.$refs.options as HTMLElement | undefined
    if (optionsEl && this.isFloating) {
      if (this.originalParent) {
        if (
          this.originalNextSibling &&
          this.originalNextSibling.parentNode === this.originalParent
        ) {
          this.originalParent.insertBefore(optionsEl, this.originalNextSibling)
        } else {
          this.originalParent.appendChild(optionsEl)
        }
      }
      optionsEl.style.top = ''
      optionsEl.style.left = ''
      optionsEl.style.minWidth = ''
    }
    this.isFloating = false
    this.originalParent = null
    this.originalNextSibling = null
    if (this.rafId) {
      cancelAnimationFrame(this.rafId)
      this.rafId = 0
    }
  }

  private scheduleUpdate(): void {
    if (!this.isFloating) return
    if (this.rafId) cancelAnimationFrame(this.rafId)
    // jsdom 部分版本无 rAF，退化为宏任务，避免单测环境抛错
    const schedule = typeof window.requestAnimationFrame === 'function'
      ? window.requestAnimationFrame.bind(window)
      : (callback: FrameRequestCallback) => window.setTimeout(() => callback(performance.now()), 0)
    this.rafId = schedule(() => this.measureAndPlace())
  }

  /** 核心定位：方向判断 + fixed 坐标计算 */
  private measureAndPlace(): void {
    const root = this.$refs.root as HTMLElement | undefined
    const optionsEl = this.$refs.options as HTMLElement | undefined
    if (!root || !optionsEl || !this.isFloating) return

    const rect = root.getBoundingClientRect()
    const viewportH = window.innerHeight
    const GAP = 4

    // 先移出视口测量真实高度，避免定位前的闪烁与布局抖动
    optionsEl.style.left = `${rect.left}px`
    optionsEl.style.top = '-9999px'
    const actualH = optionsEl.offsetHeight

    const spaceBelow = viewportH - rect.bottom
    const spaceAbove = rect.top
    // 下方放得下，或下方空间更大时优先向下（避免极端情况下完全藏起来）
    const openDown = spaceBelow >= actualH + GAP || spaceBelow >= spaceAbove

    let top: number
    if (openDown) {
      top = rect.bottom + GAP
    } else {
      top = rect.top - GAP - actualH
      // 防止极端情况向上溢出视口顶部
      if (top < GAP) top = GAP
    }

    // 横向：默认左对齐触发器；右溢出时右对齐，并保证不贴边
    let left = rect.left
    const optionsWidth = optionsEl.offsetWidth
    if (left + optionsWidth > window.innerWidth - 8) {
      left = window.innerWidth - optionsWidth - 8
    }
    if (left < 8) left = 8

    optionsEl.style.top = `${top}px`
    optionsEl.style.left = `${left}px`
    // 浮层宽度不小于触发器宽度（fixed 定位后百分比基准是视口，不能靠 CSS 100%）
    optionsEl.style.minWidth = `${rect.width}px`
  }
}
