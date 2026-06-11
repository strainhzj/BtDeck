<template>
  <div class="app-container recycle-bin-page">
    <!-- 页面标题 -->
    <div style="margin-bottom: 20px;">
      <h2 style="font-size: 20px; color: #303133; font-weight: 600; margin: 0;">
        🗑️ 回收站
      </h2>
      <p style="font-size: 14px; color: #909399; margin-top: 8px; margin-bottom: 0;">
        管理已删除的种子，支持还原或永久删除
      </p>
    </div>

    <!-- ========== 筛选区域 ========== -->
    <div class="filter-container">
      <el-input
        v-model="listQuery.search"
        placeholder="搜索种子名称..."
        style="width: 200px;"
        class="filter-item"
        clearable
        @keyup.enter.native="handleFilter"
      >
        <i slot="prefix" class="el-input__icon el-icon-search"></i>
      </el-input>

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
    </div>

    <!-- ========== 批量操作工具栏 ========== -->
    <section class="batch-operations">
      <!-- 批量还原 -->
      <batch-button
        type="success"
        icon="el-icon-check"
        tooltip="还原"
        :disabled="selectedItems.length === 0"
        @click="handleBatchRestore"
      />

      <!-- 批量删除 -->
      <batch-button
        type="danger"
        icon="el-icon-delete"
        tooltip="删除"
        :disabled="selectedItems.length === 0"
        @click="handleBatchDelete"
      />

      <!-- 清理预览 -->
      <batch-button
        type="warning"
        icon="el-icon-view"
        tooltip="清理预览"
        @click="handleCleanupPreview"
      />

      <div class="toolbar-divider"></div>

      <!-- 刷新列表 -->
      <batch-button
        type="default"
        icon="el-icon-refresh"
        tooltip="刷新列表"
        @click="handleRefresh"
      />

      <!-- 清空回收站 -->
      <batch-button
        v-if="false"
        type="danger"
        icon="el-icon-delete"
        tooltip="清空回收站"
        @click="handleClearAll"
      />

      <div style="flex: 1;"></div>

      <!-- 手动上传还原 -->
      <batch-button
        type="primary"
        icon="el-icon-upload2"
        tooltip="手动上传还原"
        @click="handleManualUpload"
      />
    </section>

    <!-- ========== 数据表格 ========== -->
    <section
      class="table-wrapper"
      v-loading="listLoading"
      element-loading-text="加载中..."
      element-loading-spinner="el-icon-loading"
      element-loading-background="rgba(0, 0, 0, 0.1)"
    >
      <table class="torrent-table" v-if="!isEmpty">
        <thead>
          <tr>
            <th style="width: 50px;">
              <el-checkbox
                v-model="selectAll"
                :indeterminate="isIndeterminate"
                @change="handleSelectAll"
              />
            </th>
            <th>种子名称</th>
            <th style="width: 100px;">状态</th>
            <th style="width: 120px;">大小</th>
            <th style="width: 160px;">删除时间</th>
            <th style="width: 130px;">所属下载器</th>
            <th>原路径</th>
            <th style="width: 180px;" class="action-column">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in list"
            :key="item.info_id"
            :class="{selected: item.selected}"
            @click="handleRowClick(item)"
          >
            <td @click.stop>
              <el-checkbox v-model="item.selected" @change="handleSelectionChange" />
            </td>
            <td>
              <div class="torrent-name" :title="item.name" style="font-weight: 500;">
                {{ item.name }}
              </div>
            </td>
            <td>
              <el-tag
                size="mini"
                :type="item.dr === 1 ? 'danger' : 'success'"
                effect="plain">
                {{ item.dr === 1 ? '不可还原' : '可还原' }}
              </el-tag>
            </td>
            <td>
              <span class="file-size">{{ formatFileSize(item.size) }}</span>
            </td>
            <td>
              <span style="font-size: 13px; color: #606266;">{{ formatDate(item.deleted_at) }}</span>
            </td>
            <td>
              <el-tag size="mini" type="info">{{ item.downloader_name }}</el-tag>
            </td>
            <td>
              <div class="file-path" :title="item.save_path">{{ item.save_path }}</div>
            </td>
            <td @click.stop>
              <div class="action-buttons">
                <button class="action-btn restore" @click="handleRestoreSingle(item)">
                  还原
                </button>
                <button class="action-btn delete" @click="handleDeleteSingle(item)">
                  删除
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 空状态 -->
      <div class="empty-state" v-if="isEmpty && !listLoading">
        <div class="empty-icon">🗑️</div>
        <div class="empty-text">回收站为空</div>
        <div class="empty-hint">删除的种子会显示在这里</div>
      </div>
    </section>

    <!-- ========== 分页 ========== -->
    <div class="pagination-container" v-if="!isEmpty">
      <el-pagination
        :current-page="listQuery.page"
        :page-size="listQuery.page_size"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>

    <!-- ========== 清理预览对话框 ========== -->
    <el-dialog
      title="清理预览"
      :visible.sync="cleanupPreviewVisible"
      width="70%"
      :close-on-click-modal="false"
    >
      <div class="dialog-content">
        <!-- 天数设置 -->
        <div class="days-input-wrapper">
          <span style="font-size: 14px; color: #606266;">清理</span>
          <el-input-number
            v-model="cleanupDays"
            :min="1"
            :max="365"
            size="small"
          />
          <span style="font-size: 14px; color: #606266;">天前的种子</span>
          <el-button
            type="primary"
            size="small"
            icon="el-icon-search"
            @click="loadCleanupPreview"
            :loading="previewLoading"
          >
            预览
          </el-button>
        </div>

        <!-- 预览摘要 -->
        <div class="cleanup-summary" v-if="cleanupPreview">
          <div class="cleanup-summary-item">
            <span class="cleanup-summary-label">种子数量：</span>
            <span class="cleanup-summary-value highlight">{{ cleanupPreview.total_count }}</span>
          </div>
          <div class="cleanup-summary-item">
            <span class="cleanup-summary-label">总大小：</span>
            <span class="cleanup-summary-value highlight">{{ formatFileSize(cleanupPreview.total_size) }}</span>
          </div>
        </div>

        <!-- 预览列表 -->
        <el-table
          :data="cleanupPreview?.torrent_list || []"
          max-height="400"
          v-loading="previewLoading"
          stripe
        >
          <el-table-column prop="name" label="种子名称" show-overflow-tooltip />
          <el-table-column prop="size" label="大小" width="120">
            <template slot-scope="scope">
              {{ formatFileSize(scope.row.size) }}
            </template>
          </el-table-column>
          <el-table-column prop="deleted_at" label="删除时间" width="160" />
          <el-table-column prop="save_path" label="原路径" show-overflow-tooltip />
        </el-table>
      </div>

      <span slot="footer">
        <el-button @click="cleanupPreviewVisible = false">取消</el-button>
        <el-button
          type="danger"
          @click="handleExecuteCleanup"
          :disabled="!cleanupPreview || cleanupPreview.total_count === 0"
          :loading="cleanupLoading"
        >
          确认清理
        </el-button>
      </span>
    </el-dialog>

    <!-- ========== 手动上传还原对话框 ========== -->
    <el-dialog
      title="手动上传种子文件还原"
      :visible.sync="manualUploadVisible"
      width="500px"
      :close-on-click-modal="false"
    >
      <div class="dialog-content">
        <el-form :model="manualUploadForm" label-width="100px">
          <el-form-item label="种子ID">
            <el-input
              v-model="manualUploadForm.torrent_id"
              placeholder="请输入要还原的种子ID"
              clearable
            />
          </el-form-item>

          <el-form-item label="种子文件">
            <el-upload
              ref="upload"
              :auto-upload="false"
              :limit="1"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              :file-list="fileList"
              action="#"
              accept=".torrent"
            >
              <el-button slot="trigger" size="small" icon="el-icon-upload">
                选择种子文件
              </el-button>
              <div slot="tip" class="el-upload__tip">
                只能上传.torrent文件，且不超过10MB
              </div>
            </el-upload>
          </el-form-item>

          <el-alert
            title="提示"
            type="info"
            :closable="false"
            style="margin-top: 16px;"
          >
            当种子文件备份不存在时，可以手动上传种子文件进行还原
          </el-alert>
        </el-form>
      </div>

      <span slot="footer">
        <el-button @click="manualUploadVisible = false">取消</el-button>
        <el-button
          type="primary"
          @click="handleExecuteManualRestore"
          :loading="manualRestoreLoading"
          :disabled="!manualUploadForm.torrent_id || fileList.length === 0"
        >
          开始还原
        </el-button>
      </span>
    </el-dialog>

    <!-- ========== 确认对话框 ========== -->
    <el-dialog
      :title="confirmDialog.title"
      :visible.sync="confirmDialog.visible"
      width="450px"
      :close-on-click-modal="false"
    >
      <div class="confirm-dialog-content">
        <div v-if="confirmDialog.type === 'clearAll'" class="confirm-warning">
          ⚠️ 危险操作
        </div>
        <div>{{ confirmDialog.message }}</div>
        <div class="confirm-detail" v-if="confirmDialog.detail">
          {{ confirmDialog.detail }}
        </div>
      </div>
      <span slot="footer">
        <el-button @click="confirmDialog.visible = false">取消</el-button>
        <el-button
          :type="confirmDialog.confirmButtonType || 'primary'"
          @click="handleConfirmAction"
          :loading="confirmDialog.loading"
        >
          确认
        </el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script>
import {
  getRecycleBinList,
  restoreTorrents,
  restoreTorrentWithFile,
  cleanupPreview,
  manualCleanup
} from '@/api/recycle-bin'
import { formatFileSize, formatDate, extractErrorMessage } from '@/utils/formatters'
import BatchButton from '@/components/BatchButton/index.vue'

export default {
  name: 'RecycleBin',
  components: {
    BatchButton
  },
  data() {
    return {
      // 查询参数
      listQuery: {
        page: 1,
        page_size: 20,
        search: ''
      },

      // 列表数据
      list: [],
      total: 0,
      listLoading: false,

      // 选择状态
      selectAll: false,
      isIndeterminate: false,
      selectedItems: [],

      // 清理预览
      cleanupPreviewVisible: false,
      cleanupDays: 30,
      cleanupPreview: null,
      previewLoading: false,
      cleanupLoading: false,

      // 手动上传
      manualUploadVisible: false,
      manualUploadForm: {
        torrent_id: ''
      },
      fileList: [],
      manualRestoreLoading: false,

      // 确认对话框
      confirmDialog: {
        visible: false,
        title: '',
        message: '',
        detail: '',
        type: '',
        confirmButtonType: 'primary',
        loading: false,
        action: null
      }
    }
  },
  computed: {
    isEmpty() {
      return this.list.length === 0
    }
  },
  created() {
    this.getList()
  },
  methods: {
    // ========== 工具函数 ==========
    formatFileSize,
    formatDate,

    // ========== 获取列表 ==========
    async getList() {
      this.listLoading = true
      try {
        const response = await getRecycleBinList(this.listQuery)
        if (response.code === '200' && response.data) {
          // ✅ 正确：使用 list 字段（符合项目规范）
          this.list = (response.data.list || []).map(item => ({
            ...item,
            selected: false
          }))
          this.total = response.data.total || 0

          // 重置选择状态
          this.selectAll = false
          this.isIndeterminate = false
          this.selectedItems = []
        } else {
          this.$message.error(response.msg || '获取回收站列表失败')
        }
      } catch (error) {
        console.error('获取回收站列表失败:', error)
        this.$message.error(extractErrorMessage(error, '获取回收站列表失败'))
      } finally {
        this.listLoading = false
      }
    },

    // ========== 搜索筛选 ==========
    handleFilter() {
      this.listQuery.page = 1
      this.getList()
    },

    resetFilter() {
      this.listQuery = {
        page: 1,
        page_size: this.listQuery.page_size,
        search: ''
      }
      this.getList()
    },

    // ========== 选择相关 ==========
    handleSelectAll(val) {
      this.list.forEach(item => {
        item.selected = val
      })
      this.updateSelectAllState()
    },

    handleSelectionChange() {
      this.updateSelectAllState()
    },

    updateSelectAllState() {
      const selectedItems = this.list.filter(item => item.selected)
      this.selectedItems = selectedItems
      this.selectAll = selectedItems.length === this.list.length && selectedItems.length > 0
      this.isIndeterminate = selectedItems.length > 0 && selectedItems.length < this.list.length
    },

    handleRowClick(row) {
      // 行点击暂不处理，可扩展显示详情
    },

    // ========== 批量操作 ==========
    handleBatchRestore() {
      const count = this.selectedItems.length
      this.showConfirmDialog(
        '批量还原',
        `确定要还原选中的 ${count} 个种子吗？`,
        '还原操作将重新添加种子到下载器，并清除删除标记。',
        'batchRestore',
        'success'
      )
    },

    handleBatchDelete() {
      const count = this.selectedItems.length
      this.showConfirmDialog(
        '批量删除',
        `确定要永久删除选中的 ${count} 个种子吗？`,
        '此操作不可撤销，种子将被永久删除！',
        'batchDelete',
        'danger'
      )
    },

    handleCleanupPreview() {
      this.cleanupPreviewVisible = true
      this.cleanupDays = 30
      this.cleanupPreview = null
      this.loadCleanupPreview()
    },

    async loadCleanupPreview() {
      this.previewLoading = true
      try {
        const response = await cleanupPreview({ days: this.cleanupDays })
        if (response.code === '200' && response.data) {
          this.cleanupPreview = response.data
        } else {
          this.$message.error(response.msg || '获取预览失败')
        }
      } catch (error) {
        console.error('获取预览失败:', error)
        this.$message.error(extractErrorMessage(error, '获取预览失败'))
      } finally {
        this.previewLoading = false
      }
    },

    handleExecuteCleanup() {
      if (!this.cleanupPreview || !this.cleanupPreview.torrent_list || this.cleanupPreview.total_count === 0) {
        this.$message.warning('没有可清理的种子')
        return
      }

      const torrentIds = this.cleanupPreview.torrent_list.map(item => item.info_id)
      this.showConfirmDialog(
        '确认清理',
        `确定要清理 ${this.cleanupPreview.total_count} 个种子吗？`,
        `释放空间：${this.formatFileSize(this.cleanupPreview.total_size)}`,
        'executeCleanup',
        'danger',
        torrentIds
      )
    },

    async executeCleanup(torrentIds) {
      this.cleanupLoading = true
      try {
        const response = await manualCleanup({ torrent_ids: torrentIds })
        if (response.code === '200') {
          this.$message.success('清理成功')
          this.cleanupPreviewVisible = false
          this.getList()
        } else {
          this.$message.error(response.msg || '清理失败')
        }
      } catch (error) {
        console.error('清理失败:', error)
        this.$message.error(extractErrorMessage(error, '清理失败'))
      } finally {
        this.cleanupLoading = false
      }
    },

    handleRefresh() {
      this.getList()
      this.$message.success('刷新成功')
    },

    handleClearAll() {
      const count = this.total
      if (count === 0) {
        this.$message.warning('回收站为空')
        return
      }

      this.showConfirmDialog(
        '清空回收站',
        '确定要清空回收站吗？',
        `此操作将永久删除回收站中的所有 ${count} 个种子，不可撤销！`,
        'clearAll',
        'danger'
      )
    },

    async executeClearAll() {
      try {
        // 获取所有种子的ID
        const response = await getRecycleBinList({
          page: 1,
          page_size: 999999,
          search: ''
        })

        if (response.code === '200' && response.data?.list) {
          const torrentIds = response.data.list.map(item => item.info_id)
          await this.executeCleanup(torrentIds)
        }
      } catch (error) {
        console.error('清空回收站失败:', error)
        this.$message.error(extractErrorMessage(error, '清空回收站失败'))
      }
    },

    // ========== 手动上传 ==========
    handleManualUpload() {
      this.manualUploadVisible = true
      this.manualUploadForm.torrent_id = ''
      this.fileList = []
    },

    handleFileChange(file, fileList) {
      this.fileList = fileList
    },

    handleFileRemove() {
      this.fileList = []
    },

    async handleExecuteManualRestore() {
      if (!this.manualUploadForm.torrent_id) {
        this.$message.warning('请输入种子ID')
        return
      }

      if (this.fileList.length === 0) {
        this.$message.warning('请选择种子文件')
        return
      }

      if (!this.fileList[0].raw) {
        this.$message.warning('种子文件对象无效')
        return
      }

      this.manualRestoreLoading = true
      try {
        const file = this.fileList[0].raw
        const response = await restoreTorrentWithFile({
          torrent_id: this.manualUploadForm.torrent_id,
          torrent_file: file
        })

        if (response.code === '200') {
          const result = response.data
          if (result.failed_count === 0) {
            this.$message.success('还原成功')
          } else if (result.success_count === 0) {
            this.$message.error('还原失败')
          } else {
            this.$message.warning(`部分成功：成功${result.success_count}个，失败${result.failed_count}个`)
          }

          this.manualUploadVisible = false
          this.getList()
        } else {
          this.$message.error(response.msg || '还原失败')
        }
      } catch (error) {
        console.error('手动还原失败:', error)
        this.$message.error(extractErrorMessage(error, '手动还原失败'))
      } finally {
        this.manualRestoreLoading = false
      }
    },

    // ========== 单个操作 ==========
    handleRestoreSingle(item) {
      this.showConfirmDialog(
        '还原种子',
        `确定要还原 "${item.name}" 吗？`,
        '种子将被重新添加到下载器。',
        'restoreSingle',
        'success',
        item
      )
    },

    handleDeleteSingle(item) {
      this.showConfirmDialog(
        '删除种子',
        `确定要永久删除 "${item.name}" 吗？`,
        '此操作不可撤销，种子将被永久删除！',
        'deleteSingle',
        'danger',
        item
      )
    },

    // ========== 确认对话框 ==========
    showConfirmDialog(title, message, detail, type, buttonType = 'primary', data = null) {
      this.confirmDialog = {
        visible: true,
        title,
        message,
        detail,
        type,
        confirmButtonType: buttonType,
        loading: false,
        action: () => this.executeConfirmAction(type, data)
      }
    },

    handleConfirmAction() {
      if (this.confirmDialog.action) {
        this.confirmDialog.action()
      }
    },

    async executeConfirmAction(type, data) {
      this.confirmDialog.loading = true

      try {
        switch (type) {
          case 'batchRestore':
            await this.executeRestore(this.selectedItems.map(item => item.info_id))
            break

          case 'batchDelete':
            await this.executeDelete(this.selectedItems.map(item => item.info_id))
            break

          case 'executeCleanup':
            await this.executeCleanup(data)
            break

          case 'clearAll':
            await this.executeClearAll()
            break

          case 'restoreSingle':
            await this.executeRestore([data.info_id])
            break

          case 'deleteSingle':
            await this.executeDelete([data.info_id])
            break

          default:
            break
        }
      } finally {
        this.confirmDialog.loading = false
        this.confirmDialog.visible = false
      }
    },

    async executeRestore(torrentIds) {
      try {
        const response = await restoreTorrents({ torrent_ids: torrentIds })
        if (response.code === '200') {
          const result = response.data
          if (result.failed_count === 0) {
            this.$message.success(`还原成功：共${result.success_count}个种子`)
          } else if (result.success_count === 0) {
            this.$message.error(`还原失败：共${result.failed_count}个种子`)
          } else {
            this.$message.warning(`还原部分成功：成功${result.success_count}个，失败${result.failed_count}个`)
          }

          this.getList()
        } else {
          this.$message.error(response.msg || '还原失败')
        }
      } catch (error) {
        console.error('还原失败:', error)
        this.$message.error(extractErrorMessage(error, '还原失败'))
      }
    },

    async executeDelete(torrentIds) {
      try {
        const response = await manualCleanup({ torrent_ids: torrentIds })
        if (response.code === '200') {
          const result = response.data
          if (result.failed_count === 0) {
            this.$message.success(`删除成功：共${result.success_count}个种子`)
          } else if (result.success_count === 0) {
            this.$message.error(`删除失败：共${result.failed_count}个种子`)
          } else {
            this.$message.warning(`删除部分成功：成功${result.success_count}个，失败${result.failed_count}个`)
          }

          this.getList()
        } else {
          this.$message.error(response.msg || '删除失败')
        }
      } catch (error) {
        console.error('删除失败:', error)
        this.$message.error(extractErrorMessage(error, '删除失败'))
      }
    },

    // ========== 分页 ==========
    handleSizeChange(size) {
      this.listQuery.page_size = size
      this.listQuery.page = 1
      this.getList()
    },

    handleCurrentChange(page) {
      this.listQuery.page = page
      this.getList()
    }
  }
}
</script>

<style lang="scss" scoped>
.recycle-bin-page {
  width: 100%;
}

// ========== 筛选区域 ==========
.filter-container {
  margin-bottom: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;

  .filter-item {
    margin-right: 10px;

    &:last-child {
      margin-right: 0;
    }
  }
}

// ========== 批量操作工具栏 ==========
.batch-operations {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(to bottom, #f8f9fa, #ffffff);
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  margin-bottom: 20px;
}

.batch-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  background: linear-gradient(to bottom, #ffffff, #f8f9fa);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 18px;
  position: relative;

  &:hover:not(:disabled) {
    background: linear-gradient(to bottom, #f0f0f0, #e8e8e8);
    border-color: #409EFF;
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
  }

  &:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: none;
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  &.primary {
    border-color: #409EFF;
    background: linear-gradient(to bottom, #409EFF, #66b1ff);

    &:hover:not(:disabled) {
      background: linear-gradient(to bottom, #66b1ff, #409EFF);
    }
  }

  &.success {
    border-color: #67C23A;
    background: linear-gradient(to bottom, #67C23A, #85ce61);

    &:hover:not(:disabled) {
      background: linear-gradient(to bottom, #85ce61, #67C23A);
    }
  }

  &.danger {
    border-color: #F56C6C;
    background: linear-gradient(to bottom, #F56C6C, #f78989);

    &:hover:not(:disabled) {
      background: linear-gradient(to bottom, #f78989, #F56C6C);
    }
  }

  &.warning {
    border-color: #E6A23C;
    background: linear-gradient(to bottom, #E6A23C, #ebb563);

    &:hover:not(:disabled) {
      background: linear-gradient(to bottom, #ebb563, #E6A23C);
    }
  }

  &.info {
    border-color: #909399;
    background: linear-gradient(to bottom, #909399, #a6a9ad);

    &:hover:not(:disabled) {
      background: linear-gradient(to bottom, #a6a9ad, #909399);
    }
  }

  &[data-tooltip]::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: -30px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0, 0, 0, 0.8);
    color: white;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s ease;
    z-index: 1000;
  }

  &[data-tooltip]:hover::after {
    opacity: 1;
  }
}

.toolbar-divider {
  width: 1px;
  height: 24px;
  background: #e0e0e0;
  margin: 0 8px;
}

// ========== 数据表格 ==========
.table-wrapper {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
  min-height: 300px;
}

.torrent-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 14px;

  thead {
    // 统一主题色渐变背景（与种子列表保持一致）
    background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
    color: white;
    border-bottom: 2px solid var(--color-primary);

    th {
      padding: 12px 16px;
      text-align: left;
      font-weight: 600;
      color: white;
      white-space: nowrap;

      // Table header top-left border radius
      &:first-child {
        border-top-left-radius: 12px;
      }

      // Table header top-right border radius
      &:last-child {
        border-top-right-radius: 12px;
      }
    }
  }

  tbody tr {
    border-bottom: 1px solid #f0f0f0;
    transition: background-color 0.2s ease;
    cursor: pointer;

    &:hover {
      background-color: #f5f7fa;
    }

    &.selected {
      background-color: #ecf5ff;
    }

    &:last-child {
      border-bottom: none;
    }

    td {
      padding: 12px 16px;
      color: #606266;
    }
  }
}

.file-size {
  font-family: 'Monaco', 'Consolas', monospace;
  color: #909399;
  font-size: 13px;
}

.file-path {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #606266;
}

.action-buttons {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 4px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: white;
  color: #606266;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    border-color: #409EFF;
    color: #409EFF;
  }

  &.restore:hover {
    border-color: #67C23A;
    color: #67C23A;
  }

  &.delete:hover {
    border-color: #F56C6C;
    color: #F56C6C;
  }
}

// ========== 空状态 ==========
.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: #909399;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 20px;
  opacity: 0.5;
}

.empty-text {
  font-size: 16px;
  margin-bottom: 8px;
  color: #606266;
}

.empty-hint {
  font-size: 14px;
  color: #c0c4cc;
}

// ========== 分页 ==========
.pagination-container {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 16px 0;
  margin-top: 20px;
}

// ========== 对话框样式 ==========
.dialog-content {
  padding: 20px 0;
}

.days-input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;

  .el-input-number {
    width: 150px;
  }
}

.cleanup-summary {
  background: #f0f9ff;
  border: 1px solid #b3d8ff;
  border-radius: 4px;
  padding: 16px;
  margin-bottom: 20px;
}

.cleanup-summary-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 14px;
}

.cleanup-summary-label {
  color: #606266;
}

.cleanup-summary-value {
  font-weight: 600;
  color: #303133;

  &.highlight {
    color: #F56C6C;
    font-size: 18px;
  }
}

.confirm-dialog-content {
  padding: 20px 0;
  line-height: 1.6;
}

.confirm-warning {
  color: #E6A23C;
  font-weight: 600;
  margin-bottom: 8px;
}

.confirm-detail {
  background: #fef0f0;
  border-left: 3px solid #F56C6C;
  padding: 12px;
  margin-top: 16px;
  font-size: 14px;
  color: #F56C6C;
  border-radius: 2px;
}
</style>
