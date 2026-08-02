<template>
  <el-dialog
    :visible.sync="visible"
    :before-close="handleClose"
    :close-on-click-modal="false"
    :show-close="false"
    width="min(1040px, 92vw)"
    custom-class="template-selection-dialog"
  >
    <template #title>
      <div class="template-dialog-header">
        <span class="template-dialog-header__mark"><LucideIcon name="layout-template" :size="19" /></span>
        <div>
          <span class="template-dialog-header__eyebrow">CONFIGURATION LIBRARY</span>
          <h3>从模板选择配置</h3>
        </div>
        <button type="button" aria-label="关闭模板库" @click="handleClose">
          <LucideIcon name="x" :size="16" />
        </button>
      </div>
    </template>
    <div class="dialog-body">
      <div v-if="loading" class="template-loading">
        <LucideIcon class="is-spinning" name="refresh-cw" :size="20" />
        <span>正在同步模板索引</span>
      </div>
      <!-- 模板卡片网格 -->
      <div v-else-if="templateList.length > 0" class="template-grid">
        <div
          v-for="template in templateList"
          :key="template.id"
          :class="['template-card', {selected: selectedTemplate?.id === template.id}]"
          @click="selectTemplate(template)"
        >
          <!-- 系统默认徽章 -->
          <div v-if="template.is_system_default" class="system-badge">
            系统默认
          </div>

          <!-- 单选按钮 -->
          <div class="card-radio"></div>

          <!-- 卡片头部 -->
          <div class="card-header">
            <div class="card-icon">
              <LucideIcon name="zap" :size="20" />
            </div>
            <div class="card-title-section">
              <div class="card-title">{{ template.name }}</div>
              <div class="card-type">
                <LucideIcon name="clock" :size="11" />
                {{ getDownloaderTypeLabel(template.downloader_type) }}
              </div>
            </div>
          </div>

          <!-- 卡片描述 -->
          <div class="card-description" :title="template.description">
            {{ template.description }}
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else class="template-empty">
        <LucideIcon name="inbox" :size="38" :stroke-width="1.4" />
        <span>暂无可用模板</span>
      </div>
    </div>

    <div slot="footer" class="dialog-footer">
      <div class="footer-info">
        已选择: <strong>{{ selectedTemplate?.name || '未选择' }}</strong>
      </div>
      <div class="footer-actions">
        <el-button @click="handleClose">
          <LucideIcon class="button-icon" name="x" :size="14" />
          取消
        </el-button>
        <el-button type="warning" :disabled="!selectedTemplate" @click="handleApplyDirect">
          <LucideIcon class="button-icon" name="download" :size="14" />
          直接应用
        </el-button>
        <el-button type="primary" :disabled="!selectedTemplate" @click="handleApplyWithPreview">
          <LucideIcon class="button-icon" name="check" :size="14" />
          确定
        </el-button>
      </div>
    </div>

    <!-- 确认对话框 -->
    <el-dialog
      :visible.sync="confirmDialogVisible"
      width="400px"
      :show-close="false"
      append-to-body
    >
      <template #title>
        <div class="template-confirm-header">
          <span>确认直接应用模板</span>
          <button type="button" aria-label="关闭确认框" @click="confirmDialogVisible = false">
            <LucideIcon name="x" :size="15" />
          </button>
        </div>
      </template>
      <div class="confirm-content">
        <div class="confirm-icon">
          <LucideIcon name="alert-triangle" :size="30" :stroke-width="1.5" />
        </div>
        <div class="confirm-message">
          即将应用模板 <strong>{{ selectedTemplate?.name }}</strong
          ><br />
          直接应用将覆盖当前下载器配置，是否继续？
        </div>
      </div>
      <div slot="footer" class="confirm-actions">
        <el-button @click="confirmDialogVisible = false" style="flex: 1">取消</el-button>
        <el-button type="warning" @click="confirmApply" style="flex: 1">确认应用</el-button>
      </div>
    </el-dialog>
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { SettingTemplate } from '../types'
import { getTemplateList, applyTemplate } from '@/api/downloader'

interface ApiErrorLike {
  response?: { data?: { msg?: string } }
  message?: string
}

@Component({
  name: 'TemplateSelectionDialog'
})
export default class TemplateSelectionDialog extends Vue {
  @Prop({ default: false }) visible!: boolean
  @Prop({ required: true }) downloaderType!: 0 | 1
  @Prop({ required: true }) downloaderId!: string

  // 加载状态
  private loading = false

  // 模板列表
  private templateList: SettingTemplate[] = []

  // 选中的模板
  private selectedTemplate: SettingTemplate | null = null

  // 确认对话框显示状态
  private confirmDialogVisible = false

  // 监听对话框显示状态
  @Watch('visible')
  onVisibleChange(val: boolean) {
    if (val) {
      this.loadTemplates()
    } else {
      this.selectedTemplate = null
    }
  }

  // 加载模板列表
  private async loadTemplates() {
    this.loading = true
    try {
      const response = await getTemplateList({
        page: 1,
        pageSize: 100
      })

      if (response.code === '200') {
        // 过滤出适用于当前下载器类型的模板
        this.templateList = response.data.list.filter((template: SettingTemplate) => {
          return (
            template.downloader_type === this.downloaderType ||
            template.downloader_type === 2
          )
        })
      }
    } catch (error) {
      console.error('加载模板列表失败:', error)
      this.$message.error('加载模板列表失败')
    } finally {
      this.loading = false
    }
  }

  // 选择模板
  private selectTemplate(template: SettingTemplate) {
    this.selectedTemplate = template
  }

  // 直接应用
  private handleApplyDirect() {
    if (!this.selectedTemplate) return
    this.confirmDialogVisible = true
  }

  // 确认应用
  private async confirmApply() {
    if (!this.selectedTemplate) return

    try {
      // ✅ 使用prop传递的downloaderId，避免深层parent访问
      const downloaderId = this.downloaderId
      if (!downloaderId || typeof downloaderId !== 'string' || downloaderId.trim() === '') {
        this.$message.error('下载器ID无效，已取消模板应用')
        this.confirmDialogVisible = false
        return
      }

      const response = await applyTemplate(
        this.selectedTemplate.id,
        downloaderId.trim()
      )

      if (response.code === '200') {
        this.$message.success('模板应用成功')
        this.$emit('template-selected', this.selectedTemplate)
        this.confirmDialogVisible = false
        this.handleClose()
      }
    } catch (error: unknown) {
      console.error('应用模板失败:', error)
      const apiError = error as ApiErrorLike
      const errorMsg = apiError.response?.data?.msg || apiError.message || '应用模板失败'
      this.$message.error(errorMsg)
    }
  }

  // 预览后应用
  private handleApplyWithPreview() {
    if (!this.selectedTemplate) return
    // 触发模板选择事件，由父组件处理预览逻辑
    this.$emit('template-selected', this.selectedTemplate)
    this.handleClose()
  }

  // 关闭对话框
  private handleClose() {
    this.$emit('update:visible', false)
    this.selectedTemplate = null
  }

  // 获取下载器类型标签
  private getDownloaderTypeLabel(type: number): string {
    if (type === 0) return 'qBittorrent'
    if (type === 1) return 'Transmission'
    return '通用'
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

::v-deep .template-selection-dialog {
  .el-dialog__header {
    padding: var(--spacing-lg) var(--spacing-xl);
    border-bottom: 1px solid var(--color-border-primary);
  }

  .el-dialog__title {
    font-size: 20px;
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-primary);
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
  }

  .el-dialog__body {
    padding: 0;
  }

  .el-dialog__footer {
    padding: var(--spacing-lg) var(--spacing-xl);
    border-top: 1px solid var(--color-border-primary);
  }
}

.dialog-body {
  padding: var(--spacing-xl);
  max-height: 60vh;
  overflow-y: auto;
}

// 模板卡片网格
.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacing-lg);
}

// 模板卡片
.template-card {
  background: var(--color-bg-primary);
  border: 2px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  cursor: pointer;
  transition: all var(--transition-base);
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);

  &:hover {
    border-color: var(--color-primary);
    box-shadow: var(--spacing-sm) var(--spacing-sm) 0 rgba(5, 150, 105, 0.1);
    transform: translateY(-2px);
  }

  &.selected {
    border-color: var(--color-primary);
    background: var(--color-primary-lightest);
  }
}

// 系统默认徽章
.system-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
  color: white;
  font-size: 11px;
  font-weight: var(--font-weight-semibold);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  box-shadow: 0 2px 4px rgba(5, 150, 105, 0.2);
}

// 单选按钮
.card-radio {
  position: absolute;
  top: var(--spacing-md);
  right: var(--spacing-md);
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-border-primary);
  border-radius: 50%;
  transition: all var(--transition-base);

  &::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) scale(0);
    width: 10px;
    height: 10px;
    background: var(--color-primary);
    border-radius: 50%;
    transition: all var(--transition-base);
  }
}

.template-card.selected .card-radio {
  border-color: var(--color-primary);

  &::after {
    transform: translate(-50%, -50%) scale(1);
  }
}

// 卡片头部
.card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
  padding-top: var(--spacing-sm);
}

.card-icon {
  width: 48px;
  height: 48px;
  background: var(--color-primary-lightest);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  svg {
    width: 24px;
    height: 24px;
    color: var(--color-primary);
  }
}

.card-title-section {
  flex: 1;
}

.card-title {
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.card-type {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  background: var(--color-bg-secondary);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}

// 卡片描述
.card-description {
  font-size: 14px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;

  &:hover {
    -webkit-line-clamp: unset;
    max-height: none;
    background: var(--color-bg-secondary);
    padding: var(--spacing-sm);
    border-radius: var(--radius-md);
    margin: calc(var(--spacing-sm) * -1);
  }
}

// 对话框底部
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-bg-secondary);
}

.footer-info {
  font-size: 14px;
  color: var(--color-text-secondary);
}

.footer-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.button-icon {
  display: inline;
  vertical-align: middle;
  margin-right: 6px;
  width: 16px;
  height: 16px;
}

// 确认对话框内容
.confirm-content {
  text-align: center;
  padding: var(--spacing-lg) 0;
}

.confirm-icon {
  width: 64px;
  height: 64px;
  background: var(--color-warning-light);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto var(--spacing-md);

  svg {
    width: 32px;
    height: 32px;
    color: var(--color-warning);
  }
}

.confirm-message {
  font-size: 14px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.confirm-actions {
  display: flex;
  gap: var(--spacing-sm);
}

// 滚动条样式
.dialog-body::-webkit-scrollbar {
  width: 8px;
}

.dialog-body::-webkit-scrollbar-track {
  background: var(--color-bg-secondary);
}

.dialog-body::-webkit-scrollbar-thumb {
  background: var(--color-border-primary);
  border-radius: 4px;
}

.dialog-body::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-tertiary);
}

::v-deep .template-selection-dialog {
  overflow: hidden;
  border: 1px solid rgba(var(--color-primary-rgb), 0.18);
  border-radius: 15px;
  box-shadow: 0 28px 80px rgba(15, 23, 42, 0.2);

  .el-dialog__header {
    padding: 0;
  }

  .el-dialog__footer {
    padding: 10px 13px;
  }
}

.template-dialog-header {
  display: flex;
  min-height: 64px;
  align-items: center;
  gap: 10px;
  padding: 10px 13px;
  background:
    radial-gradient(circle at 78% 20%, rgba(var(--color-primary-rgb), 0.13), transparent 30%),
    var(--color-bg-primary);

  &__mark {
    display: inline-flex;
    width: 38px;
    height: 38px;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(var(--color-primary-rgb), 0.22);
    border-radius: 10px;
    color: var(--color-primary);
    background: rgba(var(--color-primary-rgb), 0.07);
  }

  &__eyebrow {
    color: var(--color-primary);
    font-family: var(--font-mono);
    font-size: 7px;
    letter-spacing: 0.18em;
  }

  h3 {
    margin: 2px 0 0;
    color: var(--color-text-primary);
    font-size: 16px;
    letter-spacing: -0.02em;
  }

  button,
  .template-confirm-header button {
    display: inline-flex;
    width: 30px;
    height: 30px;
    align-items: center;
    justify-content: center;
    margin-left: auto;
    border: 1px solid var(--color-border-secondary);
    border-radius: 8px;
    color: var(--color-text-secondary);
    background: rgba(255, 255, 255, 0.62);
    cursor: pointer;
  }
}

.dialog-body {
  min-height: 220px;
  max-height: 56vh;
  padding: 12px;
  background:
    linear-gradient(rgba(15, 23, 42, 0.026) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.026) 1px, transparent 1px),
    var(--color-bg-secondary);
  background-size: 24px 24px;
}

.template-grid {
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
}

.template-card {
  gap: 8px;
  min-height: 128px;
  padding: 12px;
  border-width: 1px;
  border-radius: 11px;

  &:hover {
    box-shadow: 7px 7px 0 rgba(var(--color-primary-rgb), 0.08);
    transform: translateY(-1px);
  }
}

.system-badge {
  top: 8px;
  left: 8px;
  padding: 3px 7px;
  font-size: 8px;
}

.card-radio {
  top: 10px;
  right: 10px;
  width: 16px;
  height: 16px;

  &::after {
    width: 8px;
    height: 8px;
  }
}

.card-header {
  gap: 9px;
}

.card-icon {
  width: 36px;
  height: 36px;
}

.card-title {
  margin-bottom: 3px;
  font-size: 12px;
}

.card-type {
  padding: 3px 6px;
  font-family: var(--font-mono);
  font-size: 8px;
}

.card-description,
.footer-info {
  font-size: 9px;
}

.dialog-footer,
.footer-actions {
  gap: 6px;
}

.footer-actions ::v-deep .el-button {
  height: 31px;
  margin-left: 0;
  padding: 0 10px;
  font-size: 9px;
}

.footer-actions ::v-deep .el-button span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.button-icon {
  margin-right: 0;
}

.template-loading,
.template-empty {
  display: flex;
  min-height: 196px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 9px;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
}

.template-confirm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;

  button {
    display: inline-flex;
    width: 28px;
    height: 28px;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--color-border-secondary);
    border-radius: 8px;
    color: var(--color-text-secondary);
    background: transparent;
    cursor: pointer;
  }
}

.is-spinning {
  animation: template-spin 0.8s linear infinite;
}

@keyframes template-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 620px) {
  .dialog-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .footer-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .footer-actions .el-button:last-child {
    grid-column: 1 / -1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .template-card {
    transition-duration: 0.01ms;
  }

  .is-spinning {
    animation: none;
  }
}
</style>
