import router from './router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { Route } from 'vue-router'
import { UserModule } from '@/store/modules/user'

NProgress.configure({ showSpinner: false })

const whiteList = ['/login']

router.beforeEach(async(to: Route, from: Route, next: any) => {
  // Start progress bar
  NProgress.start()

  // Determine whether the user has logged in
  if (UserModule.token) {
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
          // 用户信息获取成功后，直接放行到目标页面
          // 此时不会触发额外的导航，因为这是在同一个导航周期内完成
          next()
        } catch (err) {
          // Token无效或过期，清除状态并重定向到登录页
          UserModule.ResetToken()
          next(`/login?redirect=${encodeURIComponent(to.path)}`)
          NProgress.done()
        }
      } else {
        // 已有用户信息，直接放行
        next()
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
