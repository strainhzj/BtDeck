import router from '@/router'
import type { RawLocation } from 'vue-router'
import NProgress from 'nprogress'
import '@/permission'
import { UserModule } from '@/store/modules/user'
import { getUserInfo, refreshAccessToken } from '@/api/users'
import { getUserId, removeRefreshToken } from '@/utils/cookies'
import { ApiError } from '@/types/api'

/**
 * 路由守卫主动过期检查回归（双令牌 W6 伴随修复 + 跨标签竞态修复）：
 * 通过真实 router 导航（目标 /404，不经过 Layout）验证守卫分支：
 * - access token 过期 + 续期成功 → 放行，且内存令牌已更新
 * - access token 过期 + 续期确证失败 → 登出并跳登录（ExpireSession：
 *   保留 refresh cookie，防跨标签竞态清掉他标签有效令牌），redirect 保留目标路由
 * - 过期 + 目标即 /login → 直接放行登录页（无 redirect 自指循环）
 * - 过期 + 续期瞬时网络失败 + roles 未加载 → 中止导航保留会话（不登出）
 * - 过期 + 续期瞬时网络失败 + roles 已加载 → 放行目标路由（页面请求自愈）
 * - 未过期 → 不触发主动续期（refreshAccessToken 不被调用）
 * - token 有效但 GetUserInfo 失败 → 原有兜底登出仍生效（保留 refresh cookie）
 * - token 有效 + GetUserInfo 网络失败 → 中止导航保留会话（不登出）
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

/** 网络层失败（无 HTTP 响应）经拦截器归一化后的 ApiError 形态 */
const networkApiError = new ApiError('网络连接失败，请检查网络连接', { code: '0', httpStatus: 0 })

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
  // 先复位会话（内部会调用 cookies mock 的 remove*），再清调用记录——
  // 否则"removeRefreshToken 未被调用"断言会吃到复位期间的调用
  UserModule.ResetToken()
  jest.clearAllMocks()
  ;(getUserId as jest.Mock).mockReturnValue('')
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

  it('过期 + 续期失败 → 登出并跳登录页，redirect 保留目标路由；refresh cookie 保留（ExpireSession）', async() => {
    UserModule.SetToken(makeJwt(EXPIRED))
    // api mock 边界在拦截器之后：后端明确拒绝应以拦截器归一化的 ApiError 401 拒绝
    mockRefresh.mockRejectedValue(new ApiError('已撤销', { code: '401', httpStatus: 200 }))

    await pushQuietly('/orphan-files')

    expect(router.currentRoute.path).toBe('/login')
    expect(router.currentRoute.query.redirect).toBe('/orphan-files')
    expect(UserModule.token).toBe('')
    // 跨标签竞态加固：被动登出不得清共享 refresh cookie
    expect(removeRefreshToken).not.toHaveBeenCalled()
    // 续期失败直接登出，不应再走 GetUserInfo
    expect(mockGetUserInfo).not.toHaveBeenCalled()
  })

  it('过期 + 续期瞬时网络失败 + roles 未加载 → 中止导航保留会话（不登出不清 cookie）', async() => {
    UserModule.SetToken(makeJwt(EXPIRED))
    mockRefresh.mockRejectedValue(networkApiError)

    // next(false) 中止导航时 afterEach 不触发：手动 NProgress.done 是唯一收尾，
    // 缺失即进度条悬挂（回归锚点——审查抓出的必改项）
    const doneSpy = jest.spyOn(NProgress, 'done')

    await pushQuietly('/404')

    expect(doneSpy.mock.calls.length).toBeGreaterThanOrEqual(1)
    doneSpy.mockRestore()

    // next(false) 中止导航：停留在 beforeEach 复位的 /login
    expect(router.currentRoute.path).toBe('/login')
    // 会话现场完整保留：token 未被清、refresh cookie 未被动、未跳登录 redirect
    expect(UserModule.token).toBe(makeJwt(EXPIRED))
    expect(removeRefreshToken).not.toHaveBeenCalled()
    expect(router.currentRoute.query.redirect).toBeUndefined()
  })

  it('过期 + 续期瞬时网络失败 + roles 已加载 → 放行目标路由（页面请求自愈续期）', async() => {
    // 第一步：用有效令牌完成一次导航，加载 roles
    UserModule.SetToken(makeJwt(VALID))
    await pushQuietly('/404')
    expect(router.currentRoute.path).toBe('/404')

    // 第二步：令牌过期 + 续期网络抖动，但 roles 已在 → 守卫放行
    UserModule.SetToken(makeJwt(EXPIRED))
    mockRefresh.mockRejectedValue(networkApiError)

    await pushQuietly('/recycle-bin')

    expect(router.currentRoute.path).toBe('/recycle-bin')
    expect(UserModule.token).toBe(makeJwt(EXPIRED))
    expect(removeRefreshToken).not.toHaveBeenCalled()
  })

  it('过期 + 目标即 /login → 直接放行登录页，无 redirect 自指（防守卫循环）', async() => {
    UserModule.SetToken(makeJwt(EXPIRED))
    mockRefresh.mockRejectedValue(new ApiError('已撤销', { code: '401', httpStatus: 200 }))

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

  it('token 未过期但 GetUserInfo 失败 → 原有兜底登出仍生效（ExpireSession 保留 refresh cookie）', async() => {
    UserModule.SetToken(makeJwt(VALID))
    mockGetUserInfo.mockRejectedValue(new Error('boom'))

    await pushQuietly('/recycle-bin')

    expect(router.currentRoute.path).toBe('/login')
    expect(UserModule.token).toBe('')
    expect(removeRefreshToken).not.toHaveBeenCalled()
  })

  it('token 未过期 + GetUserInfo 网络失败 → 中止导航保留会话（不升级为登出）', async() => {
    UserModule.SetToken(makeJwt(VALID))
    mockGetUserInfo.mockRejectedValue(networkApiError)

    await pushQuietly('/recycle-bin')

    // next(false) 中止导航：停留在 /login，token 与 cookie 均保留
    expect(router.currentRoute.path).toBe('/login')
    expect(UserModule.token).toBe(makeJwt(VALID))
    expect(removeRefreshToken).not.toHaveBeenCalled()
    expect(router.currentRoute.query.redirect).toBeUndefined()
  })
})
