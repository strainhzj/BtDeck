import { UserModule } from '@/store/modules/user'
import { login, logout } from '@/api/users'
import { setRefreshToken, removeRefreshToken, setToken, removeToken, removeUserId, getUserId } from '@/utils/cookies'

/**
 * 双令牌体系前端存储回归（verified-bugfix-remediation W6-2）：
 * - Login 成功后持久化 refresh_token（cookie）
 * - Login 响应缺 refresh_token 时清除旧值（残留已撤销 token 会让续期永远失败）
 * - ResetToken / LogOut 清空 refresh_token
 * - SetToken action 更新内存 + cookie（401 单飞刷新后重放依赖）
 * - LogOut 容忍空 token（登出按钮在任何状态下可用）
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
