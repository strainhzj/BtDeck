<template>
  <div class="notification-item" :class="{'is-unread': !notification.is_read}">
    <!-- 类型图标 -->
    <div class="notification-icon" :class="iconClass">
      <i :class="iconName" />
    </div>

    <!-- 内容区域 -->
    <div class="notification-content" @click.stop="$emit('view', notification)">
      <div class="notification-header">
        <span class="notification-title">{{ notification.title }}</span>
        <span class="notification-time">{{ formattedTime }}</span>
      </div>
      <div v-if="notification.content" class="notification-body">
        {{ notification.content }}
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="notification-ops">
      <el-tooltip :content="notification.is_read ? '标记未读' : '标记已读'" placement="top">
        <el-button
          type="text"
          size="mini"
          :class="{'btn-read': notification.is_read}"
          @click.stop="$emit('toggle-read', notification.id)"
        >
          <i :class="notification.is_read ? 'el-icon-refresh-left' : 'el-icon-check'" />
        </el-button>
      </el-tooltip>
      <el-tooltip content="删除" placement="top">
        <el-button type="text" size="mini" class="btn-delete" @click.stop="$emit('delete', notification.id)">
          <i class="el-icon-delete" />
        </el-button>
      </el-tooltip>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'
import { NotificationItem } from '@/api/notification'

@Component({ name: 'NotificationItem' })
export default class extends Vue {
  @Prop({ required: true }) private notification!: NotificationItem

  get iconName(): string {
    const map: Record<string, string> = {
      version_update: 'el-icon-upload',
      system: 'el-icon-setting'
    }
    return map[this.notification.type] || 'el-icon-bell'
  }

  get iconClass(): string {
    const map: Record<string, string> = {
      info: 'icon-info',
      warning: 'icon-warning',
      error: 'icon-error'
    }
    return map[this.notification.priority] || 'icon-info'
  }

  get formattedTime(): string {
    if (!this.notification.created_at) return ''
    const date = new Date(this.notification.created_at)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}小时前`
    const days = Math.floor(hours / 24)
    if (days < 30) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
  }
}
</script>

<style lang="scss" scoped>
.notification-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md, 12px);
  padding: var(--spacing-md, 12px);
  border-radius: var(--radius-md, 8px);
  transition: background var(--transition-base, 200ms);
  cursor: default;

  &:hover {
    background: var(--color-bg-hover, #F3F4F6);
  }

  &.is-unread {
    background: var(--color-bg-secondary, #F9FAFB);
    .notification-title {
      font-weight: 600;
    }
  }
}

.notification-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full, 9999px);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  i { font-size: 18px; }

  &.icon-info {
    background: rgba(59, 130, 246, 0.1);
    color: #3B82F6;
  }
  &.icon-warning {
    background: rgba(245, 158, 11, 0.1);
    color: #F59E0B;
  }
  &.icon-error {
    background: rgba(239, 68, 68, 0.1);
    color: #EF4444;
  }
}

.notification-content {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.notification-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-sm, 8px);
}

.notification-title {
  font-size: 14px;
  color: var(--color-text-primary, #1F2937);
  line-height: 1.4;
}

.notification-time {
  font-size: 12px;
  color: var(--color-text-tertiary, #9CA3AF);
  white-space: nowrap;
  flex-shrink: 0;
}

.notification-body {
  font-size: 13px;
  color: var(--color-text-secondary, #6B7280);
  line-height: 1.5;
  margin-top: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.notification-ops {
  display: flex;
  flex-direction: column;
  gap: 4px;
  opacity: 0;
  transition: opacity var(--transition-base, 200ms);

  .notification-item:hover & {
    opacity: 1;
  }

  .btn-delete {
    color: var(--color-text-tertiary, #9CA3AF);
    &:hover { color: var(--color-error, #EF4444); }
  }

  .btn-read {
    color: var(--color-text-tertiary, #9CA3AF);
    &:hover { color: var(--color-primary, #059669); }
  }
}
</style>
