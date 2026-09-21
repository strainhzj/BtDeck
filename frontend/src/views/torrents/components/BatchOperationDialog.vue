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
        <p><strong>{{ $t('torrent.batchDialog.opType') }}</strong>{{ operationText }}</p>
        <p><strong>{{ $t('torrent.batchDialog.affectCount') }}</strong>{{ $t('torrent.batchDialog.countTorrents', {count: selectedCount}) }}</p>
      </div>

      <el-divider />

      <div class="affected-items">
        <h4>{{ $t('torrent.batchDialog.affected') }}</h4>
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
      <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
      <el-button :type="confirmButtonType" @click="handleConfirm" :loading="loading">
        {{ $t('torrent.batchDialog.confirmAction', {op: operationText}) }}
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
    const key = `torrent.batchDialog.title.${this.operation}`
    return this.$te(key) ? this.$t(key) : this.$t('torrent.batchDialog.title.fallback')
  }

  get operationText() {
    const key = `torrent.batchDialog.op.${this.operation}`
    return this.$te(key) ? this.$t(key) : this.$t('torrent.batchDialog.op.fallback')
  }

  get alertType() {
    return this.operation === 'delete' ? 'error' : 'warning'
  }

  get confirmButtonType() {
    return this.operation === 'delete' ? 'danger' : 'primary'
  }

  get operationMessage() {
    const key = `torrent.batchDialog.message.${this.operation}`
    return this.$te(key) ? this.$t(key) : this.$t('torrent.batchDialog.message.fallback')
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
