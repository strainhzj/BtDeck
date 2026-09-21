/**
 * DownloaderSettingsDialog 整页复用形态初始化契约（2026-09-12 移动设置页无数据根修）：
 * /m/downloader/settings/:id 以 visible=true 创建弹窗时，@Watch('visible') 不会为
 * 初始值触发——挂载时必须补一次 initDialog，否则表单空白。
 * 注：该 SFC 模板含 ?. 可选链，jest 的 buble 模板编译器无法解析，无法真挂载，
 * 沿用 downloader-control-room-ui.spec 的源码契约模式；行为由浏览器实测兜底。
 */
import fs from 'fs'
import path from 'path'

const readSource = (): string =>
  fs.readFileSync(
    path.resolve(__dirname, '../../src/views/downloader/components/DownloaderSettingsDialog.vue'),
    'utf-8'
  )

/** 契约锚点缺失即红（与 mobile-shell 几何契约同款失败语义） */
const mustMatch = (source: string, re: RegExp, label: string): string => {
  const m = source.match(re)
  if (!m) throw new Error(`契约锚点缺失：${label}`)
  return m[0]
}

describe('DownloaderSettingsDialog 整页复用（visible 初始 true）初始化契约', () => {
  it('mounted 钩子在 visible 已为 true 时补一次 initDialog（watch 不为初始值触发）', () => {
    const source = readSource()
    const mountedBody = mustMatch(source, /mounted\(\): void \{[\s\S]*?\n  \}/, 'mounted 钩子')
    expect(mountedBody).toContain('if (this.visible)')
    expect(mountedBody).toMatch(/this\.initDialog\(\)/)
    // 补初始化必须在 matchMedia 页签处理之前判定，防止后续重构挪走
    expect(mountedBody.indexOf('if (this.visible)')).toBeLessThan(mountedBody.indexOf('matchMedia'))
  })

  it('@Watch(\'visible\') 打开路径保留（桌面 visible false→true 仍初始化）', () => {
    const source = readSource()
    expect(source).toContain(`@Watch('visible')`)
    expect(source).toMatch(/onVisibleChange\(val: boolean\) \{\s*if \(val\) \{\s*this\.initDialog\(\)/)
  })

  it('移动端顶部页签纯文字：≤780 媒体块隐藏页签图标与副标题', () => {
    const source = readSource()
    const mediaBlock = mustMatch(
      source,
      /@media \(max-width: 780px\) \{[\s\S]*?\n  \}\n\}/,
      '780 媒体块'
    )
    const labelRule = mediaBlock.slice(mediaBlock.indexOf('.workspace-tab-label'))
    expect(labelRule).toContain('&__icon')
    expect(labelRule).toMatch(/&__icon \{\s*display: none/)
    expect(labelRule).toContain('&__copy')
    expect(labelRule).toMatch(/small \{\s*display: none/)
  })
})
