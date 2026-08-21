<template>
  <section
    class="management-panel collapsible-panel"
    :aria-labelledby="titleId"
    :class="{'collapsible-panel--collapsed': isCollapsed}"
  >
    <div class="management-panel__header">
      <button
        type="button"
        class="collapsible-panel__toggle"
        :aria-expanded="String(!isCollapsed)"
        :aria-controls="contentId"
        @click="handleToggle"
      >
        <div class="management-panel__heading">
          <h2 :id="titleId" class="management-panel__title">{{ title }}</h2>
          <p v-if="description" class="management-panel__description">{{ description }}</p>
        </div>
        <span class="collapsible-panel__chevron">
          <LucideIcon :name="isCollapsed ? 'chevron-down' : 'chevron-up'" :size="16" />
        </span>
      </button>
      <div v-if="$slots.meta" class="management-panel__meta">
        <slot name="meta" />
      </div>
    </div>
    <div v-show="!isCollapsed" :id="contentId" class="collapsible-panel__content">
      <slot />
    </div>
  </section>
</template>

<script lang="ts">
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import LucideIcon from '@/components/common/LucideIcon.vue'
import { getStorage, setStorage } from '@/utils/cookies'

/**
 * 通用可折叠面板（verified-bugfix-remediation W8-1）
 *
 * - 折叠状态可选持久化：storageKey 提供时写入 localStorage（btdeck_ 前缀），
 *   不提供则仅会话内生效（dashboard 等"按需求排除"页面天然不写存储）
 * - 未设置存储值时默认展开；显式 '1' 表示折叠（与 '0'/null 区分）
 * - a11y：aria-expanded / aria-controls（对齐 FilterGroup 既有写法）
 */
@Component({
  name: 'CollapsiblePanel',
  components: { LucideIcon }
})
export default class CollapsiblePanel extends Vue {
  @Prop({ type: String, required: true }) title!: string
  @Prop({ type: String, default: '' }) description!: string
  @Prop({ type: String, default: '' }) storageKey!: string
  @Prop({ type: Boolean, default: false }) defaultCollapsed!: boolean

  private collapsed = false
  // 实例唯一 ID（多实例共存时 aria 关联不冲突）
  private readonly uid = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`

  get isCollapsed(): boolean {
    return this.collapsed
  }

  get titleId(): string {
    return `collapsible-panel-title-${this.uid}`
  }

  get contentId(): string {
    return `collapsible-panel-content-${this.uid}`
  }

  created() {
    if (this.storageKey) {
      // null（未设置）与 '0' 区分：未设置时回退 defaultCollapsed
      const stored = getStorage(this.storageKey)
      this.collapsed = stored === null ? this.defaultCollapsed : stored === '1'
    } else {
      this.collapsed = this.defaultCollapsed
    }
  }

  @Watch('collapsed')
  onCollapsedChange(value: boolean) {
    if (this.storageKey) {
      setStorage(this.storageKey, value ? '1' : '0')
    }
    this.$emit('input', value)
  }

  private handleToggle() {
    this.collapsed = !this.collapsed
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.collapsible-panel {
  .management-panel__header {
    align-items: center;
  }

  &__toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex: 1;
    min-width: 0;
    gap: var(--spacing-md, 12px);
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
    text-align: left;
    color: inherit;

    &:hover .collapsible-panel__chevron {
      color: var(--color-primary, #409eff);
    }

    &:focus-visible {
      outline: 2px solid var(--color-primary, #409eff);
      outline-offset: 2px;
      border-radius: 6px;
    }
  }

  &__chevron {
    display: inline-flex;
    flex-shrink: 0;
    color: var(--color-text-secondary, #909399);
    transition: color 0.15s ease;
  }

  &__content {
    padding-top: var(--spacing-md, 12px);
  }
}
</style>
