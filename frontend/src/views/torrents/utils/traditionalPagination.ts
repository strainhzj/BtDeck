export const TRADITIONAL_PAGE_SIZE_MIN = 1
export const TRADITIONAL_PAGE_SIZE_MAX = 100000

export function normalizeTraditionalPageSize(value: unknown, fallback: number): number {
  if (value === null || value === undefined || String(value).trim() === '') {
    return fallback
  }

  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return fallback
  }

  return Math.min(
    TRADITIONAL_PAGE_SIZE_MAX,
    Math.max(TRADITIONAL_PAGE_SIZE_MIN, Math.trunc(parsed))
  )
}
