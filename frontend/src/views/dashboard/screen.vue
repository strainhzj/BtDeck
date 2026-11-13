<template>
  <div
    class="data-screen"
    data-testid="data-screen"
    tabindex="0"
  >
    <!-- 头部：标题 + 时钟 + 运行信息 + 退出 -->
    <div class="screen-head">
      <div class="screen-title">
        <lucide-icon name="layout-dashboard" />
        <span>{{ $t('dashboard.screen.title') }}</span>
      </div>
      <div
        class="screen-clock mono"
        data-testid="screen-clock"
      >{{ clockText }}</div>
      <div class="screen-sub">
        <div>{{ dateLine }}</div>
        <div>{{ $t('dashboard.screen.uptime', {duration: uptimeDisplay}) }} · {{ $t('dashboard.screen.onlineCount', {count: onlineCount}) }}</div>
      </div>
      <button
        type="button"
        class="screen-exit"
        data-testid="screen-exit-btn"
        @click="exitScreen()"
      >
        <lucide-icon name="x" />
        {{ $t('dashboard.screen.exit') }}
      </button>
    </div>

    <!-- KPI 条六项（一期可交付项，不含分享率/异常数） -->
    <div class="screen-kpis">
      <div class="skpi">
        <div class="l">{{ $t('dashboard.downloadSpeed') }}</div>
        <div
          class="v mono accent"
          data-testid="skpi-download"
        >{{ speedText(dash.system.total_download_speed) }}</div>
      </div>
      <div class="skpi">
        <div class="l">{{ $t('dashboard.uploadSpeed') }}</div>
        <div
          class="v mono accent2"
          data-testid="skpi-upload"
        >{{ speedText(dash.system.total_upload_speed) }}</div>
      </div>
      <div class="skpi">
        <div class="l">{{ $t('dashboard.kpi.activeTorrents') }}</div>
        <div class="v mono">{{ dash.torrents.active }}</div>
      </div>
      <div class="skpi">
        <div class="l">{{ $t('dashboard.screen.upload24h') }}</div>
        <div class="v mono accent2">{{ upload24hText }}</div>
      </div>
      <div class="skpi">
        <div class="l">{{ $t('dashboard.screen.enabledTasks') }}</div>
        <div class="v mono accent3">{{ dash.tasks.enabled }}</div>
      </div>
      <div class="skpi">
        <div class="l">{{ $t('dashboard.screen.uptimeLabel') }}</div>
        <div class="v mono">{{ uptimeDisplay }}</div>
      </div>
    </div>

    <!-- 主区：链路雷达 / 吞吐波浪 / 任务播报 -->
    <div class="screen-main">
      <div class="spanel">
        <div class="st">
          <lucide-icon name="radar" />
          <span>{{ $t('dashboard.screen.radarTitle') }}</span>
        </div>
        <RadarCard
          class="screen-radar"
          :list="dash.downloader_list"
          :dark="true"
          radar-test-id="screen-radar"
        />
      </div>
      <div class="spanel">
        <div class="st">
          <lucide-icon name="waves" />
          <span>{{ $t('dashboard.screen.waveTitle') }}</span>
        </div>
        <div class="screen-wave-wrap">
          <canvas ref="waveCanvas" />
        </div>
      </div>
      <div class="spanel">
        <div class="st">
          <lucide-icon name="upload" />
          <span>{{ $t('dashboard.screen.tickerTitle') }}</span>
        </div>
        <div class="ticker-list">
          <div
            v-for="(t, i) in tickerTorrents"
            :key="t.hash + i"
            class="ticker-row"
          >
            <span class="nm">{{ nameOf(t) }}</span>
            <span class="mono sp">{{ speedText(t.downloadSpeed) }}</span>
            <span class="mono pct">{{ Math.round(t.progress) }}%</span>
          </div>
          <div
            v-if="tickerTorrents.length === 0"
            class="ticker-empty"
          >
            {{ $t('dashboard.widgets.hero.empty') }}
          </div>
        </div>
      </div>
    </div>

    <!-- 底注 -->
    <div class="screen-foot">
      <span>{{ $t('dashboard.screen.refreshNote') }}</span>
      <span>{{ $t('dashboard.screen.brand') }}</span>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * DataScreen —— 数据大屏沉浸页（仪表盘一期 W4）。
 *
 * - 深色画布：--screen-* 变量独立于应用明暗主题（不动 theme-variables.scss）；
 * - 路由 /dashboard/screen（Layout 内 hidden 子路由，根元素 fixed 覆盖层，
 *   先例=趣味报告沉浸页）；进入/退出即路由切换，刷新停留大屏即 query 持久化；
 * - 数据轮询（复用现有端点，3~5s）：getDashboardData（KPI/下载器/任务启用）
 *   + getActiveTorrents（播报）；近 24h 上传走 getReportsSpeedHistory 低频
 *   （2min，分钟级 raw 积分无需高频）；
 * - KPI 六项：下载/上传速度/活跃种子/近 24h 上传/已启用任务/运行时长
 *   （不含分享率与异常数——决策 #4 与二期边界）；
 * - 吞吐波浪：共享 waveCanvas 三层正弦（SCREEN_WAVE_LAYERS 深色配色）；
 *   链路雷达：复用 RadarCard（dark 模式）；
 * - Esc 退出 + 按钮 退出（router.push('/dashboard')）。
 */
import { Component, Vue } from 'vue-property-decorator'
import { getDashboardData } from '@/api/dashboard'
import { getActiveTorrents, ActiveTorrentSpeed } from '@/api/torrents'
import { getReportsSpeedHistory } from '@/api/reports'
import { DashboardData } from '@/types/dashboard'
import { formatSpeed } from '@/utils/formatters'
import RadarCard from '@/views/dashboard/components/RadarCard.vue'
import { drawWaves, fitCanvasToContainer, SCREEN_WAVE_LAYERS } from '@/views/dashboard/components/waveCanvas'
import { bucketSpeedHistoryByHour } from '@/views/dashboard/components/trafficBinning'
import { formatTrafficBytes } from '@/views/dashboard/components/trafficBinning'

const DASH_POLL_MS = 5000
const TICKER_POLL_MS = 5000
const TRAFFIC_POLL_MS = 120000
const CLOCK_MS = 1000
const TICKER_MAX = 8

@Component({ name: 'DataScreen', components: { RadarCard } })
export default class DataScreen extends Vue {
  private dashboardData: DashboardData | null = null
  private activeTorrents: ActiveTorrentSpeed[] = []
  private upload24hBytes = 0
  private clockText = '--:--:--'
  private dateLine = ''

  private dashTimer: number | null = null
  private tickerTimer: number | null = null
  private trafficTimer: number | null = null
  private clockTimer: number | null = null

  private rafId = 0
  private waveT = 0

  private get dash(): DashboardData {
    return (
      this.dashboardData || {
        downloaders: { total: 0, online: 0, offline: 0 },
        torrents: {
          active: 0,
          downloading: 0,
          seeding: 0,
          paused: 0,
          statusBuckets: { error: 0, downloading: 0, seeding: 0, paused: 0, other: 0 },
          siteBuckets: []
        },
        tasks: { total: 0, running: 0, stopped: 0, enabled: 0 },
        system: { uptime: 0, uptime_display: '--', version: '--', total_download_speed: 0, total_upload_speed: 0 },
        downloader_list: [],
        activities: []
      }
    )
  }

  private get onlineCount(): number {
    return this.dash.downloaders.online
  }

  private get uptimeDisplay(): string {
    return this.dash.system.uptime_display || '--'
  }

  private get upload24hText(): string {
    return formatTrafficBytes(this.upload24hBytes)
  }

  private get tickerTorrents(): ActiveTorrentSpeed[] {
    return [...this.activeTorrents]
      .sort((a, b) => b.downloadSpeed - a.downloadSpeed)
      .filter(t => t.downloadSpeed > 0)
      .slice(0, TICKER_MAX)
  }

  private mounted() {
    this.refreshClock()
    this.fetchDashboard()
    this.fetchTicker()
    this.fetchTraffic()
    this.startTimers()
    document.addEventListener('keydown', this.onKeydown)
    const canvas = this.$refs.waveCanvas as HTMLCanvasElement | undefined
    if (canvas) {
      fitCanvasToContainer(canvas, canvas.parentElement)
      this.loop()
    }
  }

  private beforeDestroy() {
    this.stopTimers()
    cancelAnimationFrame(this.rafId)
    document.removeEventListener('keydown', this.onKeydown)
  }

  private onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      this.exitScreen()
    }
  }

  private exitScreen() {
    this.$router.push('/dashboard').catch(() => undefined)
  }

  // ==================== 数据轮询 ====================

  private async fetchDashboard() {
    try {
      const res = await getDashboardData()
      if (res.code === '200' && res.data) {
        this.dashboardData = res.data
      }
    } catch {
      // 轮询失败保持上一轮快照
    }
  }

  private async fetchTicker() {
    try {
      const res = await getActiveTorrents()
      if (res.code === '200' && Array.isArray(res.data)) {
        this.activeTorrents = res.data
      }
    } catch {
      // 同上
    }
  }

  private async fetchTraffic() {
    try {
      const res = await getReportsSpeedHistory('24h')
      if (res.code === '200' && res.data?.series) {
        const result = bucketSpeedHistoryByHour(res.data.series)
        this.upload24hBytes = result.uploadTotalBytes
      }
    } catch {
      // 同上
    }
  }

  private startTimers() {
    this.dashTimer = window.setInterval(() => this.fetchDashboard(), DASH_POLL_MS)
    this.tickerTimer = window.setInterval(() => this.fetchTicker(), TICKER_POLL_MS)
    this.trafficTimer = window.setInterval(() => this.fetchTraffic(), TRAFFIC_POLL_MS)
    this.clockTimer = window.setInterval(() => this.refreshClock(), CLOCK_MS)
  }

  private stopTimers() {
    for (const timer of [this.dashTimer, this.tickerTimer, this.trafficTimer, this.clockTimer]) {
      if (timer) clearInterval(timer)
    }
    this.dashTimer = null
    this.tickerTimer = null
    this.trafficTimer = null
    this.clockTimer = null
  }

  private refreshClock() {
    const d = new Date()
    const p = (n: number) => (n < 10 ? `0${n}` : `${n}`)
    this.clockText = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
    const weekday = this.$t(`dashboard.screen.weekday.${d.getDay()}`).toString()
    this.dateLine = this.$t('dashboard.screen.dateLine', {
      y: d.getFullYear(),
      m: d.getMonth() + 1,
      d: d.getDate(),
      w: weekday
    }).toString()
  }

  // ==================== 波浪 ====================

  private loop = () => {
    const canvas = this.$refs.waveCanvas as HTMLCanvasElement | undefined
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (ctx) {
      drawWaves(ctx, canvas.width, canvas.height, this.waveT, SCREEN_WAVE_LAYERS)
      this.waveT += 1
    }
    this.rafId = requestAnimationFrame(this.loop)
  }

  // ==================== 展示辅助 ====================

  private nameOf(t: ActiveTorrentSpeed): string {
    return t.name || t.hash.slice(0, 12)
  }

  private speedText(bytesPerSec: number): string {
    return formatSpeed(bytesPerSec || 0) || '0 B/s'
  }
}
</script>

<style lang="scss" scoped>
/* 深色画布变量：独立于应用明暗主题（W4 约束，不动 theme-variables.scss） */
.data-screen {
  --screen-bg: #0a1120;
  --screen-panel: rgba(255, 255, 255, 0.045);
  --screen-border: rgba(255, 255, 255, 0.09);
  --screen-text: #e5e7eb;
  --screen-muted: #94a3b8;
  --screen-accent: #34d399;
  --screen-accent2: #60a5fa;
  --screen-accent3: #fbbf24;

  position: fixed;
  inset: 0;
  z-index: 1200;
  background: var(--screen-bg);
  color: var(--screen-text);
  display: flex;
  flex-direction: column;
  padding: 18px 22px;
  gap: 14px;
  outline: none;
  overflow: hidden;
}

.screen-head {
  display: flex;
  align-items: center;
  gap: 16px;
}

.screen-title {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 1px;
  display: flex;
  align-items: center;
  gap: 10px;

  .lucide-icon {
    width: 20px;
    height: 20px;
    color: var(--screen-accent);
  }
}

.screen-clock {
  font-size: 26px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--screen-accent);
}

.screen-sub {
  color: var(--screen-muted);
  font-size: 12px;
  line-height: 1.6;
}

.screen-exit {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: 1px solid var(--screen-border);
  color: var(--screen-muted);
  border-radius: var(--radius-md);
  padding: 7px 14px;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: var(--transition-base);

  &:hover {
    color: var(--screen-accent);
    border-color: var(--screen-accent);
    background: rgba(52, 211, 153, 0.08);
  }

  .lucide-icon {
    width: 14px;
    height: 14px;
  }
}

.screen-kpis {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}

.skpi {
  background: var(--screen-panel);
  border: 1px solid var(--screen-border);
  border-radius: var(--radius-lg);
  padding: 10px 14px;

  .l {
    font-size: 11.5px;
    color: var(--screen-muted);
  }

  .v {
    font-size: 20px;
    font-weight: 700;
    margin-top: 3px;

    &.accent {
      color: var(--screen-accent);
    }

    &.accent2 {
      color: var(--screen-accent2);
    }

    &.accent3 {
      color: var(--screen-accent3);
    }
  }
}

.screen-main {
  flex: 1;
  display: grid;
  grid-template-columns: 300px 1fr 240px;
  gap: 14px;
  min-height: 0;
}

.spanel {
  background: var(--screen-panel);
  border: 1px solid var(--screen-border);
  border-radius: var(--radius-lg);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  min-height: 0;

  .st {
    font-size: 12.5px;
    color: var(--screen-muted);
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;

    .lucide-icon {
      width: 13px;
      height: 13px;
      color: var(--screen-accent);
    }
  }
}

.screen-radar {
  flex: 1;
  min-height: 0;
}

.screen-wave-wrap {
  flex: 1;
  min-height: 0;
  position: relative;

  canvas {
    width: 100%;
    height: 100%;
    display: block;
  }
}

.ticker-list {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ticker-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 12px;
  font-size: 12px;
  color: var(--screen-muted);
  align-items: center;

  .nm {
    color: var(--screen-text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sp {
    color: var(--screen-accent);
  }

  .pct {
    color: var(--screen-muted);
  }
}

.ticker-empty {
  color: var(--screen-muted);
  font-size: 12px;
  padding: 12px 0;
  text-align: center;
}

.screen-foot {
  display: flex;
  justify-content: space-between;
  color: var(--screen-muted);
  font-size: 11.5px;
}

@media (max-width: 900px) {
  .data-screen .screen-main {
    grid-template-columns: 1fr;
  }

  .data-screen .screen-kpis {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
