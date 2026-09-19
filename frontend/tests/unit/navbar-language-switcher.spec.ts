/**
 * 语言切换入口源码契约（desktop-bilingual-20260918.p1）。
 *
 * 挂载级验证不可行（Navbar 依赖 Element 下拉/徽章、登录页依赖完整表单链），
 * 沿用本仓「源码契约」模式直读实现文件钉死结构。防回流点：
 * - Navbar 语言下拉存在且走 store SetLanguage 动作（单一动作源）；
 * - 切换入口显式刷新 document.title（vue-i18n@8 无 locale 订阅 API）；
 * - 选项文案用语言自名（中文/English 不经 $t，属语言无关常量）；
 * - 相对时间源码不得回流硬编码中文（formatters 已接 i18n）；
 * - 保持既有图标契约（无 <svg / el-icon-）。
 */

import i18n from '@/i18n'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const readSource = (relativePath: string): string =>
  readFileSync(resolve(__dirname, '../../src', relativePath), 'utf8').replace(/\r\n/g, '\n')

describe('Navbar 语言切换器', () => {
  const source = readSource('layout/components/Navbar/index.vue')

  it('存在语言下拉且选项为语言自名（中文/English 字面量在 types 常量，不在模板硬编码）', () => {
    expect(source).toContain('class="lang-switcher')
    expect(source).toContain('@command="handleLanguageCommand"')
    expect(source).toContain('LOCALE_AUTONYMS')
    expect(source).toContain('SUPPORTED_LOCALES')
    // 模板不直接写死中英文选项文案（自名常量在 i18n/types.ts）
    const template = source.slice(0, source.indexOf('<script'))
    expect(template).not.toContain('>中文<')
    expect(template).not.toContain('>English<')
  })

  it('切换走 store SetLanguage 并显式刷新页面标题', () => {
    expect(source).toContain('AppModule.SetLanguage(command)')
    expect(source).toContain('resolvePageTitle(this.$route)')
    expect(source).toContain('isSupportedLocale(command)')
  })

  it('壳层文案走 $t 且键可达（首页/退出登录/反馈/通知）', () => {
    // 2026-09-19 修正：原契约锁的是 `$t('navigation.navbar.home')`——键实际位于
    // navigation.navbar.*，旧前缀使 zh 缺键返回空串（静默空文案）。
    // 现按真实键路径断言，并补可达性（i18n.te）防再次锁死错键。
    expect(source).toContain("$t('navigation.navbar.home')")
    expect(i18n.te('navigation.navbar.home')).toBe(true)
    expect(i18n.te('navigation.navbar.home', 'en')).toBe(true)
    expect(source).toContain("$t('navigation.navbar.logout')")
    expect(source).toContain("$t('navigation.navbar.feedback')")
    expect(source).toContain("$t('navigation.navbar.openNotifications')")
    expect(source).not.toContain('>首页<')
    expect(source).not.toContain('>退出登录<')
  })

  it('保持既有图标契约（无内联 svg / Element 图标类）', () => {
    const template = source.slice(0, source.indexOf('<script'))
    expect(template).not.toContain('<svg')
    expect(template).not.toContain('el-icon-')
  })
})

describe('登录页语言入口', () => {
  const source = readSource('views/login/index.vue')

  it('存在语言选项按钮且与 Navbar 同一动作源', () => {
    expect(source).toContain('class="lang-selector"')
    expect(source).toContain('handleLanguageSelect')
    expect(source).toContain('AppModule.SetLanguage(locale)')
    expect(source).toContain('isSupportedLocale(locale)')
    expect(source).toContain('resolvePageTitle(this.$route)')
  })
})

describe('语言状态单一动作源（app store）', () => {
  const source = readSource('store/modules/app.ts')

  it('language 状态 + SetLanguage 动作（rawError）+ 委托 i18n 层持久化', () => {
    expect(source).toContain('public language: Locale = getLocale()')
    expect(source).toContain('public SetLanguage(locale: Locale)')
    expect(source).toContain('setLocale(locale)')
  })
})

describe('Element UI 内置文案接线（main.ts）', () => {
  const source = readSource('main.ts')

  it('ElementLocale.i18n 挂到 vue-i18n 单例且根实例注入 i18n（el 包随语言响应式）', () => {
    expect(source).toContain("import ElementLocale from 'element-ui/lib/locale'")
    expect(source).toContain('ElementLocale.i18n((path: string) => i18n.t(path) as string)')
    // 挂接必须先于 Vue.use(ElementUI)，首次渲染即走接管路径
    expect(source.indexOf('ElementLocale.i18n')).toBeLessThan(source.indexOf('Vue.use(ElementUI)'))
    // 根实例注入 i18n，组件层 $t 可用且同一翻译源
    expect(source).toContain('i18n,')
    expect(source).toMatch(/new Vue\(\{\s*router,\s*store,\s*i18n,/)
  })
})

describe('相对时间防回流', () => {
  const source = readSource('utils/formatters.ts')

  it('formatRelativeTime 不再硬编码中文档位（走 i18n 键）', () => {
    expect(source).not.toContain('刚刚')
    expect(source).not.toContain('分钟前')
    expect(source).not.toContain('小时前')
    expect(source).toContain("translate('time.justNow')")
    expect(source).toContain("translateChoice('time.minutesAgo'")
  })
})
