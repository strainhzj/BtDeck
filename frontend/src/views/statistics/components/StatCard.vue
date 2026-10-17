<template>
  <div
    class="stat-card"
    data-testid="stat-card"
  >
    <div class="stat-card__label">{{ label }}</div>
    <div
      class="stat-card__value"
      data-testid="stat-card-value"
    >{{ value }}</div>
    <div
      v-if="sub"
      class="stat-card__sub"
      data-testid="stat-card-sub"
    >{{ sub }}</div>
    <slot />
  </div>
</template>

<script lang="ts">
/**
 * 统计数字卡（statistics-reports W5，四页签共用）。
 *
 * label/value/sub 纯展示；额外内容（图标/链接等）经默认插槽注入。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'

@Component({ name: 'StatCard' })
export default class StatCard extends Vue {
  @Prop({ type: String, required: true })
  private readonly label!: string

  @Prop({ type: [String, Number], required: true })
  private readonly value!: string | number

  @Prop({ type: String, default: '' })
  private readonly sub!: string
}
</script>

<style scoped>
.stat-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 18px;
  border-radius: 8px;
  background: var(--app-card-bg, #fff);
  border: 1px solid var(--app-border-color, #ebeef5);
  min-width: 0;
}

.stat-card__label {
  font-size: 12px;
  color: var(--app-text-secondary, #909399);
}

.stat-card__value {
  font-size: 22px;
  font-weight: 600;
  color: var(--app-text-primary, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat-card__sub {
  font-size: 12px;
  color: var(--app-text-secondary, #909399);
}
</style>
