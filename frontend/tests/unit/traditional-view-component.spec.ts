import { readFileSync } from 'fs'
import { resolve } from 'path'
import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import TraditionalView from '@/views/torrents/TraditionalView.vue'
import {
  getActiveTorrents,
  getDownloaderList,
  getDuplicateTorrents,
  getTorrentList
} from '@/api/torrents'
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
const mockGetTorrentList = getTorrentList as jest.MockedFunction<typeof getTorrentList>
const mockGetDownloaderList = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
const mockGetActiveTorrents = getActiveTorrents as jest.MockedFunction<typeof getActiveTorrents>
const mockGetDuplicateTorrents = getDuplicateTorrents as jest.MockedFunction<typeof getDuplicateTorrents>
const mockGetAllCategories = getAllCategories as jest.Mock
const mockGetAllTags = getAllTags as jest.Mock

interface TorrentRow {
  hash: string
  name: string
}

interface TraditionalViewVm extends Vue {
  pageSizeInput: string
  pageSize: number
  currentPage: number
  showingDuplicates: boolean
  currentRow: TorrentRow | null
  activeDetailTab: string
  detailTabs: Array<{ label: string, value: string }>
  categoryFilterItems: Array<{ label: string, value: string }>
  tagFilterItems: Array<{ label: string, value: string }>
  handleRowClick(row: TorrentRow): void
  handleShowDuplicateTorrents(): Promise<void>
  handlePageChange(page: number): void
  handleManualRefresh(): void
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

async function flushLifecycle(): Promise<void> {
  for (let index = 0; index < 8; index += 1) {
    await Promise.resolve()
  }
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

  it('自定义分页在 Enter 和失焦时生效、钳制到 100000 并回到第 1 页', async() => {
    wrapper = mountTraditionalView()
    await flushLifecycle()
    mockGetTorrentList.mockClear()
    const vm = wrapper.vm as unknown as TraditionalViewVm
    const input = wrapper.find('.page-size-input')

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

    const input = wrapper.find('.page-size-input')
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

  it('左侧过滤内容保留独立滚动所需的 flex 最小高度和滚动条空间', () => {
    expect(source).toMatch(/\.filter-panel,[\s\S]*?\.filter-panel-content\s*\{[\s\S]*?min-height:\s*0;/)
    expect(source).toMatch(/\.filter-panel-content\s*\{[\s\S]*?overscroll-behavior:\s*contain;/)
    expect(source).toContain('scrollbar-gutter: stable;')
  })
})
