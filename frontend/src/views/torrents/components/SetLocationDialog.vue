<template>
  <div>
    <el-dialog
      :title="`修改保存路径（已选择${torrents.length}个种子）`"
      :visible.sync="dialogVisible"
      width="650px"
      :before-close="handleClose"
      :close-on-click-modal="false"
    >
      <!-- 当前路径信息 -->
      <div class="current-path-section">
        <div class="section-title">当前路径：</div>
        <div class="path-info">
          <el-tag type="info" size="medium">
            <i class="el-icon-folder" />
            {{ currentPath }}
          </el-tag>
        </div>
      </div>

      <el-divider />

      <el-form
        ref="locationForm"
        :model="formData"
        :rules="formRules"
        label-width="110px"
        @submit.native.prevent
      >
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

        <!-- 是否移动文件选项 -->
        <el-form-item>
          <el-checkbox v-model="formData.move_files">
            移动已下载的文件
            <el-tooltip
              content="勾选后会将已下载的文件移动到新路径，否则仅修改保存路径不影响现有文件"
              placement="top"
            >
              <i class="el-icon-question" />
            </el-tooltip>
          </el-checkbox>
        </el-form-item>
      </el-form>

      <span slot="footer" class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ submitting ? '提交中...' : '确定' }}
        </el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import {
  setTorrentLocation,
  getDownloaderPaths,
  type SetLocationRequest
} from '@/api/torrents'
import { getDownloaderId } from '@/utils/formatters'

@Component
export default class SetLocationDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  @Prop(Array) torrents!: any[]

  // 对话框显示状态
  dialogVisible = false

  // 表单数据
  formData: {
    target_path: string
    move_files: boolean
  } = {
    target_path: '',
    move_files: true
  }

  // 表单验证规则
  formRules = {
    target_path: [
      { required: true, message: '请输入目标路径', trigger: 'blur' }
    ]
  }

  // 下载器路径列表
  downloaderPaths: any[] = []

  // 提交状态
  submitting = false

  // 当前路径（所有选中的种子应该在同一下载器）
  get currentPath(): string {
    if (!this.torrents || this.torrents.length === 0) {
      return '-'
    }
    // 显示第一个种子的路径
    const first = this.torrents[0]
    return first?.savePath || first?.save_path || '-'
  }

  get downloaderId(): string {
    if (!this.torrents || this.torrents.length === 0) {
      return ''
    }
    return getDownloaderId(this.torrents[0])
  }

  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.initDialog()
    }
  }

  async initDialog() {
    const vm = this
    // 重置表单
    vm.resetForm()

    // 加载下载器路径列表
    await vm.loadDownloaderPaths()
  }

  resetForm() {
    this.formData = {
      target_path: '',
      move_files: true
    }
    if (this.$refs.locationForm) {
      (this.$refs.locationForm as any).clearValidate()
    }
  }

  async loadDownloaderPaths() {
    const vm = this
    const downloaderId = vm.downloaderId
    if (!downloaderId) {
      return
    }

    try {
      const res = await getDownloaderPaths(downloaderId)
      if (res.code === '200' && res.data) {
        // 获取启用的路径
        vm.downloaderPaths = (res.data.paths || []).filter((p: any) => p.is_enabled)

        // 按path_value去重，保留id最大的（最新的记录）
        const pathMap = new Map<string, any>()
        vm.downloaderPaths.forEach((path: any) => {
          const existing = pathMap.get(path.path_value)
          if (!existing || path.id > existing.id) {
            pathMap.set(path.path_value, path)
          }
        })

        vm.downloaderPaths = Array.from(pathMap.values())

        // 如果有默认路径，自动填充
        const defaultPath = vm.downloaderPaths.find((p: any) => p.path_type === 'default')
        if (defaultPath && defaultPath.path_value !== vm.currentPath) {
          vm.formData.target_path = defaultPath.path_value
        }
      }
    } catch (error) {
      console.error('加载路径列表失败:', error)
    }
  }

  queryPathSuggestions(queryString: string, cb: any) {
    const suggestions = this.downloaderPaths
      .filter(path => path.path_value.toLowerCase().includes(queryString.toLowerCase()))
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
    const vm = this
    // 验证表单
    const form = vm.$refs.locationForm as any
    if (!form) return

    try {
      await form.validate()
    } catch (error) {
      return
    }

    // 二次确认
    const confirmMsg = vm.formData.move_files
      ? `确认将 ${vm.torrents.length} 个种子移动到新路径？\n这将移动已下载的文件到: ${vm.formData.target_path}`
      : `确认修改 ${vm.torrents.length} 个种子的保存路径？\n仅修改路径，不移动文件。`

    try {
      await vm.$confirm(confirmMsg, '确认操作', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })

      await vm.executeSetLocation()
    } catch {
      // 用户取消
    }
  }

  async executeSetLocation() {
    const vm = this
    vm.submitting = true

    const request: SetLocationRequest = {
      downloader_id: vm.downloaderId,
      hashes: vm.torrents.map(t => t.hash),
      target_path: vm.formData.target_path,
      move_files: vm.formData.move_files
    }

    try {
      const res = await setTorrentLocation(request)

      if (res.code === '200' && res.data) {
        const { success, moved_count, failed_count } = res.data

        // 显示提示消息（不阻塞）
        if (success) {
          vm.$message.success({
            message: `成功提交${moved_count}个种子路径修改请求，正在后台处理...`,
            duration: 3000
          })

          // 关闭对话框
          vm.dialogVisible = false
          vm.$emit('update:visible', false)

          // 通知父组件刷新列表
          vm.$emit('success')
        } else {
          vm.$message.error({
            message: res.data.error_message || '修改路径失败',
            duration: 5000
          })
        }
      } else {
        vm.$message.error({
          message: res.msg || '修改路径失败',
          duration: 5000
        })
      }
    } catch (error: any) {
      console.error('修改路径异常:', error)
      const errorMsg = error.response?.data?.msg || error.message || '修改路径失败，请稍后重试'
      vm.$message.error({
        message: errorMsg,
        duration: 5000
      })
    } finally {
      vm.submitting = false
    }
  }

  handleClose() {
    this.dialogVisible = false
    this.$emit('update:visible', false)
  }
}
</script>

<style scoped lang="scss">
.current-path-section {
  margin-bottom: 16px;
}

.section-title {
  font-weight: bold;
  margin-bottom: 12px;
  color: #303133;
}

.path-info {
  .el-tag {
    max-width: 100%;
    i {
      margin-right: 6px;
    }
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
</style>
