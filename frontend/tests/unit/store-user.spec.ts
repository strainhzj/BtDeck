import { UserModule } from '@/store/modules/user'
import { login } from '@/api/users'
import { setRefreshToken, removeRefreshToken, setToken, removeToken, getUserId } from '@/utils/cookies'

/**
 * 双令牌体系前端存储回归（verified-bugfix-remediation W6-2）：
 * - Login 成功后持久化 refresh_token（cookie）
 * - ResetToken / LogOut 清空 refresh_token
 * - SetToken action 更新内存 + cookie（401 单飞刷新后重放依赖）
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
const mockSetRefreshToken = setRefreshToken as jest.MockedFunction<typeof setRefreshToken>
const mockRemoveRefreshToken = removeRefreshToken as jest.MockedFunction<typeof removeRefreshToken>
const mockSetToken = setToken as jest.MockedFunction<typeof setToken>
const mockRemoveToken = removeToken as jest.MockedFunction<typeof removeToken>

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

  it('Login 响应无 refresh_token 时不清除旧值（向后兼容旧后端）', async() => {
    mockLogin.mockResolvedValue({
      status: 'success',
      msg: '登录成功',
      code: '200',
      data: [{ access_token: 'new-access', token_type: 'bearer', user_id: 7 }]
    })

    await UserModule.Login({ username: 'tester', password: 'pass' })

    expect(mockSetRefreshToken).not.toHaveBeenCalled()
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
})
