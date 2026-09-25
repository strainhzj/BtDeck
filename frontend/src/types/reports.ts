/**
 * 统计报表契约类型（statistics-reports W4，PLANS/statistics-reports.md §4.4）。
 *
 * 纯 JSON 契约形状——与后端 report_service 输出一一对应。
 * ⚠ 禁止 import echarts 类型：契约类型不依赖图表库，避免把 echarts d.ts
 * 拖进 tsc 解析面（W4 实测锚定：echarts 5.5.1 + 锁定 TS 4.9.5）。
 */

// ==================== 公共 ====================

export interface SizeCountItem {
  count: number
  sizeBytes: number
}

export interface StatusDistItem extends SizeCountItem {
  bucket: 'error' | 'downloading' | 'seeding' | 'paused' | 'other'
}

// ==================== 总览（A1-A5） ====================

export interface OverviewTotals {
  count: number
  sizeBytes: number
  avgSizeBytes: number
  recycleBinSizeBytes: number
}

export interface LargestItem {
  hash: string
  name: string
  sizeBytes: number
}

export interface NameCountItem extends SizeCountItem {
  name: string
}

export interface PathCountItem extends SizeCountItem {
  path: string
}

export interface DownloaderCompareItem extends SizeCountItem {
  downloaderId: string
  nickname: string
  type: number | null
  removed: boolean
  statusDist: StatusDistItem[]
}

export interface LiveSpeedItem {
  downloaderId: string
  nickname: string
  online: boolean
  downloadSpeed: number
  uploadSpeed: number
}

export interface LiveSpeed {
  totalDownloadSpeed: number
  totalUploadSpeed: number
  items: LiveSpeedItem[]
}

export interface ReportsOverviewData {
  totals: OverviewTotals
  largest: LargestItem[]
  statusDist: StatusDistItem[]
  categories: NameCountItem[]
  tags: NameCountItem[]
  paths: PathCountItem[]
  downloaders: DownloaderCompareItem[]
  liveSpeed: LiveSpeed
}

// ==================== 趋势（B6-B8 + B9 速度历史） ====================

export interface TimeBucketItem extends SizeCountItem {
  key: string
}

export interface AgeBucketItem extends SizeCountItem {
  name: 'under7d' | 'to30d' | 'to90d' | 'to180d' | 'to1y' | 'over1y' | 'unknown'
}

export interface SpeedPoint {
  ts: string
  downloadSpeed: number
  uploadSpeed: number
  /** raw 点携带（分钟级）；hourly 点不携带 */
  online?: boolean
  /** hourly 点携带（供前端区分"全离线小时"与"停机无行"） */
  sampleCount?: number
  onlineCount?: number
}

export interface SpeedSeries {
  downloaderId: string
  nickname: string
  removed: boolean
  points: SpeedPoint[]
}

export interface SpeedHistory {
  range: '24h' | '7d' | '30d'
  series: SpeedSeries[]
  samplingActive: boolean
  firstSampleAt: string | null
}

export interface ReportsTrendsData {
  added: TimeBucketItem[]
  completed: TimeBucketItem[]
  ageBuckets: AgeBucketItem[]
  speedHistory: SpeedHistory
}

// ==================== 做种（C10-C12） ====================

export interface RatioBucketItem extends SizeCountItem {
  bucket: '<0.5' | '0.5-1' | '1-2' | '2-5' | '5-10' | '10+'
}

export interface SlackerItem {
  hash: string
  name: string
  sizeBytes: number
  ratio: number
}

export interface AuxiliarySeedItem {
  hash: string
  name: string
  auxiliarySeedCount: number
  sizeBytes: number
}

export interface AuxiliarySummary {
  totalTorrents: number
  crossSeedCount: number
  crossSeedRate: number
  top10: AuxiliarySeedItem[]
}

export interface ReportsSeedingData {
  ratioBuckets: RatioBucketItem[]
  ratioNullCount: number
  slackers: SlackerItem[]
  auxiliary: AuxiliarySummary
}

// ==================== Tracker（D14-D16） ====================

export interface TrackerSiteItem extends SizeCountItem {
  host: string
}

export interface TrackerHealthItem {
  host: string
  errorRate: number
  affectedCount: number
}

export interface SupplyDemandItem {
  host: string
  avgSeeders: number
  avgLeechers: number
  avgDownloads: number
  /** 有效行数（均值排除 NULL 后的分母） */
  count: number
}

export interface ReportsTrackersData {
  sites: TrackerSiteItem[]
  health: TrackerHealthItem[]
  supplyDemand: SupplyDemandItem[]
}

// ==================== 趣味（24/25/26/27） ====================

export interface GuardianFireItem {
  hash: string
  name: string
  sizeBytes: number
  minSeeders: number
}

export interface GuardianSummary {
  fireCount: number
  totalConsidered: number
  excludedCount: number
  top10: GuardianFireItem[]
}

export interface BadgeEquivalents {
  movies: number
  blurays: number
  tvSeasons: number
}

export type BadgeTier = 'bronze' | 'silver' | 'gold' | 'platinum' | 'diamond'

export interface BadgesSummary {
  uploadedBytes: number
  currentTier: BadgeTier
  nextTier: BadgeTier | null
  nextTierAtTB: number | null
  equivalents: BadgeEquivalents
}

export interface RatioRankItem {
  hash: string
  name: string
  ratio: number
  sizeBytes: number
}

export interface ReportsFunSummaryData {
  guardian: GuardianSummary
  badges: BadgesSummary
  shame: RatioRankItem[]
  pride: RatioRankItem[]
}

export interface ElderItem {
  hash: string
  name: string
  addedDate: string
  seedingDays: number
}

export interface KeyCountItem {
  key: string
  count: number
}

export interface ReportsFunYearlyData {
  year: number
  yearAdded: SizeCountItem
  busiestMonth: KeyCountItem | null
  busiestDay: KeyCountItem | null
  topSite: { host: string, sizeBytes: number } | null
  elder: ElderItem | null
  fireCount: number
  uploadEstimate: BadgesSummary
}

// ==================== 信封 ====================

export interface ReportsResponse<T> {
  code: string
  msg: string
  status: string
  data: T
}
