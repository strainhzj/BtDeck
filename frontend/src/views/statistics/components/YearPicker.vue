<template>
  <div
    class="year-picker"
    data-testid="year-picker"
  >
    <button
      v-for="y in years"
      :key="y"
      type="button"
      class="year-picker__item"
      :class="{'year-picker__item--active': y === value}"
      :data-year="y"
      @click="emitChange(y)"
    >
      {{ y }}
    </button>
  </div>
</template>

<script lang="ts">
/**
 * 年度报告年份选择器（statistics-reports W6，fun-report 专属）。
 *
 * 年份范围 2024–当前年（PLANS/statistics-reports.md §1.2 编号 26）；
 * 变更经 change 事件上抛（父级写回 route query 持久化——决策 10）。
 */
import { Component, Prop, Vue } from 'vue-property-decorator'

@Component({ name: 'YearPicker' })
export default class YearPicker extends Vue {
  @Prop({ type: Number, required: true })
  private readonly value!: number

  private get years(): number[] {
    const current = new Date().getFullYear()
    const list: number[] = []
    for (let y = current; y >= 2024; y--) {
      list.push(y)
    }
    return list
  }

  private emitChange(year: number): void {
    if (year !== this.value) {
      this.$emit('change', year)
    }
  }
}
</script>

<style scoped>
.year-picker {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.year-picker__item {
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s;
}

.year-picker__item:hover {
  background: rgba(255, 255, 255, 0.3);
}

.year-picker__item--active {
  background: #fff;
  color: #303133;
  font-weight: 600;
}
</style>
