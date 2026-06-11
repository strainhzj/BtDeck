<template>
  <el-dialog
    :visible.sync="dialogVisible"
    :title="dialogTitle"
    width="500px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    @close="handleClose"
  >
    <div class="dialog-body">
      <div class="form-group">
        <label class="form-label">关键词内容 *</label>
        <input
          ref="keywordInput"
          v-model="keywordForm.keyword"
          type="text"
          class="form-input"
          placeholder="请输入关键词"
          @keypress.enter="handleConfirm"
        >
        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
      </div>
    </div>

    <div slot="footer" class="dialog-footer">
      <button class="btn btn-secondary" @click="handleClose">取消</button>
      <button class="btn btn-primary" :disabled="!keywordForm.keyword || loading" @click="handleConfirm">
        <span v-if="loading" class="spinner"></span>
        <span>{{ loading ? '添加中...' : '确定添加' }}</span>
      </button>
    </div>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { createKeyword } from '@/api/tracker'
import { PoolType } from '@/api/tracker'
import { extractErrorMessage } from '@/utils/tracker'

interface KeywordForm {
  keyword: string
}

@Component({
  name: 'AddKeywordDialog'
})
export default class AddKeywordDialog extends Vue {
  @Prop({ type: Boolean, default: false }) visible!: boolean
  @Prop({ type: String, required: true }) poolType!: PoolType
  @Prop({ type: String, required: true }) poolLabel!: string

  dialogVisible = false
  loading = false
  errorMessage = ''
  keywordForm: KeywordForm = {
    keyword: ''
  }

  poolTypeMap: Record<PoolType, 'success' | 'failed' | 'ignored'> = {
    success: 'success',
    failed: 'failed',
    ignored: 'ignored',
    candidate: 'ignored' // 候选池不允许添加,默认使用ignored
  }

  get dialogTitle(): string {
    return `添加关键词到 ${this.poolLabel}`
  }

  get keywordType(): 'success' | 'failed' | 'ignored' {
    return this.poolTypeMap[this.poolType] || 'ignored'
  }

  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.resetForm()
      this.$nextTick(() => {
        (this.$refs.keywordInput as HTMLInputElement)?.focus()
      })
    }
  }

  @Watch('dialogVisible')
  onDialogVisibleChange(val: boolean) {
    this.$emit('update:visible', val)
  }

  resetForm() {
    this.keywordForm = {
      keyword: ''
    }
    this.errorMessage = ''
    this.loading = false
  }

  validateKeyword(): boolean {
    if (!this.keywordForm.keyword || !this.keywordForm.keyword.trim()) {
      this.errorMessage = '关键词不能为空'
      return false
    }

    if (this.keywordForm.keyword.trim().length > 100) {
      this.errorMessage = '关键词长度不能超过100个字符'
      return false
    }

    this.errorMessage = ''
    return true
  }

  async handleConfirm() {
    if (!this.validateKeyword()) {
      return
    }

    this.loading = true
    this.errorMessage = ''

    try {
      const response = await createKeyword({
        keyword: this.keywordForm.keyword.trim(),
        keyword_type: this.keywordType,
        enabled: true,
        priority: 1
      })

      if (response.code === '200') {
        this.$message.success(`已添加关键词 "${this.keywordForm.keyword}" 到 ${this.poolLabel}`)
        this.$emit('success')
        this.handleClose()
      } else {
        this.errorMessage = response.msg || '添加关键词失败'
      }
    } catch (error: any) {
      console.error('添加关键词失败:', error)
      this.errorMessage = extractErrorMessage(error, '添加关键词失败,请稍后重试')
    } finally {
      this.loading = false
    }
  }

  handleClose() {
    this.dialogVisible = false
  }
}
</script>

<style lang="scss" scoped>
.dialog-body {
  padding: var(--spacing-md) 0;
}

.form-group {
  margin-bottom: var(--spacing-lg);
}

.form-label {
  display: block;
  margin-bottom: var(--spacing-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
}

.form-input {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 2px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  transition: all 0.2s;
  color: var(--color-text-primary);
  background: var(--color-bg-primary);

  &:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1);
  }

  &::placeholder {
    color: var(--color-text-secondary);
  }
}

.error-message {
  color: var(--color-error);
  font-size: var(--font-size-xs);
  margin-top: var(--spacing-xs);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}

.btn {
  padding: var(--spacing-sm) var(--spacing-lg);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.btn-secondary {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border-primary);

  &:hover {
    background: var(--color-border-primary);
  }
}

.btn-primary {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  color: white;

  &:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
  }
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

// 覆盖Element UI的dialog样式
::v-deep .el-dialog {
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
}

::v-deep .el-dialog__header {
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-primary);
}

::v-deep .el-dialog__title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

::v-deep .el-dialog__body {
  padding: var(--spacing-lg);
}

::v-deep .el-dialog__footer {
  padding: var(--spacing-lg);
  border-top: 1px solid var(--color-border-primary);
}
</style>
