import {
  DEMO_ROUTE_MATRIX,
  DEMO_STATE_VERSION,
  DEMO_ACCESS_TOKEN,
  DEMO_USER_ID
} from '@/demo/types'
import { demoSession, isDemoMode } from '@/demo/config'

describe('demo config', () => {
  const originalDemoMode = process.env.VUE_APP_DEMO_MODE

  afterEach(() => {
    if (originalDemoMode === undefined) {
      delete process.env.VUE_APP_DEMO_MODE
    } else {
      process.env.VUE_APP_DEMO_MODE = originalDemoMode
    }
  })

  it('only enables demo mode for the explicit true value', () => {
    delete process.env.VUE_APP_DEMO_MODE
    expect(isDemoMode()).toBe(false)

    process.env.VUE_APP_DEMO_MODE = 'false'
    expect(isDemoMode()).toBe(false)

    process.env.VUE_APP_DEMO_MODE = 'true'
    expect(isDemoMode()).toBe(true)
  })

  it('provides a stable local session and route matrix', () => {
    expect(demoSession).toEqual({
      token: DEMO_ACCESS_TOKEN,
      userId: DEMO_USER_ID,
      stateVersion: DEMO_STATE_VERSION
    })
    expect(DEMO_ROUTE_MATRIX.some(route => route.path === '/dashboard' && route.category === 'core')).toBe(true)
    expect(DEMO_ROUTE_MATRIX.some(route => route.path === '/login' && route.category === 'disabled')).toBe(true)
    // 统计报表四页签（statistics-reports W5）：readonly 类别（demo 静态展示归 W7）
    expect(DEMO_ROUTE_MATRIX.some(route => route.path === '/statistics/overview' && route.category === 'readonly')).toBe(true)
    expect(DEMO_ROUTE_MATRIX.some(route => route.path.startsWith('/statistics/') && route.category === 'readonly')).toBe(true)
  })
})
