<template>
  <div class="filter-group">
    <button
      type="button"
      class="filter-group-header"
      :aria-expanded="String(!collapsed)"
      :aria-controls="itemsId"
      @click="toggleCollapsed"
    >
      <span>{{ title }}</span>
      <span class="arrow" :class="{collapsed}">▾</span>
    </button>
    <div :id="itemsId" class="filter-group-items" v-show="!collapsed">
      <button
        v-for="item in items"
        :key="item.value"
        type="button"
        class="filter-item"
        :class="{active: isActive(item.value)}"
        :aria-pressed="String(isActive(item.value))"
        @click="selectItem(item.value)"
      >
        <span class="filter-icon">{{ item.icon }}</span>
        <span class="filter-label" :title="item.label">{{ item.label }}</span>
        <span v-if="item.count !== undefined" class="filter-count">{{ item.count }}</span>
      </button>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'

export interface FilterItem {
  icon: string
  label: string
  value: string
  count?: number
}

@Component({
  name: 'FilterGroup'
})
export default class extends Vue {
  @Prop(String) readonly title!: string
  @Prop({ type: Array as () => FilterItem[], default: () => [] }) readonly items!: FilterItem[]
  @Prop({ type: [String, Array] as () => string | string[], default: '' }) readonly activeValue!: string | string[]

  private collapsed = false

  private get itemsId(): string {
    const normalizedTitle = this.title.replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, '-')
    return `filter-group-${normalizedTitle || 'items'}-${this._uid}`
  }

  private toggleCollapsed() {
    this.collapsed = !this.collapsed
  }

  private selectItem(value: string) {
    this.$emit('select', value)
  }

  private isActive(value: string): boolean {
    if (Array.isArray(this.activeValue)) {
      return this.activeValue.includes(value)
    }
    return this.activeValue === value
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/traditional-view-theme.scss';

.filter-group-header,
.filter-item {
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;

  &:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: -2px;
  }
}
</style>
