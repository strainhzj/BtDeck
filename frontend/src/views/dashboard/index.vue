<template>
  <div class="dashboard-container">
    <!-- 头部 -->
    <div class="dashboard-header">
      <div class="dashboard-header-info">
        <h1 class="dashboard-title">数据仪表盘</h1>
        <p class="dashboard-subtitle">今天是 {{ currentDate }}</p>
      </div>
      <div class="dashboard-actions">
        <!-- <el-button @click="refreshData">刷新数据</el-button> -->
        <!-- <el-button type="primary" @click="exportReport">导出报告</el-button> -->
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div
        class="stat-card"
        @click="navigateTo('/downloader/index')"
        role="button"
        tabindex="0"
        aria-label="查看下载器管理"
        @keypress.enter="navigateTo('/downloader/index')"
      >
        <div class="stat-card-header">
          <span class="stat-card-title">下载器</span>
          <div class="stat-card-icon primary">📡</div>
        </div>
        <div class="stat-card-value">{{ formatRatio(dashboard.downloaders.online, dashboard.downloaders.total) }}</div>
        <div class="stat-card-progress">
          <div class="stat-card-progress-bar" :style="{width: downloaderProgress + '%'}"></div>
        </div>
        <div
          class="stat-card-trend"
          :class="{up: hasDashboardData && dashboard.downloaders.online === dashboard.downloaders.total}"
        >
          <span v-if="hasDashboardData && dashboard.downloaders.total > 0 && dashboard.downloaders.online === dashboard.downloaders.total">全部在线</span>
          <span v-else-if="hasDashboardData">{{ dashboard.downloaders.online }} 在线</span>
          <span v-else>--</span>
        </div>
      </div>

      <div
        class="stat-card"
        @click="navigateTo('/torrents/index')"
        role="button"
        tabindex="0"
        aria-label="查看种子管理"
        @keypress.enter="navigateTo('/torrents/index')"
      >
        <div class="stat-card-header">
          <span class="stat-card-title">活跃种子</span>
          <div class="stat-card-icon success">📥</div>
        </div>
        <div class="stat-card-value">{{ formatStatValue(dashboard.torrents.active) }}</div>
        <div class="stat-card-progress">
          <div class="stat-card-progress-bar" :style="{width: torrentProgress + '%'}"></div>
        </div>
      </div>

      <div
        class="stat-card"
        @click="navigateTo('/tasks/index')"
        role="button"
        tabindex="0"
        aria-label="查看定时任务"
        @keypress.enter="navigateTo('/tasks/index')"
      >
        <div class="stat-card-header">
          <span class="stat-card-title">定时任务</span>
          <div class="stat-card-icon warning">⏰</div>
        </div>
        <div class="stat-card-value">{{ formatRatio(dashboard.tasks.running, dashboard.tasks.total) }}</div>
        <div class="stat-card-progress">
          <div class="stat-card-progress-bar" :style="{width: taskProgress + '%'}"></div>
        </div>
        <div class="stat-card-trend">
          <span>运行中</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-card-header">
          <span class="stat-card-title">系统状态</span>
          <div class="stat-card-icon info">✓</div>
        </div>
        <div class="stat-card-value">{{ systemHealthDisplay }}<span v-if="hasDashboardData">%</span></div>
        <div class="stat-card-progress">
          <div class="stat-card-progress-bar" :style="{width: systemHealth + '%'}"></div>
        </div>
        <div class="stat-card-trend up">
          <span>运行时间</span>
          <span>{{ systemUptime }}</span>
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 下载器状态 -->
      <div class="content-card">
        <div class="content-card-header">
          <h2 class="content-card-title">下载器状态</h2>
          <el-link type="primary" @click="navigateTo('/downloader/index')">管理 →</el-link>
        </div>
        <div class="downloader-grid">
          <div
            v-for="downloader in dashboard.downloader_list"
            :key="downloader.downloader_id"
            class="downloader-card"
            @click="viewDownloader(downloader)"
            role="button"
            tabindex="0"
            :aria-label="`查看${downloader.nickname}详情`"
            @keypress.enter="viewDownloader(downloader)"
          >
            <div class="downloader-card-header">
              <div>
                <div class="downloader-card-name">{{ downloader.nickname }}</div>
                <span class="downloader-card-type">{{ getDownloaderTypeLabel(downloader.downloader_type) }}</span>
              </div>
              <div class="downloader-status-badge" :class="downloader.status">
                <span>●</span>
                <span>{{ downloader.status === 'online' ? '在线' : '离线' }}</span>
              </div>
            </div>
            <div v-if="downloader.status === 'online'" class="downloader-card-stats">
              <div class="downloader-mini-stat">
                <div class="downloader-mini-stat-value">{{ formatStatValue(downloader.downloading) }}</div>
                <div class="downloader-mini-stat-label">下载中</div>
              </div>
              <div class="downloader-mini-stat">
                <div class="downloader-mini-stat-value">{{ formatStatValue(downloader.seeding) }}</div>
                <div class="downloader-mini-stat-label">做种中</div>
              </div>
            </div>
            <div v-else class="downloader-card-stats">
              <div class="downloader-mini-stat">
                <div class="downloader-mini-stat-value">-</div>
                <div class="downloader-mini-stat-label">离线</div>
              </div>
            </div>
          </div>

          <!-- 添加下载器占位卡片 -->
          <div
            class="downloader-card downloader-card-add"
            @click="navigateTo('/downloader/index')"
            role="button"
            tabindex="0"
            aria-label="添加下载器"
            @keypress.enter="navigateTo('/downloader/index')"
          >
            <div class="add-icon">➕</div>
            <div class="add-text">添加下载器</div>
          </div>
        </div>
      </div>

      <!-- 活动时间线 -->
      <div class="content-card">
        <div class="content-card-header">
          <h2 class="content-card-title">最近活动</h2>
          <el-link type="primary" @click="viewAllActivities">查看全部 →</el-link>
        </div>
        <div class="activity-timeline">
          <div v-if="dashboard.activities.length === 0" class="activity-empty">暂无活动记录</div>
          <div v-else>
            <div v-for="(activity, index) in dashboard.activities" :key="index" class="activity-item">
              <div class="activity-time">{{ activity.time }}</div>
              <div class="activity-content">
                <span>{{ activity.action }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="content-card quick-actions-section">
      <div class="content-card-header">
        <h2 class="content-card-title">快捷操作</h2>
      </div>
      <div class="quick-actions">
        <div
          class="quick-action-item"
          @click="navigateTo('/downloader/index')"
          role="button"
          tabindex="0"
          aria-label="添加下载器"
          @keypress.enter="navigateTo('/downloader/index')"
        >
          <div class="quick-action-icon">➕</div>
          <div class="quick-action-label">添加下载器</div>
        </div>
        <div
          class="quick-action-item"
          @click="navigateTo('/tasks/index')"
          role="button"
          tabindex="0"
          aria-label="新建任务"
          @keypress.enter="navigateTo('/tasks/index')"
        >
          <div class="quick-action-icon">📥</div>
          <div class="quick-action-label">新建任务</div>
        </div>
        <div
          class="quick-action-item"
          @click="navigateTo('/torrents/index')"
          role="button"
          tabindex="0"
          aria-label="搜索种子"
          @keypress.enter="navigateTo('/torrents/index')"
        >
          <div class="quick-action-icon">🔍</div>
          <div class="quick-action-label">搜索种子</div>
        </div>
        <div
          class="quick-action-item"
          @click="viewLogs"
          role="button"
          tabindex="0"
          aria-label="查看日志"
          @keypress.enter="viewLogs()"
        >
          <div class="quick-action-icon">📝</div>
          <div class="quick-action-label">查看日志</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { UserModule } from '@/store/modules/user'
import { getDashboardData } from '@/api/dashboard'
import { DashboardData, DownloaderListItem } from '@/types/dashboard'
import { debounce } from 'lodash-es'
import { Message } from 'element-ui'

@Component({
  name: 'Dashboard'
})
export default class extends Vue {
  // Dashboard data
  private loading = false
  private hasDashboardData = false
  private dashboardData: DashboardData | null = null
  private refreshTimer: number | null = null
  private emptyDashboardData: DashboardData = {
    downloaders: { total: 0, online: 0, offline: 0 },
    torrents: { active: 0, downloading: 0, seeding: 0, paused: 0 },
    tasks: { total: 0, running: 0, stopped: 0 },
    system: { uptime: 0, uptime_display: '--', version: '--' },
    downloader_list: [],
    activities: []
  }

  get name() {
    return UserModule.name
  }

  get roles() {
    return UserModule.roles
  }

  get currentDate() {
    const now = new Date()
    const options: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }
    return now.toLocaleDateString('zh-CN', options)
  }

  get dashboard(): DashboardData {
    return this.dashboardData || this.emptyDashboardData
  }

  get downloaderProgress() {
    if (!this.hasDashboardData) {
      return 0
    }
    const total = this.dashboard.downloaders.total
    return total > 0
      ? Math.round((this.dashboard.downloaders.online / total) * 100)
      : 0
  }

  get torrentProgress() {
    if (!this.hasDashboardData) {
      return 0
    }
    const active = this.dashboard.torrents.active
    return active > 0
      ? Math.round((this.dashboard.torrents.downloading / active) * 100)
      : 0
  }

  get taskProgress() {
    if (!this.hasDashboardData) {
      return 0
    }
    const total = this.dashboard.tasks.total
    return total > 0
      ? Math.round((this.dashboard.tasks.running / total) * 100)
      : 0
  }

  get systemUptime() {
    return this.hasDashboardData ? this.dashboard.system.uptime_display : '--'
  }

  get systemHealth() {
    return this.hasDashboardData ? 100 : 0
  }

  get systemHealthDisplay() {
    return this.hasDashboardData ? String(this.systemHealth) : '--'
  }

  created() {
    this.fetchDashboardData()
    this.startAutoRefresh()
  }

  beforeDestroy() {
    this.stopAutoRefresh()
  }

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

  private startAutoRefresh() {
    this.refreshTimer = window.setInterval(() => {
      this.fetchDashboardData()
    }, 30000)
  }

  private stopAutoRefresh() {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer)
      this.refreshTimer = null
    }
  }

  // 路由导航
  private navigateTo(path: string) {
    this.$router.push(path)
  }

  // 刷新数据 - 更新仪表盘数据
  private refreshData = debounce(async() => {
    try {
      await this.fetchDashboardData()
      Message({
        message: '数据刷新成功',
        type: 'success',
        duration: 2000
      })
    } catch (error) {
      Message({
        message: '数据刷新失败',
        type: 'error',
        duration: 2000
      })
    }
  }, 300)

  // 导出报告
  private exportReport() {
    Message({
      message: '报告导出功能开发中',
      type: 'info',
      duration: 2000
    })
  }

  // 查看下载器详情
  private viewDownloader(downloader: DownloaderListItem) {
    if (downloader.status === 'offline') {
      Message({
        message: '下载器离线，无法查看',
        type: 'warning',
        duration: 2000
      })
      return
    }
    this.navigateTo('/downloader/index')
  }

  // 查看全部活动
  private viewAllActivities() {
    Message({
      message: '活动详情功能开发中',
      type: 'info',
      duration: 2000
    })
  }

  // 查看日志
  private viewLogs() {
    this.navigateTo('/logs/audit')
  }

  private formatStatValue(value?: number | null): string {
    if (!this.hasDashboardData) {
      return '--'
    }
    if (value === null || value === undefined) {
      return '--'
    }
    return String(value)
  }

  private formatRatio(current?: number | null, total?: number | null): string {
    if (!this.hasDashboardData) {
      return '--/--'
    }
    const safeCurrent = current ?? 0
    const safeTotal = total ?? 0
    return `${safeCurrent}/${safeTotal}`
  }

  private getDownloaderTypeLabel(type: number): string {
    return type === 1 ? 'Transmission' : 'qBittorrent'
  }
}
</script>


<style lang="scss" scoped>
.dashboard-container {
  max-width: 1920px;
  margin: 0 auto;
  padding: var(--spacing-xl);
}

// 头部
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xl);
}

.dashboard-header-info {
  flex: 1;
}

.dashboard-title {
  font-size: 32px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xs);
}

.dashboard-subtitle {
  font-size: 14px;
  color: var(--color-text-secondary);
}

.dashboard-actions {
  display: flex;
  gap: var(--spacing-md);
}

// 统计卡片
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-xl);
}

.stat-card {
  background: linear-gradient(135deg, var(--color-bg-primary) 0%, var(--color-bg-secondary) 100%);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-lg);
  transition: all var(--transition-base);
  cursor: pointer;
  position: relative;
  overflow: true;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, var(--color-primary), var(--color-primary-light));
    opacity: 0;
    transition: opacity var(--transition-base);
  }

  &:hover::before {
    opacity: 1;
  }

  &:hover {
    box-shadow: var(--shadow-lg);
    border-color: var(--color-border-focus);
    transform: translateY(-4px);
  }

  &:focus {
    outline: none;
    border-color: var(--color-border-focus);
    box-shadow: 0 0 0 3px var(--color-primary-lightest);
  }
}

.stat-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
}

.stat-card-title {
  font-size: 14px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.stat-card-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  box-shadow: var(--shadow-sm);

  &.primary {
    background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
    color: white;
  }

  &.success {
    background: linear-gradient(135deg, var(--color-success), #34D399);
    color: white;
  }

  &.warning {
    background: linear-gradient(135deg, var(--color-warning), #FBBF24);
    color: white;
  }

  &.info {
    background: linear-gradient(135deg, var(--color-info), #60A5FA);
    color: white;
  }
}

.stat-card-value {
  font-size: 40px;
  font-weight: 800;
  background: linear-gradient(135deg, var(--color-text-primary), var(--color-primary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: var(--spacing-sm);
}

.stat-card-progress {
  height: 6px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  overflow: hidden;
  margin-bottom: var(--spacing-sm);
}

.stat-card-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-primary-light));
  border-radius: var(--radius-sm);
  transition: width 1s ease;
}

.stat-card-trend {
  font-size: 12px;
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);

  &.up {
    color: var(--color-success);
  }

  &.down {
    color: var(--color-error);
  }
}

// 主内容区
.main-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-xl);
}

.content-card {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-xl);
  box-shadow: var(--shadow-md);
}

.content-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
}

.content-card-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);

  &::before {
    content: '';
    width: 4px;
    height: 20px;
    background: linear-gradient(180deg, var(--color-primary), var(--color-primary-light));
    border-radius: var(--radius-sm);
  }
}

// 下载器卡片
.downloader-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-md);
}

.downloader-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  transition: all var(--transition-base);
  cursor: pointer;

  &:hover {
    background: var(--color-bg-tertiary);
    border-color: var(--color-primary);
  }

  &:focus {
    outline: none;
    border-color: var(--color-border-focus);
    box-shadow: 0 0 0 3px var(--color-primary-lightest);
  }
}

.downloader-card-add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-style: dashed;
  min-height: 120px;

  .add-icon {
    font-size: 32px;
    margin-bottom: var(--spacing-sm);
  }

  .add-text {
    font-size: 13px;
    font-weight: 600;
    color: var(--color-text-secondary);
  }

  &:hover {
    border-color: var(--color-primary);
    background: var(--color-bg-secondary);

    .add-text {
      color: var(--color-primary);
    }
  }
}

.downloader-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
}

.downloader-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.downloader-card-type {
  font-size: 11px;
  color: var(--color-text-tertiary);
  background: var(--color-bg-tertiary);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.downloader-status-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: var(--radius-sm);

  &.online {
    background: var(--color-primary-lightest);
    color: var(--color-primary);
  }

  &.offline {
    background: #FEE2E2;
    color: var(--color-error);
  }
}

.downloader-card-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-sm);
}

.downloader-mini-stat {
  background: var(--color-bg-primary);
  padding: var(--spacing-sm);
  border-radius: var(--radius-md);
}

.downloader-mini-stat-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-primary);
}

.downloader-mini-stat-label {
  font-size: 11px;
  color: var(--color-text-tertiary);
}

// 活动时间线
.activity-timeline {
  position: relative;
  padding-left: var(--spacing-lg);
}

.activity-timeline::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, var(--color-primary), var(--color-primary-lightest));
  border-radius: var(--radius-sm);
}

.activity-item {
  position: relative;
  padding-bottom: var(--spacing-lg);

  &::before {
    content: '';
    position: absolute;
    left: -23px;
    top: 6px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--color-primary);
    border: 3px solid var(--color-bg-primary);
    box-shadow: 0 0 0 3px var(--color-primary-lightest);
  }

  &:last-child {
    padding-bottom: 0;
  }
}

.activity-time {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-xs);
  font-weight: 500;
}

.activity-content {
  font-size: 14px;
  color: var(--color-text-primary);
  line-height: 1.6;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-primary);

  .activity-source {
    font-weight: 600;
    color: var(--color-primary);
  }

  .activity-highlight {
    color: var(--color-primary);
    font-weight: 700;
  }
}

.activity-empty {
  font-size: 13px;
  color: var(--color-text-tertiary);
  padding: var(--spacing-sm) 0;
}

// 快捷操作
.quick-actions-section {
  margin-bottom: var(--spacing-xl);
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-md);
}

.quick-action-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-lg);
  background: linear-gradient(135deg, var(--color-bg-secondary), var(--color-bg-tertiary));
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(135deg, var(--color-primary-lightest), transparent);
    opacity: 0;
    transition: opacity var(--transition-base);
  }

  &:hover::before {
    opacity: 1;
  }

  &:hover {
    border-color: var(--color-primary);
    transform: translateY(-4px);
    box-shadow: var(--shadow-md);
  }

  &:focus {
    outline: none;
    border-color: var(--color-border-focus);
    box-shadow: 0 0 0 3px var(--color-primary-lightest);
  }
}

.quick-action-icon {
  font-size: 36px;
  margin-bottom: var(--spacing-sm);
  position: relative;
  z-index: 1;
}

.quick-action-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  position: relative;
  z-index: 1;
}

// 响应式
@media (max-width: 1280px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .main-content {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .dashboard-container {
    padding: var(--spacing-md);
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .quick-actions {
    grid-template-columns: repeat(2, 1fr);
  }

  .downloader-grid {
    grid-template-columns: 1fr;
  }

  .dashboard-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-md);
  }
}
</style>
