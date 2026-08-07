<template>
  <div class="app-container file-management-page">
    <!-- 页面标题（BEM 范式，对齐 orphan-files） -->
    <div class="management-page__header">
      <h2 class="management-page__title">
        <LucideIcon name="folder" :size="20" />种子文件管理
      </h2>
      <p class="management-page__subtitle">管理种子文件备份，支持去重、导出、导入操作</p>
    </div>

    <!-- ========== 筛选区域（BEM 范式，复用 management-list-page.scss 全局样式） ========== -->
    <section class="management-panel" aria-label="种子文件筛选条件">
      <div class="management-filter">
        <div class="management-filter__field">
          <label class="management-filter__label" for="file-search">任务名称 / Info Hash</label>
          <el-input
            id="file-search"
            v-model="listQuery.search"
            class="management-filter__control file-mgmt-input"
            placeholder="搜索任务名称或Info Hash..."
            prefix-icon="el-icon-search"
            clearable
            @keyup.enter.native="handleFilter"
            @clear="handleFilter"
          />
        </div>

        <div class="management-filter__field">
          <label class="management-filter__label" for="file-downloader">下载器</label>
          <el-select
            id="file-downloader"
            v-model="listQuery.downloader_id"
            class="management-filter__control file-mgmt-input"
            placeholder="全部下载器"
            clearable
            @change="handleFilter"
          >
            <el-option
              v-for="downloader in downloaderList"
              :key="downloader.downloader_id"
              :label="downloader.downloader_name"
              :value="downloader.downloader_id"
            />
          </el-select>
        </div>

        <div class="management-filter__field management-filter__field--wide">
          <label class="management-filter__label" for="file-date">创建时间</label>
          <el-date-picker
            id="file-date"
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            class="management-filter__control file-mgmt-input file-mgmt-daterange"
            value-format="yyyy-MM-dd"
            clearable
            @change="handleDateChange"
          />
        </div>

        <div class="management-filter__actions file-mgmt-actions">
          <el-button type="primary" icon="el-icon-search" @click="handleFilter">搜索</el-button>
          <el-button icon="el-icon-refresh-left" @click="resetFilter">重置</el-button>
        </div>
      </div>
    </section>

    <!-- ========== 批量操作工具栏 ========== -->
    <section class="batch-operations">
      <!-- 去重 -->
      <batch-button
        type="warning"
        icon="el-icon-delete"
        tooltip="去重"
        :disabled="selectedItems.length === 0"
        @click="handleDeduplicate"
      />

      <!-- 导出 -->
      <batch-button
        type="success"
        icon="el-icon-download"
        tooltip="导出"
        :disabled="selectedItems.length === 0"
        @click="handleExport"
      />

      <!-- 导入 -->
      <batch-button
        type="primary"
        icon="el-icon-upload2"
        tooltip="导入"
        @click="handleImport"
      />
    </section>

    <!-- ========== 表格区域 ========== -->
    <el-table
      v-loading="listLoading"
      :data="list"
      element-loading-text="加载中..."
      border
      fit
      highlight-current-row
      style="width: 100%; margin-top: 20px;"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="55" />

      <el-table-column label="任务名称" min-width="200" show-overflow-tooltip>
        <template slot-scope="{row}">
          <span>{{ row.task_name || row.torrent_name || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="Info Hash" min-width="120" show-overflow-tooltip>
        <template slot-scope="{row}">
          <span style="font-family: monospace; font-size: 12px;">{{ row.info_hash }}</span>
        </template>
      </el-table-column>

      <el-table-column label="下载器" width="150" show-overflow-tooltip>
        <template slot-scope="{row}">
          <span>{{ getDownloaderName(row.downloader_id) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="上传时间" width="160" align="center">
        <template slot-scope="{row}">
          <span>{{ formatTime(row.created_at) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="最后更新" width="160" align="center">
        <template slot-scope="{row}">
          <span>{{ formatTime(row.updated_at) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="150" align="center" fixed="right">
        <template slot-scope="{row}">
          <el-tooltip content="详情" placement="top">
            <el-button
              type="info"
              size="mini"
              icon="el-icon-info"
              circle
              @click="handleDetail(row)"
            />
          </el-tooltip>
          <el-tooltip content="下载" placement="top">
            <el-button
              type="success"
              size="mini"
              icon="el-icon-download"
              circle
              @click="handleDownload(row)"
            />
          </el-tooltip>
          <el-tooltip content="删除" placement="top">
            <el-button
              type="danger"
              size="mini"
              icon="el-icon-delete"
              circle
              @click="handleDelete(row)"
            />
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- ========== 分页组件 ========== -->
    <pagination
      v-show="total > 0"
      :total="total"
      :page.sync="listQuery.page"
      :limit.sync="listQuery.pageSize"
      @pagination="handlePageChange"
    />

    <!-- ========== 详情对话框 ========== -->
    <el-dialog
      title="种子文件详情"
      :visible.sync="detailDialogVisible"
      width="600px"
    >
      <el-descriptions :column="1" border>
        <el-descriptions-item label="任务名称">
          {{ currentDetail.task_name || currentDetail.torrent_name || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="Info Hash">
          <span style="font-family: monospace;">{{ currentDetail.info_hash }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="下载器">
          {{ getDownloaderName(currentDetail.downloader_id) }}
        </el-descriptions-item>
        <el-descriptions-item label="文件路径">
          {{ currentDetail.file_path || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="上传时间">
          {{ formatTime(currentDetail.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="最后更新">
          {{ formatTime(currentDetail.updated_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="上传用户">
          {{ currentDetail.uploader_username || '-' }}
        </el-descriptions-item>
      </el-descriptions>

      <div slot="footer" class="dialog-footer">
        <el-button @click="detailDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="handleDownload(currentDetail)">下载文件</el-button>
      </div>
    </el-dialog>

    <!-- ========== 导入对话框 ========== -->
    <el-dialog
      title="批量导入种子文件"
      :visible.sync="importDialogVisible"
      width="500px"
    >
      <el-form :model="importForm" label-width="100px">
        <el-form-item label="目标下载器">
          <el-select
            v-model="importForm.downloader_id"
            placeholder="请选择下载器"
            style="width: 100%;"
          >
            <el-option
              v-for="downloader in downloaderList"
              :key="downloader.downloader_id"
              :label="downloader.downloader_name"
              :value="downloader.downloader_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="种子文件">
          <el-upload
            ref="upload"
            :action="uploadUrl"
            :headers="uploadHeaders"
            :on-success="handleUploadSuccess"
            :on-error="handleUploadError"
            :on-change="handleFileChange"
            :auto-upload="false"
            :file-list="fileList"
            multiple
            accept=".torrent"
            drag
          >
            <i class="el-icon-upload"></i>
            <div class="el-upload__text">
              将文件拖到此处，或<em>点击上传</em>
            </div>
            <div slot="tip" class="el-upload__tip">
              只能上传 .torrent 文件，支持批量上传
            </div>
          </el-upload>
        </el-form-item>
      </el-form>

      <div slot="footer" class="dialog-footer">
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importLoading" @click="handleConfirmImport">
          确定导入
        </el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import Pagination from '@/components/Pagination/index.vue'
import BatchButton from '@/components/BatchButton/index.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'
import waves from '@/directive/waves'
import { getToken } from '@/utils/cookies'
import {
  getTorrentBackupList,
  deduplicateTorrentBackup,
  deleteTorrentBackup,
  importTorrentBackup,
  TorrentBackup,
  getDownloaderList
} from '@/api/torrents'
import service from '@/utils/request'

interface ListQuery {
  page: number
  pageSize: number
  search: string
  downloader_id: number | null
  startTime: string
  endTime: string
}

@Component({
  name: 'FileManagement',
  directives: { waves },
  components: { Pagination, BatchButton, LucideIcon }
})
export default class FileManagement extends Vue {
  // 列表数据
  list: TorrentBackup[] = []
  total = 0
  listLoading = false

  // 查询参数
  listQuery: ListQuery = {
    page: 1,
    pageSize: 20,
    search: '',
    downloader_id: null,
    startTime: '',
    endTime: ''
  }

  // 日期范围
  dateRange: string[] = []

  // 下载器列表
  downloaderList: any[] = []

  // 选中的项目
  selectedItems: TorrentBackup[] = []

  // 详情对话框
  detailDialogVisible = false
  currentDetail: Partial<TorrentBackup> = {}

  // 导入对话框
  importDialogVisible = false
  importForm = {
    downloader_id: null as number | null
  }
  fileList: any[] = []
  importLoading = false

  // 上传配置
  get uploadUrl() {
    return `${process.env.VUE_APP_BASE_API}/torrents/backup/import?downloader_id=${this.importForm.downloader_id}`
  }

  get uploadHeaders() {
    return {
      'x-access-token': getToken()
    }
  }

  mounted() {
    this.fetchDownloaderList()
    this.fetchList()
  }

  // 获取下载器列表
  async fetchDownloaderList() {
    try {
      const res = await getDownloaderList()
      if (res.code === '200') {
        this.downloaderList = res.data.list || []
      }
    } catch (error) {
      console.error('获取下载器列表失败:', error)
    }
  }

  // 获取种子文件备份列表
  async fetchList() {
    this.listLoading = true
    try {
      const params: any = {
        page: this.listQuery.page,
        pageSize: this.listQuery.pageSize
      }

      if (this.listQuery.downloader_id) {
        params.downloader_id = this.listQuery.downloader_id
      }

      const res = await getTorrentBackupList(params)
      if (res.code === '200') {
        const data = res.data || {}
        this.list = Array.isArray(data.list) ? data.list : []
        this.total = typeof data.total === 'number' ? data.total : 0

        // 客户端搜索过滤
        if (this.listQuery.search) {
          const searchLower = this.listQuery.search.toLowerCase()
          this.list = this.list.filter(item =>
            (item.task_name && item.task_name.toLowerCase().includes(searchLower)) ||
            (item.info_hash && item.info_hash.toLowerCase().includes(searchLower))
          )
        }

        // 客户端时间过滤
        if (this.listQuery.startTime && this.listQuery.endTime) {
          const startTime = new Date(this.listQuery.startTime).getTime()
          const endTime = new Date(this.listQuery.endTime).getTime()
          this.list = this.list.filter(item => {
            const itemTime = new Date(item.created_at).getTime()
            return itemTime >= startTime && itemTime <= endTime
          })
        }
      }
    } catch (error) {
      console.error('获取种子文件列表失败:', error)
      this.$message.error('获取数据失败')
    } finally {
      this.listLoading = false
    }
  }

  // 搜索过滤
  handleFilter() {
    this.listQuery.page = 1
    this.fetchList()
  }

  // 重置过滤
  resetFilter() {
    this.listQuery = {
      page: 1,
      pageSize: 20,
      search: '',
      downloader_id: null,
      startTime: '',
      endTime: ''
    }
    this.dateRange = []
    this.fetchList()
  }

  // 日期范围变化
  handleDateChange(value: string[]) {
    if (value && value.length === 2) {
      this.listQuery.startTime = value[0]
      this.listQuery.endTime = value[1]
    } else {
      this.listQuery.startTime = ''
      this.listQuery.endTime = ''
    }
  }

  // 分页变化
  handlePageChange(pagination: any) {
    this.listQuery.page = pagination.page
    this.listQuery.pageSize = pagination.limit
    this.fetchList()
  }

  // 选择变化
  handleSelectionChange(selection: TorrentBackup[]) {
    this.selectedItems = selection
  }

  // 刷新列表
  handleRefresh() {
    this.fetchList()
  }

  // 去重
  async handleDeduplicate() {
    try {
      const res = await deduplicateTorrentBackup()
      if (res.code === '200') {
        this.$message.success(res.msg || '操作成功')
        this.fetchList()
      } else {
        this.$message.error(res.msg || res.data?.msg || '去重失败')
      }
    } catch (error) {
      console.error('去重失败:', error)
      this.$message.error('去重失败')
    }
  }

  // 导出
  async handleExport() {
    if (this.selectedItems.length === 0) {
      this.$message.warning('请先选择要导出的种子文件')
      return
    }

    try {
      const infoHashes = this.selectedItems.map(item => item.info_hash).join(',')
      const url = `${process.env.VUE_APP_BASE_API}/torrents/backup/export?info_hashes=${encodeURIComponent(infoHashes)}`

      // 创建隐藏的下载链接
      const link = document.createElement('a')
      link.href = url
      link.download = `torrent_backup_${new Date().getTime()}.zip`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)

      this.$message.success('导出成功')
    } catch (error) {
      console.error('导出失败:', error)
      this.$message.error('导出失败')
    }
  }

  // 导入
  handleImport() {
    this.importForm.downloader_id = null
    this.fileList = []
    this.importDialogVisible = true
  }

  // 文件变化
  handleFileChange(file: any, fileList: any[]) {
    this.fileList = fileList
  }

  // 确认导入
  // 确认导入
  async handleConfirmImport() {
    if (!this.importForm.downloader_id) {
      this.$message.warning('请选择目标下载器')
      return
    }

    if (this.fileList.length === 0) {
      this.$message.warning('请选择要导入的种子文件')
      return
    }

    this.importLoading = true
    try {
      const files = this.fileList
        .map(f => f?.raw)
        .filter(Boolean) as File[]
      if (files.length === 0) {
        this.$message.error('请选择有效文件')
        return
      }
      if (this.importForm.downloader_id === undefined) {
        this.$message.error('请选择下载器')
        return
      }
      const res = await importTorrentBackup(this.importForm.downloader_id, files)

      if (res.code === '200') {
        this.$message.success(res.msg)
        this.importDialogVisible = false
        this.fetchList()

        // 显示导入结果详情
        const failedItems = res.data?.failed_items
        if (Array.isArray(failedItems) && failedItems.length > 0) {
          const failedList = failedItems.map((item: any) => `${item.filename}: ${item.reason}`).join('\n')
          this.$message.warning({
            message: `部分文件导入失败:\n${failedList}`,
            duration: 5000,
            showClose: true
          } as any)
        }
      } else {
        this.$message.error(res.msg || '导入失败')
      }
    } catch (error) {
      console.error('导入失败:', error)
      this.$message.error('导入失败')
    } finally {
      this.importLoading = false
    }
  }

  // 上传成功（未使用，使用手动上传）
  handleUploadSuccess(response: any, _file: any, _fileList: any[]) {
    console.log('Upload success:', response)
  }

  // 上传失败
  handleUploadError(error: any) {
    console.error('Upload error:', error)
    this.$message.error('上传失败')
  }

  // 详情
  handleDetail(row: TorrentBackup) {
    this.currentDetail = row
    this.detailDialogVisible = true
  }

  // 下载单个文件（使用Axios + Blob模式，支持Token认证）
  async handleDownload(row: TorrentBackup) {
    try {
      // 发送GET请求，携带token，指定响应类型为blob
      const response = await service({
        url: `/torrents/backup/download/${row.info_hash}`,
        method: 'get',
        responseType: 'blob'  // 关键：指定响应类型为blob
      })

      // 创建Blob对象
      const blob = new Blob([response], {
        type: 'application/x-bittorrent'
      })

      // 创建Blob URL
      const blobUrl = window.URL.createObjectURL(blob)

      // 创建下载链接
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = `${row.task_name || row.info_hash}.torrent`
      document.body.appendChild(link)
      link.click()

      // 清理资源
      document.body.removeChild(link)
      window.URL.revokeObjectURL(blobUrl)

      this.$message.success('下载成功')
    } catch (error: any) {
      console.error('下载失败:', error)

      // 处理错误响应
      if (error.response) {
        // 服务器返回了错误状态码
        const status = error.response.status
        if (status === 401) {
          this.$message.error('认证失败，请重新登录')
        } else if (status === 404) {
          this.$message.error('种子文件不存在')
        } else {
          this.$message.error(`下载失败: ${status}`)
        }
      } else if (error.request) {
        // 请求已发出但没有收到响应
        this.$message.error('网络错误，请检查网络连接')
      } else {
        // 其他错误
        this.$message.error('下载失败，请稍后重试')
      }
    }
  }

  // 删除
  handleDelete(row: TorrentBackup) {
    this.$confirm('确认删除该种子文件备份吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async() => {
      try {
        const res = await deleteTorrentBackup(row.info_hash)
        if (res.code === '200') {
          this.$message.success('删除成功')
          this.fetchList()
        } else {
          this.$message.error(res.msg || res.data?.msg || '删除失败')
        }
      } catch (error) {
        console.error('删除失败:', error)
        this.$message.error('删除失败')
      }
    }).catch(() => {
      // 用户取消
    })
  }

  // 获取下载器名称
  getDownloaderName(downloaderId: number) {
    const downloader = this.downloaderList.find(d => d.downloader_id === downloaderId)
    return downloader ? downloader.downloader_name : `下载器${downloaderId}`
  }

  // 格式化时间
  formatTime(time: string) {
    if (!time) return '-'
    const date = new Date(time)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }
}
</script>

<style lang="scss" scoped>
.file-management-page {
  padding: 20px;
}

// 三控件统一高度对齐（修复重构前的高度不齐问题）。
// orphan-files 的等高前提是 AdvancedMultiSelect 自带 32px；本页改用 el-select/el-date-picker，
// 无法自动等高，需用 ::v-deep 统一压到 32px（参照 orphan-files .orphan-path-input）。
.file-mgmt-input {
  ::v-deep .el-input__inner {
    // 命中 el-input 与 el-select（内部同为 .el-input__inner）
    height: 32px;
    line-height: 32px;
    font-size: 12px;
    border-radius: 4px;
  }

  // 命中 el-date-picker 外壳（.el-input__inner 选择器无法命中 .el-range-editor）
  ::v-deep .el-range-editor {
    height: 32px;
  }

  ::v-deep .el-range-input {
    font-size: 12px;
  }
}

// 搜索/重置按钮紧跟控件（覆盖全局 .management-filter__actions 的 margin-left:auto，
// 避免 field 较少时按钮被推到面板最右留出大段空白）。
.file-mgmt-actions {
  margin-left: 0 !important;
}

// 日期范围选择器精简版修复：确保"至"分隔符与清除图标在窄宽下不被遮挡。
// （management-filter__field--wide 的 flex-basis:320px 仍可能挤压 daterange，故保留必要修正。）
.file-mgmt-daterange {
  ::v-deep .el-range-separator {
    padding: 0 8px;
    min-width: 24px;
    line-height: 32px;
  }

  ::v-deep .el-range-input {
    flex: 1;
    min-width: 0;
  }
}

.batch-operations {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
  padding: 10px;
  background-color: #f5f7fa;
  border-radius: 4px;
  align-items: flex-start;
}

.el-table {
  ::v-deep .el-table__header-wrapper {
    thead {
      // 统一主题色渐变背景（与回收站保持一致）
      background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light)) !important;
      border-bottom: 2px solid var(--color-primary);
    }

    th {
      // 关键：使用 fixed 让渐变相对于视口固定，所有单元格共享同一个渐变源
      background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light)) !important;
      background-attachment: fixed !important;
      color: white !important;
      font-weight: 600;

      // Table header top-left border radius
      &:first-child {
        border-top-left-radius: 12px;
      }

      // Table header top-right border radius
      &:last-child {
        border-top-right-radius: 12px;
      }
    }

    // 移除单元格之间的边框，使渐变看起来是连续的
    th.el-table__cell {
      border-right: none;
    }
  }
}
</style>
