<template>
  <div
    class="dashboard-container dashboard-page"
    :class="{'dash-page--editing': editing}"
  >
    <!-- 头部 -->
    <div class="dashboard-header">
      <div class="dashboard-header-info">
        <h1 class="dashboard-title">{{ $t('dashboard.title') }}</h1>
        <p class="dashboard-subtitle">{{ $t('dashboard.subtitle', {date: currentDate}) }}</p>
      </div>
      <div class="dashboard-actions">
        <div
          class="dash-seg"
          role="tablist"
          :aria-label="$t('dashboard.preset.label')"
        >
          <button
            v-for="p in presetOptions"
            :key="p"
            type="button"
            role="tab"
            :aria-selected="preset === p"
            :class="{on: preset === p}"
            @click="choosePreset(p)"
          >
            {{ $t(`dashboard.preset.${p}`) }}
          </button>
        </div>
        <el-button
          size="small"
          :class="{'is-active': editing}"
          :data-testid="'edit-layout-btn'"
          @click="toggleEditing()"
        >
          <lucide-icon :icon="editing ? 'check' : 'pencil'" />
          {{ editing ? $t('dashboard.edit.done') : $t('dashboard.edit.button') }}
        </el-button>
        <el-button
          size="small"
          type="primary"
          data-testid="enter-screen-btn"
          @click="enterScreen()"
        >
          <lucide-icon icon="maximize-2" />
          {{ $t('dashboard.screen.enter') }}
        </el-button>
      </div>
    </div>

    <!-- 编辑提示条 -->
    <div class="dash-edit-hint">
      <lucide-icon icon="alert-triangle" />
      <span class="grow">{{ $t('dashboard.edit.hint') }}</span>
      <el-button
        size="mini"
        data-testid="reset-layout-btn"
        @click="resetLayout()"
      >
        {{ $t('dashboard.edit.reset') }}
      </el-button>
    </div>

    <!-- KPI 行（恒显于网格外，不参与预设/编辑） -->
    <section class="dash-kpi-row">
      <KpiCard
        :label="$t('dashboard.kpi.downloaders')"
        icon="server"
        clickable
        :aria-label="$t('dashboard.aria.viewDownloaders')"
        @click="navigateTo('/downloader/index')"
      >
        <template #value>
          {{ hasDashboardData ? dashboard.downloaders.online : '--' }}<small>/ {{ hasDashboardData ? dashboard.downloaders.total : '--' }}</small>
        </template>
        <template #foot>
          <span
            v-if="hasDashboardData"
            :class="['dash-kpi-chip', dashboard.downloaders.online === dashboard.downloaders.total && dashboard.downloaders.total > 0 ? 'up' : 'flat']"
          >
            {{ dashboard.downloaders.online === dashboard.downloaders.total && dashboard.downloaders.total > 0 ? $t('dashboard.allOnline') : $t('dashboard.onlineCount', {count: dashboard.downloaders.online}) }}
          </span>
          <span
            v-else
            class="dash-kpi-chip flat"
          >--</span>
        </template>
      </KpiCard>

      <KpiCard
        :label="$t('dashboard.kpi.activeTorrents')"
        icon="download"
        clickable
        :aria-label="$t('dashboard.aria.viewTorrents')"
        @click="navigateTo('/torrents/index')"
      >
        <template #value>
          {{ hasDashboardData ? dashboard.torrents.active : '--' }}
        </template>
        <template #foot>
          <span class="dash-kpi-chip flat">
            {{ $t('dashboard.kpi.dlSplit', {count: dashboard.torrents.downloading}) }} · {{ $t('dashboard.kpi.sdSplit', {count: dashboard.torrents.seeding}) }}
          </span>
        </template>
      </KpiCard>

      <KpiCard
        :label="$t('dashboard.kpi.enabledTasks')"
        icon="clock"
        clickable
        :aria-label="$t('dashboard.aria.viewTasks')"
        @click="navigateTo('/tasks/index')"
      >
        <template #value>
          {{ hasDashboardData ? dashboard.tasks.enabled : '--' }}<small> {{ $t('dashboard.kpi.enabledUnit') }}</small>
        </template>
        <template #foot>
          <span class="dash-kpi-chip flat">{{ $t('dashboard.kpi.enabledNote') }}</span>
        </template>
      </KpiCard>

      <KpiCard
        :label="$t('dashboard.kpi.systemSpeed')"
        icon="zap"
      >
        <template #value>
          <span />
        </template>
        <template #default>
          <div class="dash-kpi-dual">
            <div class="kv">
              <div
                class="v mono"
                style="color:var(--color-primary)"
              >
                {{ hasDashboardData ? speedText(dashboard.system.total_download_speed) : '--' }}
              </div>
              <div class="l">
                <span
                  class="dash-kpi-dot"
                  style="background:var(--color-primary)"
                />
                {{ $t('dashboard.downloadSpeed') }}
              </div>
            </div>
            <div class="kv">
              <div
                class="v mono"
                style="color:var(--color-info)"
              >
                {{ hasDashboardData ? speedText(dashboard.system.total_upload_speed) : '--' }}
              </div>
              <div class="l">
                <span
                  class="dash-kpi-dot"
                  style="background:var(--color-info)"
                />
                {{ $t('dashboard.uploadSpeed') }}
              </div>
            </div>
          </div>
        </template>
      </KpiCard>
    </section>

    <!-- Widget 网格（12 列 + 预设可见性 + 编辑模式） -->
    <DashboardGrid
      :layout="layout"
      :preset="preset"
      :editing="editing"
      @reorder="onReorder"
      @cycle-width="onCycleWidth"
    >
      <template #health>
        <InstanceHealthCard :list="dashboard.downloader_list" />
      </template>
      <template #spark>
        <SpeedSparkCard :ready="speedReady">
          <span />
        </SpeedSparkCard>
      </template>
      <template #statusPie>
        <StatusDonutCard :buckets="dashboard.torrents.statusBuckets" />
      </template>
      <template #traffic>
        <DailyTrafficCard
          :ready="false"
          :loading="hasDashboardData"
        />
      </template>
      <template #sites>
        <SiteBarsCard :buckets="dashboard.torrents.siteBuckets" />
      </template>
      <template #hot>
        <HotTorrentsCard :torrents="activeTorrents" />
      </template>
      <template #tasks>
        <CronTaskCard :tasks="taskList" />
      </template>
      <template #activity>
        <ActivityTimelineCard :activities="dashboard.activities" />
      </template>
      <template #quick>
        <QuickActionsCard />
      </template>
      <template #radar>
        <RadarCard :list="dashboard.downloader_list" />
      </template>
      <template #tubes>
        <ThroughputTubesCard
          :download-speed="dashboard.system.total_download_speed"
          :upload-speed="dashboard.system.total_upload_speed"
        />
      </template>
      <template #hero>
        <HeroPulseCard
          :download-speed="dashboard.system.total_download_speed"
          :upload-speed="dashboard.system.total_upload_speed"
          :downloading="dashboard.torrents.downloading"
          :seeding="dashboard.torrents.seeding"
          :active-torrents="activeTorrents"
        />
      </template>
    </DashboardGrid>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { getDashboardData } from '@/api/dashboard'
import { getActiveTorrents, ActiveTorrentSpeed } from '@/api/torrents'
import { getTaskList } from '@/api/tasks'
import { ScheduledTask } from '@/api/tasks'
import { DashboardData } from '@/types/dashboard'
import { formatSpeed } from '@/utils/formatters'
import { getLocale } from '@/i18n'
import KpiCard from './components/KpiCard.vue'
import DashboardGrid from './components/DashboardGrid.vue'
import InstanceHealthCard from './components/InstanceHealthCard.vue'
import SpeedSparkCard from './components/SpeedSparkCard.vue'
import StatusDonutCard from './components/StatusDonutCard.vue'
import DailyTrafficCard from './components/DailyTrafficCard.vue'
import SiteBarsCard from './components/SiteBarsCard.vue'
import HotTorrentsCard from './components/HotTorrentsCard.vue'
import CronTaskCard from './components/CronTaskCard.vue'
import ActivityTimelineCard from './components/ActivityTimelineCard.vue'
import QuickActionsCard from './components/QuickActionsCard.vue'
import RadarCard from './components/RadarCard.vue'
import ThroughputTubesCard from './components/ThroughputTubesCard.vue'
import HeroPulseCard from './components/HeroPulseCard.vue'
import {
  DashboardLayoutState,
  PresetKey,
  WidgetId,
  defaultLayout,
  loadLayout,
  nextWidth,
  saveLayout,
  clearLayout
} from './components/dashboardLayout'

const DASHBOARD_REFRESH_MS = 30000
const ACTIVE_POLL_MS = 3000
const TASK_REFRESH_MS = 60000
/** 速度采样：3s × 60 点（W3 速度曲线消费；W2 先累积） */
const SPEED_SAMPLE_MAX = 60

@Component({
  name: 'Dashboard',
  components: {
    KpiCard,
    DashboardGrid,
    InstanceHealthCard,
    SpeedSparkCard,
    StatusDonutCard,
    DailyTrafficCard,
    SiteBarsCard,
    HotTorrentsCard,
    CronTaskCard,
    ActivityTimelineCard,
    QuickActionsCard,
    RadarCard,
    ThroughputTubesCard,
    HeroPulseCard
  }
})
export default class extends Vue {
  private loading = false
  private hasDashboardData = false
  private dashboardData: DashboardData | null = null
  private activeTorrents: ActiveTorrentSpeed[] = []
  private taskList: ScheduledTask[] = []
  /** 速度采样序列 [{t, dl, ul}]（W3 接 echarts 双线渐变面积图） */
  private speedSamples: Array<{ t: number, dl: number, ul: number }> = []

  private layout: DashboardLayoutState = defaultLayout()
  private preset: PresetKey = 'overview'
  private editing = false

  private dashboardTimer: number | null = null
  private activeTimer: number | null = null
  private taskTimer: number | null = null

  private readonly presetOptions: PresetKey[] = ['overview', 'focus', 'pulse', 'custom']

  private emptyDashboardData: DashboardData = {
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

  get currentDate() {
    const now = new Date()
    const options: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }
    return now.toLocaleDateString(getLocale() === 'en' ? 'en-US' : 'zh-CN', options)
  }

  get dashboard(): DashboardData {
    return this.dashboardData || this.emptyDashboardData
  }

  /** W3 速度曲线就绪条件：采样点 ≥2；W2 阶段恒为空态占位 */
  get speedReady(): boolean {
    return this.speedSamples.length >= 2
  }

  created() {
    this.restoreLayout()
    this.fetchDashboardData()
    this.fetchActiveTorrents()
    this.fetchTasks()
    this.startTimers()
  }

  beforeDestroy() {
    this.stopTimers()
  }

  // ==================== 数据获取 ====================

  private async fetchDashboardData() {
    this.loading = true
    try {
      const res = await getDashboardData()
      if (res.code === '200' && res.data) {
        this.dashboardData = res.data
        this.hasDashboardData = true
      } else {
        this.handleEmptyState()
      }
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error('获取仪表盘数据失败:', error)
      this.handleEmptyState()
    } finally {
      this.loading = false
    }
  }

  private handleEmptyState() {
    this.dashboardData = this.emptyDashboardData
    this.hasDashboardData = false
  }

  private async fetchActiveTorrents() {
    try {
      const res = await getActiveTorrents()
      if (res.code === '200' && Array.isArray(res.data)) {
        this.activeTorrents = res.data
      }
    } catch {
      // 轮询失败保持上一轮快照，不打断 UI
    }
  }

  private async fetchTasks() {
    try {
      const res = await getTaskList({ page: 1, limit: 100 })
      const data = res.data
      const list = data?.list || data?.data || data?.items || []
      this.taskList = list
    } catch {
      // 静默降级：任务卡显示空态
    }
  }

  private startTimers() {
    this.dashboardTimer = window.setInterval(() => {
      this.fetchDashboardData()
    }, DASHBOARD_REFRESH_MS)
    this.activeTimer = window.setInterval(() => {
      this.fetchActiveTorrents()
      this.pushSpeedSample()
    }, ACTIVE_POLL_MS)
    this.taskTimer = window.setInterval(() => {
      this.fetchTasks()
    }, TASK_REFRESH_MS)
  }

  private stopTimers() {
    for (const timer of [this.dashboardTimer, this.activeTimer, this.taskTimer]) {
      if (timer) clearInterval(timer)
    }
    this.dashboardTimer = null
    this.activeTimer = null
    this.taskTimer = null
  }

  /** 3s 采样：总速度累积进 60 点滚动窗（W3 速度曲线数据源） */
  private pushSpeedSample() {
    const system = this.dashboard.system
    this.speedSamples.push({
      t: Date.now(),
      dl: system.total_download_speed || 0,
      ul: system.total_upload_speed || 0
    })
    if (this.speedSamples.length > SPEED_SAMPLE_MAX) {
      this.speedSamples.shift()
    }
  }

  // ==================== 布局状态机（预设/编辑/持久化） ====================

  private restoreLayout() {
    const saved = loadLayout(window.localStorage)
    this.layout = saved || defaultLayout()
    this.preset = this.layout.preset
    // 持久化的 custom 预设不自动恢复编辑模式（进入页面总是浏览态）
    this.editing = false
  }

  private persist() {
    this.layout = { ...this.layout, preset: this.preset }
    saveLayout(window.localStorage, this.layout)
  }

  private choosePreset(p: PresetKey) {
    this.preset = p
    if (p === 'custom' && !this.editing) {
      this.editing = true
    }
    if (p !== 'custom' && this.editing) {
      this.editing = false
    }
    this.persist()
  }

  private toggleEditing() {
    this.editing = !this.editing
    if (this.editing && this.preset !== 'custom') {
      this.preset = 'custom'
    }
    this.persist()
  }

  private onReorder(order: WidgetId[]) {
    this.layout = { ...this.layout, order }
    this.persist()
  }

  private onCycleWidth(id: WidgetId) {
    const spans = { ...this.layout.spans }
    spans[id] = nextWidth(spans[id] || 6)
    this.layout = { ...this.layout, spans }
    this.persist()
  }

  private resetLayout() {
    clearLayout(window.localStorage)
    this.layout = defaultLayout()
    this.preset = 'overview'
    this.editing = false
  }

  // ==================== 导航 ====================

  private navigateTo(path: string) {
    this.$router.push(path).catch(() => undefined)
  }

  private enterScreen() {
    // W4 交付沉浸页路由 /dashboard/screen（一期 W2 先落入口按钮）
    this.navigateTo('/dashboard/screen')
  }

  private speedText(bytesPerSec: number): string {
    return formatSpeed(bytesPerSec || 0) || '0 B/s'
  }
}
</script>

<style lang="scss" scoped>
.dashboard-container {
  max-width: 1920px;
  margin: 0 auto;
  padding: var(--spacing-xl);
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.dashboard-header-info {
  flex: 1;
  min-width: 220px;
}

.dashboard-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xs);
}

.dashboard-subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.dashboard-actions {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  flex-wrap: wrap;

  .lucide-icon {
    width: 14px;
    height: 14px;
    margin-right: 4px;
  }
}
</style>
