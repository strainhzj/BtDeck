import router from './router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { Message } from 'element-ui'
import { Route } from 'vue-router'
import { UserModule } from '@/store/modules/user'
import { isTokenExpired } from '@/utils/session'
import { trySilentRefresh } from '@/utils/request'
import { ApiError } from '@/types/api'

NProgress.configure({ showSpinner: false })

const whiteList = ['/login']

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

/** 网络层失败（无 HTTP 响应）判定：ApiError code '0'（buildNetworkError 契约） */
const isTransientNetworkError = (err: unknown): boolean =>
  err instanceof ApiError && err.code === '0'

/**
 * 以"中止导航"替代"登出"处理瞬时网络失败：保留令牌与会话现场，
 * 用户再次点击菜单/刷新即重试。next(false) 后 afterEach 不触发，
 * 进度条必须手动收尾（对齐本文件其余非 next() 出口的手动 done 惯例）。
 */
const abortNavigation = (next: any): void => {
  Message.warning({
    message: '网络波动，请稍后重试',
    duration: 3000
  })
  next(false)
  NProgress.done()
}

router.beforeEach(async(to: Route, from: Route, next: any) => {
  // Start progress bar
  NProgress.start()

  // Determine whether the user has logged in
  if (UserModule.token) {
    // 会话主动过期检查（双令牌 W6 伴随修复）：access token 已过期时先静默
    // 续期，失败按三态分流——确证死亡才登出；网络抖动保留会话现场
    if (isTokenExpired(UserModule.token)) {
      const outcome = await trySilentRefresh()
      if (outcome.status === 'transient') {
        // 网络抖动不杀会话：已有用户信息直接放行（页面请求自行重试续期）；
        // 首导航（需 GetUserInfo）中止本次导航，避免把瞬时失败升级成登出
        if (UserModule.roles.length === 0) {
          abortNavigation(next)
          return
        }
      } else if (outcome.status === 'rejected') {
        // ExpireSession 保留 refresh cookie：防跨标签轮换竞态清掉他标签
        // 刚换得的有效令牌（死 token 残留无害，重登录时覆盖）
        UserModule.ExpireSession()
        if (to.path === '/login') {
          next()
        } else {
          next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
        }
        NProgress.done()
        return
      }
    }
    if (to.path === '/login') {
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
          // 网络抖动（GetUserInfo 网络失败原样上抛的 ApiError code '0'）：
          // 保留令牌与会话，中止本次导航待重试，不升级为登出
          if (isTransientNetworkError(err)) {
            abortNavigation(next)
            return
          }
          // Token无效或过期：ExpireSession 保留 refresh cookie（401 链路的
          // redirectToLogin 已按同语义处理，这里不重置为全清防竞态误杀）
          UserModule.ExpireSession()
          next(`/login?redirect=${encodeURIComponent(to.path)}`)
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
    if (whiteList.indexOf(to.path) !== -1) {
      // In the free login whitelist, go directly
      next()
    } else {
      // Other pages that do not have permission to access are redirected to the login page.
      next(`/login?redirect=${encodeURIComponent(to.path)}`)
      NProgress.done()
    }
  }
})

router.afterEach((to: Route) => {
  // Finish progress bar
  NProgress.done()

  // set page title
  document.title = to.meta?.title || 'BtDeck'
})
