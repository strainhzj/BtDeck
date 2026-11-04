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
      <EChart
        :option="chartOption"
        :height="150"
        data-testid="traffic-chart"
      />
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
 * DailyTrafficCard —— 近 24h 流量分时 widget（仪表盘一期 W3，M-2 修正口径）。
 *
 * 数据源：/reports/speed/history?range=24h 分钟级 raw → trafficBinning
 * 小时分桶积分（滚动 24h 窗、每点 speed×60s）；文案统一「近 24h」
 * 不用「今日」。EChart 分时双柱（上传 info / 下载 primary）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import EChart from '@/components/charts/EChart.vue'
import { HourTrafficResult, formatTrafficBytes } from './trafficBinning'

@Component({ name: 'DailyTrafficCard', components: { EChart } })
export default class DailyTrafficCard extends Vue {
  @Prop({ default: false }) private ready!: boolean
  @Prop({ default: false }) private loading!: boolean
  @Prop({ default: null }) private result!: HourTrafficResult | null

  private get primaryColor(): string {
    return this.cssVar('--color-primary', '#059669')
  }

  private get infoColor(): string {
    return this.cssVar('--color-info', '#3B82F6')
  }

  private cssVar(name: string, fallback: string): string {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return v || fallback
  }

  private get rangeLabel(): string {
    const buckets = this.result?.buckets || []
    if (buckets.length === 0) return this.$t('dashboard.widgets.traffic.rangeEmpty').toString()
    return `${buckets[0].label} — ${buckets[buckets.length - 1].label}`
  }

  private get downloadTotal(): string {
    return formatTrafficBytes(this.result?.downloadTotalBytes || 0)
  }

  private get uploadTotal(): string {
    return formatTrafficBytes(this.result?.uploadTotalBytes || 0)
  }

  private get chartOption(): Record<string, unknown> | null {
    const buckets = this.result?.buckets || []
    if (!this.ready || buckets.length === 0) return null
    return {
      animation: false,
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => formatTrafficBytes(v || 0) },
      grid: { left: 8, right: 8, top: 10, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category',
        data: buckets.map(b => b.label),
        axisLabel: { interval: Math.max(0, Math.floor(buckets.length / 6) - 1), fontSize: 10 }
      },
      yAxis: { type: 'value', axisLabel: { formatter: (v: number) => formatTrafficBytes(v), fontSize: 10 } },
      series: [
        {
          name: this.$t('dashboard.widgets.traffic.upload').toString(),
          type: 'bar',
          stack: 'traffic',
          barWidth: '62%',
          data: buckets.map(b => Math.round(b.uploadBytes)),
          itemStyle: { color: this.infoColor, opacity: 0.85 }
        },
        {
          name: this.$t('dashboard.widgets.traffic.download').toString(),
          type: 'bar',
          stack: 'traffic',
          barWidth: '62%',
          data: buckets.map(b => Math.round(b.downloadBytes)),
          itemStyle: { color: this.primaryColor, borderRadius: [3, 3, 0, 0] }
        }
      ]
    }
  }
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
