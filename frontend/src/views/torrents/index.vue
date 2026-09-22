<template>
  <div class="torrent-management-page" :class="`theme-${currentTheme}`">
    <!-- 搜索筛选区 -->
    <section class="filter-container">
      <div class="simple-search">
        <el-input
          v-model="listQuery.name_like"
          :placeholder="$t('torrent.list.searchPlaceholder')"
          style="width: 200px;"
          class="search-input"
          @input="debouncedSearch"
          @keyup.enter.native="handleFilter"
        />
        <AdvancedMultiSelect
          v-model="listQuery.downloader_id"
          :placeholder="$t('torrent.list.downloaderPlaceholder')"
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
          :placeholder="$t('torrent.list.statusPlaceholder')"
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
          :placeholder="$t('torrent.list.trackerPlaceholder')"
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
          {{ $t('torrent.list.activeOnly') }}
        </el-checkbox>
        <el-button class="search-btn" @click="handleFilter">
          {{ $t('torrent.list.search') }}
        </el-button>
        <el-button class="advanced-search-btn" @click="openAdvancedSearch">
          {{ $t('torrent.list.advancedSearch') }}
        </el-button>
        <label
          class="duplicate-search-switch"
          :class="{'is-active': showingDuplicates}"
        >
          <el-switch
            v-model="showingDuplicates"
            active-color="var(--color-success, #10b981)"
            inactive-color="var(--color-border-secondary, #c0c4cc)"
            :aria-label="$t('torrent.list.duplicateSwitch')"
            @change="handleDuplicateSearchToggle"
          />
          <span>{{ $t('torrent.list.duplicateSwitch') }}</span>
        </label>
        <el-button class="clear-btn" @click="handleClearFilter">
          {{ $t('torrent.list.clear') }}
        </el-button>
        <el-button class="refresh-btn" @click="handleManualRefresh" :loading="listLoading">
          {{ $t('torrent.list.refresh') }}
        </el-button>
      </div>
    </section>

    <el-alert
      v-if="showingSameContent"
      class="same-content-list-alert"
      :title="$t('torrent.list.alert.sameContent')"
      type="warning"
      :closable="false"
      show-icon
    >
      <el-button type="text" @click="exitSameContentInspection">
        {{ $t('torrent.list.alert.exit') }}
      </el-button>
    </el-alert>
    <el-alert
      v-if="showingSingleErrors"
      class="single-error-list-alert"
      :title="$t('torrent.list.alert.singleError')"
      type="error"
      :closable="false"
      show-icon
    >
      <el-button type="text" @click="exitSingleErrorInspection">
        {{ $t('torrent.list.alert.exit') }}
      </el-button>
    </el-alert>

    <!-- 批量操作工具栏 -->
    <section class="batch-operations">
      <!-- 批量开始 -->
      <batch-button
        type="success"
        lucide-icon="play"
        :tooltip="$t('torrent.list.toolbar.start')"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchStart"
      />

      <!-- 批量暂停 -->
      <batch-button
        type="warning"
        lucide-icon="pause"
        :tooltip="$t('torrent.list.toolbar.pause')"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchPause"
      />

      <!-- 批量删除（带下拉菜单） -->
      <el-dropdown
        @command="handleBatchDeleteByLevelCommand"
        trigger="click"
        :hide-on-click="true"
        :append-to-body="true"
        :disabled="multipleSelection.length === 0"
      >
        <batch-button
          type="danger"
          lucide-icon="trash"
          :tooltip="$t('torrent.list.toolbar.delete')"
          :disabled="multipleSelection.length === 0"
        />
        <el-dropdown-menu slot="dropdown" class="delete-level-menu">
          <el-dropdown-item command="4">
            <LucideIcon class="menu-icon" name="tag" :size="14" />{{ $t('torrent.list.deleteMenu.level4') }}
          </el-dropdown-item>
          <el-dropdown-item v-if="level3Available" command="3">
            <LucideIcon class="menu-icon" name="trash-2" :size="14" />{{ $t('torrent.list.deleteMenu.level3') }}
          </el-dropdown-item>
          <el-dropdown-item command="2">
            <LucideIcon class="menu-icon" name="trash" :size="14" />{{ $t('torrent.list.deleteMenu.level2') }}
          </el-dropdown-item>
          <el-dropdown-item command="1" divided>
            <LucideIcon class="menu-icon danger" name="alert-triangle" :size="14" />{{ $t('torrent.list.deleteMenu.level1') }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>

      <!-- 批量重检 -->
      <batch-button
        type="info"
        lucide-icon="refresh-cw"
        :tooltip="$t('torrent.list.toolbar.recheck')"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchRecheck"
      />

      <!-- Tracker操作 -->
      <batch-button
        type="default"
        lucide-icon="link"
        :tooltip="$t('torrent.list.toolbar.trackerOps')"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchTracker"
      />

      <!-- Tracker汇报 -->
      <batch-button
        type="info"
        lucide-icon="forward"
        :tooltip="$t('torrent.list.toolbar.reannounce')"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchReannounce"
      />

      <!-- 全局替换 -->
      <batch-button
        type="default"
        lucide-icon="settings"
        :tooltip="$t('torrent.list.toolbar.globalReplace')"
        @click="showGlobalReplaceDialog = true"
      />

      <!-- 批量转移 -->
      <batch-button
        v-if="seedTransferAvailable"
        type="info"
        lucide-icon="route"
        :tooltip="$t('torrent.list.toolbar.transfer')"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchTransfer"
      />

      <!-- 批量修改路径 -->
      <batch-button
        type="primary"
        lucide-icon="folder-open"
        :tooltip="$t('torrent.list.toolbar.setLocation')"
        :disabled="multipleSelection.length === 0"
        @click="handleBatchSetLocation"
      />

      <!-- 快捷操作（下拉） -->
      <el-dropdown trigger="click" @command="handleQuickActionCommand">
        <batch-button
          type="default"
          lucide-icon="zap"
          :tooltip="$t('torrent.list.toolbar.quickActions')"
        />
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="inspect-same-content">
            <i class="el-icon-search"></i> {{ $t('torrent.list.quickMenu.sameContent') }}
          </el-dropdown-item>
          <el-dropdown-item command="inspect-single-errors">
            <i class="el-icon-warning-outline"></i> {{ $t('torrent.list.quickMenu.singleError') }}
          </el-dropdown-item>
          <el-dropdown-item command="delete-duplicates" divided>
            <i class="el-icon-delete"></i> {{ $t('torrent.list.quickMenu.deleteDuplicates') }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>

      <div style="flex: 1;"></div>

      <!-- 添加种子 -->
      <batch-button
        type="primary"
        lucide-icon="plus"
        :tooltip="$t('torrent.list.toolbar.add')"
        @click="showAddDialog = true"
      />

      <!-- 列设置 -->
      <batch-button
        type="default"
        lucide-icon="settings"
        :tooltip="$t('torrent.list.toolbar.columns')"
        @click="showColumnSettings = true"
      />

      <!-- 视图切换 -->
      <div class="view-switcher">
        <el-button
          type="text"
          size="small"
          :class="{active: viewModeModule.currentMode === 'list'}"
          @click="switchViewMode('list')"
          :title="$t('torrent.list.view.list')"
        >
          <i class="el-icon-s-grid"></i>
        </el-button>
        <el-button
          type="text"
          size="small"
          :class="{active: viewModeModule.currentMode === 'traditional'}"
          @click="switchViewMode('traditional')"
          :title="$t('torrent.list.view.traditional')"
        >
          <i class="el-icon-menu"></i>
        </el-button>
      </div>
    </section>

    <!-- 种子列表表格 -->
    <section
      class="torrents-table-wrapper"
      v-loading.fullscreen.lock="listLoading"
      :element-loading-text="$t('torrent.list.loading')"
      element-loading-spinner="el-icon-loading"
      element-loading-background="rgba(0, 0, 0, 0.2)"
    >
      <table
        class="torrent-table"
        :style="{width: tableMinWidth + 'px', minWidth: tableMinWidth + 'px'}"
      >
        <thead>
          <tr>
            <th :style="columnWidthStyle('checkbox')">
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
              :style="columnWidthStyle('name')"
              data-sort-field="name"
              tabindex="0"
              :aria-sort="getSortAriaValue('name')"
              :title="$t('torrent.list.sortTitle.name')"
              @click="handleSort('name')"
              @keydown.enter.prevent="handleSort('name')"
              @keydown.space.prevent="handleSort('name')"
            >
              {{ $t('torrent.list.column.name') }}
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('name')"
                :size="13"
                :stroke-width="2"
              />
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('name', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('name')"
                @click.stop
              ></span>
            </th>
            <th v-if="getColumnSetting('downloadSpeed').visible" :style="columnWidthStyle('downloadSpeed')">
              {{ $t('torrent.list.column.downloadSpeed') }}
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('downloadSpeed', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('downloadSpeed')"
                @click.stop
              ></span>
            </th>
            <th v-if="getColumnSetting('uploadSpeed').visible" :style="columnWidthStyle('uploadSpeed')">
              {{ $t('torrent.list.column.uploadSpeed') }}
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('uploadSpeed', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('uploadSpeed')"
                @click.stop
              ></span>
            </th>
            <th
              v-if="getColumnSetting('size').visible"
              class="sortable-column"
              :class="{sorted: listQuery.sort_by === 'size'}"
              data-sort-field="size"
              :style="columnWidthStyle('size')"
              tabindex="0"
              :aria-sort="getSortAriaValue('size')"
              :title="$t('torrent.list.sortTitle.size')"
              @click="handleSort('size')"
              @keydown.enter.prevent="handleSort('size')"
              @keydown.space.prevent="handleSort('size')"
            >
              {{ $t('torrent.list.column.size') }}
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('size')"
                :size="13"
                :stroke-width="2"
              />
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('size', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('size')"
                @click.stop
              ></span>
            </th>
            <th v-if="getColumnSetting('auxiliarySeedCount').visible" :style="columnWidthStyle('auxiliarySeedCount')">
              {{ $t('torrent.list.column.auxiliarySeedCount') }}
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('auxiliarySeedCount', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('auxiliarySeedCount')"
                @click.stop
              ></span>
            </th>
            <th v-if="getColumnSetting('progress').visible" :style="columnWidthStyle('progress')">
              {{ $t('torrent.list.column.progress') }}
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('progress', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('progress')"
                @click.stop
              ></span>
            </th>
            <th
              v-if="getColumnSetting('status').visible"
              class="sortable-column"
              :class="{sorted: listQuery.sort_by === 'status'}"
              data-sort-field="status"
              :style="columnWidthStyle('status')"
              tabindex="0"
              :aria-sort="getSortAriaValue('status')"
              :title="$t('torrent.list.sortTitle.status')"
              @click="handleSort('status')"
              @keydown.enter.prevent="handleSort('status')"
              @keydown.space.prevent="handleSort('status')"
            >
              {{ $t('torrent.list.column.status') }}
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('status')"
                :size="13"
                :stroke-width="2"
              />
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('status', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('status')"
                @click.stop
              ></span>
            </th>
            <th v-if="getColumnSetting('downloader').visible" :style="columnWidthStyle('downloader')">
              {{ $t('torrent.list.column.downloader') }}
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('downloader', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('downloader')"
                @click.stop
              ></span>
            </th>
            <th
              v-if="getColumnSetting('ratio').visible"
              class="sortable-column"
              :class="{sorted: listQuery.sort_by === 'ratio'}"
              data-sort-field="ratio"
              :style="columnWidthStyle('ratio')"
              tabindex="0"
              :aria-sort="getSortAriaValue('ratio')"
              :title="$t('torrent.list.sortTitle.ratio')"
              @click="handleSort('ratio')"
              @keydown.enter.prevent="handleSort('ratio')"
              @keydown.space.prevent="handleSort('ratio')"
            >
              {{ $t('torrent.list.column.ratio') }}
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('ratio')"
                :size="13"
                :stroke-width="2"
              />
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('ratio', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('ratio')"
                @click.stop
              ></span>
            </th>
            <th v-if="getColumnSetting('category').visible" :style="columnWidthStyle('category')">
              {{ $t('torrent.list.column.category') }}
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('category', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('category')"
                @click.stop
              ></span>
            </th>
            <th v-if="getColumnSetting('savePath').visible" :style="columnWidthStyle('savePath')">
              {{ $t('torrent.list.column.savePath') }}
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('savePath', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('savePath')"
                @click.stop
              ></span>
            </th>
            <th
              v-if="getColumnSetting('addedDate').visible"
              class="sortable-column"
              :class="{sorted: listQuery.sort_by === 'added_date'}"
              data-sort-field="added_date"
              :style="columnWidthStyle('addedDate')"
              tabindex="0"
              :aria-sort="getSortAriaValue('added_date')"
              :title="$t('torrent.list.sortTitle.addedDate')"
              @click="handleSort('added_date')"
              @keydown.enter.prevent="handleSort('added_date')"
              @keydown.space.prevent="handleSort('added_date')"
            >
              {{ $t('torrent.list.column.addedDate') }}
              <LucideIcon
                class="sort-icon"
                :name="getSortIconName('added_date')"
                :size="13"
                :stroke-width="2"
              />
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('addedDate', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('addedDate')"
                @click.stop
              ></span>
            </th>
            <th
              v-if="getColumnSetting('actions').visible"
              class="action-column"
              :style="columnWidthStyle('actions')"
            >
              {{ $t('torrent.list.column.actions') }}
              <span
                class="column-resizer"
                :title="$t('torrent.list.resizeHint')"
                @mousedown.stop.prevent="startColumnResize('actions', $event)"
                @dblclick.stop.prevent="handleColumnResizeDblclick('actions')"
                @click.stop
              ></span>
            </th>
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
                  :title="showTrackerErrorTag(torrent) ? $t('torrent.list.trackerErrorTitle', {status: getStatusText(torrent.status)}) : ''"
                >
                  <LucideIcon
                    :name="getStatusIcon(torrent.status)"
                    :size="10"
                    :stroke-width="2.5"
                  />
                </div>
                <el-tooltip
                  ref="torrentErrorTooltips"
                  :disabled="!getTorrentErrorReason(torrent)"
                  :content="getTorrentErrorReason(torrent)"
                  :enterable="false"
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
              <span
                v-if="showTrackerErrorTag(torrent)"
                class="tracker-error-tag"
                :title="getTorrentErrorReason(torrent)"
              >{{ $t('torrent.list.trackerError') }}</span>
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
                  :title="$t('torrent.list.action.recheck')"
                >
                  <LucideIcon name="refresh-cw" :size="14" />
                </button>
                <button
                  class="action-btn location"
                  @click.stop="handleSetLocation(torrent)"
                  :title="$t('torrent.list.action.setLocation')"
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
                  <button class="action-btn delete">
                    <LucideIcon name="trash" :size="14" />
                  </button>
                  <el-dropdown-menu slot="dropdown" class="delete-level-menu">
                    <el-dropdown-item command="4">
                      <LucideIcon class="menu-icon" name="tag" :size="14" />{{ $t('torrent.list.deleteMenu.level4') }}
                    </el-dropdown-item>
                    <el-dropdown-item v-if="level3Available" command="3">
                      <LucideIcon class="menu-icon" name="trash-2" :size="14" />{{ $t('torrent.list.deleteMenu.level3') }}
                    </el-dropdown-item>
                    <el-dropdown-item command="2">
                      <LucideIcon class="menu-icon" name="trash" :size="14" />{{ $t('torrent.list.deleteMenu.level2') }}
                    </el-dropdown-item>
                    <el-dropdown-item command="1" divided>
                      <LucideIcon class="menu-icon danger" name="alert-triangle" :size="14" />{{ $t('torrent.list.deleteMenu.level1') }}
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
      :files-state="detailFilesState"
      :peers-state="detailPeersState"
      :media-state="detailMediaState"
      @close="handleCloseTrackerDetail"
      @reannounce="handleTrackerReannounce"
      @refresh="handleDetailRefresh"
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
        <span class="pagination-summary">{{ $t('torrent.list.pagination.summary', {total: total, page: currentPage, pages: totalPages}) }}</span>
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
            {{ $t('torrent.list.columnSettings.title') }}
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
              <span>{{ $t(`torrent.list.column.${column.key}`) }}</span>
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <div class="modal-footer-left">
            <button class="btn-secondary" @click="resetColumnSettings">{{ $t('torrent.list.columnSettings.reset') }}</button>
            <button class="btn-secondary" @click="handleResetColumnWidths">{{ $t('torrent.list.columnSettings.resetWidths') }}</button>
          </div>
          <div class="modal-footer-right">
            <button class="btn-secondary" @click="showColumnSettings = false">{{ $t('common.cancel') }}</button>
            <button class="btn-primary" @click="applyColumnSettings">{{ $t('torrent.list.columnSettings.apply') }}</button>
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
      @batch-complete="handleBatchAddCompleted"
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
          <span>{{ $t('torrent.list.advancedSearch') }}</span>
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
import TrackerDetailCard, {
  DEFAULT_TRACKER_DETAIL_TABS
} from './components/TrackerDetailCard.vue'
import type { TrackerDetailTab } from './components/TrackerDetailCard.vue'
import { ViewModeModule, ViewModeType } from '@/store/modules/viewMode'
import TorrentBatchMixin from './mixins/torrentBatch'
import SpeedPollingMixin from './mixins/speedPolling'
import ColumnResizeMixin from './mixins/columnResize'
import TorrentErrorTooltipDismissMixin from './mixins/errorTooltipDismiss'
import TrackerDetailDataMixin from './mixins/detailTabsData'
import {
  getTorrentList,
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
  reconcileRuntimeTorrentStates,
  applySearchTemplate,
  type Torrent,
  type QueryTemplateConditions
} from '@/api/torrents'
import { TorrentStatus } from '@/types/torrent'
import { localizedStatusOptions, getStatusIcon, getStatusText } from '@/constants/status-config'
import ThemeManager, { ThemeType } from '@/utils/theme-manager'
import {
  normalizeTorrent,
  normalizeTorrentStatus,
  getDownloaderId,
  formatFileSize,
  formatSpeed,
  formatDate,
  formatRatio,
  extractErrorMessage,
  normalizePaginatedResponse,
  debounce
} from '@/utils/formatters'
import { apiErrorMessage, apiResponseMessage } from '@/i18n'
import {
  getTorrentSpeed as getTorrentSpeedFromSnapshot,
  deriveVisibleTorrentList,
  buildSpeedSnapshot,
  collectRuntimeStateReconcileCandidates,
  RuntimeListMembershipTracker,
  TerminalReloadTracker,
  isTorrentRowEffectivelyComplete,
  needsActiveSnapshotRefresh,
  buildAdvancedSearchRequest,
  buildAdvancedSearchRequestFromTemplateGroups,
  getTorrentErrorReason as sharedErrorReason,
  showTrackerErrorTag as sharedShowTrackerErrorTag,
  countMatchedTrackerRows
} from './utils/torrentBatch'
import type { SpeedUpdate } from './utils/torrentBatch'
import {
  buildTorrentSpeedTargetIndex,
  resolveTorrentSpeedTargets
} from './utils/traditionalTorrentIdentity'
import type { AdvancedSearchBuilderParams } from '@/components/torrents/advancedSearchState'
import { normalizeTraditionalPageSize } from './utils/traditionalPagination'
import { isCapabilityAvailable } from '@/api/platform-capabilities'

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
export default class extends mixins(
  TorrentBatchMixin,
  SpeedPollingMixin,
  ColumnResizeMixin,
  TorrentErrorTooltipDismissMixin,
  TrackerDetailDataMixin
) {
  get level3Available(): boolean {
    return isCapabilityAvailable('level3_recycle')
  }

  get seedTransferAvailable(): boolean {
    return isCapabilityAvailable('seed_transfer')
  }
  // 视图模式管理
  private viewModeModule = ViewModeModule

  // ====== 列宽拖拽（ColumnResizeMixin 契约字段） ======
  protected columnWidthStorageKey = 'btdeck_torrents_column_widths'
  protected defaultColumnWidths: Record<string, number> = {
    checkbox: 50,
    name: 400,
    downloadSpeed: 100,
    uploadSpeed: 100,
    size: 100,
    auxiliarySeedCount: 90,
    progress: 140,
    status: 130,
    downloader: 110,
    ratio: 70,
    category: 180,
    savePath: 200,
    addedDate: 130,
    actions: 140
  }

  /** 表级宽度：可见列宽之和（严格列宽，qBittorrent 风格；含名称列，视口富余时右侧留白） */
  get tableMinWidth(): number {
    const fixedKeys = ['checkbox', 'actions']
    const optionalKeys = [
      'name', 'downloadSpeed', 'uploadSpeed', 'size', 'auxiliarySeedCount', 'progress',
      'status', 'downloader', 'ratio', 'category', 'savePath', 'addedDate'
    ]
    const visibleKeys = [
      ...fixedKeys,
      ...optionalKeys.filter(key => this.getColumnSetting(key).visible)
    ]
    return this.sumColumnWidths(visibleKeys)
  }

  // 主题相关
  private currentTheme: ThemeType = 'emerald'

  // 数据状态
  private list: any[] = []
  private total = 0
  private listLoading = true
  private multipleSelection: any[] = []

  // 实时速度轮询（speedTimer/speedPollingActive 由 SpeedPollingMixin 提供）
  private speedSnapshotReady = false
  private activeSpeedMap: Record<string, {
    downloadSpeed: number
    uploadSpeed: number
    progress: number
    status?: string
    downloadComplete?: boolean
  }> = {}
  private activeListRetryPending = false
  private activeListRetryInFlight = false
  private runtimeStateMisses: Record<string, number> = {}
  private runtimeStateReconcileInFlight = false
  private runtimeListMembership = new RuntimeListMembershipTracker()
  /** 终态整表刷新去重：同一复合键完成证据只触发一次 getList（防滞后窗口每秒刷新循环）。
   * 筛选/模板/排查模式等上下文变化处 clear()；排序/翻页/手动刷新不清——去重键是
   * downloader+hash 行身份键与行序无关，翻页与手动刷新本身即 getList。 */
  private terminalReloadTracker = new TerminalReloadTracker()

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

  // Tracker详情（detailFilesState/detailPeersState/handleDetailRefresh 由 TrackerDetailDataMixin 提供）
  private showTrackerDetail = false
  private currentRow: any = null
  private activeDetailTab = 'tracker'
  private detailTabs: TrackerDetailTab[] = DEFAULT_TRACKER_DETAIL_TABS

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

  // 列设置（展示名按 torrent.list.column.* 键渲染，不在 data 固定译文）
  private columnSettings = [
    { key: 'name', visible: true },
    { key: 'downloadSpeed', visible: true },
    { key: 'uploadSpeed', visible: true },
    { key: 'size', visible: true },
    { key: 'auxiliarySeedCount', visible: true },
    { key: 'progress', visible: true },
    { key: 'status', visible: true },
    { key: 'downloader', visible: true },
    { key: 'ratio', visible: true },
    { key: 'category', visible: true },
    { key: 'savePath', visible: true },
    { key: 'addedDate', visible: true },
    { key: 'actions', visible: true }
  ]

  // 下载器列表
  private downloaderList: DownloaderSimple[] = []

  // 计算属性

  /**
   * 状态选项列表（使用统一配置）
   */
  get statusOptions() {
    return localizedStatusOptions()
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
        this.$message.error(response.msg || this.$t('torrent.msg.applyTemplateFailed'))
      }
    } catch (error) {
      this.$message.error(this.$t('torrent.msg.applyTemplateFailedWith', { message: (error as Error).message }))
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

      // 观察日志：与后端 [tracker-domain-filter] debug 日志对账，验证命中标记口径
      console.debug(
        '[tracker-filter] total=%d 本页=%d 命中标记行=%d',
        total,
        normalizedList.length,
        countMatchedTrackerRows(normalizedList)
      )
    } catch (error) {
      const errorMessage = extractErrorMessage(error)
      console.error('获取种子列表失败:', error)
      this.$message.error(errorMessage || this.$t('torrent.msg.getListFailed'))
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
    // 筛选上下文变化：重置终态刷新去重
    this.terminalReloadTracker.clear()
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
    // 筛选上下文变化：重置终态刷新去重
    this.terminalReloadTracker.clear()
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
    // 排查模式切换等效换筛选：重置终态刷新去重
    this.terminalReloadTracker.clear()
    if (command === 'inspect-same-content') {
      this.showingDuplicates = false
      this.showingSingleErrors = false
      this.showingSameContent = true
      this.currentPage = 1
      this.listQuery.skip = 0
      await this.getList()
      this.$message.success(this.$t('torrent.msg.inspectSameContentDone', { count: this.total }))
    } else if (command === 'inspect-single-errors') {
      this.showingDuplicates = false
      this.showingSameContent = false
      this.showingSingleErrors = true
      this.currentPage = 1
      this.listQuery.skip = 0
      await this.getList()
      this.$message.success(this.$t('torrent.msg.inspectSingleErrorDone', { count: this.total }))
    } else if (command === 'delete-duplicates') {
      this.showQuickDeleteDuplicatesDialog = true
    }
  }

  private async exitSameContentInspection() {
    this.showingSameContent = false
    this.currentPage = 1
    this.listQuery.skip = 0
    this.terminalReloadTracker.clear()
    await this.getList()
  }

  private async exitSingleErrorInspection() {
    this.showingSingleErrors = false
    this.currentPage = 1
    this.listQuery.skip = 0
    this.terminalReloadTracker.clear()
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
    return sharedErrorReason(torrent)
  }

  private showTrackerErrorTag(torrent: Torrent | null | undefined): boolean {
    return sharedShowTrackerErrorTag(torrent)
  }

  /**
   * 处理单个Tracker的汇报操作
   */
  private async handleTrackerReannounce(tracker: any, _index: number) {
    if (!this.currentRow?.hash) {
      this.$message.error(this.$t('torrent.msg.reannounceIncomplete'))
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
        this.$message.success(this.$t('torrent.msg.reannounceSuccess'))
        // 刷新种子列表
        await this.getList()
      } else {
        // 双语 P4 错误契约：优先 reasonCode 本地化，未契约化路径回退原始 msg
        this.$message.error(apiResponseMessage(response, this.$t('torrent.msg.reannounceFailed') as string))
      }
    } catch (error) {
      console.error('Tracker汇报失败:', error)
      this.$message.error(this.$t('torrent.msg.reannounceFailed'))
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
        this.$message.warning(this.$t('torrent.msg.reannouncePartial', { succeeded: succeeded, failed: failed, total: total }))
      } else {
        this.$message.success(this.$t('torrent.msg.reannounceBatchSuccess', { total: total, downloaderCount: downloaderCount }))
      }

      this.getList()
    } catch (error) {
      console.error('Tracker汇报失败:', error)
      this.$message.error(this.$t('torrent.msg.reannounceBatchFailed'))
    }
  }

  private handleBatchTracker() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning(this.$t('torrent.msg.selectFirstAction'))
      return
    }
    this.selectedTorrentsForTracker = [...this.multipleSelection]
    this.trackerOperationType = ''
    this.showTrackerOperationDialog = true
  }
  private handleBatchTransfer() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning(this.$t('torrent.msg.selectFirstTransfer'))
      return
    }
    // 检查选中的种子是否都在同一下载器
    const downloaderIds = new Set(this.multipleSelection.map(t => getDownloaderId(t)))
    if (downloaderIds.has(undefined) || downloaderIds.has(null)) {
      this.$message.warning(this.$t('torrent.msg.missingDownloader'))
      return
    }
    if (downloaderIds.size > 1) {
      this.$message.warning(this.$t('torrent.msg.transferSingleDownloaderOnly'))
      return
    }
    this.showBatchTransferDialog = true
  }

  private handleBatchTransferSuccess() {
    this.showBatchTransferDialog = false
    this.getList()
    this.$message.success(this.$t('torrent.msg.transferDone'))
  }

  // 修改保存路径
  private handleSetLocation(torrent: any) {
    this.selectedTorrentsForLocation = [torrent]
    this.showSetLocationDialog = true
  }

  private handleBatchSetLocation() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning(this.$t('torrent.msg.selectFirst'))
      return
    }

    // 验证所有选中的种子是否在同一下载器
    const downloaderIds = new Set(this.multipleSelection.map(t => getDownloaderId(t)))
    if (downloaderIds.has(undefined) || downloaderIds.has(null)) {
      this.$message.warning(this.$t('torrent.msg.missingDownloader'))
      return
    }
    if (downloaderIds.size > 1) {
      this.$message.warning(this.$t('torrent.msg.setLocationSingleDownloaderOnly'))
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
        this.$message.success(this.$t('torrent.msg.startSuccess'))
      } else {
        await pauseTorrents({ downloader_id: downloaderId, hashes: [row.hash] })
        this.$message.success(this.$t('torrent.msg.pauseSuccess'))
      }
      this.getList()
    } catch (error) {
      // 双语 P4 错误契约：优先 reasonCode 本地化，未契约化路径回退原始 msg
      const errorMessage = apiErrorMessage(error, this.$t('torrent.msg.opFailed') as string)
      console.error('操作失败:', error)
      this.$message.error(errorMessage)
    }
  }

  private async handleRecheck(row: any) {
    try {
      const downloaderId = row.downloader_id || row.downloaderId
      await recheckTorrents({ downloader_id: downloaderId, hashes: [row.hash] })
      this.$message.success(this.$t('torrent.msg.recheckSuccess'))
      this.getList()
    } catch (error) {
      // 双语 P4 错误契约：优先 reasonCode 本地化，未契约化路径回退原始 msg
      const errorMessage = apiErrorMessage(error, this.$t('torrent.msg.recheckFailed') as string)
      console.error('重新检查失败:', error)
      this.$message.error(errorMessage)
    }
  }

  private async handleAdd() {
    this.showAddDialog = false
    this.getList()
  }

  /** 202 后台添加真正完成后再拉一次权威列表，覆盖首次刷新早于入库的竞态。 */
  private async handleBatchAddCompleted() {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const component = this
    await component.getList()
    await component.loadActiveSpeed()
  }

  // Tracker操作
  private handleTrackerOperationSuccess() {
    this.getList()
    this.$message.success(this.$t('torrent.msg.trackerOpSuccess'))
  }

  private handleGlobalReplaceSuccess() {
    this.getList()
    this.$message.success(this.$t('torrent.msg.globalReplaceSuccess'))
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

  /** 列设置菜单：全部列宽恢复默认（ColumnResizeMixin 提供 resetColumnWidths） */
  private handleResetColumnWidths() {
    this.resetColumnWidths()
    this.$message.success(this.$t('torrent.list.columnSettings.widthsReset'))
  }

  private applyColumnSettings() {
    this.showColumnSettings = false
    this.saveUserPreferences()
    this.updateColumnVisibility()
    this.$message.success(this.$t('torrent.list.columnSettings.saved'))
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
    this.$message.success(this.$t('torrent.msg.conditionsReset'))
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
      this.$message.error(error || this.$t('torrent.msg.invalidSearchParams'))
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
        this.$message.success(this.$t('torrent.msg.advancedDone', { count: this.total }))
      } else {
        this.$message.error(response.msg || this.$t('torrent.msg.searchFailed'))
      }
    } catch (error) {
      console.error('高级搜索失败:', error)
      this.$message.error(this.$t('torrent.msg.advancedFailed'))
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
      this.$message.error(this.$t('torrent.msg.templateInvalid'))
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
        // 模板重建筛选上下文：重置终态刷新去重
        this.terminalReloadTracker.clear()
        await this.getList()
        this.$message.success(this.$t('torrent.msg.templateApplied'))
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
          this.$message.error(error || this.$t('torrent.msg.invalidSearchParams'))
          return false
        }
        const response = await advancedSearch(request)
        if (response.code === '200' && response.data) {
          this.list = (response.data.list || []).map(normalizeTorrent).map(item => ({ ...item, checked: false }))
          this.total = response.data.total || 0
          this.listQuery.skip = 0
          this.currentPage = 1
          this.resetBatchSelection()
          this.$message.success(this.$t('torrent.msg.advancedTemplateApplied'))
          return true
        }
        this.$message.error(response.msg || this.$t('torrent.msg.searchFailed'))
        return false
      } else {
        this.$message.warning(this.$t('torrent.msg.unsupportedTemplate'))
      }
    } catch (error) {
      this.$message.error(this.$t('torrent.msg.applyTemplateFailedWith', { message: (error as Error).message }))
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

  /** 将实时快照更新应用到当前列表，始终按 downloader_id + hash 精确命中。 */
  private applySpeedUpdates(updates: SpeedUpdate[]): boolean {
    const targetIndex = buildTorrentSpeedTargetIndex(this.list)
    let terminalObserved = false
    updates.forEach(update => {
      const targets = resolveTorrentSpeedTargets(targetIndex, update)
      targets.forEach(torrent => {
        // 转移判定的前态必须在本循环对该行任何赋值（speed/progress/status）之前捕获：
        // buildSpeedSnapshot 会把完成证据的 status 改写为 'completed'，分支内延迟求值
        // 会让行永远呈现已终态、转移永不触发，合法的滞后首刷会被彻底杀死。
        const wasComplete = isTorrentRowEffectivelyComplete(torrent)
        torrent.downloadSpeed = update.downloadSpeed
        torrent.uploadSpeed = update.uploadSpeed
        torrent.progress = update.downloadComplete ? 100 : update.progress
        if (update.status) {
          torrent.status = normalizeTorrentStatus(update.status, update.status)
        }
        if (update.downloadComplete) {
          torrent.downloadComplete = true
          // 稳态证据（行已是终态，如做种行每轮带回 downloadComplete）不再报告，
          // 根治筛选下每秒 getList 的稳态循环；滞后窗口的重复触发由
          // terminalReloadTracker 按复合键去重兜底。
          if (!wasComplete) terminalObserved = true
        }
      })
    })
    return terminalObserved
  }

  private async reconcileRuntimeStates(
    candidates: Array<{ downloader_id: string, hash: string }>
  ): Promise<boolean> {
    if (!candidates.length || this.runtimeStateReconcileInFlight) return false
    this.runtimeStateReconcileInFlight = true
    try {
      const response = await reconcileRuntimeTorrentStates(candidates)
      const data = response.code === '200' && response.data
        ? response.data
        : null
      if (!data || !Array.isArray(data.list)) return false

      const reconcileSnapshot = buildSpeedSnapshot({
        status: response.status,
        msg: response.msg,
        code: '200',
        data: data.list
      })
      const terminalObserved = this.applySpeedUpdates(reconcileSnapshot.updates)
      if (
        terminalObserved &&
        (this.listQuery.showActiveOnly ||
          (Array.isArray(this.listQuery.status) && this.listQuery.status.length > 0)) &&
        this.terminalReloadTracker.observeNewTerminal(reconcileSnapshot.updates)
      ) {
        await this.getList()
      }
      return true
    } catch (error) {
      console.debug('[速度轮询] 终态核验失败:', error)
      return false
    } finally {
      this.runtimeStateReconcileInFlight = false
    }
  }

  /** 加载活跃种子实时速度和进度 */
  protected async loadActiveSpeed(): Promise<boolean> {
    const requestId = Date.now()

    try {
      const res = await getActiveTorrents()
      const snapshot = buildSpeedSnapshot(res)
      if ((snapshot.ready || snapshot.partial) && snapshot.activeSpeedMap && snapshot.torrentSpeedMap) {
        const newlyUnlistedKeys = this.runtimeListMembership.observe(
          this.list,
          snapshot.updates,
          snapshot.ready
        )
        let terminalObserved = this.applySpeedUpdates(snapshot.updates)
        // 206 是可用但不完整的增量：合并已知键，不得清空上一轮完整快照。
        this.activeSpeedMap = snapshot.ready
          ? snapshot.torrentSpeedMap
          : { ...this.activeSpeedMap, ...snapshot.torrentSpeedMap }
        if (newlyUnlistedKeys.length > 0) {
          // eslint-disable-next-line @typescript-eslint/no-this-alias
          const component = this
          terminalObserved = (await component.runtimeListMembership.refresh(
            () => component.list,
            snapshot.updates,
            () => component.getList(),
            updates => component.applySpeedUpdates(updates)
          )) || terminalObserved
        }
        if (snapshot.ready) {
          this.speedSnapshotReady = true
          const reconcile = collectRuntimeStateReconcileCandidates(
            this.list,
            snapshot.updates,
            this.runtimeStateMisses
          )
          this.runtimeStateMisses = reconcile.misses
          if (reconcile.candidates.length) {
            await this.reconcileRuntimeStates(reconcile.candidates)
          }
        }
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
        if (
          terminalObserved &&
          (this.listQuery.showActiveOnly ||
            (Array.isArray(this.listQuery.status) && this.listQuery.status.length > 0)) &&
          this.terminalReloadTracker.observeNewTerminal(snapshot.updates)
        ) {
          await this.getList()
        }
        return snapshot.ready
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
    // 数据源模式切换等效换筛选：重置终态刷新去重
    this.terminalReloadTracker.clear()
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
        this.$message.success(this.$t('torrent.msg.duplicatesFound', { count: total }))
      }
    } catch (error) {
      const errorMessage = extractErrorMessage(error) || this.$t('torrent.msg.duplicateFetchFailed')
      console.error('查找重复任务失败:', error)
      this.$message.error(errorMessage || this.$t('torrent.msg.duplicateFetchFailedRetry'))
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
