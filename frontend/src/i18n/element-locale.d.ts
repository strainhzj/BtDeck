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
 * element-ui 语言包与 Locale 单例的模块声明。
 *
 * 注意：本文件必须是「全局脚本」形态（顶层无 import/export），
 * 否则 declare module 会退化为模块增强而非环境声明，类型检查报 TS7016。
 * ElementMessageTree 与 src/i18n/types.ts 的 MessageTree 结构等价
 * （环境声明内不能 import，只能内联同构类型）。
 */

declare module 'element-ui/lib/locale' {
  interface ElementLocaleSingleton {
    /** 接管组件内文案取值：挂到 vue-i18n 后内置语言随界面语言响应式切换 */
    i18n(fn: (path: string, ...args: unknown[]) => string): void
    use(lang: string, messages: unknown): void
    t(path: string, options?: { [key: string]: unknown }): string
  }
  const Locale: ElementLocaleSingleton
  export default Locale
}

declare module 'element-ui/lib/locale/lang/zh-CN' {
  interface ElementMessageTree {
    [key: string]: string | ElementMessageTree
  }
  const messages: { el: ElementMessageTree }
  export default messages
}

declare module 'element-ui/lib/locale/lang/en' {
  const messages: { el: ElementMessageTree }
  export default messages
}
