<template>
  <div class="condition-value-input">
    <span
      v-if="inputType === 'none'"
      class="condition-value-input__empty"
    >无需填写</span>

    <!-- 文本输入 -->
    <el-input
      v-else-if="inputType === 'text'"
      v-model="inputValue"
      :placeholder="placeholder"
      size="small"
      clearable
      @input="handleInput"
      @change="handleChange"
    />

    <!-- 数字输入 -->
    <el-input-number
      v-else-if="inputType === 'number'"
      v-model="inputValue"
      :placeholder="placeholder"
      size="small"
      :min="minValue"
      :max="maxValue"
      :step="step"
      :precision="precision"
      @input="handleInput"
      @change="handleChange"
    />

    <!-- 日期选择器 -->
    <el-date-picker
      v-else-if="inputType === 'date'"
      v-model="inputValue"
      :type="datePickerType"
      :placeholder="placeholder"
      size="small"
      format="yyyy-MM-dd HH:mm:ss"
      value-format="yyyy-MM-dd HH:mm:ss"
      @input="handleInput"
      @change="handleChange"
    />

    <!-- 最近N天输入 -->
    <div
      v-else-if="inputType === 'lastDays'"
      class="last-days-input"
    >
      <el-input-number
        v-model="inputValue.days"
        :min="1"
        :max="365"
        size="small"
        style="width: 100px;"
        @input="handleInput"
        @change="handleChange"
      />
      <span class="days-label">天内</span>
    </div>

    <!-- 日期范围选择器 -->
    <div
      v-else-if="inputType === 'dateRange'"
      class="date-range-input"
    >
      <el-date-picker
        v-model="inputValue.start"
        type="datetime"
        placeholder="开始时间"
        size="small"
        format="yyyy-MM-dd HH:mm:ss"
        value-format="yyyy-MM-dd HH:mm:ss"
        class="range-date-picker"
        @input="handleInput"
        @change="handleChange"
      />
      <span class="range-separator">至</span>
      <el-date-picker
        v-model="inputValue.end"
        type="datetime"
        placeholder="结束时间"
        size="small"
        format="yyyy-MM-dd HH:mm:ss"
        value-format="yyyy-MM-dd HH:mm:ss"
        class="range-date-picker"
        @input="handleInput"
        @change="handleChange"
      />
    </div>

    <!-- 数值范围输入（ratio/ratio_limit 的 between） -->
    <div
      v-else-if="inputType === 'numberRange'"
      class="number-range-input"
    >
      <span class="size-label">最小:</span>
      <el-input-number
        :value="inputValue && inputValue.min !== undefined ? inputValue.min : null"
        :min="0"
        :precision="2"
        :controls="true"
        :step="0.1"
        placeholder="最小值"
        size="small"
        class="size-number-input"
        @change="handleNumberRangeMinChange"
      />
      <span class="range-separator">至</span>
      <span class="size-label">最大:</span>
      <el-input-number
        :value="inputValue && inputValue.max !== undefined ? inputValue.max : null"
        :min="0"
        :precision="2"
        :controls="true"
        :step="0.1"
        placeholder="最大值"
        size="small"
        class="size-number-input"
        @change="handleNumberRangeMaxChange"
      />
    </div>

    <!-- 种子大小范围输入 -->
    <div
      v-else-if="inputType === 'sizeRange'"
      class="size-range-input"
    >
      <!-- 最小值 -->
      <div class="size-input-wrapper">
        <span class="size-label">最小:</span>
        <el-input-number
          :value="inputValue && inputValue.min !== undefined ? inputValue.min : null"
          :min="0"
          :precision="2"
          :controls="true"
          :step="1"
          placeholder="最小值"
          size="small"
          class="size-number-input"
          @input="handleMinValueChange"
          @change="handleMinValueChange"
        />
        <el-select
          :value="inputValue && inputValue.minUnit ? inputValue.minUnit : 'GB'"
          placeholder="单位"
          size="small"
          class="size-unit-select"
          @change="handleMinUnitChange"
        >
          <el-option label="B" value="B" />
          <el-option label="KB" value="KB" />
          <el-option label="MB" value="MB" />
          <el-option label="GB" value="GB" />
          <el-option label="TB" value="TB" />
        </el-select>
        <span class="size-hint">{{ formatSizeHint(inputValue && inputValue.min, inputValue && inputValue.minUnit) }}</span>
      </div>

      <span class="range-separator">至</span>

      <!-- 最大值 -->
      <div class="size-input-wrapper">
        <span class="size-label">最大:</span>
        <el-input-number
          :value="inputValue && inputValue.max !== undefined ? inputValue.max : null"
          :min="0"
          :precision="2"
          :controls="true"
          :step="1"
          placeholder="最大值"
          size="small"
          class="size-number-input"
          @input="handleMaxValueChange"
          @change="handleMaxValueChange"
        />
        <el-select
          :value="inputValue && inputValue.maxUnit ? inputValue.maxUnit : 'GB'"
          placeholder="单位"
          size="small"
          class="size-unit-select"
          @change="handleMaxUnitChange"
        >
          <el-option label="B" value="B" />
          <el-option label="KB" value="KB" />
          <el-option label="MB" value="MB" />
          <el-option label="GB" value="GB" />
          <el-option label="TB" value="TB" />
        </el-select>
        <span class="size-hint">{{ formatSizeHint(inputValue && inputValue.max, inputValue && inputValue.maxUnit) }}</span>
      </div>
    </div>

    <!-- 种子大小单个值输入（带单位） -->
    <div
      v-else-if="inputType === 'sizeWithUnit'"
      class="size-with-unit-input"
    >
      <el-input-number
        :value="inputValue && inputValue.value !== undefined ? inputValue.value : null"
        :min="0"
        :precision="2"
        :controls="true"
        :step="1"
        :placeholder="placeholder"
        size="small"
        class="size-number-input"
        @input="handleSizeValueChange"
        @change="handleSizeValueChange"
      />
      <el-select
        :value="inputValue && inputValue.unit ? inputValue.unit : 'GB'"
        placeholder="单位"
        size="small"
        class="size-unit-select"
        @change="handleSizeUnitChange"
      >
        <el-option label="B" value="B" />
        <el-option label="KB" value="KB" />
        <el-option label="MB" value="MB" />
        <el-option label="GB" value="GB" />
        <el-option label="TB" value="TB" />
      </el-select>
      <span class="size-hint">{{ formatSizeHint(inputValue && inputValue.value, inputValue && inputValue.unit) }}</span>
    </div>

    <!-- 下拉选择器 -->
    <el-select
      v-else-if="inputType === 'select'"
      v-model="inputValue"
      :placeholder="placeholder"
      size="small"
      clearable
      filterable
      @input="handleInput"
      @change="handleChange"
      style="width: 100%;"
    >
      <el-option
        v-for="option in currentFieldOptions"
        :key="option.value"
        :label="option.label"
        :value="option.value"
      >
        <LucideIcon
          v-if="option.icon"
          :name="option.icon"
          :size="13"
          style="margin-right: 6px; vertical-align: middle; color: var(--color-text-tertiary, #9ca3af);"
        />
        <span>{{ option.label }}</span>
      </el-option>
    </el-select>

    <!-- 多选输入器 -->
    <div
      v-else-if="inputType === 'multiSelect'"
      class="multi-select-input"
    >
      <AdvancedMultiSelect
        v-model="inputValue"
        :options="fieldOptions"
        :allow-create="!['status', 'downloader_name'].includes(field)"
        :virtual-scroll-threshold="100"
        :list-height="200"
        :show-advanced="true"
        @change="handleChange"
      />
    </div>

    <!-- 布尔选择器 -->
    <el-select
      v-else-if="inputType === 'boolean'"
      v-model="inputValue"
      :placeholder="placeholder"
      size="small"
      @input="handleInput"
      @change="handleChange"
      style="width: 120px;"
    >
      <el-option label="是" :value="true" />
      <el-option label="否" :value="false" />
    </el-select>

    <!-- 正则表达式输入 -->
    <div
      v-else-if="inputType === 'regex'"
      class="regex-input"
    >
      <el-input
        v-if="inputValue"
        v-model="inputValue.pattern"
        placeholder="正则表达式"
        size="small"
        clearable
        @input="handleInput"
        @change="handleChange"
      />
      <el-switch
        v-if="inputValue"
        v-model="inputValue.caseSensitive"
        size="small"
        active-text="区分大小写"
        inactive-text="不区分"
        style="margin-left: 8px;"
        @input="handleInput"
        @change="handleChange"
      />
    </div>

    <!-- 默认输入 -->
    <el-input
      v-else
      v-model="inputValue"
      :placeholder="placeholder"
      size="small"
      clearable
      @input="handleInput"
      @change="handleChange"
    />
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import AdvancedMultiSelect from './AdvancedMultiSelect.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'
import {
  AdvancedSearchConditionValue,
  AdvancedSearchValidationError,
  NumberRangeValue,
  SizeRangeValue,
  SizeValue
} from './advancedSearchState'

// 字段选项接口
interface FieldOption {
  label: string
  value: string
  icon?: string
}

@Component({
  name: 'ConditionValueInput',
  components: {
    AdvancedMultiSelect,
    LucideIcon
  }
})
export default class ConditionValueInput extends Vue {
  // Props
  @Prop({ required: true }) field!: string
  @Prop({ required: true }) operator!: string
  @Prop({ default: null }) value!: AdvancedSearchConditionValue

  // Data
  inputValue: AdvancedSearchConditionValue = null
  multiInputText = ''
  multiSelectMode: 'tags' | 'input' = 'tags'

  // 字段类型配置
  readonly fieldTypeMap = {
    name: 'text',
    size: 'number',
    status: 'multiSelect',
    downloader_name: 'multiSelect',
    save_path: 'text',
    added_date: 'date',
    completed_date: 'date',
    ratio: 'number',
    ratio_limit: 'number',
    tags: 'multiSelect',
    category: 'multiSelect',
    super_seeding: 'select',
    tracker_url: 'text',
    tracker_msg: 'text'
  }

  // 字段选项（将通过API或prop传入）
  @Prop({ default: () => [] }) fieldOptions!: FieldOption[]

  // 状态选项
  readonly statusOptions: FieldOption[] = [
    { label: '下载中', value: 'downloading' },
    { label: '已完成', value: 'completed' },
    { label: '暂停', value: 'paused' },
    { label: '错误', value: 'error' }
  ]

  readonly superSeedingOptions: FieldOption[] = [
    { label: '是', value: '1' },
    { label: '否', value: '0' },
    { label: '不支持', value: 'unsupported' }
  ]

  // Computed
  get inputType(): string {
    const fieldType = this.fieldTypeMap[this.field as keyof typeof this.fieldTypeMap] || 'text'

    if (this.operator === 'is_null' || this.operator === 'is_not_null') {
      return 'none'
    }

    // 根据操作符调整输入类型
    switch (this.operator) {
      case 'last_days':
        return 'lastDays'
      case 'date_range':
        return 'dateRange'
      case 'regex':
        return 'regex'
      case 'between':
        // 种子大小范围查询（带单位）
        if (this.field === 'size') {
          return 'sizeRange'
        }
        // 日期字段 between 复用 dateRange 模板（与 date_range 操作符同 UI）
        if (fieldType === 'date') {
          return 'dateRange'
        }
        // 数值字段（ratio/ratio_limit 等）between 走 numberRange 模板
        if (fieldType === 'number') {
          return 'numberRange'
        }
        return fieldType
      default:
        // 种子大小字段的所有其他操作符也使用单位选择
        if (this.field === 'size') {
          return 'sizeWithUnit'
        }
        return fieldType
    }
  }

  get placeholder(): string {
    switch (this.inputType) {
      case 'text':
        return '输入文本内容'
      case 'number':
        return '输入数字'
      case 'date':
        return '选择日期时间'
      case 'select':
        return '请选择'
      case 'multiSelect':
        return '选择或输入标签'
      case 'boolean':
        return '请选择'
      case 'lastDays':
        return '输入天数'
      case 'dateRange':
        return '选择日期范围'
      case 'sizeRange':
        return '选择大小范围'
      case 'sizeWithUnit':
        return '输入大小值'
      case 'regex':
        return '输入正则表达式'
      default:
        return '请输入值'
    }
  }

  get datePickerType(): string {
    if (this.operator === 'greater_than' || this.operator === 'less_than' ||
        this.operator === 'greater_equal' || this.operator === 'less_equal') {
      return 'datetime'
    }
    return 'datetime'
  }

  get minValue(): number | undefined {
    if (this.field === 'size') return 0
    return undefined
  }

  get maxValue(): number | undefined {
    return undefined
  }

  get step(): number {
    // 种子大小字段的步进值改为1
    if (this.field === 'size') return 1
    return 1
  }

  get precision(): number {
    // 种子大小和比率支持小数
    if (this.field === 'size' || this.field === 'ratio' || this.field === 'ratio_limit') return 2
    return 0
  }

  get currentFieldOptions(): FieldOption[] {
    // 使用传入的选项，如果没有则使用默认选项
    if (this.fieldOptions.length > 0) {
      return this.fieldOptions
    }

    // 根据字段类型返回默认选项
    switch (this.field) {
      case 'status':
        return this.statusOptions
      case 'super_seeding':
        return this.superSeedingOptions
      default:
        return []
    }
  }

  // Watchers
  @Watch('value', { immediate: true, deep: true })
  onValueChange(newValue: AdvancedSearchConditionValue) {
    if (Array.isArray(newValue)) {
      this.inputValue = [...newValue]
    } else if (typeof newValue === 'object' && newValue !== null) {
      this.inputValue = { ...newValue } as AdvancedSearchConditionValue
    } else {
      this.inputValue = newValue
    }
  }

  // Methods
  // 处理输入事件
  handleInput() {
    this.emitChange()
  }

  // 处理变更事件
  handleChange() {
    this.emitChange()
  }

  // 发出变更事件
  private emitChange() {
    this.$emit('input', this.inputValue)
    this.$emit('change', this.inputValue)
  }

  // 多选输入模式处理
  setMultiSelectMode(mode: 'tags' | 'input') {
    this.multiSelectMode = mode
    if (mode === 'input') {
      this.multiInputText = ''
    }
  }

  // 添加多选输入值
  addMultiInputValue() {
    const text = this.multiInputText.trim()
    if (
      text &&
      Array.isArray(this.inputValue) &&
      !this.inputValue.includes(text)
    ) {
      this.inputValue = [...this.inputValue, text]
      this.multiInputText = ''
      this.emitChange()
    }
  }

  // 删除多选输入值
  removeMultiInputValue(index: number) {
    if (!Array.isArray(this.inputValue)) return
    this.inputValue = this.inputValue.filter(
      (_item, itemIndex) => itemIndex !== index
    )
    this.emitChange()
  }

  private requireSizeRange(): SizeRangeValue {
    const value = this.inputValue
    if (
      typeof value !== 'object' ||
      value === null ||
      Array.isArray(value) ||
      !('minUnit' in value) ||
      !('maxUnit' in value)
    ) {
      throw new AdvancedSearchValidationError(
        '父组件未提供种子大小范围状态'
      )
    }
    return value as SizeRangeValue
  }

  private requireNumberRange(): NumberRangeValue {
    const value = this.inputValue
    if (
      typeof value !== 'object' ||
      value === null ||
      Array.isArray(value) ||
      !('min' in value) ||
      !('max' in value)
    ) {
      throw new AdvancedSearchValidationError('父组件未提供数值范围状态')
    }
    return value as NumberRangeValue
  }

  private requireSizeValue(): SizeValue {
    const value = this.inputValue
    if (
      typeof value !== 'object' ||
      value === null ||
      Array.isArray(value) ||
      !('value' in value) ||
      !('unit' in value)
    ) {
      throw new AdvancedSearchValidationError('父组件未提供种子大小状态')
    }
    return value as SizeValue
  }

  // 种子大小范围处理方法
  handleMinValueChange(value: number | null) {
    this.inputValue = { ...this.requireSizeRange(), min: value }
    this.emitChange()
  }

  handleMinUnitChange(unit: string) {
    this.inputValue = { ...this.requireSizeRange(), minUnit: unit }
    this.emitChange()
  }

  handleMaxValueChange(value: number | null) {
    this.inputValue = { ...this.requireSizeRange(), max: value }
    this.emitChange()
  }

  handleMaxUnitChange(unit: string) {
    this.inputValue = { ...this.requireSizeRange(), maxUnit: unit }
    this.emitChange()
  }

  // 数值范围（ratio/ratio_limit 的 between）：value 结构 {min, max}，无单位
  handleNumberRangeMinChange(value: number | null) {
    this.inputValue = { ...this.requireNumberRange(), min: value }
    this.emitChange()
  }

  handleNumberRangeMaxChange(value: number | null) {
    this.inputValue = { ...this.requireNumberRange(), max: value }
    this.emitChange()
  }

  // 格式化大小提示
  formatSizeHint(
    value: number | null | undefined,
    unit: string | undefined
  ): string {
    if (value === null || value === undefined || value === 0) {
      return ''
    }

    // 转换为字节并格式化显示
    const bytes = value * this.getUnitMultiplier(unit || 'B')
    return this.formatBytes(bytes)
  }

  // 获取单位倍数
  getUnitMultiplier(unit: string): number {
    const multipliers: Record<string, number> = {
      'B': 1,
      'KB': 1024,
      'MB': 1024 ** 2,
      'GB': 1024 ** 3,
      'TB': 1024 ** 4
    }
    return multipliers[unit] || 1
  }

  // 格式化字节数
  formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B'

    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let size = bytes
    let unitIndex = 0

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024
      unitIndex++
    }

    return `${size.toFixed(2)} ${units[unitIndex]}`
  }

  // 种子大小单个值处理方法
  handleSizeValueChange(value: number | null) {
    this.inputValue = { ...this.requireSizeValue(), value }
    this.emitChange()
  }

  handleSizeUnitChange(unit: string) {
    this.inputValue = { ...this.requireSizeValue(), unit }
    this.emitChange()
  }
}
</script>

<style lang="scss" scoped>
.condition-value-input {
  width: 100%;

  &__empty {
    display: inline-flex;
    align-items: center;
    min-height: 32px;
    color: #909399;
    font-size: 13px;
  }

  .last-days-input {
    display: flex;
    align-items: center;
    gap: 8px;

    .days-label {
      font-size: 12px;
      color: #606266;
    }
  }

  .date-range-input {
    display: flex;
    align-items: center;
    gap: 8px;

    /* 内联定宽类化（桌面 180px 不变）：窄屏断点可弹性铺满（移动端条件组适配） */
    .range-date-picker {
      width: 180px;
    }

    .range-separator {
      font-size: 12px;
      color: #606266;
    }
  }

  .size-range-input {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;

    .size-input-wrapper {
      display: flex;
      align-items: center;
      gap: 6px;
      flex: 1;
      min-width: 200px;
      padding: 6px;
      background-color: #f8fafc;
      border-radius: 4px;
      border: 1px solid #e2e8f0;

      .size-label {
        font-size: 12px;
        color: #475569;
        white-space: nowrap;
        font-weight: 500;
      }

      .size-number-input {
        width: 100px;
      }

      .size-unit-select {
        width: 80px;
      }

      .size-hint {
        font-size: 11px;
        color: #94a3b8;
        white-space: nowrap;
        font-family: 'Courier New', Monaco, monospace;
      }
    }

    .range-separator {
      font-size: 13px;
      color: #606266;
      font-weight: 500;
      white-space: nowrap;
    }
  }

  .size-with-unit-input {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px;
    background-color: #f8fafc;
    border-radius: 4px;
    border: 1px solid #e2e8f0;

    .size-number-input {
      width: 120px;
    }

    .size-unit-select {
      width: 80px;
    }

    .size-hint {
      font-size: 11px;
      color: #94a3b8;
      white-space: nowrap;
      font-family: 'Courier New', Monaco, monospace;
      margin-left: auto;
    }
  }

  .multi-select-input {
    .multi-input-mode {
      margin-bottom: 8px;

      .multi-input-tags {
        margin-top: 4px;
        display: flex;
        flex-wrap: wrap;
        gap: 4px;

        .el-tag {
          margin: 0;
        }
      }
    }

    .multi-select-toggle {
      display: flex;
      margin-top: 4px;

      .el-button {
        flex: 1;
      }
    }
  }

  .regex-input {
    display: flex;
    align-items: center;
    gap: 8px;

    .el-switch {
      white-space: nowrap;
    }
  }
}

// 响应式设计
@media (max-width: 768px) {
  .condition-value-input {
    .size-range-input {
      flex-direction: column;

      .size-input-wrapper {
        width: 100%;
        min-width: auto;
      }

      .range-separator {
        display: none;
      }
    }

    /* 日期范围 2×180px+分隔符超窄屏宽度：两个时间选择器弹性对分整行 */
    .date-range-input {
      .range-date-picker {
        width: auto;
        flex: 1;
        min-width: 0;
      }
    }
  }
}
</style>
