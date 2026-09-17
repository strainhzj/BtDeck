import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import TorrentsManagement from '@/views/torrents/index.vue'
import PageSizeCombobox from '@/components/torrents/PageSizeCombobox.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'
import TrackerDetailCard from '@/views/torrents/components/TrackerDetailCard.vue'
import {
  advancedSearch,
  deleteBatchAsync,
  getActiveTorrents,
  getBatchDeleteStatus,
  getDownloaderList,
  getDuplicateTorrents,
  getTorrentFiles,
  getTorrentPeers,
  reconcileRuntimeTorrentStates,
  getTrackerDomains,
  getTorrentList
} from '@/api/torrents'
import type { Torrent } from '@/api/torrents'
import {
  setPlatformCapabilityCacheForTesting,
  resetPlatformCapabilityCache
} from '@/api/platform-capabilities'
import {
  getLoadingDirectiveSnapshot,
  installLoadingDirectiveProbe
} from './helpers/loadingDirectiveProbe'

jest.mock('@/store/modules/viewMode', () => ({
  ViewModeModule: {
    currentMode: 'list',
    setViewMode: jest.fn()
  }
}))

jest.mock('@/utils/theme-manager', () => ({
  __esModule: true,
  default: {
    initTheme: jest.fn(),
    getCurrentTheme: jest.fn(() => 'emerald'),
    getAllThemes: jest.fn(() => []),
    setTheme: jest.fn()
  }
}))

jest.mock('@/api/torrents', () => ({
  getTorrentList: jest.fn(),
  deleteTorrents: jest.fn(),
  deleteTorrentsWithLevel: jest.fn(),
  deleteBatchAsync: jest.fn(),
  getBatchDeleteStatus: jest.fn(),
  pauseTorrents: jest.fn(),
  resumeTorrents: jest.fn(),
  recheckTorrents: jest.fn(),
  advancedSearch: jest.fn(),
  getDuplicateTorrents: jest.fn(),
  getDownloaderList: jest.fn(),
  getTrackerDomains: jest.fn(),
  reannounceTorrents: jest.fn(),
  getActiveTorrents: jest.fn(),
  getTorrentFiles: jest.fn(),
  getTorrentPeers: jest.fn(),
  reconcileRuntimeTorrentStates: jest.fn(),
  applySearchTemplate: jest.fn(),
  createSearchTemplate: jest.fn()
}))

const localVue = createLocalVue()
const mockAdvancedSearch = advancedSearch as jest.MockedFunction<typeof advancedSearch>
const mockGetTorrentList = getTorrentList as jest.MockedFunction<typeof getTorrentList>
const mockGetDownloaderList = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
const mockGetTrackerDomains = getTrackerDomains as jest.MockedFunction<typeof getTrackerDomains>
const mockGetActiveTorrents = getActiveTorrents as jest.MockedFunction<typeof getActiveTorrents>
const mockGetTorrentFiles = getTorrentFiles as jest.MockedFunction<typeof getTorrentFiles>
const mockGetTorrentPeers = getTorrentPeers as jest.MockedFunction<typeof getTorrentPeers>
const mockReconcileRuntimeTorrentStates = reconcileRuntimeTorrentStates as jest.MockedFunction<
  typeof reconcileRuntimeTorrentStates
>
const mockGetDuplicateTorrents = getDuplicateTorrents as jest.MockedFunction<typeof getDuplicateTorrents>
const mockDeleteBatchAsync = deleteBatchAsync as jest.MockedFunction<typeof deleteBatchAsync>
const mockGetBatchDeleteStatus = getBatchDeleteStatus as jest.MockedFunction<typeof getBatchDeleteStatus>
installLoadingDirectiveProbe(localVue)

const SwitchStub = localVue.extend({
  name: 'ElSwitchStub',
  props: {
    value: Boolean,
    activeColor: String,
    inactiveColor: String
  },
  methods: {
    toggle() {
      const nextValue = !this.value
      this.$emit('input', nextValue)
      this.$emit('change', nextValue)
    }
  },
  template: `
    <button
      type="button"
      class="el-switch-stub"
      :aria-checked="value ? 'true' : 'false'"
      :data-active-color="activeColor"
      :data-inactive-color="inactiveColor"
      @click="toggle"
    />
  `
})

interface ListQueryState {
  skip: number
  limit: number
  name_like: string
  sort_by: string
  sort_order: string
  showActiveOnly: boolean
  tracker_domain: string[]
  status: string[]
}

interface TorrentListViewVm extends Vue {
  list: Torrent[]
  currentPage: number
  pageSize: number
  pageSizeInput: string
  pageSizeDropdownExpanded: boolean
  listLoading: boolean
  showingDuplicates: boolean
  showingSameContent: boolean
  showingSingleErrors: boolean
  listQuery: ListQueryState
  handleQuickActionCommand(command: string): Promise<void>
  exitSameContentInspection(): Promise<void>
  exitSingleErrorInspection(): Promise<void>
  handleDuplicateSearchToggle(enabled: boolean): Promise<void>
  handleFilter(): void
  handleClearFilter(): void
  handleSort(field: 'name' | 'size' | 'status' | 'ratio' | 'added_date'): void
  handlePageChange(page: number): void
  handlePageSizeSelect(suggestion: { value: string }): void
  handleManualRefresh(): void
  performAdvancedSearch(searchParams: Record<string, unknown>): Promise<void>
  applyQueryTemplate(conditions: Record<string, unknown>): Promise<boolean>
  callDeleteWithLevelAPI(torrents: Torrent[], level: number): Promise<void>
  loadActiveSpeed(): Promise<boolean>
  applySpeedUpdates(updates: Array<Record<string, unknown>>): boolean
  handleBatchAddCompleted(): Promise<void>
  runtimeStateMisses: Record<string, number>
}

const message = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
  info: jest.fn()
}

function successListResponse(pageSize = 20) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      list: [],
      total: 0,
      pageSize
    }
  }
}

async function flushLifecycle(): Promise<void> {
  for (let index = 0; index < 12; index += 1) {
    await Promise.resolve()
  }
  await localVue.nextTick()
}

function mountListView(): Wrapper<Vue> {
  return shallowMount(TorrentsManagement, {
    localVue,
    mocks: {
      $route: { query: {} },
      $router: { replace: jest.fn() },
      $message: message,
      $notify: {
        success: jest.fn(),
        error: jest.fn(),
        warning: jest.fn()
      },
      $confirm: jest.fn(() => Promise.resolve()),
      $loading: jest.fn(() => ({ close: jest.fn() }))
    },
    stubs: {
      BatchButton: true,
      PageSizeCombobox,
      LucideIcon,
      BatchOperationDialog: true,
      AdvancedSearchBuilder: true,
      TorrentAddDialog: true,
      TrackerOperationDialog: true,
      GlobalReplaceTrackerDialog: true,
      BatchTransferDialog: true,
      SetLocationDialog: true,
      'el-button': {
        template: '<button v-on="$listeners"><slot /></button>'
      },
      'el-checkbox': true,
      'el-dropdown': {
        template: '<div><slot /><slot name="dropdown" /></div>'
      },
      'el-dropdown-menu': {
        template: '<div><slot /></div>'
      },
      'el-dropdown-item': {
        template: '<div class="el-dropdown-item-stub"><slot /></div>'
      },
      'el-dialog': {
        template: '<div><slot /><slot name="title" /><slot name="footer" /></div>'
      },
      'el-input': true,
      'el-option': true,
      'el-select': true,
      'el-switch': SwitchStub
    }
  })
}

function torrentFixture(): Torrent {
  return {
    infoId: 'info-1',
    downloaderId: 'downloader-1',
    downloaderName: 'qb',
    torrentId: 'torrent-1',
    hash: 'hash-1',
    name: '种子-1',
    savePath: '/downloads',
    size: 1024,
    status: 'paused',
    torrentFile: '',
    addedDate: '2026-08-08T00:00:00Z',
    completedDate: null,
    ratio: 0,
    ratioLimit: 0,
    tags: '',
    category: '',
    superSeeding: false,
    enabled: true,
    auxiliarySeedCount: 1
  }
}

describe('torrent list view pagination and sorting', () => {
  let wrapper: Wrapper<Vue>
  let consoleDebugSpy: jest.SpyInstance

  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    // 视图按 level3Available（level3_recycle 能力）裁剪删除下拉的等级3 项：
    // 注入 desktop+supported 还原全四级入口契约（矩阵批次落地时未同步本 spec）
    setPlatformCapabilityCacheForTesting({
      schemaVersion: 1,
      platform: 'desktop',
      capabilities: { level3_recycle: { label: '三级回收', level: 'supported' } },
      degradedCount: 0,
      unsupportedCount: 0
    })
    consoleDebugSpy = jest.spyOn(console, 'debug').mockImplementation()
    mockGetTorrentList.mockResolvedValue(successListResponse())
    mockGetDownloaderList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: []
    })
    mockGetActiveTorrents.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: []
    })
    mockReconcileRuntimeTorrentStates.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: { list: [], missing: [] }
    })
    mockGetTrackerDomains.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: []
    })
    mockAdvancedSearch.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: { list: [], total: 0, page: 1, pageSize: 20 }
    })
    mockGetDuplicateTorrents.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: { list: [], total: 0, page: 1, pageSize: 20 }
    })
  })

  afterEach(() => {
    wrapper?.destroy()
    resetPlatformCapabilityCache()
    consoleDebugSpy.mockRestore()
  })

  it('批量与行内删除等级入口均使用正确的 LucideIcon', async() => {
    mockGetTorrentList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [torrentFixture()],
        total: 1,
        pageSize: 20
      }
    })

    wrapper = mountListView()
    await flushLifecycle()

    const expectedIcons = ['tag', 'trash-2', 'trash', 'alert-triangle']
    const menus = wrapper.findAll('.delete-level-menu')
    expect(menus).toHaveLength(2)

    menus.wrappers.forEach(menu => {
      const levelItems = menu.findAll('.el-dropdown-item-stub')
      expect(levelItems).toHaveLength(4)

      levelItems.wrappers.forEach((item, index) => {
        expect(item.find('svg').exists()).toBe(true)
        expect(item.find('.lucide-icon--missing').exists()).toBe(false)
        expect(item.findComponent(LucideIcon).props('name')).toBe(expectedIcons[index])
        expect(item.find('.lucide-icon').classes()).toContain('menu-icon')
      })

      expect(levelItems.at(3).find('.lucide-icon').classes()).toContain('danger')
      expect(levelItems.at(0).find('.lucide-icon').classes()).not.toContain('danger')
      expect(levelItems.at(1).find('.lucide-icon').classes()).not.toContain('danger')
      expect(levelItems.at(2).find('.lucide-icon').classes()).not.toContain('danger')
    })
  })

  it('列表视图展示同步任务持久化的辅种数量', async() => {
    mockGetTorrentList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [{ ...torrentFixture(), auxiliarySeedCount: 31 }],
        total: 1,
        pageSize: 20
      }
    })

    wrapper = mountListView()
    await flushLifecycle()

    const headers = wrapper.findAll('thead th').wrappers
    const auxiliaryIndex = headers.findIndex(header => header.text() === '辅种数量')
    const cells = wrapper.find('tbody tr').findAll('td').wrappers

    expect(auxiliaryIndex).toBeGreaterThan(-1)
    expect(cells[auxiliaryIndex].text()).toBe('31')
  })

  it('状态列为 tracker 异常种子叠加 Tracker异常 标签（error 状态与正常种子不打）', async() => {
    mockGetTorrentList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [
          { ...torrentFixture(), status: 'seeding', hasTrackerError: true, lastAnnounceMsg: 'You cannot seed the same torrent' },
          { ...torrentFixture(), infoId: 'info-2', hash: 'hash-2', status: 'error', hasTrackerError: true },
          { ...torrentFixture(), infoId: 'info-3', hash: 'hash-3', status: 'seeding' }
        ],
        total: 3,
        pageSize: 20
      }
    })

    wrapper = mountListView()
    await flushLifecycle()

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(3)
    // seeding + hasTrackerError：徽标 + 红色小标签
    expect(rows.at(0).find('.status-badge').text()).toBe('做种中')
    expect(rows.at(0).find('.tracker-error-tag').exists()).toBe(true)
    expect(rows.at(0).find('.tracker-error-tag').text()).toBe('Tracker异常')
    expect(rows.at(0).find('.tracker-error-tag').attributes('title')).toContain('You cannot seed')
    // error 状态已有"错误"徽标，不重复打标
    expect(rows.at(1).find('.status-badge').text()).toBe('错误')
    expect(rows.at(1).find('.tracker-error-tag').exists()).toBe(false)
    // 正常种子无标签
    expect(rows.at(2).find('.tracker-error-tag').exists()).toBe(false)
  })

  it('查询等待期间向 loading 指令传入 fullscreen+lock，失败后解除 loading', async() => {
    let rejectRequest: (reason?: unknown) => void = () => undefined
    const pendingRequest = new Promise<never>((_resolve, reject) => {
      rejectRequest = reject
    })
    mockGetTorrentList.mockImplementationOnce(() => pendingRequest)
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()

    try {
      wrapper = mountListView()
      await flushLifecycle()
      const vm = wrapper.vm as unknown as TorrentListViewVm
      const loadingTarget = wrapper.find('.torrents-table-wrapper').element

      expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
      expect(vm.listLoading).toBe(true)
      expect(getLoadingDirectiveSnapshot(loadingTarget)).toEqual({
        value: true,
        modifiers: { fullscreen: true, lock: true }
      })

      rejectRequest(new Error('network unavailable'))
      await flushLifecycle()

      expect(vm.listLoading).toBe(false)
      expect(getLoadingDirectiveSnapshot(loadingTarget)).toEqual({
        value: false,
        modifiers: { fullscreen: true, lock: true }
      })
      expect(message.error).toHaveBeenCalledTimes(1)
    } finally {
      consoleErrorSpy.mockRestore()
    }
  })

  it('同内容模式的筛选、排序、分页大小、翻页和刷新始终复用列表查询', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm
    mockGetTorrentList.mockClear()
    mockGetActiveTorrents.mockClear()

    expect(wrapper.text()).toContain('辅种异常排查')
    expect(vm.showingSameContent).toBe(false)

    await vm.handleQuickActionCommand('inspect-same-content')
    await flushLifecycle()

    expect(vm.showingSameContent).toBe(true)
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 0, limit: 20, same_content_only: true })
    )
    expect(wrapper.text()).toContain('退出排查并返回普通列表')

    vm.listQuery.name_like = 'needle'
    vm.handleFilter()
    await flushLifecycle()
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ name_like: 'needle', skip: 0, same_content_only: true })
    )

    vm.handleSort('name')
    await flushLifecycle()
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: 'name', sort_order: 'desc', same_content_only: true })
    )

    vm.handlePageSizeSelect({ value: '50' })
    await flushLifecycle()
    expect(vm.currentPage).toBe(1)
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 0, limit: 50, same_content_only: true })
    )

    vm.handlePageChange(2)
    await flushLifecycle()
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 50, limit: 50, same_content_only: true })
    )

    mockGetTorrentList.mockClear()
    vm.handleManualRefresh()
    await flushLifecycle()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 50, limit: 50, same_content_only: true })
    )
    expect(mockGetActiveTorrents).toHaveBeenCalledTimes(1)

    await vm.exitSameContentInspection()
    expect(vm.showingSameContent).toBe(false)
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.not.objectContaining({ same_content_only: true })
    )
  })

  it('简单搜索三个下拉框按下载器、状态、tracker展示提示语', () => {
    wrapper = mountListView()
    // vue-test-utils v1 对驼峰注册名不做 kebab 转换，stub 标签为 advancedmultiselect-stub
    const selects = wrapper.findAll('advancedmultiselect-stub')

    expect(selects).toHaveLength(3)
    expect(selects.at(0).attributes('placeholder')).toBe('请选择下载器')
    expect(selects.at(1).attributes('placeholder')).toBe('请选择种子状态')
    expect(selects.at(2).attributes('placeholder')).toBe('请选择tracker')
  })

  it('重复任务、高级搜索和查询模板均会退出同内容模式', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm

    await vm.handleQuickActionCommand('inspect-same-content')
    mockGetTorrentList.mockClear()
    mockGetDuplicateTorrents.mockClear()

    await vm.handleDuplicateSearchToggle(true)

    expect(vm.showingSameContent).toBe(false)
    expect(vm.showingDuplicates).toBe(true)
    expect(mockGetDuplicateTorrents).toHaveBeenCalledTimes(1)
    expect(mockGetTorrentList).not.toHaveBeenCalled()

    await vm.handleQuickActionCommand('inspect-same-content')
    mockAdvancedSearch.mockClear()
    await vm.performAdvancedSearch({
      complex_search: true,
      groups_count: 1,
      groups: JSON.stringify([{
        logic: 'AND',
        conditions: [{ field: 'name', operator: 'contains', value: 'needle' }]
      }]),
      between_group_logics: JSON.stringify([])
    })
    expect(vm.showingSameContent).toBe(false)
    expect(mockAdvancedSearch).toHaveBeenCalledTimes(1)

    await vm.handleQuickActionCommand('inspect-same-content')
    mockGetTorrentList.mockClear()
    const applied = await vm.applyQueryTemplate({
      source: 'simple',
      version: 1,
      listQuery: {
        name_like: 'template',
        downloader_id: [],
        status: [],
        showActiveOnly: false,
        sort_by: 'added_date',
        sort_order: 'desc'
      }
    })
    expect(applied).toBe(true)
    expect(vm.showingSameContent).toBe(false)
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.not.objectContaining({ same_content_only: true })
    )
  })

  it('支持 Tracker 主域名筛选，并可快捷排查错误单种', async() => {
    mockGetTrackerDomains.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: ['tracker.example.com', 'mirror.example.net']
    })
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm & {
      trackerDomainOptions: Array<{ value: string, label: string }>
    }

    expect(vm.trackerDomainOptions).toEqual([
      { value: 'tracker.example.com', label: 'tracker.example.com' },
      { value: 'mirror.example.net', label: 'mirror.example.net' }
    ])

    vm.listQuery.tracker_domain = ['tracker.example.com', 'mirror.example.net']
    mockGetTorrentList.mockClear()
    vm.handleFilter()
    await flushLifecycle()
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ tracker_domain: 'tracker.example.com,mirror.example.net' })
    )

    await vm.handleQuickActionCommand('inspect-single-errors')
    await flushLifecycle()
    expect(vm.showingSingleErrors).toBe(true)
    expect(vm.showingSameContent).toBe(false)
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({
        tracker_domain: 'tracker.example.com,mirror.example.net',
        single_error_only: true
      })
    )
    expect(wrapper.text()).toContain('错误单种排查')

    await vm.exitSingleErrorInspection()
    expect(vm.showingSingleErrors).toBe(false)
  })

  it('uses the traditional page-size combobox presets and custom limit behavior', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm

    expect(wrapper.find('.page-size-select').exists()).toBe(false)
    expect(wrapper.find('.page-size-combobox').exists()).toBe(true)
    expect(wrapper.findAll('.page-size-options button').wrappers.map(option => option.text()))
      .toEqual(['20', '50', '100', '500', '1000'])

    vm.currentPage = 4
    const input = wrapper.find('.page-size-input')
    await input.setValue('500')
    await input.trigger('keyup', { key: 'Enter', keyCode: 13 })
    await flushLifecycle()

    expect(vm.pageSize).toBe(500)
    expect(vm.pageSizeInput).toBe('500')
    expect(vm.currentPage).toBe(1)
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 0, limit: 500 })
    )
  })

  it('重复任务开关默认关闭，用户开启后渲染绿色状态并触发重复查询', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    mockGetDuplicateTorrents.mockClear()
    const vm = wrapper.vm as unknown as TorrentListViewVm
    const switchShell = wrapper.find('.duplicate-search-switch')
    const switchControl = wrapper.findComponent(SwitchStub)

    expect(vm.showingDuplicates).toBe(false)
    expect(switchShell.classes()).not.toContain('is-active')
    expect(switchControl.attributes('aria-checked')).toBe('false')
    expect(switchControl.attributes('data-active-color')).toBe('var(--color-success, #10b981)')

    await switchControl.trigger('click')
    await flushLifecycle()

    expect(vm.showingDuplicates).toBe(true)
    expect(switchShell.classes()).toContain('is-active')
    expect(switchControl.attributes('aria-checked')).toBe('true')
    expect(mockGetDuplicateTorrents).toHaveBeenCalledTimes(1)
  })

  it('重复任务开关开启后筛选、排序、切页和关闭均使用正确数据源', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    mockGetDuplicateTorrents.mockClear()
    const vm = wrapper.vm as unknown as TorrentListViewVm

    vm.listQuery.showActiveOnly = true
    await vm.handleDuplicateSearchToggle(true)
    expect(vm.showingDuplicates).toBe(true)
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({
        page: 1,
        pageSize: 20,
        sort_by: 'added_date',
        sort_order: 'desc',
        active_only: true
      })
    )

    vm.listQuery.name_like = 'needle'
    vm.handleFilter()
    await flushLifecycle()
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({ name_like: 'needle', page: 1 })
    )
    expect(mockGetTorrentList).not.toHaveBeenCalled()

    vm.handleSort('name')
    await flushLifecycle()
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: 'name', sort_order: 'desc' })
    )

    vm.handlePageChange(2)
    await flushLifecycle()
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2, pageSize: 20 })
    )

    await vm.handleDuplicateSearchToggle(false)
    expect(vm.showingDuplicates).toBe(false)
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
  })

  it('异步删除提交后先刷新列表再开始轮询，并提示跳过的处理中项', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    mockDeleteBatchAsync.mockResolvedValueOnce({
      status: 'success',
      msg: '已提交删除任务，正在后台执行',
      code: '200',
      data: {
        task_id: 'delete-task-1',
        total_count: 1,
        requested_count: 2,
        accepted_count: 1,
        skipped_count: 1,
        skipped_info_ids: ['info-1'],
        delete_level: 2
      }
    })
    mockGetBatchDeleteStatus.mockResolvedValueOnce({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        task_id: 'delete-task-1',
        status: 'completed',
        total_count: 1,
        requested_count: 2,
        accepted_count: 1,
        skipped_count: 1,
        skipped_info_ids: ['info-1'],
        success_count: 1,
        failed_count: 0,
        results: [],
        failed_items: []
      }
    })
    const second = {
      ...torrentFixture(),
      infoId: 'info-2',
      torrentId: 'torrent-2',
      hash: 'hash-2'
    }

    await (wrapper.vm as unknown as TorrentListViewVm).callDeleteWithLevelAPI(
      [torrentFixture(), second],
      2
    )

    expect(message.warning).toHaveBeenCalledWith('已跳过 1 个正在处理的种子')
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    expect(mockGetBatchDeleteStatus).toHaveBeenCalledWith('delete-task-1')
    expect(mockGetTorrentList.mock.invocationCallOrder[0])
      .toBeLessThan(mockGetBatchDeleteStatus.mock.invocationCallOrder[0])
  })

  it('全部已在处理中时不轮询但仍立即刷新列表', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    mockDeleteBatchAsync.mockResolvedValueOnce({
      status: 'success',
      msg: '所选种子均已在删除任务中处理',
      code: '200',
      data: {
        task_id: null,
        total_count: 0,
        requested_count: 2,
        accepted_count: 0,
        skipped_count: 2,
        skipped_info_ids: ['info-1', 'info-2'],
        delete_level: 2
      }
    })
    const second = {
      ...torrentFixture(),
      infoId: 'info-2',
      torrentId: 'torrent-2',
      hash: 'hash-2'
    }

    await (wrapper.vm as unknown as TorrentListViewVm).callDeleteWithLevelAPI(
      [torrentFixture(), second],
      2
    )

    expect(message.info).toHaveBeenCalledWith('所选种子均已在删除任务中处理')
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    expect(mockGetBatchDeleteStatus).not.toHaveBeenCalled()
  })

  it('名称列登记列宽并渲染可拖拽手柄，表格按列宽总和严格定宽', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as {
      tableMinWidth: number
      defaultColumnWidths: Record<string, number>
      columnWidths: Record<string, number>
    }

    // qBittorrent 风格严格列宽：表格 width 与 min-width 同绑列宽总和（视口富余右侧留白）
    const tableStyle = wrapper.find('table.torrent-table').attributes('style') || ''
    expect(tableStyle).toContain(`width: ${vm.tableMinWidth}px`)
    expect(tableStyle).toContain(`min-width: ${vm.tableMinWidth}px`)

    // 名称列不再是自适应列：内联宽 + 右缘手柄
    const nameHeader = wrapper.find('th[data-sort-field="name"]')
    expect(nameHeader.attributes('style')).toContain(`width: ${vm.defaultColumnWidths.name}px`)
    const handle = nameHeader.find('.column-resizer')
    expect(handle.exists()).toBe(true)

    // 手柄真实进入拖拽会话：body 拖拽态、按位移更新、mouseup 一次性落盘
    handle.element.dispatchEvent(new MouseEvent('mousedown', { buttons: 1, clientX: 300, bubbles: true }))
    await localVue.nextTick()
    expect(document.body.classList.contains('column-resizing')).toBe(true)

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 360 }))
    await localVue.nextTick()
    expect(vm.columnWidths.name).toBe(vm.defaultColumnWidths.name + 60)

    document.dispatchEvent(new MouseEvent('mouseup', { clientX: 360 }))
    await localVue.nextTick()
    expect(document.body.classList.contains('column-resizing')).toBe(false)
    expect(JSON.parse(localStorage.getItem('btdeck_torrents_column_widths') || '{}'))
      .toEqual(expect.objectContaining({ name: vm.defaultColumnWidths.name + 60 }))
  })

  it('sorts the same five headers as traditional mode by click and keyboard', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm
    const sortableHeaders = wrapper.findAll('th.sortable-column')

    expect(sortableHeaders.wrappers.map(header => header.attributes('data-sort-field')))
      .toEqual(['name', 'size', 'status', 'ratio', 'added_date'])
    expect(wrapper.find('th[data-sort-field="added_date"]').attributes('aria-sort')).toBe('descending')
    expect(sortableHeaders.wrappers.every(header => header.find('.sort-icon').exists())).toBe(true)
    expect(wrapper.find('th[data-sort-field="name"] .sort-icon').findComponent(LucideIcon).props('name'))
      .toBe('arrow-up-down')
    expect(wrapper.find('th[data-sort-field="added_date"] .sort-icon').findComponent(LucideIcon).props('name'))
      .toBe('arrow-down')

    const nameHeader = wrapper.find('th[data-sort-field="name"]')
    await nameHeader.trigger('click')
    await flushLifecycle()

    expect(vm.listQuery.sort_by).toBe('name')
    expect(vm.listQuery.sort_order).toBe('desc')
    expect(nameHeader.attributes('aria-sort')).toBe('descending')
    expect(nameHeader.find('.sort-icon').findComponent(LucideIcon).props('name')).toBe('arrow-down')
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: 'name', sort_order: 'desc' })
    )

    await nameHeader.trigger('keydown', { key: 'Enter', keyCode: 13 })
    await flushLifecycle()

    expect(vm.listQuery.sort_order).toBe('asc')
    expect(nameHeader.attributes('aria-sort')).toBe('ascending')
    expect(nameHeader.find('.sort-icon').findComponent(LucideIcon).props('name')).toBe('arrow-up')
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: 'name', sort_order: 'asc' })
    )
  })

  it('uses Space to switch Lucide direction without falling back to triangle characters', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    const vm = wrapper.vm as unknown as TorrentListViewVm
    const sortableHeaders = wrapper.findAll('th.sortable-column')
    const sizeHeader = wrapper.find('th[data-sort-field="size"]')

    expect(sortableHeaders.wrappers.map(header => header.text()).join('')).not.toMatch(/[▲▼]/)
    expect(sizeHeader.find('.sort-icon').findComponent(LucideIcon).props('name')).toBe('arrow-up-down')

    await sizeHeader.trigger('keydown', { key: ' ', code: 'Space', keyCode: 32 })
    await flushLifecycle()

    expect(vm.listQuery.sort_by).toBe('size')
    expect(vm.listQuery.sort_order).toBe('desc')
    expect(sizeHeader.attributes('aria-sort')).toBe('descending')
    expect(sizeHeader.find('.sort-icon').findComponent(LucideIcon).props('name')).toBe('arrow-down')
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: 'size', sort_order: 'desc' })
    )

    await sizeHeader.trigger('keydown', { key: ' ', code: 'Space', keyCode: 32 })
    await flushLifecycle()

    expect(vm.listQuery.sort_order).toBe('asc')
    expect(sizeHeader.attributes('aria-sort')).toBe('ascending')
    expect(sizeHeader.find('.sort-icon').findComponent(LucideIcon).props('name')).toBe('arrow-up')
  })

  it('连续完整快照未命中后核验零速终态，并把主列表行收敛到100%', async() => {
    mockGetTorrentList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [{ ...torrentFixture(), status: 'downloading', progress: 99 }],
        total: 1,
        pageSize: 20
      }
    })
    mockReconcileRuntimeTorrentStates.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [{
          hash: 'hash-1',
          downloader_id: 'downloader-1',
          downloadSpeed: 0,
          uploadSpeed: 0,
          progress: 99,
          status: 'seeding',
          downloadComplete: true,
          num_seeds: 0,
          num_leechs: 0
        }],
        missing: []
      }
    })
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.runtimeStateMisses = {}
    mockGetActiveTorrents.mockClear()
    mockReconcileRuntimeTorrentStates.mockClear()

    await vm.loadActiveSpeed()
    expect(mockReconcileRuntimeTorrentStates).not.toHaveBeenCalled()
    await vm.loadActiveSpeed()

    expect(mockReconcileRuntimeTorrentStates).toHaveBeenCalledWith([
      { downloader_id: 'downloader-1', hash: 'hash-1' }
    ])
    expect(vm.list[0]).toEqual(expect.objectContaining({
      status: 'seeding',
      progress: 100,
      downloadComplete: true,
      downloadSpeed: 0,
      uploadSpeed: 0
    }))
  })

  it('完整快照出现新的未展示复合键时重拉数据库列表，并立即应用同轮进度', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm

    // 显式建立“当前页之外活动键”的初始基线，避免把分页既有任务误判为新增。
    mockGetActiveTorrents.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200', data: []
    })
    await vm.loadActiveSpeed()
    mockGetTorrentList.mockClear()

    const newlyAdded = {
      ...torrentFixture(),
      infoId: 'new-info', downloaderId: 'downloader-1', hash: 'new-hash',
      name: '刚入库种子', status: 'downloading', progress: 0
    }
    mockGetTorrentList.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200',
      data: { list: [newlyAdded], total: 1, pageSize: 20 }
    })
    mockGetActiveTorrents.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200', data: [{
        hash: 'new-hash', downloader_id: 'downloader-1',
        downloadSpeed: 4096, uploadSpeed: 0, progress: 37,
        status: 'downloading', num_seeds: 0, num_leechs: 0
      }]
    })

    await vm.loadActiveSpeed()

    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    expect(vm.list).toHaveLength(1)
    expect(vm.list[0]).toEqual(expect.objectContaining({
      hash: 'new-hash', name: '刚入库种子', progress: 37, downloadSpeed: 4096
    }))
  })

  it('批量添加完成信号会再次拉取权威列表并补一次实时进度', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm
    mockGetTorrentList.mockClear()
    mockGetActiveTorrents.mockClear()

    mockGetTorrentList.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200',
      data: {
        list: [{ ...torrentFixture(), status: 'downloading', progress: 0 }],
        total: 1,
        pageSize: 20
      }
    })
    mockGetActiveTorrents.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200', data: [{
        hash: 'hash-1', downloader_id: 'downloader-1',
        downloadSpeed: 2048, uploadSpeed: 0, progress: 19,
        status: 'downloading', num_seeds: 0, num_leechs: 0
      }]
    })

    const addDialog = wrapper.findComponent({ name: 'TorrentAddDialog' })
    expect(addDialog.exists()).toBe(true)
    addDialog.vm.$emit('batch-complete')
    await flushLifecycle()

    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    expect(mockGetActiveTorrents).toHaveBeenCalledTimes(1)
    expect(vm.list[0]).toEqual(expect.objectContaining({ progress: 19, downloadSpeed: 2048 }))
  })
})

describe('详情死路由不启动轮询（W1-1）', () => {
  function mountWithRoute(path: string): Wrapper<Vue> {
    return shallowMount(TorrentsManagement, {
      localVue,
      mocks: {
        $route: { path, query: {} },
        $router: { replace: jest.fn() },
        $message: message,
        $notify: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
        $confirm: jest.fn(() => Promise.resolve()),
        $loading: jest.fn(() => ({ close: jest.fn() }))
      },
      stubs: {
        BatchButton: true,
        PageSizeCombobox,
        LucideIcon,
        BatchOperationDialog: true,
        AdvancedSearchBuilder: true,
        TorrentAddDialog: true,
        TrackerOperationDialog: true,
        GlobalReplaceTrackerDialog: true,
        BatchTransferDialog: true,
        SetLocationDialog: true,
        QuickDeleteDuplicatesDialog: true,
        TrackerDetailCard: true,
        'el-button': { template: '<button v-on="$listeners"><slot /></button>' },
        'el-checkbox': true,
        'el-dropdown': { template: '<div><slot /><slot name="dropdown" /></div>' },
        'el-dropdown-menu': { template: '<div><slot /></div>' },
        'el-dropdown-item': { template: '<div><slot /></div>' },
        'el-table': { template: '<div><slot /></div>' },
        'el-table-column': { template: '<div><slot /></div>' },
        'el-pagination': true,
        'el-select': { template: '<div><slot /></div>' },
        'el-option': true,
        'el-input': { template: '<input v-on="$listeners" />' },
        'el-date-picker': true,
        'el-tag': true,
        'el-switch': true,
        'el-tooltip': true,
        'el-popover': true,
        'el-dialog': { template: '<div><slot /></div>' },
        'el-form': { template: '<form><slot /></form>' },
        'el-form-item': true,
        'el-tabs': { template: '<div><slot /></div>' },
        'el-tab-pane': { template: '<div><slot /></div>' },
        'el-badge': true,
        'el-empty': true,
        'el-skeleton': true,
        'el-skeleton-item': true,
        'el-alert': true,
        'el-radio-group': true,
        'el-radio': true,
        'el-tree': true,
        'el-upload': true,
        'el-progress': true,
        'el-rate': true,
        'el-autocomplete': true,
        'el-cascader': true,
        'el-checkbox-group': true,
        'el-color-picker': true,
        'el-input-number': true,
        'el-radio-button': true,
        'el-slider': true,
        'el-switch-stub': true,
        'el-time-select': true,
        'el-transfer': true,
        'el-divider': true,
        'el-link': true,
        'el-card': true,
        'el-carousel': true,
        'el-carousel-item': true,
        'el-collapse': true,
        'el-collapse-item': true,
        'el-container': true,
        'el-aside': true,
        'el-header': true,
        'el-main': true,
        'el-footer': true,
        'el-row': true,
        'el-col': true,
        'el-steps': true,
        'el-step': true,
        'el-timeline': true,
        'el-timeline-item': true,
        'el-breadcrumb': true,
        'el-breadcrumb-item': true,
        'el-page-header': true,
        'el-descriptions': true,
        'el-descriptions-item': true,
        'el-result': true,
        'el-avatar': true,
        'el-image': true,
        'el-backtop': true,
        'el-infinite-scroll': true,
        'el-loading': true,
        'el-drawer': true,
        'el-menu': true,
        'el-menu-item': true,
        'el-submenu': true,
        'el-button-group': true,
        'el-option-group': true
      }
    })
  }

  it('/torrents/detail/:hash 下不启动速度轮询', async() => {
    const wrapper = mountWithRoute('/torrents/detail/abc123')
    await flushLifecycle()
    expect((wrapper.vm as any).speedPollingActive).toBe(false)
  })

  it('/torrents/index 下正常启动速度轮询', async() => {
    const wrapper = mountWithRoute('/torrents/index')
    await flushLifecycle()
    expect((wrapper.vm as any).speedPollingActive).toBe(true)
  })
})

describe('终态整表刷新循环治理（稳态证据 + 滞后窗口）', () => {
  let wrapper: Wrapper<Vue>
  let consoleDebugSpy: jest.SpyInstance

  /** 活跃快照：hash-1 在 downloader-1 上带完成证据（qB active 过滤含做种中种子） */
  const terminalActiveSnapshot = () => ({
    status: 'success',
    msg: 'ok',
    code: '200',
    data: [{
      hash: 'hash-1',
      downloader_id: 'downloader-1',
      downloadSpeed: 0,
      uploadSpeed: 512,
      progress: 100,
      status: 'uploading',
      downloadComplete: true,
      num_seeds: 0,
      num_leechs: 1
    }]
  })

  // mock 必须每次返回新鲜行对象：applySpeedUpdates 会原地突变成终态，共享
  // fixture 会让「后续轮次不再 getList」的断言空转通过（同 mobile-torrents.spec 坑）。
  /** DB 滞后行：下载器已完成但同步任务未落地，getList 仍返回 downloading/99 */
  const laggingListResponse = () => ({
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      list: [{ ...torrentFixture(), status: 'downloading', progress: 99 }],
      total: 1,
      pageSize: 20
    }
  })

  /** DB 已收敛的做种行：progress=100 + completed_date（稳态循环场景的列表形态） */
  const seedingListResponse = () => ({
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      list: [{
        ...torrentFixture(),
        status: 'seeding',
        progress: 100,
        completedDate: '2026-09-01T00:00:00Z'
      }],
      total: 1,
      pageSize: 20
    }
  })

  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    // 视图按 level3Available（level3_recycle 能力）裁剪删除下拉的等级3 项：
    // 注入 desktop+supported 还原全四级入口契约（矩阵批次落地时未同步本 spec）
    setPlatformCapabilityCacheForTesting({
      schemaVersion: 1,
      platform: 'desktop',
      capabilities: { level3_recycle: { label: '三级回收', level: 'supported' } },
      degradedCount: 0,
      unsupportedCount: 0
    })
    consoleDebugSpy = jest.spyOn(console, 'debug').mockImplementation()
    mockGetTorrentList.mockResolvedValue(successListResponse())
    mockGetDownloaderList.mockResolvedValue({ status: 'success', msg: 'ok', code: '200', data: [] })
    mockGetActiveTorrents.mockResolvedValue({ status: 'success', msg: 'ok', code: '200', data: [] })
    mockReconcileRuntimeTorrentStates.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200', data: { list: [], missing: [] }
    })
    mockGetTrackerDomains.mockResolvedValue({ status: 'success', msg: 'ok', code: '200', data: [] })
  })

  afterEach(() => {
    wrapper?.destroy()
    resetPlatformCapabilityCache()
    consoleDebugSpy.mockRestore()
  })

  it('转移判定最低层锚：downloading 行收到完成证据必须报告转移（求值时机错则恒不报）', async() => {
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.list = [{ ...torrentFixture(), status: 'downloading', progress: 99 }]

    const reported = vm.applySpeedUpdates([{
      hash: 'hash-1',
      downloaderId: 'downloader-1',
      downloadSpeed: 0,
      uploadSpeed: 512,
      progress: 100,
      status: 'completed',
      downloadComplete: true
    }])

    expect(reported).toBe(true)
    expect(vm.list[0].downloadComplete).toBe(true)
  })

  it('滞后窗口循环（主快照路径）：status 筛选下同一完成证据只触发一次 getList', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(laggingListResponse()))
    // mount 期间用空快照：桌面 created 即启动首轮轮询（immediate=true），
    // 终态快照会把 created getList 的滞后行原地突变成终态，后续转移永远不成立
    wrapper = mountListView()
    await flushLifecycle()
    mockGetActiveTorrents.mockResolvedValue(terminalActiveSnapshot())
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    // 修复前：getList 拉回 DB 滞后行，下一轮证据又触发 → 每秒一次刷新循环
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
  })

  it('稳态循环：做种筛选下 DB 已收敛的做种行持续带完成证据，全程零 getList', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(seedingListResponse()))
    mockGetActiveTorrents.mockResolvedValue(terminalActiveSnapshot())
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.listQuery.status = ['seeding']
    mockGetTorrentList.mockClear()

    // 修复前：稳态证据（行已终态）也置 terminalObserved → 每秒 getList 无限循环
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).not.toHaveBeenCalled()
  })

  it('滞后窗口循环（reconcile 路径）：终态核验带回完成证据同样只触发一次 getList', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(laggingListResponse()))
    // 快照为空：hash-1 行连续 miss，两轮后触发低频核验；核验直连下载器带回完成证据
    mockGetActiveTorrents.mockResolvedValue({ status: 'success', msg: 'ok', code: '200', data: [] })
    mockReconcileRuntimeTorrentStates.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [{
          hash: 'hash-1',
          downloader_id: 'downloader-1',
          downloadSpeed: 0,
          uploadSpeed: 0,
          progress: 100,
          status: 'seeding',
          downloadComplete: true,
          num_seeds: 0,
          num_leechs: 0
        }],
        missing: []
      }
    })
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.runtimeStateMisses = {}
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    // getList 拉回滞后行后 miss 重新累计，第二次核验的转移被同键去重挡住
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
  })

  it('筛选变化重置终态去重：handleFilter 后同一完成证据允许再触发一次', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(laggingListResponse()))
    wrapper = mountListView()
    await flushLifecycle()
    mockGetActiveTorrents.mockResolvedValue(terminalActiveSnapshot())
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)

    vm.handleFilter()
    await flushLifecycle()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(2)
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
  })

  it('showActiveOnly 触发分支：同一完成证据同样只触发一次 getList', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(laggingListResponse()))
    wrapper = mountListView()
    await flushLifecycle()
    mockGetActiveTorrents.mockResolvedValue(terminalActiveSnapshot())
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.listQuery.showActiveOnly = true
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
  })

  it('206 部分快照终态证据同样只触发一次 getList（增量合并路径去重）', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(laggingListResponse()))
    wrapper = mountListView()
    await flushLifecycle()
    // 206：部分下载器成功的增量快照（partial=true，跳过 reconcile/membership 基线重建）
    mockGetActiveTorrents.mockResolvedValue({
      status: 'partial',
      msg: 'partial',
      code: '206',
      data: [{
        hash: 'hash-1',
        downloader_id: 'downloader-1',
        downloadSpeed: 0,
        uploadSpeed: 512,
        progress: 100,
        status: 'uploading',
        downloadComplete: true,
        num_seeds: 0,
        num_leechs: 1
      }]
    })
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
  })

  it('排序变化不清终态去重：handleSort 后同一完成证据不再触发 getList', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(laggingListResponse()))
    wrapper = mountListView()
    await flushLifecycle()
    mockGetActiveTorrents.mockResolvedValue(terminalActiveSnapshot())
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)

    vm.handleSort('name')
    await flushLifecycle()
    mockGetTorrentList.mockClear()

    // 排序只变行序不变行集合，去重键是 downloader+hash 身份键——不得重置
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).not.toHaveBeenCalled()
  })

  it('翻页不清终态去重：handlePageChange 重拉列表后同一完成证据不再触发 getList', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(laggingListResponse()))
    wrapper = mountListView()
    await flushLifecycle()
    mockGetActiveTorrents.mockResolvedValue(terminalActiveSnapshot())
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)

    vm.handlePageChange(2)
    await flushLifecycle()
    mockGetTorrentList.mockClear()

    // 翻页本身即 getList（新鲜滞后行回列），同键去重继续生效
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).not.toHaveBeenCalled()
  })

  it('handleClearFilter 重置终态去重：重新开筛选后允许再触发一次', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(laggingListResponse()))
    wrapper = mountListView()
    await flushLifecycle()
    mockGetActiveTorrents.mockResolvedValue(terminalActiveSnapshot())
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)

    vm.handleClearFilter()
    await flushLifecycle()
    // 重新开筛选（直接赋值模拟，避免 handleFilter 的 getList 混入计数）
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
  })

  it('无筛选期间去重额度不被消费：短路顺序保证开筛选后首次终态仍可触发一次', async() => {
    mockGetTorrentList.mockImplementation(() => Promise.resolve(laggingListResponse()))
    wrapper = mountListView()
    await flushLifecycle()
    mockGetActiveTorrents.mockResolvedValue(terminalActiveSnapshot())
    const vm = wrapper.vm as unknown as TorrentListViewVm
    mockGetTorrentList.mockClear()

    // 无筛选：转移成立但触发条件为 false → 0 次 getList，tracker 因 && 短路未被消费
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).not.toHaveBeenCalled()

    // 翻页重拉新鲜滞后行（行被前两轮就地标记终态，需非终态行才能再次转移）
    vm.handlePageChange(2)
    await flushLifecycle()
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
  })

  it('新未展示键与终态证据同轮到达：成员自愈一次+终态首刷一次，后续轮零刷新（有界）', async() => {
    // created 首次 getList 返回空列表（种子尚未入库展示），此后每次返回新鲜滞后行
    let listCallCount = 0
    mockGetTorrentList.mockImplementation(() => {
      listCallCount += 1
      return Promise.resolve(listCallCount === 1 ? successListResponse() : laggingListResponse())
    })
    wrapper = mountListView()
    await flushLifecycle()
    mockGetActiveTorrents.mockResolvedValue(terminalActiveSnapshot())
    const vm = wrapper.vm as unknown as TorrentListViewVm
    vm.listQuery.status = ['downloading']
    mockGetTorrentList.mockClear()

    await vm.loadActiveSpeed()
    // membership.refresh 拉表 1 次（新键入列）+ 终态触发点首刷 1 次（重放转移+新复合键）
    expect(mockGetTorrentList).toHaveBeenCalledTimes(2)
    await vm.loadActiveSpeed()
    await vm.loadActiveSpeed()
    expect(mockGetTorrentList).toHaveBeenCalledTimes(2)
  })
})

describe('详情卡片文件/Peers 页签数据接线（TrackerDetailDataMixin 集成回归）', () => {
  let wrapper: Wrapper<Vue>
  let consoleDebugSpy: jest.SpyInstance

  const detailEnvelope = <T>(list: T[]) => ({
    status: 'success',
    msg: 'ok',
    code: '200',
    data: { list, total: list.length, page: 1, pageSize: 100000 }
  })

  // 假定时器阶段的微任务冲刷（不含 setTimeout，配合 advanceTimersByTime 使用）
  const flushMicro = async() => {
    for (let index = 0; index < 12; index += 1) {
      await Promise.resolve()
    }
    await localVue.nextTick()
  }

  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    // 视图按 level3Available（level3_recycle 能力）裁剪删除下拉的等级3 项：
    // 注入 desktop+supported 还原全四级入口契约（矩阵批次落地时未同步本 spec）
    setPlatformCapabilityCacheForTesting({
      schemaVersion: 1,
      platform: 'desktop',
      capabilities: { level3_recycle: { label: '三级回收', level: 'supported' } },
      degradedCount: 0,
      unsupportedCount: 0
    })
    consoleDebugSpy = jest.spyOn(console, 'debug').mockImplementation()
    mockGetTorrentList.mockResolvedValue(successListResponse())
    mockGetDownloaderList.mockResolvedValue({ status: 'success', msg: 'ok', code: '200', data: [] })
    mockGetActiveTorrents.mockResolvedValue({ status: 'success', msg: 'ok', code: '200', data: [] })
    mockReconcileRuntimeTorrentStates.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200', data: { list: [], missing: [] }
    })
    mockGetTrackerDomains.mockResolvedValue({ status: 'success', msg: 'ok', code: '200', data: [] })
    mockGetTorrentFiles.mockResolvedValue(
      detailEnvelope([{ name: 'a.iso', size: 1024, progress: 0.5 }])
    )
    mockGetTorrentPeers.mockResolvedValue(
      detailEnvelope([{ ip: '1.2.3.4', port: 6881, client: 'qB 5.0', progress: 0.5, down_speed: 1, up_speed: 2, flags: 'D', country: '' }])
    )
  })

  afterEach(() => {
    wrapper?.destroy()
    consoleDebugSpy.mockRestore()
    jest.useRealTimers()
  })

  async function openDetailCard(): Promise<ReturnType<Wrapper<Vue>['findComponent']>> {
    wrapper = mountListView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as { handleRowClick(row: Torrent): void }
    vm.handleRowClick(torrentFixture())
    await localVue.nextTick()
    return wrapper.findComponent(TrackerDetailCard)
  }

  it('行点击打开卡片：layout=list、默认 Tracker 页签、透传三个页签与空的双页签状态', async() => {
    const card = await openDetailCard()
    expect(card.exists()).toBe(true)
    expect(card.props('layout')).toBe('list')
    expect(card.props('visible')).toBe(true)
    expect(card.props('activeTab')).toBe('tracker')
    expect(card.props('tabs').map((tab: { value: string }) => tab.value)).toEqual(['tracker', 'files', 'peers'])
    expect(card.props('filesState')).toEqual({ list: [], loading: false, error: '' })
    expect(card.props('peersState')).toEqual({ list: [], loading: false, error: '' })
  })

  it('切文件页签按 hash+downloaderId 懒加载一次并透传 files-state；同键不重取；refresh 事件强制重取', async() => {
    const card = await openDetailCard()

    card.vm.$emit('update:activeTab', 'files')
    await flushLifecycle()
    expect(mockGetTorrentFiles).toHaveBeenCalledTimes(1)
    expect(mockGetTorrentFiles).toHaveBeenCalledWith('hash-1', 'downloader-1')
    expect(card.props('filesState')).toEqual({
      list: [{ name: 'a.iso', size: 1024, progress: 0.5 }],
      loading: false,
      error: ''
    })

    // 同键切走再切回：命中缓存不重复拉取
    card.vm.$emit('update:activeTab', 'tracker')
    await flushLifecycle()
    card.vm.$emit('update:activeTab', 'files')
    await flushLifecycle()
    expect(mockGetTorrentFiles).toHaveBeenCalledTimes(1)

    // 卡片内刷新按钮 → refresh 事件 → 强制重取
    card.vm.$emit('refresh', 'files')
    await flushLifecycle()
    expect(mockGetTorrentFiles).toHaveBeenCalledTimes(2)
  })

  it('Peers 页签 5s 链式轮询；close 事件（右上角与收起条同源）停止轮询并复位双页签状态', async() => {
    const card = await openDetailCard()
    jest.useFakeTimers()

    card.vm.$emit('update:activeTab', 'peers')
    await flushMicro()
    expect(mockGetTorrentPeers).toHaveBeenCalledTimes(1)
    expect(card.props('peersState').list).toHaveLength(1)

    jest.advanceTimersByTime(5000)
    await flushMicro()
    expect(mockGetTorrentPeers).toHaveBeenCalledTimes(2)

    card.vm.$emit('close')
    await flushMicro()
    expect(card.props('visible')).toBe(false)
    expect(card.props('peersState')).toEqual({ list: [], loading: false, error: '' })
    expect(card.props('filesState')).toEqual({ list: [], loading: false, error: '' })

    jest.advanceTimersByTime(15000)
    await flushMicro()
    expect(mockGetTorrentPeers).toHaveBeenCalledTimes(2)
  })
})
