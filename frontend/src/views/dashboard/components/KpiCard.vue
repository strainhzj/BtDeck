<template>
  <div
    class="dash-kpi"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    :aria-label="ariaLabel"
    @click="clickable && $emit('click')"
    @keypress.enter="clickable && $emit('click')"
  >
    <div class="dash-kpi-label">
      <lucide-icon :icon="icon" />
      <span>{{ label }}</span>
    </div>
    <div class="dash-kpi-value mono">
      <slot name="value" />
    </div>
    <div class="dash-kpi-foot">
      <slot name="foot" />
    </div>
  </div>
</template>

<script lang="ts">
/**
 * KpiCard —— KPI 行卡片壳（仪表盘一期 W2，BitMatrix kpi-row 风格）。
 *
 * - 四张 KPI 恒显于网格外，不参与预设档位与编辑模式（与示意图行为一致）；
 * - label+icon 固定；大数值与脚注区交给具名 slot（活跃种子卡塞双芯片、
 *   系统速度卡塞双列数值均由调用方决定）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'

@Component({ name: 'KpiCard' })
export default class KpiCard extends Vue {
  @Prop({ required: true }) private label!: string
  @Prop({ required: true }) private icon!: string
  /** 可点击（跳转详情页）时挂 role=button 与键盘可达 */
  @Prop({ default: false }) private clickable!: boolean
  @Prop({ default: '' }) private ariaLabel!: string
}
</script>
