/**
 * UI 模式工具（dual-mode-client Phase 4 M1）
 *
 * 移动/桌面视图选择的原则（与计划一致）：
 * 1. 不以 UA 自动识别作为唯一依据——默认 auto=按视口宽度判定；
 * 2. 用户显式选择优先并持久化（localStorage）；
 * 3. 窄视口默认移动版，且移动版头部提供切回桌面的出口（不自锁）；
 * 4. 伴侣 App WebView 恒移动端（2026-09-12 用户决策）：APK 全程移动端
 *    操作，不存在桌面浏览器预览场景——无视口与偏好，UA 含 App 注入
 *    标记即强制 mobile（顺带覆盖旧 APK 无条件出口写入的 desktop 偏好）。
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

/** 伴侣 App WebView（WebViewActivity 在 UA 追加 BtDeckCompanion 标记） */
export function isCompanionAppWebView(): boolean {
  if (typeof navigator === 'undefined') return false
  return navigator.userAgent.includes('BtDeckCompanion')
}

/** 当前会话应使用的模式（偏好 + 视口合成；App WebView 强制移动端） */
export function currentUiMode(): ResolvedUiMode {
  if (isCompanionAppWebView()) return 'mobile'
  return resolveUiMode(getStoredUiMode())
}

/** 桌面顶层页 → 移动版对应页；无对应关系的页面兜底到移动仪表盘 */
export function toMobilePath(path: string): string {
  // 查询模板已并入 /torrents 组（须在 /torrents 通配之前精确拦截，否则会落 /m/torrents）：
  // 移动端查询模板页已裁撤，模板能力收敛进 /m/search 工作区
  if (path.startsWith('/torrents/query-templates')) return '/m/search'
  if (path.startsWith('/torrents')) return '/m/torrents'
  if (path.startsWith('/dashboard')) return '/m/dashboard'
  // M2 已移动化的管理页（与守卫重定向清单保持同步）
  if (path.startsWith('/recycle-bin')) return '/m/recycle-bin'
  if (path.startsWith('/logs')) return '/m/logs'
  // 移动端查询模板页已裁撤（仅保留高级搜索）：模板能力收敛进 /m/search 工作区
  //（旧顶层深链经路由 redirect 已并入 /torrents 组，此分支防御性保留旧路径直调）
  if (path.startsWith('/query-templates')) return '/m/search'
  // 系统设置已移动化（/m/settings 整页复用桌面设置组件）
  if (path.startsWith('/settings')) return '/m/settings'
  // M3：定时任务整页移动化（含日志页签，编辑/新建走桌面完整版）；
  // Tracker 仅看板/搜索两子页移动化，汇报配置与测试工具保留桌面直达（守卫精确拦截）
  if (path.startsWith('/tasks')) return '/m/tasks'
  if (
    path === '/tracker' ||
    path === '/tracker/keywords-board' ||
    path === '/tracker/keywords-search'
  ) {
    return '/m/tracker/keywords-board'
  }
  // M4：孤儿文件整页移动化（聚合/副本位置/前缀快捷/批量走桌面完整版）
  if (path.startsWith('/orphan-files')) return '/m/orphan-files'
  return '/m/dashboard'
}

/** 登录跳转目标按模式选择登录页 */
export function loginPathForMode(redirectFullPath?: string): string {
  const suffix = redirectFullPath ? `?redirect=${encodeURIComponent(redirectFullPath)}` : ''
  return currentUiMode() === 'mobile' ? `/m/login${suffix}` : `/login${suffix}`
}
