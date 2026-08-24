<template>
  <div class="m-notifications">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />
    <div v-if="!loading && list.length === 0" class="m-hint">暂无通知</div>
    <div
      v-for="n in list"
      :key="n.id"
      class="m-notice"
      :class="{'is-unread': !n.is_read}"
      @click="read(n)"
    >
      <div class="m-notice-title">
        <el-tag v-if="!n.is_read" size="mini" type="danger">未读</el-tag>
        <span class="m-notice-title-text">{{ n.title }}</span>
      </div>
      <div v-if="n.content" class="m-notice-content">{{ n.content }}</div>
      <div class="m-notice-time">{{ formatTime(n.created_at) }}</div>
    </div>
    <el-button class="m-refresh" size="small" :loading="loading" @click="load">刷新</el-button>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import { getNotificationList, markAsRead, NotificationItem } from '@/api/notification'
import { extractErrorMessage } from '@/utils/formatters'
import { NotificationModule } from '@/store/modules/notification'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'

/** 移动通知中心（Phase 4 M1）：复用 /notifications API，点击标记已读；已读后同步布局壳未读角标 */
@Component({
  name: 'MobileNotifications',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileNotifications extends Mixins(PullToRefresh) {
  private list: NotificationItem[] = []
  private loading = false

  mounted(): void {
    this.load()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.load()
  }

  private async load(): Promise<void> {
    this.loading = true
    try {
      const res = await getNotificationList({ page: 1, pageSize: 50 })
      if (res.code === '200' && res.data) {
        this.list = res.data.list ?? []
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
    }
  }

  private async read(n: NotificationItem): Promise<void> {
    if (n.is_read) return
    try {
      const res = await markAsRead(n.id)
      if (res.code === '200') {
        n.is_read = true
        // 本页直调 API 绕过 store，须手动同步布局壳角标的未读数
        await NotificationModule.FetchUnreadCount()
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    }
  }

  private formatTime(value: string): string {
    if (!value) return ''
    return value.replace('T', ' ').slice(0, 16)
  }
}
</script>

<style scoped>
.m-notice {
  background: #fff;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.m-notice.is-unread {
  border-left: 3px solid #f56c6c;
}

.m-notice-title {
  display: flex;
  align-items: center;
  gap: 6px;
}

.m-notice-title-text {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.m-notice-content {
  margin-top: 4px;
  font-size: 13px;
  color: #606266;
  line-height: 1.4;
}

.m-notice-time {
  margin-top: 4px;
  font-size: 11px;
  color: #c0c4cc;
}

.m-refresh {
  display: flex;
  margin: 8px auto 0;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>
