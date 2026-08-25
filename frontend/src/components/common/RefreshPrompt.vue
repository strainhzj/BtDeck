<template>
  <transition name="btdeck-refresh-fade">
    <div v-if="visible" class="btdeck-refresh-prompt" role="status">
      <span class="btdeck-refresh-text">发现新版本</span>
      <button type="button" class="btdeck-refresh-apply" @click="applyUpdate">
        立即刷新
      </button>
      <button type="button" class="btdeck-refresh-dismiss" aria-label="暂不刷新" @click="dismiss">
        ✕
      </button>
    </div>
  </transition>
</template>

<script lang="ts">
import { Component, Vue } from 'vue-property-decorator'
import { SW_UPDATED_EVENT, SwUpdatedDetail } from '@/registerServiceWorker'

/**
 * SW 新版本提示（v1.0.6 PWA 完整启用）：registerServiceWorker 的 updated()
 * 回调派发 SW_UPDATED_EVENT，本组件常驻 App.vue 顶层（桌面/移动布局通用），
 * 弹条提示「发现新版本」，用户点「立即刷新」后向 waiting worker 发
 * SKIP_WAITING，controllerchange 到达时重载一次（去抖，防连刷）。
 *
 * skipWaiting=false（vue.config pwa.workboxOptions）：更新不抢激活，
 * 由用户显式确认后再切换，避免旧页面被新 worker 接管导致半新半旧。
 */
@Component({ name: 'RefreshPrompt' })
export default class RefreshPrompt extends Vue {
  private visible = false
  private reloading = false
  private registration: ServiceWorkerRegistration | null = null

  private handleControllerChange = (): void => {
    if (this.reloading) return
    this.reloading = true
    this.doReload()
  }

  mounted(): void {
    window.addEventListener(SW_UPDATED_EVENT, this.handleSwUpdated as EventListener)
  }

  beforeDestroy(): void {
    window.removeEventListener(SW_UPDATED_EVENT, this.handleSwUpdated as EventListener)
    this.serviceWorkerContainer()?.removeEventListener(
      'controllerchange',
      this.handleControllerChange
    )
  }

  private serviceWorkerContainer(): ServiceWorkerContainer | null {
    if (typeof navigator === 'undefined') return null
    return navigator.serviceWorker ? navigator.serviceWorker : null
  }

  private handleSwUpdated(event: Event): void {
    const detail = (event as CustomEvent<SwUpdatedDetail>).detail
    if (!detail || !detail.registration) return
    this.registration = detail.registration
    this.visible = true
  }

  private dismiss(): void {
    this.visible = false
  }

  private applyUpdate(): void {
    const container = this.serviceWorkerContainer()
    const waiting = this.registration ? this.registration.waiting : null
    if (!container || !waiting) {
      // waiting 已消失（他页已触发激活）或环境异常：直接重载取最新应用壳
      this.doReload()
      return
    }
    container.addEventListener('controllerchange', this.handleControllerChange)
    waiting.postMessage({ type: 'SKIP_WAITING' })
  }

  /** 独立方法便于测试覆写（jsdom 无导航实现） */
  private doReload(): void {
    window.location.reload()
  }
}
</script>

<style scoped>
.btdeck-refresh-prompt {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 3000;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px 8px 16px;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  border: 1px solid #e4e7ed;
  border-left: 3px solid var(--color-primary, #059669);
  font-size: 13px;
  color: #303133;
}

.btdeck-refresh-apply {
  border: none;
  border-radius: 6px;
  padding: 5px 12px;
  background: var(--color-primary, #059669);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.btdeck-refresh-dismiss {
  border: none;
  background: transparent;
  color: #909399;
  font-size: 13px;
  cursor: pointer;
  padding: 4px 6px;
}

.btdeck-refresh-fade-enter-active,
.btdeck-refresh-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.btdeck-refresh-fade-enter,
.btdeck-refresh-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-8px);
}
</style>
