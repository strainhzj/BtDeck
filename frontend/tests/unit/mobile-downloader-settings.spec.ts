/**
 * 移动下载器设置页契约（Phase 4 M2）：整页复用桌面 DownloaderSettingsDialog
 * （visible + downloader 契约），关闭即返回 /m/downloader；未找到下载器时空态。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import MobileDownloaderSettings from '@/views/mobile/downloader-settings.vue'
import { getList } from '@/api/downloader'

jest.mock('@/api/downloader', () => ({
  getList: jest.fn()
}))

jest.mock('@/views/downloader/components/DownloaderSettingsDialog.vue', () => ({
  name: 'DownloaderSettingsDialog',
  props: ['visible', 'downloader'],
  template: '<div class="settings-dialog-stub" />'
}))

const mountPage = (id = 'd1'): Wrapper<Vue> =>
  shallowMount(MobileDownloaderSettings, {
    mocks: {
      $route: { params: { id } },
      $router: { push: jest.fn().mockResolvedValue(undefined), replace: jest.fn().mockResolvedValue(undefined) },
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileDownloaderSettings', () => {
  beforeEach(() => {
    jest.mocked(getList).mockReset()
    jest.mocked(getList).mockResolvedValue({
      code: '200',
      data: [{ id: 'd1', downloaderId: 'd1', nickname: '主力QB', host: '1.2.3.4', port: '8080' }]
    } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('按路由 id 匹配下载器并透传给设置对话框（visible=true）', async() => {
    const wrapper = mountPage('d1')
    await flushLifecycle()
    // shallowMount 会把 mock 的 dialog 组件替换为 <downloader-settings-dialog-stub>（mock template 不渲染）
    const dialog = wrapper.find('downloader-settings-dialog-stub')
    expect(dialog.exists()).toBe(true)
    const vm = wrapper.vm as any
    expect(vm.downloader).toBeTruthy()
    expect(vm.downloader.id).toBe('d1')
    expect(vm.dialogVisible).toBe(true)
  })

  it('downloaderId 兜底匹配（id 字段缺失时）', async() => {
    jest.mocked(getList).mockResolvedValue({
      code: '200',
      data: [{ downloaderId: 'dx', nickname: 'X', host: 'h', port: 'p' }]
    } as never)
    const wrapper = mountPage('dx')
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.downloader).toBeTruthy()
  })

  it('未找到下载器：空态 + 返回按钮', async() => {
    const wrapper = mountPage('missing')
    await flushLifecycle()
    expect(wrapper.text()).toContain('未找到下载器')
    const vm = wrapper.vm as any
    vm.back()
    expect(vm.$router.replace).toHaveBeenCalledWith('/m/downloader')
  })

  it('对话框 update:visible(false)：返回下载器页', async() => {
    const wrapper = mountPage('d1')
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.onDialogVisibleChange(false)
    expect(vm.$router.replace).toHaveBeenCalledWith('/m/downloader')
  })

  it('取数异常：不崩页且可返回', async() => {
    jest.mocked(getList).mockRejectedValue(new Error('db down'))
    const wrapper = mountPage('d1')
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.loadFailed).toBe(true)
    expect(wrapper.vm.$message.error).toHaveBeenCalled()
  })
})
