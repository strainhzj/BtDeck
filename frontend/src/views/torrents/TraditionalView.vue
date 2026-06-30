<template>
  <div class="traditional-page">
    <!-- 工具栏 -->
    <div class="traditional-toolbar">
      <!-- 左侧操作区 -->
      <div class="toolbar-left">
        <el-button
          class="filter-toggle-btn"
          type="text"
          icon="el-icon-s-fold"
          @click="toggleFilterPanel"
          title="切换过滤面板"
        />
        <div class="tool-divider"></div>
        <el-button
          type="text"
          size="small"
          :disabled="multipleSelection.length === 0"
          @click="handleBatchStart"
        >
          <i class="el-icon-video-play"></i> 开始
        </el-button>
        <el-button
          type="text"
          size="small"
          :disabled="multipleSelection.length === 0"
          @click="handleBatchPause"
        >
          <i class="el-icon-video-pause"></i> 暂停
        </el-button>
        <el-button
          type="text"
          size="small"
          class="danger"
          :disabled="multipleSelection.length === 0"
          @click="handleBatchDelete"
        >
          <i class="el-icon-delete"></i> 删除
        </el-button>
        <el-dropdown
          @command="handleBatchDeleteByLevelCommand"
          trigger="click"
          :hide-on-click="true"
          :append-to-body="true"
        >
          <el-button
            type="text"
            size="small"
            class="danger"
            :disabled="multipleSelection.length === 0"
          >
            <i class="el-icon-delete"></i> 按等级删除<i class="el-icon-arrow-down el-icon--right"></i>
          </el-button>
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
        <div class="tool-divider"></div>
        <el-button
          type="text"
          size="small"
          :disabled="multipleSelection.length === 0"
          @click="handleBatchRecheck"
        >
          <i class="el-icon-refresh"></i> 重检
        </el-button>
        <div class="selection-info" :class="{visible: multipleSelection.length > 0}">
          已选 <span class="count">{{ multipleSelection.length }}</span> 个
        </div>
      </div>

      <!-- 中间搜索区 -->
      <div class="toolbar-center">
        <el-input
          v-model="listQuery.name_like"
          placeholder="搜索种子名称..."
          prefix-icon="el-icon-search"
          size="small"
          clearable
          class="search-input"
          @input="debouncedSearch"
          @keyup.enter.native="handleFilter"
        />
        <el-checkbox
          v-model="listQuery.showActiveOnly"
          class="active-only-checkbox"
          @change="handleFilter"
          title="仅显示有速度的活动种子（前端过滤当前页）"
        >
          活动
        </el-checkbox>
        <el-button
          type="text"
          size="small"
          icon="el-icon-refresh"
          class="manual-refresh-btn"
          :loading="listLoading"
          @click="handleManualRefresh"
          title="刷新"
        >
          刷新
        </el-button>
        <el-button
          type="text"
          size="small"
          icon="el-icon-search"
          @click="showAdvancedSearchDialog = true"
        >
          高级搜索
        </el-button>
        <el-button
          type="text"
          size="small"
          icon="el-icon-copy-document"
          @click="handleShowDuplicateTorrents"
          title="查找重复任务"
        >
          重复
        </el-button>
      </div>

      <!-- 右侧操作区 -->
      <div class="toolbar-right">
        <el-button
          type="primary"
          size="small"
          icon="el-icon-plus"
          @click="showAddDialog = true"
        >
          添加
        </el-button>
        <el-button
          type="text"
          size="small"
          icon="el-icon-setting"
          @click="showColumnSettings = true"
          title="列设置"
        ></el-button>
        <div class="tool-divider"></div>
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
      </div>
    </div>

    <!-- 批量操作行（P0新增，容纳进阶批量操作，避免 toolbar 过挤） -->
    <div class="traditional-batch-ops">
      <el-button
        type="text"
        size="small"
        icon="el-icon-link"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchTracker"
      >Tracker操作</el-button>
      <el-button
        type="text"
        size="small"
        icon="el-icon-share"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchReannounce"
      >Tracker汇报</el-button>
      <el-button
        type="text"
        size="small"
        icon="el-icon-setting"
        @click="showGlobalReplaceDialog = true"
      >全局替换</el-button>
      <div class="tool-divider"></div>
      <el-button
        type="text"
        size="small"
        icon="el-icon-sort"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchTransfer"
      >转移</el-button>
      <el-button
        type="text"
        size="small"
        icon="el-icon-folder-opened"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchSetLocation"
      >修改路径</el-button>
    </div>
    <div class="page-body">
      <!-- 左侧过滤面板 -->
      <aside class="filter-panel" :class="{collapsed: viewModeModule.filterPanelCollapsed}">
        <div class="filter-panel-header">
          <h3>过滤器</h3>
          <el-button
            type="text"
            class="filter-toggle-btn"
            icon="el-icon-d-arrow-left"
            @click="toggleFilterPanel"
            title="收起"
          />
        </div>

        <div class="filter-panel-content">
          <!-- 状态过滤 -->
          <FilterGroup
            title="状态"
            :items="statusFilterItems"
            :active-value="listQuery.status"
            @select="handleStatusFilter"
          />

          <!-- 下载器过滤 -->
          <FilterGroup
            title="下载器"
            :items="downloaderFilterItems"
            :active-value="listQuery.downloader_id"
            @select="handleDownloaderFilter"
          />

          <!-- 分类过滤 -->
          <FilterGroup
            title="分类"
            :items="categoryFilterItems"
            :active-value="listQuery.category_like"
            @select="handleCategoryFilter"
          />

          <!-- 标签过滤 -->
          <FilterGroup
            title="标签"
            :items="tagFilterItems"
            :active-value="listQuery.tags_like"
            @select="handleTagFilter"
          />
        </div>
      </aside>

      <!-- 表格区域 -->
      <div class="table-area">
        <div class="table-container" v-loading="listLoading">
          <table class="torrent-table traditional-table">
            <thead>
              <tr>
                <th class="col-checkbox">
                  <el-checkbox
                    :indeterminate="isIndeterminate"
                    v-model="selectAll"
                    @change="handleSelectAll"
                  />
                </th>
                <th class="col-status-icon"></th>
                <th v-if="getColumnSetting('name').visible" class="col-name" @click="handleSort('name')">
                  名称
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'name'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th v-if="getColumnSetting('size').visible" class="col-size" @click="handleSort('size')">
                  大小
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'size'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th v-if="getColumnSetting('progress').visible" class="col-progress">进度</th>
                <th v-if="getColumnSetting('status').visible" class="col-status" @click="handleSort('status')">
                  状态
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'status'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th v-if="getColumnSetting('download').visible" class="col-downspeed">↓ 下载</th>
                <th v-if="getColumnSetting('upload').visible" class="col-upspeed">↑ 上传</th>
                <th v-if="getColumnSetting('ratio').visible" class="col-ratio" @click="handleSort('ratio')">
                  比率
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'ratio'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th v-if="getColumnSetting('downloader').visible" class="col-downloader">下载器</th>
                <th v-if="getColumnSetting('category').visible" class="col-category">分类/标签</th>
                <th v-if="getColumnSetting('added').visible" class="col-added" @click="handleSort('added_date')">
                  添加时间
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'added_date'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                </th>
                <th class="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(torrent, index) in sortedList"
                :key="`${torrent.hash}-${torrent.downloaderId || torrent.downloader_id}-${index}`"
                :class="{selected: currentRow?.hash === torrent.hash}"
                @click="handleRowClick(torrent)"
              >
                <td class="col-checkbox">
                  <el-checkbox v-model="torrent.checked" @change="handleSelectionChange" @click.native.stop />
                </td>
                <td class="col-status-icon">
                  <div
                    class="status-icon-circle"
                    :class="torrent.status"
                    :title="getStatusText(torrent.status)"
                  >
                    {{ getStatusIcon(torrent.status) }}
                  </div>
                </td>
                <td v-if="getColumnSetting('name').visible" class="col-name">
                  <div class="torrent-name-cell">
                    <span class="torrent-name-text" :title="torrent.name">{{ torrent.name }}</span>
                  </div>
                </td>
                <td v-if="getColumnSetting('size').visible" class="col-size">{{ formatFileSize(torrent.size) }}</td>
                <td v-if="getColumnSetting('progress').visible" class="col-progress">
                  <div class="progress-cell-compact">
                    <div class="progress-bar-wrapper">
                      <div
                        class="progress-bar-fill"
                        :class="torrent.status"
                        :style="{width: `${torrent.progress || 0}%`}"
                      ></div>
                    </div>
                    <span class="progress-text">{{ torrent.progress || 0 }}%</span>
                  </div>
                </td>
                <td v-if="getColumnSetting('status').visible" class="col-status">
                  <span class="status-badge-trad" :class="torrent.status">{{ getStatusText(torrent.status) }}</span>
                </td>
                <td v-if="getColumnSetting('download').visible" class="col-downspeed">
                  <span
                    class="speed-value-mono"
                    :class="getTorrentSpeed(torrent, 'download') ? 'download' : 'zero'"
                  >
                    {{ formatSpeed(getTorrentSpeed(torrent, 'download')) }}
                  </span>
                </td>
                <td v-if="getColumnSetting('upload').visible" class="col-upspeed">
                  <span
                    class="speed-value-mono"
                    :class="getTorrentSpeed(torrent, 'upload') ? 'upload' : 'zero'"
                  >
                    {{ formatSpeed(getTorrentSpeed(torrent, 'upload')) }}
                  </span>
                </td>
                <td v-if="getColumnSetting('ratio').visible" class="col-ratio">
                  <span
                    class="ratio-value-graded"
                    :class="getRatioClass(torrent.ratio)"
                  >
                    {{ formatRatio(torrent.ratio) }}
                  </span>
                </td>
                <td v-if="getColumnSetting('downloader').visible" class="col-downloader">{{ torrent.downloaderName || '-' }}</td>
                <td v-if="getColumnSetting('category').visible" class="col-category">
                  <span v-if="torrent.category" class="category-tag-mini cat">{{ torrent.category }}</span>
                  <span v-if="torrent.tags" class="category-tag-mini tag">{{ torrent.tags }}</span>
                  <span v-if="!torrent.category && !torrent.tags" style="color: var(--color-text-tertiary)">-</span>
                </td>
                <td v-if="getColumnSetting('added').visible" class="col-added">{{ formatDate(torrent.addedDate) }}</td>
                <td class="col-actions">
                  <div class="action-buttons-compact">
                    <button
                      class="action-btn-mini"
                      :class="torrent.status === 'paused' ? 'play' : 'pause'"
                      @click.stop="handleTogglePause(torrent)"
                      :title="torrent.status === 'paused' ? '开始' : '暂停'"
                    >
                      {{ torrent.status === 'paused' ? '▶' : '⏸' }}
                    </button>
                    <button
                      class="action-btn-mini recheck"
                      @click.stop="handleRecheck(torrent)"
                      title="重新检查"
                    >
                      ↻
                    </button>
                    <button
                      class="action-btn-mini location"
                      @click.stop="handleSetLocation(torrent)"
                      title="修改保存路径"
                    >
                      📁
                    </button>
                    <el-dropdown
                      @command="(cmd) => handleDeleteByLevelCommand(cmd, torrent)"
                      trigger="click"
                      :hide-on-click="true"
                      :append-to-body="true"
                      @click.native.stop
                    >
                      <button class="action-btn-mini delete" title="删除">🗑</button>
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
        </div>

        <!-- 分页 -->
        <div class="table-pagination">
          <div class="pagination-info">
            <el-select v-model="pageSize" size="mini" class="page-size-select" @change="handlePageSizeChange">
              <el-option
                v-for="size in pageSizeOptions"
                :key="size"
                :label="`${size} 条/页`"
                :value="size"
              />
            </el-select>
            <span>共 <strong>{{ total }}</strong> 条，第 <strong>{{ currentPage }}</strong>/<strong>{{ totalPages }}</strong> 页</span>
          </div>
          <div class="pagination-controls">
            <el-button
              size="mini"
              :disabled="currentPage <= 1"
              @click="handlePageChange(currentPage - 1)"
            >
              ◀
            </el-button>
            <el-button
              v-for="page in visiblePages"
              :key="page"
              size="mini"
              :class="{active: page === currentPage}"
              @click="handlePageChange(page)"
            >
              {{ page }}
            </el-button>
            <el-button
              size="mini"
              :disabled="currentPage >= totalPages"
              @click="handlePageChange(currentPage + 1)"
            >
              ▶
            </el-button>
          </div>
        </div>
      </div>

      <!-- 右侧详情面板 -->
      <div class="detail-panel-trad" :class="{open: !!currentRow}">
        <div class="detail-panel-content">
          <div class="detail-header-compact">
            <h3>{{ currentRow?.name }}</h3>
            <button class="close-btn" @click="closeDetailPanel">✕</button>
          </div>
          <div class="detail-tabs-compact">
            <button
              v-for="tab in detailTabs"
              :key="tab.value"
              class="tab-btn"
              :class="{active: activeDetailTab === tab.value}"
              @click="activeDetailTab = tab.value"
            >
              {{ tab.label }}
            </button>
          </div>
          <div class="detail-content">
            <!-- 常规信息 -->
            <template v-if="activeDetailTab === 'general'">
              <div class="detail-field-row">
                <span class="field-label">状态</span>
                <span class="field-value">
                  <span class="status-badge-trad" :class="currentRow?.status">{{ getStatusText(currentRow?.status) }}</span>
                </span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">进度</span>
                <span class="field-value">{{ currentRow?.progress || 0 }}%</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">大小</span>
                <span class="field-value">{{ formatFileSize(currentRow?.size) }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">下载速度</span>
                <span class="field-value speed-value-mono download">{{ formatSpeed(getTorrentSpeed(currentRow, 'download')) }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">上传速度</span>
                <span class="field-value speed-value-mono upload">{{ formatSpeed(getTorrentSpeed(currentRow, 'upload')) }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">分享率</span>
                <span class="field-value ratio-value-graded" :class="getRatioClass(currentRow?.ratio)">
                  {{ formatRatio(currentRow?.ratio) }}
                </span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">所属下载器</span>
                <span class="field-value">{{ currentRow?.downloaderName }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">分类</span>
                <span class="field-value">{{ currentRow?.category || '-' }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">标签</span>
                <span class="field-value">{{ currentRow?.tags || '-' }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">保存路径</span>
                <span class="field-value" :title="currentRow?.savePath">{{ currentRow?.savePath }}</span>
              </div>
              <div class="detail-field-row">
                <span class="field-label">添加时间</span>
                <span class="field-value">{{ formatDate(currentRow?.addedDate) }}</span>
              </div>
            </template>

            <!-- Tracker 信息 -->
            <template v-else-if="activeDetailTab === 'tracker'">
              <table class="tracker-table tracker-table-detail">
                <thead>
                  <tr>
                    <th>Tracker名称</th>
                    <th style="width: 80px;">Announce</th>
                    <th>Announce信息</th>
                    <th style="width: 80px;">Scrape</th>
                    <th style="width: 60px;" class="tracker-sticky-col">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(tracker, index) in (currentRow?.tracker_info || currentRow?.trackerInfo || [])"
                    :key="index"
                  >
                    <td>
                      <div>{{ tracker.tracker_name || tracker.trackerName || '未知' }}</div>
                      <div
                        class="tracker-url-mini"
                        :title="tracker.tracker_url || tracker.trackerUrl || '-'"
                      >{{ tracker.tracker_url || tracker.trackerUrl || '-' }}</div>
                    </td>
                    <td>
                      <span
                        :class="trackerStatusClass(tracker.last_announce_succeeded || tracker.lastAnnounceSucceeded)"
                      >
                        <template v-if="trackerAnnounceSuccess(tracker.last_announce_succeeded || tracker.lastAnnounceSucceeded)">
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
                        :class="trackerStatusClass(tracker.last_scrape_succeeded || tracker.lastScrapeSucceeded)"
                      >
                        <template v-if="trackerAnnounceSuccess(tracker.last_scrape_succeeded || tracker.lastScrapeSucceeded)">
                          ✓ 工作
                        </template>
                        <template v-else>
                          ✗ {{ tracker.last_scrape_succeeded || tracker.lastScrapeSucceeded || '失败' }}
                        </template>
                      </span>
                    </td>
                    <td class="tracker-sticky-col">
                      <el-button
                        type="text"
                        size="mini"
                        :loading="tracker.reannouncing"
                        @click="handleTrackerReannounce(tracker, index)"
                      >汇报</el-button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </template>

            <!-- 文件列表（占位） -->
            <template v-else-if="activeDetailTab === 'files'">
              <div style="text-align: center; color: var(--color-text-tertiary); padding: 20px;">
                文件列表功能开发中...
              </div>
            </template>

            <!-- Peers（占位） -->
            <template v-else-if="activeDetailTab === 'peers'">
              <div style="text-align: center; color: var(--color-text-tertiary); padding: 20px;">
                Peers 信息功能开发中...
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部全局状态栏 -->
    <div class="global-statusbar-compact">
      <div class="statusbar-section">
        <div class="connection-dot"></div>
        <span style="color: var(--color-text-secondary);">已连接</span>
      </div>
      <div class="statusbar-sep"></div>
      <div class="statusbar-section">
        <div class="global-speed">
          <span class="speed-icon down">↓</span>
          <span class="speed-val" style="color: #3b82f6;">{{ formatSpeed(globalDownloadSpeed) }}</span>
        </div>
        <div class="global-speed">
          <span class="speed-icon up">↑</span>
          <span class="speed-val" style="color: var(--color-success);">{{ formatSpeed(globalUploadSpeed) }}</span>
        </div>
      </div>
      <div class="statusbar-sep"></div>
      <div class="statusbar-section">
        <span class="label">活动:</span>
        <span style="color: var(--color-text-primary);">{{ activeTorrentCount }}</span>
        <span class="label">/ {{ total }}</span>
      </div>
      <div class="statusbar-right">
        <div
          v-for="downloader in downloaderList"
          :key="downloader.downloader_id"
          class="statusbar-section"
        >
          <span class="label">{{ downloader.nickname }}</span>
          <span style="color: var(--color-success);">●</span>
        </div>
      </div>
    </div>

    <!-- 复用现有对话框组件 -->
    <TorrentAddDialog
      :visible.sync="showAddDialog"
      :downloaders="downloaderList"
      @confirm="handleAdd"
    />

    <!-- P0新增：修改保存路径 -->
    <SetLocationDialog
      :visible.sync="showSetLocationDialog"
      :torrents="selectedTorrentsForLocation"
      @success="handleSetLocationSuccess"
    />

    <!-- P0新增：批量转移 -->
    <BatchTransferDialog
      :visible.sync="showBatchTransferDialog"
      :torrents="multipleSelection"
      @success="handleBatchTransferSuccess"
    />

    <!-- P0新增：Tracker操作（增/改/替换） -->
    <TrackerOperationDialog
      :visible.sync="showTrackerOperationDialog"
      :selected-torrents="selectedTorrentsForTracker"
      :operation-type="trackerOperationType"
      @success="handleTrackerOperationSuccess"
    />

    <!-- P0新增：全局替换Tracker -->
    <GlobalReplaceTrackerDialog
      :visible.sync="showGlobalReplaceDialog"
      @success="handleGlobalReplaceSuccess"
    />

    <!-- P1新增：高级搜索 -->
    <el-dialog
      title="🔍 高级搜索"
      :visible.sync="showAdvancedSearchDialog"
      width="80%"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      append-to-body
    >
      <AdvancedSearchBuilder
        ref="advancedSearchBuilder"
        :searching="advancedSearchSearching"
        @search="handleAdvancedSearchFromBuilder"
        @reset="handleResetAdvancedSearch"
        @save-template="handleSaveSearchTemplate"
      />
    </el-dialog>

    <!-- P2-2 列设置 -->
    <el-dialog
      title="⚙️ 列设置"
      :visible.sync="showColumnSettings"
      width="500px"
      append-to-body
    >
      <div class="columns-grid-trad">
        <label
          v-for="column in columnSettings"
          :key="column.key"
          class="column-checkbox-trad"
        >
          <input type="checkbox" v-model="column.visible" />
          <span>{{ column.label }}</span>
        </label>
      </div>
      <span slot="footer" class="dialog-footer">
        <el-button size="small" @click="resetColumnSettings">重置</el-button>
        <el-button size="small" @click="showColumnSettings = false">取消</el-button>
        <el-button size="small" type="primary" @click="applyColumnSettings">应用</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component } from 'vue-property-decorator'
import { mixins } from 'vue-class-component'
import { ViewModeModule, ViewModeType } from '@/store/modules/viewMode'
import TorrentAddDialog from './components/TorrentAddDialog.vue'
import SetLocationDialog from './components/SetLocationDialog.vue'
import BatchTransferDialog from './components/BatchTransferDialog.vue'
import TrackerOperationDialog from './components/TrackerOperationDialog.vue'
import GlobalReplaceTrackerDialog from './components/GlobalReplaceTrackerDialog.vue'
import FilterGroup from '@/components/torrents/FilterGroup.vue'
import TorrentBatchMixin from './mixins/torrentBatch'
// 复用现有 API、工具函数、状态配置
import {
  getTorrentList,
  addTorrent,
  deleteTorrents,
  pauseTorrents,
  resumeTorrents,
  recheckTorrents,
  reannounceTorrents,
  getDownloaderList,
  getActiveTorrents,
  advancedSearch,
  getDuplicateTorrents,
  applySearchTemplate,
  createSearchTemplate,
  type DownloaderSimple,
  type ActiveTorrentSpeed,
  type QueryTemplateConditions
} from '@/api/torrents'
import { getAllCategories, getAllTags } from '@/api/tag-management'
import { STATUS_OPTIONS, getStatusIcon, getStatusText } from '@/constants/status-config'
import {
  formatFileSize,
  formatSpeed,
  formatDate,
  formatRatio,
  normalizeTorrent,
  normalizePaginatedResponse,
  getTorrentId,
  getDownloaderId,
  extractErrorMessage,
  debounce
} from '@/utils/formatters'
// P0/P1下沉纯函数（防回归，避免复制列表模式逻辑）
import {
  assertSameDownloader,
  isTrackerAnnounceSuccess,
  getTrackerStatusClass,
  buildAdvancedSearchRequest,
  getTorrentSpeed as getTorrentSpeedFromSnapshot,
  deriveVisibleTorrentList,
  buildAdvancedSearchRequestFromTemplateGroups
} from './utils/torrentBatch'

interface FilterItem {
  icon: string
  label: string
  value: string
  count?: number
}

@Component({
  name: 'TraditionalView',
  components: {
    TorrentAddDialog,
    SetLocationDialog,
    BatchTransferDialog,
    TrackerOperationDialog,
    GlobalReplaceTrackerDialog,
    FilterGroup,
    AdvancedSearchBuilder: () => import('@/components/torrents/AdvancedSearchBuilder.vue')
  }
})
export default class extends mixins(TorrentBatchMixin) {
  // ====== 状态管理 ======
  private viewModeModule = ViewModeModule

  // ====== 数据状态 ======
  private list: any[] = []
  private total = 0
  private listLoading = true
  private multipleSelection: any[] = []

  // 实时速度轮询
  private speedTimer: number | null = null
  private speedPollingActive = false
  private speedSnapshotReady = false
  private activeSpeedMap: Record<string, { downloadSpeed: number, uploadSpeed: number, progress: number }> = {}

  // 分类和标签数据
  private categoryList: string[] = []
  private tagList: string[] = []

  // 分页
  private currentPage = 1
  private pageSize = 20
  private pageSizeOptions = [10, 20, 50, 100]

  // 复选框
  private selectAll = false
  private isIndeterminate = false

  // 弹窗状态
  private showAddDialog = false
  // P0新增弹窗状态
  private showSetLocationDialog = false
  private showBatchTransferDialog = false
  private showTrackerOperationDialog = false
  private showGlobalReplaceDialog = false

  // P0新增：修改路径 / Tracker操作 的选中种子载体
  private selectedTorrentsForLocation: any[] = []
  private selectedTorrentsForTracker: any[] = []
  private trackerOperationType: 'add' | 'replace' | 'modify' | '' = ''

  // P1新增：高级搜索 / 查找重复
  private showAdvancedSearchDialog = false
  private advancedSearchSearching = false

  // 详情面板
  private currentRow: any = null
  private activeDetailTab = 'general'
  private detailTabs = [
    { label: '常规', value: 'general' },
    { label: 'Tracker', value: 'tracker' },
    { label: '文件', value: 'files' },
    { label: 'Peers', value: 'peers' }
  ]

  // 查询参数（复用现有结构）
  private listQuery: any = {
    skip: 0,
    limit: 20,
    name_like: '',
    downloader_id: [],
    status: [],
    category_like: '',
    tags_like: '',
    showActiveOnly: false, // P0#1：仅显示活动种子（前端过滤，known-issue：分页total失真）
    sort_by: 'added_date', // P1前置：统一蛇形，后端用 getattr(TorrentInfo, sort_by) 匹配ORM字段名
    sort_order: 'desc'
  }

  // 下载器列表
  private downloaderList: DownloaderSimple[] = []

  // P2-2 列设置（3列固定：checkbox/statusIcon/actions 不在此数组；11列可隐藏）
  private showColumnSettings = false
  private columnSettings = [
    { key: 'name', label: '名称', visible: true },
    { key: 'size', label: '大小', visible: true },
    { key: 'progress', label: '进度', visible: true },
    { key: 'status', label: '状态', visible: true },
    { key: 'download', label: '下载速度', visible: true },
    { key: 'upload', label: '上传速度', visible: true },
    { key: 'ratio', label: '比率', visible: true },
    { key: 'downloader', label: '下载器', visible: true },
    { key: 'category', label: '分类/标签', visible: true },
    { key: 'added', label: '添加时间', visible: true }
  ]

  // 防抖搜索
  private debouncedSearch: any = null

  // ====== 计算属性 ======
  get totalPages() {
    return Math.ceil(this.total / this.pageSize)
  }

  get visiblePages() {
    const pages: number[] = []
    const showPages = 5
    let start = Math.max(1, this.currentPage - Math.floor(showPages / 2))
    let end = Math.min(this.totalPages, start + showPages - 1)

    if (end - start < showPages - 1) {
      start = Math.max(1, end - showPages + 1)
    }

    for (let i = start; i <= end; i++) {
      pages.push(i)
    }

    return pages
  }

  get sortedList() {
    // 委托给 mixin 的 sortedActiveList（逻辑单点维护，防回归 Bug#7）
    // 模板通过 sortedList 引用，这里做透传
    return deriveVisibleTorrentList(
      this.list,
      this.activeSpeedMap,
      this.speedSnapshotReady,
      this.listQuery.showActiveOnly === true
    )
  }

  get globalDownloadSpeed() {
    return Object.values(this.activeSpeedMap).reduce((sum, s) => sum + s.downloadSpeed, 0)
  }

  get globalUploadSpeed() {
    return Object.values(this.activeSpeedMap).reduce((sum, s) => sum + s.uploadSpeed, 0)
  }

  get activeTorrentCount() {
    return Object.keys(this.activeSpeedMap).length
  }

  // ====== 过滤器数据 ======
  get statusFilterItems(): FilterItem[] {
    return [
      { icon: '📥', label: '全部', value: '' },
      ...STATUS_OPTIONS.map(opt => ({
        icon: getStatusIcon(opt.value),
        label: opt.label.replace(/^[^\s]+\s*/, ''),
        value: opt.value
      }))
    ]
  }

  get downloaderFilterItems(): FilterItem[] {
    return [
      { icon: '🖥', label: '全部', value: '' },
      ...this.downloaderList.map(d => ({
        icon: '🔵',
        label: d.nickname,
        value: d.downloader_id
      }))
    ]
  }

  get categoryFilterItems(): FilterItem[] {
    const items = [
      { icon: '📂', label: '全部', value: '' },
      ...this.categoryList.map(name => ({
        icon: '📁',
        label: name,
        value: name
      }))
    ]
    return items
  }

  get tagFilterItems(): FilterItem[] {
    const items = [
      { icon: '🏷', label: '全部', value: '' },
      ...this.tagList.map(name => ({
        icon: '🏷',
        label: name,
        value: name
      }))
    ]
    return items
  }

  // ====== 生命周期 ======
  public async created() {
    this.debouncedSearch = debounce(this.handleFilter, 300)
    this.loadColumnPreferences() // P2-2：加载列显隐偏好
    await this.fetchDownloaderList()
    await this.fetchCategoryAndTags()
    await this.getList()
    this.startSpeedPolling()

    // P1#9：处理从查询模板管理页跳转来的应用请求（traditional 模式下 index.vue 未挂载，
    // 路由参数需在本视图处理）
    await this.handleApplyTemplateFromRoute()
  }

  public beforeDestroy() {
    this.stopSpeedPolling()
    // P2-I：调 mixin 的 loading 清理，防 4 等级删除轮询期间销毁残留遮罩
    ;(this as any).closeDeleteLoading && (this as any).closeDeleteLoading()
  }

  // ====== 数据获取 ======
  private async getList() {
    this.listLoading = true
    try {
      const params = { ...this.listQuery }
      params.skip = (this.currentPage - 1) * this.pageSize
      params.limit = this.pageSize

      // P0#1：showActiveOnly 仅前端过滤，不发给后端
      delete params.showActiveOnly

      // 处理数组参数
      if (Array.isArray(params.downloader_id) && params.downloader_id.length > 0) {
        params.downloader_id = params.downloader_id.join(',')
      } else {
        delete params.downloader_id
      }

      if (Array.isArray(params.status) && params.status.length > 0) {
        params.status = params.status.join(',')
      } else {
        delete params.status
      }

      // 清理空值
      Object.keys(params).forEach(key => {
        if (params[key] === '' || params[key] === null || params[key] === undefined) {
          delete params[key]
        }
      })

      const response = await getTorrentList(params)
      const { list, total } = normalizePaginatedResponse<any>(response)

      // 规范化并提供默认 checked
      const normalizedList = list.map(normalizeTorrent).map(item => ({
        ...item,
        checked: false
      }))

      // P0#1 前端过滤"仅显示活动种子"：筛选有速度的种子
      // known-issue（对齐列表模式 index.vue 既有缺陷）：开启后分页 total 变为当前页过滤后的条数，
      // 翻页时每页独立过滤、页码总数失真。后续可改用 getActiveTorrents 全量拉取彻底解决。
      this.list = normalizedList
      this.total = total

      // 修复 Bug#8：新数据全部 checked:false，必须同步重置批量选中状态，
      // 否则分页/筛选切换后 multipleSelection 仍持有已不在当前视图的旧种子，
      // 用户在加载期间点击批量操作会误伤。
      // 委托给 mixin 的 resetBatchSelection（逻辑单点维护）
      this.resetBatchSelection()
    } catch (error) {
      console.error('获取种子列表失败:', error)
      this.$message.error('获取种子列表失败')
    } finally {
      this.listLoading = false
    }
  }

  private async fetchDownloaderList() {
    try {
      const response = await getDownloaderList()
      this.downloaderList = response.data || []
    } catch (error) {
      console.error('获取下载器列表失败:', error)
    }
  }

  private async fetchCategoryAndTags() {
    try {
      // 并发获取分类和标签
      const [categoryResponse, tagResponse] = await Promise.all([
        getAllCategories(),
        getAllTags()
      ])

      if (categoryResponse.code === '200' && categoryResponse.data) {
        this.categoryList = categoryResponse.data
      }

      if (tagResponse.code === '200' && tagResponse.data) {
        this.tagList = tagResponse.data
      }
    } catch (error) {
      console.error('获取分类和标签失败:', error)
    }
  }

  // ====== 实时速度轮询 ======
  private startSpeedPolling() {
    if (this.speedPollingActive) return
    this.speedPollingActive = true
    const poll = async() => {
      if (!this.speedPollingActive) return
      await this.loadActiveSpeed()
      if (!this.speedPollingActive) return
      this.speedTimer = window.setTimeout(poll, 1000)
    }
    poll()
  }

  private stopSpeedPolling() {
    this.speedPollingActive = false
    if (this.speedTimer) {
      window.clearTimeout(this.speedTimer)
      this.speedTimer = null
    }
  }

  /**
   * 加载活跃种子实时速度和进度（对齐列表模式 index.vue:2177-2214）
   * 修复 Bug#3：原用原生 fetch + localStorage.getItem('token')，
   * token 实际存在 Cookie（cookies.ts:10），导致恒为 null → 401 → 速度永远为 0。
   * 改用封装的 getActiveTorrents()，复用统一 axios 拦截器（token 注入、401 跳登录）。
   */
  private async loadActiveSpeed() {
    const requestId = Date.now()
    try {
      const res = await getActiveTorrents()
      if (res.code === '200' && res.data) {
        const map: Record<string, { downloadSpeed: number, uploadSpeed: number, progress: number }> = {}
        const torrents = res.data as ActiveTorrentSpeed[]
        torrents.forEach((t: ActiveTorrentSpeed) => {
          // 防御性检查：确保 hash 字段存在
          if (!t.hash) {
            console.warn('[速度轮询] 跳过无效种子数据:', t)
            return
          }
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
        this.speedSnapshotReady = true
        console.debug(`[速度轮询] 请求 ${requestId} 完成，更新 ${Object.keys(map).length} 个活跃种子`)
      }
    } catch (e) {
      // 静默失败，不影响主流程
      console.debug(`[速度轮询] 请求 ${requestId} 失败:`, e)
    }
  }

  private getTorrentSpeed(torrent: any, type: 'download' | 'upload'): number | null {
    if (!torrent || !torrent.hash) {
      return null
    }
    return getTorrentSpeedFromSnapshot(torrent, type, this.activeSpeedMap, this.speedSnapshotReady)
  }

  // ====== 工具方法 ======
  private formatFileSize = formatFileSize
  private formatSpeed = formatSpeed
  private formatDate = formatDate
  private formatRatio = formatRatio
  private getStatusIcon = getStatusIcon
  private getStatusText = getStatusText

  private getRatioClass(ratio: number | string) {
    const r = typeof ratio === 'string' ? parseFloat(ratio) : ratio
    if (r < 0.5) return 'low'
    if (r < 1.0) return 'mid'
    if (r < 2.0) return 'good'
    return 'great'
  }

  // 注：isTrackerSuccess/getTrackerStatusText 已删除，统一委托给
  // 下沉纯函数 trackerAnnounceSuccess/trackerStatusClass（防回归 P0-D，消除两视图语义分歧）

  // ====== 事件处理 ======
  private handleFilter() {
    this.currentPage = 1
    this.getList()
  }

  private handleSort(field: string) {
    if (this.listQuery.sort_by === field) {
      this.listQuery.sort_order = this.listQuery.sort_order === 'asc' ? 'desc' : 'asc'
    } else {
      this.listQuery.sort_by = field
      this.listQuery.sort_order = 'desc'
    }
    this.getList()
  }

  private handlePageChange(page: number) {
    this.currentPage = page
    this.getList()
  }

  private handlePageSizeChange() {
    this.currentPage = 1
    this.getList()
  }

  private handleSelectAll(checked: boolean) {
    this.list.forEach(item => {
      item.checked = checked
    })
    this.handleSelectionChange()
  }

  private handleSelectionChange() {
    this.multipleSelection = this.list.filter(item => item.checked)
    this.isIndeterminate = this.multipleSelection.length > 0 && this.multipleSelection.length < this.list.length
    this.selectAll = this.multipleSelection.length === this.list.length
  }

  private handleRowClick(torrent: any) {
    if (this.currentRow?.hash === torrent.hash) {
      this.currentRow = null
      return
    }
    this.currentRow = torrent
    this.activeDetailTab = 'general'
  }

  private closeDetailPanel() {
    this.currentRow = null
  }

  private toggleFilterPanel() {
    this.viewModeModule.toggleFilterPanel()
  }

  private switchViewMode(mode: ViewModeType) {
    this.viewModeModule.setViewMode(mode)
  }

  // 过滤器选择
  private handleStatusFilter(value: string) {
    if (value === '') {
      this.listQuery.status = []
    } else {
      this.listQuery.status = [value]
    }
    this.handleFilter()
  }

  private handleDownloaderFilter(value: string) {
    if (value === '') {
      this.listQuery.downloader_id = []
    } else {
      this.listQuery.downloader_id = [value]
    }
    this.handleFilter()
  }

  private handleCategoryFilter(value: string) {
    this.listQuery.category_like = value
    this.handleFilter()
  }

  private handleTagFilter(value: string) {
    this.listQuery.tags_like = value
    this.handleFilter()
  }

  // ====== 辅助方法 ======
  // groupTorrentsByDownloader / deleteTorrentsInternal / 批量开始/暂停/重检
  // 已由 TorrentBatchMixin 提供（mixins/torrentBatch.ts + utils/torrentBatch.ts），
  // 此处不再重复实现，消除「改一处忘一处」的回归风险。

  // ====== 批量操作 ======
  // handleBatchStart / handleBatchPause / handleBatchRecheck 由 mixin 提供，
  // 模板 @click 直接绑定 mixin 的方法（Vue 2 class mixin 合并后可访问）。

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

  private async performBatchDelete(deleteData: number) {
    // deleteTorrentsInternal 由 mixin 提供（注入真实 deleteTorrents）
    const results = await this.deleteTorrentsInternal(this.multipleSelection, deleteData)

    const dataFileText = deleteData === 1 ? '（已删除数据文件）' : '（已保留数据文件）'
    if (results.failCount === 0) {
      this.$message.success(`成功删除 ${results.successCount} 个种子 ${dataFileText}`)
    } else if (results.successCount === 0) {
      // 汇总错误原因（对齐列表模式 index.vue:1717-1734）
      const errorCounts = results.errors.reduce((acc, err) => {
        acc[err] = (acc[err] || 0) + 1
        return acc
      }, {} as Record<string, number>)
      const errorMsg = Object.keys(errorCounts).length > 0
        ? Object.entries(errorCounts).map(([err, count]) => `${err}(${count}次)`).join('; ')
        : `共 ${results.failCount} 个种子删除失败`
      this.$message.error(`批量删除失败: ${errorMsg}`)
    } else {
      const errorDetail = results.errors.length > 0
        ? ` 失败原因: ${results.errors.slice(0, 3).join('; ')}`
        : ''
      this.$message.warning(
        `部分删除成功：成功 ${results.successCount} 个，失败 ${results.failCount} 个 ${dataFileText}${errorDetail}`
      )
    }

    this.getList()
  }

  // ====== 单个种子操作 ======
  private async handleTogglePause(torrent: any) {
    if (!torrent) return

    const downloaderId = torrent.downloader_id || torrent.downloaderId
    if (!downloaderId) {
      this.$message.error('种子缺少下载器信息')
      return
    }

    try {
      if (torrent.status === 'paused') {
        await resumeTorrents({ downloader_id: downloaderId, hashes: [torrent.hash] })
        this.$message.success('开始任务成功')
      } else {
        await pauseTorrents({ downloader_id: downloaderId, hashes: [torrent.hash] })
        this.$message.success('暂停任务成功')
      }
      this.getList()
    } catch (error) {
      console.error('切换暂停状态失败:', error)
      this.$message.error('操作失败')
    }
  }

  private async handleRecheck(torrent: any) {
    if (!torrent) return

    const downloaderId = torrent.downloader_id || torrent.downloaderId
    if (!downloaderId) {
      this.$message.error('种子缺少下载器信息')
      return
    }

    try {
      await recheckTorrents({ downloader_id: downloaderId, hashes: [torrent.hash] })
      this.$message.success('重新检查任务已提交')
      this.getList()
    } catch (error) {
      console.error('重检种子失败:', error)
      this.$message.error('重检失败')
    }
  }

  private async handleDelete(torrent: any) {
    if (!torrent) return

    this.$confirm(`确定要删除种子"${torrent.name}"吗？`, '删除确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async() => {
      this.$confirm('是否同时删除数据文件？', '删除数据文件', {
        confirmButtonText: '同时删除种子和数据',
        cancelButtonText: '仅删除种子，保留数据',
        distinguishCancelAndClose: true,
        type: 'warning'
      }).then(async() => {
        await this.performSingleDelete(torrent, 1)
      }).catch((action) => {
        if (action === 'cancel') {
          this.performSingleDelete(torrent, 0)
        }
      })
    }).catch(() => undefined)
  }

  private async performSingleDelete(torrent: any, deleteData: number) {
    // 修复 Bug#4：deleteTorrents 后端只接受 info_id / delete_data / id_recycle，
    // 不识别 hashes / deleteData。对齐列表模式 index.vue:1808-1821。
    const infoId = getTorrentId(torrent)
    const downloaderId = getDownloaderId(torrent)
    if (!downloaderId) {
      this.$message.error('种子缺少下载器信息')
      return
    }

    try {
      await deleteTorrents({
        info_id: infoId,
        downloader_id: downloaderId,
        delete_data: deleteData,
        id_recycle: 1
      })

      const dataFileText = deleteData === 1 ? '（已删除数据文件）' : '（已保留数据文件）'
      this.$message.success(`删除种子成功 ${dataFileText}`)
      this.getList()
      // 如果删除的是当前详情面板的种子，关闭详情面板
      if (this.currentRow?.hash === torrent.hash) {
        this.currentRow = null
      }
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('删除种子失败:', error)
      this.$message.error(errorMessage || '删除种子失败')
    }
  }

  private async handleAdd(torrentData: any) {
    try {
      const response = await addTorrent(torrentData)
      if (response.code === '200') {
        this.$message.success('添加种子成功')
        this.showAddDialog = false
        this.getList()
      } else {
        this.$message.error(response.msg || '添加种子失败')
      }
    } catch (error) {
      console.error('添加种子失败:', error)
      this.$message.error('添加种子失败')
    }
  }

  // ====== P0#2 手动刷新（对齐列表模式，含静态+速度双刷新） ======
  private handleManualRefresh() {
    this.getList()
    this.loadActiveSpeed()
  }

  // ====== P0#3/#4 Tracker 状态判断（委托下沉的纯函数） + 单条汇报 ======
  private trackerAnnounceSuccess(status: string | boolean | undefined | null): boolean {
    return isTrackerAnnounceSuccess(status)
  }

  private trackerStatusClass(status: string | boolean | undefined | null): string {
    return getTrackerStatusClass(status)
  }

  /** P0#4 单条 Tracker 汇报（在详情面板 Tracker tab 内触发） */
  private async handleTrackerReannounce(tracker: any, _index: number) {
    if (!this.currentRow?.hash) {
      this.$message.error('种子信息不完整，无法汇报')
      return
    }
    const downloaderId = this.currentRow.downloader_id || this.currentRow.downloaderId
    this.$set(tracker, 'reannouncing', true)
    try {
      const response = await reannounceTorrents({
        hashes: [this.currentRow.hash],
        downloader_id: downloaderId
      })
      if (response.code === '200') {
        this.$message.success('Tracker汇报成功')
        await this.getList()
      } else {
        this.$message.error(response.msg || 'Tracker汇报失败')
      }
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('Tracker汇报失败:', error)
      this.$message.error(errorMessage || 'Tracker汇报失败')
    } finally {
      this.$set(tracker, 'reannouncing', false)
    }
  }

  // ====== P0#5 批量 Tracker 汇报（按下载器分组，复用 mixin groupBy） ======
  private async handleBatchReannounce() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请先选择要汇报的种子')
      return
    }
    try {
      const groups = this.groupTorrentsByDownloader(this.multipleSelection)
      const promises = Object.entries(groups).map(([downloaderId, torrents]) => {
        const hashes = torrents.map(t => t.hash)
        return reannounceTorrents({ downloader_id: downloaderId, hashes })
      })
      const responses = await Promise.allSettled(promises)
      const succeeded = responses.filter(r => r.status === 'fulfilled').length
      const failed = responses.filter(r => r.status === 'rejected').length
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

  // ====== P0#6 修改保存路径（单条+批量） ======
  private handleSetLocation(torrent: any) {
    this.selectedTorrentsForLocation = [torrent]
    this.showSetLocationDialog = true
  }

  private handleBatchSetLocation() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请先选择种子')
      return
    }
    // 同源校验委托纯函数（防回归 P0-E）
    const check = assertSameDownloader(this.multipleSelection)
    if (!check.ok) {
      this.$message.warning(check.reason)
      return
    }
    this.selectedTorrentsForLocation = this.multipleSelection
    this.showSetLocationDialog = true
  }

  private handleSetLocationSuccess() {
    this.showSetLocationDialog = false
    this.getList()
  }

  // ====== P0#7 批量转移 ======
  private handleBatchTransfer() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请先选择要转移的种子')
      return
    }
    const check = assertSameDownloader(this.multipleSelection)
    if (!check.ok) {
      this.$message.warning(check.reason)
      return
    }
    this.showBatchTransferDialog = true
  }

  private handleBatchTransferSuccess() {
    this.showBatchTransferDialog = false
    this.getList()
    this.$message.success('批量转移操作完成')
  }

  // ====== P0#8 Tracker 操作（增/改/替换） ======
  private handleBatchTracker() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请先选择要操作的种子')
      return
    }
    this.selectedTorrentsForTracker = [...this.multipleSelection]
    this.trackerOperationType = ''
    this.showTrackerOperationDialog = true
  }

  private handleTrackerOperationSuccess() {
    this.getList()
    this.$message.success('Tracker操作成功')
  }

  // ====== P0#9 全局替换 Tracker ======
  private handleGlobalReplaceSuccess() {
    this.getList()
    this.$message.success('全局替换Tracker成功')
  }

  // ====== P1#8 高级搜索 ======
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

  /**
   * P1#8 执行高级搜索（解析逻辑委托 buildAdvancedSearchRequest 纯函数，防回归 P1-F）
   * 视图只保留「调 API + 设 list/total + 提示」
   */
  private async performAdvancedSearch(searchParams: any) {
    this.advancedSearchSearching = true
    try {
      const { request, error } = buildAdvancedSearchRequest(
        searchParams,
        this.listQuery.sort_by || 'added_date',
        this.listQuery.limit || this.pageSize
      )
      if (error || !request) {
        this.$message.error(error || '搜索条件格式错误')
        return
      }

      const response = await advancedSearch(request)
      if (response.code === '200' && response.data) {
        this.list = (response.data.list || []).map(normalizeTorrent).map(item => ({ ...item, checked: false }))
        this.total = response.data.total || 0
        this.listQuery.skip = 0
        this.currentPage = 1
        this.resetBatchSelection()
        this.$message.success(`高级搜索完成，找到 ${this.total} 条结果`)
      } else {
        this.$message.error(response.msg || '搜索失败')
      }
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('高级搜索失败:', error)
      this.$message.error(errorMessage || '高级搜索失败，请检查搜索条件')
    } finally {
      this.advancedSearchSearching = false
    }
  }

  /** P1#9 把当前高级搜索条件保存为查询模板 */
  private async handleSaveSearchTemplate(template: any) {
    const conditions: QueryTemplateConditions = {
      source: 'advanced',
      version: 1,
      condition_groups: template.conditions || [],
      sort_by: this.listQuery.sort_by,
      sort_order: this.listQuery.sort_order
    }
    try {
      const response = await createSearchTemplate({
        name: template.name,
        description: template.description,
        conditions,
        is_public: false
      } as any)
      if (response.code === '200') {
        this.$message.success('模板保存成功')
      } else {
        this.$message.error(response.msg || '模板保存失败')
      }
    } catch (error) {
      this.$message.error('模板保存失败：' + (error as Error).message)
    }
  }

  /**
   * P1#9 应用查询模板（按 conditions.source 分支）
   * - source=simple：回填 listQuery 并 getList()
   * - source=advanced：回填 AdvancedSearchBuilder 的 conditionGroups 并执行（依赖#8）
   */
  private async applyQueryTemplate(conditions: QueryTemplateConditions): Promise<boolean> {
    if (!conditions || !conditions.source) {
      this.$message.error('模板条件格式无效')
      return false
    }
    try {
      if (conditions.source === 'simple' && conditions.listQuery) {
        const saved = conditions.listQuery
        this.listQuery = {
          skip: 0,
          limit: this.listQuery.limit,
          name_like: saved.name_like ?? '',
          downloader_id: saved.downloader_id ? [...saved.downloader_id] : [],
          status: saved.status ? [...saved.status] : [],
          category_like: saved.category_like ?? '',
          tags_like: saved.tags_like ?? '',
          showActiveOnly: saved.showActiveOnly ?? false,
          sort_by: saved.sort_by ?? 'added_date',
          sort_order: saved.sort_order ?? 'desc'
        }
        this.currentPage = 1
        await this.getList()
        this.$message.success('已应用查询模板')
        return true
      } else if (conditions.source === 'advanced' && conditions.condition_groups) {
        const sortBy = conditions.sort_by || this.listQuery.sort_by || 'added_date'
        const sortOrder = conditions.sort_order || this.listQuery.sort_order || 'desc'
        this.listQuery.sort_by = sortBy
        this.listQuery.sort_order = sortOrder
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

  /** P1#9 处理路由 query 中的 apply_template_id（从查询模板管理页跳转来） */
  private async handleApplyTemplateFromRoute() {
    const templateId = this.$route.query.apply_template_id as string | undefined
    if (!templateId) return
    let applied = false
    try {
      const response = await applySearchTemplate(templateId)
      if (response.code === '200' && response.data) {
        const conditions = (response.data as any).conditions as QueryTemplateConditions
        if (conditions) {
          applied = await this.applyQueryTemplate(conditions)
        }
      } else {
        this.$message.error(response.msg || '应用模板失败')
      }
    } catch (error) {
      this.$message.error('应用模板失败：' + (error as Error).message)
    }
    if (applied) {
      // 清除 query 参数，避免刷新重复应用
      this.$router.replace({ query: {} })
    }
  }

  // ====== P1#10 查找重复任务 ======
  private async handleShowDuplicateTorrents() {
    this.listLoading = true
    try {
      const response = await getDuplicateTorrents()
      if (response.code === '200' && response.data) {
        const dupList = (response.data.list || response.data.torrents || []) as any[]
        this.list = dupList.map(normalizeTorrent).map(item => ({ ...item, checked: false }))
        this.total = dupList.length
        this.currentPage = 1
        this.resetBatchSelection()
        this.$message.success(`找到 ${dupList.length} 条重复种子`)
      } else {
        this.$message.error(response.msg || '查找重复失败')
      }
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('查找重复失败:', error)
      this.$message.error(errorMessage || '查找重复失败')
    } finally {
      this.listLoading = false
    }
  }

  // ====== P2-2 列设置 ======
  private getColumnSetting(key: string) {
    return this.columnSettings.find(col => col.key === key) || { visible: true }
  }

  private resetColumnSettings() {
    this.columnSettings.forEach(column => { column.visible = true })
  }

  private applyColumnSettings() {
    this.showColumnSettings = false
    this.saveColumnPreferences()
    this.$message.success('列设置已保存')
  }

  private saveColumnPreferences() {
    const visibility = this.columnSettings.reduce((acc, col) => {
      acc[col.key] = col.visible
      return acc
    }, {} as Record<string, boolean>)
    // P2-J：用独立 key，与列表模式 torrents_columns_visibility 分开（两视图列结构不同）
    localStorage.setItem('traditional_columns_visibility', JSON.stringify(visibility))
  }

  private loadColumnPreferences() {
    const saved = localStorage.getItem('traditional_columns_visibility')
    if (!saved) return
    try {
      const visibilityMap = JSON.parse(saved)
      this.columnSettings.forEach(col => {
        if (col.key in visibilityMap) {
          col.visible = visibilityMap[col.key]
        }
      })
    } catch (e) {
      console.error('加载列设置失败:', e)
    }
  }
}
</script>

<style lang="scss" scoped>
// 复用现有样式变量
@import '@/styles/traditional-view-theme.scss';

.traditional-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-primary);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.page-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.toolbar-left,
.toolbar-center,
.toolbar-right {
  display: flex;
  align-items: center;
}

.toolbar-center {
  flex: 1;
  justify-content: center;
  gap: 8px;
}

.filter-toggle-btn {
  font-size: 16px;
}

.tool-divider {
  width: 1px;
  height: 18px;
  background: var(--color-border-primary);
  margin: 0 3px;
}

.search-input {
  width: 220px;

  ::v-deep .el-input__inner {
    font-size: 12px;
  }
}

// P0新增：活动种子开关 + 手动刷新按钮（在 toolbar-center）
.active-only-checkbox {
  margin: 0 4px;
  ::v-deep .el-checkbox__label { font-size: 12px; padding-left: 4px; }
}

.manual-refresh-btn {
  padding: 0 6px;
}

// P0新增：批量操作行（容纳进阶批量操作，避免主 toolbar 过挤）
.traditional-batch-ops {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 10px;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border-primary);
  flex-shrink: 0;

  .el-button--text {
    font-size: 12px;
    padding: 3px 6px;
  }
}

.selection-info {
  font-size: 11px;
  color: var(--color-text-tertiary);
  padding: 3px 7px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  display: none;

  &.visible {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .count {
    color: var(--color-primary);
    font-weight: var(--font-weight-semibold);
  }
}

.view-switcher {
  display: flex;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  padding: 2px;
  gap: 1px;

  .el-button--text {
    &.active {
      background: var(--color-primary);
      color: white;
    }
  }
}

.table-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.table-container {
  flex: 1;
  overflow: auto;
  position: relative;

  // 使用项目滚动条样式
  &::-webkit-scrollbar {
    width: var(--scrollbar-width);
    height: var(--scrollbar-height);
  }

  &::-webkit-scrollbar-thumb {
    background: var(--scrollbar-thumb-bg);
    border-radius: var(--scrollbar-border-radius);
  }

  &::-webkit-scrollbar-thumb:hover {
    background: var(--scrollbar-thumb-bg-hover);
  }
}

// 表格列宽
.col-checkbox { width: 36px; text-align: center !important; }
.col-status-icon { width: 32px; text-align: center !important; }
.col-name { /* auto */ }
.col-size { width: 80px; }
.col-progress { width: 130px; }
.col-status { width: 90px; }
.col-downspeed { width: 90px; }
.col-upspeed { width: 90px; }
.col-ratio { width: 60px; }
.col-downloader { width: 100px; }
.col-category { width: 130px; }
.col-added { width: 120px; }
.col-actions { width: 100px; }

.table-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  background: var(--color-bg-primary);
  border-top: 1px solid var(--color-border-primary);
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;

  .pagination-info {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .pagination-controls {
    display: flex;
    align-items: center;
    gap: 1px;

    .el-button--mini {
      &.active {
        background: var(--color-primary);
        color: white;
        border-color: var(--color-primary);
      }
    }
  }

  .page-size-select {
    width: 90px;
  }
}

// Tracker 表格样式
.tracker-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;

  th {
    text-align: left;
    padding: 5px;
    background: var(--color-bg-secondary);
    border-bottom: 1px solid var(--color-border-primary);
    color: var(--color-text-tertiary);
    font-weight: var(--font-weight-semibold);
  }

  td {
    padding: 5px;
    border-bottom: 1px solid var(--color-border-secondary);
  }

  .tracker-status {
    display: flex;
    align-items: center;
    gap: 4px;

    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;

      &.ok {
        background: var(--color-success);
      }

      &.fail {
        background: var(--color-error);
      }
    }
  }

  // P0#3 Tracker 详情表增强样式
  &.tracker-table-detail {
    .tracker-url-mini {
      font-size: 10px;
      color: var(--color-text-tertiary);
      max-width: 120px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    // Announce/Scrape 状态色（复用列表模式 class 名）
    .tracker-status-working { color: var(--color-success); }
    .tracker-status-error { color: var(--color-error); }
    .tracker-status-neutral { color: var(--color-text-tertiary); }

    .tracker-sticky-col {
      position: sticky;
      right: 0;
      background: var(--color-bg-primary);
    }
  }
}

// P2-2 列设置对话框
.columns-grid-trad {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 16px;

  .column-checkbox-trad {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--color-text-primary);
    cursor: pointer;

    input[type='checkbox'] {
      cursor: pointer;
    }
  }
}
</style>
