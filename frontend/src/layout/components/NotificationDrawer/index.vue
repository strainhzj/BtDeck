<template>
  <div>
  <el-drawer
    :visible.sync="drawerVisible"
    direction="rtl"
    size="400px"
    :show-close="false"
    :wrapper-closable="true"
    custom-class="notification-drawer"
    @open="handleOpen"
    @close="handleClose"
  >
    <!-- 自定义头部 -->
    <template slot="title">
      <div class="drawer-header">
        <span class="drawer-title"><LucideIcon name="bell" :size="16" />通知中心</span>
        <div class="drawer-header-actions">
          <el-button
            v-if="unreadCount > 0"
            type="text"
            size="small"
            @click="handleReadAll"
          >
            全部已读
          </el-button>
          <button type="button" class="drawer-close" aria-label="关闭通知中心" @click="handleClose">
            <LucideIcon name="x" :size="15" />
          </button>
        </div>
      </div>
    </template>

    <!-- 筛选 Tab -->
    <div class="drawer-tabs">
      <div
        v-for="tab in tabs"
        :key="tab.value"
        class="tab-item"
        :class="{'is-active': activeTab === tab.value}"
        @click="handleTabChange(tab.value)"
      >
        {{ tab.label }}
        <span v-if="tab.value === 'unread' && unreadCount > 0" class="tab-badge">{{ unreadCount }}</span>
      </div>
    </div>

    <!-- 通知列表 -->
    <div class="drawer-body">
      <div v-if="loading" class="drawer-loading">
        <LucideIcon class="is-spinning" name="refresh-cw" :size="20" />
      </div>

      <template v-else-if="notifications.length > 0">
        <notification-item
          v-for="item in notifications"
          :key="item.id"
          :notification="item"
          @toggle-read="handleToggleRead"
          @delete="handleDelete"
          @view="handleView"
        />
        <div v-if="hasMore" class="load-more">
          <el-button type="text" size="small" @click="loadMore">加载更多</el-button>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-else class="drawer-empty">
        <LucideIcon name="bell" :size="34" :stroke-width="1.35" />
        <p>暂无通知</p>
      </div>
    </div>
  </el-drawer>

  <!-- 通知详情弹窗 -->
  <el-dialog
    :visible.sync="detailVisible"
    width="500px"
    :show-close="false"
    append-to-body
    custom-class="notification-detail-dialog"
    @close="handleDetailClose"
  >
    <template #title>
      <div class="detail-dialog-header">
        <span>{{ detailTitle }}</span>
        <button type="button" aria-label="关闭通知详情" @click="detailVisible = false">
          <LucideIcon name="x" :size="15" />
        </button>
      </div>
    </template>
    <div class="detail-meta">
      <el-tag size="mini" :type="detailTypeTag">{{ detailTypeLabel }}</el-tag>
      <span class="detail-time">{{ detailTime }}</span>
    </div>
    <div class="detail-content" v-html="detailHtml" />
    <div v-if="detailFailureList.length > 0" class="detail-failures">
      <h4>失败明细</h4>
      <ul>
        <li v-for="(item, index) in detailFailureList" :key="failureItemKey(item, index)">
          <span class="detail-failure-target">{{ failureItemTarget(item) }}</span>：{{ item.reason }}
        </li>
      </ul>
    </div>
    <div v-if="detailReleaseUrl" class="detail-footer">
      <a :href="detailReleaseUrl" target="_blank" class="detail-link">
        <LucideIcon name="external-link" :size="13" /> 在 GitHub 上查看完整 Release
      </a>
    </div>
  </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { NotificationModule } from '@/store/modules/notification'
import { NotificationFailureItem, NotificationExtraData, NotificationItem } from '@/api/notification'
import NotificationItemComp from './NotificationItem.vue'

@Component({
  name: 'NotificationDrawer',
  components: {
    NotificationItem: NotificationItemComp
  }
})
export default class extends Vue {
  private activeTab = 'all'
  private pollingTimer: ReturnType<typeof setInterval> | null = null

  // 详情弹窗状态
  private detailVisible = false
  private detailTitle = ''
  private detailContent = ''
  private detailType = ''
  private detailCreatedAt = ''
  private detailExtraData: NotificationExtraData | null = null

  private tabs = [
    { label: '全部', value: 'all' },
    { label: '未读', value: 'unread' },
    { label: '更新', value: 'version_update' },
    { label: '系统', value: 'system' }
  ]

  get drawerVisible() {
    return NotificationModule.drawerVisible
  }

  set drawerVisible(val: boolean) {
    NotificationModule.ToggleDrawer(val)
  }

  get notifications() {
    return NotificationModule.notifications
  }

  get unreadCount() {
    return NotificationModule.unreadCount
  }

  get loading() {
    return NotificationModule.loading
  }

  get hasMore() {
    return NotificationModule.total > NotificationModule.notifications.length
  }

  private handleOpen() {
    this.fetchList()
  }

  private handleClose() {
    NotificationModule.ToggleDrawer(false)
  }

  private handleTabChange(tab: string) {
    this.activeTab = tab
    this.fetchList()
  }

  private fetchList() {
    const params: { page?: number, type?: string, is_read?: boolean } = {}
    if (this.activeTab === 'unread') {
      params.is_read = false
    } else if (this.activeTab !== 'all') {
      params.type = this.activeTab
    }
    NotificationModule.FetchNotifications(params)
  }

  private loadMore() {
    // 简单分页：当前页 + 1
    const nextPage = Math.floor(this.notifications.length / 20) + 1
    NotificationModule.FetchNotifications({ page: nextPage })
  }

  private async handleRead(id: number) {
    await NotificationModule.MarkAsRead(id)
  }

  private async handleToggleRead(id: number) {
    const notification = this.notifications.find(n => n.id === id)
    if (notification) {
      if (notification.is_read) {
        // 标记为未读
        await NotificationModule.MarkAsUnread(id)
      } else {
        // 标记为已读
        await NotificationModule.MarkAsRead(id)
      }
    }
  }

  private async handleReadAll() {
    await NotificationModule.MarkAllAsRead()
  }

  private async handleDelete(id: number) {
    await NotificationModule.DeleteNotification(id)
  }

  // --- 详情弹窗 ---

  private get detailTypeLabel(): string {
    return this.detailType === 'version_update' ? '版本更新' : '系统通知'
  }

  private get detailTypeTag(): string {
    return this.detailType === 'version_update' ? 'success' : 'info'
  }

  private get detailTime(): string {
    if (!this.detailCreatedAt) return ''
    const date = new Date(this.detailCreatedAt)
    return date.toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit'
    })
  }

  private get detailHtml(): string {
    if (!this.detailContent) return ''
    // 按 Markdown 规则分块处理：先拆成行，逐行转换，再合并
    const lines = this.detailContent.split('\n')
    const html: string[] = []
    let inList = false

    for (const raw of lines) {
      const line = raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      const trimmed = line.trim()

      // 空行
      if (trimmed === '') {
        if (inList) { html.push('</ul>'); inList = false }
        continue
      }

      // 标题
      if (trimmed.startsWith('### ')) {
        if (inList) { html.push('</ul>'); inList = false }
        html.push(`<h4>${trimmed.slice(4)}</h4>`)
        continue
      }
      if (trimmed.startsWith('## ')) {
        if (inList) { html.push('</ul>'); inList = false }
        html.push(`<h3>${trimmed.slice(3)}</h3>`)
        continue
      }
      if (trimmed.startsWith('# ')) {
        if (inList) { html.push('</ul>'); inList = false }
        html.push(`<h2>${trimmed.slice(2)}</h2>`)
        continue
      }

      // 分隔线
      if (trimmed === '---') {
        if (inList) { html.push('</ul>'); inList = false }
        html.push('<hr />')
        continue
      }

      // 列表项
      if (trimmed.startsWith('- ')) {
        if (!inList) { html.push('<ul>'); inList = true }
        html.push(`<li>${trimmed.slice(2)}</li>`)
        continue
      }

      // 普通段落
      if (inList) { html.push('</ul>'); inList = false }
      html.push(`<p>${trimmed}</p>`)
    }
    if (inList) html.push('</ul>')

    // 内联格式：粗体、行内代码（在结构化输出上做替换）
    return html
      .join('\n')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.*?)`/g, '<code>$1</code>')
  }

  private get detailReleaseUrl(): string {
    return this.detailExtraData?.release_url || ''
  }

  private get detailFailureList(): NotificationFailureItem[] {
    return this.detailExtraData?.failed_list || []
  }

  private failureItemTarget(item: NotificationFailureItem): string {
    return item.file_name || item.file_path || item.canonical_path || item.quarantine_path || (item.id ? `记录 ${item.id}` : '未知项')
  }

  private failureItemKey(item: NotificationFailureItem, index: number): string {
    return `${this.failureItemTarget(item)}-${index}`
  }

  private handleView(notification: NotificationItem) {
    this.detailTitle = notification.title
    this.detailContent = notification.content || ''
    this.detailType = notification.type
    this.detailCreatedAt = notification.created_at
    this.detailExtraData = notification.extra_data
    this.detailVisible = true

    // 未读通知自动标记已读
    if (!notification.is_read) {
      NotificationModule.MarkAsRead(notification.id)
    }
  }

  private handleDetailClose() {
    this.detailVisible = false
    this.detailTitle = ''
    this.detailContent = ''
    this.detailType = ''
    this.detailCreatedAt = ''
    this.detailExtraData = null
  }

  private startPolling() {
    // 60秒轮询未读数
    this.pollingTimer = setInterval(() => {
      NotificationModule.FetchUnreadCount()
    }, 60000)
  }

  private stopPolling() {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer)
      this.pollingTimer = null
    }
  }

  mounted() {
    // 首次加载未读数
    NotificationModule.FetchUnreadCount()
    this.startPolling()
  }

  beforeDestroy() {
    this.stopPolling()
  }
}
</script>

<style lang="scss" scoped>
/* 抽屉头部 */
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: var(--spacing-md, 16px);
}

.drawer-title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary, #1F2937);
}

.drawer-header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.drawer-close {
  display: inline-flex;
  width: 28px;
  height: 28px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border-primary, #E5E7EB);
  border-radius: 8px;
  color: var(--color-text-secondary, #6B7280);
  background: transparent;
  cursor: pointer;
}

/* 筛选标签 */
.drawer-tabs {
  display: flex;
  gap: var(--spacing-sm, 8px);
  padding: var(--spacing-md, 12px) var(--spacing-lg, 20px);
  border-bottom: 1px solid var(--color-border-primary, #E5E7EB);
}

.tab-item {
  font-size: 13px;
  color: var(--color-text-secondary, #6B7280);
  padding: 4px 12px;
  border-radius: var(--radius-full, 9999px);
  cursor: pointer;
  transition: all var(--transition-base, 200ms);
  display: flex;
  align-items: center;
  gap: 4px;

  &:hover {
    color: var(--color-primary, #059669);
    background: rgba(5, 150, 105, 0.08);
  }

  &.is-active {
    color: #fff;
    background: var(--color-primary, #059669);
  }
}

.tab-badge {
  font-size: 11px;
  background: var(--color-error, #EF4444);
  color: #fff;
  border-radius: var(--radius-full, 9999px);
  padding: 0 6px;
  line-height: 18px;
  min-width: 18px;
  text-align: center;

  .is-active & {
    background: rgba(255, 255, 255, 0.3);
  }
}

/* 内容区域 */
.drawer-body {
  padding: var(--spacing-md, 12px) var(--spacing-lg, 20px);
  overflow-y: auto;
  height: calc(100% - 110px);
}

.drawer-loading {
  display: flex;
  justify-content: center;
  padding: var(--spacing-xl, 32px);
  color: var(--color-text-tertiary, #9CA3AF);
}

.drawer-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-xxl, 48px) 0;
  color: var(--color-text-quaternary, #D1D5DB);
  p { margin-top: var(--spacing-md, 12px); color: var(--color-text-tertiary, #9CA3AF); font-size: 14px; }
}

.is-spinning {
  animation: notification-spin 0.8s linear infinite;
}

@keyframes notification-spin {
  to { transform: rotate(360deg); }
}

.load-more {
  text-align: center;
  padding: var(--spacing-md, 12px) 0;
}
</style>

<style lang="scss">
/* 通知详情弹窗样式 */
.notification-detail-dialog {
  .el-dialog__header {
    padding: 14px 18px;
    border-bottom: 1px solid #E5E7EB;
  }

  .detail-dialog-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    color: #111827;
    font-size: 15px;
    font-weight: 600;

    button {
      display: inline-flex;
      width: 28px;
      height: 28px;
      align-items: center;
      justify-content: center;
      border: 1px solid #E5E7EB;
      border-radius: 8px;
      color: #6B7280;
      background: transparent;
      cursor: pointer;
    }
  }

  .el-dialog__body {
    padding-top: 12px;
  }

  .detail-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
  }

  .detail-time {
    font-size: 12px;
    color: #9CA3AF;
  }

  .detail-content {
    font-size: 14px;
    line-height: 1.6;
    color: #374151;
    word-break: break-word;

    h2 { font-size: 16px; margin: 12px 0 6px; font-weight: 600; color: #111827; }
    h3 { font-size: 15px; margin: 10px 0 4px; font-weight: 600; color: #1F2937; }
    h4 { font-size: 14px; margin: 8px 0 4px; font-weight: 600; color: #374151; }

    p { margin: 4px 0; }

    ul {
      padding-left: 18px;
      margin: 4px 0;
      list-style-type: disc;
    }

    li {
      margin: 2px 0;
      line-height: 1.5;
    }

    strong { color: #111827; }

    code {
      background: #F3F4F6;
      padding: 1px 4px;
      border-radius: 3px;
      font-size: 13px;
      color: #DC2626;
    }

    hr {
      border: none;
      border-top: 1px solid #E5E7EB;
      margin: 8px 0;
    }
  }

  .detail-failures {
    margin-top: 16px;
    padding: 12px;
    border: 1px solid #FDE68A;
    border-radius: 8px;
    background: #FFFBEB;
    color: #78350F;
    font-size: 13px;
    line-height: 1.5;

    h4 {
      margin: 0 0 6px;
      font-size: 13px;
      font-weight: 600;
    }

    ul {
      margin: 0;
      padding-left: 18px;
    }

    li {
      margin: 3px 0;
      word-break: break-word;
    }

    .detail-failure-target {
      color: #92400E;
      font-weight: 600;
    }
  }

  .detail-footer {
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid #E5E7EB;
  }

  .detail-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    color: #059669;
    text-decoration: none;

    &:hover { text-decoration: underline; }
  }
}
</style>

<style lang="scss">
/* 全局样式：覆盖 el-drawer 默认样式 */
.notification-drawer {
  .el-drawer__header {
    margin-bottom: 0;
    padding: var(--spacing-md, 16px) var(--spacing-lg, 20px);
    border-bottom: 1px solid var(--color-border-primary, #E5E7EB);
  }

  .el-drawer__body {
    padding: 0;
    overflow: hidden;
  }
}
</style>
