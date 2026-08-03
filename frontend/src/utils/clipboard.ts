/**
 * 复制文本到系统剪贴板。
 *
 * HTTPS/localhost 优先使用 Clipboard API；HTTP 部署、旧浏览器或权限拒绝时，
 * 回退到隐藏 textarea + execCommand，确保局域网部署仍可复制。
 */
export async function copyTextToClipboard(text: string): Promise<void> {
  const clipboard = typeof navigator !== 'undefined' ? navigator.clipboard : undefined
  if (clipboard && typeof clipboard.writeText === 'function') {
    try {
      await clipboard.writeText(text)
      return
    } catch {
      // 权限拒绝或非安全上下文实现异常时继续使用 DOM 回退。
    }
  }

  if (typeof document === 'undefined' || !document.body || typeof document.execCommand !== 'function') {
    throw new Error('当前环境不支持剪贴板复制')
  }

  const activeElement = document.activeElement instanceof HTMLElement
    ? document.activeElement
    : null
  const textArea = document.createElement('textarea')
  textArea.value = text
  textArea.setAttribute('readonly', '')
  textArea.setAttribute('aria-hidden', 'true')
  textArea.style.position = 'fixed'
  textArea.style.left = '-9999px'
  textArea.style.top = '0'
  textArea.style.opacity = '0'

  document.body.appendChild(textArea)
  try {
    textArea.select()
    textArea.setSelectionRange(0, text.length)
    if (!document.execCommand('copy')) {
      throw new Error('浏览器拒绝复制命令')
    }
  } finally {
    document.body.removeChild(textArea)
    activeElement?.focus()
  }
}
