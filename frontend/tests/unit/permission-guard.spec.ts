import router from '@/router'
import type { RawLocation } from 'vue-router'
import '@/permission'
import { UserModule } from '@/store/modules/user'
import { getUserInfo, refreshAccessToken } from '@/api/users'
import { getUserId } from '@/utils/cookies'

/**
 * 路由守卫主动过期检查回归（双令牌 W6 伴随修复）：
 * 通过真实 router 导航（目标 /404，不经过 Layout）验证守卫分支：
 * - access token 过期 + 续期成功 → 放行，且内存令牌已更新
 * - access token 过期 + 续期失败 → 登出并跳登录，redirect 保留目标路由
 * - 过期 + 目标即 /login → 直接放行登录页（无 redirect 自指循环）
 * - 未过期 → 不触发主动续期（refreshAccessToken 不被调用）
 * - token 有效但 GetUserInfo 失败 → 原有兜底登出仍生效
 */

// permission.ts 引入 nprogress.css：node_modules 下的 css 不经转译，需桩掉
jest.mock('nprogress/nprogress.css', () => ({}))

jest.mock('@/api/users', () => ({
  login: jest.fn(),
  logout: jest.fn(),
  getUserInfo: jest.fn(),
  refreshAccessToken: jest.fn(),
  changePassword: jest.fn()
}))

jest.mock('@/utils/cookies', () => ({
  getSidebarStatus: jest.fn(() => 'opened'),
  setSidebarStatus: jest.fn(),
  getToken: jest.fn(),
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

const mockGetUserInfo = getUserInfo as jest.MockedFunction<typeof getUserInfo>
const mockRefresh = refreshAccessToken as jest.MockedFunction<typeof refreshAccessToken>

// 后端 /auth/refresh 失效语义：HTTP 200 + code 401 + data null
const refreshFailEnvelope = {
  status: 'error',
  msg: '已撤销',
  code: '401',
  data: null
} as unknown as Awaited<ReturnType<typeof refreshAccessToken>>

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

function makeJwt(exp: number): string {
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url({ exp })}.sig`
}

const EXPIRED = Math.floor(1_700_000_000_000 / 1000) // 2023-11，必已过期
const VALID = 4_100_000_000 // 2100 年，必未过期

/**
 * 守卫内 next('/login?...') 重定向会让原 push 以 NavigationRedirectedError
 * 拒绝（vue-router 3 语义），属预期路径，统一吞掉后断言最终路由。
 */
const pushQuietly = (to: RawLocation): Promise<void> =>
  router.push(to).then(
    () => undefined,
    () => undefined
  )

beforeEach(async() => {
  jest.clearAllMocks()
  ;(getUserId as jest.Mock).mockReturnValue('')
  UserModule.ResetToken()
  mockGetUserInfo.mockResolvedValue({
    status: 'success',
    msg: '',
    code: '200',
    data: { userId: '7', roles: ['admin'], name: 't', avatar: '', introduction: '', twoFactorFlag: '0' }
  })
  // 统一回登录页复位导航状态：避免连续 push 同一路由触发
  // NavigationDuplicated（router.ts 会吞掉该错误，守卫不执行导致假绿）
  await pushQuietly('/login')
})

describe('守卫主动过期检查（真实路由导航）', () => {
  it('过期 + 续期成功 → 放行目标路由，令牌已更新且 GetUserInfo 正常拉取', async() => {
    UserModule.SetToken(makeJwt(EXPIRED))
    mockRefresh.mockResolvedValue({
      status: 'success',
      msg: '',
      code: '200',
      data: [
        { access_token: 'renewed-access', refresh_token: 'renewed-refresh', token_type: 'bearer', user_id: 7 }
      ]
    })

    await pushQuietly('/404')

    expect(router.currentRoute.path).toBe('/404')
    expect(UserModule.token).toBe('renewed-access')
    expect(mockRefresh).toHaveBeenCalledTimes(1)
    expect(mockGetUserInfo).toHaveBeenCalledTimes(1)
  })

  it('过期 + 续期失败 → 登出并跳登录页，redirect 保留目标路由', async() => {
    UserModule.SetToken(makeJwt(EXPIRED))
    mockRefresh.mockResolvedValue(refreshFailEnvelope)

    await pushQuietly('/orphan-files')

    expect(router.currentRoute.path).toBe('/login')
    expect(router.currentRoute.query.redirect).toBe('/orphan-files')
    expect(UserModule.token).toBe('')
    // 续期失败直接登出，不应再走 GetUserInfo
    expect(mockGetUserInfo).not.toHaveBeenCalled()
  })

  it('过期 + 目标即 /login → 直接放行登录页，无 redirect 自指（防守卫循环）', async() => {
    UserModule.SetToken(makeJwt(EXPIRED))
    mockRefresh.mockRejectedValue(new Error('refresh 401'))

    // 带 query 使 fullPath 与 beforeEach 的 /login 不同，避免 NavigationDuplicated
    await pushQuietly({ path: '/login', query: { from: 'guard-test' } })

    expect(router.currentRoute.path).toBe('/login')
    expect(router.currentRoute.query.redirect).toBeUndefined()
    expect(UserModule.token).toBe('')
  })

  it('未过期 → 不触发主动续期，正常放行', async() => {
    UserModule.SetToken(makeJwt(VALID))

    await pushQuietly('/404')

    expect(router.currentRoute.path).toBe('/404')
    expect(mockRefresh).not.toHaveBeenCalled()
    expect(mockGetUserInfo).toHaveBeenCalledTimes(1)
  })

  it('token 未过期但 GetUserInfo 失败 → 原有兜底登出仍生效', async() => {
    UserModule.SetToken(makeJwt(VALID))
    mockGetUserInfo.mockRejectedValue(new Error('boom'))

    await pushQuietly('/recycle-bin')

    expect(router.currentRoute.path).toBe('/login')
    expect(UserModule.token).toBe('')
  })
})
