<template>
  <div class="downloader-card">
    <!-- 顶部渐变条（hover时显示） -->
    <div class="downloader-card-top-bar"></div>

    <!-- 卡片头部：名称 + 状态徽章 -->
    <div class="downloader-card-header">
      <div class="downloader-card-info">
        <div class="downloader-card-name">{{ info.nickname }}</div>
        <span class="downloader-card-type">
          {{ downloaderTypeLabel }}
        </span>
      </div>
      <div :class="['downloader-status-badge', statusClass]">
        <span v-if="onlineStatus === 'online'" class="status-indicator"></span>
        <span>{{ statusText }}</span>
      </div>
    </div>

    <!-- 卡片内容：统计数据 + 详细信息 -->
    <div class="downloader-card-content">
      <!-- 统计数据网格 -->
      <div class="downloader-card-stats">
        <div class="downloader-stat">
          <div class="downloader-stat-value">
            {{ displayValue(status.downloading_count) }}
          </div>
          <div class="downloader-stat-label">下载中</div>
        </div>
        <div class="downloader-stat">
          <div class="downloader-stat-value">
            {{ displayValue(status.seeding_count) }}
          </div>
          <div class="downloader-stat-label">做种中</div>
        </div>
        <div class="downloader-stat">
          <div class="downloader-stat-value">
            {{ status.delay !== undefined && status.delay !== null ? `${status.delay.toFixed(1)}ms` : '-' }}
          </div>
          <div class="downloader-stat-label">延迟ms</div>
        </div>
      </div>

      <!-- 详细信息 -->
      <div class="downloader-card-details">
        <div class="detail-item">
          <span class="detail-label">主机</span>
          <span class="detail-value">{{ info.host }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">端口</span>
          <span class="detail-value">{{ info.port }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">SSL</span>
          <span class="detail-value">{{ info.host.includes('https') || info.port.includes('https') ? '✅' : '❌' }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">类型</span>
          <span class="detail-value">{{ downloaderTypeLabel }}</span>
        </div>

        <!-- 在线时显示速度，离线时显示连接状态 -->
        <template v-if="isOnline">
          <div class="detail-item">
            <span class="detail-label">下载</span>
            <span class="detail-value">{{ status.download_speed || '0.00 KB/s' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">上传</span>
            <span class="detail-value">{{ status.upload_speed || '0.00 KB/s' }}</span>
          </div>
        </template>
        <template v-else>
          <div class="detail-item">
            <span class="detail-label">最后在线</span>
            <span class="detail-value">{{ status.last_online || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">连接</span>
            <span class="detail-value">
              {{ status.connection_msg || '❌ 失败' }}
            </span>
          </div>
        </template>
      </div>
    </div>

    <!-- 卡片底部：操作按钮 + 启用开关 -->
    <div class="downloader-card-footer">
      <div class="action-buttons">
        <button class="action-btn settings" @click="$emit('settings', info)">
          ⚙️ 设置
        </button>
        <button
          class="action-btn sync"
          :disabled="isSyncing"
          @click="$emit('sync', info?.id)"
        >
          {{ isSyncing ? '⏳ 同步中...' : '🔄 同步' }}
        </button>
        <button class="action-btn delete" @click="$emit('delete', info)">
          🗑️
        </button>
      </div>
      <div class="enable-switch">
        <span class="enable-switch-label">启用</span>
        <el-switch
          :value="(info.enabled === '1') || (info.enabled === '0')"
          @input="$emit('toggle-enable', info)"
        />
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'
import { Downloader, DownloaderStatus, OnlineStatus } from '../types'

@Component({
  name: 'DownloaderCard'
})
export default class DownloaderCard extends Vue {
  @Prop({ required: true }) info!: Downloader
  @Prop({ required: true }) status!: DownloaderStatus
  @Prop({ default: false }) isTesting!: boolean
  @Prop({ default: false }) isSyncing!: boolean

  // 计算属性：下载器类型标签
  get downloaderTypeLabel(): string {
    // 优先使用后端返回的 downloaderTypeName 字段（已转换好的类型名称）
    if (this.info.downloaderTypeName) {
      return this.info.downloaderTypeName === 'qbittorrent' ? 'qBittorrent' : 'Transmission'
    }

    // 降级：使用数字枚举转换
    const type = this.info.downloaderType
    if (type === 0) return 'qBittorrent'
    if (type === 1) return 'Transmission'

    // 未知类型兜底
    return '未知类型'
  }

  // 计算属性：在线状态（优先使用 online，降级到 connection_status）
  get isOnline(): boolean {
    // 优先使用 online 字段
    if (this.status.online === true) return true
    if (this.status.online === false) return false

    // online 为 undefined 时，根据 connection_status 降级判断
    return this.status.connection_status === 'success'
  }

  // 计算属性：在线状态枚举
  get onlineStatus(): OnlineStatus {
    if (this.isTesting) return OnlineStatus.TESTING
    return this.isOnline ? OnlineStatus.ONLINE : OnlineStatus.OFFLINE
  }

  // 计算属性：状态徽章样式类
  get statusClass(): string {
    return this.onlineStatus
  }

  // 计算属性：状态文本
  get statusText(): string {
    switch (this.onlineStatus) {
      case OnlineStatus.ONLINE:
        return '在线'
      case OnlineStatus.OFFLINE:
        return '离线'
      case OnlineStatus.TESTING:
        return '测试中'
      default:
        return '未知'
    }
  }

  // 方法：显示值（支持降级逻辑）
  displayValue(value: any, suffix = '', fallback = '-'): string {
    if (value === undefined || value === null) return fallback
    return `${value}${suffix}`
  }
}
</script>

<style lang="scss" scoped>
// 使用项目CSS变量
@import '@/styles/theme-variables.scss';

// 正方形卡片
.downloader-card {
  aspect-ratio: 1 / 1;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-xl);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-md);
  transition: all var(--transition-base);
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;

  // 顶部渐变条（hover时显示）
  &-top-bar {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, var(--color-primary), var(--color-primary-light));
    opacity: 0;
    transition: opacity var(--transition-base);
  }

  &:hover {
    box-shadow: var(--shadow-lg);
    border-color: var(--color-border-focus);
    transform: translateY(-4px);

    .downloader-card-top-bar {
      opacity: 1;
    }
  }
}

// 卡片头部
.downloader-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
}

.downloader-card-info {
  flex: 1;
}

.downloader-card-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin-bottom: 6px;
}

.downloader-card-type {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: var(--color-bg-tertiary);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  display: inline-block;
}

// 状态徽章
.downloader-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  padding: 6px 12px;
  border-radius: var(--radius-md);
  white-space: nowrap;

  &.online {
    background: var(--color-success-lightest);
    color: var(--color-success);
  }

  &.offline {
    background: var(--color-error-light);
    color: var(--color-error);
  }

  &.testing {
    background: var(--color-info-lightest);
    color: var(--color-info);
  }
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

// 卡片内容区
.downloader-card-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

// 统计数据网格
.downloader-card-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-lg);
}

.downloader-stat {
  text-align: center;
}

.downloader-stat-value {
  font-size: 20px;
  font-weight: var(--font-weight-bold);
  color: var(--color-primary);
  margin-bottom: 4px;
}

.downloader-stat-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

// 详细信息
.downloader-card-details {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  font-size: var(--font-size-xs);
}

.detail-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 8px;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
}

.detail-label {
  color: var(--color-text-tertiary);
}

.detail-value {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

// 卡片底部操作区
.downloader-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: auto;
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

// 左侧操作按钮
.action-buttons {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 8px 14px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  border: none;
  cursor: pointer;
  transition: all var(--transition-base);

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &.edit {
    background: var(--color-primary);
    color: white;

    &:hover:not(:disabled) {
      background: var(--color-primary-hover);
    }
  }

  &.test {
    background: var(--color-info);
    color: white;

    &:hover:not(:disabled) {
      background: var(--color-info-dark);
    }
  }

&.settings {    background: #F59E0B;    color: white;    &:hover:not(:disabled) {      background: #D97706;    }  }
    &.sync {
    background: var(--color-success);
    color: white;

    &:hover:not(:disabled) {
      background: var(--color-success-dark);
    }
  }

&.delete {
    background: var(--color-error-light);
    color: var(--color-error);

    &:hover:not(:disabled) {
      background: #fecaca;
    }
  }
}

// 右侧启用开关
.enable-switch {
  display: flex;
  align-items: center;
  gap: 8px;
}

.enable-switch-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}
</style>
