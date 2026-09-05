import { demoStore } from '@/demo/demo-store'

describe('demo store', () => {
  beforeEach(() => {
    demoStore.reset()
  })

  it('filters and paginates torrents with the project pagination contract', () => {
    const response = demoStore.listTorrents({
      page: 1,
      pageSize: 2,
      status: 'downloading'
    })

    expect(response.pageSize).toBe(2)
    expect(response.list).toHaveLength(2)
    expect(response.total).toBe(2)
    expect(response.list.every(item => item.status === 'downloading')).toBe(true)
  })

  it('updates torrent state and restores the fixture on reset', () => {
    const original = demoStore.snapshot().torrents[0]
    expect(original).toBeDefined()

    const changed = demoStore.updateTorrentState([original.hash], 'paused')
    expect(changed[0].status).toBe('paused')
    expect(demoStore.getTorrent(original.hash)?.downloadSpeed).toBe(0)

    demoStore.reset()
    expect(demoStore.getTorrent(original.hash)?.status).toBe(original.status)
    expect(demoStore.getTorrent(original.hash)?.downloadSpeed).toBe(original.downloadSpeed)
  })

  it('keeps template and notification mutations local to the store', () => {
    const beforeTemplates = demoStore.listTemplates().length
    const created = demoStore.createTemplate({ name: '本地演示模板' })
    expect(demoStore.listTemplates()).toHaveLength(beforeTemplates + 1)
    expect(demoStore.applyTemplate(created.id)?.usage_count).toBe(1)
    expect(demoStore.deleteTemplate(created.id)).toBe(true)

    const unreadBefore = demoStore.getUnreadNotificationCount()
    const notification = demoStore.getNotifications({ page: 1, pageSize: 1 }).list[0]
    demoStore.markNotification(notification.id, true)
    expect(demoStore.getUnreadNotificationCount()).toBe(unreadBefore - 1)
    demoStore.reset()
    expect(demoStore.getUnreadNotificationCount()).toBe(unreadBefore)
  })
})
