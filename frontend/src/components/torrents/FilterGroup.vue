<template>
  <div class="filter-group">
    <div class="filter-group-header" @click="toggleCollapsed">
      <span>{{ title }}</span>
      <span class="arrow" :class="{ collapsed }">▾</span>
    </div>
    <div class="filter-group-items" v-show="!collapsed">
      <div
        v-for="item in items"
        :key="item.value"
        class="filter-item"
        :class="{ active: isActive(item.value) }"
        @click="$emit('select', item.value)"
      >
        <span class="filter-icon">{{ item.icon }}</span>
        <span class="filter-label" :title="item.label">{{ item.label }}</span>
        <span v-if="item.count !== undefined" class="filter-count">{{ item.count }}</span>
      </div>
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

  private toggleCollapsed() {
    this.collapsed = !this.collapsed
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
</style>
