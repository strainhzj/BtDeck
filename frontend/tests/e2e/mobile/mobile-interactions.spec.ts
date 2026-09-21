import { test, expect } from '@playwright/test'
import { loginViaMobile } from './helpers/auth'

test.describe('移动端关键交互', () => {
  test('底部 Tab 导航切换页面', async({ page }) => {
    await loginViaMobile(page)
    await page.locator('.mobile-tab', { hasText: '下载器' }).click()
    await expect(page.locator('.m-downloader')).toBeVisible()
    await page.locator('.mobile-tab', { hasText: '种子' }).click()
    await expect(page.locator('.m-torrents')).toBeVisible()
    await page.locator('.mobile-tab', { hasText: '通知' }).click()
    await expect(page.locator('.m-notifications')).toBeVisible()
  })

  test('抽屉功能菜单打开并含核心入口', async({ page }) => {
    await loginViaMobile(page)
    await page.locator('.mobile-header-menu').click()
    const menu = page.locator('.mobile-menu')
    await expect(menu).toBeVisible()
    await expect(menu.getByText('高级搜索')).toBeVisible()
    // 查询模板页已裁撤（v1.0.5 后仅保留高级搜索），菜单不再含该入口
    await expect(menu.getByText('查询模板')).toHaveCount(0)
    await expect(menu.getByText('Tracker关键词')).toBeVisible()
    await expect(menu.getByText('定时任务')).toBeVisible()
    await expect(menu.getByText('孤儿文件')).toBeVisible()
  })

  test('二级页头部 ← 返回：固定回退映射回到归属主页', async({ page }) => {
    await loginViaMobile(page)
    // 高级搜索（抽屉二级页）：← 映射回仪表盘
    await page.goto('/#/m/search')
    await expect(page.locator('.mobile-header-back')).toBeVisible()
    // 二级页汉堡并存（抽屉全局可达）
    await expect(page.locator('.mobile-header-menu')).toBeVisible()
    await expect(page.locator('.mobile-header-title')).toHaveText('高级搜索')
    await page.locator('.mobile-header-back').click()
    await page.waitForURL(/#\/m\/dashboard/)

    // 种子详情（动态路由二级页）：← 映射回种子列表
    await page.goto('/#/m/torrents/detail/none/0000000000000000000000000000000000000000')
    await page.waitForTimeout(800)
    await page.locator('.mobile-header-back').click()
    await page.waitForURL(/#\/m\/torrents$/)

    // 四个 Tab 主页不显示返回按钮（汉堡 + 品牌）
    await page.locator('.mobile-tab', { hasText: '仪表盘' }).click()
    await expect(page.locator('.mobile-header-back')).toHaveCount(0)
    await expect(page.locator('.mobile-header-menu')).toBeVisible()
  })

  test('底部 Tab 渲染图标（仪表盘/下载器/种子/通知）', async({ page }) => {
    await loginViaMobile(page)
    await expect(page.locator('.mobile-tab-icon')).toHaveCount(4)
  })

  test('种子卡片点击进入详情页（动态路由）', async({ page }) => {
    await loginViaMobile(page)
    await page.goto('/#/m/torrents')
    // 开发库有真实种子数据；空库环境按条件跳过而非误报失败
    const hasData = await page
      .locator('.m-torrent-card')
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasData, '种子列表为空，跳过详情页冒烟')
    // 点名称区域：卡片底部操作按钮行有 @click.stop，点卡片中心可能落在按钮上
    await page.locator('.m-torrent-card .m-torrent-name').first().click()
    await page.waitForURL(/#\/m\/torrents\/detail\//)
    await expect(page.locator('.m-torrent-detail')).toBeVisible()
  })

  test('下载器卡片打开高级设置页（动态路由）', async({ page }) => {
    await loginViaMobile(page)
    await page.goto('/#/m/downloader')
    const settingsButton = page.getByRole('button', { name: '设置', exact: true }).first()
    const hasData = await settingsButton
      .waitFor({ state: 'visible', timeout: 15000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasData, '无下载器，跳过设置页冒烟')
    await settingsButton.click()
    await page.waitForURL(/#\/m\/downloader\/settings\//)
    await expect(page.locator('.m-dl-settings')).toBeVisible()
  })

  // ============ 2026-09-05 失控根修回归（无限滚动网络层） ============
  // jsdom 无真实布局（指令几何读数为 0，旧 v-infinite-scroll 缺陷在单测层不可复现），
  // 失控行为只能在本层拦截：页面空闲期不得自动连发 getList，滚动才允许有界追加。

  test('种子页无限滚动受控：空闲零 getList、滚动到底有界追加（失控根修回归）', async({ page }) => {
    await loginViaMobile(page)
    await page.goto('/#/m/torrents')
    const hasData = await page
      .locator('.m-torrent-card')
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasData, '种子列表为空，跳过无限滚动回归')

    // 数据量门槛：total ≤ 40（两页）时旧缺陷与修复后行为不可区分，跳过
    const hintText = await page
      .locator('.m-load-more-hint')
      .first()
      .textContent()
      .catch(() => '')
    const totalMatch = (hintText || '').match(/共\s*(\d+)/)
    test.skip(!totalMatch || Number(totalMatch[1]) <= 40, `数据量不足（${(hintText || '').trim()}），无判别力，跳过`)

    // 等待初始加载静默后开始计数
    await page.waitForTimeout(1500)
    let getListCalls = 0
    page.on('request', req => {
      if (req.url().includes('/torrents/getList')) getListCalls += 1
    })

    // 空闲 8 秒（覆盖速度轮询带来的 DOM 行更新）：修复前每次 DOM 变化都会连环
    // 触发 loadMore（真栈实测 65s/74 次），修复后必须为 0
    await page.waitForTimeout(8000)
    expect(getListCalls, '空闲期不得自动拉表（无限加载失控复发）').toBe(0)

    // 真实滚动到底：恰好触发有界追加（1 页 + 至多 1 次补页检查）
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
    await page.waitForTimeout(2000)
    expect(getListCalls).toBeGreaterThanOrEqual(1)
    expect(getListCalls).toBeLessThanOrEqual(3)
  })
})
