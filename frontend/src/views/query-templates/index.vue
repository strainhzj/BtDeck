<template>
  <div class="app-container management-page query-templates-page">
    <header class="management-page__header" aria-labelledby="query-templates-title">
      <div class="management-page__heading">
        <h1 id="query-templates-title" class="management-page__title">{{ $t('queryTemplate.list.title') }}</h1>
        <p class="management-page__subtitle">{{ $t('queryTemplate.list.subtitle') }}</p>
      </div>
      <div class="management-page__actions">
        <el-button
          icon="el-icon-refresh"
          :loading="listLoading"
          @click="getList"
        >
          {{ $t('common.refresh') }}
        </el-button>
        <el-button type="primary" icon="el-icon-plus" @click="handleCreate">
          {{ $t('queryTemplate.list.create') }}
        </el-button>
      </div>
    </header>

    <!-- 筛选条件 -->
    <section class="management-panel" :aria-label="$t('queryTemplate.list.filterAria')">
      <div class="management-filter">
        <div class="management-filter__field management-filter__field--wide">
          <label class="management-filter__label" for="query-template-name">{{ $t('queryTemplate.list.nameLabel') }}</label>
          <el-input
            id="query-template-name"
            v-model="listQuery.name"
            class="management-filter__control"
            :placeholder="$t('queryTemplate.list.namePlaceholder')"
            prefix-icon="el-icon-search"
            clearable
            @keyup.enter.native="handleFilter"
            @clear="handleFilter"
          />
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="query-template-source">{{ $t('queryTemplate.list.sourceLabel') }}</label>
          <el-select
            id="query-template-source"
            v-model="listQuery.source"
            class="management-filter__control"
            :placeholder="$t('queryTemplate.list.sourcePlaceholder')"
            clearable
            @change="handleFilter"
          >
            <el-option :label="$t('queryTemplate.list.sourceAll')" value="" />
            <el-option :label="$t('queryTemplate.list.simple')" value="simple" />
            <el-option :label="$t('queryTemplate.list.advanced')" value="advanced" />
          </el-select>
        </div>
        <div class="management-filter__actions">
          <el-button type="primary" icon="el-icon-search" @click="handleFilter">
            {{ $t('queryTemplate.list.search') }}
          </el-button>
        </div>
      </div>
    </section>

    <!-- 模板列表 -->
    <section class="management-panel" aria-labelledby="query-template-list-title">
      <div class="management-panel__header">
        <div class="management-panel__heading">
          <h2 id="query-template-list-title" class="management-panel__title">{{ $t('queryTemplate.list.listTitle') }}</h2>
          <p class="management-panel__description">{{ $t('queryTemplate.list.listDesc') }}</p>
        </div>
        <div class="management-panel__meta">
          <el-tag type="info" effect="plain">{{ $t('queryTemplate.list.countTag', {count: filteredList.length}) }}</el-tag>
        </div>
      </div>
      <div class="management-table-scroll">
        <el-table
          v-loading="listLoading"
          :data="filteredList"
          class="management-table"
          border
          fit
          highlight-current-row
          :empty-text="$t('queryTemplate.list.empty')"
          style="width: 100%"
        >
          <el-table-column :label="$t('queryTemplate.list.colName')" min-width="140" show-overflow-tooltip>
            <template slot-scope="scope">
              {{ displayPresetName(scope.row) }}
            </template>
          </el-table-column>
          <el-table-column :label="$t('queryTemplate.list.colDesc')" min-width="200" show-overflow-tooltip>
            <template slot-scope="scope">
              {{ displayPresetDescription(scope.row) || '-' }}
            </template>
          </el-table-column>
          <el-table-column :label="$t('queryTemplate.list.colType')" width="100" align="center">
            <template slot-scope="scope">
              <el-tag :type="getConditionsSource(scope.row) === 'simple' ? '' : 'success'" size="small">
                {{ getConditionsSource(scope.row) === 'simple' ? $t('queryTemplate.list.simple') : $t('queryTemplate.list.advanced') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('queryTemplate.list.colSource')" width="90" align="center">
            <template slot-scope="scope">
              <el-tag v-if="scope.row.is_default" type="warning" size="small">{{ $t('queryTemplate.list.tagSystem') }}</el-tag>
              <el-tag v-else-if="scope.row.is_public" type="info" size="small">{{ $t('queryTemplate.list.tagPublic') }}</el-tag>
              <el-tag v-else type="info" size="small" effect="plain">{{ $t('queryTemplate.list.tagPrivate') }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('queryTemplate.list.colUsage')" prop="usage_count" width="90" align="center" />
          <el-table-column :label="$t('queryTemplate.list.colCreated')" width="160" align="center">
            <template slot-scope="scope">
              {{ formatTime(scope.row.created_time) }}
            </template>
          </el-table-column>
          <el-table-column :label="$t('queryTemplate.list.colActions')" width="138" align="center" fixed="right">
            <template slot-scope="scope">
              <div class="template-row-actions">
                <el-tooltip :content="$t('queryTemplate.list.applyTip')" placement="top" :open-delay="200">
                  <span class="template-action-trigger">
                    <el-button
                      type="text"
                      class="template-action-btn template-action-btn--apply"
                      :aria-label="$t('queryTemplate.list.applyTip')"
                      @click="handleApply(scope.row)"
                    >
                      <LucideIcon name="play" :size="15" />
                    </el-button>
                  </span>
                </el-tooltip>
                <el-tooltip
                  :content="scope.row.is_default ? $t('queryTemplate.list.editDisabled') : $t('queryTemplate.list.editTip')"
                  placement="top"
                  :open-delay="200"
                >
                  <span class="template-action-trigger">
                    <el-button
                      type="text"
                      class="template-action-btn"
                      :aria-label="scope.row.is_default ? $t('queryTemplate.list.editDisabled') : $t('queryTemplate.list.editTip')"
                      :disabled="scope.row.is_default"
                      @click="handleEdit(scope.row)"
                    >
                      <LucideIcon name="pencil" :size="15" />
                    </el-button>
                  </span>
                </el-tooltip>
                <el-tooltip
                  :content="scope.row.is_default ? $t('queryTemplate.list.deleteDisabled') : $t('queryTemplate.list.deleteTip')"
                  placement="top"
                  :open-delay="200"
                >
                  <span class="template-action-trigger">
                    <el-button
                      type="text"
                      class="template-action-btn template-action-btn--delete"
                      :aria-label="scope.row.is_default ? $t('queryTemplate.list.deleteDisabled') : $t('queryTemplate.list.deleteTip')"
                      :disabled="scope.row.is_default"
                      @click="handleDelete(scope.row)"
                    >
                      <LucideIcon name="trash" :size="15" />
                    </el-button>
                  </span>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- 创建/编辑对话框 -->
    <query-template-dialog
      :visible.sync="dialogVisible"
      :template="editingTemplate"
      @success="handleDialogSuccess"
    />
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import QueryTemplateDialog from './components/QueryTemplateDialog.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'
import {
  getSearchTemplates,
  deleteSearchTemplate,
  SearchTemplate
} from '@/api/torrents'
import { getLocale } from '@/i18n'
import { presetDisplayDescription, presetDisplayName } from '@/components/torrents/advancedSearchFields'

@Component({
  name: 'QueryTemplates',
  components: { QueryTemplateDialog, LucideIcon }
})
export default class QueryTemplates extends Vue {
  private list: SearchTemplate[] = []
  private listLoading = false
  private listQuery = {
    name: '',
    source: ''
  }
  private dialogVisible = false
  private editingTemplate: SearchTemplate | null = null

  mounted() {
    this.getList()
  }

  get filteredList(): SearchTemplate[] {
    return this.list.filter(item => {
      // 名称过滤
      if (this.listQuery.name && !item.name.includes(this.listQuery.name)) {
        return false
      }
      // 类型过滤
      if (this.listQuery.source) {
        const source = this.getConditionsSource(item)
        if (source !== this.listQuery.source) {
          return false
        }
      }
      return true
    })
  }

  /** 名称列展示：系统预设按 preset_key 本地化，未识别保留原文（Q01/Q02） */
  private displayPresetName(row: SearchTemplate): string {
    return presetDisplayName(row)
  }

  /** 描述列展示：系统预设按 preset_key 本地化，未识别保留原文（无描述回退占位） */
  private displayPresetDescription(row: SearchTemplate): string {
    return presetDisplayDescription(row)
  }

  private async getList() {
    this.listLoading = true
    try {
      const response = await getSearchTemplates({ is_public: true })
      if (response.code === '200') {
        // response.data 可能是数组或 {list: [...]}
        const data = response.data as any
        this.list = Array.isArray(data) ? data : (data?.list || [])
      } else {
        this.$message.error(response.msg || this.$t('queryTemplate.list.loadFailed'))
      }
    } catch (error) {
      this.$message.error(
        this.$t('queryTemplate.list.loadFailedWith', { message: (error as Error).message })
      )
    } finally {
      this.listLoading = false
    }
  }

  private handleFilter() {
    // 前端过滤，filteredQuery 自动响应
  }

  private getConditionsSource(row: SearchTemplate): string {
    const conditions = row.conditions as any
    return conditions?.source || 'simple'
  }

  private formatTime(time: string): string {
    if (!time) return '-'
    try {
      return new Date(time).toLocaleString(getLocale() === 'en' ? 'en-US' : 'zh-CN', { hour12: false })
    } catch {
      return time
    }
  }

  private handleCreate() {
    this.editingTemplate = null
    this.dialogVisible = true
  }

  private handleEdit(row: SearchTemplate) {
    this.editingTemplate = row
    this.dialogVisible = true
  }

  private handleDialogSuccess() {
    this.dialogVisible = false
    this.getList()
  }

  private async handleApply(row: SearchTemplate) {
    // 应用模板：跳转到种子列表，并通过 query 传递模板 id
    // 实际应用逻辑在 torrents/index.vue 的 applyQueryTemplate 中实现
    this.$router.push({
      path: '/torrents/index',
      query: { apply_template_id: row.id }
    })
  }

  private async handleDelete(row: SearchTemplate) {
    try {
      await this.$confirm(
        this.$t('queryTemplate.list.confirmDelete', { name: row.name }).toString(),
        this.$t('queryTemplate.list.confirmTitle').toString(),
        {
          confirmButtonText: this.$t('queryTemplate.list.confirmOk').toString(),
          cancelButtonText: this.$t('common.cancel').toString(),
          type: 'warning'
        }
      )
      const response = await deleteSearchTemplate(row.id)
      if (response.code === '200') {
        this.$message.success(this.$t('queryTemplate.list.deleteOk'))
        this.getList()
      } else {
        this.$message.error(response.msg || this.$t('queryTemplate.list.deleteFailed'))
      }
    } catch (error) {
      // 用户取消或删除失败
      if ((error as any)?.message) {
        this.$message.error(
          this.$t('queryTemplate.list.deleteFailedWith', { message: (error as Error).message })
        )
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.template-row-actions {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.template-action-trigger {
  display: inline-flex;
}

.template-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--color-text-tertiary);
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background-color var(--transition-fast);

  &:hover:not(.is-disabled),
  &:focus-visible:not(.is-disabled) {
    color: var(--color-primary);
    background: var(--color-primary-lightest);
  }

  &--apply {
    color: var(--color-primary);
  }

  &--delete:hover:not(.is-disabled),
  &--delete:focus-visible:not(.is-disabled) {
    color: var(--color-error);
    background: var(--color-error-lightest, #fef2f2);
  }
}
</style>
