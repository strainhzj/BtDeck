/**
 * 会话状态主动维护（双令牌体系 W6 伴随修复）。
 *
 * 背景：401 静默续期只覆盖"恰好有 API 请求"的场景——会话过期在无轮询页面
 * 上无感知；且 Vuex 里的 token 是页面加载时的一次性快照，跨标签页登录/
 * 续期只写 cookie 与事发标签的内存，其余标签持续携带旧令牌（表现为
 * "重新登录后要手动刷新页面才生效"）。
 *
 * 本模块职责：
 * - isTokenExpired：纯解析 JWT exp 供路由守卫/可见性监听主动判断过期；
 *   格式异常一律视为未过期，交回 401 拦截器兜底，避免误杀会话
 * - buildLoginRedirectTarget：hash 模式感知的登录跳转 URL 纯构造
 * - syncTokenFromCookie：标签页重新可见时把 cookie 最新令牌同步回内存快照
 * - initSessionWatch：visibilitychange/focus 时执行上述同步
 */

import { UserModule } from '@/store/modules/user'
import { getToken } from '@/utils/cookies'
import { redirectToLogin } from '@/utils/request'

/** 临近过期的提前量：补偿前后端时钟偏差，避免"刚判断未过期、发请求即 401"的窄窗口 */
const DEFAULT_SKEW_MS = 30 * 1000

/** 解析 JWT payload 的 exp（秒级时间戳）。非 JWT/无 exp/解析失败返回 null。 */
export function getTokenExp(token: string): number | null {
  if (!token) {
    return null
  }
  const parts = token.split('.')
  if (parts.length !== 3) {
    return null
  }
  try {
    // base64url → base64：替换字母表并补齐 padding 后 atob
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
    const payload = JSON.parse(atob(padded)) as { exp?: unknown }
    return typeof payload.exp === 'number' ? payload.exp : null
  } catch {
    return null
  }
}

/**
 * access token 是否已过期（含时钟偏差提前量）。
 * 无法解析 exp 时返回 false：主动检查只做提前量，最终裁决权仍在后端 401。
 */
export function isTokenExpired(
  token: string,
  nowMs: number = Date.now(),
  skewMs: number = DEFAULT_SKEW_MS
): boolean {
  const exp = getTokenExp(token)
  if (exp === null) {
    return false
  }
  return exp * 1000 - skewMs <= nowMs
}

/**
 * 构造 hash 模式感知的登录页跳转 URL。
 * 真实路由在 location.hash 内（如 '#/torrents?page=2'），pathname 恒为部署根，
 * 必须从 hash 取 redirect 目标；hash 为空（history 部署/首屏）退化为 pathname。
 */
export function buildLoginRedirectTarget(currentHash: string, currentPathname: string): string {
  const route =
    currentHash && currentHash.length > 1
      ? currentHash.slice(1)
      : currentPathname || '/'
  return `/#/login?redirect=${encodeURIComponent(route || '/')}`
}

export type SessionSyncResult = 'noop' | 'synced' | 'logged-out'

/**
 * 将 cookie 中的最新令牌同步回 Vuex 内存快照。
 * - 'synced'：cookie 新于内存（他标签登录/续期），已回写，新令牌立即生效
 * - 'logged-out'：cookie 已空而内存仍有 token（他标签登出/过期清理），需登出
 * - 'noop'：一致或均空
 */
export function syncTokenFromCookie(): SessionSyncResult {
  const cookieToken = getToken() || ''
  if (cookieToken && cookieToken !== UserModule.token) {
    UserModule.SetToken(cookieToken)
    return 'synced'
  }
  if (!cookieToken && UserModule.token) {
    return 'logged-out'
  }
  return 'noop'
}

/**
 * 注册标签页会话监听：页面重新可见/获得焦点时同步令牌快照。
 * 检测到会话已在别处结束时走统一的登出跳转。main.ts 启动时调用一次。
 */
export function initSessionWatch(): void {
  const resync = () => {
    if (syncTokenFromCookie() === 'logged-out') {
      redirectToLogin()
    }
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      resync()
    }
  })
  window.addEventListener('focus', resync)
}
