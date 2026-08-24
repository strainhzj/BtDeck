<template>
  <div class="m-torrent-detail">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />

    <div v-if="loading" class="m-hint">加载中…</div>

    <div v-else-if="!torrent" class="m-detail-empty">
      <div class="m-hint">未找到种子（可能已被删除或来源列表未加载）</div>
      <el-button size="small" @click="backToList">返回列表</el-button>
    </div>

    <template v-else>
      <div class="m-detail-card">
        <div class="m-detail-name">{{ torrent.name }}</div>
        <div class="m-detail-meta">
          <el-tag size="mini" :type="statusTagType(status)">{{ statusLabel(status) }}</el-tag>
          <span class="m-detail-meta-text">{{ downloaderName }}</span>
        </div>
        <el-progress
          :percentage="progressOf"
          :status="status === 'error' ? 'exception' : undefined"
          :stroke-width="8"
          :show-text="false"
        />
        <div class="m-detail-progress-text">{{ progressOf.toFixed(1) }}%</div>
        <div class="m-detail-speed">
          <span>↓ {{ speedText(downloadSpeed) }}</span>
          <span>↑ {{ speedText(uploadSpeed) }}</span>
        </div>
      </div>

      <div class="m-detail-card m-detail-grid">
        <div class="m-detail-cell">
          <div class="m-cell-label">大小</div>
          <div class="m-cell-value">{{ formatSize(size) }}</div>
        </div>
        <div class="m-detail-cell">
          <div class="m-cell-label">分享率</div>
          <div class="m-cell-value">{{ ratioText }}</div>
        </div>
        <div class="m-detail-cell">
          <div class="m-cell-label">做种 / 连接</div>
          <div class="m-cell-value">{{ seedsText }} / {{ peersText }}</div>
        </div>
        <div class="m-detail-cell">
          <div class="m-cell-label">Tracker</div>
          <div class="m-cell-value">
            {{ trackers.length }}<template v-if="hasTrackerError"> · <span class="m-cell-warn">Tracker异常</span></template>
          </div>
        </div>
        <div class="m-detail-cell">
          <div class="m-cell-label">添加时间</div>
          <div class="m-cell-value">{{ formatTime(addedDate) }}</div>
        </div>
        <div class="m-detail-cell">
          <div class="m-cell-label">完成时间</div>
          <div class="m-cell-value">{{ formatTime(completedDate) }}</div>
        </div>
        <div class="m-detail-cell">
          <div class="m-cell-label">分类</div>
          <div class="m-cell-value">{{ torrent.category || '-' }}</div>
        </div>
        <div class="m-detail-cell">
          <div class="m-cell-label">标签</div>
          <div class="m-cell-value">{{ torrent.tags || '-' }}</div>
        </div>
        <div class="m-detail-cell m-detail-cell--full">
          <div class="m-cell-label">保存路径</div>
          <div class="m-cell-value m-cell-path">{{ savePath || '-' }}</div>
        </div>
        <div v-if="errorReason" class="m-detail-cell m-detail-cell--full">
          <div class="m-cell-label">错误信息</div>
          <div class="m-cell-value m-cell-error">{{ errorReason }}</div>
        </div>
      </div>

      <div v-if="trackers.length" class="m-detail-card">
        <button type="button" class="m-tracker-toggle" @click="trackerExpanded = !trackerExpanded">
          <span>Tracker 明细（{{ trackers.length }}）</span>
          <span class="m-tracker-toggle-arrow">{{ trackerExpanded ? '收起' : '展开' }}</span>
        </button>
        <div v-if="trackerExpanded" class="m-tracker-list">
          <div
            v-for="(tr, i) in trackers"
            :key="(trackerUrlOf(tr) || '') + '-' + i"
            class="m-tracker-item"
          >
            <div class="m-tracker-name">{{ trackerNameOf(tr) }}</div>
            <div class="m-tracker-meta">
              <span :class="['m-tracker-status', trackerStatusClass(tr)]">{{ trackerStatusText(tr) }}</span>
              <span v-if="announceMsgOf(tr)" class="m-tracker-msg">{{ announceMsgOf(tr) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="m-detail-actions">
        <el-button size="small" :disabled="busy" @click="pause">暂停</el-button>
        <el-button size="small" :disabled="busy" @click="resume">恢复</el-button>
        <el-button size="small" type="danger" plain :disabled="busy" @click="remove">删除</el-button>
      </div>
      <div class="m-detail-actions m-detail-actions--secondary">
        <el-button size="small" @click="backToList">返回列表</el-button>
      </div>
    </template>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import {
  getTorrentList,
  getActiveTorrents,
  pauseTorrents,
  resumeTorrents,
  deleteTorrents,
  Torrent,
  TrackerInfo,
  ActiveTorrentSpeed
} from '@/api/torrents'
import { extractErrorMessage, formatRatio } from '@/utils/formatters'
import {
  isTrackerAnnounceSuccess,
  getTrackerStatusClass
} from '@/views/torrents/utils/torrentBatch'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'
import { takeCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import {
  torrentStatusLabel,
  torrentStatusTagType,
  formatTorrentSize
} from '@/views/mobile/torrent-status'

/** 移动端速度展示：0/空显示 0（详情页语义与列表不同，空串会造成空白） */
function formatDetailSpeed(speed: number | null | undefined): string {
  if (speed === null || speed === undefined || speed <= 0) return '0 KB/s'
  if (speed >= 1024) return `${(speed / 1024).toFixed(2)} MB/s`
  return `${Math.round(speed)} KB/s`
}

const ACTIVE_POLL_INTERVAL_MS = 5000
const BASE_REFETCH_LIMIT = 100

/**
 * 移动种子详情页（Phase 4 M1）：
 * - 数据源：列表快照缓存立即渲染 + getList（downloader_id + name_like）回查刷新；
 *   后端单种子端点 /torrents/{info_id}/.. 实测返回空 data（ORM 实体直塞 CommonResponse
 *   会被序列化为 null），不可用，故不走该端点；
 * - 实时速度/进度/做种数：轮询 getActiveTorrents()（桌面 1s 轮询同款轻量接口），
 *   移动端 5s 节奏；非活跃种子由 live=null 自然回落到列表行字段；
 * - 操作：暂停/恢复/删除（入回收站）复用现有 API，删除成功回列表。
 */
@Component({
  name: 'MobileTorrentDetail',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileTorrentDetail extends Mixins(PullToRefresh) {
  private torrent: Torrent | null = null
  private loading = false
  private busy = false
  private trackerExpanded = false
  private live: ActiveTorrentSpeed | null = null
  private pollTimer = 0

  mounted(): void {
    this.torrent = takeCachedTorrent()
    if (this.torrent) {
      // 快照先渲染，基础字段后台静默刷新
      void this.refreshBase()
    } else {
      this.loading = true
      this.refreshBase().finally(() => {
        this.loading = false
      })
    }
    void this.pollActive()
    this.pollTimer = window.setInterval(() => {
      void this.pollActive()
    }, ACTIVE_POLL_INTERVAL_MS)
  }

  beforeDestroy(): void {
    if (this.pollTimer) {
      window.clearInterval(this.pollTimer)
      this.pollTimer = 0
    }
  }

  // ============ 路由与字段（camel/snake 双兼容，与桌面读取惯例一致） ============

  private get downloaderId(): string {
    const fromRoute = this.$route.params.downloaderId
    const fromRow = this.torrent?.downloaderId ?? this.torrent?.downloader_id
    return String(fromRoute || fromRow || '')
  }

  private get torrentHash(): string {
    const fromRoute = this.$route.params.hash
    return String(fromRoute || this.torrent?.hash || '')
  }

  private get downloaderName(): string {
    return String(this.torrent?.downloaderName ?? this.torrent?.downloader_name ?? '-')
  }

  private get status(): string {
    return this.torrent?.status ?? '-'
  }

  private get size(): number {
    return this.torrent?.size ?? 0
  }

  private get savePath(): string {
    return String(this.torrent?.savePath ?? this.torrent?.save_path ?? '')
  }

  private get addedDate(): string | null {
    return this.torrent?.addedDate ?? this.torrent?.added_date ?? null
  }

  private get completedDate(): string | null {
    return this.torrent?.completedDate ?? this.torrent?.completed_date ?? null
  }

  private get ratio(): number | null {
    return this.torrent?.ratio ?? null
  }

  private get errorReason(): string {
    return String(this.torrent?.errorReason ?? this.torrent?.error_reason ?? '')
  }

  private get hasTrackerError(): boolean {
    return Boolean(this.torrent?.hasTrackerError ?? this.torrent?.has_tracker_error)
  }

  private get trackers(): TrackerInfo[] {
    return this.torrent?.trackerInfo ?? this.torrent?.tracker_info ?? []
  }

  // ============ 实时覆盖（getActiveTorrents 轮询） ============

  private get downloadSpeed(): number | null {
    if (this.live) return this.live.downloadSpeed
    return this.torrent?.downloadSpeed ?? this.torrent?.download_speed ?? null
  }

  private get uploadSpeed(): number | null {
    if (this.live) return this.live.uploadSpeed
    return this.torrent?.uploadSpeed ?? this.torrent?.upload_speed ?? null
  }

  private get progressOf(): number {
    const value = this.live?.progress ?? this.torrent?.progress
    if (typeof value !== 'number') return 0
    return Math.min(100, Math.max(0, value))
  }

  private get seedsText(): string {
    if (this.live) return String(this.live.num_seeds ?? 0)
    const seeds = this.torrent?.seeds
    return seeds === null || seeds === undefined ? '-' : String(seeds)
  }

  private get peersText(): string {
    if (this.live) return String(this.live.num_leechs ?? 0)
    const peers = this.torrent?.peers
    return peers === null || peers === undefined ? '-' : String(peers)
  }

  // ============ 数据刷新 ============

  /** 基础字段回查：getList 按下载器 + 名称模糊查，再按 hash 精确匹配本行 */
  private async refreshBase(): Promise<void> {
    if (!this.downloaderId || !this.torrentHash) return
    try {
      const res = await getTorrentList({
        downloader_id: this.downloaderId,
        ...(this.torrent?.name ? { name_like: this.torrent.name } : {}),
        limit: BASE_REFETCH_LIMIT
      })
      if (res.code === '200' && res.data) {
        const row = (res.data.list ?? []).find((t) => t.hash === this.torrentHash)
        if (row) {
          this.torrent = row
        }
      }
    } catch (e) {
      // 回查失败：有快照则保留展示；无快照交给未找到空态
      if (!this.torrent) {
        this.$message.error(extractErrorMessage(e))
      }
    }
  }

  private async pollActive(): Promise<void> {
    if (!this.torrentHash) return
    try {
      const res = await getActiveTorrents()
      if (res.code === '200' && Array.isArray(res.data)) {
        this.live = res.data.find(
          (item) => item.hash === this.torrentHash &&
            (!item.downloaderId || item.downloaderId === this.downloaderId)
        ) ?? null
      }
    } catch {
      // 速度轮询失败静默，下个周期重试
    }
  }

  protected async onPullRefresh(): Promise<void> {
    await this.refreshBase()
    await this.pollActive()
  }

  // ============ 操作（复用列表页三件套） ============

  private async pause(): Promise<void> {
    await this.withBusy(() =>
      pauseTorrents({ downloader_id: this.downloaderId, hashes: [this.torrentHash] })
    )
  }

  private async resume(): Promise<void> {
    await this.withBusy(() =>
      resumeTorrents({ downloader_id: this.downloaderId, hashes: [this.torrentHash] })
    )
  }

  private remove(): void {
    if (!this.torrent) return
    const infoId = String(this.torrent.infoId ?? this.torrent.info_id ?? '')
    this.$confirm(`删除种子「${this.torrent.name}」？文件移入回收站，可从回收站恢复。`, '删除确认', { type: 'warning' })
      .then(async() => {
        await this.withBusy(() =>
          deleteTorrents({
            info_id: infoId,
            downloader_id: this.downloaderId,
            delete_data: 0,
            id_recycle: 1
          })
        )
        this.$message.success('已删除，返回列表')
        this.backToList()
      })
      .catch(() => undefined)
  }

  private async withBusy(action: () => Promise<{ code?: string }>): Promise<void> {
    this.busy = true
    try {
      const res = await action()
      if (res && res.code && res.code !== '200') return
      this.$message.success('操作成功')
      await this.refreshBase()
      await this.pollActive()
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.busy = false
    }
  }

  private backToList(): void {
    this.$router.replace('/m/torrents').catch(() => undefined)
  }

  // ============ 展示辅助 ============

  private statusLabel(status: string): string {
    return torrentStatusLabel(status)
  }

  private statusTagType(status: string): string {
    return torrentStatusTagType(status)
  }

  private formatSize(bytes: number): string {
    return formatTorrentSize(bytes)
  }

  private get ratioText(): string {
    return formatRatio(this.ratio)
  }

  private speedText(speed: number | null): string {
    return formatDetailSpeed(speed)
  }

  private formatTime(value: string | null): string {
    if (!value) return '-'
    return value.replace('T', ' ').slice(0, 16)
  }

  private trackerNameOf(tr: TrackerInfo): string {
    return String(
      tr.trackerName ?? tr.tracker_name ?? tr.trackerHost ?? tr.tracker_host ??
      tr.trackerUrl ?? tr.tracker_url ?? '-'
    )
  }

  private trackerUrlOf(tr: TrackerInfo): string {
    return String(tr.trackerUrl ?? tr.tracker_url ?? '')
  }

  private announceSucceeded(tr: TrackerInfo): string | boolean | undefined | null {
    return tr.lastAnnounceSucceeded ?? tr.last_announce_succeeded
  }

  private trackerStatusText(tr: TrackerInfo): string {
    if (tr.trackerStatus ?? tr.tracker_status) {
      return String(tr.trackerStatus ?? tr.tracker_status)
    }
    return isTrackerAnnounceSuccess(this.announceSucceeded(tr)) ? '正常' : '未通告'
  }

  private trackerStatusClass(tr: TrackerInfo): string {
    return getTrackerStatusClass(this.announceSucceeded(tr))
  }

  private announceMsgOf(tr: TrackerInfo): string {
    return String(tr.lastAnnounceMsg ?? tr.last_announce_msg ?? '')
  }
}
</script>

<style scoped>
.m-torrent-detail {
  padding-bottom: 8px;
}

.m-detail-empty {
  text-align: center;
}

.m-detail-card {
  background: #fff;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
}

.m-detail-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  line-height: 1.4;
  word-break: break-all;
}

.m-detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
}

.m-detail-meta-text {
  font-size: 12px;
  color: #909399;
}

.m-detail-progress-text {
  margin-top: 4px;
  font-size: 12px;
  color: #606266;
  text-align: right;
}

.m-detail-speed {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 14px;
  color: #303133;
}

.m-detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 12px;
}

.m-detail-cell--full {
  grid-column: 1 / -1;
}

.m-cell-label {
  font-size: 12px;
  color: #909399;
}

.m-cell-value {
  margin-top: 2px;
  font-size: 14px;
  color: #303133;
  word-break: break-all;
}

.m-cell-warn {
  color: #e6a23c;
  font-size: 12px;
}

.m-cell-path {
  font-size: 13px;
  color: #606266;
}

.m-cell-error {
  color: #f56c6c;
  font-size: 13px;
}

.m-tracker-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 4px 0;
  border: none;
  background: transparent;
  color: #303133;
  font-size: 14px;
  font-weight: 600;
}

.m-tracker-toggle-arrow {
  font-size: 12px;
  color: var(--color-primary);
}

.m-tracker-item {
  padding: 8px 0;
  border-bottom: 1px solid #f2f6fc;
}

.m-tracker-item:last-child {
  border-bottom: none;
}

.m-tracker-name {
  font-size: 13px;
  color: #303133;
  word-break: break-all;
}

.m-tracker-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}

.m-tracker-status {
  flex-shrink: 0;
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 10px;
  background: #f4f4f5;
  color: #909399;
}

.m-tracker-status.tracker-status-working {
  color: var(--color-primary);
  background: var(--color-primary-lightest);
}

.m-tracker-status.tracker-status-error {
  color: #f56c6c;
  background: #fef0f0;
}

.m-tracker-msg {
  font-size: 12px;
  color: #c0c4cc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-detail-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 6px;
}

.m-detail-actions .el-button {
  margin-left: 0;
}

.m-detail-actions--secondary {
  justify-content: center;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
