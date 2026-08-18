import { getToken, removeRefreshToken } from '@/utils/cookies'
import {
  getTokenExp,
  isTokenExpired,
  buildLoginRedirectTarget,
  syncTokenFromCookie,
  initSessionWatch
} from '@/utils/session'
import { UserModule } from '@/store/modules/user'

/**
 * 会话主动维护回归（双令牌 W6 伴随修复）：
 * - isTokenExpired：JWT exp 解析（过期/未过期/畸形不误杀）
 * - buildLoginRedirectTarget：hash 模式登录跳转 URL 构造
 * - syncTokenFromCookie：跨标签页令牌快照回同步三分支
 * - initSessionWatch：标签页重新可见/聚焦时的同步与登出跳转
 */

jest.mock('element-ui', () => ({ Message: jest.fn() }))

jest.mock('@/api/users', () => ({
  login: jest.fn(),
  logout: jest.fn(),
  getUserInfo: jest.fn(),
  refreshAccessToken: jest.fn(),
  changePassword: jest.fn()
}))

jest.mock('@/utils/cookies', () => ({
  getToken: jest.fn(),
  setToken: jest.fn(),
  removeToken: jest.fn(),
  getRefreshToken: jest.fn(),
  setRefreshToken: jest.fn(),
  removeRefreshToken: jest.fn(),
  getUserId: jest.fn(() => ''),
  setUserId: jest.fn(),
  removeUserId: jest.fn(),
  getStorage: jest.fn(),
  setStorage: jest.fn()
}))

const mockGetToken = getToken as jest.MockedFunction<typeof getToken>

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

function makeJwt(payload: object): string {
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.sig`
}

describe('getTokenExp / isTokenExpired', () => {
  it('解析有效 JWT 的 exp', () => {
    const token = makeJwt({ exp: 1900000000 })
    expect(getTokenExp(token)).toBe(1900000000)
  })

  it('exp 已过期为 expired（含提前量）', () => {
    const now = 1800000000000
    expect(isTokenExpired(makeJwt({ exp: 1799999999 }), now)).toBe(true)
    // 距过期不足 30s 提前量：按已过期处理
    expect(isTokenExpired(makeJwt({ exp: (now + 10 * 1000) / 1000 }), now)).toBe(true)
  })

  it('exp 未到且超出提前量为未过期', () => {
    const now = 1800000000000
    expect(isTokenExpired(makeJwt({ exp: (now + 60 * 1000) / 1000 }), now)).toBe(false)
  })

  it('非 JWT / 无 exp / 畸形 payload 不误杀（返回 null / false，交回 401 兜底）', () => {
    expect(getTokenExp('')).toBeNull()
    expect(getTokenExp('not-a-jwt')).toBeNull()
    expect(getTokenExp(makeJwt({}))).toBeNull()
    expect(getTokenExp('a.!!!.c')).toBeNull()
    expect(isTokenExpired('opaque-token')).toBe(false)
  })
})

describe('buildLoginRedirectTarget', () => {
  it('hash 模式下从 hash 内取真实路由并编码', () => {
    expect(buildLoginRedirectTarget('#/torrents?page=2', '/')).toBe(
      `/#/login?redirect=${encodeURIComponent('/torrents?page=2')}`
    )
  })

  it('hash 为空时退化为 pathname（history 部署/首屏）', () => {
    expect(buildLoginRedirectTarget('', '/some/path')).toBe(
      `/#/login?redirect=${encodeURIComponent('/some/path')}`
    )
  })

  it('两者皆空时回退首页', () => {
    expect(buildLoginRedirectTarget('', '')).toBe(
      `/#/login?redirect=${encodeURIComponent('/')}`
    )
  })
})

describe('syncTokenFromCookie', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    UserModule.ResetToken()
  })

  it('cookie 新于内存快照（他标签登录/续期）→ 回写并返回 synced', () => {
    UserModule.SetToken('old-access')
    mockGetToken.mockReturnValue('new-access')

    expect(syncTokenFromCookie()).toBe('synced')
    expect(UserModule.token).toBe('new-access')
  })

  it('cookie 已空而内存仍有 token（他标签登出/过期清理）→ 返回 logged-out', () => {
    UserModule.SetToken('stale-access')
    mockGetToken.mockReturnValue(undefined as unknown as string)

    expect(syncTokenFromCookie()).toBe('logged-out')
    expect(UserModule.token).toBe('stale-access')
  })

  it('令牌一致或均空 → noop 不动状态', () => {
    mockGetToken.mockReturnValue('same-token')
    UserModule.SetToken('same-token')
    expect(syncTokenFromCookie()).toBe('noop')

    // 均空：先清内存快照再验证
    mockGetToken.mockReturnValue(undefined as unknown as string)
    UserModule.ResetToken()
    expect(syncTokenFromCookie()).toBe('noop')
  })
})

describe('initSessionWatch', () => {
  // 监听器只注册一次：重复注册会让同一事件触发多次同步
  beforeAll(() => {
    initSessionWatch()
  })

  it('标签页重新可见：cookie 新于内存（他标签登录/续期）→ 回同步新令牌', () => {
    UserModule.ResetToken()
    UserModule.SetToken('old-access')
    mockGetToken.mockReturnValue('new-access')

    document.dispatchEvent(new Event('visibilitychange'))

    expect(UserModule.token).toBe('new-access')
  })

  it('标签页获得焦点且会话已在别处结束（cookie 已空）→ 统一登出跳转（ExpireSession 保留 refresh cookie）', () => {
    UserModule.ResetToken()
    UserModule.SetToken('stale-access')
    mockGetToken.mockReturnValue(undefined as unknown as string)
    window.location.hash = ''
    // 复位期间的 cookie mock 调用不计入断言
    jest.clearAllMocks()

    window.dispatchEvent(new Event('focus'))

    expect(UserModule.token).toBe('')
    expect(window.location.hash).toContain('#/login?redirect=')
    // 登出跳转走 ExpireSession：不清 refresh cookie（跨标签竞态加固语义一致）
    expect(removeRefreshToken).not.toHaveBeenCalled()
  })
})
