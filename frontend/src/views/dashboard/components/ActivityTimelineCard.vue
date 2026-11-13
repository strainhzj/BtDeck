<template>
  <div>
    <div
      v-for="(item, i) in activities"
      :key="i"
      class="dash-tl-item"
    >
      <span class="dash-tl-time dash-ellip">{{ item.time }}</span>
      <span class="dash-tl-dotcol" />
      <div class="grow dash-ellip">
        {{ item.action }}
      </div>
    </div>
    <div
      v-if="activities.length === 0"
      class="dash-empty"
    >
      <lucide-icon name="history" />
      <span>{{ $t('dashboard.noActivities') }}</span>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * ActivityTimelineCard —— 最近活动 widget（仪表盘一期 W2）。
 *
 * 数据源：GET /dashboard 的 activities（后端 torrent_audit_log TOP10 组合
 * 文案，time 为相对时间字符串）。时间线样式对齐验收示意图。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import { ActivityItem } from '@/types/dashboard'

@Component({ name: 'ActivityTimelineCard' })
export default class ActivityTimelineCard extends Vue {
  @Prop({ required: true }) private activities!: ActivityItem[]
}
</script>
