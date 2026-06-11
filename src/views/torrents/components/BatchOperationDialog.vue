<template>
  <el-dialog
    :title="dialogTitle"
    :visible.sync="visible"
    width="500px"
    :before-close="handleClose"
  >
    <div class="batch-operation-content">
      <el-alert
        :type="alertType"
        :closable="false"
        show-icon
      >
        <template slot="title">
          {{ operationMessage }}
        </template>
      </el-alert>

      <div class="operation-details">
        <p><strong>操作类型：</strong>{{ operationText }}</p>
        <p><strong>影响数量：</strong>{{ selectedCount }} 个种子</p>
      </div>

      <el-divider />

      <div class="affected-items">
        <h4>受影响的种子：</h4>
        <el-scrollbar style="height: 200px">
          <ul>
            <li v-for="item in selectedItems" :key="item.info_id">
              {{ item.name }} ({{ formatSize(item.size) }})
            </li>
          </ul>
        </el-scrollbar>
      </div>
    </div>

    <span slot="footer" class="dialog-footer">
      <el-button @click="handleClose">取消</el-button>
      <el-button :type="confirmButtonType" @click="handleConfirm" :loading="loading">
        确认{{ operationText }}
      </el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop } from 'vue-property-decorator'

@Component
export default class BatchOperationDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  @Prop(String) operation!: string
  @Prop(Array) selectedItems!: any[]

  private loading = false

  get dialogTitle() {
    const titles: Record<string, string> = {
      delete: '批量删除确认',
      pause: '批量暂停确认',
      resume: '批量恢复确认',
      start: '批量开始确认'
    }
    return titles[this.operation] || '批量操作确认'
  }

  get operationText() {
    const texts: Record<string, string> = {
      delete: '删除',
      pause: '暂停',
      resume: '恢复',
      start: '开始'
    }
    return texts[this.operation] || '操作'
  }

  get alertType() {
    return this.operation === 'delete' ? 'error' : 'warning'
  }

  get confirmButtonType() {
    return this.operation === 'delete' ? 'danger' : 'primary'
  }

  get operationMessage() {
    const messages: Record<string, string> = {
      delete: '您确定要删除这些种子吗？此操作不可撤销！',
      pause: '您确定要暂停这些种子吗？',
      resume: '您确定要恢复这些种子吗？',
      start: '您确定要开始这些种子吗？'
    }
    return messages[this.operation] || '您确定要执行此操作吗？'
  }

  get selectedCount() {
    return this.selectedItems.length
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

  handleConfirm() {
    this.$emit('confirm', this.operation, this.selectedItems)
  }

  handleClose() {
    this.$emit('update:visible', false)
  }
}
</script>

<style scoped>
.batch-operation-content {
  padding: 10px 0;
}

.operation-details p {
  margin: 8px 0;
}

.affected-items h4 {
  margin-bottom: 10px;
}

.affected-items ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.affected-items li {
  padding: 8px;
  border-bottom: 1px solid #eee;
}

.affected-items li:last-child {
  border-bottom: none;
}
</style>
