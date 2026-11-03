<template>
  <div>
    <div
      v-for="site in buckets"
      :key="site.host"
      class="dash-hbar-row"
    >
      <span class="dash-hbar-name">{{ displayName(site.host) }}</span>
      <div class="dash-hbar-track">
        <div
          class="dash-hbar-fill"
          :class="{muted: site.host === 'other'}"
          :style="{width: widthOf(site)}"
        />
      </div>
      <span class="dash-hbar-val mono">{{ site.count }}</span>
    </div>
    <div
      v-if="buckets.length === 0"
      class="dash-empty"
    >
      <lucide-icon icon="globe" />
      <span>{{ $t('dashboard.widgets.sites.empty') }}</span>
    </div>
    <div class="dash-muted sites-note">
      {{ $t('dashboard.widgets.sites.note') }}
    </div>
  </div>
</template>

<script lang="ts">
/**
 * SiteBarsCard —— Tracker 站点分布横向条形 widget（仪表盘一期 W2）。
 *
 * 数据源：W1 torrents.siteBuckets（tracker_host 去端口归一、按种子去重
 * 计数、TopN + other，5min 独立节流）。显示名直接用 host（tracker_mapper
 * 仅支持 host 提取，站点别名映射不在一期范围——计划 v2 M-4 口径）。
 * CSS 横条实现（对齐示意图），非 echarts（少一个图表类型有助于 gz 预算）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'
import { SiteBucket } from '@/types/dashboard'

@Component({ name: 'SiteBarsCard' })
export default class SiteBarsCard extends Vue {
  @Prop({ required: true }) private buckets!: SiteBucket[]

  private get maxCount(): number {
    return this.buckets.reduce((m, b) => Math.max(m, b.count), 0)
  }

  private widthOf(site: SiteBucket): string {
    if (this.maxCount <= 0) return '0%'
    return `${Math.max(4, Math.round((site.count / this.maxCount) * 100))}%`
  }

  private displayName(host: string): string {
    return host === 'other' ? this.$t('dashboard.widgets.sites.other').toString() : host
  }
}
</script>

<style lang="scss" scoped>
.sites-note {
  font-size: 11.5px;
  margin-top: 8px;
}
</style>
