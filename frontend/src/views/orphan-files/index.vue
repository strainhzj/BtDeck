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

    <!-- 页面 Tab：孤儿文件 / 隔离区 -->
    <el-tabs v-model="activeTab" class="orphan-files-tabs" @tab-click="handleTabSwitch">
      <el-tab-pane label="孤儿文件" name="orphans">
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
          <i class="el-icon-warning-outline" />
        </span>
        <div class="management-stat-card__content">
          <div class="management-stat-card__label">已忽视文件数</div>
          <div class="management-stat-card__value">{{ scanContext.ignored_count }}</div>
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
        <div class="management-filter__field">
          <label class="management-filter__label" for="orphan-path-like">文件路径</label>
          <el-input
            id="orphan-path-like"
            v-model="listQuery.path_like"
            class="management-filter__control"
            placeholder="路径关键字模糊匹配"
            prefix-icon="el-icon-search"
            clearable
            @keyup.enter.native="handleFilter"
            @clear="handleFilter"
          />
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="orphan-downloader">下载器</label>
          <el-select
            id="orphan-downloader"
            v-model="listQuery.downloader_id"
            class="management-filter__control"
            placeholder="全部下载器"
            clearable
            filterable
            @change="handleFilter"
          >
            <el-option
              v-for="opt in downloaderOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="orphan-status">状态</label>
          <el-select
            id="orphan-status"
            v-model="listQuery.status"
            class="management-filter__control"
            placeholder="全部状态"
            clearable
            @change="handleFilter"
          >
            <el-option label="待清理" value="pending" />
            <el-option label="已忽视" value="ignored" />
            <el-option label="已清理" value="deleted" />
          </el-select>
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="orphan-min-size">最小大小(字节)</label>
          <el-input
            id="orphan-min-size"
            v-model.number="listQuery.min_size"
            class="management-filter__control"
            placeholder="如 10485760"
            type="number"
            clearable
            @keyup.enter.native="handleFilter"
            @clear="handleFilter"
          />
        </div>
        <div class="management-filter__actions">
          <el-button type="primary" icon="el-icon-search" @click="handleFilter">
            搜索
          </el-button>
          <el-button icon="el-icon-refresh-left" @click="handleResetFilter">
            重置
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
            :disabled="!canBatchCleanup"
            :title="batchCleanupTitle"
            @click="handleCleanupPreview"
          >
            清理选中
          </el-button>
          <el-button
            icon="el-icon-warning-outline"
            :disabled="!canBatchIgnore"
            :title="batchIgnoreTitle"
            @click="handleBatchIgnore(true)"
          >
            忽视选中
          </el-button>
          <el-button
            icon="el-icon-circle-check"
            :disabled="!canBatchUnignore"
            :title="batchUnignoreTitle"
            @click="handleBatchIgnore(false)"
          >
            取消忽视
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
          <el-table-column type="selection" width="55" :selectable="rowSelectable" />
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
          <el-table-column label="下载器" width="140" align="center" show-overflow-tooltip>
            <template slot-scope="scope">
              <span>{{ scope.row.downloader_name || (scope.row.downloader_id ? maskId(scope.row.downloader_id) : '-') }}</span>
            </template>
          </el-table-column>
          <el-table-column label="置信度" width="100" align="center">
            <template slot-scope="scope">
              <el-tooltip
                v-if="scope.row.confidence === 'low'"
                content="离线降级目录粗筛判定，有误判风险；手动清理可删，自动清理需等下载器上线精筛"
                placement="top"
              >
                <el-tag type="info" size="small">低</el-tag>
              </el-tooltip>
              <el-tooltip v-else content="在线精筛判定，确认未被任何种子引用" placement="top">
                <el-tag type="success" size="small">高</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template slot-scope="scope">
              <el-tag v-if="scope.row.is_deleted" type="info" size="small">已清理</el-tag>
              <el-tag v-else-if="scope.row.is_ignored" type="warning" size="small">已忽视</el-tag>
              <el-tag v-else type="danger" size="small">待清理</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center" fixed="right">
            <template slot-scope="scope">
              <el-button
                v-if="!scope.row.is_deleted && !scope.row.is_ignored"
                type="text"
                size="small"
                @click="handleRowIgnore(scope.row, true)"
              >
                忽视
              </el-button>
              <el-button
                v-else-if="!scope.row.is_deleted && scope.row.is_ignored"
                type="text"
                size="small"
                @click="handleRowIgnore(scope.row, false)"
              >
                取消忽视
              </el-button>
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 分页：复用种子列表列表模式同款（PageSizeCombobox + 自定义翻页按钮 + 文字汇总） -->
      <nav class="torrent-pagination management-pagination">
        <div class="pagination-info">
          <PageSizeCombobox
            ref="pageSizeCombobox"
            :append-to-body="true"
            v-model="pageSizeInput"
            :page-size="listQuery.page_size"
            :options="pageSizeOptions"
            :expanded="pageSizeDropdownExpanded"
            controls-id="orphan-page-size-options"
            @focus="handlePageSizeFocus"
            @blur="handlePageSizeBlur"
            @toggle="togglePageSizeDropdown"
            @apply="applyPageSizeSelection"
            @select="handlePageSizeSelect"
          />
          <span class="pagination-summary">共 <strong>{{ total }}</strong> 条，第 <strong>{{ listQuery.page }}</strong>/<strong>{{ totalPages }}</strong> 页</span>
        </div>
        <div class="pagination-controls">
          <button
            class="pagination-btn"
            :disabled="listQuery.page <= 1"
            @click="handlePageChange(listQuery.page - 1)"
          >
            <LucideIcon name="chevron-left" :size="14" />
          </button>
          <button
            v-for="page in visiblePages"
            :key="page"
            class="pagination-btn"
            :class="{active: page === listQuery.page}"
            @click="handlePageChange(page)"
          >
            {{ page }}
          </button>
          <button
            class="pagination-btn"
            :disabled="listQuery.page >= totalPages"
            @click="handlePageChange(listQuery.page + 1)"
          >
            <LucideIcon name="chevron-right" :size="14" />
          </button>
        </div>
      </nav>
    </section>
      </el-tab-pane>

      <!-- 隔离区管理 -->
      <el-tab-pane label="隔离区" name="quarantine">
        <section class="management-panel" aria-labelledby="quarantine-list-title">
          <div class="management-panel__header">
            <div class="management-panel__heading">
              <h2 id="quarantine-list-title" class="management-panel__title">隔离区文件</h2>
              <p class="management-panel__subtitle">
                已清理文件暂存于此（保留期 {{ quarantineRetentionDays }} 天），可恢复到原位置或立即彻底删除
              </p>
            </div>
            <div class="management-panel__meta">
              <el-tag v-if="quarantineSelected.length > 0" type="info" effect="plain">
                已选择 {{ quarantineSelected.length }} 项
              </el-tag>
              <el-button
                type="success"
                icon="el-icon-refresh-left"
                :disabled="quarantineSelected.length === 0"
                :loading="restoreExecuting"
                @click="handleQuarantineRestore"
              >
                恢复选中
              </el-button>
              <el-button
                type="danger"
                icon="el-icon-delete-solid"
                :disabled="quarantineSelected.length === 0"
                :loading="purgeExecuting"
                @click="handleQuarantinePurge"
              >
                彻底删除选中
              </el-button>
              <el-button icon="el-icon-refresh" :loading="quarantineLoading" @click="loadQuarantineList">
                刷新
              </el-button>
            </div>
          </div>
          <div class="management-table-scroll">
            <el-table
              ref="quarantineTable"
              v-loading="quarantineLoading"
              :data="quarantineList"
              border
              stripe
              @selection-change="handleQuarantineSelectionChange"
            >
              <el-table-column type="selection" width="55" />
              <el-table-column label="原位置（规范化路径）" prop="canonical_path" min-width="300" show-overflow-tooltip />
              <el-table-column label="大小" width="120" align="center">
                <template slot-scope="{row}">
                  {{ formatSize(row.file_size) }}
                </template>
              </el-table-column>
              <el-table-column label="隔离时间" width="170" align="center">
                <template slot-scope="{row}">
                  {{ formatIsoTime(row.quarantined_at) }}
                </template>
              </el-table-column>
              <el-table-column label="预计删除" width="170" align="center">
                <template slot-scope="{row}">
                  {{ formatIsoTime(row.purge_after) }}
                </template>
              </el-table-column>
              <el-table-column label="下载器" width="140" align="center" show-overflow-tooltip>
                <template slot-scope="{row}">
                  {{ row.downloader_name || row.downloader_id || '-' }}
                </template>
              </el-table-column>
            </el-table>
          </div>
          <nav class="management-pagination" aria-label="隔离区分页">
            <span class="management-pagination__total">共 {{ quarantineTotal }} 条</span>
            <el-pagination
              background
              :current-page.sync="quarantinePage"
              :page-size="quarantinePageSize"
              :total="quarantineTotal"
              layout="prev, pager, next"
              @current-change="loadQuarantineList"
            />
          </nav>
        </section>
      </el-tab-pane>
    </el-tabs>

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
        <el-alert
          v-if="cleanupPreviewData && (cleanupPreviewData.low_confidence_count || 0) > 0"
          class="cleanup-low-confidence-warn"
          :title="`其中 ${cleanupPreviewData.low_confidence_count} 个为低置信度（离线降级目录粗筛判定）`"
          type="error"
          :closable="false"
          show-icon
        >
          <template slot="default">
            <p>低置信度文件有误判风险（可能并非真正的孤儿）。确认清理前请核对路径，避免误删用户数据。</p>
          </template>
        </el-alert>
      </div>
      <span slot="footer" class="dialog-footer">
        <el-button @click="handleCloseCleanupDialog">关闭</el-button>
        <el-button
          v-if="cleanupPreviewData"
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
  setIgnored,
  getQuarantineList,
  restoreQuarantined,
  purgeQuarantineNow,
  OrphanFileItem,
  OrphanListParams,
  OrphanScanContext,
  OrphanScanRecord,
  OrphanStatusFilter,
  CleanupPreviewSuccess,
  QuarantineItem
} from '@/api/orphan-files'
import { getDownloaderList, DownloaderSimple } from '@/api/torrents'
import { formatFileSize, formatDate, extractErrorMessage } from '@/utils/formatters'
import PageSizeCombobox, { PageSizeSuggestion } from '@/components/torrents/PageSizeCombobox.vue'
import { normalizeTraditionalPageSize } from '@/views/torrents/utils/traditionalPagination'

interface OrphanListQuery {
  page: number
  page_size: number
  downloader_id: string
  path_like: string
  status: OrphanStatusFilter | ''
  min_size: number | ''
}

interface DownloaderOption {
  value: string
  label: string
}

interface OrphanTableRef extends Vue {
  clearSelection: () => void
}

@Component({ name: 'OrphanFiles', components: { PageSizeCombobox } })
export default class OrphanFiles extends Vue {
  private list: OrphanFileItem[] = []
  private total = 0
  private listLoading = false
  private scanLoading = false
  private ignoreLoading = false
  private listQuery: OrphanListQuery = {
    page: 1,
    page_size: 20,
    downloader_id: '',
    path_like: '',
    status: '',
    min_size: ''
  }
  private refreshRequestSeq = 0

  // 页面 Tab：orphans=孤儿文件，quarantine=隔离区
  private activeTab: 'orphans' | 'quarantine' = 'orphans'

  // 隔离区列表状态
  private quarantineList: QuarantineItem[] = []
  private quarantineTotal = 0
  private quarantineLoading = false
  private quarantinePage = 1
  private quarantinePageSize = 20
  private quarantineSelected: QuarantineItem[] = []
  private restoreExecuting = false
  private purgeExecuting = false
  private quarantineRetentionDays = 7

  // 每页数量组合框状态（复用种子列表 PageSizeCombobox，与列表模式交互一致）
  private pageSizeInput = String(this.listQuery.page_size)
  private pageSizeDropdownExpanded = false
  private pageSizeOptions = [20, 50, 100, 500, 1000]

  // 下载器列表（用于别名展示与下拉筛选）
  private downloaderList: DownloaderSimple[] = []

  // 选中状态：保存完整行以支持按主导状态启停批量按钮
  private selectedRows: OrphanFileItem[] = []

  // 页面列表、统计和清理门禁共用的后端权威快照
  private scanContext: OrphanScanContext = {
    latest_attempt: null,
    display_scan: null,
    remaining_count: 0,
    remaining_size: 0,
    ignored_count: 0,
    cleanup_allowed: false,
    cleanup_block_reason: '尚无可清理的成功扫描'
  }

  // 清理对话框
  private cleanupDialogVisible = false
  private cleanupLoading = false
  private cleanupExecuting = false
  private cleanupPreviewData: CleanupPreviewSuccess | null = null
  private previewScanId: string | null = null
  private previewOrphanIds: number[] = []

  async created() {
    // 下载器列表失败不阻塞主流程（仅影响别名展示与下拉）
    try {
      const resp = await getDownloaderList()
      if (resp.code === '200' && Array.isArray(resp.data)) {
        this.downloaderList = resp.data
      }
    } catch (error) {
      // 静默降级：列表仍可用 downloader_name 后端字段
      void error
    }
  }

  mounted() {
    void this.refreshPageData()
  }

  beforeDestroy() {
    this.refreshRequestSeq += 1
  }

  // ==================== 隔离区管理 ====================

  private async handleTabSwitch() {
    if (this.activeTab === 'quarantine' && this.quarantineList.length === 0) {
      await this.loadQuarantineList()
    }
  }

  private async loadQuarantineList() {
    this.quarantineLoading = true
    try {
      const res = await getQuarantineList({
        page: this.quarantinePage,
        page_size: this.quarantinePageSize
      })
      if (res.code === '200' && res.data) {
        this.quarantineList = res.data.list
        this.quarantineTotal = res.data.total
      }
    } catch (error) {
      this.$message.error('加载隔离区列表失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      this.quarantineLoading = false
    }
  }

  private handleQuarantineSelectionChange(rows: QuarantineItem[]) {
    this.quarantineSelected = rows
  }

  private async handleQuarantineRestore() {
    if (this.quarantineSelected.length === 0) return
    try {
      await this.$confirm('确认恢复选中的文件到原位置？', '恢复确认', {
        type: 'warning'
      })
    } catch {
      return
    }
    this.restoreExecuting = true
    try {
      const paths = this.quarantineSelected.map(r => r.canonical_path)
      const res = await restoreQuarantined({ canonical_paths: paths })
      if (res.code === '200' && res.data) {
        const d = res.data
        if (d.rejected) {
          this.$message.error(d.failed_list[0]?.reason || '恢复被拒绝')
        } else {
          this.$message.success(`恢复完成：成功 ${d.restored_count} 个${d.failed_count ? '，失败 ' + d.failed_count + ' 个' : ''}`)
        }
        this.quarantinePage = 1
        await this.loadQuarantineList()
      }
    } catch (error) {
      this.$message.error('恢复失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      this.restoreExecuting = false
    }
  }

  private async handleQuarantinePurge() {
    if (this.quarantineSelected.length === 0) return
    try {
      await this.$confirm(
        '确认彻底删除选中的文件？此操作不可恢复，文件将被永久删除！',
        '彻底删除确认',
        { type: 'error', confirmButtonText: '确认删除', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
    this.purgeExecuting = true
    try {
      const paths = this.quarantineSelected.map(r => r.canonical_path)
      const res = await purgeQuarantineNow({ canonical_paths: paths })
      if (res.code === '200' && res.data) {
        this.$message.success(
          `彻底删除任务已提交（${res.data.task_id.slice(0, 8)}），完成或失败后将在通知中心提醒`
        )
        this.quarantineSelected = []
        const table = this.$refs.quarantineTable as OrphanTableRef | undefined
        table?.clearSelection()
      }
    } catch (error) {
      this.$message.error('删除失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      this.purgeExecuting = false
    }
  }

  private formatIsoTime(iso: string | null): string {
    if (!iso) return '-'
    return formatDate(iso)
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

  private get selectedIds(): number[] {
    return this.selectedRows.map((r) => r.id)
  }

  private get downloaderOptions(): DownloaderOption[] {
    return this.downloaderList.map((d) => ({
      value: d.downloader_id,
      label: d.nickname || d.downloader_id
    }))
  }

  // ========== 批量按钮启停（按选中主导状态）==========

  /** 选中集合中"可清理"的项：待清理（未删除未忽视）。 */
  private get pendingSelection(): OrphanFileItem[] {
    return this.selectedRows.filter((r) => !r.is_deleted && !r.is_ignored)
  }

  /** 选中集合中"已忽视"的项。 */
  private get ignoredSelection(): OrphanFileItem[] {
    return this.selectedRows.filter((r) => !r.is_deleted && r.is_ignored)
  }

  /** 选中是否全部为待清理态（可清理+可忽视）。 */
  private get allSelectionPending(): boolean {
    return this.selectedRows.length > 0 && this.pendingSelection.length === this.selectedRows.length
  }

  /** 选中是否全部为已忽视态（可取消忽视）。 */
  private get allSelectionIgnored(): boolean {
    return this.selectedRows.length > 0 && this.ignoredSelection.length === this.selectedRows.length
  }

  private get canBatchCleanup(): boolean {
    return this.allSelectionPending && this.cleanupAllowed
  }

  private get batchCleanupTitle(): string {
    if (this.selectedRows.length === 0) return '请先选择待清理文件'
    if (!this.allSelectionPending) return '请勿混选不同状态，仅支持清理"待清理"项'
    return this.cleanupAllowed ? '' : this.cleanupBlockReason
  }

  private get canBatchIgnore(): boolean {
    return this.allSelectionPending
  }

  private get batchIgnoreTitle(): string {
    if (this.selectedRows.length === 0) return '请先选择待清理文件'
    if (!this.allSelectionPending) return '请勿混选不同状态，仅支持忽视"待清理"项'
    return ''
  }

  private get canBatchUnignore(): boolean {
    return this.allSelectionIgnored
  }

  private get batchUnignoreTitle(): string {
    if (this.selectedRows.length === 0) return '请先选择已忽视文件'
    if (!this.allSelectionIgnored) return '请勿混选不同状态，仅支持取消"已忽视"项'
    return ''
  }

  /** 总页数（total=0 时返回 0，避免空表显示 1/1）。 */
  private get totalPages(): number {
    if (this.total === 0) return 0
    return Math.max(1, Math.ceil(this.total / this.listQuery.page_size))
  }

  /** 翻页按钮可见页码窗口（最多 5 个，与种子列表列表模式一致）。 */
  private get visiblePages(): number[] {
    const pages: number[] = []
    const maxVisible = 5
    let start = Math.max(1, this.listQuery.page - Math.floor(maxVisible / 2))
    let end = Math.min(this.totalPages, start + maxVisible - 1)

    if (end - start < maxVisible - 1) {
      start = Math.max(1, end - maxVisible + 1)
    }

    for (let i = start; i <= end; i++) {
      pages.push(i)
    }

    return pages
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
      downloader_id: this.listQuery.downloader_id,
      path_like: this.listQuery.path_like,
      status: this.listQuery.status,
      min_size: this.listQuery.min_size
    })
    this.listLoading = true
    try {
      const params: OrphanListParams = {
        page: querySnapshot.page,
        page_size: querySnapshot.page_size,
        downloader_id: querySnapshot.downloader_id || undefined,
        path_like: querySnapshot.path_like || undefined,
        status: querySnapshot.status || undefined,
        min_size: querySnapshot.min_size === '' ? undefined : Number(querySnapshot.min_size)
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
        this.selectedRows = []
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

  private handleResetFilter() {
    this.listQuery = {
      page: 1,
      page_size: this.listQuery.page_size,
      downloader_id: '',
      path_like: '',
      status: '',
      min_size: ''
    }
    void this.refreshPageData()
  }

  // 每页数量变更：与种子列表列表模式一致，应用后回到第一页。
  private handlePageSizeSelect(suggestion: PageSizeSuggestion) {
    this.pageSizeDropdownExpanded = false
    this.applyPageSizeSelection(suggestion.value)
  }

  private handlePageSizeFocus() {
    this.pageSizeDropdownExpanded = true
  }

  private handlePageSizeBlur() {
    this.pageSizeDropdownExpanded = false
    this.applyPageSizeSelection(this.pageSizeInput)
  }

  private togglePageSizeDropdown() {
    this.pageSizeDropdownExpanded = !this.pageSizeDropdownExpanded
    if (!this.pageSizeDropdownExpanded) return
    this.$nextTick(() => {
      const combobox = this.$refs.pageSizeCombobox as PageSizeCombobox | undefined
      combobox?.focusInput()
    })
  }

  private applyPageSizeSelection(value: string | number) {
    const normalizedPageSize = normalizeTraditionalPageSize(value, this.listQuery.page_size)
    this.pageSizeInput = String(normalizedPageSize)
    this.pageSizeDropdownExpanded = false
    if (normalizedPageSize === this.listQuery.page_size) return

    this.listQuery.page_size = normalizedPageSize
    this.listQuery.page = 1
    void this.refreshPageData()
  }

  // 翻页：切换当前页并重新加载。
  private handlePageChange(page: number) {
    if (page < 1 || page > this.totalPages) return
    this.listQuery.page = page
    void this.refreshPageData()
  }

  private handleSelectionChange(rows: OrphanFileItem[]) {
    this.selectedRows = rows
  }

  /** 已清理行不可勾选；待清理/已忽视行均可勾选（用于对应批量操作）。 */
  private rowSelectable(row: OrphanFileItem): boolean {
    return !row.is_deleted
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
        } else if (response.data.total_count === 0) {
          // 预览为空：所选文件均不满足清理条件（低置信度/已忽视/已清理/scan_id 不匹配）。
          // 不弹空对话框，给出针对性提示引导用户。
          this.$message.warning(
            '所选文件均无可清理项：可能是低置信度（需等下载器上线精筛）、已忽视（需先取消忽视）或已清理。'
          )
          this.cleanupDialogVisible = false
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
        const taskId = response.data.task_id
        this.$message.success(
          `主动清理任务已提交（${taskId.slice(0, 8)}），完成或失败后将在通知中心提醒`
        )
        this.handleCloseCleanupDialog()
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
    this.previewScanId = null
    this.previewOrphanIds = []
  }

  // ========== 忽视操作 ==========

  private async handleRowIgnore(row: OrphanFileItem, ignored: boolean): Promise<void> {
    await this.applyIgnore([row.id], ignored)
  }

  private async handleBatchIgnore(ignored: boolean): Promise<void> {
    const rows = ignored ? this.pendingSelection : this.ignoredSelection
    if (rows.length === 0) {
      this.$message.warning(ignored ? '请选择待清理的文件' : '请选择已忽视的文件')
      return
    }
    await this.applyIgnore(rows.map((r) => r.id), ignored)
  }

  private async applyIgnore(orphanIds: number[], ignored: boolean): Promise<void> {
    const action = ignored ? '忽视' : '取消忽视'
    try {
      await this.$confirm(`确认${action}选中的 ${orphanIds.length} 个孤儿文件？`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'info'
      })
    } catch {
      return // 用户取消
    }

    this.ignoreLoading = true
    try {
      const displayScan = this.displayScan
      const response = await setIgnored({
        scan_id: displayScan ? displayScan.scan_id : undefined,
        orphan_ids: orphanIds,
        ignored
      })
      if (response.code === '200' && response.data) {
        const data = response.data
        if (data.rejected === true) {
          this.$message.error(data.error || `${action}失败`)
        } else {
          let msg = `${action}完成: 成功 ${data.success_count} 个`
          if (data.failed_count > 0) {
            msg += `，失败 ${data.failed_count} 个`
          }
          this.$message.success(msg)
        }
        await this.refreshPageData()
      } else {
        this.$message.error(response.msg || `${action}失败`)
      }
    } catch (error) {
      this.$message.error(`${action}失败：` + extractErrorMessage(error, '网络错误'))
    } finally {
      this.ignoreLoading = false
    }
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

  .cleanup-low-confidence-warn {
    margin-top: var(--spacing-md);
  }

  /* 分页区：复用种子列表列表模式同款（PageSizeCombobox + 翻页按钮 + 文字汇总） */
  .torrent-pagination.management-pagination {
    justify-content: space-between;
    gap: var(--spacing-md);

    .pagination-info {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: var(--color-text-secondary);

      .pagination-summary strong {
        color: var(--color-text-primary);
      }
    }

    .pagination-controls {
      display: flex;
      gap: 6px;
      align-items: center;

      .pagination-btn {
        width: 32px;
        height: 32px;
        border: 1px solid var(--color-border-primary);
        background: var(--color-bg-primary);
        border-radius: var(--radius-sm);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        color: var(--color-text-primary);
        transition: background-color var(--transition-base) ease,
          border-color var(--transition-base) ease, color var(--transition-base) ease;

        &:hover:not(:disabled) {
          background: var(--color-primary);
          border-color: var(--color-primary);
          color: #fff;
        }

        &:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        &.active {
          background: var(--color-primary);
          border-color: var(--color-primary);
          color: #fff;
          font-weight: var(--font-weight-semibold);
        }
      }
    }
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
