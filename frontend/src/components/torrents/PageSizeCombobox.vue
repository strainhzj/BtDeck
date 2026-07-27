<template>
  <div
    class="page-size-combobox"
    role="combobox"
    aria-haspopup="listbox"
    :aria-controls="controlsId"
    :aria-expanded="String(expanded)"
  >
    <input
      ref="input"
      :value="value"
      class="page-size-input"
      type="text"
      inputmode="numeric"
      aria-label="每页数量"
      title="选择预设值或输入 1 至 100000，按 Enter 或失焦生效"
      @input="handleInput"
      @focus="$emit('focus')"
      @keyup.enter="handleApply"
      @blur="$emit('blur')"
    />
    <button
      type="button"
      class="page-size-toggle"
      :class="expanded ? 'el-icon-arrow-up' : 'el-icon-arrow-down'"
      :aria-label="expanded ? '收起分页大小选项' : '展开分页大小选项'"
      :aria-expanded="String(expanded)"
      @mousedown.prevent.stop
      @click.stop="$emit('toggle')"
    ></button>
    <ul
      v-show="expanded"
      :id="controlsId"
      class="page-size-options"
      role="listbox"
      aria-label="分页大小预设"
    >
      <li
        v-for="size in options"
        :key="size"
        role="none"
      >
        <button
          type="button"
          role="option"
          :aria-selected="String(size === pageSize)"
          @mousedown.prevent
          @click="handleSelect(size)"
        >{{ size }}</button>
      </li>
    </ul>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'

export interface PageSizeSuggestion {
  value: string
}

@Component({
  name: 'PageSizeCombobox'
})
export default class PageSizeCombobox extends Vue {
  @Prop({ required: true }) value!: string
  @Prop({ required: true }) pageSize!: number
  @Prop({ default: false }) expanded!: boolean
  @Prop({ default: () => [20, 50, 100, 500, 1000] }) options!: number[]
  @Prop({ default: 'torrent-page-size-options' }) controlsId!: string

  public focusInput(): void {
    const input = this.$refs.input as HTMLInputElement | undefined
    input?.focus()
  }

  private handleInput(event: Event): void {
    const input = event.target as HTMLInputElement | null
    this.$emit('input', input?.value ?? '')
  }

  private handleApply(): void {
    this.$emit('apply', this.value)
  }

  private handleSelect(size: number): void {
    const suggestion: PageSizeSuggestion = { value: String(size) }
    this.$emit('select', suggestion)
  }
}
</script>
