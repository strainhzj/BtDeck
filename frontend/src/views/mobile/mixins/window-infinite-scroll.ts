/**
 * 移动端 window 驱动无限滚动 mixin（2026-09-05 无限加载失控根修）：
 * Element v-infinite-scroll 会把布局壳 .mobile-content 选为滚动容器（它
 * overflow-y:auto），但在 .mobile-layout min-height:100vh 的实际布局下长内容
 * 把布局整体撑高、.mobile-content 从不内部滚动（高度恒等于内容）——指令的
 * "列表底部距容器底部"几何恒真，且 immediate 的 MutationObserver 把每次 DOM
 * 变化（含轮询速度更新、追加卡片本身）都变成一次 loadMore，页面打开即自动
 * 连发请求直到拉满 total（真实库实测：空闲 65 秒 74 次 getList，工具栏刷新
 * 按钮持续转圈）。实际滚动容器是 window（与返回顶部浮标同源事实）。
 *
 * - 滚动到距视口底部 WINDOW_LOAD_MORE_DISTANCE_PX 内触发一次子类 loadMore；
 * - 子类每页加载完成后调用 maybeLoadMore()：内容仍不足一屏时主动补页
 *   （window 无滚动事件可依赖的场景）；
 * - 节流由子类 loadMore 自身的 loading/total 门禁承担（infiniteDisabled）。
 *
 * 防回归要点：生命周期钩子与监听器必须用原型方法（vue-class-component 对
 * 箭头函数类字段的 this 指向收集后丢弃的实例，2026-08-28 已踩坑记录）。
 */
import Component from 'vue-class-component'
import { Vue } from 'vue-property-decorator'

/** 距视口底部多少像素内触发加载下一页（沿原 infinite-scroll-distance 语义） */
export const WINDOW_LOAD_MORE_DISTANCE_PX = 60

@Component({ name: 'WindowInfiniteScroll' })
export class WindowInfiniteScroll extends Vue {
  /** 子类覆写：loading 或已拉满时为 true（与原 infinite-scroll-disabled 同语义） */
  protected get infiniteDisabled(): boolean {
    return true
  }

  /** 子类覆写：加载下一页（内部自行置 loading、去重与拼接） */
  protected async loadMore(): Promise<void> {
    // 由页面覆写
  }

  /** 距视口底部阈值内返回 true（scrollHeight ≤ clientHeight 的短内容页恒真，
   * 用于加载后主动补页；几何取 documentElement 与返回顶部浮标同源） */
  protected isNearViewportBottom(): boolean {
    const doc = document.documentElement
    const scrolled = doc.clientHeight + (window.scrollY || doc.scrollTop)
    return scrolled >= doc.scrollHeight - WINDOW_LOAD_MORE_DISTANCE_PX
  }

  /** 触发时机统一入口：滚动事件与每页加载完成后调用，门禁由子类承担 */
  protected maybeLoadMore(): void {
    if (this.infiniteDisabled) return
    if (this.isNearViewportBottom()) void this.loadMore()
  }

  private onWindowScroll(): void {
    this.maybeLoadMore()
  }

  mounted(): void {
    window.addEventListener('scroll', this.onWindowScroll, { passive: true })
  }

  beforeDestroy(): void {
    window.removeEventListener('scroll', this.onWindowScroll)
  }
}
