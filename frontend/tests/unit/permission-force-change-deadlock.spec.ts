/**
 * W9 强制改密路由回归守护（生产事故修复后的行为锚定）。
 *
 * 事故回顾：重新登录后点击任何页面 URL 都变成 /#/settings?forceChange=1
 * 且设置页无法进入（死锁）——守卫重定向目标/白名单写的是父路径 /settings
 * （只挂 Layout，内容区空占位），真实改密页在 /settings/index 又被弹回。
 *
 * 修复后本文件锚定的行为（真实 router.ts 路由表 + 真实 permission.ts 守卫）：
 * 1. 拦截落点是真实改密页 /settings/index?forceChange=1 且组件渲染可达
 *    （改密表单可见 = 用户可自救，死锁解除）
 * 2. 登录后/F5 后的首次导航（roles 为空走 GetUserInfo 分支）同样被拦截
 * 3. 父路径 /settings 由路由表 redirect 解析到 /settings/index，内容非空
 * 4. 改密成功（标志清除）后业务页恢复可达（闭环）
 *
 * 后端半边（启动置位、/user/info 下发标志）见
 * backend/tests/api/test_w9_force_change_reproduction.py 与
 * backend/tests/api/test_login_throttle_and_change_password.py。
 */
import Vue, { CreateElement, VNode } from 'vue'

// ---- 外围依赖 mock（守卫与路由表本身保持真实） ----------------------------

const mockUserModule = {
  token: 'regression-access-token',
  roles: [] as string[],
  mustChangePassword: false,
  GetUserInfo: jest.fn().mockResolvedValue(undefined),
  ResetToken: jest.fn()
}

jest.mock('@/store/modules/user', () => ({ UserModule: mockUserModule }))
jest.mock('@/utils/session', () => ({ isTokenExpired: jest.fn(() => false) }))
jest.mock('@/utils/request', () => ({ trySilentRefresh: jest.fn(async() => true) }))
jest.mock('nprogress', () => ({ configure: jest.fn(), start: jest.fn(), done: jest.fn() }))
jest.mock('nprogress/nprogress.css', () => ({}))
jest.mock('element-ui', () => ({ Message: { warning: jest.fn(), error: jest.fn(), success: jest.fn() } }))
jest.mock('@/utils/deployment-recovery', () => ({ recoverFromChunkLoadError: jest.fn() }))

// Layout 必须内嵌 router-view，子路由（内容区）才有地方渲染
// （__esModule: true 不可省——否则 ts-jest interop 会把 { default } 包裹
//  对象整体当成组件交给路由表，组件渲染为空占位）
jest.mock('@/layout/index.vue', () => ({
  __esModule: true,
  default: {
    name: 'LayoutMock',
    render: (h: CreateElement): VNode => h('div', { class: 'mock-layout' }, [h('router-view')])
  }
}))

const viewStub = (name: string, marker: string) => ({
  __esModule: true,
  default: {
    name,
    render: (h: CreateElement): VNode => h('div', { class: marker }, `${marker} body`)
  }
})

jest.mock('@/views/settings/index.vue', () => viewStub('SettingsPageMock', 'mock-settings-page'))
// /torrents/index 路由挂的真实组件是 TorrentViewSwitcher（非 torrents/index.vue）
jest.mock('@/views/torrents/TorrentViewSwitcher.vue', () => viewStub('TorrentsPageMock', 'mock-torrents-page'))
jest.mock('@/views/dashboard/index.vue', () => viewStub('DashboardPageMock', 'mock-dashboard-page'))
jest.mock('@/views/login/index.vue', () => viewStub('LoginPageMock', 'mock-login-page'))
jest.mock('@/views/404.vue', () => viewStub('NotFoundMock', 'mock-404-page'))

// ---- 真实路由表 + 真实守卫 --------------------------------------------------

import router from '@/router'
import '@/permission'
import { Message } from 'element-ui'

const mockWarning = Message.warning as jest.Mock

const flushNavigation = async(): Promise<void> => {
  // 重定向链（守卫 next(location) / record redirect 触发的二次导航）跨微任务，
  // 双 flush 确保收敛
  for (let i = 0; i < 2; i++) {
    await new Promise<void>(resolve => { setTimeout(resolve, 0) })
    await Vue.nextTick()
  }
}

const navigate = async(path: string): Promise<void> => {
  // 守卫重定向会让原始 push 以 NavigationFailure 结束，属于预期行为
  await router.push(path).catch(() => undefined)
  await flushNavigation()
}

// router 是模块级单例且 push 修补会吞 NavigationDuplicated——每个用例必须
// 从与目标 fullPath 互异的当前路由出发（先以 flag=false 落到起点页再置位），
// 否则重定向解析结果与当前路由相同会导致守卫根本不执行、断言空转通过
const startFrom = async(path: string): Promise<void> => {
  mockUserModule.roles = ['admin']
  mockUserModule.mustChangePassword = false
  await navigate(path)
  mockUserModule.mustChangePassword = true
}

describe('W9 强制改密路由（生产事故修复回归）', () => {
  let app: Vue
  let dateNowSpy: jest.SpyInstance<number>
  // 递增假时钟（步长 10s > 3s 节流窗）：守卫的节流时间戳是模块级、
  // 跨用例保留——tick 绝不在用例间重置（一旦归零，新用例时钟永远
  // 小于历史时间戳，全程被节流）；单调递增保证每用例首次拦截可弹。
  // 节流用例自行 override 固定时钟（取大于任何递增历史的值）
  let tick = 0

  beforeEach(() => {
    dateNowSpy = jest.spyOn(Date, 'now').mockImplementation(() => 1_000_000_000 + 10_000 * ++tick)
    mockWarning.mockClear()
    mockUserModule.token = 'regression-access-token'
    mockUserModule.roles = ['admin']
    mockUserModule.mustChangePassword = true
    const host = document.createElement('div')
    document.body.appendChild(host)
    app = new Vue({
      router,
      render: (h: CreateElement): VNode => h('router-view')
    })
    app.$mount(host)
  })

  afterEach(() => {
    dateNowSpy.mockRestore()
    app.$destroy()
    if (app.$el && app.$el.parentNode) {
      app.$el.parentNode.removeChild(app.$el)
    }
  })

  it('拦截：标志置位时业务页导航被弹到 /settings/index?forceChange=1 且改密页渲染可达', async() => {
    await startFrom('/dashboard')
    // 清掉 mount 初始导航触发的拦截提示，只断言本次点击菜单的反馈
    mockWarning.mockClear()

    await navigate('/torrents/index')

    // 落点是真实改密页（子路由），不再是空白的父路径——死锁解除的核心断言
    expect(router.currentRoute.path).toBe('/settings/index')
    expect(router.currentRoute.query.forceChange).toBe('1')
    expect(app.$el.innerHTML).toContain('mock-settings-page')
    expect(app.$el.innerHTML).not.toContain('mock-torrents-page')
    // 拦截时弹"先改密码"提示（用户点其它菜单被弹回时需要反馈）
    expect(mockWarning).toHaveBeenCalledTimes(1)
    const payload = mockWarning.mock.calls[0][0] as { message: string }
    expect(payload.message).toContain('请先修改密码')
  })

  it('拦截：登录后/F5 后首次导航（roles 为空走 GetUserInfo 分支）同样被拦截', async() => {
    await startFrom('/dashboard')

    // 模拟 F5 后的 store 状态：roles 清空、标志重置（token 仍在 cookie），
    // 真实 GetUserInfo 会填充 roles 并下发标志——事故前该分支放行一次业务页
    mockUserModule.roles = []
    mockUserModule.mustChangePassword = false
    mockUserModule.GetUserInfo.mockImplementationOnce(async() => {
      mockUserModule.roles = ['admin']
      mockUserModule.mustChangePassword = true
    })
    // 清掉 mount 初始导航触发的拦截提示，只断言本次首导航的反馈
    mockWarning.mockClear()

    await navigate('/torrents/index')

    expect(router.currentRoute.path).toBe('/settings/index')
    expect(router.currentRoute.query.forceChange).toBe('1')
    expect(app.$el.innerHTML).toContain('mock-settings-page')
    // 首导航拦截同样弹"先改密码"提示（与 roles 已就绪分支行为一致）
    expect(mockWarning).toHaveBeenCalledTimes(1)
    const payload = mockWarning.mock.calls[0][0] as { message: string }
    expect(payload.message).toContain('请先修改密码')
  })

  it('redirect：手输父路径 /settings 被路由表解析到 /settings/index，内容区非空', async() => {
    await startFrom('/dashboard')

    await navigate('/settings')

    // record redirect 在守卫前解析：to.path 已是子路径且在白名单内 → 放行；
    // 事故前该落点内容区是 <!----> 空占位
    expect(router.currentRoute.path).toBe('/settings/index')
    expect(router.currentRoute.query.forceChange).toBeUndefined()
    expect(app.$el.innerHTML).toContain('mock-settings-page')
    expect(app.$el.innerHTML).not.toBe('<!---->')
  })

  it('放行：手动直达真实改密页 /settings/index 不被弹回（事故前被白名单挡回）', async() => {
    await startFrom('/dashboard')

    await navigate('/settings/index')

    expect(router.currentRoute.path).toBe('/settings/index')
    expect(app.$el.innerHTML).toContain('mock-settings-page')
  })

  it('闭环：改密成功（标志清除）后业务页恢复可达', async() => {
    await startFrom('/dashboard')
    await navigate('/torrents/index')
    expect(router.currentRoute.path).toBe('/settings/index')

    // 模拟设置页改密成功后的 SetMustChangePassword(false)
    mockUserModule.mustChangePassword = false

    await navigate('/torrents/index')

    expect(router.currentRoute.path).toBe('/torrents/index')
    expect(app.$el.innerHTML).toContain('mock-torrents-page')
  })

  it('提示节流：3 秒窗口内连续点多个菜单只弹一次，窗口过后恢复', async() => {
    // 固定时钟取大于递增基数（10 亿）的值：窗口内首次拦截可弹，
    // 同窗口后续拦截被节流
    dateNowSpy.mockImplementation(() => 2_000_000_000)

    await startFrom('/dashboard')
    mockWarning.mockClear()

    await navigate('/torrents/index')
    await navigate('/recycle-bin/index')
    await navigate('/orphan-files/index')

    expect(mockWarning).toHaveBeenCalledTimes(1)

    // 时钟推进超过节流窗口后再拦截 → 恢复提示
    dateNowSpy.mockImplementation(() => 2_000_000_000 + 4_000)
    await navigate('/tasks/index')

    expect(mockWarning).toHaveBeenCalledTimes(2)
    expect(router.currentRoute.path).toBe('/settings/index')
  })

  it('对照组：标志为 false 时一切正常（dashboard 可达且渲染）', async() => {
    mockUserModule.mustChangePassword = false

    await navigate('/dashboard')

    expect(router.currentRoute.path).toBe('/dashboard')
    expect(app.$el.innerHTML).toContain('mock-dashboard-page')
    expect(mockWarning).not.toHaveBeenCalled()
  })
})
