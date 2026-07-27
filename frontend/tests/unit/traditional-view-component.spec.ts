import { readFileSync } from 'fs'
import { resolve } from 'path'
import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import TraditionalView from '@/views/torrents/TraditionalView.vue'
import PageSizeCombobox from '@/components/torrents/PageSizeCombobox.vue'
import {
  advancedSearch,
  getActiveTorrents,
  getDownloaderList,
  getDuplicateTorrents,
  getTorrentList,
  addTorrent
} from '@/api/torrents'
import type { ApiResponse, Torrent, TorrentListResponseData } from '@/api/torrents'
import { getAllCategories, getAllTags } from '@/api/tag-management'

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
const mockAdvancedSearch = advancedSearch as jest.MockedFunction<typeof advancedSearch>
const mockGetTorrentList = getTorrentList as jest.MockedFunction<typeof getTorrentList>
const mockGetDownloaderList = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
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
  currentRow: TorrentRow | null
  activeDetailTab: string
  detailTabs: Array<{ label: string, value: string }>
  categoryFilterItems: Array<{ label: string, value: string }>
  tagFilterItems: Array<{ label: string, value: string }>
  virtualizedList: TorrentRow[]
  sortedList: TorrentRow[]
  virtualTopSpacerHeight: number
  virtualBottomSpacerHeight: number
  handleRowClick(row: TorrentRow): void
  showAddDialog: boolean
  handleAdd(): Promise<void>
  handlePageSizeSelect(suggestion: PageSizeSuggestion): void
  queryPageSizeSuggestions(
    queryString: string,
    callback: (suggestions: PageSizeSuggestion[]) => void
  ): void
  handleShowDuplicateTorrents(): Promise<void>
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
      AdvancedSearchBuilder: true
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
    const levelItems = wrapper.findAll('.el-dropdown-item-stub')

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

  it('详情面板默认 Tracker 且不再包含常规页签', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    const vm = wrapper.vm as unknown as TraditionalViewVm
    const row = { hash: 'hash-1', name: '测试种子' }

    expect(wrapper.find('.detail-panel-trad').classes()).not.toContain('open')
    vm.handleRowClick(row)
    await localVue.nextTick()

    expect(vm.currentRow).toBe(row)
    expect(vm.activeDetailTab).toBe('tracker')
    expect(vm.detailTabs.map(tab => tab.value)).toEqual(['tracker', 'files', 'peers'])
    expect(wrapper.find('.detail-panel-trad').classes()).toContain('open')
    expect(wrapper.find('.detail-tabs-compact').text()).not.toContain('常规')
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
    expect(toggle.classes()).toContain('el-icon-arrow-down')
    expect(toggle.element.tagName).toBe('BUTTON')

    await toggle.trigger('click')
    await localVue.nextTick()
    expect(vm.pageSizeDropdownExpanded).toBe(true)
    expect(toggle.classes()).toContain('el-icon-arrow-up')
    expect(wrapper.findAll('.page-size-options button').wrappers.map(option => option.text()))
      .toEqual(['20', '50', '100', '500', '1000'])

    await toggle.trigger('click')
    expect(vm.pageSizeDropdownExpanded).toBe(false)
    expect(toggle.classes()).toContain('el-icon-arrow-down')

    await toggle.trigger('click')
    await localVue.nextTick()
    expect(vm.pageSizeDropdownExpanded).toBe(true)
    expect(toggle.classes()).toContain('el-icon-arrow-up')

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

  it('重复任务翻页、改分页大小和刷新始终保留重复任务数据源', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    mockGetDuplicateTorrents.mockClear()
    mockGetActiveTorrents.mockClear()
    const vm = wrapper.vm as unknown as TraditionalViewVm

    await vm.handleShowDuplicateTorrents()
    expect(vm.showingDuplicates).toBe(true)
    expect(mockGetDuplicateTorrents).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, pageSize: 20 })
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

  it('元数据面板绝对定位在固定分页栏上方且不占列表布局', () => {
    expect(source).toMatch(/\.table-area\s*\{[\s\S]*?position:\s*relative;[\s\S]*?overflow:\s*hidden;/)
    expect(source).toMatch(/\.detail-panel-trad\s*\{[\s\S]*?position:\s*absolute;/)
    expect(source).toContain('bottom: calc(var(--trad-pagination-height) + 8px);')
    expect(source).toContain('pointer-events: none;')
    expect(source).toMatch(/&\.open\s*\{[\s\S]*?pointer-events:\s*auto;/)
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
})
