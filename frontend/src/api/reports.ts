/**
 * 统计报表 API 模块（statistics-reports W4）。
 *
 * 照 dashboard.ts 惯例：request 返回完整信封 {status, msg, code, data}，
 * 页面按 res.code === '200' && res.data 消费。
 */

import request from '@/utils/request'
import {
  ReportsFunSummaryData,
  ReportsFunYearlyData,
  ReportsOverviewData,
  ReportsResponse,
  ReportsSeedingData,
  ReportsTrackersData,
  ReportsTrendsData,
  SpeedHistory
} from '@/types/reports'

export type TrendsPeriod = 'month' | 'week'
export type SpeedRange = '24h' | '7d' | '30d'

export const getReportsOverview = (): Promise<ReportsResponse<ReportsOverviewData>> =>
  request<ReportsResponse<ReportsOverviewData>>({
    url: '/reports/overview',
    method: 'get'
  })

export const getReportsTrends = (period: TrendsPeriod = 'month', limit = 12): Promise<ReportsResponse<ReportsTrendsData>> =>
  request<ReportsResponse<ReportsTrendsData>>({
    url: '/reports/trends',
    method: 'get',
    params: { period, limit }
  })

export const getReportsSeeding = (): Promise<ReportsResponse<ReportsSeedingData>> =>
  request<ReportsResponse<ReportsSeedingData>>({
    url: '/reports/seeding',
    method: 'get'
  })

export const getReportsTrackers = (): Promise<ReportsResponse<ReportsTrackersData>> =>
  request<ReportsResponse<ReportsTrackersData>>({
    url: '/reports/trackers',
    method: 'get'
  })

export const getReportsFunSummary = (): Promise<ReportsResponse<ReportsFunSummaryData>> =>
  request<ReportsResponse<ReportsFunSummaryData>>({
    url: '/reports/fun/summary',
    method: 'get'
  })

export const getReportsFunYearly = (year?: number): Promise<ReportsResponse<ReportsFunYearlyData>> =>
  request<ReportsResponse<ReportsFunYearlyData>>({
    url: '/reports/fun/yearly',
    method: 'get',
    params: year !== undefined ? { year } : undefined
  })

export const getReportsSpeedHistory = (range: SpeedRange = '24h', downloaderId?: string): Promise<ReportsResponse<SpeedHistory>> =>
  request<ReportsResponse<SpeedHistory>>({
    url: '/reports/speed/history',
    method: 'get',
    params: downloaderId !== undefined ? { range, downloaderId } : { range }
  })
