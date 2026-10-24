<template>
  <div
    class="caliber-notes"
    data-testid="caliber-notes"
  >
    <div
      v-for="(item, index) in normalizedNotes"
      :key="index"
      class="caliber-notes__item"
    >
      · {{ $t(item.key, item.params) }}
    </div>
  </div>
</template>

<script lang="ts">
/**
 * 口径脚注区（statistics-reports W5，四页签共用）。
 *
 * 统一消费 i18n 键（statistics.calibers.*，PLANS/statistics-reports.md §3.4
 * "口径脚注集中 i18n"）；条目支持两种形态：
 * - 'statistics.calibers.xxx'（无插值）
 * - { key: 'statistics.calibers.samplingStart', params: { time: '...' } }
 */
import { Component, Prop, Vue } from 'vue-property-decorator'

export interface CaliberNoteItem {
  key: string
  params?: Record<string, unknown>
}

@Component({ name: 'CaliberNotes' })
export default class CaliberNotes extends Vue {
  @Prop({ type: Array, required: true })
  private readonly notes!: Array<string | CaliberNoteItem>

  private get normalizedNotes(): CaliberNoteItem[] {
    return this.notes.map((n) => (typeof n === 'string' ? { key: n } : n))
  }
}
</script>

<style scoped>
.caliber-notes {
  margin-top: 8px;
  padding: 10px 14px;
  border-radius: 6px;
  background: var(--app-card-bg, #fafafa);
  border: 1px dashed var(--app-border-color, #dcdfe6);
}

.caliber-notes__item {
  font-size: 12px;
  line-height: 1.8;
  color: var(--app-text-secondary, #909399);
}
</style>
