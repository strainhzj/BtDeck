<template>
  <div class="dash-radar-wrap">
    <canvas
      ref="canvas"
      :data-testid="radarTestId"
    />
  </div>
</template>

<script lang="ts">
/**
 * RadarCard —— 链路雷达 widget（仪表盘一期 W2，W2 清单补入项）。
 *
 * 数据源：GET /dashboard 的 downloader_list（纯前端绘制，无新增请求）。
 * 实现：原生 canvas 扫描雷达（自研重写验收示意图的演示脚本为生产级——
 * devicePixelRatio 缩放、ResizeObserver 自适应、visibility 隐藏停帧、
 * beforeDestroy 清理 rAF；非移植 BitMatrix Canvas 代码，边界约束）。
 * 节点=下载器：在线绿点（有速度外圈/零速中圈），离线红点。
 */
import { Component, Prop, Vue, Watch } from 'vue-property-decorator'
import { DownloaderListItem } from '@/types/dashboard'

interface RadarNode {
  name: string
  ang: number
  r: number
  ok: boolean
}

@Component({ name: 'RadarCard' })
export default class RadarCard extends Vue {
  @Prop({ required: true }) private list!: DownloaderListItem[]
  @Prop({ default: 'radar-canvas' }) private radarTestId!: string
  /** 深色模式（数据大屏 --screen-* 画布；默认浅色应用主题） */
  @Prop({ default: false }) private dark!: boolean

  private angle = 0
  private rafId = 0
  private resizeObserver: ResizeObserver | null = null
  private visible = true

  private mounted() {
    const canvas = this.$refs.canvas as HTMLCanvasElement | undefined
    if (!canvas) return
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => this.fitCanvas())
      this.resizeObserver.observe(canvas.parentElement || canvas)
    }
    // 页面不可见时停帧（预设切换隐藏由 offsetParent 检查兜底）
    document.addEventListener('visibilitychange', this.onVisibility)
    this.fitCanvas()
    this.loop()
  }

  private beforeDestroy() {
    cancelAnimationFrame(this.rafId)
    this.resizeObserver?.disconnect()
    this.resizeObserver = null
    document.removeEventListener('visibilitychange', this.onVisibility)
  }

  private onVisibility() {
    this.visible = !document.hidden
    if (this.visible) this.loop()
  }

  private fitCanvas() {
    const canvas = this.$refs.canvas as HTMLCanvasElement | undefined
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.max(10, Math.round(rect.width * dpr))
    canvas.height = Math.max(10, Math.round(rect.height * dpr))
  }

  private get nodes(): RadarNode[] {
    const count = Math.max(this.list.length, 1)
    return this.list.map((dl, i) => {
      const active = (dl.download_speed || 0) + (dl.upload_speed || 0) > 0
      return {
        name: dl.nickname,
        ang: (i / count) * Math.PI * 2 + 0.6,
        r: dl.status === 'online' ? (active ? 0.8 : 0.5) : 0.9,
        ok: dl.status === 'online'
      }
    })
  }

  @Watch('list')
  private onListChange() {
    // 节点数据变化在下一帧绘制时自然生效
  }

  private loop = () => {
    if (!this.visible) return
    this.draw()
    this.rafId = requestAnimationFrame(this.loop)
  }

  private draw() {
    const canvas = this.$refs.canvas as HTMLCanvasElement | undefined
    if (!canvas || canvas.offsetParent === null) return // 预设隐藏时跳过绘制
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const W = canvas.width
    const H = canvas.height
    const cx = W / 2
    const cy = H / 2
    const R = Math.min(W, H) * 0.44
    const dpr = window.devicePixelRatio || 1
    const styles = getComputedStyle(document.documentElement)
    const primary = this.dark ? styles.getPropertyValue('--screen-accent').trim() || '#34D399' : styles.getPropertyValue('--color-primary').trim() || '#059669'
    const error = this.dark ? '#F87171' : styles.getPropertyValue('--color-error').trim() || '#EF4444'
    const gridLine = this.dark ? 'rgba(255,255,255,.10)' : 'rgba(31,41,55,.10)'
    const labelColor = this.dark ? 'rgba(226,232,240,.75)' : 'rgba(31,41,55,.55)'

    ctx.clearRect(0, 0, W, H)
    // 网格环与十字
    ctx.strokeStyle = gridLine
    ctx.lineWidth = 1
    for (const k of [0.33, 0.66, 1]) {
      ctx.beginPath()
      ctx.arc(cx, cy, R * k, 0, Math.PI * 2)
      ctx.stroke()
    }
    ctx.beginPath()
    ctx.moveTo(cx - R, cy)
    ctx.lineTo(cx + R, cy)
    ctx.moveTo(cx, cy - R)
    ctx.lineTo(cx, cy + R)
    ctx.stroke()

    // 扫描扇面
    this.angle += 0.022
    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(this.angle)
    const sweep = ctx.createLinearGradient(0, 0, R, 0)
    sweep.addColorStop(0, this.dark ? 'rgba(52,211,153,.45)' : 'rgba(5,150,105,.40)')
    sweep.addColorStop(1, 'rgba(5,150,105,0)')
    ctx.fillStyle = sweep
    ctx.beginPath()
    ctx.moveTo(0, 0)
    ctx.arc(0, 0, R, -0.5, 0)
    ctx.closePath()
    ctx.fill()
    ctx.restore()

    // 中心
    ctx.fillStyle = primary
    ctx.beginPath()
    ctx.arc(cx, cy, 4 * dpr, 0, Math.PI * 2)
    ctx.fill()

    // 节点
    for (const n of this.nodes) {
      const x = cx + Math.cos(n.ang) * R * n.r
      const y = cy + Math.sin(n.ang) * R * n.r
      const rr = 5 * dpr
      ctx.fillStyle = n.ok ? primary : error
      ctx.beginPath()
      ctx.arc(x, y, rr, 0, Math.PI * 2)
      ctx.fill()
      ctx.strokeStyle = ctx.fillStyle
      ctx.globalAlpha = 0.35
      ctx.beginPath()
      ctx.arc(x, y, rr + 4 * dpr * (1 + Math.sin(this.angle * 3) * 0.5), 0, Math.PI * 2)
      ctx.stroke()
      ctx.globalAlpha = 1
      ctx.fillStyle = labelColor
      ctx.font = `${11 * dpr}px Fira Code, monospace`
      ctx.fillText(n.name, x + rr + 4, y + 4)
    }
  }
}
</script>
