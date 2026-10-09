<template>
  <!-- 全自定义弹窗：零 Element UI（壳=BaseDialog，表单控件=FormSelect/FormAutocomplete/FormCheckbox） -->
  <BaseDialog
    :visible="visible"
    :title="$t('torrent.addDialog.title')"
    icon="plus-circle"
    max-width="600px"
    @close="handleClose"
  >
    <!-- 种子文件上传区域（点击 + 拖拽） -->
    <div class="form-group">
      <label class="form-label">
        {{ $t('torrent.addDialog.fileLabel') }} <span class="required-mark">*</span>
      </label>
      <div
        class="dropzone"
        :class="{'has-error': formErrors.torrent_file, 'is-dragover': dragOver}"
        role="button"
        tabindex="0"
        :aria-label="$t('torrent.addDialog.filePlaceholder')"
        @click="triggerFileSelect"
        @keydown.enter.prevent="triggerFileSelect"
        @dragenter.prevent="dragOver = true"
        @dragover.prevent
        @dragleave.prevent="dragOver = false"
        @drop.prevent="handleDrop"
      >
        <input
          ref="fileInputRef"
          type="file"
          accept=".torrent"
          multiple
          class="dropzone__input"
          @change="handleFileChange"
        >
        <template v-if="torrentFiles.length === 0">
          <LucideIcon name="file-up" :size="32" class="dropzone__icon" />
          <div class="dropzone__text">{{ $t('torrent.addDialog.filePlaceholder') }}</div>
          <div class="dropzone__subtext">{{ $t('torrent.addDialog.fileDropHint') }}</div>
        </template>
        <div v-else class="dropzone__selected">
          <LucideIcon name="circle-check-big" :size="18" class="dropzone__selected-icon" />
          <span>{{ $t('torrent.addDialog.filesSelected', {count: torrentFiles.length}) }}</span>
        </div>
      </div>

      <!-- 文件列表 -->
      <div class="file-list" v-if="torrentFiles.length > 0">
        <div class="file-list__header">
          <span class="file-list__count">
            {{ $t('torrent.addDialog.filesSelected', {count: torrentFiles.length}) }}
          </span>
          <button type="button" class="file-list__clear" @click="clearAllFiles">
            {{ $t('torrent.addDialog.clearFiles') }}
          </button>
        </div>
        <div
          v-for="(file, index) in torrentFiles"
          :key="`${file.name}-${index}`"
          class="file-item"
        >
          <LucideIcon name="file" :size="16" class="file-item__icon" />
          <span class="file-item__name">{{ file.name }}</span>
          <span class="file-item__size">{{ formatFileSize(file.size) }}</span>
          <button
            class="file-item__remove"
            type="button"
            :aria-label="$t('torrent.addDialog.removeFile')"
            @click="removeFile(index)"
          >
            <LucideIcon name="x" :size="14" />
          </button>
        </div>
      </div>

      <div class="form-error-tip" v-if="formErrors.torrent_file">{{ formErrors.torrent_file }}</div>
      <div class="form-hint">{{ $t('torrent.addDialog.fileHint') }}</div>
    </div>

    <!-- 下载器选择（选项行机会渲染类型徽章 + 在线状态点） -->
    <div class="form-group">
      <label class="form-label">
        {{ $t('torrent.addDialog.downloaderLabel') }} <span class="required-mark">*</span>
      </label>
      <FormSelect
        v-model="form.downloader_id"
        :options="downloaderOptions"
        :placeholder="$t('torrent.addDialog.downloaderPlaceholder')"
        :invalid="!!formErrors.downloader_id"
        @change="clearError('downloader_id')"
      />
      <div class="form-error-tip" v-if="formErrors.downloader_id">{{ formErrors.downloader_id }}</div>
    </div>

    <!-- 保存路径（输入 + 路径建议浮层） -->
    <div class="form-group">
      <label class="form-label">
        {{ $t('torrent.addDialog.pathLabel') }} <span class="required-mark">*</span>
      </label>
      <FormAutocomplete
        v-model="form.save_path"
        :suggestions="pathSuggestions"
        :placeholder="$t('torrent.addDialog.pathPlaceholder')"
        :invalid="!!formErrors.save_path"
        mono
        @input="clearError('save_path')"
      >
        <template #suggestion="{item}">
          <div class="path-suggestion">
            <span class="path-suggestion__value">{{ item.value }}</span>
            <span
              class="path-suggestion__type"
              :class="item.path_type === 'default' ? 'is-default' : 'is-active'"
            >
              {{ item.path_type === 'default'
                ? $t('torrent.addDialog.pathTypeDefault')
                : $t('torrent.addDialog.pathTypeInUse') }}
            </span>
            <span class="path-suggestion__count">
              {{ $t('torrent.addDialog.pathCount', {count: item.torrent_count}) }}
            </span>
          </div>
        </template>
      </FormAutocomplete>
      <div class="form-error-tip" v-if="formErrors.save_path">{{ formErrors.save_path }}</div>
    </div>

    <!-- 跳过校验：保存路径已有完整数据（辅种/续种）时跳过 qBittorrent 本地校验，
         避免进入 CheckingDL 直接做种；数据不完整时勾选会被当作 100% 完成 -->
    <div class="form-group">
      <label class="form-label">{{ $t('torrent.addDialog.checkPolicy') }}</label>
      <div class="policy-card" :class="{'is-active': form.skip_hash_check}">
        <div class="policy-card__head">
          <LucideIcon name="alert-triangle" :size="16" class="policy-card__icon" />
          <FormCheckbox v-model="form.skip_hash_check" class="policy-card__checkbox">
            {{ $t('torrent.addDialog.skipCheck') }}
          </FormCheckbox>
        </div>
        <p class="policy-card__hint">{{ $t('torrent.addDialog.skipCheckHint') }}</p>
      </div>
    </div>

    <!-- 分类 -->
    <div class="form-group">
      <label class="form-label">{{ $t('torrent.addDialog.category') }}</label>
      <FormSelect
        v-model="form.category"
        :options="categoryOptions"
        :placeholder="$t('torrent.addDialog.categoryPlaceholder')"
        filterable
        clearable
      />
    </div>

    <!-- 标签 -->
    <div class="form-group" style="margin-bottom: 0;">
      <label class="form-label">{{ $t('torrent.addDialog.tags') }}</label>
      <FormSelect
        v-model="form.tags"
        :options="tagOptions"
        :placeholder="$t('torrent.addDialog.tagsPlaceholder')"
        multiple
        filterable
        clearable
      />
    </div>

    <!-- 底部：左侧已选摘要，右侧取消/确认 -->
    <template #footer-left>
      <span v-if="torrentFiles.length > 0" class="footer-summary">
        <LucideIcon name="file" :size="14" class="footer-summary__icon" />
        {{ $t('torrent.addDialog.filesSelected', {count: torrentFiles.length}) }}
      </span>
    </template>
    <template #footer-right>
      <button class="btn-secondary" type="button" @click="handleClose">
        {{ $t('common.cancel') }}
      </button>
      <button class="btn-primary" type="button" :disabled="loading" @click="handleConfirm">
        <LucideIcon v-if="loading" name="loader-2" :size="16" class="is-spin" />
        {{ loading ? $t('torrent.addDialog.adding') : $t('torrent.addDialog.confirm') }}
      </button>
    </template>
  </BaseDialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Ref, Watch } from 'vue-property-decorator'
import { addTorrentsBatch, getDownloaderPaths, type DownloaderPath } from '@/api/torrents'
import { apiErrorMessage, apiResponseMessage } from '@/i18n'
import { getNotificationList } from '@/api/notification'
import { getTagList, TorrentTag } from '@/api/tag-management'
import BaseDialog from '@/components/common/BaseDialog.vue'
import FormSelect from '@/components/common/FormSelect.vue'
import FormAutocomplete from '@/components/common/FormAutocomplete.vue'
import FormCheckbox from '@/components/common/FormCheckbox.vue'
import type { FormSelectOption } from '@/components/common/formControls'
import type { FormAutocompleteSuggestion } from '@/components/common/formControls'

const BATCH_COMPLETION_POLL_INTERVAL_MS = 2000
const BATCH_COMPLETION_INITIAL_DELAY_MS = 500
const BATCH_COMPLETION_TIMEOUT_MS = 10 * 60 * 1000

/**
 * 下载器选项行。
 * /downloader/getList 简单 VO 现仅返回 downloader_id/nickname；
 * downloader_type/type、connectStatus/status 为可选增强字段——存在则机会渲染
 * 类型徽章（qB/TR/rt）与在线状态点，缺省自动退化，不改动调用方契约。
 */
export interface AddDialogDownloaderRow {
  downloader_id: string
  nickname: string
  downloader_type?: number
  type?: number
  connectStatus?: string
  status?: string
}

/** 保存路径建议项（FormAutocomplete 富建议：路径 + 类型徽章 + 种子数） */
export interface PathSuggestion extends FormAutocompleteSuggestion {
  path_type: string
  torrent_count: number
}

/** 下载器类型数字 → 短徽章文本（0=qB / 1=TR / 2=rt；未知值不渲染） */
const DOWNLOADER_TYPE_BADGE: Record<number, string> = {
  0: 'qB',
  1: 'TR',
  2: 'rt'
}

@Component({
  name: 'TorrentAddDialog',
  components: { BaseDialog, FormSelect, FormAutocomplete, FormCheckbox }
})
export default class TorrentAddDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  @Prop(Array) downloaders!: AddDialogDownloaderRow[]

  @Ref('fileInputRef') readonly fileInputRef!: HTMLInputElement

  private loading = false
  private dragOver = false
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

  /** 下载器下拉选项（徽章/状态点机会渲染） */
  get downloaderOptions(): FormSelectOption[] {
    return this.downloaders.map(downloader => {
      const type = downloader.downloader_type ?? downloader.type
      const badge = type !== undefined ? DOWNLOADER_TYPE_BADGE[type] : undefined
      const rawStatus = downloader.connectStatus ?? downloader.status
      let status: 'online' | 'offline' | undefined
      if (rawStatus === 'online' || rawStatus === 'connected' || rawStatus === '1') {
        status = 'online'
      } else if (rawStatus === 'offline' || rawStatus === 'disconnected' || rawStatus === '0') {
        status = 'offline'
      }
      return {
        value: downloader.downloader_id,
        label: downloader.nickname,
        badge,
        status
      }
    })
  }

  /** 分类下拉选项 */
  get categoryOptions(): FormSelectOption[] {
    return this.categoryList.map(cat => ({ value: cat.tag_name, label: cat.tag_name }))
  }

  /** 标签下拉选项 */
  get tagOptions(): FormSelectOption[] {
    return this.tagList.map(tag => ({ value: tag.tag_name, label: tag.tag_name }))
  }

  /** 保存路径建议：启用路径按当前输入过滤（空输入=全部，便于浏览既有路径） */
  get pathSuggestions(): PathSuggestion[] {
    const query = this.form.save_path.trim().toLowerCase()
    return this.downloaderPaths
      .filter(path => path.is_enabled && (!query || path.path_value.toLowerCase().includes(query)))
      .map(path => ({
        value: path.path_value,
        path_type: path.path_type,
        torrent_count: path.torrent_count
      }))
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
      this.addFiles(Array.from(input.files))
    }
  }

  // 拖拽释放：与点击选择共用同一校验/追加路径
  handleDrop(event: DragEvent) {
    this.dragOver = false
    const files = Array.from(event.dataTransfer?.files ?? [])
    if (files.length === 0) return
    this.addFiles(files)
  }

  /** 追加文件（保持既有语义：出现非法文件仅报错、整批不追加） */
  private addFiles(files: File[]) {
    const invalidFiles = files.filter(file => !file.name.endsWith('.torrent'))
    if (invalidFiles.length > 0) {
      this.formErrors.torrent_file = this.$t('torrent.addDialog.error.onlyTorrent') as string
      return
    }

    this.torrentFiles = [...this.torrentFiles, ...files]
    this.selectedFileNames = this.torrentFiles.map(f => f.name)
    this.clearError('torrent_file')
  }

  // 清空全部已选文件
  clearAllFiles() {
    this.torrentFiles = []
    this.selectedFileNames = []
    this.formErrors.torrent_file = this.$t('torrent.addDialog.error.chooseFile') as string
  }

  // 删除单个文件
  removeFile(index: number) {
    this.torrentFiles.splice(index, 1)
    this.selectedFileNames = this.torrentFiles.map(f => f.name)

    if (this.torrentFiles.length === 0) {
      this.formErrors.torrent_file = this.$t('torrent.addDialog.error.chooseFile') as string
    }
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
    this.dragOver = false

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
// 表单布局
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

.required-mark {
  color: var(--color-error);
}

.form-error-tip {
  color: var(--color-error);
  font-size: 12px;
  margin-top: 4px;
}

// 表单提示文本（文件类型说明等）
.form-hint {
  font-size: 12px;
  color: var(--color-text-quaternary);
  margin-top: 6px;
  line-height: 1.5;
}

// ========================================
// 文件拖放区
// ========================================
.dropzone {
  border: 2px dashed var(--color-border-primary);
  border-radius: var(--radius-md);
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  outline: none;

  &:hover,
  &:focus-visible {
    border-color: var(--color-primary);
    background: rgba(var(--color-primary-rgb), 0.03);
  }

  &.is-dragover {
    border-color: var(--color-primary);
    background: rgba(var(--color-primary-rgb), 0.08);
  }

  &.has-error {
    border-color: var(--color-error);

    &:hover,
    &.is-dragover {
      border-color: var(--color-error);
      background: rgba(var(--color-error-rgb), 0.04);
    }
  }
}

.dropzone__input {
  display: none;
}

.dropzone__icon {
  color: var(--color-text-quaternary);
  margin-bottom: 8px;
  transition: color var(--transition-fast);

  .dropzone:hover &,
  .dropzone.is-dragover & {
    color: var(--color-primary);
  }
}

.dropzone__text {
  color: var(--color-text-secondary);
  font-size: 14px;
}

.dropzone__subtext {
  color: var(--color-text-quaternary);
  font-size: 12px;
  margin-top: 4px;
}

.dropzone__selected {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px;
  background: rgba(var(--color-primary-rgb), 0.06);
  border-radius: var(--radius-sm);
  color: var(--color-success-dark);
  font-weight: var(--font-weight-medium);
}

.dropzone__selected-icon {
  color: var(--color-success);
}

// ========================================
// 文件列表
// ========================================
.file-list {
  margin-top: 12px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  overflow: hidden;
}

.file-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border-primary);
}

.file-list__count {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.file-list__clear {
  border: none;
  background: transparent;
  color: var(--color-primary);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--radius-sm);

  &:hover {
    background: rgba(var(--color-primary-rgb), 0.1);
  }
}

.file-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border-secondary);

  &:last-child {
    border-bottom: none;
  }

  .file-item__icon {
    flex-shrink: 0;
    color: var(--color-text-tertiary);
    margin-right: 8px;
  }

  .file-item__name {
    flex: 1;
    font-size: 13px;
    color: var(--color-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file-item__size {
    margin: 0 12px;
    font-size: 12px;
    color: var(--color-text-tertiary);
    white-space: nowrap;
  }

  .file-item__remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 4px 8px;
    background: transparent;
    border: none;
    color: var(--color-text-secondary);
    cursor: pointer;
    border-radius: var(--radius-sm);
    transition: all var(--transition-fast);

    &:hover {
      background: var(--color-error);
      color: white;
    }
  }
}

// ========================================
// 路径建议行（FormAutocomplete 作用域插槽）
// ========================================
.path-suggestion {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  min-width: 0;

  .path-suggestion__value {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
    font-size: 12px;
  }

  .path-suggestion__type {
    flex-shrink: 0;
    padding: 1px 6px;
    font-size: 11px;
    border-radius: var(--radius-sm);

    &.is-default {
      background: var(--color-info-lightest);
      color: var(--color-info-dark);
    }

    &.is-active {
      background: var(--color-success-lightest);
      color: var(--color-success-dark);
    }
  }

  .path-suggestion__count {
    flex-shrink: 0;
    color: var(--color-text-tertiary);
    font-size: 11px;
  }
}

// ========================================
// 校验策略警示卡
// ========================================
.policy-card {
  border: 1px solid var(--color-warning);
  background: var(--color-warning-lightest);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  transition: all var(--transition-fast);

  &.is-active {
    border-color: var(--color-warning-dark);
    background: var(--color-warning-light);
  }
}

.policy-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.policy-card__icon {
  flex-shrink: 0;
  color: var(--color-warning-dark);
}

.policy-card__hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

// ========================================
// 底部摘要与按钮
// ========================================
.footer-summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.footer-summary__icon {
  color: var(--color-text-quaternary);
}

.btn-secondary {
  padding: 8px 16px;
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-weight: 500;
  font-size: 14px;
  transition: all var(--transition-fast);

  &:hover {
    background: var(--color-bg-tertiary);
  }
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  transition: all var(--transition-fast);

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

// loading 旋转图标
.is-spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

// ========================================
// 移动端适配（≤768）：弹窗壳（overlay/头部/底部布局）由 BaseDialog 负责，
// 此处只收敛插槽内容：底部按钮触控高、文件移除钮放大
// ========================================
@media (max-width: 768px) {
  // 底部按钮改纵向铺满：双钮等宽 + ≥44px 触控高
  .btn-secondary,
  .btn-primary {
    flex: 1;
    min-height: 44px;
    padding: 10px 16px;
  }

  // 文件移除触控目标放大（4px padding 桌面尺寸手指难命中）
  .file-item .file-item__remove {
    min-width: 36px;
    min-height: 36px;
    margin: -4px -4px -4px 0;
    padding: 4px 10px;
  }

  .dropzone {
    padding: 18px 12px;
  }

  .file-item {
    padding: 10px 8px;

    .file-item__size {
      margin: 0 8px;
    }
  }
}
</style>
