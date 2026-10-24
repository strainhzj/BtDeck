/**
 * MCP 服务设置面板回归（mcp-service-capabilities W1）。
 *
 * 保护点：
 * 1. 能力清单由 GET catalog 下发渲染（前端无硬编码副本），全局 + 6 能力开关齐备；
 * 2. 保存载荷携带全部能力码与 expectedRevision（CAS），成功后以服务端返回态收敛；
 * 3. 409 冲突提示并自动重载最新配置（不清空草稿之外的本地状态机）；
 * 4. kill switch（forceDisabled）只读横幅展示，保存入口不受其禁用（保留意图语义）；
 * 5. dirty 跟踪：未改动时保存/放弃按钮禁用；
 * 6. W5 服务密钥卡：三态渲染（absent 引导生成 / active 明文+复制 / unreadable 引导
 *    刷新）、端点与认证头提示、生成/刷新危险确认、409 冲突重载；明文仅存组件内存；
 * 7. W5 能力描述双语：en locale 取 descriptionEn（缺失回退 description），zh 取 description。
 *
 * demo 模式下本面板经 @/demo 拦截层取数渲染（无独立分支），行为回归见
 * demo-request.spec.ts 的 MCP 用例组。
 */

import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import VueI18n from 'vue-i18n'
import i18n from '@/i18n'

import McpSettingsPanel from '@/views/settings/components/McpSettingsPanel.vue'
import {
  getMcpSettings,
  updateMcpSettings,
  getMcpApiKey,
  rotateMcpApiKey,
  McpApiKeyView,
  McpCapabilityMeta
} from '@/api/mcp-settings'
import { ApiError } from '@/types/api'
import { setLocale } from '@/i18n'
import { copyTextToClipboard } from '@/utils/clipboard'

jest.mock('@/api/mcp-settings', () => ({
  getMcpSettings: jest.fn(),
  updateMcpSettings: jest.fn(),
  getMcpApiKey: jest.fn(),
  rotateMcpApiKey: jest.fn()
}))

jest.mock('@/utils/clipboard', () => ({
  copyTextToClipboard: jest.fn().mockResolvedValue(undefined)
}))

const mockGet = getMcpSettings as jest.MockedFunction<typeof getMcpSettings>
const mockUpdate = updateMcpSettings as jest.MockedFunction<typeof updateMcpSettings>
const mockGetApiKey = getMcpApiKey as jest.MockedFunction<typeof getMcpApiKey>
const mockRotateApiKey = rotateMcpApiKey as jest.MockedFunction<typeof rotateMcpApiKey>

const localVue = createLocalVue()
localVue.use(ElementUI)
localVue.use(VueI18n)

/** class 组件的 private 成员运行时即实例成员，经接口重声明访问 */
interface PanelVm {
  load: () => Promise<void>
  save: () => Promise<void>
  dirty: boolean
  saving: boolean
  revision: number
}

const CATALOG: McpCapabilityMeta[] = [
  { code: 'torrent.advanced_search', tool: 'torrent_advanced_search', risk: 'read', description: '只读查询', descriptionEn: 'Read-only search', defaultEnabled: false, requiresConfirm: false, requiresIdempotencyKey: false },
  { code: 'torrent.mark_pending_delete', tool: 'torrent_mark_pending_delete', risk: 'write', description: '添加待删除标签', descriptionEn: 'Add pending-delete tag', defaultEnabled: false, requiresConfirm: true, requiresIdempotencyKey: true },
  { code: 'torrent.add', tool: 'torrent_add_file', risk: 'high', description: '添加种子文件', descriptionEn: 'Add torrent file', defaultEnabled: false, requiresConfirm: true, requiresIdempotencyKey: true },
  { code: 'search_template.create', tool: 'advanced_search_template_create', risk: 'write', description: '创建查询模板', descriptionEn: 'Create search template', defaultEnabled: false, requiresConfirm: true, requiresIdempotencyKey: true },
  { code: 'dashboard.read', tool: 'dashboard_get', risk: 'read', description: '仪表盘聚合', descriptionEn: 'Dashboard aggregates', defaultEnabled: false, requiresConfirm: false, requiresIdempotencyKey: false },
  { code: 'cron.trigger', tool: 'cron_task_trigger', risk: 'high', description: '触发内置任务', descriptionEn: 'Trigger built-in task', defaultEnabled: false, requiresConfirm: true, requiresIdempotencyKey: true }
]

const ALL_OFF: Record<string, boolean> = Object.fromEntries(CATALOG.map(c => [c.code, false]))

function makeResponse(opts: {
  enabled?: boolean
  capabilities?: Record<string, boolean>
  revision?: number
  forceDisabled?: boolean
  updatedAt?: string | null
  updatedBy?: string | null
} = {}) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      settings: {
        schemaVersion: 1,
        enabled: opts.enabled ?? false,
        capabilities: opts.capabilities ?? { ...ALL_OFF },
        revision: opts.revision ?? 0,
        updatedAt: opts.updatedAt ?? null,
        updatedBy: opts.updatedBy ?? null,
        forceDisabled: opts.forceDisabled ?? false,
        effectiveEnabled: (opts.enabled ?? false) && !(opts.forceDisabled ?? false)
      },
      catalog: CATALOG
    }
  } as unknown as Awaited<ReturnType<typeof getMcpSettings>>
}

function makeApiError(code: string): ApiError {
  return new ApiError('冲突', { code, httpStatus: Number(code) })
}

/** 刷净微任务队列（mounted/load/save 内的 await 链） */
async function flushPromises(): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, 0))
}

/** 按文案查找按钮，缺失即抛错（避免非空断言 lint 警告） */
function findButton(wrapper: Wrapper<Vue>, text: string): Wrapper<Vue> {
  const btn = wrapper.findAllComponents({ name: 'ElButton' }).wrappers.find(b => b.text().includes(text))
  if (!btn) throw new Error(`未找到按钮: ${text}`)
  return btn
}

const DEMO_APIKEY = 'btdmcp_' + 'A'.repeat(43)

function makeApiKeyResponse(overrides: Partial<McpApiKeyView> = {}) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      status: 'active',
      exists: true,
      revision: 1,
      createdAt: '2026-09-22T10:00:00+00:00',
      createdBy: 'admin',
      updatedAt: '2026-09-22T10:00:00+00:00',
      updatedBy: 'admin',
      keyPrefix: 'btdmcp_',
      key: DEMO_APIKEY,
      ...overrides
    }
  } as unknown as Awaited<ReturnType<typeof getMcpApiKey>>
}

/** 挂载并等待 mounted 内的首次 load 完成（密钥态默认 active，可传覆盖） */
async function mountPanel(apikeyResponse = makeApiKeyResponse()): Promise<Wrapper<Vue>> {
  mockGetApiKey.mockResolvedValue(apikeyResponse)
  const wrapper = mount(McpSettingsPanel, { localVue, i18n })
  await flushPromises()
  await wrapper.vm.$nextTick()
  return wrapper
}

beforeEach(() => {
  jest.clearAllMocks()
  jest.restoreAllMocks()
})

describe('McpSettingsPanel', () => {
  it('渲染后端下发的 6 项能力与全局开关（单一事实源，无硬编码副本）', async() => {
    mockGet.mockResolvedValue(makeResponse())
    const wrapper = await mountPanel()
    expect(mockGet).toHaveBeenCalledTimes(1)
    const switches = wrapper.findAllComponents({ name: 'ElSwitch' })
    // 1 个全局开关 + 6 个能力开关
    expect(switches.length).toBe(7)
    for (const cap of CATALOG) {
      expect(wrapper.text()).toContain(cap.tool)
    }
    // 风险分级标签存在
    expect(wrapper.text()).toContain('高风险')
    expect(wrapper.text()).toContain('只读')
  })

  it('未改动时保存与放弃按钮禁用（dirty 跟踪）', async() => {
    mockGet.mockResolvedValue(makeResponse())
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    expect(vm.dirty).toBe(false)
    const saveButton = findButton(wrapper, '保存配置')
    expect(saveButton.attributes('disabled')).toBeDefined()
  })

  it('保存携带全部能力码与 expectedRevision，成功后按服务端返回收敛', async() => {
    mockGet.mockResolvedValue(makeResponse())
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm

    // 打开全局开关 + 单个能力
    const switches = wrapper.findAllComponents({ name: 'ElSwitch' })
    const capsOn = { ...ALL_OFF, 'dashboard.read': true }
    mockUpdate.mockResolvedValue(makeResponse({ enabled: true, capabilities: capsOn, revision: 1 }))
    await switches.at(0).vm.$emit('input', true)
    await wrapper.findAllComponents({ name: 'ElSwitch' }).at(5).vm.$emit('input', true)
    expect(vm.dirty).toBe(true)

    await vm.save()
    expect(mockUpdate).toHaveBeenCalledTimes(1)
    const payload = mockUpdate.mock.calls[0][0]
    expect(payload.enabled).toBe(true)
    expect(Object.keys(payload.capabilities).sort()).toEqual(Object.keys(ALL_OFF).sort())
    expect(payload.expectedRevision).toBe(0)
    // 收敛到服务端 revision
    expect(vm.revision).toBe(1)
    expect(vm.dirty).toBe(false)
  })

  it('409 冲突提示并自动重载最新配置', async() => {
    mockGet.mockResolvedValue(makeResponse())
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    const warningSpy = jest.spyOn(wrapper.vm.$message, 'warning').mockImplementation((() => ({})) as unknown as () => never)
    const switches = wrapper.findAllComponents({ name: 'ElSwitch' })
    await switches.at(0).vm.$emit('input', true)

    mockUpdate.mockRejectedValue(makeApiError('409'))
    mockGet.mockClear()
    mockGet.mockResolvedValue(makeResponse({ enabled: false, revision: 3, updatedAt: '2026-09-08T08:00:00+00:00', updatedBy: 'other-admin' }))
    await vm.save()
    await flushPromises()

    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(vm.revision).toBe(3)
    expect(warningSpy).toHaveBeenCalledWith(expect.stringContaining('已被其他会话修改'))
  })

  it('非 409 错误给出失败提示且不重载', async() => {
    mockGet.mockResolvedValue(makeResponse())
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    const switches = wrapper.findAllComponents({ name: 'ElSwitch' })
    await switches.at(0).vm.$emit('input', true)

    mockUpdate.mockRejectedValue(makeApiError('500'))
    mockGet.mockClear()
    await vm.save()
    expect(mockGet).not.toHaveBeenCalled()
    expect(vm.dirty).toBe(true)
  })

  it('kill switch 横幅只读展示且保存入口不被禁用（保留意图语义）', async() => {
    mockGet.mockResolvedValue(makeResponse({ forceDisabled: true, enabled: true, revision: 2 }))
    const wrapper = await mountPanel()
    expect(wrapper.text()).toContain('BTDECK_MCP_FORCE_DISABLED')
    expect(wrapper.text()).toContain('当前实际生效：关闭')
    const saveButton = findButton(wrapper, '保存配置')
    // 载入即与已保存态一致（无改动）→ disabled 由 dirty 决定，与 kill switch 无关
    expect(saveButton.attributes('disabled')).toBeDefined()
    // 改动后 kill switch 不阻塞保存
    const switches = wrapper.findAllComponents({ name: 'ElSwitch' })
    await switches.at(1).vm.$emit('input', true)
    expect(saveButton.attributes('disabled')).toBeUndefined()
  })

  it('加载失败显示占位与重试，重试成功恢复', async() => {
    mockGet.mockRejectedValueOnce(makeApiError('500'))
    const wrapper = await mountPanel()
    expect(wrapper.text()).toContain('MCP 配置加载失败')

    mockGet.mockResolvedValue(makeResponse())
    const retry = findButton(wrapper, '重试')
    await retry.vm.$emit('click')
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('保存配置')
  })
  // ====== W5 服务密钥卡 ======

  it('active 态渲染明文密钥（掩码输入）、端点与认证头提示', async() => {
    mockGet.mockResolvedValue(makeResponse())
    const wrapper = await mountPanel()
    const input = wrapper.findAllComponents({ name: 'ElInput' }).wrappers.find(w => (w.props('value') as string) === DEMO_APIKEY)
    expect(input).toBeDefined()
    // 端点与认证提示
    expect(wrapper.text()).toContain('/mcp/')
    expect(wrapper.text()).toContain('Authorization: Bearer')
    // 创建/刷新时间信息
    expect(wrapper.text()).toContain('创建于')
    expect(wrapper.text()).toContain('最近刷新')
  })

  it('absent 态显示生成引导，确认后 rotate(0) 并展示新密钥', async() => {
    mockGet.mockResolvedValue(makeResponse())
    mockGetApiKey.mockResolvedValue(makeApiKeyResponse({ status: 'absent', exists: false, key: undefined, revision: 0 }))
    const confirmMock = jest.fn((..._args: unknown[]) => Promise.resolve())
    const wrapper = mount(McpSettingsPanel, { localVue, i18n, mocks: { $confirm: confirmMock } })
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('尚未生成服务密钥')
    const generateButton = findButton(wrapper, '生成服务密钥')
    const rotatedKey = 'btdmcp_' + 'B'.repeat(43)
    mockRotateApiKey.mockResolvedValue(makeApiKeyResponse({ key: rotatedKey }))
    const successSpy = jest.spyOn(wrapper.vm.$message, 'success').mockImplementation((() => ({})) as unknown as () => never)

    await generateButton.vm.$emit('click')
    await flushPromises()

    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(mockRotateApiKey).toHaveBeenCalledWith(0)
    expect(successSpy).toHaveBeenCalledWith(expect.stringContaining('服务密钥已生成'))
    const input = wrapper.findAllComponents({ name: 'ElInput' }).wrappers.find(w => (w.props('value') as string) === rotatedKey)
    expect(input).toBeDefined()
  })

  it('active 态刷新需危险确认（旧密钥立即失效警示），确认后 rotate(revision)', async() => {
    mockGet.mockResolvedValue(makeResponse())
    mockGetApiKey.mockResolvedValue(makeApiKeyResponse({ revision: 3 }))
    const confirmMock = jest.fn((..._args: unknown[]) => Promise.resolve())
    const wrapper = mount(McpSettingsPanel, { localVue, i18n, mocks: { $confirm: confirmMock } })
    await flushPromises()
    await wrapper.vm.$nextTick()

    const rotateButton = findButton(wrapper, '刷新服务密钥')
    mockRotateApiKey.mockResolvedValue(makeApiKeyResponse({ revision: 4, key: 'btdmcp_' + 'C'.repeat(43) }))
    const successSpy = jest.spyOn(wrapper.vm.$message, 'success').mockImplementation((() => ({})) as unknown as () => never)

    await rotateButton.vm.$emit('click')
    await flushPromises()

    expect(confirmMock).toHaveBeenCalledTimes(1)
    // 危险确认文案明示旧密钥失效/Agent 断联
    const confirmText = String(confirmMock.mock.calls[0][0])
    expect(confirmText).toContain('旧密钥')
    expect(confirmText).toContain('Agent')
    expect(mockRotateApiKey).toHaveBeenCalledWith(3)
    expect(successSpy).toHaveBeenCalledWith(expect.stringContaining('服务密钥已刷新'))
  })

  it('用户取消确认时不调用 rotate', async() => {
    mockGet.mockResolvedValue(makeResponse())
    mockGetApiKey.mockResolvedValue(makeApiKeyResponse())
    const confirmMock = jest.fn((..._args: unknown[]) => Promise.reject('cancel'))
    const wrapper = mount(McpSettingsPanel, { localVue, i18n, mocks: { $confirm: confirmMock } })
    await flushPromises()
    await wrapper.vm.$nextTick()

    await findButton(wrapper, '刷新服务密钥').vm.$emit('click')
    await flushPromises()
    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(mockRotateApiKey).not.toHaveBeenCalled()
  })

  it('unreadable 态显示引导刷新且不渲染密钥输入框', async() => {
    mockGet.mockResolvedValue(makeResponse())
    const wrapper = await mountPanel(makeApiKeyResponse({ status: 'unreadable', key: undefined }))
    expect(wrapper.text()).toContain('当前无法读取')
    const input = wrapper.findAllComponents({ name: 'ElInput' }).wrappers.find(w => (w.props('value') as string) === DEMO_APIKEY)
    expect(input).toBeUndefined()
  })

  it('rotate 409 冲突提示并自动重载密钥', async() => {
    mockGet.mockResolvedValue(makeResponse())
    mockGetApiKey.mockResolvedValue(makeApiKeyResponse({ revision: 1 }))
    const wrapper = await mountPanel()
    mockGetApiKey.mockClear()
    mockGetApiKey.mockResolvedValue(makeApiKeyResponse({ revision: 5 }))
    mockRotateApiKey.mockRejectedValue(makeApiError('409'))
    const warningSpy = jest.spyOn(wrapper.vm.$message, 'warning').mockImplementation((() => ({})) as unknown as () => never)

    await (wrapper.vm as unknown as { rotateApiKey: () => Promise<void> }).rotateApiKey()
    await flushPromises()

    expect(warningSpy).toHaveBeenCalledWith(expect.stringContaining('服务密钥已被其他会话变更'))
    expect(mockGetApiKey).toHaveBeenCalledTimes(1) // 冲突后重载
  })

  it('复制密钥写入剪贴板并提示成功', async() => {
    mockGet.mockResolvedValue(makeResponse())
    const wrapper = await mountPanel()
    const successSpy = jest.spyOn(wrapper.vm.$message, 'success').mockImplementation((() => ({})) as unknown as () => never)

    await findButton(wrapper, '复制').vm.$emit('click')
    await flushPromises()

    expect(copyTextToClipboard).toHaveBeenCalledWith(DEMO_APIKEY)
    expect(successSpy).toHaveBeenCalledWith(expect.stringContaining('已复制'))
  })

  it('密钥加载失败显示占位与重试', async() => {
    mockGet.mockResolvedValue(makeResponse())
    mockGetApiKey.mockRejectedValueOnce(makeApiError('500'))
    const wrapper = await mountPanel()
    expect(wrapper.text()).toContain('MCP 配置加载失败') // 密钥卡复用面板级 loadFailed 文案

    mockGetApiKey.mockResolvedValue(makeApiKeyResponse())
    await findButton(wrapper, '重试').vm.$emit('click')
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('刷新服务密钥')
  })

  it('能力描述按 locale 选取：zh 取 description，en 取 descriptionEn', async() => {
    mockGet.mockResolvedValue(makeResponse())
    const wrapper = await mountPanel()
    expect(wrapper.text()).toContain('只读查询')

    setLocale('en')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Read-only search')
    expect(wrapper.text()).not.toContain('只读查询')

    setLocale('zh-CN')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('只读查询')
  })
})

afterEach(() => {
  setLocale('zh-CN')
})
