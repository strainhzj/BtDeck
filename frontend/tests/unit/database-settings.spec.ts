/**
 * 数据库设置面板回归（database-migration-ui W4-2）。
 *
 * 保护点：
 * 1. 状态卡渲染「有效」库脱敏摘要：active/env 徽标、PG host:port/database、
 *    sslmode、池参数、generation/restartPending 锚点、托管能力——状态卡内
 *    不出现任何密码输入/凭据（脱敏视图无 password 字段）；
 * 2. PG 目标表单 sslmode 全档下拉（disable/allow/prefer/require/verify-ca/
 *    verify-full，后端 sslmode 契约），verify-ca/full 档 CA 路径必填校验联动，
 *    探测载荷映射为 snake_case PgFormInput；
 * 3. 测试连接三态结果（reachable/versionOk/targetEmpty + 版本与协商 TLS）；
 * 4. A/B 双入口均保留：B start 仅入口暴露（disabled 当 restartPending/attempt
 *    进行中，普通态只提示去维护流程）；A env 交接仅 clearActivation 预览
 *    （计划弹窗展示 steps/confirmToken，确认不执行任何动作）；
 * 5. restartPending 时 10s 轮询启动、状态恢复即停、beforeDestroy 清理定时器。
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
  MigrationCasPayload,
  PgMasked,
  TestConnectionData
} from '@/api/database'
import { ApiError } from '@/types/api'

jest.mock('@/api/database', () => ({
  getDatabaseStatus: jest.fn(),
  getMigrationStatus: jest.fn(),
  testConnection: jest.fn(),
  clearActivation: jest.fn()
}))

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
  restartPending: boolean
  attemptActive: boolean
}

const PG_MASKED: PgMasked = {
  host: 'db.local',
  port: 5432,
  user: 'btdeck',
  database: 'btdeck',
  schema: 'public',
  sslmode: 'verify-full',
  sslRootCert: '/etc/ssl/ca.pem',
  poolSize: 10,
  maxOverflow: 20,
  poolTimeout: 30
}

function makeStatusResponse(opts: {
  source?: string
  dialect?: string
  sqlitePath?: string | null
  pg?: PgMasked | null
  generation?: string | null
  restartPending?: boolean
  autoRestartCapable?: boolean
} = {}) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      effective: {
        source: opts.source ?? 'active',
        dialect: opts.dialect ?? 'postgresql',
        sqlitePath: opts.sqlitePath ?? null,
        postgresql: opts.pg ?? PG_MASKED,
        generation: null,
        expectedDatabaseId: 'db-id-1',
        receiptAttemptId: 'att-receipt-1'
      },
      control: {
        deploymentId: null,
        generation: opts.generation !== undefined ? opts.generation : 'gen-7',
        restartPending: opts.restartPending ?? false
      },
      hosting: {
        hosting: 'docker',
        optIn: true,
        pid1Self: false,
        autoRestartCapable: opts.autoRestartCapable ?? true,
        hint: opts.autoRestartCapable === false ? '托管能力提示原文' : null
      }
    }
  } as unknown as Awaited<ReturnType<typeof getDatabaseStatus>>
}

function makeMigrationStatusResponse(opts: {
  attemptId?: string | null
  phase?: string
  restartPending?: boolean
} = {}) {
  return {
    status: 'success',
    msg: 'ok',
    code: '200',
    data: {
      attemptId: opts.attemptId ?? null,
      phase: opts.phase ?? 'idle',
      epoch: 'epoch-1',
      stateVersion: 1,
      commitPhase: null,
      workerGeneration: 0,
      needsCredentials: false,
      restartPending: opts.restartPending ?? false
    }
  } as unknown as Awaited<ReturnType<typeof getMigrationStatus>>
}

function makeApiError(code: string): ApiError {
  return new ApiError('冲突', { code, httpStatus: Number(code) })
}

/** 刷净微任务队列（mounted/load 内的 await 链；fake timers 下同样可用） */
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

/** 挂载并等待 mounted 内首次 load 完成（默认 PG active 态，可传覆盖） */
async function mountPanel(
  statusResponse = makeStatusResponse(),
  migrationResponse = makeMigrationStatusResponse()
): Promise<Wrapper<Vue>> {
  mockGetStatus.mockResolvedValue(statusResponse)
  mockGetMigrationStatus.mockResolvedValue(migrationResponse)
  const wrapper = mount(DatabasePanel, { localVue, i18n })
  await flushPromises()
  await wrapper.vm.$nextTick()
  return wrapper
}

beforeEach(() => {
  jest.clearAllMocks()
  jest.restoreAllMocks()
  jest.useRealTimers()
})

describe('DatabasePanel', () => {
  it('状态卡渲染有效库脱敏摘要（来源/方言/PG 目标/sslmode/池/锚点/托管），无任何密码出现', async() => {
    const wrapper = await mountPanel()
    expect(mockGetStatus).toHaveBeenCalledTimes(1)

    const card = wrapper.findAll('.db-card').at(0)
    const text = card.text()
    // 来源徽标 + 方言 + PG 脱敏摘要（host:port/database、sslmode、池参数）
    expect(text).toContain('受管（应用管理）')
    expect(text).toContain('postgresql')
    expect(text).toContain('db.local:5432/btdeck')
    expect(text).toContain('verify-full')
    expect(text).toContain('池 10 · 溢出 20 · 获取超时 30 秒')
    // 控制锚点 + 托管能力
    expect(text).toContain('gen-7')
    expect(text).toContain('已生效')
    expect(text).toContain('docker')
    expect(text).toContain('支持托管重启')
    // 脱敏红线：状态卡不出现密码输入与密码文案（凭据永不下发）
    expect(card.findAll('input').length).toBe(0)
    expect(text).not.toContain('密码')
    expect(text).not.toContain('password')
  })

  it('env 来源显示环境变量徽标；SQLite 方言显示最终路径', async() => {
    const wrapper = await mountPanel(makeStatusResponse({
      source: 'env',
      dialect: 'sqlite',
      sqlitePath: '/data/btdeck/btdeck.db',
      pg: null,
      generation: null
    }))
    const text = wrapper.findAll('.db-card').at(0).text()
    expect(text).toContain('环境变量')
    expect(text).toContain('/data/btdeck/btdeck.db')
    // 无受管控制锚点：generation 行不渲染，restartPending 按已生效展示
    expect(text).not.toContain('gen-7')
    expect(text).toContain('已生效')
  })

  it('托管能力不足时展示需手动重启与后端 hint 原文', async() => {
    const wrapper = await mountPanel(makeStatusResponse({ autoRestartCapable: false }))
    const text = wrapper.findAll('.db-card').at(0).text()
    expect(text).toContain('需手动重启')
    expect(text).toContain('托管能力提示原文')
  })

  it('sslmode 下拉为后端契约全档（disable/allow/prefer/require/verify-ca/verify-full）', async() => {
    const wrapper = await mountPanel()
    const values = wrapper.findAllComponents({ name: 'ElOption' }).wrappers.map(opt => opt.props('value'))
    expect(values.slice().sort()).toEqual(['allow', 'disable', 'prefer', 'require', 'verify-ca', 'verify-full'])
    // 默认 prefer
    const vm = wrapper.vm as unknown as PanelVm
    expect(vm.pgForm.sslmode).toBe('prefer')
  })

  it('verify-ca/verify-full 档 CA 路径必填：非 verify 档不要求，校验失败给出专属文案', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    const caItem = () => wrapper.findAllComponents({ name: 'ElFormItem' }).wrappers.find(w => w.props('prop') === 'sslRootCert')

    // 默认 prefer：CA 非必填
    expect(caItem()?.classes()).not.toContain('is-required')

    // 切到 verify-ca：必填标记出现，空值校验失败并渲染专属错误文案
    const sslSelect = wrapper.findAllComponents({ name: 'ElSelect' }).at(0)
    sslSelect.vm.$emit('input', 'verify-ca')
    await wrapper.vm.$nextTick()
    expect(caItem()?.classes()).toContain('is-required')

    mockTestConnection.mockClear()
    await vm.runTestConnection()
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(mockTestConnection).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('verify-ca / verify-full 模式必须填写 CA 证书路径')

    // 回到 prefer：必填解除
    sslSelect.vm.$emit('input', 'prefer')
    await wrapper.vm.$nextTick()
    expect(caItem()?.classes()).not.toContain('is-required')
  })

  it('测试连接：表单必填齐全时携带 snake_case 契约载荷并渲染三态结果', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    vm.pgForm.host = 'db.local'
    vm.pgForm.user = 'btdeck'
    vm.pgForm.password = 'pg-secret-value'
    vm.pgForm.database = 'btdeck'
    vm.pgForm.sslmode = 'verify-ca'
    vm.pgForm.sslRootCert = '/etc/ssl/ca.pem'
    await wrapper.vm.$nextTick()

    const probe: TestConnectionData = {
      dialect: 'postgresql',
      reachable: true,
      serverVersion: '16.4',
      versionOk: true,
      targetEmpty: true,
      sslmode: 'verify-ca'
    }
    mockTestConnection.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200', data: probe
    } as unknown as Awaited<ReturnType<typeof testConnection>>)

    await vm.runTestConnection()
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(mockTestConnection).toHaveBeenCalledTimes(1)
    const payload = mockTestConnection.mock.calls[0][0]
    expect(payload.dialect).toBe('postgresql')
    expect(payload.postgresql).toMatchObject({
      host: 'db.local',
      port: 5432,
      user: 'btdeck',
      password: 'pg-secret-value',
      database: 'btdeck',
      schema: 'public',
      sslmode: 'verify-ca',
      ssl_root_cert: '/etc/ssl/ca.pem',
      pool_size: 10,
      max_overflow: 20,
      pool_timeout: 30
    })
    // 三态 + 版本 + 协商 TLS
    expect(wrapper.text()).toContain('可连通')
    expect(wrapper.text()).toContain('服务器版本：16.4')
    expect(wrapper.text()).toContain('空库（可迁移）')
    expect(wrapper.text()).toContain('协商 TLS：verify-ca')
  })

  it('测试连接不可达：仅展示不可连通，版本/目标行不渲染', async() => {
    const wrapper = await mountPanel()
    const vm = wrapper.vm as unknown as PanelVm
    vm.pgForm.host = 'db.local'
    vm.pgForm.user = 'btdeck'
    vm.pgForm.password = 'pg-secret-value'
    vm.pgForm.database = 'btdeck'
    await wrapper.vm.$nextTick()

    mockTestConnection.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200',
      data: { dialect: 'postgresql', reachable: false }
    } as unknown as Awaited<ReturnType<typeof testConnection>>)

    await vm.runTestConnection()
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('不可连通')
    expect(wrapper.text()).not.toContain('服务器版本')
    expect(wrapper.text()).not.toContain('空库（可迁移）')
  })

  it('B 入口 start 仅指引：普通态点击提示走维护流程，不提交任何迁移', async() => {
    const wrapper = await mountPanel()
    const infoSpy = jest.spyOn(wrapper.vm.$message, 'info').mockImplementation((() => ({})) as unknown as () => never)

    await findButton(wrapper, '发起迁移（入口指引）').vm.$emit('click')
    await flushPromises()

    expect(infoSpy).toHaveBeenCalledWith(expect.stringContaining('维护流程'))
    expect(mockTestConnection).not.toHaveBeenCalled()
    expect(mockClearActivation).not.toHaveBeenCalled()
  })

  it('B 入口 start 在 restartPending 或迁移进行中时禁用并展示原因', async() => {
    // restartPending：提交待重启生效，入口禁用
    const wrapper = await mountPanel(makeStatusResponse({ restartPending: true }))
    let startButton = findButton(wrapper, '发起迁移（入口指引）')
    expect(startButton.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('存在待重启生效的提交')
    wrapper.destroy()

    // attempt 进行中（importing）：单飞行被占，入口禁用
    const wrapper2 = await mountPanel(
      makeStatusResponse(),
      makeMigrationStatusResponse({ attemptId: 'att-1', phase: 'importing' })
    )
    const vm = wrapper2.vm as unknown as PanelVm
    expect(vm.restartPending).toBe(false)
    expect(vm.attemptActive).toBe(true)
    startButton = findButton(wrapper2, '发起迁移（入口指引）')
    expect(startButton.attributes('disabled')).toBeDefined()
    expect(wrapper2.text()).toContain('已有迁移在进行中')
    wrapper2.destroy()
  })

  it('A 入口 env 交接：clearActivation 仅预览，弹窗展示 steps/confirmToken，确认不执行', async() => {
    const msgboxMock = jest.fn((..._args: unknown[]) => Promise.resolve({ action: 'confirm' }))
    const wrapper = mount(DatabasePanel, {
      localVue,
      i18n,
      mocks: { $msgbox: msgboxMock }
    })
    await flushPromises()
    await wrapper.vm.$nextTick()
    const infoSpy = jest.spyOn(wrapper.vm.$message, 'info').mockImplementation((() => ({})) as unknown as () => never)

    const plan = {
      kind: 'HANDOFF_SAME_DB',
      handoffAttemptId: 'handoff/uuid-1',
      steps: [
        '步骤一：env 指向同库',
        '步骤二：维护态创建 HANDOFF_SAME_DB attempt',
        '步骤三：重启后 CAS 提交 ACK'
      ],
      confirmToken: 'handoff:uuid-1:dbid1234'
    }
    mockClearActivation.mockResolvedValue({
      status: 'success', msg: 'ok', code: '200', data: plan
    } as unknown as Awaited<ReturnType<typeof clearActivation>>)

    await findButton(wrapper, 'env 交接（仅预览）').vm.$emit('click')
    await flushPromises()

    // 预览载荷携带当前控制锚点（receipt attempt/generation；后端预览不校验 CAS 值）
    expect(mockClearActivation).toHaveBeenCalledTimes(1)
    const payload = mockClearActivation.mock.calls[0][0] as MigrationCasPayload
    expect(payload.attempt_id).toBe('att-receipt-1')
    expect(payload.epoch).toBe('gen-7')
    expect(payload.state_version).toBe(1)

    // 计划进入确认弹窗（steps/confirmToken 已组入 VNode；仅确认，不执行）
    expect(msgboxMock).toHaveBeenCalledTimes(1)
    const options = msgboxMock.mock.calls[0][0] as { title?: string, confirmButtonText?: string, message?: unknown }
    expect(options.title).toContain('预览')
    expect(options.confirmButtonText).toContain('预览')

    // 确认后仅回执「未执行」，无任何后续 API 调用
    await flushPromises()
    expect(infoSpy).toHaveBeenCalledWith('本次仅为预览，未执行交接')
    expect(mockClearActivation).toHaveBeenCalledTimes(1)
    expect(mockTestConnection).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('A 入口预览 409（无受管 active/env 异库）提示冲突且不弹窗', async() => {
    const msgboxMock = jest.fn((..._args: unknown[]) => Promise.resolve({ action: 'confirm' }))
    const wrapper = mount(DatabasePanel, { localVue, i18n, mocks: { $msgbox: msgboxMock } })
    await flushPromises()
    await wrapper.vm.$nextTick()

    const warningSpy = jest.spyOn(wrapper.vm.$message, 'warning').mockImplementation((() => ({})) as unknown as () => never)
    mockClearActivation.mockRejectedValue(makeApiError('409'))

    await findButton(wrapper, 'env 交接（仅预览）').vm.$emit('click')
    await flushPromises()

    expect(warningSpy).toHaveBeenCalledWith(expect.stringContaining('同库交接'))
    expect(msgboxMock).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('加载失败显示占位与重试，重试成功恢复', async() => {
    mockGetStatus.mockRejectedValueOnce(makeApiError('500'))
    mockGetMigrationStatus.mockResolvedValue(makeMigrationStatusResponse())
    const wrapper = mount(DatabasePanel, { localVue, i18n })
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('数据库状态加载失败')

    mockGetStatus.mockResolvedValue(makeStatusResponse())
    await findButton(wrapper, '重试').vm.$emit('click')
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('db.local:5432/btdeck')
    wrapper.destroy()
  })

  // ====== restartPending 轮询（10s）与生命周期清理 ======

  it('restartPending 时启动 10s 轮询；beforeDestroy 清理定时器', async() => {
    jest.useFakeTimers()
    mockGetStatus.mockResolvedValue(makeStatusResponse({ restartPending: true }))
    mockGetMigrationStatus.mockResolvedValue(makeMigrationStatusResponse())
    const wrapper = mount(DatabasePanel, { localVue, i18n })
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(mockGetStatus).toHaveBeenCalledTimes(1)

    jest.advanceTimersByTime(10000)
    await flushPromises()
    expect(mockGetStatus).toHaveBeenCalledTimes(2)

    jest.advanceTimersByTime(10000)
    await flushPromises()
    expect(mockGetStatus).toHaveBeenCalledTimes(3)

    // 销毁后定时器不再触发
    wrapper.destroy()
    jest.advanceTimersByTime(30000)
    await flushPromises()
    expect(mockGetStatus).toHaveBeenCalledTimes(3)
  })

  it('restartPending 恢复为 false 后轮询自动停止', async() => {
    jest.useFakeTimers()
    mockGetStatus.mockResolvedValueOnce(makeStatusResponse({ restartPending: true }))
    mockGetMigrationStatus.mockResolvedValue(makeMigrationStatusResponse())
    const wrapper = mount(DatabasePanel, { localVue, i18n })
    await flushPromises()
    await wrapper.vm.$nextTick()

    // 下一跳恢复已生效 → 定时器清除，后续时间推进不再请求
    mockGetStatus.mockResolvedValue(makeStatusResponse({ restartPending: false }))
    jest.advanceTimersByTime(10000)
    await flushPromises()
    await wrapper.vm.$nextTick()
    expect(mockGetStatus).toHaveBeenCalledTimes(2)

    jest.advanceTimersByTime(30000)
    await flushPromises()
    expect(mockGetStatus).toHaveBeenCalledTimes(2)
    wrapper.destroy()
  })

  it('无 restartPending 时不启动轮询', async() => {
    jest.useFakeTimers()
    mockGetStatus.mockResolvedValue(makeStatusResponse())
    mockGetMigrationStatus.mockResolvedValue(makeMigrationStatusResponse())
    const wrapper = mount(DatabasePanel, { localVue, i18n })
    await flushPromises()
    await wrapper.vm.$nextTick()

    jest.advanceTimersByTime(30000)
    await flushPromises()
    expect(mockGetStatus).toHaveBeenCalledTimes(1)
    wrapper.destroy()
  })
})
