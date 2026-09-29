import { ApiError } from '@/types/api'
import { demoRequest } from '@/demo/demo-request'
import { demoStore } from '@/demo/demo-store'
import { DemoApiEnvelope, DemoDashboardData, DemoPage, DemoTorrent } from '@/demo/types'
import { ReportsFunSummaryData, ReportsFunYearlyData, ReportsOverviewData, ReportsSeedingData, ReportsTrackersData, ReportsTrendsData, SpeedHistory } from '@/types/reports'
import request from '@/utils/request'

describe('demo request', () => {
  const originalDemoMode = process.env.VUE_APP_DEMO_MODE

  beforeEach(() => {
    demoStore.reset()
    process.env.VUE_APP_DEMO_MODE = 'true'
  })

  afterEach(() => {
    if (originalDemoMode === undefined) {
      delete process.env.VUE_APP_DEMO_MODE
    } else {
      process.env.VUE_APP_DEMO_MODE = originalDemoMode
    }
  })

  it('returns a typed envelope and list/total/pageSize pagination', async() => {
    const response = await demoRequest<DemoApiEnvelope<DemoPage<DemoTorrent>>>({
      url: '/api/v1/torrents/getList',
      method: 'get',
      params: { page: 1, pageSize: 3 }
    })

    expect(response.code).toBe('200')
    expect(response.status).toBe('success')
    expect(response.data.list).toHaveLength(3)
    expect(response.data.pageSize).toBe(3)
    expect(response.data.total).toBe(9)
    expect(response.data.list[0].infoId).toBeDefined()
  })

  it('routes local mutations without touching a network client', async() => {
    const torrent = demoStore.snapshot().torrents[0]
    const response = await demoRequest<DemoApiEnvelope<{ updated_count: number }>>({
      url: '/torrents/pause',
      method: 'post',
      data: { hashes: [torrent.hash] }
    })

    expect(response.data.updated_count).toBe(1)
    expect(demoStore.getTorrent(torrent.hash)?.status).toBe('paused')
  })

  it('switches the shared request client to Demo mode before Axios', async() => {
    const response = await request<DemoApiEnvelope<DemoDashboardData>>({
      url: '/dashboard',
      method: 'get'
    })

    expect(response.code).toBe('200')
    expect(response.data).toHaveProperty('downloaders')
  })

  it('supports Blob exports, readable fallback responses and business errors', async() => {
    const blob = await demoRequest<Blob>({
      url: '/audit-logs/download-export/demo.txt',
      method: 'get',
      responseType: 'blob'
    })
    expect(blob).toBeInstanceOf(Blob)

    const fallback = await demoRequest<DemoApiEnvelope<{ supported: boolean }>>({
      url: '/demo/not-implemented',
      method: 'get'
    })
    expect(fallback.code).toBe('200')
    expect(fallback.data.supported).toBe(false)
    await expect(demoRequest({ url: '/demo/error', method: 'get' })).rejects.toMatchObject({ code: '422' })
    await expect(demoRequest({ url: '/demo/error', method: 'get' })).rejects.toBeInstanceOf(ApiError)
  })

  describe('MCP settings', () => {
    it('serves catalog with 6 capabilities and effectiveEnabled derived from stored intent', async() => {
      const response = await demoRequest<DemoApiEnvelope<{
        settings: { enabled: boolean, forceDisabled: boolean, effectiveEnabled: boolean, revision: number }
        catalog: Array<{ code: string, risk: string }>
      }>>({ url: '/mcp/settings', method: 'get' })

      expect(response.code).toBe('200')
      expect(response.data.catalog).toHaveLength(6)
      expect(response.data.catalog.map(item => item.code)).toContain('torrent.advanced_search')
      expect(response.data.settings.effectiveEnabled)
        .toBe(response.data.settings.enabled && !response.data.settings.forceDisabled)
    })

    it('updates via revision CAS and bumps revision; stale revision yields 409', async() => {
      const current = await demoRequest<DemoApiEnvelope<{ settings: { revision: number } }>>({
        url: '/mcp/settings', method: 'get'
      })
      const revision = current.data.settings.revision

      const updated = await demoRequest<DemoApiEnvelope<{ settings: { enabled: boolean, revision: number } }>>({
        url: '/mcp/settings',
        method: 'put',
        data: { enabled: false, capabilities: {}, expectedRevision: revision }
      })
      expect(updated.data.settings.enabled).toBe(false)
      expect(updated.data.settings.revision).toBe(revision + 1)

      await expect(demoRequest({
        url: '/mcp/settings',
        method: 'put',
        data: { enabled: true, capabilities: {}, expectedRevision: revision }
      })).rejects.toMatchObject({ code: '409' })
    })
  })

  describe('MCP service key', () => {
    it('serves the demo key in active view shape', async() => {
      const response = await demoRequest<DemoApiEnvelope<{ status: string, exists: boolean, revision: number, key: string, keyPrefix: string }>>({ url: '/mcp/apikey', method: 'get' })

      expect(response.code).toBe('200')
      expect(response.data.status).toBe('active')
      expect(response.data.exists).toBe(true)
      expect(response.data.key.startsWith('btdmcp_')).toBe(true)
      expect(response.data.keyPrefix).toBe('btdmcp_')
    })

    it('rotates via revision CAS and bumps revision; stale revision yields 409', async() => {
      const current = await demoRequest<DemoApiEnvelope<{ revision: number }>>({
        url: '/mcp/apikey', method: 'get'
      })
      const revision = current.data.revision

      const rotated = await demoRequest<DemoApiEnvelope<{ revision: number }>>({
        url: '/mcp/apikey/rotate',
        method: 'post',
        data: { expectedRevision: revision }
      })
      expect(rotated.data.revision).toBe(revision + 1)

      await expect(demoRequest({
        url: '/mcp/apikey/rotate',
        method: 'post',
        data: { expectedRevision: revision }
      })).rejects.toMatchObject({ code: '409' })
    })
  })

  describe('MoviePilot integration', () => {
    it('serves settings, instance page and forward associations with task snapshots', async() => {
      const settings = await demoRequest<DemoApiEnvelope<{ settings: { enabled: boolean }, protocolVersion: number }>>({
        url: '/moviepilot/settings', method: 'get'
      })
      expect(settings.data.settings.enabled).toBe(true)
      expect(settings.data.protocolVersion).toBe(1)

      const instances = await demoRequest<DemoApiEnvelope<DemoPage<{ instanceId: string, syncedHistoryCount: number }>>>({
        url: '/moviepilot/instances', method: 'get', params: { page: 1, pageSize: 10 }
      })
      expect(instances.data.total).toBe(2)
      expect(instances.data.list[0].syncedHistoryCount).toBeGreaterThan(0)

      // linked 关联（demo-info-002 → 家庭节点 B）应回带任务快照
      const torrent = demoStore.snapshot().torrents.find(item => item.infoId === 'demo-info-002')
      const forward = await demoRequest<DemoApiEnvelope<DemoPage<{
        associationStatus: string
        task?: { infoId: string } | null
      }>>>({
        url: '/moviepilot/associations', method: 'get',
        params: { downloaderId: torrent?.downloaderId, hash: torrent?.hash, page: 1, pageSize: 10 }
      })
      expect(forward.data.total).toBe(1)
      expect(forward.data.list[0].associationStatus).toBe('linked')
      expect(forward.data.list[0].task?.infoId).toBe('demo-info-002')
    })

    it('reverse lookup matches by path prefix and honours mode filter', async() => {
      const both = await demoRequest<DemoApiEnvelope<DemoPage<{ destPath: string | null, srcPath: string | null }>>>({
        url: '/moviepilot/associations/reverse', method: 'get',
        params: { path: '/demo/media', mode: 'both', page: 1, pageSize: 10 }
      })
      expect(both.data.total).toBe(3)

      const destOnly = await demoRequest<DemoApiEnvelope<DemoPage<{ destPath: string | null }>>>({
        url: '/moviepilot/associations/reverse', method: 'get',
        params: { path: '/demo/media', mode: 'dest', page: 1, pageSize: 10 }
      })
      expect(destOnly.data.total).toBe(3)

      const srcOnly = await demoRequest<DemoApiEnvelope<DemoPage<{ srcPath: string | null }>>>({
        url: '/moviepilot/associations/reverse', method: 'get',
        params: { path: '/demo/media', mode: 'src', page: 1, pageSize: 10 }
      })
      expect(srcOnly.data.total).toBe(0)
    })

    it('updates instance mapping and re-resolves association status', async() => {
      // 未映射关联（mpDownloader 归档 qBittorrent）：补映射后应变 linked
      const instanceId = 'demo-mp-instance-001'
      const updated = await demoRequest<DemoApiEnvelope<{
        downloaderMapping: Record<string, string>
      }>>({
        url: `/moviepilot/instances/${instanceId}`,
        method: 'put',
        data: { downloaderMapping: { '归档 qBittorrent': 'demo-downloader-001' } }
      })
      expect(updated.data.downloaderMapping['归档 qBittorrent']).toBe('demo-downloader-001')

      const torrent = demoStore.snapshot().torrents.find(item => item.infoId === 'demo-info-001')
      const forward = await demoRequest<DemoApiEnvelope<DemoPage<{ associationStatus: string }>>>({
        url: '/moviepilot/associations', method: 'get',
        params: { downloaderId: torrent?.downloaderId, hash: torrent?.hash, page: 1, pageSize: 10 }
      })
      expect(forward.data.list[0].associationStatus).toBe('linked')
    })

    it('deletes instance together with its mirrored histories', async() => {
      const response = await demoRequest<DemoApiEnvelope<{ instanceId: string, deletedHistories: number }>>({
        url: '/moviepilot/instances/demo-mp-instance-001',
        method: 'delete'
      })
      expect(response.data.instanceId).toBe('demo-mp-instance-001')
      expect(response.data.deletedHistories).toBe(3)
      expect(demoStore.snapshot().moviepilotAssociations).toHaveLength(0)
    })

    it('settings update honours revision CAS', async() => {
      const current = await demoRequest<DemoApiEnvelope<{ settings: { revision: number } }>>({
        url: '/moviepilot/settings', method: 'get'
      })
      const revision = current.data.settings.revision

      const updated = await demoRequest<DemoApiEnvelope<{ settings: { enabled: boolean, revision: number } }>>({
        url: '/moviepilot/settings',
        method: 'put',
        data: { enabled: false, expectedRevision: revision }
      })
      expect(updated.data.settings.enabled).toBe(false)
      expect(updated.data.settings.revision).toBe(revision + 1)

      await expect(demoRequest({
        url: '/moviepilot/settings',
        method: 'put',
        data: { enabled: true, expectedRevision: revision }
      })).rejects.toMatchObject({ code: '409' })
    })
  })
})

describe('statistics reports branches (statistics-reports W7)', () => {
  it('serves overview with five-bucket dist and removed downloader marker', async() => {
    const response = await demoRequest<DemoApiEnvelope<ReportsOverviewData>>({
      url: '/api/v1/reports/overview',
      method: 'get'
    })
    expect(response.code).toBe('200')
    const buckets = response.data.statusDist.map(item => item.bucket)
    expect(buckets).toEqual(expect.arrayContaining(['seeding', 'downloading', 'paused', 'error', 'other']))
    const removed = response.data.downloaders.find(item => item.removed)
    expect(removed?.nickname).toBe('已退役节点')
  })

  it('serves trends with period/limit normalized (week caps to limit buckets)', async() => {
    const response = await demoRequest<DemoApiEnvelope<ReportsTrendsData>>({
      url: '/api/v1/reports/trends',
      method: 'get',
      params: { period: 'week', limit: 3 }
    })
    expect(response.data.added.length).toBe(3)
    expect(response.data.added[0].key).toMatch(/^\d{4}-\d{2}$/)
    expect(response.data.speedHistory.series.length).toBeGreaterThan(0)
  })

  it('serves seeding with ratio buckets and cross-seed rate', async() => {
    const response = await demoRequest<DemoApiEnvelope<ReportsSeedingData>>({
      url: '/api/v1/reports/seeding',
      method: 'get'
    })
    expect(response.data.ratioBuckets.map(item => item.bucket)).toEqual(['<0.5', '0.5-1', '1-2', '2-5', '5-10', '10+'])
    expect(response.data.auxiliary.crossSeedRate).toBeGreaterThan(0)
  })

  it('serves trackers health sorted implicitly and host without port', async() => {
    const response = await demoRequest<DemoApiEnvelope<ReportsTrackersData>>({
      url: '/api/v1/reports/trackers',
      method: 'get'
    })
    expect(response.data.sites.every(item => !item.host.includes(':'))).toBe(true)
    expect(response.data.health.length).toBe(3)
  })

  it('serves fun summary with badge tier and fire guardian', async() => {
    const response = await demoRequest<DemoApiEnvelope<ReportsFunSummaryData>>({
      url: '/api/v1/reports/fun/summary',
      method: 'get'
    })
    expect(response.data.badges.currentTier).toBe('gold')
    expect(response.data.guardian.fireCount).toBeGreaterThan(0)
  })

  it('serves fun yearly with year clamp and empty shape for out-of-range years', async() => {
    const inRange = await demoRequest<DemoApiEnvelope<ReportsFunYearlyData>>({
      url: '/api/v1/reports/fun/yearly',
      method: 'get',
      params: { year: 2025 }
    })
    expect(inRange.data.year).toBe(2025)
    expect(inRange.data.yearAdded.count).toBeGreaterThan(0)
    const clamped = await demoRequest<DemoApiEnvelope<ReportsFunYearlyData>>({
      url: '/api/v1/reports/fun/yearly',
      method: 'get',
      params: { year: 1999 }
    })
    expect(clamped.data.year).toBe(2024) // 越界就近收敛到 YearPicker 域下界（Demo 与后端 400 语义不同，就近展示）
    expect(clamped.data.yearAdded.count).toBeGreaterThan(0)
  })

  it('serves speed history with range normalization and downloader filter', async() => {
    const full = await demoRequest<DemoApiEnvelope<SpeedHistory>>({
      url: '/api/v1/reports/speed/history',
      method: 'get',
      params: { range: '7d' }
    })
    expect(full.data.range).toBe('7d')
    expect(full.data.series.length).toBe(2)
    expect(full.data.series[0].points.length).toBe(168) // 7d hourly
    const filtered = await demoRequest<DemoApiEnvelope<SpeedHistory>>({
      url: '/api/v1/reports/speed/history',
      method: 'get',
      params: { range: 'bogus', downloaderId: 'demo-dl-002' }
    })
    expect(filtered.data.range).toBe('24h') // 非法 range 收敛 24h
    expect(filtered.data.series.length).toBe(1)
    expect(filtered.data.series[0].downloaderId).toBe('demo-dl-002')
    expect(filtered.data.series[0].points.length).toBe(96) // 24h 15 分钟粒度假曲线
    expect(filtered.data.samplingActive).toBe(true)
  })
})
