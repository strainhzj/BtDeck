<template>
  <div class="app-container management-page audit-logs-container">
    <header class="management-page__header" aria-labelledby="audit-logs-title">
      <div class="management-page__heading">
        <h1 id="audit-logs-title" class="management-page__title">操作日志</h1>
        <p class="management-page__subtitle">检索关键操作记录，核对执行结果并导出留档</p>
      </div>
    </header>

    <!-- 筛选区域 -->
    <CollapsiblePanel
      title="筛选日志"
      description="可组合名称、类型、操作人、结果与时间范围进行查询"
      storage-key="btdeck_audit_filter_collapsed"
    >
      <template #meta>
        <el-tag type="info" effect="plain">共 {{ total }} 条</el-tag>
      </template>
      <div class="management-filter audit-filter-grid">
        <div class="management-filter__field">
          <label class="management-filter__label" for="audit-torrent-name">种子名称</label>
          <el-input
            id="audit-torrent-name"
            v-model="listQuery.torrent_name"
            class="management-filter__control"
            placeholder="支持模糊搜索"
            prefix-icon="el-icon-search"
            clearable
            @keyup.enter.native="handleFilter"
          />
        </div>
        <div class="management-filter__field">
          <label class="management-filter__label" for="audit-operation-type">操作类型</label>
          <el-select
            id="audit-operation-type"
            v-model="listQuery.operation_type"
            class="management-filter__control"
            placeholder="全部类型"
            clearable
            filterable
          >
            <el-option label="全部类型" value="" />
            <el-option-group label="种子管理">
              <el-option label="新增种子" value="add" />
              <el-option label="种子转移" value="transfer" />
              <el-option label="等级4删除（待删除）" value="delete_l4" />
              <el-option label="等级3删除（回收站）" value="delete_l3" />
              <el-option label="等级2删除（保留数据）" value="delete_l2" />
              <el-option label="等级1删除（完全删除）" value="delete_l1" />
              <el-option label="还原种子" value="restore" />
            </el-option-group>
            <el-option-group label="下载器操作">
              <el-option label="添加下载器" value="downloader_add" />
              <el-option label="删除下载器" value="downloader_delete" />
              <el-option label="修改下载器" value="downloader_update" />
              <el-option label="测试下载器" value="downloader_test" />
            </el-option-group>
            <el-option-group label="定时任务">
              <el-option label="添加定时任务" value="scheduled_task_add" />
              <el-option label="删除定时任务" value="scheduled_task_delete" />
              <el-option label="修改定时任务" value="scheduled_task_update" />
              <el-option label="执行定时任务" value="scheduled_task_execute" />
              <el-option label="中断定时任务" value="scheduled_task_interrupt" />
            </el-option-group>
            <el-option-group label="关键词规则">
              <el-option label="添加关键词规则" value="keyword_rule_add" />
              <el-option label="删除关键词规则" value="keyword_rule_delete" />
              <el-option label="修改关键词规则" value="keyword_rule_update" />
            </el-option-group>
          </el-select>
        </div>
        <div class="management-filter__field audit-filter-field--operator">
          <label class="management-filter__label" for="audit-operator">操作人</label>
          <el-input
            id="audit-operator"
            v-model="listQuery.operator"
            class="management-filter__control"
            placeholder="全部操作人"
            clearable
            @keyup.enter.native="handleFilter"
          />
        </div>
        <div class="management-filter__field audit-filter-field--result">
          <label class="management-filter__label" for="audit-operation-result">操作结果</label>
          <el-select
            id="audit-operation-result"
            v-model="listQuery.operation_result"
            class="management-filter__control"
            placeholder="全部结果"
            clearable
          >
            <el-option label="全部" value="" />
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="部分成功" value="partial" />
          </el-select>
        </div>
        <div class="management-filter__field management-filter__field--wide audit-filter-field--time">
          <label class="management-filter__label" for="audit-date-range">操作时间</label>
          <el-date-picker
            id="audit-date-range"
            v-model="dateRange"
            class="management-filter__control"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="yyyy-MM-dd HH:mm:ss"
            @change="handleDateRangeChange"
          />
        </div>
        <div class="management-filter__actions audit-search-actions">
          <el-button v-waves type="primary" icon="el-icon-search" @click="handleFilter">
            搜索
          </el-button>
          <el-button icon="el-icon-refresh-left" @click="resetFilter">重置</el-button>
        </div>
      </div>
    </CollapsiblePanel>

    <!-- 数据操作栏 -->
    <section class="management-panel audit-action-panel" aria-labelledby="audit-actions-title">
      <div class="audit-action-bar">
        <div class="audit-action-bar__heading">
          <span class="audit-action-bar__icon" aria-hidden="true"><i class="el-icon-setting" /></span>
          <div>
            <h2 id="audit-actions-title" class="audit-action-bar__title">日志操作</h2>
            <p class="audit-action-bar__description">导出当前筛选结果，或归档历史数据</p>
          </div>
        </div>
        <div class="audit-action-bar__actions">
          <el-dropdown @command="handleExport">
            <el-button type="success" icon="el-icon-download">
              导出 <i class="el-icon-arrow-down el-icon--right" />
            </el-button>
            <el-dropdown-menu slot="dropdown">
              <el-dropdown-item command="csv">导出为 CSV</el-dropdown-item>
              <el-dropdown-item command="excel">导出为 Excel</el-dropdown-item>
            </el-dropdown-menu>
          </el-dropdown>
          <el-button type="warning" icon="el-icon-folder" @click="showArchiveDialog">
            归档历史日志
          </el-button>
          <el-button icon="el-icon-refresh" @click="refreshStatistics">刷新统计</el-button>
        </div>
      </div>
    </section>

    <!-- 统计信息卡片 -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="6">
        <el-card class="statistics-card" shadow="hover">
          <div class="statistics-item">
            <i class="el-icon-document" style="font-size: 32px; color: #409EFF;" />
            <div class="statistics-content">
              <div class="statistics-value">{{ statistics.total_count || 0 }}</div>
              <div class="statistics-label">总日志数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="statistics-card" shadow="hover">
          <div class="statistics-item">
            <i class="el-icon-success" style="font-size: 32px; color: #67C23A;" />
            <div class="statistics-content">
              <div class="statistics-value">{{ statistics.result_stats?.success || 0 }}</div>
              <div class="statistics-label">成功操作</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="statistics-card" shadow="hover">
          <div class="statistics-item">
            <i class="el-icon-error" style="font-size: 32px; color: #F56C6C;" />
            <div class="statistics-content">
              <div class="statistics-value">{{ statistics.result_stats?.failed || 0 }}</div>
              <div class="statistics-label">失败操作</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="statistics-card" shadow="hover">
          <div class="statistics-item">
            <i class="el-icon-date" style="font-size: 32px; color: #E6A23C;" />
            <div class="statistics-content">
              <div class="statistics-value">{{ getTodayLogsCount() }}</div>
              <div class="statistics-label">今日操作</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 审计日志表格 -->
    <div class="table-container" v-loading="listLoading">
      <table class="audit-table">
        <thead>
          <tr>
            <th style="width: 180px;">操作类型</th>
            <th style="width: 100px;">操作人</th>
            <th style="width: 200px;">种子名称</th>
            <th style="width: 150px;">下载器名称</th>
            <th style="width: 160px;">操作时间</th>
            <th style="width: 100px;">结果</th>
            <th style="width: 140px;">IP地址</th>
            <th style="width: 100px;">操作</th>
          </tr>
        </thead>
        <tbody v-if="list.length > 0">
          <tr
            v-for="log in list"
            :key="log.log_id"
            @click="handleRowClick(log)"
            :class="{'current-row': currentRow === log}"
          >
            <td>
              <span
                class="operation-tag"
                :class="getOperationClass(log.operation_type)"
              >
                {{ getOperationTypeName(log.operation_type) }}
              </span>
            </td>
            <td>{{ log.operator }}</td>
            <td>
              <span v-if="log.torrent_name" class="torrent-name-tag">
                {{ truncateText(log.torrent_name, 30) }}
              </span>
              <span v-else style="color: #c0c4cc;">-</span>
            </td>
            <td>
              <span v-if="log.downloader_name" class="downloader-name-tag">
                {{ truncateText(log.downloader_name, 20) }}
              </span>
              <span v-else style="color: #c0c4cc;">-</span>
            </td>
            <td>{{ formatDateTime(log.operation_time) }}</td>
            <td>
              <span
                class="result-badge"
                :class="log.operation_result"
              >
                {{ getResultName(log.operation_result) }}
              </span>
            </td>
            <td>{{ log.ip_address || '-' }}</td>
            <td>
              <el-button
                type="text"
                size="small"
                icon="el-icon-view"
                @click.stop="handleViewDetail(log)"
              >
                详情
              </el-button>
            </td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr>
            <td :colspan="8" class="empty-cell">
              <div class="empty-state">
                <i class="el-icon-document" style="font-size: 64px; margin-bottom: 20px; display: block;" />
                <p class="empty-state-text">暂无审计日志</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-show="total > 0"
          background
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
          :current-page.sync="listQuery.page"
          :page-sizes="[10, 20, 50, 100]"
          :page-size.sync="listQuery.page_size"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
        />
      </div>
    </div>

    <!-- 详情对话框 -->
    <el-dialog
      title="审计日志详情"
      :visible.sync="detailDialogVisible"
      width="70%"
      :close-on-click-modal="false"
      class="audit-detail-dialog"
    >
      <div v-if="currentLog" class="detail-content">
        <!-- 基本信息 -->
        <div class="detail-section">
          <h4 class="detail-section-title">基本信息</h4>
          <el-row :gutter="20">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">操作类型：</span>
                <span class="detail-value">
                  <el-tag
                    :type="getOperationTagType(currentLog.operation_type)"
                    size="small"
                  >
                    {{ getOperationTypeName(currentLog.operation_type) }}
                  </el-tag>
                </span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">操作人：</span>
                <span class="detail-value">{{ currentLog.operator }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">操作时间：</span>
                <span class="detail-value">{{ formatDateTime(currentLog.operation_time) }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">操作结果：</span>
                <span class="detail-value">
                  <el-tag
                    :type="getResultTagType(currentLog.operation_result)"
                    size="small"
                  >
                    {{ getResultName(currentLog.operation_result) }}
                  </el-tag>
                </span>
              </div>
            </el-col>
          </el-row>
          <el-row :gutter="20" v-if="currentLog.torrent_name || currentLog.downloader_name">
            <el-col :span="12" v-if="currentLog.torrent_name">
              <div class="detail-item">
                <span class="detail-label">种子名称：</span>
                <span class="detail-value">{{ currentLog.torrent_name }}</span>
              </div>
            </el-col>
            <el-col :span="12" v-if="currentLog.downloader_name">
              <div class="detail-item">
                <span class="detail-label">下载器名称：</span>
                <span class="detail-value">{{ currentLog.downloader_name }}</span>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 调试信息 -->
        <div class="detail-section">
          <h4 class="detail-section-title">调试信息</h4>
          <el-row :gutter="20">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">IP地址：</span>
                <span class="detail-value">{{ currentLog.ip_address || '-' }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">User-Agent：</span>
                <span class="detail-value">{{ currentLog.user_agent || '-' }}</span>
              </div>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">请求ID：</span>
                <span class="detail-value">{{ currentLog.request_id || '-' }}</span>
              </div>
            </el-col>
            <el-col :span="12">
              <div class="detail-item">
                <span class="detail-label">会话ID：</span>
                <span class="detail-value">{{ currentLog.session_id || '-' }}</span>
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- 操作详情 -->
        <div class="detail-section" v-if="currentLog.operation_detail">
          <h4 class="detail-section-title">操作详情</h4>
          <div class="json-viewer">
            {{ formatJson(currentLog.operation_detail) }}
          </div>
        </div>

        <!-- 旧值 -->
        <div class="detail-section" v-if="currentLog.old_value">
          <h4 class="detail-section-title">修改前（旧值）</h4>
          <div class="json-viewer">
            {{ formatJson(currentLog.old_value) }}
          </div>
        </div>

        <!-- 新值 -->
        <div class="detail-section" v-if="currentLog.new_value">
          <h4 class="detail-section-title">修改后（新值）</h4>
          <div class="json-viewer">
            {{ formatJson(currentLog.new_value) }}
          </div>
        </div>

        <!-- 错误信息 -->
        <div class="detail-section" v-if="currentLog.error_message">
          <h4 class="detail-section-title">错误信息</h4>
          <el-alert
            :title="currentLog.error_message"
            type="error"
            :closable="false"
          />
        </div>
      </div>

      <span slot="footer" class="dialog-footer">
        <el-button @click="detailDialogVisible = false">关闭</el-button>
        <el-button type="primary" icon="el-icon-document-copy" @click="handleCopyJson">复制 JSON</el-button>
      </span>
    </el-dialog>

    <!-- 归档对话框 -->
    <el-dialog
      title="归档审计日志"
      :visible.sync="archiveDialogVisible"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-alert
        title="归档说明"
        type="warning"
        :closable="false"
        style="margin-bottom: 20px;"
      >
        归档功能会将指定时间之前的审计日志导出到独立的JSON文件，并从主数据库中删除这些日志。归档后的日志将无法在查询界面中显示，但可以通过归档文件查看。
      </el-alert>

      <el-form :model="archiveForm" label-width="120px">
        <el-form-item label="归档截止时间" required>
          <el-date-picker
            v-model="archiveForm.end_time"
            type="datetime"
            placeholder="选择日期时间"
            value-format="yyyy-MM-dd HH:mm:ss"
            style="width: 100%;"
          />
          <div style="font-size: 12px; color: #909399; margin-top: 5px;">
            此时间之前的审计日志将被归档
          </div>
        </el-form-item>

        <el-form-item label="归档文件名">
          <el-input
            v-model="archiveForm.archive_path"
            placeholder="留空则自动生成"
          />
          <div style="font-size: 12px; color: #909399; margin-top: 5px;">
            仅接受文件名（自动追加 .json 后缀），固定保存到：data/audit_logs_archive/
          </div>
        </el-form-item>
      </el-form>

      <span slot="footer" class="dialog-footer">
        <el-button @click="archiveDialogVisible = false">取消</el-button>
        <el-button type="warning" icon="el-icon-folder-checked" :loading="archiveLoading" @click="handleConfirmArchive">
          确认归档
        </el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import {
  queryAuditLogs,
  getAuditLogStatistics,
  exportAuditLogs,
  downloadExportFile,
  archiveAuditLogs,
  AuditLogArchiveRequest,
  AuditLogItem,
  AuditLogQueryRequest,
  AuditLogStatisticsResponse
} from '@/api/audit-logs'
import { copyTextToClipboard } from '@/utils/clipboard'

interface AuditLogListQuery extends AuditLogQueryRequest {
  torrent_name: string
  operation_type: string
  operator: string
  operation_result: string
  start_time: string
  end_time: string
  page: number
  page_size: number
}

function createDefaultListQuery(): AuditLogListQuery {
  return {
    torrent_name: '',
    operation_type: '',
    operator: '',
    operation_result: '',
    start_time: '',
    end_time: '',
    page: 1,
    page_size: 20
  }
}

@Component({
  name: 'AuditLogs'
})
export default class AuditLogs extends Vue {
  // 列表数据
  list: AuditLogItem[] = []
  total = 0
  listLoading = false
  currentRow: AuditLogItem | null = null

  // 查询参数
  listQuery: AuditLogListQuery = createDefaultListQuery()

  // 日期范围
  dateRange: string[] | null = null

  // 统计信息
  statistics: AuditLogStatisticsResponse = {
    total_count: 0,
    operation_type_stats: {},
    operator_stats: {},
    result_stats: {}
  }

  // 对话框
  detailDialogVisible = false
  archiveDialogVisible = false
  currentLog: AuditLogItem | null = null

  // 归档表单
  archiveForm: AuditLogArchiveRequest = {
    end_time: '',
    archive_path: ''
  }
  archiveLoading = false

  // 表格key
  tableKey = 0

  mounted() {
    this.getList()
    this.getStatistics()
  }

  // 获取列表
  async getList() {
    this.listLoading = true
    try {
      const response = await queryAuditLogs(this.listQuery)

      // 增强的响应结构验证
      if (!response) {
        throw new Error('API返回为空')
      }

      if (response.code === '200') {
        // 安全的数据提取
        const data = response.data || {}
        this.list = Array.isArray(data.list) ? data.list : []
        this.total = typeof data.total === 'number' ? data.total : 0
      } else {
        this.$message.error(response.msg || '查询失败')
        // 失败时降级到空状态
        this.list = []
        this.total = 0
      }
    } catch (error) {
      console.error('查询审计日志失败:', error)

      // 降级到空状态
      this.list = []
      this.total = 0

      this.$message.error('查询审计日志失败')
    } finally {
      this.listLoading = false
    }
  }

  // 获取统计信息
  async getStatistics() {
    try {
      const response = await getAuditLogStatistics()

      // 响应验证
      if (response && response.code === '200' && response.data) {
        this.statistics = {
          total_count: typeof response.data.total_count === 'number' ? response.data.total_count : 0,
          operation_type_stats: response.data.operation_type_stats || {},
          operator_stats: response.data.operator_stats || {},
          result_stats: response.data.result_stats || {}
        }
      } else {
        // 保持默认值，不更新统计
        console.warn('获取统计信息失败：响应格式异常')
      }
    } catch (error) {
      console.error('获取统计信息失败:', error)
      // 保持当前统计值不变
    }
  }

  // 搜索
  handleFilter() {
    this.listQuery.page = 1
    this.getList()
  }

  // 重置筛选
  resetFilter() {
    this.listQuery = createDefaultListQuery()
    this.dateRange = null
    this.getList()
  }

  // 日期范围变化
  handleDateRangeChange(value: string[] | null) {
    if (value && value.length === 2) {
      this.listQuery.start_time = value[0]
      this.listQuery.end_time = value[1]
    } else {
      this.listQuery.start_time = ''
      this.listQuery.end_time = ''
    }
  }

  // 分页大小变化
  handleSizeChange(val: number) {
    this.listQuery.page_size = val
    this.getList()
  }

  // 当前页变化
  handleCurrentChange(val: number) {
    this.listQuery.page = val
    this.getList()
  }

  // 行点击
  handleRowClick(row: AuditLogItem) {
    this.currentRow = row
  }

  // 查看详情
  handleViewDetail(row: AuditLogItem) {
    this.currentLog = row
    this.detailDialogVisible = true
  }

  // 导出
  async handleExport(command: string) {
    try {
      const exportRequest = {
        ...this.listQuery,
        export_format: command as 'csv' | 'excel',
        max_rows: 10000
      }
      const response = await exportAuditLogs(exportRequest)
      if (response && response.code === '200' && response.data) {
        this.$message.success(`正在导出为 ${command.toUpperCase()}...`)
        // 下载文件：走统一 axios 客户端（认证头/续期链路），成功后前端触发保存
        const fileName = response.data.file_name
        if (fileName) {
          const blob = await downloadExportFile(fileName)
          const url = window.URL.createObjectURL(blob as unknown as Blob)
          const link = document.createElement('a')
          link.href = url
          link.download = fileName
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          window.URL.revokeObjectURL(url)
        } else {
          this.$message.error('导出文件名缺失')
        }
      } else {
        this.$message.error(response?.msg || '导出失败')
      }
    } catch (error) {
      console.error('导出失败:', error)
      this.$message.error('导出失败，请稍后重试')
    }
  }

  // 显示归档对话框
  showArchiveDialog() {
    this.archiveForm = {
      end_time: '',
      archive_path: ''
    }
    this.archiveDialogVisible = true
  }

  // 确认归档
  async handleConfirmArchive() {
    if (!this.archiveForm.end_time) {
      this.$message.warning('请选择归档截止时间')
      return
    }

    this.$confirm('归档操作不可恢复，确定要归档审计日志吗？', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async() => {
      this.archiveLoading = true
      try {
        const response = await archiveAuditLogs(this.archiveForm)
        if (response && response.code === '200' && response.data && response.data.success) {
          const archivedCount = response.data.archived_count || 0
          this.$message.success(`归档成功，已归档 ${archivedCount} 条日志`)
          this.archiveDialogVisible = false
          this.getList()
          this.getStatistics()
        } else {
          this.$message.error(response?.msg || '归档失败')
        }
      } catch (error) {
        console.error('归档失败:', error)
        this.$message.error('归档失败，请稍后重试')
      } finally {
        this.archiveLoading = false
      }
    }).catch(() => {
      // 用户取消
    })
  }

  // 刷新统计
  refreshStatistics() {
    this.getStatistics()
    this.$message.success('统计已刷新')
  }

  // 复制JSON
  async handleCopyJson(): Promise<void> {
    const currentLog = this.currentLog
    const message = this.$message
    if (!currentLog) return

    try {
      await copyTextToClipboard(JSON.stringify(currentLog, null, 2))
      message.success('JSON 已复制到剪贴板')
    } catch (error) {
      console.error('复制审计日志 JSON 失败:', error)
      message.error('复制失败，请手动选择内容复制')
    }
  }

  // 获取操作类型名称
  getOperationTypeName(type: string): string {
    const typeMap: Record<string, string> = {
      add: '新增种子',
      transfer: '种子转移',
      delete_l4: '等级4删除',
      delete_l3: '等级3删除',
      delete_l2: '等级2删除',
      delete_l1: '等级1删除',
      restore: '还原种子',
      downloader_add: '添加下载器',
      downloader_delete: '删除下载器',
      downloader_update: '修改下载器',
      downloader_test: '测试下载器',
      scheduled_task_add: '添加定时任务',
      scheduled_task_delete: '删除定时任务',
      scheduled_task_update: '修改定时任务',
      scheduled_task_execute: '执行定时任务',
      scheduled_task_interrupt: '中断定时任务',
      keyword_rule_add: '添加关键词规则',
      keyword_rule_delete: '删除关键词规则',
      keyword_rule_update: '修改关键词规则'
    }
    return typeMap[type] || type
  }

  // 获取操作类型样式类
  getOperationClass(type: string): string {
    if (type.includes('delete')) return 'delete'
    if (type.includes('add')) return 'add'
    if (type.includes('update')) return 'update'
    if (type === 'restore') return 'restore'
    return 'add'
  }

  // 获取操作类型标签类型
  getOperationTagType(type: string): string {
    if (type.includes('delete')) return 'danger'
    if (type.includes('add')) return 'primary'
    if (type.includes('update')) return 'warning'
    if (type === 'restore') return 'info'
    return ''
  }

  // 获取操作结果名称
  getResultName(result: string): string {
    const resultMap: Record<string, string> = {
      success: '成功',
      failed: '失败',
      partial: '部分成功'
    }
    return resultMap[result] || result
  }

  // 获取操作结果标签类型
  getResultTagType(result: string): string {
    const typeMap: Record<string, string> = {
      success: 'success',
      failed: 'danger',
      partial: 'warning'
    }
    return typeMap[result] || 'info'
  }

  // 格式化日期时间
  formatDateTime(dateStr: string): string {
    if (!dateStr) return '-'
    try {
      const date = new Date(dateStr)
      const year = date.getFullYear()
      const month = String(date.getMonth() + 1).padStart(2, '0')
      const day = String(date.getDate()).padStart(2, '0')
      const hours = String(date.getHours()).padStart(2, '0')
      const minutes = String(date.getMinutes()).padStart(2, '0')
      const seconds = String(date.getSeconds()).padStart(2, '0')
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
    } catch (e) {
      return dateStr
    }
  }

  // 格式化JSON
  formatJson(jsonStr: unknown): string {
    try {
      const obj = typeof jsonStr === 'string' ? JSON.parse(jsonStr) : jsonStr
      return JSON.stringify(obj, null, 2)
    } catch (e) {
      return typeof jsonStr === 'string' ? jsonStr : String(jsonStr)
    }
  }

  // 截断文本
  truncateText(text: string, maxLength: number): string {
    if (!text) return ''
    if (text.length <= maxLength) return text
    return text.substring(0, maxLength) + '...'
  }

  // 获取今日日志数量
  getTodayLogsCount(): number {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const todayStr = today.toISOString().substring(0, 10)
    return this.list.filter(log => {
      const logDate = new Date(log.operation_time)
      return logDate.toISOString().substring(0, 10) === todayStr
    }).length
  }
}
</script>

<style lang="scss" scoped>
.audit-logs-container {
  padding: 20px;
}

.audit-filter-panel {
  overflow: visible;
}

.audit-filter-grid {
  display: grid;
  grid-template-columns: minmax(190px, 1fr) minmax(210px, 1fr) minmax(150px, 0.7fr) minmax(150px, 0.7fr);
  align-items: end;

  .management-filter__field {
    width: 100%;
    min-width: 0;
    max-width: none;
  }

  .audit-filter-field--time {
    grid-column: span 2;
  }

  .audit-search-actions {
    grid-column: span 2;
    justify-content: flex-end;
    margin-left: 0;
  }

  ::v-deep .management-filter__control {
    width: 100%;
  }
}

.audit-action-panel {
  overflow: visible;
  background:
    linear-gradient(135deg, var(--color-bg-primary), var(--color-bg-secondary));
}

.audit-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-lg);
  min-height: 82px;
  padding: var(--spacing-md) var(--spacing-lg);
}

.audit-action-bar__heading {
  display: flex;
  align-items: center;
  min-width: 0;
}

.audit-action-bar__icon {
  display: inline-flex;
  flex: 0 0 42px;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  margin-right: var(--spacing-md);
  color: #fff;
  font-size: 20px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.audit-action-bar__title {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}

.audit-action-bar__description {
  margin: var(--spacing-xs) 0 0;
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.audit-action-bar__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-sm);

  .el-button + .el-button {
    margin-left: 0;
  }
}

.statistics-card {
  height: 100px;

  ::v-deep .el-card__body {
    padding: 20px;
    height: 100%;
  }

  .statistics-item {
    display: flex;
    align-items: center;
    height: 100%;

    .statistics-content {
      margin-left: 15px;
      flex: 1;
    }

    .statistics-value {
      font-size: 28px;
      font-weight: 600;
      color: #303133;
      line-height: 1;
      margin-bottom: 5px;
    }

    .statistics-label {
      font-size: 14px;
      color: #909399;
    }
  }
}

.table-container {
  background: #fff;
  padding: 20px;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.audit-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  margin-bottom: 20px;

  thead {
    // 统一主题色渐变背景（与种子列表保持一致）
    background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
    color: white;

    th {
      padding: 12px;
      text-align: left;
      font-weight: 600;
      color: white;
      border-bottom: 1px solid var(--color-primary);
      white-space: nowrap;

      // 表头左上角圆角
      &:first-child {
        border-top-left-radius: 12px;
      }

      // 表头右上角圆角
      &:last-child {
        border-top-right-radius: 12px;
      }
    }
  }

  tbody {
    tr {
      transition: background-color 0.25s ease;

      &:hover {
        background-color: #f5f7fa;
      }

      &.current-row {
        background-color: #ecf5ff;
      }

      td {
        padding: 12px;
        border-bottom: 1px solid #ebeef5;
        color: #606266;
        font-size: 14px;
      }
    }
  }

  .empty-cell {
    padding: 60px 0;
    text-align: center;
  }
}

.operation-tag {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;

  &.delete {
    background: #fef0f0;
    color: #f56c6c;
  }

  &.add {
    background: #f0f9ff;
    color: #409eff;
  }

  &.update {
    background: #fdf6ec;
    color: #e6a23c;
  }

  &.restore {
    background: #f4f4f5;
    color: #909399;
  }
}

.result-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;

  &.success {
    background: #f0f9ff;
    color: #67c23a;
  }

  &.failed {
    background: #fef0f0;
    color: #f56c6c;
  }

  &.partial {
    background: #fdf6ec;
    color: #e6a23c;
  }
}

.torrent-id-tag {
  display: inline-block;
  padding: 2px 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  font-family: 'Courier New', monospace;
}

.torrent-name-tag {
  display: inline-block;
  padding: 2px 8px;
  background: #e1f3f8;
  border-radius: 4px;
  font-size: 13px;
  color: #409eff;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.downloader-name-tag {
  display: inline-block;
  padding: 2px 8px;
  background: #f0f9ff;
  border-radius: 4px;
  font-size: 12px;
  color: #67c23a;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-state {
  .empty-state-text {
    font-size: 16px;
    color: #909399;
  }
}

.pagination-container {
  margin-top: 20px;
  text-align: right;
}

// 详情对话框样式
::v-deep .audit-detail-dialog {
  .detail-content {
    max-height: 60vh;
    overflow-y: auto;
  }

  .detail-section {
    margin-bottom: 25px;
    padding-bottom: 20px;
    border-bottom: 1px solid #ebeef5;

    &:last-child {
      border-bottom: none;
    }

    .detail-section-title {
      font-size: 16px;
      font-weight: 500;
      color: #303133;
      margin-bottom: 15px;
      padding-left: 10px;
      border-left: 4px solid #409eff;
    }

    .detail-item {
      display: flex;
      margin-bottom: 12px;
      align-items: flex-start;

      .detail-label {
        min-width: 120px;
        color: #909399;
        font-size: 14px;
        flex-shrink: 0;
        line-height: 20px;
      }

      .detail-value {
        flex: 1;
        color: #303133;
        font-size: 14px;
        word-break: break-all;
        line-height: 20px;
      }
    }
  }

  .json-viewer {
    background: #f5f7fa;
    padding: 15px;
    border-radius: 4px;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 300px;
    overflow-y: auto;
    color: #606266;
  }
}

@media (max-width: 1200px) {
  .audit-filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .audit-logs-container {
    padding: var(--spacing-md);
  }

  .audit-filter-grid {
    grid-template-columns: 1fr;

    .audit-filter-field--time,
    .audit-search-actions {
      grid-column: span 1;
    }

    .audit-search-actions {
      justify-content: flex-start;
    }
  }

  .audit-action-bar {
    flex-direction: column;
    align-items: stretch;
    padding: var(--spacing-md);
  }

  .audit-action-bar__actions {
    justify-content: flex-start;
  }
}
</style>
