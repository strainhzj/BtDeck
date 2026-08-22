export const TRADITIONAL_VIRTUAL_ROW_HEIGHT = 32
export const TRADITIONAL_VIRTUAL_OVERSCAN = 8
export const TRADITIONAL_VIRTUAL_VIEWPORT_FALLBACK = 480

export interface TraditionalVirtualWindow {
  startIndex: number
  endIndex: number
  topSpacerHeight: number
  bottomSpacerHeight: number
}

/**
 * 计算传统表格当前需要渲染的行窗口。
 * endIndex 使用 Array.slice 的排他语义，窗口外的行由上下占位高度维持滚动条长度。
 */
export function calculateTraditionalVirtualWindow(
  itemCount: number,
  scrollTop: number,
  viewportHeight: number,
  rowHeight = TRADITIONAL_VIRTUAL_ROW_HEIGHT,
  overscan = TRADITIONAL_VIRTUAL_OVERSCAN
): TraditionalVirtualWindow {
  const normalizedCount = Math.max(0, Math.trunc(itemCount))
  if (normalizedCount === 0) {
    return {
      startIndex: 0,
      endIndex: 0,
      topSpacerHeight: 0,
      bottomSpacerHeight: 0
    }
  }

  const normalizedRowHeight = Math.max(1, rowHeight)
  const normalizedViewportHeight = Math.max(0, viewportHeight)
  const normalizedOverscan = Math.max(0, Math.trunc(overscan))
  const visibleCount = Math.max(
    1,
    Math.ceil(normalizedViewportHeight / normalizedRowHeight)
  )
  const maxFirstVisibleIndex = Math.max(0, normalizedCount - visibleCount)
  const firstVisibleIndex = Math.min(
    maxFirstVisibleIndex,
    Math.max(0, Math.floor(scrollTop / normalizedRowHeight))
  )
  const startIndex = Math.max(0, firstVisibleIndex - normalizedOverscan)
  const endIndex = Math.min(
    normalizedCount,
    firstVisibleIndex + visibleCount + normalizedOverscan
  )

  return {
    startIndex,
    endIndex,
    topSpacerHeight: startIndex * normalizedRowHeight,
    bottomSpacerHeight: (normalizedCount - endIndex) * normalizedRowHeight
  }
}
