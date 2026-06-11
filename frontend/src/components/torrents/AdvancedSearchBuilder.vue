<template>
  <div class="advanced-search-builder">
    <!-- 搜索条件组列表 -->
    <div class="condition-groups">
      <div
        v-for="(group, groupIndex) in conditionGroups"
        :key="group.id"
        class="condition-group"
      >
        <!-- 组头部 -->
        <div class="group-header">
          <div class="group-title">
            <el-input
              v-if="group.editing"
              v-model="group.name"
              size="mini"
              style="width: 120px; margin-right: 8px;"
              @blur="finishEditingGroup(group)"
              @keyup.enter.native="finishEditingGroup(group)"
              placeholder="组名称"
            />
            <span
              v-else
              @dblclick="startEditingGroup(group)"
              class="group-name"
              :title="group.name || `条件组 ${groupIndex + 1}`"
            >
              {{ group.name || `条件组 ${groupIndex + 1}` }}
            </span>
            <el-tag
              :type="getLogicTagType(group.logic)"
              size="mini"
              style="margin-left: 8px;"
            >
              {{ group.logic?.toUpperCase() || 'AND' }}
            </el-tag>
          </div>
          <div class="group-actions">
            <el-button
              size="mini"
              icon="el-icon-edit"
              @click="startEditingGroup(group)"
              title="重命名条件组"
            />
            <el-button
              size="mini"
              icon="el-icon-plus"
              @click="addCondition(group)"
            >
              添加条件
            </el-button>
            <el-dropdown v-if="conditionGroups.length > 1" trigger="click" @command="handleGroupCommand">
              <el-button size="mini" type="danger">
                更多<i class="el-icon-arrow-down el-icon--right"></i>
              </el-button>
              <el-dropdown-menu slot="dropdown">
                <el-dropdown-item :command="{action: 'delete', index: groupIndex}">
                  <i class="el-icon-delete"></i> 删除组
                </el-dropdown-item>
                <el-dropdown-item :command="{action: 'duplicate', index: groupIndex}">
                  <i class="el-icon-copy-document"></i> 复制组
                </el-dropdown-item>
                <el-dropdown-item :command="{action: 'clear', index: groupIndex}">
                  <i class="el-icon-refresh-left"></i> 清空条件
                </el-dropdown-item>
              </el-dropdown-menu>
            </el-dropdown>
          </div>
        </div>

        <!-- 组内逻辑设置 -->
        <div class="group-logic-settings">
          <el-select
            v-model="group.logic"
            size="mini"
            @change="onGroupLogicChange(group)"
            style="width: 100px;"
          >
            <el-option label="AND (并且)" value="and" />
            <el-option label="OR (或者)" value="or" />
          </el-select>
          <span class="logic-desc">{{ getGroupLogicDescription(group.logic) }}</span>
        </div>

        <!-- 条件列表 -->
        <div class="conditions">
          <div
            v-for="(condition, conditionIndex) in group.conditions"
            :key="condition.id"
            class="condition-item"
          >
            <!-- 条件间逻辑连接符 -->
            <div
              v-if="conditionIndex > 0"
              class="condition-logic"
            >
              <el-tag
                :type="getLogicTagType(group.logic)"
                size="mini"
                class="logic-tag"
              >
                {{ group.logic?.toUpperCase() }}
              </el-tag>
            </div>

            <!-- 条件内容 -->
            <div class="condition-content">
              <!-- 字段选择器 -->
              <div class="condition-field">
                <el-select
                  v-model="condition.field"
                  placeholder="选择字段"
                  size="small"
                  @change="onFieldChange(condition)"
                  style="width: 140px;"
                >
                  <el-option-group label="高级信息">
                    <el-option
                      v-for="field in advancedFields"
                      :key="field.key"
                      :label="field.label"
                      :value="field.key"
                    />
                  </el-option-group>
                  <el-option-group label="基本信息">
                    <el-option
                      v-for="field in basicFields"
                      :key="field.key"
                      :label="field.label"
                      :value="field.key"
                    />
                  </el-option-group>
                  <el-option-group label="状态信息">
                    <el-option
                      v-for="field in statusFields"
                      :key="field.key"
                      :label="field.label"
                      :value="field.key"
                    />
                  </el-option-group>
                  <el-option-group label="时间信息">
                    <el-option
                      v-for="field in timeFields"
                      :key="field.key"
                      :label="field.label"
                      :value="field.key"
                    />
                  </el-option-group>
                  <el-option-group label="比率信息">
                    <el-option
                      v-for="field in ratioFields"
                      :key="field.key"
                      :label="field.label"
                      :value="field.key"
                    />
                  </el-option-group>
                </el-select>
              </div>

              <!-- 操作符选择器 -->
              <div class="condition-operator">
                <el-select
                  v-model="condition.operator"
                  placeholder="选择操作"
                  size="small"
                  @change="onOperatorChange(condition)"
                  style="width: 120px;"
                  :disabled="!condition.field"
                >
                  <el-option-group
                    v-for="operatorGroup in getOperatorGroups(condition.field)"
                    :key="operatorGroup.type"
                    :label="operatorGroup.label"
                  >
                    <el-option
                      v-for="op in operatorGroup.operators"
                      :key="op.value"
                      :label="op.label"
                      :value="op.value"
                    />
                  </el-option-group>
                </el-select>
              </div>

              <!-- 条件值输入 -->
              <div class="condition-value">
                <ConditionValueInput
                  :field="condition.field"
                  :operator="condition.operator"
                  :value="condition.value"
                  :fieldOptions="getFieldOptions(condition.field)"
                  @input="val => onConditionValueChange(condition, val)"
                  @change="val => onConditionValueChange(condition, val)"
                  style="flex: 1;"
                />
              </div>

              <!-- 排除/包含切换 -->
              <div class="condition-mode">
                <el-radio-group
                  v-model="condition.mode"
                  size="small"
                  @change="onConditionModeChange(condition)"
                  :disabled="!fieldSupportsExclude(condition.field)"
                >
                  <el-radio-button label="include">包含</el-radio-button>
                  <el-radio-button
                    label="exclude"
                    :disabled="!fieldSupportsExclude(condition.field)"
                  >
                    排除
                  </el-radio-button>
                </el-radio-group>
              </div>

              <!-- 删除条件按钮 -->
              <div class="condition-actions">
                <el-button
                  size="mini"
                  type="danger"
                  icon="el-icon-delete"
                  circle
                  @click="removeCondition(group, conditionIndex)"
                  :disabled="group.conditions.length <= 1"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- 组间逻辑选择 -->
        <div
          v-if="groupIndex < conditionGroups.length - 1"
          class="group-between-logic"
        >
          <div class="logic-connector">
            <el-select
              v-model="group.betweenGroupLogic"
              size="small"
              @change="onBetweenGroupLogicChange(group)"
              style="width: 100px;"
            >
              <el-option label="AND" value="and" />
              <el-option label="OR" value="or" />
            </el-select>
            <span class="logic-description">{{ getBetweenGroupLogicDescription(group.betweenGroupLogic) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加条件组按钮 -->
    <div class="add-group">
      <el-button
        type="primary"
        icon="el-icon-plus"
        @click="addConditionGroup"
      >
        添加条件组
      </el-button>
    </div>

    <!-- 搜索操作按钮 -->
    <div class="search-actions">
      <el-button
        type="success"
        icon="el-icon-search"
        @click="onSearch"
        :loading="searching"
      >
        执行搜索
      </el-button>
      <el-button
        icon="el-icon-document"
        @click="saveSearchTemplate"
      >
        保存为模板
      </el-button>
      <el-button
        icon="el-icon-refresh-left"
        @click="resetConditions"
      >
        重置条件
      </el-button>
      <el-button
        icon="el-icon-view"
        @click="previewSearchQuery"
      >
        预览查询
      </el-button>
    </div>

    <!-- 搜索预览对话框 -->
    <el-dialog
      title="搜索条件预览"
      :visible.sync="previewVisible"
      width="600px"
      :modal-append-to-body="true"
      :append-to-body="true"
      :close-on-click-modal="false"
    >
      <pre class="query-preview">{{ formattedQuery }}</pre>
      <div slot="footer">
        <el-button @click="previewVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyQueryToClipboard">复制查询</el-button>
      </div>
    </el-dialog>

    <!-- 保存模板对话框 -->
    <el-dialog
      title="保存搜索模板"
      :visible.sync="saveTemplateVisible"
      width="400px"
      :modal-append-to-body="true"
      :append-to-body="true"
      :close-on-click-modal="false"
    >
      <el-form ref="templateForm" :model="templateForm" label-width="80px">
        <el-form-item label="模板名称" required>
          <el-input v-model="templateForm.name" placeholder="输入模板名称" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="templateForm.isDefault" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="templateForm.description"
            type="textarea"
            placeholder="可选：描述此模板的用途"
            :rows="3"
          />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="saveTemplateVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmSaveTemplate">保存</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch, Emit } from 'vue-property-decorator'
import ConditionValueInput from './ConditionValueInput.vue'
import { STATUS_OPTIONS } from '@/constants/status-config'

// 字段定义接口
interface SearchField {
  key: string
  label: string
  type: 'text' | 'number' | 'date' | 'select' | 'multiSelect' | 'boolean'
  options?: Array<{ label: string, value: string }>
  supportsExclude?: boolean
}

// 操作符定义接口
interface SearchOperator {
  value: string           // 前端使用的标识符
  label: string           // UI显示文本
  backendValue?: string   // 后端API格式（可选，默认与value相同）
  fallback?: string       // 降级操作符（当后端不支持时使用的前端value）
  supportedTypes?: string[] // 支持的字段类型（可选，兼容旧代码）
}

// 搜索条件接口
interface SearchCondition {
  id: string
  field: string
  operator: string
  value: any
  mode: 'include' | 'exclude'
}

// 条件组接口
interface ConditionGroup {
  id: string
  name?: string
  logic: 'and' | 'or'
  betweenGroupLogic?: 'and' | 'or'
  editing?: boolean
  conditions: SearchCondition[]
}

// 搜索模板表单接口
interface TemplateForm {
  name: string
  description: string
  isDefault: boolean
}

@Component({
  name: 'AdvancedSearchBuilder',
  components: {
    ConditionValueInput
  }
})
export default class AdvancedSearchBuilder extends Vue {
  // Props
  @Prop({ default: false }) searching!: boolean

  // Data
  conditionGroups: ConditionGroup[] = []
  previewVisible = false
  saveTemplateVisible = false
  templateForm: TemplateForm = {
    name: '',
    description: '',
    isDefault: false
  }

  // 基本信息字段
  readonly basicFields: SearchField[] = [
    { key: 'name', label: '种子名称', type: 'text', supportsExclude: true },
    { key: 'size', label: '种子大小', type: 'number', supportsExclude: true },
    { key: 'save_path', label: '保存路径', type: 'text', supportsExclude: true }
  ]

  // 状态信息字段
  readonly statusFields: SearchField[] = [
    {
      key: 'status',
      label: '状态',
      type: 'select',
      supportsExclude: true,
      options: STATUS_OPTIONS
    },
    {
      key: 'downloader_name',
      label: '下载器',
      type: 'select',
      supportsExclude: true,
      options: [] // 将通过API动态获取
    },
    {
      key: 'category',
      label: '分类',
      type: 'select',
      supportsExclude: true,
      options: [] // 将通过API动态获取
    },
    {
      key: 'super_seeding',
      label: '超级做种',
      type: 'boolean',
      supportsExclude: true
    }
  ]

  // 时间信息字段
  readonly timeFields: SearchField[] = [
    { key: 'added_date', label: '添加时间', type: 'date', supportsExclude: true },
    { key: 'completed_date', label: '完成时间', type: 'date', supportsExclude: true }
  ]

  // 高级信息字段
  readonly advancedFields: SearchField[] = [
    { key: 'tags', label: '标签', type: 'multiSelect', supportsExclude: true },
    { key: 'tracker_url', label: 'Tracker URL', type: 'text', supportsExclude: true },
    { key: 'tracker_msg', label: 'Tracker 信息', type: 'text', supportsExclude: true }
  ]

  // 比率信息字段
  readonly ratioFields: SearchField[] = [
    { key: 'ratio', label: '比率', type: 'number', supportsExclude: true },
    { key: 'ratio_limit', label: '比率限制', type: 'number', supportsExclude: true }
  ]

  // 操作符定义（统一配置：包含前端标识、后端格式、降级策略）
  readonly operatorGroups = {
    text: [
      { value: 'contains', label: '包含', backendValue: 'contains' },
      { value: 'not_contains', label: '不包含', backendValue: 'not_contains' },
      { value: 'equals', label: '等于', backendValue: 'eq' },
      { value: 'not_equals', label: '不等于', backendValue: 'ne' },
      { value: 'starts_with', label: '开头是', backendValue: 'starts_with' },
      { value: 'ends_with', label: '结尾是', backendValue: 'ends_with' },
      { value: 'regex', label: '正则匹配', backendValue: 'regex', fallback: 'contains' }
    ],
    number: [
      { value: 'equals', label: '等于', backendValue: 'eq' },
      { value: 'not_equals', label: '不等于', backendValue: 'ne' },
      { value: 'greater_than', label: '大于', backendValue: 'gt' },
      { value: 'less_than', label: '小于', backendValue: 'lt' },
      { value: 'greater_equal', label: '大于等于', backendValue: 'gte', fallback: 'greater_than' },
      { value: 'less_equal', label: '小于等于', backendValue: 'lte', fallback: 'less_than' },
      { value: 'between', label: '介于', backendValue: 'between', fallback: 'greater_than' }
    ],
    date: [
      { value: 'equals', label: '等于', backendValue: 'eq' },
      { value: 'not_equals', label: '不等于', backendValue: 'ne' },
      { value: 'greater_than', label: '晚于', backendValue: 'gt' },
      { value: 'less_than', label: '早于', backendValue: 'lt' },
      { value: 'greater_equal', label: '不早于', backendValue: 'gte', fallback: 'greater_than' },
      { value: 'less_equal', label: '不晚于', backendValue: 'lte', fallback: 'less_than' },
      { value: 'last_days', label: '最近N天', backendValue: 'last_days' },
      { value: 'date_range', label: '日期范围', backendValue: 'date_range' }
    ],
    select: [
      { value: 'equals', label: '等于', backendValue: 'eq' },
      { value: 'not_equals', label: '不等于', backendValue: 'ne' },
      { value: 'in', label: '在列表中', backendValue: 'in' },
      { value: 'not_in', label: '不在列表中', backendValue: 'not_in' }
    ],
    multiSelect: [
      { value: 'contains_any', label: '包含任意', backendValue: 'contains_any', fallback: 'contains' },
      { value: 'contains_all', label: '包含全部', backendValue: 'contains_all', fallback: 'contains' },
      { value: 'not_contains_any', label: '不包含任意', backendValue: 'not_contains_any', fallback: 'not_contains' },
      { value: 'not_contains_all', label: '不包含全部', backendValue: 'not_contains_all', fallback: 'not_contains' }
    ],
    boolean: [
      { value: 'equals', label: '等于', backendValue: 'eq' },
      { value: 'not_equals', label: '不等于', backendValue: 'ne' }
    ]
  }

  // 自动生成的前后端操作符映射（从operatorGroups自动生成）
  get operatorMapping(): Record<string, string> {
    const mapping: Record<string, string> = {}

    Object.values(this.operatorGroups).flat().forEach(op => {
      const backendValue = op.backendValue || op.value
      mapping[op.value] = backendValue
    })

    return mapping
  }

  // 自动生成的反向映射（从operatorGroups自动生成）
  get reverseOperatorMapping(): Record<string, string> {
    const mapping: Record<string, string> = {}

    Object.values(this.operatorGroups).flat().forEach(op => {
      const backendValue = op.backendValue || op.value
      mapping[backendValue] = op.value
    })

    return mapping
  }

  // 操作符降级策略配置
  private getOperatorFallback(frontendOp: string): string | null {
    const allOperators = Object.values(this.operatorGroups).flat()
    const operator = allOperators.find(op => op.value === frontendOp)
    return operator?.fallback || null
  }

  // Computed
  get formattedQuery(): string {
    return this.buildQueryText()
  }

  // Methods
  created() {
    // 开发环境验证操作符配置
    this.validateOperatorConfig()
    this.initializeConditions()
  }

  private initializeConditions() {
    if (this.conditionGroups.length === 0) {
      this.addConditionGroup()
    }
  }

  private generateId(): string {
    return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  }

  // 添加条件组
  addConditionGroup() {
    const newGroup: ConditionGroup = {
      id: this.generateId(),
      name: '',
      logic: 'and',
      betweenGroupLogic: 'and',
      editing: false,
      conditions: [this.createEmptyCondition()]
    }
    this.conditionGroups.push(newGroup)
  }

  // 删除条件组
  removeConditionGroup(groupIndex: number) {
    if (this.conditionGroups.length > 1) {
      this.conditionGroups.splice(groupIndex, 1)
    }
  }

  // 开始编辑组名称
  startEditingGroup(group: ConditionGroup) {
    // 先保存当前名称作为默认值
    if (!group.name) {
      group.name = `条件组 ${this.conditionGroups.indexOf(group) + 1}`
    }
    group.editing = true
  }

  // 完成编辑组名称
  finishEditingGroup(group: ConditionGroup) {
    if (!group.name || group.name.trim() === '') {
      // 如果名称为空，恢复默认名称
      group.name = ''
    } else {
      // 清理名称中的多余空格
      group.name = group.name.trim()
    }
    group.editing = false
  }

  // 处理组操作命令
  handleGroupCommand(command: {action: string, index: number}) {
    const { action, index } = command
    const group = this.conditionGroups[index]

    switch (action) {
      case 'delete':
        this.removeConditionGroup(index)
        break
      case 'duplicate':
        this.duplicateConditionGroup(group)
        break
      case 'clear':
        this.clearGroupConditions(group)
        break
    }
  }

  // 复制条件组
  duplicateConditionGroup(sourceGroup: ConditionGroup) {
    const newGroup: ConditionGroup = {
      id: this.generateId(),
      name: sourceGroup.name ? `${sourceGroup.name} (副本)` : '',
      logic: sourceGroup.logic,
      betweenGroupLogic: sourceGroup.betweenGroupLogic || 'and',
      editing: false,
      conditions: sourceGroup.conditions.map(condition => ({
        ...condition,
        id: this.generateId()
      }))
    }

    const sourceIndex = this.conditionGroups.indexOf(sourceGroup)
    this.conditionGroups.splice(sourceIndex + 1, 0, newGroup)
  }

  // 清空组内条件
  clearGroupConditions(group: ConditionGroup) {
    group.conditions = [this.createEmptyCondition()]
  }

  // 创建空条件
  private createEmptyCondition(): SearchCondition {
    return {
      id: this.generateId(),
      field: '',
      operator: '',
      value: null,
      mode: 'include'
    }
  }

  // 创建种子大小条件（预设为介于）
  createSizeCondition(): SearchCondition {
    return {
      id: this.generateId(),
      field: 'size',
      operator: 'between',
      value: { min: null, max: null, minUnit: 'GB', maxUnit: 'GB' },
      mode: 'include'
    }
  }

  // 添加条件
  addCondition(group: ConditionGroup) {
    group.conditions.push(this.createEmptyCondition())
  }

  // 删除条件
  removeCondition(group: ConditionGroup, conditionIndex: number) {
    if (group.conditions.length > 1) {
      group.conditions.splice(conditionIndex, 1)
    }
  }

  // 字段变更处理
  onFieldChange(condition: SearchCondition) {
    // 清空操作符和值
    condition.operator = ''
    condition.value = null
  }

  // 操作符变更处理
  onOperatorChange(condition: SearchCondition) {
    // 特殊处理：种子大小字段不应该被简单重置为null
    // 因为种子大小需要特定的对象结构 { value: number, unit: string } 或 { min: number, max: number, minUnit: string, maxUnit: string }
    if (condition.field === 'size') {
      // 不做任何处理，让ConditionValueInput组件自己处理值结构
      return
    }

    // 根据操作符设置默认值（非种子大小字段）
    if (this.needsValueReset(condition.operator)) {
      condition.value = null
    }
  }

  // 条件值变更处理
  onConditionValueChange(condition: SearchCondition, value: any) {
    condition.value = value
  }

  // 条件模式变更处理
  onConditionModeChange(condition: SearchCondition) {
    // 模式变更时的特殊处理
  }

  // 组逻辑变更处理
  onGroupLogicChange(group: ConditionGroup) {
    // 逻辑变更时的处理
  }

  // 获取字段信息
  private getFieldInfo(fieldKey: string): SearchField | undefined {
    const allFields = [
      ...this.advancedFields,
      ...this.basicFields,
      ...this.statusFields,
      ...this.timeFields,
      ...this.ratioFields
    ]
    return allFields.find(field => field.key === fieldKey)
  }

  // 获取字段选项
  getFieldOptions(fieldKey: string): Array<{label: string, value: string}> {
    const field = this.getFieldInfo(fieldKey)

    // 如果字段本身有选项定义,直接返回
    if (field?.options && field.options.length > 0) {
      return field.options
    }

    // 根据字段类型返回默认选项
    switch (fieldKey) {
      case 'super_seeding':
        return [
          { label: '是', value: 'true' },
          { label: '否', value: 'false' }
        ]

      default:
        return []
    }
  }

  // 获取操作符组
  getOperatorGroups(fieldKey: string) {
    const field = this.getFieldInfo(fieldKey)
    if (!field) return []

    const groups = []
    const fieldType = field.type

    // 基本操作符
    if (this.operatorGroups[fieldType]) {
      groups.push({
        type: 'basic',
        label: '基本操作',
        operators: this.operatorGroups[fieldType as keyof typeof this.operatorGroups]
      })
    }

    // 排除操作符（如果支持）
    if (field.supportsExclude && fieldType === 'text') {
      groups.push({
        type: 'exclude',
        label: '排除操作',
        operators: [
          { value: 'not_equals', label: '不等于' },
          { value: 'not_contains', label: '不包含' },
          { value: 'not_in', label: '不在列表中' }
        ]
      })
    }

    return groups
  }

  // 字段是否支持排除模式
  fieldSupportsExclude(fieldKey: string): boolean {
    const field = this.getFieldInfo(fieldKey)
    return field?.supportsExclude || false
  }

  // 是否需要重置值
  private needsValueReset(operator: string): boolean {
    const resetOperators = ['equals', 'not_equals', 'in', 'not_in']
    return resetOperators.includes(operator)
  }

  // 获取逻辑标签类型
  getLogicTagType(logic: string): string {
    return logic === 'and' ? 'primary' : 'success'
  }

  // 获取组逻辑描述
  getGroupLogicDescription(logic: string): string {
    return logic === 'and' ? '所有条件都必须满足' : '任意一个条件满足即可'
  }

  // 获取组间逻辑描述
  getBetweenGroupLogicDescription(logic: string): string {
    return logic === 'and' ? '并且与下一个条件组' : '或者与下一个条件组'
  }

  // 组逻辑变更处理
  onGroupLogicChange(group: ConditionGroup) {
    // 组内逻辑变更时的处理
    this.$emit('group-logic-change', {
      groupId: group.id,
      logic: group.logic
    })
  }

  // 组间逻辑变更处理
  onBetweenGroupLogicChange(group: ConditionGroup) {
    // 组间逻辑变更时的处理
    this.$emit('between-group-logic-change', {
      groupId: group.id,
      betweenGroupLogic: group.betweenGroupLogic
    })
  }

  // 构建查询文本
  private buildQueryText(): string {
    if (this.conditionGroups.length === 0) {
      return '暂无搜索条件'
    }

    const groupQueries = this.conditionGroups.map((group, groupIndex) => {
      const conditionQueries = group.conditions.map(condition => {
        const field = this.getFieldInfo(condition.field)
        if (!field) return ''

        const fieldLabel = field.label
        const operatorLabel = this.getOperatorLabel(condition.operator)
        const valueLabel = this.getValueLabel(condition)
        const modeLabel = condition.mode === 'exclude' ? '排除' : '包含'

        return `${modeLabel}: ${fieldLabel} ${operatorLabel} ${valueLabel}`
      }).filter(query => query)

      if (conditionQueries.length === 0) return ''

      const groupName = group.name || `条件组${groupIndex + 1}`
      const groupLogic = group.logic.toUpperCase()
      const conditionsStr = conditionQueries.join(` ${groupLogic} `)

      return `【${groupName}】(${conditionsStr})`
    }).filter(query => query)

    // 添加组间逻辑连接
    if (groupQueries.length === 0) return '暂无有效搜索条件'

    if (groupQueries.length === 1) {
      return groupQueries[0]
    }

    let result = groupQueries[0]
    for (let i = 1; i < this.conditionGroups.length; i++) {
      const group = this.conditionGroups[i - 1]
      const betweenLogic = (group.betweenGroupLogic || 'and').toUpperCase()
      result += ` ${betweenLogic} ${groupQueries[i]}`
    }

    return result
  }

  // 获取操作符标签
  private getOperatorLabel(operator: string): string {
    const allOperators = Object.values(this.operatorGroups).flat()
    const op = allOperators.find(o => o.value === operator)
    return op ? op.label : operator
  }

  // 获取值标签
  private getValueLabel(condition: SearchCondition): string {
    if (condition.value === null || condition.value === undefined) {
      return '未设置'
    }

    // 特殊处理种子大小范围
    if (condition.field === 'size' && condition.operator === 'between' && typeof condition.value === 'object') {
      const value = condition.value
      const min = value.min !== null ? `${value.min} ${value.minUnit || 'GB'}` : '无限制'
      const max = value.max !== null ? `${value.max} ${value.maxUnit || 'GB'}` : '无限制'
      return `${min} ~ ${max}`
    }

    // 特殊处理种子大小单个值（带单位）
    if (condition.field === 'size' && condition.operator !== 'between' && typeof condition.value === 'object' && condition.value.value !== undefined) {
      const value = condition.value
      return `${value.value} ${value.unit || 'GB'}`
    }

    if (Array.isArray(condition.value)) {
      return condition.value.join(', ')
    }

    if (typeof condition.value === 'object') {
      return JSON.stringify(condition.value)
    }

    return String(condition.value)
  }

  // 搜索事件
  onSearch() {
    const searchParams = this.buildSearchParams()
    this.$emit('search', searchParams)
  }

  // 构建搜索参数
  private buildSearchParams(): any {
    const params: any = {
      // 添加复杂查询标识
      complex_search: true,
      groups_count: this.conditionGroups.length
    }

    // 构建组数据结构
    const groupsData = this.conditionGroups.map((group, groupIndex) => {
      const conditions = group.conditions
        .filter(condition => condition.field && condition.operator && condition.value !== null)
        .map((condition, conditionIndex) => ({
          field: condition.field,
          operator: this.convertOperatorForBackend(condition.operator),  // 转换为后端格式
          value: this.formatParamValue(condition),
          mode: condition.mode,
          index: conditionIndex
        }))

      return {
        id: group.id,
        name: group.name || `条件组${groupIndex + 1}`,
        logic: group.logic,
        conditions: conditions,
        conditions_count: conditions.length
      }
    }).filter(group => group.conditions_count > 0)

    // 添加组间逻辑关系
    const betweenGroupLogics = []
    for (let i = 0; i < this.conditionGroups.length - 1; i++) {
      betweenGroupLogics.push(this.conditionGroups[i].betweenGroupLogic || 'and')
    }

    params.groups = JSON.stringify(groupsData)
    params.between_group_logics = JSON.stringify(betweenGroupLogics)

    // 为了兼容性，也生成扁平化的参数
    this.conditionGroups.forEach((group, groupIndex) => {
      const groupPrefix = groupIndex > 0 ? `group_${groupIndex}_` : ''

      group.conditions.forEach((condition, conditionIndex) => {
        if (!condition.field || !condition.operator || condition.value === null) {
          return
        }

        const paramKey = `${groupPrefix}${condition.field}`
        const paramValue = this.formatParamValue(condition)

        if (condition.mode === 'exclude') {
          params[`${paramKey}_exclude`] = paramValue
        } else {
          params[paramKey] = paramValue
        }

        // 添加操作符信息（转换为后端格式）
        params[`${paramKey}_op`] = this.convertOperatorForBackend(condition.operator)
      })

      // 添加组逻辑
      if (groupIndex > 0) {
        params[`group_${groupIndex}_logic`] = group.logic
      }
    })

    return params
  }

  // 转换前端操作符为后端格式（支持智能降级）
  private convertOperatorForBackend(frontendOperator: string): string {
    // 查找映射
    const backendOperator = this.operatorMapping[frontendOperator]

    if (backendOperator) {
      return backendOperator
    }

    // 未找到映射，尝试降级策略
    const fallbackOp = this.getOperatorFallback(frontendOperator)

    if (fallbackOp) {
      const fallbackBackendOp = this.operatorMapping[fallbackOp]
      if (fallbackBackendOp) {
        console.warn(
          `[AdvancedSearchBuilder] 操作符 "${frontendOperator}" 后端不支持，` +
          `自动降级为 "${fallbackOp}" (${fallbackBackendOp})`
        )
        return fallbackBackendOp
      }
    }

    // 降级失败，返回原值并记录错误
    console.error(
      `[AdvancedSearchBuilder] 操作符 "${frontendOperator}" 无法转换且无降级策略，` +
      `这可能导致API调用失败！请检查后端API文档。`
    )
    return frontendOperator
  }

  // 转换后端操作符为前端格式（用于编辑已保存的搜索条件）
  private convertOperatorForFrontend(backendOperator: string): string {
    const frontendOperator = this.reverseOperatorMapping[backendOperator]
    if (!frontendOperator) {
      console.warn(`[AdvancedSearchBuilder] 未找到反向操作符映射: ${backendOperator}，使用原值`)
      return backendOperator
    }
    return frontendOperator
  }

  // 验证操作符配置的完整性（开发环境调用）
  private validateOperatorConfig(): void {
    if (process.env.NODE_ENV !== 'production') {
      const allOperators = Object.values(this.operatorGroups).flat()
      const backendValues = new Set<string>()
      const duplicates: string[] = []

      // 检查重复的后端值
      allOperators.forEach(op => {
        const backendValue = op.backendValue || op.value
        if (backendValues.has(backendValue)) {
          duplicates.push(backendValue)
        }
        backendValues.add(backendValue)
      })

      if (duplicates.length > 0) {
        console.warn(
          `[AdvancedSearchBuilder] 发现重复的后端操作符值: ${duplicates.join(', ')}` +
          `这可能导致反向映射失败！`
        )
      }

      // 检查降级循环依赖
      allOperators.forEach(op => {
        if (op.fallback) {
          const fallbackOp = allOperators.find(o => o.value === op.fallback)
          if (!fallbackOp) {
            console.error(
              `[AdvancedSearchBuilder] 操作符 "${op.value}" 的降级目标 "${op.fallback}" 不存在！`
            )
          } else if (fallbackOp.fallback === op.value) {
            console.warn(
              `[AdvancedSearchBuilder] 发现循环降级依赖: "${op.value}" <-> "${fallbackOp.value}"`
            )
          }
        }
      })

      console.log(
        `[AdvancedSearchBuilder] 操作符配置验证完成\n` +
        `- 前端操作符数量: ${allOperators.length}\n` +
        `- 后端操作符数量: ${backendValues.size}\n` +
        `- 支持降级的操作符: ${allOperators.filter(op => op.fallback).length}`
      )
    }
  }

  // 获取所有支持的后端操作符列表（用于与后端API文档对照）
  private getSupportedBackendOperators(): string[] {
    return Object.values(this.operatorMapping)
  }

  // 格式化参数值
  private formatParamValue(condition: SearchCondition): any {
    const field = this.getFieldInfo(condition.field)

    // 特殊处理种子大小范围的 "介于" 操作符
    if (condition.field === 'size' && condition.operator === 'between') {
      const value = condition.value
      if (value && typeof value === 'object' && value.min !== undefined && value.max !== undefined) {
        // 返回对象格式，后端需要处理 min 和 max
        return {
          min: value.min !== null ? `${value.min} ${value.minUnit || 'GB'}` : null,
          max: value.max !== null ? `${value.max} ${value.maxUnit || 'GB'}` : null
        }
      }
      return condition.value
    }

    // 特殊处理种子大小其他操作符（带单位）
    if (condition.field === 'size' && condition.operator !== 'between') {
      const value = condition.value
      if (value && typeof value === 'object' && value.value !== undefined) {
        // 转换为 "数字 单位" 格式，如 "1.5 GB"
        return value.value !== null ? `${value.value} ${value.unit || 'GB'}` : null
      }
      return condition.value
    }

    switch (field?.type) {
      case 'date':
        if (condition.value && typeof condition.value === 'object') {
          return JSON.stringify(condition.value)
        }
        return condition.value

      case 'number':
        return Number(condition.value)

      case 'multiSelect':
        return Array.isArray(condition.value) ? condition.value.join(',') : condition.value

      case 'boolean':
        return condition.value ? '1' : '0'

      default:
        return condition.value
    }
  }

  // 预览查询
  previewSearchQuery() {
    this.previewVisible = true
  }

  // 复制查询到剪贴板
  async copyQueryToClipboard() {
    try {
      await navigator.clipboard.writeText(this.formattedQuery)
      this.$message.success('查询已复制到剪贴板')
    } catch (error) {
      this.$message.error('复制失败')
    }
  }

  // 重置条件
  resetConditions() {
    this.conditionGroups = []
    this.initializeConditions()
    this.$emit('reset')
  }

  // 保存搜索模板
  saveSearchTemplate() {
    this.templateForm = {
      name: '',
      description: '',
      isDefault: false
    }
    this.saveTemplateVisible = true
  }

  // 确认保存模板
  confirmSaveTemplate() {
    if (!this.templateForm.name.trim()) {
      this.$message.warning('请输入模板名称')
      return
    }

    const template = {
      id: this.generateId(),
      name: this.templateForm.name,
      description: this.templateForm.description,
      isDefault: this.templateForm.isDefault,
      conditions: JSON.parse(JSON.stringify(this.conditionGroups)),
      createdTime: new Date().toISOString()
    }

    this.$emit('save-template', template)
    this.saveTemplateVisible = false
    this.$message.success('模板保存成功')
  }
}
</script>

<style lang="scss" scoped>
.advanced-search-builder {
  .condition-groups {
    margin-bottom: 16px;
  }

  .condition-group {
    margin-bottom: 16px;
    padding: 16px;
    border: 1px solid #e4e7ed;
    border-radius: 8px;
    background-color: #fafafa;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);

    .group-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid #ebeef5;

      .group-title {
        font-weight: 600;
        color: #303133;
        display: flex;
        align-items: center;

        .group-name {
          cursor: pointer;
          padding: 2px 6px;
          border-radius: 4px;
          transition: background-color 0.2s;

          &:hover {
            background-color: #f0f2f5;
          }
        }
      }

      .group-actions {
        display: flex;
        gap: 8px;
      }
    }

    .group-logic-settings {
      display: flex;
      align-items: center;
      margin-bottom: 12px;
      padding: 8px 12px;
      background-color: #f0f9ff;
      border: 1px solid #bfdbfe;
      border-radius: 6px;

      .logic-desc {
        margin-left: 8px;
        font-size: 12px;
        color: #6b7280;
      }
    }

    .conditions {
      .condition-item {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        margin-bottom: 12px;
        padding: 12px;
        background-color: #fff;
        border: 1px solid #ebeef5;
        border-radius: 6px;
        position: relative;

        &:hover {
          border-color: #c0c4cc;
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
        }

        .condition-logic {
          position: absolute;
          top: -8px;
          left: 50%;
          transform: translateX(-50%);

          .logic-tag {
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 10px;
          }
        }

        .condition-content {
          display: flex;
          align-items: center;
          width: 100%;
          gap: 12px;
        }

        .condition-field,
        .condition-operator {
          flex-shrink: 0;
        }

        .condition-value {
          flex: 1;
          min-width: 200px;
        }

        .condition-mode {
          flex-shrink: 0;
        }

        .condition-actions {
          flex-shrink: 0;
        }
      }
    }

    .group-between-logic {
      display: flex;
      justify-content: center;
      margin: 16px 0;

      .logic-connector {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 12px 16px;
        background-color: #fef3c7;
        border: 1px solid #fcd34d;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(251, 191, 36, 0.1);

        .logic-description {
          margin-top: 4px;
          font-size: 11px;
          color: #92400e;
          white-space: nowrap;
        }
      }
    }
  }

  .add-group {
    margin-bottom: 16px;
    text-align: center;

    .el-button {
      padding: 12px 24px;
      border-radius: 8px;
      font-weight: 500;
    }
  }

  .search-actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    padding-top: 16px;
    border-top: 1px solid #e4e7ed;

    .el-button {
      border-radius: 6px;
    }
  }

  .query-preview {
    background-color: #f8fafc;
    padding: 16px;
    border-radius: 8px;
    font-family: 'Courier New', Monaco, monospace;
    font-size: 13px;
    line-height: 1.6;
    color: #1e293b;
    max-height: 400px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
    border: 1px solid #e2e8f0;

    &::-webkit-scrollbar {
      width: 6px;
    }

    &::-webkit-scrollbar-track {
      background: #f1f1f1;
      border-radius: 3px;
    }

    &::-webkit-scrollbar-thumb {
      background: #c1c1c1;
      border-radius: 3px;

      &:hover {
        background: #a8a8a8;
      }
    }
  }
}

// 响应式设计
@media (max-width: 768px) {
  .advanced-search-builder {
    .condition-group {
      padding: 12px;

      .condition-item {
        .condition-content {
          flex-direction: column;
          align-items: stretch;
          gap: 8px;

          .condition-field,
          .condition-operator,
          .condition-mode {
            width: 100%;
          }

          .condition-value {
            min-width: auto;
          }
        }
      }
    }

    .search-actions {
      flex-direction: column;

      .el-button {
        width: 100%;
      }
    }
  }
}
</style>
