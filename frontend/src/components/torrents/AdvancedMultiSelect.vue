<template>
  <div class="advanced-multi-select">
    <!-- 模式切换标签页 -->
    <el-tabs v-model="activeMode" @tab-click="handleModeChange" size="small">
      <!-- 选择器模式 -->
      <el-tab-pane label="选择器" name="selector">
        <div class="selector-mode">
          <!-- 搜索过滤框 -->
          <div class="search-filter">
            <el-input
              v-model="searchKeyword"
              placeholder="搜索选项..."
              size="small"
              clearable
              ref="searchInput"
              @input="handleSearch"
              @keyup.enter.native="handleCreateNewOption"
              @keydown.up.native="handleKeyboardNavigation"
              @keydown.down.native="handleKeyboardNavigation"
              @keydown.escape.native="handleEscapeKey"
            >
              <template #append>
                <el-button
                  v-if="canCreateOption"
                  size="small"
                  type="primary"
                  icon="el-icon-plus"
                  @click="handleCreateNewOption"
                >
                  创建
                </el-button>
              </template>
            </el-input>
          </div>

          <!-- 选项列表 -->
          <div class="options-list" ref="optionsList">
            <!-- 虚拟滚动容器 -->
            <virtual-scroll-list
              v-if="useVirtualScroll"
              ref="virtualScroll"
              :data="filteredOptions"
              :item-size="32"
              :height="listHeight"
              :key-field="optionValueKey"
              :label-field="optionLabelKey"
            >
              <template #item="{item, index}">
                <div
                  class="option-item"
                  :class="{
                    'selected': isSelected(item),
                    'highlight': isHighlighted(index),
                    'keyboard-highlighted': isKeyboardHighlighted(index)
                  }"
                  @click="toggleOption(item)"
                  @mouseenter="handleMouseEnter(index)"
                >
                  <el-checkbox
                    :value="isSelected(item)"
                    @change="toggleOption(item)"
                    @click.stop
                  />
                  <span class="option-label">{{ getOptionLabel(item) }}</span>
                  <span v-if="getOptionCount(item)" class="option-count">
                    ({{ getOptionCount(item) }})
                  </span>
                  <span v-if="getOptionType(item)" class="option-type">
                    {{ getOptionType(item) }}
                  </span>
                </div>
              </template>
            </virtual-scroll-list>

            <!-- 普通滚动列表 -->
            <div v-else class="normal-list" ref="normalList">
              <div
                v-for="(item, index) in filteredOptions"
                :key="getOptionKey(item)"
                class="option-item"
                :class="{
                  'selected': isSelected(item),
                  'highlight': isHighlighted(index),
                  'keyboard-highlighted': isKeyboardHighlighted(index)
                }"
                @click="toggleOption(item)"
                @mouseenter="handleMouseEnter(index)"
              >
                <el-checkbox
                  :value="isSelected(item)"
                  @change="toggleOption(item)"
                  @click.stop
                />
                <span class="option-label">{{ getOptionLabel(item) }}</span>
                <span v-if="getOptionCount(item)" class="option-count">
                  ({{ getOptionCount(item) }})
                </span>
                <span v-if="getOptionType(item)" class="option-type">
                  {{ getOptionType(item) }}
                </span>
              </div>
            </div>
          </div>

          <!-- 快速操作按钮 -->
          <div class="quick-actions">
            <el-button size="mini" @click="selectAllVisible">选择可见</el-button>
            <el-button size="mini" @click="deselectAllVisible">取消可见</el-button>
            <el-button size="mini" @click="selectAll">选择全部</el-button>
            <el-button size="mini" @click="deselectAll">清空选择</el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- 输入框模式 -->
      <el-tab-pane label="输入框" name="input">
        <div class="input-mode">
          <!-- 输入框 -->
          <div class="input-container">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="3"
              :placeholder="inputPlaceholder"
              @input="handleInputChange"
              @keyup.ctrl.enter="parseInputText"
            />
            <div class="input-hint">
              <span>提示: 使用逗号、分号或空格分隔多个值</span>
              <el-button size="mini" @click="parseInputText">解析</el-button>
            </div>
          </div>

          <!-- 解析结果预览 -->
          <div v-if="parsedInput.length > 0" class="parsed-preview">
            <div class="preview-header">
              <span>解析结果 ({{ parsedInput.length }}项):</span>
              <el-button size="mini" @click="applyParsedInput">应用</el-button>
              <el-button size="mini" @click="clearParsedInput">清空</el-button>
            </div>
            <div class="parsed-items">
              <el-tag
                v-for="(item, index) in parsedInput"
                :key="index"
                closable
                size="mini"
                @close="removeParsedItem(index)"
              >
                {{ item }}
              </el-tag>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 包含/排除模式切换 -->
    <div class="mode-toggle">
      <el-radio-group v-model="selectedMode" size="small" @change="handleModeToggle">
        <el-radio-button label="include">包含模式</el-radio-button>
        <el-radio-button label="exclude">排除模式</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 已选项目显示 -->
    <div v-if="selectedItems.length > 0" class="selected-items">
      <div class="selected-header">
        <span class="selected-count">
          {{ selectedMode === 'include' ? '包含' : '排除' }} ({{ selectedItems.length }}项):
        </span>
        <el-button size="mini" @click="clearSelected">清空</el-button>
      </div>
      <div class="selected-tags">
        <el-tag
          v-for="(item, index) in selectedItems"
          :key="getSelectedKey(item)"
          :type="selectedMode === 'exclude' ? 'danger' : 'primary'"
          closable
          size="small"
          @close="removeSelectedItem(index)"
        >
          {{ getSelectedLabel(item) }}
        </el-tag>
      </div>
    </div>

    <!-- 高级设置 -->
    <div class="advanced-settings" v-if="showAdvanced">
      <el-collapse v-model="advancedActive" size="small">
        <el-collapse-item title="高级选项" name="advanced">
          <div class="setting-item">
            <label>启用虚拟滚动:</label>
            <el-switch v-model="useVirtualScroll" @change="handleVirtualScrollChange" />
          </div>
          <div class="setting-item">
            <label>显示选项数量:</label>
            <el-input-number
              v-model="maxVisibleItems"
              :min="10"
              :max="1000"
              size="small"
              @change="handleMaxItemsChange"
            />
          </div>
          <div class="setting-item">
            <label>自定义分隔符:</label>
            <el-input
              v-model="customSeparators"
              placeholder="例如: |,~,##"
              size="small"
              @input="handleSeparatorsChange"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import VirtualScrollList from './VirtualScrollList.vue'

// 选项接口
interface SelectOption {
  value: string | number
  label: string
  count?: number
  type?: string
  category?: string
  [key: string]: any
}


@Component({
  name: 'AdvancedMultiSelect',
  components: {
    VirtualScrollList
  }
})
export default class AdvancedMultiSelect extends Vue {
  // Props
  @Prop({ default: () => [] }) options!: SelectOption[]
  @Prop({ default: () => [] }) value!: (string | number)[]
  @Prop({ default: 'selector' }) defaultMode!: 'selector' | 'input'
  @Prop({ default: 'include' }) defaultSelectedMode!: 'include' | 'exclude'
  @Prop({ default: false }) showAdvanced!: boolean
  @Prop({ default: true }) allowCreate!: boolean
  @Prop({ default: 10000 }) virtualScrollThreshold!: number
  @Prop({ default: 200 }) listHeight!: number

  // Data
  activeMode: 'selector' | 'input' = this.defaultMode
  selectedMode: 'include' | 'exclude' = this.defaultSelectedMode
  selectedItems: SelectOption[] = []
  searchKeyword = ''
  inputText = ''
  parsedInput: string[] = []
  useVirtualScroll = false
  maxVisibleItems = 1000  // 增加默认显示数量以支持大数据量
  customSeparators = ''
  advancedActive: string[] = []

  // 性能优化相关
  searchDebounceTimer = 0
  filteredOptionsCache: SelectOption[] = []
  lastSearchKeyword = ''

  // 性能监控
  renderStartTime = 0

  // 键盘导航相关
  highlightedIndex = -1

  // 配置常量
  readonly optionValueKey = 'value'
  readonly optionLabelKey = 'label'
  readonly defaultSeparators = [',', ';', ' ', '\n', '\t']

  // Computed
  get filteredOptions(): SelectOption[] {
    this.renderStartTime = performance.now()

    // 如果没有搜索关键词，直接返回截断后的选项
    if (!this.searchKeyword) {
      const result = this.options.slice(0, this.maxVisibleItems)
      this.filteredOptionsCache = result
      this.lastSearchKeyword = ''

      const renderTime = performance.now() - this.renderStartTime
      if (renderTime > 16) { // 超过一帧时间则记录警告
        console.warn(`AdvancedMultiSelect: 渲染耗时 ${renderTime.toFixed(2)}ms，项目数量: ${result.length}`)
      }

      return result
    }

    // 如果搜索关键词与上次相同，直接使用缓存
    if (this.searchKeyword === this.lastSearchKeyword && this.filteredOptionsCache.length > 0) {
      return this.filteredOptionsCache
    }

    // 执行搜索过滤
    const keyword = this.searchKeyword.toLowerCase().trim()
    const result = this.options.filter(option => {
      const label = this.getOptionLabel(option).toLowerCase()
      return label.includes(keyword)
    }).slice(0, this.maxVisibleItems)

    // 更新缓存
    this.filteredOptionsCache = result
    this.lastSearchKeyword = this.searchKeyword

    // 性能监控
    const renderTime = performance.now() - this.renderStartTime
    if (renderTime > 16) {
      console.warn(`AdvancedMultiSelect: 搜索过滤耗时 ${renderTime.toFixed(2)}ms，搜索词: "${keyword}"，结果数量: ${result.length}`)
    }

    return result
  }

  get inputPlaceholder(): string {
    const separators = this.getAllSeparators().map(s => s === ' ' ? '空格' : s).join('、')
    return `请输入多个值，使用${separators}分隔`
  }

  get canCreateOption(): boolean {
    return this.allowCreate && this.searchKeyword.trim() && !this.optionExists(this.searchKeyword.trim())
  }

  // Watchers
  @Watch('value', { immediate: true, deep: true })
  onValueChange(newVal: (string | number)[]) {
    this.updateSelectedItems(newVal)
  }

  @Watch('options')
  onOptionsChange() {
    this.updateVirtualScrollStatus()
  }

  // Lifecycle
  mounted() {
    this.updateSelectedItems(this.value)
    this.updateVirtualScrollStatus()
  }

  beforeDestroy() {
    // 清理防抖定时器，避免内存泄漏
    if (this.searchDebounceTimer) {
      clearTimeout(this.searchDebounceTimer)
      this.searchDebounceTimer = 0
    }

    // 清理缓存数据
    this.filteredOptionsCache = []
    this.lastSearchKeyword = ''
  }

  // Methods
  private updateSelectedItems(values: (string | number)[]) {
    this.selectedItems = values
      .map(value => this.options.find(opt => this.getOptionValue(opt) === value))
      .filter(item => item) as SelectOption[]
  }

  private updateVirtualScrollStatus() {
    this.useVirtualScroll = this.options.length > this.virtualScrollThreshold
  }

  private getAllSeparators(): string[] {
    const custom = this.customSeparators ? this.customSeparators.split('').filter(s => s.trim()) : []
    return [...this.defaultSeparators, ...custom]
  }

  private parseInputBySeparators(text: string): string[] {
    if (!text || text.trim() === '') {
      return []
    }

    const separators = this.getAllSeparators()
    let result = [text]

    // 性能优化：避免对空分隔符进行split操作
    const validSeparators = separators.filter(sep => sep && sep.length > 0)

    // 使用正则表达式一次性分割，提高性能
    if (validSeparators.length > 0) {
      // 创建正则表达式模式，转义特殊字符
      const escapedSeparators = validSeparators.map(sep => {
        // 转义正则表达式特殊字符
        return sep.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      })
      const regexPattern = new RegExp(escapedSeparators.join('|'), 'g')

      // 一次性分割所有分隔符
      result = text.split(regexPattern)
    }

    // 使用Set进行去重，提高大数据量下的性能
    const uniqueItems = new Set(
      result
        .map(item => item.trim())
        .filter(item => item.length > 0)
    )

    return Array.from(uniqueItems)
  }

  // 模式切换
  handleModeChange() {
    this.$emit('mode-change', this.activeMode)
  }

  handleModeToggle() {
    this.$emit('selected-mode-change', this.selectedMode)
    this.emitValue()
  }

  // 选项操作
  getOptionKey(option: SelectOption): string {
    return String(this.getOptionValue(option))
  }

  getOptionValue(option: SelectOption): string | number {
    return option[this.optionValueKey] || option.value || ''
  }

  getOptionLabel(option: SelectOption): string {
    return option[this.optionLabelKey] || option.label || String(this.getOptionValue(option))
  }

  getOptionCount(option: SelectOption): number | undefined {
    return option.count
  }

  getOptionType(option: SelectOption): string | undefined {
    return option.type || option.category
  }

  isSelected(option: SelectOption): boolean {
    return this.selectedItems.some(item => this.getOptionValue(item) === this.getOptionValue(option))
  }

  isHighlighted(index: number): boolean {
    return index === 0 && this.searchKeyword.trim()
  }

  // 键盘高亮检查
  isKeyboardHighlighted(index: number): boolean {
    return this.highlightedIndex === index
  }

  // 鼠标进入处理
  handleMouseEnter(index: number) {
    this.highlightedIndex = index
  }

  toggleOption(option: SelectOption) {
    const index = this.selectedItems.findIndex(item =>
      this.getOptionValue(item) === this.getOptionValue(option)
    )

    if (index > -1) {
      this.selectedItems.splice(index, 1)
    } else {
      this.selectedItems.push(option)
    }

    this.emitValue()
  }

  optionExists(value: string): boolean {
    return this.options.some(option => this.getOptionLabel(option) === value || this.getOptionValue(option) === value)
  }

  // 搜索功能（带防抖优化）
  handleSearch() {
    // 清除之前的定时器
    if (this.searchDebounceTimer) {
      clearTimeout(this.searchDebounceTimer)
    }

    // 设置新的定时器，300ms防抖延迟
    this.searchDebounceTimer = window.setTimeout(() => {
      // 清除缓存，强制重新计算
      this.filteredOptionsCache = []
      this.lastSearchKeyword = ''

      // 触发重新渲染
      this.$forceUpdate()
    }, 300)
  }

  handleCreateNewOption() {
    if (!this.canCreateOption) return

    const newOption: SelectOption = {
      value: this.searchKeyword.trim(),
      label: this.searchKeyword.trim(),
      type: 'custom'
    }

    this.$emit('create-option', newOption)
    this.searchKeyword = ''
    this.highlightedIndex = -1
  }

  // 键盘导航功能
  handleKeyboardNavigation(event: KeyboardEvent) {
    const filteredOptions = this.filteredOptions
    if (filteredOptions.length === 0) return

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        this.highlightedIndex = Math.min(this.highlightedIndex + 1, filteredOptions.length - 1)
        this.scrollToHighlighted()
        break

      case 'ArrowUp':
        event.preventDefault()
        this.highlightedIndex = Math.max(this.highlightedIndex - 1, 0)
        this.scrollToHighlighted()
        break

      case 'Enter':
        event.preventDefault()
        if (this.highlightedIndex >= 0 && this.highlightedIndex < filteredOptions.length) {
          this.toggleOption(filteredOptions[this.highlightedIndex])
        } else if (this.canCreateOption) {
          this.handleCreateNewOption()
        }
        break
    }
  }

  // ESC键处理
  handleEscapeKey(event: KeyboardEvent) {
    this.highlightedIndex = -1
    this.searchKeyword = ''
    event.preventDefault()
  }

  // 滚动到高亮项
  private scrollToHighlighted() {
    if (this.highlightedIndex < 0 || this.highlightedIndex >= this.filteredOptions.length) {
      return
    }

    if (this.useVirtualScroll && this.$refs.virtualScroll) {
      // 虚拟滚动模式
      const virtualScroll = this.$refs.virtualScroll as any
      virtualScroll.scrollToIndex(this.highlightedIndex)
    } else if (this.$refs.normalList) {
      // 普通滚动模式
      const normalList = this.$refs.normalList as HTMLElement
      const optionItems = normalList.querySelectorAll('.option-item')
      if (optionItems.length > this.highlightedIndex) {
        const targetElement = optionItems[this.highlightedIndex] as HTMLElement
        targetElement.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest'
        })
      }
    }
  }

  // 重置高亮索引
  private resetHighlightedIndex() {
    this.highlightedIndex = -1
  }

  // 选择操作
  selectAllVisible() {
    this.filteredOptions.forEach(option => {
      if (!this.isSelected(option)) {
        this.selectedItems.push(option)
      }
    })
    this.emitValue()
  }

  deselectAllVisible() {
    this.filteredOptions.forEach(option => {
      const index = this.selectedItems.findIndex(item =>
        this.getOptionValue(item) === this.getOptionValue(option)
      )
      if (index > -1) {
        this.selectedItems.splice(index, 1)
      }
    })
    this.emitValue()
  }

  selectAll() {
    this.selectedItems = [...this.options]
    this.emitValue()
  }

  deselectAll() {
    this.selectedItems = []
    this.emitValue()
  }

  // 输入框模式
  handleInputChange() {
    // 实时预览解析结果
    if (this.inputText.trim()) {
      this.parsedInput = this.parseInputBySeparators(this.inputText)
    } else {
      this.parsedInput = []
    }
  }

  parseInputText() {
    if (!this.inputText.trim()) return

    const parsed = this.parseInputBySeparators(this.inputText)
    const validOptions: SelectOption[] = []

    parsed.forEach(text => {
      const existingOption = this.options.find(opt =>
        this.getOptionLabel(opt) === text || this.getOptionValue(opt) === text
      )

      if (existingOption) {
        if (!this.isSelected(existingOption)) {
          validOptions.push(existingOption)
        }
      } else if (this.allowCreate) {
        validOptions.push({
          value: text,
          label: text,
          type: 'custom'
        })
      }
    })

    this.selectedItems.push(...validOptions)
    this.emitValue()
    this.inputText = ''
    this.parsedInput = []
  }

  applyParsedInput() {
    this.parseInputText()
  }

  clearParsedInput() {
    this.parsedInput = []
    this.inputText = ''
  }

  removeParsedItem(index: number) {
    this.parsedInput.splice(index, 1)
  }

  // 已选项目管理
  getSelectedKey(item: SelectOption): string {
    return String(this.getOptionValue(item))
  }

  getSelectedLabel(item: SelectOption): string {
    return this.getOptionLabel(item)
  }

  removeSelectedItem(index: number) {
    this.selectedItems.splice(index, 1)
    this.emitValue()
  }

  clearSelected() {
    this.selectedItems = []
    this.emitValue()
  }

  // 高级设置
  handleVirtualScrollChange() {
    // 虚拟滚动状态变更
  }

  handleMaxItemsChange() {
    // 最大显示项数变更
  }

  handleSeparatorsChange() {
    // 自定义分隔符变更
  }

  // 值发射
  private emitValue() {
    const values = this.selectedItems.map(item => this.getOptionValue(item))
    this.$emit('input', values)
    this.$emit('change', {
      values,
      mode: this.selectedMode,
      count: values.length
    })
  }
}
</script>

<style lang="scss" scoped>
.advanced-multi-select {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background-color: #fff;

  .selector-mode {
    padding: 12px;

    .search-filter {
      margin-bottom: 12px;

      .el-input-group__append {
        padding: 0;
      }
    }

    .options-list {
      border: 1px solid #e4e7ed;
      border-radius: 4px;
      max-height: 200px;
      overflow-y: auto;

      .option-item {
        display: flex;
        align-items: center;
        padding: 8px 12px;
        cursor: pointer;
        border-bottom: 1px solid #f0f0f0;

        &:last-child {
          border-bottom: none;
        }

        &:hover {
          background-color: #f5f7fa;
        }

        &.selected {
          background-color: #ecf5ff;
        }

        &.highlight {
          background-color: #fff7e6;
        }

        &.keyboard-highlighted {
          background-color: #e6f3ff;
          border-color: #409eff;
        }

        .option-label {
          flex: 1;
          margin-left: 8px;
          font-size: 13px;
        }

        .option-count {
          color: #909399;
          font-size: 12px;
          margin-left: 8px;
        }

        .option-type {
          background-color: #f0f0f0;
          color: #666;
          font-size: 11px;
          padding: 2px 6px;
          border-radius: 3px;
          margin-left: 8px;
        }
      }

      .normal-list {
        max-height: 200px;
        overflow-y: auto;
      }
    }

    .quick-actions {
      margin-top: 12px;
      display: flex;
      gap: 8px;
      justify-content: center;

      .el-button {
        font-size: 12px;
      }
    }
  }

  .input-mode {
    padding: 12px;

    .input-container {
      margin-bottom: 12px;

      .input-hint {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 8px;
        font-size: 12px;
        color: #909399;
      }
    }

    .parsed-preview {
      border: 1px solid #e4e7ed;
      border-radius: 4px;
      padding: 8px;

      .preview-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
        font-size: 13px;
        font-weight: 500;
      }

      .parsed-items {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;

        .el-tag {
          margin: 0;
        }
      }
    }
  }

  .mode-toggle {
    padding: 12px;
    border-top: 1px solid #e4e7ed;
    text-align: center;
  }

  .selected-items {
    padding: 12px;
    border-top: 1px solid #e4e7ed;
    background-color: #fafafa;

    .selected-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;

      .selected-count {
        font-size: 13px;
        font-weight: 500;
        color: #303133;
      }
    }

    .selected-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;

      .el-tag {
        margin: 0;
      }
    }
  }

  .advanced-settings {
    padding: 12px;
    border-top: 1px solid #e4e7ed;

    .setting-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;

      label {
        font-size: 13px;
        color: #606266;
      }

      .el-input-number {
        width: 120px;
      }

      .el-input {
        width: 200px;
      }
    }
  }
}
</style>