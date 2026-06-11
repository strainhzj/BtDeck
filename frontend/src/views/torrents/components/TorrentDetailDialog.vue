<template>
  <el-dialog
    title="种子详情"
    :visible.sync="visible"
    width="800px"
  >
    <el-descriptions v-if="torrent" :column="2" border>
      <el-descriptions-item label="种子名称">{{ torrent.name }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="getStatusType(torrent.status)">{{ torrent.status }}</el-tag>
      </el-descriptions-item>

      <el-descriptions-item label="文件大小">
        {{ formatSize(torrent.size) }}
      </el-descriptions-item>

      <el-descriptions-item label="进度">
        <el-progress :percentage="getProgress(torrent)" />
      </el-descriptions-item>

      <el-descriptions-item label="下载速度">
        {{ formatSpeed(torrent.downloadSpeed) }}
      </el-descriptions-item>

      <el-descriptions-item label="上传速度">
        {{ formatSpeed(torrent.uploadSpeed) }}
      </el-descriptions-item>

      <el-descriptions-item label="添加时间">
        {{ formatDate(torrent.addedDate) }}
      </el-descriptions-item>

      <el-descriptions-item label="完成时间">
        {{ torrent.completedDate ? formatDate(torrent.completedDate) : '未完成' }}
      </el-descriptions-item>

      <el-descriptions-item label="分享比率">
        {{ torrent.ratio || '-' }}
      </el-descriptions-item>

      <el-descriptions-item label="保存路径" :span="2">
        {{ torrent.savePath }}
      </el-descriptions-item>

      <el-descriptions-item label="标签" :span="2">
        <el-tag v-for="(tag, index) in tags" :key="index" size="small" style="margin-right: 5px">
          {{ tag }}
        </el-tag>
      </el-descriptions-item>
    </el-descriptions>

    <el-divider />

    <div class="tracker-info">
      <h4>Tracker信息</h4>
      <el-table :data="torrent.trackerInfo" size="small" max-height="300">
        <el-table-column prop="trackerName" label="名称" />
        <el-table-column prop="trackerUrl" label="URL" show-overflow-tooltip />
        <el-table-column label="状态">
          <template slot-scope="scope">
            <el-tag :type="scope.row.lastAnnounceSucceeded === 'True' ? 'success' : 'danger'" size="small">
              {{ scope.row.lastAnnounceSucceeded === 'True' ? '正常' : '异常' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <span slot="footer" class="dialog-footer">
      <el-button type="primary" @click="handleTransfer">
        <i class="el-icon-sort" />
        转移
      </el-button>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
    </span>

    <!-- 转移对话框 -->
    <transfer-dialog
      :visible.sync="transferDialogVisible"
      :torrent="torrent"
      @success="handleTransferSuccess"
    />
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'
import TransferDialog from './TransferDialog.vue'

@Component({
  components: {
    TransferDialog
  }
})
export default class TorrentDetailDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  @Prop(Object) torrent!: any

  // 转移对话框显示状态
  transferDialogVisible = false

  get tags() {
    return this.torrent?.tags?.split(',').filter(Boolean) || []
  }

  formatSize(bytes: number): string {
    if (!bytes) return '0 B'
    const k = 1024
    const m = 1024 * 1024
    const g = 1024 * 1024 * 1024
    if (bytes >= g) return (bytes / g).toFixed(2) + ' GB'
    if (bytes >= m) return (bytes / m).toFixed(2) + ' MB'
    if (bytes >= k) return (bytes / k).toFixed(2) + ' KB'
    return bytes + ' B'
  }

  formatSpeed(speed: number | null): string {
    if (!speed) return '0 B/s'
    return this.formatSize(speed) + '/s'
  }

  formatDate(dateStr: string): string {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString('zh-CN')
  }

  getProgress(torrent: any): number {
    if (!torrent.progress) return 0
    return Math.round(torrent.progress)
  }

  getStatusType(status: string): string {
    const types: Record<string, string> = {
      downloading: 'primary',
      uploading: 'success',
      paused: 'info',
      error: 'danger',
      completed: 'success'
    }
    return types[status] || 'info'
  }

  handleTransfer() {
    this.transferDialogVisible = true
  }

  handleTransferSuccess() {
    // 转移成功，关闭详情对话框并通知父组件刷新
    this.$emit('transfer-success')
    this.$emit('update:visible', false)
  }
}
</script>

<style scoped>
.tracker-info {
  margin-top: 20px;
}

.tracker-info h4 {
  margin-bottom: 10px;
}
</style>
