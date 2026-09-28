<template>
  <div class="app-container statistics-page statistics-trackers">
    <header class="statistics-page__header">
      <h1 class="statistics-page__title">{{ $t('statistics.trackers.title') }}</h1>
      <el-button
        icon="el-icon-refresh"
        :loading="loading"
        @click="fetchTrackers"
      >
        {{ $t('statistics.common.refresh') }}
      </el-button>
    </header>

    <template v-if="data">
      <!-- D14 站点构成（体积） -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.trackers.sites') }}</h2>
        <EChart
          :option="sitesOption"
          :height="Math.max(260, data.sites.length * 26 + 80)"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <!-- D15 站点健康榜（表 + 进度条；errorRate 分母排除 unknown） -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.trackers.health') }}</h2>
        <el-table
          v-if="data.health.length"
          :data="data.health"
          size="mini"
          max-height="420"
        >
          <el-table-column
            prop="host"
            label="Tracker"
            min-width="220"
            show-overflow-tooltip
          />
          <el-table-column
            :label="$t('statistics.trackers.errorRate')"
            width="220"
          >
            <template slot-scope="{row}">
              <el-progress
                :percentage="errorRatePercent(row.errorRate)"
                :color="errorRateColor(row.errorRate)"
                :stroke-width="12"
              />
            </template>
          </el-table-column>
          <el-table-column
            :label="$t('statistics.trackers.affectedCount')"
            width="120"
          >
            <template slot-scope="{row}">{{ row.affectedCount }}</template>
          </el-table-column>
        </el-table>
        <div
          v-else
          class="statistics-page__loading"
        >{{ $t('statistics.common.chartEmpty') }}</div>
      </section>

      <!-- D16 站点冷热（散点 + 表；均值排除 NULL、count=有效行数） -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.trackers.supplyDemand') }}</h2>
        <EChart
          :option="supplyOption"
          :height="320"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
        <el-table
          v-if="data.supplyDemand.length"
          :data="data.supplyDemand"
          size="mini"
          max-height="420"
        >
          <el-table-column
            prop="host"
            label="Tracker"
            min-width="220"
            show-overflow-tooltip
          />
          <el-table-column
            prop="avgSeeders"
            :label="$t('statistics.trackers.avgSeeders')"
            width="110"
          />
          <el-table-column
            prop="avgLeechers"
            :label="$t('statistics.trackers.avgLeechers')"
            width="110"
          />
          <el-table-column
            prop="avgDownloads"
            :label="$t('statistics.trackers.avgDownloads')"
            width="110"
          />
          <el-table-column
            prop="count"
            :label="$t('statistics.trackers.validRows')"
            width="100"
          />
        </el-table>
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
 * 报表·Tracker 页（D14/D15/D16，statistics-reports W5）。
 *
 * - D14 站点构成条形（体积；host 已去端口归一）；
 * - D15 健康榜：errorRate（分母排除 unknown）进度条 + 受影响种子数；
 * - D16 冷热：avgSeeders × avgLeechers 散点 + 表（均值排除 NULL 行）。
 */
import { Component, Vue } from 'vue-property-decorator'
import EChart from '@/components/charts/EChart.vue'
import { formatFileSize } from '@/utils/formatters'
import { getReportsTrackers } from '@/api/reports'
import { ReportsTrackersData } from '@/types/reports'
import CaliberNotes from '../components/CaliberNotes.vue'

@Component({ name: 'StatisticsTrackers', components: { CaliberNotes, EChart } })
export default class StatisticsTrackers extends Vue {
  private data: ReportsTrackersData | null = null
  private loading = false

  mounted() {
    this.fetchTrackers()
  }

  private async fetchTrackers(): Promise<void> {
    this.loading = true
    try {
      const res = await getReportsTrackers()
      if (res.code === '200' && res.data) {
        this.data = res.data
      }
    } catch {
      this.$message.error(this.$t('statistics.common.loadFailed').toString())
    } finally {
      this.loading = false
    }
  }

  private get sitesOption(): Record<string, unknown> | null {
    const rows = this.data?.sites ?? []
    if (!rows.length) return null
    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (v: number) => formatFileSize(v)
      },
      grid: { left: 8, right: 40, containLabel: true },
      xAxis: { type: 'value', axisLabel: { formatter: (v: number) => formatFileSize(v) } },
      yAxis: {
        type: 'category',
        inverse: true,
        data: rows.map((r) => r.host),
        axisLabel: { width: 200, overflow: 'truncate' }
      },
      series: [{ type: 'bar', data: rows.map((r) => r.sizeBytes) }]
    }
  }

  private get supplyOption(): Record<string, unknown> | null {
    const rows = this.data?.supplyDemand ?? []
    if (!rows.length) return null
    return {
      tooltip: {
        trigger: 'item',
        formatter: (p: { data: [number, number, string] }) =>
          `${p.data[2]}<br/>${this.$t('statistics.trackers.avgSeeders')}: ${p.data[0]}<br/>${this.$t('statistics.trackers.avgLeechers')}: ${p.data[1]}`
      },
      grid: { left: 8, right: 20, containLabel: true },
      xAxis: { type: 'value', name: this.$t('statistics.trackers.avgSeeders').toString() },
      yAxis: { type: 'value', name: this.$t('statistics.trackers.avgLeechers').toString() },
      series: [
        {
          type: 'scatter',
          symbolSize: 10,
          data: rows.map((r) => [round2(r.avgSeeders), round2(r.avgLeechers), r.host] as [number, number, string])
        }
      ]
    }
  }

  private errorRatePercent(rate: number): number {
    return Math.round(Math.min(1, Math.max(0, rate)) * 1000) / 10
  }

  private errorRateColor(rate: number): string {
    if (rate >= 0.5) return '#F56C6C'
    if (rate >= 0.2) return '#E6A23C'
    return '#67C23A'
  }

  private get caliberNotes(): Array<string> {
    return ['statistics.calibers.crossSiteSize', 'statistics.calibers.trackerCountStart']
  }
}

function round2(v: number): number {
  return Math.round(v * 100) / 100
}
</script>

<style scoped>
@import '@/styles/statistics-page.scss';
</style>
