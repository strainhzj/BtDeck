/**
 * 设置页两页签移动布局源码契约（downloader-settings-mobile-layout 2026-09-12）：
 * - PathMappingTab ≤780：header-actions 与描述拉开间距、按钮压过全局紧凑重制
 *   （30px/9px）的 40px/13px 触控规格——按钮规则必须走 ::v-deep（同特异性
 *   后位源序胜出，改回嵌套写法会被紧凑重制反压）；
 * - TagManagementTab ≤640：工具栏 flex 行布局——搜索撑满 + 新增标签收缩同行
 *   （此前块级纵堆，搜索与新增各占一行）。
 * CSS 媒体查询在 jsdom 不生效，沿用 mobile-shell/DownloaderSettingsDialog 的
 * 源码契约模式；视觉行为由 375×812 浏览器实测兜底（见 feature_list evidence）。
 */
import fs from 'fs'
import path from 'path'

const readTabSource = (rel: string): string =>
  fs.readFileSync(path.resolve(__dirname, rel), 'utf-8')

/** 按花括号计数提取完整媒体块（SCSS 嵌套下正则截断不可靠） */
const extractMediaBlock = (source: string, query: string): string => {
  const start = source.indexOf(query)
  if (start < 0) throw new Error(`契约锚点缺失：${query}`)
  let depth = 0
  let opened = false
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    if (source[i] === '{') {
      depth++
      opened = true
    } else if (source[i] === '}') {
      depth--
      if (opened && depth === 0) return source.slice(start, i + 1)
    }
  }
  throw new Error(`媒体块未闭合：${query}`)
}

describe('PathMappingTab 移动布局契约（≤780）', () => {
  const source = readTabSource('../../src/views/downloader/components/PathMappingTab.vue')
  const media = extractMediaBlock(source, '@media (max-width: 780px)')

  it('媒体块含 tab-header 列布局与 header-actions 规则', () => {
    expect(media).toContain('.tab-header')
    expect(media).toContain('.header-actions')
    const headerRule = media.slice(media.indexOf('.tab-header'))
    expect(headerRule).toMatch(/flex-direction: column/)
  })

  it('按钮行与上方描述拉开间距（margin-top ≥ 10px，2026-09-12 用户反馈）', () => {
    const rule = media.slice(media.indexOf('.header-actions'))
    const m = rule.match(/margin-top: (\d+)px/)
    if (!m) throw new Error('契约锚点缺失：header-actions margin-top')
    expect(Number(m[1])).toBeGreaterThanOrEqual(10)
  })

  it('按钮触控规格 40px 高/13px 字号/并排（且必须 ::v-deep 压过紧凑重制）', () => {
    const rule = media.slice(media.indexOf('.header-actions'))
    // ::v-deep 是压过全局紧凑重制（.header-actions ::v-deep .el-button 30px/9px）
    // 的机制本身：同特异性、后位源序胜出；改回嵌套 .el-button 即刻被反压
    expect(rule).toContain('::v-deep .el-button')
    expect(rule).toMatch(/min-height: 40px/)
    expect(rule).toMatch(/font-size: 13px/)
    expect(rule).toMatch(/flex: 1/)
    expect(rule).toMatch(/margin-left: 0/)
  })
})

describe('TagManagementTab 工具栏并排契约（≤640）', () => {
  const source = readTabSource('../../src/views/downloader/components/TagManagementTab.vue')
  const media = extractMediaBlock(source, '@media (max-width: 640px)')

  it('工具栏为 flex 行布局（搜索与新增同行，非纵堆）', () => {
    const rule = media.slice(media.indexOf('.toolbar {'))
    expect(rule).toMatch(/display: flex/)
    expect(rule).not.toMatch(/flex-direction: column/)
  })

  it('搜索侧弹性撑满、新增侧收缩（并排的几何前提）', () => {
    expect(media).toMatch(/\.toolbar-left \{\s*flex: 1 1 auto;\s*min-width: 0/)
    expect(media).toMatch(/\.toolbar-right \{\s*flex: 0 0 auto/)
    // 搜索框宽度走容器（击败模板内联 280px）
    expect(media).toMatch(/\.toolbar-left \.el-input \{\s*width: 100% !important/)
  })
})
