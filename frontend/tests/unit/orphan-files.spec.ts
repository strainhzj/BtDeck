import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import OrphanFiles from '@/views/orphan-files/index.vue'
import {
  ApiResponse,
  CleanupPreviewResult,
  OrphanFileItem,
  OrphanListResponse,
  OrphanSelectionPayload,
  OrphanScanContext,
  OrphanScanRecord,
  PrefixMatchPreviewResult,
  QuarantineItem,
  QuarantineListResult,
  cleanupOrphans,
  cleanupPreview,
  getQuarantineList,
  getOrphanList,
  prefixMatchPreview,
  purgeQuarantineNow,
  setIgnored,
  triggerScan
} from '@/api/orphan-files'

jest.mock('@/api/orphan-files', () => ({
  getLatestScan: jest.fn(),
  getOrphanList: jest.fn(),
  triggerScan: jest.fn(),
  cleanupPreview: jest.fn(),
  cleanupOrphans: jest.fn(),
  setIgnored: jest.fn(),
  getQuarantineList: jest.fn(),
  purgeQuarantineNow: jest.fn(),
  prefixMatchPreview: jest.fn()
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
const mockGetQuarantineList = getQuarantineList as jest.MockedFunction<typeof getQuarantineList>
const mockPurgeQuarantineNow = purgeQuarantineNow as jest.MockedFunction<typeof purgeQuarantineNow>
const mockPrefixMatchPreview = prefixMatchPreview as jest.MockedFunction<typeof prefixMatchPreview>

const clearSelection = jest.fn()
const TableStub = localVue.extend({
  props: ['data', 'height'],
  methods: {
    clearSelection
  },
  computed: {
    listenerNames(): string {
      return Object.keys(this.$listeners).join(',')
    }
  },
  template: '<div class="orphan-table-stub" :data-height="height" :data-listeners="listenerNames"><slot /></div>'
})
const TableColumnStub = localVue.extend({
  props: {
    type: { type: String, default: '' },
    selectable: { type: Function, default: null },
    prop: { type: String, default: '' }
  },
  render(createElement) {
    const slot = this.$scopedSlots.default
    if (!slot) return createElement('div', { attrs: { 'data-column-type': this.type } })
    return createElement('div', { attrs: { 'data-column-type': this.type } }, slot({ row: quarantineItem() }))
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
  pageSizeInput: string
  listQuery: {
    page: number
    page_size: number
    downloader_id: string
    path_like: string
    status: string
    confidence: string
    min_size: number | ''
  }
  selectedIds: number[]
  selectedRows: OrphanFileItem[]
  selectedCount: number
  scanContext: OrphanScanContext
  activeTab: 'orphans' | 'quarantine'
  quarantineList: QuarantineItem[]
  quarantineTotal: number
  quarantineSelected: QuarantineItem[]
  purgeExecuting: boolean
  cleanupAllowed: boolean
  canBatchCleanup: boolean
  canBatchIgnore: boolean
  canBatchUnignore: boolean
  cleanupDialogVisible: boolean
  cleanupPreviewData: CleanupPreviewResult | null
  previewScanId: string | null
  previewSelection: OrphanSelectionPayload | null
  quickActionDialogVisible: boolean
  quickActionType: 'cleanup' | 'ignore' | null
  quickActionPrefix: string
  quickActionLoading: boolean
  refreshPageData: () => Promise<void>
  loadOrphanPage: (page: number) => Promise<void>
  handleOrphanPageChange: (page: number) => Promise<void>
  handleScan: () => Promise<void>
  handleCleanupPreview: () => Promise<void>
  handleCleanupConfirm: () => Promise<void>
  handleFilter: () => void
  handleResetFilter: () => void
  applyPageSizeSelection: (value: string | number) => void
  handleOrphanSelectionChange: (rows: OrphanFileItem[]) => void
  handleBatchIgnore: (ignored: boolean) => Promise<void>
  handleRowIgnore: (row: OrphanFileItem, ignored: boolean) => Promise<void>
  handleQuickAction: (command: 'cleanup' | 'ignore') => void
  handleQuickActionCancel: () => void
  handleQuickActionConfirm: () => Promise<void>
  handleTabSwitch: () => Promise<void>
  handleQuarantinePurge: () => Promise<void>
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
const confirm = jest.fn((..._args: unknown[]) => Promise.resolve())

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

function quarantineItem(): QuarantineItem {
  return {
    canonical_path: '/data/quarantine.bin',
    downloader_id: 'dl-1',
    downloader_name: '涓讳笅杞藉櫒',
    quarantine_path: '/data/.btdeck_quarantine/quarantine.bin',
    quarantine_root: '/data/.btdeck_quarantine',
    mtime: '2026-07-30T09:00:00',
    quarantined_at: '2026-07-30T10:00:00',
    purge_after: '2026-08-06T10:00:00',
    file_size: 2048,
    confidence: 'high'
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
      'el-tabs': true,
      'el-tab-pane': true,
      'el-checkbox': true,
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
        task_id: 'cleanup-task-1',
        operation_type: 'cleanup',
        status: 'pending',
        scan_id: 'scan-completed',
        total_count: 1,
        success_count: 1,
        purged_count: 1,
        failed_count: 0,
        failed_list: [],
        total_size: 100,
        error_message: null,
        created_at: '2026-08-01T10:00:00Z',
        started_at: null,
        completed_at: null
      }
    })
    mockGetQuarantineList.mockResolvedValue({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        total: 0,
        page: 1,
        pageSize: 20,
        list: []
      } as QuarantineListResult
    })
    mockPurgeQuarantineNow.mockResolvedValue({
      code: '200',
      msg: '彻底删除任务已提交，完成后将发送通知',
      status: 'success',
      data: {
        task_id: '12345678-1234-1234-1234-123456789abc',
        status: 'pending',
        total_count: 1,
        purged_count: 0,
        failed_count: 0,
        failed_list: [],
        error_message: null,
        created_at: '2026-08-01T10:00:00',
        started_at: null,
        completed_at: null
      }
    })
  })

  it('隔离区刷新后使用组件暴露的大小格式化方法渲染', async() => {
    mockGetQuarantineList.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        total: 1,
        page: 1,
        pageSize: 20,
        list: [quarantineItem()]
      }
    })

    const renderErrors: Error[] = []
    const previousErrorHandler = localVue.config.errorHandler
    localVue.config.errorHandler = (error) => {
      renderErrors.push(error)
    }

    const wrapper = mountView()
    try {
      await flushLifecycle()
      const vm = viewModel(wrapper)
      vm.activeTab = 'quarantine'
      await vm.handleTabSwitch()
      await localVue.nextTick()

      expect(mockGetQuarantineList).toHaveBeenCalledWith({
        page: 1,
        page_size: 20
      })
      expect(vm.quarantineList).toHaveLength(1)
      expect(renderErrors).toEqual([])
    } finally {
      wrapper.destroy()
      localVue.config.errorHandler = previousErrorHandler
    }
  })

  it('彻底删除只提交后台任务并提示通过通知中心接收结果', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.quarantineSelected = [quarantineItem()]

    await vm.handleQuarantinePurge()

    expect(mockPurgeQuarantineNow).toHaveBeenCalledWith({
      canonical_paths: ['/data/quarantine.bin']
    })
    expect(message.success).toHaveBeenCalledWith(
      expect.stringContaining('完成或失败后将在通知中心提醒')
    )
    expect(vm.quarantineSelected).toEqual([])
    expect(vm.purgeExecuting).toBe(false)
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
      page: 1,
      page_size: 50,
      downloader_id: 'dl-filter',
      path_like: undefined,
      status: undefined,
      min_size: undefined
    })
    expect(vm.listQuery).toEqual({
      page: 1,
      page_size: 50,
      downloader_id: 'dl-filter',
      path_like: '',
      status: '',
      confidence: '',
      min_size: ''
    })
    expect(vm.selectedIds).toEqual([])
    // refreshPageData 现在会清空当前页选择（传统分页标准行为），通过 el-table ref 调 clearSelection
    expect(clearSelection).toHaveBeenCalled()
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

  it('提交主动清理任务后立即关闭弹窗并刷新页面', async() => {
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
    expect(message.success).toHaveBeenCalledWith(
      '主动清理任务已提交（cleanup-），完成或失败后将在通知中心提醒'
    )
    expect(vm.cleanupDialogVisible).toBe(false)
    expect(vm.scanContext.remaining_count).toBe(1)
    expect(vm.scanContext.remaining_size).toBe(200)
    expect(vm.list.map((item) => item.id)).toEqual([2])
  })

  it('主动清理任务提交失败时提示错误且不伪造完成结果', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.selectedRows = [orphanItem(1)]
    await vm.handleCleanupPreview()
    mockCleanupOrphans.mockResolvedValueOnce({
      code: '500',
      msg: '任务提交失败',
      status: 'error',
      data: null as unknown as never
    })

    await vm.handleCleanupConfirm()

    expect(message.error).toHaveBeenCalledWith('任务提交失败')
    expect(vm.cleanupDialogVisible).toBe(true)
    expect(mockGetOrphanList).toHaveBeenCalledTimes(1)
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

    const olderRequest = vm.handleOrphanPageChange(2)
    const newerRequest = vm.handleOrphanPageChange(3)
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

  it('孤儿表格使用内部固定高度滚动以保持表头可见', async() => {
    const wrapper = mountView()
    await flushLifecycle()

    const table = wrapper.find('.orphan-table-stub')
    expect(table.attributes('data-height')).toBe('100%')
  })

  it('翻页切换加载对应页并清空当前页选择', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.selectedRows = [orphanItem(1)]
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(scanContext(), [orphanItem(21)], 100, 2)
    )

    await vm.handleOrphanPageChange(2)

    expect(mockGetOrphanList).toHaveBeenLastCalledWith({
      page: 2,
      page_size: 20,
      downloader_id: undefined,
      path_like: undefined,
      status: undefined,
      min_size: undefined
    })
    expect(vm.listQuery.page).toBe(2)
    expect(vm.selectedRows).toEqual([])
    expect(vm.list.map((item) => item.id)).toEqual([21])
  })

  // 回归保护：表头全选必须用原生 type="selection" 列，而非 slot="header" 自定义 el-checkbox。
  // 后者的表头绑定不会随 data 变化更新（el-table 不重渲染表头 slot），会导致 checkbox 卡在初始 disabled。
  it('多选用原生 type=selection 列而非 slot=header 自定义 checkbox', async() => {
    const wrapper = mountView()
    await flushLifecycle()

    const table = wrapper.find('.orphan-table-stub')
    // 选择列透传 type="selection"
    const selectionColumn = table.find('[data-column-type="selection"]')
    expect(selectionColumn.exists()).toBe(true)
    // 表格绑定 @selection-change（原生选择事件驱动，而非自定义 @change）
    expect(table.attributes('data-listeners')).toContain('selection-change')
    // 不能残留表头自定义 checkbox（slot="header" 的产物）
    expect(table.find('.orphan-select-all').exists()).toBe(false)
  })

  it('选择回调仅记录当前页选中行（已清理行不可选）', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const pending1 = orphanItem(1)
    const deletedRow = { ...orphanItem(2), is_deleted: true }
    const pending3 = orphanItem(3)
    vm.list = [pending1, deletedRow, pending3]
    vm.total = 100
    vm.listQuery.status = 'pending'

    // el-table 的 :selectable=rowSelectable 保证 deleted 行不可选，
    // 故 selection-change 只回调可选行
    vm.handleOrphanSelectionChange([pending1, pending3])

    expect(vm.selectedRows.map((row) => row.id)).toEqual([1, 3])
    expect(vm.selectedCount).toBe(2)

    // 取消选中其中一行
    vm.handleOrphanSelectionChange([pending3])

    expect(vm.selectedCount).toBe(1)
    expect(vm.selectedRows.map((row) => row.id)).toEqual([3])
  })

  // 端到端验证 @selection-change 事件绑定：模拟 el-table emit selection-change，
  // 确认事件名与 handler 正确连通（防止拼错事件名或漏绑）。
  it('el-table 触发 selection-change 事件时同步到 selectedRows', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const pending1 = orphanItem(1)
    const pending2 = orphanItem(2)

    // shallowMount 下 el-table 是 TableStub，直接用其根元素 vm emit
    const tableEl = wrapper.find('.orphan-table-stub')
    ;(tableEl.vm as Vue).$emit('selection-change', [pending1, pending2])
    await localVue.nextTick()

    expect(vm.selectedRows.map((row) => row.id)).toEqual([1, 2])
  })

  it('当前页选中后批量忽视提交 orphan_ids 而非 select_all', async() => {
    mockSetIgnored.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: { success_count: 2, failed_count: 0, failed_list: [] }
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const pending1 = orphanItem(1)
    const pending3 = orphanItem(3)
    vm.list = [pending1, pending3]
    vm.total = 50
    vm.listQuery.status = 'pending'
    vm.handleOrphanSelectionChange([pending1, pending3])

    await vm.handleBatchIgnore(true)

    const call = mockSetIgnored.mock.calls[0][0]
    expect(call.scan_id).toBe('scan-completed')
    expect(call.orphan_ids).toEqual([1, 3])
    expect(call.ignored).toBe(true)
    expect(call.select_all).toBeUndefined()
    expect(call.excluded_orphan_ids).toBeUndefined()
    expect(call.filters).toBeUndefined()
  })

  it('当前页选中后清理预览提交 orphan_ids 而非 select_all', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const pending1 = orphanItem(1)
    vm.list = [pending1]
    vm.total = 30
    vm.listQuery.status = 'pending'
    vm.handleOrphanSelectionChange([pending1])

    await vm.handleCleanupPreview()

    expect(mockCleanupPreview).toHaveBeenCalledWith({
      scan_id: 'scan-completed',
      orphan_ids: [1]
    })
    expect(vm.previewSelection).toEqual({ orphan_ids: [1] })
  })

  it('自定义单次加载数量超过上限时自动限制为 1000', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.applyPageSizeSelection(5000)
    await flushLifecycle()

    expect(vm.listQuery.page_size).toBe(1000)
    expect(vm.pageSizeInput).toBe('1000')
    expect(message.info).toHaveBeenCalledWith('单次最多加载 1000 条，已自动调整')
    expect(mockGetOrphanList).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, page_size: 1000 })
    )
  })

  it('置信度筛选会透传到列表查询并从第一页重新加载', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.listQuery.confidence = 'low'
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(scanContext(), [orphanItem(7)], 1, 1)
    )

    vm.handleFilter()
    await flushLifecycle()

    expect(mockGetOrphanList).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      downloader_id: undefined,
      path_like: undefined,
      status: undefined,
      min_size: undefined,
      confidence: 'low'
    })
    expect(vm.list.map((item) => item.id)).toEqual([7])
    expect(vm.listQuery.page).toBe(1)
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
    vm.listQuery.confidence = 'low'
    vm.listQuery.min_size = 1024
    vm.handleResetFilter()

    expect(vm.listQuery.path_like).toBe('')
    expect(vm.listQuery.status).toBe('')
    expect(vm.listQuery.confidence).toBe('')
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
        failed_list: []
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

  it('忽视全部失败时展示后端逐项失败原因而不是成功提示', async() => {
    mockSetIgnored.mockResolvedValueOnce({
      code: '200',
      msg: '忽视完成: 成功 0 个，失败 1 个',
      status: 'success',
      data: {
        success_count: 0,
        failed_count: 1,
        failed_list: [
          {
            id: 1,
            file_path: '/data/1.bin',
            reason: '当前候选状态不存在或已失效'
          }
        ]
      }
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    await vm.handleRowIgnore(orphanItem(1), true)

    expect(message.error).toHaveBeenCalledWith(
      '忽视失败：当前候选状态不存在或已失效'
    )
    expect(message.success).not.toHaveBeenCalled()
  })

  it('忽视部分失败时展示成功数、失败数和后端原因', async() => {
    mockSetIgnored.mockResolvedValueOnce({
      code: '200',
      msg: '忽视完成: 成功 1 个，失败 1 个',
      status: 'success',
      data: {
        success_count: 1,
        failed_count: 1,
        failed_list: [{ id: 2, reason: '候选已进入清理流程' }]
      }
    })
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    await vm.handleRowIgnore(orphanItem(1), true)

    expect(message.warning).toHaveBeenCalledWith(
      '忽视部分完成：成功 1 个，失败 1 个；候选已进入清理流程'
    )
    expect(message.success).not.toHaveBeenCalled()
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

describe('orphan files quick action (prefix match)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  function prefixPreviewSuccess(
    count = 3,
    totalSize = 600,
    lowConfidenceCount = 0
  ): ApiResponse<PrefixMatchPreviewResult> {
    return {
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        count,
        total_size: totalSize,
        low_confidence_count: lowConfidenceCount,
        sample_paths: ['/data/leak/a.bin', '/data/leak/b.bin', '/data/leak/c.bin']
      }
    }
  }

  function prefixPreviewRejected(reason: string): ApiResponse<PrefixMatchPreviewResult> {
    return {
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        rejected: true,
        reason,
        count: 0,
        total_size: 0,
        low_confidence_count: 0,
        sample_paths: []
      }
    }
  }

  it('handleQuickAction 打开对话框并重置前缀', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.quickActionPrefix = '旧前缀'

    vm.handleQuickAction('cleanup')

    expect(vm.quickActionType).toBe('cleanup')
    expect(vm.quickActionPrefix).toBe('')
    expect(vm.quickActionDialogVisible).toBe(true)
  })

  it('handleQuickActionCancel 关闭对话框', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.quickActionDialogVisible = true

    vm.handleQuickActionCancel()

    expect(vm.quickActionDialogVisible).toBe(false)
  })

  it('空前缀提示警告且不发起请求', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('ignore')
    vm.quickActionPrefix = '   '

    await vm.handleQuickActionConfirm()

    expect(message.warning).toHaveBeenCalledWith('请输入路径前缀')
    expect(mockPrefixMatchPreview).not.toHaveBeenCalled()
  })

  it('无成功扫描批次时提示且不发起请求', async() => {
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(
        scanContext({ display_scan: null, cleanup_allowed: false }),
        [],
        0
      )
    )
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('ignore')
    vm.quickActionPrefix = '/data/'

    await vm.handleQuickActionConfirm()

    expect(message.warning).toHaveBeenCalledWith('当前无可用的成功扫描批次，无法按前缀操作')
    expect(mockPrefixMatchPreview).not.toHaveBeenCalled()
  })

  it('preview rejected(scan 过期)提示原因并保留对话框', async() => {
    mockPrefixMatchPreview.mockResolvedValueOnce(
      prefixPreviewRejected('最新扫描已完成新批次，当前快照已过期')
    )
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('cleanup')
    vm.quickActionPrefix = '/data/leak/'

    await vm.handleQuickActionConfirm()

    expect(mockPrefixMatchPreview).toHaveBeenCalledWith({
      path_prefix: '/data/leak/',
      scan_id: 'scan-completed'
    })
    expect(message.error).toHaveBeenCalledWith('最新扫描已完成新批次，当前快照已过期')
    expect(vm.quickActionDialogVisible).toBe(true)
    expect(vm.quickActionLoading).toBe(false)
  })

  it('命中数为 0 时提示无匹配且保留对话框', async() => {
    mockPrefixMatchPreview.mockResolvedValueOnce(prefixPreviewSuccess(0))
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('ignore')
    vm.quickActionPrefix = '/data/none/'

    await vm.handleQuickActionConfirm()

    expect(message.warning).toHaveBeenCalledWith('没有匹配的待清理文件')
    expect(mockSetIgnored).not.toHaveBeenCalled()
    expect(vm.quickActionDialogVisible).toBe(true)
  })

  it('快捷删除：preview→二次确认→cleanupOrphans 用 select_all+path_prefix+pending', async() => {
    mockPrefixMatchPreview.mockResolvedValueOnce(prefixPreviewSuccess(5, 1500))
    mockCleanupOrphans.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        task_id: 'cleanup-task-abc12345',
        operation_type: 'cleanup',
        status: 'pending',
        scan_id: 'scan-completed',
        total_count: 5,
        success_count: 0,
        purged_count: 0,
        failed_count: 0,
        failed_list: [],
        total_size: 1500,
        error_message: null,
        created_at: '2026-08-04T10:00:00',
        started_at: null,
        completed_at: null
      }
    })
    mockGetOrphanList.mockResolvedValueOnce(listResponse())
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('cleanup')
    vm.quickActionPrefix = '/data/leak/'

    await vm.handleQuickActionConfirm()

    // 选择载荷必须带 scan_id + select_all + filters(path_prefix + status=pending)
    expect(mockCleanupOrphans).toHaveBeenCalledTimes(1)
    const call = mockCleanupOrphans.mock.calls[0][0]
    expect(call.scan_id).toBe('scan-completed')
    expect(call.select_all).toBe(true)
    expect(call.filters).toEqual({ path_prefix: '/data/leak/', status: 'pending' })
    // 未携带 orphan_ids（避免与 select_all 混淆）
    expect(call.orphan_ids).toBeUndefined()
    // 成功提示与关闭弹窗 + 刷新
    expect(message.success).toHaveBeenCalledWith(
      '主动清理任务已提交（cleanup-），完成或失败后将在通知中心提醒'
    )
    expect(vm.quickActionDialogVisible).toBe(false)
    expect(mockGetOrphanList).toHaveBeenCalled()
  })

  it('快捷删除含低置信度时二次确认文案带警告但仍执行', async() => {
    mockPrefixMatchPreview.mockResolvedValueOnce(prefixPreviewSuccess(5, 500, 2))
    mockCleanupOrphans.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        task_id: 'cleanup-low-conf',
        operation_type: 'cleanup',
        status: 'pending',
        scan_id: 'scan-completed',
        total_count: 5,
        success_count: 0,
        purged_count: 0,
        failed_count: 0,
        failed_list: [],
        total_size: 500,
        error_message: null,
        created_at: '2026-08-04T10:00:00',
        started_at: null,
        completed_at: null
      }
    })
    mockGetOrphanList.mockResolvedValueOnce(listResponse())
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('cleanup')
    vm.quickActionPrefix = '/data/leak/'

    await vm.handleQuickActionConfirm()

    // $confirm 被调用且文案含低置信度警告
    expect(confirm).toHaveBeenCalledTimes(1)
    const confirmText = String(confirm.mock.calls[0][0])
    expect(confirmText).toContain('将影响 5 个待清理文件')
    expect(confirmText).toContain('其中 2 个为低置信度')
    // 仍提交任务
    expect(mockCleanupOrphans).toHaveBeenCalledTimes(1)
  })

  it('快捷忽视：跳过 applyIgnore 直接调 setIgnored(不双重确认)', async() => {
    mockPrefixMatchPreview.mockResolvedValueOnce(prefixPreviewSuccess(2))
    mockSetIgnored.mockResolvedValueOnce({
      code: '200',
      msg: '忽视完成: 成功 2 个',
      status: 'success',
      data: {
        success_count: 2,
        failed_count: 0,
        failed_list: []
      }
    })
    mockGetOrphanList.mockResolvedValueOnce(listResponse())
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('ignore')
    vm.quickActionPrefix = '/data/leak/'

    await vm.handleQuickActionConfirm()

    // 只有一次 $confirm（二次确认），applyIgnore 的内置确认不被触发
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(mockSetIgnored).toHaveBeenCalledTimes(1)
    const call = mockSetIgnored.mock.calls[0][0]
    expect(call.ignored).toBe(true)
    expect(call.scan_id).toBe('scan-completed')
    expect(call.select_all).toBe(true)
    expect(call.filters).toEqual({ path_prefix: '/data/leak/', status: 'pending' })
    expect(message.success).toHaveBeenCalledWith('忽视完成：成功 2 个')
    expect(vm.quickActionDialogVisible).toBe(false)
  })

  it('快捷忽视部分失败时展示成功数/失败数/原因', async() => {
    mockPrefixMatchPreview.mockResolvedValueOnce(prefixPreviewSuccess(2))
    mockSetIgnored.mockResolvedValueOnce({
      code: '200',
      msg: '忽视完成: 成功 1 个，失败 1 个',
      status: 'success',
      data: {
        success_count: 1,
        failed_count: 1,
        failed_list: [{ id: 9, reason: '候选已进入清理流程' }]
      }
    })
    mockGetOrphanList.mockResolvedValueOnce(listResponse())
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('ignore')
    vm.quickActionPrefix = '/data/leak/'

    await vm.handleQuickActionConfirm()

    expect(message.warning).toHaveBeenCalledWith(
      '忽视部分完成：成功 1 个，失败 1 个；候选已进入清理流程'
    )
    expect(message.success).not.toHaveBeenCalled()
  })

  it('用户取消二次确认时复位 loading 且保留对话框与前缀', async() => {
    mockPrefixMatchPreview.mockResolvedValueOnce(prefixPreviewSuccess(3))
    const cancelConfirm = jest.fn(() => Promise.reject(new Error('cancel')))
    const wrapper = shallowMount(OrphanFiles, {
      localVue,
      mocks: { $message: message, $confirm: cancelConfirm },
      stubs: {
        'el-button': ButtonStub,
        'el-alert': AlertStub,
        'el-dialog': DialogStub,
        'el-table': TableStub,
        'el-table-column': TableColumnStub,
        'el-input': true,
        'el-pagination': true,
        'el-tag': true,
        'el-tabs': true,
        'el-tab-pane': true,
        'el-checkbox': true,
        'el-select': true,
        'el-option': true,
        'el-tooltip': true
      }
    })
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('cleanup')
    vm.quickActionPrefix = '/data/leak/'

    await vm.handleQuickActionConfirm()

    expect(mockCleanupOrphans).not.toHaveBeenCalled()
    expect(vm.quickActionLoading).toBe(false)
    expect(vm.quickActionDialogVisible).toBe(true)
    expect(vm.quickActionPrefix).toBe('/data/leak/')
  })

  it('cleanup 门禁关闭时快捷删除提示且不发请求', async() => {
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(
        scanContext({ cleanup_allowed: false, cleanup_block_reason: '最新扫描尚未完成' }),
        [orphanItem(1)],
        1
      )
    )
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.handleQuickAction('cleanup')
    vm.quickActionPrefix = '/data/leak/'

    await vm.handleQuickActionConfirm()

    expect(message.warning).toHaveBeenCalledWith('最新扫描尚未完成')
    expect(mockPrefixMatchPreview).not.toHaveBeenCalled()
    expect(mockCleanupOrphans).not.toHaveBeenCalled()
  })
})
