/**
 * 401 静默续期编排（双令牌体系 W6-1 + 跨标签竞态修复）
 *
 * 从 request.ts 拦截器中抽出的可注入依赖纯编排模块（仿 error-normalize 先例，
 * 便于单测；真实 axios 层只负责"401 时调用本模块并按其返回值处理"）。
 *
 * 语义：
 * - 单飞：并发 401 共享同一个 refresh Promise，只发一次刷新批（含内部重试）
 * - 三态结果：
 *   - renewed：刷新成功，令牌对已持久化（后端使用即轮换），调用方重放原请求
 *   - rejected：refresh 血统确证死亡（后端明确 401 / 无 refresh token），
 *     调用方走登出（但不应清共享 refresh cookie——见 request.ts 说明）
 *   - transient：网络抖动/服务端瞬时错误，调用方保留会话现场等待自愈
 * - cookie 最新值有限重试：多标签共享同一 refresh cookie 且后端使用即轮换，
 *   本标签 definite 失败可能只因他标签刚刚轮换成功——重读 cookie 发现值已变
 *   时用新值再刷（上限 3 次防活锁）
 * - /auth/refresh 自身 401 由调用方按 isLoginRequest 豁免，不进入本模块
 */

export interface TokenPair {
  accessToken: string
  refreshToken: string
}

export type RefreshOutcome =
  | { status: 'renewed', pair: TokenPair }
  | { status: 'rejected' }
  | { status: 'transient', error: unknown }

export interface RefreshDependencies {
  /** 发起 /auth/refresh 请求，成功返回新令牌对，失败抛错 */
  doRefresh(refreshToken: string): Promise<TokenPair>
  /** 读取当前 refresh token（生产实现读 cookie，多标签间共享最新值） */
  getRefreshToken(): string
  /** 持久化新令牌对 */
  saveTokens(pair: TokenPair): void
  /**
   * 判定刷新失败是否"确证死亡"（后端明确 401：业务码 401 或 HTTP 401）。
   * 其余失败（网络断连/超时/5xx/响应契约异常）视为瞬时，保留会话现场。
   */
  isDefiniteFailure(err: unknown): boolean
}

/** 同一刷新批内的最大尝试次数（含首次）：cookie 每轮都被他标签更新仍失败时按死亡收敛 */
const MAX_REFRESH_ATTEMPTS = 3

let refreshPromise: Promise<RefreshOutcome> | null = null

/** 重置单飞状态（测试用；页面刷新后模块状态自然重置） */
export function resetRefreshState(): void {
  refreshPromise = null
}

/**
 * 单飞刷新入口（含 cookie 最新值有限重试）。
 *
 * @returns renewed / rejected / transient 三态结果，调用方按状态分流
 */
export function refreshTokensOnce(deps: RefreshDependencies): Promise<RefreshOutcome> {
  if (refreshPromise) {
    return refreshPromise
  }

  const attempt = async(): Promise<RefreshOutcome> => {
    for (let i = 0; i < MAX_REFRESH_ATTEMPTS; i++) {
      const refreshToken = deps.getRefreshToken()
      // 无 refresh token：无望续期，确证死亡（不得归 transient——
      // "不清 token 也不跳转"会让会话卡死在半失效状态）
      if (!refreshToken) {
        return { status: 'rejected' }
      }

      try {
        const pair = await deps.doRefresh(refreshToken)
        deps.saveTokens(pair)
        return { status: 'renewed', pair }
      } catch (err) {
        if (!deps.isDefiniteFailure(err)) {
          // 网络抖动/服务端瞬时错误：保留现场，下个请求/导航再试
          return { status: 'transient', error: err }
        }
      }

      // 后端明确拒绝。cookie 已被他标签轮换更新 → 追新值再刷；
      // 值未变 → 本标签持有的令牌血统确证死亡
      if (refreshToken === deps.getRefreshToken()) {
        return { status: 'rejected' }
      }
    }
    // 超过重试上限（cookie 每轮都在变仍未成功）：按死亡收敛，交调用方登出
    return { status: 'rejected' }
  }

  refreshPromise = attempt().finally(() => {
    refreshPromise = null
  })

  return refreshPromise
}
