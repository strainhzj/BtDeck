<template>
  <div
    class="dash-grid"
    data-testid="dash-grid"
    @dragstart="onDragStart"
    @dragover="onDragOver"
    @drop="onDrop"
    @dragend="onDragEnd"
  >
    <DashWidget
      v-for="id in layout.order"
      :key="id"
      :widget-id="id"
      :title="$t(`dashboard.widgets.${id}.title`)"
      :span="spanOf(id)"
      :editing="editing"
      :dragging="dragId === id"
      :style="{display: isVisible(id) ? undefined : 'none'}"
      @cycle-width="$emit('cycle-width', id)"
    >
      <slot :name="id" />
    </DashWidget>
  </div>
</template>

<script lang="ts">
/**
 * DashboardGrid —— 12 列 widget 网格 + 编辑模式状态机（仪表盘一期 W2）。
 *
 * - 网格渲染 layout.order 全量卡（v-show 隐藏不可见卡，保留组件实例与
 *   轮询/采样状态，切换预设回来不丢数据）；
 * - 原生 HTML5 DnD：容器级事件代理（dragstart/dragover/drop/dragend），
 *   dragover 实时重排 emit reorder —— 与验收示意图一致的即时插序形态；
 * - 布局数据（order/spans/preset）与持久化在父级（index.vue 持有，
 *   dashboardLayout 纯函数落 localStorage），本组件只渲染与上抛事件。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import DashWidget from './DashWidget.vue'
import { WidgetId, WidgetLayout, visibleWidgetIds, PresetKey } from './dashboardLayout'

@Component({ name: 'DashboardGrid', components: { DashWidget } })
export default class DashboardGrid extends Vue {
  @Prop({ required: true }) private layout!: WidgetLayout
  @Prop({ required: true }) private preset!: PresetKey
  @Prop({ default: false }) private editing!: boolean

  private dragId: WidgetId | null = null

  private isVisible(id: WidgetId): boolean {
    return visibleWidgetIds(this.preset).includes(id)
  }

  private spanOf(id: WidgetId): number {
    return this.layout.spans[id] || 6
  }

  private widgetIdFromEvent(e: DragEvent): WidgetId | null {
    const target = e.target as HTMLElement | null
    const el = target ? target.closest<HTMLElement>('.dash-widget') : null
    const id = el?.dataset.widgetId
    return id ? (id as WidgetId) : null
  }

  private onDragStart(e: DragEvent) {
    if (!this.editing) return
    const id = this.widgetIdFromEvent(e)
    if (!id || !e.dataTransfer) return
    this.dragId = id
    e.dataTransfer.effectAllowed = 'move'
    try {
      e.dataTransfer.setData('text/plain', id)
    } catch {
      // setData 在部分环境（无 DataTransfer 构造）抛错可忽略；拖拽仍以 dragId 为准
    }
  }

  private onDragOver(e: DragEvent) {
    if (!this.editing || !this.dragId) return
    const overId = this.widgetIdFromEvent(e)
    if (!overId || overId === this.dragId) return
    e.preventDefault()
    const order = [...this.layout.order]
    const from = order.indexOf(this.dragId)
    const to = order.indexOf(overId)
    if (from < 0 || to < 0) return
    order.splice(to, 0, order.splice(from, 1)[0])
    this.$emit('reorder', order)
  }

  private onDrop(e: DragEvent) {
    if (this.editing) e.preventDefault()
  }

  private onDragEnd() {
    this.dragId = null
  }
}
</script>
