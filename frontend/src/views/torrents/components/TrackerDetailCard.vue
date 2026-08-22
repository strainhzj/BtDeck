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
              >
                <td>
                  <div>{{ tracker.tracker_name || tracker.trackerName || '未知' }}</div>
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

      <div v-else-if="activeTab === 'files'" class="tracker-placeholder">
        文件列表功能开发中...
      </div>

      <div v-else-if="activeTab === 'peers'" class="tracker-placeholder">
        Peers 信息功能开发中...
      </div>
    </div>
  </section>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'
import LucideIcon from '@/components/common/LucideIcon.vue'
import type { TrackerInfo } from '@/api/torrents'
import {
  isTrackerAnnounceSuccess,
  getTrackerStatusClass
} from '../utils/torrentBatch'

export interface TrackerDetailRow extends TrackerInfo {
  reannouncing?: boolean
}

export type TrackerDetailTabValue = 'tracker' | 'files' | 'peers'

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

  private getAnnounceStatus(tracker: TrackerDetailRow): string | undefined {
    return tracker.last_announce_succeeded || tracker.lastAnnounceSucceeded
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

  private handleTabChange(tab: TrackerDetailTabValue) {
    this.$emit('update:activeTab', tab)
  }

  private handleClose() {
    this.$emit('close')
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

.tracker-table {
  @include tracker-table-styles;

  tbody tr:hover {
    background: var(--color-bg-hover);
  }
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
