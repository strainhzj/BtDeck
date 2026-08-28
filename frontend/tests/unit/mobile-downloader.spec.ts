/**
 * 移动下载器页契约（Phase 4 M2 升级为完整管理）：
 * 复用桌面 /downloader 全套 API——监控（在线徽标/测试/同步）+ 新增/编辑
 * （DownloaderDialog 复用，submit 由本页显式调 add/up 落库）+ 删除 + 设置跳转。
 * 注：shallowMount 下 el-button 为 kebab stub 不转发 click——交互直调组件方法。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import fs from 'fs'
import path from 'path'
import MobileDownloader from '@/views/mobile/downloader.vue'
import {
  getList,
  testConnection,
  syncDownloader,
  addDownloader,
  upDownloader,
  deleteDownloader
} from '@/api/downloader'

jest.mock('@/api/downloader', () => ({
  getList: jest.fn(),
  testConnection: jest.fn(),
  syncDownloader: jest.fn(),
  addDownloader: jest.fn(),
  upDownloader: jest.fn(),
  deleteDownloader: jest.fn()
}))

jest.mock('@/views/downloader/components/DownloaderDialog.vue', () => ({
  name: 'DownloaderDialog',
  render: (h: (t: string) => unknown) => h('div')
}))

const mockedList = [
  {
    id: 'd1',
    nickname: '主力QB',
    host: '192.168.5.51',
    port: '8080',
    downloaderType: 0,
    downloaderTypeName: 'qbittorrent',
    connectStatus: '1'
  },
  {
    id: 'd2',
    nickname: 'TR辅种',
    host: '192.168.5.52',
    port: '9091',
    downloaderType: 1,
    downloaderTypeName: 'transmission',
    connectStatus: '0'
  }
]

const mountPage = (query: Record<string, string> = {}): Wrapper<Vue> =>
  shallowMount(MobileDownloader, {
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
      $confirm: jest.fn().mockResolvedValue('confirm'),
      $router: { push: jest.fn().mockResolvedValue(undefined), replace: jest.fn().mockResolvedValue(undefined) },
      $route: { query }
    }
  })

/** 排空 mounted 异步链（load 的 await + 渲染 tick） */
async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileDownloader（M2 管理版）', () => {
  beforeEach(() => {
    jest.mocked(getList).mockReset()
    jest.mocked(getList).mockResolvedValue({ code: '200', data: mockedList } as never)
    jest.mocked(testConnection).mockReset()
    jest.mocked(syncDownloader).mockReset()
    jest.mocked(addDownloader).mockReset()
    jest.mocked(upDownloader).mockReset()
    jest.mocked(deleteDownloader).mockReset()
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('列表渲染：卡片含名称/在线离线徽标/host，工具条显示计数', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('主力QB')
    expect(wrapper.text()).toContain('在线')
    expect(wrapper.text()).toContain('离线')
    expect(wrapper.text()).toContain('192.168.5.51:8080')
    expect(wrapper.text()).toContain('共 2 个下载器')
  })

  it('空列表显示空态', async() => {
    jest.mocked(getList).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('暂无下载器')
  })

  it('接口异常：错误提示不崩页', async() => {
    jest.mocked(getList).mockRejectedValue(new Error('db down'))
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.vm.$message.error).toHaveBeenCalled()
  })

  it('测试连接成功后刷新列表，失败不刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    // 后端约定：连接失败时信封 code 仍为 200，业务成败看 data.success（与桌面端一致）
    jest.mocked(testConnection).mockResolvedValue({
      code: '200',
      data: { success: true, delay: 5, message: '连接成功' }
    } as never)
    await vm.testOne(vm.list[0])
    expect(testConnection).toHaveBeenCalledWith('d1')
    expect(getList).toHaveBeenCalledTimes(2)
    jest.mocked(testConnection).mockResolvedValue({
      code: '200',
      data: { success: false, delay: null, message: '连接失败' }
    } as never)
    const before = jest.mocked(getList).mock.calls.length
    await vm.testOne(vm.list[0])
    expect(jest.mocked(getList).mock.calls.length).toBe(before)
    expect(wrapper.vm.$message.error).toHaveBeenCalled()
  })

  it('同步：调 syncDownloader 并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(syncDownloader).mockResolvedValue({ code: '200' } as never)
    await vm.syncOne(vm.list[0])
    expect(syncDownloader).toHaveBeenCalledWith('d1')
    expect(wrapper.vm.$message.success).toHaveBeenCalled()
  })

  it('设置：跳转移动设置页（携带 id）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.openSettings(vm.list[0])
    expect(vm.$router.push).toHaveBeenCalledWith('/m/downloader/settings/d1')
  })

  it('新增：submit 显式调 addDownloader 并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.openCreate()
    expect(vm.editingItem).toBeNull()
    jest.mocked(addDownloader).mockResolvedValue({ code: '200' } as never)
    await vm.onDialogSubmit({ nickname: '新下载器', host: '1.2.3.4' })
    expect(addDownloader).toHaveBeenCalledWith({ nickname: '新下载器', host: '1.2.3.4' })
    expect(vm.editDialogVisible).toBe(false)
  })

  it('编辑：submit 显式调 upDownloader（以原 id 落库）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.openEdit(vm.list[1])
    expect(vm.editingItem).not.toBeNull()
    jest.mocked(upDownloader).mockResolvedValue({ code: '200' } as never)
    await vm.onDialogSubmit({ nickname: '改名' })
    expect(upDownloader).toHaveBeenCalledWith(expect.objectContaining({ id: 'd2', nickname: '改名' }))
  })

  it('删除：确认后调 deleteDownloader 并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(deleteDownloader).mockResolvedValue({ code: '200' } as never)
    await vm.removeOne(vm.list[0])
    await flushLifecycle()
    expect(deleteDownloader).toHaveBeenCalledWith('d1')
    expect(wrapper.vm.$message.success).toHaveBeenCalled()
  })

  it('在线徽标与页面沿用主题色变量（与桌面端同源）', () => {
    const source = fs.readFileSync(
      path.resolve(__dirname, '../../src/views/mobile/downloader.vue'),
      'utf-8'
    )
    expect(source).toContain('.m-dl-badge.is-online')
    expect(source).toContain('var(--color-primary)')
    expect(source).not.toContain('#409eff')
  })

  it('?create=1 直达新增：挂载即弹新增弹窗（种子页空态 CTA 落点）', async() => {
    const wrapper = mountPage({ create: '1' })
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.editDialogVisible).toBe(true)
    expect(vm.editingItem).toBeNull()
    wrapper.destroy()
  })
})
