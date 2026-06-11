<template>
  <div class="condition-value-input">
    <!-- 文本输入 -->
    <el-input
      v-if="inputType === 'text'"
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
        style="width: 180px;"
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
        style="width: 180px;"
        @input="handleInput"
        @change="handleChange"
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
        v-for="option in fieldOptions"
        :key="option.value"
        :label="option.label"
        :value="option.value"
      />
    </el-select>

    <!-- 多选输入器 -->
    <div
      v-else-if="inputType === 'multiSelect'"
      class="multi-select-input"
    >
      <AdvancedMultiSelect
        :options="fieldOptions"
        :value="inputValue"
        :allow-create="true"
        :virtual-scroll-threshold="100"
        :list-height="200"
        :show-advanced="true"
        @input="handleInput"
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

// 字段选项接口
interface FieldOption {
  label: string
  value: string
}

// 正则表达式值接口
interface RegexValue {
  pattern: string
  caseSensitive: boolean
}

// 日期范围值接口
interface DateRangeValue {
  start: string
  end: string
}

// 最近N天值接口
interface LastDaysValue {
  days: number
}

@Component({
  name: 'ConditionValueInput',
  components: {
    AdvancedMultiSelect
  }
})
export default class ConditionValueInput extends Vue {
  // Props
  @Prop({ required: true }) field!: string
  @Prop({ required: true }) operator!: string
  @Prop({ default: null }) value!: any

  // Data
  inputValue: any = null
  multiInputText = ''
  multiSelectMode: 'tags' | 'input' = 'tags'

  // 字段类型配置
  readonly fieldTypeMap = {
    name: 'text',
    size: 'number',
    status: 'select',
    downloader_name: 'select',
    save_path: 'text',
    added_date: 'date',
    completed_date: 'date',
    ratio: 'number',
    ratio_limit: 'number',
    tags: 'multiSelect',
    category: 'select',
    super_seeding: 'boolean',
    tracker_url: 'text'
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

  // 布尔选项
  readonly booleanOptions: FieldOption[] = [
    { label: '是', value: 'true' },
    { label: '否', value: 'false' }
  ]

  // Computed
  get inputType(): string {
    const fieldType = this.fieldTypeMap[this.field as keyof typeof this.fieldTypeMap] || 'text'

    // 根据操作符调整输入类型
    switch (this.operator) {
      case 'last_days':
        return 'lastDays'
      case 'date_range':
        return 'dateRange'
      case 'regex':
        return 'regex'
      case 'between':
        // 种子大小范围查询
        if (this.field === 'size') {
          return 'sizeRange'
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
        return this.booleanOptions
      default:
        return []
    }
  }

  // Watchers
  @Watch('value', { immediate: true, deep: true })
  onValueChange(newVal: any) {
    this.inputValue = this.normalizeValue(newVal)

    // 额外安全检查：确保种子大小字段总是有正确的数据结构
    if (this.field === 'size' && !this.isValidSizeValue()) {
      // 如果数据结构不正确，立即初始化为默认值
      if (this.operator === 'between') {
        this.inputValue = { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
      } else {
        this.inputValue = { value: null, unit: 'GB' }
      }
    }
  }

  @Watch('field')
  onFieldChange(newField: string, oldField: string) {
    // 字段变化时重置多选模式
    if (this.inputType === 'multiSelect') {
      this.multiSelectMode = 'tags'
    }

    // 当切换到种子大小字段时，立即初始化正确的数据结构
    if (newField === 'size' && oldField !== 'size') {
      if (this.operator === 'between') {
        this.inputValue = { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
      } else {
        this.inputValue = { value: null, unit: 'GB' }
      }
    }
  }

  @Watch('operator')
  onOperatorChange(newOp: string, oldOp: string) {
    // 当操作符在"介于"和其他操作符之间切换时，如果是种子大小字段，需要调整数据结构
    if (this.field === 'size') {
      if (newOp === 'between' && oldOp !== 'between') {
        // 切换到"介于"，需要范围数据结构
        const currentValue = this.inputValue?.value || null
        const currentUnit = this.inputValue?.unit || 'GB'
        this.inputValue = {
          min: currentValue,
          max: null,
          minUnit: currentUnit,
          maxUnit: currentUnit
        }
      } else if (newOp !== 'between' && oldOp === 'between') {
        // 从"介于"切换到其他操作符，需要单个值数据结构
        const minValue = this.inputValue?.min || null
        const minUnit = this.inputValue?.minUnit || 'GB'
        this.inputValue = {
          value: minValue,
          unit: minUnit
        }
      }
    }
  }

  @Watch('inputType')
  onInputTypeChange(newType: string) {
    // 当输入类型改变时，如果需要特殊的数据结构，初始化为默认值
    if (newType === 'sizeWithUnit' || newType === 'sizeRange') {
      if (!this.isValidSizeValue()) {
        if (newType === 'sizeRange') {
          this.inputValue = { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
        } else {
          this.inputValue = { value: null, unit: 'GB' }
        }
      }
    }
  }

  // Methods
  mounted() {
    this.initializeValue()
  }

  private initializeValue() {
    this.inputValue = this.normalizeValue(this.value)
  }

  // 检查是否是有效的种子大小值
  private isValidSizeValue(): boolean {
    if (!this.inputValue || typeof this.inputValue !== 'object') {
      return false
    }

    if (this.inputType === 'sizeWithUnit') {
      return 'value' in this.inputValue && 'unit' in this.inputValue
    }

    if (this.inputType === 'sizeRange') {
      return 'min' in this.inputValue && 'max' in this.inputValue
    }

    return false
  }

  // 标准化输入值
  private normalizeValue(value: any): any {
    // 先检查字段类型，对于种子大小字段特殊处理
    if (this.field === 'size') {
      // null 或 undefined 值
      if (value === null || value === undefined) {
        // 优先根据操作符判断数据结构
        if (this.operator === 'between') {
          return { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
        } else if (this.operator === '') {
          // 操作符还未设置时，默认使用单个值结构
          // 这可以避免初始化时的竞态条件
          return { value: null, unit: 'GB' }
        } else {
          return { value: null, unit: 'GB' }
        }
      }

      // 数字值：转换为种子大小对象结构
      if (typeof value === 'number') {
        if (this.operator === 'between') {
          return { min: value, max: null, minUnit: 'GB', maxUnit: 'GB' }
        } else {
          return { value: value, unit: 'GB' }
        }
      }

      // 已是正确对象结构
      if (typeof value === 'object') {
        if (this.operator === 'between') {
          if (value.min !== undefined) {
            return {
              min: value.min,
              max: value.max,
              minUnit: value.minUnit || 'GB',
              maxUnit: value.maxUnit || 'GB'
            }
          }
          return { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
        } else {
          if (value.value !== undefined) {
            return {
              value: value.value,
              unit: value.unit || 'GB'
            }
          }
          return { value: null, unit: 'GB' }
        }
      }

      // 其他情况返回默认值
      return this.getDefaultValue()
    }

    // 非种子大小字段的常规处理
    if (value === null || value === undefined) {
      return this.getDefaultValue()
    }

    switch (this.inputType) {
      case 'number':
        return Number(value) || 0

      case 'boolean':
        return Boolean(value)

      case 'multiSelect':
        if (Array.isArray(value)) {
          return value
        } else if (typeof value === 'string' && value) {
          return value.split(',').map(item => item.trim()).filter(item => item)
        }
        return []

      case 'lastDays':
        if (typeof value === 'number') {
          return { days: value }
        } else if (typeof value === 'object' && value?.days) {
          return { days: Number(value.days) }
        }
        return { days: 7 }

      case 'dateRange':
        if (typeof value === 'object' && value?.start && value?.end) {
          return { start: value.start, end: value.end }
        } else if (typeof value === 'string') {
          try {
            const parsed = JSON.parse(value)
            if (parsed.start && parsed.end) {
              return parsed
            }
          } catch (e) {
            // 解析失败，使用默认值
          }
        }
        return { start: '', end: '' }

      case 'regex':
        if (typeof value === 'object' && value?.pattern) {
          return { pattern: value.pattern, caseSensitive: Boolean(value.caseSensitive) }
        } else if (typeof value === 'string') {
          return { pattern: value, caseSensitive: false }
        }
        return { pattern: '', caseSensitive: false }

      case 'sizeRange':
        if (typeof value === 'object' && value?.min !== undefined) {
          return {
            min: value.min,
            max: value.max,
            minUnit: value.minUnit || 'GB',
            maxUnit: value.maxUnit || 'GB'
          }
        }
        return { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }

      case 'sizeWithUnit':
        if (typeof value === 'object' && value?.value !== undefined) {
          return {
            value: value.value,
            unit: value.unit || 'GB'
          }
        }
        return { value: null, unit: 'GB' }

      default:
        return value
    }
  }

  // 获取默认值
  private getDefaultValue(): any {
    switch (this.inputType) {
      case 'number':
        return 0

      case 'boolean':
        return null

      case 'multiSelect':
        return []

      case 'lastDays':
        return { days: 7 }

      case 'dateRange':
        return { start: '', end: '' }

      case 'regex':
        return { pattern: '', caseSensitive: false }

      case 'sizeRange':
        return { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }

      case 'sizeWithUnit':
        return { value: null, unit: 'GB' }

      default:
        return null
    }
  }

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
    if (text && !this.inputValue.includes(text)) {
      this.inputValue.push(text)
      this.multiInputText = ''
      this.emitChange()
    }
  }

  // 删除多选输入值
  removeMultiInputValue(index: number) {
    this.inputValue.splice(index, 1)
    this.emitChange()
  }

  // 种子大小范围处理方法
  handleMinValueChange(value: number) {
    if (!this.inputValue || typeof this.inputValue !== 'object') {
      this.inputValue = { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
    }
    this.inputValue.min = value
    this.emitChange()
  }

  handleMinUnitChange(unit: string) {
    if (!this.inputValue || typeof this.inputValue !== 'object') {
      this.inputValue = { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
    }
    this.inputValue.minUnit = unit
    this.emitChange()
  }

  handleMaxValueChange(value: number) {
    if (!this.inputValue || typeof this.inputValue !== 'object') {
      this.inputValue = { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
    }
    this.inputValue.max = value
    this.emitChange()
  }

  handleMaxUnitChange(unit: string) {
    if (!this.inputValue || typeof this.inputValue !== 'object') {
      this.inputValue = { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' }
    }
    this.inputValue.maxUnit = unit
    this.emitChange()
  }

  // 格式化大小提示
  formatSizeHint(value: number | null, unit: string): string {
    if (value === null || value === undefined || value === 0) {
      return ''
    }

    // 转换为字节并格式化显示
    const bytes = value * this.getUnitMultiplier(unit)
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
  handleSizeValueChange(value: number) {
    if (!this.inputValue || typeof this.inputValue !== 'object') {
      this.inputValue = { value: null, unit: 'GB' }
    }
    this.inputValue.value = value
    this.emitChange()
  }

  handleSizeUnitChange(unit: string) {
    if (!this.inputValue || typeof this.inputValue !== 'object') {
      this.inputValue = { value: null, unit: 'GB' }
    }
    this.inputValue.unit = unit
    this.emitChange()
  }
}
</script>

<style lang="scss" scoped>
.condition-value-input {
  width: 100%;

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
  }
}
</style>