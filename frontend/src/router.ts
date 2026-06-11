import Vue from 'vue'
import Router from 'vue-router'
import Layout from '@/layout/index.vue'

Vue.use(Router)

/*
  redirect:                      if set to 'noredirect', no redirect action will be trigger when clicking the breadcrumb
  meta: {
    title: 'title'               the name showed in subMenu and breadcrumb (recommend set)
    icon: 'svg-name'             the icon showed in the sidebar
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
      path: '/',
      component: Layout,
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          component: () => import(/* webpackChunkName: "dashboard" */ '@/views/dashboard/index.vue'),
          meta: {
            title: '首页',
            icon: 'home'
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
            keepAlive: true,
            title: '下载器管理',
            icon: 'download'
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
        icon: 'files'
      },
      children: [
        {
          path: 'index',
          component: () => import(/* webpackChunkName: "torrents" */ '@/views/torrents/index.vue'),
          meta: {
            keepAlive: true,
            title: '种子列表',
            icon: 'list'
          }
        },
        {
          path: 'file-management',
          component: () => import(/* webpackChunkName: "file-management" */ '@/views/torrents/FileManagement.vue'),
          meta: {
            keepAlive: true,
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
            keepAlive: true,
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
            keepAlive: true,
            title: '关键词看板',
            icon: 'data-board'
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
            keepAlive: true,
            title: '汇报配置',
            icon: 'setting'
          }
        },
        {
          path: 'test',
          component: () => import(/* webpackChunkName: "tracker-test" */ '@/views/tracker/test.vue'),
          meta: {
            keepAlive: true,
            title: '测试工具',
            icon: 'tools'
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
        icon: 'document'
      },
      children: [
        {
          path: 'audit',
          component: () => import(/* webpackChunkName: "audit-logs" */ '@/views/logs/audit.vue'),
          meta: {
            keepAlive: true,
            title: '操作日志',
            icon: 'document'
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
            keepAlive: true,
            title: '回收站',
            icon: 'delete'
          }
        }
      ]
    },
    {
      path: '/settings',
      component: Layout,
      children: [
        {
          path: 'index',
          component: () => import(/* webpackChunkName: "settings" */ '@/views/settings/index.vue'),
          meta: {
            keepAlive: true,
            title: '系统设置',
            icon: 'setting'
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
const originalPush = router.push
router.push = function push(location: any, onComplete?: Function, onAbort?: Function) {
  // 当提供回调参数时，Vue Router 3.x返回undefined（非Promise模式）
  // 这种情况下直接调用原方法，不期望返回值
  if (typeof onComplete === 'function' || typeof onAbort === 'function') {
    return originalPush.call(this, location, onComplete, onAbort)
  }

  // 只在没有回调参数时才期望返回Promise（Promise模式）
  const result = originalPush.call(this, location)

  // 防御性检查：确保返回的是Promise
  // 在某些边缘情况下，即使没有回调也可能返回undefined
  if (!result || typeof result.then !== 'function') {
    console.warn('[Router.push] Expected Promise but got:', result, 'Location:', location)
    return Promise.resolve()
  }

  // 正常的Promise链处理
  return result.catch((err: Error) => {
    // 忽略 NavigationDuplicated 错误（用户点击相同路由）
    if (err.name === 'NavigationDuplicated') {
      return Promise.resolve()
    }
    // 其他错误正常抛出
    return Promise.reject(err)
  })
}

export default router
