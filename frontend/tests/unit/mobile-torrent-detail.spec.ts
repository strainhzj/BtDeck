/**
 * 移动种子详情页契约（dual-mode-client Phase 4 M1 余项）：
 * - 数据源：列表快照缓存立即渲染（含 Tracker 数/速度），getList 回查刷新基础字段；
 * - 无缓存/回查未命中：走 getList 兜底，仍无则「未找到」空态 + 返回列表；
 * - 活动速度轮询（getActiveTorrents）按 hash 覆盖进度/速度/做种连接数；
 * - 操作：暂停/恢复/删除（入回收站）复用现有 API，删除成功回列表。
 * 注：shallowMount 下 el-button 为 kebab stub 不转发 click，按钮交互直调组件方法。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import { Torrent } from '@/api/torrents'
import MobileTorrentDetail from '@/views/mobile/torrent-detail.vue'
import { takeCachedTorrent } from '@/views/mobile/torrent-detail-cache'
import {
  getTorrentList,
  getActiveTorrents,
  pauseTorrents,
  resumeTorrents,
  deleteTorrents
} from '@/api/torrents'

jest.mock('@/api/torrents', () => ({
  getTorrentList: jest.fn().mockResolvedValue({ code: '200', data: { list: [], total: 0 } }),
  getActiveTorrents: jest.fn().mockResolvedValue({ code: '200', data: [] }),
  pauseTorrents: jest.fn().mockResolvedValue({ code: '200' }),
  resumeTorrents: jest.fn().mockResolvedValue({ code: '200' }),
  deleteTorrents: jest.fn().mockResolvedValue({ code: '200' })
}))

jest.mock('@/views/mobile/torrent-detail-cache', () => ({
  takeCachedTorrent: jest.fn().mockReturnValue(null),
  setCachedTorrent: jest.fn()
}))

const flushPromises = (): Promise<void> => new Promise((resolve) => { setTimeout(resolve, 0) })

const baseTorrent: Torrent = {
  infoId: 'i1',
  downloaderId: 'd1',
  downloaderName: '测试下载器',
  torrentId: 't1',
  hash: 'abc123',
  name: '移动端测试种子',
  savePath: '/data/downloads/test',
  size: 1073741824,
  status: 'downloading',
  torrentFile: '/data/torrents/test.torrent',
  addedDate: '2026-08-20T10:00:00',
  completedDate: null,
  ratio: 1.5,
  ratioLimit: null,
  tags: '',
  category: '',
  superSeeding: false,
  enabled: true,
  trackerInfo: [
    { trackerName: 'TrackerA', trackerUrl: 'http://a.example/announce', lastAnnounceSucceeded: 'true' },
    { trackerName: 'TrackerB', trackerUrl: 'http://b.example/announce', lastAnnounceSucceeded: 'false' }
  ],
  progress: 42.5,
  downloadSpeed: 102400,
  uploadSpeed: 2048,
  seeds: 3,
  peers: 5
}

const mountDetail = (): Wrapper<Vue> =>
  shallowMount(MobileTorrentDetail, {
    mocks: {
      $route: { path: '/m/torrents/detail/d1/abc123', params: { downloaderId: 'd1', hash: 'abc123' } },
      $router: {
        replace: jest.fn().mockResolvedValue(undefined),
        push: jest.fn().mockResolvedValue(undefined)
      },
      $confirm: jest.fn().mockResolvedValue('confirm'),
      $message: { success: jest.fn(), error: jest.fn() }
    }
  })

describe('views/mobile/torrent-detail', () => {
  let wrapper: Wrapper<Vue> | null = null
  const vm = (): any => (wrapper as Wrapper<Vue>).vm

  const destroyWrapper = (): void => {
    if (wrapper) {
      wrapper.destroy()
      wrapper = null
    }
  }

  afterEach(() => {
    destroyWrapper()
    jest.clearAllMocks()
    jest.mocked(takeCachedTorrent).mockReturnValue(null)
    jest.mocked(getTorrentList).mockResolvedValue({ code: '200', data: { list: [], total: 0 } } as never)
  })

  it('快照命中：立即渲染名称/状态/进度/速度/Tracker 数', async() => {
    jest.mocked(takeCachedTorrent).mockReturnValue(baseTorrent)
    wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.find('.m-detail-name').text()).toBe('移动端测试种子')
    expect(wrapper.text()).toContain('下载中')
    expect(wrapper.find('.m-detail-progress-text').text()).toContain('42.5')
    expect(wrapper.find('.m-detail-speed').text()).toContain('100.00 MB/s')
    expect(wrapper.find('.m-tracker-toggle').text()).toContain('Tracker 明细（2）')
  })

  it('无缓存：getList 回查命中后渲染', async() => {
    jest.mocked(takeCachedTorrent).mockReturnValue(null)
    jest.mocked(getTorrentList).mockResolvedValue({
      code: '200',
      data: { list: [baseTorrent], total: 1 }
    } as never)
    wrapper = mountDetail()
    await flushPromises()
    expect(jest.mocked(getTorrentList)).toHaveBeenCalledWith(
      expect.objectContaining({ downloader_id: 'd1', limit: 100 })
    )
    expect(wrapper.find('.m-detail-name').text()).toBe('移动端测试种子')
  })

  it('无缓存且回查未命中：未找到空态，返回列表走 replace', async() => {
    jest.mocked(takeCachedTorrent).mockReturnValue(null)
    jest.mocked(getTorrentList).mockResolvedValue({
      code: '200',
      data: { list: [], total: 0 }
    } as never)
    wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.find('.m-detail-empty').exists()).toBe(true)
    vm().backToList()
    expect(vm().$router.replace).toHaveBeenCalledWith('/m/torrents')
  })

  it('活动速度轮询：按 hash 匹配覆盖进度/速度/做种连接数', async() => {
    jest.mocked(takeCachedTorrent).mockReturnValue(baseTorrent)
    wrapper = mountDetail()
    await flushPromises()
    jest.mocked(getActiveTorrents).mockResolvedValue({
      code: '200',
      data: [
        { hash: 'other', downloadSpeed: 9, uploadSpeed: 9, progress: 1, num_seeds: 0, num_leechs: 0 },
        { hash: 'abc123', downloadSpeed: 1, uploadSpeed: 2, progress: 99, num_seeds: 7, num_leechs: 8 }
      ]
    } as never)
    await vm().pollActive()
    expect(wrapper.find('.m-detail-progress-text').text()).toContain('99.0')
    expect(wrapper.text()).toContain('7 / 8')
    expect(wrapper.find('.m-detail-speed').text()).toContain('1 KB/s')
  })

  it('暂停/恢复：携带复合键调用现有 API 并刷新', async() => {
    jest.mocked(takeCachedTorrent).mockReturnValue(baseTorrent)
    wrapper = mountDetail()
    await flushPromises()
    await vm().pause()
    expect(jest.mocked(pauseTorrents)).toHaveBeenCalledWith({ downloader_id: 'd1', hashes: ['abc123'] })
    await vm().resume()
    expect(jest.mocked(resumeTorrents)).toHaveBeenCalledWith({ downloader_id: 'd1', hashes: ['abc123'] })
  })

  it('删除：确认后入回收站并返回列表', async() => {
    jest.mocked(takeCachedTorrent).mockReturnValue(baseTorrent)
    wrapper = mountDetail()
    await flushPromises()
    await vm().remove()
    await flushPromises()
    expect(jest.mocked(deleteTorrents)).toHaveBeenCalledWith({
      info_id: 'i1',
      downloader_id: 'd1',
      delete_data: 0,
      id_recycle: 1
    })
    expect(vm().$router.replace).toHaveBeenCalledWith('/m/torrents')
  })

  it('轮询迁移 SpeedPollingMixin：立即首拉一次 + 5s 间隔 + 底部冗余返回排已移除', async() => {
    jest.mocked(takeCachedTorrent).mockReturnValue(baseTorrent)
    jest.mocked(getActiveTorrents).mockClear()
    wrapper = mountDetail()
    await flushPromises()
    // mounted 立即首拉一次；mixin immediate=false 不双发（真 timer 下 5s 周期不触发）
    expect(jest.mocked(getActiveTorrents)).toHaveBeenCalledTimes(1)
    expect(vm().speedPollIntervalMs).toBe(5000)
    expect(vm().pollTimer).toBeUndefined()
    // 底部操作区只剩 暂停/恢复/删除，冗余"返回列表"排由 header ← 返回承载
    const actions = wrapper.findAll('.m-detail-actions')
    expect(actions).toHaveLength(1)
    expect(actions.at(0).text()).not.toContain('返回列表')
  })
})
