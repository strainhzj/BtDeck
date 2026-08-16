/**
 * 401 静默续期编排（双令牌体系 W6-1）
 *
 * 从 request.ts 拦截器中抽出的可注入依赖纯编排模块（仿 error-normalize 先例，
 * 便于单测；真实 axios 层只负责"401 时调用本模块并按其返回值处理"）。
 *
 * 语义：
 * - 单飞：并发 401 共享同一个 refresh Promise，只发一次 /auth/refresh
 * - 刷新成功：更新 access + refresh（后端使用即轮换），重放原请求一次
 * - 刷新失败：返回 null，调用方走原登出流程（redirectToLogin）
 * - /auth/refresh 自身 401 绝不进入刷新循环（由调用方按 isLoginRequest 豁免）
 */

export interface TokenPair {
  accessToken: string
  refreshToken: string
}

export interface RefreshDependencies {
  /** 发起 /auth/refresh 请求，成功返回新令牌对，失败抛错 */
  doRefresh(refreshToken: string): Promise<TokenPair>
  /** 读取当前 refresh token */
  getRefreshToken(): string
  /** 持久化新令牌对 */
  saveTokens(pair: TokenPair): void
}

let refreshPromise: Promise<TokenPair | null> | null = null

/** 重置单飞状态（测试用；页面刷新后模块状态自然重置） */
export function resetRefreshState(): void {
  refreshPromise = null
}

/**
 * 单飞刷新入口。
 * @returns 刷新成功返回新令牌对；失败/无 refresh token 返回 null
 */
export function refreshTokensOnce(deps: RefreshDependencies): Promise<TokenPair | null> {
  if (refreshPromise) {
    return refreshPromise
  }

  const refreshToken = deps.getRefreshToken()
  if (!refreshToken) {
    refreshPromise = Promise.resolve(null)
    // 无 refresh token 无法续期：立即复位（下次 401 再试没有意义，直接登出）
    queueMicrotask(() => {
      refreshPromise = null
    })
    return refreshPromise
  }

  refreshPromise = deps
    .doRefresh(refreshToken)
    .then((pair) => {
      deps.saveTokens(pair)
      return pair
    })
    .catch(() => {
      // 刷新失败（token 失效/网络）：清空单飞状态，让调用方登出
      return null
    })
    .finally(() => {
      refreshPromise = null
    })

  return refreshPromise
}
