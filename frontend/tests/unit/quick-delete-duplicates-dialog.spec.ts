import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'
import fs from 'fs'
import path from 'path'

import QuickDeleteDuplicatesDialog from '@/components/torrents/QuickDeleteDuplicatesDialog.vue'
import {
  getBatchDeleteStatus,
  getDownloaderList,
  getQuickDeleteDuplicatePreview,
  quickDeleteDuplicates
} from '@/api/torrents'
import type { QuickDeletePreviewResponse } from '@/api/torrents'

jest.mock('@/api/torrents', () => ({
  getDownloaderList: jest.fn(),
  getQuickDeleteDuplicatePreview: jest.fn(),
  quickDeleteDuplicates: jest.fn(),
  getBatchDeleteStatus: jest.fn()
}))

const localVue = createLocalVue()
const mockGetDownloaderList = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
const mockQuickDeleteDuplicates = quickDeleteDuplicates as jest.MockedFunction<typeof quickDeleteDuplicates>

interface QuickDeleteDialogVm extends Vue {
  preview: QuickDeletePreviewResponse | null
  detectDownloaderIds: Array<string | number>
  keepDownloaderIds: Array<string | number>
  handleDelete(): Promise<void>
  pollDeleteStatus(taskId: string): Promise<void>
}

const message = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
  info: jest.fn()
}

const preview: QuickDeletePreviewResponse = {
  total: 1,
  page: 1,
  pageSize: 20,
  total_groups: 1,
  total_delete: 1,
  skipped_groups: 0,
  list: []
}

const mockGetQuickDeleteDuplicatePreview = getQuickDeleteDuplicatePreview as jest.MockedFunction<typeof getQuickDeleteDuplicatePreview>

/** 等待选择完成自动预览的防抖（250ms）落地 */
const waitAutoPreview = async(): Promise<void> => {
  await Vue.nextTick()
  await new Promise(resolve => setTimeout(resolve, 400))
}

function mountDialog(): Wrapper<Vue> {
  return shallowMount(QuickDeleteDuplicatesDialog, {
    localVue,
    propsData: { visible: false },
    mocks: { $message: message }
  })
}

describe('QuickDeleteDuplicatesDialog in-flight deletion handling', () => {
  let wrapper: Wrapper<Vue>

  beforeEach(() => {
    jest.clearAllMocks()
    mockGetDownloaderList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: []
    })
  })

  afterEach(() => {
    wrapper?.destroy()
  })

  it('全部候选已在处理中时提示并通知父列表立即刷新', async() => {
    mockQuickDeleteDuplicates.mockResolvedValueOnce({
      status: 'success',
      msg: '重复种子均已在删除任务中处理',
      code: '200',
      data: {
        task_id: null,
        total_count: 0,
        requested_count: 1,
        accepted_count: 0,
        skipped_count: 1,
        skipped_info_ids: ['delete-1'],
        delete_level: 2
      }
    })
    wrapper = mountDialog()
    const vm = wrapper.vm as unknown as QuickDeleteDialogVm
    vm.preview = preview
    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    vm.keepDownloaderIds = ['dl-b']

    await vm.handleDelete()

    expect(message.info).toHaveBeenCalledWith('重复种子均已在删除任务中处理')
    expect(wrapper.emitted('deleted')).toHaveLength(1)
    expect(getBatchDeleteStatus).not.toHaveBeenCalled()
    expect(getQuickDeleteDuplicatePreview).not.toHaveBeenCalled()
  })

  it('混合提交展示跳过数量，只轮询后端接受的新任务', async() => {
    mockQuickDeleteDuplicates.mockResolvedValueOnce({
      status: 'success',
      msg: '已提交删除任务，正在后台执行',
      code: '200',
      data: {
        task_id: 'delete-task-2',
        total_count: 1,
        requested_count: 2,
        accepted_count: 1,
        skipped_count: 1,
        skipped_info_ids: ['delete-1'],
        delete_level: 2
      }
    })
    wrapper = mountDialog()
    const vm = wrapper.vm as unknown as QuickDeleteDialogVm
    const poll = jest.spyOn(vm, 'pollDeleteStatus').mockResolvedValue()
    vm.preview = preview
    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    vm.keepDownloaderIds = ['dl-b']

    await vm.handleDelete()

    expect(message.success).toHaveBeenCalledWith(
      '已提交删除任务（共 1 个种子，跳过处理中 1 个）'
    )
    expect(wrapper.emitted('deleted')).toHaveLength(1)
    expect(poll).toHaveBeenCalledWith('delete-task-2')
  })
})

describe('QuickDeleteDuplicatesDialog 选择完成自动预览与删除后关闭（2026-09-12）', () => {
  let wrapper: Wrapper<Vue>

  beforeEach(() => {
    jest.clearAllMocks()
    mockGetDownloaderList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: []
    })
  })

  afterEach(() => {
    wrapper?.destroy()
  })

  it('选择完成（≥2 待检测 + ≥1 保留子集）自动触发预览，无需手动按钮', async() => {
    mockGetQuickDeleteDuplicatePreview.mockResolvedValueOnce({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: preview
    })
    wrapper = mountDialog()
    const vm = wrapper.vm as unknown as QuickDeleteDialogVm
    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    vm.keepDownloaderIds = ['dl-b']
    await waitAutoPreview()

    expect(mockGetQuickDeleteDuplicatePreview).toHaveBeenCalledWith(
      expect.objectContaining({
        downloader_ids: ['dl-a', 'dl-b'],
        keep_downloader_ids: ['dl-b'],
        page: 1
      })
    )
    expect(vm.preview).toEqual(preview)
  })

  it('选择未完成不触发；保留被清空时清除过期预览', async() => {
    mockGetQuickDeleteDuplicatePreview.mockResolvedValueOnce({
      code: '200',
      data: preview
    } as never)
    wrapper = mountDialog()
    const vm = wrapper.vm as unknown as QuickDeleteDialogVm
    // 仅待检测、无保留：不触发
    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    await waitAutoPreview()
    expect(mockGetQuickDeleteDuplicatePreview).not.toHaveBeenCalled()

    // 补齐保留：触发
    vm.keepDownloaderIds = ['dl-b']
    await waitAutoPreview()
    expect(mockGetQuickDeleteDuplicatePreview).toHaveBeenCalledTimes(1)
    expect(vm.preview).toEqual(preview)

    // 清空保留：过期预览被清除且不再发请求
    vm.keepDownloaderIds = []
    await waitAutoPreview()
    expect(vm.preview).toBeNull()
    expect(mockGetQuickDeleteDuplicatePreview).toHaveBeenCalledTimes(1)
  })

  it('确认删除成功后关闭弹窗（dialogVisible=false + emit close）', async() => {
    mockQuickDeleteDuplicates.mockResolvedValueOnce({
      status: 'success',
      msg: '已提交删除任务，正在后台执行',
      code: '200',
      data: {
        task_id: 'delete-task-close',
        total_count: 1,
        requested_count: 1,
        accepted_count: 1,
        skipped_count: 0,
        skipped_info_ids: [],
        delete_level: 2
      }
    })
    wrapper = mountDialog()
    const vm = wrapper.vm as unknown as QuickDeleteDialogVm & { dialogVisible: boolean }
    const poll = jest.spyOn(vm, 'pollDeleteStatus').mockResolvedValue()
    vm.preview = preview
    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    vm.keepDownloaderIds = ['dl-b']

    await vm.handleDelete()

    expect(vm.dialogVisible).toBe(false)
    expect(wrapper.emitted('close')).toHaveLength(1)
    // 后台轮询不因关闭而中断
    expect(poll).toHaveBeenCalledWith('delete-task-close')
  })

  it('源码契约：手动预览按钮已移除（事件触发替代）', () => {
    const source = fs.readFileSync(
      path.resolve(__dirname, '../../src/components/torrents/QuickDeleteDuplicatesDialog.vue'),
      'utf-8'
    )
    expect(source).not.toContain('handlePreview')
    expect(source).not.toContain('预览重复</el-button>')
  })
})
