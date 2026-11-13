<template>
  <div class="m-dashboard dashboard-page">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />
    <div v-if="loading" class="m-hint">{{ $t('dashboard.mobile.loading') }}</div>
    <template v-else>
      <!-- KPI 2×2（恒显于卡片流之外，语义同桌面一期） -->
      <section class="m-kpi-grid">
        <kpi-card
          :label="$t('dashboard.kpi.downloaders')"
          icon="server"
          clickable
          :aria-label="$t('dashboard.aria.viewDownloaders')"
          @click="navigateTo('/m/downloader')"
        >
          <template #value>
            {{ hasData ? dashboard.downloaders.online : '--' }}<small>/ {{ hasData ? dashboard.downloaders.total : '--' }}</small>
          </template>
          <template #foot>
            <span
              v-if="hasData"
              :class="['dash-kpi-chip', allDownloadersOnline ? 'up' : 'flat']"
            >
              {{ allDownloadersOnline ? $t('dashboard.allOnline') : $t('dashboard.onlineCount', {count: dashboard.downloaders.online}) }}
            </span>
            <span
              v-else
              class="dash-kpi-chip flat"
            >--</span>
          </template>
        </kpi-card>

        <kpi-card
          :label="$t('dashboard.kpi.activeTorrents')"
          icon="download"
          clickable
          :aria-label="$t('dashboard.aria.viewTorrents')"
          @click="navigateTo('/m/torrents')"
        >
          <template #value>
            {{ hasData ? dashboard.torrents.active : '--' }}
          </template>
          <template #foot>
            <span class="dash-kpi-chip flat">
              {{ $t('dashboard.kpi.dlSplit', {count: dashboard.torrents.downloading}) }} · {{ $t('dashboard.kpi.sdSplit', {count: dashboard.torrents.seeding}) }}
            </span>
          </template>
        </kpi-card>

        <kpi-card
          :label="$t('dashboard.kpi.enabledTasks')"
          icon="clock"
          clickable
          :aria-label="$t('dashboard.aria.viewTasks')"
          @click="navigateTo('/m/tasks')"
        >
          <template #value>
            {{ hasData ? dashboard.tasks.enabled : '--' }}<small> {{ $t('dashboard.kpi.enabledUnit') }}</small>
          </template>
          <template #foot>
            <span class="dash-kpi-chip flat">{{ $t('dashboard.kpi.enabledNote') }}</span>
          </template>
        </kpi-card>

        <kpi-card :label="$t('dashboard.kpi.systemSpeed')" icon="zap">
          <template #value>
            <span />
          </template>
          <template #default>
            <div class="dash-kpi-dual">
              <div class="kv">
                <div class="v mono" style="color:var(--color-primary)">
                  {{ hasData ? speedText(dashboard.system.total_download_speed) : '--' }}
                </div>
                <div class="l">
                  <span class="dash-kpi-dot" style="background:var(--color-primary)" />
                  {{ $t('dashboard.downloadSpeed') }}
                </div>
              </div>
              <div class="kv">
                <div class="v mono" style="color:var(--color-info)">
                  {{ hasData ? speedText(dashboard.system.total_upload_speed) : '--' }}
                </div>
                <div class="l">
                  <span class="dash-kpi-dot" style="background:var(--color-info)" />
                  {{ $t('dashboard.uploadSpeed') }}
                </div>
              </div>
            </div>
          </template>
        </kpi-card>
      </section>

      <!-- widget 单列卡片流（dashboard-mobile-2026-11：复用一期桌面卡片族） -->
      <section class="m-widget-stack">
        <dash-widget widget-id="hero" :span="12" :title="$t('dashboard.widgets.hero.title')">
          <hero-pulse-card
            :download-speed="dashboard.system.total_download_speed"
            :upload-speed="dashboard.system.total_upload_speed"
            :downloading="dashboard.torrents.downloading"
            :seeding="dashboard.torrents.seeding"
            :active-torrents="activeTorrents"
          />
        </dash-widget>

        <dash-widget widget-id="statusPie" :span="12" :title="$t('dashboard.widgets.statusPie.title')">
          <status-donut-card :buckets="dashboard.torrents.statusBuckets" />
        </dash-widget>

        <dash-widget widget-id="traffic" :span="12" :title="$t('dashboard.widgets.traffic.title')">
          <daily-traffic-card
            :ready="trafficReady"
            :loading="trafficLoading"
            :result="trafficResult"
          />
        </dash-widget>

        <dash-widget widget-id="sites" :span="12" :title="$t('dashboard.widgets.sites.title')">
          <site-bars-card :buckets="dashboard.torrents.siteBuckets" />
        </dash-widget>

        <dash-widget widget-id="hot" :span="12" :title="$t('dashboard.widgets.hot.title')">
          <hot-torrents-card :torrents="activeTorrents" />
          <button type="button" class="m-view-all" @click="navigateTo('/m/torrents')">
            {{ $t('dashboard.mobile.viewAllTorrents') }}
            <lucide-icon icon="chevron-right" />
          </button>
        </dash-widget>

        <dash-widget widget-id="health" :span="12" :title="$t('dashboard.widgets.health.title')">
          <instance-health-card v-if="downloaderList.length" :list="downloaderList" />
          <div v-else class="m-empty-cta">
            <div class="m-empty-text">{{ $t('dashboard.mobile.noDownloaders') }}</div>
            <button type="button" class="m-cta-btn" @click="goAddDownloader">
              {{ $t('dashboard.mobile.addDownloader') }}
            </button>
          </div>
        </dash-widget>

        <dash-widget widget-id="tasks" :span="12" :title="$t('dashboard.widgets.tasks.title')">
          <cron-task-card :tasks="taskList" />
        </dash-widget>

        <dash-widget widget-id="activity" :span="12" :title="$t('dashboard.widgets.activity.title')">
          <activity-timeline-card :activities="dashboard.activities" />
        </dash-widget>
      </section>
    </template>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import { getDashboardData } from '@/api/dashboard'
import { getActiveTorrents, ActiveTorrentSpeed } from '@/api/torrents'
import { getTaskList, ScheduledTask } from '@/api/tasks'
import { getReportsSpeedHistory } from '@/api/reports'
import { DashboardData, DownloaderListItem } from '@/types/dashboard'
import { extractErrorMessage, formatSpeed } from '@/utils/formatters'
import SpeedPollingMixin from '@/views/torrents/mixins/speedPolling'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import KpiCard from '@/views/dashboard/components/KpiCard.vue'
import DashWidget from '@/views/dashboard/components/DashWidget.vue'
import HeroPulseCard from '@/views/dashboard/components/HeroPulseCard.vue'
import StatusDonutCard from '@/views/dashboard/components/StatusDonutCard.vue'
import DailyTrafficCard from '@/views/dashboard/components/DailyTrafficCard.vue'
import SiteBarsCard from '@/views/dashboard/components/SiteBarsCard.vue'
import HotTorrentsCard from '@/views/dashboard/components/HotTorrentsCard.vue'
import InstanceHealthCard from '@/views/dashboard/components/InstanceHealthCard.vue'
import CronTaskCard from '@/views/dashboard/components/CronTaskCard.vue'
import ActivityTimelineCard from '@/views/dashboard/components/ActivityTimelineCard.vue'
import { bucketSpeedHistoryByHour, HourTrafficResult } from '@/views/dashboard/components/trafficBinning'

const DASHBOARD_REFRESH_MS = 30000
/** D1（用户拍板）：活跃种子轮询与桌面一致 3s（SpeedPollingMixin 后台自动暂停兜底省电） */
const ACTIVE_POLL_MS = 3000
const TASK_REFRESH_MS = 60000
const TRAFFIC_REFRESH_MS = 120000

/**
 * 移动仪表盘二期（dashboard-mobile-2026-11）：
 *
 * - 一期桌面改造（PLANS/dashboard-redesign-2026-11.md）desktop-only，本页此前为
 *   Phase 4 旧简化页，未消费一期任何新字段——本版重写为纵向卡片流，直接复用
 *   一期桌面卡片族（全部 props 驱动）+ DashWidget 卡壳 + dashboard-page 皮肤；
 * - 数据源与桌面一致：getDashboardData（30s）/ getActiveTorrents（3s）/
 *   getTaskList（60s）/ /reports/speed/history 24h（120s）+ 下拉刷新全量并发；
 * - 后端零改动；移动端无预设/编辑/拖拽/布局持久化（固定单列流）；
 * - 空态引导与"查看全部种子"等页面级新文案走 dashboard.mobile.* i18n 键（zh/en）。
 */
@Component({
  name: 'MobileDashboard',
  components: {
    'm-pull-indicator': MobilePullIndicator,
    KpiCard,
    DashWidget,
    HeroPulseCard,
    StatusDonutCard,
    DailyTrafficCard,
    SiteBarsCard,
    HotTorrentsCard,
    InstanceHealthCard,
    CronTaskCard,
    ActivityTimelineCard
  }
})
export default class MobileDashboard extends Mixins(PullToRefresh, SpeedPollingMixin) {
  private loading = false
  private hasData = false
  private dashboardData: DashboardData | null = null
  private activeTorrents: ActiveTorrentSpeed[] = []
  private taskList: ScheduledTask[] = []
  private trafficResult: HourTrafficResult | null = null
  private trafficLoading = false

  private dashboardTimer: number | null = null
  private taskTimer: number | null = null
  private trafficTimer: number | null = null

  protected speedPollIntervalMs = ACTIVE_POLL_MS

  private readonly emptyDashboardData: DashboardData = {
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

  // 模板经 vue-jest(buble) 编译不支持 ?. 与 ??，字段兜底收敛到 computed
  private get dashboard(): DashboardData {
    return this.dashboardData || this.emptyDashboardData
  }

  private get downloaderList(): DownloaderListItem[] {
    return this.dashboardData ? this.dashboardData.downloader_list : []
  }

  private get allDownloadersOnline(): boolean {
    const d = this.dashboard.downloaders
    return d.online === d.total && d.total > 0
  }

  private get trafficReady(): boolean {
    return (this.trafficResult?.buckets.length || 0) > 0
  }

  created(): void {
    this.initialLoad()
    this.startTimers()
    // startSpeedPolling(false)：首轮延迟一个周期，避免与 initialLoad 双发
    this.startSpeedPolling(false)
  }

  beforeDestroy(): void {
    this.stopTimers()
    this.stopSpeedPolling()
  }

  // ==================== 数据获取 ====================

  private async initialLoad(): Promise<void> {
    this.loading = true
    try {
      await Promise.all([
        this.fetchDashboardData(),
        this.fetchActiveTorrents(),
        this.fetchTasks(),
        this.fetchTraffic()
      ])
    } finally {
      this.loading = false
    }
  }

  /** SpeedPollingMixin 轮询体：3s 活跃种子（热门种子/hero 速度共源） */
  protected async loadActiveSpeed(): Promise<boolean> {
    await this.fetchActiveTorrents()
    return true
  }

  /** 下拉刷新：全量并发（不置 loading，保留旧渲染防闪断） */
  protected async onPullRefresh(): Promise<void> {
    await Promise.all([
      this.fetchDashboardData(),
      this.fetchActiveTorrents(),
      this.fetchTasks(),
      this.fetchTraffic()
    ])
  }

  private async fetchDashboardData(): Promise<void> {
    try {
      const res = await getDashboardData()
      if (res.code === '200' && res.data) {
        this.dashboardData = res.data
        this.hasData = true
      }
    } catch (e) {
      // 首载失败提示并落空态；轮询失败保持上一轮快照
      if (!this.hasData) {
        this.$message.error(extractErrorMessage(e))
      }
    }
  }

  private async fetchActiveTorrents(): Promise<void> {
    try {
      const res = await getActiveTorrents()
      if (res.code === '200' && Array.isArray(res.data)) {
        this.activeTorrents = res.data
      }
    } catch {
      // 轮询失败保持上一轮快照，不打断 UI
    }
  }

  private async fetchTasks(): Promise<void> {
    try {
      const res = await getTaskList({ page: 1, limit: 100 })
      const data = res.data
      const list = data?.list || data?.data || data?.items || []
      this.taskList = list
    } catch {
      // 静默降级：任务卡显示空态
    }
  }

  /** 近 24h 流量：分钟级 raw → 小时分桶积分（与桌面 M-2 口径一致） */
  private async fetchTraffic(): Promise<void> {
    this.trafficLoading = true
    try {
      const res = await getReportsSpeedHistory('24h')
      if (res.code === '200' && res.data?.series) {
        this.trafficResult = bucketSpeedHistoryByHour(res.data.series)
      }
    } catch {
      // 轮询失败保持上一轮分桶
    } finally {
      this.trafficLoading = false
    }
  }

  // ==================== 定时器 ====================

  private startTimers(): void {
    // 低频定时器带前台门控（SpeedPollingMixin 只管 3s 链）
    this.dashboardTimer = window.setInterval(() => {
      if (!document.hidden) this.fetchDashboardData()
    }, DASHBOARD_REFRESH_MS)
    this.taskTimer = window.setInterval(() => {
      if (!document.hidden) this.fetchTasks()
    }, TASK_REFRESH_MS)
    this.trafficTimer = window.setInterval(() => {
      if (!document.hidden) this.fetchTraffic()
    }, TRAFFIC_REFRESH_MS)
  }

  private stopTimers(): void {
    for (const timer of [this.dashboardTimer, this.taskTimer, this.trafficTimer]) {
      if (timer) clearInterval(timer)
    }
    this.dashboardTimer = null
    this.taskTimer = null
    this.trafficTimer = null
  }

  // ==================== 导航 ====================

  private navigateTo(path: string): void {
    this.$router.push(path).catch(() => undefined)
  }

  /** 空态 CTA：直达下载器页并自动弹新增表单（沿用旧页语义） */
  private goAddDownloader(): void {
    this.$router
      .replace({ path: '/m/downloader', query: { create: '1' } })
      .catch(() => undefined)
  }

  private speedText(bytesPerSec: number): string {
    return formatSpeed(bytesPerSec || 0) || '0 B/s'
  }
}
</script>

<style lang="scss" scoped>
.m-hint {
  padding: 40px 0;
  text-align: center;
  font-size: 13px;
  color: var(--color-text-tertiary, #909399);
}

// KPI 2×2：卡内数值比桌面单行四列收紧一档
.m-kpi-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.m-kpi-grid ::v-deep .dash-kpi-value {
  font-size: 24px;
}

.m-kpi-grid ::v-deep .dash-kpi-dual {
  gap: 10px;

  .kv .v {
    font-size: 17px;
  }
}

// widget 纵向卡片流
.m-widget-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
}

.m-widget-stack ::v-deep .dash-widget-body {
  padding: 10px 12px 12px;
}

.m-widget-stack ::v-deep .dash-hero-stats {
  gap: 16px;

  .hs .v {
    font-size: 22px;
  }
}

.m-view-all {
  width: 100%;
  margin-top: 8px;
  border: 0;
  background: var(--color-bg-tertiary, #f5f7fa);
  border-radius: var(--radius-md, 8px);
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12.5px;
  font-family: inherit;
  color: var(--color-primary, #059669);
  cursor: pointer;
  transition: var(--transition-base, background 0.2s);

  .lucide-icon {
    width: 14px;
    height: 14px;
  }

  &:active {
    background: var(--color-bg-hover, #ebeef5);
  }
}

.m-empty-cta {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 18px 0;
}

.m-empty-text {
  font-size: 12.5px;
  color: var(--color-text-tertiary, #909399);
  text-align: center;
}

.m-cta-btn {
  border: 1px solid var(--color-primary, #059669);
  background: transparent;
  color: var(--color-primary, #059669);
  border-radius: var(--radius-md, 8px);
  padding: 7px 16px;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: var(--transition-base, background 0.2s);

  &:active {
    background: var(--color-primary-lightest, rgba(5, 150, 105, 0.08));
  }
}
</style>
