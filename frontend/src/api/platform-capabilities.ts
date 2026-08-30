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

export interface PlatformCapabilityEntry {
  label: string
  level: CapabilityLevel
  /** 降级/不支持时的展示说明（服务端矩阵冻结文案） */
  note?: string
}

export interface PlatformCapabilitiesData {
  platform: 'desktop' | 'android-server'
  capabilities: Record<string, PlatformCapabilityEntry>
  degradedCount: number
  unsupportedCount: number
}

let cache: PlatformCapabilitiesData | null = null
let inflight: Promise<PlatformCapabilitiesData | null> | null = null

/** 读取主机能力矩阵（进程内单例缓存；force 强制刷新）。失败返回 null——调用方按全能力兜底，不阻断页面。 */
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

/** 同步读取已缓存的能力级别（未加载/加载失败返回 supported——与后端 fail-safe 方向一致）。 */
export function cachedCapabilityLevel(key: string): CapabilityLevel {
  return cache?.capabilities[key]?.level ?? 'supported'
}

/** 同步读取缓存形态（未加载返回 desktop）。 */
export function cachedPlatform(): 'desktop' | 'android-server' {
  return cache?.platform ?? 'desktop'
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
