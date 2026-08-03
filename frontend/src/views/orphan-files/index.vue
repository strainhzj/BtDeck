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
          <label class="management-filter__label" for="orphan-confidence">置信度</label>
          <el-select
            id="orphan-confidence"
            v-model="listQuery.confidence"
            class="management-filter__control"
            placeholder="全部置信度"
            clearable
            @change="handleFilter"
          >
            <el-option label="高置信度" value="high" />
            <el-option label="低置信度" value="low" />
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
          <el-tag v-if="selectedCount > 0" type="info" effect="plain">
            已选择 {{ selectedCount }} 项
          </el-tag>
          <el-tag v-if="allMatchingSelected" type="success" effect="plain">
            当前筛选全部
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
      <div class="management-table-scroll orphan-table-scroll">
        <el-table
          ref="orphanTable"
          v-loading="listLoading"
          :data="virtualTableData"
          class="management-table"
          height="100%"
          :row-key="orphanRowKey"
          :row-class-name="orphanRowClassName"
          :row-style="orphanRowStyle"
          :cell-style="orphanCellStyle"
          border
          fit
          highlight-current-row
          empty-text="暂无孤儿文件，点击“立即扫描”开始检测"
          style="width: 100%"
        >
          <el-table-column
            width="55"
            align="center"
          >
            <template slot="header">
              <el-checkbox
                class="orphan-select-all"
                :value="selectionAllChecked"
                :indeterminate="selectionIndeterminate"
                :disabled="selectableTotal === 0"
                aria-label="选择当前筛选条件下的全部孤儿文件"
                @change="handleSelectAllChange"
              />
            </template>
            <template slot-scope="scope">
              <el-checkbox
                v-if="rowSelectable(scope.row)"
                class="orphan-row-checkbox"
                :value="isRowSelected(scope.row)"
                :aria-label="`选择 ${scope.row.file_path}`"
                @click.native.stop
                @change="handleRowSelectionChange(scope.row, $event)"
              />
            </template>
          </el-table-column>
          <el-table-column label="文件路径" prop="file_path" min-width="300" show-overflow-tooltip />
          <el-table-column label="大小" width="120" align="center">
            <template slot-scope="scope">
              <span v-if="!isVirtualSpacer(scope.row)">{{ formatSize(scope.row.file_size) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="修改时间" width="170" align="center">
            <template slot-scope="scope">
              <span v-if="!isVirtualSpacer(scope.row)">{{ scope.row.mtime ? formatTime(scope.row.mtime) : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="下载器" width="140" align="center" show-overflow-tooltip>
            <template slot-scope="scope">
              <span v-if="!isVirtualSpacer(scope.row)">{{ scope.row.downloader_name || (scope.row.downloader_id ? maskId(scope.row.downloader_id) : '-') }}</span>
            </template>
          </el-table-column>
          <el-table-column label="置信度" width="100" align="center">
            <template slot-scope="scope">
              <template v-if="!isVirtualSpacer(scope.row)">
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
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template slot-scope="scope">
              <template v-if="!isVirtualSpacer(scope.row)">
                <el-tag v-if="scope.row.is_deleted" type="info" size="small">已清理</el-tag>
                <el-tag v-else-if="scope.row.is_ignored" type="warning" size="small">已忽视</el-tag>
                <el-tag v-else type="danger" size="small">待清理</el-tag>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center" fixed="right">
            <template slot-scope="scope">
              <el-button
                v-if="!isVirtualSpacer(scope.row) && !scope.row.is_deleted && !scope.row.is_ignored"
                type="text"
                size="small"
                @click="handleRowIgnore(scope.row, true)"
              >
                忽视
              </el-button>
              <el-button
                v-else-if="!isVirtualSpacer(scope.row) && !scope.row.is_deleted && scope.row.is_ignored"
                type="text"
                size="small"
                @click="handleRowIgnore(scope.row, false)"
              >
                取消忽视
              </el-button>
              <span v-else-if="!isVirtualSpacer(scope.row)">-</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 列表按页追加，滚动到底部时懒加载下一页。 -->
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
          <span class="pagination-summary">已加载 <strong>{{ list.length }}</strong> / <strong>{{ total }}</strong> 条</span>
        </div>
        <div class="pagination-controls">
          <span v-if="listLoading" class="pagination-summary">正在加载…</span>
          <span v-else-if="list.length < total" class="pagination-summary">继续滚动加载更多</span>
          <span v-else class="pagination-summary">已加载全部结果</span>
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
          <div class="management-table-scroll quarantine-table-scroll">
            <el-table
              ref="quarantineTable"
              v-loading="quarantineLoading"
              :data="quarantineList"
              class="management-table"
              border
              stripe
              fit
              style="width: 100%"
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
  OrphanConfidence,
  OrphanStatusFilter,
  OrphanSelectionFilters,
  OrphanSelectionPayload,
  CleanupPreviewSuccess,
  IgnoreResult,
  QuarantineItem
} from '@/api/orphan-files'
import { getDownloaderList, DownloaderSimple } from '@/api/torrents'
import { formatFileSize, formatDate, extractErrorMessage } from '@/utils/formatters'
import PageSizeCombobox, { PageSizeSuggestion } from '@/components/torrents/PageSizeCombobox.vue'
import { normalizeTraditionalPageSize } from '@/views/torrents/utils/traditionalPagination'
import { calculateTraditionalVirtualWindow } from '@/views/torrents/utils/traditionalVirtualList'

interface OrphanListQuery {
  page: number
  page_size: number
  downloader_id: string
  path_like: string
  status: OrphanStatusFilter | ''
  confidence: OrphanConfidence | ''
  min_size: number | ''
}

interface DownloaderOption {
  value: string
  label: string
}

interface OrphanTableRef extends Vue {
  clearSelection: () => void
  bodyWrapper?: HTMLElement
  doLayout?: () => void
}

type OrphanVirtualSpacer = 'top' | 'bottom'

interface OrphanVirtualTableRow extends OrphanFileItem {
  __virtualSpacer?: OrphanVirtualSpacer
  __virtualHeight?: number
}

interface OrphanTableRenderArgs {
  row: OrphanVirtualTableRow
}

type OrphanTableInlineStyle = Record<string, string>

const ORPHAN_VIRTUAL_ROW_HEIGHT = 48
const ORPHAN_VIRTUAL_OVERSCAN = 8
const ORPHAN_TABLE_VIEWPORT_FALLBACK = 472
const ORPHAN_PAGE_SIZE_MAX = 1000

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
    confidence: '',
    min_size: ''
  }
  private refreshRequestSeq = 0
  private tableScrollTop = 0
  private tableViewportHeight = ORPHAN_TABLE_VIEWPORT_FALLBACK
  private orphanTableBody: HTMLElement | null = null
  private readonly orphanTableScrollListener: EventListener = (event) => {
    this.handleListScroll(event)
  }

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
  private allMatchingSelected = false
  private excludedSelectionIds: number[] = []

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
  private previewSelection: OrphanSelectionPayload | null = null

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
    this.$nextTick(() => this.bindOrphanTableScroll())
    void this.refreshPageData()
  }

  beforeDestroy() {
    this.refreshRequestSeq += 1
    this.unbindOrphanTableScroll()
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

  private get selectableTotal(): number {
    return this.listQuery.status === 'deleted' ? 0 : this.total
  }

  private get selectedCount(): number {
    if (!this.allMatchingSelected) return this.selectedRows.length
    return Math.max(0, this.selectableTotal - this.excludedSelectionIds.length)
  }

  private get selectionAllChecked(): boolean {
    return this.selectableTotal > 0 && this.selectedCount === this.selectableTotal
  }

  private get selectionIndeterminate(): boolean {
    return this.selectedCount > 0 && !this.selectionAllChecked
  }

  private get currentSelectionFilters(): OrphanSelectionFilters {
    const filters: OrphanSelectionFilters = {}
    if (this.listQuery.downloader_id) filters.downloader_id = this.listQuery.downloader_id
    if (this.listQuery.path_like) filters.path_like = this.listQuery.path_like
    if (this.listQuery.status) filters.status = this.listQuery.status
    if (this.listQuery.confidence) filters.confidence = this.listQuery.confidence
    if (this.listQuery.min_size !== '') filters.min_size = Number(this.listQuery.min_size)
    return filters
  }

  private get orphanVirtualWindow() {
    return calculateTraditionalVirtualWindow(
      this.list.length,
      this.tableScrollTop,
      this.tableViewportHeight,
      ORPHAN_VIRTUAL_ROW_HEIGHT,
      ORPHAN_VIRTUAL_OVERSCAN
    )
  }

  private get virtualTableData(): OrphanVirtualTableRow[] {
    const window = this.orphanVirtualWindow
    const rows: OrphanVirtualTableRow[] = []
    if (window.topSpacerHeight > 0) {
      rows.push(this.createVirtualSpacer('top', window.topSpacerHeight))
    }
    rows.push(...this.list.slice(window.startIndex, window.endIndex))
    if (window.bottomSpacerHeight > 0) {
      rows.push(this.createVirtualSpacer('bottom', window.bottomSpacerHeight))
    }
    return rows
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
    if (this.allMatchingSelected) {
      return this.selectedCount > 0 && this.listQuery.status === 'pending'
    }
    return this.selectedRows.length > 0 && this.pendingSelection.length === this.selectedRows.length
  }

  /** 选中是否全部为已忽视态（可取消忽视）。 */
  private get allSelectionIgnored(): boolean {
    if (this.allMatchingSelected) {
      return this.selectedCount > 0 && this.listQuery.status === 'ignored'
    }
    return this.selectedRows.length > 0 && this.ignoredSelection.length === this.selectedRows.length
  }

  private get canBatchCleanup(): boolean {
    return this.allSelectionPending && this.cleanupAllowed
  }

  private get batchCleanupTitle(): string {
    if (this.selectedCount === 0) return '请先选择待清理文件'
    if (this.allMatchingSelected && this.listQuery.status !== 'pending') {
      return '全选当前筛选结果时，请先将状态筛选为“待清理”'
    }
    if (!this.allSelectionPending) return '请勿混选不同状态，仅支持清理"待清理"项'
    return this.cleanupAllowed ? '' : this.cleanupBlockReason
  }

  private get canBatchIgnore(): boolean {
    return this.allSelectionPending
  }

  private get batchIgnoreTitle(): string {
    if (this.selectedCount === 0) return '请先选择待清理文件'
    if (this.allMatchingSelected && this.listQuery.status !== 'pending') {
      return '全选当前筛选结果时，请先将状态筛选为“待清理”'
    }
    if (!this.allSelectionPending) return '请勿混选不同状态，仅支持忽视"待清理"项'
    return ''
  }

  private get canBatchUnignore(): boolean {
    return this.allSelectionIgnored
  }

  private get batchUnignoreTitle(): string {
    if (this.selectedCount === 0) return '请先选择已忽视文件'
    if (this.allMatchingSelected && this.listQuery.status !== 'ignored') {
      return '全选当前筛选结果时，请先将状态筛选为“已忽视”'
    }
    if (!this.allSelectionIgnored) return '请勿混选不同状态，仅支持取消"已忽视"项'
    return ''
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

  private async refreshPageData(): Promise<void> {
    this.listQuery.page = 1
    await this.loadOrphanPage(1, true)
  }

  /** 请求一页孤儿文件；replace=true 用于筛选/刷新，false 用于滚动追加。 */
  private async loadOrphanPage(page: number, replace: boolean): Promise<void> {
    const requestId = ++this.refreshRequestSeq
    const querySnapshot: Readonly<OrphanListQuery> = Object.freeze({
      page,
      page_size: this.listQuery.page_size,
      downloader_id: this.listQuery.downloader_id,
      path_like: this.listQuery.path_like,
      status: this.listQuery.status,
      confidence: this.listQuery.confidence,
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
      if (querySnapshot.confidence) {
        params.confidence = querySnapshot.confidence
      }
      const response = await getOrphanList(params)
      if (requestId !== this.refreshRequestSeq) return

      if (response.code === '200' && response.data) {
        if (replace) {
          this.list = response.data.list
          this.resetOrphanTableScroll()
          this.clearOrphanSelection()
        } else {
          const existingIds = new Set(this.list.map((item) => item.id))
          this.list = this.list.concat(
            response.data.list.filter((item) => !existingIds.has(item.id))
          )
        }
        this.total = response.data.total
        this.scanContext = response.data.scan_context
        this.listQuery.page = querySnapshot.page
        this.$nextTick(() => {
          this.bindOrphanTableScroll()
          const table = this.$refs.orphanTable as OrphanTableRef | undefined
          table?.doLayout?.()
        })
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

  private handleListScroll(event: Event) {
    const target = event.target as HTMLElement | null
    if (!target) return
    this.tableScrollTop = Math.max(0, target.scrollTop)
    this.tableViewportHeight = target.clientHeight || ORPHAN_TABLE_VIEWPORT_FALLBACK
    if (this.listLoading || this.list.length >= this.total) return
    if (target.scrollHeight - target.scrollTop - target.clientHeight > 80) return
    void this.loadNextOrphanPage()
  }

  private async loadNextOrphanPage(): Promise<void> {
    if (this.listLoading || this.list.length >= this.total) return
    await this.loadOrphanPage(this.listQuery.page + 1, false)
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
      confidence: '',
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
    const requestedPageSize = Number(value)
    const normalizedPageSize = Math.min(
      normalizeTraditionalPageSize(value, this.listQuery.page_size),
      ORPHAN_PAGE_SIZE_MAX
    )
    if (Number.isFinite(requestedPageSize) && requestedPageSize > ORPHAN_PAGE_SIZE_MAX) {
      this.$message.info(`单次最多加载 ${ORPHAN_PAGE_SIZE_MAX} 条，已自动调整`)
    }
    this.pageSizeInput = String(normalizedPageSize)
    this.pageSizeDropdownExpanded = false
    if (normalizedPageSize === this.listQuery.page_size) return

    this.listQuery.page_size = normalizedPageSize
    this.listQuery.page = 1
    void this.refreshPageData()
  }

  private handleSelectAllChange(checked: boolean): void {
    if (!checked || this.selectableTotal === 0) {
      this.clearOrphanSelection()
      return
    }
    this.allMatchingSelected = true
    this.excludedSelectionIds = []
    this.selectedRows = []
  }

  private handleRowSelectionChange(row: OrphanVirtualTableRow, checked: boolean): void {
    if (!this.rowSelectable(row)) return
    if (this.allMatchingSelected) {
      const exclusions = new Set(this.excludedSelectionIds)
      if (checked) exclusions.delete(row.id)
      else exclusions.add(row.id)
      this.excludedSelectionIds = Array.from(exclusions)
      return
    }

    if (checked) {
      if (!this.selectedRows.some((selected) => selected.id === row.id)) {
        this.selectedRows = this.selectedRows.concat(row)
      }
    } else {
      this.selectedRows = this.selectedRows.filter((selected) => selected.id !== row.id)
    }
  }

  private isRowSelected(row: OrphanVirtualTableRow): boolean {
    if (!this.rowSelectable(row)) return false
    if (this.allMatchingSelected) return !this.excludedSelectionIds.includes(row.id)
    return this.selectedRows.some((selected) => selected.id === row.id)
  }

  private clearOrphanSelection(): void {
    this.selectedRows = []
    this.allMatchingSelected = false
    this.excludedSelectionIds = []
  }

  private buildSelectionPayload(): OrphanSelectionPayload {
    if (this.allMatchingSelected) {
      return {
        select_all: true,
        excluded_orphan_ids: [...this.excludedSelectionIds],
        filters: { ...this.currentSelectionFilters }
      }
    }
    return { orphan_ids: [...this.selectedIds] }
  }

  /** 已清理行不可勾选；待清理/已忽视行均可勾选（用于对应批量操作）。 */
  private rowSelectable(row: OrphanVirtualTableRow): boolean {
    return !this.isVirtualSpacer(row) && !row.is_deleted
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
    if (this.selectedCount === 0) {
      this.$message.warning('请先选择要清理的文件')
      return
    }
    if (!this.allSelectionPending) {
      this.$message.warning(this.batchCleanupTitle)
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
    this.previewSelection = this.buildSelectionPayload()
    this.cleanupLoading = true

    try {
      const response = await cleanupPreview({
        scan_id: this.previewScanId,
        ...this.previewSelection
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
      if (!this.previewScanId || !this.previewSelection) {
        this.$message.warning('扫描批次已失效，请刷新后重试')
        return
      }
      const response = await cleanupOrphans({
        scan_id: this.previewScanId,
        ...this.previewSelection
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
    this.previewSelection = null
  }

  // ========== 忽视操作 ==========

  private async handleRowIgnore(row: OrphanFileItem, ignored: boolean): Promise<void> {
    await this.applyIgnore({ orphan_ids: [row.id] }, 1, ignored)
  }

  private async handleBatchIgnore(ignored: boolean): Promise<void> {
    if (this.allMatchingSelected) {
      const validSelection = ignored ? this.allSelectionPending : this.allSelectionIgnored
      if (!validSelection) {
        this.$message.warning(ignored ? this.batchIgnoreTitle : this.batchUnignoreTitle)
        return
      }
      await this.applyIgnore(this.buildSelectionPayload(), this.selectedCount, ignored)
      return
    }
    const rows = ignored ? this.pendingSelection : this.ignoredSelection
    if (rows.length === 0) {
      this.$message.warning(ignored ? '请选择待清理的文件' : '请选择已忽视的文件')
      return
    }
    await this.applyIgnore({ orphan_ids: rows.map((r) => r.id) }, rows.length, ignored)
  }

  private async applyIgnore(
    selection: OrphanSelectionPayload,
    selectionCount: number,
    ignored: boolean
  ): Promise<void> {
    const action = ignored ? '忽视' : '取消忽视'
    try {
      await this.$confirm(`确认${action}选中的 ${selectionCount} 个孤儿文件？`, '提示', {
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
        ...selection,
        ignored
      })
      if (response.code === '200' && response.data) {
        const data = response.data
        if (data.rejected === true) {
          this.$message.error(`${action}失败：${this.summarizeIgnoreFailures(data)}`)
        } else if (data.success_count === 0 && data.failed_count > 0) {
          this.$message.error(`${action}失败：${this.summarizeIgnoreFailures(data)}`)
        } else if (data.failed_count > 0) {
          this.$message.warning(
            `${action}部分完成：成功 ${data.success_count} 个，失败 ${data.failed_count} 个；${this.summarizeIgnoreFailures(data)}`
          )
        } else {
          this.$message.success(`${action}完成：成功 ${data.success_count} 个`)
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

  private bindOrphanTableScroll(): void {
    const table = this.$refs.orphanTable as OrphanTableRef | undefined
    const body = table?.bodyWrapper || table?.$el.querySelector<HTMLElement>('.el-table__body-wrapper')
    if (!body) return
    if (this.orphanTableBody !== body) {
      this.unbindOrphanTableScroll()
      this.orphanTableBody = body
      body.addEventListener('scroll', this.orphanTableScrollListener, { passive: true })
    }
    this.tableViewportHeight = body.clientHeight || ORPHAN_TABLE_VIEWPORT_FALLBACK
  }

  private unbindOrphanTableScroll(): void {
    if (!this.orphanTableBody) return
    this.orphanTableBody.removeEventListener('scroll', this.orphanTableScrollListener)
    this.orphanTableBody = null
  }

  private resetOrphanTableScroll(): void {
    this.tableScrollTop = 0
    if (this.orphanTableBody) {
      this.orphanTableBody.scrollTop = 0
    }
  }

  private createVirtualSpacer(
    position: OrphanVirtualSpacer,
    height: number
  ): OrphanVirtualTableRow {
    return {
      id: position === 'top' ? -1 : -2,
      scan_id: '',
      file_path: '',
      file_size: 0,
      mtime: null,
      downloader_id: null,
      confidence: 'high',
      canonical_path: null,
      downloader_name: null,
      is_ignored: false,
      ignored_at: null,
      ignored_by: null,
      is_deleted: true,
      deleted_at: null,
      deleted_by: null,
      created_at: null,
      __virtualSpacer: position,
      __virtualHeight: height
    }
  }

  private isVirtualSpacer(row: OrphanVirtualTableRow): boolean {
    return Boolean(row.__virtualSpacer)
  }

  private orphanRowKey(row: OrphanVirtualTableRow): number | string {
    return row.__virtualSpacer ? `orphan-virtual-${row.__virtualSpacer}` : row.id
  }

  private orphanRowClassName({ row }: OrphanTableRenderArgs): string {
    return this.isVirtualSpacer(row) ? 'orphan-virtual-spacer' : 'orphan-table-row'
  }

  private orphanRowStyle({ row }: OrphanTableRenderArgs): OrphanTableInlineStyle {
    const height = row.__virtualSpacer
      ? Math.max(0, row.__virtualHeight || 0)
      : ORPHAN_VIRTUAL_ROW_HEIGHT
    return { height: `${height}px` }
  }

  private orphanCellStyle({ row }: OrphanTableRenderArgs): OrphanTableInlineStyle {
    if (!this.isVirtualSpacer(row)) return {}
    return {
      height: `${Math.max(0, row.__virtualHeight || 0)}px`,
      padding: '0',
      borderBottom: '0'
    }
  }

  private summarizeIgnoreFailures(data: IgnoreResult): string {
    if (data.error) return data.error
    const reasons = Array.from(
      new Set(data.failed_list.map((item) => item.reason).filter((reason) => Boolean(reason)))
    )
    if (reasons.length === 0) return `${data.failed_count} 个文件未处理`
    const summary = reasons.slice(0, 3).join('；')
    return reasons.length > 3 ? `${summary}；另有 ${reasons.length - 3} 类原因` : summary
  }

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

  /* 列表固定可视高度，数据通过滚动触底按页追加。 */
  .orphan-table-scroll {
    height: 520px;
    max-height: calc(100vh - 430px);
    min-height: 300px;
    overflow: hidden;

    ::v-deep .management-table {
      min-width: 0;
    }

    ::v-deep .orphan-table-row > td {
      box-sizing: border-box;
      height: 48px;
      padding: 8px 0;
    }

    ::v-deep .orphan-virtual-spacer > td {
      padding: 0 !important;
      border-bottom: 0 !important;
    }

    ::v-deep .orphan-virtual-spacer .cell {
      height: 100%;
      min-height: 0;
      padding: 0 !important;
      overflow: hidden;
    }

    ::v-deep .orphan-virtual-spacer .el-checkbox {
      display: none;
    }

    ::v-deep .orphan-select-all .el-checkbox__inner {
      border-color: rgba(255, 255, 255, 0.9);
    }

    ::v-deep .orphan-select-all.is-checked .el-checkbox__inner,
    ::v-deep .orphan-select-all.is-indeterminate .el-checkbox__inner {
      background: #fff;
      border-color: #fff;
    }

    ::v-deep .orphan-select-all.is-checked .el-checkbox__inner::after,
    ::v-deep .orphan-select-all.is-indeterminate .el-checkbox__inner::before {
      border-color: var(--color-primary);
      background: var(--color-primary);
    }
  }

  .quarantine-table-scroll {
    ::v-deep .management-table {
      min-width: 920px;
    }
  }

  /* 懒加载状态沿用列表底部汇总区，避免滚动过程中布局跳动。 */
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
      align-items: center;
      min-height: 32px;
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
