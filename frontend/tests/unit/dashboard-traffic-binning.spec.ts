/**
 * trafficBinning 单测（仪表盘一期 W3/W5，计划 v2 M-2 口径钉死）。
 *
 * 重点场景：
 * - 跨 0 点：滚动 24h 窗内昨天 23 点与今天 0 点各自成桶、按时间升序；
 * - 小时分桶 + 速度×60s 积分；多下载器合并；窗口外点裁剪；
 * - formatTrafficBytes 分档。
 */

import { bucketSpeedHistoryByHour, formatTrafficBytes, HourTrafficResult } from '@/views/dashboard/components/trafficBinning'
import { SpeedSeries } from '@/types/reports'

function rawPoint(ts: string, dl: number, ul: number) {
  return { ts, downloadSpeed: dl, uploadSpeed: ul }
}

describe('bucketSpeedHistoryByHour', () => {
  it('bins minutes into one hour bucket and integrates speed × 60s', () => {
    // 固定"现在"：2026-11-03 14:30 本地时间
    const now = new Date(2026, 10, 3, 14, 30, 0)
    const series: SpeedSeries[] = [
      {
        downloaderId: 'dl-1',
        nickname: 'qb',
        removed: false,
        points: [
          rawPoint(new Date(2026, 10, 3, 14, 0, 0).toISOString(), 100, 50),
          rawPoint(new Date(2026, 10, 3, 14, 1, 0).toISOString(), 200, 0)
        ]
      }
    ]
    const result = bucketSpeedHistoryByHour(series, now)
    expect(result.buckets).toHaveLength(1)
    const b = result.buckets[0]
    expect(b.label).toBe('14:00')
    expect(b.hourStart.getHours()).toBe(14)
    // (100+50)*60 + (200+0)*60
    expect(b.downloadBytes).toBe((100 + 200) * 60)
    expect(b.uploadBytes).toBe(50 * 60)
    expect(result.downloadTotalBytes).toBe(300 * 60)
    expect(result.uploadTotalBytes).toBe(50 * 60)
  })

  it('crosses midnight: yesterday 23:00 and today 00:00 are separate ascending buckets', () => {
    // 跨 0 点场景（M-2 钉死）：now=今天 00:30，窗口覆盖昨天 00:30 之后
    const now = new Date(2026, 10, 3, 0, 30, 0)
    const series: SpeedSeries[] = [
      {
        downloaderId: 'dl-1',
        nickname: 'qb',
        removed: false,
        points: [
          rawPoint(new Date(2026, 10, 2, 23, 10, 0).toISOString(), 100, 10), // 昨天 23 点桶
          rawPoint(new Date(2026, 10, 2, 23, 59, 0).toISOString(), 100, 10),
          rawPoint(new Date(2026, 10, 3, 0, 5, 0).toISOString(), 300, 30) // 今天 0 点桶
        ]
      }
    ]
    const result = bucketSpeedHistoryByHour(series, now)
    expect(result.buckets).toHaveLength(2)
    const [y23, t0] = result.buckets
    expect(y23.label).toBe('23:00')
    expect(y23.hourStart.getDate()).toBe(2)
    expect(t0.label).toBe('00:00')
    expect(t0.hourStart.getDate()).toBe(3)
    // 升序：昨天桶在前
    expect(y23.hourStart.getTime()).toBeLessThan(t0.hourStart.getTime())
    expect(y23.downloadBytes).toBe(200 * 60)
    expect(t0.downloadBytes).toBe(300 * 60)
  })

  it('merges multiple downloader series into the same bucket', () => {
    const now = new Date(2026, 10, 3, 10, 0, 0)
    const mk = (id: string, dl: number): SpeedSeries => ({
      downloaderId: id,
      nickname: id,
      removed: false,
      points: [rawPoint(new Date(2026, 10, 3, 9, 15, 0).toISOString(), dl, 0)]
    })
    const result = bucketSpeedHistoryByHour([mk('a', 100), mk('b', 250)], now)
    expect(result.buckets).toHaveLength(1)
    expect(result.buckets[0].downloadBytes).toBe(350 * 60)
  })

  it('clips points outside the rolling 24h window', () => {
    const now = new Date(2026, 10, 3, 12, 0, 0)
    const series: SpeedSeries[] = [
      {
        downloaderId: 'dl-1',
        nickname: 'qb',
        removed: false,
        points: [
          rawPoint(new Date(2026, 10, 2, 12, 0, 0).toISOString(), 999, 999), // 恰在窗口起点（<= 排除）
          rawPoint(new Date(2026, 10, 2, 12, 0, 1).toISOString(), 100, 0), // 窗口内
          rawPoint(new Date(2026, 10, 3, 12, 0, 5).toISOString(), 50, 0), // 未来点裁剪
          rawPoint('not-a-date', 500, 500) // 非法 ts 跳过
        ]
      }
    ]
    const result = bucketSpeedHistoryByHour(series, now)
    // 仅窗口内点计入：边界点(999)/未来点(50)/非法点均被裁剪
    expect(result.downloadTotalBytes).toBe(100 * 60)
    expect(result.uploadTotalBytes).toBe(0)
  })

  it('returns empty result for empty or point-less series', () => {
    const now = new Date(2026, 10, 3, 12, 0, 0)
    const empty = bucketSpeedHistoryByHour([], now)
    expect(empty.buckets).toEqual([])
    expect(empty.downloadTotalBytes).toBe(0)
    const noPoints = bucketSpeedHistoryByHour(
      [{ downloaderId: 'a', nickname: 'a', removed: false, points: [] }],
      now
    ) as HourTrafficResult
    expect(noPoints.buckets).toEqual([])
  })
})

describe('formatTrafficBytes', () => {
  it('formats B/KB/MB/GB/TB with per-magnitude digits', () => {
    expect(formatTrafficBytes(0)).toBe('0 B')
    expect(formatTrafficBytes(512)).toBe('512 B')
    expect(formatTrafficBytes(1024)).toBe('1.00 KB')
    expect(formatTrafficBytes(1536 * 1024)).toBe('1.50 MB')
    expect(formatTrafficBytes(412 * 1024 ** 3)).toBe('412 GB')
    expect(formatTrafficBytes(1.6 * 1024 ** 4)).toBe('1.60 TB')
  })

  it('handles non-finite and negative values as zero', () => {
    expect(formatTrafficBytes(-5)).toBe('0 B')
    expect(formatTrafficBytes(Number.NaN)).toBe('0 B')
  })
})
