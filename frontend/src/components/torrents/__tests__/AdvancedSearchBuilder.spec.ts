import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'
import AdvancedSearchBuilder from '../AdvancedSearchBuilder.vue'
import { getAllCategories, getAllTags } from '@/api/tag-management'
import { getDownloaderList } from '@/api/torrents'

// 显式 mock 三个 api 模块（项目范式：仿 traditional-view-component.spec.ts，不用 requireActual）
jest.mock('@/api/tag-management', () => ({
  getAllCategories: jest.fn(),
  getAllTags: jest.fn()
}))
jest.mock('@/api/torrents', () => ({
  getDownloaderList: jest.fn()
}))

interface SearchParams {
  complex_search: boolean
  groups_count: number
  groups: string
  between_group_logics: string
  [key: string]: unknown
}

interface GroupPayload {
  name: string
  logic: string
  conditions_count: number
  conditions: Array<{
    field: string
    operator: string
    value: unknown
    mode: string
  }>
}

interface SearchConditionVm {
  id: string
  field: string
  operator: string
  value: unknown
  mode: 'include' | 'exclude'
}

interface ConditionGroupVm {
  id: string
  name?: string
  logic: 'and' | 'or'
  betweenGroupLogic?: 'and' | 'or'
  editing?: boolean
  conditions: SearchConditionVm[]
}

interface AdvancedSearchBuilderVm extends Vue {
  conditionGroups: ConditionGroupVm[]
  formattedQuery: string
  saveTemplateVisible: boolean
  templateForm: {
    name: string
    description: string
    isDefault: boolean
  }
  categoryOptions: Array<{ label: string, value: string }>
  tagOptions: Array<{ label: string, value: string }>
  downloaderOptions: Array<{ label: string, value: string }>
  fieldOptionsLoading: boolean
  duplicateConditionGroup(group: ConditionGroupVm): void
  clearGroupConditions(group: ConditionGroupVm): void
  removeConditionGroup(index: number): void
  startEditingGroup(group: ConditionGroupVm): void
  finishEditingGroup(group: ConditionGroupVm): void
  onFieldChange(condition: SearchConditionVm): void
  onOperatorChange(condition: SearchConditionVm): void
  getFieldOptions(fieldKey: string): Array<{ label: string, value: string }>
  getOperatorGroups(fieldKey: string): Array<{ type: string, label: string, operators?: Array<{ value: string, label: string }> }>
  fieldSupportsExclude(fieldKey: string): boolean
  addConditionGroup(): void
  buildSearchParams(): SearchParams
  onSearch(): void
  onGroupLogicChange(group: ConditionGroupVm): void
  onBetweenGroupLogicChange(group: ConditionGroupVm): void
  applyTemplateGroups(groups: ConditionGroupVm[]): void
  resetConditions(): void
  saveSearchTemplate(): void
  confirmSaveTemplate(): void
  refreshFieldOptions(): void
  loadFieldOptions(): Promise<void>
}

// 项目无 flushPromises 工具；复用 traditional-view-component.spec.ts 的 flushLifecycle 三段式
// Vue 2 的 nextTick 是全局静态方法，与 localVue.nextTick 等价。
async function flushLifecycle(): Promise<void> {
  for (let index = 0; index < 16; index += 1) {
    await Promise.resolve()
  }
  await new Promise(resolve => setTimeout(resolve, 0))
  await Vue.nextTick()
}

describe('AdvancedSearchBuilder 关键查询链路', () => {
  const localVue = createLocalVue()
  const message = {
    success: jest.fn(),
    warning: jest.fn(),
    error: jest.fn()
  }
  let wrapper: Wrapper<Vue>
  let vm: AdvancedSearchBuilderVm
  let logSpy: jest.SpyInstance
  let warnSpy: jest.SpyInstance
  let errorSpy: jest.SpyInstance

  beforeEach(() => {
    logSpy = jest.spyOn(console, 'log').mockImplementation(() => undefined)
    warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined)
    message.success.mockReset()
    message.warning.mockReset()
    message.error.mockReset()

    // 动态字段选项 API 的默认 mock 值（成功返回 envelope）
    const mockGetAllCategories = getAllCategories as jest.MockedFunction<typeof getAllCategories>
    const mockGetAllTags = getAllTags as jest.MockedFunction<typeof getAllTags>
    const mockGetDownloaderList = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
    mockGetAllCategories.mockReset()
    mockGetAllTags.mockReset()
    mockGetDownloaderList.mockReset()
    mockGetAllCategories.mockResolvedValue({ code: '200', data: ['电影', '音乐'], msg: 'ok', status: 'success' } as any)
    mockGetAllTags.mockResolvedValue({ code: '200', data: ['tag1', 'tag2'], msg: 'ok', status: 'success' } as any)
    mockGetDownloaderList.mockResolvedValue({
      code: '200',
      data: [
        { downloader_id: 'd1', nickname: 'qbit-主' },
        { downloader_id: 'd2', nickname: 'tr-辅' }
      ],
      msg: 'ok',
      status: 'success'
    } as any)

    wrapper = shallowMount(AdvancedSearchBuilder, {
      localVue,
      mocks: { $message: message },
      stubs: {
        'condition-value-input': true,
        'el-input': true,
        'el-tag': true,
        'el-button': true,
        'el-dropdown': true,
        'el-dropdown-menu': true,
        'el-dropdown-item': true,
        'el-select': true,
        'el-option': true,
        'el-option-group': true,
        'el-switch': true,
        'el-dialog': true,
        'el-form': true,
        'el-form-item': true
      }
    })
    vm = wrapper.vm as unknown as AdvancedSearchBuilderVm
  })

  afterEach(() => {
    wrapper.destroy()
    logSpy.mockRestore()
    warnSpy.mockRestore()
    errorSpy.mockRestore()
  })

  it('初始化一个 AND 条件组和空条件', () => {
    expect(vm.conditionGroups).toHaveLength(1)
    expect(vm.conditionGroups[0]).toMatchObject({
      logic: 'and',
      betweenGroupLogic: 'and',
      editing: false
    })
    expect(vm.conditionGroups[0].conditions).toHaveLength(1)
    expect(vm.formattedQuery).toBe('暂无有效搜索条件')
  })

  it('添加、复制、清空和删除条件组时保持独立数据', () => {
    const source = vm.conditionGroups[0]
    source.name = '下载条件'
    source.conditions[0].field = 'name'
    source.conditions[0].operator = 'contains'
    source.conditions[0].value = 'Ubuntu'

    vm.duplicateConditionGroup(source)
    expect(vm.conditionGroups).toHaveLength(2)
    expect(vm.conditionGroups[1].name).toBe('下载条件 (副本)')
    expect(vm.conditionGroups[1].conditions[0].id).not.toBe(source.conditions[0].id)

    vm.clearGroupConditions(vm.conditionGroups[1])
    expect(vm.conditionGroups[1].conditions[0]).toMatchObject({ field: '', operator: '', value: null })
    expect(source.conditions[0].field).toBe('name')

    vm.removeConditionGroup(1)
    vm.removeConditionGroup(0)
    expect(vm.conditionGroups).toHaveLength(1)
  })

  it('重命名条件组时补默认名称并清理空白', () => {
    const group = vm.conditionGroups[0]
    vm.startEditingGroup(group)
    expect(group.name).toBe('条件组 1')
    expect(group.editing).toBe(true)

    group.name = '  核心条件  '
    vm.finishEditingGroup(group)
    expect(group.name).toBe('核心条件')
    expect(group.editing).toBe(false)

    group.name = '   '
    vm.finishEditingGroup(group)
    expect(group.name).toBe('')
  })

  it('字段和操作符变化只重置应重置的值', () => {
    const condition = vm.conditionGroups[0].conditions[0]
    condition.field = 'name'
    condition.operator = 'equals'
    condition.value = 'old'

    vm.onFieldChange(condition)
    expect(condition).toMatchObject({ operator: '', value: null })

    condition.field = 'name'
    condition.operator = 'not_equals'
    condition.value = 'old'
    vm.onOperatorChange(condition)
    expect(condition.value).toBeNull()

    condition.field = 'size'
    condition.operator = 'between'
    condition.value = { min: 1, max: 2, minUnit: 'GB', maxUnit: 'GB' }
    vm.onOperatorChange(condition)
    expect(condition.value).toEqual({ min: 1, max: 2, minUnit: 'GB', maxUnit: 'GB' })
  })

  it('根据字段返回操作符、选项和排除能力', () => {
    expect(vm.getFieldOptions('status').length).toBeGreaterThan(0)
    expect(vm.getFieldOptions('super_seeding')).toEqual([
      { label: '是', value: 'true' },
      { label: '否', value: 'false' }
    ])
    expect(vm.getOperatorGroups('name')[0]).toMatchObject({ type: 'basic', label: '基本操作' })
    expect(vm.fieldSupportsExclude('name')).toBe(true)
    expect(vm.fieldSupportsExclude('missing')).toBe(false)
  })

  it('构建分组与兼容扁平参数并转换后端操作符和值', () => {
    const firstGroup = vm.conditionGroups[0]
    firstGroup.name = '大小条件'
    firstGroup.conditions[0].field = 'size'
    firstGroup.conditions[0].operator = 'between'
    firstGroup.conditions[0].value = { min: 1, max: 2, minUnit: 'GB', maxUnit: 'TB' }

    vm.addConditionGroup()
    const secondGroup = vm.conditionGroups[1]
    secondGroup.logic = 'or'
    firstGroup.betweenGroupLogic = 'or'
    secondGroup.conditions[0].field = 'status'
    secondGroup.conditions[0].operator = 'not_equals'
    secondGroup.conditions[0].value = 'paused'
    secondGroup.conditions[0].mode = 'exclude'

    const params = vm.buildSearchParams()
    const groups = JSON.parse(params.groups) as GroupPayload[]

    expect(params).toMatchObject({
      complex_search: true,
      groups_count: 2,
      size_op: 'between',
      group_1_status_exclude: 'paused',
      group_1_status_op: 'ne',
      group_1_logic: 'or'
    })
    expect(JSON.parse(params.between_group_logics)).toEqual(['or'])
    expect(groups).toHaveLength(2)
    expect(groups[0].conditions[0]).toMatchObject({
      field: 'size',
      operator: 'between',
      value: { min: '1 GB', max: '2 TB' }
    })
    expect(groups[1]).toMatchObject({ logic: 'or', conditions_count: 1 })
  })

  it('搜索事件携带当前构建参数', () => {
    const condition = vm.conditionGroups[0].conditions[0]
    condition.field = 'name'
    condition.operator = 'contains'
    condition.value = 'linux'

    vm.onSearch()

    const emitted = wrapper.emitted('search')
    expect(emitted).toHaveLength(1)
    expect(emitted?.[0][0]).toMatchObject({ name: 'linux', name_op: 'contains' })
  })

  it('组内和组间逻辑变化发出可追踪事件', () => {
    const group = vm.conditionGroups[0]
    group.logic = 'or'
    group.betweenGroupLogic = 'or'

    vm.onGroupLogicChange(group)
    vm.onBetweenGroupLogicChange(group)

    expect(wrapper.emitted('group-logic-change')?.[0][0]).toEqual({
      groupId: group.id,
      logic: 'or'
    })
    expect(wrapper.emitted('between-group-logic-change')?.[0][0]).toEqual({
      groupId: group.id,
      betweenGroupLogic: 'or'
    })
  })

  it('应用模板时深拷贝，空模板恢复默认组', () => {
    const source = [{
      id: 'template-group',
      name: '模板组',
      logic: 'and' as const,
      conditions: [{ id: 'c1', field: 'name', operator: 'contains', value: 'linux', mode: 'include' as const }]
    }]

    vm.applyTemplateGroups(source)
    source[0].conditions[0].value = 'changed'
    expect(vm.conditionGroups[0].conditions[0].value).toBe('linux')

    vm.applyTemplateGroups([])
    expect(vm.conditionGroups).toHaveLength(1)
    expect(vm.conditionGroups[0].conditions[0].field).toBe('')
  })

  it('重置条件和保存模板均发出稳定事件', () => {
    vm.resetConditions()
    expect(wrapper.emitted('reset')).toHaveLength(1)

    vm.saveSearchTemplate()
    expect(vm.saveTemplateVisible).toBe(true)
    vm.confirmSaveTemplate()
    expect(message.warning).toHaveBeenCalledWith('请输入模板名称')

    vm.templateForm.name = '常用查询'
    vm.templateForm.description = '回归测试模板'
    vm.confirmSaveTemplate()
    expect(wrapper.emitted('save-template')).toHaveLength(1)
    expect(wrapper.emitted('save-template')?.[0][0]).toMatchObject({
      name: '常用查询',
      description: '回归测试模板'
    })
    expect(vm.saveTemplateVisible).toBe(false)
    expect(message.success).toHaveBeenCalledWith('模板保存成功')
  })

  // ===== 动态字段选项注入（分类/标签/下载器）回归保护 =====

  it('created 触发首次加载并填充分类/标签/下载器选项，下载器 value 为 nickname', async() => {
    await flushLifecycle()

    // 分类
    const categoryOptions = vm.getFieldOptions('category')
    expect(categoryOptions).toHaveLength(2)
    expect(categoryOptions).toEqual([
      { label: '电影', value: '电影' },
      { label: '音乐', value: '音乐' }
    ])

    // 标签
    expect(vm.getFieldOptions('tags')).toEqual([
      { label: 'tag1', value: 'tag1' },
      { label: 'tag2', value: 'tag2' }
    ])

    // 下载器：value 必须是 nickname，不能是 downloader_id
    // （TorrentInfo.downloader_name 列存的就是 downloader.nickname）
    const downloaderOptions = vm.getFieldOptions('downloader_name')
    expect(downloaderOptions).toHaveLength(2)
    expect(downloaderOptions.every(o => o.value === o.label)).toBe(true)
    expect(downloaderOptions.map(o => o.value)).toEqual(['qbit-主', 'tr-辅'])

    // 既有字段不受污染：status 仍返回 STATUS_OPTIONS，super_seeding 仍是是/否
    expect(vm.getFieldOptions('status').length).toBeGreaterThan(0)
    expect(vm.getFieldOptions('super_seeding')).toEqual([
      { label: '是', value: 'true' },
      { label: '否', value: 'false' }
    ])

    // 三个 API 各被 created 调用一次
    expect(getAllCategories).toHaveBeenCalledTimes(1)
    expect(getAllTags).toHaveBeenCalledTimes(1)
    expect(getDownloaderList).toHaveBeenCalledTimes(1)
  })

  it('部分失败降级：单个 API 失败不影响其它两个填充，且不弹错误提示', async() => {
    await flushLifecycle() // 先消耗 created 的首次调用

    // 标签失败、另两个成功
    const mockGetAllTags = getAllTags as jest.MockedFunction<typeof getAllTags>
    mockGetAllTags.mockReset()
    mockGetAllTags.mockRejectedValue(new Error('network'))

    message.error.mockClear()
    ;(getAllCategories as jest.MockedFunction<typeof getAllCategories>).mockClear()
    ;(getDownloaderList as jest.MockedFunction<typeof getDownloaderList>).mockClear()

    await vm.refreshFieldOptions()
    await flushLifecycle()

    // 成功项已填充
    expect(vm.getFieldOptions('category').length).toBe(2)
    expect(vm.getFieldOptions('downloader_name').length).toBe(2)
    // 失败项保持空
    expect(vm.getFieldOptions('tags')).toEqual([])
    // 部分失败静默，不弹 toast
    expect(message.error).not.toHaveBeenCalled()
    expect(vm.fieldOptionsLoading).toBe(false)
  })

  it('全部失败才弹出一次错误提示，三字段保持空', async() => {
    await flushLifecycle()

    const mockCats = getAllCategories as jest.MockedFunction<typeof getAllCategories>
    const mockTags = getAllTags as jest.MockedFunction<typeof getAllTags>
    const mockDls = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
    mockCats.mockReset()
    mockTags.mockReset()
    mockDls.mockReset()
    mockCats.mockRejectedValue(new Error('e1'))
    mockTags.mockRejectedValue(new Error('e2'))
    mockDls.mockRejectedValue(new Error('e3'))

    message.error.mockClear()
    await vm.refreshFieldOptions()
    await flushLifecycle()

    expect(vm.getFieldOptions('category')).toEqual([])
    expect(vm.getFieldOptions('tags')).toEqual([])
    expect(vm.getFieldOptions('downloader_name')).toEqual([])
    expect(message.error).toHaveBeenCalledTimes(1)
    expect(vm.fieldOptionsLoading).toBe(false)
  })

  it('refreshFieldOptions 重新拉取：每次调用都重新请求三个接口并填充', async() => {
    await flushLifecycle()
    expect(getAllCategories).toHaveBeenCalledTimes(1)

    const mockCats = getAllCategories as jest.MockedFunction<typeof getAllCategories>
    const mockTags = getAllTags as jest.MockedFunction<typeof getAllTags>
    const mockDls = getDownloaderList as jest.MockedFunction<typeof getDownloaderList>
    mockCats.mockClear()
    mockTags.mockClear()
    mockDls.mockClear()
    mockCats.mockResolvedValue({ code: '200', data: ['新分类'], msg: 'ok', status: 'success' } as any)
    mockTags.mockResolvedValue({ code: '200', data: ['新标签'], msg: 'ok', status: 'success' } as any)
    mockDls.mockResolvedValue({
      code: '200',
      data: [{ downloader_id: 'x', nickname: '新下载器' }],
      msg: 'ok',
      status: 'success'
    } as any)

    await vm.refreshFieldOptions()
    await flushLifecycle()

    // 三个接口各被再调用一次
    expect(mockCats).toHaveBeenCalledTimes(1)
    expect(mockTags).toHaveBeenCalledTimes(1)
    expect(mockDls).toHaveBeenCalledTimes(1)
    // 选项已更新为最新数据
    expect(vm.getFieldOptions('category')).toEqual([{ label: '新分类', value: '新分类' }])
    expect(vm.getFieldOptions('tags')).toEqual([{ label: '新标签', value: '新标签' }])
    expect(vm.getFieldOptions('downloader_name')).toEqual([{ label: '新下载器', value: '新下载器' }])
  })

  it('multiSelect 字段：value 以数组形态进 condition_groups，且不生成扁平参数', async() => {
    await flushLifecycle()

    // category 现在是 multiSelect（matchMode=exact），用 in 操作符 + 数组 value
    const categoryValues = vm.getFieldOptions('category').map(o => o.value) // ['电影','音乐']
    const condition = vm.conditionGroups[0].conditions[0]
    condition.field = 'category'
    condition.operator = 'in'
    condition.value = categoryValues

    const params = vm.buildSearchParams()
    // 1) groups JSON 侧：value 是数组（不再 join 逗号串），operator 转 'in'
    const groups = JSON.parse(params.groups) as Array<{ conditions: Array<{ field: string, operator: string, value: unknown }> }>
    const catCond = groups[0].conditions.find(c => c.field === 'category')
    expect(catCond).toBeDefined()
    expect(catCond?.operator).toBe('in')
    expect(catCond?.value).toEqual(categoryValues) // 数组原样
    expect(Array.isArray(catCond?.value)).toBe(true)

    // 2) 扁平参数侧：multiSelect 字段不生成扁平参数（避免 apply_basic_filters 的 == 误用数组）
    expect(params.category).toBeUndefined()
    expect(params.category_op).toBeUndefined()
  })

  it('multiSelect 字段单值 value 被包装成数组（formatParamValue 兜底分支）', async() => {
    await flushLifecycle()
    const condition = vm.conditionGroups[0].conditions[0]
    condition.field = 'category'
    condition.operator = 'in'
    condition.value = '电影' // 单值字符串（旧模板可能存过）

    const params = vm.buildSearchParams()
    const groups = JSON.parse(params.groups) as Array<{ conditions: Array<{ field: string, value: unknown }> }>
    const catCond = groups[0].conditions.find(c => c.field === 'category')
    expect(catCond).toBeDefined()
    // Array.isArray=false 时走 [condition.value] 包装分支
    expect(catCond?.value).toEqual(['电影'])
  })

  it('onFieldChange：multiSelect 字段初始化 value 为 []，其它字段为 null', () => {
    const condition = vm.conditionGroups[0].conditions[0]

    // multiSelect 字段（category）
    condition.field = 'category'
    vm.onFieldChange(condition)
    expect(condition.operator).toBe('')
    expect(condition.value).toEqual([])

    // multiSelect 字段（tags）
    condition.field = 'tags'
    vm.onFieldChange(condition)
    expect(condition.value).toEqual([])

    // 非 multiSelect 字段（name，text 类型）→ null
    condition.field = 'name'
    vm.onFieldChange(condition)
    expect(condition.value).toBeNull()
  })

  it('getOperatorGroups 按 matchMode 过滤：单值列只暴露 in/not_in，逗号串列只暴露 contains_*', () => {
    // category（单值精确列，matchMode=exact）→ 只 in/not_in
    const catOps = (vm.getOperatorGroups('category')[0].operators || []).map((o: { value: string }) => o.value)
    expect(catOps).toEqual(['in', 'not_in'])
    expect(catOps).not.toContain('contains_any')

    // downloader_name（单值精确列）→ 只 in/not_in
    const dlOps = (vm.getOperatorGroups('downloader_name')[0].operators || []).map((o: { value: string }) => o.value)
    expect(dlOps).toEqual(['in', 'not_in'])

    // tags（逗号串列，matchMode=substring）→ 只 contains_any/not_contains_any
    const tagOps = (vm.getOperatorGroups('tags')[0].operators || []).map((o: { value: string }) => o.value)
    expect(tagOps).toEqual(['contains_any', 'not_contains_any'])
    expect(tagOps).not.toContain('in')
  })

  it('applyTemplateGroups 归一化：旧 contains_any 在单值列转 in，逗号串 value 拆数组', () => {
    const source = [{
      id: 'g1', name: '组1', logic: 'and' as const, betweenGroupLogic: 'and' as const,
      conditions: [
        // 旧格式：category（单值列）用了 contains_any + 逗号串 value
        { id: 'c1', field: 'category', operator: 'contains_any', value: '电影,音乐', mode: 'include' as const },
        // tags（逗号串列）保留 contains_any + 单值 value
        { id: 'c2', field: 'tags', operator: 'contains_any', value: 'movie', mode: 'include' as const }
      ]
    }]
    vm.applyTemplateGroups(source)

    const conds = vm.conditionGroups[0].conditions
    // category：operator 转为 in（单值精确列不允许 contains_*），value 拆数组
    expect(conds[0].field).toBe('category')
    expect(conds[0].operator).toBe('in')
    expect(conds[0].value).toEqual(['电影', '音乐'])

    // tags：operator 保留 contains_any（逗号串列），value 包装为数组
    expect(conds[1].field).toBe('tags')
    expect(conds[1].operator).toBe('contains_any')
    expect(conds[1].value).toEqual(['movie'])
  })

  it('dialog 复用语义：组件不销毁时再次调用 refreshFieldOptions 会再次拉取', async() => {
    // 模拟 el-dialog 默认 destroy-on-close=false 的行为：
    // 组件实例常驻，created 只触发一次，后续靠父组件显式调 refreshFieldOptions 刷新
    await flushLifecycle()
    const callsAfterMount = (getAllCategories as jest.MockedFunction<typeof getAllCategories>).mock.calls.length
    expect(callsAfterMount).toBe(1) // 仅 created 触发的一次

    // 不销毁组件，模拟再次打开对话框
    await vm.refreshFieldOptions()
    await flushLifecycle()

    const callsAfterReopen = (getAllCategories as jest.MockedFunction<typeof getAllCategories>).mock.calls.length
    expect(callsAfterReopen).toBe(2) // created 一次 + refreshFieldOptions 一次
  })
})
