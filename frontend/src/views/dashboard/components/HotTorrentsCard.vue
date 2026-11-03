<template>
  <div>
    <div
      v-for="(t, i) in top5"
      :key="t.hash + i"
      class="dash-tor-row"
    >
      <span class="dash-tor-rank">{{ i + 1 }}</span>
      <div
        class="grow dash-ellip"
        :title="nameOf(t)"
      >
        {{ nameOf(t) }}
      </div>
      <span class="dash-tor-sp dl">
        <lucide-icon icon="arrow-down" />
        <span class="mono">{{ speedText(t.downloadSpeed) }}</span>
      </span>
      <span class="dash-tor-sp ul">
        <lucide-icon icon="arrow-up" />
        <span class="mono">{{ speedText(t.uploadSpeed) }}</span>
      </span>
    </div>
    <div
      v-if="top5.length === 0"
      class="dash-empty"
    >
      <lucide-icon icon="flame" />
      <span>{{ $t('dashboard.widgets.hot.empty') }}</span>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * HotTorrentsCard —— 热门种子 widget（仪表盘一期 W2 骨架 / W3 收口排序口径）。
 *
 * 数据源：GET /torrents/active-torrents（3s 轮询），前端按速度
 * （下载+上传之和）排序 Top5；名称来自端点 name 键（W2 扩展，qB/TR 均
 * 返回），缺失时回退 hash 前缀。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import { ActiveTorrentSpeed } from '@/api/torrents'
import { formatSpeed } from '@/utils/formatters'

@Component({ name: 'HotTorrentsCard' })
export default class HotTorrentsCard extends Vue {
  @Prop({ required: true }) private torrents!: ActiveTorrentSpeed[]

  private get top5(): ActiveTorrentSpeed[] {
    return [...this.torrents]
      .sort((a, b) => (b.downloadSpeed + b.uploadSpeed) - (a.downloadSpeed + a.uploadSpeed))
      .slice(0, 5)
  }

  private nameOf(t: ActiveTorrentSpeed): string {
    return t.name || t.hash.slice(0, 12)
  }

  private speedText(bytesPerSec: number): string {
    return formatSpeed(bytesPerSec || 0) || '0 B/s'
  }
}
</script>
