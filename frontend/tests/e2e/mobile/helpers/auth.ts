import { Page } from '@playwright/test'

/** 本地开发库默认凭据（记忆：admin 已按 SOP 改密）；可用环境变量覆盖 */
export const E2E_USERNAME = process.env.E2E_USERNAME || 'admin'
export const E2E_PASSWORD = process.env.E2E_PASSWORD || 'Btdeck@2026dev'

/**
 * 走移动端登录页完成 UI 登录（真实用户路径，非 API 直注 token）。
 * token 落在 cookie，同 context 内后续 /m/ 路由均可通过守卫。
 */
export async function loginViaMobile(page: Page): Promise<void> {
  await page.goto('/#/m/login')
  await page.getByPlaceholder('用户名').fill(E2E_USERNAME)
  await page.getByPlaceholder('密码').fill(E2E_PASSWORD)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.waitForURL(/#\/m\/dashboard/)
  await page.locator('.mobile-tabbar').waitFor()
}
