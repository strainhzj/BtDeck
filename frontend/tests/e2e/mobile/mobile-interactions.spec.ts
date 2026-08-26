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
    await expect(menu.getByText('查询模板')).toBeVisible()
    await expect(menu.getByText('Tracker关键词')).toBeVisible()
    await expect(menu.getByText('定时任务')).toBeVisible()
    await expect(menu.getByText('孤儿文件')).toBeVisible()
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
})
