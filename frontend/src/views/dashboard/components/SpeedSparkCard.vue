<template>
  <div>
    <div
      v-if="!ready"
      class="dash-empty"
      data-testid="spark-empty"
    >
      <lucide-icon icon="activity" />
      <span>{{ $t('dashboard.widgets.spark.sampling') }}</span>
    </div>
    <template v-else>
      <slot />
      <div class="dash-legend spark-legend">
        <span class="item">
          <span
            class="sw"
            style="background:var(--color-primary)"
          />
          {{ $t('dashboard.downloadSpeed') }}
        </span>
        <span class="item">
          <span
            class="sw"
            style="background:var(--color-info)"
          />
          {{ $t('dashboard.uploadSpeed') }}
        </span>
        <span class="dash-muted sample-note">{{ $t('dashboard.widgets.spark.note') }}</span>
      </div>
    </template>
  </div>
</template>

<script lang="ts">
/**
 * SpeedSparkCard —— 速度曲线 widget 壳（仪表盘一期 W2；曲线本体 W3 接
 * echarts 深路径双线渐变面积图，此处提供空态/图例与内容插槽）。
 *
 * 数据源：active-torrents 3s 采样累积 60 点（父级持有采样数组，W3 落地）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'

@Component({ name: 'SpeedSparkCard' })
export default class SpeedSparkCard extends Vue {
  /** 采样未满时显示采样中空态 */
  @Prop({ default: false }) private ready!: boolean
}
</script>

<style lang="scss" scoped>
.spark-legend {
  margin-top: 8px;
}

.sample-note {
  margin-left: auto;
  font-size: 11.5px;
}
</style>
