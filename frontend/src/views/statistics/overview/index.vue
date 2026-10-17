<template>
  <div class="app-container statistics-page statistics-overview">
    <header class="statistics-page__header">
      <div>
        <h1 class="statistics-page__title">{{ $t('statistics.overview.title') }}</h1>
      </div>
      <el-button
        icon="el-icon-refresh"
        :loading="loading"
        @click="fetchOverview"
      >
        {{ $t('statistics.common.refresh') }}
      </el-button>
    </header>

    <template v-if="data">
      <!-- 数字卡行（A1） -->
      <div class="statistics-page__cards">
        <StatCard :label="$t('statistics.overview.totalTorrents')" :value="data.totals.count" />
        <StatCard :label="$t('statistics.overview.totalSize')" :value="formatFileSize(data.totals.sizeBytes)" />
        <StatCard :label="$t('statistics.overview.avgSize')" :value="formatFileSize(data.totals.avgSizeBytes)" />
        <StatCard :label="$t('statistics.overview.recycleBinSize')" :value="formatFileSize(data.totals.recycleBinSizeBytes)" />
      </div>

      <!-- 实时速度卡（30s 轮询，随 overview 端点刷新） -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.overview.liveSpeed') }}</h2>
        <div class="statistics-page__cards">
          <StatCard :label="$t('statistics.overview.downloadSpeed')" :value="formatSpeed(data.liveSpeed.totalDownloadSpeed)" />
          <StatCard :label="$t('statistics.overview.uploadSpeed')" :value="formatSpeed(data.liveSpeed.totalUploadSpeed)" />
          <div
            v-for="item in data.liveSpeed.items"
            :key="item.downloaderId"
            class="live-speed-item"
            :class="{'live-speed-item--offline': !item.online}"
          >
            <div class="live-speed-item__name">
              {{ item.nickname }}<template v-if="!item.online">（{{ $t('statistics.common.offline') }}）</template>
            </div>
            <div class="live-speed-item__speeds">
              ↓{{ formatSpeed(item.downloadSpeed) }} ↑{{ formatSpeed(item.uploadSpeed) }}
            </div>
          </div>
        </div>
      </section>

      <!-- A2 五桶饼图 -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.overview.statusDist') }}</h2>
        <EChart
          :option="statusOption"
          :height="300"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <!-- A1 体积最大 TOP10 -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.overview.largest') }}</h2>
        <EChart
          :option="largestOption"
          :height="largestHeight"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <!-- A3 分类与标签（数量 + 体积双维度切换） -->
      <section class="statistics-panel">
        <div class="statistics-panel__head">
          <h2 class="statistics-panel__title">{{ $t('statistics.overview.categories') }} / {{ $t('statistics.overview.tags') }}</h2>
          <el-radio-group
            v-model="dimension"
            size="mini"
          >
            <el-radio-button label="count">{{ $t('statistics.common.byCount') }}</el-radio-button>
            <el-radio-button label="size">{{ $t('statistics.common.bySize') }}</el-radio-button>
          </el-radio-group>
        </div>
        <EChart
          :option="categoriesOption"
          :height="300"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
        <EChart
          :option="tagsOption"
          :height="300"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <!-- A4 目录占用排行 -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.overview.paths') }}</h2>
        <EChart
          :option="pathsOption"
          :height="300"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <!-- A5 下载器对比（堆叠柱） -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.overview.downloaders') }}</h2>
        <EChart
          :option="downloadersOption"
          :height="300"
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
 * 报表·总览页（A1-A5 + 实时速度，statistics-reports W5）。
 *
 * - 30s 轮询刷新（照 dashboard/index.vue 惯例），beforeDestroy 清理定时器；
 * - A3 双维度切换（数量/体积）经 watch dimension 重建 option；
 * - 图表 option 由数据派生（空数据 → null → EChart 空态）。
 */
import { Component, Vue } from 'vue-property-decorator'
import EChart from '@/components/charts/EChart.vue'
import { formatFileSize, formatSpeed } from '@/utils/formatters'
import { getReportsOverview } from '@/api/reports'
import { ReportsOverviewData } from '@/types/reports'
import CaliberNotes from '../components/CaliberNotes.vue'
import StatCard from '../components/StatCard.vue'

const BUCKET_COLORS: Record<string, string> = {
  error: '#F56C6C',
  downloading: '#409EFF',
  seeding: '#67C23A',
  paused: '#E6A23C',
  other: '#909399'
}

const BUCKET_ORDER = ['error', 'downloading', 'seeding', 'paused', 'other']

@Component({ name: 'StatisticsOverview', components: { StatCard, CaliberNotes, EChart } })
export default class StatisticsOverview extends Vue {
  private data: ReportsOverviewData | null = null
  private loading = false
  private dimension: 'count' | 'size' = 'count'
  private refreshTimer: number | null = null

  mounted() {
    this.fetchOverview()
    this.startAutoRefresh()
  }

  beforeDestroy() {
    this.stopAutoRefresh()
  }

  private async fetchOverview(): Promise<void> {
    this.loading = true
    try {
      const res = await getReportsOverview()
      if (res.code === '200' && res.data) {
        this.data = res.data
      }
    } catch {
      this.$message.error(this.$t('statistics.common.loadFailed').toString())
    } finally {
      this.loading = false
    }
  }

  private startAutoRefresh() {
    this.refreshTimer = window.setInterval(() => {
      this.fetchOverview()
    }, 30000)
  }

  private stopAutoRefresh() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer)
      this.refreshTimer = null
    }
  }

  private get largestHeight(): number {
    return Math.max(220, (this.data?.largest.length ?? 0) * 28 + 60)
  }

  /** 五桶 i18n 名（饼图 legend/tooltip） */
  private bucketLabel(bucket: string): string {
    return this.$t(`statistics.overview.buckets.${bucket}`).toString()
  }

  private get statusOption(): Record<string, unknown> | null {
    const dist = this.data?.statusDist ?? []
    if (!dist.length) return null
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [
        {
          type: 'pie',
          radius: ['35%', '65%'],
          data: dist.map((d) => ({
            name: this.bucketLabel(d.bucket),
            value: d.count,
            itemStyle: { color: BUCKET_COLORS[d.bucket] }
          })),
          label: { formatter: '{b}: {c}' }
        }
      ]
    }
  }

  private get largestOption(): Record<string, unknown> | null {
    const rows = this.data?.largest ?? []
    if (!rows.length) return null
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 8, right: 40, containLabel: true },
      xAxis: { type: 'value' },
      yAxis: {
        type: 'category',
        inverse: true,
        data: rows.map((r) => r.name),
        axisLabel: { width: 260, overflow: 'truncate' }
      },
      series: [
        {
          type: 'bar',
          data: rows.map((r) => r.sizeBytes),
          label: { show: true, position: 'right', formatter: (p: { dataIndex: number }) => formatFileSize(rows[p.dataIndex].sizeBytes) }
        }
      ]
    }
  }

  private get categoriesOption(): Record<string, unknown> | null {
    const rows = (this.data?.categories ?? []).map((r) => ({
      name: r.name || this.$t('statistics.overview.uncategorized').toString(),
      count: r.count,
      sizeBytes: r.sizeBytes
    }))
    if (!rows.length) return null
    return this.buildDimensionBar(rows)
  }

  private get tagsOption(): Record<string, unknown> | null {
    const rows = this.data?.tags ?? []
    if (!rows.length) return null
    return this.buildDimensionBar(rows)
  }

  private buildDimensionBar(rows: Array<{ name: string, count: number, sizeBytes: number }>): Record<string, unknown> {
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 8, right: 20, containLabel: true },
      xAxis: { type: 'category', data: rows.map((r) => r.name), axisLabel: { interval: 0, rotate: rows.length > 6 ? 30 : 0 } },
      yAxis: { type: 'value' },
      series: [
        {
          type: 'bar',
          data: this.dimension === 'count' ? rows.map((r) => r.count) : rows.map((r) => r.sizeBytes)
        }
      ]
    }
  }

  private get pathsOption(): Record<string, unknown> | null {
    const rows = this.data?.paths ?? []
    if (!rows.length) return null
    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (v: number) => formatFileSize(v)
      },
      grid: { left: 8, right: 40, containLabel: true },
      xAxis: { type: 'value', axisLabel: { formatter: (v: number) => formatFileSize(v) } },
      yAxis: { type: 'category', inverse: true, data: rows.map((r) => r.path) },
      series: [{ type: 'bar', data: rows.map((r) => r.sizeBytes) }]
    }
  }

  private get downloadersOption(): Record<string, unknown> | null {
    const rows = this.data?.downloaders ?? []
    if (!rows.length) return null
    const names = rows.map((r) => (r.removed ? `${r.nickname}（${this.$t('statistics.overview.removedDownloader')}）` : r.nickname))
    const distBy = (bucket: string): number[] =>
      rows.map((r) => r.statusDist.find((d) => d.bucket === bucket)?.count ?? 0)
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { bottom: 0 },
      grid: { left: 8, right: 20, containLabel: true },
      xAxis: { type: 'category', data: names },
      yAxis: { type: 'value' },
      series: BUCKET_ORDER.map((bucket) => ({
        name: this.bucketLabel(bucket),
        type: 'bar',
        stack: 'total',
        itemStyle: { color: BUCKET_COLORS[bucket] },
        data: distBy(bucket)
      }))
    }
  }

  private get caliberNotes(): Array<string> {
    return [
      'statistics.calibers.fileFirst',
      'statistics.calibers.statusByTorrent',
      'statistics.calibers.recycleExcluded',
      'statistics.calibers.trUncategorized'
    ]
  }

  private formatFileSize = formatFileSize
  private formatSpeed = formatSpeed
}
</script>

<style scoped>
@import '@/styles/statistics-page.scss';
</style>
