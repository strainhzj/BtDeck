/**
 * i18n 基础设施行为规格（desktop-bilingual-20260918.p1，验收矩阵 L01/L02/L04/L05、F01 片段）。
 *
 * 覆盖：
 * - 语言解析顺序：手动偏好 > 浏览器语言（navigator.languages 顺序）> 默认中文（L01）
 * - 持久化与安全回退：无效存储值清除、存储不可用不崩溃（L02）
 * - document.lang 与 document.title 解析（L04）
 * - 缺译回退与不渲染原始键（L05）
 * - 相对时间中英双语与边界（F01）
 */

import enMessages from '@/i18n/locales/en'
import {
  getLocale,
  readStoredLocale,
  resolvePageTitle,
  resolveSupportedLocale,
  setLocale,
  translate,
  translateChoice
} from '@/i18n'
import { DEFAULT_LOCALE, LOCALE_STORAGE_KEY } from '@/i18n/types'
import { formatRelativeTime } from '@/utils/formatters'


describe('语言解析顺序（L01）', () => {
  it('手动偏好优先于浏览器语言', () => {
    expect(resolveSupportedLocale('en', ['zh-CN'], 'zh-CN')).toBe('en')
    expect(resolveSupportedLocale('zh-CN', ['en-US'], 'en-US')).toBe('zh-CN')
  })

  it('浏览器语言按列表顺序匹配（en*→en，zh*→zh-CN）', () => {
    expect(resolveSupportedLocale(null, ['en-US', 'zh-CN'], undefined)).toBe('en')
    expect(resolveSupportedLocale(null, ['zh-CN', 'en-US'], undefined)).toBe('zh-CN')
    expect(resolveSupportedLocale(null, ['zh-TW', 'en'], undefined)).toBe('zh-CN')
    expect(resolveSupportedLocale(null, undefined, 'en-GB')).toBe('en')
  })

  it('不支持的语言回退默认中文', () => {
    expect(resolveSupportedLocale(null, ['fr-FR', 'ja-JP'], 'fr')).toBe(DEFAULT_LOCALE)
    expect(resolveSupportedLocale(null, undefined, undefined)).toBe(DEFAULT_LOCALE)
    expect(resolveSupportedLocale(null, [], undefined)).toBe(DEFAULT_LOCALE)
  })

  it('无效存储值被忽略（不参与解析）', () => {
    expect(resolveSupportedLocale('jp', ['en-US'], undefined)).toBe('en')
  })
})

describe('持久化与安全回退（L02）', () => {
  beforeEach(() => {
    window.localStorage.clear()
    setLocale(DEFAULT_LOCALE)
  })

  it('setLocale 持久化并更新 <html lang>', () => {
    setLocale('en')
    expect(getLocale()).toBe('en')
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    setLocale('zh-CN')
    expect(getLocale()).toBe('zh-CN')
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('zh-CN')
    expect(document.documentElement.lang).toBe('zh-CN')
  })

  it('无效存储值被 readStoredLocale 清除并回退 null', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'jp')
    expect(readStoredLocale()).toBeNull()
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBeNull()
  })

  it('存储不可用（抛异常）时读取与写入均不崩溃', () => {
    const getItemSpy = jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage blocked')
    })
    const setItemSpy = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage blocked')
    })
    expect(readStoredLocale()).toBeNull()
    expect(() => setLocale('en')).not.toThrow()
    expect(getLocale()).toBe('en') // 内存仍生效
    getItemSpy.mockRestore()
    setItemSpy.mockRestore()
    setLocale(DEFAULT_LOCALE)
  })
})

describe('缺译回退与标题解析（L05/L04）', () => {
  beforeEach(() => {
    setLocale(DEFAULT_LOCALE)
  })

  it('en 缺键回退 zh-CN（fallbackLocale）', () => {
    const routes = enMessages.navigation as Record<string, Record<string, string>>
    const saved = routes.routes.dashboard
    delete routes.routes.dashboard
    try {
      setLocale('en')
      expect(translate('navigation.routes.dashboard')).toBe('首页')
    } finally {
      routes.routes.dashboard = saved
      setLocale(DEFAULT_LOCALE)
    }
  })

  it('完全缺失的键返回空串而非原始键', () => {
    setLocale('en')
    expect(translate('time.notExistAtAll')).toBe('')
    setLocale(DEFAULT_LOCALE)
  })

  it('路由标题：titleKey 优先且随语言切换；无 titleKey 保持中文原值（移动路由）', () => {
    const desktopRoute = { meta: { title: '首页', titleKey: 'navigation.routes.dashboard' } }
    const mobileRoute = { meta: { title: '仪表盘' } }
    const untitledRoute = { meta: {} }

    setLocale('zh-CN')
    expect(resolvePageTitle(desktopRoute)).toBe('首页')
    expect(resolvePageTitle(mobileRoute)).toBe('仪表盘')
    expect(resolvePageTitle(untitledRoute)).toBe('BtDeck')
    expect(resolvePageTitle(undefined)).toBe('BtDeck')

    setLocale('en')
    expect(resolvePageTitle(desktopRoute)).toBe('Home')
    // 移动路由无 titleKey：双语不侵蚀移动端中文
    expect(resolvePageTitle(mobileRoute)).toBe('仪表盘')

    setLocale('zh-CN')
  })
})

describe('相对时间双语与边界（F01）', () => {
  // formatRelativeTime 内部用 new Date() 取当前时间：以测试运行时的真实时钟为基准
  // 计算相对偏移，不 mock 时钟（避免 jest Date mock 与内部 new Date() 脱钩）。
  const isoAgo = (ms: number): number => Date.now() - ms

  beforeEach(() => {
    setLocale('zh-CN')
  })

  it('中文档位与换算语义不变（60s/60m/24h/7d/30d/365d 边界）', () => {
    expect(formatRelativeTime(isoAgo(30 * 1000))).toBe('刚刚')
    expect(formatRelativeTime(isoAgo(59 * 1000))).toBe('刚刚')
    expect(formatRelativeTime(isoAgo(60 * 1000))).toBe('1分钟前')
    expect(formatRelativeTime(isoAgo(5 * 60 * 1000))).toBe('5分钟前')
    expect(formatRelativeTime(isoAgo(60 * 60 * 1000))).toBe('1小时前')
    expect(formatRelativeTime(isoAgo(23 * 60 * 60 * 1000))).toBe('23小时前')
    expect(formatRelativeTime(isoAgo(24 * 60 * 60 * 1000))).toBe('1天前')
    expect(formatRelativeTime(isoAgo(8 * 24 * 60 * 60 * 1000))).toBe('1周前')
    expect(formatRelativeTime(isoAgo(60 * 24 * 60 * 60 * 1000))).toBe('2个月前')
    expect(formatRelativeTime(isoAgo(366 * 24 * 60 * 60 * 1000))).toBe('1年前')
  })

  it('英文档位含单复数分支', () => {
    setLocale('en')
    expect(formatRelativeTime(isoAgo(30 * 1000))).toBe('just now')
    expect(formatRelativeTime(isoAgo(60 * 1000))).toBe('1 minute ago')
    expect(formatRelativeTime(isoAgo(5 * 60 * 1000))).toBe('5 minutes ago')
    expect(formatRelativeTime(isoAgo(2 * 60 * 60 * 1000))).toBe('2 hours ago')
    expect(formatRelativeTime(isoAgo(3 * 24 * 60 * 60 * 1000))).toBe('3 days ago')
    expect(formatRelativeTime(isoAgo(2 * 7 * 24 * 60 * 60 * 1000))).toBe('2 weeks ago')
    setLocale('zh-CN')
  })

  it('translateChoice 复数边界（0 与 2 走复数支）', () => {
    setLocale('en')
    expect(translateChoice('time.daysAgo', 0, { n: 0 })).toBe('0 days ago')
    expect(translateChoice('time.daysAgo', 2, { n: 2 })).toBe('2 days ago')
    expect(translateChoice('time.daysAgo', 1, { n: 1 })).toBe('1 day ago')
    setLocale('zh-CN')
  })
})
