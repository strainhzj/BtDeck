import { createLocalVue, shallowMount } from '@vue/test-utils'
import Vue from 'vue'
import ElementUI from 'element-ui'
import QuickDeleteDuplicatesDialog from '../QuickDeleteDuplicatesDialog.vue'
import { quickDeleteDuplicates } from '@/api/torrents'

/**
 * QuickDeleteDuplicatesDialog 单测
 *
 * 覆盖：
 * - keepOptions 联动（只列出已选待检测下载器）
 * - 待检测下载器变化时 keepDownloaderIds 联动剪裁（AdvancedMultiSelect 不会自动清空）
 * - canPreview 校验（≥2 待检测 / ≥1 保留 / 保留 ⊆ 待检测）
 * - 确认删除调用 quickDeleteDuplicates 参数组装（level=2 / notify_on_complete=true）
 */

jest.mock('@/api/torrents', () => {
  const actual = jest.requireActual('@/api/torrents')
  return {
    ...actual,
    getDownloaderList: jest.fn().mockResolvedValue({
      code: '200',
      data: [
        { downloader_id: 'dl-a', nickname: 'A' },
        { downloader_id: 'dl-b', nickname: 'B' },
        { downloader_id: 'dl-c', nickname: 'C' }
      ]
    }),
    getQuickDeleteDuplicatePreview: jest.fn().mockResolvedValue({
      code: '200',
      data: {
        total: 1,
        page: 1,
        pageSize: 20,
        total_groups: 1,
        total_delete: 1,
        skipped_groups: 0,
        list: [
          {
            hash: 'aaa',
            name: 'n1',
            size: 100,
            kept: [{ info_id: 'k1', downloader_id: 'dl-b', downloader_name: 'B', name: 'n1', size: 100, status: 'seeding', hash: 'aaa' }],
            to_delete: [{ info_id: 'd1', downloader_id: 'dl-a', downloader_name: 'A', name: 'n1', size: 100, status: 'seeding', hash: 'aaa' }],
            skipped: false
          }
        ]
      }
    }),
    quickDeleteDuplicates: jest.fn().mockResolvedValue({
      code: '200',
      data: { task_id: 'task-1', total_count: 1, delete_level: 2 }
    }),
    getBatchDeleteStatus: jest.fn().mockResolvedValue({
      code: '200',
      data: { status: 'completed', success_count: 1, failed_count: 0 }
    })
  }
})

const localVue = createLocalVue()
localVue.use(ElementUI)

interface QuickDeleteDialogVm extends Vue {
  downloaderOptions: Array<{ value: string | number, label: string }>
  detectDownloaderIds: (string | number)[]
  keepDownloaderIds: (string | number)[]
  keepOptions: Array<{ value: string | number, label: string }>
  canPreview: boolean
  preview: any
  handleDelete(): Promise<void>
  handlePreview(): Promise<void>
}

describe('QuickDeleteDuplicatesDialog', () => {
  let logSpy: jest.SpyInstance
  let warnSpy: jest.SpyInstance
  let errorSpy: jest.SpyInstance

  beforeEach(() => {
    logSpy = jest.spyOn(console, 'log').mockImplementation(() => undefined)
    warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined)
    jest.clearAllMocks()
  })

  afterEach(() => {
    logSpy.mockRestore()
    warnSpy.mockRestore()
    errorSpy.mockRestore()
  })

  function mountDialog() {
    const wrapper = shallowMount(QuickDeleteDuplicatesDialog, {
      localVue,
      propsData: { visible: false },
      stubs: {
        'advanced-multi-select': true,
        'el-dialog': true,
        'el-alert': true,
        'el-pagination': true,
        'el-tooltip': true
      }
    })
    const vm = wrapper.vm as unknown as QuickDeleteDialogVm
    vm.downloaderOptions = [
      { value: 'dl-a', label: 'A' },
      { value: 'dl-b', label: 'B' },
      { value: 'dl-c', label: 'C' }
    ]
    return { wrapper, vm }
  }

  it('keepOptions 只列出已选待检测下载器', () => {
    const { vm } = mountDialog()
    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    expect(vm.keepOptions.map(o => o.value)).toEqual(['dl-a', 'dl-b'])
    vm.detectDownloaderIds = ['dl-c']
    expect(vm.keepOptions.map(o => o.value)).toEqual(['dl-c'])
  })

  it('待检测下载器变化时，keepDownloaderIds 联动剪裁为子集', async() => {
    const { vm } = mountDialog()
    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    vm.keepDownloaderIds = ['dl-b', 'dl-c'] // 含非子集项
    await vm.$nextTick()
    // 剪裁掉 dl-c
    expect(vm.keepDownloaderIds).toEqual(['dl-b'])

    vm.detectDownloaderIds = ['dl-a']
    await vm.$nextTick()
    expect(vm.keepDownloaderIds).toEqual([])
  })

  it('canPreview 校验：≥2 待检测 / ≥1 保留 / 保留 ⊆ 待检测', () => {
    const { vm } = mountDialog()
    expect(vm.canPreview).toBe(false)

    vm.detectDownloaderIds = ['dl-a']
    vm.keepDownloaderIds = ['dl-a']
    expect(vm.canPreview).toBe(false) // 待检测不足 2

    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    vm.keepDownloaderIds = []
    expect(vm.canPreview).toBe(false) // 无保留

    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    vm.keepDownloaderIds = ['dl-a']
    expect(vm.canPreview).toBe(true)
  })

  it('确认删除调用 quickDeleteDuplicates（level=2 / notify_on_complete=true）', async() => {
    const { vm } = mountDialog()
    vm.detectDownloaderIds = ['dl-a', 'dl-b']
    vm.keepDownloaderIds = ['dl-b']
    vm.preview = {
      total_delete: 1,
      total_groups: 1,
      skipped_groups: 0,
      total: 1,
      page: 1,
      pageSize: 20,
      list: []
    }

    await vm.handleDelete()

    expect(quickDeleteDuplicates).toHaveBeenCalledTimes(1)
    expect(quickDeleteDuplicates).toHaveBeenCalledWith({
      downloader_ids: ['dl-a', 'dl-b'],
      keep_downloader_ids: ['dl-b'],
      delete_level: 2,
      notify_on_complete: true
    })
  })
})
