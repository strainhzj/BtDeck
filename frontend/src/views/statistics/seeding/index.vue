<template>
  <div class="app-container statistics-page statistics-seeding">
    <header class="statistics-page__header">
      <h1 class="statistics-page__title">{{ $t('statistics.seeding.title') }}</h1>
      <el-button
        icon="el-icon-refresh"
        :loading="loading"
        @click="fetchSeeding"
      >
        {{ $t('statistics.common.refresh') }}
      </el-button>
    </header>

    <template v-if="data">
      <!-- C10 分享率分布直方图（双口径：按种子 / 按文件合计） -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">
          {{ $t('statistics.seeding.ratioDist') }}
          <el-radio-group
            v-model="ratioCaliber"
            size="mini"
            class="statistics-panel__meta"
          >
            <el-radio-button label="torrent">{{ $t('statistics.seeding.byTorrent') }}</el-radio-button>
            <el-radio-button label="file">{{ $t('statistics.seeding.byFile') }}</el-radio-button>
          </el-radio-group>
          <span class="statistics-panel__meta">
            {{ $t('statistics.seeding.ratioNullCount') }}: {{ currentRatioNullCount }}
          </span>
        </h2>
        <EChart
          :option="ratioOption"
          :height="280"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
      </section>

      <!-- C11 摸鱼象限：散点 + 表 -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.seeding.slackers') }}</h2>
        <EChart
          :option="slackersOption"
          :height="300"
          :empty-text="$t('statistics.common.chartEmpty')"
        />
        <el-table
          v-if="data.slackers.length"
          :data="data.slackers"
          size="mini"
          max-height="360"
        >
          <el-table-column
            prop="name"
            :label="$t('statistics.common.name')"
            min-width="260"
            show-overflow-tooltip
          />
          <el-table-column :label="$t('statistics.common.sizeBytes')" width="120">
            <template slot-scope="{row}">{{ formatFileSize(row.sizeBytes) }}</template>
          </el-table-column>
          <el-table-column
            prop="ratio"
            :label="$t('statistics.seeding.ratio')"
            width="100"
          />
        </el-table>
      </section>

      <!-- C12 辅种网络：卡 + 条 -->
      <section class="statistics-panel">
        <h2 class="statistics-panel__title">{{ $t('statistics.seeding.auxiliary') }}</h2>
        <div class="statistics-page__cards">
          <StatCard :label="$t('statistics.common.torrentCount')" :value="data.auxiliary.totalTorrents" />
          <StatCard :label="$t('statistics.seeding.crossSeedRate')" :value="crossSeedRatePercent" />
        </div>
        <EChart
          :option="auxiliaryOption"
          :height="280"
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
 * 报表·做种页（C10/C11/C12，statistics-reports W5）。
 *
 * - C10 ratio 半开区间直方图 + NULL 计数（TR 做种态添加种子恒 NULL——脚注）；
 * - C11 摸鱼象限：x=体积 y=分享率 散点 + TOP20 表（体积降序）；
 * - C12 辅种率 + TOP10 辅种种子条形。
 */
import { Component, Vue } from 'vue-property-decorator'
import EChart from '@/components/charts/EChart.vue'
import { formatFileSize } from '@/utils/formatters'
import { getReportsSeeding } from '@/api/reports'
import { RatioBucketItem, ReportsSeedingData } from '@/types/reports'
import CaliberNotes from '../components/CaliberNotes.vue'
import StatCard from '../components/StatCard.vue'

@Component({ name: 'StatisticsSeeding', components: { StatCard, CaliberNotes, EChart } })
export default class StatisticsSeeding extends Vue {
  private data: ReportsSeedingData | null = null
  private loading = false
  /** C10 双口径切换：torrent=实际种子各副本各自计；file=同 name+size 组内 Σratio */
  private ratioCaliber: 'torrent' | 'file' = 'torrent'

  mounted() {
    this.fetchSeeding()
  }

  private async fetchSeeding(): Promise<void> {
    this.loading = true
    try {
      const res = await getReportsSeeding()
      if (res.code === '200' && res.data) {
        this.data = res.data
      }
    } catch {
      this.$message.error(this.$t('statistics.common.loadFailed').toString())
    } finally {
      this.loading = false
    }
  }

  private get crossSeedRatePercent(): string {
    const rate = this.data?.auxiliary.crossSeedRate ?? 0
    return `${(rate * 100).toFixed(1)}%`
  }

  private get currentRatioRows(): RatioBucketItem[] {
    if (!this.data) return []
    return this.ratioCaliber === 'file' ? this.data.ratioBucketsByFile : this.data.ratioBuckets
  }

  private get currentRatioNullCount(): number {
    if (!this.data) return 0
    return this.ratioCaliber === 'file' ? this.data.ratioNullCountByFile : this.data.ratioNullCount
  }

  private get ratioOption(): Record<string, unknown> | null {
    const rows = this.currentRatioRows
    if (!rows.some((r) => r.count > 0)) return null
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 8, right: 20, containLabel: true },
      xAxis: { type: 'category', data: rows.map((r) => r.bucket) },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: rows.map((r) => r.count) }]
    }
  }

  private get slackersOption(): Record<string, unknown> | null {
    const rows = this.data?.slackers ?? []
    if (!rows.length) return null
    return {
      tooltip: {
        trigger: 'item',
        formatter: (p: { data: [number, number, string] }) =>
          `${p.data[2]}<br/>${this.$t('statistics.common.sizeBytes')}: ${formatFileSize(p.data[0])}<br/>${this.$t('statistics.seeding.ratio')}: ${p.data[1]}`
      },
      grid: { left: 8, right: 20, containLabel: true },
      xAxis: {
        type: 'value',
        name: this.$t('statistics.common.sizeBytes').toString(),
        axisLabel: { formatter: (v: number) => formatFileSize(v) }
      },
      yAxis: { type: 'value', name: this.$t('statistics.seeding.ratio').toString(), scale: true },
      series: [
        {
          type: 'scatter',
          symbolSize: 10,
          data: rows.map((r) => [r.sizeBytes, r.ratio, r.name] as [number, number, string])
        }
      ]
    }
  }

  private get auxiliaryOption(): Record<string, unknown> | null {
    const rows = this.data?.auxiliary.top10 ?? []
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
          data: rows.map((r) => r.auxiliarySeedCount),
          label: { show: true, position: 'right' }
        }
      ]
    }
  }

  private get caliberNotes(): Array<string> {
    return [
      'statistics.calibers.fileFirst',
      'statistics.calibers.ratioDual',
      'statistics.calibers.ratioNullNote'
    ]
  }

  private formatFileSize = formatFileSize
}
</script>

<style scoped>
@import '@/styles/statistics-page.scss';

.statistics-panel__meta {
  margin-left: 12px;
  font-size: 12px;
  font-weight: 400;
  color: var(--app-text-secondary, #909399);
}
</style>
