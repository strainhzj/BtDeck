/**
 * 设置页改密流程回归（W9 死锁修复的组件侧锚定）。
 *
 * 保护点（防回归）：
 * 1. 改密成功必须同时完成"双解锁"：清除 store 强制改密标志
 *    （SetMustChangePassword(false)，守卫据此放行）+ 清除 URL 上的
 *    forceChange query（防 F5 重挂载时弹过期警告）；
 * 2. URL 无 forceChange 时不做多余路由跳转；
 * 3. 改密失败不得提前解锁（不清标志、不清 query）；
 * 4. 两次输入不一致的前置校验不得被绕过（不发起 API）。
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
    SetMustChangePassword: jest.fn()
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

const mountSettings = (forceChange: string | undefined): { wrapper: Wrapper<Vue>, vm: SettingsVm, replaceMock: jest.Mock, messageMock: jest.Mock } => {
  const query: Record<string, string> = { keepMe: 'yes' }
  if (forceChange !== undefined) {
    query.forceChange = forceChange
  }
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
      $router: { replace: replaceMock },
      $message: messageMock
    }
  })
  return { wrapper, vm: wrapper.vm as SettingsVm, replaceMock, messageMock }
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

describe('设置页改密流程（W9 死锁修复组件侧）', () => {
  beforeEach(() => {
    mockChangePassword.mockReset()
    mockChangePassword.mockResolvedValue({ code: '200', status: 'success', msg: '修改成功', data: null })
    ;(UserModule.SetMustChangePassword as unknown as jest.Mock).mockClear()
  })

  it('改密成功且 URL 带 forceChange：清 store 标志 + 清 URL query（保留其他参数）', async() => {
    const { wrapper, vm, replaceMock } = mountSettings('1')
    fillValidForm(wrapper)

    await vm.changePassword()
    await flush()

    // API 收到 base64 编码的口令（与后端 _decode_password 契约对齐）
    expect(mockChangePassword).toHaveBeenCalledWith({
      userId: '1',
      new_password: window.btoa('NewPass123'),
      old_password: window.btoa('OldPass456')
    })
    // 双解锁之一：store 标志清除（守卫放行的依据）
    expect(UserModule.SetMustChangePassword).toHaveBeenCalledWith(false)
    // 双解锁之二：URL 清除 forceChange 且保留其他 query（防 F5 重弹过期警告）
    expect(replaceMock).toHaveBeenCalledTimes(1)
    const target = replaceMock.mock.calls[0][0] as { query: Record<string, string> }
    expect(target.query.forceChange).toBeUndefined()
    expect(target.query.keepMe).toBe('yes')
  })

  it('改密成功且 URL 无 forceChange：仍清 store 标志，但不做多余路由跳转', async() => {
    const { wrapper, vm, replaceMock } = mountSettings(undefined)
    fillValidForm(wrapper)

    await vm.changePassword()
    await flush()

    expect(UserModule.SetMustChangePassword).toHaveBeenCalledWith(false)
    expect(replaceMock).not.toHaveBeenCalled()
  })

  it('改密失败：不清标志、不清 URL（错误路径不得提前解锁）', async() => {
    mockChangePassword.mockRejectedValue(new Error('网络异常'))
    const { wrapper, vm, replaceMock, messageMock } = mountSettings('1')
    fillValidForm(wrapper)

    await vm.changePassword()
    await flush()

    expect(UserModule.SetMustChangePassword).not.toHaveBeenCalled()
    expect(replaceMock).not.toHaveBeenCalled()
    expect(messageMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', message: '密码修改失败' })
    )
  })

  it('两次输入不一致：前置校验拦截，不发起 API', async() => {
    const { wrapper, vm, replaceMock, messageMock } = mountSettings('1')
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
    expect(UserModule.SetMustChangePassword).not.toHaveBeenCalled()
    expect(replaceMock).not.toHaveBeenCalled()
    expect(messageMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'warning', message: '两次输入的密码不一致' })
    )
  })
})
