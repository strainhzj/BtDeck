import router from './router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { Message } from 'element-ui'
import { Route } from 'vue-router'
import { UserModule } from '@/store/modules/user'
import { isTokenExpired } from '@/utils/session'
import { trySilentRefresh } from '@/utils/request'

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

router.beforeEach(async(to: Route, from: Route, next: any) => {
  // Start progress bar
  NProgress.start()

  // Determine whether the user has logged in
  if (UserModule.token) {
    // 会话主动过期检查（双令牌 W6 伴随修复）：access token 已过期时先静默
    // 续期，失败立即登出——不再依赖"恰好有 API 请求触发 401"才被动登出
    if (isTokenExpired(UserModule.token)) {
      const refreshed = await trySilentRefresh()
      if (!refreshed) {
        UserModule.ResetToken()
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
          // Token无效或过期，清除状态并重定向到登录页
          UserModule.ResetToken()
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
