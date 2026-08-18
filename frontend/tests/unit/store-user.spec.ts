import { UserModule } from '@/store/modules/user'
import { login, logout, getUserInfo } from '@/api/users'
import { setRefreshToken, removeRefreshToken, setToken, removeToken, removeUserId, getUserId } from '@/utils/cookies'
import { ApiError } from '@/types/api'

/**
 * 双令牌体系前端存储回归（verified-bugfix-remediation W6-2 + 跨标签竞态修复）：
 * - Login 成功后持久化 refresh_token（cookie）
 * - Login 响应缺 refresh_token 时清除旧值（残留已撤销 token 会让续期永远失败）
 * - ResetToken / LogOut 清空 refresh_token；ExpireSession 被动登出保留（竞态加固）
 * - SetToken action 更新内存 + cookie（401 单飞刷新后重放依赖）
 * - LogOut 容忍空 token（登出按钮在任何状态下可用）
 * - GetUserInfo 网络层失败原样上抛（守卫网络分流的契约），其余包装为普通提示
 */

jest.mock('@/api/users', () => ({
  login: jest.fn(),
  logout: jest.fn(),
  getUserInfo: jest.fn()
}))

jest.mock('@/utils/cookies', () => ({
  getToken: jest.fn(() => 'old-access'),
  setToken: jest.fn(),
  removeToken: jest.fn(),
  getRefreshToken: jest.fn(() => 'old-refresh'),
  setRefreshToken: jest.fn(),
  removeRefreshToken: jest.fn(),
  getUserId: jest.fn(() => ''),
  setUserId: jest.fn(),
  removeUserId: jest.fn(),
  getStorage: jest.fn(),
  setStorage: jest.fn()
}))

const mockLogin = login as jest.MockedFunction<typeof login>
const mockLogout = logout as jest.MockedFunction<typeof logout>
const mockGetUserInfo = getUserInfo as jest.MockedFunction<typeof getUserInfo>

/** 网络层失败（无 HTTP 响应）经拦截器归一化后的 ApiError 形态 */
const networkApiError = new ApiError('网络连接失败，请检查网络连接', { code: '0', httpStatus: 0 })
const mockSetRefreshToken = setRefreshToken as jest.MockedFunction<typeof setRefreshToken>
const mockRemoveRefreshToken = removeRefreshToken as jest.MockedFunction<typeof removeRefreshToken>
const mockSetToken = setToken as jest.MockedFunction<typeof setToken>
const mockRemoveToken = removeToken as jest.MockedFunction<typeof removeToken>
const mockRemoveUserId = removeUserId as jest.MockedFunction<typeof removeUserId>

describe('UserModule 双令牌存储', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(getUserId as jest.Mock).mockReturnValue('')
  })

  it('Login 成功时持久化 refresh_token 并更新 access_token', async() => {
    mockLogin.mockResolvedValue({
      status: 'success',
      msg: '登录成功',
      code: '200',
      data: [
        {
          access_token: 'new-access',
          refresh_token: 'new-refresh',
          token_type: 'bearer',
          user_id: 7
        }
      ]
    })

    await UserModule.Login({ username: 'tester', password: 'pass' })

    expect(mockSetToken).toHaveBeenCalledWith('new-access')
    expect(mockSetRefreshToken).toHaveBeenCalledWith('new-refresh')
    expect(UserModule.token).toBe('new-access')
  })

  it('Login 响应缺 refresh_token 时清除旧值（残留已撤销 token 会让续期永远失败）', async() => {
    mockLogin.mockResolvedValue({
      status: 'success',
      msg: '登录成功',
      code: '200',
      data: [{ access_token: 'new-access', token_type: 'bearer', user_id: 7 }]
    })

    await UserModule.Login({ username: 'tester', password: 'pass' })

    expect(mockSetRefreshToken).not.toHaveBeenCalled()
    expect(mockRemoveRefreshToken).toHaveBeenCalled()
  })

  it('SetToken 更新内存 token 与 cookie（401 刷新后重放依赖）', async() => {
    UserModule.SetToken('refreshed-access')
    expect(mockSetToken).toHaveBeenCalledWith('refreshed-access')
    expect(UserModule.token).toBe('refreshed-access')
  })

  it('ResetToken 清空 refresh_token 与 access_token', () => {
    UserModule.ResetToken()
    expect(mockRemoveRefreshToken).toHaveBeenCalled()
    expect(mockRemoveToken).toHaveBeenCalled()
    expect(UserModule.token).toBe('')
  })

  describe('ExpireSession（会话过期被动登出，跨标签竞态加固）', () => {
    beforeEach(() => {
      jest.clearAllMocks()
      ;(getUserId as jest.Mock).mockReturnValue('')
      UserModule.SetToken('expired-access')
      UserModule.SetMustChangePassword(true)
    })

    it('清 access/userId/roles/mustChangePassword 但保留共享 refresh cookie', () => {
      UserModule.ExpireSession()

      expect(mockRemoveToken).toHaveBeenCalled()
      expect(mockRemoveUserId).toHaveBeenCalled()
      // 与 ResetToken 的本质区别：不清 refresh cookie（防"败者先读、胜者后写"
      // 残余竞态把他标签刚轮换出的有效令牌一并杀死）
      expect(mockRemoveRefreshToken).not.toHaveBeenCalled()
      expect(UserModule.token).toBe('')
      expect(UserModule.userId).toBe('')
      expect(UserModule.roles).toEqual([])
    })

    it('清除强制改密标志（W9 状态不残留到下一次会话）', () => {
      UserModule.ExpireSession()

      expect(UserModule.mustChangePassword).toBe(false)
    })
  })

  describe('GetUserInfo 错误分流（守卫网络分流的上抛契约）', () => {
    beforeEach(() => {
      jest.clearAllMocks()
      ;(getUserId as jest.Mock).mockReturnValue('')
      UserModule.ResetToken()
      UserModule.SetToken('valid-access')
    })

    it('网络层失败（ApiError code 0）原样上抛：守卫据此中止导航保留会话', async() => {
      mockGetUserInfo.mockRejectedValue(networkApiError)

      await expect(UserModule.GetUserInfo()).rejects.toBe(networkApiError)
    })

    it('非网络失败（含认证 401）包装为普通提示，不伪装成网络错误', async() => {
      mockGetUserInfo.mockRejectedValue(new ApiError('token验证失败', { code: '401', httpStatus: 200 }))

      await expect(UserModule.GetUserInfo()).rejects.toThrow('获取用户信息失败，请重新登录')
    })
  })

  describe('LogOut', () => {
    beforeEach(() => {
      jest.clearAllMocks()
      ;(getUserId as jest.Mock).mockReturnValue('')
      UserModule.ResetToken()
    })

    it('token 为空时不抛错、跳过后端调用，仍完整清理本地状态', async() => {
      await expect(UserModule.LogOut()).resolves.toBeUndefined()

      expect(mockLogout).not.toHaveBeenCalled()
      expect(mockRemoveToken).toHaveBeenCalled()
      expect(mockRemoveRefreshToken).toHaveBeenCalled()
      expect(mockRemoveUserId).toHaveBeenCalled()
      expect(UserModule.token).toBe('')
    })

    it('token 为空时也清除强制改密标志（与 ResetToken 对齐）', async() => {
      UserModule.SetMustChangePassword(true)

      await UserModule.LogOut()

      expect(UserModule.mustChangePassword).toBe(false)
    })

    it('正常路径：通知后端并清理本地状态', async() => {
      UserModule.SetToken('valid-access')
      mockLogout.mockResolvedValue({ status: 'success', msg: 'ok', code: '200', data: null })

      await UserModule.LogOut()

      expect(mockLogout).toHaveBeenCalled()
      expect(UserModule.token).toBe('')
    })

    it('后端登出失败时仍本地清理（登出 UX 不被服务端错误阻塞）', async() => {
      UserModule.SetToken('expired-access')
      mockLogout.mockRejectedValue(new Error('401'))

      await expect(UserModule.LogOut()).resolves.toBeUndefined()

      expect(mockLogout).toHaveBeenCalled()
      expect(mockRemoveToken).toHaveBeenCalled()
      expect(UserModule.token).toBe('')
    })
  })
})
