<template>
  <div>
    <el-dialog
      title="快捷删除重复种子"
      :visible.sync="dialogVisible"
      width="820px"
      :before-close="handleClose"
      :close-on-click-modal="false"
      append-to-body
    >
      <!-- 配置区 -->
      <div class="qdd-config">
        <div class="qdd-field">
          <label class="qdd-label">
            待检测下载器
            <span class="qdd-required">*</span>
          </label>
          <AdvancedMultiSelect
            v-model="detectDownloaderIds"
            :options="downloaderOptions"
            :allow-create="false"
            :show-mode-toggle="false"
            :list-height="200"
            class="qdd-control"
          />
          <div class="qdd-field-hint">选择 2 个及以上下载器，用于在其间查找重复种子</div>
        </div>

        <div class="qdd-field">
          <label class="qdd-label">
            保留下载器
            <span class="qdd-required">*</span>
          </label>
          <AdvancedMultiSelect
            v-model="keepDownloaderIds"
            :options="keepOptions"
            :allow-create="false"
            :show-mode-toggle="false"
            :list-height="200"
            class="qdd-control"
          />
          <div class="qdd-field-hint">这些下载器中的重复种子将被保留，其余下载器中的重复种子将被删除（只删种子、不删文件）</div>
        </div>

        <el-button
          type="primary"
          icon="el-icon-view"
          :loading="previewLoading"
          @click="handlePreview"
        >
          预览重复
        </el-button>
      </div>

      <el-divider />

      <!-- 预览区 -->
      <div v-if="previewLoading" class="qdd-state">
        <i class="el-icon-loading qdd-state-icon" />
        <span>正在分析重复种子...</span>
      </div>

      <el-alert
        v-else-if="previewError"
        :title="previewError"
        type="error"
        :closable="false"
        show-icon
        class="qdd-error"
      />

      <template v-else-if="preview">
        <!-- 汇总与 skipped 提醒 -->
        <div class="qdd-summary">
          <span class="qdd-summary-item">
            共 <strong>{{ preview.total_groups }}</strong> 组重复
          </span>
          <span class="qdd-summary-item">
            将删除
            <strong class="qdd-summary-delete">{{ preview.total_delete }}</strong>
            个种子
          </span>
          <span v-if="preview.skipped_groups > 0" class="qdd-skipped-hint">
            <el-tooltip
              content="这些重复仅在待删下载器间存在、无保留副本，为避免丢失最后一份数据已跳过，不会删除"
              placement="top"
            >
              <span>⚠ 另有 {{ preview.skipped_groups }} 组已跳过（无保留副本）</span>
            </el-tooltip>
          </span>
        </div>

        <!-- 空状态 -->
        <div v-if="preview.list.length === 0" class="qdd-state">
          <i class="el-icon-circle-check qdd-state-icon qdd-state-success" />
          <span>未在所选下载器间发现可删除的重复种子</span>
        </div>

        <!-- 分组列表 -->
        <div v-else class="qdd-groups">
          <div
            v-for="group in preview.list"
            :key="group.hash"
            class="qdd-group"
            :class="{'is-skipped': group.skipped}"
          >
            <div class="qdd-group-header">
              <span class="qdd-group-name" :title="group.name">{{ group.name || '（无名称）' }}</span>
              <span v-if="group.skipped" class="qdd-group-badge">已跳过</span>
              <span class="qdd-group-hash" :title="group.hash">{{ shortHash(group.hash) }}</span>
              <span class="qdd-group-size">{{ formatSize(group.size) }}</span>
            </div>
            <div v-if="group.skipped" class="qdd-skipped-body">
              <div class="qdd-skipped-text">这些副本仅在待删下载器间存在，无保留副本，为避免丢失最后一份数据已跳过（不会删除）</div>
              <div class="qdd-skipped-items">
                <span v-for="item in group.to_delete" :key="item.info_id" class="qdd-item is-skipped">
                  {{ item.downloader_name }}
                </span>
              </div>
            </div>
            <div v-else class="qdd-group-body">
              <div class="qdd-col">
                <div class="qdd-col-title is-delete">将被删除</div>
                <div v-for="item in group.to_delete" :key="item.info_id" class="qdd-item is-delete">
                  <span class="qdd-item-downloader">{{ item.downloader_name }}</span>
                  <span class="qdd-item-status">{{ item.status }}</span>
                </div>
                <div v-if="group.to_delete.length === 0" class="qdd-col-empty">—</div>
              </div>
              <div class="qdd-col">
                <div class="qdd-col-title is-keep">保留副本</div>
                <div v-for="item in group.kept" :key="item.info_id" class="qdd-item is-keep">
                  <span class="qdd-item-downloader">{{ item.downloader_name }}</span>
                  <span class="qdd-item-status">{{ item.status }}</span>
                </div>
                <div v-if="group.kept.length === 0" class="qdd-col-empty">—</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 分页 -->
        <el-pagination
          v-if="preview.total > pageSize"
          class="qdd-pagination"
          layout="total, prev, pager, next"
          :current-page.sync="currentPage"
          :page-size="pageSize"
          :total="preview.total"
          @current-change="handlePageChange"
        />
      </template>

      <span slot="footer" class="dialog-footer">
        <el-button @click="handleClose">关闭</el-button>
        <el-button
          type="danger"
          :loading="deleteLoading"
          :disabled="!preview || preview.total_delete === 0"
          @click="handleDelete"
        >
          确认删除{{ preview && preview.total_delete > 0 ? `（${preview.total_delete}个）` : '' }}
        </el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import AdvancedMultiSelect from '@/components/torrents/AdvancedMultiSelect.vue'
import type { SelectOption } from '@/components/torrents/AdvancedMultiSelect.vue'
import {
  getDownloaderList,
  getQuickDeleteDuplicatePreview,
  quickDeleteDuplicates,
  getBatchDeleteStatus,
  type QuickDeletePreviewResponse
} from '@/api/torrents'
import { formatFileSize, extractErrorMessage } from '@/utils/formatters'

@Component({
  name: 'QuickDeleteDuplicatesDialog',
  components: { AdvancedMultiSelect }
})
export default class QuickDeleteDuplicatesDialog extends Vue {
  @Prop({ type: Boolean, default: false }) readonly visible!: boolean

  // 对话框显示状态
  private dialogVisible = false

  // 下载器选项
  private downloaderOptions: SelectOption[] = []

  // 选择状态
  private detectDownloaderIds: (string | number)[] = []
  private keepDownloaderIds: (string | number)[] = []

  // 预览状态
  private previewLoading = false
  private previewError = ''
  private preview: QuickDeletePreviewResponse | null = null
  private currentPage = 1
  private readonly pageSize = 20

  // 删除状态
  private deleteLoading = false

  /** 保留下载器选项：仅列出已选待检测下载器 */
  get keepOptions(): SelectOption[] {
    const detectSet = new Set(this.detectDownloaderIds.map(id => String(id)))
    return this.downloaderOptions.filter(opt => detectSet.has(String(opt.value)))
  }

  get canPreview(): boolean {
    if (this.detectDownloaderIds.length < 2) return false
    if (this.keepDownloaderIds.length < 1) return false
    const detectSet = new Set(this.detectDownloaderIds.map(id => String(id)))
    return this.keepDownloaderIds.every(id => detectSet.has(String(id)))
  }

  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.initDialog()
    }
  }

  /** 待检测下载器变化时，联动剪裁保留下载器为子集 */
  @Watch('detectDownloaderIds', { deep: true })
  onDetectChange() {
    const detectSet = new Set(this.detectDownloaderIds.map(id => String(id)))
    const next = this.keepDownloaderIds.filter(id => detectSet.has(String(id)))
    if (next.length !== this.keepDownloaderIds.length) {
      this.keepDownloaderIds = next
    }
  }

  private async initDialog() {
    this.previewLoading = false
    this.previewError = ''
    this.preview = null
    this.currentPage = 1
    this.detectDownloaderIds = []
    this.keepDownloaderIds = []
    this.deleteLoading = false
    await this.loadDownloaders()
  }

  private async loadDownloaders() {
    try {
      const resp = await getDownloaderList({ enabled: true })
      const list = resp.data || []
      this.downloaderOptions = list.map((dl: any) => ({
        value: dl.downloader_id,
        label: dl.nickname || dl.downloader_id
      }))
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    }
  }

  private async fetchPreview(page = 1) {
    this.previewLoading = true
    this.previewError = ''
    try {
      const resp = await getQuickDeleteDuplicatePreview({
        downloader_ids: this.detectDownloaderIds.map(id => String(id)),
        keep_downloader_ids: this.keepDownloaderIds.map(id => String(id)),
        page,
        pageSize: this.pageSize
      })
      if (resp.code === '200') {
        this.preview = resp.data
      } else {
        this.previewError = resp.msg || '查询失败'
        this.preview = null
      }
    } catch (e) {
      this.previewError = extractErrorMessage(e)
      this.preview = null
    } finally {
      this.previewLoading = false
    }
  }

  private async handlePreview() {
    if (!this.canPreview) {
      this.$message.warning('请选择至少 2 个待检测下载器，并至少选择 1 个保留下载器')
      return
    }
    this.currentPage = 1
    await this.fetchPreview(1)
  }

  private async handlePageChange(page: number) {
    this.currentPage = page
    await this.fetchPreview(page)
  }

  private async handleDelete() {
    if (!this.preview || this.preview.total_delete === 0) return
    this.deleteLoading = true
    try {
      const resp = await quickDeleteDuplicates({
        downloader_ids: this.detectDownloaderIds.map(id => String(id)),
        keep_downloader_ids: this.keepDownloaderIds.map(id => String(id)),
        delete_level: 2,
        notify_on_complete: true
      })
      if (resp.code !== '200') {
        this.$message.error(resp.msg || '提交删除任务失败')
        return
      }
      if (!resp.data.task_id) {
        this.$message.info(resp.msg || '未发现可删除的重复种子')
        this.$emit('deleted')
        return
      }
      const skippedText = resp.data.skipped_count
        ? `，跳过处理中 ${resp.data.skipped_count} 个`
        : ''
      this.$message.success(`已提交删除任务（共 ${resp.data.total_count} 个种子${skippedText}）`)
      this.$emit('deleted')
      // 后台轮询完成状态，仅用于结果提示（不阻塞对话框）
      void this.pollDeleteStatus(resp.data.task_id)
    } catch (e) {
      this.$message.error(extractErrorMessage(e))
    } finally {
      this.deleteLoading = false
    }
  }

  private async pollDeleteStatus(taskId: string) {
    // 最多轮询 40 次 * 1.5s = 60s
    for (let i = 0; i < 40; i++) {
      await this.delay(1500)
      try {
        const resp = await getBatchDeleteStatus(taskId)
        if (resp.code !== '200') continue
        const st = resp.data
        if (st.status === 'completed' || st.status === 'partial' || st.status === 'failed') {
          const msg = `删除任务${st.status === 'completed' ? '完成' : st.status === 'partial' ? '部分完成' : '失败'}：成功 ${st.success_count}，失败 ${st.failed_count}`
          if (st.status === 'failed') {
            this.$message.error(msg)
          } else if (st.status === 'partial') {
            this.$message.warning(msg)
          } else {
            this.$message.success(msg)
          }
          return
        }
      } catch (e) {
        // 轮询失败继续尝试
      }
    }
    this.$message.info('删除任务仍在后台执行，可稍后在通知中心查看结果')
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  private shortHash(hash: string): string {
    if (!hash) return ''
    return hash.length > 16 ? `${hash.slice(0, 8)}…${hash.slice(-6)}` : hash
  }

  private formatSize(size: number | null | undefined): string {
    return formatFileSize(size)
  }

  private handleClose() {
    this.dialogVisible = false
    this.$emit('close')
  }
}
</script>

<style lang="scss" scoped>
.qdd-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.qdd-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.qdd-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.qdd-required {
  color: var(--theme-error, #f56c6c);
}

.qdd-field-hint {
  font-size: 12px;
  color: var(--color-text-secondary, #909399);
  line-height: 1.4;
}

.qdd-control {
  width: 100%;
}

.qdd-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--color-text-secondary, #909399);
  font-size: 14px;
}

.qdd-state-icon {
  font-size: 20px;
}

.qdd-state-success {
  color: var(--theme-success, #67c23a);
}

.qdd-error {
  margin-bottom: 8px;
}

.qdd-summary {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 10px 12px;
  background: var(--color-bg-secondary, #f5f7fa);
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--color-text-secondary, #606266);
  flex-wrap: wrap;
}

.qdd-summary-item {
  strong {
    color: var(--color-primary, #409eff);
  }
  .qdd-summary-delete {
    color: var(--theme-error, #f56c6c);
  }
}

.qdd-skipped-hint {
  cursor: help;
  color: var(--theme-warning, #e6a23c);
}

.qdd-groups {
  max-height: 380px;
  overflow-y: auto;
  border: 1px solid var(--color-border-primary, #ebeef5);
  border-radius: 6px;
}

.qdd-group {
  border-bottom: 1px solid var(--color-border-primary, #ebeef5);

  &:last-child {
    border-bottom: none;
  }

  &.is-skipped {
    .qdd-group-header {
      background: rgba(230, 162, 60, 0.08);
    }
  }
}

.qdd-group-badge {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  background: rgba(230, 162, 60, 0.15);
  color: var(--theme-warning, #e6a23c);
  border: 1px solid rgba(230, 162, 60, 0.35);
}

.qdd-skipped-body {
  padding: 8px 12px;
}

.qdd-skipped-text {
  font-size: 12px;
  color: var(--theme-warning, #e6a23c);
  margin-bottom: 6px;
}

.qdd-skipped-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.qdd-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  margin: 0 6px 4px 0;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;

  &.is-delete {
    background: rgba(245, 108, 108, 0.1);
    color: var(--theme-error, #f56c6c);
  }

  &.is-keep {
    background: rgba(103, 194, 58, 0.1);
    color: var(--theme-success, #67c23a);
  }

  &.is-skipped {
    background: rgba(230, 162, 60, 0.12);
    color: var(--theme-warning, #e6a23c);
  }

  .qdd-item-status {
    opacity: 0.75;
  }
}

.qdd-group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--color-bg-secondary, #f5f7fa);

  .qdd-group-name {
    flex: 1;
    font-size: 13px;
    font-weight: 600;
    color: var(--color-text-primary, #303133);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .qdd-group-hash {
    font-family: 'Courier New', monospace;
    font-size: 11px;
    color: var(--color-text-secondary, #909399);
  }

  .qdd-group-size {
    font-size: 12px;
    color: var(--color-text-secondary, #909399);
    white-space: nowrap;
  }
}

.qdd-group-body {
  display: flex;

  .qdd-col {
    flex: 1;
    padding: 8px 12px;
    min-width: 0;
  }

  .qdd-col + .qdd-col {
    border-left: 1px dashed var(--color-border-primary, #ebeef5);
  }
}

.qdd-col-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 6px;

  &.is-delete {
    color: var(--theme-error, #f56c6c);
  }

  &.is-keep {
    color: var(--theme-success, #67c23a);
  }
}

.qdd-col-empty {
  color: var(--color-text-tertiary, #c0c4cc);
  font-size: 12px;
}

.qdd-pagination {
  margin-top: 12px;
  text-align: right;
}
</style>
