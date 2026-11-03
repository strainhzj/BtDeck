<template>
  <section
    class="dash-widget"
    :class="{dragging: dragging}"
    :data-widget-id="widgetId"
    :draggable="editing"
    :style="{'--span': span}"
    :aria-label="title"
  >
    <div class="dash-widget-head">
      <span class="dash-widget-grip" :aria-hidden="true">
        <lucide-icon icon="grip-vertical" />
      </span>
      <span class="dash-widget-title">
        <lucide-icon :icon="meta.icon" />
        {{ title }}
      </span>
      <span
        v-if="meta.live"
        class="dash-widget-tag live"
      >{{ $t('dashboard.widgets.liveTag') }}</span>
      <span
        v-else-if="meta.presetTag"
        class="dash-widget-tag"
      >{{ $t(`dashboard.preset.${meta.presetTag}`) }}</span>
      <span class="dash-widget-actions">
        <button
          type="button"
          class="dash-widget-act"
          :title="$t('dashboard.edit.cycleWidth')"
          :aria-label="$t('dashboard.edit.cycleWidth')"
          @click.stop="$emit('cycle-width')"
        >
          <lucide-icon icon="maximize-2" />
        </button>
      </span>
    </div>
    <div class="dash-widget-body">
      <slot />
    </div>
  </section>
</template>

<script lang="ts">
/**
 * DashWidget —— widget 卡片壳（仪表盘一期 W2）。
 *
 * - grip/标题/角标（live=实时，presetTag=聚焦/脉冲归属提示）/宽度循环按钮；
 * - 编辑模式下才 draggable（原生 HTML5 DnD，拖拽事件由 DashboardGrid 容器代理）；
 * - 列宽经 CSS 变量 --span 喂给 grid-column，档位由 dashboardLayout.WIDTH_CYCLE 管理。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import { WIDGET_META, WidgetId } from '@/views/dashboard/components/dashboardLayout'

@Component({ name: 'DashWidget' })
export default class DashWidget extends Vue {
  @Prop({ required: true }) private widgetId!: WidgetId
  @Prop({ required: true }) private title!: string
  @Prop({ required: true }) private span!: number
  @Prop({ default: false }) private editing!: boolean
  @Prop({ default: false }) private dragging!: boolean

  private get meta() {
    return WIDGET_META[this.widgetId]
  }
}
</script>
