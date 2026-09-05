/**
 * 移动端下拉刷新 mixin（dual-mode-client Phase 4 M1）：
 * Element UI 无移动组件，手写轻量 touch 下拉——仅当滚动容器（布局壳
 * .mobile-content）已到顶且手指下拉时进入拉动状态，阻尼 0.5 跟手，
 * 松手超过阈值触发 onPullRefresh()（由接入页面覆写）。
 *
 * - 桌面/无触摸环境天然不触发（Chrome 设备模拟可实测 touch 事件）；
 * - 页面模板顶部放置 <m-pull-indicator> 展示状态（mixin 提供数据）；
 * - class 组件直接 extends PullToRefresh（vue-class-component 继承链，
 *   生命周期 hook 合并执行，先 mixin 后页面）。
 */
import { Component, Vue } from 'vue-property-decorator'

export const PULL_REFRESH_THRESHOLD = 60
const PULL_REFRESH_DAMPING = 0.5
const PULL_REFRESH_MAX_DISTANCE = 100
const INDICATOR_REFRESHING_HEIGHT = 36
/** 横向主导判定阈值：超过后中止本次下拉（与布局壳 Tab 滑动手势互斥） */
const PULL_REFRESH_AXIS_LOCK = 12

@Component
export class PullToRefresh extends Vue {
  public pullDistance = 0
  public pullRefreshing = false
  private pullStartX: number | null = null
  private pullStartY: number | null = null
  /** 本手势内是否发生过"未到顶的原生滚动"（回顶瞬间重置起点，防指示条跳变） */
  private pullScrolledInGesture = false

  public get pullReady(): boolean {
    return this.pullDistance >= PULL_REFRESH_THRESHOLD
  }

  /** 接入页面覆写：下拉触发的刷新动作（await 期间显示刷新中） */
  protected async onPullRefresh(): Promise<void> {
    // 默认空实现，由页面覆写
  }

  /**
   * 滚动容器：布局壳 .mobile-content（仅当其自身确实可滚时采用）。
   * 实际布局（.mobile-layout 为 min-height:100vh）下长列表会把布局整体撑高，
   * 真正滚动的是 window，.mobile-content 自身 scrollTop 恒为 0——若只判断
   * “存在该元素”，任意滚动位置都会被误判为已到顶，列表中部下滑即触发整页
   * 刷新（2026-09-05 移动验收报障）。故必须验证 scrollHeight>clientHeight。
   */
  private findScrollContainer(): HTMLElement | null {
    const el = this.$el as HTMLElement
    if (el && typeof el.closest === 'function') {
      const found = el.closest('.mobile-content')
      if (found) {
        const container = found as HTMLElement
        // clientHeight 取整存在亚像素误差，>1 容差判定“确实可滚”
        if (container.scrollHeight - container.clientHeight > 1) return container
      }
    }
    return null
  }

  private isScrolledToTop(): boolean {
    const container = this.findScrollContainer()
    if (container) return container.scrollTop <= 0
    // 实际滚动发生在 window（与种子页返回顶部浮标同款读法）
    const top = window.scrollY || document.documentElement.scrollTop
    return top <= 0
  }

  private onTouchStart(e: TouchEvent): void {
    if (this.pullRefreshing) return
    const touch = e.touches[0]
    this.pullStartY = touch ? touch.clientY : null
    this.pullStartX = touch ? touch.clientX : null
    this.pullScrolledInGesture = false
  }

  private onTouchMove(e: TouchEvent): void {
    if (this.pullStartY === null || this.pullRefreshing) return
    const touch = e.touches[0]
    if (!touch) return
    // 横向主导手势（布局壳 Tab 滑动切换）：中止下拉，指示条归零
    if (
      this.pullStartX !== null &&
      Math.abs(touch.clientX - this.pullStartX) > Math.abs(touch.clientY - this.pullStartY) &&
      Math.abs(touch.clientX - this.pullStartX) > PULL_REFRESH_AXIS_LOCK
    ) {
      this.pullDistance = 0
      this.pullStartY = null
      return
    }
    const delta = touch.clientY - this.pullStartY
    if (delta <= 0) {
      this.pullDistance = 0
      // 上滑（原生滚动/回弹方向）：标记本手势发生过滚动，回顶后再下拉需重置起点
      this.pullScrolledInGesture = true
      return
    }
    // 未到顶时交给原生滚动，不拦截
    if (!this.isScrolledToTop()) {
      this.pullScrolledInGesture = true
      return
    }
    // 同一手势内从滚动回到顶部：重置起点为当前手指位置，防止指示条从 0 跳到半程
    if (this.pullScrolledInGesture) {
      this.pullScrolledInGesture = false
      this.pullStartY = touch.clientY
      this.pullStartX = touch.clientX
      this.pullDistance = 0
      if (e.cancelable) e.preventDefault()
      return
    }
    // 到顶下拉：阻止原生滚动/回弹，跟手移动指示条（带阻尼、封顶）
    if (e.cancelable) e.preventDefault()
    this.pullDistance = Math.min(delta * PULL_REFRESH_DAMPING, PULL_REFRESH_MAX_DISTANCE)
  }

  private onTouchEnd(): void {
    if (this.pullRefreshing) return
    const distance = this.pullDistance
    this.pullDistance = 0
    this.pullStartY = null
    this.pullStartX = null
    if (distance >= PULL_REFRESH_THRESHOLD) {
      void this.triggerPullRefresh()
    }
  }

  private async triggerPullRefresh(): Promise<void> {
    if (this.pullRefreshing) return
    this.pullRefreshing = true
    try {
      await this.onPullRefresh()
    } finally {
      this.pullRefreshing = false
      this.pullDistance = 0
    }
  }

  mounted(): void {
    const el = this.$el as HTMLElement
    el.addEventListener('touchstart', this.onTouchStart as EventListener, { passive: true })
    el.addEventListener('touchmove', this.onTouchMove as EventListener, { passive: false })
    el.addEventListener('touchend', this.onTouchEnd as EventListener, { passive: true })
  }

  beforeDestroy(): void {
    const el = this.$el as HTMLElement
    el.removeEventListener('touchstart', this.onTouchStart as EventListener)
    el.removeEventListener('touchmove', this.onTouchMove as EventListener)
    el.removeEventListener('touchend', this.onTouchEnd as EventListener)
  }
}

export const PULL_INDICATOR_REFRESHING_HEIGHT = INDICATOR_REFRESHING_HEIGHT
