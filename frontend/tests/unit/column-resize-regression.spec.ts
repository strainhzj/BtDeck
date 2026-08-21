import { readFileSync } from 'fs'
import { resolve } from 'path'

/**
 * 列宽拖拽 2026-08-21 修复的静态契约（防回归核心，源码扫描式）：
 *
 * 1. 手柄样式必须全局可达——历史上只写在 torrent-theme.scss（仅列表模式
 *    scoped 引入），传统模式手柄 span 零样式整体失效；现唯一来源
 *    torrent-column-resize.scss，经 styles/index.scss 全局引入。
 *    两份主题文件均不得再各自携带手柄规则（scoped 引入只对本视图生效）。
 * 2. body.column-resizing 同理：scoped 编译成 body[data-v-x] 永不匹配。
 * 3. 名称列在两视图均登记默认宽度并渲染手柄（曾为唯一 auto 列无手柄）；
 *    tableMinWidth 计入 name，不再有 +200 隐式下限。
 * 4. 两视图表格按列宽总和严格定宽（qBittorrent 风格 width+minWidth 双绑定，
 *    视口富余右侧留白，名称列不再自动填满）。
 * 5. 名称省略号跟随列宽：.torrent-name-text 曾硬编码 max-width:300px，
 *    名称列拖宽后仍在 300px 截断留白；传统模式 .torrent-name-cell 曾无
 *    省略样式（td 兜底只裁剪不出"..."）。
 *
 * 运行时行为（拖拽会话/落盘/表级定宽）由 torrent-list-view-component.spec
 * 与 traditional-view-component.spec 的名称列用例保护。
 */
const listSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/index.vue'),
  'utf8'
)
const traditionalSource = readFileSync(
  resolve(__dirname, '../../src/views/torrents/TraditionalView.vue'),
  'utf8'
)
const globalEntrySource = readFileSync(
  resolve(__dirname, '../../src/styles/index.scss'),
  'utf8'
)
const resizerPartialSource = readFileSync(
  resolve(__dirname, '../../src/styles/torrent-column-resize.scss'),
  'utf8'
)
const listThemeSource = readFileSync(
  resolve(__dirname, '../../src/styles/torrent-theme.scss'),
  'utf8'
)
const traditionalThemeSource = readFileSync(
  resolve(__dirname, '../../src/styles/traditional-view-theme.scss'),
  'utf8'
)

describe('列宽拖拽修复静态契约', () => {
  it('手柄样式唯一来源为全局 partial，经 index.scss 全局引入（scoped 引入会使另一视图整体失效）', () => {
    expect(resizerPartialSource)
      .toMatch(/\.torrent-table thead th:not\(\.action-column\)\s*\{[\s\S]*?position:\s*relative;/)
    expect(resizerPartialSource)
      .toMatch(/\.torrent-table thead th \.column-resizer\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?cursor:\s*col-resize;/)
    // 传统表头为浅色背景，白色反馈条不可见，必须用主题色
    expect(resizerPartialSource)
      .toMatch(/\.traditional-table thead th \.column-resizer\s*\{[\s\S]*?var\(--color-primary\)/)
    expect(resizerPartialSource).toContain('body.column-resizing')
    expect(globalEntrySource).toContain("@import './torrent-column-resize.scss';")
    // 两份主题均被各视图 scoped 引入：不得再携带手柄规则，防止样式再次只对单视图生效
    expect(listThemeSource).not.toContain('.column-resizer')
    expect(listThemeSource).not.toContain('body.column-resizing')
    expect(traditionalThemeSource).not.toContain('.column-resizer')
    expect(traditionalThemeSource).not.toContain('body.column-resizing')
  })

  it('名称列在两视图均登记默认宽度并渲染手柄（含双击恢复默认）', () => {
    expect(listSource).toContain('name: 400,')
    expect(traditionalSource).toContain('name: 200,')
    for (const source of [listSource, traditionalSource]) {
      expect(source).toContain(":style=\"columnWidthStyle('name')\"")
      expect(source).toContain("@mousedown.stop.prevent=\"startColumnResize('name', $event)\"")
      expect(source).toContain("@dblclick.stop.prevent=\"handleColumnResizeDblclick('name')\"")
    }
  })

  it('tableMinWidth 计入名称列，不再有 +200 隐式下限', () => {
    expect(listSource).toMatch(/optionalKeys = \[\s*'name', 'downloadSpeed'/)
    expect(traditionalSource).toMatch(/optionalKeys = \[\s*'name', 'size',/)
    expect(listSource).not.toContain('sumColumnWidths(visibleKeys) + 200')
    expect(traditionalSource).not.toContain("...visibleKeys]) + 200")
  })

  it('两视图表格按列宽总和严格定宽（qBittorrent 风格 width+minWidth 双绑定）', () => {
    const strictWidthBinding = "width: tableMinWidth + 'px', minWidth: tableMinWidth + 'px'"
    expect(listSource).toContain(strictWidthBinding)
    expect(traditionalSource).toContain(strictWidthBinding)
  })

  it('名称省略号跟随列宽：无 300px 硬编码，flex 收缩 + 传统单元格补省略', () => {
    expect(listThemeSource).not.toContain('max-width: 300px')
    expect(listThemeSource)
      .toMatch(/\.torrent-name\s*\{[\s\S]*?overflow:\s*hidden;/)
    expect(listThemeSource)
      .toMatch(/\.torrent-name-text\s*\{[\s\S]*?flex:\s*1;[\s\S]*?min-width:\s*0;[\s\S]*?text-overflow:\s*ellipsis;/)
    expect(traditionalSource)
      .toMatch(/\.torrent-name-cell\s*\{[\s\S]*?overflow:\s*hidden;[\s\S]*?text-overflow:\s*ellipsis;/)
  })
})
