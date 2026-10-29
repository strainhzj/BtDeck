/**
 * 维护恢复页回归（database-migration-ui W4-3）。
 *
 * 保护点：
 * 1. 未认证只渲染认证区（用户名/密码/可选 twofa），不发起状态请求、不启动轮询；
 * 2. 认证成功进入状态区：粗粒度状态徽标（人类可读文案）+ 迁移状态/就绪面拉取；
 * 3. NEEDS_CREDENTIALS 呈现凭据重输表单，提交载荷为 snake_case
 *    attempt_id/password/target（经维护通道 POST /database/migration/credentials）；
 * 4. 进度条显示 done/total，100% 不掩盖未激活：phase 徽标常显；
 * 5. READY_TO_SWITCH 只读等待提示，本页不发起任何 switch 提交（无 POST）；
 * 6. restartPending 显示「配置已提交，需手动重启」提示文案；
 * 7. 维护会话过期（subscribeAuthExpired 回调）：回登录区、清内存 token、
 *    不弹全局 toast、不触碰普通会话；
 * 8. beforeDestroy 清理 10s 轮询定时器并退订 auth expired 订阅。
 */

import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import VueI18n from 'vue-i18n'
import i18n from '@/i18n'

import MaintenancePage from '@/views/maintenance/index.vue'
import {
  maintenanceLogin,
  maintenanceRequest,
  getMaintenanceStatus,
  getMaintenanceToken,
  clearMaintenanceToken,
  subscribeAuthExpired
} from '@/utils/maintenance-client'
import type { MigrationStatusData, ReadinessData } from '@/api/database'

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
  credForm: {
    host: string
    port: number
    user: string
    password: string
    database: string
    schema: string
    sslmode: string
    sslRootCert: string
  }
  pollTimer: number | null
  login: () => Promise<void>
  submitCredentials: () => Promise<void>
  refreshAll: () => Promise<void>
}

// ---------------------------------------------------------------------------
// 夹具
// ---------------------------------------------------------------------------

/** /maintenance/status 数据体（W4-1 契约：state/attemptId/epoch/extra） */
function makeStatus(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { state: 'FROZEN', attemptId: 'att-100', epoch: 'ep-7', extra: {}, ...overrides }
}

function makeMigration(overrides: Partial<MigrationStatusData> = {}): MigrationStatusData {
  return {
    attemptId: 'att-100',
    phase: 'importing',
    epoch: 'ep-7',
    stateVersion: 2,
    commitPhase: null,
    workerGeneration: 1,
    needsCredentials: false,
    restartPending: false,
    detail: { progress: { phase: 'importing', done: 4, total: 8 } },
    ...overrides
  }
}

function makeReadiness(overrides: Partial<ReadinessData> = {}): ReadinessData {
  return {
    attemptId: 'att-100',
    phase: 'importing',
    readyToSwitch: false,
    needsCredentials: false,
    ...overrides
  }
}

let statusFixture: Record<string, unknown> = makeStatus()
let migrationFixture: MigrationStatusData = makeMigration()
let readinessFixture: ReadinessData = makeReadiness()
const credentialsResultFixture: MigrationStatusData = makeMigration({
  phase: 'importing',
  needsCredentials: false
})

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

/** 刷净微任务队列（mounted/login/refreshAll 内的 await 链） */
async function flushPromises(): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, 0))
}

/** 挂载并等待 mounted 内的首次刷新完成 */
async function mountPage(): Promise<Wrapper<Vue>> {
  const wrapper = mount(MaintenancePage, { localVue, i18n })
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
  mockGetStatus.mockImplementation(async() => statusFixture as Record<string, unknown> as never)
  mockRequest.mockImplementation(async(method: string, url: string) => {
    if (url === '/database/migration/status') return migrationFixture as never
    if (url === '/database/target-readiness') return readinessFixture as never
    if (url === '/database/migration/credentials') return credentialsResultFixture as never
    throw new Error(`unexpected request: ${method} ${url}`)
  })
})

afterEach(() => {
  if (activeWrapper) {
    activeWrapper.destroy()
    activeWrapper = null
  }
})

describe('MaintenancePage', () => {
  it('未认证：仅渲染认证区（用户名/密码/可选 twofa），不拉状态、不启动轮询', async() => {
    const setIntervalSpy = jest.spyOn(window, 'setInterval')
    const wrapper = await mountPage()
    activeWrapper = wrapper

    expect(wrapper.text()).toContain('维护认证')
    expect(wrapper.text()).toContain('用户名')
    expect(wrapper.text()).toContain('两步验证码（可选）')
    // 状态区/迁移区不渲染
    expect(wrapper.text()).not.toContain('维护状态')
    expect(wrapper.text()).not.toContain('迁移进度')
    // 不发起任何状态请求，不创建轮询定时器
    expect(mockGetStatus).not.toHaveBeenCalled()
    expect(mockRequest).not.toHaveBeenCalled()
    expect(setIntervalSpy).not.toHaveBeenCalled()
  })

  it('认证成功后进入状态区：粗粒度徽标文案 + 迁移状态/就绪面拉取', async() => {
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
    // 粗粒度状态 FROZEN → 人类可读文案 + 迁移单号锚点
    expect(wrapper.text()).toContain('已冻结')
    expect(wrapper.text()).toContain('att-100')
    // 迁移面经维护通道直调（信封 data 手动映射）
    expect(mockGetStatus).toHaveBeenCalled()
    expect(mockRequest).toHaveBeenCalledWith('get', '/database/migration/status')
    expect(mockRequest).toHaveBeenCalledWith('get', '/database/target-readiness')
  })

  it('NEEDS_CREDENTIALS：凭据重输表单可见，提交 snake_case attempt_id/password/target', async() => {
    mockGetToken.mockReturnValue('mtk-live')
    statusFixture = makeStatus({ state: 'NEEDS_CREDENTIALS' })
    migrationFixture = makeMigration({ phase: 'needs_credentials', needsCredentials: true })
    readinessFixture = makeReadiness({ phase: 'needs_credentials', needsCredentials: true })

    const wrapper = await mountPage()
    activeWrapper = wrapper
    const vm = wrapper.vm as unknown as PageVm

    expect(wrapper.text()).toContain('需要重新输入凭据')
    expect(wrapper.text()).toContain('目标主机')
    expect(wrapper.text()).toContain('提交凭据')

    vm.credForm.host = 'pg.local'
    vm.credForm.port = 5433
    vm.credForm.user = 'btdeck'
    vm.credForm.password = 'secret'
    vm.credForm.database = 'btdeck'
    vm.credForm.schema = ''
    vm.credForm.sslmode = 'prefer'
    await vm.submitCredentials()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const credCall = mockRequest.mock.calls.find(call => call[1] === '/database/migration/credentials')
    expect(credCall).toBeDefined()
    expect(credCall?.[0]).toBe('post')
    expect(credCall?.[2]).toEqual({
      attempt_id: 'att-100',
      password: 'secret',
      target: expect.objectContaining({
        host: 'pg.local',
        port: 5433,
        user: 'btdeck',
        database: 'btdeck',
        schema: 'public',
        sslmode: 'prefer',
        ssl_root_cert: null
      })
    })
    // 提交成功回执文案
    expect(wrapper.text()).toContain('凭据已受理')
  })

  it('进度 100% 不掩盖未激活：phase 徽标常显（8/8 与 4/8 两档）', async() => {
    mockGetToken.mockReturnValue('mtk-live')
    migrationFixture = makeMigration({
      phase: 'verifying',
      detail: { progress: { phase: 'verify', done: 8, total: 8 } }
    })
    readinessFixture = makeReadiness({ phase: 'verifying' })

    const wrapper = await mountPage()
    activeWrapper = wrapper
    const vm = wrapper.vm as unknown as PageVm

    // 100% 进度下 phase 徽标仍常显（校验中），done/total 明示
    const progress = wrapper.findAllComponents({ name: 'ElProgress' }).at(0)
    expect(progress.props('percentage')).toBe(100)
    expect(wrapper.text()).toContain('8 / 8')
    expect(wrapper.text()).toContain('校验中')

    // 中途进度 50% 同样保留 phase 徽标
    migrationFixture = makeMigration({
      phase: 'importing',
      detail: { progress: { phase: 'import', done: 4, total: 8 } }
    })
    await vm.refreshAll()
    await wrapper.vm.$nextTick()
    expect(wrapper.findAllComponents({ name: 'ElProgress' }).at(0).props('percentage')).toBe(50)
    expect(wrapper.text()).toContain('4 / 8')
    expect(wrapper.text()).toContain('导入中')
  })

  it('READY_TO_SWITCH：只读等待提示，不发起任何 switch 提交（仅 GET）', async() => {
    mockGetToken.mockReturnValue('mtk-live')
    migrationFixture = makeMigration({ phase: 'ready_to_switch', detail: undefined })
    readinessFixture = makeReadiness({ phase: 'ready_to_switch', readyToSwitch: true })

    const wrapper = await mountPage()
    activeWrapper = wrapper

    expect(wrapper.text()).toContain('等待提交 / 等待重启')
    expect(wrapper.text()).toContain('不在本页执行')
    // 就绪徽标
    expect(wrapper.text()).toContain('就绪')
    // 本页只读 + 凭据重输，不出现本地 switch 执行
    expect(mockRequest.mock.calls.every(call => call[0] === 'get')).toBe(true)
  })

  it('restartPending：显示「配置已提交，需手动重启」提示文案', async() => {
    mockGetToken.mockReturnValue('mtk-live')
    migrationFixture = makeMigration({ phase: 'committed', restartPending: true })

    const wrapper = await mountPage()
    activeWrapper = wrapper

    expect(wrapper.text()).toContain('待重启生效')
    expect(wrapper.text()).toContain('配置已提交，需手动重启服务后生效')
  })

  it('维护会话过期：订阅回调回登录区、清内存 token、不弹全局 toast', async() => {
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
    // 回登录区并提示过期（行内文案，非 toast）
    expect(wrapper.text()).toContain('维护认证')
    expect(wrapper.text()).toContain('维护会话已过期，请重新认证')
    expect(messageSpy).not.toHaveBeenCalled()
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

  it('未认证 mount 时已订阅 auth expired（认证前置，早于任何请求）', async() => {
    const wrapper = await mountPage()
    activeWrapper = wrapper

    expect(mockSubscribe).toHaveBeenCalledTimes(1)
    expect(mockGetStatus).not.toHaveBeenCalled()
  })
})
