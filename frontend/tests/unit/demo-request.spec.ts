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

  describe('rss subscriptions', () => {
    it('lists feeds bound to a downloader with pendingCount and pagination shape', async() => {
      const response = await demoRequest<DemoApiEnvelope<{ list: Array<{ feedId: string, pendingCount: number }>, total: number, pageSize: number }>>({
        url: '/rss/feeds',
        method: 'get',
        params: { downloaderId: 'demo-downloader-001' }
      })
      expect(response.code).toBe('200')
      expect(response.data.total).toBe(1)
      expect(response.data.list[0].feedId).toBe('demo-rss-feed-001')
      expect(response.data.list[0].pendingCount).toBe(1)
    })

    it('lists articles with status filter and pagination envelope', async() => {
      const pending = await demoRequest<DemoApiEnvelope<{ list: Array<{ status: string }>, total: number }>>({
        url: '/rss/feeds/demo-rss-feed-001/articles',
        method: 'get',
        params: { status: 'pending', page: 1, pageSize: 10 }
      })
      expect(pending.data.total).toBe(1)
      expect(pending.data.list[0].status).toBe('pending')
    })

    it('refresh appends one deduped article and marks fetch ok', async() => {
      const first = await demoRequest<DemoApiEnvelope<{ newCount: number, articleCount: number }>>({
        url: '/rss/feeds/demo-rss-feed-001/refresh',
        method: 'post'
      })
      expect(first.data.newCount).toBe(1)
      const second = await demoRequest<DemoApiEnvelope<{ newCount: number }>>({
        url: '/rss/feeds/demo-rss-feed-001/refresh',
        method: 'post'
      })
      expect(second.data.newCount).toBe(0)
      expect(demoStore.getRssFeed('demo-rss-feed-001')?.lastFetchStatus).toBe('ok')
    })

    it('pushes an article once and rejects repeated pushes', async() => {
      const ok = await demoRequest<DemoApiEnvelope<{ article: { status: string } }>>({
        url: '/rss/articles/demo-rss-article-001/add',
        method: 'post',
        data: { downloaderId: 'demo-downloader-001' }
      })
      expect(ok.data.article.status).toBe('added')

      const repeated = await demoRequest<DemoApiEnvelope<{ reasonCode?: string }>>({
        url: '/rss/articles/demo-rss-article-001/add',
        method: 'post',
        data: {}
      })
      expect(repeated.data.reasonCode).toBe('RSS_ARTICLE_NOT_FOUND')
    })

    it('creates and deletes a local feed within the session', async() => {
      const created = await demoRequest<DemoApiEnvelope<{ feed: { feedId: string } }>>({
        url: '/rss/feeds',
        method: 'post',
        data: { downloaderId: 'demo-downloader-001', name: 'Demo 新源', url: 'https://rss.example.invalid/new.xml' }
      })
      const feedId = created.data.feed.feedId
      expect(feedId).toContain('demo-rss-feed-local')

      const deleted = await demoRequest<DemoApiEnvelope<Record<string, unknown>>>({
        url: `/rss/feeds/${feedId}`,
        method: 'delete'
      })
      expect(deleted.code).toBe('200')
      expect(demoStore.getRssFeed(feedId)).toBeNull()
    })
  })

  describe('rss phase2: mode + rules + qb proxy', () => {
    it('mode defaults btdeck and switches to qb_native', async() => {
      const initial = await demoRequest<DemoApiEnvelope<{ mode: string, qbNativeAvailable: boolean }>>({
        url: '/rss/mode',
        method: 'get',
        params: { downloaderId: 'demo-downloader-001' }
      })
      expect(initial.data.mode).toBe('btdeck')
      expect(initial.data.qbNativeAvailable).toBe(true)

      const switched = await demoRequest<DemoApiEnvelope<{ mode: string }>>({
        url: '/rss/mode',
        method: 'put',
        data: { downloaderId: 'demo-downloader-001', mode: 'qb_native' }
      })
      expect(switched.data.mode).toBe('qb_native')

      const reread = await demoRequest<DemoApiEnvelope<{ mode: string }>>({
        url: '/rss/mode',
        method: 'get',
        params: { downloaderId: 'demo-downloader-001' }
      })
      expect(reread.data.mode).toBe('qb_native')

      // 还原，避免影响后续用例
      await demoRequest({ url: '/rss/mode', method: 'put', data: { downloaderId: 'demo-downloader-001', mode: 'btdeck' } })
    })

    it('lists engine rules from fixtures', async() => {
      const rules = await demoRequest<DemoApiEnvelope<DemoPage<{ ruleId: string, name: string, matchCount: number }>>>({
        url: '/rss/rules',
        method: 'get',
        params: { downloaderId: 'demo-downloader-001' }
      })
      expect(rules.data.total).toBeGreaterThanOrEqual(2)
      expect(rules.data.list[0].name).toBe('剧集 1080p 追更')
    })

    it('creates a rule with backfill pushing matching pending articles', async() => {
      const created = await demoRequest<
        DemoApiEnvelope<{
          rule: { ruleId: string, name: string }
          backfill: { matched: number, pushed: number, failed: number, skippedMode: number }
        }>
      >({
        url: '/rss/rules',
        method: 'post',
        data: { downloaderId: 'demo-downloader-001', name: '回填规则', includeKeywords: 'Show' }
      })
      expect(created.data.backfill.matched).toBeGreaterThan(0)
      expect(created.data.backfill.pushed).toBe(created.data.backfill.matched)

      const preview = await demoRequest<
        DemoApiEnvelope<{ list: Array<{ title: string }>, total: number }>
      >({
        url: `/rss/rules/${created.data.rule.ruleId}/match-preview`,
        method: 'post'
      })
      expect(preview.data.total).toBe(0) // 回填后无剩余命中

      await demoRequest({ url: `/rss/rules/${created.data.rule.ruleId}`, method: 'delete' })
    })

    it('backfill skips push when target downloader in qb_native mode', async() => {
      await demoRequest({ url: '/rss/mode', method: 'put', data: { downloaderId: 'demo-downloader-001', mode: 'qb_native' } })
      const created = await demoRequest<
        DemoApiEnvelope<{ rule: { ruleId: string }, backfill: { matched: number, skippedMode: number, pushed: number } }>
      >({
        url: '/rss/rules',
        method: 'post',
        data: { downloaderId: 'demo-downloader-001', name: '跳过规则', includeKeywords: 'Show' }
      })
      expect(created.data.backfill.skippedMode).toBe(created.data.backfill.matched)
      expect(created.data.backfill.pushed).toBe(0)
      await demoRequest({ url: `/rss/rules/${created.data.rule.ruleId}`, method: 'delete' })
      await demoRequest({ url: '/rss/mode', method: 'put', data: { downloaderId: 'demo-downloader-001', mode: 'btdeck' } })
    })

    it('qb proxy: tree/rules/preferences/articles/mark-read', async() => {
      const tree = await demoRequest<DemoApiEnvelope<{ list: Array<{ type: string, name: string }> }>>({
        url: '/rss/qb/demo-downloader-001/feeds',
        method: 'get'
      })
      expect(tree.data.list).toHaveLength(2)
      expect(tree.data.list[0].type).toBe('folder')

      const rules = await demoRequest<DemoApiEnvelope<{ list: Array<{ name: string, mustContain: string }>, total: number }>>({
        url: '/rss/qb/demo-downloader-001/rules',
        method: 'get'
      })
      expect(rules.data.total).toBe(1)
      expect(rules.data.list[0].mustContain).toBe('Drama')

      const prefs = await demoRequest<DemoApiEnvelope<{ preferences: { rssRefreshInterval: number } }>>({
        url: '/rss/qb/demo-downloader-001/preferences',
        method: 'get'
      })
      expect(prefs.data.preferences.rssRefreshInterval).toBe(30)

      const updated = await demoRequest<DemoApiEnvelope<{ preferences: { rssRefreshInterval: number } }>>({
        url: '/rss/qb/demo-downloader-001/preferences',
        method: 'put',
        data: { rssRefreshInterval: 15 }
      })
      expect(updated.data.preferences.rssRefreshInterval).toBe(15)

      const articles = await demoRequest<DemoApiEnvelope<{ list: Array<{ articleId: string, isRead: boolean }>, unreadCount: number }>>({
        url: '/rss/qb/demo-downloader-001/articles',
        method: 'get',
        params: { path: '剧集\\周一剧组' }
      })
      expect(articles.data.unreadCount).toBe(1)

      await demoRequest({
        url: '/rss/qb/demo-downloader-001/items/mark-read',
        method: 'post',
        data: { path: '剧集\\周一剧组', articleId: articles.data.list[0].articleId }
      })
      const afterRead = await demoRequest<DemoApiEnvelope<{ unreadCount: number }>>({
        url: '/rss/qb/demo-downloader-001/articles',
        method: 'get',
        params: { path: '剧集\\周一剧组' }
      })
      expect(afterRead.data.unreadCount).toBe(0)
    })

    it('qb proxy rejects non-qB downloader', async() => {
      const rejected = await demoRequest<DemoApiEnvelope<{ reasonCode: string }>>({
        url: '/rss/qb/demo-downloader-002/rules',
        method: 'get'
      })
      expect(rejected.data.reasonCode).toBe('RSS_QB_TYPE_UNSUPPORTED')
    })
  })
})
