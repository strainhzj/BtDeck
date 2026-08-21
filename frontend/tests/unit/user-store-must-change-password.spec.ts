/**
 * user store 强制改密标志回归测试（安全修复 W9）
 *
 * 保护点（防回归）：
 * 1. Login action 必须解析登录响应的 must_change_password 并存入 state——
 *    若未来有人重构 Login 时漏掉该字段，前端路由守卫的强制改密拦截
 *    （permission.ts）将失效，默认口令部署失去第一道防线；
 * 2. SetMustChangePassword(false) 在改密成功后清除标志（守卫放行）；
 * 3. GetUserInfo 解析 /user/info 下发的 mustChangePassword（W9 补全）：
 *    wrapped 格式写入；字段缺失（滚动部署旧后端）时保持原值不误清。
 */

import { UserModule } from '@/store/modules/user'
import { getUserInfo, login, UserInfoData } from '@/api/users'
import type { ApiEnvelope } from '@/utils/request'

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
const mockGetUserInfo = getUserInfo as jest.MockedFunction<typeof getUserInfo>

describe('user store 强制改密标志', () => {
  beforeEach(() => {
    mockLogin.mockReset()
    mockGetUserInfo.mockReset()
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

  it('登录响应显式 must_change_password=false 时标志为 false（改密后再登录即解锁）', async() => {
    mockLogin.mockResolvedValue({
      code: '200',
      msg: '登录成功',
      status: 'success',
      data: [
        { access_token: 't', refresh_token: 'r', token_type: 'bearer', user_id: 1, must_change_password: false }
      ]
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

  describe('GetUserInfo 解析 /user/info 下发标志（W9 补全）', () => {
    const wrappedResponse = (user: Partial<UserInfoData>): ApiEnvelope<UserInfoData> => ({
      code: '200',
      msg: '获取用户信息成功',
      status: 'success',
      data: { user }
    })

    beforeEach(() => {
      // GetUserInfo 前置校验：token 为空直接 throw（getToken mock 返回 ''）
      UserModule.SetToken('token-for-userinfo')
    })

    it('wrapped 格式 {user:{mustChangePassword:true}} 写入 state', async() => {
      mockGetUserInfo.mockResolvedValue(wrappedResponse({
        userId: '1',
        roles: ['admin'],
        name: 'admin',
        twoFactorFlag: '0',
        mustChangePassword: true
      }))

      await UserModule.GetUserInfo()

      expect(UserModule.mustChangePassword).toBe(true)
    })

    it('扁平格式（无 user 包裹）同样解析写入（GetUserInfo 双分支对齐）', async() => {
      mockGetUserInfo.mockResolvedValue({
        code: '200',
        msg: '获取用户信息成功',
        status: 'success',
        data: { userId: '1', roles: ['admin'], name: 'admin', twoFactorFlag: '0', mustChangePassword: true }
      } as unknown as ApiEnvelope<UserInfoData>)

      await UserModule.GetUserInfo()

      expect(UserModule.roles).toEqual(['admin'])
      expect(UserModule.mustChangePassword).toBe(true)
    })

    it('wrapped 格式显式 false 覆盖登录时置位的 true（改密后 F5 即时解锁）', async() => {
      mockLogin.mockResolvedValue({
        code: '200',
        msg: '登录成功',
        status: 'success',
        data: [
          { access_token: 't', refresh_token: 'r', token_type: 'bearer', user_id: 1, must_change_password: true }
        ]
      })
      await UserModule.Login({ username: 'admin', password: 'admin' })
      UserModule.SetToken('token-for-userinfo')
      expect(UserModule.mustChangePassword).toBe(true)

      mockGetUserInfo.mockResolvedValue(wrappedResponse({
        userId: '1',
        roles: ['admin'],
        mustChangePassword: false
      }))

      await UserModule.GetUserInfo()

      expect(UserModule.mustChangePassword).toBe(false)
    })

    it('字段缺失（滚动部署旧后端）时保持原值不误清', async() => {
      mockLogin.mockResolvedValue({
        code: '200',
        msg: '登录成功',
        status: 'success',
        data: [
          { access_token: 't', refresh_token: 'r', token_type: 'bearer', user_id: 1, must_change_password: true }
        ]
      })
      await UserModule.Login({ username: 'admin', password: 'admin' })
      UserModule.SetToken('token-for-userinfo')
      expect(UserModule.mustChangePassword).toBe(true)

      mockGetUserInfo.mockResolvedValue(wrappedResponse({
        userId: '1',
        roles: ['admin'],
        twoFactorFlag: '0'
      }))

      await UserModule.GetUserInfo()

      // 未下发字段 ≠ false：若误用 || 兜底会把登录时置位的标志清掉，
      // 滚动部署期间强制改密拦截失效
      expect(UserModule.mustChangePassword).toBe(true)
    })
  })
})
