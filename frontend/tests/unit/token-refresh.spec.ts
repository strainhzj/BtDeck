import { refreshTokensOnce, resetRefreshState, RefreshDependencies } from '@/utils/token-refresh'

/**
 * 401 静默续期编排回归（verified-bugfix-remediation W6-1）：
 * - 单飞：并发 401 只发一次 /auth/refresh
 * - 刷新成功：返回新令牌对并持久化（使用即轮换）
 * - 刷新失败/无 refresh token：返回 null（调用方登出）
 * - 连续两次失败后状态复位（下次 401 可重试）
 */

function makeDeps(overrides: Partial<RefreshDependencies> = {}): {
  deps: RefreshDependencies
  calls: { doRefresh: jest.Mock, saveTokens: jest.Mock, getRefreshToken: jest.Mock }
} {
  const doRefresh = jest.fn(async() => ({ accessToken: 'new-access', refreshToken: 'new-refresh' }))
  const getRefreshToken = jest.fn(() => 'old-refresh')
  const saveTokens = jest.fn()
  const deps: RefreshDependencies = {
    doRefresh,
    getRefreshToken,
    saveTokens,
    ...overrides
  }
  return { deps, calls: { doRefresh, saveTokens, getRefreshToken } }
}

describe('refreshTokensOnce 单飞续期编排', () => {
  beforeEach(() => {
    resetRefreshState()
  })

  it('刷新成功返回新令牌对并持久化', async() => {
    const { deps, calls } = makeDeps()
    const pair = await refreshTokensOnce(deps)
    expect(pair).toEqual({ accessToken: 'new-access', refreshToken: 'new-refresh' })
    expect(calls.doRefresh).toHaveBeenCalledWith('old-refresh')
    expect(calls.saveTokens).toHaveBeenCalledWith(pair)
  })

  it('并发调用共享同一 refresh Promise（单飞）', async() => {
    const { deps, calls } = makeDeps()
    const [r1, r2, r3] = await Promise.all([
      refreshTokensOnce(deps),
      refreshTokensOnce(deps),
      refreshTokensOnce(deps)
    ])
    expect(r1).toEqual(r2)
    expect(r2).toEqual(r3)
    expect(calls.doRefresh).toHaveBeenCalledTimes(1)
  })

  it('刷新失败返回 null 且不持久化', async() => {
    const { deps, calls } = makeDeps({
      doRefresh: jest.fn(async() => {
        throw new Error('refresh token 已撤销')
      })
    })
    const result = await refreshTokensOnce(deps)
    expect(result).toBeNull()
    expect(calls.saveTokens).not.toHaveBeenCalled()
  })

  it('无 refresh token 时直接返回 null', async() => {
    const { deps, calls } = makeDeps({ getRefreshToken: jest.fn(() => '') })
    const result = await refreshTokensOnce(deps)
    expect(result).toBeNull()
    expect(calls.doRefresh).not.toHaveBeenCalled()
  })

  it('失败后状态复位：下一次调用可重试', async() => {
    let fail = true
    const { deps } = makeDeps({
      doRefresh: jest.fn(async() => {
        if (fail) {
          fail = false
          throw new Error('first fail')
        }
        return { accessToken: 'ok', refreshToken: 'ok-r' }
      })
    })
    expect(await refreshTokensOnce(deps)).toBeNull()
    expect(await refreshTokensOnce(deps)).toEqual({ accessToken: 'ok', refreshToken: 'ok-r' })
  })
})
