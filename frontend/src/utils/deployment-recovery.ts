const CHUNK_LOAD_ERROR_PATTERNS = [
  /ChunkLoadError/i,
  /Loading (?:CSS )?chunk \d+ failed/i,
  /Failed to fetch dynamically imported module/i,
  /Importing a module script failed/i
]

export const CHUNK_RECOVERY_QUERY = '__btdeck_chunk_retry'
export const CHUNK_RECOVERY_STORAGE_KEY = 'btdeck:chunk-load-retry-at'
export const CHUNK_RECOVERY_WINDOW_MS = 60_000

const LEGACY_WORKBOX_CACHE_PREFIX = 'vue-typescript-admin-template-'

export type ChunkRecoveryOutcome = 'ignored' | 'reloading' | 'suppressed'

export interface ChunkRecoveryEnvironment {
  href: string
  now: () => number
  replace: (url: string) => void
  storage: Pick<Storage, 'getItem' | 'setItem'> | null
}

export interface ChunkRecoveryHistoryEnvironment {
  href: string
  replaceState: (url: string) => void
}

export interface RetirableServiceWorkerRegistration {
  readonly scope: string
  unregister: () => Promise<boolean>
}

export interface LegacyServiceWorkerEnvironment {
  appScope: string
  deleteCache: (name: string) => Promise<boolean>
  getCacheNames: () => Promise<string[]>
  getRegistrations: () => Promise<readonly RetirableServiceWorkerRegistration[]>
}

export interface LegacyServiceWorkerRetirement {
  cachesDeleted: number
  registrationsRemoved: number
}

function errorText(error: unknown): string {
  if (error instanceof Error) {
    return `${error.name}: ${error.message}`
  }
  if (typeof error === 'string') {
    return error
  }
  if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>
    const name = typeof record.name === 'string' ? record.name : ''
    const message = typeof record.message === 'string' ? record.message : ''
    return `${name}: ${message}`
  }
  return String(error)
}

function parseTimestamp(value: string | null): number | null {
  if (!value) return null
  const timestamp = Number(value)
  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : null
}

function browserChunkRecoveryEnvironment(): ChunkRecoveryEnvironment {
  return {
    href: window.location.href,
    now: Date.now,
    replace: (url: string) => window.location.replace(url),
    storage: window.sessionStorage
  }
}

function browserChunkRecoveryHistoryEnvironment(): ChunkRecoveryHistoryEnvironment {
  return {
    href: window.location.href,
    replaceState: (url: string) => {
      window.history.replaceState(window.history.state, document.title, url)
    }
  }
}

function browserLegacyServiceWorkerEnvironment(): LegacyServiceWorkerEnvironment | null {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return null
  if (!navigator.serviceWorker || !window.caches) return null

  const appScope = new URL(process.env.BASE_URL || '/', window.location.origin).href
  return {
    appScope,
    deleteCache: (name: string) => window.caches.delete(name),
    getCacheNames: () => window.caches.keys(),
    getRegistrations: () => navigator.serviceWorker.getRegistrations()
  }
}

export function isChunkLoadError(error: unknown): boolean {
  const text = errorText(error)
  return CHUNK_LOAD_ERROR_PATTERNS.some(pattern => pattern.test(text))
}

/**
 * A running SPA can outlive a deployment. Its old webpack runtime then asks the
 * new container for chunks that no longer exist. Reload once with a unique
 * query so the browser obtains the current no-cache index instead of looping on
 * the stale runtime.
 */
export function recoverFromChunkLoadError(
  error: unknown,
  environment: ChunkRecoveryEnvironment = browserChunkRecoveryEnvironment()
): ChunkRecoveryOutcome {
  if (!isChunkLoadError(error)) return 'ignored'

  const now = environment.now()
  const recoveryUrl = new URL(environment.href)
  const queryAttempt = parseTimestamp(recoveryUrl.searchParams.get(CHUNK_RECOVERY_QUERY))
  let storageAttempt: number | null = null

  try {
    storageAttempt = environment.storage
      ? parseTimestamp(environment.storage.getItem(CHUNK_RECOVERY_STORAGE_KEY))
      : null
  } catch (_error) {
    // The query marker still prevents a reload loop when storage is unavailable.
  }

  const attempts = [queryAttempt, storageAttempt].filter(
    (attempt): attempt is number => attempt !== null
  )
  const lastAttempt = attempts.length > 0 ? Math.max(...attempts) : null
  if (lastAttempt !== null && now - lastAttempt < CHUNK_RECOVERY_WINDOW_MS) {
    return 'suppressed'
  }

  try {
    environment.storage?.setItem(CHUNK_RECOVERY_STORAGE_KEY, String(now))
  } catch (_error) {
    // Navigation recovery must still work when storage is blocked.
  }

  recoveryUrl.searchParams.set(CHUNK_RECOVERY_QUERY, String(now))
  environment.replace(recoveryUrl.href)
  return 'reloading'
}

/** Remove the visible retry marker only after Vue Router finished loading. */
export function clearChunkRecoveryQuery(
  environment: ChunkRecoveryHistoryEnvironment = browserChunkRecoveryHistoryEnvironment()
): boolean {
  const currentUrl = new URL(environment.href)
  if (!currentUrl.searchParams.has(CHUNK_RECOVERY_QUERY)) return false

  currentUrl.searchParams.delete(CHUNK_RECOVERY_QUERY)
  environment.replaceState(`${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`)
  return true
}

/**
 * PWA registration is not enabled by main.ts, but older BtDeck builds may have
 * left a controlling Workbox worker and its precache behind. Retire only this
 * app's root-scoped registration and BtDeck-prefixed caches.
 */
export async function retireLegacyServiceWorkers(
  environment: LegacyServiceWorkerEnvironment | null = browserLegacyServiceWorkerEnvironment()
): Promise<LegacyServiceWorkerRetirement> {
  if (!environment) {
    return { cachesDeleted: 0, registrationsRemoved: 0 }
  }

  try {
    const registrations = await environment.getRegistrations()
    const appRegistrations = registrations.filter(
      registration => registration.scope === environment.appScope
    )
    const registrationResults = await Promise.all(
      appRegistrations.map(registration => registration.unregister())
    )

    const cacheNames = await environment.getCacheNames()
    const appCacheNames = cacheNames.filter(name => name.startsWith(LEGACY_WORKBOX_CACHE_PREFIX))
    const cacheResults = await Promise.all(
      appCacheNames.map(name => environment.deleteCache(name))
    )

    return {
      cachesDeleted: cacheResults.filter(Boolean).length,
      registrationsRemoved: registrationResults.filter(Boolean).length
    }
  } catch (_error) {
    // Recovery is best-effort and must never block normal application startup.
    return { cachesDeleted: 0, registrationsRemoved: 0 }
  }
}
