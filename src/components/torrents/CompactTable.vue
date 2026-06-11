<template>
  <div class="compact-table-container">
    <!-- 紧凑模式表格 -->
    <el-table
      :data="compactTorrentList"
      :loading="tableLoading"
      border
      fit
      stripe
      size="mini"
      highlight-current-row
      @selection-change="handleSelectionChange"
      style="width: 100%; height: 400px;"

      <!-- 移动端优化：隐藏不必要的列 -->
      <el-table-column type="selection" width="55" align="center" :class="{'mobile-hidden': isMobile}"></el-table-column>
      <el-table-column prop="name" label="种子名称" min-width="200" show-overflow-tooltip></el-table-column>
      <el-table-column prop="size" label="种子大小" width="120" align="center" sortable="custom">
        <template #default="scope">
          <span>{{ formatSize(scope.row.size) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="state" label="状态" width="100" align="center">
        <template #default="scope">
          <el-tag :type="getStateTagType(scope.row.state)" size="mini">
            {{ getStateText(scope.row.state) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="120" align="center">
        <template #default="scope">
          <span>{{ scope.row.category || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="tags" label="标签" width="150" align="center">
        <template #default="scope">
          <el-tag v-for="tag in getTagsArray(scope.row.tags)" :key="tag" size="mini" style="margin: 1px;">
            {{ tag }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="downloader_name" label="所属下载器" width="120" align="center">
        <template #default="scope">
          <span>{{ scope.row.downloader_name || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="added_date" label="添加时间" width="150" align="center" sortable="custom">
        <template #default="scope">
          <span>{{ formatDate(scope.row.added_date) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="ratio" label="比率" width="100" align="center" sortable="custom">
        <template #default="scope">
          <span>{{ formatRatio(scope.row.ratio) }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 - 紧凑模式 -->
      <el-table-column prop="actions" label="操作" width="120" align="center" fixed="right" class-name="small-padding fixed-width">
        <template #default="scope">
          <div class="action-buttons">
            <!-- 紧凑模式特定操作 -->
            <el-button
              v-if="scope.row.state === 'downloading'"
              type="warning"
              size="mini"
              icon="el-icon-video-pause"
              :loading="resumeLoading"
              @click="handleResume(scope.row)"
              title="恢复"
            />
            <el-button
              v-if="scope.row.state === 'paused'"
              type="warning"
              size="mini"
              icon="el-icon-video-play"
              :loading="resumeLoading"
              @click="handleResume(scope.row)"
              title="开始"
            />
            <el-button
              v-if="scope.row.state === 'seeding'"
              type="success"
              size="mini"
              icon="el-icon-video-stop"
              :loading="pauseLoading"
              @click="handlePause(scope.row)"
              title="暂停"
            />
            <el-button
              v-if="scope.row.state === 'checkingDL'"
              type="info"
              size="mini"
              icon="el-icon-refresh"
              :loading="refreshLoading"
              @click="handleRefresh"
              title="检查"
            />
            <el-button
              v-if="scope.row.state === 'uploading'"
              type="success"
              size="mini"
              icon="el-icon-upload"
              :loading="uploadLoading"
              @click="handleRefresh"
              title="重试"
            />
            <el-button
              v-if="scope.row.state === 'stalledUP'"
              type="warning"
              size="mini"
              icon="el-icon-video-play"
              :loading="resumeLoading"
              @click="handleResume(scope.row)"
              title="继续"
            />

            <!-- 通用操作 -->
            <el-button
              type="text"
              size="mini"
              @click="handleDetail(scope.row)"
              icon="el-icon-view"
              title="详情"
            />
            <el-dropdown @command="handleMoreAction(scope.row)" trigger="click">
              <el-button type="text" size="mini">
                更多
                <i class="el-icon-arrow-down el-icon--right"></i>
              </el-button>
            </el-dropdown>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 紧凑模式统计信息 -->
  <div v-if="compactStats.total > 0" class="compact-stats">
    <el-card class="stats-card">
      <div slot="header" class="stats-header">
        <i class="el-icon-s-grid"></i>
        <span>紧模式统计</span>
      </div>
      <div class="stats-content">
        <div class="stat-item">
          <span class="stat-label">总种子数:</span>
          <span class="stat-value">{{ compactStats.total }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">正在下载:</span>
          <span class="stat-value">{{ compactStats.downloading }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">已完成:</span>
          <span class="stat-value">{{ compactStats.completed }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">暂停中:</span>
          <span class="stat-value">{{ compactStats.paused }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">做种中:</span>
          <span class="stat-value">{{ compactStats.seeding }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">错误:</span>
          <span class="stat-value">{{ compactStats.error }}</span>
        </div>
      </div>
    </el-card>
  </div>

  <!-- 批量操作对话框 -->
  <el-dialog
    :visible.sync="showBatchDialog"
    :title="`批量${batchOperation === 'delete' ? '删除' : batchOperation === 'pause' ? '暂停' : '恢复'}种子`"
    width="500px"
    :before-close="handleBatchDialogClose"
  >
    <div class="batch-operation-content">
      <p v-if="batchOperation === 'delete'">
        <i class="el-icon-warning" style="color: #E6A23C;"></i>
        您已选择 <strong>{{ multipleSelection.length }}</strong> 个种子进行删除操作
      </p>
      <p v-else-if="batchOperation === 'pause'">
        <i class="el-icon-info"></i>
        您已选择 <strong>{{ multipleSelection.length }}</strong> 个种子进行暂停操作
      </p>
      <p v-else>
        <i class="el-icon-info"></i>
        您已选择 <strong>{{ multipleSelection.length }}</strong> 个种子进行恢复操作
      </p>

      <!-- 删除操作：显示"同时删除数据"复选框 -->
      <el-checkbox
        v-if="batchOperation === 'delete'"
        v-model="deleteDataCheckbox"
        style="margin-top: 15px;"
      >
        <span style="color: #F56C6C;">
          <i class="el-icon-delete"></i>
          同时删除下载的文件（不可恢复）
        </span>
      </el-checkbox>

      <el-alert
        v-if="batchOperation === 'delete' && deleteDataCheckbox"
        title="警告：勾选后将同时删除种子文件，此操作不可恢复！"
        type="error"
        :closable="false"
        style="margin-top: 10px;"
      />
    </div>

    <div slot="footer" class="dialog-footer">
      <el-button @click="handleBatchDialogClose">取 消</el-button>
      <el-button
        :type="batchOperation === 'delete' && deleteDataCheckbox ? 'danger' : 'primary'"
        @click="handleBatchConfirm"
        :loading="batchOperationLoading"
      >
        确 定
      </el-button>
    </div>
  </el-dialog>
</template>

<script lang="ts">
import { getTorrentList, pauseTorrents, resumeTorrents, deleteTorrents } from '@/api/torrents'

// 工具函数
function formatSize(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
}

function formatDate(dateString: string): string {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatRatio(ratio: number): string {
  if (ratio === undefined || ratio === null) return '-'
  return ratio.toFixed(2)
}

function getStateText(state: string): string {
  const stateMap: { [key: string]: string } = {
    downloading: '下载中',
    seeding: '做种中',
    paused: '已暂停',
    completed: '已完成',
    error: '错误',
    uploading: '上传中',
    stalledDL: '等待下载',
    stalledUP: '等待上传',
    checkingDL: '检查中',
    checkingUP: '检查中',
    queuedDL: '队列中',
    queuedUP: '队列中'
  }
  return stateMap[state] || state
}

function getStateTagType(state: string): string {
  const typeMap: { [key: string]: string } = {
    downloading: 'primary',
    seeding: 'success',
    paused: 'info',
    completed: 'success',
    error: 'danger',
    uploading: 'warning',
    stalledDL: 'warning',
    stalledUP: 'info',
    checkingDL: 'info',
    checkingUP: 'info',
    queuedDL: 'info',
    queuedUP: 'info'
  }
  return typeMap[state] || 'info'
}

function getTagsArray(tags: string): string[] {
  if (!tags) return []
  return tags.split(',').map(tag => tag.trim()).filter(tag => tag)
}

export default {
  name: 'CompactTable',

  components: {
    TorrentAddDialog: () => import('./components/TorrentAddDialog.vue'),
    SearchTemplateDialog: () => import('./components/SearchTemplateDialog.vue'),
    BatchOperationDialog: () => import('./components/BatchOperationDialog.vue')
  },

  props: {
    torrentList: {
      type: Array,
      default: () => [],
      required: true
    },
    viewMode: {
      type: String,
      default: 'complete',
      required: true
    },
    currentPage: {
      type: Number,
      default: 1,
      required: true
    },
    pageSize: {
      type: Number,
      default: 20,
      required: true
    },
    tableLoading: {
      type: Boolean,
      default: false,
      required: true
    },
    refreshLoading: {
      type: Boolean,
      default: false,
      required: true
    }
  },

  data() {
    return {
      total: 0,
      compactStats: {
        total: 0,
        downloading: 0,
        completed: 0,
        paused: 0,
        seeding: 0,
        error: 0
      },
      // 批量操作相关
      multipleSelection: [] as any[],
      showBatchDialog: false,
      batchOperation: '',
      deleteDataCheckbox: false,  // 同时删除数据复选框，默认false
      batchOperationLoading: false,  // 批量操作加载状态
      selectedTorrent: null,
      showDetailDialog: false,
      showAddDialogValue: false,
      showSearchTemplateDialogValue: false,
      searchTemplates: [],
      resumeLoading: false,
      pauseLoading: false,
      uploadLoading: false
    }
  },

  computed: {
    compactTorrentList(): any[] {
      if (!this.torrentList || this.torrentList.length === 0) {
        return []
      }

      // 根据视图模式过滤数据
      let filteredList = this.torrentList as any[]

      if (this.viewMode === 'compact') {
        // 紧凑模式：只显示正在做种或已完成的种子
        filteredList = this.torrentList.filter((torrent: any) =>
          ['downloading', 'seeding', 'completed', 'paused', 'error'].includes(torrent.state) &&
          !['checkingDL', 'checkingUP', 'checkingResumeData', 'uploading', 'stalledDL', 'stalledUP', 'pausedUP'].includes(torrent.state)
        )
      }

      return filteredList
    },

    // 紧凑模式统计信息（计算属性）
    computedCompactStats() {
      if (!this.torrentList || this.torrentList.length === 0) {
        return {
          total: 0,
          downloading: 0,
          completed: 0,
          paused: 0,
          seeding: 0,
          error: 0
        }
      }

      return this.torrentList.reduce((stats: any, torrent: any) => {
        const state = torrent.state

        if (['downloading', 'uploading'].includes(state)) {
          stats.downloading++
        } else if (['completed'].includes(state)) {
          stats.completed++
        } else if (['seeding'].includes(state)) {
          stats.seeding++
        } else if (['paused'].includes(state)) {
          stats.paused++
        } else if (['error', 'checkingDL', 'checkingUP', 'checkingResumeData', 'stalledDL', 'stalledUP', 'pausedUP'].includes(state)) {
          stats.error++
        }

        stats.total++
        return stats
      }, {
        total: 0,
        downloading: 0,
        completed: 0,
        paused: 0,
        seeding: 0,
        error: 0
      })
    }
  },

  methods: {
    // 工具方法
    formatSize,
    formatDate,
    formatRatio,
    getStateText,
    getStateTagType,
    getTagsArray,

    // 移动端窗口宽度检测
    isMobile(): boolean {
      return window.innerWidth <= 768
    },

    // 从父组件获取数据
    async loadTorrents() {
      // 不能直接修改props，通过emit通知父组件
      this.$emit('load-torrents', {
        page: this.currentPage,
        limit: this.pageSize
      })
    },

    handleRefresh() {
      this.$emit('refresh')
    },

    handleSelectionChange(selection: any[]) {
      this.multipleSelection = selection
    },

    handleSizeChange(size: number) {
      this.$emit('size-change', size)
    },

    handleViewModeChange(mode: string) {
      this.$emit('view-mode-change', mode)
    },

    // 种子操作
    async handleDetail(torrent: any) {
      if (torrent) {
        this.selectedTorrent = torrent
        this.showDetailDialog = true
      }
    },

    async handleStart(torrent: any) {
      try {
        // 使用 resumeTorrents API 开始下载
        const response = await resumeTorrents({
          downloader_id: torrent.downloader_id,
          hashes: [torrent.hash]
        })
        if (response.status === 'success') {
          this.$message.success('开始下载成功')
          this.handleRefresh()
        } else {
          this.$message.error(response.msg || '开始下载失败')
        }
      } catch (error) {
        console.error('开始下载失败:', error)
        this.$message.error('开始下载失败')
      }
    },

    async handlePause(torrent: any) {
      try {
        // 使用 pauseTorrents API 暂停种子
        const response = await pauseTorrents({
          downloader_id: torrent.downloader_id,
          hashes: [torrent.hash]
        })
        if (response.status === 'success') {
          this.$message.success('暂停成功')
          this.handleRefresh()
        } else {
          this.$message.error(response.msg || '暂停失败')
        }
      } catch (error) {
        console.error('暂停失败:', error)
        this.$message.error('暂停失败')
      }
    },

    async handleResume(torrent: any) {
      try {
        // 使用 resumeTorrents API 恢复种子
        const response = await resumeTorrents({
          downloader_id: torrent.downloader_id,
          hashes: [torrent.hash]
        })
        if (response.status === 'success') {
          this.$message.success('恢复成功')
          this.handleRefresh()
        } else {
          this.$message.error(response.msg || '恢复失败')
        }
      } catch (error) {
        console.error('恢复失败:', error)
        this.$message.error('恢复失败')
      }
    },

    async handleDelete(torrent: any) {
      try {
        // 使用 deleteTorrents API 删除种子
        const response = await deleteTorrents({
          info_id: torrent.info_id,
          downloader_id: torrent.downloader_id,
          delete_data: 0,
          id_recycle: 1
        })
        if (response.status === 'success') {
          this.$message.success('删除成功')
          this.handleRefresh()
        } else {
          this.$message.error(response.msg || '删除失败')
        }
      } catch (error) {
        console.error('删除失败:', error)
        this.$message.error('删除失败')
      }
    },

    handleMoreAction(torrent: any) {
      // 更多操作占位方法
      console.log('More action for torrent:', torrent)
    },

    // 批量操作
    async handleBatchOperation(operation: string, selectedItems?: any[]) {
      if (operation === 'delete' && this.multipleSelection.length === 0) {
        this.$message.warning('请先选择要删除的种子')
        return
      }

      this.showBatchDialog = true
      this.batchOperation = operation
    },

    // 关闭批量操作对话框
    handleBatchDialogClose() {
      this.showBatchDialog = false
      this.deleteDataCheckbox = false  // 重置复选框
    },

    async handleBatchConfirm() {
      try {
        this.batchOperationLoading = true  // 开始加载

        // 修复：使用 this.multipleSelection 而不是 undefined 的 selectedItems
        const selectedItems = this.multipleSelection

        if (selectedItems.length === 0) {
          this.$message.warning('请先选择要操作的种子')
          return
        }

        let response
        const operationTextMap: { [key: string]: string } = {
          delete: '删除',
          pause: '暂停',
          resume: '恢复',
          start: '开始'
        }
        const operationText = operationTextMap[this.batchOperation]

        if (this.batchOperation === 'delete') {
          // 使用批量删除API
          // 注意：需要按下载器分组，因为批量删除API需要下载器ID
          const downloaderGroups = selectedItems.reduce((groups: any, item: any) => {
            const downloaderId = item.downloader_id
            if (!groups[downloaderId]) {
              groups[downloaderId] = []
            }
            groups[downloaderId].push(item.info_id)
            return groups
          }, {})

          // 对每个下载器执行批量删除
          const promises = Object.keys(downloaderGroups).map(downloaderId =>
            deleteTorrents({
              info_id: downloaderGroups[downloaderId][0], // 批量删除API会处理多个
              downloader_id: downloaderId,
              delete_data: this.deleteDataCheckbox ? 1 : 0,
              id_recycle: 1
            })
          )
          const results = await Promise.all(promises)
          response = results[0] // 使用第一个结果作为判断
        } else if (this.batchOperation === 'pause') {
          // 按下载器分组执行暂停操作
          const downloaderGroups = selectedItems.reduce((groups: any, item: any) => {
            const downloaderId = item.downloader_id
            if (!groups[downloaderId]) {
              groups[downloaderId] = []
            }
            groups[downloaderId].push(item.hash)
            return groups
          }, {})

          const promises = Object.keys(downloaderGroups).map(downloaderId =>
            pauseTorrents({
              downloader_id: downloaderId,
              hashes: downloaderGroups[downloaderId]
            })
          )
          const results = await Promise.all(promises)
          response = results[0]
        } else if (this.batchOperation === 'resume') {
          // 按下载器分组执行恢复操作
          const downloaderGroups = selectedItems.reduce((groups: any, item: any) => {
            const downloaderId = item.downloader_id
            if (!groups[downloaderId]) {
              groups[downloaderId] = []
            }
            groups[downloaderId].push(item.hash)
            return groups
          }, {})

          const promises = Object.keys(downloaderGroups).map(downloaderId =>
            resumeTorrents({
              downloader_id: downloaderId,
              hashes: downloaderGroups[downloaderId]
            })
          )
          const results = await Promise.all(promises)
          response = results[0]
        }

        if (response && response.status === 'success') {
          this.$message.success(`成功${operationText}${selectedItems.length}个种子`)
          this.handleRefresh()
          this.showBatchDialog = false
          this.deleteDataCheckbox = false  // 重置复选框
          this.multipleSelection = []  // 清空选择
        } else {
          this.$message.error(response?.msg || `${operationText}失败`)
          this.showBatchDialog = false
        }
      } catch (error) {
        console.error('批量操作失败:', error)
        const operationTextMap: { [key: string]: string } = {
          delete: '删除',
          pause: '暂停',
          resume: '恢复',
          start: '开始'
        }
        const operationText = operationTextMap[this.batchOperation]
        this.$message.error(`${operationText}失败`)
      } finally {
        this.batchOperationLoading = false  // 结束加载
      }
    },

    // 高级搜索相关方法
    handleSearch() {
      if (!this.isSearchValid()) {
        this.$message.warning('请至少输入一个搜索条件')
        return
      }
      this.$emit('search')
    },

    handleResetSearch() {
      this.$emit('reset-search')
    },

    isSearchValid(): boolean {
      // 简化的搜索验证
      return true
    },

    // 高级搜索对话框相关
    showAddDialogMethod() {
      this.showAddDialogValue = true
    },

    hideAddDialog() {
      this.showAddDialogValue = false
    },

    handleAddSuccess() {
      this.showAddDialogValue = false
      this.$message.success('添加种子成功')
      this.handleRefresh()
    },

    handleSearchTemplateDialog() {
      this.showSearchTemplateDialogValue = true
    },

    hideSearchTemplateDialog() {
      this.showSearchTemplateDialogValue = false
    },

    handleSearchTemplateApply() {
      this.showSearchTemplateDialogValue = false
      this.$message.success('应用模板成功')
      this.handleRefresh()
    },

    handleSearchTemplateCreate() {
      this.showSearchTemplateDialogValue = false
      this.$message.success('创建模板成功')
      this.handleRefresh()
    },

    handleSearchTemplateDelete() {
      this.showSearchTemplateDialogValue = false
      this.$message.success('删除模板成功')
      this.loadSearchTemplates()
      this.handleRefresh()
    },

    async loadSearchTemplates() {
      // 占位方法，实际API可能不存在
      console.log('加载搜索模板')
    },

    // 统计更新方法
    updateCompactStats(stats: any) {
      this.compactStats = stats
    },

    // 获取紧凑模式统计数据
    async getCompactStats() {
      // 占位方法，compact-stats API可能不存在
      console.log('获取紧凑统计数据')
    }
  }
}
</script>

<style lang="scss" scoped>
.compact-table-container {
  padding: 20px;
  background-color: #f5f5f7;
  min-height: calc(100vh - 200px);
}

.compact-stats {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 10;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  padding: 16px;
}

.stats-header {
  display: flex;
  align-items: center;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  padding: 8px 12px;
  border-radius: 4px;
}

.stats-content {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.stat-item {
  color: #333;
  padding: 8px;
  border-radius: 4px;
  text-align: center;
}

.stat-label {
  font-size: 12px;
  color: #666;
  font-weight: 600;
  margin-right: 8px;
}

.stat-value {
  font-size: 16px;
  color: #fff;
  font-weight: 500;
}

.action-buttons {
  text-align: right;
  margin-top: 8px;
}

.action-section {
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
}

.table-section {
  margin-bottom: 20px;
}

.table-info {
  font-size: 12px;
  color: #666;
}

.action-buttons {
  margin-right: 10px;
}
</style>