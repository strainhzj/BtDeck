<template>
  <div
    ref="root"
    class="page-size-combobox"
    role="combobox"
    aria-haspopup="listbox"
    :aria-controls="controlsId"
    :aria-expanded="String(expanded)"
  >
    <input
      ref="input"
      :value="value"
      class="page-size-input"
      type="text"
      inputmode="numeric"
      aria-label="每页数量"
      title="选择预设值或输入 1 至 100000，按 Enter 或失焦生效"
      @input="handleInput"
      @focus="$emit('focus')"
      @keyup.enter="handleApply"
      @blur="$emit('blur')"
    />
    <button
      type="button"
      class="page-size-toggle"
      :class="expanded ? 'el-icon-arrow-down' : 'el-icon-arrow-up'"
      :aria-label="expanded ? '收起分页大小选项' : '展开分页大小选项'"
      :aria-expanded="String(expanded)"
      @mousedown.prevent.stop
      @click.stop="$emit('toggle')"
    ></button>
    <!-- 下拉列表：默认仍在 DOM 子节点；appendToBody=true 且 expanded 时
         在 watch 钩子里被 appendChild 到 document.body，避免父级 overflow 裁剪。 -->
    <ul
      v-show="expanded"
      ref="options"
      :id="controlsId"
      class="page-size-options"
      :class="{'page-size-options--floating': isFloating}"
      role="listbox"
      aria-label="分页大小预设"
    >
      <li
        v-for="size in options"
        :key="size"
        role="none"
      >
        <button
          type="button"
          role="option"
          :aria-selected="String(size === pageSize)"
          @mousedown.prevent
          @click="handleSelect(size)"
        >{{ size }}</button>
      </li>
    </ul>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'

export interface PageSizeSuggestion {
  value: string
}

@Component({ name: 'PageSizeCombobox' })
export default class PageSizeCombobox extends Vue {
  @Prop({ required: true }) value!: string
  @Prop({ required: true }) pageSize!: number
  @Prop({ default: false }) expanded!: boolean
  @Prop({ default: () => [20, 50, 100, 500, 1000] }) options!: number[]
  @Prop({ default: 'torrent-page-size-options' }) controlsId!: string
  /**
   * 是否把下拉 teleport 到 body 并自动判断上下展开方向。
   * 默认 false —— 保持旧行为（下拉作为 DOM 子节点，受父级 overflow 裁剪），
   * 不破坏既有调用方。需要"不被遮挡 + 自动上下"的页面显式传 true。
   */
  @Prop({ type: Boolean, default: false }) appendToBody!: boolean

  // teleport 后节点脱离组件根，需要本地状态驱动 class
  isFloating = false

  // 定位/清理状态（非响应式用途，放实例字段便于调试与卸载清理）
  private rafId = 0
  private originalParent: HTMLElement | null = null
  private originalNextSibling: Node | null = null
  private onScroll: ((e: Event) => void) | null = null
  private onResize: (() => void) | null = null

  public focusInput(): void {
    const input = this.$refs.input as HTMLInputElement | undefined
    input?.focus()
  }

  @Watch('expanded')
  onExpandedChange(val: boolean) {
    if (!this.appendToBody) return
    if (val) {
      // 展开后下一帧 teleport + 定位（确保 v-show 节点已可见）
      this.$nextTick(() => this.openFloating())
    } else {
      this.closeFloating()
    }
  }

  @Watch('options')
  onOptionsChange() {
    // 选项数量变化可能改变方向判断（高度变化），重新定位
    if (this.isFloating) this.scheduleUpdate()
  }

  private mounted(): void {
    // capture=true：scroll 事件不冒泡，只能在捕获阶段于 window 一层抓到所有祖先滚动容器的滚动
    this.onScroll = () => this.scheduleUpdate()
    this.onResize = () => this.scheduleUpdate()
    window.addEventListener('scroll', this.onScroll, true)
    window.addEventListener('resize', this.onResize)
  }

  private beforeDestroy(): void {
    if (this.onScroll) window.removeEventListener('scroll', this.onScroll, true)
    if (this.onResize) window.removeEventListener('resize', this.onResize)
    if (this.rafId) cancelAnimationFrame(this.rafId)
    // 先把节点挪回原父级，再让 Vue 卸载——避免 Vue 在错误的父节点上 removeChild 报错
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
    this.rafId = requestAnimationFrame(() => this.measureAndPlace())
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
  }

  private handleInput(event: Event): void {
    const input = event.target as HTMLInputElement | null
    this.$emit('input', input?.value ?? '')
  }

  private handleApply(): void {
    this.$emit('apply', this.value)
  }

  private handleSelect(size: number): void {
    const suggestion: PageSizeSuggestion = { value: String(size) }
    this.$emit('select', suggestion)
  }
}
</script>
