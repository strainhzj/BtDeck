<template>
  <el-dialog
    :title="dialogTitle"
    :visible.sync="dialogVisible"
    width="520px"
    :close-on-click-modal="false"
    custom-class="management-dialog"
    append-to-body
  >
    <div v-loading="loading">
      <!-- 操作类型：删除 / 移动到其它池 -->
      <el-radio-group v-model="actionType" :disabled="loading" class="quick-action-type-group">
        <el-radio-button label="delete">{{ $t('tracker.quickAction.deleteMode') }}</el-radio-button>
        <el-radio-button label="move">{{ $t('tracker.quickAction.moveMode') }}</el-radio-button>
      </el-radio-group>

      <el-alert type="info" :closable="false" show-icon :title="$t('tracker.quickAction.alertTitle')">
        <template slot="default">
          <p v-html="$t('tracker.quickAction.alertBody', {pool: sourcePoolLabel})"></p>
          <p v-if="actionType === 'delete'">{{ $t('tracker.quickAction.deleteHint') }}</p>
          <p v-else>{{ $t('tracker.quickAction.moveHint') }}</p>
        </template>
      </el-alert>
      <div style="margin-top: 16px">
        <label for="quick-action-prefix" style="display:block; margin-bottom: 6px; font-weight: 600">{{ $t('tracker.quickAction.prefixLabel') }}</label>
        <el-input
          id="quick-action-prefix"
          v-model="prefix"
          :placeholder="$t('tracker.quickAction.prefixPlaceholder')"
          clearable
          :disabled="loading"
          @keyup.enter.native="handleConfirm"
        />
      </div>
      <!-- 移动目标池子（仅移动模式显示，排除 candidate 与源池子） -->
      <div v-if="actionType === 'move'" style="margin-top: 16px">
        <label for="quick-action-target" style="display:block; margin-bottom: 6px; font-weight: 600">{{ $t('tracker.quickAction.targetLabel') }}</label>
        <el-select
          id="quick-action-target"
          v-model="targetPool"
          :disabled="loading"
          style="width: 100%"
        >
          <el-option
            v-for="opt in availableTargetPools"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
    </div>
    <span slot="footer" class="dialog-footer">
      <el-button :disabled="loading" @click="handleCancel">{{ $t('tracker.pools.dialog.cancel') }}</el-button>
      <el-button type="primary" :loading="loading" @click="handleConfirm">{{ $t('tracker.pools.dialog.confirm') }}</el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import { batchDeleteKeywords, batchMoveKeywords, keywordPrefixMatchPreview, PoolType } from '@/api/tracker'
import { poolLabel } from '@/utils/tracker'
import { apiErrorMessage, apiResponseMessage, translate } from '@/i18n'

interface SuccessPayload {
  sourcePool: PoolType
  /** 移动模式的目标池；删除模式为 null */
  targetPool: PoolType | null
}

@Component({
  name: 'KeywordQuickActionDialog'
})
export default class KeywordQuickActionDialog extends Vue {
  @Prop({ required: true }) visible!: boolean
  @Prop({ required: true }) sourcePool!: PoolType
  @Prop({ default: '' }) sourcePoolLabel!: string
  /** 源池关键词总数（可选）；传入 0 时触发"源池为空"门禁，不传则跳过（由预览 0 命中兜底） */
  @Prop({ default: undefined }) sourcePoolCount!: number | undefined

  actionType: 'delete' | 'move' = 'delete'
  targetPool: PoolType = 'ignored'
  prefix = ''
  loading = false

  get dialogVisible(): boolean {
    return this.visible
  }

  set dialogVisible(val: boolean) {
    this.$emit('update:visible', val)
  }

  get dialogTitle(): string {
    const base = this.actionType === 'delete'
      ? this.$t('tracker.quickAction.deleteTitle')
      : this.$t('tracker.quickAction.moveTitle')
    return base + this.$t('tracker.quickAction.titleSuffix')
  }

  // 移动目标池子候选（排除 candidate 系统自动生成池 + 当前源池子；标签随语言切换响应式）
  get availableTargetPools(): { value: PoolType, label: string }[] {
    return (['ignored', 'success', 'failed'] as PoolType[])
      .filter(poolType => poolType !== this.sourcePool)
      .map(poolType => ({ value: poolType, label: poolLabel(poolType) }))
  }

  @Watch('visible')
  onVisibleChange(val: boolean) {
    if (val) {
      // 每次打开重置状态
      this.prefix = ''
      this.actionType = 'delete'
      this.targetPool = this.sourcePool === 'ignored' ? 'success' : 'ignored'
    }
  }

  handleCancel() {
    this.$emit('update:visible', false)
  }

  /**
   * 确认执行快捷操作：门禁 → 预览 → 二次确认 → 执行 → 通知父组件刷新。
   * 对齐 orphan-files 快捷操作流程（handleQuickActionConfirm）。
   */
  async handleConfirm() {
    const prefix = this.prefix.trim()
    const sourcePool = this.sourcePool

    // 门禁 1：前缀非空
    if (!prefix) {
      this.$message.warning(this.$t('tracker.quickAction.requirePrefix'))
      return
    }

    // 门禁 2：源池为空（仅当父组件传入 count 时生效）
    if (this.sourcePoolCount !== undefined && this.sourcePoolCount === 0) {
      this.$message.warning(this.$t('tracker.quickAction.emptyPool'))
      return
    }

    // 门禁 3：移动模式源==目标
    if (this.actionType === 'move' && sourcePool === this.targetPool) {
      this.$message.warning(this.$t('tracker.quickAction.sameTarget'))
      return
    }

    this.loading = true
    try {
      // 预览命中
      const resp = await keywordPrefixMatchPreview({ pool_type: sourcePool, prefix })
      if (resp.code !== '200' || !resp.data) {
        this.$message.error(apiResponseMessage(resp, this.$t('tracker.quickAction.previewFailed')))
        return
      }

      // 0 命中
      if (resp.data.count === 0) {
        this.$message.info(this.$t('tracker.quickAction.noMatch'))
        return
      }

      // 二次确认文案（附带 sample 前 5 条供核对）
      const sampleText = resp.data.sample_keywords.slice(0, 5).join('、')
      const more = resp.data.count > 5 ? this.$t('tracker.quickAction.sampleMore') : ''
      const sampleHint = sampleText
        ? this.$t('tracker.quickAction.sampleLine', { sample: sampleText, more })
        : ''
      const isDelete = this.actionType === 'delete'
      const targetLabel = poolLabel(this.targetPool)
      const confirmText = isDelete
        ? this.$t('tracker.quickAction.confirmDeleteText', { count: resp.data.count, sample: sampleHint })
        : this.$t('tracker.quickAction.confirmMoveText', { count: resp.data.count, pool: targetLabel, sample: sampleHint })

      try {
        await this.$confirm(confirmText, this.$t('tracker.pools.dialog.notice'), {
          confirmButtonText: this.$t('tracker.pools.dialog.confirm'),
          cancelButtonText: this.$t('tracker.pools.dialog.cancel'),
          type: isDelete ? 'warning' : 'info',
          dangerouslyUseHTMLString: false
        })
      } catch {
        // 用户取消二次确认：复位 loading，保留对话框与前缀，便于改前缀重试
        this.loading = false
        return
      }

      // 执行
      const keywordIds = resp.data.keyword_ids
      let payload: SuccessPayload
      if (isDelete) {
        await batchDeleteKeywords({ keyword_ids: keywordIds })
        this.$message.success(this.$t('tracker.quickAction.deleted', { count: resp.data.count }))
        payload = { sourcePool, targetPool: null }
      } else {
        await batchMoveKeywords({ keyword_ids: keywordIds, target_pool: this.targetPool })
        this.$message.success(this.$t('tracker.quickAction.moved', { count: resp.data.count, pool: targetLabel }))
        payload = { sourcePool, targetPool: this.targetPool }
      }

      this.$emit('success', payload)
      this.$emit('update:visible', false)
    } catch (error: any) {
      console.error('快捷操作失败:', error)
      this.$message.error(apiErrorMessage(error, translate('tracker.errors.operationFailed')))
    } finally {
      this.loading = false
    }
  }
}
</script>

<style lang="scss" scoped>
.quick-action-type-group {
  display: flex;
  margin-bottom: 16px;
}
</style>
