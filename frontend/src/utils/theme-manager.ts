import type { ThemeType } from './theme'
import { getCurrentTheme as coreGetCurrentTheme, setTheme as coreSetTheme } from './theme'

export type { ThemeType } from './theme'

export interface ThemeConfig {
  name: string
  displayName: string
  primary: string
  primaryLight: string
  primaryHover: string
  primaryActive: string
  success: string
  warning: string
  error: string
  info: string
  primaryRgb: string
  successRgb: string
  warningRgb: string
  errorRgb: string
  infoRgb: string
}

export const THEMES: Record<ThemeType, ThemeConfig> = {
  emerald: {
    name: 'emerald',
    displayName: '翡翠绿',
    primary: '#10B981',
    primaryLight: '#34D399',
    primaryHover: '#047857',
    primaryActive: '#065F46',
    success: '#10B981',
    warning: '#F59E0B',
    error: '#EF4444',
    info: '#3B82F6',
    primaryRgb: '16, 185, 129',
    successRgb: '16, 185, 129',
    warningRgb: '245, 158, 11',
    errorRgb: '239, 68, 68',
    infoRgb: '59, 130, 246'
  },
  orange: {
    name: 'orange',
    displayName: '活力橙',
    primary: '#F97316',
    primaryLight: '#FB923C',
    primaryHover: '#C2410C',
    primaryActive: '#9A3412',
    success: '#10B981',
    warning: '#F59E0B',
    error: '#DC2626',
    info: '#3B82F6',
    primaryRgb: '249, 115, 22',
    successRgb: '16, 185, 129',
    warningRgb: '245, 158, 11',
    errorRgb: '220, 38, 38',
    infoRgb: '59, 130, 246'
  },
  graphite: {
    name: 'graphite',
    displayName: '石墨灰',
    primary: '#6366F1',
    primaryLight: '#8B5CF6',
    primaryHover: '#4F46E5',
    primaryActive: '#4338CA',
    success: '#10B981',
    warning: '#F59E0B',
    error: '#EF4444',
    info: '#3B82F6',
    primaryRgb: '99, 102, 241',
    successRgb: '16, 185, 129',
    warningRgb: '245, 158, 11',
    errorRgb: '239, 68, 68',
    infoRgb: '59, 130, 246'
  }
}

export class ThemeManager {
  /**
   * 获取当前主题
   */
  static getCurrentTheme(): ThemeType {
    const theme = coreGetCurrentTheme()
    if (THEMES[theme]) {
      return theme
    }
    return 'emerald'
  }

  /**
   * 设置主题
   */
  static setTheme(theme: ThemeType): void {
    if (!THEMES[theme]) {
      console.warn(`无效的主题: ${theme}`)
      return
    }

    coreSetTheme(theme)
    this.applyTheme(theme)
  }

  /**
   * 应用主题到DOM
   */
  static applyTheme(theme: ThemeType): void {
    const config = THEMES[theme]
    const root = document.documentElement

    // 设置data-theme属性
    root.removeAttribute('data-theme')
    if (theme !== 'emerald') {
      root.setAttribute('data-theme', theme)
    }

    // 设置CSS变量
    root.style.setProperty('--theme-primary', config.primary)
    root.style.setProperty('--theme-primary-light', config.primaryLight)
    root.style.setProperty('--theme-primary-hover', config.primaryHover)
    root.style.setProperty('--theme-primary-active', config.primaryActive)
    root.style.setProperty('--theme-success', config.success)
    root.style.setProperty('--theme-warning', config.warning)
    root.style.setProperty('--theme-error', config.error)
    root.style.setProperty('--theme-info', config.info)
    root.style.setProperty('--theme-primary-rgb', config.primaryRgb)
    root.style.setProperty('--theme-success-rgb', config.successRgb)
    root.style.setProperty('--theme-warning-rgb', config.warningRgb)
    root.style.setProperty('--theme-error-rgb', config.errorRgb)
    root.style.setProperty('--theme-info-rgb', config.infoRgb)

    // 更新主题类名
    document.body.className = document.body.className
      .replace(/theme-\w+/g, '')
      .trim()
    document.body.classList.add(`theme-${theme}`)
  }

  /**
   * 初始化主题（在应用启动时调用）
   */
  static initTheme(): void {
    const currentTheme = this.getCurrentTheme()
    this.applyTheme(currentTheme)
  }

  /**
   * 获取主题配置
   */
  static getThemeConfig(theme: ThemeType): ThemeConfig {
    return THEMES[theme]
  }

  /**
   * 获取所有主题列表
   */
  static getAllThemes(): ThemeConfig[] {
    return Object.values(THEMES)
  }
}

export default ThemeManager
