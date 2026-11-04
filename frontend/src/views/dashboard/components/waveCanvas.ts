/**
 * 波浪 canvas 绘制共享工具（仪表盘一期 W4；HeroPulseCard 与 DataScreen 共用）。
 *
 * 三层正弦叠加波浪（浅色/深色两套配色由调用方传入 layers），自研实现，
 * 非移植 BitMatrix Canvas 代码（计划边界）。
 */

export interface WaveLayer {
  /** 振幅（占画布高度比例） */
  amp: number
  /** 波长密度 */
  len: number
  /** 相位速度 */
  speed: number
  /** 填充色（含 alpha） */
  color: string
  /** 基线（占画布高度比例） */
  off: number
}

/** 首页 hero 波浪（浅色令牌系） */
export const HERO_WAVE_LAYERS: WaveLayer[] = [
  { amp: 0.3, len: 1.15, speed: 0.028, color: 'rgba(5,150,105,.28)', off: 0.55 },
  { amp: 0.2, len: 0.8, speed: -0.04, color: 'rgba(59,130,246,.22)', off: 0.7 },
  { amp: 0.12, len: 1.6, speed: 0.02, color: 'rgba(16,185,129,.40)', off: 0.82 }
]

/** 大屏吞吐波浪（--screen-* 深色系） */
export const SCREEN_WAVE_LAYERS: WaveLayer[] = [
  { amp: 0.34, len: 1.05, speed: 0.03, color: 'rgba(52,211,153,.30)', off: 0.58 },
  { amp: 0.22, len: 1.9, speed: -0.045, color: 'rgba(96,165,250,.25)', off: 0.72 },
  { amp: 0.13, len: 2.8, speed: 0.022, color: 'rgba(251,191,36,.22)', off: 0.84 }
]

/** 单帧绘制三层波浪；t 为递增帧计数（调用方每帧 +1） */
export function drawWaves(ctx: CanvasRenderingContext2D, width: number, height: number, t: number, layers: WaveLayer[]): void {
  ctx.clearRect(0, 0, width, height)
  for (const L of layers) {
    const base = height * L.off
    ctx.beginPath()
    ctx.moveTo(0, height)
    for (let x = 0; x <= width; x += 6) {
      const y =
        base +
        Math.sin((x / width) * Math.PI * 2 * L.len + t * L.speed * 10) * height * L.amp * 0.45 +
        Math.sin((x / width) * Math.PI * 2 * L.len * 2.7 + t * L.speed * 6) * height * L.amp * 0.18
      ctx.lineTo(x, y)
    }
    ctx.lineTo(width, height)
    ctx.closePath()
    ctx.fillStyle = L.color
    ctx.fill()
  }
}

/** canvas 按 devicePixelRatio 适配容器尺寸；返回是否成功 */
export function fitCanvasToContainer(canvas: HTMLCanvasElement, container?: HTMLElement | null): boolean {
  const target = container || canvas
  const rect = target.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return false
  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.max(10, Math.round(rect.width * dpr))
  canvas.height = Math.max(10, Math.round(rect.height * dpr))
  return true
}
