<template>
  <div class="m-dashboard">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />
    <div v-if="loading" class="m-hint">加载中…</div>
    <template v-else-if="data">
      <div class="m-card-grid">
        <div class="m-card">
          <div class="m-card-value">{{ data.torrent_stats?.downloading ?? 0 }}</div>
          <div class="m-card-label">下载中</div>
        </div>
        <div class="m-card">
          <div class="m-card-value">{{ data.torrent_stats?.seeding ?? 0 }}</div>
          <div class="m-card-label">做种中</div>
        </div>
        <div class="m-card">
          <div class="m-card-value">{{ data.torrent_stats?.paused ?? 0 }}</div>
          <div class="m-card-label">已暂停</div>
        </div>
        <div class="m-card">
          <div class="m-card-value">{{ data.downloader_stats?.online ?? 0 }}/{{ data.downloader_stats?.total ?? 0 }}</div>
          <div class="m-card-label">下载器在线</div>
        </div>
      </div>

      <div class="m-section">
        <div class="m-section-title">传输速度</div>
        <div class="m-speed-row">
          <span>↓ {{ formatSpeedValue(data.system_stats?.total_download_speed) }}</span>
          <span>↑ {{ formatSpeedValue(data.system_stats?.total_upload_speed) }}</span>
        </div>
      </div>

      <div v-if="downloaders.length" class="m-section">
        <div class="m-section-title">下载器</div>
        <div v-for="d in downloaders" :key="d.downloader_id" class="m-row">
          <span class="m-row-name">{{ d.nickname }}</span>
          <span class="m-row-meta">↓{{ d.downloading }} 做种{{ d.seeding }}</span>
        </div>
      </div>

      <div class="m-footer-meta">
        v{{ data.system_stats?.version || '-' }} · 运行 {{ data.system_stats?.uptime_display || '-' }}
      </div>
    </template>
    <div v-else class="m-hint">暂无数据</div>
    <el-button class="m-refresh" size="small" :loading="loading" @click="load">刷新</el-button>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import { getDashboardData } from '@/api/dashboard'
import { DashboardData } from '@/types/dashboard'
import { extractErrorMessage } from '@/utils/formatters'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'

/** 移动仪表盘（Phase 4 M1）：复用桌面 /dashboard API 的卡片化展示 + 下拉刷新 */
@Component({
  name: 'MobileDashboard',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileDashboard extends Mixins(PullToRefresh) {
  private loading = false
  private data: DashboardData | null = null

  private get downloaders(): DashboardData['downloaders'] {
    return this.data?.downloaders ?? []
  }

  mounted(): void {
    this.load()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.load()
  }

  private async load(): Promise<void> {
    this.loading = true
    try {
      const res = await getDashboardData()
      if (res.code === '200' && res.data) {
        this.data = res.data
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private formatSpeedValue(value?: number): string {
    if (value === undefined || value === null) return '-'
    if (value >= 1024) return `${(value / 1024).toFixed(2)} MB/s`
    return `${value} KB/s`
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

.m-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #f2f6fc;
}

.m-row:last-child {
  border-bottom: none;
}

.m-row-name {
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-row-meta {
  flex-shrink: 0;
  color: #909399;
  font-size: 12px;
}

.m-footer-meta {
  margin-top: 12px;
  text-align: center;
  font-size: 12px;
  color: #c0c4cc;
}

.m-refresh {
  display: flex;
  margin: 12px auto 0;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
