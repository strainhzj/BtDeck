/**
 * 宽视口检测 mixin（2026-09-12 桌面版出口回归修复）：
 * 显式偏好 mobile 时宽视口仍停留移动版（ui-mode 三原则：偏好优先于视口），
 * 桌面浏览器预览移动版需要出口；手机窄屏不渲染出口（mobile-ux-fixes 决策）。
 *
 * - 提供 isWideViewport 响应式状态（≥ MOBILE_VIEWPORT_BREAKPOINT），
 *   挂载时读初值 + 媒体查询监听跟随窗口宽度变化（增删窗口即时显隐）；
 * - matchMedia 不可用（旧环境/jsdom）安全兜底为 false（不渲染出口）；
 * - class 组件直接 extends WideViewport（生命周期 hook 合并执行，
 *   先 mixin 后页面，同 PullToRefresh 惯例）。
 */
import { Component, Vue } from 'vue-property-decorator'
import { MOBILE_VIEWPORT_BREAKPOINT } from '@/utils/ui-mode'

@Component
export class WideViewport extends Vue {
  public isWideViewport = false
  private wideViewportQuery: MediaQueryList | null = null
  // 标准 API 回调收 MediaQueryListEvent；旧 addListener 同签名（均有 matches）
  private wideViewportHandler: ((ev: MediaQueryListEvent) => void) | null = null

  mounted(): void {
    if (typeof window.matchMedia !== 'function') return
    const mql = window.matchMedia(`(min-width: ${MOBILE_VIEWPORT_BREAKPOINT}px)`)
    this.isWideViewport = mql.matches
    this.wideViewportHandler = (ev: MediaQueryListEvent) => {
      this.isWideViewport = ev.matches
    }
    this.wideViewportQuery = mql
    const legacy = mql as MediaQueryList & {
      addListener?: (listener: (ev: MediaQueryListEvent) => void) => void
      removeListener?: (listener: (ev: MediaQueryListEvent) => void) => void
    }
    if (typeof mql.addEventListener === 'function') {
      mql.addEventListener('change', this.wideViewportHandler)
    } else if (typeof legacy.addListener === 'function') {
      // 旧 WebView（Safari < 14）兜底
      legacy.addListener(this.wideViewportHandler)
    }
  }

  beforeDestroy(): void {
    const mql = this.wideViewportQuery
    const handler = this.wideViewportHandler
    if (!mql || !handler) return
    const legacy = mql as MediaQueryList & {
      removeListener?: (listener: (ev: MediaQueryListEvent) => void) => void
    }
    if (typeof mql.removeEventListener === 'function') {
      mql.removeEventListener('change', handler)
    } else if (typeof legacy.removeListener === 'function') {
      legacy.removeListener(handler)
    }
    this.wideViewportQuery = null
    this.wideViewportHandler = null
  }
}
