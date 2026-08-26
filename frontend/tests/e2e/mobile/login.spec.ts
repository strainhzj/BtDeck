import { test, expect } from '@playwright/test'
import { E2E_USERNAME, loginViaMobile } from './helpers/auth'

test.describe('移动端登录（/m/login）', () => {
  test('登录页渲染核心元素', async({ page }) => {
    await page.goto('/#/m/login')
    await expect(page.locator('.m-login')).toBeVisible()
    await expect(page.getByPlaceholder('用户名')).toBeVisible()
    await expect(page.getByPlaceholder('密码')).toBeVisible()
    await expect(page.getByRole('button', { name: '登录', exact: true })).toBeEnabled()
    await expect(page.getByRole('button', { name: '使用桌面版' })).toBeVisible()
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
