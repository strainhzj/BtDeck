import router from '@/router'

/**
 * router NavigationFailure 静默补丁回归：
 * vue-router 3.1+ 会把"被守卫改道/中止/重复"的导航以 rejected promise 返回。
 * 登录页（login/index.vue）把 router.push 与登录请求包在同一个 try/catch 中，
 * rejection 一旦上抛，vue-router 内部英文消息（"Redirected when going from ...
 * via a navigation guard"）会被 $message.error 原样弹出（生产杂音，2026-08-19
 * 桌面版强制改密流程实测报告）。补丁后 push/replace 对 isNavigationFailure
 * 一律 resolve，真实异常仍上抛。
 */

const TARGET_ROUTE = '/404'

// 守卫改道后，目标路由（懒加载组件）的确认导航晚于原导航的 promise 结算；
// 在宏任务边界上等待其落定后再断言，避免微任务深度敏感。
const flush = (): Promise<void> => new Promise(resolve => setTimeout(resolve, 0))

describe('router NavigationFailure 静默补丁', () => {
  const removeGuard = router.beforeEach((to, from, next) => {
    // 模拟强制改密守卫：非白名单导航改道到登录页（真实守卫的白名单语义，
    // 避免把 /login 自身也改道造成自指循环）
    if (to.path === '/login') {
      next()
      return
    }
    next({ path: '/login', replace: true })
  })

  afterAll(() => {
    removeGuard()
  })

  it('守卫改道（redirected）时 push 不再 reject，且导航落到守卫目标', async() => {
    await expect(router.push(TARGET_ROUTE)).resolves.toBeTruthy()
    await flush()
    expect(router.currentRoute.path).toBe('/login')
  })

  it('守卫改道（redirected）时 replace 不再 reject', async() => {
    await expect(router.replace(TARGET_ROUTE)).resolves.toBeTruthy()
    await flush()
    expect(router.currentRoute.path).toBe('/login')
  })

  it('守卫中止（next(false) / aborted）时 push 同样静默', async() => {
    removeGuard()
    const removeAbortGuard = router.beforeEach((to, from, next) => {
      next(false)
    })
    const before = router.currentRoute.path
    await expect(router.push(TARGET_ROUTE)).resolves.toBeTruthy()
    expect(router.currentRoute.path).toBe(before)
    removeAbortGuard()
  })
})
