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
        <el-radio-button label="delete">删除</el-radio-button>
        <el-radio-button label="move">移动到其它池</el-radio-button>
      </el-radio-group>

      <el-alert type="info" :closable="false" show-icon title="按关键词文本前缀左匹配本池关键词">
        <template slot="default">
          <p>
            输入前缀，将匹配所有<strong>{{ sourcePoolLabel }}</strong>中<strong>关键词文本</strong>以此开头的词（排除已删除）。
          </p>
          <p v-if="actionType === 'delete'">删除后关键词进入逻辑删除状态。</p>
          <p v-else>移动后关键词进入目标池，并按前缀批量迁移。</p>
        </template>
      </el-alert>
      <div style="margin-top: 16px">
        <label for="quick-action-prefix" style="display:block; margin-bottom: 6px; font-weight: 600">关键词前缀</label>
        <el-input
          id="quick-action-prefix"
          v-model="prefix"
          placeholder="例如：success- 或 50%"
          clearable
          :disabled="loading"
          @keyup.enter.native="handleConfirm"
        />
      </div>
      <!-- 移动目标池子（仅移动模式显示，排除 candidate 与源池子） -->
      <div v-if="actionType === 'move'" style="margin-top: 16px">
        <label for="quick-action-target" style="display:block; margin-bottom: 6px; font-weight: 600">移动到池子</label>
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
      <el-button :disabled="loading" @click="handleCancel">取消</el-button>
      <el-button type="primary" :loading="loading" @click="handleConfirm">确定</el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import { batchDeleteKeywords, batchMoveKeywords, keywordPrefixMatchPreview, PoolType } from '@/api/tracker'
import { extractErrorMessage } from '@/utils/tracker'

const POOL_LABELS: Record<PoolType, string> = {
  candidate: '候选池',
  ignored: '忽略池',
  success: '成功池',
  failed: '失败池'
}

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
    const base = this.actionType === 'delete' ? '快捷删除' : '快捷移动'
    return `${base}（按前缀）`
  }

  // 移动目标池子候选（排除 candidate 系统自动生成池 + 当前源池子）
  get availableTargetPools(): { value: PoolType, label: string }[] {
    return (Object.keys(POOL_LABELS) as PoolType[])
      .filter(poolType => poolType !== 'candidate' && poolType !== this.sourcePool)
      .map(poolType => ({ value: poolType, label: POOL_LABELS[poolType] }))
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
      this.$message.warning('请输入关键词前缀')
      return
    }

    // 门禁 2：源池为空（仅当父组件传入 count 时生效）
    if (this.sourcePoolCount !== undefined && this.sourcePoolCount === 0) {
      this.$message.warning('该池没有关键词')
      return
    }

    // 门禁 3：移动模式源==目标
    if (this.actionType === 'move' && sourcePool === this.targetPool) {
      this.$message.warning('不能移动到原池子')
      return
    }

    this.loading = true
    try {
      // 预览命中
      const resp = await keywordPrefixMatchPreview({ pool_type: sourcePool, prefix })
      if (resp.code !== '200' || !resp.data) {
        this.$message.error(resp.msg || '预览失败')
        return
      }

      // 0 命中
      if (resp.data.count === 0) {
        this.$message.info('没有匹配的关键词')
        return
      }

      // 二次确认文案（附带 sample 前 5 条供核对）
      const sampleText = resp.data.sample_keywords.slice(0, 5).join('、')
      const sampleHint = sampleText ? `\n匹配样本：${sampleText}${resp.data.count > 5 ? ' …' : ''}` : ''
      const isDelete = this.actionType === 'delete'
      const targetLabel = POOL_LABELS[this.targetPool] || this.targetPool
      const confirmText = isDelete
        ? `将删除 ${resp.data.count} 个匹配的关键词。${sampleHint}\n\n确认删除？`
        : `将移动 ${resp.data.count} 个关键词到${targetLabel}。${sampleHint}\n\n确认移动？`

      try {
        await this.$confirm(confirmText, '提示', {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
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
        this.$message.success(`已删除 ${resp.data.count} 个关键词`)
        payload = { sourcePool, targetPool: null }
      } else {
        await batchMoveKeywords({ keyword_ids: keywordIds, target_pool: this.targetPool })
        this.$message.success(`已移动 ${resp.data.count} 个关键词到${targetLabel}`)
        payload = { sourcePool, targetPool: this.targetPool }
      }

      this.$emit('success', payload)
      this.$emit('update:visible', false)
    } catch (error: any) {
      console.error('快捷操作失败:', error)
      const errorMsg = extractErrorMessage(error, '操作失败')
      this.$message.error(errorMsg)
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
