<template>
  <div style="display:flex;flex-direction:column;align-items:center;gap:12px">
    <div
      class="donut-wrap"
      data-testid="status-donut"
    >
      <svg
        viewBox="0 0 120 120"
        width="128"
        height="128"
        :aria-hidden="true"
      >
        <circle
          cx="60"
          cy="60"
          r="48"
          fill="none"
          stroke="var(--color-bg-tertiary)"
          stroke-width="14"
        />
        <circle
          v-for="seg in segments"
          :key="seg.key"
          cx="60"
          cy="60"
          r="48"
          fill="none"
          :stroke="seg.color"
          stroke-width="14"
          :stroke-dasharray="seg.dash"
          :stroke-dashoffset="seg.offset"
        />
      </svg>
      <div class="donut-center">
        <div class="mono donut-total">
          {{ total.toLocaleString() }}
        </div>
        <div class="dash-muted donut-total-label">
          {{ $t('dashboard.widgets.statusPie.total') }}
        </div>
      </div>
    </div>
    <div class="dash-legend">
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
 * StatusDonutCard —— 状态分布环形 widget（仪表盘一期 W2）。
 *
 * 数据源：W1 torrents.statusBuckets（五桶，口径与 /reports/overview
 * statusDist 一致，has_tracker_error 优先判 error）。SVG 环形实现（对齐
 * 验收示意图形态）；W3 若切换 echarts 版本另行记录，数据口径不变。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import { StatusBuckets, StatusBucketKey } from '@/types/dashboard'

const CIRC = 2 * Math.PI * 48

/** 五桶展示顺序与配色（令牌色随三主题） */
const ORDER: ReadonlyArray<{ key: StatusBucketKey, color: string }> = [
  { key: 'seeding', color: 'var(--color-success)' },
  { key: 'downloading', color: 'var(--color-info)' },
  { key: 'paused', color: 'var(--color-warning)' },
  { key: 'error', color: 'var(--color-error)' },
  { key: 'other', color: 'var(--color-text-quaternary, #D1D5DB)' }
]

@Component({ name: 'StatusDonutCard' })
export default class StatusDonutCard extends Vue {
  @Prop({ required: true }) private buckets!: StatusBuckets

  private get total(): number {
    return ORDER.reduce((sum, o) => sum + (this.buckets[o.key] || 0), 0)
  }

  private get segments(): Array<{ key: StatusBucketKey, color: string, dash: string, offset: number }> {
    let consumed = 0
    return ORDER.map(o => {
      const count = this.buckets[o.key] || 0
      const len = this.total > 0 ? (count / this.total) * CIRC : 0
      const seg = {
        key: o.key,
        color: o.color,
        dash: `${len.toFixed(1)} ${CIRC.toFixed(1)}`,
        offset: -consumed
      }
      consumed += len
      return seg
    }).filter(s => parseFloat(s.dash) > 0)
  }

  private get legendItems(): Array<{ key: StatusBucketKey, color: string, count: number }> {
    return ORDER.map(o => ({ key: o.key, color: o.color, count: this.buckets[o.key] || 0 }))
  }
}
</script>

<style lang="scss" scoped>
.donut-wrap {
  position: relative;
  width: 128px;
  height: 128px;

  svg {
    transform: rotate(-90deg);
  }
}

.donut-center {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  text-align: center;
}

.donut-total {
  font-size: 22px;
  font-weight: 700;
}

.donut-total-label {
  font-size: 11px;
}
</style>
