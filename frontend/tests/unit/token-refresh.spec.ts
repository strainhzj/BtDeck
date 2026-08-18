import { refreshTokensOnce, resetRefreshState, RefreshDependencies, RefreshOutcome } from '@/utils/token-refresh'

/**
 * 401 静默续期编排回归（verified-bugfix-remediation W6-1 + 跨标签竞态修复）：
 * - 三态结果：renewed（成功持久化）/ rejected（血统确证死亡：后端明确 401
 *   或无 refresh token）/ transient（网络抖动等瞬时失败，保留现场）
 * - 单飞：并发 401 只发一次刷新批（含内部重试）
 * - cookie 最新值有限重试：definite 失败后他标签已轮换 cookie → 追新值再刷；
 *   cookie 未变 → rejected；上限 3 次防活锁
 */

/** 带 definite 标记的模拟"后端明确 401"错误（生产侧为 ApiError code '401'） */
function definiteError(msg = '已撤销'): Error & { definite: boolean } {
  const err = new Error(msg) as Error & { definite: boolean }
  err.definite = true
  return err
}

type DepMocks = {
  doRefresh: jest.Mock
  getRefreshToken: jest.Mock
  saveTokens: jest.Mock
  isDefiniteFailure: jest.Mock
}

function makeDeps(overrides: Partial<RefreshDependencies> = {}): {
  deps: RefreshDependencies
  calls: DepMocks
} {
  const defaults: DepMocks = {
    doRefresh: jest.fn(async() => ({ accessToken: 'new-access', refreshToken: 'new-refresh' })),
    getRefreshToken: jest.fn(() => 'old-refresh'),
    saveTokens: jest.fn(),
    isDefiniteFailure: jest.fn((err: unknown) => Boolean((err as { definite?: boolean })?.definite))
  }
  // calls 必须引用合并后的最终实现（overrides 替换过的成员），
  // 否则断言落在未使用的默认 mock 上（0 次调用假失败）
  const deps = { ...defaults, ...overrides } as RefreshDependencies & DepMocks
  return { deps, calls: deps }
}

const outcomeStatus = (outcome: RefreshOutcome): string => outcome.status

describe('refreshTokensOnce 三态续期编排', () => {
  beforeEach(() => {
    resetRefreshState()
  })

  it('刷新成功 → renewed，新令牌对持久化（使用即轮换）', async() => {
    const { deps, calls } = makeDeps()
    const outcome = await refreshTokensOnce(deps)
    expect(outcomeStatus(outcome)).toBe('renewed')
    if (outcome.status === 'renewed') {
      expect(outcome.pair).toEqual({ accessToken: 'new-access', refreshToken: 'new-refresh' })
    }
    expect(calls.doRefresh).toHaveBeenCalledWith('old-refresh')
    expect(calls.saveTokens).toHaveBeenCalledWith({ accessToken: 'new-access', refreshToken: 'new-refresh' })
  })

  it('并发调用共享同一 refresh Promise（单飞，含内部重试整体只执行一批）', async() => {
    const { deps, calls } = makeDeps()
    const [r1, r2, r3] = await Promise.all([
      refreshTokensOnce(deps),
      refreshTokensOnce(deps),
      refreshTokensOnce(deps)
    ])
    expect(outcomeStatus(r1)).toBe('renewed')
    expect(r1).toEqual(r2)
    expect(r2).toEqual(r3)
    expect(calls.doRefresh).toHaveBeenCalledTimes(1)
  })

  it('definite 失败且 cookie 未变 → rejected（本标签血统确证死亡）', async() => {
    const { deps, calls } = makeDeps({
      doRefresh: jest.fn(async() => { throw definiteError() })
    })
    const outcome = await refreshTokensOnce(deps)
    expect(outcomeStatus(outcome)).toBe('rejected')
    expect(calls.saveTokens).not.toHaveBeenCalled()
    // cookie 未变时不做无谓重试
    expect(calls.doRefresh).toHaveBeenCalledTimes(1)
  })

  it('definite 失败但 cookie 已被他标签轮换 → 追新值再刷成功 → renewed', async() => {
    // 模拟：首次用旧值被拒（他标签刚轮换成功），重读 cookie 已是新值
    // 序列 = 首次读取(旧) → definite 后重读(新) → 第二轮循环读取(新)
    const cookieValues = ['old-refresh', 'new-refresh', 'new-refresh']
    const doRefresh = jest.fn(async(rt: string) => {
      if (rt === 'old-refresh') {
        throw definiteError('refresh token 无效、已撤销或已过期')
      }
      return { accessToken: 'rotated-access', refreshToken: 'rotated-refresh' }
    })
    const { deps, calls } = makeDeps({
      doRefresh,
      getRefreshToken: jest.fn(() => cookieValues.shift() || 'new-refresh')
    })

    const outcome = await refreshTokensOnce(deps)

    expect(outcomeStatus(outcome)).toBe('renewed')
    expect(calls.doRefresh).toHaveBeenCalledTimes(2)
    expect(calls.doRefresh).toHaveBeenNthCalledWith(1, 'old-refresh')
    expect(calls.doRefresh).toHaveBeenNthCalledWith(2, 'new-refresh')
    expect(calls.saveTokens).toHaveBeenCalledWith({ accessToken: 'rotated-access', refreshToken: 'rotated-refresh' })
  })

  it('无 refresh token → rejected（不发请求；不得归 transient 防不清不跳僵死）', async() => {
    const { deps, calls } = makeDeps({ getRefreshToken: jest.fn(() => '') })
    const outcome = await refreshTokensOnce(deps)
    expect(outcomeStatus(outcome)).toBe('rejected')
    expect(calls.doRefresh).not.toHaveBeenCalled()
  })

  it('网络类失败（非 definite）→ transient 携带原始错误，且不重试', async() => {
    const networkError = new Error('网络连接失败，请检查网络连接')
    const { deps, calls } = makeDeps({
      doRefresh: jest.fn(async() => { throw networkError })
    })
    const outcome = await refreshTokensOnce(deps)
    expect(outcomeStatus(outcome)).toBe('transient')
    if (outcome.status === 'transient') {
      expect(outcome.error).toBe(networkError)
    }
    expect(calls.doRefresh).toHaveBeenCalledTimes(1)
  })

  it('cookie 每轮都变仍持续 definite 失败 → 达上限后按 rejected 收敛（防活锁）', async() => {
    let seq = 0
    const { deps, calls } = makeDeps({
      doRefresh: jest.fn(async() => { throw definiteError() }),
      getRefreshToken: jest.fn(() => `refresh-${seq++}`) // 每次读取值都不同
    })
    const outcome = await refreshTokensOnce(deps)
    expect(outcomeStatus(outcome)).toBe('rejected')
    // 上限 3 次（MAX_REFRESH_ATTEMPTS）
    expect(calls.doRefresh).toHaveBeenCalledTimes(3)
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
    // 首次为瞬时失败（非 definite）
    expect(outcomeStatus(await refreshTokensOnce(deps))).toBe('transient')
    expect(outcomeStatus(await refreshTokensOnce(deps))).toBe('renewed')
  })
})
