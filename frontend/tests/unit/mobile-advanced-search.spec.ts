/**
 * 移动端高级搜索构建器（方案三移动原生重构）：
 * - 已保存搜索胶囊：同源加载/过滤/排序（source=advanced，默认模板优先），
 *   点击应用并归一化历史模板（与桌面 applyTemplateGroups 同源）；
 * - 条件摘要卡：添加条件直接进入编辑弹层、确认回写、单条不可删除；
 * - 吸底执行：buildSearchParams 校验失败 warning 不发 search 事件；
 * - 保存为模板/保存更改/删除走同源 search-templates API（权限语义同桌面）。
 * ConditionEditSheet 以 shallowMount stub 替身（弹层契约独立 spec 覆盖）。
 */

import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'
import MobileAdvancedSearch from '@/views/mobile/components/MobileAdvancedSearch.vue'
import {
  createSearchTemplate,
  deleteSearchTemplate,
  getSearchTemplates,
  getDownloaderList,
  updateSearchTemplate
} from '@/api/torrents'
import { getAllCategories, getAllTags } from '@/api/tag-management'
import type { QueryTemplateConditions, SearchTemplate } from '@/api/torrents'
import type {
  AdvancedSearchConditionState,
  AdvancedSearchConditionValue,
  AdvancedSearchGroupState
} from '@/components/torrents/advancedSearchState'

jest.mock('@/store/modules/user', () => ({
  UserModule: { userId: 'user-1' }
}))

jest.mock('@/api/torrents', () => ({
  getSearchTemplates: jest.fn(),
  createSearchTemplate: jest.fn(),
  updateSearchTemplate: jest.fn(),
  deleteSearchTemplate: jest.fn(),
  getDownloaderList: jest.fn()
}))

jest.mock('@/api/tag-management', () => ({
  getAllCategories: jest.fn(),
  getAllTags: jest.fn()
}))

const localVue = createLocalVue()
localVue.directive('loading', {})

interface BuilderVm extends Vue {
  conditionGroups: AdvancedSearchGroupState[]
  advancedTemplates: SearchTemplate[]
  selectedTemplateId: string
  templatesLoading: boolean
  sheetVisible: boolean
  editingCondition: AdvancedSearchConditionState | null
  saveTemplateVisible: boolean
  manageVisible: boolean
  previewVisible: boolean
  templateForm: { name: string, description: string, isDefault: boolean }
  canManageSelected: boolean
  applySavedSearch(template: SearchTemplate): void
  applyTemplateGroups(groups: AdvancedSearchGroupState[]): void
  addCondition(group: AdvancedSearchGroupState): void
  removeCondition(group: AdvancedSearchGroupState, index: number): void
  handleGroupCommand(command: { action: string, index: number }): void
  handleBarCommand(command: string): void
  onSheetConfirm(draft: AdvancedSearchConditionState): void
  onSearch(): void
  resetConditions(): void
  saveSearchTemplate(): void
  confirmSaveTemplate(): void
  updateSelectedTemplate(): Promise<void>
  deleteSelectedTemplate(): Promise<void>
  getTemplateGroupsSnapshot(): AdvancedSearchGroupState[]
  previewSearchQuery(): void
  loadSavedSearches(): Promise<void>
}

const nameCondition = (field: string, operator: string, value: AdvancedSearchConditionValue): AdvancedSearchConditionState => ({
  id: `c-${field}-${operator}`,
  field,
  operator,
  value,
  mode: 'include'
})

const makeGroups = (conditions: AdvancedSearchConditionState[]): AdvancedSearchGroupState[] => [
  {
    id: 'g-1',
    name: '',
    logic: 'and',
    betweenGroupLogic: 'and',
    editing: false,
    conditions
  }
]

const makeConditions = (groups: AdvancedSearchGroupState[]): QueryTemplateConditions => ({
  source: 'advanced',
  version: 1,
  condition_groups: groups,
  sort_by: 'added_date',
  sort_order: 'desc'
})

const makeTemplate = (overrides: Partial<SearchTemplate>): SearchTemplate => ({
  id: 'tpl-1',
  user_id: 'user-1',
  name: '4K 做种监控',
  description: null,
  conditions: makeConditions(makeGroups([nameCondition('name', 'contains', '4K')])),
  is_default: false,
  is_public: false,
  usage_count: 3,
  created_time: '2026-08-01T00:00:00',
  updated_time: '2026-08-02T00:00:00',
  ...overrides
})

const message = {
  success: jest.fn(),
  warning: jest.fn(),
  error: jest.fn()
}

let confirmMock: jest.Mock

const mountBuilder = (): Wrapper<Vue> =>
  shallowMount(MobileAdvancedSearch, {
    localVue,
    mocks: {
      $message: message,
      $confirm: confirmMock
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let index = 0; index < 16; index += 1) {
    await Promise.resolve()
  }
  await new Promise(resolve => setTimeout(resolve, 0))
  await Vue.nextTick()
}

describe('views/mobile/components/MobileAdvancedSearch', () => {
  beforeEach(() => {
    message.success.mockReset()
    message.warning.mockReset()
    message.error.mockReset()
    confirmMock = jest.fn().mockResolvedValue(undefined)
    // 动态候选默认成功空列表（部分失败降级语义由桌面 spec 覆盖）
    jest.mocked(getAllCategories).mockResolvedValue({ code: '200', data: ['电影'] } as never)
    jest.mocked(getAllTags).mockResolvedValue({ code: '200', data: [] } as never)
    jest.mocked(getDownloaderList).mockResolvedValue({ code: '200', data: [] } as never)
    jest.mocked(getSearchTemplates).mockReset()
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('mounted：加载已保存搜索（过滤 simple、系统模板优先）并渲染胶囊', async() => {
    const advancedTemplate = makeTemplate({ id: 'tpl-adv', name: '4K 做种监控' })
    const simpleTemplate = makeTemplate({
      id: 'tpl-simple',
      name: '简单查询模板',
      conditions: { source: 'simple', version: 1, listQuery: {} }
    })
    const defaultTemplate = makeTemplate({ id: 'tpl-default', name: '系统默认', is_default: true })
    jest.mocked(getSearchTemplates).mockResolvedValue({
      code: '200',
      data: [advancedTemplate, simpleTemplate, defaultTemplate]
    } as never)

    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    expect(getSearchTemplates).toHaveBeenCalledWith({ is_public: true })
    expect(vm.advancedTemplates.map(t => t.id)).toEqual(['tpl-default', 'tpl-adv'])
    const chips = wrapper.findAll('.m-adv-chip')
    // ＋新建、两个模板、⚙管理
    expect(chips.length).toBe(4)
    expect(wrapper.text()).toContain('系统默认')
    expect(wrapper.text()).toContain('4K 做种监控')
    expect(wrapper.text()).not.toContain('简单查询模板')
  })

  it('点击胶囊应用模板：条件组归一化回填并记录选中', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.manageVisible = true
    vm.applySavedSearch(makeTemplate({}))
    await Vue.nextTick()

    expect(vm.selectedTemplateId).toBe('tpl-1')
    expect(vm.manageVisible).toBe(false)
    expect(vm.conditionGroups.length).toBe(1)
    expect(vm.conditionGroups[0].conditions[0].field).toBe('name')
    expect(vm.conditionGroups[0].conditions[0].operator).toBe('contains')
  })

  it('历史模板归一化：单值精确列 contains_any → in，value 串拆数组（与桌面同源）', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.applyTemplateGroups(
      makeGroups([nameCondition('category', 'contains_any', '电影, 音乐')]) as AdvancedSearchGroupState[]
    )
    const condition = vm.conditionGroups[0].conditions[0]
    expect(condition.operator).toBe('in')
    expect(condition.value).toEqual(['电影', '音乐'])
  })

  it('应用无有效条件的模板：warning 且不回填', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.applySavedSearch(makeTemplate({ conditions: { source: 'advanced', version: 1 } }))
    expect(message.warning).toHaveBeenCalledWith('该搜索配置没有有效的高级搜索条件')
    expect(vm.conditionGroups.length).toBe(1)
    expect(vm.conditionGroups[0].conditions[0].field).toBe('')
  })

  it('新建：清空选中并 emit reset（页面联动清结果）', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.selectedTemplateId = 'tpl-1'
    wrapper.findAll('.m-adv-chip').at(0).trigger('click')
    await Vue.nextTick()

    expect(vm.selectedTemplateId).toBe('')
    expect(wrapper.emitted('reset')).toBeTruthy()
  })

  it('添加条件：入列空条件并直接打开编辑弹层', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    const group = vm.conditionGroups[0]
    vm.addCondition(group)
    await Vue.nextTick()

    expect(group.conditions.length).toBe(2)
    expect(vm.sheetVisible).toBe(true)
    expect(vm.editingCondition).toBeTruthy()
    expect(vm.editingCondition?.field).toBe('')
  })

  it('弹层确认：草稿回写对应条件', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    const group = vm.conditionGroups[0]
    vm.addCondition(group)
    const draft: AdvancedSearchConditionState = {
      id: 'c-new',
      field: 'name',
      operator: 'contains',
      value: '4K',
      mode: 'include'
    }
    vm.onSheetConfirm(draft)
    await Vue.nextTick()

    expect(group.conditions[1]).toMatchObject({ field: 'name', operator: 'contains', value: '4K' })
    expect(vm.editingCondition).toBeNull()
    expect(vm.sheetVisible).toBe(false)
  })

  it('删除条件：组内唯一条件不可删，多条件可删', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    const group = vm.conditionGroups[0]
    vm.removeCondition(group, 0)
    expect(group.conditions.length).toBe(1)

    group.conditions.push(nameCondition('tags', 'contains_any', ['电影']))
    // 双条件时删除首条（空条件），留下 tags 条件
    vm.removeCondition(group, 0)
    expect(group.conditions.length).toBe(1)
    expect(group.conditions[0].field).toBe('tags')
  })

  it('组操作菜单：复制组/清空条件/删除组（单组不可删）', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    // 单组：删除被拒
    vm.handleGroupCommand({ action: 'delete', index: 0 })
    expect(vm.conditionGroups.length).toBe(1)

    // 复制组
    vm.conditionGroups[0].conditions[0] = nameCondition('name', 'contains', '4K')
    vm.handleGroupCommand({ action: 'duplicate', index: 0 })
    expect(vm.conditionGroups.length).toBe(2)
    expect(vm.conditionGroups[1].conditions[0].field).toBe('name')

    // 清空条件（回到一条空条件）
    vm.handleGroupCommand({ action: 'clear', index: 0 })
    expect(vm.conditionGroups[0].conditions.length).toBe(1)
    expect(vm.conditionGroups[0].conditions[0].field).toBe('')

    // 多组：可删
    vm.handleGroupCommand({ action: 'delete', index: 1 })
    expect(vm.conditionGroups.length).toBe(1)
  })

  it('吸底执行：有效条件 emit search（groups JSON 含构建载荷）', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.conditionGroups[0].conditions[0] = nameCondition('name', 'contains', '4K')
    vm.onSearch()

    const emitted = wrapper.emitted('search')
    expect(emitted).toBeTruthy()
    const params = emitted?.[0][0] as { complex_search: boolean, groups: string }
    expect(params.complex_search).toBe(true)
    expect(JSON.parse(params.groups)[0].conditions[0]).toMatchObject({
      field: 'name',
      operator: 'contains',
      value: '4K'
    })
  })

  it('吸底执行：未选字段校验失败 warning 且不发事件', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.onSearch()
    expect(message.warning).toHaveBeenCalled()
    expect(wrapper.emitted('search')).toBeFalsy()
  })

  it('⋯ 菜单重置：emit reset 并重建初始条件组', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.handleBarCommand('reset')
    expect(wrapper.emitted('reset')).toBeTruthy()
    expect(vm.conditionGroups.length).toBe(1)
    expect(vm.conditionGroups[0].conditions.length).toBe(1)
  })

  it('保存为模板：名称必填、成功后刷新列表并选中新建模板', async() => {
    jest.mocked(getSearchTemplates)
      .mockResolvedValueOnce({ code: '200', data: [] } as never)
      .mockResolvedValue({ code: '200', data: [makeTemplate({ id: 'tpl-new', name: '新建模板' })] } as never)
    jest.mocked(createSearchTemplate).mockResolvedValue({
      code: '200',
      data: makeTemplate({ id: 'tpl-new', name: '新建模板' })
    } as never)

    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.conditionGroups[0].conditions[0] = nameCondition('name', 'contains', '4K')

    vm.saveSearchTemplate()
    expect(vm.saveTemplateVisible).toBe(true)

    // 名称必填
    vm.confirmSaveTemplate()
    expect(message.warning).toHaveBeenCalledWith('请输入模板名称')
    expect(createSearchTemplate).not.toHaveBeenCalled()

    vm.templateForm.name = '移动新建'
    vm.confirmSaveTemplate()
    await flushLifecycle()

    expect(createSearchTemplate).toHaveBeenCalledTimes(1)
    const payload = jest.mocked(createSearchTemplate).mock.calls[0][0]
    expect(payload.name).toBe('移动新建')
    expect(payload.conditions.source).toBe('advanced')
    expect(payload.conditions.condition_groups?.[0].conditions[0].field).toBe('name')
    expect(vm.saveTemplateVisible).toBe(false)
    expect(vm.selectedTemplateId).toBe('tpl-new')
    expect(message.success).toHaveBeenCalledWith('模板保存成功')
  })

  it('管理抽屉保存更改：个人模板经快照校验后 PUT conditions', async() => {
    jest.mocked(getSearchTemplates)
      .mockResolvedValueOnce({
        code: '200',
        data: [makeTemplate({ id: 'tpl-mine', is_public: false })]
      } as never)
      .mockResolvedValue({ code: '200', data: [makeTemplate({ id: 'tpl-mine' })] } as never)
    jest.mocked(updateSearchTemplate).mockResolvedValue({
      code: '200',
      data: makeTemplate({})
    } as never)

    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.selectedTemplateId = 'tpl-mine'
    vm.conditionGroups[0].conditions[0] = nameCondition('name', 'contains', '4K')
    expect(vm.canManageSelected).toBe(true)

    await vm.updateSelectedTemplate()
    await flushLifecycle()

    expect(updateSearchTemplate).toHaveBeenCalledTimes(1)
    const payload = jest.mocked(updateSearchTemplate).mock.calls[0][1]
    expect(payload.conditions?.source).toBe('advanced')
    expect(message.success).toHaveBeenCalledWith('搜索配置已更新')
  })

  it('管理抽屉删除：确认后调用删除并清空选中', async() => {
    jest.mocked(getSearchTemplates)
      .mockResolvedValueOnce({
        code: '200',
        data: [makeTemplate({ id: 'tpl-mine', is_public: false })]
      } as never)
      .mockResolvedValue({ code: '200', data: [] } as never)
    jest.mocked(deleteSearchTemplate).mockResolvedValue({ code: '200', data: null } as never)

    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.selectedTemplateId = 'tpl-mine'
    await vm.deleteSelectedTemplate()
    await flushLifecycle()

    expect(confirmMock).toHaveBeenCalled()
    expect(deleteSearchTemplate).toHaveBeenCalledWith('tpl-mine')
    expect(vm.selectedTemplateId).toBe('')
    expect(message.success).toHaveBeenCalledWith('搜索配置已删除')
  })

  it('管理抽屉删除：取消确认则不调用删除', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({
      code: '200',
      data: [makeTemplate({ id: 'tpl-mine', is_public: false })]
    } as never)
    confirmMock = jest.fn().mockRejectedValue(new Error('cancel'))

    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.selectedTemplateId = 'tpl-mine'
    await vm.deleteSelectedTemplate()
    expect(deleteSearchTemplate).not.toHaveBeenCalled()
  })

  it('系统模板不可管理：canManageSelected 为 false', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({
      code: '200',
      data: [makeTemplate({ id: 'tpl-default', is_default: true })]
    } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.selectedTemplateId = 'tpl-default'
    expect(vm.canManageSelected).toBe(false)
  })

  it('摘要卡文案：已设条件显示 字段+操作符+值，空条件显示占位', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    expect(wrapper.text()).toContain('设置条件…')
    // Vue2 数组下标直赋无响应性，用 splice 替换触发重渲染
    vm.conditionGroups[0].conditions.splice(0, 1, nameCondition('name', 'contains', '4K'))
    await Vue.nextTick()
    expect(wrapper.text()).toContain('种子名称')
    expect(wrapper.text()).toContain('4K')
  })

  it('组间逻辑：双组时切换 OR 反映到构建载荷', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.handleGroupCommand({ action: 'duplicate', index: 0 })
    vm.conditionGroups[0].conditions[0] = nameCondition('name', 'contains', '4K')
    vm.conditionGroups[1].conditions[0] = nameCondition('tags', 'contains_any', ['电影'])
    vm.conditionGroups[0].betweenGroupLogic = 'or'
    vm.onSearch()

    const params = wrapper.emitted('search')?.[0][0] as { between_group_logics: string }
    expect(JSON.parse(params.between_group_logics)).toEqual(['or'])
  })

  // ============ 回归加固（2026-09-06 续五）：降级/竞态/校验路径与源码契约 ============

  it('加固：动态候选部分失败（1/3）静默降级——无告警且成功项保留', async() => {
    jest.mocked(getAllCategories).mockRejectedValue(new Error('分类接口炸了') as never)
    jest.mocked(getAllTags).mockResolvedValue({ code: '200', data: ['tv'] } as never)
    jest.mocked(getDownloaderList).mockResolvedValue({ code: '200', data: [] } as never)
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)

    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm & { dynamicOptions: { tagOptions: unknown[] } }

    expect(message.error).not.toHaveBeenCalled()
    expect(vm.dynamicOptions.tagOptions).toEqual([{ label: 'tv', value: 'tv' }])
  })

  it('加固：动态候选全部失败（3/3）才告警——透传首个异常文本', async() => {
    jest.mocked(getAllCategories).mockRejectedValue(new Error('后端不可用') as never)
    jest.mocked(getAllTags).mockRejectedValue(new Error('tags down') as never)
    jest.mocked(getDownloaderList).mockRejectedValue(new Error('dl down') as never)
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)

    mountBuilder()
    await flushLifecycle()

    expect(message.error).toHaveBeenCalledTimes(1)
    expect(message.error).toHaveBeenCalledWith('后端不可用')
  })

  it('加固：getSearchTemplates 信封非 200——error 提示且列表不落地', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '500', msg: '模板服务不可用' } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    expect(message.error).toHaveBeenCalledWith('模板服务不可用')
    expect(vm.advancedTemplates).toEqual([])
    expect(vm.templatesLoading).toBe(false)
  })

  it('加固：loadSavedSearches 竞态守卫——迟到的旧响应不覆盖新列表、不误动 loading', async() => {
    let resolveStale: (value: unknown) => void = () => undefined
    const stalePromise = new Promise(resolve => { resolveStale = resolve })
    jest.mocked(getSearchTemplates)
      .mockImplementationOnce(() => stalePromise as never)
      .mockResolvedValue({ code: '200', data: [makeTemplate({ id: 'tpl-fresh' })] } as never)

    const wrapper = mountBuilder()
    await Vue.nextTick()
    const vm = wrapper.vm as BuilderVm
    // 挂起的首轮（stale）之后手动触发第二轮（如管理抽屉刷新）
    const second = vm.loadSavedSearches()
    await flushLifecycle()
    expect(vm.advancedTemplates.map(t => t.id)).toEqual(['tpl-fresh'])
    expect(vm.templatesLoading).toBe(false)

    // 旧响应此刻迟到 resolve：序列号守卫应拒绝其落地
    resolveStale({ code: '200', data: [makeTemplate({ id: 'tpl-stale' })] } as never)
    await flushLifecycle()
    expect(vm.advancedTemplates.map(t => t.id)).toEqual(['tpl-fresh'])
    expect(vm.templatesLoading).toBe(false)
    await second
  })

  it('加固：列表重载后 selectedTemplateId 指向已消失模板——自动清空', async() => {
    jest.mocked(getSearchTemplates)
      .mockResolvedValueOnce({ code: '200', data: [makeTemplate({ id: 'tpl-mine' })] } as never)
      .mockResolvedValue({ code: '200', data: [makeTemplate({ id: 'tpl-other' })] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.selectedTemplateId = 'tpl-mine'
    await vm.loadSavedSearches()
    await flushLifecycle()

    expect(vm.selectedTemplateId).toBe('')
  })

  it('加固：应用含未知字段的模板——error 提示且后续搜索被校验拦截', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    const badTemplate = makeTemplate({
      conditions: makeConditions([
        {
          id: 'g-bad',
          name: '',
          logic: 'and',
          betweenGroupLogic: 'and',
          editing: false,
          conditions: [nameCondition('no_such_field' as string, 'contains', 'x')]
        }
      ])
    })
    vm.applySavedSearch(badTemplate)
    await Vue.nextTick()

    expect(message.error).toHaveBeenCalled()
    // 坏模板落地后吸底执行必须被校验拦下（不可静默发起搜索）
    vm.onSearch()
    expect(message.warning).toHaveBeenCalled()
    expect(wrapper.emitted('search')).toBeFalsy()
  })

  it('加固：confirmSaveTemplate 条件无效——warning 且不调 createSearchTemplate、对话框保持打开', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.saveTemplateVisible = true
    vm.templateForm.name = '名字有效但条件空'
    vm.confirmSaveTemplate()
    await flushLifecycle()

    expect(message.warning).toHaveBeenCalled()
    expect(createSearchTemplate).not.toHaveBeenCalled()
    expect(vm.saveTemplateVisible).toBe(true)
  })

  it('加固：预览查询——条件无效 warning 不开对话框，条件有效打开', async() => {
    jest.mocked(getSearchTemplates).mockResolvedValue({ code: '200', data: [] } as never)
    const wrapper = mountBuilder()
    await flushLifecycle()
    const vm = wrapper.vm as BuilderVm

    vm.previewSearchQuery()
    expect(message.warning).toHaveBeenCalled()
    expect(vm.previewVisible).toBe(false)

    vm.conditionGroups[0].conditions.splice(0, 1, nameCondition('name', 'contains', '4K'))
    vm.previewSearchQuery()
    expect(vm.previewVisible).toBe(true)
  })

  it('加固·源码契约：禁回流桌面工作区、消费共享层、吸底浮条避让 Tab 栏', () => {
    const fs = require('fs') as typeof import('fs')
    const source = fs.readFileSync('src/views/mobile/components/MobileAdvancedSearch.vue', 'utf-8')
    // 移动构建器不得再挂桌面工作区（方案三的核心边界）
    expect(source).not.toContain('AdvancedSearchWorkspace')
    expect(source).not.toContain('advanced-search-workspace')
    // 字段/操作符/归一化必须走共享层（防本地副本回流）
    expect(source).toContain("from '@/components/torrents/advancedSearchFields'")
    // 吸底浮条定位锚：避开悬浮 Tab 栏（同 .m-backtop 的避让几何）
    expect(source).toContain('calc(80px + env(safe-area-inset-bottom))')
  })
})
