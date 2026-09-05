<template>
  <div class="m-notifications">
    <m-pull-indicator :distance="pullDistance" :ready="pullReady" :refreshing="pullRefreshing" />
    <div v-if="!loading && list.length === 0" class="m-hint">暂无通知</div>
    <!-- 无限滚动：window 滚动驱动（mixins/window-infinite-scroll；Element 指令会被
         从不内滚的 .mobile-content 误判恒在底部导致自动连发请求拉满 total） -->
    <div>
      <div
        v-for="n in list"
        :key="n.id"
        class="m-notice"
        :class="{'is-unread': !n.is_read}"
        @click="openDetail(n)"
      >
        <div class="m-notice-title">
          <el-tag v-if="!n.is_read" size="mini" type="danger">未读</el-tag>
          <span class="m-notice-title-text">{{ n.title }}</span>
        </div>
        <div v-if="summaryText(n)" class="m-notice-content">{{ summaryText(n) }}</div>
        <div class="m-notice-time">{{ formatTime(n.created_at) }}</div>
      </div>
      <div v-if="list.length && list.length < total" class="m-load-more-hint">
        已加载 {{ list.length }} / 共 {{ total }}
      </div>
      <div v-if="loading && list.length" class="m-load-more-hint">
        <i class="el-icon-loading" /> 加载中…
      </div>
    </div>

    <!--
      通知详情：与桌面 NotificationDrawer 详情弹窗同源（utils/notification-markdown
      renderNotificationContent），标题/列表/粗体/行内代码/分隔线渲染两端一致；
      另含失败明细与 Release 链接。
    -->
    <el-dialog
      :visible.sync="detailVisible"
      width="92%"
      top="8vh"
      :show-close="false"
      append-to-body
      custom-class="m-notification-detail-dialog"
    >
      <template #title>
        <div class="m-detail-header">
          <span class="m-detail-header-text">{{ detailTitle }}</span>
          <button type="button" aria-label="关闭通知详情" @click="detailVisible = false">
            <LucideIcon name="x" :size="15" />
          </button>
        </div>
      </template>
      <div class="m-detail-meta">
        <el-tag size="mini" :type="detailTypeTag">{{ detailTypeLabel }}</el-tag>
        <span class="m-detail-time">{{ detailTime }}</span>
      </div>
      <div class="m-detail-content" v-html="detailHtml" />
      <div v-if="failureList.length > 0" class="m-detail-failures">
        <h4>失败明细</h4>
        <ul>
          <li v-for="(item, index) in failureList" :key="failureKey(item, index)">
            <span class="m-detail-failure-target">{{ failureTarget(item) }}</span>：{{ item.reason }}
          </li>
        </ul>
      </div>
      <div v-if="releaseUrl" class="m-detail-footer">
        <a :href="releaseUrl" target="_blank" class="m-detail-link">
          <LucideIcon name="external-link" :size="13" /> 在 GitHub 上查看完整 Release
        </a>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Mixins } from 'vue-property-decorator'
import { getNotificationList, markAsRead, NotificationFailureItem, NotificationItem } from '@/api/notification'
import { extractErrorMessage } from '@/utils/formatters'
import { notificationFailureTarget, plainNotificationContent, renderNotificationContent } from '@/utils/notification-markdown'
import { NotificationModule } from '@/store/modules/notification'
import SpeedPollingMixin from '@/views/torrents/mixins/speedPolling'
import { PullToRefresh } from '@/views/mobile/mixins/pull-to-refresh'
import { WindowInfiniteScroll } from '@/views/mobile/mixins/window-infinite-scroll'
import MobilePullIndicator from '@/views/mobile/components/PullIndicator.vue'

const NOTIFICATION_PAGE_SIZE = 50

/**
 * 移动通知中心（Phase 4 M1）：复用 /notifications API；点击打开详情并按桌面同源规则渲染内容，同时标记已读。
 *
 * 2026-08-28 UX 增强：无限滚动分页追加（按 id 去重防跨页重复，解除
 * 50 条封顶）；30s 静默自动刷新（未翻页整表替换、已翻页跳过本轮只同步未读角标，
 * 避免把翻页用户重置回第 1 页）；移除底部刷新按钮（下拉+自动刷新覆盖）。
 * 2026-09-05：无限滚动改 WindowInfiniteScroll mixin（window 驱动）——Element
 * 指令被从不内滚的 .mobile-content 误判恒在底部，页面打开自动连发请求拉满 total。
 */
@Component({
  name: 'MobileNotifications',
  components: { 'm-pull-indicator': MobilePullIndicator }
})
export default class MobileNotifications extends Mixins(PullToRefresh, SpeedPollingMixin, WindowInfiniteScroll) {
  private list: NotificationItem[] = []
  private total = 0
  private page = 1
  private loading = false
  private detailVisible = false
  private detail: NotificationItem | null = null

  /** 通知自动刷新节奏（非即时消息场景的省电版） */
  protected speedPollIntervalMs = 30000

  mounted(): void {
    this.load()
    this.startSpeedPolling(false)
  }

  beforeDestroy(): void {
    this.stopSpeedPolling()
  }

  protected async onPullRefresh(): Promise<void> {
    await this.load()
  }

  /** SpeedPollingMixin 轮询体：静默刷新；已翻页时跳过（防重置回第 1 页）只同步角标 */
  protected async loadActiveSpeed(): Promise<boolean> {
    if (this.page > 1) {
      NotificationModule.FetchUnreadCount().catch(() => undefined)
      return true
    }
    await this.load()
    return true
  }

  protected get infiniteDisabled(): boolean {
    return this.loading || this.list.length >= this.total
  }

  /** 整表重载（首屏/下拉刷新）：重置回第 1 页 */
  private async load(): Promise<void> {
    this.loading = true
    try {
      const res = await getNotificationList({ page: 1, pageSize: NOTIFICATION_PAGE_SIZE })
      if (res.code === '200' && res.data) {
        this.list = res.data.list ?? []
        this.total = res.data.total ?? 0
        this.page = 1
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
      // 内容不足一屏时主动补页（window 滚动驱动，无指令观察器）
      this.maybeLoadMore()
    }
  }

  /** WindowInfiniteScroll 子类实现：无限滚动追加下一页，按 id 去重（新通知插入头部会使后页 offset 前移产生重复） */
  protected async loadMore(): Promise<void> {
    if (this.infiniteDisabled) return
    this.loading = true
    try {
      const nextPage = this.page + 1
      const res = await getNotificationList({ page: nextPage, pageSize: NOTIFICATION_PAGE_SIZE })
      if (res.code === '200' && res.data) {
        const existing = new Set(this.list.map(n => n.id))
        const fresh = (res.data.list ?? []).filter(n => !existing.has(n.id))
        this.list = this.list.concat(fresh)
        this.page = res.data.page ?? nextPage
        this.total = res.data.total ?? this.total
      }
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.loading = false
      this.maybeLoadMore()
    }
  }

  private openDetail(n: NotificationItem): void {
    this.detail = n
    this.detailVisible = true
    // 与桌面详情弹窗一致：查看未读通知即标记已读
    this.read(n)
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

  // 列表摘要走共享纯文本化（与桌面列表同源）：剥离 Markdown 记号，未打开详情前不裸露 ## 等字符
  private summaryText(n: NotificationItem): string {
    return plainNotificationContent(n.content)
  }

  // --- 详情弹层（渲染逻辑与桌面 NotificationDrawer 共用 utils/notification-markdown） ---

  private get detailTitle(): string {
    return this.detail ? this.detail.title : ''
  }

  private get detailTime(): string {
    return this.detail ? this.formatTime(this.detail.created_at) : ''
  }

  private get detailTypeLabel(): string {
    return this.detail && this.detail.type === 'version_update' ? '版本更新' : '系统通知'
  }

  private get detailTypeTag(): string {
    return this.detail && this.detail.type === 'version_update' ? 'success' : 'info'
  }

  private get detailHtml(): string {
    return renderNotificationContent(this.detail && this.detail.content ? this.detail.content : '')
  }

  private get failureList(): NotificationFailureItem[] {
    return this.detail && this.detail.extra_data && this.detail.extra_data.failed_list
      ? this.detail.extra_data.failed_list
      : []
  }

  private get releaseUrl(): string {
    return this.detail && this.detail.extra_data && this.detail.extra_data.release_url
      ? this.detail.extra_data.release_url
      : ''
  }

  private failureTarget(item: NotificationFailureItem): string {
    return notificationFailureTarget(item)
  }

  private failureKey(item: NotificationFailureItem, index: number): string {
    return `${notificationFailureTarget(item)}-${index}`
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

/* 与桌面通知列表一致：摘要为剥离 Markdown 记号的纯文本 + 三行截断，完整渲染进详情 */
.m-notice-content {
  margin-top: 4px;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.m-notice-time {
  margin-top: 4px;
  font-size: 11px;
  color: #c0c4cc;
}

/* 无限滚动尾部非交互计数/加载提示 */
.m-load-more-hint {
  text-align: center;
  color: #909399;
  font-size: 12px;
  padding: 10px 0;
}

.m-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
}
</style>

<!-- 详情弹层挂 body（append-to-body），v-html 产物无 scoped 标记，样式须非 scoped 且按弹层类名收口 -->
<style>
.m-notification-detail-dialog .el-dialog__header {
  padding: 12px 14px;
  border-bottom: 1px solid #e5e7eb;
}

.m-notification-detail-dialog .m-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #111827;
  font-size: 15px;
  font-weight: 600;
}

.m-notification-detail-dialog .m-detail-header button {
  display: inline-flex;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  color: #6b7280;
  background: transparent;
  cursor: pointer;
}

.m-notification-detail-dialog .m-detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.m-notification-detail-dialog .m-detail-time {
  font-size: 12px;
  color: #9ca3af;
}

.m-notification-detail-dialog .m-detail-content {
  font-size: 14px;
  line-height: 1.6;
  color: #374151;
  word-break: break-word;
}

.m-notification-detail-dialog .m-detail-content h2 {
  font-size: 16px;
  margin: 12px 0 6px;
  font-weight: 600;
  color: #111827;
}

.m-notification-detail-dialog .m-detail-content h3 {
  font-size: 15px;
  margin: 10px 0 4px;
  font-weight: 600;
  color: #1f2937;
}

.m-notification-detail-dialog .m-detail-content h4 {
  font-size: 14px;
  margin: 8px 0 4px;
  font-weight: 600;
  color: #374151;
}

.m-notification-detail-dialog .m-detail-content p {
  margin: 4px 0;
}

.m-notification-detail-dialog .m-detail-content ul {
  padding-left: 18px;
  margin: 4px 0;
  list-style-type: disc;
}

.m-notification-detail-dialog .m-detail-content li {
  margin: 2px 0;
  line-height: 1.5;
}

.m-notification-detail-dialog .m-detail-content strong {
  color: #111827;
}

.m-notification-detail-dialog .m-detail-content code {
  background: #f3f4f6;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 13px;
  color: #dc2626;
}

.m-notification-detail-dialog .m-detail-content hr {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 8px 0;
}

.m-notification-detail-dialog .m-detail-failures {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  color: #78350f;
  font-size: 13px;
  line-height: 1.5;
}

.m-notification-detail-dialog .m-detail-failures h4 {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
}

.m-notification-detail-dialog .m-detail-failures ul {
  margin: 0;
  padding-left: 18px;
}

.m-notification-detail-dialog .m-detail-failures li {
  margin: 3px 0;
  word-break: break-word;
}

.m-notification-detail-dialog .m-detail-failure-target {
  color: #92400e;
  font-weight: 600;
}

.m-notification-detail-dialog .m-detail-footer {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

.m-notification-detail-dialog .m-detail-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #059669;
  text-decoration: none;
}
</style>
