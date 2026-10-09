import { shallowMount, createLocalVue, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import i18n from '@/i18n'

import TorrentAddDialog from '@/views/torrents/components/TorrentAddDialog.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'
import { addTorrentsBatch, getDownloaderPaths } from '@/api/torrents'
import { getNotificationList } from '@/api/notification'
import { getTagList } from '@/api/tag-management'

// shallowMount 会 stub 已注册子组件；LucideIcon 经 localVue 注册后不再报 unknown element
const localVue = createLocalVue()
localVue.component('LucideIcon', LucideIcon)

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
      localVue,
      i18n,
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
      localVue,
      i18n,
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
      localVue,
      i18n,
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
  // 弹窗壳（overlay 顶铆/全宽/接管滚动）的 ≤768 契约随样式迁移至 BaseDialog.spec.ts
  const readSource = (): string => {
    const fs = require('fs') as typeof import('fs')
    return fs.readFileSync('src/views/torrents/components/TorrentAddDialog.vue', 'utf-8')
  }

  it('≤768 媒体块：底部双钮 44px 等宽 + 文件移除钮 36px 触控目标', () => {
    const source = readSource()
    expect(source).toContain('@media (max-width: 768px)')
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

  it('全自定义组件契约：模板零 Element 组件（el-*）与原生 select', () => {
    const source = readSource()
    // 2026-10 全自定义组件化：Element 表单控件（el-form/el-select/el-autocomplete/el-checkbox）与原生 select 全部退场
    expect(source).not.toMatch(/<el-/)
    expect(source).not.toMatch(/<\/el-/)
    expect(source).not.toContain('<select')
    // 壳与表单控件均使用自定义组件
    expect(source).toContain('<BaseDialog')
    expect(source).toContain('<FormSelect')
    expect(source).toContain('<FormAutocomplete')
    expect(source).toContain('<FormCheckbox')
  })
})

describe('TorrentAddDialog 拖拽上传与选项构建（行为）', () => {
  let wrapper: Wrapper<Vue>

  const mountDialog = (downloaders: Array<Record<string, unknown>> = []): Wrapper<Vue> =>
    shallowMount(TorrentAddDialog, {
      localVue,
      i18n,
      propsData: { visible: true, downloaders },
      mocks: {
        $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
      }
    })

  afterEach(() => {
    wrapper?.destroy()
  })

  it('拖拽释放合法 .torrent 文件：追加进文件列表并清错', () => {
    wrapper = mountDialog()
    const vm = wrapper.vm as any
    const event = {
      dataTransfer: { files: [new File(['a'], 'dragged.torrent', { type: 'application/x-bittorrent' })] }
    } as unknown as DragEvent
    vm.handleDrop(event)
    expect(vm.torrentFiles).toHaveLength(1)
    expect(vm.torrentFiles[0].name).toBe('dragged.torrent')
    expect(vm.formErrors.torrent_file).toBeUndefined()
  })

  it('拖入非 .torrent 文件：整批拒绝并提示 onlyTorrent', () => {
    wrapper = mountDialog()
    const vm = wrapper.vm as any
    const event = {
      dataTransfer: { files: [new File(['a'], 'bad.txt')] }
    } as unknown as DragEvent
    vm.handleDrop(event)
    expect(vm.torrentFiles).toHaveLength(0)
    expect(vm.formErrors.torrent_file).toBe('只能选择 .torrent 文件')
  })

  it('clearAllFiles 清空列表并回到“请选择种子文件”错误态', () => {
    wrapper = mountDialog()
    const vm = wrapper.vm as any
    vm.addFiles([new File(['a'], 'a.torrent')])
    vm.clearAllFiles()
    expect(vm.torrentFiles).toHaveLength(0)
    expect(vm.formErrors.torrent_file).toBe('请选择种子文件')
  })

  it('downloaderOptions：类型徽章与状态点机会渲染（简单 VO 缺字段则退化）', () => {
    wrapper = mountDialog([
      { downloader_id: 'dl-plain', nickname: 'Plain' },
      {
        downloader_id: 'dl-rich',
        nickname: 'Rich',
        downloader_type: 0,
        connectStatus: 'connected'
      },
      {
        downloader_id: 'dl-off',
        nickname: 'Off',
        type: 1,
        status: '0'
      }
    ])
    const vm = wrapper.vm as any
    expect(vm.downloaderOptions).toEqual([
      { value: 'dl-plain', label: 'Plain', badge: undefined, status: undefined },
      { value: 'dl-rich', label: 'Rich', badge: 'qB', status: 'online' },
      { value: 'dl-off', label: 'Off', badge: 'TR', status: 'offline' }
    ])
  })

  it('pathSuggestions：仅启用路径，且按当前输入大小写不敏感过滤', () => {
    wrapper = mountDialog()
    const vm = wrapper.vm as any
    vm.downloaderPaths = [
      { id: 1, downloader_id: 1, path_type: 'default', path_value: '/data/movies', is_enabled: true, torrent_count: 5, last_updated_time: '' },
      { id: 2, downloader_id: 1, path_type: 'active', path_value: '/data/TV', is_enabled: true, torrent_count: 2, last_updated_time: '' },
      { id: 3, downloader_id: 1, path_type: 'active', path_value: '/disabled', is_enabled: false, torrent_count: 0, last_updated_time: '' }
    ]
    vm.form.save_path = '/data/mo'
    expect(vm.pathSuggestions).toEqual([
      { value: '/data/movies', path_type: 'default', torrent_count: 5 }
    ])
    // 空输入 = 全部启用路径（便于浏览既有路径）
    vm.form.save_path = ''
    expect(vm.pathSuggestions).toHaveLength(2)
  })
})
