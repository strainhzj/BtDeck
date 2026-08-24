/**
 * UI 模式工具（dual-mode-client Phase 4 M1）
 *
 * 移动/桌面视图选择的三条原则（与计划一致）：
 * 1. 不以 UA 自动识别作为唯一依据——默认 auto=按视口宽度判定；
 * 2. 用户显式选择优先并持久化（localStorage）；
 * 3. 窄视口默认移动版，且移动版头部提供切回桌面的出口（不自锁）。
 */

const MODE_STORAGE_KEY = 'btdeck_ui_mode'

export type UiModePreference = 'auto' | 'mobile' | 'desktop'
export type ResolvedUiMode = 'mobile' | 'desktop'

/** 窄视口阈值（px）：低于该宽度按移动版布局 */
export const MOBILE_VIEWPORT_BREAKPOINT = 768

export function getStoredUiMode(): UiModePreference {
  const raw = localStorage.getItem(MODE_STORAGE_KEY)
  return raw === 'mobile' || raw === 'desktop' ? raw : 'auto'
}

export function setStoredUiMode(mode: UiModePreference): void {
  localStorage.setItem(MODE_STORAGE_KEY, mode)
}

export function isNarrowViewport(width?: number): boolean {
  const w = width ?? (typeof window !== 'undefined' ? window.innerWidth : MOBILE_VIEWPORT_BREAKPOINT)
  return w < MOBILE_VIEWPORT_BREAKPOINT
}

export function resolveUiMode(preference: UiModePreference, width?: number): ResolvedUiMode {
  if (preference === 'mobile') return 'mobile'
  if (preference === 'desktop') return 'desktop'
  return isNarrowViewport(width) ? 'mobile' : 'desktop'
}

/** 当前会话应使用的模式（偏好 + 视口合成） */
export function currentUiMode(): ResolvedUiMode {
  return resolveUiMode(getStoredUiMode())
}

/** 桌面顶层页 → 移动版对应页；无对应关系的页面兜底到移动仪表盘 */
export function toMobilePath(path: string): string {
  if (path.startsWith('/torrents')) return '/m/torrents'
  if (path.startsWith('/dashboard')) return '/m/dashboard'
  // M2 已移动化的管理页（与守卫重定向清单保持同步）
  if (path.startsWith('/recycle-bin')) return '/m/recycle-bin'
  if (path.startsWith('/logs')) return '/m/logs'
  if (path.startsWith('/query-templates')) return '/m/query-templates'
  return '/m/dashboard'
}

/** 登录跳转目标按模式选择登录页 */
export function loginPathForMode(redirectFullPath?: string): string {
  const suffix = redirectFullPath ? `?redirect=${encodeURIComponent(redirectFullPath)}` : ''
  return currentUiMode() === 'mobile' ? `/m/login${suffix}` : `/login${suffix}`
}
