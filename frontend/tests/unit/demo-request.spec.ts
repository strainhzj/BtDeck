import { ApiError } from '@/types/api'
import { demoRequest } from '@/demo/demo-request'
import { demoStore } from '@/demo/demo-store'
import { DemoApiEnvelope, DemoDashboardData, DemoPage, DemoTorrent } from '@/demo/types'
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
})
