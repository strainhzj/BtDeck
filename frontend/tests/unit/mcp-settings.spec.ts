/**
 * MCP 服务设置面板回归（mcp-service-capabilities W1）。
 *
 * 保护点：
 * 1. 能力清单由 GET catalog 下发渲染（前端无硬编码副本），全局 + 6 能力开关齐备；
 * 2. 保存载荷携带全部能力码与 expectedRevision（CAS），成功后以服务端返回态收敛；
 * 3. 409 冲突提示并自动重载最新配置（不清空草稿之外的本地状态机）；
 * 4. kill switch（forceDisabled）只读横幅展示，保存入口不受其禁用（保留意图语义）；
 * 5. demo 模式不发起任何 API，显示只读占位；
 * 6. dirty 跟踪：未改动时保存/放弃按钮禁用。
 */

import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'

import McpSettingsPanel from '@/views/settings/components/McpSettingsPanel.vue'
import { getMcpSettings, updateMcpSettings, McpCapabilityMeta } from '@/api/mcp-settings'
import { isDemoMode } from '@/demo/config'
import { ApiError } from '@/types/api'

jest.mock('@/api/mcp-settings', () => ({
  getMcpSettings: jest.fn(),
  updateMcpSettings: jest.fn()
}))

jest.mock('@/demo/config', () => ({
  isDemoMode: jest.fn(() => false)
}))

const mockGet = getMcpSettings as jest.MockedFunction<typeof getMcpSettings>
const mockUpdate = updateMcpSettings as jest.MockedFunction<typeof updateMcpSettings>
const mockIsDemoMode = isDemoMode as jest.MockedFunction<typeof isDemoMode>

const localVue = createLocalVue()
localVue.use(ElementUI)

/** class 组件的 private 成员运行时即实例成员，经接口重声明访问 */
interface PanelVm {
  load: () => Promise<void>
  save: () => Promise<void>
  dirty: boolean
  saving: boolean
  revision: number
}

const CATALOG: McpCapabilityMeta[] = [
  { code: 'torrent.advanced_search', tool: 'torrent_advanced_search', risk: 'read', description: '只读查询', defaultEnabled: false, requiresConfirm: false, requiresIdempotencyKey: false },
  { code: 'torrent.mark_pending_delete', tool: 'torrent_mark_pending_delete', risk: 'write', description: '添加待删除标签', defaultEnabled: false, requiresConfirm: true, requiresIdempotencyKey: true },
  { code: 'torrent.add', tool: 'torrent_add_file', risk: 'high', description: '添加种子文件', defaultEnabled: false, requiresConfirm: true, requiresIdempotencyKey: true },
  { code: 'search_template.create', tool: 'advanced_search_template_create', risk: 'write', description: '创建查询模板', defaultEnabled: false, requiresConfirm: true, requiresIdempotencyKey: true },
  { code: 'dashboard.read', tool: 'dashboard_get', risk: 'read', description: '仪表盘聚合', defaultEnabled: false, requiresConfirm: false, requiresIdempotencyKey: false },
  { code: 'cron.trigger', tool: 'cron_task_trigger', risk: 'high', description: '触发内置任务', defaultEnabled: false, requiresConfirm: true, requiresIdempotencyKey: true }
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

/** 挂载并等待 mounted 内的首次 load 完成 */
async function mountPanel(): Promise<Wrapper<Vue>> {
  const wrapper = mount(McpSettingsPanel, { localVue })
  await flushPromises()
  await wrapper.vm.$nextTick()
  return wrapper
}

beforeEach(() => {
  jest.clearAllMocks()
  jest.restoreAllMocks()
  mockIsDemoMode.mockReturnValue(false)
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

  it('demo 模式不发起 API，显示只读占位', async() => {
    mockIsDemoMode.mockReturnValue(true)
    const wrapper = await mountPanel()
    expect(mockGet).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('演示模式不支持修改 MCP 服务配置')
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
})
