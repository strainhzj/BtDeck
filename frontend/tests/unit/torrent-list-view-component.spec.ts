import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import TorrentsManagement from '@/views/torrents/index.vue'
import PageSizeCombobox from '@/components/torrents/PageSizeCombobox.vue'
import LucideIcon from '@/components/common/LucideIcon.vue'
import {
  deleteBatchAsync,
  getActiveTorrents,
  getBatchDeleteStatus,
  getDownloaderList,
  getTorrentList
} from '@/api/torrents'
import type { Torrent } from '@/api/torrents'

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
  reannounceTorrents: jest.fn(),
  getActiveTorrents: jest.fn(),
  applySearchTemplate: jest.fn(),
  createSearchTemplate: jest.fn()
}))

const localVue = createLocalVue()
const mockGetTorrentList = getTorrentList as jest.MockedFunction<typeof getTorrentList>
const mockGetDownloaderList = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
const mockGetActiveTorrents = getActiveTorrents as jest.MockedFunction<typeof getActiveTorrents>
const mockDeleteBatchAsync = deleteBatchAsync as jest.MockedFunction<typeof deleteBatchAsync>
const mockGetBatchDeleteStatus = getBatchDeleteStatus as jest.MockedFunction<typeof getBatchDeleteStatus>
localVue.directive('loading', {})

interface ListQueryState {
  skip: number
  limit: number
  sort_by: string
  sort_order: string
}

interface TorrentListViewVm extends Vue {
  currentPage: number
  pageSize: number
  pageSizeInput: string
  pageSizeDropdownExpanded: boolean
  listQuery: ListQueryState
  callDeleteWithLevelAPI(torrents: Torrent[], level: number): Promise<void>
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
      'el-switch': true
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
    enabled: true
  }
}

describe('torrent list view pagination and sorting', () => {
  let wrapper: Wrapper<Vue>
  let consoleDebugSpy: jest.SpyInstance

  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
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
  })

  afterEach(() => {
    wrapper?.destroy()
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
})
