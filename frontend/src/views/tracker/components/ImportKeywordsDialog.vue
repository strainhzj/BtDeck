<template>
  <el-dialog
    :visible.sync="dialogVisible"
    :title="dialogTitle"
    width="700px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div class="dialog-body">
      <div class="import-methods">
        <!-- 文件上传 -->
        <div>
          <div
            class="upload-area"
            :class="{'dragover': isDragOver}"
            @click="handleFileSelect"
            @dragover.prevent="handleDragOver"
            @dragleave="handleDragLeave"
            @drop.prevent="handleDrop"
          >
            <div class="upload-icon">📁</div>
            <div class="upload-text">点击或拖拽TXT文件到此处</div>
            <div class="upload-hint">仅支持.txt文件,每行一个关键词</div>
          </div>
          <input
            ref="fileInput"
            type="file"
            accept=".txt"
            style="display: none"
            @change="handleFileChange"
          >
        </div>

        <!-- 文本输入 -->
        <div>
          <label class="form-label">或手动输入关键词</label>
          <textarea
            v-model="textContent"
            class="form-textarea"
            placeholder="每行一个关键词,按回车分隔"
            @input="parseTextContent"
          ></textarea>
        </div>
      </div>

      <!-- 预览区域 -->
      <div class="preview-area">
        <div class="preview-text">
          将导入 <span class="preview-count">{{ parsedKeywords.length }}</span> 个关键词
        </div>
      </div>

      <!-- 进度条 -->
      <div v-if="importing" class="progress-bar-wrapper">
        <div class="progress-bar">
          <div class="progress-fill" :style="{width: progress + '%'}"></div>
        </div>
        <div class="progress-text">{{ progressText }}</div>
      </div>

      <!-- 成功消息 -->
      <div v-if="importSuccess" class="success-message">
        <span class="success-icon">✅</span>
        <span>成功导入 {{ successCount }} 个关键词,失败 {{ failCount }} 个</span>
      </div>
    </div>

    <div slot="footer" class="dialog-footer">
      <button class="btn btn-secondary" @click="handleClose" :disabled="importing">
        {{ importing ? '导入中...' : '取消' }}
      </button>
      <button v-if="!importing" class="btn btn-primary" :disabled="parsedKeywords.length === 0" @click="handleImport">
        开始导入
      </button>
      <button v-else class="btn btn-danger" @click="handleCancelImport">
        <span class="spinner"></span>
        <span>取消导入</span>
      </button>
    </div>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { createKeyword } from '@/api/tracker'
import { PoolType } from '@/api/tracker'

@Component({
  name: 'ImportKeywordsDialog'
})
export default class ImportKeywordsDialog extends Vue {
  @Prop({ type: Boolean, default: false }) visible!: boolean
  @Prop({ type: String, required: true }) poolType!: PoolType
  @Prop({ type: String, required: true }) poolLabel!: string

  dialogVisible = false
  textContent = ''
  parsedKeywords: string[] = []
  isDragOver = false
  importing = false
  importCancelled = false // 导入取消标志
  progress = 0
  progressText = ''
  importSuccess = false
  successCount = 0
  failCount = 0
  private autoCloseTimer: ReturnType<typeof setTimeout> | null = null

  poolTypeMap: Record<PoolType, 'success' | 'failed' | 'ignored'> = {
    success: 'success',
    failed: 'failed',
    ignored: 'ignored',
    candidate: 'ignored'
  }

  get dialogTitle(): string {
    return `导入关键词到 ${this.poolLabel}`
  }

  get keywordType(): 'success' | 'failed' | 'ignored' {
    return this.poolTypeMap[this.poolType] || 'ignored'
  }

  @Watch('visible')
  onVisibleChange(val: boolean) {
    this.dialogVisible = val
    if (val) {
      this.resetForm()
    }
  }

  @Watch('dialogVisible')
  onDialogVisibleChange(val: boolean) {
    this.$emit('update:visible', val)
  }

  resetForm() {
    this.textContent = ''
    this.parsedKeywords = []
    this.isDragOver = false
    this.importing = false
    this.importCancelled = false // 重置取消标志
    this.progress = 0
    this.progressText = ''
    this.importSuccess = false
    this.successCount = 0
    this.failCount = 0
  }

  parseTextContent() {
    const lines = this.textContent.split('\n')
    this.parsedKeywords = lines
      .map(line => line.trim())
      .filter(line => line.length > 0)
      .filter((line, index, self) => self.indexOf(line) === index) // 去重
  }

  handleFileSelect() {
    (this.$refs.fileInput as HTMLInputElement).click()
  }

  handleDragOver() {
    this.isDragOver = true
  }

  handleDragLeave() {
    this.isDragOver = false
  }

  handleDrop(event: DragEvent) {
    this.isDragOver = false
    const files = event.dataTransfer?.files
    if (files && files.length > 0) {
      this.processFile(files[0])
    }
  }

  handleFileChange(event: Event) {
    const input = event.target as HTMLInputElement
    if (input.files && input.files.length > 0) {
      this.processFile(input.files[0])
    }
  }

  processFile(file: File) {
    if (!file.name.endsWith('.txt')) {
      this.$message.error('仅支持.txt文件')
      return
    }

    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      this.textContent = content
      this.parseTextContent()
      this.$message.success(`已读取 ${this.parsedKeywords.length} 个关键词`)
    }
    reader.onerror = () => {
      this.$message.error('文件读取失败')
    }
    reader.readAsText(file)
  }

  async handleImport() {
    if (this.parsedKeywords.length === 0) {
      this.$message.warning('请先输入或上传关键词')
      return
    }

    this.importing = true
    this.importCancelled = false // 重置取消标志
    this.progress = 0
    this.successCount = 0
    this.failCount = 0
    this.importSuccess = false

    const total = this.parsedKeywords.length
    const batchSize = 5 // 每批处理5个

    try {
      for (let i = 0; i < this.parsedKeywords.length; i += batchSize) {
        // 检查是否取消
        if (this.importCancelled) {
          this.progressText = '导入已取消'
          this.$message.warning(`导入已取消,成功 ${this.successCount} 个,失败 ${this.failCount} 个`)
          break
        }

        const batch = this.parsedKeywords.slice(i, i + batchSize)

        // 并发处理当前批次
        const promises = batch.map(keyword => this.addKeyword(keyword))
        const results = await Promise.allSettled(promises)

        results.forEach(result => {
          if (result.status === 'fulfilled') {
            this.successCount++
          } else {
            this.failCount++
          }
        })

        // 更新进度
        this.progress = Math.min(100, Math.round(((i + batch.length) / total) * 100))
        this.progressText = `正在导入 ${this.progress}% (${this.successCount + this.failCount}/${total})`

        // 避免过快请求
        await new Promise(resolve => setTimeout(resolve, 200))
      }

      // 如果正常完成(未被取消)
      if (!this.importCancelled) {
        this.importing = false
        this.importSuccess = true
        this.progressText = '导入完成'

        // 显示成功消息
        if (this.successCount > 0) {
          this.$message.success(`成功导入 ${this.successCount} 个关键词${this.failCount > 0 ? `,失败 ${this.failCount} 个` : ''}`)
          this.$emit('success', this.successCount)

          // 3秒后自动关闭
          this.autoCloseTimer = setTimeout(() => {
            if (this.successCount > 0) {
              this.handleClose()
            }
          }, 3000)
        } else {
          this.$message.error('导入失败,请稍后重试')
        }
      }
    } catch (error) {
      console.error('导入过程出错:', error)
      this.$message.error('导入过程出错,请稍后重试')
    } finally {
      this.importing = false
    }
  }

  // 取消导入
  handleCancelImport() {
    this.importCancelled = true
    this.$message.info('正在取消导入...')
  }

  beforeDestroy() {
    // 清理自动关闭定时器,避免内存泄漏
    if (this.autoCloseTimer) {
      clearTimeout(this.autoCloseTimer)
      this.autoCloseTimer = null
    }
  }

  async addKeyword(keyword: string): Promise<void> {
    try {
      const response = await createKeyword({
        keyword: keyword.trim(),
        keyword_type: this.keywordType,
        enabled: true,
        priority: 1
      })

      if (response.code !== '200') {
        throw new Error(response.msg || '添加失败')
      }
    } catch (error) {
      console.error(`添加关键词 "${keyword}" 失败:`, error)
      throw error
    }
  }

  handleClose() {
    if (this.importing) {
      return
    }
    this.dialogVisible = false
  }
}
</script>

<style lang="scss" scoped>
.dialog-body {
  padding: var(--spacing-md) 0;
}

.import-methods {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.upload-area {
  border: 2px dashed var(--color-border-primary);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;

  &:hover,
  &.dragover {
    border-color: var(--color-primary);
    background: rgba(16, 185, 129, 0.05);
  }
}

.upload-icon {
  font-size: 48px;
  margin-bottom: var(--spacing-sm);
}

.upload-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xs);
}

.upload-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.form-label {
  display: block;
  margin-bottom: var(--spacing-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
}

.form-textarea {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 2px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-family: inherit;
  resize: vertical;
  min-height: 150px;
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

.preview-area {
  background: var(--color-bg-secondary);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-lg);
}

.preview-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.preview-count {
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-lg);
  color: var(--color-primary);
}

.progress-bar-wrapper {
  margin-bottom: var(--spacing-md);
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--color-border-primary);
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-bottom: var(--spacing-sm);
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary) 0%, var(--color-primary-light) 100%);
  transition: width 0.3s;
}

.progress-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  text-align: center;
}

.success-message {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--color-success-dark);
}

.success-icon {
  font-size: 20px;
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

  &:hover:not(:disabled) {
    background: var(--color-border-primary);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
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

.btn-danger {
  background: linear-gradient(135deg, var(--color-error) 0%, var(--color-error-dark) 100%);
  color: white;
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);

  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
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

// 响应式
@media (max-width: 768px) {
  .import-methods {
    grid-template-columns: 1fr;
  }
}
</style>
