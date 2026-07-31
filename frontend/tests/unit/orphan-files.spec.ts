import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import OrphanFiles from '@/views/orphan-files/index.vue'
import {
  ApiResponse,
  CleanupPreviewResult,
  CleanupResult,
  OrphanFileItem,
  OrphanListResponse,
  OrphanScanContext,
  OrphanScanRecord,
  cleanupOrphans,
  cleanupPreview,
  getOrphanList,
  setIgnored,
  triggerScan
} from '@/api/orphan-files'

jest.mock('@/api/orphan-files', () => ({
  getLatestScan: jest.fn(),
  getOrphanList: jest.fn(),
  triggerScan: jest.fn(),
  cleanupPreview: jest.fn(),
  cleanupOrphans: jest.fn(),
  setIgnored: jest.fn()
}))

jest.mock('@/api/torrents', () => ({
  getDownloaderList: jest.fn(() =>
    Promise.resolve({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: [{ downloader_id: 'dl-1', nickname: '主下载器' }]
    })
  )
}))

const localVue = createLocalVue()
localVue.directive('loading', {})

const mockGetOrphanList = getOrphanList as jest.MockedFunction<typeof getOrphanList>
const mockTriggerScan = triggerScan as jest.MockedFunction<typeof triggerScan>
const mockCleanupPreview = cleanupPreview as jest.MockedFunction<typeof cleanupPreview>
const mockCleanupOrphans = cleanupOrphans as jest.MockedFunction<typeof cleanupOrphans>
const mockSetIgnored = setIgnored as jest.MockedFunction<typeof setIgnored>

const clearSelection = jest.fn()
const TableStub = localVue.extend({
  props: ['data'],
  methods: {
    clearSelection
  },
  template: '<div class="orphan-table-stub"><slot /></div>'
})
const TableColumnStub = localVue.extend({
  render(createElement) {
    return createElement('div')
  }
})
const ButtonStub = localVue.extend({
  props: {
    disabled: Boolean,
    title: String,
    loading: Boolean
  },
  template: `
    <button
      :disabled="disabled"
      :title="title"
      :data-loading="String(loading)"
      @click="$emit('click')"
    >
      <slot />
    </button>
  `
})
const AlertStub = localVue.extend({
  props: ['title', 'description', 'type'],
  template: `
    <div class="orphan-alert-stub" :data-type="type">
      <strong>{{ title }}</strong>
      <span>{{ description }}</span>
      <slot />
    </div>
  `
})
const DialogStub = localVue.extend({
  props: ['visible'],
  template: '<div class="orphan-dialog-stub"><slot /><slot name="footer" /></div>'
})

interface OrphanFilesVm extends Vue {
  list: OrphanFileItem[]
  total: number
  listLoading: boolean
  scanLoading: boolean
  ignoreLoading: boolean
  listQuery: {
    page: number
    page_size: number
    downloader_id: string
    path_like: string
    status: string
    min_size: number | ''
  }
  selectedIds: number[]
  selectedRows: OrphanFileItem[]
  scanContext: OrphanScanContext
  cleanupAllowed: boolean
  canBatchCleanup: boolean
  canBatchIgnore: boolean
  canBatchUnignore: boolean
  cleanupDialogVisible: boolean
  cleanupPreviewData: CleanupPreviewResult | null
  cleanupResult: CleanupResult | null
  previewScanId: string | null
  refreshPageData: (allowPageCorrection?: boolean) => Promise<void>
  handleScan: () => Promise<void>
  handleCleanupPreview: () => Promise<void>
  handleCleanupConfirm: () => Promise<void>
  handleResetFilter: () => void
  handleBatchIgnore: (ignored: boolean) => Promise<void>
  handleRowIgnore: (row: OrphanFileItem, ignored: boolean) => Promise<void>
}

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason?: unknown) => void
}

const message = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
  info: jest.fn()
}
const confirm = jest.fn(() => Promise.resolve())

function deferred<T>(): Deferred<T> {
  let resolvePromise!: (value: T) => void
  let rejectPromise!: (reason?: unknown) => void
  const promise = new Promise<T>((resolve, reject) => {
    resolvePromise = resolve
    rejectPromise = reject
  })
  return {
    promise,
    resolve: resolvePromise,
    reject: rejectPromise
  }
}

function scanRecord(
  overrides: Partial<OrphanScanRecord> = {}
): OrphanScanRecord {
  return {
    scan_id: 'scan-completed',
    scan_time: '2026-07-30T10:00:00',
    scan_type: 'manual',
    total_paths_scanned: 3,
    total_files_scanned: 20,
    total_orphans: 2,
    total_orphan_size: 300,
    status: 'completed',
    error_message: null,
    operator: 'tester',
    created_at: '2026-07-30T10:00:00',
    ...overrides
  }
}

function scanContext(
  overrides: Partial<OrphanScanContext> = {}
): OrphanScanContext {
  const completed = scanRecord()
  return {
    latest_attempt: completed,
    display_scan: completed,
    remaining_count: 2,
    remaining_size: 300,
    ignored_count: 0,
    cleanup_allowed: true,
    cleanup_block_reason: null,
    ...overrides
  }
}

function orphanItem(id: number, scanId = 'scan-completed'): OrphanFileItem {
  return {
    id,
    scan_id: scanId,
    file_path: `/data/${id}.bin`,
    file_size: id * 100,
    mtime: '2026-07-30T09:00:00',
    downloader_id: 'dl-1',
    confidence: 'high',
    canonical_path: `/data/${id}.bin`,
    downloader_name: '主下载器',
    is_ignored: false,
    ignored_at: null,
    ignored_by: null,
    is_deleted: false,
    deleted_at: null,
    deleted_by: null,
    created_at: '2026-07-30T10:00:00'
  }
}

function listResponse(
  context: OrphanScanContext = scanContext(),
  list: OrphanFileItem[] = [orphanItem(1), orphanItem(2)],
  total = list.length,
  page = 1
): ApiResponse<OrphanListResponse> {
  return {
    code: '200',
    msg: 'ok',
    status: 'success',
    data: {
      list,
      total,
      page,
      pageSize: 20,
      scan_context: context
    }
  }
}

async function flushLifecycle(): Promise<void> {
  for (let index = 0; index < 15; index += 1) {
    await Promise.resolve()
  }
  await localVue.nextTick()
}

function mountView(): Wrapper<Vue> {
  return shallowMount(OrphanFiles, {
    localVue,
    mocks: {
      $message: message,
      $confirm: confirm
    },
    stubs: {
      'el-button': ButtonStub,
      'el-alert': AlertStub,
      'el-dialog': DialogStub,
      'el-table': TableStub,
      'el-table-column': TableColumnStub,
      'el-input': true,
      'el-pagination': true,
      'el-tag': true,
      'el-select': true,
      'el-option': true,
      'el-tooltip': true
    }
  })
}

function viewModel(wrapper: Wrapper<Vue>): OrphanFilesVm {
  return wrapper.vm as OrphanFilesVm
}

describe('orphan files atomic page state', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetOrphanList.mockResolvedValue(listResponse())
    mockTriggerScan.mockResolvedValue({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        scan_id: 'scan-completed',
        scan_time: '2026-07-30T10:00:00',
        scan_type: 'manual',
        total_paths_scanned: 3,
        total_files_scanned: 20,
        total_orphans: 2,
        total_orphan_size: 300,
        status: 'completed'
      }
    })
    mockCleanupPreview.mockResolvedValue({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        total_count: 1,
        total_size: 100,
        items: [{ id: 1, file_path: '/data/1.bin', file_size: 100 }]
      }
    })
    mockCleanupOrphans.mockResolvedValue({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        success_count: 1,
        failed_count: 0,
        failed_list: [],
        total_size: 100
      }
    })
  })

  it('首次加载用一次分页响应同时更新列表、统计和扫描上下文', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    expect(mockGetOrphanList).toHaveBeenCalledTimes(1)
    expect(vm.list.map((item) => item.id)).toEqual([1, 2])
    expect(vm.total).toBe(2)
    expect(vm.scanContext.remaining_count).toBe(2)
    expect(vm.scanContext.remaining_size).toBe(300)
    expect(wrapper.text()).toContain('待清理文件数')
    expect(wrapper.text()).toContain('待清理空间')
  })

  it('点击顶部刷新会同时替换列表与统计上下文', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(
        scanContext({ remaining_count: 1, remaining_size: 900 }),
        [orphanItem(9)],
        1
      )
    )

    await wrapper.find('.management-page__actions button').trigger('click')
    await flushLifecycle()
    const vm = viewModel(wrapper)

    expect(mockGetOrphanList).toHaveBeenCalledTimes(2)
    expect(vm.list[0].id).toBe(9)
    expect(vm.scanContext.remaining_count).toBe(1)
    expect(vm.scanContext.remaining_size).toBe(900)
  })

  it('刷新保留查询快照并只在最新成功响应后清空选择', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    clearSelection.mockClear()
    vm.listQuery.page = 3
    vm.listQuery.page_size = 50
    vm.listQuery.downloader_id = 'dl-filter'
    vm.selectedRows = [orphanItem(1)]
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(scanContext(), [orphanItem(3)], 120, 3)
    )

    await vm.refreshPageData()

    expect(mockGetOrphanList).toHaveBeenLastCalledWith({
      page: 3,
      page_size: 50,
      downloader_id: 'dl-filter',
      path_like: undefined,
      status: undefined,
      min_size: undefined
    })
    expect(vm.listQuery).toEqual({
      page: 3,
      page_size: 50,
      downloader_id: 'dl-filter',
      path_like: '',
      status: '',
      min_size: ''
    })
    expect(vm.selectedIds).toEqual([])
    expect(clearSelection).toHaveBeenCalledTimes(1)
  })

  it('最新失败时展示旧成功结果和失败原因，并禁用清理', async() => {
    const failed = scanRecord({
      scan_id: 'scan-failed',
      status: 'failed',
      error_message: '下载器不可用'
    })
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(
        scanContext({
          latest_attempt: failed,
          cleanup_allowed: false,
          cleanup_block_reason: '最新扫描状态为 failed，禁止清理'
        }),
        [orphanItem(1)]
      )
    )

    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.selectedRows = [orphanItem(1)]
    await localVue.nextTick()

    expect(vm.list).toHaveLength(1)
    expect(vm.cleanupAllowed).toBe(false)
    expect(wrapper.text()).toContain('下载器不可用')
    expect(wrapper.text()).toContain('只读展示')
    expect(
      wrapper.find('.management-panel__meta button').attributes('disabled')
    ).toBe('disabled')
  })

  it('最新运行中时保持空列表、零统计且不回退旧批次', async() => {
    const running = scanRecord({
      scan_id: 'scan-running',
      status: 'running'
    })
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(
        scanContext({
          latest_attempt: running,
          display_scan: null,
          remaining_count: 0,
          remaining_size: 0,
          cleanup_allowed: false,
          cleanup_block_reason: '扫描进行中'
        }),
        [],
        0
      )
    )

    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    expect(vm.list).toEqual([])
    expect(vm.scanContext.display_scan).toBeNull()
    expect(vm.scanContext.remaining_count).toBe(0)
    expect(vm.cleanupAllowed).toBe(false)
    expect(wrapper.text()).toContain('扫描正在进行中')
  })

  it('清理成功后从统一刷新响应更新剩余数量和大小', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.selectedRows = [orphanItem(1)]
    await vm.handleCleanupPreview()
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(
        scanContext({ remaining_count: 1, remaining_size: 200 }),
        [orphanItem(2)],
        1
      )
    )

    await vm.handleCleanupConfirm()

    expect(mockCleanupOrphans).toHaveBeenCalledWith({
      scan_id: 'scan-completed',
      orphan_ids: [1]
    })
    expect(vm.scanContext.remaining_count).toBe(1)
    expect(vm.scanContext.remaining_size).toBe(200)
    expect(vm.list.map((item) => item.id)).toEqual([2])
  })

  it('后端拒绝 stale 清理时显示原因、关闭弹窗并刷新', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.selectedRows = [orphanItem(1)]
    await vm.handleCleanupPreview()
    mockCleanupOrphans.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        rejected: true,
        error: 'scan_id 已过期',
        success_count: 0,
        failed_count: 1,
        failed_list: [{ id: 1, reason: 'scan_id 已过期' }],
        total_size: 0
      }
    })
    mockGetOrphanList.mockResolvedValueOnce(listResponse())

    await vm.handleCleanupConfirm()

    expect(message.error).toHaveBeenCalledWith('scan_id 已过期')
    expect(vm.cleanupDialogVisible).toBe(false)
    expect(mockGetOrphanList).toHaveBeenCalledTimes(2)
  })

  it('逆序成功响应不能覆盖新结果、选择、页码或 loading', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const older = deferred<ApiResponse<OrphanListResponse>>()
    const newer = deferred<ApiResponse<OrphanListResponse>>()
    mockGetOrphanList
      .mockImplementationOnce(() => older.promise)
      .mockImplementationOnce(() => newer.promise)

    vm.listQuery.page = 2
    const olderRequest = vm.refreshPageData()
    vm.listQuery.page = 3
    const newerRequest = vm.refreshPageData()
    newer.resolve(
      listResponse(
        scanContext({ remaining_count: 1 }),
        [orphanItem(30)],
        100,
        3
      )
    )
    await newerRequest
    vm.selectedRows = [orphanItem(99)]
    clearSelection.mockClear()

    older.resolve(
      listResponse(
        scanContext({ remaining_count: 9 }),
        [orphanItem(20)],
        100,
        2
      )
    )
    await olderRequest

    expect(vm.list.map((item) => item.id)).toEqual([30])
    expect(vm.scanContext.remaining_count).toBe(1)
    expect(vm.listQuery.page).toBe(3)
    expect(vm.selectedIds).toEqual([99])
    expect(vm.listLoading).toBe(false)
    expect(clearSelection).not.toHaveBeenCalled()
    expect(mockGetOrphanList.mock.calls.slice(-2)).toEqual([
      [{ page: 2, page_size: 20, downloader_id: undefined, path_like: undefined, status: undefined, min_size: undefined }],
      [{ page: 3, page_size: 20, downloader_id: undefined, path_like: undefined, status: undefined, min_size: undefined }]
    ])
  })

  it('扫描触发 busy 只反馈占用并通过统一刷新读取持久化状态', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    mockTriggerScan.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        status: 'busy',
        error: '孤儿文件维护任务正在进行'
      }
    })
    const persistedRunning = scanRecord({
      scan_id: 'scan-running',
      status: 'running'
    })
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(
        scanContext({
          latest_attempt: persistedRunning,
          display_scan: null,
          remaining_count: 0,
          remaining_size: 0,
          cleanup_allowed: false,
          cleanup_block_reason: '扫描进行中'
        }),
        [],
        0
      )
    )

    await vm.handleScan()

    expect(message.warning).toHaveBeenCalledWith('孤儿文件维护任务正在进行')
    expect(mockGetOrphanList).toHaveBeenCalledTimes(2)
    expect(vm.scanContext.latest_attempt?.status).toBe('running')
    expect(vm.scanContext.latest_attempt?.status).not.toBe('busy')
  })

  it('最新刷新失败时保留已有数据并结束 loading', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const previousList = vm.list
    const previousContext = vm.scanContext
    mockGetOrphanList.mockRejectedValueOnce(new Error('network down'))

    await vm.refreshPageData()

    expect(vm.list).toBe(previousList)
    expect(vm.scanContext).toBe(previousContext)
    expect(vm.listLoading).toBe(false)
    expect(message.error).toHaveBeenCalledWith(
      expect.stringContaining('获取孤儿文件列表失败')
    )
  })

  it('过期失败响应静默退出且不修改较新请求状态', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    message.error.mockClear()
    const stale = deferred<ApiResponse<OrphanListResponse>>()
    const fresh = deferred<ApiResponse<OrphanListResponse>>()
    mockGetOrphanList
      .mockImplementationOnce(() => stale.promise)
      .mockImplementationOnce(() => fresh.promise)

    const staleRequest = vm.refreshPageData()
    const freshRequest = vm.refreshPageData()
    fresh.resolve(listResponse(scanContext(), [orphanItem(8)], 1))
    await freshRequest
    stale.reject(new Error('stale failure'))
    await staleRequest

    expect(vm.list.map((item) => item.id)).toEqual([8])
    expect(vm.listLoading).toBe(false)
    expect(message.error).not.toHaveBeenCalled()
  })

  it('页码超出末页时最多修正一次并使用新请求序号补发', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.listQuery.page = 5
    mockGetOrphanList
      .mockResolvedValueOnce(listResponse(scanContext(), [], 1, 5))
      .mockResolvedValueOnce(
        listResponse(scanContext(), [orphanItem(1)], 1, 1)
      )

    await vm.refreshPageData()

    expect(vm.listQuery.page).toBe(1)
    expect(vm.list.map((item) => item.id)).toEqual([1])
    expect(mockGetOrphanList.mock.calls.slice(-2)).toEqual([
      [{ page: 5, page_size: 20, downloader_id: undefined, path_like: undefined, status: undefined, min_size: undefined }],
      [{ page: 1, page_size: 20, downloader_id: undefined, path_like: undefined, status: undefined, min_size: undefined }]
    ])
  })

  it('列表项渲染置信度与下载器别名', async() => {
    const wrapper = mountView()
    await flushLifecycle()

    // 视图以 confidence/downloader_name 字段驱动展示（shallowMount 下验证 vm 数据契约）
    const vm = viewModel(wrapper)
    expect(vm.list[0].confidence).toBe('high')
    expect(vm.list[0].downloader_name).toBe('主下载器')
    expect(vm.scanContext.ignored_count).toBe(0)
  })

  it('搜索条件重置后回到默认空筛选', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.listQuery.path_like = '/movie'
    vm.listQuery.status = 'ignored'
    vm.listQuery.min_size = 1024
    vm.handleResetFilter()

    expect(vm.listQuery.path_like).toBe('')
    expect(vm.listQuery.status).toBe('')
    expect(vm.listQuery.min_size).toBe('')
  })

  it('批量忽视调用 setIgnored 并刷新列表', async() => {
    mockSetIgnored.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        success_count: 1,
        failed_count: 0,
        failed_list: [],
        total_size: 0
      }
    })
    mockGetOrphanList.mockResolvedValueOnce(listResponse())
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    // 选中一个待清理项（默认 orphanItem 为 pending：未删除未忽视）
    vm.selectedRows = [orphanItem(1)]

    await vm.handleBatchIgnore(true)

    expect(mockSetIgnored).toHaveBeenCalledTimes(1)
    const call = mockSetIgnored.mock.calls[0][0]
    expect(call.ignored).toBe(true)
    expect(call.orphan_ids).toEqual([1])
    expect(message.success).toHaveBeenCalled()
    // 忽视后刷新列表
    expect(mockGetOrphanList).toHaveBeenCalled()
  })

  it('混选不同状态时批量按钮禁用', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    // 混选：一个待清理（默认 is_ignored=false）+ 一个已忽视
    vm.selectedRows = [orphanItem(1), { ...orphanItem(2), is_ignored: true }]

    expect(vm.canBatchIgnore).toBe(false)
    expect(vm.canBatchUnignore).toBe(false)
    expect(vm.canBatchCleanup).toBe(false)
  })
})
