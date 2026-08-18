/**
 * 设置页改密流程回归（W9 死锁修复的组件侧锚定 + 改密会话终结）。
 *
 * 保护点（防回归）：
 * 1. 改密成功必须终结会话：后端 change_password 已撤销该用户全部
 *    refresh token（W9），本地不可再续期——ResetToken 全清（含强制改密
 *    标志，守卫放行依据随登出自然失效）+ 跳转登录页用新密码重登；
 *    URL 上的 forceChange query 随整页跳转自然失效，不再单独清理；
 * 2. 改密失败不得提前终结会话（不 ResetToken、不跳转）；
 * 3. 两次输入不一致的前置校验不得被绕过（不发起 API）。
 */

import Vue, { CreateElement, VNode } from 'vue'
import { createLocalVue, shallowMount, Wrapper } from '@vue/test-utils'

import Settings from '@/views/settings/index.vue'
import { changePassword } from '@/api/users'
import { UserModule } from '@/store/modules/user'

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

const mockChangePassword = changePassword as jest.MockedFunction<typeof changePassword>

// class 组件的 private 方法/数据在运行时即实例成员，经接口重声明访问
interface SettingsVm extends Vue {
  changePassword: () => Promise<void>
}

const TrueStub = createLocalVue().extend({
  render: (h: CreateElement): VNode => h('div')
})

const localVue = createLocalVue()

const mountSettings = (forceChange: string | undefined): {
  wrapper: Wrapper<Vue>
  vm: SettingsVm
  pushMock: jest.Mock
  replaceMock: jest.Mock
  messageMock: jest.Mock
} => {
  const query: Record<string, string> = { keepMe: 'yes' }
  if (forceChange !== undefined) {
    query.forceChange = forceChange
  }
  const pushMock = jest.fn()
  const replaceMock = jest.fn()
  const messageMock = jest.fn()
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
      $route: { query, path: '/settings/index' },
      $router: { push: pushMock, replace: replaceMock },
      $message: messageMock
    }
  })
  return { wrapper, vm: wrapper.vm as SettingsVm, pushMock, replaceMock, messageMock }
}

const fillValidForm = (wrapper: Wrapper<Vue>): void => {
  wrapper.setData({
    confirmPass: 'NewPass123',
    passwordFormChange: {
      name: 'admin',
      userId: '1',
      new_password: 'NewPass123',
      old_password: 'OldPass456'
    }
  })
}

const flush = async(): Promise<void> => {
  await new Promise<void>(resolve => { setTimeout(resolve, 0) })
  await Vue.nextTick()
}

describe('设置页改密流程（W9 + 改密会话终结）', () => {
  beforeEach(() => {
    mockChangePassword.mockReset()
    mockChangePassword.mockResolvedValue({ code: '200', status: 'success', msg: '修改成功', data: null })
    ;(UserModule.SetMustChangePassword as unknown as jest.Mock).mockClear()
    ;(UserModule.ResetToken as unknown as jest.Mock).mockClear()
  })

  it('改密成功（URL 带 forceChange）：ResetToken 终结会话 + 跳登录页，API 收到 base64 口令', async() => {
    const { wrapper, vm, pushMock, replaceMock, messageMock } = mountSettings('1')
    fillValidForm(wrapper)

    await vm.changePassword()
    await flush()

    // API 收到 base64 编码的口令（与后端 _decode_password 契约对齐）
    expect(mockChangePassword).toHaveBeenCalledWith({
      userId: '1',
      new_password: window.btoa('NewPass123'),
      old_password: window.btoa('OldPass456')
    })
    // 会话终结：全清（ResetToken 内含强制改密标志清除）
    expect(UserModule.ResetToken).toHaveBeenCalledTimes(1)
    // 跳登录页用新密码重登；forceChange query 随整页跳转失效，无需 replace 清理
    expect(pushMock).toHaveBeenCalledWith('/login')
    expect(replaceMock).not.toHaveBeenCalled()
    expect(messageMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'success', message: expect.stringContaining('重新登录') })
    )
  })

  it('改密成功（URL 无 forceChange）：同样 ResetToken + 跳登录（行为不依赖 query）', async() => {
    const { wrapper, vm, pushMock, replaceMock } = mountSettings(undefined)
    fillValidForm(wrapper)

    await vm.changePassword()
    await flush()

    expect(UserModule.ResetToken).toHaveBeenCalledTimes(1)
    expect(pushMock).toHaveBeenCalledWith('/login')
    expect(replaceMock).not.toHaveBeenCalled()
  })

  it('改密失败：不终结会话、不跳转（错误路径不得误杀登录态）', async() => {
    mockChangePassword.mockRejectedValue(new Error('网络异常'))
    const { wrapper, vm, pushMock, replaceMock, messageMock } = mountSettings('1')
    fillValidForm(wrapper)

    await vm.changePassword()
    await flush()

    expect(UserModule.ResetToken).not.toHaveBeenCalled()
    expect(pushMock).not.toHaveBeenCalled()
    expect(replaceMock).not.toHaveBeenCalled()
    expect(messageMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', message: '密码修改失败' })
    )
  })

  it('两次输入不一致：前置校验拦截，不发起 API、不终结会话', async() => {
    const { wrapper, vm, pushMock, messageMock } = mountSettings('1')
    wrapper.setData({
      confirmPass: 'Different999',
      passwordFormChange: {
        name: 'admin',
        userId: '1',
        new_password: 'NewPass123',
        old_password: 'OldPass456'
      }
    })

    await vm.changePassword()
    await flush()

    expect(mockChangePassword).not.toHaveBeenCalled()
    expect(UserModule.ResetToken).not.toHaveBeenCalled()
    expect(pushMock).not.toHaveBeenCalled()
    expect(messageMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'warning', message: '两次输入的密码不一致' })
    )
  })
})
