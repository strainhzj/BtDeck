<template>
  <div class="dash-hero">
    <div class="dash-hero-stats">
      <div class="hs">
        <div class="v mono hero-dl">
          {{ speedText(downloadSpeed) }} <small>{{ speedUnit(downloadSpeed) }}</small>
        </div>
        <div class="l">{{ $t('dashboard.downloadSpeed') }}</div>
      </div>
      <div class="hs">
        <div class="v mono hero-ul">
          {{ speedText(uploadSpeed) }} <small>{{ speedUnit(uploadSpeed) }}</small>
        </div>
        <div class="l">{{ $t('dashboard.uploadSpeed') }}</div>
      </div>
      <div class="hs">
        <div class="v mono">{{ downloading }}</div>
        <div class="l">{{ $t('dashboard.widgets.hero.activeDownloading') }}</div>
      </div>
      <div class="hs">
        <div class="v mono">{{ seeding }}</div>
        <div class="l">{{ $t('dashboard.widgets.hero.activeSeeding') }}</div>
      </div>
    </div>
    <div class="dash-hero-canvas">
      <canvas ref="canvas" />
    </div>
    <div class="dash-hero-ticker">
      <div
        v-for="(t, i) in tickerTorrents"
        :key="t.hash + i"
        class="dash-rowline"
      >
        <span class="dash-status-pill st-run">{{ $t('dashboard.widgets.hero.downloading') }}</span>
        <div
          class="grow dash-ellip"
          :title="nameOf(t)"
        >
          {{ nameOf(t) }}
        </div>
        <span class="dash-tor-sp dl">
          <lucide-icon name="arrow-down" />
          <span class="mono">{{ speedText(t.downloadSpeed) }}</span>
        </span>
        <span class="dash-muted mono">{{ Math.round(t.progress) }}%</span>
      </div>
      <div
        v-if="tickerTorrents.length === 0"
        class="dash-empty"
      >
        <lucide-icon name="waves" />
        <span>{{ $t('dashboard.widgets.hero.empty') }}</span>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * HeroPulseCard —— 实时脉搏 widget（仪表盘一期 W2，聚焦档主卡）。
 *
 * 数据源：system 总速度 + torrents 活跃数 + active-torrents ticker。
 * 波浪为原生 canvas 三层正弦（自研重写为生产级：dpr 缩放/ResizeObserver/
 * visibility 停帧/beforeDestroy 清理；非移植 BitMatrix Canvas 代码）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import { ActiveTorrentSpeed } from '@/api/torrents'
import { formatSpeed } from '@/utils/formatters'
import { drawWaves, fitCanvasToContainer, HERO_WAVE_LAYERS } from './waveCanvas'

@Component({ name: 'HeroPulseCard' })
export default class HeroPulseCard extends Vue {
  @Prop({ required: true }) private downloadSpeed!: number
  @Prop({ required: true }) private uploadSpeed!: number
  @Prop({ required: true }) private downloading!: number
  @Prop({ required: true }) private seeding!: number
  @Prop({ required: true }) private activeTorrents!: ActiveTorrentSpeed[]

  private t = 0
  private rafId = 0
  private resizeObserver: ResizeObserver | null = null
  private visible = true

  private get tickerTorrents(): ActiveTorrentSpeed[] {
    return [...this.activeTorrents]
      .sort((a, b) => b.downloadSpeed - a.downloadSpeed)
      .filter(t => t.downloadSpeed > 0)
      .slice(0, 2)
  }

  private mounted() {
    const canvas = this.$refs.canvas as HTMLCanvasElement | undefined
    if (!canvas) return
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => fitCanvasToContainer(canvas, canvas.parentElement))
      this.resizeObserver.observe(canvas.parentElement || canvas)
    }
    document.addEventListener('visibilitychange', this.onVisibility)
    fitCanvasToContainer(canvas, canvas.parentElement)
    this.loop()
  }

  private beforeDestroy() {
    cancelAnimationFrame(this.rafId)
    this.resizeObserver?.disconnect()
    this.resizeObserver = null
    document.removeEventListener('visibilitychange', this.onVisibility)
  }

  private onVisibility() {
    this.visible = !document.hidden
    if (this.visible) this.loop()
  }

  private fitCanvas() {
    const canvas = this.$refs.canvas as HTMLCanvasElement | undefined
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.max(10, Math.round(rect.width * dpr))
    canvas.height = Math.max(10, Math.round(rect.height * dpr))
  }

  private loop = () => {
    if (!this.visible) return
    this.draw()
    this.rafId = requestAnimationFrame(this.loop)
  }

  private draw() {
    const canvas = this.$refs.canvas as HTMLCanvasElement | undefined
    if (!canvas || canvas.offsetParent === null) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    drawWaves(ctx, canvas.width, canvas.height, this.t, HERO_WAVE_LAYERS)
    this.t += 1
  }

  private nameOf(t: ActiveTorrentSpeed): string {
    return t.name || t.hash.slice(0, 12)
  }

  private speedText(bytesPerSec: number): string {
    return formatSpeed(bytesPerSec || 0) || '0'
  }

  private speedUnit(bytesPerSec: number): string {
    const text = formatSpeed(bytesPerSec || 0) || '0 B/s'
    // formatSpeed 输出形如 "12.3 MB/s"，取单位部分
    const parts = text.split(' ')
    return parts.length > 1 ? parts[1] : 'B/s'
  }
}
</script>

<style lang="scss" scoped>
.hero-dl {
  color: var(--color-primary);
}

.hero-ul {
  color: var(--color-info);
}
</style>
