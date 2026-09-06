<template>
  <section
    class="tracker-detail-card"
    :class="[
      `tracker-detail-card--${layout}`,
      {'is-open': visible}
    ]"
  >
    <div class="tracker-detail-header">
      <h3 class="tracker-title">
        <LucideIcon name="bar-chart-3" :size="14" />
        Tracker详情 - {{ torrentName }}
      </h3>
      <button class="tracker-close" @click="handleClose">
        <LucideIcon name="x" :size="16" />
      </button>
    </div>

    <div class="tracker-detail-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        class="tracker-tab-btn"
        :class="{active: activeTab === tab.value}"
        @click="handleTabChange(tab.value)"
      >
        {{ tab.label }}
      </button>
    </div>

    <div class="tracker-detail-content">
      <template v-if="activeTab === 'tracker'">
        <el-alert
          v-if="errorReason"
          class="torrent-error-alert"
          title="种子错误原因"
          :description="errorReason"
          type="error"
          show-icon
          :closable="false"
        />
        <div class="tracker-table-wrapper">
          <table class="tracker-table tracker-table-detail">
            <thead>
              <tr>
                <th>Tracker名称</th>
                <th style="width: 80px;">Announce</th>
                <th>Announce信息</th>
                <th style="width: 80px;">Scrape</th>
                <th style="width: 60px;" class="tracker-sticky-col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(tracker, index) in trackerInfo"
                :key="index"
                :class="{'tracker-row-matched': !!matchedDomainOf(tracker)}"
              >
                <td>
                  <div class="tracker-name-cell">
                    <span>{{ tracker.tracker_name || tracker.trackerName || '未知' }}</span>
                    <span
                      v-if="matchedDomainOf(tracker)"
                      class="tracker-matched-tag"
                      :title="`命中当前 Tracker 域名筛选：${matchedDomainOf(tracker)}`"
                    >命中筛选</span>
                  </div>
                  <div
                    class="tracker-url-mini"
                    :title="tracker.tracker_url || tracker.trackerUrl || '-'"
                  >{{ tracker.tracker_url || tracker.trackerUrl || '-' }}</div>
                </td>
                <td>
                  <span :class="trackerStatusClass(getAnnounceStatus(tracker))">
                    <template v-if="trackerAnnounceSuccess(getAnnounceStatus(tracker))">
                      ✓ 工作
                    </template>
                    <template v-else>
                      ✗ {{ getAnnounceStatus(tracker) || '失败' }}
                    </template>
                  </span>
                </td>
                <td>{{ tracker.last_announce_msg || tracker.lastAnnounceMsg || '-' }}</td>
                <td>
                  <span :class="trackerStatusClass(getScrapeStatus(tracker))">
                    <template v-if="trackerAnnounceSuccess(getScrapeStatus(tracker))">
                      ✓ 工作
                    </template>
                    <template v-else>
                      ✗ {{ getScrapeStatus(tracker) || '失败' }}
                    </template>
                  </span>
                </td>
                <td class="tracker-sticky-col">
                  <el-button
                    type="text"
                    size="mini"
                    :loading="tracker.reannouncing"
                    @click="handleTrackerReannounce(tracker, index)"
                  >汇报</el-button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-else-if="activeTab === 'files'">
        <div v-if="filesEmptyState === 'loading'" class="tracker-placeholder">文件列表加载中...</div>
        <el-alert
          v-else-if="filesEmptyState === 'error'"
          class="torrent-error-alert"
          title="文件列表加载失败"
          :description="filesState.error"
          type="error"
          show-icon
          :closable="false"
        />
        <div v-else-if="filesEmptyState === 'empty'" class="tracker-placeholder">暂无文件数据</div>
        <template v-else>
          <div class="tracker-detail-toolbar">
            <span class="tracker-detail-count">共 {{ filesState.list.length }} 个文件</span>
            <el-button type="text" size="mini" @click="handleRefresh">刷新</el-button>
          </div>
          <div v-if="filesState.error" class="tracker-stale-note" :title="filesState.error">更新失败，显示上次数据</div>
          <div class="tracker-table-wrapper">
            <table class="tracker-table tracker-table-detail tracker-fixed-table">
              <thead>
                <tr>
                  <th>文件名</th>
                  <th style="width: 80px;">大小</th>
                  <th style="width: 140px;">进度</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(file, index) in visibleFiles" :key="index">
                  <td class="tracker-ellipsis-cell">
                    <span class="tracker-cell-ellipsis" :title="file.name">{{ file.name }}</span>
                  </td>
                  <td class="tracker-speed-cell">{{ formatFileSizeText(file.size) }}</td>
                  <td>
                    <div class="tracker-progress-cell">
                      <el-progress
                        class="tracker-progress-bar"
                        :percentage="progressPercent(file.progress)"
                        :stroke-width="6"
                        :show-text="false"
                        :color="progressBarColor(file.progress)"
                      />
                      <span :class="['tracker-progress-text', progressTextClass(file.progress)]">
                        {{ progressPercent(file.progress) }}%
                      </span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="filesTruncateNote" class="tracker-truncate-note">{{ filesTruncateNote }}</div>
        </template>
      </template>

      <template v-else-if="activeTab === 'peers'">
        <div v-if="peersEmptyState === 'loading'" class="tracker-placeholder">Peers 列表加载中...</div>
        <el-alert
          v-else-if="peersEmptyState === 'error'"
          class="torrent-error-alert"
          title="Peers 列表加载失败"
          :description="peersState.error"
          type="error"
          show-icon
          :closable="false"
        />
        <div v-else-if="peersEmptyState === 'empty'" class="tracker-placeholder">暂无 Peers 数据</div>
        <template v-else>
          <div class="tracker-detail-toolbar">
            <span class="tracker-detail-count">共 {{ peersState.list.length }} 个 Peers（每 5 秒自动刷新）</span>
            <el-button type="text" size="mini" @click="handleRefresh">刷新</el-button>
          </div>
          <div v-if="peersState.error" class="tracker-stale-note" :title="peersState.error">更新失败，显示上次数据</div>
          <div class="tracker-table-wrapper">
            <table class="tracker-table tracker-table-detail tracker-fixed-table">
              <thead>
                <tr>
                  <th>地址</th>
                  <th style="width: 150px;">客户端</th>
                  <th style="width: 70px;">进度</th>
                  <th style="width: 85px;">↓速度</th>
                  <th style="width: 85px;">↑速度</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(peer, index) in visiblePeers" :key="index">
                  <td class="tracker-ellipsis-cell">
                    <span class="tracker-cell-ellipsis" :title="peerTitle(peer) || peer.ip">{{ peer.ip }}:{{ peer.port }}</span>
                  </td>
                  <td class="tracker-ellipsis-cell">
                    <span class="tracker-cell-ellipsis" :title="peer.client">{{ peer.client || '-' }}</span>
                  </td>
                  <td>
                    <span :class="progressTextClass(peer.progress)">{{ progressPercent(peer.progress) }}%</span>
                  </td>
                  <td class="tracker-speed-cell">{{ formatSpeedText(peer.down_speed || peer.downSpeed) }}</td>
                  <td class="tracker-speed-cell">{{ formatSpeedText(peer.up_speed || peer.upSpeed) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="peersTruncateNote" class="tracker-truncate-note">{{ peersTruncateNote }}</div>
        </template>
      </template>
    </div>

    <button
      class="tracker-collapse-bar"
      type="button"
      title="收起详情"
      aria-label="收起详情"
      @click="handleClose"
    >
      <LucideIcon name="chevron-down" :size="14" />
    </button>
  </section>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'
import LucideIcon from '@/components/common/LucideIcon.vue'
import type { TrackerInfo, TorrentFileInfo, TorrentPeerInfo } from '@/api/torrents'
import { formatFileSize, formatSpeed } from '@/utils/formatters'
import type {
  DetailTabDataState,
  TrackerDetailTabValue
} from '../mixins/detailTabsData'
import {
  isTrackerAnnounceSuccess,
  getTrackerStatusClass
} from '../utils/torrentBatch'

export interface TrackerDetailRow extends TrackerInfo {
  reannouncing?: boolean
}

export interface TrackerDetailTab {
  label: string
  value: TrackerDetailTabValue
}

export type TrackerDetailLayout = 'list' | 'traditional'

export const DEFAULT_TRACKER_DETAIL_TABS: TrackerDetailTab[] = [
  { label: 'Tracker', value: 'tracker' },
  { label: '文件', value: 'files' },
  { label: 'Peers', value: 'peers' }
]

/** 大列表渲染截断阈值（文件/Peers 行数超限时只渲染前 N 行并提示总数） */
const DETAIL_MAX_VISIBLE_ROWS = 1000

function emptyDetailState<T>(): DetailTabDataState<T> {
  return { list: [], loading: false, error: '' }
}

@Component({
  name: 'TrackerDetailCard',
  components: {
    LucideIcon
  }
})
export default class TrackerDetailCard extends Vue {
  @Prop({ type: Boolean, default: false }) visible!: boolean
  @Prop({ type: String, default: '' }) torrentName!: string
  @Prop({ type: String, default: 'list' }) layout!: TrackerDetailLayout
  @Prop({ type: String, default: 'tracker' }) activeTab!: TrackerDetailTabValue
  @Prop({ type: Array, default: () => DEFAULT_TRACKER_DETAIL_TABS }) tabs!: TrackerDetailTab[]
  @Prop({ type: Array, default: () => [] }) trackerInfo!: TrackerDetailRow[]
  @Prop({ type: String, default: '' }) errorReason!: string
  @Prop({ type: Object, default: () => emptyDetailState<TorrentFileInfo>() }) filesState!: DetailTabDataState<TorrentFileInfo>
  @Prop({ type: Object, default: () => emptyDetailState<TorrentPeerInfo>() }) peersState!: DetailTabDataState<TorrentPeerInfo>

  // ====== 文件页签 ======

  private get visibleFiles(): TorrentFileInfo[] {
    return this.filesState.list.slice(0, DETAIL_MAX_VISIBLE_ROWS)
  }

  private get filesTruncateNote(): string {
    if (this.filesState.list.length <= DETAIL_MAX_VISIBLE_ROWS) return ''
    return `共 ${this.filesState.list.length} 个文件，仅显示前 ${DETAIL_MAX_VISIBLE_ROWS} 个`
  }

  /** 无数据时的占位状态：'loading' | 'error' | 'empty' | ''（有数据） */
  private get filesEmptyState(): 'loading' | 'error' | 'empty' | '' {
    const state = this.filesState
    if (state.list.length > 0) return ''
    if (state.loading) return 'loading'
    if (state.error) return 'error'
    return 'empty'
  }

  // ====== Peers 页签 ======

  private get visiblePeers(): TorrentPeerInfo[] {
    return this.peersState.list.slice(0, DETAIL_MAX_VISIBLE_ROWS)
  }

  private get peersTruncateNote(): string {
    if (this.peersState.list.length <= DETAIL_MAX_VISIBLE_ROWS) return ''
    return `共 ${this.peersState.list.length} 个 Peers，仅显示前 ${DETAIL_MAX_VISIBLE_ROWS} 个`
  }

  private get peersEmptyState(): 'loading' | 'error' | 'empty' | '' {
    const state = this.peersState
    if (state.list.length > 0) return ''
    if (state.loading) return 'loading'
    if (state.error) return 'error'
    return 'empty'
  }

  // ====== Tracker 页签辅助 ======

  private getAnnounceStatus(tracker: TrackerDetailRow): string | undefined {
    return tracker.last_announce_succeeded || tracker.lastAnnounceSucceeded
  }

  /** 命中当前 tracker 域名筛选的域名（后端 matched_domain，snake/camel 双读）；未命中返回 undefined */
  private matchedDomainOf(tracker: TrackerDetailRow): string | undefined {
    return tracker.matched_domain || tracker.matchedDomain || undefined
  }

  private getScrapeStatus(tracker: TrackerDetailRow): string | undefined {
    return tracker.last_scrape_succeeded || tracker.lastScrapeSucceeded
  }

  private trackerAnnounceSuccess(status: string | boolean | undefined | null): boolean {
    return isTrackerAnnounceSuccess(status)
  }

  private trackerStatusClass(status: string | boolean | undefined | null): string {
    return getTrackerStatusClass(status)
  }

  // ====== 文件/Peers 展示辅助 ======

  /** 进度换算为 0~100 整数并 clamp（el-progress percentage 校验器强制 0~100） */
  private progressPercent(progress: number | null | undefined): number {
    const value = typeof progress === 'number' && Number.isFinite(progress) ? progress * 100 : 0
    return Math.min(100, Math.max(0, Math.round(value)))
  }

  private progressBarColor(progress: number | null | undefined): string {
    return this.progressPercent(progress) >= 100 ? 'var(--color-success)' : 'var(--color-primary)'
  }

  private progressTextClass(progress: number | null | undefined): string {
    const percent = this.progressPercent(progress)
    if (percent >= 100) return 'tracker-progress-done'
    if (percent > 0) return 'tracker-progress-partial'
    return 'tracker-progress-zero'
  }

  private formatFileSizeText(size: number | null | undefined): string {
    return formatFileSize(size)
  }

  /** formatSpeed 对 0/空值返回空串，Peers 速度列兜底显示 '-' */
  private formatSpeedText(speed: number | null | undefined): string {
    return formatSpeed(speed) || '-'
  }

  /** Peer 地址列的悬浮提示：国家/连接标志（qB 提供，TR 恒空） */
  private peerTitle(peer: TorrentPeerInfo): string {
    const parts: string[] = []
    if (peer.country) parts.push(peer.country)
    if (peer.flags) parts.push(`Flags: ${peer.flags}`)
    return parts.join(' · ')
  }

  private handleTabChange(tab: TrackerDetailTabValue) {
    this.$emit('update:activeTab', tab)
  }

  private handleClose() {
    this.$emit('close')
  }

  /** 页签内刷新按钮 → 交由父级（TrackerDetailDataMixin.handleDetailRefresh）重取数据 */
  private handleRefresh() {
    this.$emit('refresh', this.activeTab)
  }

  private handleTrackerReannounce(tracker: TrackerDetailRow, index: number) {
    this.$emit('reannounce', tracker, index)
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/tracker-table';

.tracker-detail-card {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--color-bg-primary);
  border: 1px solid transparent;
  border-left: 4px solid transparent;
  border-radius: var(--radius-lg);
  box-shadow: none;
  opacity: 0;
  pointer-events: none;
  transform: translateY(8px);
  visibility: hidden;
  transition:
    height 0.2s ease,
    margin 0.2s ease,
    opacity 0.2s ease,
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    visibility 0s linear 0.2s;

  &.is-open {
    border-color: var(--color-border-primary);
    border-left-color: var(--color-primary);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
    opacity: 1;
    pointer-events: auto;
    transform: translateY(0);
    visibility: visible;
    transition-delay: 0s;
  }

  &--list {
    position: relative;
    height: 0;
    margin-top: 0;
    flex-shrink: 0;
  }

  &--list.is-open {
    height: 240px;
    margin-top: 12px;
  }

  &--traditional {
    position: absolute;
    z-index: 20;
    left: 8px;
    right: 8px;
    bottom: calc(var(--trad-pagination-height) + 8px);
    height: 0;
    max-height: calc(100% - var(--trad-pagination-height) - 24px);
  }

  &--traditional.is-open {
    height: 240px;
  }
}

.tracker-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  min-width: 0;
  padding: 8px 12px;
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-primary);
}

.tracker-title {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  margin: 0;
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: var(--font-weight-semibold);
  text-overflow: ellipsis;
  white-space: nowrap;

  .lucide-icon {
    flex-shrink: 0;
    margin-right: 6px;
    color: var(--color-primary);
  }
}

.tracker-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 2px 4px;
  color: var(--color-text-tertiary);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover {
    color: var(--color-text-primary);
    background: var(--color-bg-tertiary);
  }
}

/* 底部整行收起条：点击与右上角关闭按钮等效（复用 close 事件），卡片总高不变 */
.tracker-collapse-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 100%;
  height: 24px;
  padding: 0;
  color: var(--color-text-tertiary);
  background: none;
  border: none;
  border-top: 1px solid var(--color-border-primary);
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover {
    color: var(--color-text-primary);
    background: var(--color-bg-tertiary);
  }
}

.tracker-detail-tabs {
  display: flex;
  gap: 1px;
  flex-shrink: 0;
  margin: 0 12px 10px;
  border-bottom: 1px solid var(--color-border-primary);
}

.tracker-tab-btn {
  padding: 5px 10px;
  color: var(--color-text-tertiary);
  font-size: 11px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all var(--transition-fast);

  &:hover {
    color: var(--color-text-secondary);
  }

  &.active {
    color: var(--color-primary);
    border-bottom-color: var(--color-primary);
  }
}

.tracker-detail-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.torrent-error-alert {
  flex-shrink: 0;
  margin-bottom: 10px;
}

.tracker-table-wrapper {
  flex: 1;
  min-height: 0;
  overflow-x: auto;
  overflow-y: auto;
}

.tracker-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 0;
  padding: 20px;
  color: var(--color-text-tertiary);
  font-size: 11px;
}

/* 文件/Peers 页签：计数 + 刷新按钮工具条 */
.tracker-detail-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  padding: 2px 12px 6px;
}

.tracker-detail-count {
  overflow: hidden;
  color: var(--color-text-tertiary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 轮询/刷新失败但仍有上次数据时的非侵入提示 */
.tracker-stale-note {
  flex-shrink: 0;
  margin: 0 12px 6px;
  padding-left: 6px;
  overflow: hidden;
  color: var(--color-error);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-left: 2px solid var(--color-error);
}

.tracker-truncate-note {
  flex-shrink: 0;
  padding: 4px 12px;
  color: var(--color-text-tertiary);
  font-size: 10px;
  border-top: 1px solid var(--color-border-secondary);
}

.tracker-table {
  @include tracker-table-styles;

  tbody tr:hover {
    background: var(--color-bg-hover);
  }
}

/* 固定列宽表格：首列（文件名/地址）吃剩余宽度，配合单元格省略号 */
.tracker-fixed-table {
  table-layout: fixed;
}

.tracker-ellipsis-cell {
  overflow: hidden;
}

.tracker-cell-ellipsis {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tracker-progress-cell {
  display: flex;
  align-items: center;
  gap: 6px;

  .tracker-progress-bar {
    flex: 1;
    min-width: 0;
  }
}

.tracker-progress-text {
  flex-shrink: 0;
  min-width: 32px;
  font-size: 11px;
  text-align: right;
}

.tracker-progress-done {
  color: var(--color-success);
}

.tracker-progress-partial {
  color: var(--color-primary);
}

.tracker-progress-zero {
  color: var(--color-text-tertiary);
}

.tracker-speed-cell {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

@media screen and (max-width: 768px) {
  .tracker-detail-card--list.is-open {
    position: fixed;
    z-index: var(--z-index-fixed);
    right: 0;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 180px;
    margin: 0;
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  }
}
</style>
