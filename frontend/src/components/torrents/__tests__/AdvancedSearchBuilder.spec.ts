import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'
import AdvancedSearchBuilder from '../AdvancedSearchBuilder.vue'

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
  duplicateConditionGroup(group: ConditionGroupVm): void
  clearGroupConditions(group: ConditionGroupVm): void
  removeConditionGroup(index: number): void
  startEditingGroup(group: ConditionGroupVm): void
  finishEditingGroup(group: ConditionGroupVm): void
  onFieldChange(condition: SearchConditionVm): void
  onOperatorChange(condition: SearchConditionVm): void
  getFieldOptions(fieldKey: string): Array<{ label: string, value: string }>
  getOperatorGroups(fieldKey: string): Array<{ type: string, label: string }>
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
})
