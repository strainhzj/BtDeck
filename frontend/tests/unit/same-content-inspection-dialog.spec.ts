import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import SameContentInspectionDialog from '@/components/torrents/SameContentInspectionDialog.vue'
import { getSameContentInspection } from '@/api/torrents'
import type {
  SameContentInspectionMode,
  SameContentInspectionResponse
} from '@/api/torrents'

jest.mock('@/api/torrents', () => ({
  getSameContentInspection: jest.fn()
}))

const localVue = createLocalVue()
localVue.directive('loading', {})

const mockGetSameContentInspection = getSameContentInspection as jest.MockedFunction<
  typeof getSameContentInspection
>

interface SameContentInspectionDialogVm extends Vue {
  mode: SameContentInspectionMode
  result: SameContentInspectionResponse | null
  currentPage: number
  handleModeChange(mode: SameContentInspectionMode): void
  handlePageChange(page: number): void
  handleClose(): void
}

const responseData: SameContentInspectionResponse = {
  total: 1,
  page: 1,
  pageSize: 10,
  summary: {
    candidate_group_count: 1,
    candidate_torrent_count: 2,
    error_group_count: 1,
    error_torrent_count: 1
  },
  list: [
    {
      group_key: 'group-1',
      name: 'Same.Name',
      size: 1024,
      copy_count: 2,
      distinct_hash_count: 2,
      downloader_count: 1,
      error_count: 1,
      tracker_hosts: ['tracker.example'],
      last_updated_at: null,
      items: [
        {
          info_id: 'error-1',
          downloader_id: 'dl-1',
          downloader_name: 'Transmission',
          hash: 'hash-error-1',
          status: 'error',
          error_reason: 'No data found',
          has_tracker_error: false,
          is_error: true,
          error_types: ['torrent_status', 'error_reason'],
          tracker_hosts: ['tracker.example'],
          tracker_issues: [],
          updated_at: null
        }
      ]
    }
  ]
}

function successResponse(data: SameContentInspectionResponse = responseData) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data
  }
}

async function flushRequests(): Promise<void> {
  for (let index = 0; index < 8; index += 1) {
    await Promise.resolve()
  }
  await localVue.nextTick()
}

function mountDialog(visible = true): Wrapper<Vue> {
  return shallowMount(SameContentInspectionDialog, {
    localVue,
    propsData: { visible },
    stubs: {
      'el-dialog': {
        template: '<div><slot /><slot name="footer" /></div>'
      },
      'el-radio-group': {
        template: '<div><slot /></div>'
      },
      'el-radio-button': true,
      'el-alert': true,
      'el-button': true,
      'el-pagination': true
    }
  })
}

describe('SameContentInspectionDialog', () => {
  let wrapper: Wrapper<Vue>

  beforeEach(() => {
    jest.clearAllMocks()
    mockGetSameContentInspection.mockResolvedValue(successResponse())
  })

  afterEach(() => {
    wrapper?.destroy()
  })

  it('打开时自动查询完整排查结果', async() => {
    wrapper = mountDialog(true)
    await flushRequests()

    const vm = wrapper.vm as unknown as SameContentInspectionDialogVm
    expect(mockGetSameContentInspection).toHaveBeenCalledWith({
      mode: 'all',
      page: 1,
      pageSize: 10
    })
    expect(vm.result).toEqual(responseData)
    expect(wrapper.text()).toContain('候选组')
    expect(wrapper.text()).toContain('Same.Name')
  })

  it('切换仅错误模式时重置分页并重新查询', async() => {
    wrapper = mountDialog(true)
    await flushRequests()
    const vm = wrapper.vm as unknown as SameContentInspectionDialogVm
    mockGetSameContentInspection.mockClear()
    vm.currentPage = 4

    vm.handleModeChange('errors')
    await flushRequests()

    expect(vm.mode).toBe('errors')
    expect(vm.currentPage).toBe(1)
    expect(mockGetSameContentInspection).toHaveBeenCalledWith({
      mode: 'errors',
      page: 1,
      pageSize: 10
    })
  })

  it('按候选组分页并在关闭时同步父组件', async() => {
    wrapper = mountDialog(true)
    await flushRequests()
    const vm = wrapper.vm as unknown as SameContentInspectionDialogVm
    mockGetSameContentInspection.mockClear()

    vm.handlePageChange(3)
    await flushRequests()

    expect(mockGetSameContentInspection).toHaveBeenCalledWith({
      mode: 'all',
      page: 3,
      pageSize: 10
    })

    vm.handleClose()
    expect(wrapper.emitted('update:visible')).toEqual([[false]])
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
