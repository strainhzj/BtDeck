<template>
  <div class="size-range-filter">
    <!-- 最小值输入 -->
    <div class="size-input-group">
      <label class="size-label">最小值:</label>
      <el-input-number
        :value="sizeMinValue"
        :min="0"
        :precision="2"
        :controls="true"
        placeholder="输入数字"
        class="size-input"
        @change="handleSizeMinChange"
      />
      <el-select
        :value="sizeMinUnit"
        placeholder="单位"
        class="size-unit-select"
        @change="handleSizeMinUnitChange"
      >
        <el-option label="B" value="B" />
        <el-option label="KB" value="KB" />
        <el-option label="MB" value="MB" />
        <el-option label="GB" value="GB" />
        <el-option label="TB" value="TB" />
      </el-select>
      <span class="size-hint">
        {{ formatSizeHint(sizeMinValue, sizeMinUnit) }}
      </span>
    </div>

    <!-- 最大值输入 -->
    <div class="size-input-group">
      <label class="size-label">最大值:</label>
      <el-input-number
        :value="sizeMaxValue"
        :min="0"
        :precision="2"
        :controls="true"
        placeholder="输入数字"
        class="size-input"
        @change="handleSizeMaxChange"
      />
      <el-select
        :value="sizeMaxUnit"
        placeholder="单位"
        class="size-unit-select"
        @change="handleSizeMaxUnitChange"
      >
        <el-option label="B" value="B" />
        <el-option label="KB" value="KB" />
        <el-option label="MB" value="MB" />
        <el-option label="GB" value="GB" />
        <el-option label="TB" value="TB" />
      </el-select>
      <span class="size-hint">
        {{ formatSizeHint(sizeMaxValue, sizeMaxUnit) }}
      </span>
    </div>

    <!-- 快捷预设 -->
    <div class="size-presets">
      <span class="preset-label">快捷选择:</span>
      <el-button
        v-for="preset in sizePresets"
        :key="preset.label"
        size="small"
        @click="applyPreset(preset)"
      >
        {{ preset.label }}
      </el-button>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'

interface SizePreset {
  label: string
  min: number | null
  minUnit: string
  max: number | null
  maxUnit: string | null
}

interface SizeValue {
  size_min: string | null
  size_max: string | null
}

@Component({
  name: 'SizeRangeFilter'
})
export default class SizeRangeFilter extends Vue {
  // Props
  @Prop({ type: Object, default: () => ({ size_min: null, size_max: null }) })
  readonly value!: SizeValue

  // Data
  private sizeMinValue: number | null = null
  private sizeMinUnit = 'MB'
  private sizeMaxValue: number | null = null
  private sizeMaxUnit = 'GB'

  // 快捷预设
  private sizePresets: SizePreset[] = [
    { label: '小文件 (<100MB)', min: 0, minUnit: 'MB', max: 100, maxUnit: 'MB' },
    { label: '中文件 (100MB-1GB)', min: 100, minUnit: 'MB', max: 1, maxUnit: 'GB' },
    { label: '大文件 (1GB-10GB)', min: 1, minUnit: 'GB', max: 10, maxUnit: 'GB' },
    { label: '超大文件 (>10GB)', min: 10, minUnit: 'GB', max: null, maxUnit: null },
    { label: '高清电影 (4GB-20GB)', min: 4, minUnit: 'GB', max: 20, maxUnit: 'GB' }
  ]

  // Lifecycle
  mounted() {
    this.initFromValue()
  }

  // Watch value changes
  @Watch('value', { immediate: true, deep: true })
  private onValueChange(newVal: SizeValue) {
    if (newVal) {
      this.initFromValue()
    }
  }

  // Methods
  private initFromValue() {
    if (this.value?.size_min) {
      const parsed = this.parseSizeString(this.value.size_min)
      if (parsed) {
        this.sizeMinValue = parsed.value
        this.sizeMinUnit = parsed.unit
      }
    }

    if (this.value?.size_max) {
      const parsed = this.parseSizeString(this.value.size_max)
      if (parsed) {
        this.sizeMaxValue = parsed.value
        this.sizeMaxUnit = parsed.unit
      }
    }
  }

  private parseSizeString(sizeStr: string): { value: number, unit: string } | null {
    // 解析类似 "1.5 GB" 的字符串
    const match = sizeStr.match(/^(\d+(?:\.\d+)?)\s*([KMGT]?B?)$/i)
    if (match) {
      return {
        value: parseFloat(match[1]),
        unit: match[2].toUpperCase()
      }
    }
    return null
  }

  private handleSizeMinChange(value: number) {
    this.sizeMinValue = value
    this.emitChange()
  }

  private handleSizeMinUnitChange(unit: string) {
    this.sizeMinUnit = unit
    this.emitChange()
  }

  private handleSizeMaxChange(value: number) {
    this.sizeMaxValue = value
    this.emitChange()
  }

  private handleSizeMaxUnitChange(unit: string) {
    this.sizeMaxUnit = unit
    this.emitChange()
  }

  private emitChange() {
    const sizeMin = this.formatSizeString(this.sizeMinValue, this.sizeMinUnit)
    const sizeMax = this.formatSizeString(this.sizeMaxValue, this.sizeMaxUnit)

    const newValue: SizeValue = {
      ...this.value,
      size_min: sizeMin,
      size_max: sizeMax
    }

    this.$emit('input', newValue)
    this.$emit('change', { size_min: sizeMin, size_max: sizeMax })
  }

  private formatSizeString(value: number | null, unit: string): string | null {
    if (value === null || value === undefined) return null
    return `${value} ${unit}`
  }

  private formatSizeHint(value: number | null, unit: string): string {
    if (value === null || value === undefined) return ''

    // 转换为字节并格式化显示
    const bytes = value * this.getUnitMultiplier(unit)
    return this.formatBytes(bytes)
  }

  private getUnitMultiplier(unit: string): number {
    const multipliers: Record<string, number> = {
      'B': 1,
      'KB': 1024,
      'MB': 1024 ** 2,
      'GB': 1024 ** 3,
      'TB': 1024 ** 4
    }
    return multipliers[unit] || 1
  }

  private formatBytes(bytes: number): string {
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

  private applyPreset(preset: SizePreset) {
    if (preset.min !== null) {
      this.sizeMinValue = preset.min
      this.sizeMinUnit = preset.minUnit
    }

    if (preset.max !== null && preset.maxUnit !== null) {
      this.sizeMaxValue = preset.max
      this.sizeMaxUnit = preset.maxUnit
    } else {
      this.sizeMaxValue = null
    }

    this.emitChange()
    this.$message.success(`已应用: ${preset.label}`)
  }
}
</script>

<style lang="scss" scoped>
.size-range-filter {
  .size-input-group {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
    padding: 8px;
    background-color: #f8fafc;
    border-radius: 6px;
    border: 1px solid #e2e8f0;

    .size-label {
      min-width: 60px;
      font-size: 14px;
      font-weight: 500;
      color: #475569;
      margin-right: 12px;
    }

    .size-input {
      width: 150px;
      margin-right: 8px;

      ::v-deep .el-input__inner {
        border-radius: 4px;
      }
    }

    .size-unit-select {
      width: 100px;
      margin-right: 12px;

      ::v-deep .el-input__inner {
        border-radius: 4px;
      }
    }

    .size-hint {
      flex: 1;
      font-size: 12px;
      color: #94a3b8;
      font-family: 'Courier New', Monaco, monospace;
    }
  }

  .size-presets {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #e2e8f0;

    .preset-label {
      font-size: 14px;
      font-weight: 500;
      color: #475569;
      margin-right: 12px;
    }

    .el-button {
      margin-right: 8px;
      margin-bottom: 8px;
      border-radius: 4px;
      font-size: 13px;
      padding: 8px 15px;
      transition: all 0.3s ease;

      &:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
      }
    }
  }
}

// 响应式设计
@media (max-width: 768px) {
  .size-range-filter {
    .size-input-group {
      flex-direction: column;
      align-items: stretch;

      .size-label {
        margin-bottom: 8px;
      }

      .size-input,
      .size-unit-select {
        width: 100%;
        margin-right: 0;
        margin-bottom: 8px;
      }

      .size-hint {
        text-align: center;
      }
    }

    .size-presets {
      .el-button {
        width: calc(50% - 8px);
        margin-right: 8px;
      }
    }
  }
}
</style>
