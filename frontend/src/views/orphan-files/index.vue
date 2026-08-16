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
      v-else-if="latestAttempt && (latestAttempt.status === 'queued' || latestAttempt.status === 'running')"
      class="orphan-scan-state-alert"
      :title="latestAttempt.status === 'queued' ? '孤儿文件扫描等待执行' : '孤儿文件扫描进行中'"
      :description="scanStatusMessage"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="largeScanReminderVisible"
      class="orphan-scan-state-alert"
      title="超量扫描提醒"
      type="warning"
      :closable="true"
      show-icon
      @close="dismissLargeScanReminder"
    >
      本次扫描发现的孤儿文件数量较多，请留意下载器路径映射和孤儿判定；此提醒不影响清理。
    </el-alert>

    <!-- 筛选条件 -->
    <section class="management-panel" aria-label="孤儿文件筛选条件">
      <div class="management-filter">
        <div class="management-filter__field">
          <label class="management-filter__label" for="orphan-path-like">文件路径</label>
          <el-input
            id="orphan-path-like"
            v-model="listQuery.path_like"
            class="management-filter__control orphan-path-input"
            placeholder="路径关键字模糊匹配"
            prefix-icon="el-icon-search"
            clearable
            @keyup.enter.native="handleFilter"
            @clear="handleFilter"
          />
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="orphan-downloader">下载器</label>
          <AdvancedMultiSelect
            v-model="listQuery.downloader_id"
            :options="downloaderOptions"
            :allow-create="false"
            :show-mode-toggle="false"
            :virtual-scroll-threshold="100"
            :list-height="240"
            class="management-filter__control"
            @change="handleFilter"
          />
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="orphan-status">
            状态
            <el-tooltip
              v-if="statusFilterDegraded"
              content="同时选“待清理”与“已忽视/已清理”会扩大为全部未删除文件"
              placement="top"
              :open-delay="200"
            >
              <span class="management-filter__warn-icon" aria-label="筛选组合提示">⚠</span>
            </el-tooltip>
          </label>
          <AdvancedMultiSelect
            v-model="listQuery.status"
            :options="statusOptions"
            :allow-create="false"
            :show-mode-toggle="false"
            :virtual-scroll-threshold="100"
            :list-height="240"
            class="management-filter__control"
            @change="handleFilter"
          />
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="orphan-confidence">置信度</label>
          <AdvancedMultiSelect
            v-model="listQuery.confidence"
            :options="confidenceOptions"
            :allow-create="false"
            :show-mode-toggle="false"
            :virtual-scroll-threshold="100"
            :list-height="240"
            class="management-filter__control"
            @change="handleFilter"
          />
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="orphan-located-copies">副本定位</label>
          <el-tooltip
            content="按每日预扫描任务落库的结果过滤，与列表实时副本数可能短暂不一致"
            placement="top"
            :open-delay="200"
          >
            <el-checkbox
              id="orphan-located-copies"
              v-model="listQuery.hardlinkCopies"
              class="management-filter__control orphan-located-copies-checkbox"
              @change="handleFilter"
            >
              已定位副本
            </el-checkbox>
          </el-tooltip>
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
          <el-tooltip
            content="开启后同目录下多个文件折叠为文件夹一行（仅影响展示，删除仍按文件）"
            placement="top"
          >
            <el-button
              :type="folderView ? 'primary' : 'default'"
              :icon="folderView ? 'el-icon-folder-opened' : 'el-icon-folder'"
              @click="setFolderView(!folderView)"
            >
              按文件夹展示
            </el-button>
          </el-tooltip>
          <el-dropdown trigger="click" @command="handleQuickAction">
            <el-button icon="el-icon-magic-stick">
              快捷操作<i class="el-icon-arrow-down el-icon--right"></i>
            </el-button>
            <el-dropdown-menu slot="dropdown">
              <el-dropdown-item
                command="cleanup"
                icon="el-icon-delete"
                :disabled="!cleanupAllowed"
                :title="cleanupBlockReason"
              >
                快捷删除（按前缀）
              </el-dropdown-item>
              <el-dropdown-item
                command="ignore"
                icon="el-icon-warning-outline"
                :disabled="!displayScan"
                title="按路径前缀批量忽视待清理文件"
              >
                快捷忽视（按前缀）
              </el-dropdown-item>
              <el-dropdown-item
                command="toggleLocatedCopies"
                :icon="listQuery.hardlinkCopies ? 'el-icon-check' : 'el-icon-copy-document'"
                :disabled="!displayScan"
                :title="listQuery.hardlinkCopies ? '取消副本定位筛选，恢复完整列表' : '仅显示预扫描已定位到硬链接副本路径的文件'"
                divided
              >
                {{ listQuery.hardlinkCopies ? '取消已定位副本筛选' : '筛选已定位副本' }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </el-dropdown>
        </div>
      </div>
      <div class="management-table-scroll orphan-table-scroll">
        <el-table
          ref="orphanTable"
          v-loading="listLoading"
          :data="tableData"
          :row-key="getRowKey"
          :row-class-name="getOrphanRowClassName"
          class="management-table"
          height="100%"
          border
          fit
          highlight-current-row
          empty-text="暂无孤儿文件，点击“立即扫描”开始检测"
          style="width: 100%"
          @selection-change="handleOrphanSelectionChange"
          @expand-change="handleFolderExpandChange"
        >
          <el-table-column v-if="folderView" type="expand" width="48">
            <template slot-scope="scope">
              <div v-if="scope.row._is_folder" class="orphan-folder-children">
                <el-table
                  v-loading="scope.row.children_loading"
                  :data="scope.row.children"
                  :row-key="getRowKey"
                  :show-header="false"
                  border
                  size="mini"
                  @selection-change="handleFolderChildSelection(scope.row, $event)"
                >
                  <el-table-column type="selection" width="48" :selectable="rowSelectable" />
                  <el-table-column prop="file_path" label="文件路径" min-width="320" show-overflow-tooltip />
                  <el-table-column label="大小" width="110" align="center">
                    <template slot-scope="childScope">{{ formatSize(childScope.row.file_size) }}</template>
                  </el-table-column>
                  <el-table-column label="副本数量" width="90" align="center">
                    <template slot-scope="childScope">
                      <button
                        v-if="canOpenHardlinkLocations(childScope.row)"
                        type="button"
                        class="orphan-hardlink-copy-count orphan-hardlink-copy-count--link"
                        :title="getHardlinkCopyCountTitle(childScope.row)"
                        @click.stop="handleHardlinkCopyClick(childScope.row)"
                      >
                        {{ formatHardlinkCopyCount(childScope.row.hardlink_copy_count) }}
                      </button>
                      <span v-else>{{ formatHardlinkCopyCount(childScope.row.hardlink_copy_count) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="状态" width="90" align="center">
                    <template slot-scope="childScope">
                      <el-tag v-if="childScope.row.is_deleted" type="info" size="mini">已清理</el-tag>
                      <el-tag v-else-if="childScope.row.is_ignored" type="warning" size="mini">已忽视</el-tag>
                      <el-tag v-else type="danger" size="mini">待清理</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="90" align="center">
                    <template slot-scope="childScope">
                      <el-button
                        v-if="!childScope.row.is_deleted"
                        type="text"
                        size="mini"
                        @click="handleRowIgnore(childScope.row, !childScope.row.is_ignored)"
                      >
                        {{ childScope.row.is_ignored ? '取消忽视' : '忽视' }}
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <el-pagination
                  class="orphan-folder-children__pagination"
                  background
                  layout="total, prev, pager, next, sizes"
                  :current-page="scope.row.child_page"
                  :page-size="scope.row.child_page_size"
                  :page-sizes="[20, 50, 100, 200]"
                  :total="scope.row.child_total"
                  @current-change="handleFolderChildPageChange(scope.row, $event)"
                  @size-change="handleFolderChildPageSizeChange(scope.row, $event)"
                />
              </div>
            </template>
          </el-table-column>
          <el-table-column
            type="selection"
            width="55"
            align="center"
            :selectable="rowSelectable"
            aria-label="选择当前页的全部孤儿文件"
          />
          <el-table-column label="文件路径" prop="file_path" min-width="300" show-overflow-tooltip class-name="orphan-path-cell">
            <template slot-scope="scope">
              <span v-if="scope.row._is_folder" class="orphan-folder-cell">
                <i class="el-icon-folder" aria-hidden="true"></i>
                <span class="orphan-folder-cell__path" :title="scope.row.folder_path">{{ scope.row.folder_path }}</span>
                <el-tag size="mini" type="info" class="orphan-folder-cell__count">
                  {{ scope.row.child_count }} 个文件
                </el-tag>
              </span>
              <span v-else>{{ scope.row.file_path }}</span>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="120" align="center">
            <template slot-scope="scope">
              {{ formatSize(scope.row._is_folder ? scope.row.total_size : scope.row.file_size) }}
            </template>
          </el-table-column>
          <el-table-column label="副本数量" width="100" align="center">
            <template slot-scope="scope">
              <button
                v-if="canOpenHardlinkLocations(scope.row)"
                type="button"
                class="orphan-hardlink-copy-count orphan-hardlink-copy-count--link"
                :title="getHardlinkCopyCountTitle(scope.row)"
                :aria-label="getHardlinkCopyCountTitle(scope.row)"
                @click.stop="handleHardlinkCopyClick(scope.row)"
              >
                {{ formatHardlinkCopyCount(scope.row.hardlink_copy_count) }}
              </button>
              <span
                v-else
                class="orphan-hardlink-copy-count"
                :title="getHardlinkCopyCountTitle(scope.row)"
              >
                {{ formatHardlinkCopyCount(scope.row.hardlink_copy_count) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="修改时间" width="170" align="center">
            <template slot-scope="scope">
              {{ (scope.row._is_folder ? scope.row.latest_mtime : scope.row.mtime) ? formatTime(scope.row._is_folder ? scope.row.latest_mtime : scope.row.mtime) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="下载器" width="140" align="center" show-overflow-tooltip>
            <template slot-scope="scope">
              <template v-if="scope.row._is_folder">
                {{ scope.row.downloader_name || '多个' }}
              </template>
              <template v-else>
                {{ scope.row.downloader_name || (scope.row.downloader_id ? maskId(scope.row.downloader_id) : '-') }}
              </template>
            </template>
          </el-table-column>
          <el-table-column label="置信度" width="100" align="center">
            <template slot-scope="scope">
              <template v-if="scope.row._is_folder">
                <el-tooltip
                  v-if="scope.row.has_low_confidence"
                  content="文件夹内含离线降级目录粗筛判定的低置信度项，有误判风险"
                  placement="top"
                >
                  <el-tag type="info" size="small">混合</el-tag>
                </el-tooltip>
                <el-tooltip v-else content="文件夹内全部为在线精筛判定，确认未被任何种子引用" placement="top">
                  <el-tag type="success" size="small">高</el-tag>
                </el-tooltip>
              </template>
              <template v-else>
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
              <template v-if="scope.row._is_folder">
                <el-tag v-if="scope.row.all_deleted" type="info" size="small">已清理</el-tag>
                <el-tag v-else-if="scope.row.all_ignored" type="warning" size="small">已忽视</el-tag>
                <el-tag v-else-if="scope.row.all_pending" type="danger" size="small">待清理</el-tag>
                <el-tag v-else type="info" size="small">混合</el-tag>
              </template>
              <template v-else>
                <el-tag v-if="scope.row.is_deleted" type="info" size="small">已清理</el-tag>
                <el-tag v-else-if="scope.row.is_ignored" type="warning" size="small">已忽视</el-tag>
                <el-tag v-else type="danger" size="small">待清理</el-tag>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center" fixed="right">
            <template slot-scope="scope">
              <span v-if="scope.row._is_folder">-</span>
              <el-button
                v-else-if="!scope.row.is_deleted && !scope.row.is_ignored"
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

      <!-- 列表传统分页：按页码切换，切换页码时清空当前页选择。 -->
      <nav class="torrent-pagination management-pagination" aria-label="孤儿文件分页">
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
          <span class="pagination-summary">共 <strong>{{ total }}</strong> 条</span>
        </div>
        <div class="pagination-controls">
          <el-pagination
            background
            :current-page.sync="listQuery.page"
            :page-size="listQuery.page_size"
            :total="total"
            layout="prev, pager, next"
            @current-change="handleOrphanPageChange"
          />
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
              <el-table-column label="延后次数" width="110" align="center">
                <template slot-scope="{row}">
                  <el-tag
                    v-if="(row.purge_delay_count || 0) > 0"
                    type="warning"
                    size="small"
                    effect="plain"
                  >
                    {{ row.purge_delay_count }}
                  </el-tag>
                  <span v-else>-</span>
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

    <!-- 硬链接副本位置对话框（读取定时预扫描落库结果，不做实时遍历） -->
    <el-dialog
      :title="hardlinkLocationDialogTitle"
      :visible.sync="hardlinkLocationDialogVisible"
      width="760px"
      :close-on-click-modal="false"
      custom-class="management-dialog hardlink-location-dialog"
      @closed="resetHardlinkLocationDialog"
    >
      <div v-loading="hardlinkLocationLoading" class="hardlink-location-content">
        <el-alert
          title="副本位置由每日定时任务在后台整体查找并存储，此处直接显示最近一轮结果。"
          type="info"
          :closable="false"
          show-icon
        />

        <template v-if="hardlinkLocationResult">
          <div class="hardlink-location-summary">
            <span>实时副本 <strong>{{ hardlinkLocationResult.total_copy_count }}</strong></span>
            <span>已定位 <strong>{{ hardlinkLocationResult.total_found_count }}</strong></span>
            <span>待预扫描 <strong>{{ hardlinkLocationResult.pending_scan_count }}</strong></span>
          </div>

          <el-alert
            v-if="hardlinkLocationResult.total_unlocated_count > 0"
            class="hardlink-location-alert"
            :title="`还有 ${hardlinkLocationResult.total_unlocated_count} 个副本未在最近一轮预扫描中定位`"
            description="这些副本可能位于无权限或未挂载目录，也可能尚未被预扫描覆盖；副本总数为实时统计。"
            type="warning"
            :closable="false"
            show-icon
          />
          <el-alert
            v-if="hardlinkLocationResult.unknown_count > 0"
            class="hardlink-location-alert"
            :title="`${hardlinkLocationResult.unknown_count} 个源文件当前不可访问，无法核对位置`"
            type="error"
            :closable="false"
            show-icon
          />
          <el-alert
            v-if="hardlinkLocationResult.search_error"
            class="hardlink-location-alert"
            :title="hardlinkLocationResult.search_error"
            type="error"
            :closable="false"
            show-icon
          />
          <el-alert
            v-if="hardlinkLocationResult.missing_orphan_ids.length > 0"
            class="hardlink-location-alert"
            :title="`${hardlinkLocationResult.missing_orphan_ids.length} 个列表项已失效，请刷新页面后重试`"
            type="warning"
            :closable="false"
            show-icon
          />

          <div class="hardlink-location-list">
            <section
              v-for="item in hardlinkLocationResult.items"
              :key="item.orphan_id"
              class="hardlink-location-item"
            >
              <header class="hardlink-location-item__header">
                <span class="hardlink-location-item__source" :title="item.file_path">
                  {{ item.file_path }}
                </span>
                <span class="hardlink-location-item__metrics">
                  <el-tag size="mini" type="info">副本 {{ formatHardlinkCopyCount(item.copy_count) }}</el-tag>
                  <el-tag v-if="item.pending_scan" size="mini" type="warning">待预扫描</el-tag>
                  <el-tag v-else size="mini" type="success">已定位 {{ item.found_count }}</el-tag>
                  <el-tag
                    v-if="item.scanned_at"
                    size="mini"
                    type="info"
                    :title="item.scanned_at"
                  >
                    扫描于 {{ formatTime(item.scanned_at) }}
                  </el-tag>
                </span>
              </header>

              <el-alert
                v-if="item.copy_count === null"
                :title="item.error || '源文件不可访问，无法重新核对副本位置'"
                type="error"
                :closable="false"
                show-icon
              />
              <el-alert
                v-else-if="item.error"
                :title="item.error"
                type="warning"
                :closable="false"
                show-icon
              />

              <div v-if="item.copies.length > 0" class="hardlink-location-copies">
                <div
                  v-for="copyPath in item.copies"
                  :key="copyPath"
                  class="hardlink-location-copy"
                >
                  <span class="hardlink-location-copy__path" :title="copyPath">{{ copyPath }}</span>
                  <el-button
                    type="text"
                    size="mini"
                    class="hardlink-location-copy__button"
                    @click="copyHardlinkPath(copyPath)"
                  >
                    复制路径
                  </el-button>
                </div>
                <p v-if="item.result_truncated" class="hardlink-location-unlocated">
                  路径数超过存储上限，仅显示前 {{ item.copies.length }} 条。
                </p>
              </div>
              <p v-else-if="item.pending_scan" class="hardlink-location-empty">
                等待每日定时任务预扫描定位副本路径，可稍后重新打开查看。
              </p>
              <p v-else-if="item.copy_count && item.copy_count > 0" class="hardlink-location-empty">
                最近一轮预扫描未定位到副本路径。
              </p>
              <p v-else-if="item.copy_count === 0" class="hardlink-location-empty">
                点击查询时已复核为 0 个副本。
              </p>
              <p v-if="item.unlocated_count && item.unlocated_count > 0" class="hardlink-location-unlocated">
                该文件还有 {{ item.unlocated_count }} 个副本位置未定位。
              </p>
            </section>
          </div>
        </template>
      </div>
      <span slot="footer" class="dialog-footer">
        <el-button @click="hardlinkLocationDialogVisible = false">关闭</el-button>
      </span>
    </el-dialog>

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

    <!-- 快捷操作（左匹配）对话框 -->
    <el-dialog
      :title="quickActionType === 'cleanup' ? '快捷删除（按前缀）' : '快捷忽视（按前缀）'"
      :visible.sync="quickActionDialogVisible"
      width="520px"
      :close-on-click-modal="false"
      custom-class="management-dialog"
    >
      <div v-loading="quickActionLoading">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="按路径前缀左匹配待清理文件"
        >
          <template slot="default">
            <p>
              输入路径前缀（绝对路径开头），将匹配所有
              <strong>文件路径</strong> 以此开头的<strong>待清理</strong>文件（排除已忽视/已清理）。
            </p>
            <p v-if="quickActionType === 'cleanup'">删除即移入隔离区，可恢复。</p>
          </template>
        </el-alert>
        <div style="margin-top: 16px">
          <label for="quick-action-prefix" style="display:block; margin-bottom: 6px; font-weight: 600">
            路径前缀
          </label>
          <el-input
            id="quick-action-prefix"
            v-model="quickActionPrefix"
            placeholder="例如：D:\downloads\待清理目录\ 或 /data/leak/"
            clearable
            :disabled="quickActionLoading"
            @keyup.enter.native="handleQuickActionConfirm"
          />
        </div>
      </div>
      <span slot="footer" class="dialog-footer">
        <el-button :disabled="quickActionLoading" @click="handleQuickActionCancel">取消</el-button>
        <el-button
          type="primary"
          :loading="quickActionLoading"
          @click="handleQuickActionConfirm"
        >
          确定
        </el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import {
  getOrphanList,
  getOrphanFolderChildren,
  getHardlinkCopyLocations,
  triggerScan,
  getScanStatus,
  cleanupPreview,
  cleanupOrphans,
  setIgnored,
  prefixMatchPreview,
  getQuarantineList,
  restoreQuarantined,
  purgeQuarantineNow,
  OrphanFileItem,
  OrphanFolderRow,
  OrphanTableRow,
  HardlinkCopyLocationsResult,
  OrphanListParams,
  OrphanScanContext,
  OrphanScanRecord,
  OrphanConfidence,
  OrphanStatusFilter,
  OrphanSelectionPayload,
  OrphanSelectionFilters,
  CleanupPreviewSuccess,
  IgnoreResult,
  QuarantineItem,
  PrefixMatchPreviewResult
} from '@/api/orphan-files'
import { getDownloaderList, DownloaderSimple } from '@/api/torrents'
import { formatFileSize, formatDate, extractErrorMessage } from '@/utils/formatters'
import PageSizeCombobox, { PageSizeSuggestion } from '@/components/torrents/PageSizeCombobox.vue'
import AdvancedMultiSelect from '@/components/torrents/AdvancedMultiSelect.vue'
import type { SelectOption } from '@/components/torrents/AdvancedMultiSelect.vue'
import { normalizeTraditionalPageSize } from '@/views/torrents/utils/traditionalPagination'
import { copyTextToClipboard } from '@/utils/clipboard'

interface OrphanListQuery {
  page: number
  page_size: number
  downloader_id: string[]
  path_like: string
  status: OrphanStatusFilter[]
  confidence: OrphanConfidence[]
  // 仅显示预扫描已定位到硬链接副本路径的文件（快捷操作可一键切换）
  hardlinkCopies: boolean
}

interface OrphanTableRef extends Vue {
  clearSelection: () => void
  toggleRowSelection: (row: OrphanTableRow, selected?: boolean) => void
  selection: OrphanTableRow[]
}

const ORPHAN_PAGE_SIZE_MAX = 1000

const FOLDER_VIEW_STORAGE_KEY = 'btdeck_orphan_folder_view'

/** 文件夹行类型守卫（列模板分支与选择联动用）；字段对齐后端 _is_folder 标记。 */
function isFolderRow(row: OrphanTableRow | undefined | null): row is OrphanFolderRow {
  return !!row && (row as OrphanFolderRow)._is_folder === true
}

@Component({ name: 'OrphanFiles', components: { PageSizeCombobox, AdvancedMultiSelect } })
export default class OrphanFiles extends Vue {
  private list: OrphanTableRow[] = []
  private total = 0
  private listLoading = false
  private scanLoading = false
  private ignoreLoading = false
  private listQuery: OrphanListQuery = {
    page: 1,
    page_size: 20,
    downloader_id: [],
    path_like: '',
    status: [],
    confidence: [],
    hardlinkCopies: false
  }
  private refreshRequestSeq = 0
  private scanPollTimer: number | null = null
  private scanPollRequestSeq = 0
  private activeScanId: string | null = null
  private scanSubmitting = false
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

  // 选中状态：保存完整行以支持按主导状态启停批量按钮（仅当前页）
  private selectedRows: OrphanTableRow[] = []
  private outerSelectedRows: OrphanFileItem[] = []
  private folderChildSelections: Record<string, OrphanFileItem[]> = {}

  // 按文件夹展示开关（localStorage 持久化）：开启后由后端按直接父目录聚合分页，
  // 同目录下 ≥2 个文件折叠为文件夹行，单文件保持原样。仅影响展示，删除仍按文件 id。
  private folderView = localStorage.getItem(FOLDER_VIEW_STORAGE_KEY) === '1'

  // 副本位置对话框：点击时才扫描配置目录；序号用于丢弃关闭/重开后的过期响应。
  private hardlinkLocationDialogVisible = false
  private hardlinkLocationLoading = false
  private hardlinkLocationResult: HardlinkCopyLocationsResult | null = null
  private hardlinkLocationDialogTitle = '硬链接副本位置'
  private hardlinkLocationRequestSeq = 0

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
  private dismissedLargeScanReminderId: string | null = null

  // 清理对话框
  private cleanupDialogVisible = false
  private cleanupLoading = false
  private cleanupExecuting = false
  private cleanupPreviewData: CleanupPreviewSuccess | null = null
  private previewScanId: string | null = null
  private previewSelection: OrphanSelectionPayload | null = null

  // 快捷操作（左匹配）：下拉 + 前缀输入对话框
  private quickActionDialogVisible = false
  private quickActionType: 'cleanup' | 'ignore' | null = null
  private quickActionPrefix = ''
  private quickActionLoading = false

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
    this.stopScanPolling()
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
        const taskId = res.data.task_id
        const skippedCount = res.data.skipped_count || 0
        if (taskId) {
          const skippedText = skippedCount ? `，跳过处理中 ${skippedCount} 个` : ''
          this.$message.success(
            `彻底删除任务已提交（${taskId.slice(0, 8)}）${skippedText}，完成或失败后将在通知中心提醒`
          )
        } else {
          this.$message.info(res.msg || '所选隔离文件均已在彻底删除任务中处理')
        }
        this.quarantineSelected = []
        const table = this.$refs.quarantineTable as OrphanTableRef | undefined
        table?.clearSelection()
        this.quarantinePage = 1
        await this.loadQuarantineList()
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

  // ==================== 按文件夹展示（后端聚合分页，删除仍按文件）====================

  /**
   * 表格数据源：两种模式都直接消费 list（后端按 group_by_folder 决定返回形态）。
   * 折叠模式 list 元素是 OrphanFolderRow（带 _is_folder/children）或 OrphanFileItem（单文件原样）；
   * 扁平模式 list 元素是 OrphanFileItem。
   */
  private get tableData(): OrphanTableRow[] {
    return this.list
  }

  /** el-table row-key：文件夹行用 folder_key，文件行用 'file:'+id，前缀隔离保唯一稳定。 */
  private getRowKey(row: OrphanTableRow): string {
    return isFolderRow(row) ? row.folder_key : 'file:' + row.id
  }

  /** 文件夹聚合行仅承担展开入口，不参与父表选择。 */
  private getOrphanRowClassName({ row }: { row: OrphanTableRow }): string {
    return isFolderRow(row) ? 'orphan-folder-row' : ''
  }

  private buildCurrentFolderParams(folderPath: string, page: number, pageSize: number) {
    return {
      folder_path: folderPath,
      page,
      page_size: pageSize,
      downloader_id: this.listQuery.downloader_id.length
        ? this.listQuery.downloader_id.join(',')
        : undefined,
      path_like: this.listQuery.path_like || undefined,
      status: this.listQuery.status.length ? this.listQuery.status.join(',') : undefined,
      confidence: this.listQuery.confidence.length
        ? this.listQuery.confidence.join(',')
        : undefined,
      hardlink_copies: this.listQuery.hardlinkCopies ? ('located' as const) : undefined
    }
  }

  private async loadFolderChildren(row: OrphanFolderRow): Promise<void> {
    this.$set(row, 'children_loading', true)
    try {
      const response = await getOrphanFolderChildren(
        this.buildCurrentFolderParams(row.folder_path, row.child_page, row.child_page_size)
      )
      if (response.code === '200' && response.data) {
        this.$set(row, 'children', response.data.list)
        this.$set(row, 'child_ids', response.data.list.map((item) => item.id))
        this.$set(row, 'child_total', response.data.total)
        this.$set(row, 'children_loaded', true)
      } else {
        this.$message.error(response.msg || '加载文件夹子项失败')
      }
    } catch (error) {
      this.$message.error('加载文件夹子项失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      this.$set(row, 'children_loading', false)
    }
  }

  private handleFolderExpandChange(row: OrphanTableRow, expanded: boolean): void {
    if (expanded && isFolderRow(row) && !row.children_loaded && !row.children_loading) {
      void this.loadFolderChildren(row)
    }
  }

  private clearFolderSelection(row: OrphanFolderRow): void {
    this.$delete(this.folderChildSelections, row.folder_key)
    this.syncVisibleSelections()
  }

  private handleFolderChildSelection(row: OrphanFolderRow, items: OrphanFileItem[]): void {
    this.$set(this.folderChildSelections, row.folder_key, items)
    this.syncVisibleSelections()
  }

  private async handleFolderChildPageChange(row: OrphanFolderRow, page: number): Promise<void> {
    this.clearFolderSelection(row)
    this.$set(row, 'child_page', page)
    await this.loadFolderChildren(row)
  }

  private async handleFolderChildPageSizeChange(row: OrphanFolderRow, pageSize: number): Promise<void> {
    this.clearFolderSelection(row)
    this.$set(row, 'child_page', 1)
    this.$set(row, 'child_page_size', pageSize)
    await this.loadFolderChildren(row)
  }

  private get largeScanReminderVisible(): boolean {
    const latest = this.latestAttempt
    return Boolean(
      latest &&
      latest.status === 'completed' &&
      latest.cleanup_review_required &&
      this.dismissedLargeScanReminderId !== latest.scan_id
    )
  }

  private dismissLargeScanReminder(): void {
    const latest = this.latestAttempt
    if (latest) this.dismissedLargeScanReminderId = latest.scan_id
  }

  /** 只有明确大于 0 的副本数量可点击；0 与未知态保持普通文本。 */
  private canOpenHardlinkLocations(row: OrphanTableRow): boolean {
    return typeof row.hardlink_copy_count === 'number' && row.hardlink_copy_count > 0
  }

  private getHardlinkCopyCountTitle(row: OrphanTableRow): string {
    const count = row.hardlink_copy_count
    if (typeof count !== 'number') {
      return isFolderRow(row) ? '展开后仅统计当前可见文件的实时副本数量' : '文件当前不可访问，副本数量未知'
    }
    if (count === 0) return '没有其它硬链接副本'
    return `点击查看 ${count} 个硬链接副本的位置`
  }

  /** 文件夹行只提交当前明确有副本的子项，避免对 0 副本文件做无意义扫描。 */
  private getHardlinkLocationTargets(row: OrphanTableRow): OrphanFileItem[] {
    const items = isFolderRow(row) ? row.children : [row]
    return items.filter(
      (item) => typeof item.hardlink_copy_count === 'number' && item.hardlink_copy_count > 0
    )
  }

  private async handleHardlinkCopyClick(row: OrphanTableRow): Promise<void> {
    const targets = this.getHardlinkLocationTargets(row)
    if (targets.length === 0) return

    const orphanIds = [...new Set(targets.map((item) => item.id))]
    const requestId = this.hardlinkLocationRequestSeq + 1
    this.hardlinkLocationRequestSeq = requestId
    this.hardlinkLocationDialogTitle = isFolderRow(row)
      ? `硬链接副本位置（${targets.length} 个文件）`
      : '硬链接副本位置'
    this.hardlinkLocationDialogVisible = true
    this.hardlinkLocationLoading = true
    this.hardlinkLocationResult = null

    try {
      const response = await getHardlinkCopyLocations({ orphan_ids: orphanIds })
      if (requestId !== this.hardlinkLocationRequestSeq) return
      if (response.code === '200' && response.data) {
        this.hardlinkLocationResult = response.data
      } else {
        this.$message.error(response.msg || '查询硬链接副本位置失败')
      }
    } catch (error) {
      if (requestId !== this.hardlinkLocationRequestSeq) return
      this.$message.error(
        '查询硬链接副本位置失败：' + extractErrorMessage(error, '网络错误')
      )
    } finally {
      if (requestId === this.hardlinkLocationRequestSeq) {
        this.hardlinkLocationLoading = false
      }
    }
  }

  private resetHardlinkLocationDialog(): void {
    this.hardlinkLocationRequestSeq += 1
    this.hardlinkLocationLoading = false
    this.hardlinkLocationResult = null
    this.hardlinkLocationDialogTitle = '硬链接副本位置'
  }

  private async copyHardlinkPath(path: string): Promise<void> {
    try {
      await copyTextToClipboard(path)
      this.$message.success('路径已复制')
    } catch (error) {
      this.$message.error('复制失败：' + extractErrorMessage(error, '当前浏览器不支持剪贴板'))
    }
  }

  /** 切换按文件夹展示：持久化偏好并重新请求后端（数据形态由后端切换）。 */
  private setFolderView(val: boolean): void {
    if (this.folderView === val) return
    this.folderView = val
    localStorage.setItem(FOLDER_VIEW_STORAGE_KEY, val ? '1' : '0')
    this.clearOrphanSelection()
    void this.refreshPageData()
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

  /** 权威选择集：展开文件夹行 child_ids 后的实际文件 id（后端始终收扁平 orphan_ids）。 */
  private get selectedFileIds(): number[] {
    const ids = new Set<number>()
    for (const row of this.selectedRows) {
      if (!isFolderRow(row)) ids.add(row.id)
    }
    return [...ids]
  }

  /**
   * 选中文件对应的完整对象：从 selectedRows 自身展开。
   * - 文件夹行：展开其 children（子文件对象，引用 list 中的原对象）
   * - 文件行：原样
   * 直接从 selectedRows 展开而非反查 list，保证直接赋值 selectedRows 的测试与调用路径语义稳定。
   */
  private get selectedFileItems(): OrphanFileItem[] {
    const items: OrphanFileItem[] = []
    for (const row of this.selectedRows) {
      if (!isFolderRow(row)) items.push(row)
    }
    return items
  }

  private get selectedIds(): number[] {
    return this.selectedFileIds
  }

  private get selectedCount(): number {
    return this.selectedFileIds.length
  }

  private get downloaderOptions(): SelectOption[] {
    return this.downloaderList.map((d) => ({
      value: d.downloader_id,
      label: d.nickname || d.downloader_id
    }))
  }

  /** 置信度筛选选项（值与 OrphanConfidence 联合类型对齐，防拼写漂移）。 */
  private get confidenceOptions(): SelectOption[] {
    return [
      { value: 'high', label: '高置信度' },
      { value: 'low', label: '低置信度' }
    ]
  }

  /** 状态筛选选项（值与 OrphanStatusFilter 联合类型对齐，防拼写漂移）。 */
  private get statusOptions(): SelectOption[] {
    return [
      { value: 'pending', label: '待清理' },
      { value: 'ignored', label: '已忽视' },
      { value: 'deleted', label: '已清理' }
    ]
  }

  /**
   * status 多选退化检测：pending 与 ignored/deleted 同选时，后端 OR 会退化为
   * “所有未删除文件”（pending+ignored 恒真；pending+deleted 含全部未删除+已删除），
   * 结果反直觉，故在 UI 给出提示。
   */
  private get statusFilterDegraded(): boolean {
    const s = this.listQuery.status
    return s.includes('pending') && (s.includes('ignored') || s.includes('deleted'))
  }

  // ========== 批量按钮启停（按选中主导状态，基于展开后的文件）==========

  /** 选中集合中"可清理"的项：待清理（未删除未忽视）。 */
  private get pendingSelection(): OrphanFileItem[] {
    return this.selectedFileItems.filter((r) => !r.is_deleted && !r.is_ignored)
  }

  /** 选中集合中"已忽视"的项。 */
  private get ignoredSelection(): OrphanFileItem[] {
    return this.selectedFileItems.filter((r) => !r.is_deleted && r.is_ignored)
  }

  /** 选中是否全部为待清理态（可清理+可忽视）。 */
  private get allSelectionPending(): boolean {
    return this.selectedFileItems.length > 0 && this.pendingSelection.length === this.selectedFileItems.length
  }

  /** 选中是否全部为已忽视态（可取消忽视）。 */
  private get allSelectionIgnored(): boolean {
    return this.selectedFileItems.length > 0 && this.ignoredSelection.length === this.selectedFileItems.length
  }

  private get canBatchCleanup(): boolean {
    return this.allSelectionPending && this.cleanupAllowed
  }

  private get batchCleanupTitle(): string {
    if (this.selectedCount === 0) return '请先选择待清理文件'
    if (!this.allSelectionPending) return '请勿混选不同状态，仅支持清理"待清理"项'
    return this.cleanupAllowed ? '' : this.cleanupBlockReason
  }

  private get canBatchIgnore(): boolean {
    return this.allSelectionPending
  }

  private get batchIgnoreTitle(): string {
    if (this.selectedCount === 0) return '请先选择待清理文件'
    if (!this.allSelectionPending) return '请勿混选不同状态，仅支持忽视"待清理"项'
    return ''
  }

  private get canBatchUnignore(): boolean {
    return this.allSelectionIgnored
  }

  private get batchUnignoreTitle(): string {
    if (this.selectedCount === 0) return '请先选择已忽视文件'
    if (!this.allSelectionIgnored) return '请勿混选不同状态，仅支持取消"已忽视"项'
    return ''
  }

  private get scanStatusMessage(): string {
    const latest = this.latestAttempt
    if (!latest) return ''
    if (latest.status === 'queued') {
      return '扫描任务已进入后台队列；页面仅轮询轻量状态，列表与清理暂不可用。'
    }
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

  /** 筛选/刷新/每页条数变更入口：回到第 1 页并清空当前页选择。 */
  private async refreshPageData(): Promise<void> {
    this.clearOrphanSelection()
    this.listQuery.page = 1
    await this.loadOrphanPage(1)
  }

  /** 翻页回调：切换页码时清空当前页选择，再加载目标页（传统分页标准行为）。 */
  private async handleOrphanPageChange(page: number): Promise<void> {
    this.clearOrphanSelection()
    this.listQuery.page = page
    await this.loadOrphanPage(page)
  }

  /** 请求一页孤儿文件，整页替换当前列表。 */
  private async loadOrphanPage(page: number): Promise<void> {
    const requestId = ++this.refreshRequestSeq
    const querySnapshot: Readonly<OrphanListQuery> = Object.freeze({
      page,
      page_size: this.listQuery.page_size,
      downloader_id: this.listQuery.downloader_id,
      path_like: this.listQuery.path_like,
      status: this.listQuery.status,
      confidence: this.listQuery.confidence,
      hardlinkCopies: this.listQuery.hardlinkCopies
    })
    this.listLoading = true
    try {
      const params: OrphanListParams = {
        page: querySnapshot.page,
        page_size: querySnapshot.page_size,
        // 多选数组转逗号串（后端按逗号分隔多值过滤）；空数组不传
        downloader_id: querySnapshot.downloader_id.length
          ? querySnapshot.downloader_id.join(',')
          : undefined,
        path_like: querySnapshot.path_like || undefined,
        status: querySnapshot.status.length
          ? querySnapshot.status.join(',')
          : undefined,
        confidence: querySnapshot.confidence.length
          ? querySnapshot.confidence.join(',')
          : undefined,
        hardlink_copies: querySnapshot.hardlinkCopies ? ('located' as const) : undefined,
        group_by_folder: this.folderView || undefined
      }
      const response = await getOrphanList(params)
      if (requestId !== this.refreshRequestSeq) return

      if (response.code === '200' && response.data) {
        this.list = response.data.list
        this.total = response.data.total
        this.scanContext = response.data.scan_context
        const latest = this.scanContext.latest_attempt
        if (
          latest &&
          (latest.status === 'queued' || latest.status === 'running') &&
          this.activeScanId !== latest.scan_id
        ) {
          this.startScanPolling(latest.scan_id)
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
      downloader_id: [],
      path_like: '',
      status: [],
      confidence: [],
      hardlinkCopies: false
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

  /** el-table 原生 selection-change：同步当前页选中行（全选/单选均由此驱动）。 */
  private handleOrphanSelectionChange(rows: OrphanTableRow[]): void {
    this.outerSelectedRows = rows.filter((row): row is OrphanFileItem => !isFolderRow(row))
    this.syncVisibleSelections()
  }

  private syncVisibleSelections(): void {
    const merged: OrphanFileItem[] = [...this.outerSelectedRows]
    Object.keys(this.folderChildSelections).forEach((folderKey) => {
      merged.push(...this.folderChildSelections[folderKey])
    })
    const unique = new Map<number, OrphanFileItem>()
    merged.forEach((item) => unique.set(item.id, item))
    this.selectedRows = [...unique.values()]
  }

  /** 通过 el-table ref 清空选择（翻页/筛选/刷新/切换展示模式时调用）。 */
  private clearOrphanSelection(): void {
    this.selectedRows = []
    this.outerSelectedRows = []
    this.folderChildSelections = {}
    const table = this.$refs.orphanTable as OrphanTableRef | undefined
    table?.clearSelection()
  }

  private buildSelectionPayload(): OrphanSelectionPayload {
    return { orphan_ids: [...this.selectedIds] }
  }

  /**
   * 行是否可勾选。
   * - 文件行：已清理行不可勾选（待清理/已忽视可勾选）
   * - 文件夹行：不可勾选，必须展开后选择当前可见子项
   */
  private rowSelectable(row: OrphanTableRow): boolean {
    if (isFolderRow(row)) return false
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

    this.scanSubmitting = true
    this.scanLoading = true
    try {
      const response = await triggerScan()
      if (response.code === '200' && response.data) {
        const data = response.data
        this.activeScanId = data.scan_id
        this.$message.success(data.accepted ? '扫描任务已提交到后台' : '已有扫描任务，继续跟踪其状态')
        await this.refreshPageData()
        this.startScanPolling(data.scan_id)
      } else {
        this.$message.error(response.msg || '扫描失败')
      }
    } catch (error) {
      this.$message.error('扫描失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      this.scanSubmitting = false
      this.scanLoading = this.activeScanId !== null
    }
  }

  private startScanPolling(scanId: string): void {
    this.stopScanPolling()
    this.activeScanId = scanId
    this.scanLoading = true
    const requestSeq = ++this.scanPollRequestSeq
    const poll = async() => {
      try {
        const response = await getScanStatus(scanId)
        if (requestSeq !== this.scanPollRequestSeq) return
        if (!response.data) {
          this.scanPollTimer = window.setTimeout(poll, 3000)
          return
        }
        const record = response.data
        this.scanContext.latest_attempt = record
        if (record.status === 'queued' || record.status === 'running') {
          this.scanPollTimer = window.setTimeout(poll, 2000)
          return
        }
        this.stopScanPolling()
        if (record.status === 'completed') {
          this.$message.success(
            `扫描完成：孤儿 ${record.total_orphans}，新增明细 ${record.new_orphans}，复用 ${record.known_orphans}`
          )
        } else {
          this.$message.warning(`扫描失败：${record.error_message || '未知错误'}`)
        }
        await this.refreshPageData()
      } catch (error) {
        if (requestSeq !== this.scanPollRequestSeq) return
        this.scanPollTimer = window.setTimeout(poll, 3000)
      }
    }
    void poll()
  }

  private stopScanPolling(): void {
    this.scanPollRequestSeq += 1
    if (this.scanPollTimer !== null) {
      window.clearTimeout(this.scanPollTimer)
      this.scanPollTimer = null
    }
    this.activeScanId = null
    this.scanLoading = this.scanSubmitting
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
        const skippedCount = response.data.skipped_count || 0
        if (taskId) {
          const skippedText = skippedCount ? `，跳过处理中 ${skippedCount} 个` : ''
          this.$message.success(
            `主动清理任务已提交（${taskId.slice(0, 8)}）${skippedText}，完成或失败后将在通知中心提醒`
          )
        } else {
          this.$message.info(response.msg || '所选孤儿文件均已在主动清理任务中处理')
        }
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

  private summarizeIgnoreFailures(data: IgnoreResult): string {
    if (data.error) return data.error
    const reasons = Array.from(
      new Set(data.failed_list.map((item) => item.reason).filter((reason) => Boolean(reason)))
    )
    if (reasons.length === 0) return `${data.failed_count} 个文件未处理`
    const summary = reasons.slice(0, 3).join('；')
    return reasons.length > 3 ? `${summary}；另有 ${reasons.length - 3} 类原因` : summary
  }

  // ========== 快捷操作（左匹配：快捷删除 / 快捷忽视；副本定位筛选切换） ==========

  private handleQuickAction(command: 'cleanup' | 'ignore' | 'toggleLocatedCopies'): void {
    if (command === 'toggleLocatedCopies') {
      // 一键切换"仅看已定位副本"筛选：不走前缀对话框流程，直接回第一页重载
      this.listQuery.hardlinkCopies = !this.listQuery.hardlinkCopies
      this.handleFilter()
      return
    }
    this.quickActionType = command
    this.quickActionPrefix = ''
    this.quickActionDialogVisible = true
  }

  private handleQuickActionCancel(): void {
    this.quickActionDialogVisible = false
  }

  private async handleQuickActionConfirm(): Promise<void> {
    const actionType = this.quickActionType
    if (!actionType) return

    const prefix = (this.quickActionPrefix || '').trim()
    if (!prefix) {
      this.$message.warning('请输入路径前缀')
      return
    }
    const displayScan = this.displayScan
    if (!displayScan) {
      this.$message.warning('当前无可用的成功扫描批次，无法按前缀操作')
      return
    }
    if (actionType === 'cleanup' && !this.cleanupAllowed) {
      this.$message.warning(this.cleanupBlockReason)
      return
    }

    this.quickActionLoading = true
    let preview: PrefixMatchPreviewResult | null = null
    try {
      const resp = await prefixMatchPreview({
        path_prefix: prefix,
        scan_id: displayScan.scan_id
      })
      if (resp.code === '200' && resp.data) {
        preview = resp.data
      } else {
        this.$message.error(resp.msg || '前缀匹配预览失败')
        this.quickActionLoading = false
        return
      }
    } catch (error) {
      this.$message.error('前缀匹配预览失败：' + extractErrorMessage(error, '网络错误'))
      this.quickActionLoading = false
      return
    }

    // scan 过期/未完成：后端返回 rejected，提示原因并保留对话框供用户刷新后重试
    if (preview && preview.rejected === true) {
      this.$message.error(preview.reason || '当前扫描快照不允许操作')
      this.quickActionLoading = false
      return
    }
    if (preview.count === 0) {
      this.$message.warning('没有匹配的待清理文件')
      this.quickActionLoading = false
      return
    }

    // 构造与 cleanup/ignore 共用的选择载荷：select_all + filters（含 status=pending）
    const filters: OrphanSelectionFilters = {
      path_prefix: prefix,
      status: 'pending'
    }
    const scanId = displayScan.scan_id

    // 二次确认（删除文案含总数/大小/低置信度警告；忽视文案含总数）
    const isCleanup = actionType === 'cleanup'
    let confirmText = `将影响 ${preview.count} 个待清理文件`
    if (isCleanup) {
      confirmText += `（共 ${this.formatSize(preview.total_size)}）`
      if (preview.low_confidence_count > 0) {
        confirmText += `\n⚠️ 其中 ${preview.low_confidence_count} 个为低置信度，有误判风险，请核对路径`
      }
      confirmText += '\n\n确认将它们移入隔离区（可恢复）？'
    } else {
      confirmText += '\n\n确认将它们设为忽视（受保护，不再被自动/手动清理）？'
    }

    try {
      await this.$confirm(confirmText, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: isCleanup ? 'warning' : 'info',
        dangerouslyUseHTMLString: false
      })
    } catch {
      // 用户取消：复位 loading，保留对话框与前缀，便于改前缀重试
      this.quickActionLoading = false
      return
    }

    try {
      if (isCleanup) {
        // 直接提交异步清理任务，跳过 cleanupPreview 明细对话框（数量已由 prefix 预览给出）
        const resp = await cleanupOrphans({
          scan_id: scanId,
          select_all: true,
          filters
        })
        if (resp.code === '200' && resp.data) {
          const taskId = resp.data.task_id || ''
          const skippedCount = resp.data.skipped_count || 0
          if (taskId) {
            const skippedText = skippedCount ? `，跳过处理中 ${skippedCount} 个` : ''
            this.$message.success(
              `主动清理任务已提交（${taskId.slice(0, 8)}）${skippedText}，完成或失败后将在通知中心提醒`
            )
          } else {
            this.$message.info(resp.msg || '匹配文件均已在主动清理任务中处理')
          }
          this.quickActionDialogVisible = false
          await this.refreshPageData()
        } else {
          this.$message.error(resp.msg || '清理任务提交失败')
        }
      } else {
        // 快捷忽视：直接调 setIgnored，跳过 applyIgnore 的内置 $confirm（此处已二次确认）
        const resp = await setIgnored({
          scan_id: scanId,
          select_all: true,
          filters,
          ignored: true
        })
        if (resp.code === '200' && resp.data) {
          const data = resp.data
          if (data.rejected === true) {
            this.$message.error(`忽视失败：${this.summarizeIgnoreFailures(data)}`)
          } else if (data.success_count === 0 && data.failed_count > 0) {
            this.$message.error(`忽视失败：${this.summarizeIgnoreFailures(data)}`)
          } else if (data.failed_count > 0) {
            this.$message.warning(
              `忽视部分完成：成功 ${data.success_count} 个，失败 ${data.failed_count} 个；${this.summarizeIgnoreFailures(data)}`
            )
          } else {
            this.$message.success(`忽视完成：成功 ${data.success_count} 个`)
          }
          this.quickActionDialogVisible = false
          await this.refreshPageData()
        } else {
          this.$message.error(resp.msg || '忽视失败')
        }
      }
    } catch (error) {
      this.$message.error(
        (isCleanup ? '清理失败：' : '忽视失败：') + extractErrorMessage(error, '网络错误')
      )
    } finally {
      this.quickActionLoading = false
    }
  }

  private formatSize(size: number): string {
    return formatFileSize(size)
  }

  private formatHardlinkCopyCount(count: number | null | undefined): string {
    return typeof count === 'number' ? String(count) : '-'
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

  .orphan-hardlink-copy-count {
    font-variant-numeric: tabular-nums;
  }

  /* 副本定位筛选复选框：与筛选区 el-input 默认高度对齐（容器按底边对齐） */
  .orphan-located-copies-checkbox {
    display: inline-flex;
    align-items: center;
    height: 40px;
  }

  .orphan-hardlink-copy-count--link {
    margin: 0;
    padding: 2px 8px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-primary);
    cursor: pointer;
    font: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;

    &:hover,
    &:focus-visible {
      background: rgba(var(--color-primary-rgb), 0.08);
      outline: none;
    }
  }

  /* 列表固定可视高度，配合分页器按页切换。 */
  .orphan-table-scroll {
    height: 520px;
    max-height: calc(100vh - 430px);
    min-height: 300px;
    overflow: hidden;

    ::v-deep .management-table {
      min-width: 0;
    }
  }

  .quarantine-table-scroll {
    ::v-deep .management-table {
      min-width: 920px;
    }
  }

  /* 分页区：左侧每页条数与总数，右侧翻页器。 */
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

  .orphan-folder-children {
    padding: var(--spacing-sm) var(--spacing-md) var(--spacing-md);
    background: var(--color-bg-secondary);

    &__pagination {
      display: flex;
      justify-content: flex-end;
      margin-top: var(--spacing-md);
    }
  }

  // Element UI 的 expand 列会为文件夹模式中的普通文件也生成箭头；
  // 普通文件没有懒加载子项，只允许聚合文件夹行展开。
  ::v-deep .management-table .el-table__body tr:not(.orphan-folder-row) .el-table__expand-icon {
    visibility: hidden;
    pointer-events: none;
  }
}

.hardlink-location-content {
  min-height: 120px;
}

.hardlink-location-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  margin: var(--spacing-md) 0;
  color: var(--color-text-secondary);

  strong {
    color: var(--color-text-primary);
  }
}

.hardlink-location-alert {
  margin-bottom: var(--spacing-md);
}

.hardlink-location-list {
  display: grid;
  gap: var(--spacing-md);
  margin-top: var(--spacing-md);
}

.hardlink-location-item {
  padding: var(--spacing-md);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);

  &__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--spacing-md);
    margin-bottom: var(--spacing-sm);
  }

  &__source {
    min-width: 0;
    color: var(--color-text-primary);
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  &__metrics {
    display: inline-flex;
    flex-shrink: 0;
    gap: var(--spacing-xs);
  }
}

.hardlink-location-copies {
  display: grid;
  gap: var(--spacing-xs);
}

.hardlink-location-copy {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  background: var(--color-bg-primary);

  &__path {
    min-width: 0;
    flex: 1 1 auto;
    color: var(--color-text-primary);
    font-family: Consolas, Monaco, monospace;
    font-size: 12px;
    overflow-wrap: anywhere;
  }

  &__button {
    flex-shrink: 0;
  }
}

.hardlink-location-empty,
.hardlink-location-unlocated {
  margin: var(--spacing-xs) 0 0;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.hardlink-location-unlocated {
  color: var(--color-warning);
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

// 按文件夹展示：文件夹聚合行单元格
// 用 inline-flex 作为内容容器（宽度跟随内容），由外层 .orphan-path-cell .cell 统一管理
// 与树展开箭头（.el-table__expand-icon）的对齐。
.orphan-folder-cell {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  gap: 6px;

  > .el-icon-folder {
    color: var(--color-warning, #e6a23c);
    flex-shrink: 0;
  }

  &__path {
    // 路径过长时省略，hover 时由 title 属性显示完整路径
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    // 关键：flex 子项默认 min-width: auto，不允许收缩到内容尺寸以下。
    // 设为 0 才能在 flex 容器内收缩并显示省略号，保证文件数标签始终可见。
    min-width: 0;
    flex: 0 1 auto;
  }

  &__count {
    flex-shrink: 0;
  }
}

// 文件路径列：让树展开箭头（.el-table__expand-icon）与单元格内容在同一水平线。
// element-ui 把箭头作为 .cell 的前置兄弟插入，默认 inline-block 且垂直对齐基线不一致，
// 加上 .orphan-folder-cell 是 inline-flex，会导致箭头与内容错行/错位。
// 将 .cell 设为横向 flex、垂直居中，箭头不收缩，内容区占据剩余宽度并内部再省略。
::v-deep .orphan-path-cell .cell {
  display: flex;
  align-items: center;
  width: 100%;

  > .el-table__expand-icon {
    flex-shrink: 0;
  }

  // 内容容器（orphan-folder-cell 或单文件 span）占据剩余空间
  > .orphan-folder-cell,
  > span:not(.el-table__expand-icon) {
    flex: 1 1 auto;
    min-width: 0;
  }
}

// 路径模糊搜索框：尺寸/圆角/字号对齐同筛选区 AdvancedMultiSelect 触发器（32px/4px/12px），
// 与下载器/状态/置信度三个下拉框视觉等高。
.orphan-path-input {
  ::v-deep .el-input__inner {
    height: 32px;
    line-height: 32px;
    font-size: 12px;
    border-radius: 4px;
  }
}
</style>
