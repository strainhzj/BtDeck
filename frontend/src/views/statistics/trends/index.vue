<template>
  <div class="app-container statistics-page statistics-trends">
    <header class="statistics-page__header">
      <h1 class="statistics-page__title">{{ $t('statistics.trends.title') }}</h1>
      <el-radio-group
        v-model="period"
        size="small"
        @change="fetchTrends"
      >
        <el-radio-button label="month">{{ $t('statistics.common.periodMonth') }}</el-radio-button>
        <el-radio-button label="week">{{ $t('statistics.common.periodWeek') }}</el-radio-button>
      </el-radio-group>
    </header>

    <template v-if="data">
      <!-- B6 新增趋势：柱（数量）+ 折线（体积，右轴） -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.trends.addedTrend') }}</h2>
        <EChart
          :option="addedOption"
          :height="320"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <!-- B7 完成趋势 -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.trends.completedTrend') }}</h2>
        <EChart
          :option="completedOption"
          :height="260"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <!-- B8 库龄结构（环形） -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.trends.ageStructure') }}</h2>
        <EChart
          :option="ageOption"
          :height="300"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <!-- B9 速度历史（range 切换 + 多系列折线） -->
      <section class="statistics-panel">
        <div class="statistics-panel__head">
          <h2 class="statistics-panel__title">{{ $t('statistics.trends.speedHistory') }}</h2>
          <el-radio-group
            v-model="speedRange"
            size="small"
            @change="fetchSpeed"
          >
            <el-radio-button label="24h">{{ $t('statistics.common.range24h') }}</el-radio-button>
            <el-radio-button label="7d">{{ $t('statistics.common.range7d') }}</el-radio-button>
            <el-radio-button label="30d">{{ $t('statistics.common.range30d') }}</el-radio-button>
          </el-radio-group>
        </div>
        <EChart
          :option="speedOption"
          :height="360"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <CaliberNotes :notes="caliberNotes" />
    </template>

    <div
      v-else
      class="statistics-page__loading"
    >
      <i
        v-if="loading"
        class="el-icon-loading"
      />
      <span v-else>{{ $t('statistics.common.chartEmpty') }}</span>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * 报表·趋势页（B6/B7/B8 + B9 速度历史，statistics-reports W5）。
 *
 * - period（month/week）切换重新拉取趋势；
 * - B9 range（24h/7d/30d）独立切换：24h 纯 raw 分钟级、更长窗口 hourly 主体
 *   + raw 尾段（后端拼接语义）；断点 = 停机时段无样本（connectNulls 不补零）；
 * - 库龄"未知"桶与时间 NULL 过滤口径见 CaliberNotes。
 */
import { Component, Vue, Watch } from 'vue-property-decorator'
import EChart from '@/components/charts/EChart.vue'
import { formatFileSize, formatSpeed } from '@/utils/formatters'
import { getReportsSpeedHistory, getReportsTrends, SpeedRange, TrendsPeriod } from '@/api/reports'
import { ReportsTrendsData, SpeedHistory } from '@/types/reports'
import CaliberNotes from '../components/CaliberNotes.vue'

const AGE_COLORS: Record<string, string> = {
  under7d: '#409EFF',
  to30d: '#67C23A',
  to90d: '#E6A23C',
  to180d: '#F56C6C',
  to1y: '#9B59B6',
  over1y: '#34495E',
  unknown: '#909399'
}

@Component({ name: 'StatisticsTrends', components: { CaliberNotes, EChart } })
export default class StatisticsTrends extends Vue {
  private data: ReportsTrendsData | null = null
  private speed: SpeedHistory | null = null
  private loading = false
  private period: TrendsPeriod = 'month'
  private speedRange: SpeedRange = '24h'

  mounted() {
    this.fetchTrends()
    this.fetchSpeed()
  }

  private async fetchTrends(): Promise<void> {
    this.loading = true
    try {
      const res = await getReportsTrends(this.period, 12)
      if (res.code === '200' && res.data) {
        this.data = res.data
      }
    } catch {
      this.$message.error(this.$t('statistics.common.loadFailed').toString())
    } finally {
      this.loading = false
    }
  }

  private async fetchSpeed(): Promise<void> {
    try {
      const res = await getReportsSpeedHistory(this.speedRange)
      if (res.code === '200' && res.data) {
        this.speed = res.data
      }
    } catch {
      this.$message.error(this.$t('statistics.common.loadFailed').toString())
    }
  }

  @Watch('period')
  onPeriodChanged() {
    this.fetchTrends()
  }

  @Watch('speedRange')
  onSpeedRangeChanged() {
    this.fetchSpeed()
  }

  private buildTimeBar(rows: Array<{ key: string, count: number, sizeBytes: number }>): Record<string, unknown> {
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 8, right: 8, containLabel: true },
      xAxis: { type: 'category', data: rows.map((r) => r.key) },
      yAxis: [
        { type: 'value', name: this.$t('statistics.common.torrentCount').toString() },
        { type: 'value', name: this.$t('statistics.common.sizeBytes').toString(), axisLabel: { formatter: (v: number) => formatFileSize(v) } }
      ],
      series: [
        { name: this.$t('statistics.common.torrentCount').toString(), type: 'bar', data: rows.map((r) => r.count) },
        {
          name: this.$t('statistics.common.sizeBytes').toString(),
          type: 'line',
          yAxisIndex: 1,
          data: rows.map((r) => r.sizeBytes)
        }
      ]
    }
  }

  private get addedOption(): Record<string, unknown> | null {
    const rows = this.data?.added ?? []
    if (!rows.length) return null
    return this.buildTimeBar(rows)
  }

  private get completedOption(): Record<string, unknown> | null {
    const rows = this.data?.completed ?? []
    if (!rows.length) return null
    return this.buildTimeBar(rows)
  }

  private get ageOption(): Record<string, unknown> | null {
    const rows = this.data?.ageBuckets ?? []
    const visible = rows.filter((r) => r.count > 0)
    if (!visible.length) return null
    return {
      tooltip: {
        trigger: 'item',
        valueFormatter: (v: number) => formatFileSize(v)
      },
      legend: { bottom: 0 },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          data: visible.map((r) => ({
            name: this.$t(`statistics.trends.ageBuckets.${r.name}`).toString(),
            value: r.sizeBytes,
            itemStyle: { color: AGE_COLORS[r.name] }
          }))
        }
      ]
    }
  }

  /** B9 多系列：每下载器上/下行两条折线；断点（停机无样本）不补零 */
  private get speedOption(): Record<string, unknown> | null {
    const series = this.speed?.series ?? []
    if (!series.length) return null
    const down: Array<Record<string, unknown>> = []
    const up: Array<Record<string, unknown>> = []
    series.forEach((s) => {
      down.push({
        name: `${s.nickname} ↓`,
        type: 'line',
        showSymbol: false,
        connectNulls: false,
        data: s.points.map((p) => [p.ts, p.downloadSpeed]),
        tooltip: { valueFormatter: (v: number) => formatSpeed(v) }
      })
      up.push({
        name: `${s.nickname} ↑`,
        type: 'line',
        showSymbol: false,
        connectNulls: false,
        data: s.points.map((p) => [p.ts, p.uploadSpeed]),
        tooltip: { valueFormatter: (v: number) => formatSpeed(v) }
      })
    })
    return {
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, type: 'scroll' },
      grid: { left: 8, right: 16, containLabel: true },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', axisLabel: { formatter: (v: number) => formatSpeed(v) } },
      series: [...down, ...up]
    }
  }

  private get caliberNotes(): Array<string | { key: string, params: Record<string, unknown> }> {
    const notes: Array<string | { key: string, params: Record<string, unknown> }> = [
      'statistics.calibers.completedNullNote',
      'statistics.calibers.speedBreak',
      'statistics.calibers.onlineRatio',
      'statistics.calibers.timezone'
    ]
    const first = this.speed?.firstSampleAt
    if (first) {
      notes.unshift({ key: 'statistics.calibers.samplingStart', params: { time: first } })
    }
    return notes
  }
}
</script>

<style scoped>
@import '@/styles/statistics-page.scss';
</style>
