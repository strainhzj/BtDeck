<template>
  <div
    class="virtual-scroll-list"
    :style="{height: height + 'px'}"
    @scroll="handleScroll"
    ref="scrollContainer"
  >
    <div
      class="virtual-scroll-phantom"
      :style="{height: totalHeight + 'px'}"
    ></div>
    <div
      class="virtual-scroll-content"
      :style="{transform: `translateY(${offsetY}px)`}"
    >
      <div
        v-for="item in visibleItems"
        :key="getItemKey(item)"
        class="virtual-scroll-item"
        :style="{height: itemSize + 'px'}"
        @click="$emit('item-click', item, $event)"
      >
        <slot name="item" :item="item" :index="getItemIndex(item)">
          <div class="default-item">{{ getItemLabel(item) }}</div>
        </slot>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'

@Component({
  name: 'VirtualScrollList'
})
export default class VirtualScrollList extends Vue {
  @Prop({ required: true }) data!: any[]
  @Prop({ default: 32 }) itemSize!: number
  @Prop({ default: 200 }) height!: number
  @Prop({ default: 'value' }) keyField!: string
  @Prop({ default: 'label' }) labelField!: string
  @Prop({ default: 5 }) buffer!: number

  // Data
  scrollTop = 0
  startIndex = 0
  endIndex = 0
  visibleItems: any[] = []
  itemHeights: number[] = []
  itemPositions: number[] = []

  // 性能优化相关
  lastScrollTop = 0
  scrollDirection = 'down'
  renderDebounceTimer = 0
  isRendering = false

  // Computed
  get totalHeight(): number {
    return this.data.length * this.itemSize
  }

  get offsetY(): number {
    return this.startIndex * this.itemSize
  }

  // Watchers
  @Watch('data', { immediate: true })
  onDataChange() {
    this.updateVisibleRange()
  }

  @Watch('height')
  onHeightChange() {
    this.updateVisibleRange()
  }

  @Watch('itemSize')
  onItemSizeChange() {
    this.updateVisibleRange()
  }

  // Lifecycle
  mounted() {
    this.updateVisibleRange()
    this.calculateItemPositions()
  }

  beforeDestroy() {
    // 清理防抖定时器
    if (this.renderDebounceTimer) {
      clearTimeout(this.renderDebounceTimer)
      this.renderDebounceTimer = 0
    }

    // 清理数据引用
    this.visibleItems = []
    this.itemPositions = []
    this.itemHeights = []
  }

  // Methods
  handleScroll(event: Event) {
    if (this.isRendering) {
      return // 如果正在渲染，跳过本次滚动
    }

    const target = event.target as HTMLElement
    const newScrollTop = target.scrollTop

    // 检测滚动方向
    this.scrollDirection = newScrollTop > this.lastScrollTop ? 'down' : 'up'
    this.lastScrollTop = newScrollTop

    // 清除之前的防抖定时器
    if (this.renderDebounceTimer) {
      clearTimeout(this.renderDebounceTimer)
    }

    // 设置防抖，16ms（一帧时间）
    this.renderDebounceTimer = window.setTimeout(() => {
      this.scrollTop = newScrollTop
      this.updateVisibleRange()
    }, 16)
  }

  private updateVisibleRange() {
    const startTime = performance.now()

    this.isRendering = true

    try {
      const visibleCount = Math.ceil(this.height / this.itemSize)
      const start = Math.floor(this.scrollTop / this.itemSize)
      const end = start + visibleCount + this.buffer

      // 根据滚动方向优化缓冲区
      let bufferStart = this.buffer
      let bufferEnd = this.buffer

      if (this.scrollDirection === 'down') {
        bufferStart = Math.max(1, Math.floor(this.buffer * 0.5))
        bufferEnd = this.buffer * 1.5
      } else {
        bufferStart = this.buffer * 1.5
        bufferEnd = Math.max(1, Math.floor(this.buffer * 0.5))
      }

      this.startIndex = Math.max(0, start - bufferStart)
      this.endIndex = Math.min(this.data.length - 1, end + bufferEnd)

      // 批量更新visibleItems
      this.visibleItems = this.data.slice(this.startIndex, this.endIndex + 1)

      const renderTime = performance.now() - startTime

      // 性能监控：如果渲染时间超过16ms，记录警告
      if (renderTime > 16) {
        console.warn(`VirtualScrollList: 渲染耗时 ${renderTime.toFixed(2)}ms，项目数量: ${this.visibleItems.length}，数据总数: ${this.data.length}`)
      }
    } finally {
      this.isRendering = false
    }
  }

  private calculateItemPositions() {
    this.itemPositions = this.data.map((_, index) => index * this.itemSize)
  }

  getItemKey(item: any): string {
    return String(item[this.keyField] || item.value || item.id || item)
  }

  getItemLabel(item: any): string {
    return String(item[this.labelField] || item.label || item.name || item)
  }

  getItemIndex(item: any): number {
    const key = this.getItemKey(item)
    return this.data.findIndex(d => this.getItemKey(d) === key)
  }

  // 公共方法
  scrollToItem(item: any) {
    const index = this.getItemIndex(item)
    if (index !== -1) {
      const container = this.$refs.scrollContainer as HTMLElement
      container.scrollTop = index * this.itemSize
    }
  }

  scrollToIndex(index: number) {
    if (index >= 0 && index < this.data.length) {
      const container = this.$refs.scrollContainer as HTMLElement
      container.scrollTop = index * this.itemSize
    }
  }

  getScrollPosition(): number {
    return this.scrollTop
  }

  setScrollPosition(position: number) {
    const container = this.$refs.scrollContainer as HTMLElement
    container.scrollTop = Math.max(0, Math.min(position, this.totalHeight - this.height))
  }
}
</script>

<style lang="scss" scoped>
.virtual-scroll-list {
  position: relative;
  overflow-y: auto;
  overflow-x: hidden;

  .virtual-scroll-phantom {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: -1;
  }

  .virtual-scroll-content {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;

    .virtual-scroll-item {
      box-sizing: border-box;
      display: flex;
      align-items: center;

      .default-item {
        padding: 8px 12px;
        width: 100%;
      }
    }
  }
}
</style>