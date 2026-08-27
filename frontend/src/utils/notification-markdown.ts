/* eslint-disable camelcase */
import { NotificationFailureItem } from '@/api/notification'

/**
 * 通知内容 Markdown-lite 渲染：桌面通知详情弹窗与移动通知详情共用，保证两端文本渲染一致。
 * 按行分块转换（标题 #/##/###、分隔线 ---、无序列表 - 、段落），输入先做 HTML 转义，
 * 最后在结构化输出上做内联替换（**粗体**、`行内代码`）。
 */
export function renderNotificationContent(content: string): string {
  if (!content) return ''
  // 按 Markdown 规则分块处理：先拆成行，逐行转换，再合并
  const lines = content.split('\n')
  const html: string[] = []
  let inList = false

  for (const raw of lines) {
    const line = raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const trimmed = line.trim()

    // 空行
    if (trimmed === '') {
      if (inList) { html.push('</ul>'); inList = false }
      continue
    }

    // 标题
    if (trimmed.startsWith('### ')) {
      if (inList) { html.push('</ul>'); inList = false }
      html.push(`<h4>${trimmed.slice(4)}</h4>`)
      continue
    }
    if (trimmed.startsWith('## ')) {
      if (inList) { html.push('</ul>'); inList = false }
      html.push(`<h3>${trimmed.slice(3)}</h3>`)
      continue
    }
    if (trimmed.startsWith('# ')) {
      if (inList) { html.push('</ul>'); inList = false }
      html.push(`<h2>${trimmed.slice(2)}</h2>`)
      continue
    }

    // 分隔线
    if (trimmed === '---') {
      if (inList) { html.push('</ul>'); inList = false }
      html.push('<hr />')
      continue
    }

    // 列表项
    if (trimmed.startsWith('- ')) {
      if (!inList) { html.push('<ul>'); inList = true }
      html.push(`<li>${trimmed.slice(2)}</li>`)
      continue
    }

    // 普通段落
    if (inList) { html.push('</ul>'); inList = false }
    html.push(`<p>${trimmed}</p>`)
  }
  if (inList) html.push('</ul>')

  // 内联格式：粗体、行内代码（在结构化输出上做替换）
  return html
    .join('\n')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
}

/**
 * 通知列表摘要纯文本化：剥离 Markdown-lite 语法记号（标题 #/##/###、分隔线 ---、
 * 列表 -、粗体 **、行内代码 `），供桌面/移动列表摘要纯文本插值共用，
 * 避免未打开详情前裸露渲染字符；完整渲染仍走 renderNotificationContent。
 * 语法集合与其保持一致，块级记号逐行剥离，内联记号在合并后替换。
 */
export function plainNotificationContent(content: string): string {
  if (!content) return ''
  const lines: string[] = []
  for (const raw of content.split('\n')) {
    const trimmed = raw.trim()
    // 空行与分隔线不产出摘要片段
    if (trimmed === '' || trimmed === '---') continue
    if (trimmed.startsWith('### ')) lines.push(trimmed.slice(4))
    else if (trimmed.startsWith('## ')) lines.push(trimmed.slice(3))
    else if (trimmed.startsWith('# ')) lines.push(trimmed.slice(2))
    else if (trimmed.startsWith('- ')) lines.push(trimmed.slice(2))
    else lines.push(trimmed)
  }
  return lines
    .join(' ')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`(.*?)`/g, '$1')
    .trim()
}

/** 失败明细展示目标名：按文件名/路径字段依次回退，缺省显示记录 id */
export function notificationFailureTarget(item: NotificationFailureItem): string {
  return item.file_name || item.file_path || item.canonical_path || item.quarantine_path || (item.id ? `记录 ${item.id}` : '未知项')
}
