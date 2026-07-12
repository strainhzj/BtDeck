<template>
  <div class="orphan-files-container">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-item">
            <div class="stat-label">孤儿文件数</div>
            <div class="stat-value">{{ latestScan ? latestScan.total_orphans : 0 }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-item">
            <div class="stat-label">总大小</div>
            <div class="stat-value">{{ formatSize(latestScan ? latestScan.total_orphan_size : 0) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-item">
            <div class="stat-label">扫描路径数</div>
            <div class="stat-value">{{ latestScan ? latestScan.total_paths_scanned : 0 }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-item">
            <div class="stat-label">最近扫描</div>
            <div class="stat-value stat-time">{{ latestScan ? formatTime(latestScan.scan_time) : '未扫描' }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 工具栏 -->
    <div class="filter-container">
      <el-input
        v-model="listQuery.downloader_id"
        placeholder="下载器ID筛选"
        style="width: 200px"
        class="filter-item"
        clearable
        @keyup.enter.native="handleFilter"
        @clear="handleFilter"
      />
      <el-button class="filter-item" type="primary" icon="el-icon-search" @click="handleFilter">
        搜索
      </el-button>
      <el-button class="filter-item" icon="el-icon-refresh" @click="getList">
        刷新
      </el-button>
      <el-button
        class="filter-item"
        type="success"
        icon="el-icon-magic-stick"
        :loading="scanLoading"
        @click="handleScan"
      >
        立即扫描
      </el-button>
      <el-button
        class="filter-item"
        type="danger"
        icon="el-icon-delete"
        :disabled="selectedIds.length === 0"
        @click="handleCleanupPreview"
      >
        清理选中 ({{ selectedIds.length }})
      </el-button>
    </div>

    <!-- 孤儿文件列表 -->
    <el-table
      v-loading="listLoading"
      :data="list"
      border
      fit
      highlight-current-row
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

    <!-- 分页 -->
    <el-pagination
      class="pagination-container"
      :current-page="listQuery.page"
      :page-size="listQuery.page_size"
      :total="total"
      :page-sizes="[10, 20, 50, 100]"
      layout="total, sizes, prev, pager, next, jumper"
      @size-change="handleSizeChange"
      @current-change="handleCurrentChange"
    />

    <!-- 清理确认对话框 -->
    <el-dialog
      title="清理确认"
      :visible.sync="cleanupDialogVisible"
      width="500px"
      :close-on-click-modal="false"
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
  getLatestScan,
  getOrphanList,
  triggerScan,
  cleanupPreview,
  cleanupOrphans,
  OrphanFileItem,
  LatestScanResult,
  CleanupPreviewResult,
  CleanupResult
} from '@/api/orphan-files'
import { formatFileSize, formatDate, extractErrorMessage } from '@/utils/formatters'

@Component({ name: 'OrphanFiles' })
export default class OrphanFiles extends Vue {
  private list: OrphanFileItem[] = []
  private total = 0
  private listLoading = false
  private scanLoading = false
  private listQuery = {
    page: 1,
    page_size: 20,
    downloader_id: ''
  }

  // 选中状态
  private selectedIds: number[] = []

  // 最新扫描结果
  private latestScan: LatestScanResult | null = null

  // 清理对话框
  private cleanupDialogVisible = false
  private cleanupLoading = false
  private cleanupExecuting = false
  private cleanupPreviewData: CleanupPreviewResult | null = null
  private cleanupResult: CleanupResult | null = null
  private previewScanId: string | null = null

  mounted() {
    this.getList()
    this.getLatestScan()
  }

  private async getList() {
    this.listLoading = true
    try {
      const response = await getOrphanList({
        page: this.listQuery.page,
        page_size: this.listQuery.page_size,
        downloader_id: this.listQuery.downloader_id || undefined
      })
      if (response.code === '200' && response.data) {
        this.list = response.data.list || []
        this.total = response.data.total || 0
      } else {
        this.$message.error(response.msg || '获取列表失败')
      }
    } catch (error) {
      this.$message.error('获取孤儿文件列表失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      this.listLoading = false
    }
  }

  private async getLatestScan() {
    try {
      const response = await getLatestScan()
      if (response.code === '200' && response.data) {
        this.latestScan = response.data
      }
    } catch (error) {
      // 静默失败，不影响列表展示
      console.warn('获取最新扫描结果失败:', error)
    }
  }

  private handleFilter() {
    this.listQuery.page = 1
    this.getList()
  }

  private handleSizeChange(size: number) {
    this.listQuery.page_size = size
    this.listQuery.page = 1
    this.getList()
  }

  private handleCurrentChange(page: number) {
    this.listQuery.page = page
    this.getList()
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
          this.$message.success(
            `扫描完成: 发现 ${data.total_orphans || 0} 个孤儿文件`
          )
        } else {
          this.$message.warning(`扫描状态: ${data.status}, ${data.error || data.message || ''}`)
        }
        await this.getLatestScan()
        await this.getList()
      } else {
        this.$message.error(response.msg || '扫描失败')
      }
    } catch (error) {
      this.$message.error('扫描失败：' + extractErrorMessage(error, '网络错误'))
    } finally {
      this.scanLoading = false
    }
  }

  private async handleCleanupPreview() {
    if (this.selectedIds.length === 0) {
      this.$message.warning('请先选择要清理的文件')
      return
    }

    this.cleanupDialogVisible = true
    this.cleanupPreviewData = null
    this.cleanupResult = null
    this.previewScanId = null
    this.cleanupLoading = true

    try {
      if (!this.latestScan || !this.latestScan.scan_id) {
        this.$message.warning('没有可用的最新扫描批次，请先刷新或重新扫描')
        this.cleanupDialogVisible = false
        return
      }
      this.previewScanId = this.latestScan.scan_id
      const response = await cleanupPreview({
        scan_id: this.previewScanId,
        orphan_ids: this.selectedIds
      })
      if (response.code === '200' && response.data) {
        this.cleanupPreviewData = response.data
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
        orphan_ids: this.selectedIds
      })
      if (response.code === '200' && response.data) {
        this.cleanupResult = response.data
        // 刷新列表
        await this.getList()
        await this.getLatestScan()
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
.orphan-files-container {
  padding: 20px;

  .stats-row {
    margin-bottom: 20px;

    .stat-item {
      text-align: center;

      .stat-label {
        font-size: 14px;
        color: #909399;
        margin-bottom: 8px;
      }

      .stat-value {
        font-size: 24px;
        font-weight: bold;
        color: #303133;
      }

      .stat-time {
        font-size: 14px;
        font-weight: normal;
      }
    }
  }

  .filter-container {
    margin-bottom: 20px;

    .filter-item {
      margin-right: 10px;
    }
  }

  .pagination-container {
    margin-top: 20px;
    text-align: right;
  }

  .cleanup-result {
    margin-top: 15px;
  }
}
</style>
