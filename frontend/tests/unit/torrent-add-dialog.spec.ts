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

describe('TorrentAddDialog 跳过校验（CheckingDL 规避）', () => {
  let wrapper: Wrapper<Vue>

  const mountDialog = (): Wrapper<Vue> =>
    shallowMount(TorrentAddDialog, {
      propsData: { visible: true, downloaders: [] },
      mocks: {
        $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
      }
    })

  const fillAndSubmit = async(vm: any, skip: boolean): Promise<void> => {
    vm.form = { downloader_id: 'dl-1', save_path: '/downloads', category: '', tags: [], skip_hash_check: skip }
    vm.torrentFiles = [new File(['torrent'], 'new.torrent', { type: 'application/x-bittorrent' })]
    await vm.handleConfirm()
  }

  beforeEach(() => {
    jest.clearAllMocks()
    jest.mocked(getDownloaderPaths).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: { paths: [] }
    } as never)
    jest.mocked(getTagList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok',
      data: { list: [], total: 0, page: 1, pageSize: 20 }
    } as never)
    jest.mocked(addTorrentsBatch).mockResolvedValue({
      code: '202', status: 'accepted', msg: 'queued',
      data: { total: 1, task_id: 'task-x', status: 'queued' }
    })
    jest.mocked(getNotificationList).mockResolvedValue({
      code: '200', status: 'success', msg: 'ok', data: { total: 0, page: 1, pageSize: 100, list: [] }
    })
  })

  afterEach(() => {
    wrapper?.destroy()
  })

  it('默认不跳过校验：skip_hash_check=false 透传批量添加（安全默认）', async() => {
    wrapper = mountDialog()
    await fillAndSubmit(wrapper.vm as any, false)
    expect(addTorrentsBatch).toHaveBeenCalledWith(expect.objectContaining({ skip_hash_check: false }))
  })

  it('勾选跳过校验：skip_hash_check=true 透传（数据已完整直接做种，规避 CheckingDL）', async() => {
    wrapper = mountDialog()
    await fillAndSubmit(wrapper.vm as any, true)
    expect(addTorrentsBatch).toHaveBeenCalledWith(expect.objectContaining({ skip_hash_check: true }))
  })

  it('关闭弹窗重置 skip_hash_check 回安全默认（下次打开不残留勾选）', async() => {
    wrapper = mountDialog()
    const vm = wrapper.vm as any
    await fillAndSubmit(vm, true)
    // 202 分支确认后自动 handleClose 重置表单
    expect(vm.form.skip_hash_check).toBe(false)
  })
})

describe('TorrentAddDialog 移动端适配与跳过校验（源码契约）', () => {
  // jsdom 不应用媒体查询：布局保护走源码契约（本仓既有模式），视觉由真机/模拟器兜底
  const readSource = (): string => {
    const fs = require('fs') as typeof import('fs')
    return fs.readFileSync('src/views/torrents/components/TorrentAddDialog.vue', 'utf-8')
  }

  it('≤768 媒体块：顶铆全宽弹窗（!important 压制内联 600px）+ 底部双钮 44px 等宽', () => {
    const source = readSource()
    expect(source).toContain('@media (max-width: 768px)')
    // 根元素带内联 max-width:600px，非 !important 压不下去
    expect(source).toContain('max-width: calc(100vw - 24px) !important')
    expect(source).toContain('align-items: flex-start')
    // overlay 接管滚动（弹窗自身 85vh 上限让位）
    expect(source).toMatch(/\.modal-overlay\.active\s*{[^}]*overflow-y: auto/s)
    // 触控目标：底部按钮 ≥44px 等宽、文件移除钮放大
    expect(source).toContain('min-height: 44px')
    expect(source).toContain('min-width: 36px')
  })

  it('跳过校验为表单复选框（默认关）而非硬编码，安全默认禁回流', () => {
    const source = readSource()
    expect(source).toContain('v-model="form.skip_hash_check"')
    expect(source).toContain('skip_hash_check: formSnapshot.skip_hash_check')
    // 旧硬编码提交（CheckingDL 根因）不得回流：快照默认值与关闭重置值除外
    expect(source.match(/skip_hash_check: false/g)?.length).toBe(2)
    expect(source).not.toContain('skip_hash_check: false,')
  })
})
