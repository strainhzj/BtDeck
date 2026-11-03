<template>
  <div class="dash-tube-wrap">
    <div class="dash-tube-col">
      <div class="dash-tube-value dl mono">{{ speedText(downloadSpeed) }}</div>
      <div class="dash-tube-label">{{ $t('dashboard.downloadSpeed') }}</div>
      <div class="dash-tube">
        <div
          class="dash-tube-fill dl"
          :style="{height: downloadLevel + '%'}"
        />
        <div class="dash-tube-flow" />
      </div>
    </div>
    <div class="dash-tube-col">
      <div class="dash-tube-value ul mono">{{ speedText(uploadSpeed) }}</div>
      <div class="dash-tube-label">{{ $t('dashboard.uploadSpeed') }}</div>
      <div class="dash-tube">
        <div
          class="dash-tube-fill ul"
          :style="{height: uploadLevel + '%'}"
        />
        <div class="dash-tube-flow" />
      </div>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * ThroughputTubesCard —— 吞吐管道 widget（仪表盘一期 W2）。
 *
 * 数据源：GET /dashboard 的 system.total_download_speed/upload_speed
 * （bytes/s）。液位按历史峰值自适应归一（组件内递推峰值，避免全局依赖）。
 */
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import { formatSpeed } from '@/utils/formatters'

@Component({ name: 'ThroughputTubesCard' })
export default class ThroughputTubesCard extends Vue {
  @Prop({ required: true }) private downloadSpeed!: number
  @Prop({ required: true }) private uploadSpeed!: number

  private peak = 1

  @Watch('downloadSpeed', { immediate: true })
  @Watch('uploadSpeed', { immediate: true })
  private onSpeed() {
    this.peak = Math.max(this.peak, this.downloadSpeed || 0, this.uploadSpeed || 0)
  }

  private get downloadLevel(): number {
    return Math.min(95, Math.round(((this.downloadSpeed || 0) / this.peak) * 100))
  }

  private get uploadLevel(): number {
    return Math.min(95, Math.round(((this.uploadSpeed || 0) / this.peak) * 100))
  }

  private speedText(bytesPerSec: number): string {
    return formatSpeed(bytesPerSec || 0) || '0 B/s'
  }
}
</script>
