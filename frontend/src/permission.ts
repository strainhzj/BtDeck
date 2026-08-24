import router from './router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { Message } from 'element-ui'
import { Route } from 'vue-router'
import { UserModule } from '@/store/modules/user'
import { isTokenExpired } from '@/utils/session'
import { trySilentRefresh } from '@/utils/request'
import { ApiError } from '@/types/api'
import { currentUiMode, loginPathForMode, toMobilePath } from '@/utils/ui-mode'

NProgress.configure({ showSpinner: false })

/** 登录页路径集合（桌面/移动双入口，Phase 4 M1） */
const loginPaths = ['/login', '/m/login']

/**
 * UI 模式重定向（Phase 4 M1）：认证检查之前按用户偏好/视口分流。
 * - 移动模式访问桌面顶层页（/、/dashboard、/torrents*）→ 对应移动页；
 * - 桌面模式访问 /m/* → 对应桌面页（通知无独立桌面页，落仪表盘）；
 * - 移动模式的 /m/login 与桌面模式的 /login 均放行，交由下方认证逻辑处理。
 * 不以 UA 作为唯一依据（与安卓壳的模式判定原则一致）。
 */
const uiModeRedirectPath = (to: Route): string | null => {
  if (currentUiMode() === 'mobile') {
    // 已移动化的桌面顶层页统一分流（M2 后含回收站/日志/查询模板；M3 含定时任务整页与 Tracker 看板/搜索两子页）
    if (
      to.path === '/' || to.path === '/dashboard' || to.path === '/torrents' || to.path.startsWith('/torrents/') ||
      to.path === '/recycle-bin' || to.path.startsWith('/recycle-bin/') ||
      to.path === '/logs' || to.path.startsWith('/logs/') ||
      to.path === '/query-templates' || to.path.startsWith('/query-templates/') ||
      to.path === '/tasks' || to.path.startsWith('/tasks/') ||
      to.path === '/tracker' || to.path === '/tracker/keywords-board' || to.path === '/tracker/keywords-search'
    ) {
      return toMobilePath(to.path)
    }
    return null
  }
  if (to.path.startsWith('/m/')) {
    if (to.path === '/m/login') return null
    if (to.path.startsWith('/m/torrents')) return '/torrents'
    return '/dashboard'
  }
  return null
}

// 强制改密放行白名单（安全修复 W9）：mustChangePassword 时只允许访问
// 改密页。真实页面挂在子路由 /settings/index（父路由 redirect 前置解析
// 后守卫不会再见到 '/settings'，防御性保留）——此前白名单写父路径导致
// 落点内容区空白、真实路径又被弹回，改密表单不可达形成死锁（生产事故）
const forceChangeAllowedPaths = ['/settings/index', '/settings']

const isForceChangeBlocked = (to: Route): boolean =>
  UserModule.mustChangePassword && !forceChangeAllowedPaths.includes(to.path)

// 拦截提示节流：拦截重定向回同一路径时设置页不会重新挂载，用户点其它
// 菜单毫无反馈——须由守卫弹窗告知；连续点多个菜单时避免弹窗堆叠
const FORCE_CHANGE_HINT_INTERVAL_MS = 3000
let lastForceChangeHintAt = 0

const forceChangeRedirect = (next: any): void => {
  const now = Date.now()
  if (now - lastForceChangeHintAt >= FORCE_CHANGE_HINT_INTERVAL_MS) {
    lastForceChangeHintAt = now
    Message.warning({
      message: '请先修改密码：完成修改前仅可访问系统设置页',
      duration: 3000
    })
  }
  next({ path: '/settings/index', query: { forceChange: '1' }, replace: true })
  NProgress.done()
}

/**
 * 瞬时失败判定（buildNetworkError/业务码契约）：
 * - ApiError code '0'：网络层失败（无 HTTP 响应）
 * - code 5xx：服务端瞬时故障（如 /info 兜底 500）——认证本身没问题，
 *   登出会让 DB 抖动误踢在线用户，同样按瞬时处理保留会话
 */
const isTransientError = (err: unknown): boolean =>
  err instanceof ApiError && (err.code === '0' || /^5/.test(err.code))

/**
 * 以"中止导航"替代"登出"处理瞬时失败：保留令牌与会话现场，
 * 用户再次点击菜单/刷新即重试。next(false) 后 afterEach 不触发，
 * 进度条必须手动收尾（对齐本文件其余非 next() 出口的手动 done 惯例）。
 */
const abortNavigation = (next: any): void => {
  Message.warning({
    message: '服务暂时不可用，请稍后重试',
    duration: 3000
  })
  next(false)
  NProgress.done()
}

/**
 * 瞬时失败连续中止的逃生通道：首导航被 next(false) 拦下时页面无渲染，
 * 且 token 真值下访问 /login 会被重定向回目标页——持久故障（如服务端
 * 持续 5xx/断网）会让用户永久卡死，唯一逃生是手清 cookie。连续中止达到
 * 上限后回落登出路径，保证 /login 可达；任何一次导航成功即清零。
 */
const TRANSIENT_ABORT_LIMIT = 3
let consecutiveTransientAborts = 0

/** 登记一次瞬时中止；返回 true 表示已达上限、调用方应回落登出路径 */
const registerTransientAbort = (): boolean => {
  consecutiveTransientAborts += 1
  return consecutiveTransientAborts >= TRANSIENT_ABORT_LIMIT
}

/** 瞬时中止的兜底出口：会话按过期处理并跳登录页（服务恢复后可重新登录/自动续期恢复） */
const fallbackToLogout = (next: any, to: Route): void => {
  consecutiveTransientAborts = 0
  UserModule.ExpireSession()
  next(loginPathForMode(to.path))
  NProgress.done()
}

router.beforeEach(async(to: Route, from: Route, next: any) => {
  // Start progress bar
  NProgress.start()

  // UI 模式分流（Phase 4 M1）：认证前的布局选择，重定向不改变 redirect 语义
  const modeRedirect = uiModeRedirectPath(to)
  if (modeRedirect) {
    next({ path: modeRedirect, replace: true })
    NProgress.done()
    return
  }

  // Determine whether the user has logged in
  if (UserModule.token) {
    // 会话主动过期检查（双令牌 W6 伴随修复）：access token 已过期时先静默
    // 续期，失败按三态分流——确证死亡才登出；网络抖动保留会话现场
    if (isTokenExpired(UserModule.token)) {
      const outcome = await trySilentRefresh()
      if (outcome.status === 'transient') {
        // 瞬时故障不杀会话：已有用户信息直接放行（页面请求自行重试续期）；
        // 首导航（需 GetUserInfo）中止本次导航，避免把瞬时失败升级成登出；
        // 连续多次中止则回落登出，防止持久故障下首导航永久卡死
        if (UserModule.roles.length === 0) {
          if (registerTransientAbort()) {
            fallbackToLogout(next, to)
            return
          }
          abortNavigation(next)
          return
        }
      } else if (outcome.status === 'rejected') {
        // ExpireSession 保留 refresh cookie：防跨标签轮换竞态清掉他标签
        // 刚换得的有效令牌（死 token 残留无害，重登录时覆盖）
        UserModule.ExpireSession()
        if (loginPaths.indexOf(to.path) !== -1) {
          next()
        } else {
          next(loginPathForMode(to.fullPath))
        }
        NProgress.done()
        return
      }
    }
    if (loginPaths.indexOf(to.path) !== -1) {
      // 已登录用户访问登录页时，读取redirect参数并重定向
      const redirect = to.query.redirect as string
      const targetPath = redirect ? decodeURIComponent(redirect) : '/'

      // 使用replace避免回退到登录页，同时保留redirect参数的语义
      // 这种设计让登录组件只需负责认证，导航由路由守卫统一管理
      next({ path: targetPath, replace: true })
      NProgress.done()
    } else {
      // Check whether the user has obtained his permission roles
      if (UserModule.roles.length === 0) {
        try {
          // 🔧 防御性检查：确保 token 有效才调用 API
          if (!UserModule.token || UserModule.token.trim() === '') {
            throw new Error('Token为空，请重新登录')
          }

          // Get user info, including roles
          await UserModule.GetUserInfo()
          // 用户信息获取成功后按强制改密标志决定放行——此分支正是登录后
          // /F5 后的首次导航路径（Login 不填充 roles）：若不在此检查，
          // 强制改密用户的首次导航会先落到业务页一次才被拦
          if (isForceChangeBlocked(to)) {
            forceChangeRedirect(next)
          } else {
            next()
          }
        } catch (err) {
          // 瞬时失败（网络层 '0' 或业务/HTTP 5xx，GetUserInfo 原样上抛的
          // ApiError）：保留令牌与会话，中止本次导航待重试，不升级为登出；
          // 连续多次中止则回落登出，防止持久故障下首导航永久卡死
          if (isTransientError(err)) {
            if (registerTransientAbort()) {
              fallbackToLogout(next, to)
              return
            }
            abortNavigation(next)
            return
          }
          // Token无效或过期：ExpireSession 保留 refresh cookie（401 链路的
          // redirectToLogin 已按同语义处理，这里不重置为全清防竞态误杀）
          UserModule.ExpireSession()
          next(loginPathForMode(to.path))
          NProgress.done()
        }
      } else {
        // 已有用户信息，直接放行
        // 强制改密拦截（安全修复 W9）：mustChangePassword 时只允许访问
        // 改密页（/settings/index），优先于 redirect 参数——仅靠登录页
        // 跳转可被直接改 URL 绕过，必须由守卫统一强制
        if (isForceChangeBlocked(to)) {
          forceChangeRedirect(next)
        } else {
          next()
        }
      }
    }
  } else {
    // Has no token
    if (loginPaths.indexOf(to.path) !== -1) {
      // In the free login whitelist, go directly
      next()
    } else {
      // Other pages that do not have permission to access are redirected to the login page.
      next(loginPathForMode(to.path))
      NProgress.done()
    }
  }
})

router.afterEach((to: Route) => {
  // Finish progress bar
  NProgress.done()

  // 导航成功即清零瞬时中止计数（连续计数只针对"一直失败到不了任何页面"）
  consecutiveTransientAborts = 0

  // set page title
  document.title = to.meta?.title || 'BtDeck'
})
