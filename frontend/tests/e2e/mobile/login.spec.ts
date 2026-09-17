import { test, expect } from '@playwright/test'
import { E2E_USERNAME, loginViaMobile } from './helpers/auth'

test.describe('移动端登录（/m/login）', () => {
  test('登录页渲染核心元素（桌面版入口已移除）', async({ page }) => {
    await page.goto('/#/m/login')
    await expect(page.locator('.m-login')).toBeVisible()
    await expect(page.getByPlaceholder('用户名')).toBeVisible()
    await expect(page.getByPlaceholder('密码')).toBeVisible()
    await expect(page.getByRole('button', { name: '登录', exact: true })).toBeEnabled()
    // mobile-ux-fixes 2026-09：移动端不再提供桌面版切换入口
    await expect(page.getByRole('button', { name: '使用桌面版' })).toHaveCount(0)
  })

  // 2026-09-12 回归守护：偏好 mobile 的桌面浏览器须有回桌面出口（仅宽视口渲染）
  test('宽视口显示桌面版出口：点击写偏好并进入桌面登录页', async({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    // 复现锁死前置：显式偏好 mobile（否则宽视口 auto 解析为桌面模式，/m/login 被分流）
    await page.addInitScript(() => localStorage.setItem('btdeck_ui_mode', 'mobile'))
    await page.goto('/#/m/login')
    await expect(page.getByRole('button', { name: '使用桌面版登录' })).toBeVisible()
    await page.getByRole('button', { name: '使用桌面版登录' }).click()
    await expect(page).toHaveURL(/#\/login/)
  })

  test('错误凭据弹出错误提示且停留在登录页', async({ page }) => {
    await page.goto('/#/m/login')
    await page.getByPlaceholder('用户名').fill(E2E_USERNAME)
    await page.getByPlaceholder('密码').fill('wrong-password-e2e')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.locator('.el-message--error')).toBeVisible()
    await expect(page).toHaveURL(/#\/m\/login/)
  })

  test('正确凭据进入移动仪表盘并展示底部 Tab', async({ page }) => {
    await loginViaMobile(page)
    await expect(page.locator('.m-dashboard')).toBeVisible()
    await expect(page.locator('.mobile-header')).toBeVisible()
    await expect(page.locator('.mobile-tabbar')).toBeVisible()
  })
})
