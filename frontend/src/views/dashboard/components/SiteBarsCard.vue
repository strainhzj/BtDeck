<template>
  <div>
    <EChart
      v-if="buckets.length > 0"
      :option="chartOption"
      :height="chartHeight"
      data-testid="site-bars"
    />
    <div
      v-else
      class="dash-empty"
    >
      <lucide-icon name="globe" />
      <span>{{ $t('dashboard.widgets.sites.empty') }}</span>
    </div>
    <div class="dash-muted sites-note">
      {{ $t('dashboard.widgets.sites.note') }}
    </div>
  </div>
</template>

<script lang="ts">
/**
 * SiteBarsCard —— Tracker 站点分布横向条形 widget（仪表盘一期 W3）。
 *
 * 数据源：W1 torrents.siteBuckets（tracker_host 去端口归一、按种子去重
 * 计数、TopN + other，5min 独立节流）。显示名直接用 host（站点别名映射
 * 不在一期范围——计划 v2 M-4 口径）。EChart 横向条形 + 渐变填充。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import EChart from '@/components/charts/EChart.vue'
import { SiteBucket } from '@/types/dashboard'

@Component({ name: 'SiteBarsCard', components: { EChart } })
export default class SiteBarsCard extends Vue {
  @Prop({ required: true }) private buckets!: SiteBucket[]

  private get chartHeight(): number {
    return Math.max(120, this.buckets.length * 32 + 24)
  }

  private get displayNames(): string[] {
    return this.buckets.map(b => (b.host === 'other' ? this.$t('dashboard.widgets.sites.other').toString() : b.host))
  }

  private get chartOption(): Record<string, unknown> | null {
    if (this.buckets.length === 0) return null
    return {
      animation: false,
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 8, right: 34, top: 6, bottom: 4, containLabel: true },
      xAxis: { type: 'value', splitLine: { show: false }, axisLabel: { show: false }, axisTick: { show: false }, axisLine: { show: false } },
      yAxis: {
        type: 'category',
        inverse: true,
        data: this.displayNames,
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { fontSize: 11, color: 'var(--color-text-secondary)' }
      },
      series: [
        {
          type: 'bar',
          barWidth: 8,
          data: this.buckets.map((b, i) => ({
            value: b.count,
            itemStyle: {
              borderRadius: 4,
              color: b.host === 'other'
                ? {
                    type: 'linear',
                    x: 0, y: 0, x2: 1, y2: 0,
                    colorStops: [
                      { offset: 0, color: this.cssVar('--color-info', '#3B82F6') },
                      { offset: 1, color: this.cssVar('--color-primary-lighter', '#34D399') }
                    ]
                  }
                : {
                    type: 'linear',
                    x: 0, y: 0, x2: 1, y2: 0,
                    colorStops: [
                      { offset: 0, color: this.cssVar('--color-primary', '#059669') },
                      { offset: 1, color: this.cssVar('--color-primary-lighter', '#34D399') }
                    ]
                  }
            },
            label: { show: true, position: 'right', fontSize: 11, formatter: () => String(b.count) }
          })),
          name: this.$t('dashboard.widgets.sites.countLabel').toString()
        }
      ]
    }
  }

  private cssVar(name: string, fallback: string): string {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return v || fallback
  }
}
</script>

<style lang="scss" scoped>
.sites-note {
  font-size: 11.5px;
  margin-top: 8px;
}
</style>
