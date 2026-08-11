import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import AdvancedSearchWorkspace from '../AdvancedSearchWorkspace.vue'
import {
  createSearchTemplate,
  deleteSearchTemplate,
  getSearchTemplates,
  updateSearchTemplate
} from '@/api/torrents'
import type { QueryTemplateConditions, SearchTemplate } from '@/api/torrents'
import type {
  AdvancedSearchGroupState,
  AdvancedSearchTemplateDraft
} from '../advancedSearchState'

jest.mock('@/store/modules/user', () => ({
  UserModule: { userId: 'user-1' }
}))

jest.mock('@/api/torrents', () => ({
  getSearchTemplates: jest.fn(),
  createSearchTemplate: jest.fn(),
  updateSearchTemplate: jest.fn(),
  deleteSearchTemplate: jest.fn()
}))

const localVue = createLocalVue()
localVue.directive('loading', {})

const mockGetSearchTemplates = getSearchTemplates as jest.MockedFunction<typeof getSearchTemplates>
const mockCreateSearchTemplate = createSearchTemplate as jest.MockedFunction<typeof createSearchTemplate>
const mockUpdateSearchTemplate = updateSearchTemplate as jest.MockedFunction<typeof updateSearchTemplate>
const mockDeleteSearchTemplate = deleteSearchTemplate as jest.MockedFunction<typeof deleteSearchTemplate>

const applyTemplateGroups = jest.fn()
const refreshFieldOptions = jest.fn()
const resetConditions = jest.fn()
const onSearch = jest.fn()
const getTemplateGroupsSnapshot = jest.fn<AdvancedSearchGroupState[], []>()

const BuilderStub = localVue.extend({
  name: 'AdvancedSearchBuilder',
  props: { searching: Boolean },
  methods: {
    applyTemplateGroups,
    refreshFieldOptions,
    resetConditions() {
      resetConditions()
      this.$emit('reset')
    },
    onSearch,
    getTemplateGroupsSnapshot
  },
  render(h) {
    return h('div', { class: 'advanced-search-builder-stub' })
  }
})

const ButtonStub = localVue.extend({
  name: 'ElButton',
  inheritAttrs: false,
  props: {
    disabled: Boolean,
    loading: Boolean
  },
  template: '<button v-bind="$attrs" :disabled="disabled || loading" v-on="$listeners"><slot /></button>'
})

const message = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
  info: jest.fn()
}

const groups: AdvancedSearchGroupState[] = [{
  id: 'group-1',
  name: '名称条件',
  logic: 'and',
  betweenGroupLogic: 'and',
  conditions: [{
    id: 'condition-1',
    field: 'name',
    operator: 'contains',
    value: 'needle',
    mode: 'include'
  }]
}]

function templateFixture(
  id: string,
  overrides: Partial<SearchTemplate> = {}
): SearchTemplate {
  return {
    id,
    user_id: 'user-1',
    name: `搜索 ${id}`,
    description: null,
    conditions: {
      source: 'advanced',
      version: 1,
      condition_groups: groups,
      sort_by: 'added_date',
      sort_order: 'desc'
    },
    is_default: false,
    is_public: false,
    usage_count: 0,
    created_time: '2026-08-11T00:00:00Z',
    updated_time: null,
    ...overrides
  }
}

function listResponse(templates: SearchTemplate[]) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: templates
  }
}

async function flushPromises() {
  for (let index = 0; index < 8; index += 1) {
    await Promise.resolve()
  }
  await localVue.nextTick()
}

interface WorkspaceVm extends Vue {
  advancedTemplates: SearchTemplate[]
  selectedTemplateId: string
  templateKeyword: string
  filteredTemplates: SearchTemplate[]
  canManageSelected: boolean
  selectTemplate(template: SearchTemplate): void
  startNewSearch(): void
  createTemplate(draft: AdvancedSearchTemplateDraft): Promise<void>
  updateSelectedTemplate(): Promise<void>
  deleteSelectedTemplate(): Promise<void>
  refreshFieldOptions(): void
  loadSavedSearches(): Promise<void>
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('AdvancedSearchWorkspace 已保存搜索侧栏', () => {
  let wrapper: Wrapper<Vue>
  const confirm = jest.fn(() => Promise.resolve())

  beforeEach(() => {
    jest.clearAllMocks()
    mockGetSearchTemplates.mockResolvedValue(listResponse([]))
    getTemplateGroupsSnapshot.mockReturnValue(groups)
  })

  afterEach(() => {
    wrapper?.destroy()
  })

  function mountWorkspace(): Wrapper<Vue> {
    return shallowMount(AdvancedSearchWorkspace, {
      localVue,
      propsData: { sortBy: 'added_date', sortOrder: 'desc' },
      mocks: {
        $message: message,
        $confirm: confirm
      },
      stubs: {
        AdvancedSearchBuilder: BuilderStub,
        LucideIcon: true,
        'el-button': ButtonStub,
        'el-input': true,
        'el-tooltip': { template: '<span><slot /></span>' }
      }
    })
  }

  it('只展示高级搜索配置，选择后回填构建器并发出排序配置', async() => {
    const systemTemplate = templateFixture('system', {
      user_id: 'system',
      name: '系统大文件',
      is_default: true,
      is_public: true
    })
    const personalTemplate = templateFixture('personal', { name: '我的搜索' })
    const simpleTemplate = templateFixture('simple', {
      conditions: {
        source: 'simple',
        version: 1,
        listQuery: { name_like: 'simple' }
      }
    })
    mockGetSearchTemplates.mockResolvedValueOnce(
      listResponse([personalTemplate, simpleTemplate, systemTemplate])
    )

    wrapper = mountWorkspace()
    await flushPromises()
    const vm = wrapper.vm as unknown as WorkspaceVm

    expect(vm.advancedTemplates.map(item => item.id)).toEqual(['system', 'personal'])
    expect(wrapper.findAll('.saved-search-item')).toHaveLength(2)

    vm.selectTemplate(personalTemplate)
    await localVue.nextTick()

    expect(applyTemplateGroups).toHaveBeenCalledWith(groups, {
      sort_by: 'added_date',
      sort_order: 'desc'
    })
    expect(wrapper.emitted('template-loaded')?.[0][0]).toEqual(personalTemplate.conditions)
    expect(vm.selectedTemplateId).toBe('personal')
    expect(vm.canManageSelected).toBe(true)
  })

  it('支持创建、覆盖更新和删除当前选择的个人搜索配置', async() => {
    const personalTemplate = templateFixture('personal', { name: '我的搜索' })
    mockGetSearchTemplates.mockResolvedValue(listResponse([personalTemplate]))
    mockCreateSearchTemplate.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: personalTemplate
    })
    mockUpdateSearchTemplate.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: personalTemplate
    })
    mockDeleteSearchTemplate.mockResolvedValue({
      status: 'success',
      msg: 'ok',
      code: '200',
      data: { id: personalTemplate.id }
    })

    wrapper = mountWorkspace()
    await flushPromises()
    const vm = wrapper.vm as unknown as WorkspaceVm
    const draft: AdvancedSearchTemplateDraft = {
      id: 'draft',
      name: '我的搜索',
      description: '描述',
      isDefault: false,
      conditions: groups,
      createdTime: '2026-08-11T00:00:00Z'
    }

    await vm.createTemplate(draft)
    expect(mockCreateSearchTemplate).toHaveBeenCalledWith(expect.objectContaining({
      name: '我的搜索',
      conditions: expect.objectContaining({
        source: 'advanced',
        condition_groups: groups,
        sort_by: 'added_date',
        sort_order: 'desc'
      })
    }))
    expect(message.success).toHaveBeenCalledWith('模板保存成功')

    vm.selectTemplate(personalTemplate)
    await vm.updateSelectedTemplate()
    expect(mockUpdateSearchTemplate).toHaveBeenCalledWith(
      'personal',
      { conditions: expect.objectContaining({ condition_groups: groups }) as QueryTemplateConditions }
    )
    expect(message.success).toHaveBeenCalledWith('搜索配置已更新')

    vm.selectTemplate(personalTemplate)
    await vm.deleteSelectedTemplate()
    expect(confirm).toHaveBeenCalled()
    expect(mockDeleteSearchTemplate).toHaveBeenCalledWith('personal')
    expect(message.success).toHaveBeenCalledWith('搜索配置已删除')
  })

  it('系统模板和他人的公开模板不可覆盖或删除，打开时可刷新字段和侧栏', async() => {
    const systemTemplate = templateFixture('system', {
      user_id: 'system',
      is_default: true,
      is_public: true
    })
    const otherTemplate = templateFixture('other', {
      user_id: 'user-2',
      is_public: true
    })
    mockGetSearchTemplates.mockResolvedValue(listResponse([systemTemplate, otherTemplate]))

    wrapper = mountWorkspace()
    await flushPromises()
    const vm = wrapper.vm as unknown as WorkspaceVm

    vm.selectTemplate(systemTemplate)
    expect(vm.canManageSelected).toBe(false)
    vm.selectTemplate(otherTemplate)
    expect(vm.canManageSelected).toBe(false)

    mockGetSearchTemplates.mockClear()
    vm.refreshFieldOptions()
    await flushPromises()
    expect(refreshFieldOptions).toHaveBeenCalled()
    expect(mockGetSearchTemplates).toHaveBeenCalledWith({ is_public: true })
  })

  it('侧栏关键词同时筛选名称和描述，新建搜索只触发一次重置并清除选中项', async() => {
    const nameMatch = templateFixture('name-match', { name: '大文件搜索' })
    const descriptionMatch = templateFixture('description-match', {
      name: '近期任务',
      description: '筛选大文件'
    })
    const unrelated = templateFixture('unrelated', { name: '已完成任务' })
    mockGetSearchTemplates.mockResolvedValueOnce(
      listResponse([nameMatch, descriptionMatch, unrelated])
    )

    wrapper = mountWorkspace()
    await flushPromises()
    const vm = wrapper.vm as unknown as WorkspaceVm

    vm.templateKeyword = '大文件'
    await localVue.nextTick()
    expect(vm.filteredTemplates.map(template => template.id)).toEqual([
      'name-match',
      'description-match'
    ])

    vm.selectTemplate(nameMatch)
    resetConditions.mockClear()
    vm.startNewSearch()
    await localVue.nextTick()

    expect(vm.selectedTemplateId).toBe('')
    expect(resetConditions).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('reset')).toHaveLength(1)
  })

  it('并发刷新已保存搜索时忽略后返回的旧响应', async() => {
    const firstRequest = deferred<ReturnType<typeof listResponse>>()
    const secondRequest = deferred<ReturnType<typeof listResponse>>()
    const staleTemplate = templateFixture('stale', { name: '旧搜索' })
    const newestTemplate = templateFixture('newest', { name: '新搜索' })
    mockGetSearchTemplates.mockReset()
    mockGetSearchTemplates
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise)

    wrapper = mountWorkspace()
    const vm = wrapper.vm as unknown as WorkspaceVm
    const latestLoad = vm.loadSavedSearches()

    secondRequest.resolve(listResponse([newestTemplate]))
    await latestLoad
    await flushPromises()
    expect(vm.advancedTemplates.map(template => template.id)).toEqual(['newest'])

    firstRequest.resolve(listResponse([staleTemplate]))
    await flushPromises()
    expect(vm.advancedTemplates.map(template => template.id)).toEqual(['newest'])
  })

  it('覆盖保存前校验当前条件，校验失败时不发送更新请求', async() => {
    const personalTemplate = templateFixture('personal', { name: '我的搜索' })
    mockGetSearchTemplates.mockResolvedValueOnce(listResponse([personalTemplate]))
    getTemplateGroupsSnapshot.mockImplementationOnce(() => {
      throw new Error('条件无效')
    })

    wrapper = mountWorkspace()
    await flushPromises()
    const vm = wrapper.vm as unknown as WorkspaceVm

    vm.selectTemplate(personalTemplate)
    await vm.updateSelectedTemplate()

    expect(mockUpdateSearchTemplate).not.toHaveBeenCalled()
    expect(message.warning).toHaveBeenCalledWith('条件无效')
  })
})
