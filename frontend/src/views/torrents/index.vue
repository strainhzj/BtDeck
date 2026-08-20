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
        <AdvancedMultiSelect
          v-model="listQuery.downloader_id"
          placeholder="请选择下载器"
          :options="downloaderOptions"
          :allow-create="false"
          :show-mode-toggle="false"
          :virtual-scroll-threshold="100"
          :list-height="240"
          style="width: 200px;"
          class="search-select"
          @change="handleFilter"
        />
        <AdvancedMultiSelect
          v-model="listQuery.status"
          placeholder="请选择种子状态"
          :options="statusOptions"
          :allow-create="false"
          :show-mode-toggle="false"
          :virtual-scroll-threshold="100"
          :list-height="240"
          style="width: 180px;"
          class="search-select"
          @change="handleFilter"
        />
        <AdvancedMultiSelect
          v-model="listQuery.tracker_domain"
          placeholder="请选择tracker"
          :options="trackerDomainOptions"
          :allow-create="false"
          :show-mode-toggle="false"
          :virtual-scroll-threshold="100"
          :list-height="240"
          style="width: 220px;"
          class="search-select"
          @change="handleFilter"
        />
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
        <el-button class="advanced-search-btn" @click="openAdvancedSearch">
          高级搜索
        </el-button>
        <label
          class="duplicate-search-switch"
          :class="{'is-active': showingDuplicates}"
        >
          <el-switch
            v-model="showingDuplicates"
            active-color="var(--color-success, #10b981)"
            inactive-color="var(--color-border-secondary, #c0c4cc)"
            aria-label="查找重复任务"
            @change="handleDuplicateSearchToggle"
          />
          <span>查找重复任务</span>
        </label>
        <el-button class="clear-btn" @click="handleClearFilter">
          清空
        </el-button>
        <el-button class="refresh-btn" @click="handleManualRefresh" :loading="listLoading">
          刷新
        </el-button>
      </div>
    </section>

    <el-alert
      v-if="showingSameContent"
      class="same-content-list-alert"
      title="同内容异常排查：当前列表仅显示名称、大小相同但 InfoHash 不同的种子"
      type="warning"
      :closable="false"
      show-icon
    >
      <el-button type="text" @click="exitSameContentInspection">
        退出排查并返回普通列表
      </el-button>
    </el-alert>
    <el-alert
      v-if="showingSingleErrors"
      class="single-error-list-alert"
      title="错误单种排查：当前列表仅显示错误且全局同内容唯一的种子"
      type="error"
      :closable="false"
      show-icon
    >
      <el-button type="text" @click="exitSingleErrorInspection">
        退出排查并返回普通列表
      </el-button>
    </el-alert>

    <!-- 批量操作工具栏 -->
    <section class="batch-operations">
      <!-- 批量开始 -->
      <batch-button
        type="success"
        lucide-icon="play"
        tooltip="开始"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchStart"
      />

      <!-- 批量暂停 -->
      <batch-button
        type="warning"
        lucide-icon="pause"
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
          lucide-icon="trash"
          tooltip="删除"
          :disabled="multipleSelection.length === 0"
        />
        <el-dropdown-menu slot="dropdown" class="delete-level-menu">
          <el-dropdown-item command="4">
            <LucideIcon class="menu-icon" name="tag" :size="14" />等级4: 标记为待删除(推荐)
          </el-dropdown-item>
          <el-dropdown-item command="3">
            <LucideIcon class="menu-icon" name="trash-2" :size="14" />等级3: 移至回收站
          </el-dropdown-item>
          <el-dropdown-item command="2">
            <LucideIcon class="menu-icon" name="trash" :size="14" />等级2: 删除任务(保留数据)
          </el-dropdown-item>
          <el-dropdown-item command="1" divided>
            <LucideIcon class="menu-icon danger" name="alert-triangle" :size="14" />等级1: 完全删除
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>

      <!-- 批量重检 -->
      <batch-button
        type="info"
        lucide-icon="refresh-cw"
        tooltip="重检"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchRecheck"
      />

      <!-- Tracker操作 -->
      <batch-button
        type="default"
        lucide-icon="link"
        tooltip="Tracker操作"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchTracker"
      />

      <!-- Tracker汇报 -->
      <batch-button
        type="info"
        lucide-icon="forward"
        tooltip="Tracker汇报"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchReannounce"
      />

      <!-- 全局替换 -->
      <batch-button
        type="default"
        lucide-icon="settings"
        tooltip="全局替换"
        @click="showGlobalReplaceDialog = true"
      />

      <!-- 批量转移 -->
      <batch-button
        type="info"
        lucide-icon="route"
        tooltip="转移"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchTransfer"
      />

      <!-- 批量修改路径 -->
      <batch-button
        type="primary"
        lucide-icon="folder-open"
        tooltip="修改路径"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchSetLocation"
      />

      <!-- 快捷操作（下拉） -->
      <el-dropdown trigger="click" @command="handleQuickActionCommand">
        <batch-button
          type="default"
          lucide-icon="zap"
          tooltip="快捷操作"
        />
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="inspect-same-content">
            <i class="el-icon-search"></i> 同内容异常排查
          </el-dropdown-item>
          <el-dropdown-item command="inspect-single-errors">
            <i class="el-icon-warning-outline"></i> 错误单种排查
          </el-dropdown-item>
          <el-dropdown-item command="delete-duplicates" divided>
            <i class="el-icon-delete"></i> 快捷删除重复种子
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>

      <div style="flex: 1;"></div>

      <!-- 添加种子 -->
      <batch-button
        type="primary"
        lucide-icon="plus"
        tooltip="添加种子"
        @click="showAddDialog = true"
      />

      <!-- 列设置 -->
      <batch-button
        type="default"
        lucide-icon="settings"
        tooltip="列设置"
        @click="showColumnSettings = true"
      />

      <!-- 视图切换 -->
      <div class="view-switcher">
        <el-button
          type="text"
          size="small"
          :class="{active: viewModeModule.currentMode === 'list'}"
          @click="switchViewMode('list')"
          title="列表模式"
        >
          <i class="el-icon-s-grid"></i>
        </el-button>
        <el-button
          type="text"
          size="small"
          :class="{active: viewModeModule.currentMode === 'traditional'}"
          @click="switchViewMode('traditional')"
          title="传统模式"
        >
          <i class="el-icon-menu"></i>
        </el-button>
      </div>
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
            <th
              v-if="getColumnSetting('name').visible"
              class="sortable-column"
              :class="{sorted: listQuery.sort_by === 'name'}"
              data-sort-field="name"
              tabindex="0"
              :aria-sort="getSortAriaValue('name')"
              title="按种子名称排序"
              @click="handleSort('name')"
              @keydown.enter.prevent="handleSort('name')"
              @keydown.space.prevent="handleSort('name')"
            >
              种子名称
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('name')"
                :size="13"
                :stroke-width="2"
              />
            </th>
            <th v-if="getColumnSetting('downloadSpeed').visible" style="width: 100px;">下载速度</th>
            <th v-if="getColumnSetting('uploadSpeed').visible" style="width: 100px;">上传速度</th>
            <th
              v-if="getColumnSetting('size').visible"
              class="sortable-column"
              :class="{sorted: listQuery.sort_by === 'size'}"
              data-sort-field="size"
              style="width: 100px;"
              tabindex="0"
              :aria-sort="getSortAriaValue('size')"
              title="按大小排序"
              @click="handleSort('size')"
              @keydown.enter.prevent="handleSort('size')"
              @keydown.space.prevent="handleSort('size')"
            >
              大小
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('size')"
                :size="13"
                :stroke-width="2"
              />
            </th>
            <th v-if="getColumnSetting('auxiliarySeedCount').visible" style="width: 90px;">辅种数量</th>
            <th v-if="getColumnSetting('progress').visible" style="width: 140px;">进度</th>
            <th
              v-if="getColumnSetting('status').visible"
              class="sortable-column"
              :class="{sorted: listQuery.sort_by === 'status'}"
              data-sort-field="status"
              style="width: 90px;"
              tabindex="0"
              :aria-sort="getSortAriaValue('status')"
              title="按状态排序"
              @click="handleSort('status')"
              @keydown.enter.prevent="handleSort('status')"
              @keydown.space.prevent="handleSort('status')"
            >
              状态
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('status')"
                :size="13"
                :stroke-width="2"
              />
            </th>
            <th v-if="getColumnSetting('downloader').visible" style="width: 110px;">所属下载器</th>
            <th
              v-if="getColumnSetting('ratio').visible"
              class="sortable-column"
              :class="{sorted: listQuery.sort_by === 'ratio'}"
              data-sort-field="ratio"
              style="width: 70px;"
              tabindex="0"
              :aria-sort="getSortAriaValue('ratio')"
              title="按比率排序"
              @click="handleSort('ratio')"
              @keydown.enter.prevent="handleSort('ratio')"
              @keydown.space.prevent="handleSort('ratio')"
            >
              比率
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('ratio')"
                :size="13"
                :stroke-width="2"
              />
            </th>
            <th v-if="getColumnSetting('category').visible" style="width: 180px;">分类/标签</th>
            <th v-if="getColumnSetting('savePath').visible" style="width: 200px;">保存路径</th>
            <th
              v-if="getColumnSetting('addedDate').visible"
              class="sortable-column"
              :class="{sorted: listQuery.sort_by === 'added_date'}"
              data-sort-field="added_date"
              style="width: 130px;"
              tabindex="0"
              :aria-sort="getSortAriaValue('added_date')"
              title="按添加时间排序"
              @click="handleSort('added_date')"
              @keydown.enter.prevent="handleSort('added_date')"
              @keydown.space.prevent="handleSort('added_date')"
            >
              添加时间
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('added_date')"
                :size="13"
                :stroke-width="2"
              />
            </th>
            <th v-if="getColumnSetting('actions').visible" class="action-column" style="width: 140px;">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(torrent, index) in sortedList"
            :key="`${torrent.hash}-${torrent.downloaderId || torrent.downloader_id}-${index}`"
            :class="{selected: currentRow && currentRow.hash === torrent.hash}"
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
                  <LucideIcon
                    :name="getStatusIcon(torrent.status)"
                    :size="10"
                    :stroke-width="2.5"
                  />
                </div>
                <el-tooltip
                  :disabled="!getTorrentErrorReason(torrent)"
                  :content="getTorrentErrorReason(torrent)"
                  placement="top"
                >
                  <div
                    class="torrent-name-text"
                    :title="getTorrentErrorReason(torrent) ? '' : torrent.name"
                  >
                    {{ torrent.name }}
                  </div>
                </el-tooltip>
              </div>
            </td>
            <td v-if="getColumnSetting('downloadSpeed').visible">
              <span class="speed-value download">{{ formatSpeed(getTorrentSpeed(torrent, 'download')) }}</span>
            </td>
            <td v-if="getColumnSetting('uploadSpeed').visible">
              <span class="speed-value upload">{{ formatSpeed(getTorrentSpeed(torrent, 'upload')) }}</span>
            </td>
            <td v-if="getColumnSetting('size').visible">{{ formatFileSize(torrent.size) }}</td>
            <td v-if="getColumnSetting('auxiliarySeedCount').visible">{{ torrent.auxiliarySeedCount || 1 }}</td>
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
                  <LucideIcon
                    :name="torrent.status === 'paused' ? 'play' : 'pause'"
                    :size="14"
                  />
                </button>
                <button
                  class="action-btn refresh"
                  @click.stop="handleRecheck(torrent)"
                  title="重新检查"
                >
                  <LucideIcon name="refresh-cw" :size="14" />
                </button>
                <button
                  class="action-btn location"
                  @click.stop="handleSetLocation(torrent)"
                  title="修改保存路径"
                >
                  <LucideIcon name="folder-open" :size="14" />
                </button>
                <el-dropdown
                  @command="(cmd) => handleDeleteCommand(cmd, torrent)"
                  trigger="click"
                  :hide-on-click="true"
                  :append-to-body="true"
                  @click.native.stop
                >
                  <button class="action-btn delete">
                    <LucideIcon name="trash" :size="14" />
                  </button>
                  <el-dropdown-menu slot="dropdown" class="delete-level-menu">
                    <el-dropdown-item command="4">
                      <LucideIcon class="menu-icon" name="tag" :size="14" />等级4: 标记为待删除(推荐)
                    </el-dropdown-item>
                    <el-dropdown-item command="3">
                      <LucideIcon class="menu-icon" name="trash-2" :size="14" />等级3: 移至回收站
                    </el-dropdown-item>
                    <el-dropdown-item command="2">
                      <LucideIcon class="menu-icon" name="trash" :size="14" />等级2: 删除任务(保留数据)
                    </el-dropdown-item>
                    <el-dropdown-item command="1" divided>
                      <LucideIcon class="menu-icon danger" name="alert-triangle" :size="14" />等级1: 完全删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </el-dropdown>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Tracker详情卡片；弹框骨架与传统模式共用 TrackerDetailCard -->
    <TrackerDetailCard
      :visible="showTrackerDetail && !!currentRow"
      layout="list"
      :torrent-name="(currentRow && currentRow.name) || ''"
      :active-tab.sync="activeDetailTab"
      :tabs="detailTabs"
      :tracker-info="(currentRow && (currentRow.tracker_info || currentRow.trackerInfo)) || []"
      :error-reason="getTorrentErrorReason(currentRow)"
      @close="handleCloseTrackerDetail"
      @reannounce="handleTrackerReannounce"
    />

    <!-- 分页 -->
    <nav class="torrent-pagination">
      <div class="pagination-info">
        <PageSizeCombobox
          ref="pageSizeCombobox"
          :append-to-body="true"
          v-model="pageSizeInput"
          :page-size="pageSize"
          :options="pageSizeOptions"
          :expanded="pageSizeDropdownExpanded"
          controls-id="list-page-size-options"
          @focus="handlePageSizeFocus"
          @blur="handlePageSizeBlur"
          @toggle="togglePageSizeDropdown"
          @apply="applyPageSizeSelection"
          @select="handlePageSizeSelect"
        />
        <span class="pagination-summary">共 <strong>{{ total }}</strong> 条，第 <strong>{{ currentPage }}</strong>/<strong>{{ totalPages }}</strong> 页</span>
      </div>
      <div class="pagination-controls">
        <button
          class="pagination-btn"
          :disabled="currentPage <= 1"
          @click="handlePageChange(currentPage - 1)"
        >
          <LucideIcon name="chevron-left" :size="14" />
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
          <LucideIcon name="chevron-right" :size="14" />
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
          <h3 class="modal-title">
            <LucideIcon name="settings" :size="18" style="margin-right: 6px; vertical-align: middle;" />
            列设置
          </h3>
          <button class="modal-close" @click="showColumnSettings = false">
            <LucideIcon name="x" :size="16" />
          </button>
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
      :visible.sync="showAdvancedSearchDialog"
      width="80%"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      class="advanced-search-dialog"
    >
      <template slot="title">
        <span class="advanced-search-dialog__title">
          <LucideIcon name="sliders-horizontal" :size="16" />
          <span>高级搜索</span>
        </span>
      </template>
      <AdvancedSearchWorkspace
        ref="advancedSearchBuilder"
        :searching="advancedSearchSearching"
        :sort-by="listQuery.sort_by"
        :sort-order="listQuery.sort_order"
        @search="handleAdvancedSearchFromBuilder"
        @reset="handleResetAdvancedSearch"
        @template-loaded="handleAdvancedTemplateLoaded"
      />
    </el-dialog>

    <!-- 快捷删除重复种子对话框 -->
    <QuickDeleteDuplicatesDialog
      :visible.sync="showQuickDeleteDuplicatesDialog"
      @close="showQuickDeleteDuplicatesDialog = false"
      @deleted="handleQuickDeleteDeleted"
    />

  </div>
</template>
<script lang="ts">
import { Component } from 'vue-property-decorator'
import { mixins } from 'vue-class-component'
import BatchButton from '@/components/BatchButton/index.vue'
import PageSizeCombobox from '@/components/torrents/PageSizeCombobox.vue'
import AdvancedMultiSelect from '@/components/torrents/AdvancedMultiSelect.vue'
import type { SelectOption } from '@/components/torrents/AdvancedMultiSelect.vue'
import AdvancedSearchWorkspace from '@/components/torrents/AdvancedSearchWorkspace.vue'
import QuickDeleteDuplicatesDialog from '@/components/torrents/QuickDeleteDuplicatesDialog.vue'
import TrackerDetailCard from './components/TrackerDetailCard.vue'
import { ViewModeModule, ViewModeType } from '@/store/modules/viewMode'
import TorrentBatchMixin from './mixins/torrentBatch'
import SpeedPollingMixin from './mixins/speedPolling'
import {
  getTorrentList,
  deleteTorrentsWithLevel,
  deleteBatchAsync,
  getBatchDeleteStatus,
  pauseTorrents,
  resumeTorrents,
  recheckTorrents,
  advancedSearch,
  getDuplicateTorrents,
  getDownloaderList,
  getTrackerDomains,
  DownloaderSimple,
  reannounceTorrents,
  getActiveTorrents,
  applySearchTemplate,
  type Torrent,
  type QueryTemplateConditions
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
  extractErrorMessage,
  normalizePaginatedResponse,
  debounce
} from '@/utils/formatters'
import {
  getTorrentSpeed as getTorrentSpeedFromSnapshot,
  deriveVisibleTorrentList,
  buildSpeedSnapshot,
  needsActiveSnapshotRefresh,
  buildAdvancedSearchRequest,
  buildAdvancedSearchRequestFromTemplateGroups
} from './utils/torrentBatch'
import type { AdvancedSearchBuilderParams } from '@/components/torrents/advancedSearchState'
import { normalizeTraditionalPageSize } from './utils/traditionalPagination'

interface PageSizeSuggestion {
  value: string
}

type TorrentSortField = 'name' | 'size' | 'status' | 'ratio' | 'added_date'
type TorrentSortIconName = 'arrow-up-down' | 'arrow-up' | 'arrow-down'

@Component({
  name: 'TorrentsManagement',
  components: {
    BatchButton,
    PageSizeCombobox,
    AdvancedMultiSelect,
    AdvancedSearchWorkspace,
    TrackerDetailCard,
    BatchOperationDialog: () => import('./components/BatchOperationDialog.vue'),
    TorrentAddDialog: () => import('./components/TorrentAddDialog.vue'),
    TrackerOperationDialog: () => import('./components/TrackerOperationDialog.vue'),
    GlobalReplaceTrackerDialog: () => import('./components/GlobalReplaceTrackerDialog.vue'),
    BatchTransferDialog: () => import('./components/BatchTransferDialog.vue'),
    SetLocationDialog: () => import('./components/SetLocationDialog.vue'),
    QuickDeleteDuplicatesDialog
    // DuplicateTorrentsDialog: () => import('@/components/torrents/DuplicateTorrentsDialog.vue') // 不再需要弹窗
  }
})
export default class extends mixins(TorrentBatchMixin, SpeedPollingMixin) {
  // 视图模式管理
  private viewModeModule = ViewModeModule

  // 主题相关
  private currentTheme: ThemeType = 'emerald'
  private allThemes = ThemeManager.getAllThemes()

  // 数据状态
  private list: any[] = []
  private total = 0
  private listLoading = true
  private multipleSelection: any[] = []

  // 实时速度轮询（speedTimer/speedPollingActive 由 SpeedPollingMixin 提供）
  private speedSnapshotReady = false
  private activeSpeedMap: Record<string, { downloadSpeed: number, uploadSpeed: number, progress: number }> = {}
  private activeListRetryPending = false
  private activeListRetryInFlight = false

  // 分页相关
  private currentPage = 1
  private pageSize = 20
  private pageSizeInput = '20'
  private pageSizeOptions = [20, 50, 100, 500, 1000]
  private pageSizeDropdownExpanded = false

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
  private showQuickDeleteDuplicatesDialog = false
  private advancedSearchSearching = false
  private showingDuplicates = false
  private showingSameContent = false
  private showingSingleErrors = false

  // Tracker 主域名筛选选项（由定时 Tracker 同步结果生成）
  private trackerDomainList: string[] = []

  // 修改路径相关
  private selectedTorrentsForLocation: any[] = []

  // 重复检测相关（不再需要弹窗）
  // private showDuplicateTorrentsDialog = false

  // 辅助方法 groupTorrentsByDownloader 已由 TorrentBatchMixin 提供，
  // 此处删除视图内的重复实现，消除回归风险（防 Bug#1/#4）。

  private batchOperation = ''
  private selectedTorrentsForTracker: any[] = []
  private trackerOperationType: 'add' | 'replace' | 'modify' | '' = ''

  // Tracker详情
  private showTrackerDetail = false
  private currentRow: any = null
  private activeDetailTab = 'tracker'
  private detailTabs = [
    { label: 'Tracker', value: 'tracker' },
    { label: '文件', value: 'files' },
    { label: 'Peers', value: 'peers' }
  ]

  // 搜索相关
  private listQuery = {
    skip: 0,
    limit: 20,  // 初始默认值，会在 handlePageSizeChange 中动态更新
    name_like: '',
    downloader_id: [] as string[],  // 支持多选
    status: [] as string[],         // 支持多选
    tracker_domain: [] as string[], // Tracker主域名多选
    showActiveOnly: false,          // 仅显示活动种子（UI 开关，映射为后端 active_only 过滤）
    sort_by: 'added_date',
    sort_order: 'desc'
  }

  // 列设置
  private columnSettings = [
    { key: 'name', label: '种子名称', visible: true },
    { key: 'downloadSpeed', label: '下载速度', visible: true },
    { key: 'uploadSpeed', label: '上传速度', visible: true },
    { key: 'size', label: '大小', visible: true },
    { key: 'auxiliarySeedCount', label: '辅种数量', visible: true },
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
   * 下载器选项列表（映射为 AdvancedMultiSelect 所需的 {value,label} 结构）
   */
  get downloaderOptions() {
    return this.downloaderList.map(downloader => ({
      value: downloader.downloader_id,
      label: downloader.nickname
    }))
  }
  get trackerDomainOptions(): SelectOption[] {
    return this.trackerDomainList.map(domain => ({
      value: domain,
      label: domain
    }))
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
    await this.getTrackerDomainList()
    await this.getList()
    this.loadUserPreferences()
    // 详情死路由（/torrents/detail/:hash）直接挂载本组件：不启动轮询，只展示列表数据
    const routePath = this.$route && this.$route.path ? this.$route.path : ''
    if (!routePath.startsWith('/torrents/detail')) {
      this.startSpeedPolling()
    }

    // v1.0.5：处理从查询模板管理页跳转来的应用请求
    await this.handleApplyTemplateFromRoute()
  }

  /**
   * v1.0.5 处理路由 query 中的 apply_template_id，应用对应查询模板
   */
  private async handleApplyTemplateFromRoute() {
    const templateId = this.$route.query.apply_template_id as string | undefined
    if (!templateId) return

    let applied = false
    try {
      const response = await applySearchTemplate(templateId)
      if (response.code === '200' && response.data) {
        // apply 端点返回 {id, name, description, conditions}
        const conditions = response.data.conditions
        if (conditions) {
          applied = await this.applyQueryTemplate(conditions)
        }
      } else {
        this.$message.error(response.msg || '应用模板失败')
      }
    } catch (error) {
      this.$message.error('应用模板失败：' + (error as Error).message)
    }

    // 清除 query 参数，避免刷新重复应用
    if (applied) {
      this.$router.replace({ query: {} })
    }
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
  private async getList(activeSnapshotRetry = false) {
    if (this.showingDuplicates) {
      await this.fetchDuplicateTorrents(false, activeSnapshotRetry)
      return
    }

    this.listLoading = true
    try {
      const params = { ...this.listQuery }

      // "仅显示活动种子"下沉为后端 active_only 过滤（解决前端过滤导致 total 失真）。
      // showActiveOnly 仅作 UI 开关状态，映射成 active_only 传给后端。
      const showActive = params.showActiveOnly === true
      delete params.showActiveOnly
      if (showActive) {
        params.active_only = true
      }
      if (this.showingSameContent) {
        params.same_content_only = true
      }
      if (this.showingSingleErrors) {
        params.single_error_only = true
      }

      // 处理数组参数：转换为逗号分隔的字符串
      if (params.downloader_id && Array.isArray(params.downloader_id)) {
        params.downloader_id = params.downloader_id.join(',')
      }
      if (params.status && Array.isArray(params.status)) {
        params.status = params.status.join(',')
      }
      if (Array.isArray(params.tracker_domain)) {
        if (params.tracker_domain.length > 0) {
          params.tracker_domain = params.tracker_domain.join(',')
        } else {
          delete params.tracker_domain
        }
      }

      // 移除空值
      Object.keys(params).forEach(key => {
        const value = params[key as keyof typeof params]
        if (value === '' || value === null || value === undefined) {
          delete params[key as keyof typeof params]
        }
      })

      const response = await getTorrentList(params)

      if (needsActiveSnapshotRefresh(response, showActive)) {
        // 206 表示后端尚无权威活动快照。保留现有 list/total，先刷新速度；完整快照
        // 到达后由 loadActiveSpeed 触发一次受控重试，避免冷启动瞬间把列表清空。
        this.activeListRetryPending = true
        if (!activeSnapshotRetry) {
          await this.loadActiveSpeed()
        }
        return
      }
      this.activeListRetryPending = false

      // 使用统一的响应处理工具
      const { list, total } = normalizePaginatedResponse<any>(response)

      // 规范化种子数据并提供默认值
      const normalizedList = list.map(normalizeTorrent).map(item => ({
        ...item,
        checked: false
      }))

      // "仅显示活动种子"过滤已下沉到后端（active_only），此处直接使用后端返回的 list 与 total，
      // 二者口径天然一致。sortedList 仅做"活动优先"排序，不再做客户端过滤。
      this.list = normalizedList
      this.total = total
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

  private async getTrackerDomainList() {
    try {
      const response = await getTrackerDomains()
      if (response.code === '200' && Array.isArray(response.data)) {
        this.trackerDomainList = response.data
      }
    } catch (error) {
      console.error('获取 Tracker 主域名失败:', error)
    }
  }

  // 搜索
  private handleFilter() {
    this.listQuery.skip = 0
    this.currentPage = 1
    this.getList()
  }

  // 列头排序与传统模式保持一致：首次选择字段默认降序，再次点击切换升/降序。
  private handleSort(field: TorrentSortField) {
    if (this.listQuery.sort_by === field) {
      this.listQuery.sort_order = this.listQuery.sort_order === 'asc' ? 'desc' : 'asc'
    } else {
      this.listQuery.sort_by = field
      this.listQuery.sort_order = 'desc'
    }
    this.getList()
  }

  private getSortAriaValue(field: TorrentSortField): 'ascending' | 'descending' | 'none' {
    if (this.listQuery.sort_by !== field) return 'none'
    return this.listQuery.sort_order === 'asc' ? 'ascending' : 'descending'
  }

  private getSortIconName(field: TorrentSortField): TorrentSortIconName {
    if (this.listQuery.sort_by !== field) return 'arrow-up-down'
    return this.listQuery.sort_order === 'asc' ? 'arrow-up' : 'arrow-down'
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
      tracker_domain: [], // Tracker主域名一并重置
      showActiveOnly: false,  // 活动种子开关一并重置（原重建 listQuery 漏掉此字段）
      sort_by: 'added_date',
      sort_order: 'desc'
    }
    this.getList()
  }

  // 切换视图模式
  private switchViewMode(mode: ViewModeType) {
    this.viewModeModule.setViewMode(mode)
  }

  // 手动刷新（静态数据 + 速度数据同时刷新）
  private handleManualRefresh() {
    this.getList()
    this.loadActiveSpeed()
  }

  // ==================== 快捷操作 ====================

  /**
   * 快捷操作下拉菜单命令分发
   */
  private async handleQuickActionCommand(command: string) {
    if (command === 'inspect-same-content') {
      this.showingDuplicates = false
      this.showingSingleErrors = false
      this.showingSameContent = true
      this.currentPage = 1
      this.listQuery.skip = 0
      await this.getList()
      this.$message.success(`排查完成，共找到 ${this.total} 条同内容种子`)
    } else if (command === 'inspect-single-errors') {
      this.showingDuplicates = false
      this.showingSameContent = false
      this.showingSingleErrors = true
      this.currentPage = 1
      this.listQuery.skip = 0
      await this.getList()
      this.$message.success(`排查完成，共找到 ${this.total} 条错误单种`)
    } else if (command === 'delete-duplicates') {
      this.showQuickDeleteDuplicatesDialog = true
    }
  }

  private async exitSameContentInspection() {
    this.showingSameContent = false
    this.currentPage = 1
    this.listQuery.skip = 0
    await this.getList()
  }

  private async exitSingleErrorInspection() {
    this.showingSingleErrors = false
    this.currentPage = 1
    this.listQuery.skip = 0
    await this.getList()
  }

  /**
   * 快捷删除重复种子完成后刷新列表
   */
  private handleQuickDeleteDeleted() {
    this.handleManualRefresh()
  }

  // 分页切换
  private handlePageChange(page: number) {
    this.currentPage = page
    this.listQuery.skip = (page - 1) * this.pageSize
    this.getList()
  }

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
    const normalizedPageSize = normalizeTraditionalPageSize(value, this.pageSize)
    this.pageSizeInput = String(normalizedPageSize)
    this.pageSizeDropdownExpanded = false
    if (normalizedPageSize === this.pageSize) return

    this.pageSize = normalizedPageSize
    this.handlePageSizeChange()
  }

  // 每页条数变更：与传统模式一致，应用后回到第一页。
  private handlePageSizeChange() {
    this.currentPage = 1
    this.listQuery.limit = this.pageSize
    this.listQuery.skip = 0
    this.getList()
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
      this.activeDetailTab = 'tracker'
      this.showTrackerDetail = true
    }
  }

  private handleCloseTrackerDetail() {
    this.showTrackerDetail = false
    this.currentRow = null
  }

  private getTorrentErrorReason(torrent: Torrent | null | undefined): string {
    return torrent?.errorReason || torrent?.error_reason || ''
  }

  /**
   * 处理单个Tracker的汇报操作
   */
  private async handleTrackerReannounce(tracker: any, _index: number) {
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

  // 批量操作：handleBatchStart / handleBatchPause / handleBatchRecheck
  // 已由 TorrentBatchMixin 提供（统一文案，防回归 Bug#2）。
  // 模板 @click 直接绑定 mixin 方法。


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
        this.$message.info(response.msg || '所选种子均已在删除任务中处理')
        await this.getList()
        return
      }
      const skippedCount = response.data?.skipped_count || 0
      if (skippedCount > 0) {
        this.$message.warning(`已跳过 ${skippedCount} 个正在处理的种子`)
      }

      // 提交成功即刷新；后端列表会排除 pending/running 任务里的种子。
      await this.getList()
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
  private handleDeleteTaskResult(taskData: any, _level: number) {
    const { status, success_count, failed_count, failed_items } = taskData

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

  // deleteTorrentsInternal 已由 TorrentBatchMixin 提供（防回归 Bug#1/#4）。
  // performBatchDelete / performDelete / callDeleteLegacyAPI 仍调用 this.deleteTorrentsInternal，
  // 由 mixin 注入真实 deleteTorrents，行为不变。

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
  private openAdvancedSearch() {
    this.showAdvancedSearchDialog = true
    // 对话框首次打开时组件才挂载；nextTick 后再调用，确保 $refs 就绪。
    // 每次打开都刷新分类/标签/下载器选项，保证下拉反映最新数据。
    this.$nextTick(() => {
      const builder = this.$refs.advancedSearchBuilder as { refreshFieldOptions?: () => void } | undefined
      builder?.refreshFieldOptions?.()
    })
  }

  private handleAdvancedSearchFromBuilder(searchParams: AdvancedSearchBuilderParams) {
    this.performAdvancedSearch(searchParams)
    this.showAdvancedSearchDialog = false
  }

  private handleResetAdvancedSearch() {
    // AdvancedSearchBuilder 在发出 reset 前已经完成内部重置；这里只处理反馈，
    // 避免再次调用 resetConditions 形成 reset 事件递归。
    this.$message.success('搜索条件已重置')
  }

  private handleAdvancedTemplateLoaded(conditions: QueryTemplateConditions) {
    if (conditions.sort_by) {
      this.listQuery.sort_by = conditions.sort_by
    }
    if (conditions.sort_order) {
      this.listQuery.sort_order = conditions.sort_order
    }
  }

  private confirmAdvancedSearch() {
    const builder = this.$refs.advancedSearchBuilder as any
    if (builder && builder.onSearch) {
      builder.onSearch()
    }
  }

  private async performAdvancedSearch(searchParams: AdvancedSearchBuilderParams) {
    const { request, error } = buildAdvancedSearchRequest(
      searchParams,
      this.listQuery.sort_by || 'added_date',
      this.listQuery.limit || this.pageSize
    )
    if (!request || error) {
      this.$message.error(error || '搜索条件格式错误')
      return
    }

    this.showingDuplicates = false
    this.showingSameContent = false
    this.showingSingleErrors = false
    this.advancedSearchSearching = true
    try {
      const response = await advancedSearch(request)

      if (response.code === '200' && response.data) {
        this.list = response.data.list || []
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

  /**
   * v1.0.5 应用查询模板（按 conditions.source 分支）
   * - source=simple：回填 listQuery 并 getList()
   * - source=advanced：回填 AdvancedSearchBuilder 的 conditionGroups 并执行高级搜索
   */
  private async applyQueryTemplate(conditions: QueryTemplateConditions): Promise<boolean> {
    if (!conditions || !conditions.source) {
      this.$message.error('模板条件格式无效')
      return false
    }

    try {
      if (conditions.source === 'simple' && conditions.listQuery) {
        this.showingDuplicates = false
        this.showingSameContent = false
        this.showingSingleErrors = false
        // 简单查询：回填 listQuery（保留 skip/limit），回到第 1 页
        const saved = conditions.listQuery
        this.listQuery = {
          skip: 0,
          limit: this.listQuery.limit,
          name_like: saved.name_like ?? '',
          downloader_id: saved.downloader_id ? [...saved.downloader_id] : [],
          status: saved.status ? [...saved.status] : [],
          tracker_domain: saved.tracker_domain ? [...saved.tracker_domain] : [],
          showActiveOnly: saved.showActiveOnly ?? false,
          sort_by: saved.sort_by ?? 'added_date',
          sort_order: saved.sort_order ?? 'desc'
        }
        // 重置分页到第 1 页
        this.currentPage = 1
        await this.getList()
        this.$message.success('已应用查询模板')
        return true
      } else if (conditions.source === 'advanced' && conditions.condition_groups) {
        this.showingDuplicates = false
        this.showingSameContent = false
        this.showingSingleErrors = false
        const sortBy = conditions.sort_by || this.listQuery.sort_by || 'added_date'
        const sortOrder = conditions.sort_order || this.listQuery.sort_order || 'desc'
        this.listQuery.sort_by = sortBy
        this.listQuery.sort_order = sortOrder
        // 高级搜索：回填 AdvancedSearchBuilder 的 conditionGroups
        const builderRef = this.$refs.advancedSearchBuilder as any
        if (builderRef && typeof builderRef.applyTemplateGroups === 'function') {
          builderRef.applyTemplateGroups(conditions.condition_groups, {
            sort_by: sortBy,
            sort_order: sortOrder
          })
        }
        const { request, error } = buildAdvancedSearchRequestFromTemplateGroups(
          conditions.condition_groups,
          sortBy,
          sortOrder,
          this.listQuery.limit || this.pageSize
        )
        if (error || !request) {
          this.$message.error(error || '搜索条件格式错误')
          return false
        }
        const response = await advancedSearch(request)
        if (response.code === '200' && response.data) {
          this.list = (response.data.list || []).map(normalizeTorrent).map(item => ({ ...item, checked: false }))
          this.total = response.data.total || 0
          this.listQuery.skip = 0
          this.currentPage = 1
          this.resetBatchSelection()
          this.$message.success('已应用高级搜索模板')
          return true
        }
        this.$message.error(response.msg || '搜索失败')
        return false
      } else {
        this.$message.warning('不支持的模板类型')
      }
    } catch (error) {
      this.$message.error('应用模板失败：' + (error as Error).message)
    }
    return false
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
    // 第4参数固定 false：活动种子过滤已下沉到后端 active_only，此处仅保留"活跃优先排序"，
    // 关闭客户端二次过滤，避免与后端过滤叠加。
    return deriveVisibleTorrentList(
      this.list,
      this.activeSpeedMap,
      this.speedSnapshotReady,
      false
    )
  }

  /** 获取种子的实时显示速度（优先使用轮询数据，降级使用静态数据） */
  private getTorrentSpeed(torrent: any, type: 'download' | 'upload'): number | null {
    return getTorrentSpeedFromSnapshot(torrent, type, this.activeSpeedMap, this.speedSnapshotReady)
  }

  /** 加载活跃种子实时速度和进度 */
  protected async loadActiveSpeed(): Promise<boolean> {
    const requestId = Date.now()

    try {
      const res = await getActiveTorrents()
      const snapshot = buildSpeedSnapshot(res)
      if (snapshot.ready && snapshot.activeSpeedMap) {
        // 直接更新列表中命中种子的实时数据（副作用，留在视图层）
        snapshot.updates.forEach(u => {
          const torrentInList = this.list.find(item => item.hash === u.hash)
          if (torrentInList) {
            torrentInList.downloadSpeed = u.downloadSpeed
            torrentInList.uploadSpeed = u.uploadSpeed
            torrentInList.progress = u.progress
          }
        })
        this.activeSpeedMap = snapshot.activeSpeedMap
        this.speedSnapshotReady = true
        console.debug(`[速度轮询] 请求 ${requestId} 完成，更新 ${snapshot.count} 个活跃种子`)

        if (
          this.activeListRetryPending &&
          this.listQuery.showActiveOnly &&
          !this.activeListRetryInFlight
        ) {
          this.activeListRetryInFlight = true
          try {
            await this.getList(true)
          } finally {
            this.activeListRetryInFlight = false
          }
        }
        return true
      }
      return false
    } catch (e) {
      // 静默失败，不影响主流程
      console.debug(`[速度轮询] 请求 ${requestId} 失败:`, e)
      return false
    }
  }

  // ====== 实时速度轮询 ======
  // startSpeedPolling / stopSpeedPolling 由 SpeedPollingMixin 提供（含后台标签页暂停/恢复）

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

  private handleBatchConfirm(_operation: string, _selectedItems: any[]) {
    this.showBatchDialog = false
    // 批量操作确认处理
  }

  // ==================== 重复种子相关方法 ====================

  /** 切换重复任务数据源；开启后所有筛选、排序、分页和刷新都继续走重复查询。 */
  private async handleDuplicateSearchToggle(enabled: boolean) {
    this.showingDuplicates = enabled
    if (enabled) {
      this.showingSameContent = false
      this.showingSingleErrors = false
    }
    this.currentPage = 1
    this.listQuery.skip = 0
    if (!enabled) {
      await this.getList()
      return
    }

    await this.fetchDuplicateTorrents(true)
  }

  private async fetchDuplicateTorrents(showResultMessage = false, activeSnapshotRetry = false) {
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
        pageSize: this.pageSize,
        sort_by: this.listQuery.sort_by as TorrentSortField,
        sort_order: this.listQuery.sort_order as 'asc' | 'desc',
        active_only: this.listQuery.showActiveOnly || undefined
      }

      const response = await getDuplicateTorrents(params)

      if (needsActiveSnapshotRefresh(response, this.listQuery.showActiveOnly)) {
        this.activeListRetryPending = true
        if (!activeSnapshotRetry) {
          await this.loadActiveSpeed()
        }
        return
      }
      this.activeListRetryPending = false

      const { list, total } = normalizePaginatedResponse<any>(response)

      this.list = list.map(normalizeTorrent).map(item => ({
        ...item,
        checked: false
      }))

      this.total = total

      if (showResultMessage) {
        this.$message.success(`查找完成，共找到 ${total} 条重复种子`)
      }
    } catch (error) {
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

.torrent-error-alert {
  width: auto;
  margin: 12px 16px 0;
}

.same-content-list-alert {
  margin: 0 16px 12px;
}

.single-error-list-alert {
  margin: 0 16px 12px;
}

.advanced-search-dialog__title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--color-text-primary);
  font-size: 15px;
  font-weight: 600;
  line-height: 1.2;
}

// ========================================
// 搜索框样式：与相邻 AdvancedMultiSelect 折叠态 trigger 对齐
// （height:32px / padding:0 10px / font-size:12px / token border + radius / primary focus）
// ========================================
.simple-search {
  ::v-deep .search-input {
    .el-input__inner {
      height: 32px;
      line-height: 32px;
      padding: 0 10px;
      font-size: 12px;
      border: 1px solid var(--color-border-primary, #dcdfe6);
      border-radius: var(--radius-sm, 4px);
      background: var(--color-bg-primary, #fff);
      color: var(--color-text-primary, #1f2937);
      transition: border-color var(--transition-fast, 150ms),
                  box-shadow var(--transition-fast, 150ms);

      &:focus {
        border-color: var(--color-primary, #059669);
        box-shadow: 0 0 0 2px var(--color-primary-lightest, #d1fae5);
      }

      &::placeholder {
        color: var(--color-text-tertiary, #9ca3af);
      }
    }
  }
}

// ========================================
// 视图切换器样式
// ========================================
.view-switcher {
  display: flex;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  padding: 2px;
  gap: 1px;
  margin-left: 8px;

  .el-button--text {
    padding: 5px 8px;
    border-radius: var(--radius-xs);
    transition: all var(--transition-fast);

    &.active {
      background: var(--color-primary);
      color: white;
    }

    &:hover {
      background: var(--color-bg-hover);
    }

    &.active:hover {
      background: var(--color-primary-hover);
    }
  }
}

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
  display: inline-flex;
  align-items: center;
  justify-content: center;
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
// 重复任务查询开关：开启态使用全局成功色，和查询数据源状态保持一致。
// ========================================
.duplicate-search-switch {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  min-height: 32px;
  padding: 0 10px;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: var(--font-weight-medium, 500);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm, 4px);
  cursor: pointer;
  transition: all var(--transition-fast, 150ms);

  &:hover {
    border-color: var(--color-success);
  }

  &.is-active {
    color: var(--color-success-dark);
    background: var(--color-success-light);
    border-color: var(--color-success);
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
