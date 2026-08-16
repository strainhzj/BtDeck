/**
 * user store 强制改密标志回归测试（安全修复 W9）
 *
 * 保护点（防回归）：
 * 1. Login action 必须解析登录响应的 must_change_password 并存入 state——
 *    若未来有人重构 Login 时漏掉该字段，前端路由守卫的强制改密拦截
 *    （permission.ts）将失效，默认口令部署失去第一道防线；
 * 2. SetMustChangePassword(false) 在改密成功后清除标志（守卫放行）。
 */

import { UserModule } from '@/store/modules/user'
import { login } from '@/api/users'

jest.mock('@/api/users', () => ({
  login: jest.fn(),
  logout: jest.fn(),
  getUserInfo: jest.fn()
}))

jest.mock('@/utils/cookies', () => ({
  getToken: jest.fn(() => ''),
  setToken: jest.fn(),
  removeToken: jest.fn(),
  getRefreshToken: jest.fn(() => ''),
  setRefreshToken: jest.fn(),
  removeRefreshToken: jest.fn(),
  getUserId: jest.fn(() => ''),
  setUserId: jest.fn(),
  removeUserId: jest.fn()
}))

const mockLogin = login as jest.MockedFunction<typeof login>

describe('user store 强制改密标志', () => {
  beforeEach(() => {
    mockLogin.mockReset()
    UserModule.SetMustChangePassword(false)
    UserModule.ResetToken()
  })

  it('登录响应携带 must_change_password=true 时写入 state', async() => {
    mockLogin.mockResolvedValue({
      code: '200',
      msg: '登录成功',
      status: 'success',
      data: [
        {
          access_token: 'token-abc',
          refresh_token: 'refresh-xyz',
          token_type: 'bearer',
          user_id: 1,
          must_change_password: true
        }
      ]
    })

    await UserModule.Login({ username: 'admin', password: 'admin' })

    expect(UserModule.token).toBe('token-abc')
    expect(UserModule.mustChangePassword).toBe(true)
  })

  it('登录响应缺省 must_change_password 时标志为 false（存量兼容）', async() => {
    mockLogin.mockResolvedValue({
      code: '200',
      msg: '登录成功',
      status: 'success',
      data: [{ access_token: 't', refresh_token: 'r', token_type: 'bearer', user_id: 1 }]
    })

    await UserModule.Login({ username: 'admin', password: 'admin' })

    expect(UserModule.mustChangePassword).toBe(false)
  })

  it('改密成功后清除标志（守卫据此放行）', async() => {
    mockLogin.mockResolvedValue({
      code: '200',
      msg: '登录成功',
      status: 'success',
      data: [
        { access_token: 't', refresh_token: 'r', token_type: 'bearer', user_id: 1, must_change_password: true }
      ]
    })
    await UserModule.Login({ username: 'admin', password: 'admin' })
    expect(UserModule.mustChangePassword).toBe(true)

    UserModule.SetMustChangePassword(false)

    expect(UserModule.mustChangePassword).toBe(false)
  })

  it('ResetToken 同时清除强制改密标志', async() => {
    mockLogin.mockResolvedValue({
      code: '200',
      msg: '登录成功',
      status: 'success',
      data: [
        { access_token: 't', refresh_token: 'r', token_type: 'bearer', user_id: 1, must_change_password: true }
      ]
    })
    await UserModule.Login({ username: 'admin', password: 'admin' })

    UserModule.ResetToken()

    expect(UserModule.mustChangePassword).toBe(false)
  })
})
