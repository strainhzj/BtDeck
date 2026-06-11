<template>
  <div>
    <el-dialog
    :title="`批量转移种子（已选择${torrents.length}个）`"
    :visible.sync="dialogVisible"
    width="700px"
    :before-close="handleClose"
    :close-on-click-modal="false"
  >
    <!-- 选中的种子列表 -->
    <div class="selected-torrents-section">
      <div class="section-title">已选择的种子：</div>
      <div class="torrents-list">
        <div
          v-for="torrent in torrents"
          :key="torrent.hash"
          class="torrent-item"
        >
          <div class="torrent-name">
            <i class="el-icon-document" />
            <span :title="torrent.name">{{ torrent.name }}</span>
          </div>
          <div class="torrent-info">
            <span class="info-item">
              <i class="el-icon-download" />
              {{ torrent.downloaderName }}
            </span>
            <span class="info-item">
              <i class="el-icon-folder" />
              <span :title="torrent.savePath">{{ truncatePath(torrent.savePath) }}</span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <el-divider />

    <el-form
      ref="transferForm"
      :model="formData"
      :rules="formRules"
      label-width="120px"
      @submit.native.prevent
    >
      <!-- 目标下载器选择 -->
      <el-form-item label="目标下载器:" prop="target_downloader_id">
        <el-select
          v-model="formData.target_downloader_id"
          placeholder="请选择目标下载器"
          filterable
          style="width: 100%"
          @change="handleTargetDownloaderChange"
        >
          <el-option
            v-for="downloader in availableDownloaders"
            :key="downloader.downloader_id"
            :label="downloader.nickname"
            :value="downloader.downloader_id"
          />
        </el-select>
      </el-form-item>

      <!-- 目标路径输入/选择 -->
      <el-form-item label="目标路径:" prop="target_path">
        <el-autocomplete
          v-model="formData.target_path"
          :fetch-suggestions="queryPathSuggestions"
          placeholder="请输入或选择目标路径"
          style="width: 100%"
          @select="handlePathSelect"
        >
          <template slot-scope="{item}">
            <div class="path-suggestion">
              <span class="path-value">{{ item.value }}</span>
              <span v-if="item.path_type === 'default'" class="path-type">默认路径</span>
              <span class="torrent-count">({{ item.torrent_count }}个种子)</span>
            </div>
          </template>
        </el-autocomplete>
      </el-form-item>

      <!-- 删除原种子选项 -->
      <el-form-item>
        <el-checkbox v-model="formData.delete_source">
          删除原种子
          <el-tooltip content="勾选后，转移成功会删除原下载器中的种子（需二次确认）" placement="top">
            <i class="el-icon-question" />
          </el-tooltip>
        </el-checkbox>
      </el-form-item>
    </el-form>

    <span slot="footer" class="dialog-footer">
      <el-button @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        @click="handleSubmit"
      >
        {{ submitting ? '转移中...' : '确定' }}
      </el-button>
    </span>
    </el-dialog>

    <!-- 批量转移结果对话框（安全渲染，避免XSS） -->
    <el-dialog
    title="批量转移完成"
    :visible.sync="resultDialogVisible"
    width="600px"
    :close-on-click-modal="false"
  >
    <div class="result-summary">
      <div>总数: {{ resultTotal }}个</div>
      <div class="success-count">成功: {{ resultSuccess }}个</div>
      <div class="failed-count">失败: {{ resultFailed }}个</div>
    </div>

    <div v-if="resultFailed > 0" class="failed-list">
      <div class="failed-title">失败列表：</div>
      <div class="failed-items">
        <div v-for="item in resultFailedItems" :key="itemKey(item)" class="failed-item">
          <div class="failed-name">{{ item.torrent_name || item.info_hash || '-' }}</div>
          <div class="failed-reason">{{ item.error_message || '未知错误' }}</div>
        </div>
      </div>
    </div>

    <span slot="footer" class="dialog-footer">
      <el-button @click="handleResultClose">关闭</el-button>
      <el-button type="primary" @click="handleResultConfirm">确定</el-button>
    </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import {
  transferSeedsBatch,
  getDownloaderList,
  getDownloaderPaths,
  deleteTorrents,
  type DownloaderSimple,
  type DownloaderPath,
  type SeedTransferBatchRequest
} from '@/api/torrents'

@Component
export default class BatchTransferDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  @Prop(Array) torrents!: any[]

  // 对话框显示状态
  dialogVisible = false

  // 表单数据
  formData: {
    target_downloader_id: string | null
    target_path: string
    delete_source: boolean
  } = {
    target_downloader_id: null,
    target_path: '',
    delete_source: false
  }

  // 表单验证规则
  formRules = {
    target_downloader_id: [
      { required: true, message: '请选择目标下载器', trigger: 'change' },
      {
        validator: (rule: any, value: string, callback: Function) => {
          // 防御性检查：确保 torrents 不为 undefined
          if (!this.torrents || !Array.isArray(this.torrents) || this.torrents.length === 0) {
            callback()
            return
          }

          // 检查是否与所有选中种子的下载器都不同
          const downloaderIds = new Set(this.torrents.map(t => t.downloaderId))
          if (downloaderIds.has(value)) {
            callback(new Error('目标下载器不能与选中种子的下载器相同'))
          } else {
            callback()
          }
        },
        trigger: 'change'
      }
    ],
    target_path: [
      { required: true, message: '请输入目标路径', trigger: 'blur' }
    ]
  }

  // 可用的下载器列表
  availableDownloaders: DownloaderSimple[] = []

  // 目标下载器的路径列表
  targetDownloaderPaths: DownloaderPath[] = []

  // 提交状态
  submitting = false

  // 批量转移结果
  batchResult: any = null
  resultDialogVisible = false

  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.initDialog()
    }
  }

  async initDialog() {
    // 重置表单
    this.resetForm()

    // 加载下载器列表
    await this.loadDownloaders()
  }

  resetForm() {
    this.formData = {
      target_downloader_id: null,
      target_path: '',
      delete_source: false
    }
    this.targetDownloaderPaths = []
    this.batchResult = null
    if (this.$refs.transferForm) {
      (this.$refs.transferForm as any).clearValidate()
    }
  }

  async loadDownloaders() {
    try {
      const res = await getDownloaderList({ enabled: true })
      if (res.code === '200' && res.data) {
        // 获取所有选中种子的下载器ID
        const selectedDownloaderIds = new Set(this.torrents.map(t => t.downloaderId))
        // 过滤掉选中种子所在的下载器
        this.availableDownloaders = res.data.filter(
          (d: DownloaderSimple) => !selectedDownloaderIds.has(d.downloader_id)
        )
      }
    } catch (error) {
      this.$message.error('加载下载器列表失败')
      console.error('加载下载器列表失败:', error)
    }
  }

  async handleTargetDownloaderChange(downloaderId: number) {
    // 清空目标路径
    this.formData.target_path = ''

    // 加载目标下载器的路径列表
    try {
      const res = await getDownloaderPaths(downloaderId)
      if (res.code === '200' && res.data) {
        // 获取启用的路径
        const enabledPaths = (res.data.paths || []).filter(
          (p: DownloaderPath) => p.is_enabled
        )

        // 按path_value去重，保留id最大的（最新的记录）
        const pathMap = new Map<string, DownloaderPath>()
        enabledPaths.forEach((path: DownloaderPath) => {
          const existing = pathMap.get(path.path_value)
          if (!existing || path.id > existing.id) {
            pathMap.set(path.path_value, path)
          }
        })

        this.targetDownloaderPaths = Array.from(pathMap.values())

        // 如果有默认路径，自动填充
        const defaultPath = this.targetDownloaderPaths.find(
          (p: DownloaderPath) => p.path_type === 'default'
        )
        if (defaultPath) {
          this.formData.target_path = defaultPath.path_value
        }
      }
    } catch (error) {
      console.error('加载路径列表失败:', error)
    }
  }

  queryPathSuggestions(queryString: string, cb: any) {
    const suggestions = this.targetDownloaderPaths
      .filter(path => path.is_enabled && path.path_value.toLowerCase().includes(queryString.toLowerCase()))
      .map(path => ({
        value: path.path_value,
        path_type: path.path_type,
        torrent_count: path.torrent_count
      }))

    cb(suggestions)
  }

  handlePathSelect(item: any) {
    this.formData.target_path = item.value
  }

  async handleSubmit() {
    // 验证表单
    const form = this.$refs.transferForm as any
    if (!form) return

    try {
      await form.validate()
    } catch (error) {
      return
    }

    // 如果勾选了删除原种子，先确认
    if (this.formData.delete_source) {
      this.$confirm(
        '勾选"删除原种子"后，转移成功会自动删除原下载器种子，请谨慎操作。是否继续？',
        '确认操作',
        {
          confirmButtonText: '继续',
          cancelButtonText: '取消',
          type: 'warning'
        }
      ).then(() => {
        this.executeBatchTransfer()
      }).catch(() => {
        // 用户取消
      })
    } else {
      this.executeBatchTransfer()
    }
  }

  async executeBatchTransfer() {
    this.submitting = true

    // 获取所有选中种子的源下载器ID（假设都在同一下载器）
    if (!this.torrents || this.torrents.length === 0) {
      this.$message.error('未选择任何种子')
      this.submitting = false
      return
    }

    const sourceDownloaderId = this.getTorrentDownloaderId(this.torrents[0])
    if (!sourceDownloaderId) {
      this.$message.error('无法获取源下载器信息')
      this.submitting = false
      return
    }

    const request: SeedTransferBatchRequest = {
      source_downloader_id: sourceDownloaderId,
      target_downloader_id: this.formData.target_downloader_id,
      info_hashes: this.torrents.map(t => t.hash),
      target_path: this.formData.target_path,
      delete_source: false // 先不删除，转移成功后再处理
    }

    try {
      const res = await transferSeedsBatch(request)

      if (res.code === '200' && res.data) {
        this.batchResult = res.data

        // 关闭当前对话框
        this.dialogVisible = false
        this.$emit('update:visible', false)

        // 显示结果对话框
        this.resultDialogVisible = true
      } else {
        // 转移失败，显示错误信息
        const errorMsg = res.msg || '批量转移失败'
        this.$message.error({
          message: `批量转移失败: ${errorMsg}`,
          duration: 5000
        })
      }
    } catch (error: any) {
      console.error('批量转移异常:', error)
      const errorMsg = error.response?.data?.msg || error.message || '批量转移失败，请稍后重试'
      this.$message.error({
        message: `批量转移失败: ${errorMsg}`,
        duration: 5000
      })
    } finally {
      this.submitting = false
    }
  }

  async handleResultConfirm() {
    this.resultDialogVisible = false
    // 如果全部成功且需要删除原种子，直接执行删除
    if (this.resultFailed === 0 && this.formData.delete_source && this.resultSuccess > 0) {
      await this.batchDeleteSourceTorrents()
    } else {
      this.$emit('success')
    }
  }

  handleResultClose() {
    this.resultDialogVisible = false
  }

  get resultTotal() {
    return this.batchResult?.total_count ?? 0
  }

  get resultSuccess() {
    return this.batchResult?.success_count ?? 0
  }

  get resultFailed() {
    return this.batchResult?.failed_count ?? 0
  }

  get resultFailedItems() {
    const results = this.batchResult?.results
    if (!Array.isArray(results)) return []
    return results.filter((item: any) => !item?.success)
  }

  itemKey(item: any) {
    return item?.info_hash || item?.torrent_name || Math.random().toString(36)
  }

  async batchDeleteSourceTorrents() {
    const loading = this.$loading({
      lock: true,
      text: '正在删除原种子...',
      spinner: 'el-icon-loading',
      background: 'rgba(0, 0, 0, 0.7)'
    })

    try {
      // 并发删除所有原种子
      const promises = this.torrents.map(torrent =>
        deleteTorrents({
          info_id: torrent.infoId,
          downloader_id: torrent.downloaderId,
          delete_data: 0,
          id_recycle: 0
        })
      )

      await Promise.all(promises)

      this.$message.success(`批量转移完成，已成功删除 ${this.resultSuccess} 个原种子`)
      this.$emit('success')
    } catch (error: any) {
      console.error('批量删除原种子异常:', error)
      this.$message.error('删除原种子时发生错误，请手动检查')
      this.$emit('success')
    } finally {
      loading.close()
    }
  }

  truncatePath(path: string): string {
    const maxLength = 40
    if (path.length <= maxLength) return path
    return '...' + path.substring(path.length - maxLength)
  }

  getTorrentDownloaderId(torrent: any) {
    return torrent?.downloader_id || torrent?.downloaderId
  }

  handleClose() {
    this.dialogVisible = false
    this.$emit('update:visible', false)
  }
}
</script>

<style scoped lang="scss">
.selected-torrents-section {
  margin-bottom: 16px;
}

.section-title {
  font-weight: bold;
  margin-bottom: 12px;
  color: #303133;
}

.torrents-list {
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid #DCDFE6;
  border-radius: 4px;
  padding: 8px;
}

.torrent-item {
  padding: 8px;
  border-bottom: 1px solid #EBEEF5;

  &:last-child {
    border-bottom: none;
  }
}

.torrent-name {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
  font-weight: 500;
  color: #303133;

  i {
    margin-right: 6px;
    color: #909399;
  }

  span {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.torrent-info {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #909399;
}

.info-item {
  display: flex;
  align-items: center;

  i {
    margin-right: 4px;
  }

  span {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.path-suggestion {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;

  .path-value {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .path-type {
    margin-left: 8px;
    padding: 2px 6px;
    background-color: #E5E7EB;
    color: #374151;
    font-size: 12px;
    border-radius: 3px;
  }

  .torrent-count {
    margin-left: 8px;
    color: #9CA3AF;
    font-size: 12px;
  }
}

.result-summary {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.success-count {
  color: #67C23A;
}

.failed-count {
  color: #F56C6C;
}

.failed-list {
  margin-top: 8px;
}

.failed-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.failed-items {
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid #EBEEF5;
  border-radius: 4px;
  padding: 8px;
}

.failed-item {
  padding: 6px 4px;
  border-bottom: 1px solid #F2F6FC;

  &:last-child {
    border-bottom: none;
  }
}

.failed-name {
  font-weight: 500;
}

.failed-reason {
  color: #F56C6C;
  font-size: 12px;
}
</style>
