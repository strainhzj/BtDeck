/**
 * notification-markdown.ts 渲染逻辑单元测试。
 *
 * 核心契约：通知内容 Markdown-lite 渲染（标题/列表/粗体/行内代码/分隔线）
 * 由桌面 NotificationDrawer 详情与移动通知详情共用，本测试锁定两端一致的行为：
 * 结构分块正确、输入先转义防注入、内联格式在结构化输出上替换。
 */
import { notificationFailureTarget, renderNotificationContent } from '@/utils/notification-markdown'

const countOf = (source: string, re: RegExp): number => (source.match(re) || []).length

describe('renderNotificationContent', () => {
  it('空内容返回空串', () => {
    expect(renderNotificationContent('')).toBe('')
  })

  it('普通行渲染为段落', () => {
    expect(renderNotificationContent('任务已完成')).toBe('<p>任务已完成</p>')
  })

  it('多行段落与空行：空行不产出节点', () => {
    const html = renderNotificationContent('第一段\n\n第二段')
    expect(html).toBe('<p>第一段</p>\n<p>第二段</p>')
  })

  it('一至三级标题分别渲染为 h2/h3/h4', () => {
    const html = renderNotificationContent('# 大标题\n## 中标题\n### 小标题')
    expect(html).toContain('<h2>大标题</h2>')
    expect(html).toContain('<h3>中标题</h3>')
    expect(html).toContain('<h4>小标题</h4>')
  })

  it('分隔线渲染为 hr 且闭合前置列表', () => {
    const html = renderNotificationContent('- 项目\n---')
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>项目</li>')
    expect(html).toContain('</ul>')
    expect(html).toContain('<hr />')
  })

  it('连续列表项合并为一个 ul，列表后段落闭合列表', () => {
    const html = renderNotificationContent('- 甲\n- 乙\n收尾说明')
    expect(html).toBe('<ul>\n<li>甲</li>\n<li>乙</li>\n</ul>\n<p>收尾说明</p>')
  })

  it('粗体与行内代码在结构化输出上替换', () => {
    const html = renderNotificationContent('**重要**：使用 `docker compose` 部署')
    expect(html).toContain('<strong>重要</strong>')
    expect(html).toContain('<code>docker compose</code>')
  })

  it('HTML 输入先转义，防止内容注入', () => {
    const html = renderNotificationContent('<script>alert(1)</script>')
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })

  it('转义后的尖括号不会被误认为标题语法', () => {
    const html = renderNotificationContent('<h1>x')
    expect(html).toBe('<p>&lt;h1&gt;x</p>')
  })

  it('末尾未闭合的列表在输出尾部补闭合标签', () => {
    const html = renderNotificationContent('- 仅一项')
    expect(html.endsWith('</ul>')).toBe(true)
  })

  it('CRLF 行尾兼容：\\r 在 trim 中去除，不残留在输出', () => {
    const html = renderNotificationContent('段落\r\n- 列表项\r\n## 标题')
    expect(html).toContain('<p>段落</p>')
    expect(html).toContain('<li>列表项</li>')
    expect(html).toContain('<h3>标题</h3>')
    expect(html).not.toContain('\r')
  })

  it('& 亦被转义（与 < > 同级，防实体注入）', () => {
    expect(renderNotificationContent('a & b')).toBe('<p>a &amp; b</p>')
    expect(renderNotificationContent('&lt;script&gt;')).toContain('&amp;lt;')
  })

  it('纯空白行视同空行，不产出空段落节点', () => {
    const html = renderNotificationContent('上\n   \n下')
    expect(html).toBe('<p>上</p>\n<p>下</p>')
  })

  it('标题与空行都会闭合前置列表（列表被打断不再复用同一 ul）', () => {
    const html = renderNotificationContent('- 甲\n# 标题')
    expect(html.indexOf('</ul>')).toBeLessThan(html.indexOf('<h2>'))
    const html2 = renderNotificationContent('- 甲\n\n- 乙')
    expect(countOf(html2, /<ul>/g)).toBe(2)
  })

  it('内联替换覆盖全部块级节点：列表项内粗体、标题内行内代码', () => {
    const html = renderNotificationContent('- **重点** 项\n## 用 `docker` 部署')
    expect(html).toContain('<li><strong>重点</strong> 项</li>')
    expect(html).toContain('<h3>用 <code>docker</code> 部署</h3>')
  })

  it('未配对的 ** 与 ` 保持字面量，不产生半截标签', () => {
    const html = renderNotificationContent('a ** b 与 c ` d')
    expect(html).toBe('<p>a ** b 与 c ` d</p>')
  })

  it('连续分隔线渲染为两个 hr', () => {
    const html = renderNotificationContent('---\n---')
    expect(countOf(html, /<hr \/>/g)).toBe(2)
  })
})

describe('notificationFailureTarget', () => {
  it('优先 file_name', () => {
    expect(notificationFailureTarget({ file_name: 'a.txt', file_path: '/x/a.txt', reason: 'r' })).toBe('a.txt')
  })

  it('file_name 缺失时回退 file_path / canonical_path / quarantine_path', () => {
    expect(notificationFailureTarget({ file_path: '/x/a.txt', reason: 'r' })).toBe('/x/a.txt')
    expect(notificationFailureTarget({ canonical_path: '/c/a.txt', reason: 'r' })).toBe('/c/a.txt')
    expect(notificationFailureTarget({ quarantine_path: '/q/a.txt', reason: 'r' })).toBe('/q/a.txt')
  })

  it('全部路径字段缺失时回退记录 id，再缺省为未知项', () => {
    expect(notificationFailureTarget({ id: 7, reason: 'r' })).toBe('记录 7')
    expect(notificationFailureTarget({ reason: 'r' })).toBe('未知项')
  })
})
