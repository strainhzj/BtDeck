<template>
  <!-- 自定义弹窗壳：overlay/头部/关闭/ESC/滚动锁/移动端顶铆 -->
  <div
    class="modal-overlay"
    :class="{active: visible}"
    @click.self="handleOverlayClick"
  >
    <div
      class="modal-dialog"
      :style="{maxWidth}"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
    >
      <div class="modal-header">
        <div class="modal-header__title">
          <LucideIcon v-if="icon" :name="icon" :size="20" class="modal-header__icon" />
          <h3 class="modal-title">{{ title }}</h3>
        </div>
        <button
          class="modal-close"
          type="button"
          :aria-label="$t('common.close')"
          @click="requestClose"
        >
          <LucideIcon name="x" :size="18" />
        </button>
      </div>
      <div class="modal-body">
        <slot />
      </div>
      <div v-if="hasFooter" class="modal-footer">
        <div class="modal-footer-left"><slot name="footer-left" /></div>
        <div class="modal-footer-right"><slot name="footer-right" /></div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'

/**
 * BaseDialog —— 全自定义弹窗壳（零 Element UI）
 *
 * 2026-10 添加种子弹窗全自定义组件化时从 TorrentAddDialog 的 modal-* 样式族抽取：
 * 承担 overlay 蒙层/渐变头/关闭钮/ESC 关闭/body 滚动锁/进出场动画/≤768 顶部锚定，
 * 业务内容经默认插槽与 footer-left/footer-right 插槽注入。其余弹窗可渐进迁移。
 */

// body 滚动锁计数：多个弹窗叠开时仅最后一个关闭时恢复
let bodyLockCount = 0
let bodyOriginalOverflow = ''

@Component({ name: 'BaseDialog' })
export default class BaseDialog extends Vue {
  @Prop(Boolean) visible!: boolean
  /** 标题（同时作为 dialog 的 aria-label） */
  @Prop({ type: String, default: '' }) title!: string
  /** 头部 Lucide 图标名，空串不渲染 */
  @Prop({ type: String, default: '' }) icon!: string
  /** 弹窗最大宽度（内联注入，移动端媒体查询以 !important 压制） */
  @Prop({ type: String, default: '600px' }) maxWidth!: string
  /** 点击蒙层是否关闭 */
  @Prop({ type: Boolean, default: true }) closeOnOverlay!: boolean
  /** 按 ESC 是否关闭 */
  @Prop({ type: Boolean, default: true }) closeOnEsc!: boolean

  private onKeydown: ((event: KeyboardEvent) => void) | null = null

  get hasFooter(): boolean {
    return Boolean(this.$slots['footer-left'] || this.$slots['footer-right'])
  }

  @Watch('visible')
  onVisibleChange(val: boolean): void {
    if (val) {
      this.lockBodyScroll()
      this.bindKeydown()
    } else {
      this.unbindKeydown()
      this.unlockBodyScroll()
    }
  }

  private mounted(): void {
    if (this.visible) {
      this.lockBodyScroll()
      this.bindKeydown()
    }
  }

  private beforeDestroy(): void {
    this.unbindKeydown()
    this.unlockBodyScroll()
  }

  private lockBodyScroll(): void {
    if (bodyLockCount === 0) {
      bodyOriginalOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
    }
    bodyLockCount += 1
  }

  private unlockBodyScroll(): void {
    if (bodyLockCount > 0) bodyLockCount -= 1
    if (bodyLockCount === 0 && document.body.style.overflow === 'hidden') {
      document.body.style.overflow = bodyOriginalOverflow
    }
  }

  private bindKeydown(): void {
    if (this.onKeydown || !this.closeOnEsc) return
    this.onKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') this.requestClose()
    }
    document.addEventListener('keydown', this.onKeydown)
  }

  private unbindKeydown(): void {
    if (!this.onKeydown) return
    document.removeEventListener('keydown', this.onKeydown)
    this.onKeydown = null
  }

  private handleOverlayClick(): void {
    if (this.closeOnOverlay) this.requestClose()
  }

  /** 请求关闭：双事件（update:visible 供 .sync，close 供需要重置表单的宿主） */
  private requestClose(): void {
    if (!this.visible) return
    this.$emit('update:visible', false)
    this.$emit('close')
  }
}
</script>

<style lang="scss" scoped>
.modal-overlay {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 2000;
  align-items: center;
  justify-content: center;

  &.active {
    display: flex;
  }
}

.modal-dialog {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  width: 90%;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: var(--shadow-xl);
  animation: modalSlideIn 0.3s ease;
}

@keyframes modalSlideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.modal-header {
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
  color: white;
  padding: 16px 20px;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.modal-header__title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.modal-header__icon {
  flex-shrink: 0;
}

.modal-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-close {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: white;
  transition: all var(--transition-fast);

  &:hover {
    background: rgba(255, 255, 255, 0.3);
  }
}

.modal-body {
  padding: 16px;
}

.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--color-border-primary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-footer-left,
.modal-footer-right {
  display: flex;
  gap: 10px;
  align-items: center;
}

// ========================================
// 滚动条样式
// ========================================
.modal-dialog::-webkit-scrollbar {
  width: 8px;
}

.modal-dialog::-webkit-scrollbar-track {
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
}

.modal-dialog::-webkit-scrollbar-thumb {
  background: var(--color-border-primary);
  border-radius: var(--radius-sm);
}

.modal-dialog::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-quaternary);
}

// ========================================
// 移动端适配（≤768）：本壳是自定义 modal 非 el-dialog，宽度/布局须自行覆盖
// ========================================
@media (max-width: 768px) {
  // 顶部锚定 + overlay 自身可滚：长表单不再受 85vh 挤压
  .modal-overlay.active {
    align-items: flex-start;
    padding: 12px;
    overflow-y: auto;
  }

  // 根元素带内联 max-width（prop 注入），须 !important 压制；全宽贴边留 12px 边距
  .modal-dialog {
    width: 100%;
    max-width: calc(100vw - 24px) !important;
    max-height: none;
  }

  .modal-header {
    padding: 14px 16px;
    // 吸顶圆角随内容滚动裁切，收敛为上下同圆角避免视觉断层
    border-radius: var(--radius-lg);
  }

  .modal-title {
    font-size: 16px;
  }

  .modal-close {
    width: 36px;
    height: 36px;
  }

  .modal-body {
    padding: 12px 14px;
  }

  // 底部布局收窄；按钮本体（44px 触控高）由宿主插槽内容样式负责
  .modal-footer {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    padding: 12px 14px;
  }

  .modal-footer-left {
    display: none;
  }

  .modal-footer-right {
    width: 100%;
  }
}
</style>
