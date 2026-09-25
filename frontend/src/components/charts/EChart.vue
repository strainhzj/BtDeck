<template>
  <div
    ref="root"
    class="echart"
    :style="{height: normalizedHeight}"
  >
    <div
      ref="chart"
      class="echart__canvas"
    />
    <div
      v-if="isEmpty"
      class="echart__empty"
      data-testid="echart-empty"
    >
      <slot name="empty">
        <span class="echart__empty-text">{{ emptyText }}</span>
      </slot>
    </div>
  </div>
</template>

<script lang="ts">
/**
 * echarts 按需 + 懒加载封装（statistics-reports W4，PLANS/statistics-reports.md §4.1）。
 *
 * - Options API class 风格（vue-property-decorator，与 query-templates 同款）；
 * - echarts/core + Bar/Line/Pie/Scatter + Grid/Tooltip/Legend/DataZoom/Title +
 *   CanvasRenderer，全部动态 import 且统一 webpackChunkName "echarts"（单 chunk
 *   gz 门禁 <200KB；首次渲染才加载）；
 * - 竞态：import 完成后若 option 已就绪立即 setOption；
 * - watch 浅比较：父组件传新对象引用时才重渲染（setOption notMerge）；
 * - 生命周期：mounted init → ResizeObserver 自适应 → beforeDestroy dispose
 *   + disconnect；
 * - 空态插槽：option 为空/无 series 时显示占位（具名 slot empty 可覆盖）。
 *
 * 类型策略：SFC 内类型不进 CI（fork-ts-checker vue.enabled=false + tsc 不编译
 * .vue）；契约类型全放 types/reports.ts（禁 echarts 类型 import）。
 */
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'

/** echarts 实例最小面（SFC 内仅用到的成员；不 import echarts d.ts 实体类型） */
interface ChartInstanceLike {
  setOption: (option: Record<string, unknown>, opts?: { notMerge?: boolean }) => void
  resize: () => void
  dispose: () => void
  showLoading: () => void
  hideLoading: () => void
}

type ChartInitFn = (el: HTMLElement) => ChartInstanceLike

/** 模块级单例 promise：多图表实例只加载一次 echarts chunk */
let echartsReady: Promise<ChartInitFn> | null = null

function loadECharts(): Promise<ChartInitFn> {
  if (!echartsReady) {
    echartsReady = Promise.all([
      import(/* webpackChunkName: "echarts" */ 'echarts/core'),
      import(/* webpackChunkName: "echarts" */ 'echarts/charts'),
      import(/* webpackChunkName: "echarts" */ 'echarts/components'),
      import(/* webpackChunkName: "echarts" */ 'echarts/renderers')
    ]).then(([core, charts, components, renderers]) => {
      core.use([
        charts.BarChart,
        charts.LineChart,
        charts.PieChart,
        charts.ScatterChart,
        components.GridComponent,
        components.TooltipComponent,
        components.LegendComponent,
        components.DataZoomComponent,
        components.TitleComponent,
        renderers.CanvasRenderer
      ])
      return core.init as ChartInitFn
    })
  }
  return echartsReady
}

/** 浅比较（watch 防抖：同层键值一致不重渲染） */
function shallowEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false
  const ka = Object.keys(a as Record<string, unknown>)
  const kb = Object.keys(b as Record<string, unknown>)
  if (ka.length !== kb.length) return false
  return ka.every((k) => (a as Record<string, unknown>)[k] === (b as Record<string, unknown>)[k])
}

@Component({ name: 'EChart' })
export default class EChart extends Vue {
  @Prop({ type: Object, default: null })
  private readonly option!: Record<string, unknown> | null

  @Prop({ type: [String, Number], default: 320 })
  private readonly height!: string | number

  @Prop({ type: Boolean, default: false })
  private readonly loading!: boolean

  @Prop({ type: String, default: '' })
  private readonly emptyText!: string

  private chart: ChartInstanceLike | null = null
  private observer: ResizeObserver | null = null
  private disposed = false
  private lastApplied: Record<string, unknown> | null = null

  get normalizedHeight(): string {
    return typeof this.height === 'number' ? `${this.height}px` : this.height
  }

  get isEmpty(): boolean {
    if (!this.option) return true
    const series = (this.option as Record<string, unknown>).series
    return !Array.isArray(series) || series.length === 0
  }

  mounted() {
    void loadECharts().then((init) => {
      // 竞态：beforeDestroy 先到则放弃 init
      if (this.disposed) return
      const el = this.$refs.chart as HTMLElement | undefined
      if (!el) return
      this.chart = init(el)
      this.applyOption()
      this.applyLoading()
      this.observeResize()
    })
  }

  beforeDestroy() {
    this.disposed = true
    if (this.observer) {
      this.observer.disconnect()
      this.observer = null
    }
    if (this.chart) {
      this.chart.dispose()
      this.chart = null
    }
  }

  @Watch('option')
  onOptionChanged() {
    this.applyOption()
  }

  @Watch('loading')
  onLoadingChanged() {
    this.applyLoading()
  }

  /** 外部触发的尺寸变化兜底（容器动画/页签切换后调用） */
  public resizeChart(): void {
    if (this.chart) this.chart.resize()
  }

  private applyOption(): void {
    if (!this.chart || !this.option) return
    if (shallowEqual(this.option, this.lastApplied)) return
    this.chart.setOption(this.option, { notMerge: true })
    this.lastApplied = this.option
  }

  private applyLoading(): void {
    if (!this.chart) return
    if (this.loading) {
      this.chart.showLoading()
    } else {
      this.chart.hideLoading()
    }
  }

  private observeResize(): void {
    if (typeof ResizeObserver === 'undefined') return
    const rootEl = this.$refs.root as HTMLElement | undefined
    if (!rootEl) return
    this.observer = new ResizeObserver(() => {
      if (this.chart) this.chart.resize()
    })
    this.observer.observe(rootEl)
  }
}
</script>

<style scoped>
.echart {
  position: relative;
  width: 100%;
}

.echart__canvas {
  width: 100%;
  height: 100%;
}

.echart__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--app-card-bg, #fff);
}

.echart__empty-text {
  color: var(--app-text-secondary, #909399);
  font-size: 13px;
}
</style>
