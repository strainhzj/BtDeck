<template>
  <div class="app-container management-page orphan-files-page">
    <header class="management-page__header" aria-labelledby="orphan-files-title">
      <div class="management-page__heading">
        <h1 id="orphan-files-title" class="management-page__title">孤儿文件</h1>
        <p class="management-page__subtitle">扫描未被种子引用的文件，并在清理前进行安全复核</p>
      </div>
      <div class="management-page__actions">
        <el-button
          icon="el-icon-refresh"
          :loading="listLoading"
          @click="refreshPageData()"
        >
          刷新
        </el-button>
        <el-button
          type="primary"
          icon="el-icon-magic-stick"
          :loading="scanLoading"
          @click="handleScan"
        >
          立即扫描
        </el-button>
      </div>
    </header>

    <!-- 统计摘要 -->
    <section class="management-stats-grid" aria-label="最近一次孤儿文件扫描摘要">
      <div class="management-stat-card">
        <span class="management-stat-card__icon" aria-hidden="true">
          <i class="el-icon-document" />
        </span>
        <div class="management-stat-card__content">
          <div class="management-stat-card__label">待清理文件数</div>
          <div class="management-stat-card__value">{{ scanContext.remaining_count }}</div>
        </div>
      </div>
      <div class="management-stat-card">
        <span class="management-stat-card__icon management-stat-card__icon--success" aria-hidden="true">
          <i class="el-icon-coin" />
        </span>
        <div class="management-stat-card__content">
          <div class="management-stat-card__label">待清理空间</div>
          <div class="management-stat-card__value">{{ formatSize(scanContext.remaining_size) }}</div>
        </div>
      </div>
      <div class="management-stat-card">
        <span class="management-stat-card__icon management-stat-card__icon--info" aria-hidden="true">
          <i class="el-icon-folder-opened" />
        </span>
        <div class="management-stat-card__content">
          <div class="management-stat-card__label">扫描路径数</div>
          <div class="management-stat-card__value">{{ displayScan ? displayScan.total_paths_scanned : 0 }}</div>
        </div>
      </div>
      <div class="management-stat-card">
        <span class="management-stat-card__icon management-stat-card__icon--warning" aria-hidden="true">
          <i class="el-icon-time" />
        </span>
        <div class="management-stat-card__content">
          <div class="management-stat-card__label">最近成功扫描</div>
          <div class="management-stat-card__value management-stat-card__value--compact">
            {{ displayScan ? formatTime(displayScan.scan_time) : '尚无成功扫描' }}
          </div>
        </div>
      </div>
    </section>

    <el-alert
      v-if="latestAttempt && latestAttempt.status === 'failed'"
      class="orphan-scan-state-alert"
      title="最近一次扫描失败"
      :description="scanStatusMessage"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="latestAttempt && latestAttempt.status === 'running'"
      class="orphan-scan-state-alert"
      title="孤儿文件扫描进行中"
      :description="scanStatusMessage"
      type="info"
      :closable="false"
      show-icon
    />

    <!-- 筛选条件 -->
    <section class="management-panel" aria-label="孤儿文件筛选条件">
      <div class="management-filter">
        <div class="management-filter__field management-filter__field--wide">
          <label class="management-filter__label" for="orphan-downloader-id">下载器 ID</label>
          <el-input
            id="orphan-downloader-id"
            v-model="listQuery.downloader_id"
            class="management-filter__control"
            placeholder="输入下载器 ID"
            prefix-icon="el-icon-search"
            clearable
            @keyup.enter.native="handleFilter"
            @clear="handleFilter"
          />
        </div>
        <div class="management-filter__actions">
          <el-button type="primary" icon="el-icon-search" @click="handleFilter">
            搜索
          </el-button>
        </div>
      </div>
    </section>

    <!-- 孤儿文件列表 -->
    <section class="management-panel" aria-labelledby="orphan-file-list-title">
      <div class="management-panel__header">
        <div class="management-panel__heading">
          <h2 id="orphan-file-list-title" class="management-panel__title">文件列表</h2>
          <p class="management-panel__description">
            {{ displayScan ? `展示成功扫描 ${formatTime(displayScan.scan_time)} 的剩余结果` : '完成首次成功扫描后将在此显示结果' }}
          </p>
        </div>
        <div class="management-panel__meta">
          <el-tag v-if="selectedIds.length > 0" type="info" effect="plain">
            已选择 {{ selectedIds.length }} 项
          </el-tag>
          <el-button
            type="danger"
            icon="el-icon-delete"
            :disabled="selectedIds.length === 0 || !cleanupAllowed"
            :title="cleanupAllowed ? '' : cleanupBlockReason"
            @click="handleCleanupPreview"
          >
            清理选中
          </el-button>
        </div>
      </div>
      <div class="management-table-scroll">
        <el-table
          ref="orphanTable"
          v-loading="listLoading"
          :data="list"
          class="management-table"
          border
          fit
          highlight-current-row
          empty-text="暂无孤儿文件，点击“立即扫描”开始检测"
          style="width: 100%"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="55" />
          <el-table-column label="文件路径" prop="file_path" min-width="300" show-overflow-tooltip />
          <el-table-column label="大小" width="120" align="center">
            <template slot-scope="scope">
              {{ formatSize(scope.row.file_size) }}
            </template>
          </el-table-column>
          <el-table-column label="修改时间" width="170" align="center">
            <template slot-scope="scope">
              {{ scope.row.mtime ? formatTime(scope.row.mtime) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="下载器" width="120" align="center">
            <template slot-scope="scope">
              <span>{{ scope.row.downloader_id ? maskId(scope.row.downloader_id) : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template slot-scope="scope">
              <el-tag v-if="scope.row.is_deleted" type="info" size="small">已清理</el-tag>
              <el-tag v-else type="danger" size="small">待清理</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 分页 -->
      <div class="management-pagination">
        <el-pagination
          background
          :current-page="listQuery.page"
          :page-size="listQuery.page_size"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </section>

    <!-- 清理确认对话框 -->
    <el-dialog
      title="清理确认"
      :visible.sync="cleanupDialogVisible"
      width="500px"
      :close-on-click-modal="false"
      custom-class="management-dialog"
    >
      <div v-loading="cleanupLoading">
        <el-alert
          v-if="cleanupPreviewData"
          title="确认清理以下孤儿文件？此操作不可恢复！"
          type="warning"
          :closable="false"
          show-icon
        >
          <template slot="default">
            <p>文件数量: <strong>{{ cleanupPreviewData.total_count }}</strong></p>
            <p>总大小: <strong>{{ formatSize(cleanupPreviewData.total_size) }}</strong></p>
          </template>
        </el-alert>
        <div v-if="cleanupResult" class="cleanup-result">
          <el-alert
            :title="`清理完成: 成功 ${cleanupResult.success_count} 个`"
            :type="cleanupResult.failed_count > 0 ? 'warning' : 'success'"
            :closable="false"
            show-icon
          >
            <template slot="default">
              <p v-if="cleanupResult.failed_count > 0">失败: {{ cleanupResult.failed_count }} 个</p>
              <p>释放空间: {{ formatSize(cleanupResult.total_size) }}</p>
            </template>
          </el-alert>
        </div>
      </div>
      <span slot="footer" class="dialog-footer">
        <el-button @click="handleCloseCleanupDialog">关闭</el-button>
        <el-button
          v-if="cleanupPreviewData && !cleanupResult"
          type="danger"
          :loading="cleanupExecuting"
          @click="handleCleanupConfirm"
        >
          确认清理
        </el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import {
  getOrphanList,
  triggerScan,
  cleanupPreview,
  cleanupOrphans,
  OrphanFileItem,
  OrphanListParams,
  OrphanScanContext,
  OrphanScanRecord,
  CleanupPreviewSuccess,
  CleanupSuccessResult
} from '@/api/orphan-files'
import { formatFileSize, formatDate, extractErrorMessage } from '@/utils/formatters'

interface OrphanListQuery {
  page: number
  page_size: number
  downloader_id: string
}

interface OrphanTableRef extends Vue {
  clearSelection: () => void
}

@Component({ name: 'OrphanFiles' })
export default class OrphanFiles extends Vue {
  private list: OrphanFileItem[] = []
  private total = 0
  private listLoading = false
  private scanLoading = false
  private listQuery: OrphanListQuery = {
    page: 1,
    page_size: 20,
    downloader_id: ''
  }
  private refreshRequestSeq = 0

  // 选中状态
  private selectedIds: number[] = []

  // 页面列表、统计和清理门禁共用的后端权威快照
  private scanContext: OrphanScanContext = {
    latest_attempt: null,
    display_scan: null,
    remaining_count: 0,
    remaining_size: 0,
    cleanup_allowed: false,
    cleanup_block_reason: '尚无可清理的成功扫描'
  }

  // 清理对话框
  private cleanupDialogVisible = false
  private cleanupLoading = false
  private cleanupExecuting = false
  private cleanupPreviewData: CleanupPreviewSuccess | null = null
  private cleanupResult: CleanupSuccessResult | null = null
  private previewScanId: string | null = null
  private previewOrphanIds: number[] = []

  mounted() {
    void this.refreshPageData()
  }

  beforeDestroy() {
    this.refreshRequestSeq += 1
  }

  private get latestAttempt(): OrphanScanRecord | null {
    return this.scanContext.latest_attempt
  }

  private get displayScan(): OrphanScanRecord | null {
    return this.scanContext.display_scan
  }

  private get cleanupAllowed(): boolean {
    return Boolean(
      this.scanContext.cleanup_allowed &&
      this.scanContext.display_scan &&
      this.scanContext.display_scan.scan_id
    )
  }

  private get cleanupBlockReason(): string {
    return this.scanContext.cleanup_block_reason || '当前扫描快照不允许清理'
  }

  private get scanStatusMessage(): string {
    const latest = this.latestAttempt
    if (!latest) return ''
    if (latest.status === 'running') {
      return '扫描正在进行中，完成前列表与统计保持为空，清理功能暂不可用。'
    }
    if (latest.status === 'failed') {
      const reason = latest.error_message || '未知错误'
      if (this.displayScan) {
        return `失败原因：${reason}。当前只读展示最近一次成功扫描的剩余结果，重新扫描成功前不可清理。`
      }
      return `失败原因：${reason}。当前尚无可展示的成功扫描结果。`
    }
    return ''
  }

  private async refreshPageData(allowPageCorrection = true): Promise<void> {
    const requestId = ++this.refreshRequestSeq
    const querySnapshot: Readonly<OrphanListQuery> = Object.freeze({
      page: this.listQuery.page,
      page_size: this.listQuery.page_size,
      downloader_id: this.listQuery.downloader_id
    })
    this.listLoading = true
    try {
      const params: OrphanListParams = {
        page: querySnapshot.page,
        page_size: querySnapshot.page_size,
        downloader_id: querySnapshot.downloader_id || undefined
      }
      const response = await getOrphanList(params)
      if (requestId !== this.refreshRequestSeq) return

      if (response.code === '200' && response.data) {
        const maxPage = Math.max(
          1,
          Math.ceil(response.data.total / querySnapshot.page_size)
        )
        if (
          allowPageCorrection &&
          querySnapshot.page > maxPage
        ) {
          this.listQuery.page = maxPage
          await this.refreshPageData(false)
          return
        }

        this.list = response.data.list
        this.total = response.data.total
        this.scanContext = response.data.scan_context
        this.selectedIds = []
        const table = this.$refs.orphanTable as OrphanTableRef | undefined
        if (table && typeof table.clearSelection === 'function') {
          table.clearSelection()
        }
      } else {
        this.$message.error(response.msg || '获取列表失败')
      }
    } catch (error) {
      if (requestId !== this.refreshRequestSeq) return
      this.$message.error('获取孤儿文件列表失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      if (requestId === this.refreshRequestSeq) {
        this.listLoading = false
      }
    }
  }

  private handleFilter() {
    this.listQuery.page = 1
    void this.refreshPageData()
  }

  private handleSizeChange(size: number) {
    this.listQuery.page_size = size
    this.listQuery.page = 1
    void this.refreshPageData()
  }

  private handleCurrentChange(page: number) {
    this.listQuery.page = page
    void this.refreshPageData()
  }

  private handleSelectionChange(rows: OrphanFileItem[]) {
    this.selectedIds = rows.map((r) => r.id)
  }

  private async handleScan() {
    try {
      await this.$confirm('确认立即扫描孤儿文件？扫描可能需要较长时间。', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'info'
      })
    } catch {
      return // 用户取消
    }

    this.scanLoading = true
    try {
      const response = await triggerScan()
      if (response.code === '200' && response.data) {
        const data = response.data
        if (data.status === 'completed') {
          this.$message.success(`扫描完成: 发现 ${data.total_orphans} 个孤儿文件`)
        } else if (data.status === 'busy') {
          this.$message.warning(data.error || '孤儿文件维护任务正在进行')
        } else {
          this.$message.warning(`扫描失败: ${data.error}`)
        }
      } else {
        this.$message.error(response.msg || '扫描失败')
      }
    } catch (error) {
      this.$message.error('扫描失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      await this.refreshPageData()
      this.scanLoading = false
    }
  }

  private async handleCleanupPreview() {
    if (this.selectedIds.length === 0) {
      this.$message.warning('请先选择要清理的文件')
      return
    }
    const displayScan = this.displayScan
    if (!this.cleanupAllowed || !displayScan) {
      this.$message.warning(this.cleanupBlockReason)
      return
    }

    this.cleanupDialogVisible = true
    this.cleanupPreviewData = null
    this.cleanupResult = null
    this.previewScanId = displayScan.scan_id
    this.previewOrphanIds = [...this.selectedIds]
    this.cleanupLoading = true

    try {
      const response = await cleanupPreview({
        scan_id: this.previewScanId,
        orphan_ids: this.previewOrphanIds
      })
      if (response.code === '200' && response.data) {
        if (response.data.rejected === true) {
          this.$message.error(response.data.error || response.data.reason)
          this.cleanupDialogVisible = false
          await this.refreshPageData()
        } else {
          this.cleanupPreviewData = response.data
        }
      } else {
        this.$message.error(response.msg || '预览失败')
        this.cleanupDialogVisible = false
      }
    } catch (error) {
      this.$message.error('预览失败：' + extractErrorMessage(error, '网络错误'))
      this.cleanupDialogVisible = false
    } finally {
      this.cleanupLoading = false
    }
  }

  private async handleCleanupConfirm() {
    this.cleanupExecuting = true
    try {
      if (!this.previewScanId) {
        this.$message.warning('扫描批次已失效，请刷新后重试')
        return
      }
      const response = await cleanupOrphans({
        scan_id: this.previewScanId,
        orphan_ids: this.previewOrphanIds
      })
      if (response.code === '200' && response.data) {
        if (response.data.rejected === true) {
          this.$message.error(response.data.error || this.cleanupBlockReason)
          this.cleanupDialogVisible = false
        } else {
          this.cleanupResult = response.data
        }
        await this.refreshPageData()
      } else {
        this.$message.error(response.msg || '清理失败')
      }
    } catch (error) {
      this.$message.error('清理失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      this.cleanupExecuting = false
    }
  }

  private handleCloseCleanupDialog() {
    this.cleanupDialogVisible = false
    this.cleanupPreviewData = null
    this.cleanupResult = null
    this.previewScanId = null
    this.previewOrphanIds = []
  }

  // ========== 工具方法 ==========

  private formatSize(size: number): string {
    return formatFileSize(size)
  }

  private formatTime(time: string | null): string {
    if (!time) return '-'
    return formatDate(time)
  }

  private maskId(id: string): string {
    if (!id || id.length <= 8) return id
    return id.substring(0, 4) + '****' + id.substring(id.length - 4)
  }
}
</script>

<style lang="scss" scoped>
.orphan-files-page {
  .orphan-scan-state-alert {
    margin-bottom: var(--spacing-lg);
  }

  .cleanup-result {
    margin-top: var(--spacing-md);
  }
}

::v-deep .management-dialog {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);

  .el-dialog__header,
  .el-dialog__footer {
    padding: var(--spacing-lg);
  }

  .el-dialog__header {
    border-bottom: 1px solid var(--color-border-primary);
  }

  .el-dialog__body {
    padding: var(--spacing-lg);
  }

  .el-dialog__footer {
    border-top: 1px solid var(--color-border-primary);
  }
}

@media (max-width: 600px) {
  ::v-deep .management-dialog {
    width: calc(100% - 32px) !important;
  }
}
</style>
