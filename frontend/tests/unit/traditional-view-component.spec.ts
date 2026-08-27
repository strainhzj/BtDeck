import { readFileSync } from 'fs'
import { resolve } from 'path'
import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import TraditionalView from '@/views/torrents/TraditionalView.vue'
import TrackerDetailCard from '@/views/torrents/components/TrackerDetailCard.vue'
import PageSizeCombobox from '@/components/torrents/PageSizeCombobox.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'
import {
  advancedSearch,
  getActiveTorrents,
  getDownloaderList,
  getDuplicateTorrents,
  getTrackerDomains,
  getTorrentList,
  addTorrent
} from '@/api/torrents'
import type { ApiResponse, Torrent, TorrentListResponseData } from '@/api/torrents'
import { getAllCategories, getAllTags } from '@/api/tag-management'
import {
  getLoadingDirectiveSnapshot,
  installLoadingDirectiveProbe
} from './helpers/loadingDirectiveProbe'

jest.mock('@/store/modules/viewMode', () => ({
  ViewModeModule: {
    currentMode: 'traditional',
    filterPanelCollapsed: false,
    setViewMode: jest.fn(),
    toggleFilterPanel: jest.fn()
  }
}))

jest.mock('@/api/torrents', () => ({
  getTorrentList: jest.fn(),
  addTorrent: jest.fn(),
  addTorrentsBatch: jest.fn(),
  deleteTorrents: jest.fn(),
  pauseTorrents: jest.fn(),
  resumeTorrents: jest.fn(),
  recheckTorrents: jest.fn(),
  reannounceTorrents: jest.fn(),
  getDownloaderList: jest.fn(),
  getTrackerDomains: jest.fn(),
  getActiveTorrents: jest.fn(),
  advancedSearch: jest.fn(),
  getDuplicateTorrents: jest.fn(),
  applySearchTemplate: jest.fn(),
  createSearchTemplate: jest.fn(),
  deleteTorrentsWithLevel: jest.fn(),
  deleteBatchAsync: jest.fn(),
  getBatchDeleteStatus: jest.fn()
}))

jest.mock('@/api/tag-management', () => ({
  getAllCategories: jest.fn(),
  getAllTags: jest.fn()
}))

jest.mock('@/views/torrents/components/TorrentAddDialog.vue', () => ({
  name: 'TorrentAddDialog',
  template: '<div />'
}))
jest.mock('@/views/torrents/components/SetLocationDialog.vue', () => ({
  name: 'SetLocationDialog',
  template: '<div />'
}))
jest.mock('@/views/torrents/components/BatchTransferDialog.vue', () => ({
  name: 'BatchTransferDialog',
  template: '<div />'
}))
jest.mock('@/views/torrents/components/TrackerOperationDialog.vue', () => ({
  name: 'TrackerOperationDialog',
  template: '<div />'
}))
jest.mock('@/views/torrents/components/GlobalReplaceTrackerDialog.vue', () => ({
  name: 'GlobalReplaceTrackerDialog',
  template: '<div />'
}))
jest.mock('@/components/torrents/FilterGroup.vue', () => ({
  name: 'FilterGroup',
  template: '<div />'
}))

const localVue = createLocalVue()
installLoadingDirectiveProbe(localVue)
const mockAdvancedSearch = advancedSearch as jest.MockedFunction<typeof advancedSearch>
const mockGetTorrentList = getTorrentList as jest.MockedFunction<typeof getTorrentList>
const mockGetDownloaderList = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
const mockGetTrackerDomains = getTrackerDomains as jest.MockedFunction<typeof getTrackerDomains>
const mockGetActiveTorrents = getActiveTorrents as jest.MockedFunction<typeof getActiveTorrents>
const mockGetDuplicateTorrents = getDuplicateTorrents as jest.MockedFunction<typeof getDuplicateTorrents>
const mockAddTorrent = addTorrent as jest.MockedFunction<typeof addTorrent>
const mockGetAllCategories = getAllCategories as jest.Mock
const mockGetAllTags = getAllTags as jest.Mock

interface TorrentRow {
  infoId?: string
  downloaderId?: string
  hash: string
  name: string
  checked?: boolean
  status?: string
  progress?: number | null
}

interface PageSizeSuggestion {
  value: string
}

interface TraditionalViewVm extends Vue {
  list: TorrentRow[]
  pageSizeInput: string
  pageSize: number
  pageSizeDropdownExpanded: boolean
  currentPage: number
  listLoading: boolean
  tableScrollTop: number
  tableViewportHeight: number
  showingDuplicates: boolean
  showingSameContent: boolean
  showingSingleErrors: boolean
  listQuery: {
    name_like: string
    sort_by: string
    sort_order: string
    category_like: string
    tags_like: string
    showActiveOnly: boolean
    tracker_domain: string[]
  }
  currentRow: TorrentRow | null
  activeDetailTab: string
  detailTabs: Array<{ label: string, value: string }>
  categoryFilterItems: Array<{ label: string, value: string }>
  tagFilterItems: Array<{ label: string, value: string }>
  virtualizedList: TorrentRow[]
  sortedList: TorrentRow[]
  virtualTopSpacerHeight: number
  virtualBottomSpacerHeight: number
  visibleTableColumnCount: number
  handleRowClick(row: TorrentRow): void
  handleQuickActionCommand(command: string): Promise<void>
  exitSameContentInspection(): Promise<void>
  exitSingleErrorInspection(): Promise<void>
  showAddDialog: boolean
  handleAdd(): Promise<void>
  handlePageSizeSelect(suggestion: PageSizeSuggestion): void
  queryPageSizeSuggestions(
    queryString: string,
    callback: (suggestions: PageSizeSuggestion[]) => void
  ): void
  handleDuplicateSearchToggle(enabled: boolean): Promise<void>
  handleFilter(): void
  handleSort(field: string): void
  handlePageChange(page: number): void
  handleManualRefresh(): void
  performAdvancedSearch(searchParams: Record<string, unknown>): Promise<void>
  applyQueryTemplate(conditions: Record<string, unknown>): Promise<boolean>
  loadActiveSpeed(): Promise<boolean>
  getTorrentSpeed(row: TorrentRow, type: 'download' | 'upload'): number | null
}

const message = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
  info: jest.fn()
}

const InputStub = localVue.extend({
  name: 'ElInputStub',
  inheritAttrs: false,
  props: {
    value: {
      type: [String, Number],
      default: ''
    }
  },
  template: `
    <input
      v-bind="$attrs"
      :value="value"
      @input="$emit('input', $event.target.value)"
      @blur="$emit('blur', $event)"
    />
  `
})

const ButtonStub = localVue.extend({
  name: 'ElButtonStub',
  inheritAttrs: false,
  props: {
    disabled: Boolean
  },
  template: '<button v-bind="$attrs" :disabled="disabled" v-on="$listeners"><slot /></button>'
})

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

const DropdownStub = localVue.extend({
  name: 'ElDropdownStub',
  template: '<div class="el-dropdown-stub"><slot /><slot name="dropdown" /></div>'
})

const DropdownItemStub = localVue.extend({
  name: 'ElDropdownItemStub',
  props: {
    command: {
      type: [String, Number],
      default: ''
    }
  },
  template: '<div class="el-dropdown-item-stub"><slot /></div>'
})

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

function torrentFixture(index: number, overrides: Partial<Torrent> = {}): Torrent {
  return {
    infoId: `info-${index}`,
    downloaderId: 'dl-1',
    downloaderName: 'qb',
    torrentId: `torrent-${index}`,
    hash: `hash-${index}`,
    name: `种子-${index}`,
    savePath: '/downloads',
    size: 0,
    status: 'paused',
    torrentFile: '',
    addedDate: '',
    completedDate: null,
    ratio: 0,
    ratioLimit: 0,
    tags: '',
    category: '',
    superSeeding: false,
    enabled: true,
    auxiliarySeedCount: 1,
    ...overrides
  }
}

function createDeferred<T>(): {
  promise: Promise<T>
  resolve: (value: T) => void
} {
  let resolvePromise!: (value: T) => void
  const promise = new Promise<T>(resolve => {
    resolvePromise = resolve
  })
  return { promise, resolve: resolvePromise }
}

function torrentListResponse(list: Torrent[], total = list.length): ApiResponse<TorrentListResponseData> {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: { list, total, pageSize: 20 }
  }
}

async function flushLifecycle(): Promise<void> {
  for (let index = 0; index < 16; index += 1) {
    await Promise.resolve()
  }
  await new Promise(resolve => setTimeout(resolve, 0))
  await localVue.nextTick()
}

function mountTraditionalView(): Wrapper<Vue> {
  return shallowMount(TraditionalView, {
    localVue,
    methods: {
      startSpeedPolling: jest.fn()
    },
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
      'el-button': ButtonStub,
      'el-input': InputStub,
      'el-dropdown': DropdownStub,
      'el-dropdown-menu': {
        template: '<div class="el-dropdown-menu-stub"><slot /></div>'
      },
      'el-dropdown-item': DropdownItemStub,
      'el-select': {
        template: '<div class="el-select-stub"><slot /></div>'
      },
      'el-option': true,
      'el-progress': true,
      'el-switch': SwitchStub,
      'el-tooltip': {
        template: '<span><slot /></span>'
      },
      'el-dialog': {
        template: '<div><slot /><slot name="footer" /></div>'
      },
      FilterGroup: true,
      TorrentAddDialog: true,
      SetLocationDialog: true,
      BatchTransferDialog: true,
      TrackerOperationDialog: true,
      GlobalReplaceTrackerDialog: true,
      PageSizeCombobox,
      AdvancedSearchBuilder: true,
      // shallowMount 默认会把 LucideIcon stub 成空占位，无法断言 svg/name。
      // 传入真实组件引用，让 <LucideIcon> 真实渲染（见 FilterGroup.spec.ts 同款做法）。
      LucideIcon
    }
  })
}

describe('TraditionalView component regressions', () => {
  let wrapper: Wrapper<Vue>

  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    mockGetTorrentList.mockResolvedValue(successListResponse())
    mockGetDownloaderList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: []
    })
    mockGetTrackerDomains.mockResolvedValue({
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
    mockAdvancedSearch.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [],
        total: 0,
        page: 1,
        pageSize: 20
      }
    })
    mockGetDuplicateTorrents.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [],
        total: 0,
        page: 1,
        pageSize: 20
      }
    })
    mockGetAllCategories.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: []
    })
    mockGetAllTags.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: []
    })
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.destroy()
    }
  })

  it('只显示命名为“删除”的四级删除入口', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()

    const deleteTrigger = wrapper.find('.toolbar-left .danger')
    // 仅统计"删除"下拉菜单内的等级入口，避免被工具栏其它下拉
    // （如"快捷操作"中的快捷删除重复种子）误计入
    const levelItems = wrapper.findAll('.delete-level-menu .el-dropdown-item-stub')

    expect(deleteTrigger.exists()).toBe(true)
    expect(deleteTrigger.text()).toContain('删除')
    expect(wrapper.text()).not.toContain('按等级删除')
    expect(levelItems).toHaveLength(4)
    expect(levelItems.wrappers.map(item => item.text())).toEqual([
      '等级4: 标记为待删除(推荐)',
      '等级3: 移至回收站',
      '等级2: 删除任务(保留数据)',
      '等级1: 完全删除'
    ])
    expect('handleBatchDelete' in (wrapper.vm as object)).toBe(false)
  })

  it('同内容模式的筛选、排序、分页大小、翻页和刷新始终复用列表查询', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm
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

  it('重复任务、高级搜索和查询模板均会退出同内容模式', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm

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
        category_like: '',
        tags_like: '',
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
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm & {
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

  it('删除下拉四个等级项各自渲染正确的 LucideIcon（name + danger）', async() => {
    // 图标迁移回归锚点：4 个等级入口的图标从 el-icon-* 改为 LucideIcon。
    // 任一回退（改回 el-icon、name 写错、等级1 丢失 danger 红色）都会让本用例失败。
    wrapper = mountTraditionalView()
    await flushLifecycle()

    const levelItems = wrapper.findAll('.delete-level-menu .el-dropdown-item-stub')
    expect(levelItems).toHaveLength(4)

    // 下标顺序与 DOM 一致：command 4 / 3 / 2 / 1
    const expectedIcons = ['tag', 'trash-2', 'trash', 'alert-triangle']

    for (let index = 0; index < levelItems.length; index += 1) {
      const item = levelItems.at(index)

      // 真实 svg 渲染，防回退成 missing 占位或 el-icon 字体图标
      expect(item.find('svg').exists()).toBe(true)
      expect(item.find('.lucide-icon--missing').exists()).toBe(false)

      // name prop 契约
      const icon = item.findComponent(LucideIcon)
      expect(icon.exists()).toBe(true)
      expect(icon.props('name')).toBe(expectedIcons[index])

      // 每个图标都带 menu-icon 间距类
      expect(item.find('.lucide-icon').classes()).toContain('menu-icon')
    }

    // 仅等级1（完全删除）带 danger 红色警示
    expect(levelItems.at(3).find('.lucide-icon').classes()).toContain('danger')
    expect(levelItems.at(0).find('.lucide-icon').classes()).not.toContain('danger')
    expect(levelItems.at(1).find('.lucide-icon').classes()).not.toContain('danger')
    expect(levelItems.at(2).find('.lucide-icon').classes()).not.toContain('danger')
  })

  it('详情面板默认 Tracker 且不再包含常规页签', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm
    const row = { hash: 'hash-1', name: '测试种子' }

    const trackerCard = wrapper.findComponent(TrackerDetailCard)
    expect(trackerCard.exists()).toBe(true)
    expect(trackerCard.props('layout')).toBe('traditional')
    expect(trackerCard.props('visible')).toBe(false)
    vm.handleRowClick(row)
    await localVue.nextTick()

    expect(vm.currentRow).toBe(row)
    expect(vm.activeDetailTab).toBe('tracker')
    expect(vm.detailTabs.map(tab => tab.value)).toEqual(['tracker', 'files', 'peers'])
    expect(trackerCard.props('visible')).toBe(true)
    expect(trackerCard.props('activeTab')).toBe('tracker')
  })

  it('同 hash 不同下载器使用任务身份切换详情且只高亮当前行', async() => {
    const first = torrentFixture(1, {
      infoId: 'info-a',
      downloaderId: 'dl-a',
      hash: 'same-hash',
      name: '下载器 A'
    })
    const second = torrentFixture(2, {
      infoId: 'info-b',
      downloaderId: 'dl-b',
      hash: 'same-hash',
      name: '下载器 B'
    })
    mockGetTorrentList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: { list: [first, second], total: 2, pageSize: 20 }
    })

    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm
    const rows = wrapper.findAll('.torrent-row')

    await rows.at(0).trigger('click')
    expect(vm.currentRow?.infoId).toBe('info-a')
    expect(wrapper.findAll('.torrent-row.selected')).toHaveLength(1)
    expect(rows.at(0).classes()).toContain('selected')

    await rows.at(1).trigger('click')
    expect(vm.currentRow?.infoId).toBe('info-b')
    expect(wrapper.findAll('.torrent-row.selected')).toHaveLength(1)
    expect(rows.at(1).classes()).toContain('selected')

    await rows.at(1).trigger('click')
    expect(vm.currentRow).toBeNull()
  })

  it('完整映射接口返回的全部分类与标签', async() => {
    const categories = Array.from({ length: 120 }, (_, index) => `分类${index}`)
    const tags = Array.from({ length: 130 }, (_, index) => `标签${index}`)
    mockGetAllCategories.mockResolvedValue({ code: '200', data: categories })
    mockGetAllTags.mockResolvedValue({ code: '200', data: tags })

    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm

    expect(vm.categoryFilterItems.map(item => item.value)).toEqual(['', ...categories])
    expect(vm.tagFilterItems.map(item => item.value)).toEqual(['', ...tags])
  })

  it('在分类标签与添加时间之间显示可配置的保存路径列', async() => {
    const savePath = '/downloads/library/linux.iso'
    mockGetTorrentList.mockResolvedValue(torrentListResponse([
      torrentFixture(1, { savePath: '', save_path: savePath })
    ]))

    wrapper = mountTraditionalView()
    await flushLifecycle()

    const headers = wrapper.findAll('thead th').wrappers
    const categoryIndex = headers.findIndex(header => header.classes().includes('col-category'))
    const savePathIndex = headers.findIndex(header => header.classes().includes('col-save-path'))
    const addedIndex = headers.findIndex(header => header.classes().includes('col-added'))
    const savePathCell = wrapper.find('tbody td.col-save-path')

    expect(categoryIndex).toBeGreaterThan(-1)
    expect(savePathIndex).toBe(categoryIndex + 1)
    expect(addedIndex).toBe(savePathIndex + 1)
    expect(headers[savePathIndex].text()).toBe('保存路径')
    expect(savePathCell.text()).toBe(savePath)
    expect(savePathCell.attributes('title')).toBe(savePath)
    expect(wrapper.findAll('.column-checkbox-trad').wrappers.map(label => label.text()))
      .toContain('保存路径')
  })

  it('名称列登记列宽并渲染可拖拽手柄，表格按列宽总和严格定宽', async() => {
    wrapper = mountTraditionalView()
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

    // 名称列不再是自适应列：表头内联宽 + 右缘手柄
    const nameHeader = wrapper.find('thead th.col-name')
    expect(nameHeader.attributes('style')).toContain(`width: ${vm.defaultColumnWidths.name}px`)
    const handle = nameHeader.find('.column-resizer')
    expect(handle.exists()).toBe(true)

    // 手柄真实进入拖拽会话：body 拖拽态、按位移更新、mouseup 一次性落盘（视图独立存储 key）
    handle.element.dispatchEvent(new MouseEvent('mousedown', { buttons: 1, clientX: 200, bubbles: true }))
    await localVue.nextTick()
    expect(document.body.classList.contains('column-resizing')).toBe(true)

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 260 }))
    await localVue.nextTick()
    expect(vm.columnWidths.name).toBe(vm.defaultColumnWidths.name + 60)

    document.dispatchEvent(new MouseEvent('mouseup', { clientX: 260 }))
    await localVue.nextTick()
    expect(document.body.classList.contains('column-resizing')).toBe(false)
    expect(JSON.parse(localStorage.getItem('btdeck_traditional_column_widths') || '{}'))
      .toEqual(expect.objectContaining({ name: vm.defaultColumnWidths.name + 60 }))
  })

  it('传统视图展示同步任务持久化的辅种数量', async() => {
    mockGetTorrentList.mockResolvedValue(torrentListResponse([
      torrentFixture(1, { auxiliarySeedCount: 31 })
    ]))

    wrapper = mountTraditionalView()
    await flushLifecycle()

    expect(wrapper.find('thead th.col-auxiliary-seed-count').text()).toBe('辅种数量')
    expect(wrapper.find('tbody td.col-auxiliary-seed-count').text()).toBe('31')
  })

  it('状态列为 tracker 异常种子叠加 Tracker异常 标签（error 状态与正常种子不打）', async() => {
    mockGetTorrentList.mockResolvedValue(torrentListResponse([
      torrentFixture(1, { status: 'seeding', hasTrackerError: true, lastAnnounceMsg: 'You cannot seed the same torrent' }),
      torrentFixture(2, { status: 'error', hasTrackerError: true }),
      torrentFixture(3, { status: 'seeding' })
    ]))

    wrapper = mountTraditionalView()
    await flushLifecycle()

    const rows = wrapper.findAll('tbody tr').wrappers
    expect(rows).toHaveLength(3)
    const taggedRows = rows.filter(row => row.find('.tracker-error-tag').exists())
    expect(taggedRows).toHaveLength(1)
    expect(taggedRows[0].find('.tracker-error-tag').text()).toBe('Tracker异常')
    expect(taggedRows[0].find('.col-status .status-badge-trad').text()).toBe('做种中')
    expect(taggedRows[0].find('.tracker-error-tag').attributes('title')).toContain('You cannot seed')
    // error 状态行（已有"错误"徽标）与正常种子行都不打标
    const errorRow = rows.find(row => row.find('.col-status .status-badge-trad').classes().includes('error'))
    expect(errorRow).toBeDefined()
    if (errorRow) {
      expect(errorRow.find('.tracker-error-tag').exists()).toBe(false)
    }
    const normalRow = rows.find(row => row.text().includes('种子-3'))
    expect(normalRow).toBeDefined()
    if (normalRow) {
      expect(normalRow.find('.tracker-error-tag').exists()).toBe(false)
    }
  })

  it('旧版列偏好缺少 savePath 时仍默认显示新增路径列', async() => {
    localStorage.setItem('traditional_columns_visibility', JSON.stringify({ name: false }))
    mockGetTorrentList.mockResolvedValue(torrentListResponse([
      torrentFixture(1, { savePath: '/downloads/legacy-compatible' })
    ]))

    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm

    expect(wrapper.find('thead th.col-name').exists()).toBe(false)
    expect(wrapper.find('thead th.col-save-path').exists()).toBe(true)
    expect(wrapper.find('tbody td.col-save-path').text()).toBe('/downloads/legacy-compatible')
    expect(vm.visibleTableColumnCount).toBe(14)
  })

  it('显式隐藏保存路径时同步移除表头、数据列和虚拟占位列计数', async() => {
    localStorage.setItem('traditional_columns_visibility', JSON.stringify({ savePath: false }))
    mockGetTorrentList.mockResolvedValue(torrentListResponse([
      torrentFixture(1, { savePath: '/downloads/hidden' })
    ]))

    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm

    expect(wrapper.find('thead th.col-save-path').exists()).toBe(false)
    expect(wrapper.find('tbody td.col-save-path').exists()).toBe(false)
    expect(vm.visibleTableColumnCount).toBe(14)
  })

  it('分页组合框完整展示预设并用箭头切换展开与收起', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    const vm = wrapper.vm as unknown as TraditionalViewVm
    let suggestions: PageSizeSuggestion[] = []

    vm.queryPageSizeSuggestions('20', result => { suggestions = result })

    expect(wrapper.findAll('.page-size-combobox')).toHaveLength(1)
    expect(wrapper.find('.page-size-select').exists()).toBe(false)
    expect(wrapper.find('.custom-page-size').exists()).toBe(false)
    expect(suggestions.map(item => item.value)).toEqual(['20', '50', '100', '500', '1000'])

    const toggle = wrapper.find('.page-size-toggle')
    expect(toggle.classes()).toContain('el-icon-arrow-up')
    expect(toggle.element.tagName).toBe('BUTTON')

    await toggle.trigger('click')
    await localVue.nextTick()
    expect(vm.pageSizeDropdownExpanded).toBe(true)
    expect(toggle.classes()).toContain('el-icon-arrow-down')
    expect(wrapper.findAll('.page-size-options button').wrappers.map(option => option.text()))
      .toEqual(['20', '50', '100', '500', '1000'])

    await toggle.trigger('click')
    expect(vm.pageSizeDropdownExpanded).toBe(false)
    expect(toggle.classes()).toContain('el-icon-arrow-up')

    await toggle.trigger('click')
    await localVue.nextTick()
    expect(vm.pageSizeDropdownExpanded).toBe(true)
    expect(toggle.classes()).toContain('el-icon-arrow-down')

    await wrapper.findAll('.page-size-options button').at(1).trigger('click')
    await flushLifecycle()

    expect(vm.pageSize).toBe(50)
    expect(vm.pageSizeInput).toBe('50')
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 0, limit: 50 })
    )
  })

  it('分页组合框在 Enter 和失焦时生效、钳制到 100000 并回到第 1 页', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    const vm = wrapper.vm as unknown as TraditionalViewVm
    const input = wrapper.find('.page-size-combobox input')

    vm.currentPage = 4
    await input.setValue('100001')
    await input.trigger('keyup.enter')
    await flushLifecycle()

    expect(vm.pageSize).toBe(100000)
    expect(vm.pageSizeInput).toBe('100000')
    expect(vm.currentPage).toBe(1)
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 0, limit: 100000 })
    )

    vm.currentPage = 3
    await input.setValue('50')
    await input.trigger('blur')
    await flushLifecycle()

    expect(vm.pageSize).toBe(50)
    expect(vm.currentPage).toBe(1)
    expect(mockGetTorrentList).toHaveBeenLastCalledWith(
      expect.objectContaining({ skip: 0, limit: 50 })
    )
  })

  it('传统视图重复任务开关默认关闭，用户开启后渲染绿色状态', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    mockGetDuplicateTorrents.mockClear()
    const vm = wrapper.vm as unknown as TraditionalViewVm
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

  it('重复任务翻页、改分页大小和刷新始终保留重复任务数据源', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    mockGetDuplicateTorrents.mockClear()
    mockGetActiveTorrents.mockClear()
    const vm = wrapper.vm as unknown as TraditionalViewVm

    vm.listQuery.category_like = 'movies'
    vm.listQuery.tags_like = 'featured'
    vm.listQuery.showActiveOnly = true
    await vm.handleDuplicateSearchToggle(true)
    expect(vm.showingDuplicates).toBe(true)
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({
        page: 1,
        pageSize: 20,
        sort_by: 'added_date',
        sort_order: 'desc',
        category_like: 'movies',
        tags_like: 'featured',
        active_only: true
      })
    )

    mockGetDuplicateTorrents.mockClear()
    vm.listQuery.name_like = 'needle'
    vm.handleFilter()
    await flushLifecycle()
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({ name_like: 'needle', page: 1 })
    )
    expect(mockGetTorrentList).not.toHaveBeenCalled()

    mockGetDuplicateTorrents.mockClear()
    vm.handleSort('name')
    await flushLifecycle()
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort_by: 'name', sort_order: 'desc' })
    )

    mockGetDuplicateTorrents.mockClear()
    vm.handlePageChange(2)
    await flushLifecycle()
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2, pageSize: 20 })
    )

    const input = wrapper.find('.page-size-combobox input')
    await input.setValue('100000')
    await input.trigger('keyup.enter')
    await flushLifecycle()
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, pageSize: 100000 })
    )

    mockGetDuplicateTorrents.mockClear()
    vm.handleManualRefresh()
    await flushLifecycle()
    expect(mockGetDuplicateTorrents).toHaveBeenCalledTimes(1)
    expect(mockGetTorrentList).not.toHaveBeenCalled()
    expect(mockGetActiveTorrents).toHaveBeenCalledTimes(1)

    mockGetTorrentList.mockClear()
    await vm.handleDuplicateSearchToggle(false)
    expect(vm.showingDuplicates).toBe(false)
    expect(mockGetTorrentList).toHaveBeenCalledTimes(1)
  })

  it('切页开始加载时立即关闭上一页详情', async() => {
    mockGetTorrentList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: { list: [torrentFixture(1)], total: 2, pageSize: 20 }
    })
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm

    await wrapper.find('.torrent-row').trigger('click')
    expect(vm.currentRow).not.toBeNull()

    vm.handlePageChange(2)
    expect(vm.currentRow).toBeNull()
    await flushLifecycle()
  })

  it('查询等待期间向 loading 指令传入 fullscreen+lock，失败后解除 loading', async() => {
    let rejectRequest: (reason?: unknown) => void = () => undefined
    const pendingRequest = new Promise<never>((_resolve, reject) => {
      rejectRequest = reject
    })
    mockGetTorrentList.mockImplementationOnce(() => pendingRequest)
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()

    try {
      wrapper = mountTraditionalView()
      await flushLifecycle()
      const vm = wrapper.vm as unknown as TraditionalViewVm
      const loadingTarget = wrapper.find('.table-container').element

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

  it('忽略过期分页响应且旧请求结束不会提前关闭新请求 loading', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm
    const pageTwo = createDeferred<ApiResponse<TorrentListResponseData>>()
    const pageThree = createDeferred<ApiResponse<TorrentListResponseData>>()
    mockGetTorrentList
      .mockImplementationOnce(() => pageTwo.promise)
      .mockImplementationOnce(() => pageThree.promise)

    vm.handlePageChange(2)
    vm.handlePageChange(3)
    expect(vm.listLoading).toBe(true)

    pageTwo.resolve(torrentListResponse([
      torrentFixture(2, { name: '过期第 2 页' })
    ]))
    await flushLifecycle()
    expect(vm.list).toEqual([])
    expect(vm.listLoading).toBe(true)

    pageThree.resolve(torrentListResponse([
      torrentFixture(3, { name: '当前第 3 页' })
    ]))
    await flushLifecycle()
    expect(vm.list.map(row => row.name)).toEqual(['当前第 3 页'])
    expect(vm.listLoading).toBe(false)
  })

  it('高级搜索翻页、改分页大小及模板均使用当前分页大小', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm
    const input = wrapper.find('.page-size-input')

    await input.setValue('500')
    await input.trigger('keyup.enter')
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    mockAdvancedSearch.mockClear()

    const strictSearchParams = {
      complex_search: true,
      groups_count: 1,
      groups: JSON.stringify([{
        logic: 'AND',
        conditions: [{
          field: 'name',
          operator: 'contains',
          value: 'needle'
        }]
      }]),
      between_group_logics: JSON.stringify([])
    }
    await vm.performAdvancedSearch(strictSearchParams)
    expect(mockAdvancedSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({
        page: 1,
        limit: 500,
        condition_groups: [{
          logic: 'AND',
          conditions: [{
            field: 'name',
            operator: 'contains',
            value: 'needle'
          }]
        }],
        between_group_logics: []
      })
    )

    mockAdvancedSearch.mockClear()
    vm.handlePageChange(2)
    await flushLifecycle()
    expect(mockAdvancedSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({
        page: 2,
        limit: 500,
        condition_groups: expect.any(Array)
      })
    )
    expect(mockGetTorrentList).not.toHaveBeenCalled()

    await input.setValue('1000')
    await input.trigger('keyup.enter')
    await flushLifecycle()
    expect(mockAdvancedSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({
        page: 1,
        limit: 1000,
        condition_groups: expect.any(Array)
      })
    )

    mockAdvancedSearch.mockClear()
    const applied = await vm.applyQueryTemplate({
      source: 'advanced',
      version: 1,
      condition_groups: [{
        logic: 'and',
        conditions: [{ field: 'name', operator: 'contains', value: 'template' }]
      }],
      sort_by: 'name',
      sort_order: 'asc'
    })
    expect(applied).toBe(true)
    expect(mockAdvancedSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, limit: 1000, sort_by: 'name', sort_order: 'asc' })
    )
  })

  it('速度轮询用下载器与 hash 精确更新同 hash 的不同任务', async() => {
    mockGetTorrentList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [
          torrentFixture(1, { infoId: 'info-a', downloaderId: 'dl-a', hash: 'same-hash' }),
          torrentFixture(2, { infoId: 'info-b', downloaderId: 'dl-b', hash: 'same-hash' })
        ],
        total: 2,
        pageSize: 20
      }
    })
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm

    mockGetActiveTorrents.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: [
        {
          hash: 'same-hash',
          downloader_id: 'dl-a',
          downloadSpeed: 100,
          uploadSpeed: 0,
          progress: 25,
          num_seeds: 0,
          num_leechs: 0
        },
        {
          hash: 'same-hash',
          downloader_id: 'dl-b',
          downloadSpeed: 200,
          uploadSpeed: 0,
          progress: 75,
          num_seeds: 0,
          num_leechs: 0
        }
      ]
    })

    await vm.loadActiveSpeed()

    expect(vm.getTorrentSpeed(vm.list[0], 'download')).toBe(100)
    expect(vm.getTorrentSpeed(vm.list[1], 'download')).toBe(200)
    expect(vm.list[0].progress).toBe(25)
    expect(vm.list[1].progress).toBe(75)
    expect(vm.sortedList.map(row => row.infoId)).toEqual(['info-b', 'info-a'])
  })

  it('兼容未返回下载器 ID 的旧速度响应并更新同 hash 桶', async() => {
    mockGetTorrentList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: [
          torrentFixture(1, { infoId: 'info-a', downloaderId: 'dl-a', hash: 'same-hash' }),
          torrentFixture(2, { infoId: 'info-b', downloaderId: 'dl-b', hash: 'same-hash' })
        ],
        total: 2,
        pageSize: 20
      }
    })
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm
    mockGetActiveTorrents.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: [{
        hash: 'same-hash',
        downloadSpeed: 300,
        uploadSpeed: 0,
        progress: 60,
        num_seeds: 0,
        num_leechs: 0
      }]
    })

    await vm.loadActiveSpeed()

    expect(vm.list.map(row => row.progress)).toEqual([60, 60])
    expect(vm.list.map(row => vm.getTorrentSpeed(row, 'download'))).toEqual([300, 300])
  })

  it('长列表仅渲染当前虚拟窗口和上下缓冲行', async() => {
    const longList: Torrent[] = Array.from({ length: 1000 }, (_, index) => ({
      infoId: `info-${index}`,
      downloaderId: 'dl-1',
      downloaderName: 'qb',
      torrentId: `torrent-${index}`,
      hash: `hash-${index}`,
      name: `种子-${index}`,
      savePath: '/downloads',
      size: 0,
      status: 'paused',
      torrentFile: '',
      addedDate: '',
      completedDate: null,
      ratio: 0,
      ratioLimit: 0,
      tags: '',
      category: '',
      superSeeding: false,
      enabled: true
    }))
    mockGetTorrentList.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: {
        list: longList,
        total: longList.length,
        pageSize: 1000
      }
    })
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm

    await wrapper.setData({
      tableViewportHeight: 320,
      tableScrollTop: 640
    })

    expect(vm.virtualizedList).toHaveLength(26)
    expect(vm.virtualTopSpacerHeight).toBeGreaterThan(0)
    expect(vm.virtualBottomSpacerHeight).toBeGreaterThan(0)
  })

  it('真实 scroll 经 RAF 更新窗口，ResizeObserver 更新高度且销毁时清理资源', async() => {
    let resizeCallback: ResizeObserverCallback | null = null
    const observe = jest.fn()
    const disconnect = jest.fn()
    const OriginalResizeObserver = global.ResizeObserver
    const OriginalRequestAnimationFrame = window.requestAnimationFrame
    const OriginalCancelAnimationFrame = window.cancelAnimationFrame
    const frames = new Map<number, FrameRequestCallback>()
    let frameId = 0

    class ResizeObserverStub {
      constructor(callback: ResizeObserverCallback) {
        resizeCallback = callback
      }

      observe = observe
      disconnect = disconnect
      unobserve = jest.fn()
    }

    global.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
    window.requestAnimationFrame = jest.fn((callback: FrameRequestCallback) => {
      frameId += 1
      frames.set(frameId, callback)
      return frameId
    })
    window.cancelAnimationFrame = jest.fn((id: number) => {
      frames.delete(id)
    })

    try {
      wrapper = mountTraditionalView()
      const container = wrapper.find('.table-container').element as HTMLElement
      let viewportHeight = 360
      Object.defineProperty(container, 'clientHeight', {
        configurable: true,
        get: () => viewportHeight
      })
      await flushLifecycle()
      const vm = wrapper.vm as unknown as TraditionalViewVm

      expect(observe).toHaveBeenCalledWith(container)
      expect(resizeCallback).not.toBeNull()
      const invokeResize = resizeCallback as unknown as ResizeObserverCallback
      invokeResize([], {} as ResizeObserver)
      expect(vm.tableViewportHeight).toBe(360)

      container.scrollTop = 640
      await wrapper.find('.table-container').trigger('scroll')
      expect(vm.tableScrollTop).toBe(0)
      const firstFrame = frames.get(1)
      expect(firstFrame).toBeDefined()
      firstFrame?.(0)
      await localVue.nextTick()
      expect(vm.tableScrollTop).toBe(640)

      viewportHeight = 480
      invokeResize([], {} as ResizeObserver)
      expect(vm.tableViewportHeight).toBe(480)

      container.scrollTop = 960
      await wrapper.find('.table-container').trigger('scroll')
      expect(frames.has(2)).toBe(true)
      wrapper.destroy()

      expect(window.cancelAnimationFrame).toHaveBeenCalledWith(2)
      expect(disconnect).toHaveBeenCalledTimes(1)
    } finally {
      global.ResizeObserver = OriginalResizeObserver
      window.requestAnimationFrame = OriginalRequestAnimationFrame
      window.cancelAnimationFrame = OriginalCancelAnimationFrame
    }
  })

  it('handleAdd 只刷新列表与关闭对话框，不重复调用 addTorrent', async() => {
    // prod-hotfix-2026-07-19 回归锚点：
    // TorrentAddDialog 内部已通过 addTorrentsBatch 完成种子添加，成功后
    // emit('confirm', this.form)。本视图 handleAdd 不应再调用单条 addTorrent——
    // this.form 不含 torrent_file（File 对象），重复调用会触发 422
    // ("Expected UploadFile, received: <class 'str'>")。
    // 与 index.vue 的 handleAdd 行为对齐：只关闭对话框 + 刷新列表。
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm

    mockGetTorrentList.mockClear()
    mockAddTorrent.mockClear()
    vm.showAddDialog = true
    await localVue.nextTick()
    expect(vm.showAddDialog).toBe(true)

    await vm.handleAdd()

    // 关闭对话框
    expect(vm.showAddDialog).toBe(false)
    // 刷新列表（getTorrentList 被调用）
    expect(mockGetTorrentList).toHaveBeenCalled()
    // 关键契约：不再调用单条 addTorrent
    expect(mockAddTorrent).not.toHaveBeenCalled()
  })
})

describe('TraditionalView layout contracts', () => {
  const source = readFileSync(
    resolve(__dirname, '../../src/views/torrents/TraditionalView.vue'),
    'utf8'
  )
  const listSource = readFileSync(
    resolve(__dirname, '../../src/views/torrents/index.vue'),
    'utf8'
  )
  const listThemeSource = readFileSync(
    resolve(__dirname, '../../src/styles/torrent-theme.scss'),
    'utf8'
  )
  const traditionalThemeSource = readFileSync(
    resolve(__dirname, '../../src/styles/traditional-view-theme.scss'),
    'utf8'
  )
  const trackerDetailCardSource = readFileSync(
    resolve(__dirname, '../../src/views/torrents/components/TrackerDetailCard.vue'),
    'utf8'
  )
  const sharedTrackerTableSource = readFileSync(
    resolve(__dirname, '../../src/styles/_tracker-table.scss'),
    'utf8'
  )

  it('元数据面板绝对定位在固定分页栏上方且不占列表布局', () => {
    expect(source).toMatch(/\.table-area\s*\{[\s\S]*?position:\s*relative;[\s\S]*?overflow:\s*hidden;/)
    expect(trackerDetailCardSource).toMatch(/&--traditional\s*\{[\s\S]*?position:\s*absolute;/)
    expect(trackerDetailCardSource).toContain('bottom: calc(var(--trad-pagination-height) + 8px);')
    expect(trackerDetailCardSource).toContain('pointer-events: none;')
    expect(trackerDetailCardSource).toMatch(/&\.is-open\s*\{[\s\S]*?pointer-events:\s*auto;/)
    expect(source).not.toContain('detail-panel-trad')
  })

  it('传统列表锁定视口高度并使用表格虚拟窗口', () => {
    expect(source).toMatch(/\.traditional-page\s*\{[\s\S]*?height:\s*calc\(100vh - 84px\);/)
    expect(source).toMatch(/\.table-container\s*\{[\s\S]*?flex:\s*1 1 0;[\s\S]*?height:\s*0;[\s\S]*?overflow:\s*auto;/)
    expect(source).toContain('v-for="(torrent, index) in virtualizedList"')
    expect(source).toContain('class="virtual-spacer-row"')
    expect(source).toContain('--trad-row-height: 32px;')
  })

  it('左侧过滤内容保留独立滚动所需的 flex 最小高度和滚动条空间', () => {
    expect(source).toMatch(/\.filter-panel,[\s\S]*?\.filter-panel-content\s*\{[\s\S]*?min-height:\s*0;/)
    expect(source).toMatch(/\.filter-panel-content\s*\{[\s\S]*?overscroll-behavior:\s*contain;/)
    expect(source).toContain('scrollbar-gutter: stable;')
  })

  it('两种视图使用同一个 TrackerDetailCard 组件', () => {
    for (const viewSource of [source, listSource]) {
      expect(viewSource).toContain('<TrackerDetailCard')
      expect(viewSource).toContain("import TrackerDetailCard from './components/TrackerDetailCard.vue'")
      expect(viewSource).toContain('TrackerDetailCard,')
      expect(viewSource).toContain(':tracker-info="(currentRow && (currentRow.tracker_info || currentRow.trackerInfo)) || []"')
      expect(viewSource).toContain('@reannounce="handleTrackerReannounce"')
      expect(viewSource).not.toContain('<table class="tracker-table tracker-table-detail">')
    }
    expect(listSource).toContain('layout="list"')
    expect(source).toContain('layout="traditional"')
    expect(trackerDetailCardSource).toContain('<table class="tracker-table tracker-table-detail">')
    expect(trackerDetailCardSource).toContain('<th style="width: 80px;">Announce</th>')
    expect(trackerDetailCardSource).toContain('<th>Announce信息</th>')
    expect(trackerDetailCardSource).toContain('<th style="width: 80px;">Scrape</th>')
    expect(trackerDetailCardSource).toContain('trackerAnnounceSuccess(')
    expect(trackerDetailCardSource).toContain('trackerStatusClass(')
    expect(listSource).not.toContain('<th>Tracker地址</th>')
    expect(listSource).not.toContain('<th>Scrape信息</th>')
  })

  it('共享 TrackerDetailCard 组件引用同一份紧凑视觉样式', () => {
    expect(sharedTrackerTableSource).toContain('@mixin tracker-table-styles')
    expect(sharedTrackerTableSource).toContain('font-size: 11px;')
    expect(sharedTrackerTableSource).toContain('padding: 5px;')
    expect(trackerDetailCardSource).toContain("@import '@/styles/tracker-table';")
    expect(trackerDetailCardSource).toContain('@include tracker-table-styles;')
    expect(listThemeSource).not.toContain("@import './tracker-table';")
    expect(traditionalThemeSource).not.toContain("@import './tracker-table';")
    expect(source).not.toContain('@include tracker-table-styles;')
  })
})
