/**
 * 设置页 2FA 二维码缺失降级回归（Android 服务端形态 Pillow ANDROID-DROP）。
 *
 * 保护点：
 * 1. 后端 Pillow 缺失时 verifyPasswordFor2FA 返回成功信封但 qr_code_base64 为空
 *    ——前端步骤 2 必须降级为「手动录入密钥」块（secret + 复制 + 账户名/TOTP 参数），
 *    绑定流程不得中断（历史缺陷：code=500 卡死在步骤 1，secret 落库却不可见）；
 * 2. Pillow 可用（桌面/Docker）行为零变化：渲染 img 二维码，手动录入块不出现；
 * 3. 复制密钥复用共享 clipboard util，失败有兜底提示；
 * 4. resetFlow/停用成功清理手动录入态。
 */

import Vue from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'
import fs from 'fs'
import path from 'path'

import Settings from '@/views/settings/index.vue'
import { copyTextToClipboard } from '@/utils/clipboard'

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

jest.mock('@/utils/clipboard', () => ({
  copyTextToClipboard: jest.fn()
}))

import request from '@/utils/request'

const mockPost = (request as unknown as { post: jest.Mock }).post
const mockCopy = copyTextToClipboard as jest.Mock

// class 组件的 private 方法/数据在运行时即实例成员，经接口重声明访问
interface SettingsVm extends Vue {
  passwordForm: { password: string }
  verifyPassword: () => Promise<void>
  resetFlow: () => void
  copyManualSecret: () => Promise<void>
  manualEntrySecret: string
  manualEntryAccount: string
  qrCodeData: string
  currentStep: number
}

const localVue = createLocalVue()

const mountSettings = (): { wrapper: Wrapper<Vue>, vm: SettingsVm, messageMock: jest.Mock } => {
  const messageMock = jest.fn()
  const wrapper = shallowMount(Settings, {
    localVue,
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

const readSource = (): string =>
  fs.readFileSync(path.resolve(__dirname, '../../src/views/settings/index.vue'), 'utf8')

describe('设置页 2FA 手动录入降级（Pillow 缺失）', () => {
  beforeEach(() => {
    mockPost.mockReset()
    mockCopy.mockReset()
  })

  it('二维码可用（桌面）：渲染 img，不出现手动录入块', async() => {
    mockPost.mockResolvedValue({
      code: '200',
      status: 'success',
      data: { qr_code_base64: 'data:image/png;base64,AAA=', secret: 'SECRET123', qr_available: true }
    })
    const { wrapper, vm } = mountSettings()
    vm.passwordForm.password = 'right'

    await vm.verifyPassword()
    await flush()

    expect(vm.currentStep).toBe(2)
    expect(vm.qrCodeData).toBe('data:image/png;base64,AAA=')
    expect(wrapper.find('.qr-code img').exists()).toBe(true)
    expect(wrapper.find('.manual-secret-entry').exists()).toBe(false)
    expect(wrapper.find('.qr-code-manual').exists()).toBe(false)
  })

  it('二维码缺失（Android）：降级手动录入块渲染 secret 与账户名', async() => {
    mockPost.mockResolvedValue({
      code: '200',
      status: 'success',
      data: { qr_code_base64: '', secret: 'JBSWY3DPEHPK3PXP', qr_available: false }
    })
    const { wrapper, vm } = mountSettings()
    vm.passwordForm.password = 'right'

    await vm.verifyPassword()
    await flush()

    expect(vm.currentStep).toBe(2)
    expect(vm.qrCodeData).toBe('')
    expect(vm.manualEntrySecret).toBe('JBSWY3DPEHPK3PXP')
    expect(vm.manualEntryAccount).toBe('admin')
    // 步骤 2 渲染手动录入块而非二维码位
    expect(wrapper.find('.qr-code img').exists()).toBe(false)
    expect(wrapper.find('.manual-secret-entry').exists()).toBe(true)
    expect(wrapper.find('.qr-code-manual').exists()).toBe(true)
    expect(wrapper.find('.manual-entry-meta').text()).toContain('admin')
    expect(wrapper.find('.manual-entry-meta').text()).toContain('TOTP')
  })

  it('复制密钥：走共享 clipboard util，成功提示', async() => {
    mockPost.mockResolvedValue({
      code: '200',
      data: { qr_code_base64: '', secret: 'JBSWY3DPEHPK3PXP', qr_available: false }
    })
    const { vm, messageMock } = mountSettings()
    vm.passwordForm.password = 'right'
    await vm.verifyPassword()
    await flush()

    mockCopy.mockResolvedValue(undefined)
    await vm.copyManualSecret()
    await flush()

    expect(mockCopy).toHaveBeenCalledWith('JBSWY3DPEHPK3PXP')
    expect(messageMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'success', message: expect.stringContaining('已复制') })
    )
  })

  it('复制失败：兜底提示手动复制，不抛未捕获异常', async() => {
    mockPost.mockResolvedValue({
      code: '200',
      data: { qr_code_base64: '', secret: 'JBSWY3DPEHPK3PXP', qr_available: false }
    })
    const { vm, messageMock } = mountSettings()
    vm.passwordForm.password = 'right'
    await vm.verifyPassword()
    await flush()

    mockCopy.mockRejectedValue(new Error('denied'))
    await vm.copyManualSecret()
    await flush()

    expect(messageMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', message: expect.stringContaining('复制失败') })
    )
  })

  it('resetFlow 清理手动录入态（密钥不留驻 UI）', async() => {
    mockPost.mockResolvedValue({
      code: '200',
      data: { qr_code_base64: '', secret: 'JBSWY3DPEHPK3PXP', qr_available: false }
    })
    const { wrapper, vm } = mountSettings()
    vm.passwordForm.password = 'right'
    await vm.verifyPassword()
    await flush()
    expect(wrapper.find('.manual-secret-entry').exists()).toBe(true)

    vm.resetFlow()
    await flush()

    expect(vm.manualEntrySecret).toBe('')
    expect(vm.manualEntryAccount).toBe('')
    expect(wrapper.find('.manual-secret-entry').exists()).toBe(false)
  })

  it('源码契约：空二维码兜底/共享剪贴板/指引双分支/禁裸 500 中断', () => {
    const source = readSource()
    // 空串兜底（旧后端字段缺失或降级时不得 undefined 透传）
    expect(source).toContain("this.qrCodeData = response.data.qr_code_base64 || ''")
    // 复制必须复用共享 util（禁组件内私有实现）
    expect(source).toContain("import { copyTextToClipboard } from '@/utils/clipboard'")
    // 使用步骤按二维码可用性分流
    expect(source).toContain('<li v-if="qrCodeData">扫描上方二维码</li>')
    expect(source).toContain('<li v-else>手动输入上方密钥完成添加</li>')
    // 手动录入块以 qrCodeData 空且非加载中为条件（禁仅凭 qr_available 字段）
    expect(source).toContain("'qr-code-manual': !qrCodeData && !qrLoading")
  })
})
