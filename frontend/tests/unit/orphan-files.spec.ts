import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import OrphanFiles from '@/views/orphan-files/index.vue'
import {
  ApiResponse,
  CleanupPreviewResult,
  HardlinkCopyLocationsResult,
  OrphanFileItem,
  OrphanFolderRow,
  OrphanListResponse,
  OrphanSelectionPayload,
  OrphanScanContext,
  OrphanScanRecord,
  OrphanTableRow,
  PrefixMatchPreviewResult,
  QuarantineItem,
  QuarantineListResult,
  cleanupOrphans,
  cleanupPreview,
  getHardlinkCopyLocations,
  getOrphanFolderChildren,
  getQuarantineList,
  getOrphanList,
  getScanStatus,
  prefixMatchPreview,
  purgeQuarantineNow,
  setIgnored,
  triggerScan,
  reviewScanGuardrail
} from '@/api/orphan-files'
import { copyTextToClipboard } from '@/utils/clipboard'

jest.mock('@/api/orphan-files', () => ({
  getLatestScan: jest.fn(),
  getOrphanList: jest.fn(),
  getOrphanFolderChildren: jest.fn(),
  triggerScan: jest.fn(),
  getScanStatus: jest.fn(),
  reviewScanGuardrail: jest.fn(),
  cleanupPreview: jest.fn(),
  cleanupOrphans: jest.fn(),
  getHardlinkCopyLocations: jest.fn(),
  setIgnored: jest.fn(),
  getQuarantineList: jest.fn(),
  purgeQuarantineNow: jest.fn(),
  prefixMatchPreview: jest.fn()
}))

jest.mock('@/utils/clipboard', () => ({
  copyTextToClipboard: jest.fn(() => Promise.resolve())
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
const mockGetOrphanFolderChildren = getOrphanFolderChildren as jest.MockedFunction<typeof getOrphanFolderChildren>
const mockTriggerScan = triggerScan as jest.MockedFunction<typeof triggerScan>
const mockGetScanStatus = getScanStatus as jest.MockedFunction<typeof getScanStatus>
const mockReviewScanGuardrail = reviewScanGuardrail as jest.MockedFunction<typeof reviewScanGuardrail>
const mockCleanupPreview = cleanupPreview as jest.MockedFunction<typeof cleanupPreview>
const mockCleanupOrphans = cleanupOrphans as jest.MockedFunction<typeof cleanupOrphans>
const mockGetHardlinkCopyLocations = getHardlinkCopyLocations as jest.MockedFunction<typeof getHardlinkCopyLocations>
const mockSetIgnored = setIgnored as jest.MockedFunction<typeof setIgnored>
const mockGetQuarantineList = getQuarantineList as jest.MockedFunction<typeof getQuarantineList>
const mockPurgeQuarantineNow = purgeQuarantineNow as jest.MockedFunction<typeof purgeQuarantineNow>
const mockPrefixMatchPreview = prefixMatchPreview as jest.MockedFunction<typeof prefixMatchPreview>
const mockCopyTextToClipboard = copyTextToClipboard as jest.MockedFunction<typeof copyTextToClipboard>

const clearSelection = jest.fn()
const TableStub = localVue.extend({
  props: {
    data: { type: Array, default: () => [] },
    height: { type: [String, Number], default: '' },
    showHeader: { type: Boolean, default: true }
  },
  methods: {
    clearSelection
  },
  computed: {
    listenerNames(): string {
      return Object.keys(this.$listeners).join(',')
    }
  },
  template: '<div class="orphan-table-stub" :data-height="height" :data-show-header="String(showHeader)" :data-row-count="String(data.length)" :data-listeners="listenerNames"><slot /></div>'
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
  // 多数历史用例使用扁平列表；文件夹行为由 tableData 单独覆盖。
  list: OrphanFileItem[]
  total: number
  listLoading: boolean
  scanLoading: boolean
  ignoreLoading: boolean
  pageSizeInput: string
  listQuery: {
    page: number
    page_size: number
    downloader_id: string[]
    path_like: string
    status: string[]
    confidence: string[]
  }
  statusFilterDegraded: boolean
  selectedIds: number[]
  selectedRows: OrphanTableRow[]
  selectedCount: number
  selectedFileIds: number[]
  selectedFileItems: OrphanFileItem[]
  folderView: boolean
  tableData: OrphanTableRow[]
  setFolderView: (val: boolean) => void
  getOrphanRowClassName: (payload: { row: OrphanTableRow }) => string
  handleFolderExpandChange: (row: OrphanTableRow, expanded: boolean) => void
  loadFolderChildren: (row: OrphanFolderRow) => Promise<void>
  handleFolderChildSelection: (row: OrphanFolderRow, items: OrphanFileItem[]) => void
  getRowKey: (row: OrphanTableRow) => string
  rowSelectable: (row: OrphanTableRow) => boolean
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
  hardlinkLocationDialogVisible: boolean
  hardlinkLocationLoading: boolean
  hardlinkLocationResult: HardlinkCopyLocationsResult | null
  refreshPageData: () => Promise<void>
  loadOrphanPage: (page: number) => Promise<void>
  handleOrphanPageChange: (page: number) => Promise<void>
  handleScan: () => Promise<void>
  stopScanPolling: () => void
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
  canOpenHardlinkLocations: (row: OrphanTableRow) => boolean
  handleHardlinkCopyClick: (row: OrphanTableRow) => Promise<void>
  copyHardlinkPath: (path: string) => Promise<void>
  formatHardlinkCopyCount: (count: number | null | undefined) => string
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
    details_mode: 'current',
    new_orphans: 2,
    known_orphans: 0,
    resolved_orphans: 0,
    cleanup_review_required: false,
    cleanup_reviewed_at: null,
    cleanup_reviewed_by: null,
    cleanup_review_note: null,
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

function orphanItem(
  id: number,
  scanId = 'scan-completed',
  overrides: Partial<OrphanFileItem> = {}
): OrphanFileItem {
  return {
    id,
    scan_id: scanId,
    file_path: `/data/${id}.bin`,
    file_size: id * 100,
    hardlink_copy_count: 0,
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
    created_at: '2026-07-30T10:00:00',
    ...overrides
  }
}

/** 构造后端 get_orphan_list_grouped 返回的 OrphanFolderRow（snake_case 对齐契约）。 */
function folderRow(
  folderPath: string,
  children: OrphanFileItem[],
  overrides: Partial<OrphanFolderRow> = {}
): OrphanFolderRow {
  const childIds = children.map((c) => c.id)
  const totalSize = children.reduce((s, c) => s + (c.file_size || 0), 0)
  const allDeleted = children.every((c) => c.is_deleted)
  const allIgnored = !allDeleted && children.every((c) => c.is_ignored)
  const allPending = !allDeleted && !allIgnored && children.every((c) => !c.is_deleted && !c.is_ignored)
  const hardlinkCopyCount = children.every((c) => c.hardlink_copy_count !== null)
    ? children.reduce((sum, child) => sum + (child.hardlink_copy_count || 0), 0)
    : null
  return {
    _is_folder: true,
    folder_key: 'folder:' + folderPath,
    folder_path: folderPath,
    child_count: children.length,
    children,
    child_ids: childIds,
    children_loaded: children.length > 0,
    children_loading: false,
    child_page: 1,
    child_page_size: 20,
    child_total: children.length,
    total_size: totalSize,
    hardlink_copy_count: hardlinkCopyCount,
    latest_mtime: children[0]?.mtime ?? null,
    downloader_name: children[0]?.downloader_name ?? null,
    all_pending: allPending,
    all_ignored: allIgnored,
    all_deleted: allDeleted,
    has_low_confidence: children.some((c) => c.confidence === 'low'),
    ...overrides
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
    purge_delay_count: 0,
    file_size: 2048,
    confidence: 'high'
  }
}

function listResponse(
  context: OrphanScanContext = scanContext(),
  list: OrphanTableRow[] = [orphanItem(1), orphanItem(2)],
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

function hardlinkLocationsResponse(
  data: HardlinkCopyLocationsResult
): ApiResponse<HardlinkCopyLocationsResult> {
  return {
    code: '200',
    msg: 'ok',
    status: 'success',
    data
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
      'el-tooltip': true,
      AdvancedMultiSelect: true
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
    mockGetOrphanFolderChildren.mockResolvedValue({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: { total: 0, page: 1, pageSize: 20, list: [] }
    })
    mockTriggerScan.mockResolvedValue({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        scan_id: 'scan-completed',
        task_id: 'scan-completed',
        status: 'queued',
        accepted: true
      }
    })
    mockGetScanStatus.mockResolvedValue({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: scanRecord()
    })
    mockReviewScanGuardrail.mockResolvedValue({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: scanRecord({ cleanup_review_required: true, cleanup_reviewed_at: '2026-08-13T10:00:00' })
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
    expect(mockGetQuarantineList).toHaveBeenCalledTimes(1)
  })

  it('隔离文件全部处理中时提示并刷新，不伪造新任务号', async() => {
    mockPurgeQuarantineNow.mockResolvedValueOnce({
      code: '200',
      msg: '所选隔离文件均已在彻底删除任务中处理',
      status: 'success',
      data: {
        task_id: null,
        status: 'already_running',
        total_count: 0,
        requested_count: 1,
        accepted_count: 0,
        skipped_count: 1,
        skipped_items: ['/data/quarantine.bin'],
        purged_count: 0,
        failed_count: 0,
        failed_list: [],
        error_message: null,
        created_at: null,
        started_at: null,
        completed_at: null
      }
    })
    const wrapper = mountView()
    await flushLifecycle()
    mockGetQuarantineList.mockClear()
    const vm = viewModel(wrapper)
    vm.quarantineSelected = [quarantineItem()]

    await vm.handleQuarantinePurge()

    expect(message.info).toHaveBeenCalledWith(
      '所选隔离文件均已在彻底删除任务中处理'
    )
    expect(message.success).not.toHaveBeenCalled()
    expect(mockGetQuarantineList).toHaveBeenCalledTimes(1)
    expect(vm.quarantineSelected).toEqual([])
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
    vm.listQuery.downloader_id = ['dl-filter']
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
      confidence: undefined
    })
    expect(vm.listQuery).toEqual({
      page: 1,
      page_size: 50,
      downloader_id: ['dl-filter'],
      path_like: '',
      status: [],
      confidence: []
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
    mockGetScanStatus.mockResolvedValue({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: running
    })

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

  it('主动清理项全部处理中时关闭弹窗并立即刷新可用列表', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.selectedRows = [orphanItem(1)]
    await vm.handleCleanupPreview()
    mockGetOrphanList.mockClear()
    mockCleanupOrphans.mockResolvedValueOnce({
      code: '200',
      msg: '所选孤儿文件均已在主动清理任务中处理',
      status: 'success',
      data: {
        task_id: null,
        operation_type: 'cleanup',
        status: 'already_running',
        scan_id: 'scan-completed',
        total_count: 0,
        requested_count: 1,
        accepted_count: 0,
        skipped_count: 1,
        skipped_items: [1],
        success_count: 0,
        purged_count: 0,
        failed_count: 0,
        failed_list: [],
        total_size: 0,
        error_message: null,
        created_at: null,
        started_at: null,
        completed_at: null
      }
    })

    await vm.handleCleanupConfirm()

    expect(message.info).toHaveBeenCalledWith(
      '所选孤儿文件均已在主动清理任务中处理'
    )
    expect(message.success).not.toHaveBeenCalled()
    expect(vm.cleanupDialogVisible).toBe(false)
    expect(mockGetOrphanList).toHaveBeenCalledTimes(1)
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
      [{ page: 2, page_size: 20, downloader_id: undefined, path_like: undefined, status: undefined }],
      [{ page: 3, page_size: 20, downloader_id: undefined, path_like: undefined, status: undefined }]
    ])
  })

  it('扫描触发立即返回 queued 并开始轻量状态轮询', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    mockTriggerScan.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        scan_id: 'scan-running',
        task_id: 'scan-running',
        status: 'queued',
        accepted: false
      }
    })
    const persistedRunning = scanRecord({
      scan_id: 'scan-running',
      status: 'running'
    })
    mockGetScanStatus.mockResolvedValueOnce({ code: '200', msg: 'ok', status: 'success', data: persistedRunning })

    await vm.handleScan()
    await Promise.resolve()

    expect(message.success).toHaveBeenCalledWith('已有扫描任务，继续跟踪其状态')
    expect(mockGetOrphanList).toHaveBeenCalledTimes(2)
    expect(mockGetScanStatus).toHaveBeenCalledWith('scan-running')
    expect(vm.scanLoading).toBe(true)
    vm.stopScanPolling()
    expect(vm.scanLoading).toBe(false)
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
      status: undefined
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
    vm.listQuery.status = ['pending']

    // el-table 的 :selectable=rowSelectable 保证 deleted 行不可选，
    // 故 selection-change 只回调可选行
    vm.handleOrphanSelectionChange([pending1, pending3])

    expect(vm.selectedFileIds).toEqual([1, 3])
    expect(vm.selectedCount).toBe(2)

    // 取消选中其中一行
    vm.handleOrphanSelectionChange([pending3])

    expect(vm.selectedCount).toBe(1)
    expect(vm.selectedFileIds).toEqual([3])
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

    expect(vm.selectedFileIds).toEqual([1, 2])
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
    vm.listQuery.status = ['pending']
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
    vm.listQuery.status = ['pending']
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
    vm.listQuery.confidence = ['low']
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
    vm.listQuery.status = ['ignored']
    vm.listQuery.confidence = ['low']
    vm.handleResetFilter()

    expect(vm.listQuery.path_like).toBe('')
    expect(vm.listQuery.status).toEqual([])
    expect(vm.listQuery.confidence).toEqual([])
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


// ============================================================================
// 按文件夹展示（后端聚合分页）：删除仍按文件，仅展示折叠
// 覆盖：消费后端 folder row / 选择联动（含反向同步）/ 持久化 / 扁平模式回归
// ============================================================================

describe('orphan files folder view (consume backend folder rows)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    mockGetOrphanList.mockResolvedValue(listResponse())
  })

  it('默认扁平模式：folderView=false，tableData 直接返回 list', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    expect(vm.folderView).toBe(false)
    expect(vm.tableData).toBe(vm.list)
  })

  it('折叠模式：tableData 消费后端返回的混合 list（folder row + 单文件）', async() => {
    const folderChildren = [
      orphanItem(1, 'scan-completed', { file_path: '/data/movie/a.mp4', file_size: 100 }),
      orphanItem(2, 'scan-completed', { file_path: '/data/movie/b.mp4', file_size: 200 })
    ]
    const single = orphanItem(3, 'scan-completed', { file_path: '/data/alone.mp4', file_size: 50 })
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(scanContext(), [folderRow('/data/movie', folderChildren), single], 2)
    )
    localStorage.setItem('btdeck_orphan_folder_view', '1')
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    expect(vm.folderView).toBe(true)
    expect(vm.tableData).toHaveLength(2)
    // 第一项是文件夹行
    const folder = vm.tableData[0] as OrphanFolderRow
    expect(folder._is_folder).toBe(true)
    expect(folder.folder_path).toBe('/data/movie')
    expect(folder.child_count).toBe(2)
    expect(folder.child_ids).toEqual([1, 2])
    expect(folder.total_size).toBe(300)
    // 第二项是单文件（原样 OrphanFileItem，无 _is_folder）
    const fileItem = vm.tableData[1] as OrphanFileItem
    expect((fileItem as unknown as { _is_folder?: boolean })._is_folder).toBeUndefined()
    expect(fileItem.id).toBe(3)
  })

  it('getRowKey：文件夹行用 folder_key，文件行用 file: 前缀', async() => {
    const folderChildren = [
      orphanItem(1, 'scan-completed', { file_path: '/data/m/a' }),
      orphanItem(2, 'scan-completed', { file_path: '/data/m/b' })
    ]
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(scanContext(), [folderRow('/data/m', folderChildren)], 1)
    )
    localStorage.setItem('btdeck_orphan_folder_view', '1')
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    const folder = vm.tableData[0] as OrphanFolderRow
    expect(vm.getRowKey(folder)).toBe('folder:/data/m')
    expect(vm.getRowKey(folder.children[0])).toBe('file:1')
  })
})

describe('orphan files folder view (selection linkage)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    const folderChildren = [
      orphanItem(1, 'scan-completed', { file_path: '/data/m/a', file_size: 100 }),
      orphanItem(2, 'scan-completed', { file_path: '/data/m/b', file_size: 200 })
    ]
    mockGetOrphanList.mockResolvedValue(
      listResponse(scanContext(), [folderRow('/data/m', folderChildren)], 1)
    )
  })

  it('文件夹首次展开后才请求独立分页子项', async() => {
    localStorage.setItem('btdeck_orphan_folder_view', '1')
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const folder = vm.tableData[0] as OrphanFolderRow
    const children = [...folder.children]
    folder.children = []
    folder.child_ids = []
    folder.children_loaded = false
    mockGetOrphanFolderChildren.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: { total: 2, page: 1, pageSize: 20, list: children }
    })

    await vm.loadFolderChildren(folder)

    expect(mockGetOrphanFolderChildren).toHaveBeenCalledWith(expect.objectContaining({
      folder_path: '/data/m',
      page: 1,
      page_size: 20
    }))
    expect(folder.children.map((item) => item.id)).toEqual([1, 2])
    expect(folder.children_loaded).toBe(true)
  })

  it('展开事件只为未加载文件夹请求子项，普通文件不会触发子项请求', async() => {
    const child = orphanItem(3, 'scan-completed', { file_path: '/data/movie/c.mp4' })
    const folder = folderRow('/data/movie', [], {
      child_count: 1,
      child_ids: [],
      children_loaded: false,
      child_total: 1
    })
    const single = orphanItem(4, 'scan-completed', { file_path: '/data/alone.mp4' })
    mockGetOrphanList.mockResolvedValueOnce(listResponse(scanContext(), [folder, single], 2))
    mockGetOrphanFolderChildren.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: { total: 1, page: 1, pageSize: 20, list: [child] }
    })
    localStorage.setItem('btdeck_orphan_folder_view', '1')
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const rows = vm.tableData
    const loadedFolder = rows[0] as OrphanFolderRow
    const visibleFile = rows[1] as OrphanFileItem

    vm.handleFolderExpandChange(visibleFile, true)
    await flushLifecycle()
    expect(mockGetOrphanFolderChildren).not.toHaveBeenCalled()

    vm.handleFolderExpandChange(loadedFolder, true)
    await flushLifecycle()
    expect(mockGetOrphanFolderChildren).toHaveBeenCalledTimes(1)
    expect(loadedFolder.children.map((item) => item.id)).toEqual([3])
  })

  it('选择只包含当前可见且明确勾选的子文件', async() => {
    localStorage.setItem('btdeck_orphan_folder_view', '1')
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const folder = vm.tableData[0] as OrphanFolderRow

    vm.handleFolderChildSelection(folder, [folder.children[0]])
    expect(vm.selectedFileIds).toEqual([1])
    expect(vm.selectedFileItems.map((item) => item.id)).toEqual([1])
  })

  it('文件夹父行永远不可选择，避免隐式提交未加载子项', async() => {
    localStorage.setItem('btdeck_orphan_folder_view', '1')
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const folder = vm.tableData[0] as OrphanFolderRow

    expect(vm.rowSelectable(folder)).toBe(false)
  })

  it('rowSelectable：文件夹行和已清理文件不可选', async() => {
    const deletedChildren = [
      orphanItem(1, 'scan-completed', { file_path: '/data/m/a', is_deleted: true }),
      orphanItem(2, 'scan-completed', { file_path: '/data/m/b', is_deleted: true })
    ]
    mockGetOrphanList.mockResolvedValueOnce(
      listResponse(scanContext(), [folderRow('/data/m', deletedChildren), orphanItem(3, 'scan-completed', { is_deleted: true })], 2)
    )
    localStorage.setItem('btdeck_orphan_folder_view', '1')
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    const folder = vm.tableData[0] as OrphanFolderRow
    expect(vm.rowSelectable(folder)).toBe(false)
    expect(vm.rowSelectable(vm.list[1] as OrphanTableRow)).toBe(false)
  })
})

describe('orphan files folder view (persistence + regression)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    mockGetOrphanList.mockResolvedValue(listResponse())
  })

  it('setFolderView 持久化到 localStorage', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)

    vm.setFolderView(true)
    expect(vm.folderView).toBe(true)
    expect(localStorage.getItem('btdeck_orphan_folder_view')).toBe('1')

    vm.setFolderView(false)
    expect(localStorage.getItem('btdeck_orphan_folder_view')).toBe('0')
  })

  it('从 localStorage 恢复 folderView 偏好', async() => {
    localStorage.setItem('btdeck_orphan_folder_view', '1')
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    expect(vm.folderView).toBe(true)
  })

  it('扁平模式回归：selectedIds/selectedCount 行为不变', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    expect(vm.folderView).toBe(false)
    vm.selectedRows = [vm.list[0]]
    expect(vm.selectedIds).toEqual([1])
    expect(vm.selectedCount).toBe(1)
    expect(vm.selectedFileIds).toEqual([1])
  })

  it('扁平模式回归：tableData 不含文件夹行，getRowKey 文件行用 file: 前缀', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    expect(vm.tableData).toBe(vm.list)
    expect((vm.tableData as OrphanTableRow[]).every((r) => (r as unknown as { _is_folder?: boolean })._is_folder !== true)).toBe(true)
    expect(vm.getRowKey(vm.list[0])).toBe('file:1')
  })

  it('只有文件夹模式注册展开列，扁平模式不显示展开入口', async() => {
    const flatWrapper = mountView()
    await flushLifecycle()

    expect(flatWrapper.findAll('[data-column-type="expand"]')).toHaveLength(0)
    flatWrapper.destroy()

    localStorage.setItem('btdeck_orphan_folder_view', '1')
    const folderWrapper = mountView()
    await flushLifecycle()

    expect(folderWrapper.findAll('[data-column-type="expand"]')).toHaveLength(1)
  })

  it('切换展示模式时展开列随 folderView 动态增删', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    const expandColumns = () => wrapper.findAll('[data-column-type="expand"]')

    expect(expandColumns()).toHaveLength(0)

    vm.setFolderView(true)
    await flushLifecycle()
    expect(expandColumns()).toHaveLength(1)
    expect(localStorage.getItem('btdeck_orphan_folder_view')).toBe('1')

    vm.setFolderView(false)
    await flushLifecycle()
    expect(expandColumns()).toHaveLength(0)
    expect(localStorage.getItem('btdeck_orphan_folder_view')).toBe('0')
  })
})

/**
 * 文件夹聚合行渲染契约回归。
 *
 * 保护本轮三处模板/CSS 修复：
 * 1. 文件路径列透传 class-name="orphan-path-cell"（让 .cell 成为横向 flex 容器，
 *    与树展开箭头同水平线对齐）
 * 2. 文件夹行渲染 .orphan-folder-cell（图标 + __path + __count），
 *    路径过长时 __path 收缩显示省略号，「N 个文件」标签始终可见（不被挤出可视区）
 * 3. __path 绑定 :title=folder_path，hover 显示完整路径（替代被嵌套结构干扰的原生 tooltip）
 *
 * 既有 TableColumnStub 把 slot 的 row 硬编码为 quarantineItem()，无法覆盖文件夹行
 * 模板分支，故此处用按注入 rows 多行渲染的本地 column stub。
 * jsdom 不计算 CSS（flex/省略号不可直接断言），改为严格校验模板结构契约。
 */
describe('orphan files folder view (folder row rendering contract)', () => {
  /**
   * 按注入 rows 多行渲染 scoped slot 的列 stub：
   * - 透传 class-name 到根元素，用于校验列级 class-name 透传
   * - 对每一行调用默认 scoped slot，使文件夹行分支（_is_folder）与单文件分支都能渲染
   *
   * shallowMount 下 el-table 被 stub，列组件的 $parent 是 TableStub 而非 OrphanFiles，
   * 故向上遍历原型链找到带 tableData 的实例（即 OrphanFiles 根组件 vm）。
   */
  const FolderColumnStub = localVue.extend({
    props: {
      type: { type: String, default: '' },
      prop: { type: String, default: '' },
      label: { type: String, default: '' },
      className: { type: String, default: '' }
    },
    render(createElement) {
      let parent: unknown = this.$parent
      let rows: OrphanTableRow[] = []
      while (parent) {
        const maybe = parent as { tableData?: OrphanTableRow[] }
        if (maybe && Array.isArray(maybe.tableData)) {
          rows = maybe.tableData
          break
        }
        parent = (parent as { $parent?: unknown }).$parent
      }
      const slot = this.$scopedSlots.default
      const children = slot ? rows.map((row) => slot({ row })) : []
      return createElement(
        'div',
        {
          class: this.className,
          attrs: {
            'data-column-type': this.type,
            'data-column-label': this.label
          }
        },
        children
      )
    }
  })

  function mountFolderView(rows: OrphanTableRow[]): Wrapper<Vue> {
    mockGetOrphanList.mockResolvedValueOnce(listResponse(scanContext(), rows, rows.length))
    localStorage.setItem('btdeck_orphan_folder_view', '1')
    return shallowMount(OrphanFiles, {
      localVue,
      mocks: { $message: message, $confirm: confirm },
      stubs: {
        'el-button': ButtonStub,
        'el-alert': AlertStub,
        'el-dialog': DialogStub,
        'el-table': TableStub,
        'el-table-column': FolderColumnStub,
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

  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
  })

  it('文件路径列透传 class-name="orphan-path-cell"（.cell 横向 flex 对齐锚点）', async() => {
    const children = [
      orphanItem(1, 'scan-completed', { file_path: '/data/movie/a.mp4' }),
      orphanItem(2, 'scan-completed', { file_path: '/data/movie/b.mp4' })
    ]
    const wrapper = mountFolderView([folderRow('/data/movie', children)])
    await flushLifecycle()

    // FolderColumnStub 把 class-name 渲染到列根元素；el-table-column 的 class-name 属性
    // 在真实 element-ui 中会落到 td.el-table__cell 上，这里只验证属性被组件正确透传。
    const pathColumn = wrapper.find('.orphan-path-cell')
    expect(pathColumn.exists()).toBe(true)
  })

  it('文件夹行渲染 .orphan-folder-cell 结构，__count 始终显示「N 个文件」且数量正确', async() => {
    const children = [
      orphanItem(1, 'scan-completed', { file_path: '/data/movie/a.mp4', file_size: 100 }),
      orphanItem(2, 'scan-completed', { file_path: '/data/movie/b.mp4', file_size: 200 }),
      orphanItem(3, 'scan-completed', { file_path: '/data/movie/c.mp4', file_size: 300 })
    ]
    const wrapper = mountFolderView([folderRow('/data/movie', children)])
    await flushLifecycle()

    const folderCell = wrapper.find('.orphan-folder-cell')
    expect(folderCell.exists()).toBe(true)
    // 文件夹图标
    expect(folderCell.find('.el-icon-folder').exists()).toBe(true)
    // 文件数标签（el-tag 被 stub，文本直接渲染）
    const countEl = folderCell.find('.orphan-folder-cell__count')
    expect(countEl.exists()).toBe(true)
    expect(countEl.text()).toContain('3')
    expect(countEl.text()).toContain('个文件')
  })

  it('文件夹路径过长：__path 显示省略号锚点（min-width:0 修复）并绑定 :title 显示完整路径', async() => {
    const longPath = '/downloads/complete/movies/2026/very-long-folder-name-that-overflows-the-cell-width/movie.mkv'
    const children = [
      orphanItem(1, 'scan-completed', { file_path: longPath + '/a.mp4' }),
      orphanItem(2, 'scan-completed', { file_path: longPath + '/b.mp4' })
    ]
    const wrapper = mountFolderView([folderRow(longPath, children)])
    await flushLifecycle()

    const pathEl = wrapper.find('.orphan-folder-cell__path')
    expect(pathEl.exists()).toBe(true)
    // 文本内容是完整路径（省略号是 CSS 渲染效果，jsdom 不计算；这里验证节点存在且文本为路径）
    expect(pathEl.text()).toBe(longPath)
    // :title 绑定完整路径，hover 可见（替代被嵌套结构破坏的列级 tooltip）
    expect(pathEl.attributes('title')).toBe(longPath)
    // 文件数标签仍存在（未被挤出 DOM 结构，jsdom 下无法验证可视性，但结构契约被锁定）
    expect(wrapper.find('.orphan-folder-cell__count').exists()).toBe(true)
  })

  it('单文件行不渲染 .orphan-folder-cell（仅文件夹行走聚合行结构）', async() => {
    const single = orphanItem(1, 'scan-completed', { file_path: '/data/alone.mp4' })
    const wrapper = mountFolderView([single])
    await flushLifecycle()

    // 单文件行不走文件夹聚合分支
    expect(wrapper.find('.orphan-folder-cell').exists()).toBe(false)
    // 但仍渲染在路径列中（FolderColumnStub 按行渲染 slot）
    const pathColumn = wrapper.find('.orphan-path-cell')
    expect(pathColumn.exists()).toBe(true)
    expect(pathColumn.text()).toContain('/data/alone.mp4')
    // 文件夹模式虽然保留主表展开列，但普通文件行不能产生展开内容。
    expect(wrapper.find('.orphan-folder-children').exists()).toBe(false)
    expect(wrapper.findAll('.orphan-folder-children .orphan-table-stub')).toHaveLength(0)
  })

  it('展开行 class 只标记文件夹，普通文件保持可被箭头隐藏的普通行 class', async() => {
    const children = [orphanItem(1, 'scan-completed', { file_path: '/data/movie/a.mp4' })]
    const folder = folderRow('/data/movie', children)
    const single = orphanItem(2, 'scan-completed', { file_path: '/data/alone.mp4' })
    const wrapper = mountFolderView([folder, single])
    await flushLifecycle()
    const vm = viewModel(wrapper)

    expect(vm.getOrphanRowClassName({ row: folder })).toBe('orphan-folder-row')
    expect(vm.getOrphanRowClassName({ row: single })).toBe('')
  })

  it('文件夹展开子表隐藏重复表头', async() => {
    const children = [
      orphanItem(1, 'scan-completed', { file_path: '/data/movie/a.mp4' }),
      orphanItem(2, 'scan-completed', { file_path: '/data/movie/b.mp4' })
    ]
    const wrapper = mountFolderView([folderRow('/data/movie', children)])
    await flushLifecycle()

    const tables = wrapper.findAll('.orphan-table-stub')
    expect(tables.length).toBeGreaterThan(1)
    expect(tables.at(0).attributes('data-show-header')).toBe('true')
    expect(tables.at(1).attributes('data-show-header')).toBe('false')
    expect(tables.at(1).attributes('data-row-count')).toBe('2')
    expect(tables.at(1).attributes('data-listeners')).toContain('selection-change')
    expect(tables.at(1).find('[data-column-type="selection"]').exists()).toBe(true)
  })

  it('副本数量列只显示可见文件数值，文件夹父行不汇总未加载子项', async() => {
    const children = [
      orphanItem(1, 'scan-completed', { hardlink_copy_count: 2 }),
      orphanItem(2, 'scan-completed', { hardlink_copy_count: 0 })
    ]
    const zeroCopyFile = orphanItem(3, 'scan-completed', { hardlink_copy_count: 0 })
    const lazyFolder = folderRow('/data/movie', children, {
      children: [],
      child_ids: [],
      children_loaded: false,
      hardlink_copy_count: null
    })
    const wrapper = mountFolderView([lazyFolder, zeroCopyFile])
    await flushLifecycle()

    const countColumn = wrapper.find('[data-column-label="副本数量"]')
    expect(countColumn.exists()).toBe(true)
    const values = countColumn.findAll('.orphan-hardlink-copy-count')
    // 渲染 stub 只展开首个父行；真实懒加载目录父行不做硬链接 stat，也不显示汇总值。
    expect(values).toHaveLength(0)
  })

  it('仅有副本的数量可点击，文件夹行只查询有副本的子文件并展示位置', async() => {
    const linked = orphanItem(1, 'scan-completed', { hardlink_copy_count: 2 })
    const solo = orphanItem(2, 'scan-completed', { hardlink_copy_count: 0 })
    const configuredCopy = '/library/movies/linked-copy.mkv'
    mockGetHardlinkCopyLocations.mockResolvedValueOnce({
      code: '200',
      msg: 'ok',
      status: 'success',
      data: {
        requested_count: 1,
        resolved_count: 1,
        missing_orphan_ids: [],
        total_copy_count: 2,
        total_found_count: 1,
        total_unlocated_count: 1,
        unknown_count: 0,
        searched_root_count: 2,
        search_error: null,
        items: [{
          orphan_id: linked.id,
          file_path: linked.file_path,
          copy_count: 2,
          found_count: 1,
          unlocated_count: 1,
          copies: [configuredCopy],
          error: null
        }]
      }
    })
    const wrapper = mountFolderView([folderRow('/data/movie', [linked, solo]), solo])
    await flushLifecycle()

    const countColumn = wrapper.find('[data-column-label="副本数量"]')
    const links = countColumn.findAll('button.orphan-hardlink-copy-count--link')
    expect(links).toHaveLength(1)
    expect(links.at(0).text()).toBe('2')

    await links.at(0).trigger('click')
    await flushLifecycle()

    expect(mockGetHardlinkCopyLocations).toHaveBeenCalledWith({ orphan_ids: [linked.id] })
    expect(viewModel(wrapper).hardlinkLocationDialogVisible).toBe(true)
    expect(wrapper.find('.hardlink-location-summary').text()).toContain('已定位 1')
    expect(wrapper.find('.hardlink-location-copy__path').text()).toBe(configuredCopy)
    expect(wrapper.text()).toContain('还有 1 个副本未在已配置目录中定位')

    await wrapper.find('.hardlink-location-copy__button').trigger('click')
    await flushLifecycle()
    expect(mockCopyTextToClipboard).toHaveBeenCalledWith(configuredCopy)
  })

  it('连续点击不同文件时只接受最后一次位置响应，旧响应不得覆盖弹框', async() => {
    const first = orphanItem(1, 'scan-completed', { hardlink_copy_count: 1 })
    const second = orphanItem(2, 'scan-completed', { hardlink_copy_count: 1 })
    const firstRequest = deferred<ApiResponse<HardlinkCopyLocationsResult>>()
    const secondRequest = deferred<ApiResponse<HardlinkCopyLocationsResult>>()
    mockGetHardlinkCopyLocations
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise)

    const wrapper = mountFolderView([first, second])
    await flushLifecycle()
    const vm = viewModel(wrapper)

    const firstCall = vm.handleHardlinkCopyClick(first)
    const secondCall = vm.handleHardlinkCopyClick(second)
    expect(mockGetHardlinkCopyLocations).toHaveBeenNthCalledWith(1, { orphan_ids: [first.id] })
    expect(mockGetHardlinkCopyLocations).toHaveBeenNthCalledWith(2, { orphan_ids: [second.id] })

    secondRequest.resolve(hardlinkLocationsResponse({
      requested_count: 1,
      resolved_count: 1,
      missing_orphan_ids: [],
      total_copy_count: 1,
      total_found_count: 1,
      total_unlocated_count: 0,
      unknown_count: 0,
      searched_root_count: 1,
      search_error: null,
      items: [{
        orphan_id: second.id,
        file_path: second.file_path,
        copy_count: 1,
        found_count: 1,
        unlocated_count: 0,
        copies: ['/library/second-copy.bin'],
        error: null
      }]
    }))
    await secondCall
    await flushLifecycle()

    expect(vm.hardlinkLocationLoading).toBe(false)
    expect(vm.hardlinkLocationResult?.items[0].orphan_id).toBe(second.id)

    firstRequest.resolve(hardlinkLocationsResponse({
      requested_count: 1,
      resolved_count: 1,
      missing_orphan_ids: [],
      total_copy_count: 1,
      total_found_count: 1,
      total_unlocated_count: 0,
      unknown_count: 0,
      searched_root_count: 1,
      search_error: null,
      items: [{
        orphan_id: first.id,
        file_path: first.file_path,
        copy_count: 1,
        found_count: 1,
        unlocated_count: 0,
        copies: ['/library/first-copy.bin'],
        error: null
      }]
    }))
    await firstCall
    await flushLifecycle()

    expect(vm.hardlinkLocationResult?.items[0].orphan_id).toBe(second.id)
    expect(vm.hardlinkLocationLoading).toBe(false)
  })

  it('弹框同时提示扫描失败、源文件不可访问和已失效列表项', async() => {
    const linked = orphanItem(1, 'scan-completed', { hardlink_copy_count: 1 })
    const unavailable = orphanItem(2, 'scan-completed', { hardlink_copy_count: 1 })
    const removed = orphanItem(3, 'scan-completed', { hardlink_copy_count: 1 })
    const searchError = '已配置下载目录扫描失败，未能完整定位副本位置'
    mockGetHardlinkCopyLocations.mockResolvedValueOnce(hardlinkLocationsResponse({
      requested_count: 3,
      resolved_count: 2,
      missing_orphan_ids: [removed.id],
      total_copy_count: 1,
      total_found_count: 0,
      total_unlocated_count: 1,
      unknown_count: 1,
      searched_root_count: 2,
      search_error: searchError,
      items: [
        {
          orphan_id: linked.id,
          file_path: linked.file_path,
          copy_count: 1,
          found_count: 0,
          unlocated_count: 1,
          copies: [],
          error: searchError
        },
        {
          orphan_id: unavailable.id,
          file_path: unavailable.file_path,
          copy_count: null,
          found_count: 0,
          unlocated_count: null,
          copies: [],
          error: '源文件不可访问，无法重新核对副本位置'
        }
      ]
    }))
    const wrapper = mountFolderView([
      folderRow('/data/movie', [linked, unavailable, removed])
    ])
    await flushLifecycle()

    await wrapper.find('button.orphan-hardlink-copy-count--link').trigger('click')
    await flushLifecycle()

    expect(mockGetHardlinkCopyLocations).toHaveBeenCalledWith({
      orphan_ids: [linked.id, unavailable.id, removed.id]
    })
    expect(wrapper.text()).toContain(searchError)
    expect(wrapper.text()).toContain('1 个源文件当前不可访问，无法核对位置')
    expect(wrapper.text()).toContain('1 个列表项已失效，请刷新页面后重试')
    expect(wrapper.text()).toContain('源文件不可访问，无法重新核对副本位置')
  })

  it('位置查询异常后释放加载态并保留空结果', async() => {
    const linked = orphanItem(1, 'scan-completed', { hardlink_copy_count: 1 })
    mockGetHardlinkCopyLocations.mockRejectedValueOnce(new Error('storage offline'))
    const wrapper = mountFolderView([linked])
    await flushLifecycle()
    const vm = viewModel(wrapper)

    await vm.handleHardlinkCopyClick(linked)
    await flushLifecycle()

    expect(vm.hardlinkLocationLoading).toBe(false)
    expect(vm.hardlinkLocationResult).toBeNull()
    expect(message.error).toHaveBeenCalledWith(expect.stringContaining('storage offline'))
  })
})

describe('orphan files hardlink copy count formatting', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    mockGetOrphanList.mockResolvedValue(listResponse())
  })

  it('明确区分无副本 0 与文件不可访问的未知状态', async() => {
    const vm = viewModel(mountView())
    await flushLifecycle()

    expect(vm.formatHardlinkCopyCount(0)).toBe('0')
    expect(vm.formatHardlinkCopyCount(3)).toBe('3')
    expect(vm.formatHardlinkCopyCount(null)).toBe('-')
    expect(vm.formatHardlinkCopyCount(undefined)).toBe('-')
  })

  it('只有大于 0 的实时数量允许打开位置查询', async() => {
    const vm = viewModel(mountView())
    await flushLifecycle()

    expect(vm.canOpenHardlinkLocations(orphanItem(1, 'scan-completed', { hardlink_copy_count: 1 }))).toBe(true)
    expect(vm.canOpenHardlinkLocations(orphanItem(2, 'scan-completed', { hardlink_copy_count: 0 }))).toBe(false)
    expect(vm.canOpenHardlinkLocations(orphanItem(3, 'scan-completed', { hardlink_copy_count: null }))).toBe(false)
  })
})

// 回归保护：status 多选退化检测（pending 与 ignored/deleted 组合会扩大为全部未删除文件）
describe('orphan files status filter degradation hint', () => {
  function mountAndGetVm() {
    const wrapper = mountView()
    return viewModel(wrapper)
  }

  it('仅选 pending 不触发退化提示', async() => {
    const vm = mountAndGetVm()
    vm.listQuery.status = ['pending']
    await localVue.nextTick()
    expect(vm.statusFilterDegraded).toBe(false)
  })

  it('仅选 ignored 或 deleted 不触发退化提示', async() => {
    const vm = mountAndGetVm()
    vm.listQuery.status = ['ignored']
    await localVue.nextTick()
    expect(vm.statusFilterDegraded).toBe(false)
    vm.listQuery.status = ['deleted']
    await localVue.nextTick()
    expect(vm.statusFilterDegraded).toBe(false)
  })

  it('pending + ignored 触发退化提示', async() => {
    const vm = mountAndGetVm()
    vm.listQuery.status = ['pending', 'ignored']
    await localVue.nextTick()
    expect(vm.statusFilterDegraded).toBe(true)
  })

  it('pending + deleted 触发退化提示', async() => {
    const vm = mountAndGetVm()
    vm.listQuery.status = ['pending', 'deleted']
    await localVue.nextTick()
    expect(vm.statusFilterDegraded).toBe(true)
  })

  it('ignored + deleted 不触发退化提示（不矛盾的组合）', async() => {
    const vm = mountAndGetVm()
    vm.listQuery.status = ['ignored', 'deleted']
    await localVue.nextTick()
    expect(vm.statusFilterDegraded).toBe(false)
  })

  it('三态全选触发退化提示', async() => {
    const vm = mountAndGetVm()
    vm.listQuery.status = ['pending', 'ignored', 'deleted']
    await localVue.nextTick()
    expect(vm.statusFilterDegraded).toBe(true)
  })

  it('空数组不触发退化提示', async() => {
    const vm = mountAndGetVm()
    vm.listQuery.status = []
    await localVue.nextTick()
    expect(vm.statusFilterDegraded).toBe(false)
  })
})

// 回归保护：多选筛选数组提交转换为逗号串（修复空数组 truthy 提交判断 bug）
describe('orphan files multi-value filter submission', () => {
  it('downloader_id 多选数组提交为逗号串', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.listQuery.downloader_id = ['dl-001', 'dl-002']
    mockGetOrphanList.mockClear()
    mockGetOrphanList.mockResolvedValue(listResponse())
    vm.handleFilter()
    await flushLifecycle()

    expect(mockGetOrphanList).toHaveBeenLastCalledWith(
      expect.objectContaining({ downloader_id: 'dl-001,dl-002' })
    )
  })

  it('confidence 多选数组提交为逗号串', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.listQuery.confidence = ['high', 'low']
    mockGetOrphanList.mockClear()
    mockGetOrphanList.mockResolvedValue(listResponse())
    vm.handleFilter()
    await flushLifecycle()

    expect(mockGetOrphanList).toHaveBeenLastCalledWith(
      expect.objectContaining({ confidence: 'high,low' })
    )
  })

  it('status 多选数组提交为逗号串', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.listQuery.status = ['pending', 'deleted']
    mockGetOrphanList.mockClear()
    mockGetOrphanList.mockResolvedValue(listResponse())
    vm.handleFilter()
    await flushLifecycle()

    expect(mockGetOrphanList).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'pending,deleted' })
    )
  })

  it('空数组不提交（修复原 || undefined 对空数组 truthy 的判断 bug）', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    // 三个筛选都置空数组
    vm.listQuery.downloader_id = []
    vm.listQuery.confidence = []
    vm.listQuery.status = []
    mockGetOrphanList.mockClear()
    mockGetOrphanList.mockResolvedValue(listResponse())
    vm.handleFilter()
    await flushLifecycle()

    const callArgs = mockGetOrphanList.mock.calls[mockGetOrphanList.mock.calls.length - 1][0]
    expect(callArgs.downloader_id).toBeUndefined()
    expect(callArgs.confidence).toBeUndefined()
    expect(callArgs.status).toBeUndefined()
  })

  it('单选值数组提交为单值字符串（走 join 仍正确）', async() => {
    const wrapper = mountView()
    await flushLifecycle()
    const vm = viewModel(wrapper)
    vm.listQuery.downloader_id = ['dl-only']
    mockGetOrphanList.mockClear()
    mockGetOrphanList.mockResolvedValue(listResponse())
    vm.handleFilter()
    await flushLifecycle()

    expect(mockGetOrphanList).toHaveBeenLastCalledWith(
      expect.objectContaining({ downloader_id: 'dl-only' })
    )
  })
})
