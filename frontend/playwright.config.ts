import { PlaywrightTestConfig, devices } from '@playwright/test'

/**
 * 移动端 E2E 冒烟（Playwright + 设备模拟）。
 *
 * - 设备模拟 iPhone 12（390×844 视口 + 触摸 + 移动 UA），与既有移动实测视口一致；
 * - 依赖本机 dev 栈：后端 5001 + 前端 8080（vue.config 的 /api 代理 5001）；
 * - 凭据经 E2E_USERNAME / E2E_PASSWORD 环境变量覆盖，默认本地开发库 admin。
 */
const config: PlaywrightTestConfig = {
  testDir: './tests/e2e/mobile',
  timeout: 30000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  projects: [
    {
      // iOS Safari 真实引擎（iPhone 12 设备默认 WebKit）
      name: 'mobile-webkit',
      use: { ...devices['iPhone 12'] }
    },
    {
      // Chromium 引擎同视口回归（与既有 IAB 实测引擎一致，跑得更快）
      name: 'mobile-chromium',
      use: { ...devices['iPhone 12'], browserName: 'chromium' }
    }
  ]
}

export default config
