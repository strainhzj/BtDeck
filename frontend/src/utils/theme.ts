/**
 * 主题管理工具
 * 支持三种主题色切换：翡翠绿、活力橙、石墨灰
 */

export type ThemeType = 'emerald' | 'orange' | 'graphite'

export interface ThemeConfig {
  /** 展示名键（P6-5：common.theme.names.*；不再存中文文本） */
  nameKey: string
  value: ThemeType
  color: string
  /** 描述键（P6-5：common.theme.descriptions.*） */
  descriptionKey: string
}

/**
 * 主题变更事件详情类型
 */
export interface ThemeChangeEventDetail {
  theme: ThemeType
}

/**
 * 主题配置列表
 */
export const THEMES: ThemeConfig[] = [
  {
    nameKey: 'common.theme.names.emerald',
    value: 'emerald',
    color: '#059669',
    descriptionKey: 'common.theme.descriptions.emerald'
  },
  {
    nameKey: 'common.theme.names.orange',
    value: 'orange',
    color: '#EA580C',
    descriptionKey: 'common.theme.descriptions.orange'
  },
  {
    nameKey: 'common.theme.names.graphite',
    value: 'graphite',
    color: '#374151',
    descriptionKey: 'common.theme.descriptions.graphite'
  }
]

/**
 * 默认主题
 */
export const DEFAULT_THEME: ThemeType = 'emerald'

const THEME_STORAGE_KEY = 'btdeck-theme'
// 旧键已弃用，保留注释以供参考
// const LEGACY_BTP_THEME_STORAGE_KEY = 'btp-manager-theme'  // 旧的 btpManager 键
// const LEGACY_TORRENT_THEME_STORAGE_KEY = 'torrent_theme'  // 更旧的键

/**
 * 获取当前主题
 */
export function getCurrentTheme(): ThemeType {
  // 读取新键
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored && isValidTheme(stored)) {
    return stored as ThemeType
  }

  // 旧键迁移逻辑已移除，直接使用新键
  // 如需从旧版本迁移，请手动在浏览器控制台执行：
  // localStorage.setItem('btdeck-theme', localStorage.getItem('btp-manager-theme') || 'emerald')

  // 检查系统属性
  const root = document.documentElement
  const dataTheme = root.getAttribute('data-theme')
  if (dataTheme && isValidTheme(dataTheme)) {
    return dataTheme as ThemeType
  }

  // 默认返回翡翠绿主题
  return DEFAULT_THEME
}

/**
 * 设置主题
 */
export function setTheme(theme: ThemeType): void {
  if (!isValidTheme(theme)) {
    console.warn(`Invalid theme: ${theme}, using default theme`)
    theme = DEFAULT_THEME
  }

  document.documentElement.setAttribute('data-theme', theme)

  localStorage.setItem(THEME_STORAGE_KEY, theme)

  window.dispatchEvent(new CustomEvent('theme-change', { detail: { theme } }))
}

/**
 * 验证主题是否有效
 */
function isValidTheme(theme: string): boolean {
  return ['emerald', 'orange', 'graphite'].includes(theme)
}

/**
 * 切换到下一个主题
 */
export function toggleTheme(): ThemeType {
  const themes: ThemeType[] = ['emerald', 'orange', 'graphite']
  const currentTheme = getCurrentTheme()
  const currentIndex = themes.indexOf(currentTheme)
  const nextIndex = (currentIndex + 1) % themes.length
  const nextTheme = themes[nextIndex]

  setTheme(nextTheme)
  return nextTheme
}

/**
 * 监听主题变更
 */
export function onThemeChange(callback: (theme: ThemeType) => void): () => void {
  const handler = ((event: Event) => {
    const customEvent = event as CustomEvent<ThemeChangeEventDetail>
    if (customEvent.detail?.theme) {
      callback(customEvent.detail.theme)
    }
  }) as EventListener

  window.addEventListener('theme-change', handler)

  // 返回清理函数
  return () => {
    window.removeEventListener('theme-change', handler)
  }
}

/**
 * 初始化主题
 */
export function initTheme(): void {
  const theme = getCurrentTheme()
  setTheme(theme)
}

/**
 * 获取主题配置
 */
export function getThemeConfig(theme: ThemeType): ThemeConfig | undefined {
  return THEMES.find(t => t.value === theme)
}

/**
 * 获取所有主题配置
 */
export function getAllThemes(): ThemeConfig[] {
  return [...THEMES]
}
