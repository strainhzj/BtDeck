/**
 * 移动查询模板契约（Phase 4 M2）：客户端名称/类型过滤；「应用」经 m2 缓存
 * 跳 /m/search 执行；系统模板（is_default）只可应用不可删除（与桌面判定一致）。
 */

import { shallowMount, Wrapper } from '@vue/test-utils'
import MobileQueryTemplates from '@/views/mobile/query-templates.vue'
import { getSearchTemplates, deleteSearchTemplate, SearchTemplate } from '@/api/torrents'
import { setAppliedTemplateConditions } from '@/views/mobile/m2-template-cache'

jest.mock('@/api/torrents', () => ({
  getSearchTemplates: jest.fn(),
  deleteSearchTemplate: jest.fn(),
  createSearchTemplate: jest.fn(),
  getTrackerDomains: jest.fn(),
  getTorrentList: jest.fn(),
  advancedSearch: jest.fn()
}))

jest.mock('@/views/mobile/m2-template-cache', () => ({
  setAppliedTemplateConditions: jest.fn(),
  takeAppliedTemplateConditions: jest.fn().mockReturnValue(null)
}))

const baseTemplate = {
  id: 'tpl-1',
  user_id: 'u1',
  name: '常用查询',
  description: '描述',
  is_default: false,
  is_public: false,
  usage_count: 3,
  created_time: '2026-08-01T10:00:00',
  updated_time: null,
  conditions: {
    source: 'simple',
    version: 1,
    listQuery: { name_like: '关键词', status: ['seeding'] }
  }
} as unknown as SearchTemplate

const systemTemplate = {
  ...baseTemplate,
  id: 'tpl-sys',
  name: '系统模板',
  is_default: true,
  conditions: {
    source: 'advanced',
    version: 1,
    condition_groups: [{ conditions: [{ field: 'name', operator: 'contains', value: 'x' }] }]
  }
} as unknown as SearchTemplate

const mountPage = (): Wrapper<Vue> =>
  shallowMount(MobileQueryTemplates, {
    mocks: {
      $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn() },
      $confirm: jest.fn().mockResolvedValue('confirm'),
      $router: { push: jest.fn().mockResolvedValue(undefined), replace: jest.fn().mockResolvedValue(undefined) }
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await Promise.resolve()
  }
  await Promise.resolve()
}

describe('views/mobile/MobileQueryTemplates', () => {
  beforeEach(() => {
    jest.mocked(getSearchTemplates).mockReset()
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [baseTemplate, systemTemplate] } as never)
    jest.mocked(deleteSearchTemplate).mockReset()
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('列表渲染：名称/类型标签/使用次数；系统模板带「系统」标记', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('常用查询')
    expect(wrapper.text()).toContain('简单查询')
    expect(wrapper.text()).toContain('高级搜索')
    expect(wrapper.text()).toContain('系统')
    expect(wrapper.text()).toContain('使用 3 次')
  })

  it('名称与类型为客户端过滤（与桌面一致）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    expect(vm.filteredList.length).toBe(2)
    vm.nameFilter = '常用'
    expect(vm.filteredList.length).toBe(1)
    vm.nameFilter = ''
    vm.sourceFilter = 'advanced'
    expect(vm.filteredList.length).toBe(1)
    expect(vm.filteredList[0].id).toBe('tpl-sys')
  })

  it('应用：写入 m2 缓存并跳 /m/search', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    vm.apply(vm.list[0])
    expect(setAppliedTemplateConditions).toHaveBeenCalledWith(baseTemplate.conditions, '常用查询')
    expect(vm.$router.push).toHaveBeenCalledWith('/m/search')
  })

  it('个人模板：确认后删除并刷新；系统模板不提供删除（判定 is_default）', async() => {
    const wrapper = mountPage()
    await flushLifecycle()
    const vm = wrapper.vm as any
    jest.mocked(deleteSearchTemplate).mockResolvedValue({ code: '200' } as never)
    await vm.remove(vm.list[0])
    await flushLifecycle()
    expect(deleteSearchTemplate).toHaveBeenCalledWith('tpl-1')
    // 系统模板删除按钮不渲染（v-if="!tpl.is_default"）；Jest 无全局 element-ui，
    // el-button 为 unknown 元素不产生 stub，故按卡片文本断言删除入口
    const cards = wrapper.findAll('.m-tpl-card')
    expect(cards.length).toBe(2)
    expect(cards.at(0).text()).toContain('删除')
    expect(cards.at(1).text()).not.toContain('删除')
  })

  it('空列表显示空态', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountPage()
    await flushLifecycle()
    expect(wrapper.text()).toContain('暂无查询模板')
  })
})
