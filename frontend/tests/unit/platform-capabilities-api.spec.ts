/**
 * 主机能力 API 客户端缓存与降级兜底测试（dual-mode-client Phase 4 批次 C）。
 */
import {
  cachedCapabilityLevel,
  FILESYSTEM_CAPABILITIES,
  isCapabilityAvailable,
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
  it('未加载时形态未知，文件系统能力闭锁', () => {
    expect(cachedCapabilityLevel('custom_scripts')).toBe('supported')
    expect(cachedPlatform()).toBe('unknown')
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
    expect(cachedPlatform()).toBe('unknown')
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

  it('信封 status 非 success 时缓存 null（调用方保持闭锁）', async() => {
    const request = jest.requireMock('@/utils/request').default as jest.Mock
    request.mockResolvedValueOnce({ status: 'error', msg: 'x', code: '500', data: null })
    expect(await loadPlatformCapabilities()).toBeNull()
    expect(cachedPlatform()).toBe('unknown')
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


describe('文件系统能力与远端矩阵', () => {
  it.each([...FILESYSTEM_CAPABILITIES])('未加载或旧矩阵缺少 %s 时闭锁', key => {
    expect(isCapabilityAvailable(key)).toBe(false)
    setPlatformCapabilityCacheForTesting(androidData())
    expect(cachedCapabilityLevel(key)).toBe('unknown')
    expect(isCapabilityAvailable(key)).toBe(false)
  })

  it('Android 浏览器访问远端 desktop 时采用服务端矩阵', async() => {
    const userAgent = jest.spyOn(window.navigator, 'userAgent', 'get')
      .mockReturnValue('Mozilla/5.0 (Linux; Android 15)')
    try {
      const remote: PlatformCapabilitiesData = {
        schemaVersion: 2,
        platform: 'desktop',
        capabilities: Object.fromEntries(FILESYSTEM_CAPABILITIES.map(key => [key, { label: key, level: 'supported' }])),
        degradedCount: 0,
        unsupportedCount: 0
      }
      request.mockResolvedValueOnce({ status: 'success', data: remote })
      await loadPlatformCapabilities()
      expect(cachedPlatform()).toBe('desktop')
      FILESYSTEM_CAPABILITIES.forEach(key => expect(isCapabilityAvailable(key)).toBe(true))
    } finally {
      userAgent.mockRestore()
    }
  })

  it('强制刷新失败后撤销旧矩阵的文件系统授权', async() => {
    setPlatformCapabilityCacheForTesting({
      platform: 'desktop', capabilities: { path_mapping: { label: 'path', level: 'supported' } },
      degradedCount: 0, unsupportedCount: 0
    })
    request.mockRejectedValueOnce(new Error('network'))
    expect(await loadPlatformCapabilities(true)).toBeNull()
    expect(cachedPlatform()).toBe('unknown')
    expect(isCapabilityAvailable('path_mapping')).toBe(false)
  })
})
