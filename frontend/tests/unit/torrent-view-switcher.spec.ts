import Vue from 'vue'
import { createLocalVue, mount, Wrapper } from '@vue/test-utils'

import TorrentViewSwitcher from '@/views/torrents/TorrentViewSwitcher.vue'
import { ViewModeModule } from '@/store/modules/viewMode'

jest.mock('@/store/modules/viewMode', () => ({
  ViewModeModule: {
    currentMode: 'list'
  }
}))

jest.mock('@/views/torrents/index.vue', () => ({
  name: 'ListView',
  data() {
    return {
      listQuery: { name_like: 'list-search', sort_by: 'added_date', sort_order: 'desc' },
      currentPage: 3,
      pageSize: 50,
      multipleSelection: [{ hash: 'list-selected' }],
      list: [{ hash: 'list-item' }],
      total: 12,
      downloaderList: [{ id: 'list-downloader' }],
      showingDuplicates: false,
      showingSameContent: true,
      showingSingleErrors: true
    }
  },
  render(h: typeof Vue.prototype.$createElement) {
    return h('div', { class: 'list-view-stub' })
  }
}))

jest.mock('@/views/torrents/TraditionalView.vue', () => ({
  name: 'TraditionalView',
  data() {
    return {
      listQuery: { name_like: '', sort_by: 'name', sort_order: 'asc' },
      currentPage: 1,
      pageSize: 20,
      multipleSelection: [],
      list: [],
      total: 0,
      downloaderList: [],
      showingDuplicates: false,
      showingSameContent: false,
      showingSingleErrors: false
    }
  },
  render(h: typeof Vue.prototype.$createElement) {
    return h('div', { class: 'traditional-view-stub' })
  }
}))

const localVue = createLocalVue()

interface SharedViewState extends Vue {
  listQuery: Record<string, unknown>
  currentPage: number
  pageSize: number
  multipleSelection: Array<Record<string, unknown>>
  list: Array<Record<string, unknown>>
  total: number
  downloaderList: Array<Record<string, unknown>>
  showingDuplicates: boolean
  showingSameContent: boolean
  showingSingleErrors: boolean
}

function currentView(wrapper: Wrapper<Vue>): SharedViewState {
  return wrapper.vm.$refs.currentViewRef as SharedViewState
}

async function flushViewSwitch(): Promise<void> {
  await localVue.nextTick()
  await localVue.nextTick()
}

describe('TorrentViewSwitcher 跨视图状态', () => {
  let wrapper: Wrapper<Vue>
  let consoleLogSpy: jest.SpyInstance

  beforeEach(() => {
    ViewModeModule.currentMode = 'list'
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation()
  })

  afterEach(() => {
    wrapper?.destroy()
    consoleLogSpy.mockRestore()
  })

  it('在列表与传统模式之间完整保留同内容排查、查询和分页状态', async() => {
    wrapper = mount(TorrentViewSwitcher, { localVue })
    await flushViewSwitch()

    const listView = currentView(wrapper)
    expect(listView.showingDuplicates).toBe(false)
    expect(listView.showingSameContent).toBe(true)
    expect(listView.showingSingleErrors).toBe(true)
    expect(listView.listQuery.name_like).toBe('list-search')
    expect(listView.currentPage).toBe(3)

    ViewModeModule.currentMode = 'traditional'
    await flushViewSwitch()

    const traditionalView = currentView(wrapper)
    expect(wrapper.find('.traditional-view-stub').exists()).toBe(true)
    expect(traditionalView.showingDuplicates).toBe(false)
    expect(traditionalView.showingSameContent).toBe(true)
    expect(traditionalView.showingSingleErrors).toBe(true)
    expect(traditionalView.listQuery).toEqual(expect.objectContaining({
      name_like: 'list-search',
      sort_by: 'added_date',
      sort_order: 'desc'
    }))
    expect(traditionalView.currentPage).toBe(3)
    expect(traditionalView.pageSize).toBe(50)
    expect(traditionalView.total).toBe(12)
    expect(traditionalView.multipleSelection).toEqual([{ hash: 'list-selected' }])

    traditionalView.listQuery.name_like = 'traditional-search'
    traditionalView.currentPage = 5
    traditionalView.pageSize = 100
    traditionalView.total = 23
    traditionalView.showingDuplicates = false
    traditionalView.showingSameContent = false
    traditionalView.showingSingleErrors = true
    traditionalView.multipleSelection = [{ hash: 'traditional-selected' }]

    ViewModeModule.currentMode = 'list'
    await flushViewSwitch()

    const restoredListView = currentView(wrapper)
    expect(wrapper.find('.list-view-stub').exists()).toBe(true)
    expect(restoredListView.showingDuplicates).toBe(false)
    expect(restoredListView.showingSameContent).toBe(false)
    expect(restoredListView.showingSingleErrors).toBe(true)
    expect(restoredListView.listQuery.name_like).toBe('traditional-search')
    expect(restoredListView.currentPage).toBe(5)
    expect(restoredListView.pageSize).toBe(100)
    expect(restoredListView.total).toBe(23)
    expect(restoredListView.multipleSelection).toEqual([{ hash: 'traditional-selected' }])
  })
})
