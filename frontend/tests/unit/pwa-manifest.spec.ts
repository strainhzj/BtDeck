/**
 * PWA 品牌契约（v1.0.6 移动独有优化）：
 * - manifest 品牌化：BtDeck 名称、#059669 主题色（与 --color-primary 同源）、
 *   standalone、192/512/maskable 图标齐全且文件真实存在；
 * - vue.config pwa 配置：themeColor/msTileColor 品牌色、workbox 缓存前缀
 *   品牌化（btdeck，与模板遗留清理前缀区分）、skipWaiting=false +
 *   clientsClaim=true（更新经用户确认激活）；
 * - main.ts 接线：注册前先退休模板遗留 SW（源码契约，防回退到不注册状态）。
 */

import { existsSync, readFileSync } from 'fs'
import { resolve } from 'path'

const BRAND_COLOR = '#059669'

interface ManifestIcon {
  src: string
  sizes: string
  type: string
  purpose?: string
}

interface PwaManifest {
  name: string
  short_name: string
  theme_color: string
  display: string
  icons: ManifestIcon[]
}

const readManifest = (): PwaManifest =>
  JSON.parse(readFileSync(resolve(__dirname, '../../public/manifest.json'), 'utf8'))

describe('pwa brand contract', () => {
  it('品牌资源：完整 Logo/mark 和浏览器图标引用统一', () => {
    const publicDir = resolve(__dirname, '../../public')
    const indexHtml = readFileSync(resolve(publicDir, 'index.html'), 'utf8')

    expect(existsSync(resolve(publicDir, 'img/brand/btdeck-logo.png'))).toBe(true)
    expect(existsSync(resolve(publicDir, 'img/brand/btdeck-logo.svg'))).toBe(true)
    expect(existsSync(resolve(publicDir, 'img/brand/btdeck-logo-inverse.png'))).toBe(true)
    expect(existsSync(resolve(publicDir, 'img/brand/btdeck-logo-inverse.svg'))).toBe(true)
    expect(existsSync(resolve(publicDir, 'img/brand/btdeck-mark.png'))).toBe(true)
    expect(existsSync(resolve(publicDir, 'img/brand/btdeck-mark-inverse.png'))).toBe(true)
    expect(existsSync(resolve(publicDir, 'img/brand/btdeck-mark-micro.png'))).toBe(true)
    expect(existsSync(resolve(publicDir, 'img/brand/btdeck-mark-micro-inverse.png'))).toBe(true)
    expect(existsSync(resolve(publicDir, 'favicon.ico'))).toBe(true)
    expect(indexHtml).toContain('img/icons/favicon.svg')
    expect(indexHtml).toContain('img/icons/favicon-32x32.png')
    expect(indexHtml).toContain('img/icons/apple-touch-icon-180x180.png')
    expect(readFileSync(resolve(publicDir, 'img/icons/favicon.svg'), 'utf8')).not.toContain('<image')
  })
  it('manifest 品牌化：BtDeck 名称与 #059669 主题色、standalone 展示', () => {
    const manifest = readManifest()
    expect(manifest.name).toBe('BtDeck')
    expect(manifest.short_name).toBe('BtDeck')
    expect(manifest.theme_color).toBe(BRAND_COLOR)
    expect(manifest.display).toBe('standalone')
  })

  it('manifest 图标齐全（192/512/maskable）且文件真实存在', () => {
    const manifest = readManifest()
    const publicDir = resolve(__dirname, '../../public')
    const bySize = new Map(manifest.icons.map(icon => [icon.sizes, icon]))
    expect(bySize.get('192x192')).toBeDefined()
    expect(bySize.get('512x512')).toBeDefined()
    const maskable = manifest.icons.find(icon => icon.purpose === 'maskable')
    expect(maskable).toBeDefined()
    expect(maskable && maskable.sizes).toBe('512x512')
    manifest.icons.forEach(icon => {
      // icon.src 相对应用根（public 目录）声明
      const file = resolve(publicDir, icon.src)
      expect({ src: icon.src, exists: existsSync(file) }).toEqual({ src: icon.src, exists: true })
    })
  })

  it('vue.config pwa：品牌色注入、btdeck 缓存前缀、更新需用户确认', () => {
    const source = readFileSync(resolve(__dirname, '../../vue.config.js'), 'utf8')
    const pwaBlock = source.slice(source.indexOf('pwa: {'), source.indexOf('pluginOptions'))
    expect(pwaBlock).toContain(`themeColor: '${BRAND_COLOR}'`)
    expect(pwaBlock).toContain(`msTileColor: '${BRAND_COLOR}'`)
    expect(pwaBlock).toContain("cacheId: 'btdeck'")
    expect(pwaBlock).not.toContain("cacheId: 'vue-typescript-admin-template'")
    expect(pwaBlock).toContain('skipWaiting: false')
    expect(pwaBlock).toContain('clientsClaim: true')
    expect(pwaBlock).toContain("appleMobileWebAppCapable: 'yes'")
  })

  it('main.ts 接线：退休模板遗留 SW 后注册本版 worker（带标记共存）', () => {
    const source = readFileSync(resolve(__dirname, '../../src/main.ts'), 'utf8')
    expect(source).toContain('retireLegacyServiceWorkers')
    expect(source).toContain("import('@/registerServiceWorker')")
  })

  it('SW 注册脚本带标记（与模板遗留注册区分，retire 不误伤）', () => {
    const source = readFileSync(resolve(__dirname, '../../src/registerServiceWorker.ts'), 'utf8')
    expect(source).toContain('PWA_SW_SCRIPT_MARKER')
  })
})
