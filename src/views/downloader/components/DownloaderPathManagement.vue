<template>
  <div class="downloader-path-management">
    <!-- 头部说明和操作区 -->
    <div class="tab-header">
      <div class="header-info">
        <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
        </svg>
        <div class="header-text">
          <h3 class="header-title">下载器路径管理</h3>
          <p class="header-desc">管理下载器的默认路径和在用路径，用于种子转移时选择目标路径</p>
        </div>
      </div>
      <div class="header-actions">
        <el-button
          type="success"
          size="medium"
          :loading="refreshing"
          @click="handleRefresh"
        >
          <svg v-if="!refreshing" class="button-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"></polyline>
            <polyline points="1 20 1 14 7 14"></polyline>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
          </svg>
          刷新路径
        </el-button>
        <el-button
          type="primary"
          size="medium"
          @click="handleAddPath"
        >
          <svg class="button-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          添加路径
        </el-button>
      </div>
    </div>

    <!-- 筛选区域 -->
    <div class="filter-section">
      <el-form :inline="true" size="small">
        <el-form-item label="路径类型:">
          <el-select
            v-model="filterType"
            placeholder="全部类型"
            clearable
            @change="handleFilterChange"
            style="width: 150px;"
          >
            <el-option label="默认路径" value="default" />
            <el-option label="在用路径" value="active" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态:">
          <el-select
            v-model="filterEnabled"
            placeholder="全部状态"
            clearable
            @change="handleFilterChange"
            style="width: 150px;"
          >
            <el-option label="已启用" :value="true" />
            <el-option label="已禁用" :value="false" />
          </el-select>
        </el-form-item>
      </el-form>
    </div>

    <!-- 路径表格 -->
    <div class="path-table-wrapper">
      <el-table
        :data="paths"
        :loading="loading"
        style="width: 100%"
        header-row-class-name="path-table-header"
        v-loading="loading"
      >
        <!-- 路径类型 -->
        <el-table-column label="路径类型" width="120">
          <template #default="{row}">
            <el-tag
              :type="row.path_type === 'default' ? 'primary' : 'success'"
              size="small"
            >
              {{ row.path_type === 'default' ? '默认路径' : '在用路径' }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 路径值 -->
        <el-table-column label="路径值" min-width="300">
          <template #default="{row}">
            <div class="path-value-cell">
              <svg class="path-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
              </svg>
              <span class="path-text" :title="row.path_value">{{ row.path_value }}</span>
            </div>
          </template>
        </el-table-column>

        <!-- 种子数量 -->
        <el-table-column label="种子数量" width="100" align="center">
          <template #default="{row}">
            <el-badge
              :value="row.torrent_count"
              :max="999"
              class="torrent-count-badge"
            />
          </template>
        </el-table-column>

        <!-- 状态 -->
        <el-table-column label="状态" width="80" align="center">
          <template #default="{row}">
            <el-switch
              v-model="row.is_enabled"
              @change="handleToggleEnabled(row)"
              :disabled="updating"
              active-color="#059669"
              inactive-color="#d1d5db"
            />
          </template>
        </el-table-column>

        <!-- 最后更新时间 -->
        <el-table-column label="最后更新" width="160">
          <template #default="{row}">
            <span class="time-text">{{ formatTime(row.last_updated_time) }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{row}">
            <el-button
              type="text"
              size="small"
              @click="handleEditPath(row)"
              :disabled="updating"
            >
              编辑
            </el-button>
            <el-button
              type="text"
              size="small"
              class="delete-button"
              @click="handleDeletePath(row)"
              :disabled="updating"
            >
              删除
            </el-button>
          </template>
        </el-table-column>

        <!-- 空状态 -->
        <template #empty>
          <div class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
            </svg>
            <p class="empty-text">暂无路径数据</p>
            <p class="empty-hint">点击"添加路径"按钮创建新路径</p>
          </div>
        </template>
      </el-table>
    </div>

    <!-- 添加/编辑路径对话框 -->
    <el-dialog
      :title="dialogMode === 'add' ? '添加路径' : '编辑路径'"
      :visible.sync="dialogVisible"
      width="500px"
      :before-close="handleDialogClose"
      :close-on-click-modal="false"
    >
      <el-form
        ref="pathFormRef"
        :model="formData"
        :rules="formRules"
        label-width="100px"
      >
        <el-form-item label="路径类型" prop="path_type">
          <el-select
            v-model="formData.path_type"
            placeholder="请选择路径类型"
            :disabled="dialogMode === 'edit'"
            style="width: 100%;"
          >
            <el-option label="默认路径" value="default" />
            <el-option label="在用路径" value="active" />
          </el-select>
          <div class="form-item-help">
            <svg class="help-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span>默认路径：下载器的默认保存路径；在用路径：种子任务使用的路径</span>
          </div>
        </el-form-item>

        <el-form-item label="路径值" prop="path_value">
          <el-input
            v-model="formData.path_value"
            placeholder="请输入绝对路径，如: /downloads 或 D:\Downloads"
            clearable
          />
          <div class="form-item-help">
            <svg class="help-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span>请输入下载器可访问的绝对路径</span>
          </div>
        </el-form-item>

        <el-form-item label="是否启用" prop="is_enabled">
          <el-switch
            v-model="formData.is_enabled"
            active-color="#059669"
            inactive-color="#d1d5db"
          />
          <div class="form-item-help">
            <svg class="help-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <span>禁用后，该路径将不会在种子转移时显示</span>
          </div>
        </el-form-item>
      </el-form>

      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ dialogMode === 'add' ? '添加' : '保存' }}
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import { Downloader } from '../types'
import {
  getDownloaderPaths,
  addDownloaderPath,
  updateDownloaderPath,
  deleteDownloaderPath
} from '@/api/downloader'

interface PathItem {
  id: number
  downloader_id: number
  path_type: string
  path_value: string
  is_enabled: boolean
  torrent_count: number
  last_updated_time: string | null
  created_at: string | null
  updated_at: string | null
}

@Component({
  name: 'DownloaderPathManagement'
})
export default class DownloaderPathManagement extends Vue {
  @Prop({ default: null }) downloader!: Downloader | null

  // 路径列表
  private paths: PathItem[] = []

  // 加载状态
  private loading = false
  private refreshing = false
  private updating = false
  private submitting = false

  // 筛选条件
  private filterType: string | null = null
  private filterEnabled: boolean | null = null

  // 对话框状态
  private dialogVisible = false
  private dialogMode: 'add' | 'edit' = 'add'
  private currentEditPath: PathItem | null = null

  // 表单数据
  private formData = {
    path_type: 'active',
    path_value: '',
    is_enabled: true
  }

  // 表单验证规则
  private formRules = {
    path_type: [
      { required: true, message: '请选择路径类型', trigger: 'change' }
    ],
    path_value: [
      { required: true, message: '请输入路径值', trigger: 'blur' },
      { min: 1, max: 500, message: '路径长度为1-500个字符', trigger: 'blur' }
    ]
  }

  // 获取表单引用
  get pathFormRef(): ElForm {
    return this.$refs.pathFormRef as ElForm
  }

  // 初始化
  mounted() {
    this.loadPaths()
  }

  // 加载路径列表
  private async loadPaths() {
    if (!this.downloader) {
      this.paths = []
      return
    }
    // 安全获取下载器ID
    const downloaderId = this.downloader?.id ?? this.downloader?.downloaderId
    if (!downloaderId) {
      this.$message.error("下载器信息不完整")
      this.paths = []
      return
    }

    this.loading = true

    try {
      const response = await getDownloaderPaths(
        downloaderId,
        this.filterType || undefined,
        this.filterEnabled || undefined
      )

      if (response.code === '200') {
        // 验证响应数据格式
        const data = response.data
        // 支持两种格式：直接数组 或 包含paths字段的对象
        let pathList: PathItem[] = []
        if (Array.isArray(data)) {
          pathList = data
        } else if (data && Array.isArray(data.paths)) {
          pathList = data.paths
        } else {
          this.paths = []
          console.warn('API返回的数据格式不正确,期望数组或包含paths字段的对象:', data)
          return
        }

        // 过滤并验证数据
        this.paths = pathList.filter(item =>
          item && typeof item.id === 'number' && typeof item.path_value === 'string'
        )
      } else {
        this.$message.error(response.msg || '加载路径列表失败')
      }
    } catch (error: any) {
      console.error('加载路径列表失败:', error)
      this.$message.error(error?.response?.data?.msg || error?.message || '加载路径列表失败')
    } finally {
      this.loading = false
    }
  }

  // 刷新路径列表
  private async handleRefresh() {
    this.refreshing = true
    try {
      await this.loadPaths()
      this.$message.success('刷新成功')
    } finally {
      this.refreshing = false
    }
  }

  // 筛选条件变化
  private handleFilterChange() {
    this.loadPaths()
  }

  // 添加路径
  private handleAddPath() {
    this.dialogMode = 'add'
    this.currentEditPath = null
    this.formData = {
      path_type: 'active',
      path_value: '',
      is_enabled: true
    }
    this.dialogVisible = true

    this.$nextTick(() => {
      if (this.pathFormRef) {
        this.pathFormRef.clearValidate()
      }
    })
  }

  // 编辑路径
  private handleEditPath(row: PathItem) {
    this.dialogMode = 'edit'
    this.currentEditPath = row
    this.formData = {
      path_type: row.path_type,
      path_value: row.path_value,
      is_enabled: row.is_enabled
    }
    this.dialogVisible = true

    this.$nextTick(() => {
      if (this.pathFormRef) {
        this.pathFormRef.clearValidate()
      }
    })
  }

  // 删除路径
  private async handleDeletePath(row: PathItem) {
    try {
      await this.$confirm(
        `确认删除路径"${row.path_value}"吗？删除后该路径将被禁用。`,
        '删除确认',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )

      // 安全获取下载器ID
      const downloaderId = this.downloader?.id ?? this.downloader?.downloaderId
      if (!downloaderId) {
        this.$message.error('下载器信息不完整')
        return
      }

      this.updating = true

      const response = await deleteDownloaderPath(
        downloaderId,
        row.id
      )

      if (response.code === '200') {
        this.$message.success('删除成功')
        await this.loadPaths()
      } else {
        this.$message.error(response.msg || '删除失败')
      }
    } catch (error: any) {
      if (error !== 'cancel') {
        console.error('删除路径失败:', error)
        this.$message.error(error?.response?.data?.msg || error?.message || '删除失败')
      }
    } finally {
      this.updating = false
    }
  }

  // 切换启用状态
  private async handleToggleEnabled(row: PathItem) {
// 保存原始状态用于恢复
    const originalState = !row.is_enabled

    // 安全获取下载器ID
    const downloaderId = this.downloader?.id ?? this.downloader?.downloaderId
    if (!downloaderId) {
      this.$message.error('下载器信息不完整')
      row.is_enabled = originalState
      return
    }

    this.updating = true

    try {
      const response = await updateDownloaderPath(
        downloaderId,
        row.id,
        {
          is_enabled: row.is_enabled
        }
      )

      if (response.code === '200') {
        this.$message.success(row.is_enabled ? '已启用' : '已禁用')
        await this.loadPaths()
      } else {
        // 恢复原状态
        row.is_enabled = originalState
        this.$message.error(response.msg || '操作失败')
      }
    } catch (error: any) {
      // 恢复原状态
      row.is_enabled = originalState
      console.error('切换状态失败:', error)
      this.$message.error(error?.response?.data?.msg || error?.message || '操作失败')
    } finally {
      this.updating = false
    }
  }

  // 提交表单
  private async handleSubmit() {
    try {
      await this.pathFormRef.validate()

      // 安全获取下载器ID
      const downloaderId = this.downloader?.id ?? this.downloader?.downloaderId
      if (!downloaderId) {
        this.$message.error('下载器信息不完整')
        return
      }

      this.submitting = true

      if (this.dialogMode === 'add') {
        // 添加路径
        const response = await addDownloaderPath(
          downloaderId,
          this.formData
        )

        if (response.code === '200') {
          this.$message.success('添加成功')
          this.dialogVisible = false
          await this.loadPaths()
        } else {
          this.$message.error(response.msg || '添加失败')
        }
      } else {
        // 编辑路径
        if (!this.currentEditPath) {
          this.$message.error('未选择要编辑的路径')
          return
        }

        const response = await updateDownloaderPath(
          downloaderId,
          this.currentEditPath.id,
          {
            path_value: this.formData.path_value,
            is_enabled: this.formData.is_enabled
          }
        )

        if (response.code === '200') {
          this.$message.success('保存成功')
          this.dialogVisible = false
          await this.loadPaths()
        } else {
          this.$message.error(response.msg || '保存失败')
        }
      }
    } catch (error: any) {
      console.error('提交失败:', error)
      this.$message.error(error?.response?.data?.msg || error?.message || '操作失败')
    } finally {
      this.submitting = false
    }
  }

  // 关闭对话框
  private handleDialogClose(done: Function) {
    if (this.submitting) {
      return
    }
    done()
  }

  // 格式化时间 (修复P2问题: 改进Invalid Date处理)
  private formatTime(timeStr: string | null): string {
    if (!timeStr) return '-'

    const date = new Date(timeStr)

    // 验证日期是否有效
    if (isNaN(date.getTime())) {
      return '-'
    }

    const now = new Date()
    const diff = now.getTime() - date.getTime()

    // 验证时间差是否有效
    if (isNaN(diff)) {
      return '-'
    }

    // 小于1小时
    if (diff < 3600000) {
      const minutes = Math.floor(diff / 60000)
      return minutes < 1 ? '刚刚' : `${minutes}分钟前`
    }

    // 小于24小时
    if (diff < 86400000) {
      const hours = Math.floor(diff / 3600000)
      return `${hours}小时前`
    }

    // 小于7天
    if (diff < 604800000) {
      const days = Math.floor(diff / 86400000)
      return `${days}天前`
    }

    // 其他情况显示完整日期
    try {
      return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return '-'
    }
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

.downloader-path-management {
  padding: 0;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-lg);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
}

.header-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.header-icon {
  width: 32px;
  height: 32px;
  color: var(--color-primary);
  flex-shrink: 0;
}

.header-text {
  flex: 1;
}

.header-title {
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0 0 4px 0;
}

.header-desc {
  font-size: 13px;
  color: var(--color-text-tertiary);
  margin: 0;
}

.button-icon {
  display: inline;
  vertical-align: middle;
  margin-right: 6px;
  width: 16px;
  height: 16px;
}

.header-actions {
  display: flex;
  gap: var(--spacing-md);
  align-items: center;
}

.filter-section {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
}

.path-table-wrapper {
  margin-bottom: var(--spacing-lg);
}

// 表头整行渐变背景（修复：应用在tr元素而非单个th上）
::v-deep .path-table-header {
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));

  th {
    background: transparent;
    font-weight: var(--font-weight-semibold);
    color: white;

    // Table header top-left border radius
    &:first-child {
      border-top-left-radius: 12px;
    }

    // Table header top-right border radius
    &:last-child {
      border-top-right-radius: 12px;
    }
  }
}

.path-value-cell {
  display: flex;
  align-items: center;
  gap: 8px;

  .path-icon {
    width: 16px;
    height: 16px;
    color: var(--color-text-tertiary);
    flex-shrink: 0;
  }

  .path-text {
    flex: 1;
    font-size: 13px;
    color: var(--color-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.torrent-count-badge {
  ::v-deep .el-badge__content {
    background-color: var(--color-primary);
  }
}

.time-text {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.delete-button {
  color: var(--color-error);
}

.delete-button:hover {
  color: var(--color-error-dark);
}

.empty-state {
  padding: var(--spacing-xxl) 0;
  text-align: center;
}

.empty-icon {
  width: 64px;
  height: 64px;
  color: var(--color-border-primary);
  margin-bottom: var(--spacing-md);
}

.empty-text {
  font-size: 14px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin: 0 0 var(--spacing-sm) 0;
}

.empty-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin: 0;
}

.form-item-help {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: var(--spacing-xs);
  padding: 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.5;
}

.help-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--color-text-tertiary);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}
</style>
