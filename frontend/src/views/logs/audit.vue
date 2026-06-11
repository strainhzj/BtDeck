<template>
  <div class="app-container audit-logs-container">
    <!-- 筛选区域 -->
    <div class="filter-container">
      <el-input
        v-model="listQuery.torrent_name"
        placeholder="种子名称（支持模糊搜索）"
        style="width: 200px;"
        class="filter-item"
        clearable
        @keyup.enter.native="handleFilter"
      />
      <el-select
        v-model="listQuery.operation_type"
        placeholder="操作类型"
        style="width: 200px;"
        class="filter-item"
        clearable
        filterable
      >
        <el-option label="全部类型" value="" />
        <el-option-group label="种子管理">
          <el-option label="新增种子" value="add" />
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
        </el-option-group>
        <el-option-group label="关键词规则">
          <el-option label="添加关键词规则" value="keyword_rule_add" />
          <el-option label="删除关键词规则" value="keyword_rule_delete" />
          <el-option label="修改关键词规则" value="keyword_rule_update" />
        </el-option-group>
      </el-select>
      <el-input
        v-model="listQuery.operator"
        placeholder="操作人"
        style="width: 150px;"
        class="filter-item"
        clearable
        @keyup.enter.native="handleFilter"
      />
      <el-select
        v-model="listQuery.operation_result"
        placeholder="操作结果"
        style="width: 130px;"
        class="filter-item"
        clearable
      >
        <el-option label="全部" value="" />
        <el-option label="成功" value="success" />
        <el-option label="失败" value="failed" />
        <el-option label="部分成功" value="partial" />
      </el-select>

      <!-- 时间范围选择 -->
      <el-date-picker
        v-model="dateRange"
        type="datetimerange"
        range-separator="至"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        value-format="yyyy-MM-dd HH:mm:ss"
        style="width: 350px;"
        class="filter-item"
        @change="handleDateRangeChange"
      />

      <el-button
        v-waves
        class="filter-item"
        type="primary"
        icon="el-icon-search"
        @click="handleFilter"
      >
        搜索
      </el-button>
      <el-button
        class="filter-item"
        type="default"
        icon="el-icon-refresh"
        @click="resetFilter"
      >
        重置
      </el-button>

      <!-- 导出和归档按钮 -->
      <el-dropdown @command="handleExport" class="filter-item">
        <el-button type="success" icon="el-icon-download">
          导出 <i class="el-icon-arrow-down el-icon--right" />
        </el-button>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="csv">导出为 CSV</el-dropdown-item>
          <el-dropdown-item command="excel">导出为 Excel</el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>

      <el-button
        class="filter-item"
        type="warning"
        icon="el-icon-folder"
        @click="showArchiveDialog"
      >
        归档历史日志
      </el-button>

      <el-button
        class="filter-item"
        type="info"
        icon="el-icon-refresh"
        @click="refreshStatistics"
      >
        刷新统计
      </el-button>
    </div>

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
        <el-button type="primary" @click="handleCopyJson">📋 复制JSON</el-button>
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

        <el-form-item label="归档文件路径">
          <el-input
            v-model="archiveForm.archive_path"
            placeholder="留空则自动生成"
          />
          <div style="font-size: 12px; color: #909399; margin-top: 5px;">
            默认保存到：data/audit_logs_archive/
          </div>
        </el-form-item>
      </el-form>

      <span slot="footer" class="dialog-footer">
        <el-button @click="archiveDialogVisible = false">取消</el-button>
        <el-button type="warning" :loading="archiveLoading" @click="handleConfirmArchive">
          📁 确认归档
        </el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { queryAuditLogs, getAuditLogStatistics, exportAuditLogs, archiveAuditLogs } from '@/api/audit-logs'

@Component({
  name: 'AuditLogs'
})
export default class AuditLogs extends Vue {
  // 列表数据
  list: any[] = []
  total = 0
  listLoading = false
  currentRow: any = null

  // 查询参数
  listQuery = {
    torrent_name: '',
    operation_type: '',
    operator: '',
    operation_result: '',
    start_time: '',
    end_time: '',
    page: 1,
    page_size: 20
  }

  // 日期范围
  dateRange: string[] | null = null

  // 统计信息
  statistics: any = {
    total_count: 0,
    operation_type_stats: {},
    operator_stats: {},
    result_stats: {}
  }

  // 对话框
  detailDialogVisible = false
  archiveDialogVisible = false
  currentLog: any = null

  // 归档表单
  archiveForm = {
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
    this.listQuery = {
      torrent_name: '',
      operation_type: '',
      operator: '',
      operation_result: '',
      start_time: '',
      end_time: '',
      page: 1,
      page_size: 20
    }
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
  handleRowClick(row: any) {
    this.currentRow = row
  }

  // 查看详情
  handleViewDetail(row: any) {
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
        // 下载文件
        const fileName = response.data.file_name
        if (fileName) {
          const downloadUrl = `/api/audit-logs/download-export/${fileName}`
          window.open(downloadUrl, '_blank')
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
  handleCopyJson() {
    if (this.currentLog) {
      const jsonText = JSON.stringify(this.currentLog, null, 2)
      navigator.clipboard.writeText(jsonText).then(() => {
        this.$message.success('JSON已复制到剪贴板')
      }).catch(() => {
        this.$message.error('复制失败')
      })
    }
  }

  // 获取操作类型名称
  getOperationTypeName(type: string): string {
    const typeMap: Record<string, string> = {
      add: '新增种子',
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
  formatJson(jsonStr: string): string {
    try {
      const obj = typeof jsonStr === 'string' ? JSON.parse(jsonStr) : jsonStr
      return JSON.stringify(obj, null, 2)
    } catch (e) {
      return jsonStr
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
  // 继承app-container的padding
  padding: 20px;
}

.filter-container {
  background: #fff;
  padding: 20px;
  border-radius: 4px;
  margin-bottom: 20px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);

  .filter-item {
    margin-right: 10px;
    margin-bottom: 10px;
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
</style>
