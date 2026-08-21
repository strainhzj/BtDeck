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
            <i class="el-icon-delete"></i> 删除<i class="el-icon-arrow-down el-icon--right"></i>
          </el-button>
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
          @click="openAdvancedSearch"
        >
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
      <el-dropdown trigger="click" @command="handleQuickActionCommand">
        <el-button type="text" size="small" title="快捷操作">
          快捷操作<i class="el-icon-arrow-down el-icon--right"></i>
        </el-button>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="inspect-same-content">
            <i class="el-icon-search"></i> 同内容异常排查
          </el-dropdown-item>
          <el-dropdown-item command="inspect-single-errors">
            <i class="el-icon-warning-outline"></i> 错误单种排查
          </el-dropdown-item>
          <el-dropdown-item command="delete-duplicates">
            <i class="el-icon-delete"></i> 快捷删除重复种子
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </div>
    <el-alert
      v-if="showingSameContent"
      class="same-content-list-alert"
      title="同内容异常排查：当前列表仅显示名称、大小相同但 InfoHash 不同的种子"
      type="warning"
      :closable="false"
      show-icon
    >
      <el-button type="text" size="small" @click="exitSameContentInspection">
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
      <el-button type="text" size="small" @click="exitSingleErrorInspection">
        退出排查并返回普通列表
      </el-button>
    </el-alert>
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
            :active-value="activeStatusFilterValue"
            @select="handleStatusFilter"
          />

          <!-- 下载器过滤 -->
          <FilterGroup
            title="下载器"
            :items="downloaderFilterItems"
            :active-value="listQuery.downloader_id"
            @select="handleDownloaderFilter"
          />

          <!-- Tracker 主域名过滤 -->
          <div class="tracker-domain-filter">
            <div class="filter-group-title">Tracker主域名</div>
            <AdvancedMultiSelect
              v-model="listQuery.tracker_domain"
              placeholder="请选择tracker"
              :options="trackerDomainOptions"
              :allow-create="false"
              :show-mode-toggle="false"
              :virtual-scroll-threshold="100"
              :list-height="240"
              style="width: 100%;"
              @change="handleFilter"
            />
          </div>

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
        <div
          ref="tableContainer"
          class="table-container"
          v-loading="listLoading"
          @scroll="handleTableScroll"
        >
          <table
            class="torrent-table traditional-table"
            :aria-rowcount="sortedList.length + 1"
            :style="{width: tableMinWidth + 'px', minWidth: tableMinWidth + 'px'}"
          >
            <thead>
              <tr>
                <th class="col-checkbox" :style="columnWidthStyle('checkbox')">
                  <el-checkbox
                    :indeterminate="isIndeterminate"
                    v-model="selectAll"
                    @change="handleSelectAll"
                  />
                </th>
                <th class="col-status-icon" :style="columnWidthStyle('statusIcon')"></th>
                <th
                  v-if="getColumnSetting('name').visible"
                  class="col-name"
                  :style="columnWidthStyle('name')"
                  @click="handleSort('name')"
                >
                  名称
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'name'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('name', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('name')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('size').visible"
                  class="col-size"
                  :style="columnWidthStyle('size')"
                  @click="handleSort('size')"
                >
                  大小
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'size'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('size', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('size')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('auxiliarySeedCount').visible"
                  class="col-auxiliary-seed-count"
                  :style="columnWidthStyle('auxiliarySeedCount')"
                >
                  辅种数量
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('auxiliarySeedCount', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('auxiliarySeedCount')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('progress').visible"
                  class="col-progress"
                  :style="columnWidthStyle('progress')"
                >
                  进度
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('progress', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('progress')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('status').visible"
                  class="col-status"
                  :style="columnWidthStyle('status')"
                  @click="handleSort('status')"
                >
                  状态
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'status'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('status', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('status')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('download').visible"
                  class="col-downspeed"
                  :style="columnWidthStyle('download')"
                >
                  ↓ 下载
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('download', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('download')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('upload').visible"
                  class="col-upspeed"
                  :style="columnWidthStyle('upload')"
                >
                  ↑ 上传
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('upload', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('upload')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('ratio').visible"
                  class="col-ratio"
                  :style="columnWidthStyle('ratio')"
                  @click="handleSort('ratio')"
                >
                  比率
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'ratio'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('ratio', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('ratio')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('downloader').visible"
                  class="col-downloader"
                  :style="columnWidthStyle('downloader')"
                >
                  下载器
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('downloader', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('downloader')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('category').visible"
                  class="col-category"
                  :style="columnWidthStyle('category')"
                >
                  分类/标签
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('category', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('category')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('savePath').visible"
                  class="col-save-path"
                  :style="columnWidthStyle('savePath')"
                >
                  保存路径
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('savePath', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('savePath')"
                    @click.stop
                  ></span>
                </th>
                <th
                  v-if="getColumnSetting('added').visible"
                  class="col-added"
                  :style="columnWidthStyle('added')"
                  @click="handleSort('added_date')"
                >
                  添加时间
                  <span class="sort-arrow" v-if="listQuery.sort_by === 'added_date'">
                    {{ listQuery.sort_order === 'asc' ? '▲' : '▼' }}
                  </span>
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('added', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('added')"
                    @click.stop
                  ></span>
                </th>
                <th class="col-actions" :style="columnWidthStyle('actions')">
                  操作
                  <span
                    class="column-resizer"
                    title="拖拽调整列宽，双击恢复默认"
                    @mousedown.stop.prevent="startColumnResize('actions', $event)"
                    @dblclick.stop.prevent="handleColumnResizeDblclick('actions')"
                    @click.stop
                  ></span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-if="virtualTopSpacerHeight > 0"
                class="virtual-spacer-row"
                aria-hidden="true"
              >
                <td
                  :colspan="visibleTableColumnCount"
                  :style="{height: `${virtualTopSpacerHeight}px`}"
                ></td>
              </tr>
              <tr
                v-for="(torrent, index) in virtualizedList"
                :key="getTorrentRowKey(torrent)"
                class="torrent-row"
                :class="{selected: isCurrentRow(torrent)}"
                :aria-rowindex="virtualWindow.startIndex + index + 2"
                @click="handleRowClick(torrent)"
              >
                <td class="col-checkbox">
                  <el-checkbox v-model="torrent.checked" @change="handleSelectionChange" @click.native.stop />
                </td>
                <td class="col-status-icon">
                  <div
                    class="status-icon-circle"
                    :class="torrent.status"
                    :title="showTrackerErrorTag(torrent) ? `${getStatusText(torrent.status)}（Tracker异常）` : getStatusText(torrent.status)"
                  >
                    <LucideIcon :name="getStatusIcon(torrent.status)" :size="14" />
                  </div>
                </td>
                <td v-if="getColumnSetting('name').visible" class="col-name">
                  <div class="torrent-name-cell">
                    <el-tooltip
                      :disabled="!getTorrentErrorReason(torrent)"
                      :content="getTorrentErrorReason(torrent)"
                      placement="top"
                    >
                      <span
                        class="torrent-name-text"
                        :title="getTorrentErrorReason(torrent) ? '' : torrent.name"
                      >{{ torrent.name }}</span>
                    </el-tooltip>
                  </div>
                </td>
                <td v-if="getColumnSetting('size').visible" class="col-size">{{ formatFileSize(torrent.size) }}</td>
                <td v-if="getColumnSetting('auxiliarySeedCount').visible" class="col-auxiliary-seed-count">
                  {{ torrent.auxiliarySeedCount || 1 }}
                </td>
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
                  <span
                    v-if="showTrackerErrorTag(torrent)"
                    class="tracker-error-tag"
                    :title="getTorrentErrorReason(torrent)"
                  >Tracker异常</span>
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
                <td
                  v-if="getColumnSetting('savePath').visible"
                  class="col-save-path"
                  :title="torrent.savePath || torrent.save_path || ''"
                >{{ torrent.savePath || torrent.save_path || '-' }}</td>
                <td v-if="getColumnSetting('added').visible" class="col-added">{{ formatDate(torrent.addedDate) }}</td>
                <td class="col-actions">
                  <div class="action-buttons-compact">
                    <button
                      class="action-btn-mini"
                      :class="torrent.status === 'paused' ? 'play' : 'pause'"
                      @click.stop="handleTogglePause(torrent)"
                      :title="torrent.status === 'paused' ? '开始' : '暂停'"
                    >
                      <LucideIcon :name="torrent.status === 'paused' ? 'play' : 'pause'" :size="14" />
                    </button>
                    <button
                      class="action-btn-mini recheck"
                      @click.stop="handleRecheck(torrent)"
                      title="重新检查"
                    >
                      <LucideIcon name="refresh-cw" :size="14" />
                    </button>
                    <button
                      class="action-btn-mini location"
                      @click.stop="handleSetLocation(torrent)"
                      title="修改保存路径"
                    >
                      <LucideIcon name="folder-open" :size="14" />
                    </button>
                    <el-dropdown
                      @command="(cmd) => handleDeleteByLevelCommand(cmd, torrent)"
                      trigger="click"
                      :hide-on-click="true"
                      :append-to-body="true"
                      @click.native.stop
                    >
                      <button class="action-btn-mini delete" title="删除">
                        <LucideIcon name="trash" :size="14" />
                      </button>
                      <el-dropdown-menu slot="dropdown">
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
              <tr
                v-if="virtualBottomSpacerHeight > 0"
                class="virtual-spacer-row"
                aria-hidden="true"
              >
                <td
                  :colspan="visibleTableColumnCount"
                  :style="{height: `${virtualBottomSpacerHeight}px`}"
                ></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 分页 -->
        <div class="table-pagination">
          <div class="pagination-info">
            <PageSizeCombobox
              ref="pageSizeCombobox"
              :append-to-body="true"
              v-model="pageSizeInput"
              :page-size="pageSize"
              :options="pageSizeOptions"
              :expanded="pageSizeDropdownExpanded"
              controls-id="traditional-page-size-options"
              @focus="handlePageSizeFocus"
              @blur="handlePageSizeBlur"
              @toggle="togglePageSizeDropdown"
              @apply="applyPageSizeSelection"
              @select="handlePageSizeSelect"
            />
            <span>共 <strong>{{ total }}</strong> 条，第 <strong>{{ currentPage }}</strong>/<strong>{{ totalPages }}</strong> 页</span>
          </div>
          <div class="pagination-controls">
            <el-button
              size="mini"
              :disabled="currentPage <= 1"
              @click="handlePageChange(currentPage - 1)"
            >
              <LucideIcon name="chevron-left" :size="14" />
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
              <LucideIcon name="chevron-right" :size="14" />
            </el-button>
          </div>
        </div>
        <!-- Tracker详情卡片；列表模式与传统模式共用完整弹框骨架 -->
        <TrackerDetailCard
          :visible="!!currentRow"
          layout="traditional"
          :torrent-name="(currentRow && currentRow.name) || ''"
          :active-tab.sync="activeDetailTab"
          :tabs="detailTabs"
          :tracker-info="(currentRow && (currentRow.tracker_info || currentRow.trackerInfo)) || []"
          :error-reason="getTorrentErrorReason(currentRow)"
          @close="closeDetailPanel"
          @reannounce="handleTrackerReannounce"
        />
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

    <!-- 快捷删除重复种子 -->
    <QuickDeleteDuplicatesDialog
      :visible.sync="showQuickDeleteDuplicatesDialog"
      @close="showQuickDeleteDuplicatesDialog = false"
      @deleted="handleQuickDeleteDeleted"
    />

    <!-- P1新增：高级搜索 -->
    <el-dialog
      :visible.sync="showAdvancedSearchDialog"
      width="80%"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      append-to-body
    >
      <template slot="title">
        <span class="dialog-title-with-icon">
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

    <!-- P2-2 列设置 -->
    <el-dialog
      :visible.sync="showColumnSettings"
      width="500px"
      append-to-body
    >
      <template slot="title">
        <span class="dialog-title-with-icon">
          <LucideIcon name="settings" :size="16" />
          <span>列设置</span>
        </span>
      </template>
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
        <el-button size="small" @click="handleResetColumnWidths">重置列宽</el-button>
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
import TrackerDetailCard from './components/TrackerDetailCard.vue'
import QuickDeleteDuplicatesDialog from '@/components/torrents/QuickDeleteDuplicatesDialog.vue'
import AdvancedSearchWorkspace from '@/components/torrents/AdvancedSearchWorkspace.vue'
import AdvancedMultiSelect from '@/components/torrents/AdvancedMultiSelect.vue'
import type { SelectOption } from '@/components/torrents/AdvancedMultiSelect.vue'
import FilterGroup from '@/components/torrents/FilterGroup.vue'
import PageSizeCombobox from '@/components/torrents/PageSizeCombobox.vue'
import TorrentBatchMixin from './mixins/torrentBatch'
import SpeedPollingMixin from './mixins/speedPolling'
import ColumnResizeMixin from './mixins/columnResize'
// 复用现有 API、工具函数、状态配置
import {
  getTorrentList,
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
  getTrackerDomains,
  type Torrent,
  type DownloaderSimple,
  type QueryTemplateConditions,
  type AdvancedSearchRequest
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
  buildAdvancedSearchRequest,
  getTorrentSpeed as getTorrentSpeedFromSnapshot,
  deriveVisibleTorrentList,
  buildSpeedSnapshot,
  needsActiveSnapshotRefresh,
  buildAdvancedSearchRequestFromTemplateGroups,
  getTorrentErrorReason as sharedErrorReason,
  showTrackerErrorTag as sharedShowTrackerErrorTag
} from './utils/torrentBatch'
import {
  buildTraditionalStatusFilterItems,
  getTraditionalStatusFilterValue,
  resolveTraditionalStatusFilterSelection
} from './utils/traditionalStatusFilter'
import type { StatusFilterItem } from './utils/traditionalStatusFilter'
import type { AdvancedSearchBuilderParams } from '@/components/torrents/advancedSearchState'
import { normalizeTraditionalPageSize } from './utils/traditionalPagination'
import {
  calculateTraditionalVirtualWindow,
  TRADITIONAL_VIRTUAL_OVERSCAN,
  TRADITIONAL_VIRTUAL_ROW_HEIGHT,
  TRADITIONAL_VIRTUAL_VIEWPORT_FALLBACK
} from './utils/traditionalVirtualList'
import type { TraditionalVirtualWindow } from './utils/traditionalVirtualList'
import {
  buildTorrentSpeedTargetIndex,
  getTraditionalTorrentRowKey,
  resolveTorrentSpeedTargets
} from './utils/traditionalTorrentIdentity'
import type {
  TorrentIdentityLike,
  TorrentSpeedTargetIndex
} from './utils/traditionalTorrentIdentity'

interface PageSizeSuggestion {
  value: string
}

interface TraditionalSpeedTarget extends TorrentIdentityLike {
  downloadSpeed?: number | null
  uploadSpeed?: number | null
  progress?: number | null
}

@Component({
  name: 'TraditionalView',
  components: {
    TorrentAddDialog,
    SetLocationDialog,
    BatchTransferDialog,
    TrackerOperationDialog,
    GlobalReplaceTrackerDialog,
    TrackerDetailCard,
    QuickDeleteDuplicatesDialog,
    FilterGroup,
    PageSizeCombobox,
    AdvancedSearchWorkspace,
    AdvancedMultiSelect
  }
})
export default class extends mixins(TorrentBatchMixin, SpeedPollingMixin, ColumnResizeMixin) {
  // ====== 状态管理 ======
  private viewModeModule = ViewModeModule

  // ====== 列宽拖拽（ColumnResizeMixin 契约字段；默认值与 .col-* SCSS 兜底一致） ======
  protected columnWidthStorageKey = 'btdeck_traditional_column_widths'
  protected defaultColumnWidths: Record<string, number> = {
    checkbox: 36,
    statusIcon: 32,
    name: 200,
    size: 80,
    auxiliarySeedCount: 90,
    progress: 130,
    status: 145,
    download: 90,
    upload: 90,
    ratio: 60,
    downloader: 100,
    category: 130,
    savePath: 180,
    added: 120,
    actions: 100
  }

  /** 表级宽度：固定列（复选框/状态图标）+ 可见列宽之和（严格列宽，含名称列） */
  get tableMinWidth(): number {
    const optionalKeys = [
      'name', 'size', 'auxiliarySeedCount', 'progress', 'status', 'download', 'upload',
      'ratio', 'downloader', 'category', 'savePath', 'added'
    ]
    const visibleKeys = [
      ...optionalKeys.filter(key => this.getColumnSetting(key).visible),
      'actions'
    ]
    return this.sumColumnWidths(['checkbox', 'statusIcon', ...visibleKeys])
  }

  // ====== 数据状态 ======
  private list: any[] = []
  private total = 0
  private listLoading = true
  private multipleSelection: any[] = []

  // 实时速度轮询
  // 实时速度轮询（speedTimer/speedPollingActive 由 SpeedPollingMixin 提供）
  private speedSnapshotReady = false
  private activeSpeedMap: Record<string, { downloadSpeed: number, uploadSpeed: number, progress: number }> = {}
  private torrentSpeedTargetIndex: TorrentSpeedTargetIndex<TraditionalSpeedTarget> = buildTorrentSpeedTargetIndex([])
  private activeListRetryPending = false
  private activeListRetryInFlight = false

  // 分类和标签数据
  private categoryList: string[] = []
  private tagList: string[] = []

  // 分页
  private currentPage = 1
  private pageSize = 20
  private pageSizeInput = '20'
  private pageSizeOptions = [20, 50, 100, 500, 1000]
  private pageSizeDropdownExpanded = false

  // 固定高度表格使用虚拟窗口，只渲染可视行和少量缓冲行
  private tableScrollTop = 0
  private pendingTableScrollTop = 0
  private tableViewportHeight = TRADITIONAL_VIRTUAL_VIEWPORT_FALLBACK
  private tableScrollFrame: number | null = null
  private tableResizeObserver: ResizeObserver | null = null
  private listRequestSequence = 0

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
  // 快捷删除重复种子
  private showQuickDeleteDuplicatesDialog = false

  // 详情面板
  private currentRow: any = null
  private activeDetailTab = 'tracker'
  private detailTabs = [
    { label: 'Tracker', value: 'tracker' },
    { label: '文件', value: 'files' },
    { label: 'Peers', value: 'peers' }
  ]

  // 重复任务查询使用独立分页，避免翻页后意外回到普通列表
  private showingDuplicates = false
  private showingSameContent = false
  private showingSingleErrors = false
  private activeAdvancedSearchRequest: AdvancedSearchRequest | null = null

  // 查询参数（复用现有结构）
  private listQuery: any = {
    skip: 0,
    limit: 20,
    name_like: '',
    downloader_id: [],
    status: [],
    tracker_domain: [],
    category_like: '',
    tags_like: '',
    showActiveOnly: false, // P0#1：仅显示活动种子（UI 开关，映射为后端 active_only 过滤，total 口径一致）
    sort_by: 'added_date', // P1前置：统一蛇形，后端用 getattr(TorrentInfo, sort_by) 匹配ORM字段名
    sort_order: 'desc'
  }

  // 下载器列表
  private downloaderList: DownloaderSimple[] = []
  private trackerDomainList: string[] = []

  // P2-2 列设置（3列固定：checkbox/statusIcon/actions 不在此数组；11列可隐藏）
  private showColumnSettings = false
  private columnSettings = [
    { key: 'name', label: '名称', visible: true },
    { key: 'size', label: '大小', visible: true },
    { key: 'auxiliarySeedCount', label: '辅种数量', visible: true },
    { key: 'progress', label: '进度', visible: true },
    { key: 'status', label: '状态', visible: true },
    { key: 'download', label: '下载速度', visible: true },
    { key: 'upload', label: '上传速度', visible: true },
    { key: 'ratio', label: '比率', visible: true },
    { key: 'downloader', label: '下载器', visible: true },
    { key: 'category', label: '分类/标签', visible: true },
    { key: 'savePath', label: '保存路径', visible: true },
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
    // 模板通过 sortedList 引用，这里做透传。
    // 第4参数固定 false：活动种子过滤已下沉到后端 active_only，此处仅保留"活跃优先排序"，
    // 关闭客户端二次过滤，避免与后端过滤叠加。
    return deriveVisibleTorrentList(
      this.list,
      this.activeSpeedMap,
      this.speedSnapshotReady,
      false
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
  get activeStatusFilterValue(): string {
    return getTraditionalStatusFilterValue(
      this.listQuery.status,
      this.listQuery.showActiveOnly
    )
  }

  get virtualWindow(): TraditionalVirtualWindow {
    return calculateTraditionalVirtualWindow(
      this.sortedList.length,
      this.tableScrollTop,
      this.tableViewportHeight,
      TRADITIONAL_VIRTUAL_ROW_HEIGHT,
      TRADITIONAL_VIRTUAL_OVERSCAN
    )
  }

  get virtualizedList() {
    return this.sortedList.slice(
      this.virtualWindow.startIndex,
      this.virtualWindow.endIndex
    )
  }

  get virtualTopSpacerHeight(): number {
    return this.virtualWindow.topSpacerHeight
  }

  get virtualBottomSpacerHeight(): number {
    return this.virtualWindow.bottomSpacerHeight
  }

  get visibleTableColumnCount(): number {
    return 3 + this.columnSettings.filter(column => column.visible).length
  }

  get statusFilterItems(): StatusFilterItem[] {
    return buildTraditionalStatusFilterItems(
      STATUS_OPTIONS.map(opt => ({
        icon: getStatusIcon(opt.value),
        label: opt.label,
        value: opt.value
      }))
    )
  }

  get downloaderFilterItems(): StatusFilterItem[] {
    return [
      { icon: 'server', label: '全部', value: '' },
      ...this.downloaderList.map(d => ({
        icon: 'circle',
        label: d.nickname,
        value: d.downloader_id
      }))
    ]
  }

  get trackerDomainOptions(): SelectOption[] {
    return this.trackerDomainList.map(domain => ({
      value: domain,
      label: domain
    }))
  }

  get categoryFilterItems(): StatusFilterItem[] {
    const items = [
      { icon: 'folder', label: '全部', value: '' },
      ...this.categoryList.map(name => ({
        icon: 'folder-open',
        label: name,
        value: name
      }))
    ]
    return items
  }

  get tagFilterItems(): StatusFilterItem[] {
    const items = [
      { icon: 'tag', label: '全部', value: '' },
      ...this.tagList.map(name => ({
        icon: 'tag',
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
    await this.fetchTrackerDomains()
    await this.fetchCategoryAndTags()
    await this.getList()
    this.startSpeedPolling()

    // P1#9：处理从查询模板管理页跳转来的应用请求（traditional 模式下 index.vue 未挂载，
    // 路由参数需在本视图处理）
    await this.handleApplyTemplateFromRoute()
  }

  public mounted() {
    this.$nextTick(() => {
      this.updateTableViewportHeight()
      const tableContainer = this.$refs.tableContainer as HTMLElement | undefined
      if (tableContainer && typeof ResizeObserver !== 'undefined') {
        this.tableResizeObserver = new ResizeObserver(() => {
          this.updateTableViewportHeight()
        })
        this.tableResizeObserver.observe(tableContainer)
      }
    })
  }

  public beforeDestroy() {
    this.stopSpeedPolling()
    if (this.tableScrollFrame !== null) {
      window.cancelAnimationFrame(this.tableScrollFrame)
      this.tableScrollFrame = null
    }
    if (this.tableResizeObserver) {
      this.tableResizeObserver.disconnect()
      this.tableResizeObserver = null
    }
    // P2-I：调 mixin 的 loading 清理，防 4 等级删除轮询期间销毁残留遮罩
    (this as any).closeDeleteLoading && (this as any).closeDeleteLoading()
  }

  // ====== 数据获取 ======
  private async getList(activeSnapshotRetry = false) {
    if (this.showingDuplicates) {
      await this.fetchDuplicateTorrents(false, activeSnapshotRetry)
      return
    }

    this.activeAdvancedSearchRequest = null
    const requestSequence = this.prepareForListReplacement()
    this.listLoading = true
    try {
      const params = { ...this.listQuery }
      params.skip = (this.currentPage - 1) * this.pageSize
      params.limit = this.pageSize

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

      if (Array.isArray(params.tracker_domain) && params.tracker_domain.length > 0) {
        params.tracker_domain = params.tracker_domain.join(',')
      } else {
        delete params.tracker_domain
      }

      // 清理空值
      Object.keys(params).forEach(key => {
        if (params[key] === '' || params[key] === null || params[key] === undefined) {
          delete params[key]
        }
      })

      const response = await getTorrentList(params)
      if (requestSequence !== this.listRequestSequence) return
      if (needsActiveSnapshotRefresh(response, showActive)) {
        // 后端尚无完整活动快照时保留当前列表。速度轮询拿到 code=200 的完整快照后，
        // loadActiveSpeed 会触发一次受控重试。
        this.activeListRetryPending = true
        if (!activeSnapshotRetry) {
          await this.loadActiveSpeed()
        }
        return
      }
      this.activeListRetryPending = false

      const { list, total } = normalizePaginatedResponse<any>(response)

      // 规范化并提供默认 checked
      const normalizedList = list.map(normalizeTorrent).map(item => ({
        ...item,
        checked: false
      }))

      // "仅显示活动种子"过滤已下沉到后端（active_only），此处直接使用后端返回的 list 与 total，
      // 二者口径天然一致。sortedList 仅做"活动优先"排序，不再做客户端过滤。
      this.replaceTorrentList(normalizedList, total)
    } catch (error) {
      if (requestSequence !== this.listRequestSequence) return
      console.error('获取种子列表失败:', error)
      this.$message.error('获取种子列表失败')
    } finally {
      if (requestSequence === this.listRequestSequence) {
        this.listLoading = false
      }
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

  private async fetchTrackerDomains() {
    try {
      const response = await getTrackerDomains()
      if (response.code === '200' && Array.isArray(response.data)) {
        this.trackerDomainList = response.data
      }
    } catch (error) {
      console.error('获取 Tracker 主域名失败:', error)
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
  // startSpeedPolling / stopSpeedPolling 由 SpeedPollingMixin 提供（含后台标签页暂停/恢复）

  /**
   * 加载活跃种子实时速度和进度（对齐列表模式 index.vue:2177-2214）
   * 修复 Bug#3：原用原生 fetch + localStorage.getItem('token')，
   * token 实际存在 Cookie（cookies.ts:10），导致恒为 null → 401 → 速度永远为 0。
   * 改用封装的 getActiveTorrents()，复用统一 axios 拦截器（token 注入、401 跳登录）。
   */
  protected async loadActiveSpeed(): Promise<boolean> {
    const requestId = Date.now()
    try {
      const res = await getActiveTorrents()
      const snapshot = buildSpeedSnapshot(res)
      if (snapshot.ready && snapshot.activeSpeedMap && snapshot.torrentSpeedMap) {
        // 列表替换时已建立 downloader_id + hash 索引；轮询只按键命中活动任务，
        // 避免 10 万行场景为每条更新重复执行 Array.find。
        snapshot.updates.forEach(u => {
          const targets = resolveTorrentSpeedTargets(this.torrentSpeedTargetIndex, u)
          targets.forEach(torrent => {
            torrent.downloadSpeed = u.downloadSpeed
            torrent.uploadSpeed = u.uploadSpeed
            torrent.progress = u.progress
          })
        })
        this.activeSpeedMap = snapshot.torrentSpeedMap
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

  // ====== 事件处理 ======
  private handleFilter() {
    this.currentPage = 1
    this.resetTableViewport()
    this.getList()
  }

  private handleSort(field: string) {
    if (this.listQuery.sort_by === field) {
      this.listQuery.sort_order = this.listQuery.sort_order === 'asc' ? 'desc' : 'asc'
    } else {
      this.listQuery.sort_by = field
      this.listQuery.sort_order = 'desc'
    }
    this.resetTableViewport()
    this.getList()
  }

  private handlePageChange(page: number) {
    this.currentPage = page
    this.resetTableViewport()
    if (this.activeAdvancedSearchRequest) {
      this.fetchAdvancedSearchPage()
    } else if (this.showingDuplicates) {
      this.fetchDuplicateTorrents()
    } else {
      this.getList()
    }
  }

  private queryPageSizeSuggestions(
    _queryString: string,
    callback: (suggestions: PageSizeSuggestion[]) => void
  ) {
    const suggestions = this.pageSizeOptions
      .map(size => ({ value: String(size) }))
    callback(suggestions)
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

  private handlePageSizeChange() {
    this.currentPage = 1
    this.resetTableViewport()
    if (this.activeAdvancedSearchRequest) {
      this.fetchAdvancedSearchPage()
    } else if (this.showingDuplicates) {
      this.fetchDuplicateTorrents()
    } else {
      this.getList()
    }
  }

  private handleTableScroll(event: Event) {
    const target = event.currentTarget as HTMLElement
    this.pendingTableScrollTop = target.scrollTop
    if (this.tableScrollFrame !== null) return

    this.tableScrollFrame = window.requestAnimationFrame(() => {
      this.tableScrollTop = this.pendingTableScrollTop
      this.tableScrollFrame = null
    })
  }

  private updateTableViewportHeight() {
    const tableContainer = this.$refs.tableContainer as HTMLElement | undefined
    if (tableContainer && tableContainer.clientHeight > 0) {
      this.tableViewportHeight = tableContainer.clientHeight
    }
  }

  private resetTableViewport() {
    this.tableScrollTop = 0
    this.pendingTableScrollTop = 0
    if (this.tableScrollFrame !== null) {
      window.cancelAnimationFrame(this.tableScrollFrame)
      this.tableScrollFrame = null
    }
    this.$nextTick(() => {
      const tableContainer = this.$refs.tableContainer as HTMLElement | undefined
      if (tableContainer) {
        tableContainer.scrollTop = 0
      }
      this.updateTableViewportHeight()
    })
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

  private getTorrentRowKey(torrent: TorrentIdentityLike | null | undefined): string {
    return getTraditionalTorrentRowKey(torrent)
  }

  private isCurrentRow(torrent: TorrentIdentityLike | null | undefined): boolean {
    return Boolean(
      this.currentRow &&
      this.getTorrentRowKey(this.currentRow) === this.getTorrentRowKey(torrent)
    )
  }

  private handleRowClick(torrent: any) {
    if (this.isCurrentRow(torrent)) {
      this.currentRow = null
      return
    }
    this.currentRow = torrent
    this.activeDetailTab = 'tracker'
  }

  private closeDetailPanel() {
    this.currentRow = null
  }

  private getTorrentErrorReason(torrent: Torrent | null | undefined): string {
    return sharedErrorReason(torrent)
  }

  private showTrackerErrorTag(torrent: Torrent | null | undefined): boolean {
    return sharedShowTrackerErrorTag(torrent)
  }

  private prepareForListReplacement(): number {
    // 切页、筛选或切换数据源后旧行已不属于当前列表，立即关闭以阻止误操作。
    this.closeDetailPanel()
    this.listRequestSequence += 1
    return this.listRequestSequence
  }

  private replaceTorrentList(nextList: TraditionalSpeedTarget[], total: number) {
    this.closeDetailPanel()
    this.list = nextList
    this.total = total
    this.torrentSpeedTargetIndex = buildTorrentSpeedTargetIndex(nextList)
    // 新数据全部 checked:false，需同步清空批量选择，避免旧页任务被误操作。
    this.resetBatchSelection()
  }

  private toggleFilterPanel() {
    this.viewModeModule.toggleFilterPanel()
  }

  private switchViewMode(mode: ViewModeType) {
    this.viewModeModule.setViewMode(mode)
  }

  // 过滤器选择
  private handleStatusFilter(value: string) {
    const selection = resolveTraditionalStatusFilterSelection(value)
    this.listQuery.showActiveOnly = selection.showActiveOnly
    this.listQuery.status = selection.status
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
      if (this.isCurrentRow(torrent)) {
        this.currentRow = null
      }
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('删除种子失败:', error)
      this.$message.error(errorMessage || '删除种子失败')
    }
  }

  private async handleAdd() {
    // TorrentAddDialog 内部已通过 addTorrentsBatch 完成种子添加，
    // 并在有成功项时才 emit('confirm', this.form)。本回调只需关闭对话框 + 刷新列表，
    // 不应再调用 addTorrent —— this.form 不含 torrent_file（File 对象），
    // 重复调用会触发 422（"Expected UploadFile, received: <class 'str'>"）。
    // 与 index.vue:1718 handleAdd 行为对齐。
    this.showAddDialog = false
    this.getList()
  }

  // ====== P0#2 手动刷新（对齐列表模式，含静态+速度双刷新） ======
  private handleManualRefresh() {
    if (this.activeAdvancedSearchRequest) {
      this.fetchAdvancedSearchPage()
    } else if (this.showingDuplicates) {
      this.fetchDuplicateTorrents()
    } else {
      this.getList()
    }
    this.loadActiveSpeed()
  }

  // ====== 快捷操作 ======

  /**
   * 快捷操作下拉菜单命令分发
   */
  private async handleQuickActionCommand(command: string) {
    if (command === 'inspect-same-content') {
      this.showingDuplicates = false
      this.showingSingleErrors = false
      this.showingSameContent = true
      this.activeAdvancedSearchRequest = null
      this.currentPage = 1
      this.listQuery.skip = 0
      this.resetTableViewport()
      await this.getList()
      this.$message.success(`排查完成，共找到 ${this.total} 条同内容种子`)
    } else if (command === 'inspect-single-errors') {
      this.showingDuplicates = false
      this.showingSameContent = false
      this.showingSingleErrors = true
      this.activeAdvancedSearchRequest = null
      this.currentPage = 1
      this.listQuery.skip = 0
      this.resetTableViewport()
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
    this.resetTableViewport()
    await this.getList()
  }

  private async exitSingleErrorInspection() {
    this.showingSingleErrors = false
    this.currentPage = 1
    this.listQuery.skip = 0
    this.resetTableViewport()
    await this.getList()
  }

  /**
   * 快捷删除重复种子完成后刷新列表
   */
  private handleQuickDeleteDeleted() {
    this.handleManualRefresh()
  }

  /** 单条 Tracker 汇报（在详情面板 Tracker tab 内触发） */
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

  /**
   * P1#8 执行高级搜索（解析逻辑委托 buildAdvancedSearchRequest 纯函数，防回归 P1-F）
   * 视图只保留「调 API + 设 list/total + 提示」
   */
  private async performAdvancedSearch(searchParams: AdvancedSearchBuilderParams) {
    this.advancedSearchSearching = true
    try {
      const { request, error } = buildAdvancedSearchRequest(
        searchParams,
        this.listQuery.sort_by || 'added_date',
        this.pageSize
      )
      if (error || !request) {
        this.$message.error(error || '搜索条件格式错误')
        return
      }

      this.showingDuplicates = false
      this.showingSameContent = false
      this.showingSingleErrors = false
      this.currentPage = 1
      this.listQuery.skip = 0
      this.activeAdvancedSearchRequest = request as AdvancedSearchRequest
      this.resetTableViewport()
      await this.fetchAdvancedSearchPage('search')
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('高级搜索失败:', error)
      this.$message.error(errorMessage || '高级搜索失败，请检查搜索条件')
    } finally {
      this.advancedSearchSearching = false
    }
  }

  /** 当前高级搜索的统一分页入口，分页大小始终取组合框的实时值。 */
  private async fetchAdvancedSearchPage(successContext?: 'search' | 'template'): Promise<boolean> {
    const baseRequest = this.activeAdvancedSearchRequest
    if (!baseRequest) return false

    const requestSequence = this.prepareForListReplacement()
    const request: AdvancedSearchRequest = {
      ...baseRequest,
      page: this.currentPage,
      limit: this.pageSize
    }
    this.listLoading = true
    try {
      const response = await advancedSearch(request)
      if (
        requestSequence !== this.listRequestSequence ||
        baseRequest !== this.activeAdvancedSearchRequest
      ) return false

      if (response.code === '200' && response.data) {
        const nextList = (response.data.list || [])
          .map(normalizeTorrent)
          .map(item => ({ ...item, checked: false }))
        this.replaceTorrentList(nextList, response.data.total || 0)
        if (successContext === 'search') {
          this.$message.success(`高级搜索完成，找到 ${this.total} 条结果`)
        } else if (successContext === 'template') {
          this.$message.success('已应用高级搜索模板')
        }
        return true
      }
      this.$message.error(response.msg || '搜索失败')
      return false
    } catch (error) {
      if (requestSequence !== this.listRequestSequence) return false
      const errorMessage = extractErrorMessage(error)
      console.error('高级搜索失败:', error)
      this.$message.error(errorMessage || '搜索失败')
      return false
    } finally {
      if (requestSequence === this.listRequestSequence) {
        this.listLoading = false
      }
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
        this.showingDuplicates = false
        this.showingSameContent = false
        this.showingSingleErrors = false
        const saved = conditions.listQuery
        this.listQuery = {
          skip: 0,
          limit: this.listQuery.limit,
          name_like: saved.name_like ?? '',
          downloader_id: saved.downloader_id ? [...saved.downloader_id] : [],
          status: saved.status ? [...saved.status] : [],
          tracker_domain: saved.tracker_domain ? [...saved.tracker_domain] : [],
          category_like: saved.category_like ?? '',
          tags_like: saved.tags_like ?? '',
          showActiveOnly: saved.showActiveOnly ?? false,
          sort_by: saved.sort_by ?? 'added_date',
          sort_order: saved.sort_order ?? 'desc'
        }
        this.currentPage = 1
        this.resetTableViewport()
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
          this.pageSize
        )
        if (error || !request) {
          this.$message.error(error || '搜索条件格式错误')
          return false
        }
        this.showingDuplicates = false
        this.showingSameContent = false
        this.showingSingleErrors = false
        this.currentPage = 1
        this.listQuery.skip = 0
        this.activeAdvancedSearchRequest = request as AdvancedSearchRequest
        this.resetTableViewport()
        return await this.fetchAdvancedSearchPage('template')
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
    if (applied) {
      // 清除 query 参数，避免刷新重复应用
      this.$router.replace({ query: {} })
    }
  }

  // ====== P1#10 查找重复任务 ======
  private async handleDuplicateSearchToggle(enabled: boolean) {
    this.showingDuplicates = enabled
    if (enabled) {
      this.showingSameContent = false
      this.showingSingleErrors = false
    }
    this.activeAdvancedSearchRequest = null
    this.currentPage = 1
    this.listQuery.skip = 0
    this.resetTableViewport()
    if (!enabled) {
      await this.getList()
      return
    }

    await this.fetchDuplicateTorrents(true)
  }

  private async fetchDuplicateTorrents(showResultMessage = false, activeSnapshotRetry = false) {
    this.activeAdvancedSearchRequest = null
    const requestSequence = this.prepareForListReplacement()
    this.listLoading = true
    try {
      const downloaderId = this.listQuery.downloader_id.length > 0
        ? this.listQuery.downloader_id.join(',')
        : undefined
      const status = this.listQuery.status.length > 0
        ? this.listQuery.status.join(',')
        : undefined
      const response = await getDuplicateTorrents({
        name_like: this.listQuery.name_like || undefined,
        downloader_id: downloaderId,
        status,
        category_like: this.listQuery.category_like || undefined,
        tags_like: this.listQuery.tags_like || undefined,
        page: this.currentPage,
        pageSize: this.pageSize,
        sort_by: this.listQuery.sort_by,
        sort_order: this.listQuery.sort_order,
        active_only: this.listQuery.showActiveOnly || undefined
      })
      if (requestSequence !== this.listRequestSequence) return
      if (needsActiveSnapshotRefresh(response, this.listQuery.showActiveOnly)) {
        this.activeListRetryPending = true
        if (!activeSnapshotRetry) {
          await this.loadActiveSpeed()
        }
        return
      }
      this.activeListRetryPending = false
      const { list, total } = normalizePaginatedResponse<any>(response)
      const nextList = list.map(normalizeTorrent).map(item => ({ ...item, checked: false }))
      this.replaceTorrentList(nextList, total)
      if (showResultMessage) {
        this.$message.success(`查找完成，共找到 ${total} 条重复种子`)
      }
    } catch (error) {
      if (requestSequence !== this.listRequestSequence) return
      const errorMessage = extractErrorMessage(error)
      console.error('查找重复失败:', error)
      this.$message.error(errorMessage || '查找重复失败')
    } finally {
      if (requestSequence === this.listRequestSequence) {
        this.listLoading = false
      }
    }
  }

  // ====== P2-2 列设置 ======
  private getColumnSetting(key: string) {
    return this.columnSettings.find(col => col.key === key) || { visible: true }
  }

  private resetColumnSettings() {
    this.columnSettings.forEach(column => { column.visible = true })
  }

  /** 列设置菜单：全部列宽恢复默认（ColumnResizeMixin 提供 resetColumnWidths） */
  private handleResetColumnWidths() {
    this.resetColumnWidths()
    this.$message.success('列宽已重置为默认')
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

.torrent-error-alert {
  margin-bottom: 10px;
}

.same-content-list-alert {
  margin: 0 10px 10px;
}

.single-error-list-alert {
  margin: 0 10px 10px;
}

// 对话框标题：图标 + 文本对齐（el-dialog #title slot）
.dialog-title-with-icon {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--color-text-primary);
  font-size: 15px;
  font-weight: 600;
  line-height: 1.2;
}

.traditional-page {
  // 与列表模式一致锁定到当前视口，避免表格高度随种子数量变化
  height: calc(100vh - 84px);
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

.filter-panel,
.filter-panel-content {
  min-height: 0;
}

.filter-panel-content {
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.tracker-domain-filter {
  padding: 5px 6px 8px;
  margin-bottom: 2px;
}

.filter-group-title {
  padding: 0 6px 5px;
  color: var(--color-text-tertiary);
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.3px;
  text-transform: uppercase;
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

.manual-refresh-btn {
  padding: 0 6px;
}

.duplicate-search-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 8px;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: var(--font-weight-medium, 500);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
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
  --trad-pagination-height: 38px;
  --trad-row-height: 32px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.table-container {
  // height: 0 配合 flex 固定为剩余可视高度，内容只在容器内部滚动
  flex: 1 1 0;
  height: 0;
  min-height: 0;
  overflow: auto;
  position: relative;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;

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

.traditional-table {
  // 兜底值：运行时由 tableMinWidth computed 内联绑定 width/minWidth（可见列宽
  // 之和，严格列宽含名称列），列宽拖宽后横向滚动条自适应；此静态值仅在首帧/无脚本回退时生效。
  min-width: 1435px;

  tbody .torrent-row {
    height: var(--trad-row-height);

    > td {
      height: var(--trad-row-height);
      box-sizing: border-box;
    }
  }

  tbody .virtual-spacer-row {
    border: 0;
    cursor: default;
    pointer-events: none;
    transition: none;

    &:hover {
      background: transparent;
    }

    > td {
      padding: 0;
      border: 0;
      line-height: 0;
    }
  }
}

// 名称单元格文字随列宽省略（td 的 overflow 兜底只裁剪不产生"..."，需在内容块上生效）
.torrent-name-cell {
  overflow: hidden;
  text-overflow: ellipsis;
}

// 表格列宽（兜底；运行时由 columnWidthStyle 内联宽覆盖，qBittorrent 风格严格列宽）
.col-checkbox { width: 36px; text-align: center !important; }
.col-status-icon { width: 32px; text-align: center !important; }
.col-name { width: 200px; }
.col-size { width: 80px; }
.col-progress { width: 130px; }
.col-status { width: 145px; }
.col-downspeed { width: 90px; }
.col-upspeed { width: 90px; }
.col-ratio { width: 60px; }
.col-downloader { width: 100px; }
.col-category { width: 130px; }
.col-save-path { width: 180px; }
.col-added { width: 120px; }
.col-actions { width: 100px; }

.table-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--trad-pagination-height);
  min-height: var(--trad-pagination-height);
  box-sizing: border-box;
  padding: 4px 10px;
  background: var(--color-bg-primary);
  border-top: 1px solid var(--color-border-primary);
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
  position: relative;
  z-index: 30;

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
