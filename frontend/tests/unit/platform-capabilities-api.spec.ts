/**
 * 主机能力 API 客户端缓存与降级兜底测试（dual-mode-client Phase 4 批次 C）。
 */
import {
  cachedCapabilityLevel,
  cachedPlatform,
  customScriptsUnsupported,
  loadPlatformCapabilities,
  PlatformCapabilitiesData,
  resetPlatformCapabilityCache,
  setPlatformCapabilityCacheForTesting
} from '@/api/platform-capabilities'

jest.mock('@/utils/request', () => ({
  __esModule: true,
  default: jest.fn()
}))

const request = jest.requireMock('@/utils/request').default as jest.Mock

const androidData = (): PlatformCapabilitiesData => ({
  platform: 'android-server',
  capabilities: {
    custom_scripts: { label: '自定义脚本', level: 'unsupported', note: 'x' },
    scheduled_tasks: { label: '定时任务', level: 'degraded', note: 'y' }
  },
  degradedCount: 1,
  unsupportedCount: 1
})

beforeEach(() => {
  resetPlatformCapabilityCache()
  // 对 request fn reset（清计数与实现，各用例自挂实现——避免跨用例累积）
  ;(request as jest.Mock).mockReset()
})

describe('缓存读取与兜底', () => {
  it('未加载时按 supported/desktop 兜底（与后端 fail-safe 同方向）', () => {
    expect(cachedCapabilityLevel('custom_scripts')).toBe('supported')
    expect(cachedPlatform()).toBe('desktop')
    expect(customScriptsUnsupported()).toBe(false)
  })

  it('注入 android-server 缓存后读取一致', () => {
    setPlatformCapabilityCacheForTesting(androidData())
    expect(cachedPlatform()).toBe('android-server')
    expect(cachedCapabilityLevel('custom_scripts')).toBe('unsupported')
    expect(cachedCapabilityLevel('scheduled_tasks')).toBe('degraded')
    expect(customScriptsUnsupported()).toBe(true)
  })

  it('reset 清空缓存', () => {
    setPlatformCapabilityCacheForTesting(androidData())
    resetPlatformCapabilityCache()
    expect(cachedPlatform()).toBe('desktop')
  })
})

describe('loadPlatformCapabilities 请求路径与缓存', () => {
  it('GET /platform/capabilities 并缓存信封 data', async() => {
    const request = jest.requireMock('@/utils/request').default as jest.Mock
    request.mockResolvedValueOnce({ status: 'success', msg: '', code: '200', data: androidData() })
    const data = await loadPlatformCapabilities()
    expect(request).toHaveBeenCalledWith(
      expect.objectContaining({ url: '/platform/capabilities', method: 'get' })
    )
    expect(data?.platform).toBe('android-server')
    // 第二次调用不再发请求（单例缓存）
    await loadPlatformCapabilities()
    expect(request).toHaveBeenCalledTimes(1)
  })

  it('信封 status 非 success 时缓存 null（调用方走全能力兜底）', async() => {
    const request = jest.requireMock('@/utils/request').default as jest.Mock
    request.mockResolvedValueOnce({ status: 'error', msg: 'x', code: '500', data: null })
    expect(await loadPlatformCapabilities()).toBeNull()
    expect(cachedPlatform()).toBe('desktop')
  })

  it('请求异常返回 null 不抛出', async() => {
    const request = jest.requireMock('@/utils/request').default as jest.Mock
    request.mockRejectedValueOnce(new Error('network'))
    expect(await loadPlatformCapabilities()).toBeNull()
  })

  it('force=true 绕过缓存重新请求', async() => {
    const request = jest.requireMock('@/utils/request').default as jest.Mock
    request.mockResolvedValue({ status: 'success', msg: '', code: '200', data: androidData() })
    await loadPlatformCapabilities()
    await loadPlatformCapabilities(true)
    expect(request).toHaveBeenCalledTimes(2)
  })
})
