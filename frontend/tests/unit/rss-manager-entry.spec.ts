/* eslint-disable @typescript-eslint/no-explicit-any */
// RSS 统一管理入口路由契约（feature rss-subscription-phase2-2026-09-24）：
// /downloader 组双 children（index + rss）、移动端 /m/rss + toMobilePath 映射、
// 组件复用关系（统一页复用 RssSubscriptionTab，多入口不冲突）。
import { readFileSync } from 'fs'
import { resolve } from 'path'
import router from '@/router'
import { toMobilePath } from '@/utils/ui-mode'

const routes = router.options.routes || []

const read = (relative: string): string => readFileSync(resolve(__dirname, relative), 'utf-8')

describe('RSS 统一管理入口（rss2.5）', () => {
  it('/downloader 组含 index 与 rss 两个 children（子菜单形态）', () => {
    const group = routes.find((route: any) => route.path === '/downloader')
    expect(group).toBeTruthy()
    expect((group as any).redirect).toBe('/downloader/index')
    const children = ((group as any).children || []).map((child: any) => child.path)
    expect(children).toEqual(['index', 'rss'])
  })

  it('rss 子路由指向统一管理页并带 keepAlive + rssManagement 标题键', () => {
    const group = routes.find((route: any) => route.path === '/downloader') as any
    const rssRoute = group.children.find((child: any) => child.path === 'rss')
    expect(rssRoute.meta.titleKey).toBe('navigation.routes.rssManagement')
    expect(rssRoute.meta.keepAlive).toBe(true)
  })

  it('移动端 /m/rss 路由存在且隐藏（不入底栏）', () => {
    const mobile = routes.find((route: any) => route.path === '/m') as any
    const rssRoute = mobile.children.find((child: any) => child.path === 'rss')
    expect(rssRoute).toBeTruthy()
    expect(rssRoute.meta.hidden).toBe(true)
  })

  it('toMobilePath 将 /downloader/rss 映射到 /m/rss，其余 /downloader 不误伤', () => {
    expect(toMobilePath('/downloader/rss')).toBe('/m/rss')
    expect(toMobilePath('/downloader/index')).not.toBe('/m/rss')
  })

  it('统一管理页与移动页均复用 RssSubscriptionTab（多入口共享实现）', () => {
    const page = read('../../src/views/rss/index.vue')
    expect(page).toMatch(/RssSubscriptionTab from '@\/views\/downloader\/components\/RssSubscriptionTab.vue'/)
    const mobilePage = read('../../src/views/mobile/rss.vue')
    expect(mobilePage).toMatch(/RssSubscriptionTab from '@\/views\/downloader\/components\/RssSubscriptionTab.vue'/)
  })

  it('移动端下载器页提供 RSS 管理入口（goRssManager → /m/rss）', () => {
    const mobileDownloader = read('../../src/views/mobile/downloader.vue')
    expect(mobileDownloader).toMatch(/goRssManager/)
    expect(mobileDownloader).toMatch(/\/m\/rss/)
  })

  it('设置弹窗 rssSubscription 页签保留（双入口并存）', () => {
    const dialog = read('../../src/views/downloader/components/DownloaderSettingsDialog.vue')
    expect(dialog).toMatch(/name="rssSubscription"/)
    expect(dialog).toMatch(/RssSubscriptionTab/)
  })

  it('DEMO_ROUTE_MATRIX 登记 /downloader/rss 演示行', () => {
    const types = read('../../src/demo/types.ts')
    expect(types).toMatch(/path: '\/downloader\/rss'/)
  })
})
