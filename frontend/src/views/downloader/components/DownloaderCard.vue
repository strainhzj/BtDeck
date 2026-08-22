<template>
  <article :class="['downloader-node', `downloader-node--${statusClass}`]">
    <div class="downloader-node__beam" aria-hidden="true" />

    <header class="node-header">
      <div class="node-index">NODE / {{ nodeIndex }}</div>
      <div class="node-identity">
        <span class="node-identity__mark">
          <LucideIcon name="server" :size="20" :stroke-width="1.7" />
        </span>
        <div class="node-identity__copy">
          <h3>{{ info.nickname }}</h3>
          <span :title="displayEndpoint">{{ displayEndpoint }}</span>
        </div>
      </div>
      <div :class="['node-status', statusClass]" aria-live="polite">
        <LucideIcon :name="statusIcon" :size="14" :stroke-width="1.9" />
        <span>{{ statusText }}</span>
      </div>
    </header>

    <div class="node-telemetry">
      <div class="throughput-block throughput-block--download">
        <span class="throughput-block__icon">
          <LucideIcon name="download" :size="16" :stroke-width="1.9" />
        </span>
        <div>
          <span>DOWNLOAD</span>
          <strong>{{ status.download_speed || '0.00 KB/s' }}</strong>
        </div>
      </div>
      <div class="throughput-block throughput-block--upload">
        <span class="throughput-block__icon">
          <LucideIcon name="upload" :size="16" :stroke-width="1.9" />
        </span>
        <div>
          <span>UPLOAD</span>
          <strong>{{ status.upload_speed || '0.00 KB/s' }}</strong>
        </div>
      </div>

      <dl class="node-counters">
        <div>
          <dt>下载中</dt>
          <dd>{{ displayValue(status.downloading_count) }}</dd>
        </div>
        <div>
          <dt>做种中</dt>
          <dd>{{ displayValue(status.seeding_count) }}</dd>
        </div>
        <div>
          <dt>延迟</dt>
          <dd>{{ latencyText }}</dd>
        </div>
      </dl>
    </div>

    <div class="node-meta" aria-label="下载器连接详情">
      <span>
        <LucideIcon name="database" :size="13" :stroke-width="1.8" />
        {{ downloaderTypeLabel }}
      </span>
      <span :class="{'is-positive': isSSL}">
        <LucideIcon :name="isSSL ? 'shield-check' : 'shield-off'" :size="13" :stroke-width="1.8" />
        {{ isSSL ? 'HTTPS' : 'HTTP' }}
      </span>
      <span :class="{'is-positive': searchEnabled}">
        <LucideIcon name="search" :size="13" :stroke-width="1.8" />
        {{ searchEnabled ? '可搜索' : '未搜索' }}
      </span>
      <span>
        <LucideIcon name="clock" :size="13" :stroke-width="1.8" />
        {{ isOnline ? '实时遥测' : (status.connection_msg || '等待连接') }}
      </span>
    </div>

    <footer class="node-footer">
      <label class="node-enable">
        <el-switch
          :value="isEnabled"
          :aria-label="`${info.nickname}启用状态`"
          @input="$emit('toggle-enable', info)"
        />
        <span>
          <strong>{{ isEnabled ? '节点启用' : '节点停用' }}</strong>
          <small>{{ isEnabled ? '参与自动任务' : '仅保留配置' }}</small>
        </span>
      </label>

      <div class="node-actions">
        <button
          type="button"
          class="node-action"
          :disabled="isTesting"
          :aria-label="`测试 ${info.nickname} 的连接`"
          title="测试连接"
          @click="$emit('test', downloaderId)"
        >
          <LucideIcon
            name="activity"
            :size="15"
            :stroke-width="1.9"
            :class="{'is-pulsing': isTesting}"
          />
          <span>{{ isTesting ? '测试中' : '测试' }}</span>
        </button>
        <button
          type="button"
          class="node-action"
          :disabled="isSyncing"
          :aria-label="`同步 ${info.nickname}`"
          title="同步种子"
          @click="$emit('sync', downloaderId)"
        >
          <LucideIcon
            name="refresh-cw"
            :size="15"
            :stroke-width="1.9"
            :class="{'is-spinning': isSyncing}"
          />
          <span>{{ isSyncing ? '同步中' : '同步' }}</span>
        </button>
        <button
          type="button"
          class="node-action node-action--settings"
          :aria-label="`打开 ${info.nickname} 的设置`"
          @click="$emit('settings', info)"
        >
          <LucideIcon name="settings" :size="15" :stroke-width="1.9" />
          <span>设置</span>
        </button>
        <button
          type="button"
          class="node-action node-action--danger"
          :aria-label="`删除 ${info.nickname}`"
          title="删除下载器"
          @click="$emit('delete', info)"
        >
          <LucideIcon name="trash-2" :size="15" :stroke-width="1.9" />
        </button>
      </div>
    </footer>
  </article>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'
import { Downloader, DownloaderStatus, OnlineStatus } from '../types'

@Component({
  name: 'DownloaderCard'
})
export default class DownloaderCard extends Vue {
  @Prop({ default: 0 }) index!: number
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

  get statusIcon(): string {
    if (this.onlineStatus === OnlineStatus.TESTING) return 'activity'
    return this.isOnline ? 'wifi' : 'wifi-off'
  }

  get nodeIndex(): string {
    return String(this.index + 1).padStart(2, '0')
  }

  get downloaderId(): string {
    return String(this.info.id || this.info.downloaderId || '')
  }

  get displayEndpoint(): string {
    const host = String(this.info.host || '').replace(/\/$/, '')
    const port = String(this.info.port || '')
    if (!port || host.endsWith(`:${port}`)) return host
    return `${host}:${port}`
  }

  get isSSL(): boolean {
    return this.info.is_ssl === '1' || String(this.info.host || '').toLowerCase().startsWith('https://')
  }

  get isEnabled(): boolean {
    return this.info.enabled === '1'
  }

  get searchEnabled(): boolean {
    return (this.info.isSearch ?? this.info.is_search) === '1'
  }

  get latencyText(): string {
    if (this.status.delay === undefined || this.status.delay === null) return '-'
    return `${this.status.delay.toFixed(1)} ms`
  }

  // 方法：显示值（支持降级逻辑）
  displayValue(value: string | number | null | undefined, suffix = '', fallback = '-'): string {
    if (value === undefined || value === null) return fallback
    return `${value}${suffix}`
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.downloader-node {
  position: relative;
  min-width: 0;
  min-height: 236px;
  padding: 18px;
  overflow: hidden;
  border: 1px solid rgba(var(--color-primary-rgb), 0.13);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 14px 45px rgba(15, 23, 42, 0.055);
  backdrop-filter: blur(15px);
  transition: transform 420ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 280ms ease, border-color 280ms ease;

  &::before {
    content: '';
    position: absolute;
    top: -100px;
    right: -90px;
    width: 230px;
    height: 230px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(var(--color-primary-rgb), 0.075), transparent 68%);
  }

  &:hover {
    z-index: 2;
    border-color: rgba(var(--color-primary-rgb), 0.34);
    box-shadow: 0 24px 65px rgba(15, 23, 42, 0.1);
    transform: translateY(-3px);
  }

  &--offline {
    filter: saturate(0.82);
  }

  &__beam {
    position: absolute;
    top: 0;
    left: 18px;
    width: 54px;
    height: 2px;
    background: var(--color-warning);
    box-shadow: 0 0 15px rgba(245, 158, 11, 0.35);

    .downloader-node--online & {
      background: var(--color-success);
      box-shadow: 0 0 15px rgba(16, 185, 129, 0.35);
    }

    .downloader-node--testing & {
      background: var(--color-info);
      box-shadow: 0 0 15px rgba(59, 130, 246, 0.35);
    }
  }
}

.node-header {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  margin-bottom: 15px;
}

.node-index {
  position: absolute;
  top: -7px;
  right: 0;
  color: var(--color-text-quaternary);
  font-family: var(--font-mono);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.node-identity {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
  flex: 1;

  &__mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 38px;
    height: 38px;
    flex: 0 0 38px;
    border: 1px solid rgba(var(--color-primary-rgb), 0.16);
    border-radius: 12px;
    background: linear-gradient(145deg, var(--color-bg-primary), rgba(var(--color-primary-rgb), 0.055));
    color: var(--color-primary);
  }

  &__copy {
    min-width: 0;

    h3 {
      overflow: hidden;
      margin: 0 0 3px;
      font-size: 16px;
      font-weight: 680;
      letter-spacing: -0.025em;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    > span {
      display: block;
      max-width: 270px;
      overflow: hidden;
      color: var(--color-text-tertiary);
      font-family: var(--font-mono);
      font-size: 9px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}

.node-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 11px;
  padding: 5px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
  white-space: nowrap;

  &.online {
    background: var(--color-success-lightest);
    border-color: rgba(16, 185, 129, 0.16);
    color: var(--color-success);
  }

  &.offline {
    background: var(--color-error-light);
    border-color: rgba(var(--color-error-rgb), 0.13);
    color: var(--color-error);
  }

  &.testing {
    background: var(--color-info-lightest);
    border-color: rgba(59, 130, 246, 0.14);
    color: var(--color-info);
  }
}

.node-telemetry {
  position: relative;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr)) minmax(170px, 0.82fr);
  gap: 8px;
  margin-bottom: 10px;
}

.throughput-block {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 11px;
  background: rgba(249, 250, 251, 0.88);

  &__icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    flex: 0 0 28px;
    border-radius: 8px;
    background: var(--color-primary-lightest);
    color: var(--color-primary);
  }

  &--upload .throughput-block__icon {
    background: var(--color-info-lightest);
    color: var(--color-info);
  }

  > div {
    min-width: 0;
  }

  span:not(.throughput-block__icon) {
    display: block;
    margin-bottom: 2px;
    color: var(--color-text-tertiary);
    font-family: var(--font-mono);
    font-size: 7px;
    letter-spacing: 0.12em;
  }

  strong {
    display: block;
    overflow: hidden;
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.node-counters {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 0;
  border: 1px solid var(--color-border-secondary);
  border-radius: 11px;
  background: rgba(249, 250, 251, 0.88);

  div {
    min-width: 0;
    padding: 8px 6px;
    border-right: 1px solid var(--color-border-secondary);
    text-align: center;

    &:last-child {
      border-right: 0;
    }
  }

  dt {
    overflow: hidden;
    color: var(--color-text-tertiary);
    font-size: 8px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  dd {
    overflow: hidden;
    margin: 5px 0 0;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 650;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.node-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin-bottom: 11px;
  overflow: hidden;

  span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    padding: 4px 7px;
    border: 1px solid var(--color-border-secondary);
    border-radius: 7px;
    background: rgba(249, 250, 251, 0.76);
    color: var(--color-text-tertiary);
    font-size: 8px;
    white-space: nowrap;

    &:last-child {
      overflow: hidden;
      text-overflow: ellipsis;
    }

    &.is-positive {
      color: var(--color-primary);
    }
  }
}

.node-footer {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding-top: 11px;
  border-top: 1px solid var(--color-border-secondary);
}

.node-enable {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;

  > span {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  strong {
    font-size: 9px;
    font-weight: 650;
  }

  small {
    margin-top: 1px;
    color: var(--color-text-tertiary);
    font-size: 7px;
    white-space: nowrap;
  }

  ::v-deep .el-switch {
    transform: scale(0.78);
    transform-origin: left center;
    margin-right: -8px;
  }
}

.node-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.node-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 34px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--color-border-primary);
  border-radius: 8px;
  background: var(--color-bg-primary);
  color: var(--color-text-secondary);
  font-size: 9px;
  font-weight: 600;
  cursor: pointer;
  transition: transform var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast), background var(--transition-fast);

  &:hover:not(:disabled),
  &:focus-visible {
    border-color: rgba(var(--color-primary-rgb), 0.4);
    background: var(--color-primary-lightest);
    color: var(--color-primary);
    transform: translateY(-1px);
    outline: none;
  }

  &:disabled {
    opacity: 0.46;
    cursor: not-allowed;
  }

  &--settings {
    border-color: rgba(var(--color-primary-rgb), 0.23);
    color: var(--color-primary);
  }

  &--danger {
    padding: 0 7px;
    border-color: rgba(var(--color-error-rgb), 0.14);
    color: var(--color-error);

    &:hover:not(:disabled) {
      border-color: rgba(var(--color-error-rgb), 0.3);
      background: var(--color-error-light);
      color: var(--color-error);
    }
  }
}

.is-spinning {
  animation: node-spin 0.85s linear infinite;
}

.is-pulsing {
  animation: node-pulse 1s ease-in-out infinite;
}

@keyframes node-spin {
  to { transform: rotate(360deg); }
}

@keyframes node-pulse {
  50% { opacity: 0.4; transform: scale(0.9); }
}

@media (max-width: 560px) {
  .downloader-node {
    padding: 15px;
  }

  .node-telemetry {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .node-counters {
    grid-column: 1 / -1;
  }

  .node-footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .node-actions {
    width: 100%;
  }

  .node-action {
    flex: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .downloader-node,
  .node-action {
    transition-duration: 0.01ms !important;
  }

  .is-spinning,
  .is-pulsing {
    animation: none !important;
  }
}
</style>
