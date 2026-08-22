<template>
  <div class="app-container management-page query-templates-page">
    <header class="management-page__header" aria-labelledby="query-templates-title">
      <div class="management-page__heading">
        <h1 id="query-templates-title" class="management-page__title">查询模板</h1>
        <p class="management-page__subtitle">集中管理并复用常用的简单查询与高级搜索条件</p>
      </div>
      <div class="management-page__actions">
        <el-button
          icon="el-icon-refresh"
          :loading="listLoading"
          @click="getList"
        >
          刷新
        </el-button>
        <el-button type="primary" icon="el-icon-plus" @click="handleCreate">
          新建模板
        </el-button>
      </div>
    </header>

    <!-- 筛选条件 -->
    <section class="management-panel" aria-label="查询模板筛选条件">
      <div class="management-filter">
        <div class="management-filter__field management-filter__field--wide">
          <label class="management-filter__label" for="query-template-name">模板名称</label>
          <el-input
            id="query-template-name"
            v-model="listQuery.name"
            class="management-filter__control"
            placeholder="输入模板名称"
            prefix-icon="el-icon-search"
            clearable
            @keyup.enter.native="handleFilter"
            @clear="handleFilter"
          />
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="query-template-source">模板类型</label>
          <el-select
            id="query-template-source"
            v-model="listQuery.source"
            class="management-filter__control"
            placeholder="全部类型"
            clearable
            @change="handleFilter"
          >
            <el-option label="全部" value="" />
            <el-option label="简单查询" value="simple" />
            <el-option label="高级搜索" value="advanced" />
          </el-select>
        </div>
        <div class="management-filter__actions">
          <el-button type="primary" icon="el-icon-search" @click="handleFilter">
            搜索
          </el-button>
        </div>
      </div>
    </section>

    <!-- 模板列表 -->
    <section class="management-panel" aria-labelledby="query-template-list-title">
      <div class="management-panel__header">
        <div class="management-panel__heading">
          <h2 id="query-template-list-title" class="management-panel__title">模板列表</h2>
          <p class="management-panel__description">系统模板仅可应用，个人模板可以编辑或删除</p>
        </div>
        <div class="management-panel__meta">
          <el-tag type="info" effect="plain">共 {{ filteredList.length }} 个模板</el-tag>
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
          empty-text="暂无查询模板"
          style="width: 100%"
        >
          <el-table-column label="模板名称" prop="name" min-width="140" show-overflow-tooltip />
          <el-table-column label="描述" prop="description" min-width="200" show-overflow-tooltip>
            <template slot-scope="scope">
              {{ scope.row.description || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100" align="center">
            <template slot-scope="scope">
              <el-tag :type="getConditionsSource(scope.row) === 'simple' ? '' : 'success'" size="small">
                {{ getConditionsSource(scope.row) === 'simple' ? '简单查询' : '高级搜索' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="90" align="center">
            <template slot-scope="scope">
              <el-tag v-if="scope.row.is_default" type="warning" size="small">系统</el-tag>
              <el-tag v-else-if="scope.row.is_public" type="info" size="small">公开</el-tag>
              <el-tag v-else type="info" size="small" effect="plain">私有</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="使用次数" prop="usage_count" width="90" align="center" />
          <el-table-column label="创建时间" width="160" align="center">
            <template slot-scope="scope">
              {{ formatTime(scope.row.created_time) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="138" align="center" fixed="right">
            <template slot-scope="scope">
              <div class="template-row-actions">
                <el-tooltip content="应用模板" placement="top" :open-delay="200">
                  <span class="template-action-trigger">
                    <el-button
                      type="text"
                      class="template-action-btn template-action-btn--apply"
                      aria-label="应用模板"
                      @click="handleApply(scope.row)"
                    >
                      <LucideIcon name="play" :size="15" />
                    </el-button>
                  </span>
                </el-tooltip>
                <el-tooltip
                  :content="scope.row.is_default ? '系统模板不可编辑' : '编辑模板'"
                  placement="top"
                  :open-delay="200"
                >
                  <span class="template-action-trigger">
                    <el-button
                      type="text"
                      class="template-action-btn"
                      :aria-label="scope.row.is_default ? '系统模板不可编辑' : '编辑模板'"
                      :disabled="scope.row.is_default"
                      @click="handleEdit(scope.row)"
                    >
                      <LucideIcon name="pencil" :size="15" />
                    </el-button>
                  </span>
                </el-tooltip>
                <el-tooltip
                  :content="scope.row.is_default ? '系统模板不可删除' : '删除模板'"
                  placement="top"
                  :open-delay="200"
                >
                  <span class="template-action-trigger">
                    <el-button
                      type="text"
                      class="template-action-btn template-action-btn--delete"
                      :aria-label="scope.row.is_default ? '系统模板不可删除' : '删除模板'"
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

  private async getList() {
    this.listLoading = true
    try {
      const response = await getSearchTemplates({ is_public: true })
      if (response.code === '200') {
        // response.data 可能是数组或 {list: [...]}
        const data = response.data as any
        this.list = Array.isArray(data) ? data : (data?.list || [])
      } else {
        this.$message.error(response.msg || '获取模板列表失败')
      }
    } catch (error) {
      this.$message.error('获取模板列表失败：' + (error as Error).message)
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
      return new Date(time).toLocaleString('zh-CN', { hour12: false })
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
      await this.$confirm(`确认删除模板 "${row.name}" 吗？`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
      const response = await deleteSearchTemplate(row.id)
      if (response.code === '200') {
        this.$message.success('删除成功')
        this.getList()
      } else {
        this.$message.error(response.msg || '删除失败')
      }
    } catch (error) {
      // 用户取消或删除失败
      if ((error as any)?.message) {
        this.$message.error('删除失败：' + (error as Error).message)
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
