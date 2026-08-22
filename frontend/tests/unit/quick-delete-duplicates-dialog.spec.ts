import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

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
