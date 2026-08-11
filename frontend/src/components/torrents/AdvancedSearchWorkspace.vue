<template>
  <div class="advanced-search-workspace">
    <aside class="saved-search-sidebar" aria-label="已保存高级搜索">
      <div class="saved-search-sidebar__header">
        <div class="saved-search-sidebar__heading">
          <LucideIcon name="layout-template" :size="16" />
          <span>已保存搜索</span>
          <span class="saved-search-sidebar__count">{{ advancedTemplates.length }}</span>
        </div>
        <div class="saved-search-sidebar__header-actions">
          <el-tooltip content="新建搜索配置" placement="top" :open-delay="200">
            <el-button
              type="text"
              class="saved-search-icon-btn"
              aria-label="新建搜索配置"
              @click="startNewSearch"
            >
              <LucideIcon name="plus" :size="15" />
            </el-button>
          </el-tooltip>
          <el-tooltip content="刷新已保存搜索" placement="top" :open-delay="200">
            <el-button
              type="text"
              class="saved-search-icon-btn"
              :loading="templatesLoading"
              aria-label="刷新已保存搜索"
              @click="loadSavedSearches"
            >
              <LucideIcon name="refresh-cw" :size="14" />
            </el-button>
          </el-tooltip>
        </div>
      </div>

      <el-input
        v-model="templateKeyword"
        class="saved-search-sidebar__filter"
        size="small"
        prefix-icon="el-icon-search"
        placeholder="筛选已保存搜索"
        clearable
      />

      <div v-loading="templatesLoading" class="saved-search-list">
        <button
          v-for="template in filteredTemplates"
          :key="template.id"
          type="button"
          class="saved-search-item"
          :class="{'is-selected': template.id === selectedTemplateId}"
          :aria-pressed="template.id === selectedTemplateId ? 'true' : 'false'"
          @click="selectTemplate(template)"
        >
          <span class="saved-search-item__icon" aria-hidden="true">
            <LucideIcon name="list-filter" :size="15" />
          </span>
          <span class="saved-search-item__content">
            <span class="saved-search-item__name" :title="template.name">{{ template.name }}</span>
            <span class="saved-search-item__meta">
              <span v-if="template.is_default">系统</span>
              <span v-else-if="template.is_public">公开</span>
              <span v-else>个人</span>
              <span>使用 {{ template.usage_count || 0 }} 次</span>
            </span>
          </span>
          <LucideIcon class="saved-search-item__chevron" name="chevron-right" :size="14" />
        </button>

        <div v-if="!templatesLoading && filteredTemplates.length === 0" class="saved-search-empty">
          <LucideIcon name="search-x" :size="24" />
          <span>{{ templateKeyword ? '没有匹配的已保存搜索' : '暂无已保存高级搜索' }}</span>
        </div>
      </div>

      <div class="saved-search-sidebar__footer">
        <el-tooltip :content="selectedManageHint" placement="top" :open-delay="200">
          <span class="saved-search-action-trigger">
            <el-button
              size="mini"
              type="primary"
              plain
              :disabled="!canManageSelected"
              :loading="templateActionLoading"
              @click="updateSelectedTemplate"
            >
              <LucideIcon name="save" :size="14" />
              <span>保存更改</span>
            </el-button>
          </span>
        </el-tooltip>
        <el-tooltip :content="selectedDeleteHint" placement="top" :open-delay="200">
          <span class="saved-search-action-trigger">
            <el-button
              size="mini"
              :disabled="!canManageSelected"
              :loading="templateActionLoading"
              @click="deleteSelectedTemplate"
            >
              <LucideIcon name="trash" :size="14" />
              <span>删除</span>
            </el-button>
          </span>
        </el-tooltip>
      </div>
    </aside>

    <section class="advanced-search-workspace__builder" aria-label="高级搜索条件配置">
      <AdvancedSearchBuilder
        ref="builder"
        :searching="searching"
        @search="$emit('search', $event)"
        @reset="$emit('reset')"
        @save-template="createTemplate"
      />
    </section>
  </div>
</template>

<script lang="ts">
import { Component, Prop, Vue } from 'vue-property-decorator'
import AdvancedSearchBuilder from './AdvancedSearchBuilder.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'
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
import type {
  AdvancedSearchGroupState,
  AdvancedSearchTemplateDraft
} from './advancedSearchState'

interface AdvancedSearchBuilderRef extends Vue {
  refreshFieldOptions(): void
  applyTemplateGroups(
    groups: AdvancedSearchGroupState[],
    options?: { sort_by?: string, sort_order?: string }
  ): void
  resetConditions(): void
  onSearch(): void
  getTemplateGroupsSnapshot(): AdvancedSearchGroupState[]
}

@Component({
  name: 'AdvancedSearchWorkspace',
  components: {
    AdvancedSearchBuilder,
    LucideIcon
  }
})
export default class AdvancedSearchWorkspace extends Vue {
  @Prop({ type: Boolean, default: false }) readonly searching!: boolean
  @Prop({ type: String, default: 'added_date' }) readonly sortBy!: string
  @Prop({ type: String, default: 'desc' }) readonly sortOrder!: 'asc' | 'desc'

  private advancedTemplates: SearchTemplate[] = []
  private selectedTemplateId = ''
  private templateKeyword = ''
  private templatesLoading = false
  private templateActionLoading = false
  private templateRequestSequence = 0

  mounted() {
    void this.loadSavedSearches()
  }

  get filteredTemplates(): SearchTemplate[] {
    const keyword = this.templateKeyword.trim().toLocaleLowerCase()
    if (!keyword) return this.advancedTemplates
    return this.advancedTemplates.filter(template => (
      template.name.toLocaleLowerCase().includes(keyword) ||
      (template.description || '').toLocaleLowerCase().includes(keyword)
    ))
  }

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

  private get builder(): AdvancedSearchBuilderRef | undefined {
    return this.$refs.builder as AdvancedSearchBuilderRef | undefined
  }

  /** 父对话框每次打开时调用：刷新字段候选和已保存搜索。 */
  public refreshFieldOptions() {
    this.builder?.refreshFieldOptions()
    void this.loadSavedSearches()
  }

  /** 保持与 AdvancedSearchBuilder 相同的公开入口，兼容路由模板应用。 */
  public applyTemplateGroups(
    groups: AdvancedSearchGroupState[],
    options?: { sort_by?: string, sort_order?: string }
  ) {
    this.builder?.applyTemplateGroups(groups, options)
  }

  public resetConditions() {
    this.builder?.resetConditions()
  }

  public onSearch() {
    this.builder?.onSearch()
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

  private selectTemplate(template: SearchTemplate) {
    const groups = template.conditions.condition_groups
    if (!groups || groups.length === 0) {
      this.$message.warning('该搜索配置没有有效的高级搜索条件')
      return
    }

    try {
      this.builder?.applyTemplateGroups(groups, {
        sort_by: template.conditions.sort_by,
        sort_order: template.conditions.sort_order
      })
      this.selectedTemplateId = template.id
      this.$emit('template-loaded', template.conditions)
    } catch (error) {
      this.$message.error(extractErrorMessage(error) || '加载搜索配置失败')
    }
  }

  private startNewSearch() {
    this.selectedTemplateId = ''
    this.builder?.resetConditions()
  }

  private buildTemplateConditions(groups: AdvancedSearchGroupState[]): QueryTemplateConditions {
    return {
      source: 'advanced',
      version: 1,
      condition_groups: groups,
      sort_by: this.sortBy || 'added_date',
      sort_order: this.sortOrder || 'desc'
    }
  }

  private async createTemplate(draft: AdvancedSearchTemplateDraft) {
    const message = this.$message
    const conditions = this.buildTemplateConditions(draft.conditions || [])
    this.templateActionLoading = true
    try {
      const response = await createSearchTemplate({
        name: draft.name,
        description: draft.description,
        conditions,
        is_public: false
      })
      if (response.code !== '200') {
        message.error(response.msg || '模板保存失败')
        return
      }
      this.selectedTemplateId = response.data.id
      await this.loadSavedSearches()
      message.success('模板保存成功')
    } catch (error) {
      message.error(extractErrorMessage(error) || '模板保存失败')
    } finally {
      this.templateActionLoading = false
    }
  }

  private async updateSelectedTemplate() {
    const template = this.selectedTemplate
    const builder = this.builder
    if (!template || !this.canManageSelected || !builder) return

    let groups: AdvancedSearchGroupState[]
    try {
      groups = builder.getTemplateGroupsSnapshot()
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
}
</script>

<style lang="scss" scoped>
.advanced-search-workspace {
  display: flex;
  align-items: stretch;
  gap: var(--spacing-md, 12px);
  min-height: 480px;
}

.saved-search-sidebar {
  display: flex;
  flex: 0 0 238px;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg, 8px);
}

.saved-search-sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 46px;
  padding: 0 var(--spacing-sm, 8px) 0 var(--spacing-md, 12px);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-primary);
}

.saved-search-sidebar__heading,
.saved-search-sidebar__header-actions,
.saved-search-sidebar__footer,
.saved-search-action-trigger,
.saved-search-item__meta {
  display: flex;
  align-items: center;
}

.saved-search-sidebar__heading {
  min-width: 0;
  gap: 7px;
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: var(--font-weight-semibold, 600);
}

.saved-search-sidebar__count {
  min-width: 20px;
  padding: 1px 6px;
  color: var(--color-text-tertiary);
  font-size: 11px;
  font-weight: var(--font-weight-medium, 500);
  text-align: center;
  background: var(--color-bg-tertiary);
  border-radius: 999px;
}

.saved-search-sidebar__header-actions {
  gap: 2px;
}

.saved-search-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  color: var(--color-text-tertiary);
  border-radius: var(--radius-sm, 4px);

  &:hover,
  &:focus-visible {
    color: var(--color-primary);
    background: var(--color-primary-lightest);
  }
}

.saved-search-sidebar__filter {
  width: auto;
  margin: var(--spacing-sm, 8px);
}

.saved-search-list {
  flex: 1;
  min-height: 250px;
  padding: 0 var(--spacing-xs, 4px) var(--spacing-sm, 8px);
  overflow-y: auto;
}

.saved-search-item {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 52px;
  margin: 2px 0;
  padding: 7px 8px;
  color: var(--color-text-primary);
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  transition: all var(--transition-fast, 150ms);

  &:hover,
  &:focus-visible {
    background: var(--color-bg-primary);
    border-color: var(--color-border-secondary);
    outline: none;
  }

  &.is-selected {
    color: var(--color-primary);
    background: var(--color-primary-lightest);
    border-color: var(--color-primary);
  }
}

.saved-search-item__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  margin-right: 7px;
  color: var(--color-primary);
  background: var(--color-bg-primary);
  border-radius: var(--radius-md, 6px);
}

.saved-search-item__content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  gap: 4px;
}

.saved-search-item__name {
  overflow: hidden;
  font-size: 12px;
  font-weight: var(--font-weight-semibold, 600);
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.saved-search-item__meta {
  gap: 8px;
  color: var(--color-text-tertiary);
  font-size: 10px;
}

.saved-search-item__chevron {
  margin-left: 4px;
  color: var(--color-text-quaternary);
}

.saved-search-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: var(--spacing-sm, 8px);
  min-height: 180px;
  padding: var(--spacing-md, 12px);
  color: var(--color-text-tertiary);
  font-size: 12px;
  text-align: center;
}

.saved-search-sidebar__footer {
  justify-content: space-between;
  gap: var(--spacing-xs, 4px);
  padding: var(--spacing-sm, 8px);
  background: var(--color-bg-primary);
  border-top: 1px solid var(--color-border-primary);

  .el-button {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-left: 0;
  }
}

.saved-search-action-trigger {
  min-width: 0;
}

.advanced-search-workspace__builder {
  flex: 1;
  min-width: 0;
  padding: 2px;
  overflow: auto;
}

@media (max-width: 900px) {
  .advanced-search-workspace {
    flex-direction: column;
  }

  .saved-search-sidebar {
    flex-basis: auto;
    max-height: 260px;
  }

  .saved-search-list {
    min-height: 120px;
  }
}
</style>
