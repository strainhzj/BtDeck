/**
 * 近 24h 流量分桶积分（仪表盘一期 W3，计划 v2 M-2 修正口径）。
 *
 * 输入：/reports/speed/history?range=24h 的分钟级 raw 点（多下载器 series）；
 * 处理：滚动 24h 窗口裁剪 → 合并多下载器 → 按本地小时分桶 →
 *       速度积分成字节（每 raw 点代表 60s 采样：speed × 60）；
 * 输出：按时间升序的 24 桶（label "HH:00"）+ 上传/下载合计。
 *
 * 文案口径：滚动 24h 窗，用「近 24h」不用「今日」（跨 0 点的桶按时间顺序
 * 排列，昨天与今天的同一小时数是两个桶——Jest 跨 0 点场景钉此行为）。
 */

import { SpeedSeries } from '@/types/reports'

export interface HourTrafficBucket {
  /** 本地小时标签 "HH:00"（仅展示用，非唯一键） */
  label: string
  /** 桶起始时间（本地，用于排序/测试断言） */
  hourStart: Date
  downloadBytes: number
  uploadBytes: number
}

export interface HourTrafficResult {
  buckets: HourTrafficBucket[]
  downloadTotalBytes: number
  uploadTotalBytes: number
}

/** raw 点代表的采样间隔（后端 speed_sampler 60s 采样，分钟级 raw） */
const SECONDS_PER_POINT = 60

/** 滚动窗口：24h */
const WINDOW_MS = 24 * 3600 * 1000

/** 小时桶 key：本地时间的整点毫秒值 */
function hourKey(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), date.getHours()).getTime()
}

function labelOf(date: Date): string {
  const h = date.getHours()
  return `${h < 10 ? '0' : ''}${h}:00`
}

/**
 * 多下载器分钟级 raw → 24 桶小时流量。
 *
 * - 窗口裁剪：仅保留 (now - 24h, now] 的点（后端已裁，前端防御性再裁）；
 * - 积分：每点 speed(B/s) × 60s 入该点所在小时的桶（多下载器直接累加）；
 * - 桶按时间升序输出；无数据返回空结果。
 */
export function bucketSpeedHistoryByHour(series: SpeedSeries[], now: Date = new Date()): HourTrafficResult {
  const windowStart = now.getTime() - WINDOW_MS
  const buckets = new Map<number, HourTrafficBucket>()
  let downloadTotal = 0
  let uploadTotal = 0

  for (const s of series) {
    for (const p of s.points || []) {
      const ts = new Date(p.ts).getTime()
      if (!Number.isFinite(ts) || ts <= windowStart || ts > now.getTime()) continue
      const key = hourKey(new Date(ts))
      let bucket = buckets.get(key)
      if (!bucket) {
        const hourStart = new Date(key)
        bucket = { label: labelOf(hourStart), hourStart, downloadBytes: 0, uploadBytes: 0 }
        buckets.set(key, bucket)
      }
      const dl = (p.downloadSpeed || 0) * SECONDS_PER_POINT
      const ul = (p.uploadSpeed || 0) * SECONDS_PER_POINT
      bucket.downloadBytes += dl
      bucket.uploadBytes += ul
      downloadTotal += dl
      uploadTotal += ul
    }
  }

  const ordered = [...buckets.values()].sort((a, b) => a.hourStart.getTime() - b.hourStart.getTime())
  return { buckets: ordered, downloadTotalBytes: downloadTotal, uploadTotalBytes: uploadTotal }
}

/** 字节量格式化（流量卡合计展示；GB/TB 两档足够，B/KB 场景展示原始值） */
export function formatTrafficBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let value = bytes
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  const digits = value >= 100 ? 0 : value >= 10 ? 1 : 2
  return `${value.toFixed(digits)} ${units[idx]}`
}
