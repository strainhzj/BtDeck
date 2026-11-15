<template>
  <div>
    <div
      v-if="!ready"
      class="dash-empty"
      data-testid="spark-empty"
    >
      <lucide-icon name="activity" />
      <span>{{ $t('dashboard.widgets.spark.sampling') }}</span>
    </div>
    <template v-else>
      <EChart
        :option="chartOption"
        :height="170"
        data-testid="spark-chart"
      />
      <div class="dash-legend spark-legend">
        <span class="item">
          <span
            class="sw"
            :style="{background: primaryColor}"
          />
          {{ $t('dashboard.downloadSpeed') }}
        </span>
        <span class="item">
          <span
            class="sw"
            :style="{background: infoColor}"
          />
          {{ $t('dashboard.uploadSpeed') }}
        </span>
        <span class="dash-muted sample-note">{{ $t('dashboard.widgets.spark.note') }}</span>
      </div>
    </template>
  </div>
</template>

<script lang="ts">
/**
 * SpeedSparkCard —— 速度曲线 widget（仪表盘一期 W3）。
 *
 * 数据源：active-torrents 3s 采样累积 60 点（父级滚动窗数组）。
 * EChart 深路径双线渐变面积（复用 EChart.vue 封装，echarts chunk 与报表
 * 页共用，不新增包体）；颜色取 --color-primary/--color-info 计算值（canvas
 * 不解析 CSS 变量，随 3s 数据更新自然刷新主题色）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import EChart from '@/components/charts/EChart.vue'
import { formatSpeed } from '@/utils/formatters'

export interface SpeedSample {
  t: number
  dl: number
  ul: number
}

@Component({ name: 'SpeedSparkCard', components: { EChart } })
export default class SpeedSparkCard extends Vue {
  @Prop({ required: true }) private samples!: SpeedSample[]
  /** 采样未满时显示采样中空态 */
  @Prop({ default: false }) private ready!: boolean

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

  private get chartOption(): Record<string, unknown> | null {
    if (!this.ready) return null
    const gradient = (base: string) => ({
      type: 'linear',
      x: 0,
      y: 0,
      x2: 0,
      y2: 1,
      colorStops: [
        { offset: 0, color: `${base}33` },
        { offset: 1, color: `${base}05` }
      ]
    })
    return {
      animation: false,
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => formatSpeed(v || 0) },
      grid: { left: 8, right: 12, top: 10, bottom: 4, containLabel: true },
      xAxis: { type: 'time', splitLine: { show: false }, axisLabel: { show: false } },
      yAxis: { type: 'value', axisLabel: { formatter: (v: number) => formatSpeed(v) }, splitNumber: 3 },
      series: [
        {
          name: this.$t('dashboard.downloadSpeed').toString(),
          type: 'line',
          showSymbol: false,
          smooth: true,
          data: this.samples.map(s => [s.t, s.dl]),
          lineStyle: { width: 2, color: this.primaryColor },
          itemStyle: { color: this.primaryColor },
          areaStyle: { color: gradient(this.primaryColor) }
        },
        {
          name: this.$t('dashboard.uploadSpeed').toString(),
          type: 'line',
          showSymbol: false,
          smooth: true,
          data: this.samples.map(s => [s.t, s.ul]),
          lineStyle: { width: 2, color: this.infoColor },
          itemStyle: { color: this.infoColor },
          areaStyle: { color: gradient(this.infoColor) }
        }
      ]
    }
  }
}
</script>

<style lang="scss" scoped>
.spark-legend {
  margin-top: 8px;
}

.sample-note {
  margin-left: auto;
  font-size: 11.5px;
}
</style>
