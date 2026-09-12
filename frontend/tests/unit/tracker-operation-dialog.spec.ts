/**
 * TrackerOperationDialog 契约：
 * - 常规模式（selectedTorrents）：按种子列表提交 addTracker/modifyTracker
 *   （desktop index.vue 批量入口的行为锚，scopeDownloader 分支不得影响该路径）；
 * - 按下载器触发模式（scopeDownloader，2026-09-12 移动端引入）：
 *   范围行/标题/按钮文案切换 + 提交走 by-downloader 端点（服务端解析种子范围），
 *   成功提示带成功/失败计数。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import TrackerOperationDialog from '@/views/torrents/components/TrackerOperationDialog.vue'
import {
  addTracker,
  modifyTracker,
  addTrackerByDownloader,
  modifyTrackerByDownloader
} from '@/api/torrents'
import type { Torrent } from '@/api/torrents'

jest.mock('@/api/torrents', () => ({
  addTracker: jest.fn(),
  modifyTracker: jest.fn(),
  addTrackerByDownloader: jest.fn(),
  modifyTrackerByDownloader: jest.fn()
}))

jest.mock('@/views/torrents/utils/torrentBatch', () => ({
  isTrackerAnnounceSuccess: jest.fn(() => true)
}))

const singleTorrent = {
  infoId: 'i1',
  info_id: 'i1',
  hash: 'abc',
  name: '单种',
  downloaderId: 'd1'
} as Torrent

const mountDialog = (propsData: Record<string, unknown>): Wrapper<Vue> =>
  shallowMount(TrackerOperationDialog, {
    propsData,
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
    }
  })

describe('views/torrents/components/TrackerOperationDialog', () => {
  beforeEach(() => {
    jest.mocked(addTracker).mockReset()
    jest.mocked(addTracker).mockResolvedValue({ code: '200', data: null } as never)
    jest.mocked(modifyTracker).mockReset()
    jest.mocked(modifyTracker).mockResolvedValue({ code: '200', data: null } as never)
    jest.mocked(addTrackerByDownloader).mockReset()
    jest.mocked(addTrackerByDownloader).mockResolvedValue({
      code: '200', data: { success_count: 8, failed_count: 0 }
    } as never)
    jest.mocked(modifyTrackerByDownloader).mockReset()
    jest.mocked(modifyTrackerByDownloader).mockResolvedValue({
      code: '200', data: { success_count: 5, failed_count: 2 }
    } as never)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  /** 绕过 el-form ref（shallow stub 无 validate）：直写表单模型 + 注入带 validate 的桩后调提交体 */
  const callPrivateSubmit = async(
    vm: any,
    method: 'handleAddSubmit' | 'handleModifySubmit',
    trackers: string
  ): Promise<void> => {
    const formKey = method === 'handleAddSubmit' ? 'addForm' : 'modifyForm'
    vm[formKey].trackers = trackers
    vm.$refs[formKey] = { validate: jest.fn().mockResolvedValue(undefined) }
    await vm[method]()
  }

  describe('常规模式（selectedTorrents，桌面行为不变）', () => {
    it('单种提交 addTracker 走种子 ID（scopeDownloader 分支不得劫持）', async() => {
      const wrapper = mountDialog({ visible: true, selectedTorrents: [singleTorrent], operationType: '' })
      await Vue.nextTick()
      await callPrivateSubmit(wrapper.vm as any, 'handleAddSubmit', 'https://t.example.com/announce')
      expect(addTracker).toHaveBeenCalledWith({
        torrentInfoIds: 'i1',
        trackers: 'https://t.example.com/announce'
      })
      expect(addTrackerByDownloader).not.toHaveBeenCalled()
      wrapper.destroy()
    })

    it('批量标题与提交按钮沿用种子计数口径', async() => {
      const two = [singleTorrent, { ...singleTorrent, infoId: 'i2', info_id: 'i2', hash: 'h2' } as Torrent]
      const wrapper = mountDialog({ visible: true, selectedTorrents: two, operationType: '' })
      await Vue.nextTick()
      const vm = wrapper.vm as any
      expect(vm.dialogTitle).toBe('批量Tracker操作 - 已选2个种子')
      expect(vm.addSubmitLabel).toBe('批量添加 (2个种子)')
      expect(vm.scoped).toBe(false)
      wrapper.destroy()
    })
  })

  describe('按下载器触发模式（scopeDownloader）', () => {
    const scope = { id: 'dl-9', name: '远端QB', total: 3200 }

    const mountScoped = (): Wrapper<Vue> =>
      mountDialog({ visible: true, selectedTorrents: [], operationType: '', scopeDownloader: scope })

    it('范围行/标题/按钮文案切换为按下载器口径（含总数）', async() => {
      const wrapper = mountScoped()
      await Vue.nextTick()
      const vm = wrapper.vm as any
      expect(vm.scoped).toBe(true)
      expect(vm.dialogTitle).toBe('Tracker操作（按下载器） - 远端QB')
      expect(vm.scopeLabel).toBe('下载器「远端QB」全部种子')
      expect(vm.scopeTotalSuffix).toBe('（共 3200 个）')
      expect(vm.addSubmitLabel).toBe('添加到该下载器全部种子')
      expect(vm.modifySubmitLabel).toBe('替换该下载器全部种子Tracker')
      expect(wrapper.text()).toContain('下载器「远端QB」全部种子（共 3200 个）')
      wrapper.destroy()
    })

    it('total 未提供时范围行省略计数', async() => {
      const wrapper = mountDialog({
        visible: true, selectedTorrents: [], operationType: '',
        scopeDownloader: { id: 'dl-9', name: '远端QB' }
      })
      await Vue.nextTick()
      const vm = wrapper.vm as any
      expect(vm.scopeTotalSuffix).toBe('')
      wrapper.destroy()
    })

    it('添加提交走 addTrackerByDownloader（不传种子列表）', async() => {
      const wrapper = mountScoped()
      await Vue.nextTick()
      await callPrivateSubmit(wrapper.vm as any, 'handleAddSubmit', 'https://a.example/announce;https://b.example/announce')
      expect(addTrackerByDownloader).toHaveBeenCalledWith({
        downloader_id: 'dl-9',
        trackers: 'https://a.example/announce;https://b.example/announce'
      })
      expect(addTracker).not.toHaveBeenCalled()
      expect(wrapper.vm.$message.success).toHaveBeenCalledWith('添加Tracker成功（成功 8）')
      wrapper.destroy()
    })

    it('修改提交走 modifyTrackerByDownloader，计数含失败', async() => {
      const wrapper = mountScoped()
      await Vue.nextTick()
      await callPrivateSubmit(wrapper.vm as any, 'handleModifySubmit', 'https://new.example/announce')
      expect(modifyTrackerByDownloader).toHaveBeenCalledWith({
        downloader_id: 'dl-9',
        trackers: 'https://new.example/announce'
      })
      expect(modifyTracker).not.toHaveBeenCalled()
      expect(wrapper.vm.$message.success).toHaveBeenCalledWith('修改Tracker成功（成功 5，失败 2）')
      wrapper.destroy()
    })

    it('by-downloader 信封非 200：错误提示且不 emit success', async() => {
      jest.mocked(addTrackerByDownloader).mockResolvedValue({ code: '500', msg: '下载器不存在' } as never)
      const wrapper = mountScoped()
      await Vue.nextTick()
      await callPrivateSubmit(wrapper.vm as any, 'handleAddSubmit', 'https://t.example.com/announce')
      expect(wrapper.vm.$message.error).toHaveBeenCalledWith('下载器不存在')
      expect(wrapper.emitted('success')).toBeUndefined()
      wrapper.destroy()
    })
  })
})
