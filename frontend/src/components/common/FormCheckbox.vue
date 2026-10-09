<template>
  <label
    class="form-checkbox"
    :class="{'is-checked': value, 'is-disabled': disabled}"
  >
    <input
      class="form-checkbox__input"
      type="checkbox"
      :checked="value"
      :disabled="disabled"
      @change="handleChange"
    >
    <span class="form-checkbox__box" aria-hidden="true">
      <LucideIcon name="check" :size="14" :stroke-width="3" class="form-checkbox__mark" />
    </span>
    <span class="form-checkbox__label"><slot /></span>
  </label>
</template>

<script lang="ts">
import { Component, Vue, Prop, Model } from 'vue-property-decorator'

/**
 * FormCheckbox —— 全自定义复选框（零 Element UI）
 *
 * 原生 input 承载焦点/键盘/读屏语义（视觉隐藏），外观由令牌化样式绘制；
 * v-model 绑定 boolean。视觉态由 .is-checked 类驱动，避免依赖 :checked 伪类穿透。
 */
@Component({ name: 'FormCheckbox' })
export default class FormCheckbox extends Vue {
  @Model('input', { type: Boolean, default: false }) value!: boolean
  @Prop({ type: Boolean, default: false }) disabled!: boolean

  private handleChange(event: Event): void {
    if (this.disabled) return
    const checked = (event.target as HTMLInputElement).checked
    this.$emit('input', checked)
    this.$emit('change', checked)
  }
}
</script>

<style lang="scss" scoped>
.form-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;

  &.is-disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
}

// 视觉隐藏但保持可聚焦/可读屏
.form-checkbox__input {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;

  &:focus-visible + .form-checkbox__box {
    box-shadow: 0 0 0 3px rgba(var(--color-primary-rgb), 0.18);
    border-color: var(--color-primary);
  }
}

.form-checkbox__box {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1.5px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  background: var(--color-bg-primary);
  color: transparent;
  transition: all var(--transition-fast);
}

.is-checked .form-checkbox__box {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.is-disabled .form-checkbox__box {
  background: var(--color-bg-disabled);
}

.form-checkbox__label {
  font-size: 14px;
  color: var(--color-text-primary);
  line-height: 1.5;
}

.form-checkbox__mark {
  display: block;
}
</style>
