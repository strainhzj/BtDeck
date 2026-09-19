<template>
  <div class="downloader-path-management">
    <!-- 头部说明和操作区 -->
    <div class="tab-header">
      <div class="header-info">
        <span class="header-icon"><LucideIcon name="folder-cog" :size="18" /></span>
        <div class="header-text">
          <h3 class="header-title">{{ $t('downloader.pathMaintenance.headerTitle') }}</h3>
          <p class="header-desc">{{ $t('downloader.pathMaintenance.headerDesc') }}</p>
        </div>
      </div>
      <div class="header-actions">
        <el-button
          type="success"
          size="medium"
          :disabled="refreshing"
          @click="handleRefresh"
        >
          <LucideIcon class="button-icon" name="refresh-cw" :size="14" :class="{'is-spinning': refreshing}" />
          {{ $t('downloader.pathMaintenance.refresh') }}
        </el-button>
        <el-button
          type="primary"
          size="medium"
          @click="handleAddPath"
        >
          <LucideIcon class="button-icon" name="plus" :size="14" />
          {{ $t('downloader.pathMaintenance.add') }}
        </el-button>
      </div>
    </div>

    <!-- 筛选区域 -->
    <div class="filter-section">
      <el-form :inline="true" size="small">
        <el-form-item :label="$t('downloader.pathMaintenance.filterType')">
          <el-select
            v-model="filterType"
            :placeholder="$t('downloader.pathMaintenance.typeAll')"
            clearable
            @change="handleFilterChange"
            style="width: 150px;"
          >
            <el-option :label="$t('downloader.pathMaintenance.typeDefault')" value="default" />
            <el-option :label="$t('downloader.pathMaintenance.typeActive')" value="active" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('downloader.pathMaintenance.filterStatus')">
          <el-select
            v-model="filterEnabled"
            :placeholder="$t('downloader.pathMaintenance.statusAll')"
            clearable
            @change="handleFilterChange"
            style="width: 150px;"
          >
            <el-option :label="$t('downloader.pathMaintenance.enabled')" :value="true" />
            <el-option :label="$t('downloader.pathMaintenance.disabled')" :value="false" />
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
        <el-table-column :label="$t('downloader.pathMaintenance.colType')" width="120">
          <template #default="{row}">
            <el-tag
              :type="row.path_type === 'default' ? 'primary' : 'success'"
              size="small"
            >
              {{ row.path_type === 'default' ? $t('downloader.pathMaintenance.typeDefault') : $t('downloader.pathMaintenance.typeActive') }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 路径值 -->
        <el-table-column :label="$t('downloader.pathMaintenance.colValue')" min-width="300">
          <template #default="{row}">
            <div class="path-value-cell">
              <LucideIcon class="path-icon" name="folder-open" :size="14" />
              <span class="path-text" :title="row.path_value">{{ row.path_value }}</span>
            </div>
          </template>
        </el-table-column>

        <!-- 种子数量 -->
        <el-table-column :label="$t('downloader.pathMaintenance.colTorrentCount')" width="100" align="center">
          <template #default="{row}">
            <el-badge
              :value="row.torrent_count"
              :max="999"
              class="torrent-count-badge"
            />
          </template>
        </el-table-column>

        <!-- 状态 -->
        <el-table-column :label="$t('downloader.pathMaintenance.colStatus')" width="96" align="center">
          <template #default="{row}">
            <div class="status-cell">
              <el-switch
                v-model="row.is_enabled"
                @change="handleToggleEnabled(row)"
                :disabled="updating"
                active-color="#059669"
                inactive-color="#d1d5db"
              />
              <!-- 历史路径（自动禁用，种子回归后自动恢复）/ 手动禁用（需用户重新启用） -->
              <span
                v-if="!row.is_enabled"
                class="disabled-source-tag"
                :class="row.disabled_by === 'user' ? 'disabled-source-tag--user' : 'disabled-source-tag--auto'"
              >{{ row.disabled_by === 'user' ? $t('downloader.pathMaintenance.disabledByUser') : $t('downloader.pathMaintenance.historyPath') }}</span>
            </div>
          </template>
        </el-table-column>

        <!-- 最后更新时间 -->
        <el-table-column :label="$t('downloader.pathMaintenance.colUpdated')" width="160">
          <template #default="{row}">
            <span class="time-text">{{ formatTime(row.last_updated_time) }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column :label="$t('downloader.pathMaintenance.colActions')" width="120" fixed="right">
          <template #default="{row}">
            <el-button
              type="text"
              size="small"
              @click="handleEditPath(row)"
              :disabled="updating"
            >
              <LucideIcon name="pencil" :size="13" />
              {{ $t('downloader.pathMaintenance.edit') }}
            </el-button>
            <el-button
              type="text"
              size="small"
              class="delete-button"
              @click="handleDeletePath(row)"
              :disabled="updating"
            >
              <LucideIcon name="trash-2" :size="13" />
              {{ $t('downloader.pathMaintenance.delete') }}
            </el-button>
          </template>
        </el-table-column>

        <!-- 空状态 -->
        <template #empty>
          <div class="empty-state">
            <LucideIcon class="empty-icon" name="folder-search" :size="40" :stroke-width="1.35" />
            <p class="empty-text">{{ $t('downloader.pathMaintenance.emptyText') }}</p>
            <p class="empty-hint">{{ $t('downloader.pathMaintenance.emptyHint') }}</p>
          </div>
        </template>
      </el-table>
    </div>

    <!-- 添加/编辑路径对话框 -->
    <el-dialog
      :title="dialogMode === 'add' ? $t('downloader.pathMaintenance.dialogAddTitle') : $t('downloader.pathMaintenance.dialogEditTitle')"
      :visible.sync="dialogVisible"
      width="500px" custom-class="path-mgmt-dialog"
      :before-close="handleDialogClose"
      :close-on-click-modal="false"
    >
      <el-form
        ref="pathFormRef"
        :model="formData"
        :rules="formRules"
        label-width="100px"
      >
        <el-form-item :label="$t('downloader.pathMaintenance.typeLabel')" prop="path_type">
          <el-select
            v-model="formData.path_type"
            :placeholder="$t('downloader.pathMaintenance.typePlaceholder')"
            :disabled="dialogMode === 'edit'"
            style="width: 100%;"
          >
            <el-option :label="$t('downloader.pathMaintenance.typeDefault')" value="default" />
            <el-option :label="$t('downloader.pathMaintenance.typeActive')" value="active" />
          </el-select>
          <div class="form-item-help">
            <LucideIcon class="help-icon" name="info" :size="13" />
            <span>{{ $t('downloader.pathMaintenance.typeHint') }}</span>
          </div>
        </el-form-item>

        <el-form-item :label="$t('downloader.pathMaintenance.valueLabel')" prop="path_value">
          <el-input
            v-model="formData.path_value"
            :placeholder="$t('downloader.pathMaintenance.valuePlaceholder')"
            clearable
          />
          <div class="form-item-help">
            <LucideIcon class="help-icon" name="info" :size="13" />
            <span>{{ $t('downloader.pathMaintenance.valueHint') }}</span>
          </div>
        </el-form-item>

        <el-form-item :label="$t('downloader.pathMaintenance.enableLabel')" prop="is_enabled">
          <el-switch
            v-model="formData.is_enabled"
            active-color="#059669"
            inactive-color="#d1d5db"
          />
          <div class="form-item-help">
            <LucideIcon class="help-icon" name="info" :size="13" />
            <span>{{ $t('downloader.pathMaintenance.enableHint') }}</span>
          </div>
        </el-form-item>
      </el-form>

      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">{{ $t('downloader.pathMaintenance.cancel') }}</el-button>
        <el-button type="primary" :disabled="submitting" @click="handleSubmit">
          <LucideIcon :name="submitting ? 'refresh-cw' : 'save'" :size="14" :class="{'is-spinning': submitting}" />
          {{ dialogMode === 'add' ? $t('downloader.pathMaintenance.submitAdd') : $t('downloader.pathMaintenance.submitSave') }}
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import { Downloader } from '../types'
import { translate } from '@/i18n'
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
  disabled_by: string | null
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
      { required: true, message: this.$t('downloader.pathMaintenance.validate.typeRequired').toString(), trigger: 'change' }
    ],
    path_value: [
      { required: true, message: this.$t('downloader.pathMaintenance.validate.valueRequired').toString(), trigger: 'blur' },
      { min: 1, max: 500, message: this.$t('downloader.pathMaintenance.validate.valueLength').toString(), trigger: 'blur' }
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
      this.$message.error(this.$t('downloader.pathMaintenance.msg.downloaderIncomplete').toString())
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
        this.$message.error(response.msg || this.$t('downloader.pathMaintenance.msg.loadFailed').toString())
      }
    } catch (error: any) {
      console.error('加载路径列表失败:', error)
      this.$message.error(error?.response?.data?.msg || error?.message || '加载路径列表失败')
    } finally {
      this.loading = false
    }
  }

  // {{ $t('downloader.pathMaintenance.refresh') }}列表
  private async handleRefresh() {
    this.refreshing = true
    try {
      await this.loadPaths()
      this.$message.success(this.$t('downloader.pathMaintenance.msg.refreshSuccess').toString())
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
        this.$t('downloader.pathMaintenance.msg.deleteConfirm', { path: row.path_value }).toString(),
        this.$t('downloader.pathMaintenance.msg.deleteTitle').toString(),
        {
          confirmButtonText: this.$t('downloader.pathMaintenance.msg.confirm').toString(),
          cancelButtonText: this.$t('downloader.pathMaintenance.msg.cancel').toString(),
          type: 'warning'
        }
      )

      // 安全获取下载器ID
      const downloaderId = this.downloader?.id ?? this.downloader?.downloaderId
      if (!downloaderId) {
        this.$message.error(this.$t('downloader.pathMaintenance.msg.downloaderIncomplete').toString())
        return
      }

      this.updating = true

      const response = await deleteDownloaderPath(
        downloaderId,
        row.id
      )

      if (response.code === '200') {
        this.$message.success(this.$t('downloader.pathMaintenance.msg.deleteSuccess').toString())
        await this.loadPaths()
      } else {
        this.$message.error(response.msg || this.$t('downloader.pathMaintenance.msg.deleteFailed').toString())
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
      this.$message.error(this.$t('downloader.pathMaintenance.msg.downloaderIncomplete').toString())
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
        this.$message.success(row.is_enabled
        ? this.$t('downloader.pathMaintenance.msg.toggleEnabled').toString()
        : this.$t('downloader.pathMaintenance.msg.toggleDisabled').toString())
        await this.loadPaths()
      } else {
        // 恢复原状态
        row.is_enabled = originalState
        this.$message.error(response.msg || this.$t('downloader.pathMaintenance.msg.opFailed').toString())
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
        this.$message.error(this.$t('downloader.pathMaintenance.msg.downloaderIncomplete').toString())
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
          this.$message.success(this.$t('downloader.pathMaintenance.msg.addSuccess').toString())
          this.dialogVisible = false
          await this.loadPaths()
        } else {
          this.$message.error(response.msg || this.$t('downloader.pathMaintenance.msg.addFailed').toString())
        }
      } else {
        // 编辑路径
        if (!this.currentEditPath) {
          this.$message.error(this.$t('downloader.pathMaintenance.msg.noEditSelection').toString())
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
          this.$message.success(this.$t('downloader.pathMaintenance.msg.saveSuccess').toString())
          this.dialogVisible = false
          await this.loadPaths()
        } else {
          this.$message.error(response.msg || this.$t('downloader.pathMaintenance.msg.saveFailed').toString())
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
      return minutes < 1
      ? translate('downloader.pathMaintenance.time.justNow')
      : translate('downloader.pathMaintenance.time.minutesAgo', { n: minutes })
    }

    // 小于24小时
    if (diff < 86400000) {
      const hours = Math.floor(diff / 3600000)
      return translate('downloader.pathMaintenance.time.hoursAgo', { n: hours })
    }

    // 小于7天
    if (diff < 604800000) {
      const days = Math.floor(diff / 86400000)
      return translate('downloader.pathMaintenance.time.daysAgo', { n: days })
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
  display: block;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  padding: 0;
  text-align: left;
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

.tab-header {
  margin-bottom: 8px;
  padding: 10px 12px;
  border-color: var(--color-border-secondary);
  border-radius: 11px;
  background:
    linear-gradient(110deg, rgba(var(--color-primary-rgb), 0.075), transparent 42%),
    rgba(255, 255, 255, 0.66);
}

.header-info {
  min-width: 0;
  gap: 9px;
}

.header-icon {
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(var(--color-primary-rgb), 0.2);
  border-radius: 9px;
  background: rgba(var(--color-primary-rgb), 0.07);
}

.header-title {
  margin-bottom: 2px;
  font-size: 12px;
  letter-spacing: 0.03em;
}

.header-desc {
  overflow: hidden;
  max-width: 680px;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-actions {
  gap: 6px;
}

.header-actions ::v-deep .el-button {
  height: 30px;
  padding: 0 10px;
  font-size: 9px;
}

.header-actions ::v-deep .el-button span,
::v-deep .el-table .el-button span,
.dialog-footer ::v-deep .el-button span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.button-icon {
  margin-right: 0;
}

.filter-section {
  margin-bottom: 8px;
  padding: 6px 9px;
  border-color: var(--color-border-secondary);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.62);
}

.filter-section ::v-deep .el-form-item {
  margin: 0 10px 0 0;
}

.filter-section ::v-deep .el-form-item__label {
  font-size: 9px;
}

.path-table-wrapper {
  overflow: hidden;
  margin-bottom: 0;
  border: 1px solid var(--color-border-secondary);
  border-radius: 11px;
}

::v-deep .path-table-header {
  background: var(--color-bg-tertiary);

  th {
    height: 31px;
    color: var(--color-text-secondary);
    font-size: 9px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
}

::v-deep .el-table td {
  height: 40px;
  padding-top: 3px;
  padding-bottom: 3px;
}

::v-deep .el-table .cell,
.path-value-cell .path-text,
.time-text {
  font-size: 10px;
}

::v-deep .el-table .el-button {
  margin-left: 5px;
  font-size: 9px;
}

.empty-state {
  padding: 38px 0;
}

.empty-icon {
  width: 40px;
  height: 40px;
  margin-bottom: 9px;
}

.empty-text {
  font-size: 11px;
}

.empty-hint,
.form-item-help {
  font-size: 9px;
}

.is-spinning {
  animation: managed-path-spin 0.8s linear infinite;
}

.status-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.disabled-source-tag {
  font-size: 11px;
  line-height: 1;
  padding: 2px 6px;
  border-radius: 8px;
  white-space: nowrap;
}

.disabled-source-tag--auto {
  color: var(--color-warning, #b45309);
  background: rgba(180, 83, 9, 0.12);
}

.disabled-source-tag--user {
  color: var(--color-danger, #b91c1c);
  background: rgba(185, 28, 28, 0.1);
}

@keyframes managed-path-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 780px) {
  /* Element 表格自带横向滚动；手机下增大单元格行高与字号提升可读性 */
  ::v-deep .el-table .cell {
    font-size: 12px;
    line-height: 1.5;
  }

  ::v-deep .el-table .el-button--mini {
    min-height: 30px;
    padding: 5px 8px;
  }

  .tab-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions {
    width: 100%;

    .el-button {
      flex: 1;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .is-spinning {
    animation: none;
  }
}
</style>

<style lang="scss">
/* 内嵌弹窗手机适配（mobile-ux-fixes 2026-09-12）：挂 body，scoped 不达，
   宽度 prop 内联需 !important 覆盖；页脚按钮全宽 */
@media (max-width: 768px) {
  .path-mgmt-dialog {
    width: 92% !important;
    max-width: 500px;
  }

  .path-mgmt-dialog .dialog-footer {
    display: flex;
    gap: 8px;
  }

  .path-mgmt-dialog .dialog-footer .el-button {
    flex: 1;
    margin-left: 0;
    min-height: 40px;
  }
}
</style>
