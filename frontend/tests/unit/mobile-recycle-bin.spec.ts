/**
 * 移动回收站契约（Phase 4 M2）：卡片列表 + 单条恢复/彻底删除；
 * 批量与手动恢复保留桌面版。交互直调组件方法（el-button stub 不转发 click）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileRecycleBin from '@/views/mobile/recycle-bin.vue'
import { getRecycleBinList, restoreTorrents, manualCleanup } from '@/api/recycle-bin'

jest.mock('@/api/recycle-bin', () => ({
  getRecycleBinList: jest.fn(),
  restoreTorrents: jest.fn(),
  manualCleanup: jest.fn()
}))

const mockedItems = [
  {
    info_id: 'i1',
    name: '已删种子A',
    size: 1073741824,
    save_path: '/downloads/a',
    deleted_at: '2026-08-20T10:00:00',
    downloader_name: 'qb',
    torrent_id: 't1'
  },
  {
    info_id: 'i2',
    name: '无记录种子B',
    size: 52428800,
    save_path: '/downloads/b',
    deleted_at: '2026-08-21T11:00:00',
    downloader_name: 'tr',
    torrent_id: undefined
  }
]

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileRecycleBin, {
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
      $confirm: jest.fn().mockResolvedValue('confirm')
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileRecycleBin', () => {
  beforeEach(() => {
    jest.mocked(getRecycleBinList).mockReset()
    jest.mocked(getRecycleBinList).mockResolvedValue({
      code: '200',
      data: { total: 2, page: 1, pageSize: 20, list: mockedItems }
    } as never)
    jest.mocked(restoreTorrents).mockReset()
    jest.mocked(manualCleanup).mockReset()
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('列表渲染：名称/大小/路径/删除时间/下载器', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('已删种子A')
    expect(wrapper.text()).toContain('1.0 GB')
    expect(wrapper.text()).toContain('/downloads/a')
    expect(wrapper.text()).toContain('2026-08-20 10:00')
    expect(wrapper.text()).toContain('qb')
  })

  it('空列表显示空态', async() => {
    jest.mocked(getRecycleBinList).mockResolvedValue({
      code: '200',
      data: { total: 0, page: 1, pageSize: 20, list: [] }
    } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('回收站为空')
  })

  it('搜索词作为 search 参数提交', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.search = '关键词'
    await vm.reload()
    expect(getRecycleBinList).toHaveBeenLastCalledWith(expect.objectContaining({ search: '关键词' }))
  })

  it('恢复：携带 torrent_ids 单条恢复并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(restoreTorrents).mockResolvedValue({
      code: '200',
      data: { success_count: 1, failed_count: 0, skipped_count: 0, success_list: [], failed_list: [] }
    } as never)
    await vm.restore(vm.list[0])
    expect(restoreTorrents).toHaveBeenCalledWith({ torrent_ids: ['t1'] })
    expect(wrapper.vm.$message.success).toHaveBeenCalled()
  })

  it('恢复部分失败：给出警告提示', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(restoreTorrents).mockResolvedValue({
      code: '200',
      data: { success_count: 0, failed_count: 1, skipped_count: 0, success_list: [], failed_list: [] }
    } as never)
    await vm.restore(vm.list[0])
    expect(wrapper.vm.$message.warning).toHaveBeenCalled()
  })

  it('无 torrent_id 的记录：恢复/删除方法直接返回（按钮禁用语义）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    await vm.restore(vm.list[1])
    vm.destroy(vm.list[1])
    expect(restoreTorrents).not.toHaveBeenCalled()
    expect(manualCleanup).not.toHaveBeenCalled()
  })

  it('彻底删除：确认后调 manualCleanup 并刷新', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(manualCleanup).mockResolvedValue({
      code: '200',
      data: { success_count: 1, failed_count: 0, success_list: [], failed_list: [] }
    } as never)
    await vm.destroy(vm.list[0])
    await flushLifecycle()
    expect(manualCleanup).toHaveBeenCalledWith({ torrent_ids: ['t1'] })
    expect(wrapper.vm.$message.success).toHaveBeenCalled()
  })
})
