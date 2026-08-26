import { test, expect } from '@playwright/test'
import { loginViaMobile } from './helpers/auth'

interface MobileRouteCase {
  name: string
  path: string
  rootSelector: string
}

/** 静态移动路由全集（Phase 4 M1-M4）；动态参数路由见 mobile-interactions.spec.ts */
const ROUTES: MobileRouteCase[] = [
  { name: '仪表盘', path: '/m/dashboard', rootSelector: '.m-dashboard' },
  { name: '下载器', path: '/m/downloader', rootSelector: '.m-downloader' },
  { name: '种子列表', path: '/m/torrents', rootSelector: '.m-torrents' },
  { name: '高级搜索', path: '/m/search', rootSelector: '.m-search' },
  { name: '查询模板', path: '/m/query-templates', rootSelector: '.m-templates' },
  { name: '回收站', path: '/m/recycle-bin', rootSelector: '.m-recycle-bin' },
  { name: '审计日志', path: '/m/logs', rootSelector: '.m-logs' },
  { name: 'Tracker关键词看板', path: '/m/tracker/keywords-board', rootSelector: '.m-tracker-kw' },
  { name: 'Tracker关键词搜索', path: '/m/tracker/keywords-search', rootSelector: '.m-kw-search' },
  { name: '定时任务', path: '/m/tasks', rootSelector: '.m-tasks' },
  { name: '孤儿文件', path: '/m/orphan-files', rootSelector: '.m-orphan' },
  { name: '通知中心', path: '/m/notifications', rootSelector: '.m-notifications' }
]

test.describe('移动端静态路由冒烟', () => {
  for (const route of ROUTES) {
    test(`${route.name} ${route.path} 可达且渲染`, async({ page }) => {
      const pageErrors: string[] = []
      page.on('pageerror', (error: Error) => pageErrors.push(error.message))
      await loginViaMobile(page)
      await page.goto(`/#${route.path}`)
      await expect(page.locator(route.rootSelector)).toBeVisible()
      await expect(page.locator('.mobile-header')).toBeVisible()
      await expect(page.locator('.mobile-tabbar')).toBeVisible()
      expect(pageErrors).toEqual([])
    })
  }
})
