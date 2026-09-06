/**
 * 移动端条件编辑底部弹层（方案三移动原生重构）：
 * - 打开时克隆条件为本地草稿，确认才回写（深拷贝隔离）；
 * - 字段/操作符联动语义与桌面 AdvancedSearchBuilder 同源
 *   （字段变更重置操作符与值、操作符变更转换值形态、排除模式按操作符收敛）；
 * - 操作符分组与值候选走共享层（advancedSearchFields）。
 * ConditionValueInput 以 shallowMount stub 替身（其契约由独立 spec 覆盖）。
 */

import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'
import Vue from 'vue'
import ConditionEditSheet from '@/views/mobile/components/ConditionEditSheet.vue'
import type {
  AdvancedSearchConditionState
} from '@/components/torrents/advancedSearchState'
import type {
  AdvancedSearchDynamicOptionSet,
  OperatorDisplayGroup
} from '@/components/torrents/advancedSearchFields'

jest.mock('@/api/torrents', () => ({
  getDownloaderList: jest.fn()
}))

jest.mock('@/api/tag-management', () => ({
  getAllCategories: jest.fn(),
  getAllTags: jest.fn()
}))

const localVue = createLocalVue()

interface SheetVm extends Vue {
  draft: AdvancedSearchConditionState
  operatorGroups: OperatorDisplayGroup[]
  excludeSupported: boolean
  fieldOptionsForDraft: Array<{ label: string, value: string }>
  onFieldChange(): void
  onOperatorChange(): void
  onValueChange(value: unknown): void
  onVisibleUpdate(visible: boolean): void
  confirm(): void
}

const sampleCondition: AdvancedSearchConditionState = {
  id: 'c-1',
  field: 'name',
  operator: 'contains',
  value: '4K',
  mode: 'include'
}

const dynamicOptions: AdvancedSearchDynamicOptionSet = {
  categoryOptions: [{ label: '电影', value: '电影' }],
  tagOptions: [{ label: 'tv', value: 'tv' }],
  downloaderOptions: [{ label: 'qb', value: 'd-1' }]
}

const mountSheet = (visible = false): Wrapper<Vue> =>
  shallowMount(ConditionEditSheet, {
    localVue,
    propsData: {
      visible,
      condition: sampleCondition,
      dynamicOptions
    }
  })

async function flushLifecycle(): Promise<void> {
  for (let index = 0; index < 8; index += 1) {
    await Promise.resolve()
  }
  await Vue.nextTick()
}

describe('views/mobile/components/ConditionEditSheet', () => {
  afterEach(() => {
    jest.clearAllMocks()
  })

  it('打开时克隆条件为草稿：修改草稿不影响原始条件', async() => {
    const wrapper = mountSheet(false)
    const vm = wrapper.vm as SheetVm
    expect(vm.draft.field).toBe('')

    await wrapper.setProps({ visible: true })
    expect(vm.draft).toMatchObject({ id: 'c-1', field: 'name', operator: 'contains', value: '4K' })

    vm.draft.value = 'changed'
    expect(sampleCondition.value).toBe('4K')
  })

  it('condition 为空时打开：给一条全新空草稿', async() => {
    const wrapper = shallowMount(ConditionEditSheet, {
      localVue,
      propsData: { visible: false, condition: null, dynamicOptions }
    })
    const vm = wrapper.vm as SheetVm
    await wrapper.setProps({ visible: true })
    expect(vm.draft.field).toBe('')
    expect(vm.draft.id).not.toBe('')
  })

  it('字段变更：清空操作符、按字段类型重置值、方式回落包含', async() => {
    const wrapper = mountSheet(false)
    const vm = wrapper.vm as SheetVm
    await wrapper.setProps({ visible: true })

    vm.draft.field = 'size'
    vm.onFieldChange()
    expect(vm.draft.operator).toBe('')
    // size 字段空操作符的默认值形态是单值+单位（非 between 不给范围结构）
    expect(vm.draft.value).toEqual({ value: null, unit: 'GB' })
    expect(vm.draft.mode).toBe('include')
  })

  it('操作符变更：size between 转换为范围值形态', async() => {
    const wrapper = mountSheet(true)
    const vm = wrapper.vm as SheetVm
    await flushLifecycle()

    vm.draft.field = 'size'
    vm.draft.operator = 'between'
    vm.onOperatorChange()
    expect(vm.draft.value).toEqual({
      min: null,
      max: null,
      minUnit: 'GB',
      maxUnit: 'GB'
    })
  })

  it('操作符变更：is_null 值清空且排除模式不可用', async() => {
    const wrapper = mountSheet(true)
    const vm = wrapper.vm as SheetVm
    await flushLifecycle()

    vm.draft.field = 'name'
    vm.draft.operator = 'is_null'
    vm.onOperatorChange()
    expect(vm.draft.value).toBeNull()
    expect(vm.excludeSupported).toBe(false)
    expect(vm.draft.mode).toBe('include')
  })

  it('操作符分组：tags（逗号串列）暴露 contains_any 不暴露 in；category（单值列）反之', async() => {
    const wrapper = mountSheet(true)
    const vm = wrapper.vm as SheetVm
    await flushLifecycle()

    vm.draft.field = 'tags'
    expect(vm.operatorGroups[0].operators.map(op => op.value)).toEqual(expect.arrayContaining(['contains_any']))
    expect(vm.operatorGroups[0].operators.map(op => op.value)).not.toEqual(expect.arrayContaining(['in']))

    vm.draft.field = 'category'
    expect(vm.operatorGroups[0].operators.map(op => op.value)).toEqual(expect.arrayContaining(['in']))
    expect(vm.operatorGroups[0].operators.map(op => op.value)).not.toEqual(expect.arrayContaining(['contains_any']))
  })

  it('排除模式可用性：contains 支持，is_null 不支持', async() => {
    const wrapper = mountSheet(true)
    const vm = wrapper.vm as SheetVm
    await flushLifecycle()

    vm.draft.operator = 'contains'
    expect(vm.excludeSupported).toBe(true)

    vm.draft.operator = 'is_null'
    expect(vm.excludeSupported).toBe(false)
  })

  it('值候选：category 注入动态选项，status 走静态选项', async() => {
    const wrapper = mountSheet(true)
    const vm = wrapper.vm as SheetVm
    await flushLifecycle()

    vm.draft.field = 'category'
    expect(vm.fieldOptionsForDraft).toEqual([{ label: '电影', value: '电影' }])

    vm.draft.field = 'status'
    expect(vm.fieldOptionsForDraft.length).toBeGreaterThan(0)
  })

  it('值变更：回写草稿值', async() => {
    const wrapper = mountSheet(true)
    const vm = wrapper.vm as SheetVm
    await flushLifecycle()

    vm.onValueChange('新值')
    expect(vm.draft.value).toBe('新值')
  })

  it('确认：emit 深拷贝草稿并关闭弹层，事后改草稿不影响已回写值', async() => {
    const wrapper = mountSheet(false)
    const vm = wrapper.vm as SheetVm
    // 草稿克隆发生在 visible false→true 变更时
    await wrapper.setProps({ visible: true })

    vm.confirm()
    const emitted = wrapper.emitted('confirm')
    expect(emitted).toBeTruthy()
    const confirmed = emitted?.[0][0] as AdvancedSearchConditionState
    expect(confirmed).toMatchObject({ field: 'name', operator: 'contains', value: '4K' })

    expect(wrapper.emitted('update:visible')?.[0]).toEqual([false])

    vm.draft.value = '事后修改'
    expect(confirmed.value).toBe('4K')
  })

  it('弹层可见性回传：onVisibleUpdate 转发 update:visible', async() => {
    const wrapper = mountSheet(true)
    const vm = wrapper.vm as SheetVm

    vm.onVisibleUpdate(false)
    expect(wrapper.emitted('update:visible')?.[0]).toEqual([false])
  })
})
