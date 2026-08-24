<template>
  <div
    class="m-pull-indicator"
    :class="{'is-ready': ready, 'is-refreshing': refreshing}"
    :style="{ height: indicatorHeight + 'px' }"
  >
    <span v-if="refreshing" class="m-pull-indicator-text">刷新中…</span>
    <span v-else-if="ready" class="m-pull-indicator-text">↓ 松手刷新</span>
    <span v-else-if="distance > 0" class="m-pull-indicator-text">↓ 下拉刷新</span>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'
import { PULL_INDICATOR_REFRESHING_HEIGHT } from '@/views/mobile/mixins/pull-to-refresh'

/**
 * 移动下拉刷新指示条（Phase 4 M1）：mixin 提供状态，页面顶部放置本组件。
 * 拉动时高度随 distance（封顶 80px）增长，刷新中固定 36px。
 */
@Component({ name: 'MobilePullIndicator' })
export default class MobilePullIndicator extends Vue {
  @Prop({ type: Number, default: 0 }) private distance!: number
  @Prop({ type: Boolean, default: false }) private ready!: boolean
  @Prop({ type: Boolean, default: false }) private refreshing!: boolean

  private get indicatorHeight(): number {
    if (this.refreshing) return PULL_INDICATOR_REFRESHING_HEIGHT
    return Math.min(this.distance, 80)
  }
}
</script>

<style scoped>
.m-pull-indicator {
  overflow: hidden;
  text-align: center;
  transition: height 0.2s ease;
}

.m-pull-indicator-text {
  font-size: 12px;
  color: #909399;
  line-height: 36px;
  white-space: nowrap;
}

.m-pull-indicator.is-ready .m-pull-indicator-text {
  color: var(--color-primary);
  font-weight: 600;
}
</style>
