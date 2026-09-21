<template>
  <div class="m-dashboard">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />
    <div v-if="loading" class="m-hint">加载中…</div>
    <template v-else-if="data">
      <div class="m-card-grid">
        <div class="m-card">
          <div class="m-card-value">{{ torrentStats.downloading }}</div>
          <div class="m-card-label">下载中</div>
        </div>
        <div class="m-card">
          <div class="m-card-value">{{ torrentStats.seeding }}</div>
          <div class="m-card-label">做种中</div>
        </div>
        <div class="m-card">
          <div class="m-card-value">{{ torrentStats.paused }}</div>
          <div class="m-card-label">已暂停</div>
        </div>
        <div class="m-card">
          <div class="m-card-value">{{ downloaderStats.online }}/{{ downloaderStats.total }}</div>
          <div class="m-card-label">下载器在线</div>
        </div>
      </div>

      <div class="m-section">
        <div class="m-section-title">传输速度</div>
        <div class="m-speed-row">
          <span>↓ {{ formatSpeedDisplay(systemStats.total_download_speed) }}</span>
          <span>↑ {{ formatSpeedDisplay(systemStats.total_upload_speed) }}</span>
        </div>
      </div>

      <div class="m-section">
        <div class="m-section-title">下载器</div>
        <template v-if="downloaderList.length">
          <div
            v-for="d in downloaderList"
            :key="d.downloader_id"
            class="m-dl-card"
            :class="{'is-offline': d.status === 'offline'}"
            role="button"
            tabindex="0"
            :aria-label="`查看${d.nickname}详情`"
            @click="openDownloader"
            @keypress.enter="openDownloader"
          >
            <div class="m-dl-card-head">
              <div class="m-dl-card-name">
                <span class="m-dl-badge" :class="d.status"></span>
                <span>{{ d.nickname }}</span>
              </div>
              <span class="m-dl-card-type">{{ getDownloaderTypeLabel(d.downloader_type) }}</span>
            </div>
            <div class="m-dl-card-stats">
              <div class="m-dl-stat">
                <div class="m-dl-stat-value">{{ d.downloading }}</div>
                <div class="m-dl-stat-label">下载中</div>
              </div>
              <div class="m-dl-stat">
                <div class="m-dl-stat-value">{{ d.seeding }}</div>
                <div class="m-dl-stat-label">做种</div>
              </div>
              <div class="m-dl-stat">
                <div class="m-dl-stat-value">{{ d.paused }}</div>
                <div class="m-dl-stat-label">暂停</div>
              </div>
              <div v-if="d.status === 'online'" class="m-dl-stat">
                <div class="m-dl-stat-value m-dl-stat-value--speed">↓{{ formatSpeedDisplay(d.download_speed) }}</div>
                <div class="m-dl-stat-value m-dl-stat-value--speed">↑{{ formatSpeedDisplay(d.upload_speed) }}</div>
                <div class="m-dl-stat-label">速度</div>
              </div>
              <div v-else class="m-dl-stat">
                <div class="m-dl-stat-value">--</div>
                <div class="m-dl-stat-label">离线</div>
              </div>
            </div>
          </div>
        </template>
        <!-- 空状态引导：首启用户一步直达新增下载器 -->
        <div v-else class="m-dl-empty">
          <div class="m-dl-empty-text">还没有下载器，添加后即可管理种子</div>
          <el-button size="small" type="primary" plain @click="goAddDownloader">去添加下载器</el-button>
        </div>
      </div>

      <div class="m-footer-meta">
        v{{ systemStats.version || '-' }} · 运行 {{ systemStats.uptime_display || '-' }}
      </div>
    </template>
    <div v-else class="m-hint">暂无数据</div>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import { getDashboardData } from '@/api/dashboard'
import { DashboardData, DownloaderListItem, DownloaderStats, SystemStats, TorrentStats } from '@/types/dashboard'
import { extractErrorMessage, formatSpeed } from '@/utils/formatters'
import SpeedPollingMixin from '@/views/torrents/mixins/speedPolling'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'

/**
 * 移动仪表盘（Phase 4 M1）：复用桌面 /dashboard API 的卡片化展示 + 下拉刷新。
 *
 * 2026-08-28 UX 增强：15s 静默自动刷新（SpeedPollingMixin 复用，visibilitychange
 * 后台暂停；silent 不置 loading 防整页闪断）；下载器空列表显示"去添加下载器"
 * CTA（直达 /m/downloader?create=1）；移除底部刷新按钮（下拉+自动刷新覆盖）。
 */
@Component({
  name: 'MobileDashboard',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileDashboard extends Mixins(PullToRefresh, SpeedPollingMixin) {
  private loading = false
  private data: DashboardData | null = null

  /** 仪表盘自动刷新节奏（mixin 默认 1s 的省电版） */
  protected speedPollIntervalMs = 15000

  // 模板经 vue-jest(buble) 编译，不支持 ?. 与 ??，字段兜底须收敛到 computed
  private get torrentStats(): TorrentStats {
    return this.data?.torrents ?? { active: 0, downloading: 0, seeding: 0, paused: 0 }
  }

  private get downloaderStats(): DownloaderStats {
    return this.data?.downloaders ?? { total: 0, online: 0, offline: 0 }
  }

  private get systemStats(): SystemStats {
    return this.data?.system ?? {
      uptime: 0,
      uptime_display: '-',
      version: '-',
      total_download_speed: 0,
      total_upload_speed: 0
    }
  }

  private get downloaderList(): DownloaderListItem[] {
    return this.data?.downloader_list ?? []
  }

  mounted(): void {
    this.load()
    this.startSpeedPolling(false)
  }

  beforeDestroy(): void {
    this.stopSpeedPolling()
  }

  protected async onPullRefresh(): Promise<void> {
    // 指示条由 pullRefreshing 驱动，不额外置 loading（防整页闪"加载中…"）
    await this.load(true)
  }

  /** SpeedPollingMixin 轮询体：静默刷新（保留旧数据渲染，不闪 loading） */
  protected async loadActiveSpeed(): Promise<boolean> {
    await this.load(true)
    return true
  }

  private async load(silent = false): Promise<void> {
    if (silent) {
      await this.fetchData()
    } else {
      this.loading = true
      try {
        await this.fetchData()
      } finally {
        this.loading = false
      }
    }
  }

  private async fetchData(): Promise<void> {
    try {
      const res = await getDashboardData()
      if (res.code === '200' && res.data) {
        this.data = res.data
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    }
  }

  // 穿透：下载器卡片点击进入移动下载器监控页（测试连接/同步/设置入口）
  private openDownloader(): void {
    this.$router.push('/m/downloader')
  }

  // 空状态 CTA：直达下载器页并自动弹新增表单
  private goAddDownloader(): void {
    this.$router
      .replace({ path: '/m/downloader', query: { create: '1' } })
      .catch(() => undefined)
  }

  private getDownloaderTypeLabel(type: number): string {
    return type === 1 ? 'Transmission' : 'qBittorrent'
  }

  // 后端速度为 bytes/s，复用桌面端 formatSpeed 语义；0 显示 0 B/s
  private formatSpeedDisplay(value?: number | null): string {
    if (value === null || value === undefined) return '--'
    return formatSpeed(value) || '0 B/s'
  }
}
</script>

<style scoped>
.m-card-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.m-card {
  background: #fff;
  border-radius: 8px;
  padding: 14px 12px;
  text-align: center;
}

.m-card-value {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}

.m-card-label {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.m-section {
  margin-top: 12px;
  background: #fff;
  border-radius: 8px;
  padding: 12px;
}

.m-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.m-speed-row {
  display: flex;
  justify-content: space-between;
  font-size: 15px;
  color: #303133;
}

.m-dl-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.m-dl-card:focus {
  outline: none;
  border-color: #059669;
}

.m-dl-card:last-child {
  margin-bottom: 0;
}

.m-dl-card.is-offline {
  background: #fafafa;
}

.m-dl-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.m-dl-card-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-dl-badge {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.m-dl-badge.online {
  background: #059669;
}

.m-dl-badge.offline {
  background: #c0c4cc;
}

.m-dl-card-type {
  font-size: 11px;
  color: #909399;
  background: #f4f4f5;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.m-dl-card-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}

.m-dl-stat {
  text-align: center;
  min-width: 0;
}

.m-dl-stat-value {
  font-size: 15px;
  font-weight: 700;
  color: #059669;
}

.m-dl-stat-value--speed {
  font-size: 11px;
  font-weight: 600;
  color: #606266;
  line-height: 1.4;
}

.m-dl-stat-label {
  font-size: 10px;
  color: #909399;
  margin-top: 2px;
}

.m-footer-meta {
  margin-top: 12px;
  text-align: center;
  font-size: 12px;
  color: #c0c4cc;
}

/* 下载器空状态引导（首启直达新增） */
.m-dl-empty {
  background: #fff;
  border-radius: 8px;
  padding: 20px 12px;
  text-align: center;
}

.m-dl-empty-text {
  font-size: 13px;
  color: #909399;
  margin-bottom: 12px;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
