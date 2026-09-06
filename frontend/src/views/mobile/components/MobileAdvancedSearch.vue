<template>
  <div class="m-adv-search">
    <!-- 已保存搜索横滑胶囊：与桌面已保存搜索同源数据，点击即应用；
         ⚙ 进管理抽屉（保存更改/删除），＋ 新建（清空条件） -->
    <div class="m-adv-search__chips" aria-label="已保存高级搜索">
      <button type="button" class="m-adv-chip m-adv-chip--new" @click="startNewSearch">
        <i class="el-icon-plus" aria-hidden="true" />新建
      </button>
      <button
        v-for="tpl in advancedTemplates"
        :key="tpl.id"
        type="button"
        class="m-adv-chip"
        :class="{'is-selected': tpl.id === selectedTemplateId}"
        :title="tpl.name"
        @click="applySavedSearch(tpl)"
      >
        {{ tpl.name }}
      </button>
      <button
        type="button"
        class="m-adv-chip m-adv-chip--manage"
        aria-label="管理已保存搜索"
        @click="manageVisible = true"
      >
        <i class="el-icon-setting" aria-hidden="true" />
      </button>
    </div>

    <!-- 条件组：每条条件以一行摘要卡呈现，点击弹底部弹层编辑 -->
    <section
      v-for="(group, groupIndex) in conditionGroups"
      :key="group.id"
      class="m-adv-group"
    >
      <header class="m-adv-group__header">
        <el-input
          v-if="group.editing"
          v-model="group.name"
          size="small"
          class="m-adv-group__name-input"
          placeholder="组名称"
          @blur="finishEditingGroup(group)"
          @keyup.enter.native="finishEditingGroup(group)"
        />
        <button
          v-else
          type="button"
          class="m-adv-group__name"
          @click="startEditingGroup(group)"
        >
          {{ group.name || `条件组 ${groupIndex + 1}` }}
          <i class="el-icon-edit" aria-hidden="true" />
        </button>
        <div class="m-adv-group__header-side">
          <el-radio-group v-model="group.logic" size="mini" class="m-adv-group__logic">
            <el-radio-button label="and">AND</el-radio-button>
            <el-radio-button label="or">OR</el-radio-button>
          </el-radio-group>
          <el-dropdown
            v-if="conditionGroups.length > 1"
            trigger="click"
            @command="handleGroupCommand"
          >
            <button type="button" class="m-adv-group__more" aria-label="更多组操作">
              <i class="el-icon-more" aria-hidden="true" />
            </button>
            <el-dropdown-menu slot="dropdown">
              <el-dropdown-item :command="{action: 'rename', index: groupIndex}">
                <i class="el-icon-edit" aria-hidden="true" />重命名
              </el-dropdown-item>
              <el-dropdown-item :command="{action: 'duplicate', index: groupIndex}">
                <i class="el-icon-copy-document" aria-hidden="true" />复制组
              </el-dropdown-item>
              <el-dropdown-item :command="{action: 'clear', index: groupIndex}">
                <i class="el-icon-refresh-left" aria-hidden="true" />清空条件
              </el-dropdown-item>
              <el-dropdown-item :command="{action: 'delete', index: groupIndex}" divided>
                <i class="el-icon-delete" aria-hidden="true" />删除组
              </el-dropdown-item>
            </el-dropdown-menu>
          </el-dropdown>
        </div>
      </header>

      <div class="m-adv-group__conditions">
        <div
          v-for="(condition, conditionIndex) in group.conditions"
          :key="condition.id"
          class="m-adv-cond-card"
          role="button"
          @click="openConditionEditor(groupIndex, conditionIndex)"
        >
          <span
            class="m-adv-cond-card__summary"
            :class="{'is-empty': !condition.field}"
          >
            {{ conditionSummary(condition) }}
          </span>
          <button
            v-if="group.conditions.length > 1"
            type="button"
            class="m-adv-cond-card__remove"
            aria-label="删除条件"
            @click.stop="removeCondition(group, conditionIndex)"
          >
            <i class="el-icon-close" aria-hidden="true" />
          </button>
        </div>
        <button type="button" class="m-adv-cond-add" @click="addCondition(group)">
          <i class="el-icon-plus" aria-hidden="true" />添加条件
        </button>
      </div>

      <!-- 组间逻辑：组与组之间的独立控件，不属于任一条件组 -->
      <div v-if="groupIndex < conditionGroups.length - 1" class="m-adv-between">
        <el-radio-group v-model="group.betweenGroupLogic" size="mini">
          <el-radio-button label="and">AND</el-radio-button>
          <el-radio-button label="or">OR</el-radio-button>
        </el-radio-group>
        <span class="m-adv-between__desc">{{ betweenLogicDesc(group) }}</span>
      </div>
    </section>

    <button type="button" class="m-adv-add-group" @click="addConditionGroup">
      <i class="el-icon-plus" aria-hidden="true" />添加条件组
    </button>

    <!-- 吸底操作条：主操作常驻（避开悬浮 Tab 栏，同返回顶部浮标定位），
         次要操作（保存为模板/重置/预览）收进 ⋯ 菜单 -->
    <div class="m-adv-bar">
      <el-button
        type="primary"
        class="m-adv-bar__search"
        :loading="searching"
        @click="onSearch"
      >
        <i class="el-icon-search" aria-hidden="true" />执行搜索
      </el-button>
      <el-dropdown trigger="click" @command="handleBarCommand">
        <button type="button" class="m-adv-bar__more" aria-label="更多操作">
          <i class="el-icon-more" aria-hidden="true" />
        </button>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="save-template">
            <i class="el-icon-document" aria-hidden="true" />保存为模板
          </el-dropdown-item>
          <el-dropdown-item command="reset">
            <i class="el-icon-refresh-left" aria-hidden="true" />重置条件
          </el-dropdown-item>
          <el-dropdown-item command="preview">
            <i class="el-icon-view" aria-hidden="true" />预览查询
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </div>

    <!-- 单条条件编辑底部弹层 -->
    <condition-edit-sheet
      :visible="sheetVisible"
      :condition="editingCondition"
      :dynamic-options="dynamicOptions"
      @update:visible="sheetVisible = $event"
      @confirm="onSheetConfirm"
    />

    <!-- 已保存搜索管理抽屉 -->
    <el-drawer
      custom-class="m-adv-manage"
      direction="btt"
      size="64%"
      :visible="manageVisible"
      :append-to-body="true"
      @update:visible="manageVisible = $event"
    >
      <div class="m-adv-manage__body">
        <div class="m-adv-manage__grabber" aria-hidden="true" />
        <div class="m-adv-manage__header">
          <span class="m-adv-manage__title">已保存搜索（{{ advancedTemplates.length }}）</span>
          <el-button
            type="text"
            size="mini"
            :loading="templatesLoading"
            aria-label="刷新已保存搜索"
            @click="loadSavedSearches"
          >
            <i class="el-icon-refresh" aria-hidden="true" />
          </el-button>
        </div>
        <div v-loading="templatesLoading" class="m-adv-manage__list">
          <button
            v-for="tpl in advancedTemplates"
            :key="tpl.id"
            type="button"
            class="m-adv-manage__item"
            :class="{'is-selected': tpl.id === selectedTemplateId}"
            @click="applySavedSearch(tpl)"
          >
            <span class="m-adv-manage__name" :title="tpl.name">{{ tpl.name }}</span>
            <span class="m-adv-manage__meta">
              <span v-if="tpl.is_default">系统</span>
              <span v-else-if="tpl.is_public">公开</span>
              <span v-else>个人</span>
              <span>使用 {{ tpl.usage_count || 0 }} 次</span>
            </span>
          </button>
          <div v-if="!templatesLoading && advancedTemplates.length === 0" class="m-adv-manage__empty">
            暂无已保存高级搜索
          </div>
        </div>
        <div class="m-adv-manage__footer">
          <el-tooltip :content="selectedManageHint" placement="top" :open-delay="200">
            <span class="m-adv-manage__trigger">
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="!canManageSelected"
                :loading="templateActionLoading"
                @click="updateSelectedTemplate"
              >
                保存更改
              </el-button>
            </span>
          </el-tooltip>
          <el-tooltip :content="selectedDeleteHint" placement="top" :open-delay="200">
            <span class="m-adv-manage__trigger">
              <el-button
                size="small"
                :disabled="!canManageSelected"
                :loading="templateActionLoading"
                @click="deleteSelectedTemplate"
              >
                删除
              </el-button>
            </span>
          </el-tooltip>
        </div>
      </div>
    </el-drawer>

    <!-- 保存模板对话框（窄屏压宽走 .m-adv-dialog 全局样式） -->
    <el-dialog
      title="保存搜索模板"
      :visible.sync="saveTemplateVisible"
      width="90%"
      custom-class="m-adv-dialog"
      :modal-append-to-body="true"
      :append-to-body="true"
      :close-on-click-modal="false"
    >
      <el-form ref="templateForm" :model="templateForm" label-position="top">
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
        <el-button
          type="primary"
          :loading="templateActionLoading"
          @click="confirmSaveTemplate"
        >
          保存
        </el-button>
      </div>
    </el-dialog>

    <!-- 预览查询对话框 -->
    <el-dialog
      title="搜索条件预览"
      :visible.sync="previewVisible"
      width="90%"
      custom-class="m-adv-dialog"
      :modal-append-to-body="true"
      :append-to-body="true"
      :close-on-click-modal="false"
    >
      <pre class="m-adv-preview">{{ formattedQuery }}</pre>
      <div slot="footer">
        <el-button @click="previewVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyQueryToClipboard">复制查询</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'
import ConditionEditSheet from './ConditionEditSheet.vue'
import {
  createSearchTemplate,
  deleteSearchTemplate,
  getSearchTemplates,
  updateSearchTemplate,
  QueryTemplateConditions,
  SearchTemplate
} from '@/api/torrents'
import { UserModule } from '@/store/modules/user'
import { extractErrorMessage } from '@/utils/formatters'
import {
  AdvancedSearchBuilderParams,
  AdvancedSearchConditionState,
  AdvancedSearchGroupState,
  AdvancedSearchValidationError,
  buildAdvancedSearchParams
} from '@/components/torrents/advancedSearchState'
import {
  AdvancedSearchDynamicOptionSet,
  buildGroupsQueryText,
  describeCondition,
  generateConditionId,
  loadAdvancedSearchDynamicOptions,
  normalizeLoadedGroups
} from '@/components/torrents/advancedSearchFields'

/** 移动端固定排序（与 /m/search 执行搜索的 sort 默认一致） */
const MOBILE_SORT_BY = 'added_date'
const MOBILE_SORT_ORDER: 'asc' | 'desc' = 'desc'

interface GroupCommand {
  action: 'rename' | 'delete' | 'duplicate' | 'clear'
  index: number
}

/**
 * 移动端高级搜索构建器（方案三移动原生重构）：
 * - 条件以一行摘要卡呈现，点击弹 ConditionEditSheet 编辑；
 * - 已保存搜索收进顶部横滑胶囊（点击应用）＋ ⚙ 管理抽屉（保存更改/删除），
 *   数据与桌面已保存搜索同源（getSearchTemplates is_public，source=advanced）；
 * - 字段/操作符/校验/请求构造与桌面 AdvancedSearchBuilder 共享同源实现
 *   （advancedSearchState + advancedSearchFields），本组件只重写交互壳；
 * - 吸底“执行搜索”常驻，次要操作收进 ⋯ 菜单。
 * 对外接口与桌面工作区对齐：onSearch()/refreshFieldOptions()/
 * applyTemplateGroups()/resetConditions()（/m/search 下拉刷新复用）。
 */
@Component({
  name: 'MobileAdvancedSearch',
  components: {
    'condition-edit-sheet': ConditionEditSheet
  }
})
export default class MobileAdvancedSearch extends Vue {
  @Prop({ type: Boolean, default: false }) readonly searching!: boolean

  private conditionGroups: AdvancedSearchGroupState[] = []
  private dynamicOptions: AdvancedSearchDynamicOptionSet = {
    categoryOptions: [],
    tagOptions: [],
    downloaderOptions: []
  }

  // 已保存搜索
  private advancedTemplates: SearchTemplate[] = []
  private selectedTemplateId = ''
  private templatesLoading = false
  private templateActionLoading = false
  private templateRequestSequence = 0

  // 条件编辑弹层
  private sheetVisible = false
  private editingGroupIndex = -1
  private editingConditionIndex = -1
  private editingCondition: AdvancedSearchConditionState | null = null

  // 抽屉与对话框
  private manageVisible = false
  private saveTemplateVisible = false
  private previewVisible = false
  private templateForm = {
    name: '',
    description: '',
    isDefault: false
  }

  // ============ 生命周期 ============

  created() {
    this.initializeConditions()
    this.loadFieldOptions()
  }

  mounted() {
    void this.loadSavedSearches()
  }

  // ============ 对外入口（与桌面工作区同签名） ============

  /** 校验并触发 search 事件（下拉刷新重跑复用） */
  public onSearch() {
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

  /** 刷新动态字段候选与已保存搜索列表 */
  public refreshFieldOptions() {
    this.loadFieldOptions()
    void this.loadSavedSearches()
  }

  /** 应用模板条件组（归一化历史模板，与桌面同源；排序沿用移动端固定值） */
  public applyTemplateGroups(
    groups: AdvancedSearchGroupState[],
    _options?: { sort_by?: string, sort_order?: string }
  ) {
    if (!Array.isArray(groups) || groups.length === 0) {
      this.conditionGroups = []
      this.initializeConditions()
      return
    }
    this.conditionGroups = JSON.parse(JSON.stringify(groups)) as AdvancedSearchGroupState[]
    normalizeLoadedGroups(this.conditionGroups)
  }

  public resetConditions() {
    this.conditionGroups = []
    this.initializeConditions()
    this.$emit('reset')
  }

  /** 返回经过完整校验的条件快照，供已保存搜索更新复用 */
  public getTemplateGroupsSnapshot(): AdvancedSearchGroupState[] {
    this.buildSearchParams()
    return JSON.parse(JSON.stringify(this.conditionGroups)) as AdvancedSearchGroupState[]
  }

  // ============ 查询构建 ============

  private buildSearchParams(): AdvancedSearchBuilderParams {
    return buildAdvancedSearchParams(this.conditionGroups)
  }

  get formattedQuery(): string {
    return buildGroupsQueryText(this.conditionGroups)
  }

  // ============ 动态字段候选 ============

  private async loadFieldOptions() {
    if (this._isDestroyed) return
    const options = await loadAdvancedSearchDynamicOptions()
    if (this._isDestroyed) return
    this.dynamicOptions = {
      categoryOptions: options.categoryOptions,
      tagOptions: options.tagOptions,
      downloaderOptions: options.downloaderOptions
    }
    // 全部失败才告警；部分失败静默降级（与桌面同语义）
    if (options.failedCount === 3) {
      this.$message.error(extractErrorMessage(options.firstError) || '加载搜索字段选项失败')
    }
  }

  // ============ 已保存搜索 ============

  get selectedTemplate(): SearchTemplate | null {
    return this.advancedTemplates.find(template => template.id === this.selectedTemplateId) || null
  }

  get canManageSelected(): boolean {
    const template = this.selectedTemplate
    if (!template || template.is_default) return false
    if (!template.is_public) return true
    return Boolean(UserModule.userId) && String(template.user_id) === String(UserModule.userId)
  }

  get selectedManageHint(): string {
    if (!this.selectedTemplate) return '请先选择一个个人搜索配置'
    if (this.selectedTemplate.is_default) return '系统搜索配置不可修改'
    if (!this.canManageSelected) return '公开搜索配置仅创建者可修改'
    return '用当前条件覆盖已选择的搜索配置'
  }

  get selectedDeleteHint(): string {
    if (!this.selectedTemplate) return '请先选择一个个人搜索配置'
    if (this.selectedTemplate.is_default) return '系统搜索配置不可删除'
    if (!this.canManageSelected) return '公开搜索配置仅创建者可删除'
    return '删除已选择的搜索配置'
  }

  async loadSavedSearches() {
    const message = this.$message
    const requestSequence = ++this.templateRequestSequence
    this.templatesLoading = true
    try {
      const response = await getSearchTemplates({ is_public: true })
      if (requestSequence !== this.templateRequestSequence) return
      if (response.code !== '200') {
        message.error(response.msg || '获取已保存搜索失败')
        return
      }

      const templates = Array.isArray(response.data) ? response.data : []
      this.advancedTemplates = templates
        .filter(template => template.conditions?.source === 'advanced')
        .sort((left, right) => {
          const defaultOrder = Number(right.is_default) - Number(left.is_default)
          if (defaultOrder !== 0) return defaultOrder
          const rightTime = Date.parse(right.updated_time || right.created_time) || 0
          const leftTime = Date.parse(left.updated_time || left.created_time) || 0
          return rightTime - leftTime
        })
      if (
        this.selectedTemplateId &&
        !this.advancedTemplates.some(template => template.id === this.selectedTemplateId)
      ) {
        this.selectedTemplateId = ''
      }
    } catch (error) {
      if (requestSequence === this.templateRequestSequence) {
        message.error(extractErrorMessage(error) || '获取已保存搜索失败')
      }
    } finally {
      if (requestSequence === this.templateRequestSequence) {
        this.templatesLoading = false
      }
    }
  }

  private applySavedSearch(template: SearchTemplate) {
    const groups = template.conditions.condition_groups
    if (!groups || groups.length === 0) {
      this.$message.warning('该搜索配置没有有效的高级搜索条件')
      return
    }

    try {
      this.applyTemplateGroups(groups, {
        sort_by: template.conditions.sort_by,
        sort_order: template.conditions.sort_order
      })
      this.selectedTemplateId = template.id
      this.manageVisible = false
    } catch (error) {
      this.$message.error(extractErrorMessage(error) || '加载搜索配置失败')
    }
  }

  private startNewSearch() {
    this.selectedTemplateId = ''
    this.resetConditions()
  }

  private buildTemplateConditions(groups: AdvancedSearchGroupState[]): QueryTemplateConditions {
    return {
      source: 'advanced',
      version: 1,
      condition_groups: groups,
      sort_by: MOBILE_SORT_BY,
      sort_order: MOBILE_SORT_ORDER
    }
  }

  private async createTemplate() {
    const message = this.$message
    let groups: AdvancedSearchGroupState[]
    try {
      groups = this.getTemplateGroupsSnapshot()
    } catch (error) {
      this.$message.warning(extractErrorMessage(error) || '当前搜索条件无效')
      return
    }

    const conditions = this.buildTemplateConditions(groups)
    this.templateActionLoading = true
    try {
      const response = await createSearchTemplate({
        name: this.templateForm.name,
        description: this.templateForm.description,
        conditions,
        is_public: false
      })
      if (response.code !== '200') {
        message.error(response.msg || '模板保存失败')
        return
      }
      this.selectedTemplateId = response.data.id
      await this.loadSavedSearches()
      this.saveTemplateVisible = false
      message.success('模板保存成功')
    } catch (error) {
      message.error(extractErrorMessage(error) || '模板保存失败')
    } finally {
      this.templateActionLoading = false
    }
  }

  private async updateSelectedTemplate() {
    const template = this.selectedTemplate
    if (!template || !this.canManageSelected) return

    let groups: AdvancedSearchGroupState[]
    try {
      groups = this.getTemplateGroupsSnapshot()
    } catch (error) {
      this.$message.warning(extractErrorMessage(error) || '当前搜索条件无效')
      return
    }

    const message = this.$message
    const conditions = this.buildTemplateConditions(groups)
    this.templateActionLoading = true
    try {
      const response = await updateSearchTemplate(template.id, { conditions })
      if (response.code !== '200') {
        message.error(response.msg || '保存更改失败')
        return
      }
      await this.loadSavedSearches()
      message.success('搜索配置已更新')
    } catch (error) {
      message.error(extractErrorMessage(error) || '保存更改失败')
    } finally {
      this.templateActionLoading = false
    }
  }

  private async deleteSelectedTemplate() {
    const template = this.selectedTemplate
    if (!template || !this.canManageSelected) return

    const message = this.$message
    const confirm = this.$confirm
    try {
      await confirm(`确认删除搜索配置“${template.name}”吗？`, '删除搜索配置', {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      })
    } catch {
      return
    }

    this.templateActionLoading = true
    try {
      const response = await deleteSearchTemplate(template.id)
      if (response.code !== '200') {
        message.error(response.msg || '删除搜索配置失败')
        return
      }
      this.selectedTemplateId = ''
      await this.loadSavedSearches()
      message.success('搜索配置已删除')
    } catch (error) {
      message.error(extractErrorMessage(error) || '删除搜索配置失败')
    } finally {
      this.templateActionLoading = false
    }
  }

  // ============ 条件组编辑 ============

  private initializeConditions() {
    if (this.conditionGroups.length === 0) {
      this.addConditionGroup()
    }
  }

  private addConditionGroup() {
    this.conditionGroups.push({
      id: generateConditionId(),
      name: '',
      logic: 'and',
      betweenGroupLogic: 'and',
      editing: false,
      conditions: [this.createEmptyCondition()]
    })
  }

  private createEmptyCondition(): AdvancedSearchConditionState {
    return {
      id: generateConditionId(),
      field: '',
      operator: '',
      value: null,
      mode: 'include'
    }
  }

  private handleGroupCommand(command: GroupCommand) {
    const { action, index } = command
    const group = this.conditionGroups[index]
    if (!group) return

    switch (action) {
      case 'rename':
        this.startEditingGroup(group)
        break
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

  private removeConditionGroup(groupIndex: number) {
    if (this.conditionGroups.length > 1) {
      this.conditionGroups.splice(groupIndex, 1)
    }
  }

  private duplicateConditionGroup(sourceGroup: AdvancedSearchGroupState) {
    const insertIndex = this.conditionGroups.indexOf(sourceGroup) + 1
    this.conditionGroups.splice(insertIndex, 0, {
      id: generateConditionId(),
      name: sourceGroup.name ? `${sourceGroup.name} (副本)` : '',
      logic: sourceGroup.logic,
      betweenGroupLogic: sourceGroup.betweenGroupLogic || 'and',
      editing: false,
      conditions: sourceGroup.conditions.map(condition => ({
        ...condition,
        id: generateConditionId()
      }))
    })
  }

  private clearGroupConditions(group: AdvancedSearchGroupState) {
    group.conditions = [this.createEmptyCondition()]
  }

  private startEditingGroup(group: AdvancedSearchGroupState) {
    if (!group.name) {
      group.name = `条件组 ${this.conditionGroups.indexOf(group) + 1}`
    }
    group.editing = true
  }

  private finishEditingGroup(group: AdvancedSearchGroupState) {
    if (!group.name || group.name.trim() === '') {
      group.name = ''
    } else {
      group.name = group.name.trim()
    }
    group.editing = false
  }

  private addCondition(group: AdvancedSearchGroupState) {
    group.conditions.push(this.createEmptyCondition())
    // 新条件直接进入编辑弹层：空条件摘要卡对用户无信息量
    this.openConditionEditor(
      this.conditionGroups.indexOf(group),
      group.conditions.length - 1
    )
  }

  private removeCondition(group: AdvancedSearchGroupState, conditionIndex: number) {
    if (group.conditions.length > 1) {
      group.conditions.splice(conditionIndex, 1)
    }
  }

  private openConditionEditor(groupIndex: number, conditionIndex: number) {
    const group = this.conditionGroups[groupIndex]
    const condition = group?.conditions[conditionIndex]
    if (!condition) return
    this.editingGroupIndex = groupIndex
    this.editingConditionIndex = conditionIndex
    this.editingCondition = JSON.parse(JSON.stringify(condition)) as AdvancedSearchConditionState
    this.sheetVisible = true
  }

  private onSheetConfirm(draft: AdvancedSearchConditionState) {
    const group = this.conditionGroups[this.editingGroupIndex]
    if (group && group.conditions[this.editingConditionIndex]) {
      // 组内唯一条件被清空成无效条件时，搜索校验仍会拦截，这里保持回写不拦截
      group.conditions.splice(this.editingConditionIndex, 1, draft)
    }
    this.editingGroupIndex = -1
    this.editingConditionIndex = -1
    this.editingCondition = null
    // 弹层自身也会发 update:visible(false)，这里兜底关闭避免状态悬挂
    this.sheetVisible = false
  }

  // ============ 次要操作（⋯ 菜单） ============

  private handleBarCommand(command: string) {
    switch (command) {
      case 'save-template':
        this.saveSearchTemplate()
        break
      case 'reset':
        this.resetConditions()
        break
      case 'preview':
        this.previewSearchQuery()
        break
    }
  }

  private saveSearchTemplate() {
    this.templateForm = {
      name: '',
      description: '',
      isDefault: false
    }
    this.saveTemplateVisible = true
  }

  private confirmSaveTemplate() {
    if (!this.templateForm.name.trim()) {
      this.$message.warning('请输入模板名称')
      return
    }
    void this.createTemplate()
  }

  private previewSearchQuery() {
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

  private async copyQueryToClipboard() {
    try {
      await navigator.clipboard.writeText(this.formattedQuery)
      this.$message.success('查询已复制到剪贴板')
    } catch (error) {
      this.$message.error('复制失败')
    }
  }

  // ============ 展示辅助 ============

  /** 模板禁直调模块级函数（同 torrent-detail 约定） */
  private conditionSummary(condition: AdvancedSearchConditionState): string {
    return describeCondition(condition) || '设置条件…'
  }

  private betweenLogicDesc(group: AdvancedSearchGroupState): string {
    return (group.betweenGroupLogic || 'and') === 'and'
      ? '并且与下一个条件组'
      : '或者与下一个条件组'
  }
}
</script>

<style scoped>
.m-adv-search {
  padding-bottom: 64px; /* 预留吸底操作条高度，避免末行被遮挡 */
}

/* 已保存搜索胶囊条 */
.m-adv-search__chips {
  display: flex;
  gap: 8px;
  padding: 2px 0 10px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.m-adv-search__chips::-webkit-scrollbar {
  display: none;
}

.m-adv-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
  height: 32px;
  padding: 0 14px;
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 16px;
}

.m-adv-chip.is-selected {
  color: var(--color-primary, #059669);
  background: var(--color-primary-lightest, #d1fae5);
  border-color: var(--color-primary, #059669);
}

.m-adv-chip--manage {
  width: 32px;
  justify-content: center;
  padding: 0;
  color: #909399;
}

/* 条件组卡片 */
.m-adv-group {
  margin-bottom: 10px;
  padding: 10px 12px;
  background: #fff;
  border-radius: 8px;
}

.m-adv-group__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.m-adv-group__name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  background: transparent;
  border: none;
}

.m-adv-group__name i {
  font-size: 13px;
  color: #c0c4cc;
}

.m-adv-group__name-input {
  width: 150px;
}

.m-adv-group__header-side {
  display: flex;
  align-items: center;
  gap: 6px;
}

.m-adv-group__more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  color: #909399;
  background: transparent;
  border: none;
}

/* 条件摘要卡 */
.m-adv-group__conditions {
  padding-top: 8px;
}

.m-adv-cond-card {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  margin-bottom: 8px;
  padding: 10px 12px;
  cursor: pointer;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.m-adv-cond-card__summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  color: #303133;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-adv-cond-card__summary.is-empty {
  color: #c0c4cc;
}

.m-adv-cond-card__remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  color: #909399;
  background: transparent;
  border: none;
}

.m-adv-cond-add {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  min-height: 40px;
  font-size: 13px;
  color: var(--color-primary, #059669);
  background: transparent;
  border: 1px dashed rgba(var(--color-primary-rgb, 5, 150, 105), 0.5);
  border-radius: 8px;
}

/* 组间逻辑 */
.m-adv-between {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  margin: 10px 0 2px;
}

.m-adv-between__desc {
  font-size: 11px;
  color: #92400e;
  white-space: normal;
}

/* 添加条件组 */
.m-adv-add-group {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  min-height: 42px;
  margin-bottom: 8px;
  font-size: 13px;
  color: #606266;
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
}

/* 吸底操作条：悬浮 Tab 栏上方（同返回顶部浮标 .m-backtop 的避让定位） */
.m-adv-bar {
  position: fixed;
  left: 12px;
  right: 12px;
  bottom: calc(80px + env(safe-area-inset-bottom));
  z-index: 9;
  display: flex;
  gap: 8px;
  padding: 6px;
  background: var(--glass-bg, rgba(255, 255, 255, 0.85));
  backdrop-filter: blur(var(--glass-blur, 12px));
  -webkit-backdrop-filter: blur(var(--glass-blur, 12px));
  border: var(--glass-border, 1px solid rgba(255, 255, 255, 0.3));
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--shadow-md, 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06));
}

@supports not (backdrop-filter: blur(12px)) {
  .m-adv-bar {
    background: var(--color-bg-primary, #ffffff);
    border: 1px solid var(--color-border-primary, #e5e7eb);
  }
}

.m-adv-bar__search {
  flex: 1;
  margin-left: 0;
  font-size: 15px;
  border-radius: 8px;
}

.m-adv-bar__more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  font-size: 18px;
  color: #606266;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
}
</style>

<style>
/* 挂 body 的弹层/抽屉（append-to-body），scoped 够不到：核心样式走全局 */
.m-adv-manage {
  border-radius: 16px 16px 0 0;
  background: #fff;
}

.m-adv-manage__body {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 8px 16px calc(16px + env(safe-area-inset-bottom));
}

.m-adv-manage__grabber {
  align-self: center;
  width: 36px;
  height: 4px;
  margin-bottom: 8px;
  border-radius: 2px;
  background: #e4e7ed;
}

.m-adv-manage__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.m-adv-manage__title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.m-adv-manage__list {
  flex: 1;
  min-height: 120px;
  overflow-y: auto;
}

.m-adv-manage__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  margin: 2px 0;
  padding: 10px 10px;
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
}

.m-adv-manage__item.is-selected {
  color: var(--color-primary, #059669);
  background: var(--color-primary-lightest, #d1fae5);
  border-color: var(--color-primary, #059669);
}

.m-adv-manage__name {
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-adv-manage__item .m-adv-manage__name {
  color: inherit;
}

.m-adv-manage__meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: #909399;
}

.m-adv-manage__item.is-selected .m-adv-manage__meta {
  color: inherit;
  opacity: 0.75;
}

.m-adv-manage__empty {
  padding: 24px 0;
  font-size: 12px;
  color: #909399;
  text-align: center;
}

.m-adv-manage__footer {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
}

.m-adv-manage__footer .el-button {
  flex: 1;
  margin-left: 0;
}

.m-adv-manage__trigger {
  flex: 1;
  min-width: 0;
}

.m-adv-preview {
  max-height: 50vh;
  padding: 12px;
  overflow-y: auto;
  font-family: 'Courier New', Monaco, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #1e293b;
  word-break: break-all;
  white-space: pre-wrap;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
</style>
