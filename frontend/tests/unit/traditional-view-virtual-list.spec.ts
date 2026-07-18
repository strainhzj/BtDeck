import {
  calculateTraditionalVirtualWindow,
  TRADITIONAL_VIRTUAL_ROW_HEIGHT
} from '@/views/torrents/utils/traditionalVirtualList'

describe('traditional view virtual list', () => {
  it('returns an empty window for an empty page', () => {
    expect(calculateTraditionalVirtualWindow(0, 0, 320)).toEqual({
      startIndex: 0,
      endIndex: 0,
      topSpacerHeight: 0,
      bottomSpacerHeight: 0
    })
  })

  it('renders all rows when the current page fits in the viewport', () => {
    const result = calculateTraditionalVirtualWindow(6, 0, 320)

    expect(result.startIndex).toBe(0)
    expect(result.endIndex).toBe(6)
    expect(result.topSpacerHeight).toBe(0)
    expect(result.bottomSpacerHeight).toBe(0)
  })

  it('renders only the visible rows plus overscan for a long page', () => {
    const result = calculateTraditionalVirtualWindow(1000, 640, 320)

    expect(result.startIndex).toBe(12)
    expect(result.endIndex).toBe(38)
    expect(result.topSpacerHeight).toBe(12 * TRADITIONAL_VIRTUAL_ROW_HEIGHT)
    expect(result.bottomSpacerHeight).toBe(
      (1000 - 38) * TRADITIONAL_VIRTUAL_ROW_HEIGHT
    )
  })

  it('clamps the rendered window to the final row after a large scroll jump', () => {
    const result = calculateTraditionalVirtualWindow(100, 999999, 320)

    expect(result.startIndex).toBe(82)
    expect(result.endIndex).toBe(100)
    expect(result.bottomSpacerHeight).toBe(0)
  })
})
