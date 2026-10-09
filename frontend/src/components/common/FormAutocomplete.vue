<template>
  <div
    ref="root"
    class="form-autocomplete"
    :class="{'is-invalid': invalid, 'is-mono': mono}"
  >
    <div class="form-autocomplete__box">
      <LucideIcon v-if="icon" :name="icon" :size="15" class="form-autocomplete__icon" />
      <input
        ref="input"
        :value="value"
        type="text"
        class="form-autocomplete__input"
        :placeholder="placeholder"
        :aria-label="placeholder"
        role="combobox"
        aria-autocomplete="list"
        :aria-expanded="String(expanded && hasSuggestions)"
        :aria-controls="dropdownId"
        autocomplete="off"
        @input="handleInput"
        @focus="handleFocus"
        @click="handleFocus"
        @keydown="handleKeydown"
      >
    </div>

    <!-- 建议浮层：默认仍在 DOM 子节点；展开时由 mixin teleport 到 body 并 fixed 定位 -->
    <div
      v-show="expanded && hasSuggestions"
      ref="options"
      :id="dropdownId"
      class="form-autocomplete__dropdown"
      :class="{'is-floating': isFloating}"
      role="listbox"
      :aria-label="placeholder"
    >
      <ul class="form-autocomplete__list">
        <li
          v-for="(item, index) in suggestions"
          :id="`${dropdownId}-opt-${index}`"
          :key="`${item.value}-${index}`"
          class="form-autocomplete__suggestion"
          :class="{'is-highlighted': index === highlightIndex}"
          role="option"
          :aria-selected="String(false)"
          @mouseenter="highlightIndex = index"
          @mousedown.prevent
          @click="handleSelect(item)"
        >
          <slot name="suggestion" :item="item" :index="index">
            <span class="form-autocomplete__suggestion-text">{{ item.value }}</span>
          </slot>
        </li>
      </ul>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Watch } from 'vue-property-decorator'
import { mixins } from 'vue-class-component'
import FloatingDropdown from './floatingDropdown'
import type { FormAutocompleteSuggestion } from './formControls'

/**
 * FormAutocomplete —— 全自定义自动补全输入（零 Element UI，替代 el-autocomplete）
 *
 * - 建议列表由宿主计算后经 suggestions 传入（过滤逻辑留在业务侧，组件保持纯展示）；
 * - 聚焦/输入展开浮层，↑↓ 高亮、Enter 选中、Esc/Tab 关闭；
 * - suggestion 具名作用域插槽渲染富建议行（徽章/计数等）；
 * - 浮层 teleport 到 body + 上下自适应定位（复用 FloatingDropdown mixin）。
 */
@Component({ name: 'FormAutocomplete' })
export default class FormAutocomplete extends mixins(FloatingDropdown) {
  @Prop({ default: '' }) value!: string
  /** 建议项：value 之外的字段经作用域插槽消费 */
  @Prop({ default: () => [] }) suggestions!: FormAutocompleteSuggestion[]
  @Prop({ type: String, default: '' }) placeholder!: string
  @Prop({ type: Boolean, default: false }) invalid!: boolean
  /** 等宽字体（路径/代码场景） */
  @Prop({ type: Boolean, default: false }) mono!: boolean
  /** 输入框左侧 Lucide 图标名，空串不渲染 */
  @Prop({ type: String, default: 'folder' }) icon!: string

  /** 当前高亮建议下标；-1 = 无高亮（对齐 el-autocomplete：首次 ↓ 才选中首项） */
  private highlightIndex = -1

  get dropdownId(): string {
    return `form-autocomplete-options-${this._uid}`
  }

  get hasSuggestions(): boolean {
    return this.suggestions.length > 0
  }

  @Watch('suggestions')
  onSuggestionsChange(): void {
    if (this.highlightIndex >= this.suggestions.length) this.highlightIndex = -1
    this.notifyDropdownContentChanged()
  }

  @Watch('highlightIndex')
  onHighlightIndexChange(): void {
    const optionsEl = this.$refs.options as HTMLElement | undefined
    const el = optionsEl?.querySelectorAll('.form-autocomplete__suggestion')[this.highlightIndex] as HTMLElement | undefined
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest' })
    }
  }

  handleInput(event: Event): void {
    const input = event.target as HTMLInputElement
    this.$emit('input', input.value)
    this.openDropdown()
  }

  handleFocus(): void {
    this.openDropdown()
  }

  handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'ArrowDown') {
      if (!this.expanded) {
        this.openDropdown()
        return
      }
      event.preventDefault()
      this.moveHighlight(1)
    } else if (event.key === 'ArrowUp') {
      if (!this.expanded) return
      event.preventDefault()
      this.moveHighlight(-1)
    } else if (event.key === 'Enter') {
      if (!this.expanded || !this.hasSuggestions) return
      event.preventDefault()
      const item = this.suggestions[this.highlightIndex]
      if (item) this.handleSelect(item)
    } else if (event.key === 'Escape') {
      if (!this.expanded) return
      event.preventDefault()
      this.closeDropdown()
    } else if (event.key === 'Tab') {
      this.closeDropdown()
    }
  }

  /** -1 为无高亮：↓ 进入首项、↑ 回到无高亮；其余循环 */
  private moveHighlight(delta: number): void {
    const count = this.suggestions.length
    if (count === 0) return
    if (this.highlightIndex === -1) {
      if (delta > 0) this.highlightIndex = 0
      return
    }
    if (this.highlightIndex === 0 && delta < 0) {
      this.highlightIndex = -1
      return
    }
    this.highlightIndex = (this.highlightIndex + delta + count) % count
  }

  handleSelect(item: FormAutocompleteSuggestion): void {
    this.$emit('input', item.value)
    this.$emit('select', item)
    this.closeDropdown()
    this.focusInput()
  }

  private focusInput(): void {
    const input = this.$refs.input as HTMLInputElement | undefined
    input?.focus()
  }
}
</script>

<style lang="scss" scoped>
.form-autocomplete {
  position: relative;
  width: 100%;
}

.form-autocomplete__box {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 0 12px;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
  box-sizing: border-box;

  &:focus-within {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(var(--color-primary-rgb), 0.12);
  }

  .is-invalid & {
    border-color: var(--color-error);

    &:focus-within {
      box-shadow: 0 0 0 3px rgba(var(--color-error-rgb), 0.1);
    }
  }
}

.form-autocomplete__icon {
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

.form-autocomplete__input {
  flex: 1;
  width: 100%;
  min-width: 0;
  padding: 9px 0;
  font-size: 14px;
  color: var(--color-text-primary);
  background: transparent;
  border: none;
  outline: none;
  font-family: inherit;

  &::placeholder {
    color: var(--color-text-quaternary);
  }
}

.is-mono .form-autocomplete__input {
  font-family: var(--font-mono);
  font-size: 13px;
}

// ========================================
// 建议浮层（teleport 到 body 后仍携带 scoped 属性，样式照常生效）
// ========================================
.form-autocomplete__dropdown {
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

.form-autocomplete__list {
  list-style: none;
  margin: 0;
  padding: 4px;
  max-height: 264px;
  overflow-y: auto;
}

.form-autocomplete__suggestion {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--color-text-primary);
  cursor: pointer;
  min-height: 36px;
  box-sizing: border-box;

  &.is-highlighted {
    background: var(--color-bg-hover);
  }
}

.form-autocomplete__suggestion-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
