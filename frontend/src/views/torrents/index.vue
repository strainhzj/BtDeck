<template>
  <div class="torrent-management-page" :class="`theme-${currentTheme}`">
    <!-- 搜索筛选区 -->
    <section class="filter-container">
      <div class="simple-search">
        <el-input
          v-model="listQuery.name_like"
          placeholder="搜索种子名称..."
          style="width: 200px;"
          class="search-input"
          @input="debouncedSearch"
          @keyup.enter.native="handleFilter"
        />
        <el-select
          v-model="listQuery.downloader_id"
          placeholder="全部下载器"
          clearable
          multiple
          collapse-tags
          style="width: 200px;"
          class="search-select"
          filterable
        >
          <el-option
            v-for="downloader in downloaderList"
            :key="downloader.downloader_id"
            :label="downloader.nickname"
            :value="downloader.downloader_id"
          />
        </el-select>
        <el-select
          v-model="listQuery.status"
          placeholder="全部状态"
          clearable
          multiple
          collapse-tags
          style="width: 180px;"
          class="search-select"
        >
        <el-option
          v-for="option in statusOptions"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
        </el-select>
        <el-checkbox
          v-model="listQuery.showActiveOnly"
          class="active-only-checkbox"
          @change="handleFilter"
        >
          仅显示活动种子
        </el-checkbox>
        <el-button class="search-btn" @click="handleFilter">
          搜索
        </el-button>
        <el-button class="advanced-search-btn" @click="showAdvancedSearchDialog = true">
          高级搜索
        </el-button>
        <el-button class="duplicate-detection-btn" @click="handleShowDuplicateTorrents" >
          🔍 查找重复任务
        </el-button>
        <el-button class="clear-btn" @click="handleClearFilter">
          清空
        </el-button>
        <el-button class="refresh-btn" @click="handleManualRefresh" :loading="listLoading">
          刷新
        </el-button>
      </div>
    </section>

    <!-- 批量操作工具栏 -->
    <section class="batch-operations">
      <!-- 批量开始 -->
      <batch-button
        type="success"
        icon="el-icon-video-play"
        tooltip="开始"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchStart"
      />

      <!-- 批量暂停 -->
      <batch-button
        type="warning"
        icon="el-icon-video-pause"
        tooltip="暂停"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchPause"
      />

      <!-- 批量删除（带下拉菜单） -->
      <el-dropdown
        @command="handleBatchDeleteCommand"
        trigger="click"
        :hide-on-click="true"
        :append-to-body="true"
        :disabled="multipleSelection.length === 0"
      >
        <batch-button
          type="danger"
          icon="el-icon-delete"
          tooltip="删除"
          :disabled="multipleSelection.length === 0"
        />
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="4">
            <i class="el-icon-tag"></i> 等级4: 标记为待删除(推荐)
          </el-dropdown-item>
          <el-dropdown-item command="3">
            <i class="el-icon-folder-delete"></i> 等级3: 移至回收站
          </el-dropdown-item>
          <el-dropdown-item command="2">
            <i class="el-icon-delete"></i> 等级2: 删除任务(保留数据)
          </el-dropdown-item>
          <el-dropdown-item command="1" divided>
            <i class="el-icon-warning"></i> 等级1: 完全删除
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>

      <!-- 批量重检 -->
      <batch-button
        type="info"
        icon="el-icon-refresh"
        tooltip="重检"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchRecheck"
      />

      <!-- Tracker操作 -->
      <batch-button
        type="default"
        icon="el-icon-link"
        tooltip="Tracker操作"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchTracker"
      />

      <!-- Tracker汇报 -->
      <batch-button
        type="info"
        icon="el-icon-share"
        tooltip="Tracker汇报"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchReannounce"
      />

      <!-- 全局替换 -->
      <batch-button
        type="default"
        icon="el-icon-setting"
        tooltip="全局替换"
        @click="showGlobalReplaceDialog = true"
      />

      <!-- 批量转移 -->
      <batch-button
        type="info"
        icon="el-icon-sort"
        tooltip="转移"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchTransfer"
      />

      <!-- 批量修改路径 -->
      <batch-button
        type="primary"
        icon="el-icon-folder-opened"
        tooltip="修改路径"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchSetLocation"
      />

      <div style="flex: 1;"></div>

      <!-- 添加种子 -->
      <batch-button
        type="primary"
        icon="el-icon-plus"
        tooltip="添加种子"
        @click="showAddDialog = true"
      />

      <!-- 列设置 -->
      <batch-button
        type="default"
        icon="el-icon-setting"
        tooltip="列设置"
        @click="showColumnSettings = true"
      />
    </section>

    <!-- 种子列表表格 -->
    <section
      class="torrents-table-wrapper"
      v-loading="listLoading"
      element-loading-text="加载中..."
      element-loading-spinner="el-icon-loading"
      element-loading-background="rgba(0, 0, 0, 0.2)"
    >
      <table class="torrent-table">
        <thead>
          <tr>
            <th style="width: 50px;">
              <el-checkbox
                :indeterminate="isIndeterminate"
                v-model="selectAll"
                @change="handleSelectAll"
              />
            </th>
            <th v-if="getColumnSetting('name').visible">种子名称</th>
            <th v-if="getColumnSetting('downloadSpeed').visible" style="width: 100px;">下载速度</th>
            <th v-if="getColumnSetting('uploadSpeed').visible" style="width: 100px;">上传速度</th>
            <th v-if="getColumnSetting('size').visible" style="width: 100px;">大小</th>
            <th v-if="getColumnSetting('progress').visible" style="width: 140px;">进度</th>
            <th v-if="getColumnSetting('status').visible" style="width: 90px;">状态</th>
            <th v-if="getColumnSetting('downloader').visible" style="width: 110px;">所属下载器</th>
            <th v-if="getColumnSetting('ratio').visible" style="width: 70px;">比率</th>
            <th v-if="getColumnSetting('category').visible" style="width: 180px;">分类/标签</th>
            <th v-if="getColumnSetting('savePath').visible" style="width: 200px;">保存路径</th>
            <th v-if="getColumnSetting('addedDate').visible" style="width: 130px;">添加时间</th>
            <th v-if="getColumnSetting('actions').visible" class="action-column" style="width: 140px;">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(torrent, index) in sortedList"
            :key="`${torrent.hash}-${torrent.downloaderId || torrent.downloader_id}-${index}`"
            :class="{selected: currentRow?.hash === torrent.hash}"
            @click="handleRowClick(torrent)"
          >
            <td>
              <el-checkbox
                v-model="torrent.checked"
                @change="handleSelectionChange"
                @click.native.stop
              />
            </td>
            <td v-if="getColumnSetting('name').visible">
              <div class="torrent-name">
                <div
                  class="torrent-status-icon"
                  :class="torrent.status"
                >
                  {{ getStatusIcon(torrent.status) }}
                </div>
                <div class="torrent-name-text" :title="torrent.name">
                  {{ torrent.name }}
                </div>
              </div>
            </td>
            <td v-if="getColumnSetting('downloadSpeed').visible">
              <span class="speed-value download">{{ formatSpeed(getTorrentSpeed(torrent, 'download')) }}</span>
            </td>
            <td v-if="getColumnSetting('uploadSpeed').visible">
              <span class="speed-value upload">{{ formatSpeed(getTorrentSpeed(torrent, 'upload')) }}</span>
            </td>
            <td v-if="getColumnSetting('size').visible">{{ formatFileSize(torrent.size) }}</td>
            <td v-if="getColumnSetting('progress').visible">
              <div class="progress-wrapper">
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    :style="{width: `${torrent.progress || 0}%`}"
                  ></div>
                </div>
                <div class="progress-text">
                  {{ torrent.progress || 0 }}%
                  <span v-if="getTorrentSpeed(torrent, 'download') || getTorrentSpeed(torrent, 'upload')">
                    • {{ formatSpeed(getTorrentSpeed(torrent, 'download') || getTorrentSpeed(torrent, 'upload')) }}
                  </span>
                </div>
              </div>
            </td>
            <td v-if="getColumnSetting('status').visible">
              <span class="status-badge" :class="torrent.status">
                {{ getStatusText(torrent.status) }}
              </span>
            </td>
            <td v-if="getColumnSetting('downloader').visible">{{ torrent.downloaderName || '-' }}</td>
            <td v-if="getColumnSetting('ratio').visible">{{ formatRatio(torrent.ratio) }}</td>
            <td v-if="getColumnSetting('category').visible">
              <span v-if="torrent.category" class="tag-badge category">
                {{ torrent.category }}
              </span>
              <span v-if="torrent.tags" class="tag-badge tag">
                {{ torrent.tags }}
              </span>
              <span v-if="!torrent.category && !torrent.tags">-</span>
            </td>
            <td v-if="getColumnSetting('savePath').visible" :title="torrent.savePath">{{ torrent.savePath || '-' }}</td>
            <td v-if="getColumnSetting('addedDate').visible">{{ formatDate(torrent.addedDate) }}</td>
            <td v-if="getColumnSetting('actions').visible" class="action-column">
              <div class="action-buttons">
                <button
                  class="action-btn"
                  :class="torrent.status === 'paused' ? 'play' : 'pause'"
                  @click.stop="handleTogglePause(torrent)"
                >
                  {{ torrent.status === 'paused' ? '▶️' : '⏸️' }}
                </button>
                <button
                  class="action-btn refresh"
                  @click.stop="handleRecheck(torrent)"
                >
                  🔄
                </button>
                <button
                  class="action-btn location"
                  @click.stop="handleSetLocation(torrent)"
                  title="修改保存路径"
                >
                  📁
                </button>
                <el-dropdown
                  @command="(cmd) => handleDeleteCommand(cmd, torrent)"
                  trigger="click"
                  :hide-on-click="true"
                  :append-to-body="true"
                  @click.native.stop
                >
                  <button class="action-btn delete">
                    🗑️
                  </button>
                  <el-dropdown-menu slot="dropdown">
                    <el-dropdown-item command="4">
                      <i class="el-icon-tag"></i> 等级4: 标记为待删除(推荐)
                    </el-dropdown-item>
                    <el-dropdown-item command="3">
                      <i class="el-icon-folder-delete"></i> 等级3: 移至回收站
                    </el-dropdown-item>
                    <el-dropdown-item command="2">
                      <i class="el-icon-delete"></i> 等级2: 删除任务(保留数据)
                    </el-dropdown-item>
                    <el-dropdown-item command="1" divided>
                      <i class="el-icon-warning"></i> 等级1: 完全删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </el-dropdown>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Tracker详情卡片 -->
    <section
      class="tracker-detail-card"
      :class="{active: showTrackerDetail && currentRow}"
    >
      <div class="tracker-header">
        <h3 class="tracker-title">
          📊 Tracker详情 - {{ currentRow?.name }}
        </h3>
        <button class="tracker-close" @click="handleCloseTrackerDetail">
          ✕
        </button>
      </div>
      <div class="tracker-table-wrapper">
        <table class="tracker-table">
          <thead>
            <tr>
              <th>Tracker名称</th>
              <th>Tracker地址</th>
              <th style="width: 100px;">Announce状态</th>
              <th>Announce信息</th>
              <th style="width: 100px;">Scrape状态</th>
              <th>Scrape信息</th>
              <th style="width: 80px;" class="tracker-sticky-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(tracker, index) in (currentRow?.tracker_info || currentRow?.trackerInfo || [])"
              :key="index"
            >
              <td>{{ tracker.tracker_name || tracker.trackerName || '未知' }}</td>
              <td :title="tracker.tracker_url || tracker.trackerUrl">{{ tracker.tracker_url || tracker.trackerUrl || '-' }}</td>
              <td>
                <span
                  :class="getTrackerStatusClass(tracker.last_announce_succeeded || tracker.lastAnnounceSucceeded)"
                >
                  <template v-if="isTrackerSuccess(tracker.last_announce_succeeded || tracker.lastAnnounceSucceeded)">
                    ✓ 工作
                  </template>
                  <template v-else>
                    ✗ {{ tracker.last_announce_succeeded || tracker.lastAnnounceSucceeded || '失败' }}
                  </template>
                </span>
              </td>
              <td>{{ tracker.last_announce_msg || tracker.lastAnnounceMsg || '-' }}</td>
              <td>
                <span
                  :class="getTrackerStatusClass(tracker.last_scrape_succeeded || tracker.lastScrapeSucceeded)"
                >
                  <template v-if="isTrackerSuccess(tracker.last_scrape_succeeded || tracker.lastScrapeSucceeded)">
                    ✓ 工作
                  </template>
                  <template v-else>
                    ✗ {{ tracker.last_scrape_succeeded || tracker.lastScrapeSucceeded || '失败' }}
                  </template>
                </span>
              </td>
              <td>{{ tracker.last_scrape_msg || tracker.lastScrapeMsg || '-' }}</td>
              <td class="tracker-sticky-col">
                <el-button
                  type="text"
                  size="small"
                  :loading="tracker.reannouncing"
                  @click="handleTrackerReannounce(tracker, index)"
                >
                  汇报
                </el-button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 分页 -->
    <nav class="torrent-pagination">
      <span class="pagination-info">共 {{ total }} 条，第 {{ currentPage }}/{{ totalPages }} 页</span>
      <div class="pagination-controls">
        <!-- 每页条数选择器 -->
        <el-select
          v-model="pageSize"
          class="page-size-select"
          @change="handlePageSizeChange"
        >
          <el-option
            v-for="size in pageSizeOptions"
            :key="size"
            :label="`${size} 条/页`"
            :value="size"
          />
        </el-select>

        <button
          class="pagination-btn"
          :disabled="currentPage <= 1"
          @click="handlePageChange(currentPage - 1)"
        >
          ◀
        </button>
        <button
          v-for="page in visiblePages"
          :key="page"
          class="pagination-btn"
          :class="{active: page === currentPage}"
          @click="handlePageChange(page)"
        >
          {{ page }}
        </button>
        <button
          class="pagination-btn"
          :disabled="currentPage >= totalPages"
          @click="handlePageChange(currentPage + 1)"
        >
          ▶
        </button>
      </div>
    </nav>

    <!-- 列设置对话框 - 使用设计稿样式 -->
    <div
      class="modal-overlay"
      :class="{active: showColumnSettings}"
      @click.self="showColumnSettings = false"
    >
      <div class="modal-dialog" style="max-width: 700px;">
        <div class="modal-header">
          <h3 class="modal-title">⚙️ 列设置</h3>
          <button class="modal-close" @click="showColumnSettings = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="columns-grid">
            <label
              v-for="column in columnSettings"
              :key="column.key"
              class="column-checkbox"
            >
              <input
                type="checkbox"
                v-model="column.visible"
              />
              <span>{{ column.label }}</span>
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <div class="modal-footer-left">
            <button class="btn-secondary" @click="resetColumnSettings">重置</button>
          </div>
          <div class="modal-footer-right">
            <button class="btn-secondary" @click="showColumnSettings = false">取消</button>
            <button class="btn-primary" @click="applyColumnSettings">应用</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 批量操作对话框 -->
    <BatchOperationDialog
      :visible.sync="showBatchDialog"
      :operation="batchOperation"
      :selected-items="multipleSelection"
      @confirm="handleBatchConfirm"
    />

    <!-- 添加对话框 -->
    <TorrentAddDialog
      :visible.sync="showAddDialog"
      :downloaders="downloaderList"
      @confirm="handleAdd"
    />

    <!-- Tracker操作对话框 -->
    <TrackerOperationDialog
      :visible.sync="showTrackerOperationDialog"
      :selected-torrents="selectedTorrentsForTracker"
      :operation-type="trackerOperationType"
      @success="handleTrackerOperationSuccess"
    />

    <!-- 批量转移对话框 -->
    <BatchTransferDialog
      :visible.sync="showBatchTransferDialog"
      :torrents="multipleSelection"
      @success="handleBatchTransferSuccess"
    />

    <!-- 修改保存路径对话框 -->
    <SetLocationDialog
      :visible.sync="showSetLocationDialog"
      :torrents="selectedTorrentsForLocation"
      @success="handleSetLocationSuccess"
    />

    <GlobalReplaceTrackerDialog
      :visible.sync="showGlobalReplaceDialog"
      @success="handleGlobalReplaceSuccess"
    />

    <!-- 高级搜索对话框 -->
    <el-dialog
      title="🔍 高级搜索"
      :visible.sync="showAdvancedSearchDialog"
      width="80%"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      class="advanced-search-dialog"
    >
      <AdvancedSearchBuilder
        ref="advancedSearchBuilder"
        :searching="advancedSearchSearching"
        @search="handleAdvancedSearchFromBuilder"
        @reset="handleResetAdvancedSearch"
        @save-template="handleSaveSearchTemplate"
      />
    </el-dialog>

    <!-- 重复检测对话框（不再需要弹窗，结果直接显示在主列表中） -->
    <!-- <DuplicateTorrentsDialog
      :visible.sync="showDuplicateTorrentsDialog"
      @close="handleDuplicateTorrentsDialogClose"
      @refresh="handleRefreshDuplicateTorrents"
    /> -->
  </div>
</template>
<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import BatchButton from '@/components/BatchButton/index.vue'
import {
  getTorrentList,
  addTorrent,
  deleteTorrents,
  deleteTorrentsWithLevel,
  deleteBatchAsync,
  getBatchDeleteStatus,
  pauseTorrents,
  resumeTorrents,
  recheckTorrents,
  advancedSearch,
  getDuplicateTorrents,
  getDownloaderList,
  DownloaderSimple,
  reannounceTorrents,
  getActiveTorrents
} from '@/api/torrents'
import { TorrentStatus } from '@/types/torrent'
import { STATUS_OPTIONS, getStatusIcon, getStatusText } from '@/constants/status-config'
import ThemeManager, { ThemeType } from '@/utils/theme-manager'
import {
  normalizeTorrent,
  getTorrentId,
  getDownloaderId,
  formatFileSize,
  formatSpeed,
  formatDate,
  formatRatio,
  truncateText,
  extractErrorMessage,
  normalizePaginatedResponse,
  debounce
} from '@/utils/formatters'

@Component({
  name: 'TorrentsManagement',
  components: {
    BatchButton,
    BatchOperationDialog: () => import('./components/BatchOperationDialog.vue'),
    AdvancedSearchBuilder: () => import('@/components/torrents/AdvancedSearchBuilder.vue'),
    TorrentAddDialog: () => import('./components/TorrentAddDialog.vue'),
    TrackerOperationDialog: () => import('./components/TrackerOperationDialog.vue'),
    GlobalReplaceTrackerDialog: () => import('./components/GlobalReplaceTrackerDialog.vue'),
    BatchTransferDialog: () => import('./components/BatchTransferDialog.vue'),
    SetLocationDialog: () => import('./components/SetLocationDialog.vue'),
    // DuplicateTorrentsDialog: () => import('@/components/torrents/DuplicateTorrentsDialog.vue') // 不再需要弹窗
  }
})
export default class extends Vue {
  // 主题相关
  private currentTheme: ThemeType = 'emerald'
  private allThemes = ThemeManager.getAllThemes()

  // 数据状态
  private list: any[] = []
  private total = 0
  private listLoading = true
  private multipleSelection: any[] = []

  // 实时速度轮询
  private speedTimer: number | null = null
  private _isDestroyed = false
  private activeSpeedMap: Record<string, { downloadSpeed: number, uploadSpeed: number, progress: number }> = {}

  // 分页相关
  private currentPage = 1
  private pageSize = 20
  private pageSizeOptions = [10, 20, 50, 100, 200]

  // 复选框相关
  private selectAll = false
  private isIndeterminate = false

  // 弹窗显示状态
  private showAddDialog = false
  private showBatchDialog = false
  private showColumnSettings = false
  private showTrackerOperationDialog = false
  private showGlobalReplaceDialog = false
  private showAdvancedSearchDialog = false
  private showBatchTransferDialog = false
  private showSetLocationDialog = false
  private advancedSearchSearching = false

  // 修改路径相关
  private selectedTorrentsForLocation: any[] = []

  // 重复检测相关（不再需要弹窗）
  // private showDuplicateTorrentsDialog = false

  // 批量操作
  // 辅助方法：按下载器ID分组种子
  private groupTorrentsByDownloader(torrents: Torrent[]) {
    const groups: Record<string, Torrent[]> = {}
    torrents.forEach(torrent => {
      // P1-1修复：添加空值检查，防止torrent对象为null/undefined
      if (!torrent) {
        console.warn('跳过空种子对象')
        return
      }

      // P1-1修复：使用可选链操作符防止属性访问异常
      const downloaderId = torrent?.downloader_id || torrent?.downloaderId

      // P1-1修复：如果无法获取下载器ID，跳过该种子
      if (!downloaderId) {
        console.warn('种子缺少下载器ID，跳过:', torrent)
        return
      }

      if (!groups[downloaderId]) {
        groups[downloaderId] = []
      }
      groups[downloaderId].push(torrent)
    })
    return groups
  }

  private batchOperation = ''
  private selectedTorrentsForTracker: any[] = []
  private trackerOperationType: 'add' | 'replace' | 'modify' | '' = ''

  // Tracker详情
  private showTrackerDetail = false
  private currentRow: any = null

  // 搜索相关
  private listQuery = {
    skip: 0,
    limit: 20,  // 初始默认值，会在 handlePageSizeChange 中动态更新
    name_like: '',
    downloader_id: [] as string[],  // 支持多选
    status: [] as string[],         // 支持多选
    showActiveOnly: false,          // 仅显示活动种子（有速度的种子）
    sort_by: 'added_date',
    sort_order: 'desc'
  }

  // 列设置
  private columnSettings = [
    { key: 'name', label: '种子名称', visible: true },
    { key: 'downloadSpeed', label: '下载速度', visible: true },
    { key: 'uploadSpeed', label: '上传速度', visible: true },
    { key: 'size', label: '大小', visible: true },
    { key: 'progress', label: '进度', visible: true },
    { key: 'status', label: '状态', visible: true },
    { key: 'downloader', label: '所属下载器', visible: true },
    { key: 'ratio', label: '比率', visible: true },
    { key: 'category', label: '分类/标签', visible: true },
    { key: 'savePath', label: '保存路径', visible: true },
    { key: 'addedDate', label: '添加时间', visible: true },
    { key: 'actions', label: '操作', visible: true }
  ]

  // 下载器列表
  private downloaderList: DownloaderSimple[] = []

  // 计算属性

  /**
   * 状态选项列表（使用统一配置）
   */
  get statusOptions() {
    return STATUS_OPTIONS
  }
  /**
   * 计算总页数（修复边界情况：total=0时返回0）
   */
  get totalPages() {
    if (this.total === 0) return 0
    return Math.ceil(this.total / this.pageSize)
  }

  get visiblePages() {
    const pages: number[] = []
    const maxVisible = 5
    let start = Math.max(1, this.currentPage - Math.floor(maxVisible / 2))
    let end = Math.min(this.totalPages, start + maxVisible - 1)

    if (end - start < maxVisible - 1) {
      start = Math.max(1, end - maxVisible + 1)
    }

    for (let i = start; i <= end; i++) {
      pages.push(i)
    }

    return pages
  }

  async created() {
    // 初始化主题
    ThemeManager.initTheme()
    this.currentTheme = ThemeManager.getCurrentTheme()

    await this.getDownloaderList()
    await this.getList()
    this.loadUserPreferences()
    this.startSpeedPolling()
  }

  beforeDestroy() {
    try {
      this.stopSpeedPolling()
    } catch (e) {
      console.error('[速度轮询] 清理定时器失败:', e)
    }
  }

  // 主题切换
  private handleThemeChange(theme: ThemeType) {
    this.currentTheme = theme
    ThemeManager.setTheme(theme)
  }

  // 获取种子列表
  private async getList() {
    this.listLoading = true
    try {
      const params = { ...this.listQuery }

      // 检查是否需要前端过滤"活动"种子
      const showActiveOnly = params.showActiveOnly === true

      // 移除 showActiveOnly 属性，不发送给后端
      delete params.showActiveOnly

      // 处理数组参数：转换为逗号分隔的字符串
      if (params.downloader_id && Array.isArray(params.downloader_id)) {
        params.downloader_id = params.downloader_id.join(',')
      }
      if (params.status && Array.isArray(params.status)) {
        params.status = params.status.join(',')
      }

      // 移除空值
      Object.keys(params).forEach(key => {
        const value = params[key as keyof typeof params]
        if (value === '' || value === null || value === undefined) {
          delete params[key as keyof typeof params]
        }
      })

      const response = await getTorrentList(params)

      // 使用统一的响应处理工具
      const { list, total } = normalizePaginatedResponse<any>(response)

      // 规范化种子数据并提供默认值
      let normalizedList = list.map(normalizeTorrent).map(item => ({
        ...item,
        checked: false
      }))

      // 前端过滤"仅显示活动种子"：筛选出有速度的种子
      if (showActiveOnly) {
        normalizedList = normalizedList.filter(item => {
          const speed = this.activeSpeedMap[item.hash]
          return speed && (speed.downloadSpeed > 0 || speed.uploadSpeed > 0)
        })
      }

      this.list = normalizedList
      this.total = showActiveOnly ? normalizedList.length : total
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('获取种子列表失败:', error)
      this.$message.error(errorMessage || '获取种子列表失败')
      this.list = []
      this.total = 0
    } finally {
      this.listLoading = false
    }
  }

  // 获取下载器列表
  private async getDownloaderList() {
    try {
      const response = await getDownloaderList()
      this.downloaderList = response.data || []
    } catch (error) {
      console.error('获取下载器列表失败:', error)
    }
  }

  // 搜索
  private handleFilter() {
    this.listQuery.skip = 0
    this.currentPage = 1
    this.getList()
  }

  // 防抖搜索（300ms延迟）
  private debouncedSearch = debounce(this.handleFilter, 300)

  // 清空搜索
  private handleClearFilter() {
    // 🔥 修复：使用当前 pageSize，避免硬编码为 20
    this.listQuery = {
      skip: 0,
      limit: this.pageSize,  // 使用当前的 pageSize 值
      name_like: '',
      downloader_id: [],  // 清空为空数组
      status: [],         // 清空为空数组
      sort_by: 'added_date',
      sort_order: 'desc'
    }
    this.getList()
  }

  // 手动刷新（静态数据 + 速度数据同时刷新）
  private handleManualRefresh() {
    this.getList()
    this.loadActiveSpeed()
  }

  // 分页切换
  private handlePageChange(page: number) {
    this.currentPage = page
    this.listQuery.skip = (page - 1) * this.pageSize
    this.getList()
  }

  // 每页条数变更
  private handlePageSizeChange(newSize: number) {
    this.pageSize = newSize
    // 🔥 修复：同步更新 listQuery.limit，确保 API 请求使用正确的分页大小
    this.listQuery.limit = newSize
    // 重新计算当前页码，确保不会超出总页数
    const newTotalPages = Math.ceil(this.total / this.pageSize)
    if (this.currentPage > newTotalPages && newTotalPages > 0) {
      this.currentPage = newTotalPages
    }
    // 重置到第一页或重新计算 skip
    this.listQuery.skip = (this.currentPage - 1) * this.pageSize
    this.getList()
    this.$message.success(`每页显示 ${newSize} 条数据`)
  }

  // 全选/取消全选
  private handleSelectAll(checked: boolean) {
    this.list.forEach(item => {
      item.checked = checked
    })
    this.updateMultipleSelection()
  }

  // 更新选中项
  private handleSelectionChange() {
    this.updateMultipleSelection()
  }

  private updateMultipleSelection() {
    this.multipleSelection = this.list.filter(item => item.checked)
    this.selectAll = this.multipleSelection.length === this.list.length && this.list.length > 0
    this.isIndeterminate = this.multipleSelection.length > 0 && this.multipleSelection.length < this.list.length
  }

  // 行点击
  private handleRowClick(row: any) {
    if (this.currentRow?.hash === row.hash) {
      this.handleCloseTrackerDetail()
    } else {
      this.currentRow = row
      this.showTrackerDetail = true
    }
  }

  private handleCloseTrackerDetail() {
    this.showTrackerDetail = false
    this.currentRow = null
  }

  /**
   * 判断tracker状态是否为成功状态
   * 基于 tracker_status.py 枚举的中文值
   * 成功状态：工作中
   */
  private isTrackerSuccess(status: string | undefined): boolean {
    if (!status) return false
    return status === '工作中'
  }

  /**
   * 获取tracker状态的样式类名
   * 成功状态：working (绿色✓)
   * 失败状态：error (红色✗)
   * 中性状态：neutral (灰色)
   */
  private getTrackerStatusClass(status: string | undefined): string {
    if (!status) return 'tracker-status-neutral'

    if (this.isTrackerSuccess(status)) {
      return 'tracker-status-working'
    }

    // 失败状态
    if (['工作失败', '已禁用', '超时', '已清除'].includes(status)) {
      return 'tracker-status-error'
    }

    // 中性状态
    return 'tracker-status-neutral'
  }

  /**
   * 处理单个Tracker的汇报操作
   */
  private async handleTrackerReannounce(tracker: any, index: number) {
    if (!this.currentRow?.hash) {
      this.$message.error('种子信息不完整，无法汇报')
      return  // ✅ 修复：添加hash检查
    }

    const downloaderId = this.currentRow.downloader_id || this.currentRow.downloaderId

    // 设置loading状态
    this.$set(tracker, 'reannouncing', true)

    try {
      const response = await reannounceTorrents({
        hashes: [this.currentRow.hash],
        downloader_id: downloaderId
      })

      if (response.code === '200') {
        this.$message.success(`Tracker汇报成功`)
        // 刷新种子列表
        await this.getList()
      } else {
        this.$message.error(response.msg || 'Tracker汇报失败')
      }
    } catch (error) {
      console.error('Tracker汇报失败:', error)
      this.$message.error('Tracker汇报失败')
    } finally {
      // 清除loading状态
      this.$set(tracker, 'reannouncing', false)
    }
  }

  // 批量操作
  private async handleBatchStart() {
    if (this.multipleSelection.length === 0) return
    try {
      // 按下载器ID分组
      const groups = this.groupTorrentsByDownloader(this.multipleSelection)
      
      // 并行调用所有下载器的恢复操作
      const promises = Object.entries(groups).map(([downloaderId, torrents]) => {
        const hashes = torrents.map(t => t.hash)
        return resumeTorrents({ downloader_id: downloaderId, hashes })
      })
      
      // P2-1修复：使用Promise.allSettled替代Promise.all，提供更精细的错误反馈
      const results = await Promise.allSettled(promises)

      // 统计成功和失败的数量
      const succeeded = results.filter(r => r.status === 'fulfilled').length
      const failed = results.filter(r => r.status === 'rejected').length

      // 汇总结果
      const total = this.multipleSelection.length
      const downloaderCount = Object.keys(groups).length

      if (failed > 0) {
        this.$message.warning(`批量开始部分完成：成功${succeeded}个下载器，失败${failed}个下载器（共${total}个种子）`)
      } else {
        this.$message.success(`批量开始成功(${total}个种子, ${downloaderCount}个下载器)`)
      }

      this.getList()
    } catch (error) {
      console.error('批量开始失败:', error)
      this.$message.error('批量开始失败，请查看控制台')
    }
  }

  private async handleBatchPause() {
    if (this.multipleSelection.length === 0) return
    try {
      // 按下载器ID分组
      const groups = this.groupTorrentsByDownloader(this.multipleSelection)
      
      // 并行调用所有下载器的暂停操作
      const promises = Object.entries(groups).map(([downloaderId, torrents]) => {
        const hashes = torrents.map(t => t.hash)
        return pauseTorrents({ downloader_id: downloaderId, hashes })
      })
      
      // P2-1修复：使用Promise.allSettled替代Promise.all，提供更精细的错误反馈
      const results = await Promise.allSettled(promises)

      // 统计成功和失败的数量
      const succeeded = results.filter(r => r.status === 'fulfilled').length
      const failed = results.filter(r => r.status === 'rejected').length

      // 汇总结果
      const total = this.multipleSelection.length
      const downloaderCount = Object.keys(groups).length

      if (failed > 0) {
        this.$message.warning(`批量暂停部分完成：成功${succeeded}个下载器，失败${failed}个下载器（共${total}个种子）`)
      } else {
        this.$message.success(`批量暂停成功(${total}个种子, ${downloaderCount}个下载器)`)
      }

      this.getList()
    } catch (error) {
      console.error('批量暂停失败:', error)
      this.$message.error('批量暂停失败，请查看控制台')
    }
  }

  private async handleBatchRecheck() {
    if (this.multipleSelection.length === 0) return
    try {
      // 按下载器ID分组
      const groups = this.groupTorrentsByDownloader(this.multipleSelection)
      
      // 并行调用所有下载器的重检操作
      const promises = Object.entries(groups).map(([downloaderId, torrents]) => {
        const hashes = torrents.map(t => t.hash)
        return recheckTorrents({ downloader_id: downloaderId, hashes })
      })
      
      // P2-1修复：使用Promise.allSettled替代Promise.all，提供更精细的错误反馈
      const results = await Promise.allSettled(promises)

      // 统计成功和失败的数量
      const succeeded = results.filter(r => r.status === 'fulfilled').length
      const failed = results.filter(r => r.status === 'rejected').length

      // 汇总结果
      const total = this.multipleSelection.length
      const downloaderCount = Object.keys(groups).length

      if (failed > 0) {
        this.$message.warning(`批量重检部分完成：成功${succeeded}个下载器，失败${failed}个下载器（共${total}个种子）`)
      } else {
        this.$message.success(`批量重检成功(${total}个种子, ${downloaderCount}个下载器)`)
      }

      this.getList()
    } catch (error) {
      console.error('批量重检失败:', error)
      this.$message.error('批量重检失败，请查看控制台')
    }
  }

  private async handleBatchReannounce() {
    if (this.multipleSelection.length === 0) return
    try {
      // 按下载器ID分组
      const groups = this.groupTorrentsByDownloader(this.multipleSelection)

      // 并行调用所有下载器的Tracker汇报操作
      const promises = Object.entries(groups).map(([downloaderId, torrents]) => {
        const info_ids = torrents.map(t => t.info_id)
        return reannounceTorrents({ downloader_id: downloaderId, info_ids })
      })

      // 使用Promise.allSettled获取更精细的错误反馈
      const results = await Promise.allSettled(promises)

      // 统计成功和失败的数量
      const succeeded = results.filter(r => r.status === 'fulfilled').length
      const failed = results.filter(r => r.status === 'rejected').length

      // 汇总结果
      const total = this.multipleSelection.length
      const downloaderCount = Object.keys(groups).length

      if (failed > 0) {
        this.$message.warning(`Tracker汇报部分完成：成功${succeeded}个下载器，失败${failed}个下载器（共${total}个种子）`)
      } else {
        this.$message.success(`Tracker汇报成功(${total}个种子, ${downloaderCount}个下载器)`)
      }

      this.getList()
    } catch (error) {
      console.error('Tracker汇报失败:', error)
      this.$message.error('Tracker汇报失败，请查看控制台')
    }
  }

  private handleBatchDelete() {
    if (this.multipleSelection.length === 0) return
    this.$confirm(`确定要删除选中的 ${this.multipleSelection.length} 个种子吗？`, '批量删除确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async() => {
      this.$confirm('是否同时删除这些种子对应的数据文件？', '删除数据文件', {
        confirmButtonText: '同时删除种子和数据',
        cancelButtonText: '仅删除种子，保留数据',
        distinguishCancelAndClose: true,
        type: 'warning'
      }).then(async() => {
        await this.performBatchDelete(1)
      }).catch((action) => {
        if (action === 'cancel') {
          this.performBatchDelete(0)
        }
      })
    }).catch(() => undefined)
  }

  /**
   * 批量删除种子（使用Promise.all并行请求优化性能）
   */
  private async performBatchDelete(deleteData: number) {
    const results = await this.deleteTorrentsInternal(this.multipleSelection, deleteData)

    const dataFileText = deleteData === 1 ? '（已删除数据文件）' : '（已保留数据文件）'
    if (results.failCount === 0) {
      this.$message.success(`成功删除 ${results.successCount} 个种子 ${dataFileText}`)
    } else if (results.successCount === 0) {
      this.$message.error(`批量删除失败，共 ${results.failCount} 个种子删除失败`)
    } else {
      this.$message.warning(`部分删除成功：成功 ${results.successCount} 个，失败 ${results.failCount} 个 ${dataFileText}`)
    }

    this.getList()
  }

  private handleBatchTracker() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请先选择要操作的种子')
      return
    }
    this.selectedTorrentsForTracker = [...this.multipleSelection]
    this.trackerOperationType = ''
    this.showTrackerOperationDialog = true
  }
  private handleBatchTransfer() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请先选择要转移的种子')
      return
    }
    // 检查选中的种子是否都在同一下载器
    const downloaderIds = new Set(this.multipleSelection.map(t => getDownloaderId(t)))
    if (downloaderIds.has(undefined) || downloaderIds.has(null)) {
      this.$message.warning('选中种子缺少下载器信息，请刷新后重试')
      return
    }
    if (downloaderIds.size > 1) {
      this.$message.warning('批量转移只支持同一下载器的种子，请重新选择')
      return
    }
    this.showBatchTransferDialog = true
  }

  private handleBatchTransferSuccess() {
    this.showBatchTransferDialog = false
    this.getList()
    this.$message.success('批量转移操作完成')
  }

  // 修改保存路径
  private handleSetLocation(torrent: any) {
    this.selectedTorrentsForLocation = [torrent]
    this.showSetLocationDialog = true
  }

  private handleBatchSetLocation() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请先选择种子')
      return
    }

    // 验证所有选中的种子是否在同一下载器
    const downloaderIds = new Set(this.multipleSelection.map(t => getDownloaderId(t)))
    if (downloaderIds.has(undefined) || downloaderIds.has(null)) {
      this.$message.warning('选中种子缺少下载器信息，请刷新后重试')
      return
    }
    if (downloaderIds.size > 1) {
      this.$message.warning('选中的种子必须属于同一下载器')
      return
    }

    this.selectedTorrentsForLocation = this.multipleSelection
    this.showSetLocationDialog = true
  }

  private handleSetLocationSuccess() {
    this.showSetLocationDialog = false
    this.getList()
    // 成功提示已在对话框中显示，这里不需要额外提示
  }

  // 单个操作
  private async handleTogglePause(row: any) {
    try {
      const downloaderId = row.downloader_id || row.downloaderId
      if (row.status === 'paused') {
        await resumeTorrents({ downloader_id: downloaderId, hashes: [row.hash] })
        this.$message.success('开始下载成功')
      } else {
        await pauseTorrents({ downloader_id: downloaderId, hashes: [row.hash] })
        this.$message.success('暂停下载成功')
      }
      this.getList()
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('操作失败:', error)
      this.$message.error(errorMessage || '操作失败，请稍后重试')
    }
  }

  private async handleRecheck(row: any) {
    try {
      const downloaderId = row.downloader_id || row.downloaderId
      await recheckTorrents({ downloader_id: downloaderId, hashes: [row.hash] })
      this.$message.success('重新检查成功')
      this.getList()
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('重新检查失败:', error)
      this.$message.error(errorMessage || '重新检查失败，请稍后重试')
    }
  }

  private handleDelete(row: any) {
    this.$confirm('确定要删除这个种子吗？', '删除确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async() => {
      this.$confirm('是否同时删除下载的数据文件？', '删除数据文件', {
        confirmButtonText: '同时删除种子和数据',
        cancelButtonText: '仅删除种子，保留数据',
        distinguishCancelAndClose: true,
        type: 'warning'
      }).then(async() => {
        await this.performDelete(row, 1)
      }).catch((action) => {
        if (action === 'cancel') {
          this.performDelete(row, 0)
        }
      })
    }).catch(() => undefined)
  }

  /**
   * 按等级删除种子（新功能：支持4个删除等级）
   * @param level 删除等级 (1-4) - 从el-dropdown-item传递的是字符串
   * @param torrent 种子对象
   */
  private async handleDeleteCommand(level: string | number, torrent: any) {
    // 类型转换：el-dropdown-item的command属性传递字符串
    const levelNum = typeof level === 'string' ? parseInt(level, 10) : level

    const levelNames: Record<number, string> = {
      4: '标记为待删除',
      3: '移至回收站',
      2: '删除任务（保留数据）',
      1: '完全删除'
    }

    const levelName = levelNames[levelNum] || '删除'
    const confirmMessage = (levelNum === 1 || levelNum === 3)
      ? `警告：此操作将${levelName}，是否继续？`
      : `确定要将种子${levelName}吗？`

    try {
      await this.$confirm(confirmMessage, '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: levelNum === 1 ? 'error' : 'warning'
      })

      await this.executeDeleteByLevel([torrent], levelNum)
    } catch (error: any) {
      // 用户取消或其他错误
      if (error !== 'cancel') {
        const errorMessage = error?.response?.data?.msg ?? error?.message ?? '删除失败'
        this.$message.error(errorMessage)
        console.error('删除失败:', error)
      }
    }
  }

  /**
   * 批量删除命令处理（新功能：支持4个删除等级）
   * @param level 删除等级 (1-4) - 从el-dropdown-item传递的是字符串
   */
  private async handleBatchDeleteCommand(level: string | number) {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请先选择要删除的种子')
      return
    }

    // 类型转换：el-dropdown-item的command属性传递字符串
    const levelNum = typeof level === 'string' ? parseInt(level, 10) : level

    const levelNames: Record<number, string> = {
      4: '标记为待删除',
      3: '移至回收站',
      2: '删除任务（保留数据）',
      1: '完全删除'
    }

    const levelName = levelNames[levelNum] || '删除'
    const confirmMessage = `确定要将选中的 ${this.multipleSelection.length} 个种子${levelName}吗？`

    try {
      await this.$confirm(confirmMessage, '批量删除确认', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: levelNum === 1 ? 'error' : 'warning'
      })

      await this.executeDeleteByLevel(this.multipleSelection, levelNum)
    } catch (error: any) {
      // 用户取消或其他错误
      if (error !== 'cancel') {
        const errorMessage = error?.response?.data?.msg ?? error?.message ?? '批量删除失败'
        this.$message.error(errorMessage)
        console.error('批量删除失败:', error)
      }
    }
  }

  /**
   * 统一的删除执行方法（根据等级选择API）
   * 优化：避免重复显示错误消息
   * @param torrents 要删除的种子列表
   * @param level 删除等级 (1-4)
   */
  private async executeDeleteByLevel(torrents: any[], level: number) {
    try {
      // ✅ 统一使用新的异步批量删除接口（支持所有4个等级）
      await this.callDeleteWithLevelAPI(torrents, level)

      // 刷新列表
      this.getList()
    } catch (error: any) {
      const errorMessage = error?.response?.data?.msg ??
                           error?.message ??
                           '删除失败，请稍后重试'

      // 安全的错误日志（避免循环引用导致JSON序列化失败）
      try {
        console.error('[删除异常]', {
          level,
          error: errorMessage,
          errorType: error?.constructor?.name,
          hasResponse: !!error?.response
        })
      } catch (logError) {
        console.error('[删除异常] 日志记录失败:', errorMessage)
      }

      this.$message.error(errorMessage)
    }
  }

  /**
   * 调用新的按等级删除API（等级1-4，使用异步批量删除）
   * 优化：对于多个种子，使用异步批量删除接口，避免超时
   */
  private async callDeleteWithLevelAPI(torrents: any[], level: number) {
    const infoIds = torrents.map(t => getTorrentId(t))

    // 🔥 判断是否使用异步批量删除（种子数量 >= 2）
    if (torrents.length >= 2) {
      // 使用异步批量删除接口
      const response = await deleteBatchAsync({
        torrent_info_ids: infoIds,
        delete_level: level,
        operator: 'admin'
      })

      if (response.code !== '200') {
        throw new Error(response.msg || '提交删除任务失败')
      }

      const taskId = response.data?.task_id
      if (!taskId) {
        throw new Error('未返回任务ID')
      }

      // 轮询查询任务状态（每5秒一次）
      await this.pollDeleteTaskStatus(taskId, level)
    } else {
      // 单个种子：使用同步接口（保持原有逻辑）
      const response = await deleteTorrentsWithLevel({
        torrent_info_ids: infoIds,
        delete_level: level,
        operator: 'admin'
      })

      if (response.code !== '200') {
        throw new Error(response.msg || '删除失败')
      }

      // 处理响应结果
      this.handleDeleteResponse(response.data, level)
    }
  }

  /**
   * 轮询查询批量删除任务状态
   * @param taskId 任务ID
   * @param level 删除等级
   */
  private async pollDeleteTaskStatus(taskId: string, level: number) {
    const pollInterval = 5000 // 每5秒轮询一次
    const maxPollAttempts = 120 // 最大轮询次数（10分钟）
    let pollAttempts = 0

    // 显示进度提示
    const loading = this.$loading({
      lock: true,
      text: '批量删除中，请稍候...',
      spinner: 'el-icon-loading',
      background: 'rgba(0, 0, 0, 0.7)'
    })

    try {
      while (pollAttempts < maxPollAttempts) {
        const response = await getBatchDeleteStatus(taskId)

        if (response.code !== '200') {
          throw new Error(response.msg || '查询任务状态失败')
        }

        const taskData = response.data

        // 更新进度提示
        if (taskData.status === 'running') {
          const progress = taskData.success_count + taskData.failed_count
          loading.text = `批量删除中... (${progress}/${taskData.total_count})`
        }

        // 检查任务是否完成
        if (taskData.status === 'completed' || taskData.status === 'failed' || taskData.status === 'partial') {
          // 任务完成，显示结果
          this.handleDeleteTaskResult(taskData, level)
          break
        }

        // 等待5秒后继续轮询
        await new Promise(resolve => setTimeout(resolve, pollInterval))
        pollAttempts++
      }

      if (pollAttempts >= maxPollAttempts) {
        this.$message.warning('批量删除任务执行时间过长，请稍后查看任务状态')
      }
    } finally {
      loading.close()
    }
  }

  /**
   * 处理批量删除任务结果
   * @param taskData 任务数据
   * @param level 删除等级
   */
  private handleDeleteTaskResult(taskData: any, level: number) {
    const { status, total_count, success_count, failed_count, failed_items } = taskData

    if (status === 'completed') {
      // 全部成功
      this.$message.success(`批量删除完成，成功删除 ${success_count} 个种子`)
    } else if (status === 'failed') {
      // 全部失败
      this.$message.error(`批量删除失败：${taskData.error_message || '未知错误'}`)
    } else if (status === 'partial') {
      // 部分成功
      this.$message.warning(`批量删除部分完成：成功 ${success_count} 个，失败 ${failed_count} 个`)

      // 如果有失败的项，显示详情
      if (failed_items && failed_items.length > 0) {
        const failedNames = failed_items.slice(0, 5).map((item: any) => {
          // 尝试从表格数据中找到种子名称
          const torrent = this.tableData.find((t: any) => getTorrentId(t) === item.info_id)
          return torrent?.name || item.info_id
        }).join('、')

        if (failed_items.length <= 5) {
          this.$notify.warning({
            title: '删除失败详情',
            message: `以下种子删除失败：${failedNames}`,
            duration: 5000
          })
        } else {
          this.$notify.warning({
            title: '删除失败详情',
            message: `以下种子删除失败：${failedNames} 等${failed_items.length}个`,
            duration: 5000
          })
        }
      }
    }
  }

  /**
   * 处理同步删除API响应结果
   * @param data 响应数据
   * @param level 删除等级
   */
  private handleDeleteResponse(data: any, level: number) {
    // 🔥 处理等级3删除的降级情况
    if (level === 3 && data?.level4_downgraded && data.level4_downgraded.length > 0) {
      const downgraded = data.level4_downgraded

      // 显示警告消息
      this.$message.warning(`已将 ${downgraded.length} 个种子降级为等级4删除（备份失败）`)

      // 详细信息可展开查看（最多5个）
      if (downgraded.length <= 5) {
        const names = downgraded.map((d: any) => d.torrent_name).join('、')
        this.$notify.warning({
          title: '降级详情',
          message: `以下种子备份失败，已降级为等级4：${names}`,
          duration: 5000
        })
      } else {
        // 超过5个只显示前5个
        const names = downgraded.slice(0, 5).map((d: any) => d.torrent_name).join('、')
        this.$notify.warning({
          title: '降级详情',
          message: `以下种子备份失败，已降级为等级4：${names} 等${downgraded.length}个`,
          duration: 5000
        })
      }
    }

    // 处理部分成功的情况
    if (data?.failed && data.failed.length > 0) {
      this.$message.warning(`删除完成：失败 ${data.failed.length} 个`)
    }

    // 显示成功消息（降级情况已经在上面显示过，这里只显示完全成功的情况）
    // ✅ 统计所有等级的成功数量（包括 level 1/2）
    const successCount =
      (data?.level1_success?.length || 0) +
      (data?.level2_success?.length || 0) +
      (data?.level3_success?.length || 0) +
      (data?.level4_success?.length || 0)

    if (successCount > 0 && !data?.level4_downgraded?.length) {
      // 没有降级才显示成功消息
      if (level === 3) {
        const level3Count = data?.level3_success?.length || 0
        this.$message.success(
          level3Count > 0
            ? `等级3删除成功 ${level3Count} 个`
            : `删除完成，成功 ${successCount} 个`
        )
      } else if (level === 2) {
        this.$message.success(`等级2删除完成，成功 ${successCount} 个`)
      } else if (level === 1) {
        this.$message.success(`等级1删除完成，成功 ${successCount} 个`)
      } else {
        this.$message.success(`删除完成，成功 ${successCount} 个`)
      }
    }
  }

  /**
   * 调用旧的删除API（等级1和2）
   * 优化：聚合错误消息，避免多次弹框 + 立即从本地列表移除已删除项
   */
  private async callDeleteLegacyAPI(torrents: any[], deleteData: number) {
    const results = await this.deleteTorrentsInternal(torrents, deleteData)

    const dataFileText = deleteData === 1 ? '（已删除数据文件）' : '（已保留数据文件）'

    if (results.failCount === 0) {
      // 全部成功 - 立即从本地列表中移除已删除项
      this.removeDeletedTorrentsFromList(results.deletedTorrents)
      this.$message.success(`成功删除 ${results.successCount} 个种子 ${dataFileText}`)
    } else if (results.successCount === 0) {
      // 全部失败 - 显示详细的错误信息（保留错误计数）
      const errorCounts = results.errors.reduce((acc, err) => {
        acc[err] = (acc[err] || 0) + 1
        return acc
      }, {} as Record<string, number>)

      const errorMsg = Object.keys(errorCounts).length > 0
        ? Object.entries(errorCounts)
            .map(([err, count]) => `${err}(${count}次)`)
            .join('; ')
        : `共 ${results.failCount} 个种子删除失败`

      console.error('[批量删除失败]', {
        total: results.failCount,
        errorCounts
      })

      this.$message.error(`批量删除失败: ${errorMsg}`)
    } else {
      // 部分成功 - 移除成功删除的项
      this.removeDeletedTorrentsFromList(results.deletedTorrents)

      // 保留错误计数，便于调试
      const errorCounts = results.errors.reduce((acc, err) => {
        acc[err] = (acc[err] || 0) + 1
        return acc
      }, {} as Record<string, number>)

      const errorDetail = Object.keys(errorCounts).length > 0
        ? ` 失败原因: ${Object.entries(errorCounts)
            .map(([err, count]) => `${err}(${count}次)`)
            .join('; ')}`
        : ''

      this.$message.warning(
        `部分删除成功：成功 ${results.successCount} 个，失败 ${results.failCount} 个${dataFileText}${errorDetail}`
      )
    }
  }

  /**
   * 从本地列表中移除已删除的种子（立即更新UI）
   * @param deletedTorrents 成功删除的种子列表
   */
  private removeDeletedTorrentsFromList(deletedTorrents: any[]) {
    // 确保参数是数组
    if (!Array.isArray(deletedTorrents) || deletedTorrents.length === 0) {
      console.warn('[removeDeletedTorrentsFromList] Invalid parameter:', deletedTorrents)
      return
    }

    // 提取已删除种子的唯一标识 - 过滤掉undefined/null值，防止Set污染
    const deletedHashes = new Set(
      deletedTorrents
        .map(t => t.hash || t.hash_str)
        .filter(hash => hash !== undefined && hash !== null)
    )
    const deletedIds = new Set(
      deletedTorrents
        .map(t => t.info_id || t.infoId)
        .filter(id => id !== undefined && id !== null)
    )

    console.log('[删除记录]', {
      hashCount: deletedHashes.size,
      idCount: deletedIds.size,
      totalDeleted: deletedTorrents.length
    })

    // 从本地列表中移除已删除的种子
    const originalLength = this.list.length
    this.list = this.list.filter(item => {
      const itemHash = item.hash || item.hash_str
      const itemId = item.info_id || item.infoId

      // 只有当标识符有效且匹配时才移除，避免误删
      const shouldRemove = (itemHash && deletedHashes.has(itemHash)) ||
                           (itemId && deletedIds.has(itemId))
      return !shouldRemove
    })

    const removedCount = originalLength - this.list.length
    console.log(`[本地列表更新] 移除了 ${removedCount} 个已删除的种子`)
  }

  /**
   * 单个删除种子
   */
  /**
   * 单个删除种子
   */
  private async performDelete(row: any, deleteData: number) {
    try {
      await this.deleteTorrentsInternal([row], deleteData)

      const message = deleteData === 1 ? '删除成功（已删除数据文件）' : '删除成功（已保留数据文件）'
      this.$message.success(message)

      this.getList()
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('删除失败:', error)
      this.$message.error(errorMessage || '删除失败，请稍后重试')
    }
  }

  /**
   * 内部删除逻辑（DRY原则 - 统一处理单个和批量删除）
   * 使用Promise.all并行请求提升性能
   * @param torrents 要删除的种子列表
   * @param deleteData 是否删除数据文件 (0: 仅删除种子, 1: 同时删除数据文件)
   * @returns 成功和失败计数 + 错误信息列表 + 成功删除的种子列表
   */
  private async deleteTorrentsInternal(
    torrents: any[],
    deleteData: number
  ): Promise<{ successCount: number, failCount: number, errors: string[], deletedTorrents: any[] }> {
    let successCount = 0
    let failCount = 0
    const errors: string[] = []  // 统一收集所有错误消息
    const deletedTorrents: any[] = []  // 记录成功删除的种子

    // 使用Promise.all并行执行删除操作，提升性能
    const deletePromises = torrents.map(async(torrent) => {
      try {
        const infoId = getTorrentId(torrent)
        const downloaderId = getDownloaderId(torrent)

        await deleteTorrents({
          info_id: infoId,
          downloader_id: downloaderId,
          delete_data: deleteData,
          id_recycle: 1
        })
        return { success: true, torrent }
      } catch (error: any) {
        // 提取并保留详细的错误消息
        const errorMsg = error?.response?.data?.msg ??
                         error?.message ??
                         '删除失败'
        return { success: false, error: errorMsg }
      }
    })

    const results = await Promise.all(deletePromises)
    results.forEach((result) => {
      if (result.success) {
        successCount++
        if (result.torrent) {
          deletedTorrents.push(result.torrent)  // 记录成功删除的种子
        }
      } else {
        failCount++
        if (result.error) {
          errors.push(result.error)  // 收集所有错误
        }
      }
    })

    return { successCount, failCount, errors, deletedTorrents }
  }

  private async handleAdd() {
    this.showAddDialog = false
    this.getList()
  }

  // Tracker操作
  private handleTrackerOperationSuccess() {
    this.getList()
    this.$message.success('Tracker操作成功')
  }

  private handleGlobalReplaceSuccess() {
    this.getList()
    this.$message.success('全局替换Tracker成功')
  }

  // 列设置
  private getColumnSetting(key: string) {
    return this.columnSettings.find(col => col.key === key) || { visible: true }
  }

  private updateColumnVisibility() {
    // 强制更新视图，使 v-if 条件重新评估
    this.$forceUpdate()
  }

  private resetColumnSettings() {
    this.columnSettings.forEach(column => {
      column.visible = true
    })
  }

  private applyColumnSettings() {
    this.showColumnSettings = false
    this.saveUserPreferences()
    this.updateColumnVisibility()
    this.$message.success('列设置已保存')
  }

  // 高级搜索
  private handleAdvancedSearchFromBuilder(searchParams: any) {
    this.performAdvancedSearch(searchParams)
    this.showAdvancedSearchDialog = false
  }

  private handleResetAdvancedSearch() {
    const builder = this.$refs.advancedSearchBuilder as any
    if (builder && builder.resetConditions) {
      builder.resetConditions()
    }
    this.$message.success('搜索条件已重置')
  }

  private confirmAdvancedSearch() {
    const builder = this.$refs.advancedSearchBuilder as any
    if (builder && builder.onSearch) {
      builder.onSearch()
    }
  }

  private async performAdvancedSearch(searchParams: any) {
    this.advancedSearchSearching = true
    try {
      let conditionGroups: any[] = []
      let betweenGroupLogics: string[] = []

      if (searchParams.groups) {
        try {
          const groupsData = JSON.parse(searchParams.groups)
          conditionGroups = groupsData.map((group: any) => ({
            logic: group.logic?.toUpperCase() || 'AND',
            conditions: group.conditions.map((cond: any) => ({
              field: cond.field,
              operator: cond.operator,
              value: cond.value
            }))
          }))
        } catch (e) {
          console.error('解析groups参数失败:', e)
          this.$message.error('搜索条件格式错误')
          return
        }
      }

      // 解析组间逻辑关系
      if (searchParams.between_group_logics) {
        try {
          const parsed = JSON.parse(searchParams.between_group_logics)
          // P2-2修复：添加类型验证，确保解析结果是数组且元素为字符串
          if (Array.isArray(parsed)) {
            betweenGroupLogics = parsed
              .filter((item: any) => typeof item === 'string')  // 过滤非字符串元素
              .map((logic: string) => logic.toUpperCase())      // 转换为大写
            console.log('解析的组间逻辑关系:', betweenGroupLogics)
          } else {
            console.warn('between_group_logics不是数组类型，使用默认值')
            betweenGroupLogics = []
          }
        } catch (e) {
          console.error('解析between_group_logics参数失败:', e)
          // 如果解析失败，默认使用 AND
          betweenGroupLogics = []
        }
      }

      const request: any = {
        page: 1,
        limit: this.listQuery.limit || this.pageSize,  // 🔥 修复：使用 pageSize 作为后备值
        sort_by: searchParams.sort_by || this.listQuery.sort_by || 'added_date',
        sort_order: (searchParams.sort_order || this.listQuery.sort_order || 'desc') as 'asc' | 'desc'
      }

      if (conditionGroups.length === 0) {
        if (searchParams.name) request.name = searchParams.name
        if (searchParams.downloader_id) request.downloader_id = searchParams.downloader_id
        if (searchParams.status) request.status = searchParams.status
        if (searchParams.tags) request.tags = searchParams.tags
        if (searchParams.category) request.category = searchParams.category
      }

      if (conditionGroups.length > 0) {
        request.condition_groups = conditionGroups
        // 添加组间逻辑关系（如果有多个条件组）
        if (betweenGroupLogics.length > 0) {
          request.between_group_logics = betweenGroupLogics
        }
      }

      const response = await advancedSearch(request)

      if (response.code === '200' && response.data) {
        this.list = response.data.data || []
        this.total = response.data.total || 0
        this.listQuery.skip = 0
        this.currentPage = 1
        this.$message.success(`高级搜索完成，找到 ${this.total} 条结果`)
      } else {
        this.$message.error(response.msg || '搜索失败')
      }
    } catch (error) {
      console.error('高级搜索失败:', error)
      this.$message.error('高级搜索失败，请检查搜索条件')
    } finally {
      this.advancedSearchSearching = false
    }
  }

  private handleSaveSearchTemplate(template: any) {
    // 保存搜索模板
  }

  // 用户偏好
  private saveUserPreferences() {
    const columnsVisibility = this.columnSettings.reduce((acc, col) => {
      acc[col.key] = col.visible
      return acc
    }, {} as Record<string, boolean>)
    localStorage.setItem('torrents_columns_visibility', JSON.stringify(columnsVisibility))
  }

  private loadUserPreferences() {
    const savedColumnsVisibility = localStorage.getItem('torrents_columns_visibility')
    if (savedColumnsVisibility) {
      try {
        const visibilityMap = JSON.parse(savedColumnsVisibility)
        this.columnSettings.forEach(col => {
          if (col.key in visibilityMap) {
            col.visible = visibilityMap[col.key]
          }
        })
      } catch (error) {
        console.error('加载列设置失败:', error)
      }
    }
  }

  // 工具方法
  private formatFileSize(size: number | null | undefined): string {
    return formatFileSize(size)
  }

  private formatSpeed(speed: number | null | undefined): string {
    return formatSpeed(speed)
  }

  // ==================== 实时速度轮询 ====================

  /** 用户是否正在使用筛选条件（搜索/筛选时禁用速度排序） */
  private get isUserFiltering(): boolean {
    const q = this.listQuery
    return !!(
      (q.name_like && q.name_like.trim() !== '') ||
      (q.downloader_id && q.downloader_id.length > 0) ||
      (q.status && q.status.length > 0)
    )
  }

  /** 排序后的列表（活跃种子优先，始终生效） */
  private get sortedList(): any[] {
    if (!this.list || this.list.length === 0) return []
    return [...this.list].sort((a, b) => {
      const aSpeed = this.getTorrentSpeed(a, 'download') || this.getTorrentSpeed(a, 'upload') || 0
      const bSpeed = this.getTorrentSpeed(b, 'download') || this.getTorrentSpeed(b, 'upload') || 0
      const aActive = aSpeed > 0 ? 1 : 0
      const bActive = bSpeed > 0 ? 1 : 0
      if (aActive !== bActive) return bActive - aActive
      if (aActive === 1) return bSpeed - aSpeed
      return 0
    })
  }

  /** 获取种子的实时显示速度（优先使用轮询数据，降级使用静态数据） */
  private getTorrentSpeed(torrent: any, type: 'download' | 'upload'): number | null {
    const active = this.activeSpeedMap[torrent.hash]
    if (active) {
      return type === 'download' ? active.downloadSpeed : active.uploadSpeed
    }
    return type === 'download' ? (torrent.downloadSpeed ?? null) : (torrent.uploadSpeed ?? null)
  }

  /** 加载活跃种子实时速度和进度 */
  private async loadActiveSpeed() {
    const requestId = Date.now()

    try {
      const res = await getActiveTorrents()
      if (res.code === '200' && res.data) {
        const map: Record<string, { downloadSpeed: number, uploadSpeed: number, progress: number }> = {}
        const torrents = res.data as ActiveTorrentSpeed[]
        torrents.forEach((t: ActiveTorrentSpeed) => {
          // 防御性检查：确保hash字段存在
          if (!t.hash) {
            console.warn('[速度轮询] 跳过无效种子数据:', t)
            return
          }
          // 更新速度映射（用于排序和高亮）
          map[t.hash] = {
            downloadSpeed: t.downloadSpeed ?? 0,
            uploadSpeed: t.uploadSpeed ?? 0,
            progress: t.progress ?? 0
          }

          // 直接更新列表中对应种子的实时数据
          const torrentInList = this.list.find(item => item.hash === t.hash)
          if (torrentInList) {
            torrentInList.downloadSpeed = t.downloadSpeed ?? 0
            torrentInList.uploadSpeed = t.uploadSpeed ?? 0
            torrentInList.progress = t.progress ?? 0
          }
        })
        this.activeSpeedMap = map
        console.debug(`[速度轮询] 请求 ${requestId} 完成，更新 ${Object.keys(map).length} 个活跃种子`)
      }
    } catch (e) {
      // 静默失败，不影响主流程
      console.debug(`[速度轮询] 请求 ${requestId} 失败:`, e)
    }
  }

  /** 启动速度轮询（请求完成后等待1秒再发下一次） */
  private startSpeedPolling() {
    this._isDestroyed = false
    const poll = async() => {
      await this.loadActiveSpeed()
      // 组件已销毁时不再调度下一次
      if (this._isDestroyed) return
      this.speedTimer = window.setTimeout(poll, 1000)
    }
    poll()
  }

  /** 停止速度轮询 */
  private stopSpeedPolling() {
    this._isDestroyed = true
    if (this.speedTimer) {
      clearTimeout(this.speedTimer)
      this.speedTimer = null
    }
  }

  private formatDate(timestamp: number | string | null | undefined): string {
    return formatDate(timestamp)
  }

  private formatRatio(ratio: number | string | null | undefined) {
    return formatRatio(ratio)
  }

  private getStatusIcon(status: string | TorrentStatus): string {
    return getStatusIcon(String(status))
  }

  private getStatusText(status: string | TorrentStatus): string {
    return getStatusText(String(status))
  }

  private handleBatchConfirm(operation: string, selectedItems: any[]) {
    this.showBatchDialog = false
    // 批量操作确认处理
  }

  // ==================== 重复种子相关方法 ====================

  /**
   * 查找重复任务（直接显示在主列表中）
   */
  private async handleShowDuplicateTorrents() {
    this.listLoading = true
    try {
      // 处理数组参数：转换为逗号分隔的字符串
      const downloaderIdParam = this.listQuery.downloader_id && this.listQuery.downloader_id.length > 0
        ? this.listQuery.downloader_id.join(',')
        : undefined
      const statusParam = this.listQuery.status && this.listQuery.status.length > 0
        ? this.listQuery.status.join(',')
        : undefined

      const params = {
        name_like: this.listQuery.name_like || undefined,
        downloader_id: downloaderIdParam,
        status: statusParam,
        page: this.currentPage,
        pageSize: this.pageSize
      }

      const response = await getDuplicateTorrents(params)

      const { list, total } = normalizePaginatedResponse<any>(response)

      this.list = list.map(normalizeTorrent).map(item => ({
        ...item,
        checked: false
      }))

      this.total = total
      this.listQuery.skip = 0
      this.currentPage = 1

      this.$message.success(`查找完成，共找到 ${total} 条记录`)
    } catch (error: any) {
      const errorMessage = extractErrorMessage(error) || '查找失败'
      console.error('查找重复任务失败:', error)
      this.$message.error(errorMessage || '查找失败，请稍后重试')
      this.list = []
      this.total = 0
    } finally {
      this.listLoading = false
    }
  }

  // 以下方法不再需要（已移除弹窗）
  // /**
  //  * 关闭重复种子对话框
  //  */
  // private handleDuplicateTorrentsDialogClose() {
  //   this.showDuplicateTorrentsDialog = false
  // }
  //
  // /**
  //  * 刷新重复种子列表
  //  */
  // private handleRefreshDuplicateTorrents() {
  //   // 对话框内部会自动刷新
  // }
}
</script>

<style lang="scss" scoped>
@import '@/styles/torrent-theme.scss';

// ========================================
// 多选下拉框样式优化
// ========================================
.search-select {
  // 优化多选标签样式
  ::v-deep .el-tag {
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  // 优化下拉框宽度自适应
  ::v-deep .el-select__tags {
    max-width: calc(100% - 30px);
  }
}

// 活动种子复选框样式
.active-only-checkbox {
  margin-left: 12px;
  margin-right: 12px;

  ::v-deep .el-checkbox__label {
    color: var(--color-text-primary);
    font-size: 14px;
  }

  ::v-deep .el-checkbox__input.is-checked + .el-checkbox__label {
    color: var(--color-accent-primary);
  }
}

// ========================================
// 列设置弹框补充样式
// ========================================
.columns-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

// ========================================
// 弹窗基础样式（与 torrent-theme.scss 一致）
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
  max-width: 700px;
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

// ========================================
// 重复检测按钮样式（白色按钮）
// ========================================
.duplicate-detection-btn {
  background: white !important;
  color: var(--color-text-primary) !important;
  border: 1px solid var(--color-border-primary) !important;
  transition: all var(--transition-base) ease;

  &:hover:not(:disabled) {
    background: var(--color-bg-secondary) !important;
    border-color: var(--color-border-secondary);
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

// ========================================
// 刷新按钮样式（白色按钮）
// ========================================
.refresh-btn {
  background: white !important;
  color: var(--color-text-primary) !important;
  border: 1px solid var(--color-border-primary) !important;
  transition: all var(--transition-base) ease;

  &:hover:not(:disabled) {
    background: var(--color-bg-secondary) !important;
    border-color: var(--color-border-secondary);
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

// ========================================
// 操作按钮样式
// ========================================
.action-buttons {
  display: flex;
  gap: 4px;
  align-items: center;
}

.action-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;

  &:hover {
    background: rgba(0, 0, 0, 0.05);
  }

  &.play {
    color: #67C23A;
  }

  &.pause {
    color: #E6A23C;
  }

  &.refresh {
    color: #409EFF;
  }

  &.location {
    color: #909399;
    &:hover {
      color: #409EFF;
    }
  }

  &.delete {
    color: #F56C6C;
  }
}

// ========================================
// 速度列样式
// ========================================
.speed-value {
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
  color: var(--color-text-secondary);

  &.download::before {
    content: '▼';
    margin-right: 2px;
    font-size: 10px;
    opacity: 0.6;
  }

  &.upload::before {
    content: '▲';
    margin-right: 2px;
    font-size: 10px;
    opacity: 0.6;
  }
}
</style>
