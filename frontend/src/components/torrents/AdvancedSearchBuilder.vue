<template>
  <div class="advanced-search-builder">
    <!-- 搜索条件组列表 -->
    <div class="condition-groups">
      <template v-for="(group, groupIndex) in conditionGroups">
        <div
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
                class="group-name-input"
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
                class="group-logic-tag"
              >
                {{ (group.logic || 'and').toUpperCase() }}
              </el-tag>
            </div>
            <div class="group-actions">
              <el-button
                size="mini"
                icon="el-icon-edit"
                @click="startEditingGroup(group)"
                title="重命名条件组"
              />
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
              class="group-logic-select"
              @change="onGroupLogicChange(group)"
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
                  {{ (group.logic || 'and').toUpperCase() }}
                </el-tag>
              </div>

              <!-- 条件内容 -->
              <div class="condition-content">
                <!-- 字段选择器 -->
                <div class="condition-field">
                  <!-- 行标签仅移动端堆叠布局显示（桌面横排自明，见底部媒体查询） -->
                  <span class="condition-row-label">字段</span>
                  <el-select
                    v-model="condition.field"
                    placeholder="选择字段"
                    size="small"
                    class="condition-field-select"
                    @change="onFieldChange(condition)"
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
                  <span class="condition-row-label">操作</span>
                  <el-select
                    v-model="condition.operator"
                    placeholder="选择操作"
                    size="small"
                    class="condition-operator-select"
                    @change="onOperatorChange(condition)"
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
                  <span class="condition-row-label condition-row-label--value">内容</span>
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
                  <span class="condition-row-label">方式</span>
                  <el-radio-group
                    v-model="condition.mode"
                    size="small"
                    @change="onConditionModeChange(condition)"
                    :disabled="!conditionSupportsExclude(condition)"
                  >
                    <el-radio-button label="include">包含</el-radio-button>
                    <el-radio-button
                      label="exclude"
                      :disabled="!conditionSupportsExclude(condition)"
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

          <!-- 组内添加条件放在条件列表底部，避免与全局“添加条件组”误触。 -->
          <div class="add-condition">
            <el-button
              type="primary"
              size="small"
              icon="el-icon-plus"
              @click="addCondition(group)"
            >
              添加条件
            </el-button>
          </div>
        </div>

        <!-- 组间逻辑是条件组之间的独立控件，不属于任一条件组。 -->
        <div
          v-if="groupIndex < conditionGroups.length - 1"
          :key="`${group.id}-between-logic`"
          class="group-between-logic"
        >
          <div class="logic-connector">
            <el-select
              v-model="group.betweenGroupLogic"
              size="small"
              class="between-logic-select"
              @change="onBetweenGroupLogicChange(group)"
            >
              <el-option label="AND" value="and" />
              <el-option label="OR" value="or" />
            </el-select>
            <span class="logic-description">{{ getBetweenGroupLogicDescription(group.betweenGroupLogic) }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- 添加条件组按钮 -->
    <div class="add-group">
      <el-button
        size="small"
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
        size="small"
        icon="el-icon-search"
        @click="onSearch"
        :loading="searching"
      >
        执行搜索
      </el-button>
      <el-button
        size="small"
        icon="el-icon-document"
        @click="saveSearchTemplate"
      >
        保存为模板
      </el-button>
      <el-button
        size="small"
        icon="el-icon-refresh-left"
        @click="resetConditions"
      >
        重置条件
      </el-button>
      <el-button
        size="small"
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
      custom-class="advanced-search-dialog"
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
      custom-class="advanced-search-dialog"
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
import { Component, Vue, Prop } from 'vue-property-decorator'
import ConditionValueInput from './ConditionValueInput.vue'
import { extractErrorMessage } from '@/utils/formatters'
import {
  AdvancedSearchConditionValue,
  AdvancedSearchConditionState,
  AdvancedSearchBuilderParams,
  AdvancedSearchGroupState,
  AdvancedSearchValidationError,
  buildAdvancedSearchParams,
  transitionConditionValue,
  operatorSupportsExclude
} from './advancedSearchState'
import {
  ADVANCED_SEARCH_ADVANCED_FIELDS,
  ADVANCED_SEARCH_BASIC_FIELDS,
  ADVANCED_SEARCH_STATUS_FIELDS,
  ADVANCED_SEARCH_TIME_FIELDS,
  ADVANCED_SEARCH_RATIO_FIELDS,
  OperatorDisplayGroup,
  SearchField,
  buildGroupsQueryText,
  describeConditionValue,
  generateConditionId,
  getOperatorGroupsForField,
  getOperatorLabel as sharedGetOperatorLabel,
  getSearchFieldInfo,
  getSearchFieldOptions,
  loadAdvancedSearchDynamicOptions,
  normalizeLoadedGroups
} from './advancedSearchFields'

// 搜索条件接口
type SearchCondition = AdvancedSearchConditionState

// 条件组接口
type ConditionGroup = AdvancedSearchGroupState

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

  // 动态字段选项（由 loadFieldOptions 异步填充）
  // 注：TS readonly 仅约束编译期；这三个数组在运行时可整体替换引用以触发响应式更新。
  private categoryOptions: Array<{ label: string, value: string }> = []
  private tagOptions: Array<{ label: string, value: string }> = []
  private downloaderOptions: Array<{ label: string, value: string }> = []
  private fieldOptionsLoading = false

  // 字段分组：模板需经实例属性访问，指向共享层常量（桌面/移动同源）
  get advancedFields(): readonly SearchField[] {
    return ADVANCED_SEARCH_ADVANCED_FIELDS
  }

  // 基本信息字段
  get basicFields(): readonly SearchField[] {
    return ADVANCED_SEARCH_BASIC_FIELDS
  }

  // 状态信息字段
  get statusFields(): readonly SearchField[] {
    return ADVANCED_SEARCH_STATUS_FIELDS
  }

  // 时间信息字段
  get timeFields(): readonly SearchField[] {
    return ADVANCED_SEARCH_TIME_FIELDS
  }

  // 比率信息字段
  get ratioFields(): readonly SearchField[] {
    return ADVANCED_SEARCH_RATIO_FIELDS
  }

  // 运行时配置由后端机器契约生成，禁止在组件内维护语义副本（过滤见共享层）。

  // Computed
  get formattedQuery(): string {
    return this.buildQueryText()
  }

  // Methods
  created() {
    this.initializeConditions()
    // 首次挂载拉取一次动态字段选项；后续每次打开对话框由父组件调用 refreshFieldOptions() 刷新
    this.loadFieldOptions()
  }

  /**
   * 重新拉取动态字段选项（分类/标签/下载器）。
   * 供父组件在每次打开高级搜索对话框时通过 $refs 调用，确保下拉反映最新数据。
   */
  refreshFieldOptions() {
    this.loadFieldOptions()
  }

  /**
   * 拉取逻辑在共享层 loadAdvancedSearchDynamicOptions（移动端同源复用）：
   * - 每次刷新都从空开始：避免"上次成功 + 本次失败"时残留旧数据误导用户；
   * - 仅当三个请求全部失败时才弹出 $message.error，避免一连三条红条打扰用户；
   * - 异步回调写 data 前判 _isDestroyed，规避组件销毁后的响应式警告。
   */
  private async loadFieldOptions() {
    if (this._isDestroyed) return
    this.fieldOptionsLoading = true
    this.categoryOptions = []
    this.tagOptions = []
    this.downloaderOptions = []

    const options = await loadAdvancedSearchDynamicOptions()

    if (this._isDestroyed) return
    this.categoryOptions = options.categoryOptions
    this.tagOptions = options.tagOptions
    this.downloaderOptions = options.downloaderOptions

    // 全部失败才告警；部分失败保持已成功项的填充，静默降级
    if (options.failedCount === 3) {
      this.$message.error(extractErrorMessage(options.firstError) || '加载搜索字段选项失败')
    }

    this.fieldOptionsLoading = false
  }

  private initializeConditions() {
    if (this.conditionGroups.length === 0) {
      this.addConditionGroup()
    }
  }

  private generateId(): string {
    return generateConditionId()
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
    condition.operator = ''
    const field = this.getFieldInfo(condition.field)
    condition.value = transitionConditionValue(
      condition.field,
      field?.type,
      condition.operator
    )
    condition.mode = 'include'
  }

  // 操作符变更处理
  onOperatorChange(condition: SearchCondition) {
    const field = this.getFieldInfo(condition.field)
    condition.value = transitionConditionValue(
      condition.field,
      field?.type,
      condition.operator
    )
    if (!operatorSupportsExclude(condition.operator)) {
      condition.mode = 'include'
    }
  }

  // 条件值变更处理
  onConditionValueChange(
    condition: SearchCondition,
    value: AdvancedSearchConditionValue
  ) {
    condition.value = value
  }

  // 条件模式变更处理
  onConditionModeChange(_condition: SearchCondition) {
    // 模式变更时的特殊处理
  }

  // 获取字段信息
  private getFieldInfo(fieldKey: string): SearchField | undefined {
    return getSearchFieldInfo(fieldKey)
  }

  // 获取字段选项（静态定义优先，分类/标签/下载器注入当次动态拉取结果）
  getFieldOptions(fieldKey: string): Array<{label: string, value: string}> {
    return getSearchFieldOptions(fieldKey, {
      categoryOptions: this.categoryOptions,
      tagOptions: this.tagOptions,
      downloaderOptions: this.downloaderOptions
    })
  }

  // 获取操作符组（契约过滤与 matchMode 收敛在共享层）
  getOperatorGroups(fieldKey: string): OperatorDisplayGroup[] {
    return getOperatorGroupsForField(fieldKey)
  }

  // 字段是否支持排除模式
  fieldSupportsExclude(fieldKey: string): boolean {
    const field = this.getFieldInfo(fieldKey)
    return field?.supportsExclude || false
  }

  conditionSupportsExclude(condition: SearchCondition): boolean {
    return (
      this.fieldSupportsExclude(condition.field) &&
      operatorSupportsExclude(condition.operator)
    )
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

  // 构建查询文本（渲染语义在共享层，与移动端摘要/预览同源）
  private buildQueryText(): string {
    return buildGroupsQueryText(this.conditionGroups)
  }

  // 获取操作符标签
  private getOperatorLabel(operator: string): string {
    return sharedGetOperatorLabel(operator)
  }

  // 获取值标签
  private getValueLabel(condition: SearchCondition): string {
    return describeConditionValue(condition)
  }

  // 搜索事件
  onSearch() {
    try {
      const searchParams = this.buildSearchParams()
      this.$emit('search', searchParams)
    } catch (error) {
      if (error instanceof AdvancedSearchValidationError) {
        this.$message.warning(error.message)
        return
      }
      throw error
    }
  }

  // 构建搜索参数。任何无效条件都会整体失败，禁止静默丢弃或降级。
  buildSearchParams(): AdvancedSearchBuilderParams {
    return buildAdvancedSearchParams(this.conditionGroups)
  }

  /** 返回经过完整校验的条件快照，供已保存搜索更新复用。 */
  getTemplateGroupsSnapshot(): AdvancedSearchGroupState[] {
    this.buildSearchParams()
    return JSON.parse(JSON.stringify(this.conditionGroups)) as AdvancedSearchGroupState[]
  }

  // 预览查询
  previewSearchQuery() {
    try {
      this.buildSearchParams()
      this.previewVisible = true
    } catch (error) {
      if (error instanceof AdvancedSearchValidationError) {
        this.$message.warning(error.message)
        return
      }
      throw error
    }
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

  // v1.0.5 应用模板：回填 conditionGroups（供父组件调用）
  applyTemplateGroups(
    groups: ConditionGroup[],
    _options?: { sort_by?: string, sort_order?: string }
  ) {
    if (!Array.isArray(groups) || groups.length === 0) {
      this.conditionGroups = []
      this.initializeConditions()
      return
    }
    // 深拷贝避免污染模板源数据
    this.conditionGroups = JSON.parse(JSON.stringify(groups)) as ConditionGroup[]
    // 归一化历史模板（共享层，移动端同源）：旧 multiSelect 操作符在单值精确列上
    // 转为 in/not_in，value 统一为数组形态（兼容旧逗号串/单值存储）。
    normalizeLoadedGroups(this.conditionGroups)
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
    try {
      this.buildSearchParams()
    } catch (error) {
      if (error instanceof AdvancedSearchValidationError) {
        this.$message.warning(error.message)
        return
      }
      throw error
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
  }
}
</script>

<style lang="scss" scoped>
.advanced-search-builder {
  font-size: 13px;

  ::v-deep {
    .el-input__inner,
    .el-radio-button__inner,
    .el-button,
    .el-tag {
      font-size: 12px;
    }
  }

  /* 条件行小标签：桌面横排自明不显示，仅移动端堆叠布局显示（见底部媒体查询） */
  .condition-row-label {
    display: none;
  }

  /* 内联定宽全部类化（桌面宽度不变）：窄屏断点可整体铺满（移动端 /m/search 适配） */
  .group-name-input {
    width: 120px;
    margin-right: 8px;
  }

  .group-logic-tag {
    margin-left: 8px;
  }

  .group-logic-select {
    width: 100px;
  }

  .condition-field-select {
    width: 140px;
  }

  .condition-operator-select {
    width: 120px;
  }

  .between-logic-select {
    width: 100px;
  }

  .condition-groups {
    margin-bottom: 12px;
  }

  .condition-group {
    margin-bottom: 12px;
    padding: 12px;
    border: 1px solid #e4e7ed;
    border-radius: 8px;
    background-color: #fafafa;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);

    .group-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 1px solid #ebeef5;

      .group-title {
        font-weight: 600;
        font-size: 13px;
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
      margin-bottom: 10px;
      padding: 6px 10px;
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
        gap: 8px;
        margin-bottom: 8px;
        padding: 8px;
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
          gap: 8px;
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

    .add-condition {
      display: flex;
      justify-content: center;
      margin-top: 4px;
    }
  }

  .group-between-logic {
    display: flex;
    justify-content: center;
    margin: 4px 0 16px;

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

  .add-group {
    margin-bottom: 12px;
    text-align: center;

    .el-button {
      padding: 9px 18px;
      border-radius: 6px;
      font-weight: 500;
    }
  }

  .search-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    padding-top: 12px;
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

// 响应式设计（移动端条件组适配，/m/search 整页复用本组件）：
// 选择器铺满整行、组头可换行、组内逻辑说明折行下移、AND/OR 悬浮标签
// 不压字段选择器、组间逻辑卡片通栏、操作按钮纵向铺满
@media (max-width: 768px) {
  .advanced-search-builder {
    .condition-group {
      padding: 12px;

      .group-header {
        flex-wrap: wrap;
        gap: 6px;
      }

      .group-logic-settings {
        flex-direction: column;
        align-items: stretch;
        gap: 4px;

        .logic-desc {
          margin-left: 0;
        }
      }

      .condition-item {
        // 逻辑连接标签（absolute，top:-8px）自第 2 条条件起存在：
        // 加顶部内边距避免悬浮标签压住铺满后的字段选择器
        &:not(:first-child) {
          padding-top: 20px;
        }

        // 删除按钮：堆叠布局下不随容器拉伸为通栏，右对齐保持紧凑
        .condition-actions {
          align-self: flex-end;
        }

        .condition-content {
          flex-direction: column;
          align-items: stretch;
          gap: 8px;

          // 行标签：堆叠后四个控件同为灰底圆角框，无标签难以分辨“哪一格填内容”
          .condition-row-label {
            display: block;
            margin-bottom: 4px;
            font-size: 12px;
            line-height: 1;
            color: #909399;

            // “内容”行是用户要找的填写目标，用主题色与中性行区分
            &--value {
              color: var(--color-primary, #059669);
              font-weight: 600;
            }
          }

          .condition-field,
          .condition-operator,
          .condition-mode {
            width: 100%;
          }

          // 内容输入行唯一强调底色：让“填内容”从一排灰框里跳出来
          // 边框走 --color-primary-rgb：随主题色阶联动（绿色/橙色主题均适配）。
          // width:100% 必须显式：基础 align-items:center（多一层 .conditions，
          // 特异性更高）会压掉这里的 stretch，缺宽度会收缩为内容宽。
          .condition-value {
            width: 100%;
            min-width: auto;
            padding: 8px;
            background: var(--color-primary-lightest, #d1fae5);
            border: 1px solid rgba(var(--color-primary-rgb, 5, 150, 105), 0.35);
            border-radius: 6px;
          }

          // 移动端触控目标：条件行内输入/选择控件 32px→40px
          ::v-deep {
            .el-input__inner {
              height: 40px;
              line-height: 40px;
              font-size: 14px;
            }

            .el-input__icon {
              line-height: 40px;
            }

            // AdvancedMultiSelect 玻璃搜索框自绘 32px，不参与触控放大
            .ams__search-box .el-input__inner {
              height: 32px;
              line-height: 32px;
            }
          }

          // 包含/排除：等宽拉伸为大触控按钮
          .condition-mode {
            ::v-deep .el-radio-group {
              display: flex;
              width: 100%;
            }

            ::v-deep .el-radio-button {
              flex: 1;
            }

            ::v-deep .el-radio-button__inner {
              width: 100%;
              padding: 12px 0;
              font-size: 14px;
            }
          }
        }
      }
    }

    .condition-field-select,
    .condition-operator-select,
    .group-logic-select,
    .between-logic-select {
      width: 100%;
    }

    .group-name-input {
      width: 110px;
    }

    .group-between-logic {
      .logic-connector {
        width: 100%;

        .logic-description {
          white-space: normal;
          text-align: center;
        }
      }
    }

    .search-actions {
      flex-direction: column;

      .el-button {
        width: 100%;
        margin-left: 0;
      }
    }
  }
}
</style>

<!-- 预览/保存模板对话框挂 body（append-to-body），scoped 够不到；
     el-dialog 的 width prop 是内联样式，窄屏压宽须 !important 覆盖 -->
<style>
@media (max-width: 768px) {
  .advanced-search-dialog {
    width: 94% !important;
  }
}
</style>
