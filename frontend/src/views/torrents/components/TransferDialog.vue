<template>
  <el-dialog
    title="转移种子"
    :visible.sync="dialogVisible"
    width="600px"
    :before-close="handleClose"
    :close-on-click-modal="false"
  >
    <el-form
      ref="transferForm"
      :model="formData"
      :rules="formRules"
      label-width="120px"
      @submit.native.prevent
    >
      <!-- 当前下载器信息 -->
      <el-form-item label="当前下载器:">
        <span class="info-text">{{ currentDownloaderName }}</span>
      </el-form-item>

      <!-- 当前路径信息 -->
      <el-form-item label="当前路径:">
        <span class="info-text">{{ currentPath }}</span>
      </el-form-item>

      <el-divider />

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
              <span class="path-type">{{ item.path_type === 'default' ? '默认路径' : '在用路径' }}</span>
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

    <!-- 删除确认对话框 -->
    <el-dialog
      width="400px"
      title="确认删除原种子"
      :visible.sync="deleteConfirmVisible"
      append-to-body
    >
      <div class="delete-confirm-content">
        <i class="el-icon-warning" style="color: #F59E0B; font-size: 48px; margin-bottom: 16px;" />
        <p style="margin-bottom: 8px;">种子已成功转移到目标下载器</p>
        <p style="color: #EF4444; font-weight: bold;">是否删除原下载器中的种子？</p>
        <p style="color: #909399; font-size: 12px; margin-top: 12px;">此操作不可逆，请谨慎选择</p>
      </div>
      <span slot="footer" class="dialog-footer">
        <el-button @click="deleteConfirmVisible = false">取消</el-button>
        <el-button
          type="danger"
          :loading="deleting"
          @click="handleConfirmDelete"
        >
          {{ deleting ? '删除中...' : '确认删除' }}
        </el-button>
      </span>
    </el-dialog>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import {
  transferSeed,
  getDownloaderList,
  getDownloaderPaths,
  deleteTorrents,
  type DownloaderSimple,
  type DownloaderPath,
  type SeedTransferRequest
} from '@/api/torrents'

@Component
export default class TransferDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  @Prop(Object) torrent!: any

  // 对话框显示状态
  dialogVisible = false

  // 表单数据
  formData: {
    target_downloader_id: number | null
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
        validator: (rule: any, value: number, callback: Function) => {
          if (value === this.torrent?.downloaderId) {
            callback(new Error('目标下载器不能与当前下载器相同'))
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
  deleting = false

  // 删除确认对话框显示状态
  deleteConfirmVisible = false

  // 转移成功后的数据（用于删除确认）
  transferResult: any = null

  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.initDialog()
    }
  }

  get currentDownloaderName(): string {
    return this.torrent?.downloaderName || '-'
  }

  get currentPath(): string {
    return this.torrent?.savePath || '-'
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
    this.transferResult = null
    if (this.$refs.transferForm) {
      (this.$refs.transferForm as any).clearValidate()
    }
  }

  async loadDownloaders() {
    try {
      const res = await getDownloaderList({ enabled: true })
      if (res.code === '200' && res.data) {
        // 过滤掉当前下载器
        this.availableDownloaders = res.data.filter(
          (d: DownloaderSimple) => d.downloader_id !== this.torrent?.downloaderId
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
        this.targetDownloaderPaths = res.data.paths.filter(
          (p: DownloaderPath) => p.is_enabled
        )

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
        '勾选"删除原种子"后，转移成功会自动删除原下载器种子，请谨慎操作',
        '确认操作',
        {
          confirmButtonText: '继续',
          cancelButtonText: '取消',
          type: 'warning'
        }
      ).then(() => {
        this.executeTransfer()
      }).catch(() => {
        // 用户取消
      })
    } else {
      this.executeTransfer()
    }
  }

  async executeTransfer() {
    this.submitting = true

    const request: SeedTransferRequest = {
      source_downloader_id: this.torrent.downloaderId,
      target_downloader_id: this.formData.target_downloader_id as number,
      info_hash: this.torrent.hash,
      target_path: this.formData.target_path,
      delete_source: false // 先不删除，转移成功后再处理
    }

    try {
      const res = await transferSeed(request)

      if (res.code === '200' && res.data?.success) {
        this.transferResult = res.data

        // 转移成功
        if (this.formData.delete_source) {
          // 直接执行删除，不显示确认对话框
          await this.handleConfirmDelete()
        } else {
          this.$message.success('种子转移成功')
          this.handleClose()
          this.$emit('success')
        }
      } else {
        // 转移失败，显示错误信息
        const errorMsg = res.data?.error_message || res.msg || '种子转移失败'
        this.$message.error({
          message: `种子转移失败: ${errorMsg}`,
          duration: 5000
        })
      }
    } catch (error: any) {
      console.error('种子转移异常:', error)
      const errorMsg = error.response?.data?.msg || error.message || '种子转移失败，请稍后重试'
      this.$message.error({
        message: `种子转移失败: ${errorMsg}`,
        duration: 5000
      })
    } finally {
      this.submitting = false
    }
  }

  async handleConfirmDelete() {
    this.deleting = true

    try {
      const res = await deleteTorrents({
        info_id: this.torrent.infoId,
        downloader_id: this.torrent.downloaderId,
        delete_data: 0,
        id_recycle: 0
      })

      if (res.code === '200') {
        this.$message.success('种子转移成功，原种子已删除')
        this.deleteConfirmVisible = false
        this.handleClose()
        this.$emit('success')
      } else {
        this.$message.error(res.msg || '删除原种子失败')
        this.deleteConfirmVisible = false
        this.handleClose()
        this.$emit('success')
      }
    } catch (error: any) {
      console.error('删除原种子异常:', error)
      this.$message.error(error.response?.data?.msg || '删除原种子失败')
      this.deleteConfirmVisible = false
      this.handleClose()
      this.$emit('success')
    } finally {
      this.deleting = false
    }
  }

  handleClose() {
    this.dialogVisible = false
    this.$emit('update:visible', false)
  }
}
</script>

<style scoped lang="scss">
.info-text {
  color: #606266;
  font-size: 14px;
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

.delete-confirm-content {
  text-align: center;
  padding: 20px;
}
</style>
