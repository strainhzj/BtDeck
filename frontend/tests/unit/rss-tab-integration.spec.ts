/**
 * 下载器设置弹窗 RSS 页签接线契约（feature rss-subscription-2026-09-24）。
 *
 * DownloaderSettingsDialog 模板含 ?. 可选链，jest 的 buble 模板编译器无法真挂载
 * （同 downloader-settings-dialog-init.spec 说明），沿用源码契约锚点模式。
 * 组件行为回归见 rss-subscription-tab.spec.ts；demo 分支见 demo-request.spec.ts。
 */
import fs from 'fs'
import path from 'path'

/** 行尾归一化：Windows autocrlf 检出为 CRLF 时多行/正则契约断言不受影响 */
const read = (p: string): string =>
  fs.readFileSync(path.resolve(__dirname, p), 'utf-8').replace(/\r\n/g, '\n')

describe('DownloaderSettingsDialog RSS 页签接线契约', () => {
  it('注册并渲染 rssSubscription 页签（能力门控 rssTabAvailable）', () => {
    const source = read('../../src/views/downloader/components/DownloaderSettingsDialog.vue')
    expect(source).toContain(`name="rssSubscription"`)
    expect(source).toContain('v-if="rssTabAvailable"')
    expect(source).toMatch(/<rss-subscription-tab/)
    expect(source).toMatch(/ref="rssSubscriptionTabRef"/)
    // 组件注册
    expect(source).toContain('RssSubscriptionTab,')
    expect(source).toMatch(/import RssSubscriptionTab from '\.\/RssSubscriptionTab\.vue'/)
    // 门控：仅 qB(0)/TR(1) 开放，rTorrent(2) 暂不开放
    expect(source).toMatch(/get rssTabAvailable\(\): boolean \{[\s\S]*?downloaderType === 0 \|\| downloaderType === 1/)
  })

  it('页签标题走 i18n 键（downloader.tabs.rss*），图标使用 rss', () => {
    const source = read('../../src/views/downloader/components/DownloaderSettingsDialog.vue')
    const pane = source.slice(source.indexOf('name="rssSubscription"'))
    const paneBlock = pane.slice(0, pane.indexOf('</el-tab-pane>'))
    expect(paneBlock).toContain(`$t('downloader.tabs.rssTitle')`)
    expect(paneBlock).toContain(`$t('downloader.tabs.rssDesc')`)
    expect(paneBlock).toMatch(/<LucideIcon name="rss"/)
  })

  it('LucideIcon 图标表注册 rss 与 external-link', () => {
    const source = read('../../src/components/common/LucideIcon.vue')
    expect(source).toMatch(/\n  Rss,\n/)
    expect(source).toMatch(/\n  ExternalLink\n/)
    expect(source).toMatch(/'external-link': ExternalLink/)
    expect(source).toMatch(/\n  rss: Rss,/)
  })
})
