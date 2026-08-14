<template>
  <div class="tracker-detail-content">
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
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'
import type { TrackerInfo } from '@/api/torrents'
import {
  isTrackerAnnounceSuccess,
  getTrackerStatusClass
} from '../utils/torrentBatch'

export interface TrackerDetailRow extends TrackerInfo {
  reannouncing?: boolean
}

@Component({
  name: 'TrackerDetailCard'
})
export default class TrackerDetailCard extends Vue {
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

  private handleTrackerReannounce(tracker: TrackerDetailRow, index: number) {
    this.$emit('reannounce', tracker, index)
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/tracker-table';

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

.tracker-table {
  @include tracker-table-styles;

  tbody tr:hover {
    background: var(--color-bg-hover);
  }
}
</style>
