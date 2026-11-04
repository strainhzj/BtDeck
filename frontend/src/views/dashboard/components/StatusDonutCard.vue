<template>
  <div
    class="donut-wrap"
    data-testid="status-donut"
  >
    <EChart
      :option="chartOption"
      :height="128"
    />
    <div class="donut-center">
      <div class="mono donut-total">
        {{ total.toLocaleString() }}
      </div>
      <div class="dash-muted donut-total-label">
        {{ $t('dashboard.widgets.statusPie.total') }}
      </div>
    </div>
    <div class="dash-legend donut-legend">
      <span
        v-for="seg in legendItems"
        :key="seg.key"
        class="item"
      >
        <span
          class="sw"
          :style="{background: seg.color}"
        />
        {{ $t(`dashboard.widgets.statusPie.${seg.key}`) }} {{ seg.count }}
      </span>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * StatusDonutCard —— 状态分布环形 widget（仪表盘一期 W3）。
 *
 * 数据源：W1 torrents.statusBuckets（五桶，口径与 /reports/overview
 * statusDist 一致）。EChart 环形（pie 内径空心 + 中心总数绝对定位），
 * 图例用语义化 dash-legend（对齐示意图形态，五桶计数直读）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import EChart from '@/components/charts/EChart.vue'
import { StatusBuckets, StatusBucketKey } from '@/types/dashboard'

/** 五桶展示顺序与配色（令牌色随三主题） */
const ORDER: ReadonlyArray<{ key: StatusBucketKey; color: string }> = [
  { key: 'seeding', color: 'var(--color-success)' },
  { key: 'downloading', color: 'var(--color-info)' },
  { key: 'paused', color: 'var(--color-warning)' },
  { key: 'error', color: 'var(--color-error)' },
  { key: 'other', color: 'var(--color-text-quaternary, #D1D5DB)' }
]

@Component({ name: 'StatusDonutCard', components: { EChart } })
export default class StatusDonutCard extends Vue {
  @Prop({ required: true }) private buckets!: StatusBuckets

  private get total(): number {
    return ORDER.reduce((sum, o) => sum + (this.buckets[o.key] || 0), 0)
  }

  private get legendItems(): Array<{ key: StatusBucketKey; color: string; count: number }> {
    return ORDER.map(o => ({ key: o.key, color: o.color, count: this.buckets[o.key] || 0 }))
  }

  private resolveColor(token: string, fallback: string): string {
    const name = token.match(/--color-[a-z-]+/)?.[0]
    if (!name) return token.startsWith('var(') ? fallback : token
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return v || fallback
  }

  private get chartOption(): Record<string, unknown> | null {
    const colorMap: Record<string, string> = {
      seeding: this.resolveColor('var(--color-success)', '#10B981'),
      downloading: this.resolveColor('var(--color-info)', '#3B82F6'),
      paused: this.resolveColor('var(--color-warning)', '#F59E0B'),
      error: this.resolveColor('var(--color-error)', '#EF4444'),
      other: this.resolveColor('var(--color-text-quaternary)', '#D1D5DB')
    }
    const data = ORDER
      .map(o => ({
        name: this.$t(`dashboard.widgets.statusPie.${o.key}`).toString(),
        value: this.buckets[o.key] || 0,
        itemStyle: { color: colorMap[o.key] }
      }))
      .filter(d => d.value > 0)
    if (data.length === 0) return null
    return {
      animation: false,
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: ['62%', '82%'],
          center: ['50%', '50%'],
          avoidLabelOverlap: false,
          label: { show: false },
          emphasis: { scale: false },
          data
        }
      ]
    }
  }
}
</script>

<style lang="scss" scoped>
.donut-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  position: relative;
}

.donut-center {
  position: absolute;
  top: 50px;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  pointer-events: none;
}

.donut-total {
  font-size: 22px;
  font-weight: 700;
}

.donut-total-label {
  font-size: 11px;
}

.donut-legend {
  justify-content: center;
}
</style>
