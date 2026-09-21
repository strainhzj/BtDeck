import { DEMO_ACCESS_TOKEN, DEMO_STATE_VERSION, DEMO_USER_ID } from '@/demo/types'

/** 构建时开关：只有显式传入 true 才进入 Demo，默认保持真实模式。 */
export const isDemoMode = (): boolean => process.env.VUE_APP_DEMO_MODE === 'true'

export const demoSession = {
  token: DEMO_ACCESS_TOKEN,
  userId: DEMO_USER_ID,
  stateVersion: DEMO_STATE_VERSION
} as const

/**
 * Demo 本地状态变化事件名。当前状态保存在内存 store，事件只用于未来页面间
 * 重置通知，不承载凭据或业务数据。
 */
export const DEMO_RESET_EVENT = 'btdeck:demo-reset'

export const emitDemoReset = (): void => {
  if (!isDemoMode() || typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(DEMO_RESET_EVENT))
}
