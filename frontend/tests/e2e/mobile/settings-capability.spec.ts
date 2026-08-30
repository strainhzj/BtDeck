import { test, expect } from '@playwright/test'

/**
 * 主机能力矩阵 E2E（dual-mode-client task .5 设备级目验）。
 *
 * 直连 AVD 本机服务端（E2E_BASE_URL 经 adb forward 指向 android-server 形态
 * 后端自带前端）——与 App WebView 同源加载，等价 UI 层验证：
 * 移动设置页（桌面组件包装）→ 主机能力 tab → android-server 形态与降级展示。
 * 凭据经 E2E_USERNAME/E2E_PASSWORD 注入（AVD 全新库为 admin/admin）。
 */
import { loginViaMobile } from './helpers/auth'

test.describe('主机能力矩阵（android-server 形态）', () => {
  test.beforeEach(async({ page }) => {
    await loginViaMobile(page)
    await page.goto('/#/m/settings')
  })

  test('设置页含主机能力 tab 且面板按卡片渲染降级项', async({ page }) => {
    await page.getByRole('tab', { name: '主机能力' }).click()
    await expect(page.locator('.capability-cards')).toBeVisible()
    await expect(page.locator('.capability-card')).toHaveCount(14)
  })

  test('形态标签与降级统计来自服务端矩阵', async({ page }) => {
    await page.getByRole('tab', { name: '主机能力' }).click()
    await expect(page.getByText('Android 服务端', { exact: true })).toBeVisible()
    await expect(page.getByText(/降级 5 项/)).toBeVisible()
    await expect(page.getByText(/不支持 3 项/)).toBeVisible()
  })

  test('unsupported 项带说明与 danger 徽标', async({ page }) => {
    await page.getByRole('tab', { name: '主机能力' }).click()
    const card = page.locator('.capability-card', { hasText: '自定义脚本任务' })
    await expect(card).toBeVisible()
    await expect(card.locator('.el-tag--danger')).toBeVisible()
    await expect(card.getByText('不支持', { exact: true })).toBeVisible()
  })

  test('degraded 项带说明与 warning 徽标', async({ page }) => {
    await page.getByRole('tab', { name: '主机能力' }).click()
    const card = page.locator('.capability-card', { hasText: '定时任务调度' })
    await expect(card).toBeVisible()
    await expect(card.locator('.el-tag--warning')).toBeVisible()
  })
})
