/**
 * 移动维护只读入口回归（database-migration-ui W4-4；/m/maintenance）。
 *
 * 保护点：
 * 1. 未认证：渲染维护认证表单（用户名/密码/可选 twofa），不拉状态、不轮询；
 * 2. 认证成功进入状态区：粗粒度状态徽标（人类可读文案）+ attemptId/epoch 锚点；
 * 3. 已有内存 token 重挂载：直接进入状态视图；
 * 4. restartPending（COMMITTED_PENDING_RESTART）：待重启标题 + 手动重启文案；
 * 5. 移动端无凭据重输表单：NEEDS_CREDENTIALS 同样只读指引（不渲染目标主机/
 *    提交凭据等输入）；
 * 6. 不做平台门控：矩阵 db_migration=unsupported 时页面照常渲染（恢复面
 *    全平台可达，§9）；
 * 7. beforeDestroy 清理 10s 轮询定时器并退订 auth expired。
 */

import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import VueI18n from 'vue-i18n'
import i18n from '@/i18n'

import MobileMaintenance from '@/views/mobile/maintenance.vue'
import {
  maintenanceLogin,
  maintenanceRequest,
  getMaintenanceStatus,
  getMaintenanceToken,
  clearMaintenanceToken,
  subscribeAuthExpired
} from '@/utils/maintenance-client'
import {
  PlatformCapabilitiesData,
  resetPlatformCapabilityCache,
  setPlatformCapabilityCacheForTesting
} from '@/api/platform-capabilities'

jest.mock('@/utils/maintenance-client', () => ({
  maintenanceLogin: jest.fn(),
  maintenanceRequest: jest.fn(),
  getMaintenanceStatus: jest.fn(),
  getMaintenanceToken: jest.fn(),
  clearMaintenanceToken: jest.fn(),
  // 订阅即返回独立退订函数（经 mock.results 捕获）
  subscribeAuthExpired: jest.fn((_handler: () => void) => jest.fn())
}))

const mockLogin = maintenanceLogin as jest.MockedFunction<typeof maintenanceLogin>
const mockRequest = maintenanceRequest as jest.MockedFunction<typeof maintenanceRequest>
const mockGetStatus = getMaintenanceStatus as jest.MockedFunction<typeof getMaintenanceStatus>
const mockGetToken = getMaintenanceToken as jest.MockedFunction<typeof getMaintenanceToken>
const mockClearToken = clearMaintenanceToken as jest.MockedFunction<typeof clearMaintenanceToken>
const mockSubscribe = subscribeAuthExpired as jest.MockedFunction<typeof subscribeAuthExpired>

const localVue = createLocalVue()
localVue.use(ElementUI)
localVue.use(VueI18n)

/** class 组件的 private 成员运行时即实例成员，经接口重声明访问 */
interface PageVm {
  authenticated: boolean
  loginForm: { username: string, password: string, twofa: string }
  pollTimer: number | null
  login: () => Promise<void>
}

/** /maintenance/status 数据体（W4-1 契约：state/attemptId/epoch/extra） */
function makeStatus(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { state: 'FROZEN', attemptId: 'att-100', epoch: 'ep-7', extra: {}, ...overrides }
}

/** 刷净微任务队列（mounted/login/fetchStatus 内的 await 链） */
async function flushPromises(): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, 0))
}

/** 挂载并等待 mounted 内首次刷新完成 */
async function mountPage(): Promise<Wrapper<Vue>> {
  const wrapper = mount(MobileMaintenance, { localVue, i18n })
  await flushPromises()
  await wrapper.vm.$nextTick()
  return wrapper
}

let activeWrapper: Wrapper<Vue> | null = null

beforeEach(() => {
  jest.clearAllMocks()
  jest.restoreAllMocks()

  mockGetToken.mockReturnValue(null)
  mockLogin.mockResolvedValue({ maintenanceToken: 'mtk-1', tokenType: 'bearer', expiresIn: 300 })
  mockGetStatus.mockImplementation(async() => makeStatus() as never)
  resetPlatformCapabilityCache()
})

afterEach(() => {
  if (activeWrapper) {
    activeWrapper.destroy()
    activeWrapper = null
  }
  resetPlatformCapabilityCache()
})

describe('MobileMaintenance（/m/maintenance）', () => {
  it('未认证：仅渲染认证区（用户名/密码/可选 twofa），不拉状态、不轮询', async() => {
    const setIntervalSpy = jest.spyOn(window, 'setInterval')
    const wrapper = await mountPage()
    activeWrapper = wrapper

    expect(wrapper.text()).toContain('维护认证')
    expect(wrapper.text()).toContain('用户名')
    expect(wrapper.text()).toContain('两步验证码（可选）')
    // 状态区/指引区不渲染（描述文案含「维护状态」字样，以徽标/锚点/指引标题判定）
    expect(wrapper.text()).not.toContain('已冻结')
    expect(wrapper.text()).not.toContain('att-100')
    expect(wrapper.text()).not.toContain('只读指引')
    // 不发起任何状态请求，不创建轮询定时器
    expect(mockGetStatus).not.toHaveBeenCalled()
    expect(mockRequest).not.toHaveBeenCalled()
    expect(setIntervalSpy).not.toHaveBeenCalled()
  })

  it('认证成功后进入状态区：粗粒度徽标文案 + attemptId/epoch 锚点', async() => {
    const wrapper = await mountPage()
    activeWrapper = wrapper
    const vm = wrapper.vm as unknown as PageVm

    vm.loginForm.username = 'admin'
    vm.loginForm.password = 'pw'
    vm.loginForm.twofa = ''
    await vm.login()
    await flushPromises()
    await wrapper.vm.$nextTick()

    // 独立通道认证（twofa 为空 → 不传）
    expect(mockLogin).toHaveBeenCalledWith('admin', 'pw', undefined)
    expect(vm.authenticated).toBe(true)
    // 认证区被状态区替换
    expect(wrapper.text()).not.toContain('维护认证')
    expect(wrapper.text()).toContain('维护状态')
    // FROZEN → 人类可读文案 + 锚点
    expect(wrapper.text()).toContain('已冻结')
    expect(wrapper.text()).toContain('att-100')
    expect(wrapper.text()).toContain('ep-7')
    expect(mockGetStatus).toHaveBeenCalled()
  })

  it('已有内存 token 重挂载：直接进入状态视图（不重走认证表单）', async() => {
    mockGetToken.mockReturnValue('mtk-live')
    const wrapper = await mountPage()
    activeWrapper = wrapper

    expect(wrapper.text()).not.toContain('维护认证')
    expect(wrapper.text()).toContain('已冻结')
    expect(mockGetStatus).toHaveBeenCalled()
  })

  it('restartPending：待重启标题 + 手动重启提示文案', async() => {
    mockGetToken.mockReturnValue('mtk-live')
    mockGetStatus.mockImplementation(async() => makeStatus({ state: 'COMMITTED_PENDING_RESTART' }) as never)

    const wrapper = await mountPage()
    activeWrapper = wrapper

    expect(wrapper.text()).toContain('待重启生效')
    expect(wrapper.text()).toContain('配置已提交，需手动重启服务后生效')
  })

  it('NEEDS_CREDENTIALS：仅状态徽标 + 只读指引，不渲染凭据重输表单', async() => {
    mockGetToken.mockReturnValue('mtk-live')
    mockGetStatus.mockImplementation(async() => makeStatus({ state: 'NEEDS_CREDENTIALS' }) as never)

    const wrapper = await mountPage()
    activeWrapper = wrapper

    // 粗粒度徽标可见
    expect(wrapper.text()).toContain('等待补交凭据')
    // 无凭据重输表单：不出现目标库字段与提交按钮
    expect(wrapper.text()).not.toContain('目标主机')
    expect(wrapper.text()).not.toContain('目标密码')
    expect(wrapper.text()).not.toContain('提交凭据')
    expect(wrapper.findAll('.m-card input').length).toBe(0)
    // 只读指引文案（操作面在桌面维护页）
    expect(wrapper.text()).toContain('只读指引')
    expect(wrapper.text()).toContain('桌面端维护页')
  })

  it('不做平台门控：矩阵 db_migration=unsupported 时页面照常渲染（恢复面全平台可达）', async() => {
    const matrix: PlatformCapabilitiesData = {
      schemaVersion: 2,
      platform: 'android-server',
      capabilities: { db_migration: { label: '数据库迁移', level: 'unsupported' } },
      degradedCount: 0,
      unsupportedCount: 1
    }
    setPlatformCapabilityCacheForTesting(matrix)
    mockGetToken.mockReturnValue('mtk-live')

    const wrapper = await mountPage()
    activeWrapper = wrapper

    // 无平台拒绝提示，状态徽标配额照常渲染
    expect(wrapper.text()).not.toContain('当前平台不支持数据库迁移')
    expect(wrapper.text()).toContain('已冻结')
  })

  it('beforeDestroy：清理 10s 轮询定时器并退订 auth expired 订阅', async() => {
    mockGetToken.mockReturnValue('mtk-live')
    const setIntervalSpy = jest.spyOn(window, 'setInterval')
    const clearIntervalSpy = jest.spyOn(window, 'clearInterval')

    const wrapper = await mountPage()
    activeWrapper = wrapper
    const vm = wrapper.vm as unknown as PageVm

    // 10s 轮询已注册
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 10000)
    const timerId = vm.pollTimer
    expect(timerId).not.toBeNull()

    const unsubscribe = mockSubscribe.mock.results[0].value as jest.Mock
    wrapper.destroy()
    activeWrapper = null

    expect(clearIntervalSpy).toHaveBeenCalledWith(timerId)
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it('维护会话过期：订阅回调回认证区、清内存 token、不弹全局 toast', async() => {
    mockGetToken.mockReturnValue('mtk-live')
    const wrapper = await mountPage()
    activeWrapper = wrapper
    const vm = wrapper.vm as unknown as PageVm
    const messageSpy = jest.spyOn(wrapper.vm, '$message')

    expect(mockSubscribe).toHaveBeenCalledTimes(1)
    const handler = mockSubscribe.mock.calls[0][0] as () => void
    handler()
    await wrapper.vm.$nextTick()

    expect(mockClearToken).toHaveBeenCalledTimes(1)
    expect(vm.authenticated).toBe(false)
    // 回认证区并提示过期（行内文案，非 toast）
    expect(wrapper.text()).toContain('维护认证')
    expect(wrapper.text()).toContain('维护会话已过期，请重新认证')
    expect(messageSpy).not.toHaveBeenCalled()
  })
})
