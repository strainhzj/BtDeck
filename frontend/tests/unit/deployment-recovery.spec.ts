import { readFileSync } from 'fs'
import { resolve } from 'path'

import {
  CHUNK_RECOVERY_QUERY,
  CHUNK_RECOVERY_STORAGE_KEY,
  CHUNK_RECOVERY_WINDOW_MS,
  ChunkRecoveryEnvironment,
  clearChunkRecoveryQuery,
  isChunkLoadError,
  recoverFromChunkLoadError,
  retireLegacyServiceWorkers
} from '@/utils/deployment-recovery'

function recoveryEnvironment(overrides: Partial<ChunkRecoveryEnvironment> = {}): {
  environment: ChunkRecoveryEnvironment
  replace: jest.Mock<void, [string]>
  values: Map<string, string>
} {
  const values = new Map<string, string>()
  const replace = jest.fn<void, [string]>()
  const environment: ChunkRecoveryEnvironment = {
    href: 'http://btdeck.test/#/orphan-files/index',
    now: () => 100_000,
    replace,
    storage: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value)
    },
    ...overrides
  }
  return { environment, replace, values }
}

describe('deployment recovery', () => {
  it.each([
    new Error('Loading CSS chunk 4687 failed.'),
    Object.assign(new Error('Loading chunk 4687 failed.'), { name: 'ChunkLoadError' }),
    'Failed to fetch dynamically imported module',
    { name: 'TypeError', message: 'Importing a module script failed' }
  ])('recognizes webpack lazy chunk failures', error => {
    expect(isChunkLoadError(error)).toBe(true)
  })

  it('ignores unrelated router failures', () => {
    const { environment, replace } = recoveryEnvironment()

    expect(recoverFromChunkLoadError(new Error('permission denied'), environment)).toBe('ignored')
    expect(replace).not.toHaveBeenCalled()
  })

  it('reloads through the current route with a cache-busting marker', () => {
    const { environment, replace, values } = recoveryEnvironment()

    expect(recoverFromChunkLoadError(new Error('Loading chunk 4687 failed.'), environment))
      .toBe('reloading')
    expect(values.get(CHUNK_RECOVERY_STORAGE_KEY)).toBe('100000')
    expect(replace).toHaveBeenCalledTimes(1)

    const target = new URL(replace.mock.calls[0][0])
    expect(target.hash).toBe('#/orphan-files/index')
    expect(target.searchParams.get(CHUNK_RECOVERY_QUERY)).toBe('100000')
  })

  it('suppresses a repeated failure inside the recovery window', () => {
    const { environment, replace, values } = recoveryEnvironment()
    values.set(CHUNK_RECOVERY_STORAGE_KEY, String(100_000 - CHUNK_RECOVERY_WINDOW_MS + 1))

    expect(recoverFromChunkLoadError(new Error('Loading CSS chunk 4687 failed.'), environment))
      .toBe('suppressed')
    expect(replace).not.toHaveBeenCalled()
  })

  it('uses the URL marker when session storage is unavailable', () => {
    const href = `http://btdeck.test/?${CHUNK_RECOVERY_QUERY}=99999#/orphan-files/index`
    const { environment, replace } = recoveryEnvironment({ href, storage: null })

    expect(recoverFromChunkLoadError(new Error('ChunkLoadError'), environment)).toBe('suppressed')
    expect(replace).not.toHaveBeenCalled()
  })

  it('clears only the recovery query after a successful initial route load', () => {
    const replaceState = jest.fn<void, [string]>()

    expect(clearChunkRecoveryQuery({
      href: `http://btdeck.test/?redirect=%2Flogin&${CHUNK_RECOVERY_QUERY}=100000#/orphan-files/index`,
      replaceState
    })).toBe(true)
    expect(replaceState).toHaveBeenCalledWith('/?redirect=%2Flogin#/orphan-files/index')
  })

  it('retires only the BtDeck root worker and BtDeck Workbox caches', async() => {
    const rootUnregister = jest.fn<Promise<boolean>, []>().mockResolvedValue(true)
    const otherUnregister = jest.fn<Promise<boolean>, []>().mockResolvedValue(true)
    const deleteCache = jest.fn<Promise<boolean>, [string]>().mockResolvedValue(true)

    const result = await retireLegacyServiceWorkers({
      appScope: 'http://btdeck.test/',
      deleteCache,
      getCacheNames: async() => [
        'vue-typescript-admin-template-precache-v2-http://btdeck.test/',
        'another-app-cache'
      ],
      getRegistrations: async() => [
        { scope: 'http://btdeck.test/', unregister: rootUnregister },
        { scope: 'http://btdeck.test/other/', unregister: otherUnregister }
      ]
    })

    expect(result).toEqual({ cachesDeleted: 1, registrationsRemoved: 1 })
    expect(rootUnregister).toHaveBeenCalledTimes(1)
    expect(otherUnregister).not.toHaveBeenCalled()
    expect(deleteCache).toHaveBeenCalledWith(
      'vue-typescript-admin-template-precache-v2-http://btdeck.test/'
    )
  })

  it('caches only fingerprinted assets immutably in Nginx', () => {
    const nginx = readFileSync(resolve(__dirname, '../../nginx.conf'), 'utf8')
    const serviceWorkerLocation = nginx.indexOf('location = /service-worker.js')
    const assetsLocation = nginx.indexOf('location /assets/')

    expect(serviceWorkerLocation).toBeGreaterThan(-1)
    expect(assetsLocation).toBeGreaterThan(serviceWorkerLocation)
    expect(nginx.slice(serviceWorkerLocation, assetsLocation)).toContain(
      'Cache-Control "no-cache, no-store, must-revalidate"'
    )
    expect(nginx.slice(assetsLocation, nginx.indexOf('# API', assetsLocation))).toContain(
      'Cache-Control "public, immutable"'
    )
    expect(nginx).not.toContain('location ~* \\.(js|css|png')
  })
})
