<template>
  <div class="query-templates-container">
    <!-- 工具栏 -->
    <div class="filter-container">
      <el-input
        v-model="listQuery.name"
        placeholder="搜索模板名称"
        style="width: 220px"
        class="filter-item"
        clearable
        @keyup.enter.native="handleFilter"
        @clear="handleFilter"
      />
      <el-select
        v-model="listQuery.source"
        placeholder="模板类型"
        clearable
        class="filter-item"
        style="width: 140px"
        @change="handleFilter"
      >
        <el-option label="全部" value="" />
        <el-option label="简单查询" value="simple" />
        <el-option label="高级搜索" value="advanced" />
      </el-select>
      <el-button class="filter-item" type="primary" icon="el-icon-search" @click="handleFilter">
        搜索
      </el-button>
      <el-button class="filter-item" style="margin-left: 10px" type="success" icon="el-icon-plus" @click="handleCreate">
        新建模板
      </el-button>
      <el-button class="filter-item" icon="el-icon-refresh" @click="getList">
        刷新
      </el-button>
    </div>

    <!-- 模板列表 -->
    <el-table
      v-loading="listLoading"
      :data="filteredList"
      border
      fit
      highlight-current-row
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
      <el-table-column label="操作" width="240" align="center" fixed="right">
        <template slot-scope="scope">
          <el-button type="primary" size="mini" icon="el-icon-video-play" @click="handleApply(scope.row)">
            应用
          </el-button>
          <el-button
            size="mini"
            icon="el-icon-edit"
            :disabled="scope.row.is_default"
            @click="handleEdit(scope.row)"
          >
            编辑
          </el-button>
          <el-button
            type="danger"
            size="mini"
            icon="el-icon-delete"
            :disabled="scope.row.is_default"
            @click="handleDelete(scope.row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

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
import {
  getSearchTemplates,
  deleteSearchTemplate,
  SearchTemplate
} from '@/api/torrents'

@Component({
  name: 'QueryTemplates',
  components: { QueryTemplateDialog }
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
.query-templates-container {
  padding: 20px;

  .filter-container {
    margin-bottom: 20px;

    .filter-item {
      margin-right: 10px;
    }
  }
}
</style>
