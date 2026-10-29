/**
 * 数据库面板平台门控回归（database-migration-ui W4-4；§9 三层拒的页面层）。
 *
 * 保护点：
 * 1. 平台矩阵 db_migration 非 supported → PG 表单（el-form disabled 传播内嵌
 *    控件）/ 测试连接 / A 入口禁用 + 提示「当前平台不支持数据库迁移」；
 *    runTestConnection / previewHandoff 直调同样被拦（不发任何请求）；
 * 2. 矩阵 db_migration=supported → 表单/按钮可用、无门控提示（探测畅通）；
 * 3. 矩阵未加载（缓存空，非 FILESYSTEM 键默认 supported）不误伤桌面默认态
 *    （W4-2 既有行为：无矩阵环境表单可用）；
 * 4. demo 模式 → 同样只读 + 样例数据提示（矩阵 supported 仍禁用）；
 * 5. Android 伴侣 WebView（UA 注入 BtDeckCompanion 标记）→ 叠加禁用 +
 *    「Android 本机不支持 PostgreSQL 数据源」提示（矩阵 supported 仍禁用）。
 */

import { createLocalVue, mount, Wrapper } from '@vue/test-utils'
import ElementUI from 'element-ui'
import VueI18n from 'vue-i18n'
import i18n from '@/i18n'

import DatabasePanel from '@/views/settings/components/DatabasePanel.vue'
import {
  getDatabaseStatus,
  getMigrationStatus,
  testConnection,
  clearActivation,
  PgMasked,
  TestConnectionData
} from '@/api/database'
import {
  PlatformCapabilitiesData,
  resetPlatformCapabilityCache,
  setPlatformCapabilityCacheForTesting
} from '@/api/platform-capabilities'

jest.mock('@/api/database', () => ({
  getDatabaseStatus: jest.fn(),
  getMigrationStatus: jest.fn(),
  testConnection: jest.fn(),
  clearActivation: jest.fn()
}))

/** demo 门直控真实开关：isDemoMode 读 process.env.VUE_APP_DEMO_MODE，
 * 测试内注入即可翻转，无需 mock 模块（避免 mock 工厂闭包 TDZ/no-var） */
const SAVED_DEMO_ENV: string | undefined = process.env.VUE_APP_DEMO_MODE

const mockGetStatus = getDatabaseStatus as jest.MockedFunction<typeof getDatabaseStatus>
const mockGetMigrationStatus = getMigrationStatus as jest.MockedFunction<typeof getMigrationStatus>
const mockTestConnection = testConnection as jest.MockedFunction<typeof testConnection>
const mockClearActivation = clearActivation as jest.MockedFunction<typeof clearActivation>

const localVue = createLocalVue()
localVue.use(ElementUI)
localVue.use(VueI18n)

/** class 组件的 private 成员运行时即实例成员，经接口重声明访问 */
interface PanelVm {
  pgForm: {
    host: string
    port: number
    user: string
    password: string
    database: string
    schema: string
    sslmode: string
    sslRootCert: string
    poolSize: number
    maxOverflow: number
    poolTimeout: number
  }
  runTestConnection: () => Promise<void>
  previewHandoff: () => Promise<void>
}

const PG_MASKED: PgMasked = {
  host: 'db.local',
  port: 5432,
  user: 'btdeck',
  database: 'btdeck',
  schema: 'public',
  sslmode: 'prefer',
  sslRootCert: null,
  poolSize: 10,
  maxOverflow: 20,
  poolTimeout: 30
}

function makeStatusResponse() {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      effective: {
        source: 'active',
        dialect: 'postgresql',
        sqlitePath: null,
        postgresql: PG_MASKED,
        generation: null,
        expectedDatabaseId: 'db-id-1',
        receiptAttemptId: 'att-receipt-1'
      },
      control: {
        deploymentId: null,
        generation: 'gen-7',
        restartPending: false
      },
      hosting: {
        hosting: 'docker',
        optIn: true,
        pid1Self: false,
        autoRestartCapable: true,
        hint: null
      }
    }
  } as unknown as Awaited<ReturnType<typeof getDatabaseStatus>>
}

function makeMigrationStatusResponse() {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      attemptId: null,
      phase: 'idle',
      epoch: 'epoch-1',
      stateVersion: 1,
      commitPhase: null,
      workerGeneration: 0,
      needsCredentials: false,
      restartPending: false
    }
  } as unknown as Awaited<ReturnType<typeof getMigrationStatus>>
}

/** 注入能力矩阵（null = 清空缓存模拟未加载） */
function setMatrix(level: 'supported' | 'unsupported' | 'degraded' | null): void {
  if (level === null) {
    resetPlatformCapabilityCache()
    return
  }
  const data: PlatformCapabilitiesData = {
    schemaVersion: 2,
    platform: level === 'supported' ? 'desktop' : 'android-server',
    capabilities: { db_migration: { label: '数据库迁移', level } },
    degradedCount: level === 'degraded' ? 1 : 0,
    unsupportedCount: level === 'unsupported' ? 1 : 0
  }
  setPlatformCapabilityCacheForTesting(data)
}

const REAL_UA = navigator.userAgent

/** 切换伴侣 App WebView UA（WebViewActivity 注入 BtDeckCompanion 标记） */
function setCompanionUA(on: boolean): void {
  Object.defineProperty(navigator, 'userAgent', {
    value: on ? 'Mozilla/5.0 (Linux; Android 14) BtDeckCompanion/1.0' : REAL_UA,
    configurable: true
  })
}

/** 刷净微任务队列（mounted/load 内的 await 链） */
async function flushPromises(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

/** 按文案查找按钮，缺失即抛错（避免非空断言 lint 警告） */
function findButton(wrapper: Wrapper<Vue>, text: string): Wrapper<Vue> {
  const btn = wrapper.findAllComponents({ name: 'ElButton' }).wrappers.find(b => b.text().includes(text))
  if (!btn) throw new Error(`未找到按钮: ${text}`)
  return btn
}

/** 挂载并等待 mounted 内首次 load 完成 */
async function mountPanel(): Promise<Wrapper<Vue>> {
  mockGetStatus.mockResolvedValue(makeStatusResponse())
  mockGetMigrationStatus.mockResolvedValue(makeMigrationStatusResponse())
  const wrapper = mount(DatabasePanel, { localVue, i18n })
  await flushPromises()
  await wrapper.vm.$nextTick()
  return wrapper
}

/** 填齐探测必填项（供直调 runTestConnection 用） */
function fillProbeForm(vm: PanelVm): void {
  vm.pgForm.host = 'db.local'
  vm.pgForm.user = 'btdeck'
  vm.pgForm.password = 'pg-secret-value'
  vm.pgForm.database = 'btdeck'
}

beforeEach(() => {
  jest.clearAllMocks()
  jest.restoreAllMocks()
  jest.useRealTimers()
  process.env.VUE_APP_DEMO_MODE = SAVED_DEMO_ENV
  setCompanionUA(false)
  resetPlatformCapabilityCache()
})

afterEach(() => {
  process.env.VUE_APP_DEMO_MODE = SAVED_DEMO_ENV
  setCompanionUA(false)
  resetPlatformCapabilityCache()
})

describe('DatabasePanel 平台门控（W4-4）', () => {
  it('矩阵 db_migration=unsupported：表单/测试连接/A 入口禁用并提示，方法直调被拦', async() => {
    setMatrix('unsupported')
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm

    // 提示文案（i18n）
    expect(wrapper.text()).toContain('当前平台不支持数据库迁移')

    // PG 表单整体只读（el-form disabled 传播内嵌控件）
    const form = wrapper.findAllComponents({ name: 'ElForm' }).at(0)
    expect(form.props('disabled')).toBe(true)
    expect(wrapper.find('.db-form input').attributes('disabled')).toBeDefined()

    // 测试连接 / A 入口按钮禁用
    expect(findButton(wrapper, '测试连接').attributes('disabled')).toBeDefined()
    expect(findButton(wrapper, 'env 交接（仅预览）').attributes('disabled')).toBeDefined()

    // 方法层防御：直调也不发任何探测/预览请求
    fillProbeForm(vm)
    await vm.runTestConnection()
    await flushPromises()
    expect(mockTestConnection).not.toHaveBeenCalled()

    await vm.previewHandoff()
    await flushPromises()
    expect(mockClearActivation).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('矩阵 db_migration=supported：表单/按钮可用、无门控提示（探测畅通）', async() => {
    setMatrix('supported')
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm

    expect(wrapper.text()).not.toContain('当前平台不支持数据库迁移')
    expect(wrapper.text()).not.toContain('样例数据')
    expect(wrapper.text()).not.toContain('Android 本机不支持')

    const form = wrapper.findAllComponents({ name: 'ElForm' }).at(0)
    expect(form.props('disabled')).toBe(false)
    expect(findButton(wrapper, '测试连接').attributes('disabled')).toBeUndefined()
    expect(findButton(wrapper, 'env 交接（仅预览）').attributes('disabled')).toBeUndefined()

    // 探测路径畅通：必填齐全时直调发出探测请求
    fillProbeForm(vm)
    const probe: TestConnectionData = {
      dialect: 'postgresql',
      reachable: true,
      versionOk: true,
      targetEmpty: true
    }
    mockTestConnection.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200', data: probe
    } as unknown as Awaited<ReturnType<typeof testConnection>>)
    await vm.runTestConnection()
    await flushPromises()
    expect(mockTestConnection).toHaveBeenCalledTimes(1)
    wrapper.destroy()
  })

  it('矩阵未加载（缓存空）不误伤桌面默认态：db_migration 非 FILESYSTEM 键默认 supported', async() => {
    setMatrix(null)
    const wrapper = await mountPanel()

    const form = wrapper.findAllComponents({ name: 'ElForm' }).at(0)
    expect(form.props('disabled')).toBe(false)
    expect(findButton(wrapper, '测试连接').attributes('disabled')).toBeUndefined()
    expect(findButton(wrapper, 'env 交接（仅预览）').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).not.toContain('当前平台不支持数据库迁移')
    wrapper.destroy()
  })

  it('demo 模式：同样只读 + 样例数据提示（矩阵 supported 仍禁用）', async() => {
    process.env.VUE_APP_DEMO_MODE = 'true'
    setMatrix('supported')
    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('样例数据')
    expect(wrapper.text()).not.toContain('当前平台不支持数据库迁移')
    const form = wrapper.findAllComponents({ name: 'ElForm' }).at(0)
    expect(form.props('disabled')).toBe(true)
    expect(findButton(wrapper, '测试连接').attributes('disabled')).toBeDefined()
    expect(findButton(wrapper, 'env 交接（仅预览）').attributes('disabled')).toBeDefined()
    wrapper.destroy()
  })

  it('Android 伴侣 WebView：叠加禁用 + Android 提示（矩阵 supported 仍禁用）', async() => {
    setMatrix('supported')
    setCompanionUA(true)
    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('Android 本机不支持 PostgreSQL 数据源')
    expect(wrapper.text()).not.toContain('当前平台不支持数据库迁移')
    const form = wrapper.findAllComponents({ name: 'ElForm' }).at(0)
    expect(form.props('disabled')).toBe(true)
    expect(findButton(wrapper, '测试连接').attributes('disabled')).toBeDefined()
    expect(findButton(wrapper, 'env 交接（仅预览）').attributes('disabled')).toBeDefined()
    wrapper.destroy()
  })
})
