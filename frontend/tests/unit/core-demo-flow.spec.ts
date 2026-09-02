import { getDashboardData } from '@/api/dashboard'
import {
  addDownloader,
  deleteDownloader,
  getDetail,
  getDownloaderCapabilities,
  getDownloaderSettings,
  getList as getDownloaderList,
  getPathMappings,
  getStatusAll,
  upDownloader
} from '@/api/downloader'
import {
  applySearchTemplate,
  createSearchTemplate,
  getSearchTemplates,
  getTorrentList,
  pauseTorrents,
  resumeTorrents
} from '@/api/torrents'
import type { ApiResponse, SearchTemplate, Torrent, TorrentListResponseData } from '@/api/torrents'
import {
  getNotificationList,
  getUnreadCount,
  markAsRead
} from '@/api/notification'
import { demoStore } from '@/demo/demo-store'
import type { Downloader } from '@/views/downloader/types'

interface DownloaderStatusRow {
  id: string
  connectStatus: string
  downloadSpeed: string
  uploadSpeed: string
}

interface DownloaderDetail extends Downloader {
  username: string
  isSsl: '0' | '1'
}

interface DownloaderSettingsSummary {
  downloader_id: string
}

interface DownloaderCapabilitiesSummary {
  supports_path_mapping: boolean
}

interface PathMappingSummary {
  mappings: unknown[]
}

describe('core demo page flow', () => {
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

  it('serves dashboard and downloader pages from the same local source', async() => {
    const dashboard = await getDashboardData()
    expect(dashboard.code).toBe('200')
    expect(dashboard.data.downloader_list).toHaveLength(3)
    expect(dashboard.data.torrents.active).toBeGreaterThan(0)

    const initialList = await getDownloaderList({}) as unknown as ApiResponse<Downloader[]>
    expect(initialList.data).toHaveLength(3)
    const firstId = initialList.data[0].id as string

    const detail = await getDetail(firstId) as unknown as ApiResponse<DownloaderDetail[]>
    expect(detail.data[0].username).toBe('demo-user')
    expect(detail.data[0].isSsl).toBe('1')

    const settings = await getDownloaderSettings(firstId) as unknown as ApiResponse<DownloaderSettingsSummary>
    expect(settings.data.downloader_id).toBe(firstId)
    const capabilities = await getDownloaderCapabilities(firstId) as unknown as ApiResponse<DownloaderCapabilitiesSummary>
    expect(capabilities.data.supports_path_mapping).toBe(true)
    const pathMappings = await getPathMappings(firstId) as unknown as ApiResponse<PathMappingSummary>
    expect(pathMappings.data.mappings).toEqual([])

    const statuses = await getStatusAll() as unknown as ApiResponse<DownloaderStatusRow[]>
    expect(statuses.data).toHaveLength(3)
    expect(statuses.data[0].connectStatus).toBe('connected')

    const created = await addDownloader({
      nickname: '临时 Demo 节点',
      host: 'local-node.example.invalid',
      port: 8080,
      username: 'demo-user',
      password: 'not-persisted'
    }) as unknown as ApiResponse<Downloader>
    expect(created.code).toBe('200')
    const createdId = created.data.downloaderId
    const afterCreate = await getDownloaderList({}) as unknown as ApiResponse<Downloader[]>
    expect(afterCreate.data.some(item => item.id === createdId)).toBe(true)

    const updatePayload = { id: createdId, nickname: '已更新 Demo 节点' }
    await upDownloader(updatePayload)
    const afterUpdate = await getDownloaderList({}) as unknown as ApiResponse<Downloader[]>
    expect(afterUpdate.data.some(item => item.nickname === '已更新 Demo 节点')).toBe(true)

    await deleteDownloader(createdId)
    const afterDelete = await getDownloaderList({}) as unknown as ApiResponse<Downloader[]>
    expect(afterDelete.data).toHaveLength(3)
  })

  it('supports torrent pause/resume and query-template application locally', async() => {
    const list = await getTorrentList({ skip: 0, limit: 2 }) as ApiResponse<TorrentListResponseData>
    expect(list.data.pageSize).toBe(2)
    expect(list.data.list).toHaveLength(2)

    const torrent: Torrent = list.data.list[0]
    await pauseTorrents({ downloader_id: torrent.downloaderId, hashes: [torrent.hash] })
    expect(demoStore.getTorrent(torrent.hash)?.status).toBe('paused')
    await resumeTorrents({ downloader_id: torrent.downloaderId, hashes: [torrent.hash] })
    expect(demoStore.getTorrent(torrent.hash)?.status).toBe('downloading')

    const templates = await getSearchTemplates({ is_public: true }) as ApiResponse<SearchTemplate[]>
    expect(templates.data.length).toBeGreaterThan(0)
    const created = await createSearchTemplate({
      name: '核心流程 Demo 模板',
      conditions: {
        source: 'simple',
        version: 1,
        listQuery: {
          name_like: '',
          category_like: '纪录片',
          tags_like: '',
          downloader_id: [],
          status: [],
          tracker_domain: [],
          showActiveOnly: false,
          sort_by: 'added_date',
          sort_order: 'desc'
        }
      }
    }) as ApiResponse<SearchTemplate>
    expect(created.data.name).toBe('核心流程 Demo 模板')
    expect((await applySearchTemplate(created.data.id)).data.conditions.source).toBe('simple')
  })

  it('keeps notification badge and read state in the local store', async() => {
    const before = await getUnreadCount()
    const page = await getNotificationList({ page: 1, pageSize: 20 })
    expect(page.data.list.length).toBeGreaterThan(0)

    const unread = page.data.list.find(item => !item.is_read)
    expect(unread).toBeDefined()
    if (!unread) return

    await markAsRead(unread.id)
    const after = await getUnreadCount()
    expect(after.data.count).toBe(before.data.count - 1)
  })
})
