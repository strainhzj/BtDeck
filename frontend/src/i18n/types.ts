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
 * i18n 基础类型与常量（桌面双语 P1）。
 *
 * 设计要点（PLANS/desktop-bilingual.md §3.1）：
 * - 支持语言固定为 zh-CN / en 两种；中文为最终回退。
 * - 手动偏好 > 浏览器语言 > 默认中文的选择顺序在 src/i18n/index.ts 实现。
 * - localStorage 持久化失败 / 值无效时安全回退，不抛异常（L02）。
 */

export const SUPPORTED_LOCALES = ['zh-CN', 'en'] as const

export type Locale = typeof SUPPORTED_LOCALES[number]

export const DEFAULT_LOCALE: Locale = 'zh-CN'

/** 语言偏好持久化键（与 btdeck-theme 同一命名风格） */
export const LOCALE_STORAGE_KEY = 'btdeck-lang'

/** 消息树：叶子为文案字符串（含 vue-i18n 复数「a|b」形式），中间节点为分组 */
export interface MessageTree {
  [key: string]: string | MessageTree
}

/** 路由 meta 中与标题相关的字段（titleKey 为桌面双语键，title 保留中文原值供移动端消费） */
export interface RouteTitleMeta {
  title?: string
  titleKey?: string
}

export function isSupportedLocale(value: unknown): value is Locale {
  return (
    typeof value === 'string' &&
    (SUPPORTED_LOCALES as readonly string[]).indexOf(value) >= 0
  )
}

/**
 * 语言自名（autonym）：语言选择器中各选项的展示名。
 * 不随当前界面语言翻译——「中文」在英文界面下仍显示「中文」。
 */
export const LOCALE_AUTONYMS: Record<Locale, string> = {
  'zh-CN': '中文',
  en: 'English'
}
