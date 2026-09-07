/**
 * 设置页「状态诊断」导出回归（2026-09-07 /health/sync 改造为 /health/diagnosis）。
 *
 * 保护点（防回归）：
 * 1. 真实模式走统一 request 客户端 blob 下载（认证头/续期链路），
 *    成功后以 btdeck-diagnosis-*.json 文件名触发保存并释放 objectURL；
 * 2. demo 模式不发起 API（demoRequest 不支持 blob），生成前端本地快照
 *    （结构与后端响应对齐，标注 demo: true）；
 * 3. 导出失败给出错误提示并复位 loading，不产生半截下载。
 */

import Vue, { CreateElement, VNode } from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import Settings from '@/views/settings/index.vue'
import { exportDiagnosisFile } from '@/api/health'
import { isDemoMode } from '@/demo/config'

jest.mock('@/api/health', () => ({
  exportDiagnosisFile: jest.fn()
}))

jest.mock('@/demo/config', () => ({
  isDemoMode: jest.fn(() => false)
}))

jest.mock('@/api/users', () => ({
  changePassword: jest.fn(),
  login: jest.fn(),
  logout: jest.fn(),
  getUserInfo: jest.fn()
}))

jest.mock('@/store/modules/user', () => ({
  UserModule: {
    userId: '1',
    name: 'admin',
    twoFactorFlag: '0',
    SetMustChangePassword: jest.fn(),
    ResetToken: jest.fn()
  }
}))

jest.mock('@/utils/request', () => ({
  __esModule: true,
  default: { post: jest.fn() },
  trySilentRefresh: jest.fn()
}))

const mockExport = exportDiagnosisFile as jest.MockedFunction<typeof exportDiagnosisFile>
const mockIsDemoMode = isDemoMode as jest.MockedFunction<typeof isDemoMode>

// class 组件的 private 方法/数据在运行时即实例成员，经接口重声明访问
interface SettingsVm extends Vue {
  handleExportDiagnosis: () => Promise<void>
  diagnosisLoading: boolean
}

const TrueStub = createLocalVue().extend({
  render: (h: CreateElement): VNode => h('div')
})

const localVue = createLocalVue()

// jsdom 无 blob URL 实现，注入桩并捕获 download 文件名
let createObjectUrlCalls: string[] = []
let revokeObjectUrlCalls: string[] = []
let clickedDownloads: Array<string | undefined> = []

const installBlobUrlStubs = (): void => {
  createObjectUrlCalls = []
  revokeObjectUrlCalls = []
  clickedDownloads = []
  const urlStub = URL as unknown as Record<string, unknown>
  urlStub.createObjectURL = jest.fn((blob: Blob) => {
    createObjectUrlCalls.push(String(blob.size))
    return 'blob:mock-diagnosis'
  })
  urlStub.revokeObjectURL = jest.fn((url: string) => {
    revokeObjectUrlCalls.push(url)
  })
  jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function mockClick(this: HTMLAnchorElement) {
    clickedDownloads.push(this.download)
  })
}

const readBlob = (blob: Blob): Promise<string> => new Promise(resolve => {
  const reader = new FileReader()
  reader.onload = () => resolve(String(reader.result))
  reader.onerror = () => resolve('')
  reader.readAsText(blob)
})

const mountSettings = (): {
  wrapper: Wrapper<Vue>
  vm: SettingsVm
  messageMock: { success: jest.Mock, error: jest.Mock, warning: jest.Mock }
} => {
  const messageMock = { success: jest.fn(), error: jest.fn(), warning: jest.fn() }
  const wrapper = shallowMount(Settings, {
    localVue,
    stubs: {
      'el-tabs': TrueStub,
      'el-tab-pane': TrueStub,
      'el-form': TrueStub,
      'el-form-item': TrueStub,
      'el-input': TrueStub,
      'el-button': TrueStub,
      'el-alert': TrueStub,
      'el-result': TrueStub
    },
    mocks: {
      $route: { query: {}, path: '/settings/index' },
      $router: { push: jest.fn(), replace: jest.fn() },
      $message: messageMock
    }
  })
  return { wrapper, vm: wrapper.vm as SettingsVm, messageMock }
}

const flush = async(): Promise<void> => {
  await new Promise<void>(resolve => { setTimeout(resolve, 0) })
  await Vue.nextTick()
}

describe('设置页状态诊断导出', () => {
  beforeEach(() => {
    mockExport.mockReset()
    mockIsDemoMode.mockReset()
    mockIsDemoMode.mockReturnValue(false)
    installBlobUrlStubs()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('真实模式：blob 走统一客户端，保存 btdeck-diagnosis-*.json 并释放 objectURL', async() => {
    mockExport.mockResolvedValue(new Blob(['{"version":"1.0.6"}'], { type: 'application/json' }))
    const { vm, messageMock } = mountSettings()

    await vm.handleExportDiagnosis()
    await flush()

    expect(mockExport).toHaveBeenCalledTimes(1)
    expect(clickedDownloads).toHaveLength(1)
    expect(clickedDownloads[0]).toMatch(/^btdeck-diagnosis-.*\.json$/)
    expect(revokeObjectUrlCalls).toEqual(['blob:mock-diagnosis'])
    expect(messageMock.success).toHaveBeenCalledWith(expect.stringContaining('已导出'))
    expect(vm.diagnosisLoading).toBe(false)
  })

  it('demo 模式：不发起 API，本地快照与后端结构对齐且标注 demo', async() => {
    mockIsDemoMode.mockReturnValue(true)
    const { vm } = mountSettings()

    await vm.handleExportDiagnosis()
    await flush()

    expect(mockExport).not.toHaveBeenCalled()
    expect(clickedDownloads).toHaveLength(1)
    expect(clickedDownloads[0]).toMatch(/^btdeck-diagnosis-.*\.json$/)
    // 本地快照内容：demo 标注 + 与后端响应对齐的顶层结构
    const passedBlobSize = createObjectUrlCalls[0]
    expect(passedBlobSize).toBeTruthy()
  })

  it('demo 快照内容契约：demo:true、version:demo、checks/sync 顶层键齐全', async() => {
    mockIsDemoMode.mockReturnValue(true)
    const { vm } = mountSettings()

    const captured: Blob[] = []
    const urlStub = URL as unknown as { createObjectURL: (blob: Blob) => string }
    const original = urlStub.createObjectURL
    urlStub.createObjectURL = (blob: Blob): string => {
      captured.push(blob)
      return original(blob)
    }

    await vm.handleExportDiagnosis()
    await flush()

    expect(captured).toHaveLength(1)
    const parsed = JSON.parse(await readBlob(captured[0])) as Record<string, unknown>
    expect(parsed.demo).toBe(true)
    expect(parsed.version).toBe('demo')
    expect(Object.keys(parsed)).toEqual(
      expect.arrayContaining(['generatedAt', 'build', 'checks', 'readinessFailureTotal', 'sync'])
    )
    expect(Object.keys(parsed.checks as Record<string, unknown>)).toEqual(
      expect.arrayContaining(['database', 'worker', 'eventLoopLag'])
    )
  })

  it('导出失败：错误提示 + loading 复位，不触发下载', async() => {
    mockExport.mockRejectedValue(new Error('HTTP 500'))
    const { vm, messageMock } = mountSettings()

    await vm.handleExportDiagnosis()
    await flush()

    expect(messageMock.error).toHaveBeenCalledWith(expect.stringContaining('导出诊断文件失败'))
    expect(clickedDownloads).toHaveLength(0)
    expect(vm.diagnosisLoading).toBe(false)
  })
})
