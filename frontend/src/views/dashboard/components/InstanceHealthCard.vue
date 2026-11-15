<template>
  <div>
    <div
      v-for="dl in list"
      :key="dl.downloader_id"
      class="dash-rowline"
      :class="{'is-clickable': clickable}"
      :role="clickable ? 'button' : undefined"
      :tabindex="clickable ? 0 : undefined"
      @click="clickable && $emit('activate', dl.downloader_id)"
      @keypress.enter="clickable && $emit('activate', dl.downloader_id)"
    >
      <svg
        class="dash-mini-ring"
        viewBox="0 0 34 34"
        :aria-hidden="true"
      >
        <circle
          cx="17"
          cy="17"
          r="13"
          fill="none"
          stroke="var(--color-bg-tertiary)"
          stroke-width="4"
        />
        <circle
          cx="17"
          cy="17"
          r="13"
          fill="none"
          :stroke="ringColor(dl)"
          stroke-width="4"
          :stroke-dasharray="ringDash(dl)"
          stroke-linecap="round"
        />
      </svg>
      <div class="grow">
        <div style="font-weight:600">
          {{ dl.nickname }}
        </div>
        <div class="dash-muted ellip-inline">
          {{ typeLabel(dl.downloader_type) }}
        </div>
      </div>
      <div style="text-align:right">
        <div>
          <span class="dash-tor-sp dl">
            <lucide-icon name="arrow-down" />
            <span class="mono">{{ speedText(dl.download_speed) }}</span>
          </span>
          <span class="dash-tor-sp ul">
            <lucide-icon name="arrow-up" />
            <span class="mono">{{ speedText(dl.upload_speed) }}</span>
          </span>
        </div>
        <div class="dash-muted download-seed-line">
          {{ $t('dashboard.widgets.health.dlCount', {count: dl.downloading}) }}
          ·
          {{ $t('dashboard.widgets.health.sdCount', {count: dl.seeding}) }}
        </div>
      </div>
      <span :class="['dash-status-pill', dl.status === 'online' ? 'st-online' : 'st-offline']">
        {{ dl.status === 'online' ? $t('dashboard.online') : $t('dashboard.offline') }}
      </span>
    </div>
    <div
      v-if="list.length === 0"
      class="dash-empty"
    >
      <lucide-icon name="server" />
      <span>{{ $t('dashboard.widgets.health.empty') }}</span>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * InstanceHealthCard —— 实例健康 widget（仪表盘一期 W2）。
 *
 * 数据源：GET /dashboard 的 downloader_list（snake_case 契约）。
 * 健康环（决策 #4：无实际分享率）：在线状态 + 速度活跃度前端推导——
 * 在线且速度>0 → 满环绿色；在线零速 → 中环黄色（警示）；离线 → 空环灰。
 * clickable（移动仪表盘二期评审修复）：行级 role=button + click/enter
 * 上抛 activate(downloader_id)，桌面不传不受影响。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import { DownloaderListItem } from '@/types/dashboard'
import { formatSpeed } from '@/utils/formatters'

const RING_CIRC = 2 * Math.PI * 13

@Component({ name: 'InstanceHealthCard' })
export default class InstanceHealthCard extends Vue {
  @Prop({ required: true }) private list!: DownloaderListItem[]
  /** 行可点击穿透（Boolean 显式声明使裸属性形态正确转换） */
  @Prop({ type: Boolean, default: false }) private clickable!: boolean

  private activity(dl: DownloaderListItem): number {
    if (dl.status !== 'online') return 0
    const speed = (dl.download_speed || 0) + (dl.upload_speed || 0)
    return speed > 0 ? 0.9 : 0.55
  }

  private ringColor(dl: DownloaderListItem): string {
    if (dl.status !== 'online') return 'var(--color-text-quaternary, #d1d5db)'
    return this.activity(dl) > 0.7 ? 'var(--color-success)' : 'var(--color-warning)'
  }

  private ringDash(dl: DownloaderListItem): string {
    const p = this.activity(dl)
    return `${(RING_CIRC * p).toFixed(1)} ${RING_CIRC.toFixed(1)}`
  }

  private speedText(bytesPerSec: number): string {
    return formatSpeed(bytesPerSec || 0) || '0 B/s'
  }

  private typeLabel(type: number): string {
    if (type === 0) return 'qBittorrent'
    if (type === 1) return 'Transmission'
    if (type === 2) return 'rTorrent'
    return 'Unknown'
  }
}
</script>

<style lang="scss" scoped>
.ellip-inline {
  font-size: 11.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.download-seed-line {
  font-size: 11px;
  margin-top: 2px;
}

.is-clickable {
  cursor: pointer;
}
</style>
