<template>
  <div class="advanced-multi-select">
    <el-popover
      v-model="panelVisible"
      class="ams__popover"
      placement="bottom-start"
      trigger="click"
      :width="420"
      :visible-arrow="false"
      popper-class="ams__dropdown-popper"
      @show="handlePanelShow"
    >
      <div class="ams__panel">
    <!-- 顶部：搜索 / 创建二合一（玻璃拟态） -->
    <div class="ams__search">
      <div class="ams__search-box">
        <LucideIcon name="search" :size="16" class="ams__search-icon" />
        <el-input
          v-model="searchKeyword"
          class="ams__search-input"
          placeholder="搜索选项..."
          size="small"
          ref="searchInput"
          @input="handleSearch"
          @keyup.enter.native="handleCreateNewOption"
          @keydown.up.native="handleKeyboardNavigation"
          @keydown.down.native="handleKeyboardNavigation"
          @keydown.escape.native="handleEscapeKey"
        />
        <transition name="ams-fade">
          <button
            v-if="canCreateOption"
            type="button"
            class="ams__create-btn"
            @click="handleCreateNewOption"
          >
            <LucideIcon name="plus" :size="14" />
            <span>创建 "{{ searchKeyword.trim() }}"</span>
          </button>
        </transition>
      </div>
    </div>

    <!-- 已选区：前置展示，先看结果再选择 -->
    <transition name="ams-expand">
      <div v-if="selectedItems.length > 0 || true" class="ams__selected">
        <div class="ams__selected-bar">
          <!-- 含 / 排除 胶囊开关（简单筛选场景可由 showModeToggle 隐藏） -->
          <div v-if="showModeToggle" class="ams__mode-pill" :class="`is-${selectedMode}`">
            <button
              type="button"
              class="ams__mode-option"
              :class="{'is-active': selectedMode === 'include'}"
              @click="setSelectedMode('include')"
            >
              <LucideIcon name="check-check" :size="13" />
              <span>包含</span>
            </button>
            <button
              type="button"
              class="ams__mode-option"
              :class="{'is-active': selectedMode === 'exclude'}"
              @click="setSelectedMode('exclude')"
            >
              <LucideIcon name="square" :size="13" />
              <span>排除</span>
            </button>
          </div>

          <div class="ams__selected-meta">
            <span class="ams__selected-count" :class="`is-${selectedMode}`">
              {{ selectedItems.length }}
            </span>
            <span class="ams__selected-label">项已选</span>
          </div>

          <button
            v-if="selectedItems.length > 0"
            type="button"
            class="ams__clear-btn"
            @click="clearSelected"
          >
            <LucideIcon name="x" :size="14" />
            <span>清空</span>
          </button>
        </div>

        <transition-group name="ams-chip" tag="div" class="ams__chips">
          <span
            v-for="(item, index) in selectedItems"
            :key="getSelectedKey(item)"
            class="ams__chip"
            :class="`is-${selectedMode}`"
          >
            <LucideIcon
              v-if="getOptionIcon(item)"
              :name="getOptionIcon(item)"
              :size="12"
              class="ams__chip-icon"
            />
            <span class="ams__chip-label">{{ getSelectedLabel(item) }}</span>
            <button
              type="button"
              class="ams__chip-remove"
              @click="removeSelectedItem(index)"
              :title="`移除 ${getSelectedLabel(item)}`"
            >
              <LucideIcon name="x" :size="12" />
            </button>
          </span>
        </transition-group>

        <div v-if="selectedItems.length === 0" class="ams__empty-hint">
          从下方选项中选择，或直接搜索创建
        </div>
      </div>
    </transition>

    <!-- 选项列表 -->
    <div class="ams__options" ref="optionsList">
      <!-- 虚拟滚动容器 -->
      <virtual-scroll-list
        v-if="useVirtualScroll"
        ref="virtualScroll"
        :data="filteredOptions"
        :item-size="36"
        :height="listHeight"
        :key-field="optionValueKey"
        :label-field="optionLabelKey"
      >
        <template #item="{item, index}">
          <div
            class="ams__option"
            :class="{
              'is-selected': isSelected(item),
              'is-keyboard': isKeyboardHighlighted(index)
            }"
            @click="toggleOption(item)"
            @mouseenter="handleMouseEnter(index)"
          >
            <span class="ams__option-check" :class="{'is-checked': isSelected(item)}">
              <LucideIcon v-if="isSelected(item)" name="check-check" :size="13" />
            </span>
            <span class="ams__option-label">
              <LucideIcon
                v-if="getOptionIcon(item)"
                :name="getOptionIcon(item)"
                :size="13"
                class="ams__option-label-icon"
              />
              <span class="ams__option-label-text">{{ getOptionLabel(item) }}</span>
            </span>
            <span v-if="getOptionCount(item)" class="ams__option-count">
              {{ getOptionCount(item) }}
            </span>
            <span v-if="getOptionType(item)" class="ams__option-badge">
              {{ getOptionType(item) }}
            </span>
          </div>
        </template>
      </virtual-scroll-list>

      <!-- 普通滚动列表（保留 .normal-list 类，测试钉死） -->
      <div v-else class="normal-list ams__normal-list" ref="normalList">
        <div
          v-for="(item, index) in filteredOptions"
          :key="getOptionKey(item)"
          class="ams__option"
          :class="{
            'is-selected': isSelected(item),
            'is-keyboard': isKeyboardHighlighted(index)
          }"
          :style="{animationDelay: `${Math.min(index, 12) * 18}ms`}"
          @click="toggleOption(item)"
          @mouseenter="handleMouseEnter(index)"
        >
          <span class="ams__option-check" :class="{'is-checked': isSelected(item)}">
            <LucideIcon v-if="isSelected(item)" name="check-check" :size="13" />
          </span>
          <span class="ams__option-label">
            <LucideIcon
              v-if="getOptionIcon(item)"
              :name="getOptionIcon(item)"
              :size="13"
              class="ams__option-label-icon"
            />
            <span class="ams__option-label-text">{{ getOptionLabel(item) }}</span>
          </span>
          <span v-if="getOptionCount(item)" class="ams__option-count">
            {{ getOptionCount(item) }}
          </span>
          <span v-if="getOptionType(item)" class="ams__option-badge">
            {{ getOptionType(item) }}
          </span>
        </div>
        <div v-if="filteredOptions.length === 0" class="ams__no-match">
          <LucideIcon name="search" :size="22" />
          <span>无匹配选项</span>
        </div>
      </div>
    </div>

    <!-- 快捷操作（Lucide 图标按钮组） -->
    <div class="ams__actions">
      <el-tooltip content="选择当前可见项" placement="top" :open-delay="300">
        <button type="button" class="ams__action-btn" @click="selectAllVisible">
          <LucideIcon name="check-check" :size="15" />
        </button>
      </el-tooltip>
      <el-tooltip content="取消当前可见项" placement="top" :open-delay="300">
        <button type="button" class="ams__action-btn" @click="deselectAllVisible">
          <LucideIcon name="square" :size="15" />
        </button>
      </el-tooltip>
      <el-tooltip content="选择全部选项" placement="top" :open-delay="300">
        <button type="button" class="ams__action-btn" @click="selectAll">
          <LucideIcon name="list-checks" :size="15" />
        </button>
      </el-tooltip>
      <el-tooltip content="清空所有选择" placement="top" :open-delay="300">
        <button type="button" class="ams__action-btn is-danger" @click="deselectAll">
          <LucideIcon name="trash" :size="15" />
        </button>
      </el-tooltip>

      <!-- 批量粘贴：原"输入框"tab 收纳为 popover -->
      <el-popover
        placement="top"
        width="320"
        trigger="click"
        v-model="pastePopoverVisible"
        :append-to-body="false"
      >
        <div class="ams__paste">
          <div class="ams__paste-title">批量粘贴</div>
          <textarea
            v-model="inputText"
            class="ams__paste-area"
            :rows="3"
            :placeholder="inputPlaceholder"
            @input="handleInputChange"
          />
          <div v-if="parsedInput.length > 0" class="ams__paste-preview">
            <span class="ams__paste-count">解析 {{ parsedInput.length }} 项</span>
            <div class="ams__paste-tags">
              <span v-for="(t, i) in parsedInput" :key="i" class="ams__paste-tag">{{ t }}</span>
            </div>
          </div>
          <div class="ams__paste-actions">
            <el-button size="mini" @click="clearParsedInput">清空</el-button>
            <el-button size="mini" type="primary" @click="applyParsedInput">应用</el-button>
          </div>
        </div>
        <button slot="reference" type="button" class="ams__action-btn">
          <LucideIcon name="clipboard-paste" :size="15" />
        </button>
      </el-popover>

      <!-- 高级选项（保留 showAdvanced prop，避免父级 dangling attribute） -->
      <el-popover
        v-if="showAdvanced"
        placement="top"
        width="280"
        trigger="click"
        :append-to-body="false"
      >
        <div class="ams__advanced">
          <div class="ams__advanced-row">
            <label>启用虚拟滚动</label>
            <el-switch v-model="useVirtualScroll" @change="handleVirtualScrollChange" />
          </div>
          <div class="ams__advanced-row">
            <label>显示选项数量</label>
            <el-input-number
              v-model="maxVisibleItems"
              :min="10"
              :max="1000"
              size="mini"
              @change="handleMaxItemsChange"
            />
          </div>
          <div class="ams__advanced-row">
            <label>自定义分隔符</label>
            <el-input
              v-model="customSeparators"
              placeholder="如: |,~,##"
              size="mini"
              @input="handleSeparatorsChange"
            />
          </div>
        </div>
        <button slot="reference" type="button" class="ams__action-btn">
          <LucideIcon name="sliders-horizontal" :size="15" />
        </button>
      </el-popover>
    </div>
      </div>

      <button
        slot="reference"
        type="button"
        class="ams__trigger"
        :class="{'is-open': panelVisible, 'has-value': selectedItems.length > 0}"
        :aria-expanded="panelVisible ? 'true' : 'false'"
        aria-haspopup="listbox"
        aria-label="选择多个条件值"
        :title="triggerLabel"
      >
        <span
          class="ams__trigger-label"
          :class="{'is-placeholder': selectedItems.length === 0}"
        >
          {{ triggerLabel }}
        </span>
        <span v-if="selectedItems.length > 0" class="ams__trigger-count">
          {{ selectedItems.length }}
        </span>
        <LucideIcon name="sliders-horizontal" :size="14" class="ams__trigger-icon" />
        <span
          v-if="selectedItems.length > 0"
          role="button"
          tabindex="0"
          class="ams__trigger-clear"
          aria-label="清空已选条件值"
          title="清空"
          @click.stop.prevent="clearSelected"
          @keypress.enter.prevent="clearSelected"
          @keypress.space.prevent="clearSelected"
        >
          <LucideIcon name="x" :size="14" />
        </span>
      </button>
    </el-popover>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import VirtualScrollList from './VirtualScrollList.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'

// 选项接口
export interface SelectOption {
  value: string | number
  label: string
  icon?: string
  count?: number
  type?: string
  category?: string
  [key: string]: any
}

@Component({
  name: 'AdvancedMultiSelect',
  components: {
    VirtualScrollList,
    LucideIcon
  }
})
export default class AdvancedMultiSelect extends Vue {
  // Props —— 严格保持稳定，父级 ConditionValueInput 依赖 options/value/allowCreate/
  // virtualScrollThreshold/listHeight/showAdvanced，测试覆盖这些字段。
  @Prop({ default: () => [] }) options!: SelectOption[]
  @Prop({ default: () => [] }) value!: (string | number)[]
  @Prop({ default: 'selector' }) defaultMode!: 'selector' | 'input'
  @Prop({ default: 'include' }) defaultSelectedMode!: 'include' | 'exclude'
  @Prop({ default: false }) showAdvanced!: boolean
  @Prop({ default: true }) allowCreate!: boolean
  // 是否展示「包含/排除」模式切换胶囊。默认 true（高级搜索场景需要）；
  // 简单列表筛选（如种子页下载器/状态过滤）传 false 以隐藏无语义的排除开关。
  @Prop({ default: true }) showModeToggle!: boolean
  @Prop({ default: 10000 }) virtualScrollThreshold!: number
  @Prop({ default: 200 }) listHeight!: number
  @Prop({ default: '请选择' }) placeholder!: string

  // Data
  // 不在字段初始化阶段读取 props；vue-class-component 尚未完成 props 代理，
  // undefined 字段不会进入 Vue 2 响应式 data，模板因此会持续告警。
  selectedMode: 'include' | 'exclude' = 'include'
  selectedItems: SelectOption[] = []
  searchKeyword = ''
  inputText = ''
  parsedInput: string[] = []
  useVirtualScroll = false
  maxVisibleItems = 1000
  customSeparators = ''
  pastePopoverVisible = false
  panelVisible = false

  // 性能优化相关（测试钉死，必须保留字段名）
  searchDebounceTimer = 0
  filteredOptionsCache: SelectOption[] = []
  lastSearchKeyword = ''

  // 性能监控（保留字段，但删除运行时 console.warn 噪声）
  renderStartTime = 0

  // 键盘导航
  highlightedIndex = -1

  // 配置常量
  readonly optionValueKey = 'value'
  readonly optionLabelKey = 'label'
  readonly defaultSeparators = [',', ';', ' ', '\n', '\t']

  // Computed
  get filteredOptions(): SelectOption[] {
    // 没有搜索关键词：直接返回截断后的选项
    if (!this.searchKeyword) {
      const result = this.options.slice(0, this.maxVisibleItems)
      this.filteredOptionsCache = result
      this.lastSearchKeyword = ''
      return result
    }

    // 缓存命中：同关键词直接复用
    if (this.searchKeyword === this.lastSearchKeyword && this.filteredOptionsCache.length > 0) {
      return this.filteredOptionsCache
    }

    // 搜索过滤
    const keyword = this.searchKeyword.toLowerCase().trim()
    const result = this.options.filter(option => {
      const label = this.getOptionLabel(option).toLowerCase()
      const searchableMetadata = [option.value, option.type, option.category]
        .filter(value => value !== undefined && value !== null)
        .map(value => String(value).toLowerCase())
      return label.includes(keyword) || searchableMetadata.some(value => value.includes(keyword))
    }).slice(0, this.maxVisibleItems)

    this.filteredOptionsCache = result
    this.lastSearchKeyword = this.searchKeyword
    return result
  }

  get inputPlaceholder(): string {
    const separators = this.getAllSeparators().map(s => s === ' ' ? '空格' : s).join('、')
    return `使用${separators}分隔多个值`
  }

  get canCreateOption(): boolean {
    return this.allowCreate && !!this.searchKeyword.trim() && !this.optionExists(this.searchKeyword.trim())
  }

  get triggerLabel(): string {
    if (this.selectedItems.length === 0) {
      return this.placeholder
    }

    const firstLabel = this.getSelectedLabel(this.selectedItems[0])
    return this.selectedItems.length === 1
      ? firstLabel
      : `${firstLabel} 等 ${this.selectedItems.length} 项`
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
  created() {
    this.selectedMode = this.defaultSelectedMode
  }

  mounted() {
    this.updateSelectedItems(this.value)
    this.updateVirtualScrollStatus()
  }

  beforeDestroy() {
    // 清理防抖定时器，避免内存泄漏（测试钉死）
    if (this.searchDebounceTimer) {
      clearTimeout(this.searchDebounceTimer)
      this.searchDebounceTimer = 0
    }
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
    this.useVirtualScroll = this.options.length >= this.virtualScrollThreshold
  }

  handlePanelShow() {
    this.$nextTick(() => {
      const searchInput = this.$refs.searchInput as Vue & { focus?: () => void }
      if (searchInput && typeof searchInput.focus === 'function') {
        searchInput.focus()
      }
    })
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
    const validSeparators = separators.filter(sep => sep && sep.length > 0)

    if (validSeparators.length > 0) {
      const escapedSeparators = validSeparators.map(sep => {
        return sep.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      })
      const regexPattern = new RegExp(escapedSeparators.join('|'), 'g')
      result = text.split(regexPattern)
    }

    const uniqueItems = new Set(
      result
        .map(item => item.trim())
        .filter(item => item.length > 0)
    )

    return Array.from(uniqueItems)
  }

  // 含/排除切换（保留 selectedMode 数据语义）
  setSelectedMode(mode: 'include' | 'exclude') {
    this.selectedMode = mode
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

  getOptionIcon(option: SelectOption): string | undefined {
    return option.icon
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

  isKeyboardHighlighted(index: number): boolean {
    return this.highlightedIndex === index
  }

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

  // 搜索（保留防抖机制，但删除运行时 $forceUpdate 噪声）
  handleSearch() {
    if (this.searchDebounceTimer) {
      clearTimeout(this.searchDebounceTimer)
    }
    this.searchDebounceTimer = window.setTimeout(() => {
      // 清缓存强制重新计算 filteredOptions
      this.filteredOptionsCache = []
      this.lastSearchKeyword = ''
      this.highlightedIndex = -1
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

  // 键盘导航
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

  // ESC
  handleEscapeKey(event: KeyboardEvent) {
    this.highlightedIndex = -1
    this.searchKeyword = ''
    this.panelVisible = false
    event.preventDefault()
  }

  private scrollToHighlighted() {
    if (this.highlightedIndex < 0 || this.highlightedIndex >= this.filteredOptions.length) {
      return
    }

    if (this.useVirtualScroll && this.$refs.virtualScroll) {
      const virtualScroll = this.$refs.virtualScroll as any
      if (virtualScroll.scrollToIndex) {
        virtualScroll.scrollToIndex(this.highlightedIndex)
      }
    } else if (this.$refs.normalList) {
      const normalList = this.$refs.normalList as HTMLElement
      const optionItems = normalList.querySelectorAll('.ams__option')
      if (optionItems.length > this.highlightedIndex) {
        const targetElement = optionItems[this.highlightedIndex] as HTMLElement
        targetElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    }
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

  // 批量粘贴（原"输入框"模式逻辑保留，仅 UI 入口变为 popover）
  handleInputChange() {
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
        validOptions.push({ value: text, label: text, type: 'custom' })
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

  // 高级设置（保留为空实现，配置由 v-model 直接驱动）
  handleVirtualScrollChange() {
    // 由 useVirtualScroll 双向绑定直接生效
  }

  handleMaxItemsChange() {
    // 由 maxVisibleItems 双向绑定直接生效
  }

  handleSeparatorsChange() {
    // 由 customSeparators 双向绑定直接生效
  }

  // 值发射（载荷形态严格不变：input = values[]，change = {values, mode, count}）
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
// ============================================================
// AdvancedMultiSelect —— 高级搜索通用多选组件
// 视觉：玻璃拟态 + 渐变高亮 + 分层阴影 + 微交互，全程走设计 token。
// 注：旧版本硬编码 Element 蓝（#409eff/#ecf5ff），现改为 var(--color-*)
//     随主题（翡翠/橙/石墨）切换 —— intentional 行为变更。
// ============================================================

.advanced-multi-select {
  width: 100%;
  min-width: 0;
}

.ams__popover {
  display: block;
  width: 100%;

  ::v-deep .el-popover__reference-wrapper {
    display: block;
    width: 100%;
  }
}

// 默认态与 Element UI small 控件同高，完整选择能力收纳到浮层中。
.ams__trigger {
  display: flex;
  align-items: center;
  width: 100%;
  height: 32px;
  min-width: 0;
  padding: 0 10px;
  border: 1px solid var(--color-border-primary, #dcdfe6);
  border-radius: var(--radius-sm, 4px);
  background: var(--color-bg-primary, #fff);
  color: var(--color-text-primary, #1f2937);
  font-family: inherit;
  font-size: 12px;
  line-height: 1;
  box-sizing: border-box;
  cursor: pointer;
  transition: border-color var(--transition-fast, 150ms), box-shadow var(--transition-fast, 150ms);

  &:hover {
    border-color: var(--color-primary-light, #10b981);
  }

  &:focus-visible,
  &.is-open {
    outline: none;
    border-color: var(--color-primary, #059669);
    box-shadow: 0 0 0 2px var(--color-primary-lightest, #d1fae5);
  }
}

.ams__trigger-label {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.is-placeholder {
    color: var(--color-text-tertiary, #9ca3af);
  }
}

.ams__trigger-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  margin-left: 6px;
  padding: 0 5px;
  border-radius: var(--radius-full, 9999px);
  background: rgba(var(--color-primary-rgb, 5, 150, 105), 0.1);
  color: var(--color-primary, #059669);
  font-size: 10px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  box-sizing: border-box;
}

.ams__trigger-icon {
  flex-shrink: 0;
  margin-left: 7px;
  color: var(--color-text-tertiary, #9ca3af);
}

// trigger 内常驻清空按钮:仅在有选中项时渲染(v-if),无需点开浮层即可清空。
// 用 span+role="button" 而非 <button>,避免与 trigger(<button>)形成 button 嵌套(违反 HTML 规范)。
// @click.stop 阻断冒泡到外层 el-popover 的 trigger="click",防止清空时误开浮层。
.ams__trigger-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-left: 6px;
  padding: 0;
  border: none;
  border-radius: var(--radius-full, 9999px);
  background: transparent;
  color: var(--color-text-tertiary, #9ca3af);
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--transition-base, 200ms);

  &:hover,
  &:focus {
    color: var(--color-error, #ef4444);
    background: rgba(var(--color-error-rgb, 239, 68, 68), 0.08);
    outline: none;
  }
}

.ams__panel {
  border-radius: var(--radius-lg, 12px);
  background-color: var(--color-bg-primary, #fff);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

// ---- 顶部搜索框 ----
.ams__search {
  padding: 10px 10px 6px;

  .ams__search-box {
    position: relative;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    border-radius: var(--radius-md, 8px);
    background: var(--glass-bg, rgba(255, 255, 255, 0.85));
    border: 1px solid var(--color-border-primary, #e5e7eb);
    backdrop-filter: blur(var(--glass-blur, 12px));
    -webkit-backdrop-filter: blur(var(--glass-blur, 12px));
    transition: border-color var(--transition-base, 200ms), box-shadow var(--transition-base, 200ms);

    &:focus-within {
      border-color: var(--color-primary, #059669);
      box-shadow: 0 0 0 3px var(--color-primary-lightest, #d1fae5);
    }

    @supports not (backdrop-filter: blur(var(--glass-blur, 12px))) {
      background: var(--color-bg-secondary, #f9fafb);
    }
  }

  .ams__search-icon {
    color: var(--color-text-tertiary, #9ca3af);
    flex-shrink: 0;
  }

  .ams__search-input {
    flex: 1;

    // 融入外层玻璃框：去掉 el-input 自带边框/背景
    ::v-deep {
      .el-input__inner {
        height: 26px;
        line-height: 26px;
        border: none;
        background: transparent;
        padding: 0;
        font-size: 13px;
        color: var(--color-text-primary, #1f2937);
        font-family: inherit;

        &::placeholder {
          color: var(--color-text-tertiary, #9ca3af);
        }
      }
    }
  }

  .ams__create-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
    padding: 3px 8px;
    border: none;
    border-radius: var(--radius-full, 9999px);
    background: linear-gradient(135deg, var(--color-primary, #059669), var(--color-primary-light, #10b981));
    color: #fff;
    font-size: 11px;
    cursor: pointer;
    box-shadow: var(--shadow-sm, 0 1px 3px rgba(0, 0, 0, 0.1));
    transition: transform var(--transition-base, 200ms), box-shadow var(--transition-base, 200ms);

    &:hover {
      transform: translateY(-1px);
      box-shadow: var(--shadow-md, 0 4px 6px -1px rgba(0, 0, 0, 0.1));
    }
  }
}

// ---- 已选区（前置） ----
.ams__selected {
  padding: 0 10px 6px;
}

.ams__selected-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.ams__mode-pill {
  display: inline-flex;
  padding: 2px;
  border-radius: var(--radius-full, 9999px);
  background: var(--color-bg-tertiary, #f3f4f6);
  border: 1px solid var(--color-border-primary, #e5e7eb);
  transition: background var(--transition-base, 200ms);

  &.is-exclude {
    background: rgba(var(--color-error-rgb, 239, 68, 68), 0.08);
  }
}

.ams__mode-option {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  border: none;
  background: transparent;
  border-radius: var(--radius-full, 9999px);
  color: var(--color-text-secondary, #6b7280);
  font-size: 11px;
  cursor: pointer;
  transition: all var(--transition-base, 200ms);

  &:hover {
    color: var(--color-text-primary, #1f2937);
  }

  &.is-active {
    color: #fff;
    background: linear-gradient(135deg, var(--color-primary, #059669), var(--color-primary-light, #10b981));
    box-shadow: var(--shadow-sm, 0 1px 3px rgba(0, 0, 0, 0.1));
  }

  .ams__mode-pill.is-exclude &.is-active {
    background: linear-gradient(135deg, var(--color-error, #ef4444), var(--color-error-dark, #dc2626));
  }
}

.ams__selected-meta {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  margin-left: auto;

  .ams__selected-count {
    font-size: 14px;
    font-weight: 600;
    line-height: 1;
    background: linear-gradient(135deg, var(--color-primary, #059669), var(--color-primary-light, #10b981));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;

    &.is-exclude {
      background: linear-gradient(135deg, var(--color-error, #ef4444), var(--color-error-dark, #dc2626));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
  }

  .ams__selected-label {
    font-size: 11px;
    color: var(--color-text-tertiary, #9ca3af);
  }
}

.ams__clear-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  border: 1px solid var(--color-border-primary, #e5e7eb);
  background: var(--color-bg-primary, #fff);
  border-radius: var(--radius-md, 8px);
  color: var(--color-text-secondary, #6b7280);
  font-size: 11px;
  cursor: pointer;
  transition: all var(--transition-base, 200ms);

  &:hover {
    color: var(--color-error, #ef4444);
    border-color: var(--color-error, #ef4444);
    background: rgba(var(--color-error-rgb, 239, 68, 68), 0.05);
  }
}

.ams__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 4px;
}

.ams__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 3px 3px 8px;
  border-radius: var(--radius-full, 9999px);
  font-size: 11px;
  background: rgba(var(--color-primary-rgb, 5, 150, 105), 0.1);
  color: var(--color-primary, #059669);
  border: 1px solid rgba(var(--color-primary-rgb, 5, 150, 105), 0.2);
  transition: all var(--transition-base, 200ms);

  &:hover {
    background: rgba(var(--color-primary-rgb, 5, 150, 105), 0.16);
    transform: translateY(-1px);
  }

  &.is-exclude {
    background: rgba(var(--color-error-rgb, 239, 68, 68), 0.1);
    color: var(--color-error, #ef4444);
    border-color: rgba(var(--color-error-rgb, 239, 68, 68), 0.2);

    &:hover {
      background: rgba(var(--color-error-rgb, 239, 68, 68), 0.16);
    }
  }

  .ams__chip-remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    border: none;
    background: transparent;
    border-radius: var(--radius-full, 9999px);
    color: inherit;
    cursor: pointer;
    opacity: 0.6;
    transition: opacity var(--transition-base, 200ms), background var(--transition-base, 200ms);

    &:hover {
      opacity: 1;
      background: rgba(0, 0, 0, 0.08);
    }
  }
}

.ams__empty-hint {
  font-size: 11px;
  color: var(--color-text-tertiary, #9ca3af);
  padding: 2px 0;
}

// ---- 选项列表 ----
.ams__options {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  max-height: 190px;
  border-top: 1px solid var(--color-border-secondary, #f3f4f6);
  border-bottom: 1px solid var(--color-border-secondary, #f3f4f6);
  margin: 6px 0;
}

.ams__normal-list {
  max-height: 184px;
  overflow-y: auto;
  padding: 4px 0;
}

.ams__option {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 12px;
  cursor: pointer;
  position: relative;
  transition: background var(--transition-fast, 150ms), padding-left var(--transition-base, 200ms);
  animation: ams-fade-up 0.3s cubic-bezier(0.4, 0, 0.2, 1) both;

  &:hover {
    background: var(--color-bg-hover, #f3f4f6);
  }

  &.is-selected {
    background: linear-gradient(135deg, var(--color-primary-lightest, #d1fae5), var(--color-bg-primary, #fff));

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 3px;
      background: linear-gradient(180deg, var(--color-primary, #059669), var(--color-primary-light, #10b981));
    }

    padding-left: 19px;
  }

  &.is-keyboard {
    box-shadow: inset 0 0 0 2px var(--color-primary, #059669);
  }

  .ams__option-check {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    border: 1.5px solid var(--color-border-primary, #e5e7eb);
    border-radius: var(--radius-sm, 4px);
    flex-shrink: 0;
    color: #fff;
    transition: all var(--transition-base, 200ms);

    &.is-checked {
      background: linear-gradient(135deg, var(--color-primary, #059669), var(--color-primary-light, #10b981));
      border-color: var(--color-primary, #059669);
    }
  }

  .ams__option-label {
    flex: 1;
    font-size: 12px;
    color: var(--color-text-primary, #1f2937);
  }

  .ams__option-count {
    color: var(--color-text-tertiary, #9ca3af);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
  }

  .ams__option-badge {
    background: rgba(var(--color-primary-rgb, 5, 150, 105), 0.08);
    color: var(--color-primary, #059669);
    font-size: 10px;
    padding: 2px 6px;
    border-radius: var(--radius-sm, 4px);
    font-weight: 500;
  }
}

.ams__no-match {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 12px;
  color: var(--color-text-tertiary, #9ca3af);
  font-size: 12px;
}

// ---- 快捷操作 ----
.ams__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px 10px;
  flex-wrap: wrap;
}

.ams__action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--color-border-primary, #e5e7eb);
  background: var(--color-bg-primary, #fff);
  border-radius: var(--radius-md, 8px);
  color: var(--color-text-secondary, #6b7280);
  cursor: pointer;
  transition: all var(--transition-base, 200ms);

  &:hover {
    color: var(--color-primary, #059669);
    border-color: var(--color-primary, #059669);
    background: rgba(var(--color-primary-rgb, 5, 150, 105), 0.06);
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm, 0 1px 3px rgba(0, 0, 0, 0.1));
  }

  &.is-danger:hover {
    color: var(--color-error, #ef4444);
    border-color: var(--color-error, #ef4444);
    background: rgba(var(--color-error-rgb, 239, 68, 68), 0.06);
  }
}

// ---- popover 内：批量粘贴 ----
.ams__paste {
  .ams__paste-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--color-text-primary, #1f2937);
    margin-bottom: 8px;
  }

  .ams__paste-area {
    width: 100%;
    box-sizing: border-box;
    border: 1px solid var(--color-border-primary, #e5e7eb);
    border-radius: var(--radius-md, 8px);
    padding: 8px;
    font-size: 12px;
    font-family: inherit;
    resize: vertical;
    outline: none;
    color: var(--color-text-primary, #1f2937);

    &:focus {
      border-color: var(--color-primary, #059669);
    }
  }

  .ams__paste-preview {
    margin-top: 8px;
    padding: 8px;
    background: var(--color-bg-tertiary, #f3f4f6);
    border-radius: var(--radius-md, 8px);

    .ams__paste-count {
      font-size: 11px;
      color: var(--color-text-secondary, #6b7280);
      display: block;
      margin-bottom: 6px;
    }

    .ams__paste-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }

    .ams__paste-tag {
      font-size: 11px;
      padding: 2px 6px;
      background: rgba(var(--color-primary-rgb, 5, 150, 105), 0.1);
      color: var(--color-primary, #059669);
      border-radius: var(--radius-sm, 4px);
    }
  }

  .ams__paste-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 10px;
  }
}

// ---- popover 内：高级选项 ----
.ams__advanced {
  .ams__advanced-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;

    &:last-child {
      margin-bottom: 0;
    }

    label {
      font-size: 12px;
      color: var(--color-text-secondary, #6b7280);
    }

    .el-input-number,
    .el-input {
      width: 130px;
    }
  }
}

// ---- 动效 ----
@keyframes ams-fade-up {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.ams-fade-enter-active,
.ams-fade-leave-active {
  transition: opacity var(--transition-base, 200ms), transform var(--transition-base, 200ms);
}
.ams-fade-enter,
.ams-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.ams-expand-enter-active,
.ams-expand-leave-active {
  transition: opacity var(--transition-base, 200ms);
}

.ams-chip-enter-active {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); // 弹簧感
}
.ams-chip-leave-active {
  transition: all var(--transition-base, 200ms);
  position: absolute;
}
.ams-chip-enter {
  opacity: 0;
  transform: scale(0.6);
}
.ams-chip-leave-to {
  opacity: 0;
  transform: scale(0.6);
}
</style>

<style lang="scss">
// el-popover 会挂载到 body；使用唯一 popper class 控制浮层外壳，避免影响其他弹层。
.ams__dropdown-popper.el-popover {
  max-width: calc(100vw - 32px);
  padding: 0;
  border: 1px solid var(--color-border-primary, #e5e7eb);
  border-radius: var(--radius-lg, 12px);
  background: var(--color-bg-primary, #fff);
  box-shadow: var(--shadow-lg, 0 10px 15px -3px rgba(0, 0, 0, 0.1));
  box-sizing: border-box;

  // 下拉项内的图标 + 文本对齐（teleport 到 body，scoped 样式不生效，故放此非 scoped 块）
  .ams__option-label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .ams__option-label-icon {
    color: var(--color-text-tertiary, #9ca3af);
    flex-shrink: 0;
  }
}
</style>
