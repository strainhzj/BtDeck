import Vue from 'vue'
import Router, { RawLocation, Route, isNavigationFailure, NavigationFailure } from 'vue-router'
import { Message } from 'element-ui'
import Layout from '@/layout/index.vue'
import MobileLayout from '@/layout/mobile/index.vue'
import { recoverFromChunkLoadError } from '@/utils/deployment-recovery'

Vue.use(Router)

/*
  redirect:                      if set to 'noredirect', no redirect action will be trigger when clicking the breadcrumb
  meta: {
    title: 'title'               the name showed in subMenu and breadcrumb (recommend set)
    icon: 'lucide-name'          the Lucide icon showed in the sidebar
    breadcrumb: false            if false, the item will be hidden in breadcrumb (default is true)
    hidden: true                 if true, this route will not show in the sidebar (default is false)
  }
*/

const router = new Router({
  // mode: 'history',  // Enable this if you need.
  scrollBehavior: (to, from, savedPosition) => {
    if (savedPosition) {
      return savedPosition
    } else {
      return { x: 0, y: 0 }
    }
  },
  base: process.env.BASE_URL,
  routes: [
    {
      path: '/login',
      component: () => import(/* webpackChunkName: "login" */ '@/views/login/index.vue'),
      meta: { hidden: true }
    },
    {
      path: '/404',
      component: () => import(/* webpackChunkName: "404" */ '@/views/404.vue'),
      meta: { hidden: true }
    },
    {
      // 移动版登录（Phase 4 M1）：守卫按 ui-mode 分流，登录链路复用 user store
      path: '/m/login',
      component: () => import(/* webpackChunkName: "m-login" */ '@/views/mobile/login.vue'),
      meta: { hidden: true }
    },
    {
      // 移动版布局（Phase 4 M1）：底部 Tab 壳；桌面侧栏不展示（hidden）
      path: '/m',
      component: MobileLayout,
      redirect: '/m/dashboard',
      meta: { hidden: true },
      children: [
        {
          path: 'dashboard',
          component: () => import(/* webpackChunkName: "m-dashboard" */ '@/views/mobile/dashboard.vue'),
          meta: { hidden: true, title: '仪表盘' }
        },
        {
          path: 'downloader',
          component: () => import(/* webpackChunkName: "m-downloader" */ '@/views/mobile/downloader.vue'),
          meta: { hidden: true, title: '下载器' }
        },
        {
          path: 'torrents',
          component: () => import(/* webpackChunkName: "m-torrents" */ '@/views/mobile/torrents.vue'),
          meta: { hidden: true, title: '种子' }
        },
        {
          // 种子详情（Phase 4 M1 余项）：列表快照缓存 + getList 回查 + 活动速度轮询
          path: 'torrents/detail/:downloaderId/:hash',
          component: () => import(/* webpackChunkName: "m-torrent-detail" */ '@/views/mobile/torrent-detail.vue'),
          meta: { hidden: true, title: '种子详情' }
        },
        {
          path: 'notifications',
          component: () => import(/* webpackChunkName: "m-notifications" */ '@/views/mobile/notifications.vue'),
          meta: { hidden: true, title: '通知' }
        }
      ]
    },
    {
      path: '/',
      component: Layout,
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          component: () => import(/* webpackChunkName: "dashboard" */ '@/views/dashboard/index.vue'),
          meta: {
            title: '首页',
            icon: 'layout-dashboard'
          }
        }
      ]
    },
    {
      path: '/downloader',
      component: Layout,
      children: [
        {
          path: 'index',
          component: () => import(/* webpackChunkName: "form" */ '@/views/downloader/index.vue'),
          meta: {
            title: '下载器管理',
            icon: 'server'
          }
        }
      ]
    },
    {
      path: '/torrents',
      component: Layout,
      redirect: '/torrents/index',
      meta: {
        title: '种子管理',
        icon: 'download'
      },
      children: [
        {
          path: 'index',
          component: () => import(/* webpackChunkName: "torrents" */ '@/views/torrents/TorrentViewSwitcher.vue'),
          meta: {
            title: '种子列表',
            icon: 'list'
          }
        },
        {
          path: 'traditional',
          component: () => import(/* webpackChunkName: "torrents-traditional" */ '@/views/torrents/TraditionalView.vue'),
          meta: {
            keepAlive: true,
            title: '种子列表（传统模式）',
            icon: 'list',
            hidden: true
          }
        },
        {
          path: 'file-management',
          component: () => import(/* webpackChunkName: "file-management" */ '@/views/torrents/FileManagement.vue'),
          meta: {
            title: '种子文件管理',
            icon: 'folder'
          }
        },
        {
          path: 'detail/:hash',
          component: () => import(/* webpackChunkName: "torrent-detail" */ '@/views/torrents/index.vue'),
          meta: {
            hidden: true,
            title: '种子详情'
          }
        }
      ]
    },
    {
      path: '/tasks',
      component: Layout,
      children: [
        {
          path: 'index',
          component: () => import(/* webpackChunkName: "tasks" */ '@/views/tasks/index.vue'),
          meta: {
            title: '定时任务',
            icon: 'timer'
          }
        }
      ]
    },
    {
      path: '/tracker',
      component: Layout,
      redirect: '/tracker/keywords-board',
      meta: {
        title: 'Tracker管理',
        icon: 'link'
      },
      children: [
        {
          path: 'keywords-board',
          component: () => import(/* webpackChunkName: "tracker-keywords-board" */ '@/views/tracker/keywords-board.vue'),
          meta: {
            title: '关键词看板',
            icon: 'panels-top-left'
          }
        },
        {
          path: 'keywords-search',
          component: () => import(/* webpackChunkName: "tracker-keywords-search" */ '@/views/tracker/keywords-search.vue'),
          meta: {
            hidden: true,
            title: '关键词搜索',
            icon: 'search'
          }
        },
        {
          path: 'reannounce-config',
          component: () => import(/* webpackChunkName: "tracker-reannounce-config" */ '@/views/tracker/reannounce-config.vue'),
          meta: {
            title: '汇报配置',
            icon: 'settings'
          }
        },
        {
          path: 'test',
          component: () => import(/* webpackChunkName: "tracker-test" */ '@/views/tracker/test.vue'),
          meta: {
            title: '测试工具',
            icon: 'wrench'
          }
        }
      ]
    },
    // 移除原有的 task-logs 独立路由，改为重定向到定时任务页面的日志页签
    {
      path: '/task-logs',
      redirect: '/tasks?tab=logs',
      meta: {
        hidden: true  // 在导航中隐藏
      }
    },
    {
      path: '/logs',
      component: Layout,
      redirect: '/logs/audit',
      meta: {
        title: '日志管理',
        icon: 'file-text'
      },
      children: [
        {
          path: 'audit',
          component: () => import(/* webpackChunkName: "audit-logs" */ '@/views/logs/audit.vue'),
          meta: {
            title: '操作日志',
            icon: 'file-text'
          }
        }
      ]
    },
    {
      path: '/recycle-bin',
      component: Layout,
      children: [
        {
          path: 'index',
          component: () => import(/* webpackChunkName: "recycle-bin" */ '@/views/recycle-bin/index.vue'),
          meta: {
            title: '回收站',
            icon: 'trash-2'
          }
        }
      ]
    },
    {
      path: '/orphan-files',
      component: Layout,
      children: [
        {
          path: 'index',
          component: () => import(/* webpackChunkName: "orphan-files" */ '@/views/orphan-files/index.vue'),
          meta: {
            keepAlive: true,
            title: '孤儿文件',
            icon: 'folder-search'
          }
        }
      ]
    },
    {
      path: '/settings',
      component: Layout,
      // 父路径必须解析到真实页面（强制改密守卫的落点）：缺 redirect 时
      // /settings 只渲染 Layout，内容区为空占位，改密表单不可达（死锁事故）
      redirect: '/settings/index',
      children: [
        {
          path: 'index',
          component: () => import(/* webpackChunkName: "settings" */ '@/views/settings/index.vue'),
          meta: {
            title: '系统设置',
            icon: 'settings'
          }
        }
      ]
    },
    {
      path: '/query-templates',
      component: Layout,
      children: [
        {
          path: 'index',
          component: () => import(/* webpackChunkName: "query-templates" */ '@/views/query-templates/index.vue'),
          meta: {
            keepAlive: true,
            title: '查询模板',
            icon: 'layout-template'
          }
        }
      ]
    },
    {
      path: '*',
      redirect: '/404',
      meta: { hidden: true }
    }
  ]
})

// 捕获并忽略冗余导航错误
// 修复Vue Router 3.x中router.push的Promise返回值问题
// 参考：https://github.com/vuejs/vue-router/issues/2881
// vue-router 3.1+ 把"被守卫改道/中止/重复"的导航以 rejected promise 返回
// （NavigationFailure：redirected/aborted/duplicated/cancelled）。这些是
// 路由守卫的正常控制流（如强制改密把 /dashboard 改道到 /settings），
// 不能作为异常抛给调用方——否则登录页等处的 catch 会把 vue-router 内部
// 英文消息（"Redirected when going from ... via a navigation guard"）
// 当成错误弹窗显示给用户。isNavigationFailure 统一判定，真实异常仍上抛。
const originalPush = router.push
const pushWithCallbacks = originalPush.bind(router) as (
  location: RawLocation,
  onComplete?: (route: Route) => void,
  onAbort?: (error: NavigationFailure) => void
) => void
const pushAsPromise = originalPush.bind(router) as (
  location: RawLocation
) => Promise<Route | NavigationFailure>

router.push = ((
  location: RawLocation,
  onComplete?: (route: Route) => void,
  onAbort?: (error: NavigationFailure) => void
) => {
  if (onComplete || onAbort) {
    pushWithCallbacks(location, onComplete, onAbort)
    return
  }

  return pushAsPromise(location).catch((err: NavigationFailure | Error) => {
    if (isNavigationFailure(err)) {
      return router.currentRoute
    }
    throw err
  })
}) as Router['push']

// replace 同样处理：forceChangeRedirect 等守卫的 next({replace: true}) 与
// 业务 replace 跳转同样会以 rejected promise 返回 NavigationFailure。
const originalReplace = router.replace
const replaceWithCallbacks = originalReplace.bind(router) as (
  location: RawLocation,
  onComplete?: (route: Route) => void,
  onAbort?: (error: NavigationFailure) => void
) => void
const replaceAsPromise = originalReplace.bind(router) as (
  location: RawLocation
) => Promise<Route | NavigationFailure>

router.replace = ((
  location: RawLocation,
  onComplete?: (route: Route) => void,
  onAbort?: (error: NavigationFailure) => void
) => {
  if (onComplete || onAbort) {
    replaceWithCallbacks(location, onComplete, onAbort)
    return
  }

  return replaceAsPromise(location).catch((err: NavigationFailure | Error) => {
    if (isNavigationFailure(err)) {
      return router.currentRoute
    }
    throw err
  })
}) as Router['replace']

// A tab opened before deployment still runs the old webpack runtime. When that
// runtime requests a removed lazy chunk, move the whole SPA to the current
// build once; the retry guard prevents a genuine server-side 404 reload loop.
router.onError((error: Error) => {
  const outcome = recoverFromChunkLoadError(error)
  if (outcome === 'suppressed') {
    Message.error({
      message: '页面资源加载失败，请手动刷新后重试',
      duration: 6000,
      showClose: true
    })
  }
})

export default router
