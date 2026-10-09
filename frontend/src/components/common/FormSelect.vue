<template>
  <div
    ref="root"
    class="form-select"
    :class="{
      'is-open': expanded,
      'is-invalid': invalid,
      'is-disabled': disabled
    }"
  >
    <!-- 触发器 -->
    <div
      class="form-select__trigger"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="String(expanded)"
      :aria-controls="dropdownId"
      :tabindex="disabled ? -1 : 0"
      @click="toggleDropdown"
      @keydown="onTriggerKeydown"
    >
      <template v-if="multiple">
        <div class="form-select__chips">
          <span
            v-for="opt in selectedOptions"
            :key="opt.value"
            class="form-select__chip"
          >
            <span class="form-select__chip-text">{{ opt.label }}</span>
            <button
              type="button"
              class="form-select__chip-remove"
              :aria-label="$t('common.formSelect.removeTag', {label: opt.label})"
              :disabled="disabled"
              @click.stop="removeChip(opt.value)"
            >
              <LucideIcon name="x" :size="12" />
            </button>
          </span>
          <span v-if="selectedOptions.length === 0" class="form-select__placeholder">
            {{ placeholder }}
          </span>
        </div>
      </template>
      <template v-else>
        <span class="form-select__value" :class="{'is-placeholder': !hasSingleValue}">
          {{ selectedLabel || placeholder }}
        </span>
      </template>

      <button
        v-if="clearable && hasValue && !disabled"
        type="button"
        class="form-select__clear"
        :aria-label="$t('common.formSelect.clear')"
        @click.stop="handleClear"
      >
        <LucideIcon name="x" :size="14" />
      </button>
      <LucideIcon
        name="chevron-down"
        :size="16"
        class="form-select__arrow"
        :class="{'is-open': expanded}"
      />
    </div>

    <!-- 下拉浮层：默认仍在 DOM 子节点；展开时由 mixin teleport 到 body 并 fixed 定位 -->
    <div
      v-show="expanded"
      ref="options"
      :id="dropdownId"
      class="form-select__dropdown"
      :class="{'is-floating': isFloating}"
      role="listbox"
      :aria-label="placeholder"
      :aria-activedescendant="`${dropdownId}-opt-${highlightIndex}`"
    >
      <div v-if="filterable" class="form-select__filter">
        <LucideIcon name="search" :size="14" class="form-select__filter-icon" />
        <input
          ref="filterInput"
          v-model="query"
          type="text"
          class="form-select__filter-input"
          :placeholder="$t('common.formSelect.searchPlaceholder')"
          autocomplete="off"
          @keydown="onFilterKeydown"
        >
      </div>
      <ul ref="list" class="form-select__list">
        <li
          v-for="(opt, index) in filteredOptions"
          :id="`${dropdownId}-opt-${index}`"
          :key="opt.value"
          class="form-select__option"
          :class="{
            'is-selected': isSelected(opt),
            'is-highlighted': index === highlightIndex
          }"
          role="option"
          :aria-selected="String(isSelected(opt))"
          @mouseenter="highlightIndex = index"
          @click="handleOptionClick(opt)"
        >
          <slot name="option" :option="opt" :selected="isSelected(opt)">
            <span class="form-select__option-main">
              <span
                v-if="opt.status"
                class="form-select__status-dot"
                :class="`is-${opt.status}`"
              />
              <span class="form-select__option-label">{{ opt.label }}</span>
            </span>
            <span
              v-if="opt.badge"
              class="form-select__badge"
              :class="opt.badgeTone ? `is-${opt.badgeTone}` : ''"
            >{{ opt.badge }}</span>
          </slot>
          <LucideIcon
            v-if="isSelected(opt)"
            name="check"
            :size="14"
            class="form-select__check"
          />
        </li>
        <li v-if="filteredOptions.length === 0" class="form-select__empty" role="presentation">
          {{ options.length === 0 ? $t('common.formSelect.noOptions') : $t('common.formSelect.noMatch') }}
        </li>
      </ul>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Watch } from 'vue-property-decorator'
import { mixins } from 'vue-class-component'
import FloatingDropdown from './floatingDropdown'
import type { FormSelectOption } from './formControls'

/**
 * FormSelect —— 全自定义下拉选择器（零 Element UI）
 *
 * - single / multiple 双模式：多选渲染 tag chips（可单独移除）；
 * - filterable / clearable / disabled / invalid（错误态边框）；
 * - 键盘流：触发器 ↑/Enter/Space 展开，浮层内 ↑↓ 高亮、Enter 选中、Esc 关闭；
 * - ARIA combobox + listbox（aria-expanded/controls/selected/activedescendant）；
 * - 浮层 teleport 到 body + 上下自适应定位（复用 FloatingDropdown mixin）。
 */
@Component({ name: 'FormSelect' })
export default class FormSelect extends mixins(FloatingDropdown) {
  @Prop({ default: '' }) value!: string | string[]
  @Prop({ default: () => [] }) options!: FormSelectOption[]
  @Prop({ type: Boolean, default: false }) multiple!: boolean
  @Prop({ type: Boolean, default: false }) filterable!: boolean
  @Prop({ type: Boolean, default: false }) clearable!: boolean
  @Prop({ type: Boolean, default: false }) disabled!: boolean
  /** 错误态（宿主校验失败时红边） */
  @Prop({ type: Boolean, default: false }) invalid!: boolean
  @Prop({ type: String, default: '' }) placeholder!: string

  private query = ''
  private highlightIndex = 0

  get dropdownId(): string {
    return `form-select-options-${this._uid}`
  }

  /** 归一化为数组：统一单/多选的选中判定路径 */
  get normalizedValue(): string[] {
    if (Array.isArray(this.value)) return this.value
    return this.value === '' || this.value === undefined || this.value === null ? [] : [this.value]
  }

  get selectedOptions(): FormSelectOption[] {
    return this.options.filter(opt => this.normalizedValue.includes(opt.value))
  }

  get hasValue(): boolean {
    return this.normalizedValue.length > 0
  }

  get hasSingleValue(): boolean {
    return !this.multiple && this.hasValue
  }

  get selectedLabel(): string {
    if (this.multiple) return ''
    const first = this.selectedOptions[0]
    if (first) return first.label
    // 选项尚未加载（如异步标签列表）：回显原始值，避免显示成空
    return this.hasValue ? String(this.value) : ''
  }

  get filteredOptions(): FormSelectOption[] {
    const keyword = this.query.trim().toLowerCase()
    if (!this.filterable || !keyword) return this.options
    return this.options.filter(
      opt => opt.label.toLowerCase().includes(keyword) || opt.value.toLowerCase().includes(keyword)
    )
  }

  @Watch('query')
  onQueryChange(): void {
    this.highlightIndex = 0
    this.notifyDropdownContentChanged()
  }

  @Watch('filteredOptions')
  onFilteredOptionsChange(): void {
    if (this.highlightIndex >= this.filteredOptions.length) this.highlightIndex = 0
    this.notifyDropdownContentChanged()
  }

  @Watch('highlightIndex')
  onHighlightIndexChange(): void {
    const list = this.$refs.list as HTMLElement | undefined
    const el = list?.children[this.highlightIndex] as HTMLElement | undefined
    // jsdom 无 scrollIntoView，可选调用
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest' })
    }
  }

  isSelected(opt: FormSelectOption): boolean {
    return this.normalizedValue.includes(opt.value)
  }

  toggleDropdown(): void {
    if (this.disabled) return
    if (this.expanded) {
      this.closeDropdown()
    } else {
      this.openDropdown()
      this.initHighlight()
      this.focusFilterInput()
    }
  }

  private initHighlight(): void {
    const selected = this.filteredOptions.findIndex(opt => this.isSelected(opt))
    this.highlightIndex = selected >= 0 ? selected : 0
  }

  private focusFilterInput(): void {
    if (!this.filterable) return
    this.$nextTick(() => {
      const input = this.$refs.filterInput as HTMLInputElement | undefined
      input?.focus()
    })
  }

  private refocusTrigger(): void {
    const root = this.$refs.root as HTMLElement | undefined
    const trigger = root?.querySelector('.form-select__trigger') as HTMLElement | undefined
    trigger?.focus()
  }

  onTriggerKeydown(event: KeyboardEvent): void {
    if (this.disabled) return
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      if (!this.expanded) {
        this.openDropdown()
        this.initHighlight()
        this.focusFilterInput()
      }
    } else if (event.key === 'Escape' && this.expanded) {
      event.preventDefault()
      this.closeDropdown()
    }
  }

  onFilterKeydown(event: KeyboardEvent): void {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      this.moveHighlight(1)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      this.moveHighlight(-1)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      this.selectHighlighted()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      this.closeDropdown()
      this.query = ''
      this.refocusTrigger()
    } else if (event.key === 'Tab') {
      this.closeDropdown()
      this.query = ''
    }
  }

  private moveHighlight(delta: number): void {
    const count = this.filteredOptions.length
    if (count === 0) return
    this.highlightIndex = (this.highlightIndex + delta + count) % count
  }

  private selectHighlighted(): void {
    const opt = this.filteredOptions[this.highlightIndex]
    if (!opt) return
    this.handleOptionClick(opt)
    // 多选保留浮层继续选；单选关闭后焦点回到触发器
    if (!this.multiple) this.refocusTrigger()
  }

  handleOptionClick(opt: FormSelectOption): void {
    if (this.multiple) {
      const selected = this.isSelected(opt)
      const next = selected
        ? this.normalizedValue.filter(v => v !== opt.value)
        : [...this.normalizedValue, opt.value]
      this.$emit('input', next)
      this.$emit('change', opt, !selected)
    } else {
      this.$emit('input', opt.value)
      this.$emit('change', opt, true)
      this.query = ''
      this.closeDropdown()
    }
  }

  removeChip(value: string): void {
    if (this.disabled) return
    const next = this.normalizedValue.filter(v => v !== value)
    this.$emit('input', next)
    const removed = this.options.find(opt => opt.value === value)
    this.$emit('change', removed ?? null, false)
  }

  handleClear(): void {
    if (this.disabled) return
    this.$emit('input', this.multiple ? [] : '')
    this.$emit('clear')
    this.$emit('change', null, false)
    this.query = ''
    this.closeDropdown()
  }
}
</script>

<style lang="scss" scoped>
.form-select {
  position: relative;
  width: 100%;

  &.is-disabled {
    cursor: not-allowed;
  }
}

.form-select__trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-height: 38px;
  padding: 4px 10px;
  font-size: 14px;
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
  outline: none;
  cursor: pointer;
  box-sizing: border-box;

  &:hover {
    border-color: var(--color-text-quaternary);
  }

  &:focus-visible {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(var(--color-primary-rgb), 0.12);
  }

  .is-open & {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(var(--color-primary-rgb), 0.12);
  }

  .is-invalid & {
    border-color: var(--color-error);

    &:focus-visible,
    &.is-open {
      box-shadow: 0 0 0 3px rgba(var(--color-error-rgb), 0.1);
    }
  }

  .is-disabled & {
    background: var(--color-bg-disabled);
    cursor: not-allowed;
  }
}

.form-select__value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;

  &.is-placeholder {
    color: var(--color-text-quaternary);
  }
}

.form-select__placeholder {
  color: var(--color-text-quaternary);
}

// 多选 chips
.form-select__chips {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

.form-select__chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  max-width: 100%;
  padding: 2px 4px 2px 8px;
  background: rgba(var(--color-primary-rgb), 0.1);
  border-radius: var(--radius-full);
  font-size: 12px;
  color: var(--color-primary);
}

.form-select__chip-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}

.form-select__chip-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  background: transparent;
  color: var(--color-primary);
  cursor: pointer;
  border-radius: var(--radius-full);
  padding: 0;
  flex-shrink: 0;

  &:hover {
    background: rgba(var(--color-error-rgb), 0.15);
    color: var(--color-error);
  }
}

.form-select__clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: none;
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
  border-radius: var(--radius-full);
  padding: 0;
  flex-shrink: 0;

  &:hover {
    background: var(--color-bg-tertiary);
    color: var(--color-text-primary);
  }
}

.form-select__arrow {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
  transition: transform var(--transition-fast);

  &.is-open {
    transform: rotate(180deg);
  }
}

// ========================================
// 下拉浮层（teleport 到 body 后仍携带 scoped 属性，样式照常生效）
// ========================================
.form-select__dropdown {
  position: fixed;
  z-index: 2100;
  min-width: 160px;
  max-width: calc(100vw - 16px);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.form-select__filter {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-border-secondary);
}

.form-select__filter-icon {
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

.form-select__filter-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 13px;
  color: var(--color-text-primary);
  background: transparent;
  min-width: 0;

  &::placeholder {
    color: var(--color-text-quaternary);
  }
}

.form-select__list {
  list-style: none;
  margin: 0;
  padding: 4px;
  max-height: 264px;
  overflow-y: auto;
}

.form-select__option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--color-text-primary);
  cursor: pointer;
  min-height: 36px;
  box-sizing: border-box;

  &.is-highlighted {
    background: var(--color-bg-hover);
  }

  &.is-selected {
    color: var(--color-primary);
    font-weight: var(--font-weight-medium);
  }
}

.form-select__option-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.form-select__option-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-select__status-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;

  &.is-online {
    background: var(--color-success);
    box-shadow: 0 0 0 3px rgba(var(--color-primary-rgb), 0.15);
  }

  &.is-offline {
    background: var(--color-text-quaternary);
  }
}

.form-select__badge {
  flex-shrink: 0;
  padding: 1px 6px;
  font-size: 12px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);

  &.is-info {
    background: var(--color-info-lightest);
    color: var(--color-info-dark);
  }

  &.is-success {
    background: var(--color-success-lightest);
    color: var(--color-success-dark);
  }

  &.is-warning {
    background: var(--color-warning-lightest);
    color: var(--color-warning-dark);
  }
}

.form-select__check {
  flex-shrink: 0;
  color: var(--color-primary);
}

.form-select__empty {
  padding: 12px;
  text-align: center;
  font-size: 13px;
  color: var(--color-text-quaternary);
}
</style>
