import request from '@/utils/request'
import type { ApiEnvelope } from '@/utils/request'

/**
 * 主机能力矩阵 API（dual-mode-client Phase 4）。
 *
 * 单一真相源：设置页/任务列表/创建表单三处消费同一缓存（一致降级，
 * 见 docs/android/host-capability-matrix.md 第 3 节设计冻结）。
 * 不以 UA 猜测形态——platform 由服务端按 BTDECK_PLATFORM 环境判定。
 */

export type CapabilityLevel = 'supported' | 'degraded' | 'unsupported'
export type CachedCapabilityLevel = CapabilityLevel | 'unknown'

export interface PlatformCapabilityEntry {
  label: string
  level: CapabilityLevel
  /** 降级/不支持时的展示说明（服务端矩阵冻结文案） */
  note?: string
}

export interface PlatformCapabilitiesData {
  schemaVersion?: number
  platform: 'desktop' | 'android-server'
  capabilities: Record<string, PlatformCapabilityEntry>
  degradedCount: number
  unsupportedCount: number
}

let cache: PlatformCapabilitiesData | null = null
let inflight: Promise<PlatformCapabilitiesData | null> | null = null

/** 读取主机能力矩阵（进程内单例缓存；force 强制刷新）。失败保留 unknown，受限入口必须闭锁。 */
export function loadPlatformCapabilities(force = false): Promise<PlatformCapabilitiesData | null> {
  if (cache && !force) return Promise.resolve(cache)
  if (inflight && !force) return inflight
  inflight = request<ApiEnvelope<PlatformCapabilitiesData>>({
    url: '/platform/capabilities',
    method: 'get'
  })
    .then(res => {
      // 拦截器已解包为信封本体；status!==success 时按失败兜底
      cache = res?.status === 'success' ? res.data : null
      return cache
    })
    .catch(() => null)
    .finally(() => {
      inflight = null
    })
  return inflight
}

/** 需要真实下载器主机文件系统的能力，取不到矩阵时必须 fail-closed。 */
export const FILESYSTEM_CAPABILITIES = [
  'downloader_filesystem_access',
  'path_mapping',
  'orphan_files',
  'torrent_backup',
  'seed_transfer',
  'level3_recycle'
] as const

/** 同步读取已缓存的能力级别；受限能力在未加载/失败时返回 unknown。 */
export function cachedCapabilityLevel(key: string): CachedCapabilityLevel {
  const level = cache?.capabilities[key]?.level
  if (level) return level
  return (FILESYSTEM_CAPABILITIES as readonly string[]).includes(key) ? 'unknown' : 'supported'
}

/** 同步读取缓存形态（未加载/失败返回 unknown，避免误把 Android 当桌面）。 */
export function cachedPlatform(): 'desktop' | 'android-server' | 'unknown' {
  return cache?.platform ?? 'unknown'
}

/** 能力只有明确 supported 才允许进入需要文件系统的功能。 */
export function isCapabilityAvailable(key: string): boolean {
  return cachedCapabilityLevel(key) === 'supported'
}

export function isCapabilityUnknown(key: string): boolean {
  return cachedCapabilityLevel(key) === 'unknown'
}

/** 自定义脚本任务类型（0=shell/1=cmd/2=powershell/3=python 文件）是否被当前主机形态禁用。 */
export function customScriptsUnsupported(): boolean {
  return cachedCapabilityLevel('custom_scripts') === 'unsupported'
}

/** 测试用途：清空缓存。 */
export function resetPlatformCapabilityCache(): void {
  cache = null
  inflight = null
}

/** 测试用途：注入缓存（组件行为测试不经网络设定形态）。 */
export function setPlatformCapabilityCacheForTesting(data: PlatformCapabilitiesData | null): void {
  cache = data
}
