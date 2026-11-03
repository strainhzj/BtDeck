<template>
  <div>
    <div
      v-if="!ready"
      class="dash-empty"
      data-testid="traffic-empty"
    >
      <lucide-icon icon="bar-chart-3" />
      <span>{{ loading ? $t('dashboard.widgets.traffic.loading') : $t('dashboard.widgets.traffic.empty') }}</span>
    </div>
    <template v-else>
      <slot />
      <div class="dash-kpi-foot traffic-foot">
        <span class="dash-muted traffic-range">{{ rangeLabel }}</span>
        <span class="traffic-sum">
          ↑ <b class="mono">{{ uploadTotal }}</b>
          &nbsp;&nbsp;↓ <b class="mono">{{ downloadTotal }}</b>
        </span>
      </div>
    </template>
  </div>
</template>

<script lang="ts">
/**
 * DailyTrafficCard —— 今日流量分时 widget 壳（仪表盘一期 W2；柱状图 W3 接
 * /reports/speed/history?range=24h 分钟级 raw + 小时分桶积分）。
 *
 * 文案口径（计划 v2 M-2）：滚动 24h 窗口，用「近 24h」不用「今日」。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'

@Component({ name: 'DailyTrafficCard' })
export default class DailyTrafficCard extends Vue {
  @Prop({ default: false }) private ready!: boolean
  @Prop({ default: false }) private loading!: boolean
  @Prop({ default: '' }) private rangeLabel!: string
  @Prop({ default: '0 B' }) private uploadTotal!: string
  @Prop({ default: '0 B' }) private downloadTotal!: string
}
</script>

<style lang="scss" scoped>
.traffic-foot {
  margin-top: 10px;
}

.traffic-range {
  font-size: 12px;
}

.traffic-sum {
  font-size: 12.5px;
}
</style>
