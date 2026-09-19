/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/**
 * i18n 单例与同源翻译入口（桌面双语 P1）。
 *
 * 职责边界（PLANS/desktop-bilingual.md §3.1）：
 * - 组件层用 this.$t / $tc；非组件层（utils/router/请求层）一律走本文件导出的
 *   translate / translateChoice，保证同一翻译源。
 * - 语言选择顺序：手动偏好（localStorage）> 浏览器语言（按 navigator.languages
 *   顺序匹配 zh 前缀与 en 前缀）> 默认中文；解析为纯函数 resolveSupportedLocale 可测。
 * - localStorage 读取失败 / 值无效时安全回退（清除无效值），不抛异常（L02）。
 * - 缺译运行时回退：en 缺键回退 zh-CN；zh-CN 也缺时经 missing 钩子返回空串并
 *   console.warn（不显示 undefined / 原始键，L05）；缺译由 parity 测试在门禁拦截。
 * - Element UI 内置文案：main.ts 将 ElementLocale.i18n 挂到本单例，随语言响应式切换。
 *
 * 选型记录（2026-09-18，PLANS/bilingual/p1-i18n-decision.md）：
 * vue-i18n@8.28.2（v8 终版）精确钉版；v8 线已停止维护，风险以「单文件封装层 +
 * 最小 API 面（t/tc/setLocale）」缓解，后续如需换引擎只动本文件。
 */

import Vue from 'vue'
import VueI18n from 'vue-i18n'
import zhCN from './locales/zh-CN'
import en from './locales/en'
import {
  DEFAULT_LOCALE,
  Locale,
  LOCALE_STORAGE_KEY,
  RouteTitleMeta,
  isSupportedLocale
} from './types'

Vue.use(VueI18n)

/**
 * 语言解析纯函数（可测）：手动偏好优先，其次按浏览器语言列表顺序匹配。
 * 匹配规则：en* → en；zh* → zh-CN（zh-TW/zh-HK 等归一化到简中，翻译缺失即回退中文）。
 */
export function resolveSupportedLocale(
  stored: unknown,
  navigatorLanguages: readonly string[] | undefined,
  navigatorLanguage: string | undefined
): Locale {
  if (isSupportedLocale(stored)) {
    return stored
  }
  const candidates: readonly string[] =
    navigatorLanguages && navigatorLanguages.length > 0
      ? navigatorLanguages
      : navigatorLanguage
      ? [navigatorLanguage]
      : []
  for (const tag of candidates) {
    if (!tag) {
      continue
    }
    const lower = tag.toLowerCase()
    if (lower.indexOf('en') === 0) {
      return 'en'
    }
    if (lower.indexOf('zh') === 0) {
      return 'zh-CN'
    }
  }
  return DEFAULT_LOCALE
}

/** 读取手动偏好；值无效时顺手清除，存储不可用返回 null（L02） */
export function readStoredLocale(): Locale | null {
  try {
    const raw = window.localStorage.getItem(LOCALE_STORAGE_KEY)
    if (!raw) {
      return null
    }
    if (!isSupportedLocale(raw)) {
      window.localStorage.removeItem(LOCALE_STORAGE_KEY)
      return null
    }
    return raw
  } catch {
    return null
  }
}

/** 仅按浏览器语言解析（不含存储偏好），供后续设置页「跟随浏览器」类功能复用 */
export function detectBrowserLocale(): Locale {
  let languages: readonly string[] | undefined
  let language: string | undefined
  try {
    languages = navigator.languages
    language = navigator.language
  } catch {
    languages = undefined
    language = undefined
  }
  return resolveSupportedLocale(null, languages, language)
}

const initialLocale = resolveSupportedLocale(
  readStoredLocale(),
  navigatorLanguagesSafe(),
  navigatorLanguageSafe()
)

const i18n = new VueI18n({
  locale: initialLocale,
  fallbackLocale: DEFAULT_LOCALE,
  messages: {
    'zh-CN': zhCN,
    en: en
  },
  missing: (_locale: VueI18n.Locale, key: VueI18n.Path) => {
    // 双保险：parity 测试保证 zh-CN 完整，正常不应触达；触达时空串 + 告警，
    // 不渲染 undefined 或原始键（L05）。
    console.warn(`[i18n] 缺少翻译键: ${key}`)
    return ''
  }
})

function navigatorLanguagesSafe(): readonly string[] | undefined {
  try {
    return navigator.languages
  } catch {
    return undefined
  }
}

function navigatorLanguageSafe(): string | undefined {
  try {
    return navigator.language
  } catch {
    return undefined
  }
}

/** 当前语言（窄化为受支持的 Locale） */
export function getLocale(): Locale {
  return isSupportedLocale(i18n.locale) ? i18n.locale : DEFAULT_LOCALE
}

/** 同步 <html lang>（无障碍 + L04 检查点） */
export function applyDocumentLocale(): void {
  try {
    document.documentElement.lang = getLocale()
  } catch {
    // 非浏览器环境忽略
  }
}

/**
 * 切换语言：内存生效 + 持久化 + document.lang。
 * 调用方（语言切换入口）负责随后刷新 document.title（见 resolvePageTitle）。
 * 存储不可用时仅内存生效，不抛异常。
 */
export function setLocale(locale: Locale): void {
  i18n.locale = locale
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    // 存储不可用（隐私模式等）：语言仅当前会话生效
  }
  applyDocumentLocale()
}

/** 非组件层同源翻译入口（组件层请用 this.$t） */
export function translate(
  key: string,
  values?: { [key: string]: string | number }
): string {
  return i18n.t(key, values) as string
}

/**
 * 非组件层复数翻译入口（对应组件层 $tc）。
 * 复数文案格式「单|复」，choice 决定取支、values 提供插值。
 */
export function translateChoice(
  key: string,
  choice: number,
  values?: { [key: string]: string | number }
): string {
  return i18n.tc(key, choice, values) as string
}

/**
 * 路由标题解析：titleKey（桌面双语键）优先，缺省回退 meta.title 中文原值
 * （移动端路由未配 titleKey，保持中文不受双语影响）。
 */
export function routeTitle(meta: unknown): string {
  const titleMeta = meta as RouteTitleMeta | undefined
  if (titleMeta && titleMeta.titleKey) {
    return i18n.t(titleMeta.titleKey) as string
  }
  return (titleMeta && titleMeta.title) || ''
}

/** document.title 解析（permission.afterEach 与语言切换入口共用） */
export function resolvePageTitle(route: { meta?: unknown } | null | undefined): string {
  if (route && route.meta) {
    const title = routeTitle(route.meta)
    if (title) {
      return title
    }
  }
  return 'BtDeck'
}

/** reasonCode → camelCase 键（AUTH_RATE_LIMITED → authRateLimited） */
function reasonCodeToMessageKey(reasonCode: string): string {
  return reasonCode
    .toLowerCase()
    .split('_')
    .map((part, idx) =>
      idx === 0 || !part ? part : part.charAt(0).toUpperCase() + part.slice(1)
    )
    .join('')
}

/** pydantic 校验错误项（全局异常处理器归一化后的 data.errors 数组成员） */
interface ValidationItem {
  loc?: unknown
  msg?: unknown
  type?: unknown
}

/** 取 loc 末段作为字段标识（['body','hashes'] → 'hashes'；非数组原样转字符串） */
function validationField(item: ValidationItem): string {
  const loc = item.loc
  if (Array.isArray(loc) && loc.length > 0) {
    return String(loc[loc.length - 1])
  }
  return String(loc ?? '')
}

/** pydantic type → errors.validation.* 键（camelCase：too_short → tooShort） */
function validationTypeKey(type: string): string {
  return reasonCodeToMessageKey(type)
}

/**
 * E17：按 pydantic type/loc 字典化单条校验错误文案。
 * 未知 type 回退 generic；字段标识原样展示（API 字段名，不翻译）。
 */
function validationItemMessage(item: ValidationItem): string {
  const field = validationField(item)
  const type = typeof item.type === 'string' && item.type ? item.type : ''
  const key = `errors.validation.${validationTypeKey(type || 'generic')}`
  if (i18n.te(key) || i18n.te(key, DEFAULT_LOCALE)) {
    return i18n.t(key, { field }) as string
  }
  return i18n.t('errors.validation.generic', { field }) as string
}

/** 从归一化后的响应体提取 data 载荷（业务错误信封与 HTTP 错误信封同构） */
function envelopeDataOf(body: unknown): unknown {
  if (!body || typeof body !== 'object') return undefined
  return (body as { data?: unknown }).data
}

/**
 * 按错误对象解析本地化文案（错误契约，主计划 §3.3；禁止按中文 msg 匹配）：
 * 1. rawResponse.data.data.reasonCode 命中 errors.byCode.* → 返回对应译文；
 * 2. 无 reasonCode 但为 422（data.errors 数组）→ 按 type/loc 字典化（E17，至多取首 2 条）；
 * 3. 有 reasonCode 但未登记 → 返回 fallback（避免英文界面透出中文 msg）；
 * 4. 无 reasonCode → 返回 error.message || fallback（保留未契约化路径的原始信息）。
 */
export function apiErrorMessage(error: unknown, fallback: string): string {
  const body = (
    error as { rawResponse?: { data?: { code?: unknown, data?: unknown } } } | null | undefined
  )?.rawResponse?.data
  const d = envelopeDataOf(body)
  const rc =
    d && typeof d === 'object' && !Array.isArray(d)
      ? (d as { reasonCode?: unknown }).reasonCode
      : undefined
  if (typeof rc === 'string' && rc) {
    const key = `errors.byCode.${reasonCodeToMessageKey(rc)}`
    if (i18n.te(key) || i18n.te(key, DEFAULT_LOCALE)) {
      return i18n.t(key) as string
    }
    return fallback
  }
  // E17：422 校验错误数组（全局异常处理器归一化后的形态）
  const code = (body as { code?: unknown } | undefined)?.code
  if (
    String(code) === '422' &&
    d && typeof d === 'object' && Array.isArray((d as { errors?: unknown }).errors)
  ) {
    const items = (d as { errors: ValidationItem[] }).errors
    if (items.length > 0) {
      return items.slice(0, 2).map(validationItemMessage).join('；')
    }
  }
  return (error instanceof Error && error.message) || fallback
}

/**
 * 已解析响应（非拋出形态）的业务错误文案：优先 data.reasonCode 本地化，
 * 否则回退 fallback（供 response.code 非 2xx 但拦截器未拒绝的分支使用）。
 */
export function apiResponseMessage(
  response: { code?: unknown, msg?: unknown, data?: unknown } | null | undefined,
  fallback: string
): string {
  if (!response) return fallback
  const d = envelopeDataOf(response)
  const rc =
    d && typeof d === 'object' && !Array.isArray(d)
      ? (d as { reasonCode?: unknown }).reasonCode
      : undefined
  if (typeof rc === 'string' && rc) {
    const key = `errors.byCode.${reasonCodeToMessageKey(rc)}`
    if (i18n.te(key) || i18n.te(key, DEFAULT_LOCALE)) {
      return i18n.t(key) as string
    }
    return fallback
  }
  return (typeof response.msg === 'string' && response.msg) || fallback
}

// 模块加载即同步 <html lang>；document.title 由 permission.ts afterEach 首次驱动。
applyDocumentLocale()

export default i18n
