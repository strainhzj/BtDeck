/**
 * 详情明细 API 契约回归（TrackerDetailCard 文件/Peers 页签）：
 * 与后端 torrent_detail.py 端点（GET /torrents/detail/{hash}/files|peers，
 * query 携带 downloader_id）锁定同一路径与参数命名，防任一侧漂移——
 * 后端侧契约由 backend/tests/api/test_torrent_detail_endpoint.py 锁定
 * （含路由注册与信封格式），本文件锁前端请求侧的镜像契约。
 */
import request from '@/utils/request'

jest.mock('@/utils/request', () => ({
  __esModule: true,
  default: jest.fn(() =>
    Promise.resolve({ status: 'success', msg: '获取成功', code: '200', data: null })
  )
}))

import { getTorrentFiles, getTorrentPeers } from '@/api/torrents'

const mockedRequest = request as unknown as jest.Mock

describe('详情明细 API 契约（/torrents/detail/{hash}/files|peers）', () => {
  afterEach(() => {
    mockedRequest.mockClear()
  })

  it('getTorrentFiles 请求 files 路径，query 携带 downloader_id', async() => {
    await getTorrentFiles('abc123def', 'dl-9')
    expect(mockedRequest).toHaveBeenCalledTimes(1)
    expect(mockedRequest).toHaveBeenCalledWith({
      url: '/torrents/detail/abc123def/files',
      method: 'get',
      params: { downloader_id: 'dl-9' }
    })
  })

  it('getTorrentPeers 请求 peers 路径，query 携带 downloader_id', async() => {
    await getTorrentPeers('abc123def', 'dl-9')
    expect(mockedRequest).toHaveBeenCalledTimes(1)
    expect(mockedRequest).toHaveBeenCalledWith({
      url: '/torrents/detail/abc123def/peers',
      method: 'get',
      params: { downloader_id: 'dl-9' }
    })
  })
})
