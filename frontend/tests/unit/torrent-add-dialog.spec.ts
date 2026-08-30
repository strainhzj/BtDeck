import { shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'

import TorrentAddDialog from '@/views/torrents/components/TorrentAddDialog.vue'
import { addTorrentsBatch, getDownloaderPaths } from '@/api/torrents'
import { getNotificationList } from '@/api/notification'
import { getTagList } from '@/api/tag-management'

jest.mock('@/api/torrents', () => ({
  addTorrentsBatch: jest.fn(),
  getDownloaderPaths: jest.fn()
}))

jest.mock('@/api/notification', () => ({
  getNotificationList: jest.fn()
}))

jest.mock('@/api/tag-management', () => ({
  getTagList: jest.fn()
}))

async function flushPromises(): Promise<void> {
  for (let index = 0; index < 20; index += 1) {
    await Promise.resolve()
  }
}

describe('TorrentAddDialog 后台完成刷新信号', () => {
  let wrapper: Wrapper<Vue>

  beforeEach(() => {
    jest.useFakeTimers()
    jest.clearAllMocks()
    jest.mocked(getDownloaderPaths).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: { paths: [] }
    } as never)
    jest.mocked(getTagList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok',
      data: { list: [], total: 0, page: 1, pageSize: 20 }
    } as never)
  })

  afterEach(() => {
    wrapper?.destroy()
    jest.useRealTimers()
  })

  it('202 后保留 task_id，完成通知到达时发出 batch-complete', async() => {
    jest.mocked(addTorrentsBatch).mockResolvedValue({
      code: '202', status: 'accepted', msg: 'queued',
      data: { total: 1, task_id: 'task-new', status: 'queued' }
    })
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: {
        total: 1, page: 1, pageSize: 100, list: [{
          id: 1,
          type: 'system',
          title: '批量添加种子完成',
          content: 'done',
          priority: 'info',
          is_read: false,
          extra_data: {
            event: 'torrent_batch_add_completed',
            task_id: 'task-new',
            task_status: 'completed',
            operation_type: 'torrent_batch_add'
          },
          created_at: '2026-08-30T00:00:00',
          read_at: null
        }]
      }
    })

    wrapper = shallowMount(TorrentAddDialog, {
      propsData: { visible: true, downloaders: [] },
      mocks: {
        $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
      }
    })
    const vm = wrapper.vm as any
    vm.form = { downloader_id: 'dl-1', save_path: '/downloads', category: '', tags: [] }
    vm.torrentFiles = [new File(['torrent'], 'new.torrent', { type: 'application/x-bittorrent' })]

    await vm.handleConfirm()

    expect(wrapper.emitted('confirm')).toHaveLength(1)
    expect(wrapper.emitted('batch-complete')).toBeUndefined()

    jest.advanceTimersByTime(500)
    await flushPromises()

    expect(getNotificationList).toHaveBeenCalledWith({ page: 1, pageSize: 100, type: 'system' })
    expect(wrapper.emitted('batch-complete')).toEqual([[
      { task_id: 'task-new', task_status: 'completed' }
    ]])
  })

  it('组件销毁会停止后台完成轮询，避免隐藏页面残留定时器', async() => {
    jest.mocked(addTorrentsBatch).mockResolvedValue({
      code: '202', status: 'accepted', msg: 'queued',
      data: { total: 1, task_id: 'task-destroyed', status: 'queued' }
    })
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok',
      data: { total: 0, page: 1, pageSize: 100, list: [] }
    })

    wrapper = shallowMount(TorrentAddDialog, {
      propsData: { visible: true, downloaders: [] },
      mocks: {
        $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
      }
    })
    const vm = wrapper.vm as any
    vm.form = { downloader_id: 'dl-1', save_path: '/downloads', category: '', tags: [] }
    vm.torrentFiles = [new File(['torrent'], 'new.torrent', { type: 'application/x-bittorrent' })]

    await vm.handleConfirm()
    wrapper.destroy()
    jest.advanceTimersByTime(5000)
    await flushPromises()

    expect(getNotificationList).not.toHaveBeenCalled()
  })
})
