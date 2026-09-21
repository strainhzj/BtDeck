/**
 * 种子错误原因 Tooltip 滚动收起 Mixin
 *
 * Element UI Tooltip 的浮层挂到 body；滚动表格或页面时，鼠标仍可能停在
 * 原坐标，引用元素不会收到 mouseleave，导致浮层悬空残留。两种桌面种子视图
 * 共用本 mixin，在滚轮手势开始或任意滚动发生时主动关闭当前页 Tooltip。
 */
import Component from 'vue-class-component'
import { Vue } from 'vue-property-decorator'

type TooltipComponent = Vue & {
  hide?: () => void
}

@Component({ name: 'TorrentErrorTooltipDismissMixin' })
export default class TorrentErrorTooltipDismissMixin extends Vue {
  private tooltipDismissListener: EventListener | null = null

  mounted(): void {
    this.tooltipDismissListener = this.dismissTorrentErrorTooltips.bind(this)
    window.addEventListener('scroll', this.tooltipDismissListener, true)
    window.addEventListener('wheel', this.tooltipDismissListener, {
      capture: true,
      passive: true
    })
  }

  beforeDestroy(): void {
    if (!this.tooltipDismissListener) return
    window.removeEventListener('scroll', this.tooltipDismissListener, true)
    window.removeEventListener('wheel', this.tooltipDismissListener, true)
    this.tooltipDismissListener = null
  }

  private dismissTorrentErrorTooltips(): void {
    const tooltipRefs = this.$refs.torrentErrorTooltips
    const tooltips = Array.isArray(tooltipRefs)
      ? tooltipRefs
      : tooltipRefs
        ? [tooltipRefs]
        : []

    tooltips.forEach(ref => {
      const tooltip = ref as TooltipComponent
      if (typeof tooltip.hide === 'function') {
        tooltip.hide()
      }
    })
  }
}
