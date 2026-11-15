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
      <lucide-icon :name="icon" />
      <span>{{ label }}</span>
    </div>
    <div class="dash-kpi-value mono">
      <slot name="value" />
    </div>
    <div class="dash-kpi-foot">
      <slot name="foot" />
    </div>
    <slot />
  </div>
</template>

<script lang="ts">
/**
 * KpiCard —— KPI 行卡片壳（仪表盘一期 W2，BitMatrix kpi-row 风格）。
 *
 * - 四张 KPI 恒显于网格外，不参与预设档位与编辑模式（与示意图行为一致）；
 * - label+icon 固定；大数值与脚注区交给具名 slot（活跃种子卡塞双芯片、
 *   系统速度卡塞双列数值均由调用方决定）；
 * - 默认 slot 渲染于 foot 之后（2026-11-13 评审修复：此前无出口致系统速度卡
 *   双列数值被静默丢弃，桌面/移动双端修复）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'

@Component({ name: 'KpiCard' })
export default class KpiCard extends Vue {
  @Prop({ required: true }) private label!: string
  @Prop({ required: true }) private icon!: string
  /** 可点击（跳转详情页）时挂 role=button 与键盘可达；Boolean 显式声明使裸属性形态（空串）正确转换 */
  @Prop({ type: Boolean, default: false }) private clickable!: boolean
  @Prop({ default: '' }) private ariaLabel!: string
}
</script>
