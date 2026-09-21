<template>
  <!-- 自定义弹窗 - 完全采用设计稿样式 -->
  <div
    class="modal-overlay"
    :class="{active: visible}"
    @click.self="handleClose"
  >
    <div class="modal-dialog" style="max-width: 600px;">
      <div class="modal-header">
        <h3 class="modal-title">➕ {{ $t('torrent.addDialog.title') }}</h3>
        <button class="modal-close" @click="handleClose">✕</button>
      </div>
      <div class="modal-body">
        <!-- 保留 Element UI 表单验证逻辑 -->
        <el-form :model="form" :rules="rules" ref="formRef" label-width="120px" class="custom-form">
          <!-- 种子文件上传区域 - 使用设计稿样式 -->
          <div class="form-group">
            <label class="form-label">
              {{ $t('torrent.addDialog.fileLabel') }} <span style="color: var(--color-error);">*</span>
            </label>
            <!-- 自定义文件上传区域 -->
            <div
              class="file-upload-area"
              :class="{'has-error': formErrors.torrent_file}"
              @click="triggerFileSelect"
            >
              <input
                ref="fileInputRef"
                type="file"
                accept=".torrent"
                multiple
                style="display: none;"
                @change="handleFileChange"
              />
              <div class="file-upload-placeholder" v-if="torrentFiles.length === 0">
                <span style="font-size: 32px; display: block; margin-bottom: 8px;">📁</span>
                <span style="color: var(--color-text-secondary);">{{ $t('torrent.addDialog.filePlaceholder') }}</span>
              </div>
              <div class="file-upload-info" v-else>
                <span style="color: var(--color-success);">✓</span>
                <span style="margin-left: 8px;">{{ $t('torrent.addDialog.filesSelected', {count: torrentFiles.length}) }}</span>
              </div>
            </div>

            <!-- 文件列表 -->
            <div class="file-list" v-if="torrentFiles.length > 0">
              <div
                v-for="(file, index) in torrentFiles"
                :key="index"
                class="file-item"
              >
                <span class="file-name">{{ file.name }}</span>
                <span class="file-size">{{ formatFileSize(file.size) }}</span>
                <button class="file-remove" @click="removeFile(index)">✕</button>
              </div>
            </div>

            <div class="form-error-tip" v-if="formErrors.torrent_file">{{ formErrors.torrent_file }}</div>
            <div style="font-size: 12px; color: var(--color-text-quaternary); margin-top: 6px;">
              {{ $t('torrent.addDialog.fileHint') }}
            </div>
          </div>

          <!-- 下载器选择 - 使用自定义样式 -->
          <div class="form-group">
            <label class="form-label">
              {{ $t('torrent.addDialog.downloaderLabel') }} <span style="color: var(--color-error);">*</span>
            </label>
            <select
              v-model="form.downloader_id"
              class="form-input"
              :class="{'has-error': formErrors.downloader_id}"
              @change="clearError('downloader_id')"
            >
              <option value="">{{ $t('torrent.addDialog.downloaderPlaceholder') }}</option>
              <option
                v-for="downloader in downloaders"
                :key="downloader.downloader_id"
                :value="downloader.downloader_id"
              >
                {{ downloader.nickname }}
              </option>
            </select>
            <div class="form-error-tip" v-if="formErrors.downloader_id">{{ formErrors.downloader_id }}</div>
          </div>

          <!-- 保存路径 -->
          <div class="form-group">
            <label class="form-label">
              {{ $t('torrent.addDialog.pathLabel') }} <span style="color: var(--color-error);">*</span>
            </label>
            <el-autocomplete
              v-model="form.save_path"
              :fetch-suggestions="queryPathSuggestions"
              :placeholder="$t('torrent.addDialog.pathPlaceholder')"
              style="width: 100%"
              @select="handlePathSelect"
              @input="clearError('save_path')"
              popper-class="torrent-add-autocomplete"
              :class="{'autocomplete-error': formErrors.save_path}"
            >
              <template slot-scope="{item}">
                <div class="path-suggestion">
                  <span class="path-value">{{ item.value }}</span>
                  <span class="path-type">{{ item.path_type === 'default' ? $t('torrent.addDialog.pathTypeDefault') : $t('torrent.addDialog.pathTypeInUse') }}</span>
                  <span class="torrent-count">({{ $t('torrent.addDialog.pathCount', {count: item.torrent_count}) }})</span>
                </div>
              </template>
            </el-autocomplete>
            <div class="form-error-tip" v-if="formErrors.save_path">{{ formErrors.save_path }}</div>
          </div>

          <!-- 跳过校验：保存路径已有完整数据（辅种/续种）时跳过 qBittorrent 本地校验，
               避免进入 CheckingDL 直接做种；数据不完整时勾选会被当作 100% 完成 -->
          <div class="form-group">
            <label class="form-label">{{ $t('torrent.addDialog.checkPolicy') }}</label>
            <el-checkbox v-model="form.skip_hash_check">{{ $t('torrent.addDialog.skipCheck') }}</el-checkbox>
            <div class="form-hint">
              {{ $t('torrent.addDialog.skipCheckHint') }}
            </div>
          </div>

          <!-- 分类 -->
          <div class="form-group">
            <label class="form-label">{{ $t('torrent.addDialog.category') }}</label>
            <el-select
              v-model="form.category"
              :placeholder="$t('torrent.addDialog.categoryPlaceholder')"
              style="width: 100%"
              filterable
              clearable
            >
              <el-option
                v-for="cat in categoryList"
                :key="cat.tag_id"
                :label="cat.tag_name"
                :value="cat.tag_name"
              />
            </el-select>
          </div>

          <!-- 标签 -->
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">{{ $t('torrent.addDialog.tags') }}</label>
            <el-select
              v-model="form.tags"
              :placeholder="$t('torrent.addDialog.tagsPlaceholder')"
              style="width: 100%"
              multiple
              filterable
              clearable
            >
              <el-option
                v-for="tag in tagList"
                :key="tag.tag_id"
                :label="tag.tag_name"
                :value="tag.tag_name"
              />
            </el-select>
          </div>
        </el-form>
      </div>
      <div class="modal-footer">
        <div class="modal-footer-left"></div>
        <div class="modal-footer-right">
          <button class="btn-secondary" @click="handleClose">{{ $t('common.cancel') }}</button>
          <button class="btn-primary" @click="handleConfirm" :disabled="loading">
            {{ loading ? $t('torrent.addDialog.adding') : $t('torrent.addDialog.confirm') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Ref, Watch } from 'vue-property-decorator'
import { addTorrentsBatch, getDownloaderPaths, type DownloaderPath } from '@/api/torrents'
import { apiErrorMessage, apiResponseMessage } from '@/i18n'
import { getNotificationList } from '@/api/notification'
import { getTagList, TorrentTag } from '@/api/tag-management'

const BATCH_COMPLETION_POLL_INTERVAL_MS = 2000
const BATCH_COMPLETION_INITIAL_DELAY_MS = 500
const BATCH_COMPLETION_TIMEOUT_MS = 10 * 60 * 1000

@Component
export default class TorrentAddDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  @Prop(Array) downloaders!: any[]

  // 使用 Ref 装饰器获取引用
  @Ref('formRef') readonly formRef!: any
  @Ref('fileInputRef') readonly fileInputRef!: any

  private loading = false
  private selectedFileNames: string[] = []
  private formErrors: Record<string, string> = {}
  private batchCompletionTimer: number | null = null
  private batchCompletionPollInFlight = false
  private pendingBatchCompletions: Record<string, number> = {}
  private batchCompletionWatcherActive = true

  // 种子文件列表（支持多个）
  private torrentFiles: File[] = []

  // 下载器路径列表
  private downloaderPaths: DownloaderPath[] = []

  // 标签列表
  private categoryList: TorrentTag[] = []
  private tagList: TorrentTag[] = []

  private form = {
    downloader_id: '',
    save_path: '',
    category: '',
    tags: [] as string[],
    /** 跳过校验（默认关：仅保存路径已有完整数据时手动勾选，见表单提示） */
    skip_hash_check: false
  }

  // 校验规则用 getter 生成：语言切换后新校验消息即时生效（不在实例化时固定译文）
  get rules() {
    return {
      torrent_file: [{ required: true, message: this.$t('torrent.addDialog.error.chooseFile'), trigger: 'change' }],
      downloader_id: [{ required: true, message: this.$t('torrent.addDialog.error.chooseDownloader'), trigger: 'change' }],
      save_path: [{ required: true, message: this.$t('torrent.addDialog.error.enterPath'), trigger: 'blur' }]
    }
  }

  beforeDestroy(): void {
    this.batchCompletionWatcherActive = false
    this.pendingBatchCompletions = {}
    if (this.batchCompletionTimer !== null) {
      window.clearTimeout(this.batchCompletionTimer)
      this.batchCompletionTimer = null
    }
  }

  /** 后台批量添加以通知中心的 task_id 终态作为权威完成信号。 */
  private watchBatchCompletion(taskId: string): void {
    if (!taskId || !this.batchCompletionWatcherActive) return
    this.pendingBatchCompletions[taskId] = Date.now() + BATCH_COMPLETION_TIMEOUT_MS
    this.scheduleBatchCompletionPoll(BATCH_COMPLETION_INITIAL_DELAY_MS)
  }

  private scheduleBatchCompletionPoll(delay = BATCH_COMPLETION_POLL_INTERVAL_MS): void {
    if (
      !this.batchCompletionWatcherActive ||
      this.batchCompletionTimer !== null ||
      this.batchCompletionPollInFlight ||
      Object.keys(this.pendingBatchCompletions).length === 0
    ) return
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const component = this
    component.batchCompletionTimer = window.setTimeout(() => {
      component.batchCompletionTimer = null
      component.pollBatchCompletions()
    }, delay)
  }

  private async pollBatchCompletions(): Promise<void> {
    if (this.batchCompletionPollInFlight) return
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const component = this
    const pendingTaskIds = Object.keys(component.pendingBatchCompletions)
    if (pendingTaskIds.length === 0) return
    component.batchCompletionPollInFlight = true

    try {
      const response = await getNotificationList({ page: 1, pageSize: 100, type: 'system' })
      if (response.code === '200' && response.data && Array.isArray(response.data.list)) {
        response.data.list.forEach(notification => {
          const extra = notification.extra_data
          const taskId = extra?.task_id || ''
          if (
            extra?.event !== 'torrent_batch_add_completed' ||
            !Object.prototype.hasOwnProperty.call(component.pendingBatchCompletions, taskId)
          ) return
          delete component.pendingBatchCompletions[taskId]
          component.$emit('batch-complete', {
            task_id: taskId,
            task_status: extra?.task_status || 'completed'
          })
        })
      }
    } catch (error) {
      console.debug('[种子添加] 查询后台任务完成通知失败:', error)
    } finally {
      component.batchCompletionPollInFlight = false
      const now = Date.now()
      Object.keys(component.pendingBatchCompletions).forEach(taskId => {
        if (component.pendingBatchCompletions[taskId] > now) return
        delete component.pendingBatchCompletions[taskId]
        // 通知写入偶发失败时仍做一次最终权威刷新，避免页面永久停留在旧快照。
        component.$emit('batch-complete', { task_id: taskId, task_status: 'timeout' })
      })
      component.scheduleBatchCompletionPoll()
    }
  }

  // 监听下载器变化，加载路径和标签
  @Watch('form.downloader_id')
  async onDownloaderChange(downloaderId: string) {
    if (!downloaderId) {
      this.downloaderPaths = []
      this.categoryList = []
      this.tagList = []
      return
    }

    // 加载路径列表
    try {
      const res = await getDownloaderPaths(downloaderId)
      if (res.code === '200' && res.data) {
        this.downloaderPaths = res.data.paths.filter((p: DownloaderPath) => p.is_enabled)
      }
    } catch (error) {
      console.error('加载路径列表失败:', error)
    }

    // 加载标签列表
    try {
      const [categoryRes, tagRes] = await Promise.all([
        getTagList({
          downloader_id: downloaderId,
          tag_type: 'category',
          sort_by: 'tag_name',
          sort_order: 'asc'
        }),
        getTagList({
          downloader_id: downloaderId,
          tag_type: 'tag',
          sort_by: 'tag_name',
          sort_order: 'asc'
        })
      ])

      if (categoryRes.code === '200') {
        this.categoryList = categoryRes.data.list || []
      }
      if (tagRes.code === '200') {
        this.tagList = tagRes.data.list || []
      }
    } catch (error) {
      console.error('加载标签列表失败:', error)
    }
  }

  // 触发文件选择
  triggerFileSelect() {
    this.fileInputRef?.click()
  }

  // 处理文件变更（支持多个文件）
  handleFileChange(event: Event) {
    const input = event.target as HTMLInputElement
    if (input.files && input.files.length > 0) {
      const files = Array.from(input.files)

      // 验证文件类型
      const invalidFiles = files.filter(file => !file.name.endsWith('.torrent'))
      if (invalidFiles.length > 0) {
        this.formErrors.torrent_file = this.$t('torrent.addDialog.error.onlyTorrent') as string
        return
      }

      // 添加文件列表
      this.torrentFiles = [...this.torrentFiles, ...files]
      this.selectedFileNames = this.torrentFiles.map(f => f.name)
      this.clearError('torrent_file')
    }
  }

  // 删除单个文件
  removeFile(index: number) {
    this.torrentFiles.splice(index, 1)
    this.selectedFileNames = this.torrentFiles.map(f => f.name)

    if (this.torrentFiles.length === 0) {
      this.formErrors.torrent_file = this.$t('torrent.addDialog.error.chooseFile') as string
    }
  }

  // 查询路径建议
  queryPathSuggestions(queryString: string, cb: any) {
    const suggestions = this.downloaderPaths
      .filter(path => path.is_enabled && path.path_value.toLowerCase().includes(queryString.toLowerCase()))
      .map(path => ({
        value: path.path_value,
        path_type: path.path_type,
        torrent_count: path.torrent_count
      }))

    cb(suggestions)
  }

  // 选择路径
  handlePathSelect(item: any) {
    this.form.save_path = item.value
  }

  // 格式化文件大小
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  // 清除错误提示
  clearError(field: string) {
    if (this.formErrors[field]) {
      this.$delete(this.formErrors, field)
    }
  }

  // 验证表单
  validateForm(): boolean {
    this.formErrors = {}

    if (this.torrentFiles.length === 0) {
      this.formErrors.torrent_file = this.$t('torrent.addDialog.error.chooseFile') as string
    }

    // 修复：使用精确判断，避免数字0被误判为false
    if (this.form.downloader_id === null || this.form.downloader_id === undefined || this.form.downloader_id === '') {
      this.formErrors.downloader_id = this.$t('torrent.addDialog.error.chooseDownloader') as string
    }

    if (!this.form.save_path) {
      this.formErrors.save_path = this.$t('torrent.addDialog.error.enterPath') as string
    }

    return Object.keys(this.formErrors).length === 0
  }

  async handleConfirm() {
    if (!this.validateForm()) {
      return
    }

    // 异步请求完成后仍使用当前组件实例，显式保留上下文快照。
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const component = this
    const formSnapshot = {
      downloader_id: this.form.downloader_id,
      save_path: this.form.save_path,
      category: this.form.category,
      tags: [...this.form.tags],
      skip_hash_check: this.form.skip_hash_check
    }
    const torrentFiles = [...this.torrentFiles]
    this.loading = true

    try {
      // 使用批量上传API
      const response = await addTorrentsBatch({
        torrent_files: torrentFiles,
        downloader_id: formSnapshot.downloader_id,
        save_path: formSnapshot.save_path,
        category: formSnapshot.category || '',
        tags: formSnapshot.tags.join(','),
        paused: false,
        skip_hash_check: formSnapshot.skip_hash_check,
        is_sequential_download: false,
        is_first_last_piece_priority: false
      })

      if (response.code === '202') {
        component.$message.success(response.msg || component.$t('torrent.addDialog.msg.submitted', { count: torrentFiles.length }))
        component.watchBatchCompletion(response.data?.task_id || '')
        component.$emit('confirm', formSnapshot)
        component.handleClose()
      } else if (response.code === '200' || response.code === '207') {
        const data = response.data
        const successCount = data.success_count ?? 0
        const failedCount = data.failed_count ?? 0
        const results = data.results ?? []
        const failedResults = results.filter(result => !result.success)
        const failureSummary = failedResults
          .slice(0, 3)
          .map(result => component.$t('torrent.addDialog.msg.failureItem', {
            name: result.file_name,
            error: result.error || component.$t('torrent.addDialog.msg.unknownError')
          }) as string)
          .join('；')
        const failureSuffix = failedResults.length > 3
          ? component.$t('torrent.addDialog.msg.moreFailures', { count: failedResults.length - 3 }) as string
          : ''

        // 根据结果显示不同的提示
        if (successCount === data.total) {
          component.$message.success(component.$t('torrent.addDialog.msg.success', { count: successCount }))
        } else if (successCount === 0) {
          component.$message.error(
            failureSummary
              ? component.$t('torrent.addDialog.msg.failedWith', { detail: failureSummary + failureSuffix }) as string
              : component.$t('torrent.addDialog.msg.failedWith', { detail: component.$t('torrent.addDialog.msg.unknownError') }) as string
          )
          console.error('所有种子添加失败:', results)
        } else {
          component.$message.warning({
            message: component.$t('torrent.addDialog.msg.partial', { success: successCount, failed: failedCount }) +
              (failureSummary ? `（${failureSummary}${failureSuffix}）` : ''),
            duration: 5000
          })
          console.error('添加失败的种子:', failedResults)
        }

        // 只要有成功的就刷新列表并关闭对话框
        if (successCount > 0) {
          component.$emit('confirm', formSnapshot)
          component.handleClose()
        }
      } else {
        // 双语 P4 错误契约：优先 reasonCode 本地化
        component.$message.error(apiResponseMessage(response, component.$t('torrent.addDialog.msg.failed') as string))
      }
    } catch (error: unknown) {
      console.error('添加种子失败:', error)
      // 双语 P4 错误契约：优先 reasonCode 本地化，未契约化路径回退原始 msg
      component.$message.error(apiErrorMessage(error, component.$t('torrent.addDialog.msg.retry') as string))
    } finally {
      component.loading = false
    }
  }

  handleClose() {
    // 重置表单
    this.form = {
      downloader_id: '',
      save_path: '',
      category: '',
      tags: [],
      skip_hash_check: false
    }
    this.torrentFiles = []
    this.selectedFileNames = []
    this.downloaderPaths = []
    this.categoryList = []
    this.tagList = []
    this.formErrors = {}

    // 清空文件输入
    if (this.fileInputRef) {
      this.fileInputRef.value = ''
    }

    this.$emit('update:visible', false)
  }
}
</script>

<style lang="scss" scoped>
// ========================================
// 弹窗基础样式
// ========================================
.modal-overlay {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 2000;
  align-items: center;
  justify-content: center;

  &.active {
    display: flex;
  }
}

.modal-dialog {
  background: var(--color-bg-primary);
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  animation: modalSlideIn 0.3s ease;
}

@keyframes modalSlideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.modal-header {
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
  color: white;
  padding: 16px 20px;
  border-radius: 12px 12px 0 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}

.modal-close {
  width: 32px;
  height: 32px;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  cursor: pointer;
  font-size: 18px;
  color: white;
  transition: all 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.3);
  }
}

.modal-body {
  padding: 16px;
}

.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--color-border-primary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-footer-left,
.modal-footer-right {
  display: flex;
  gap: 10px;
}

// ========================================
// Element UI 表单隐藏
// ========================================
.custom-form {
  ::v-deep .el-form-item__label {
    display: none;
  }

  ::v-deep .el-form-item__content {
    margin-left: 0 !important;
  }

  ::v-deep .el-form-item {
    margin-bottom: 0;
  }
}

// ========================================
// 表单样式
// ========================================
.form-group {
  margin-bottom: 16px;

  &:last-child {
    margin-bottom: 0;
  }
}

.form-label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 8px;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  font-size: 14px;
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: 6px;
  transition: all 0.2s ease;
  outline: none;
  font-family: inherit;

  &:focus {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1);
  }

  &::placeholder {
    color: var(--color-text-quaternary);
  }

  &:hover {
    border-color: var(--color-border-primary);
  }

  &.has-error {
    border-color: var(--color-error);

    &:focus {
      box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
    }
  }
}

// Autocomplete 错误状态
.autocomplete-error {
  ::v-deep .el-input__inner {
    border-color: var(--color-error) !important;

    &:focus {
      box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1) !important;
    }
  }
}

select.form-input {
  cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394A3B8' d='M2 4l4 4 4-4'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 36px;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
}

.form-error-tip {
  color: var(--color-error);
  font-size: 12px;
  margin-top: 4px;
}

// ========================================
// 文件上传区域样式
// ========================================
.file-upload-area {
  border: 2px dashed var(--color-border-primary);
  border-radius: 8px;
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    border-color: var(--color-primary);
    background: rgba(16, 185, 129, 0.02);
  }

  &.has-error {
    border-color: var(--color-error);

    &:hover {
      border-color: var(--color-error);
      background: rgba(239, 68, 68, 0.02);
    }
  }
}

.file-upload-placeholder {
  color: var(--color-text-secondary);
}

.file-upload-info {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  background: var(--color-bg-secondary);
  border-radius: 6px;
}

// 文件列表样式
.file-list {
  margin-top: 12px;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--color-border-primary);
  border-radius: 6px;
  background: var(--color-bg-secondary);
}

.file-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border-primary);

  &:last-child {
    border-bottom: none;
  }

  .file-name {
    flex: 1;
    font-size: 13px;
    color: var(--color-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file-size {
    margin: 0 12px;
    font-size: 12px;
    color: var(--color-text-tertiary);
    white-space: nowrap;
  }

  .file-remove {
    padding: 4px 8px;
    background: transparent;
    border: none;
    color: var(--color-text-secondary);
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.2s ease;

    &:hover {
      background: var(--color-error);
      color: white;
    }
  }
}

// 路径建议样式
.path-suggestion {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;

  .path-value {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .path-type {
    margin-left: 8px;
    padding: 2px 6px;
    background-color: #E5E7EB;
    color: #374151;
    font-size: 12px;
    border-radius: 3px;
  }

  .torrent-count {
    margin-left: 8px;
    color: #9CA3AF;
    font-size: 12px;
  }
}

// ========================================
// 按钮样式
// ========================================
.btn-secondary {
  padding: 8px 16px;
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  font-size: 14px;
  transition: all 0.2s ease;

  &:hover {
    background: var(--color-bg-tertiary);
  }
}

.btn-primary {
  padding: 8px 16px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

// ========================================
// 滚动条样式
// ========================================
.modal-dialog::-webkit-scrollbar {
  width: 8px;
}

.modal-dialog::-webkit-scrollbar-track {
  background: var(--color-bg-secondary);
  border-radius: 4px;
}

.modal-dialog::-webkit-scrollbar-thumb {
  background: var(--color-border-primary);
  border-radius: 4px;
}

.modal-dialog::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-quaternary);
}

// 表单提示文本（校验策略等说明行）
.form-hint {
  font-size: 12px;
  color: var(--color-text-quaternary);
  margin-top: 4px;
  line-height: 1.5;
}

// ========================================
// 移动端适配（≤768）：本弹窗是自定义 modal 非 el-dialog，宽度/布局须自行覆盖
// ========================================
@media (max-width: 768px) {
  // 顶部锚定 + overlay 自身可滚：长表单（文件列表+五组字段）不再受 85vh 挤压
  .modal-overlay.active {
    align-items: flex-start;
    padding: 12px;
    overflow-y: auto;
  }

  // 根元素带内联 max-width:600px，须 !important 压制；全宽贴边留 12px 边距
  .modal-dialog {
    width: 100%;
    max-width: calc(100vw - 24px) !important;
    max-height: none;
  }

  .modal-header {
    padding: 14px 16px;
    // 吸顶圆角随内容滚动裁切，收敛为上下同圆角避免视觉断层
    border-radius: 12px;
  }

  .modal-title {
    font-size: 16px;
  }

  .modal-close {
    width: 36px;
    height: 36px;
  }

  .modal-body {
    padding: 12px 14px;
  }

  // 底部按钮改纵向铺满：双钮等宽 + ≥44px 触控高
  .modal-footer {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    padding: 12px 14px;
  }

  .modal-footer-left {
    display: none;
  }

  .modal-footer-right {
    width: 100%;

    .btn-secondary,
    .btn-primary {
      flex: 1;
      min-height: 44px;
      padding: 10px 16px;
    }
  }

  // 文件移除触控目标放大（4px padding 桌面尺寸手指难命中）
  .file-item .file-remove {
    min-width: 36px;
    min-height: 36px;
    margin: -4px -4px -4px 0;
    padding: 4px 10px;
  }

  .file-upload-area {
    padding: 18px 12px;
  }

  .file-item {
    padding: 10px 8px;

    .file-size {
      margin: 0 8px;
    }
  }
}
</style>
