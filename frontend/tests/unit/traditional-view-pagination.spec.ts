import {
  TRADITIONAL_PAGE_SIZE_MAX,
  TRADITIONAL_PAGE_SIZE_MIN,
  normalizeTraditionalPageSize
} from '@/views/torrents/utils/traditionalPagination'

describe('traditional view custom page size', () => {
  it('accepts the upper boundary of 100000', () => {
    expect(normalizeTraditionalPageSize('100000', 20)).toBe(100000)
  })

  it('clamps values outside the supported range', () => {
    expect(normalizeTraditionalPageSize(0, 20)).toBe(TRADITIONAL_PAGE_SIZE_MIN)
    expect(normalizeTraditionalPageSize(100001, 20)).toBe(TRADITIONAL_PAGE_SIZE_MAX)
  })

  it('uses an integer page size', () => {
    expect(normalizeTraditionalPageSize('123.9', 20)).toBe(123)
  })

  it('keeps the current value for blank or invalid input', () => {
    expect(normalizeTraditionalPageSize('', 50)).toBe(50)
    expect(normalizeTraditionalPageSize('not-a-number', 50)).toBe(50)
  })
})
