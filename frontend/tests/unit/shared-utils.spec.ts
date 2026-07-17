import {
  debounce,
  extractErrorMessage,
  formatDate,
  formatDuration,
  formatFileSize,
  formatNumber,
  formatPercent,
  formatRatio,
  formatRelativeTime,
  formatSpeed,
  getDownloaderId,
  getFileExtension,
  getTorrentId,
  normalizeObjectResponse,
  normalizePaginatedResponse,
  normalizeTorrent,
  normalizeTorrentStatus,
  showErrorToast,
  throttle,
  truncateText
} from '@/utils/formatters'
import {
  downloaderStringToType,
  downloaderTypeToString,
  getDownloaderTypeLabel
} from '@/utils/downloaderType'
import {
  getStatusIcon,
  getStatusText,
  isValidStatus
} from '@/constants/status-config'
import { isExternal, isValidUsername } from '@/utils/validate'
import {
  DEFAULT_THEME,
  getAllThemes,
  getCurrentTheme,
  getThemeConfig,
  initTheme,
  onThemeChange,
  setTheme,
  ThemeType,
  toggleTheme
} from '@/utils/theme'
import { TorrentStatus } from '@/types/torrent'

describe('共享格式化与规范化工具', () => {
  let warnSpy: jest.SpyInstance

  beforeEach(() => {
    warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    warnSpy.mockRestore()
    jest.useRealTimers()
  })

  it('将空种子转换为稳定的默认结构', () => {
    expect(normalizeTorrent(null)).toMatchObject({
      hash: '',
      infoId: '',
      downloaderId: '',
      name: '-',
      status: 'unknown',
      progress: 0,
      downloadSpeed: 0,
      uploadSpeed: 0
    })
  })

  it('统一蛇形字段并防止原始 null 覆盖规范化默认值', () => {
    const normalized = normalizeTorrent({
      hash: 'hash-1',
      info_id: 'info-1',
      downloader_id: 'downloader-1',
      downloader_name: '主下载器',
      save_path: '/downloads',
      added_date: '2026-07-16',
      status: 'DOWNLOADING',
      progress: null,
      downloadSpeed: null,
      uploadSpeed: null,
      customField: 'preserved'
    })

    expect(normalized).toMatchObject({
      hash: 'hash-1',
      infoId: 'info-1',
      info_id: 'info-1',
      downloaderId: 'downloader-1',
      downloaderName: '主下载器',
      savePath: '/downloads',
      addedDate: '2026-07-16',
      status: TorrentStatus.DOWNLOADING,
      progress: 0,
      downloadSpeed: 0,
      uploadSpeed: 0,
      customField: 'preserved'
    })
  })

  it.each([
    ['DOWNLOADING', undefined, TorrentStatus.DOWNLOADING],
    [TorrentStatus.COMPLETED, undefined, TorrentStatus.COMPLETED],
    [TorrentStatus.QUEUEDDL, undefined, TorrentStatus.QUEUEDDL],
    [null, TorrentStatus.SEEDING, TorrentStatus.SEEDING],
    ['unsupported', undefined, 'unknown'],
    [undefined, undefined, 'unknown']
  ])('规范化种子状态 %s / %s', (status, state, expected) => {
    expect(normalizeTorrentStatus(status, state)).toBe(expected)
  })

  it('解析标准分页、数组与兼容 data 包装', () => {
    expect(normalizePaginatedResponse<number>({ data: { list: [1, 2], total: 8 } }))
      .toEqual({ list: [1, 2], total: 8 })
    expect(normalizePaginatedResponse<number>({ data: [3, 4] }))
      .toEqual({ list: [3, 4], total: 2 })
    expect(normalizePaginatedResponse<number>({ data: { data: [5], total: 0 } }))
      .toEqual({ list: [5], total: 1 })
  })

  it('未知分页格式返回安全空值并记录告警', () => {
    expect(normalizePaginatedResponse(null)).toEqual({ list: [], total: 0 })
    expect(normalizePaginatedResponse({ data: { rows: [] } })).toEqual({ list: [], total: 0 })
    expect(warnSpy).toHaveBeenCalledTimes(2)
  })

  it('规范化对象响应并安全提取标识', () => {
    expect(normalizeObjectResponse<{ id: number }>({ data: { id: 7 } })).toEqual({ id: 7 })
    expect(normalizeObjectResponse(null)).toBeNull()
    expect(getTorrentId({ info_id: 'info-1', hash: 'hash-1' })).toBe('info-1')
    expect(getTorrentId({ hash: 'hash-1' })).toBe('hash-1')
    expect(getTorrentId(null)).toBe('')
    expect(getDownloaderId({ downloader_id: 'dl-1' })).toBe('dl-1')
    expect(getDownloaderId(null)).toBe('')
  })

  it.each([
    [undefined, '-'],
    [0, '-'],
    [512, '512.00 B'],
    [1024, '1.00 KB'],
    [1024 * 1024, '1.00 MB']
  ])('格式化文件大小 %s', (value, expected) => {
    expect(formatFileSize(value)).toBe(expected)
  })

  it('格式化速度、比率、时长、百分比与数字', () => {
    expect(formatSpeed(2048)).toBe('2.00 KB/s')
    expect(formatSpeed(0)).toBe('')
    expect(formatRatio('2.345', 2)).toBe('2.35')
    expect(formatRatio('invalid')).toBe('-')
    expect(formatDuration(90061)).toBe('1d 1h 1m 1s')
    expect(formatDuration(0)).toBe('-')
    expect(formatPercent(0.756, 1)).toBe('75.6%')
    expect(formatPercent(undefined)).toBe('0%')
    expect(formatNumber(1234567)).toBe('1,234,567')
  })

  it('格式化日期的完整、日期和时间形式', () => {
    const timestamp = new Date(2026, 6, 16, 9, 8, 7).getTime()
    expect(formatDate(timestamp)).toBe('2026-07-16 09:08:07')
    expect(formatDate(timestamp, 'date')).toBe('2026-07-16')
    expect(formatDate(timestamp, 'time')).toBe('09:08')
    expect(formatDate('invalid')).toBe('-')
  })

  it('正确格式化同步接口返回的本地 ISO 日期字符串', () => {
    expect(formatDate('2026-07-17T10:20:30')).toBe('2026-07-17 10:20:30')
  })

  it.each([
    ['UTC Z 格式', '2026-07-17T02:20:30.123Z'],
    ['显式时区偏移格式', '2026-07-17T10:20:30.123+08:00']
  ])('正确格式化包含小数秒的%s ISO 日期字符串', (_label, isoTimestamp) => {
    const equivalentTimestamp = Date.UTC(2026, 6, 17, 2, 20, 30, 123)
    expect(formatDate(isoTimestamp)).toBe(formatDate(equivalentTimestamp))
  })

  it('保持秒级数值时间戳字符串兼容性', () => {
    const timestamp = new Date(2026, 6, 17, 10, 20, 30).getTime()
    expect(formatDate(String(timestamp / 1000))).toBe('2026-07-17 10:20:30')
  })

  it('保持毫秒级数值时间戳字符串兼容性', () => {
    const timestamp = new Date(2026, 6, 17, 10, 20, 30).getTime()
    expect(formatDate(String(timestamp))).toBe('2026-07-17 10:20:30')
  })

  it('截断文本并提取扩展名', () => {
    expect(truncateText('abcdef', 3)).toBe('abc...')
    expect(truncateText('abc', 3)).toBe('abc')
    expect(truncateText(null)).toBe('-')
    expect(getFileExtension('archive.tar.gz')).toBe('.gz')
    expect(getFileExtension('README')).toBe('')
  })

  it('根据时间差生成稳定的相对时间', () => {
    jest.useFakeTimers('modern')
    const now = new Date(2026, 6, 16, 12, 0, 0)
    jest.setSystemTime(now)

    expect(formatRelativeTime(now.getTime() - 30 * 1000)).toBe('刚刚')
    expect(formatRelativeTime(now.getTime() - 5 * 60 * 1000)).toBe('5分钟前')
    expect(formatRelativeTime(now.getTime() - 2 * 60 * 60 * 1000)).toBe('2小时前')
    expect(formatRelativeTime(now.getTime() - 8 * 24 * 60 * 60 * 1000)).toBe('1周前')
  })

  it.each([
    [{ response: { data: { msg: '后端错误' }, status: 400 } }, '后端错误'],
    [{ response: { data: {}, status: 404 } }, '请求的资源不存在'],
    [{ request: {} }, '网络连接失败，请检查网络设置'],
    [new Error('本地错误'), '本地错误'],
    [null, '未知错误']
  ])('提取错误消息', (error, expected) => {
    expect(extractErrorMessage(error)).toBe(expected)
  })

  it('组合操作上下文错误提示', () => {
    expect(showErrorToast(new Error('连接失败'), '默认值', '刷新'))
      .toBe('刷新失败：连接失败')
  })

  it('防抖只执行最后一次调用', () => {
    jest.useFakeTimers('modern')
    const callback = jest.fn<void, [string]>()
    const debounced = debounce(callback, 100)

    debounced('first')
    debounced('last')
    jest.advanceTimersByTime(99)
    expect(callback).not.toHaveBeenCalled()
    jest.advanceTimersByTime(1)
    expect(callback).toHaveBeenCalledTimes(1)
    expect(callback).toHaveBeenCalledWith('last')
  })

  it('节流立即执行首个调用并在窗口尾执行最后一个调用', () => {
    jest.useFakeTimers('modern')
    jest.setSystemTime(new Date('2026-07-16T00:00:00Z'))
    const callback = jest.fn<void, [string]>()
    const throttled = throttle(callback, 100)

    throttled('first')
    throttled('last')
    expect(callback).toHaveBeenCalledWith('first')
    jest.advanceTimersByTime(100)
    expect(callback).toHaveBeenLastCalledWith('last')
    expect(callback).toHaveBeenCalledTimes(2)
  })
})

describe('状态、下载器与校验工具', () => {
  it('转换下载器类型并提供显示名称', () => {
    expect(downloaderTypeToString(0)).toBe('qbittorrent')
    expect(downloaderTypeToString(1)).toBe('transmission')
    expect(downloaderStringToType('qbittorrent')).toBe(0)
    expect(downloaderStringToType(undefined)).toBe(1)
    expect(getDownloaderTypeLabel('qbittorrent')).toBe('qBittorrent')
    expect(getDownloaderTypeLabel('transmission')).toBe('Transmission')
  })

  it('查询状态文本、图标和有效性', () => {
    expect(getStatusText('downloading')).toBe('下载中')
    expect(getStatusText('custom')).toBe('custom')
    expect(getStatusIcon('error')).toBe('⚠️')
    expect(getStatusIcon('custom')).toBe('❓')
    expect(isValidStatus('seeding')).toBe(true)
    expect(isValidStatus('custom')).toBe(false)
  })

  it('校验用户名与外部链接', () => {
    expect(isValidUsername(' admin ')).toBe(true)
    expect(isValidUsername('guest')).toBe(false)
    expect(isExternal('https://example.com')).toBe(true)
    expect(isExternal('mailto:test@example.com')).toBe(true)
    expect(isExternal('/dashboard')).toBe(false)
  })
})

describe('主题工具', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('按存储、DOM 属性和默认值的优先级读取主题', () => {
    expect(getCurrentTheme()).toBe(DEFAULT_THEME)
    document.documentElement.setAttribute('data-theme', 'orange')
    expect(getCurrentTheme()).toBe('orange')
    localStorage.setItem('btdeck-theme', 'graphite')
    expect(getCurrentTheme()).toBe('graphite')
  })

  it('设置主题时同步 DOM、存储并广播事件', () => {
    const listener = jest.fn<void, [Event]>()
    window.addEventListener('theme-change', listener)

    setTheme('orange')

    expect(document.documentElement.getAttribute('data-theme')).toBe('orange')
    expect(localStorage.getItem('btdeck-theme')).toBe('orange')
    expect(listener).toHaveBeenCalledTimes(1)
    window.removeEventListener('theme-change', listener)
  })

  it('无效主题降级为默认主题', () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
    setTheme('invalid' as ThemeType)
    expect(getCurrentTheme()).toBe(DEFAULT_THEME)
    expect(warnSpy).toHaveBeenCalled()
  })

  it('循环切换主题并可初始化当前主题', () => {
    localStorage.setItem('btdeck-theme', 'graphite')
    expect(toggleTheme()).toBe('emerald')
    localStorage.setItem('btdeck-theme', 'orange')
    initTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBe('orange')
  })

  it('订阅主题事件并支持解除订阅', () => {
    const callback = jest.fn<void, [ThemeType]>()
    const unsubscribe = onThemeChange(callback)

    setTheme('graphite')
    expect(callback).toHaveBeenCalledWith('graphite')
    unsubscribe()
    setTheme('orange')
    expect(callback).toHaveBeenCalledTimes(1)
  })

  it('返回防御性主题列表和指定配置', () => {
    const themes = getAllThemes()
    expect(themes).toHaveLength(3)
    expect(getThemeConfig('emerald')).toMatchObject({ name: '翡翠绿' })
    themes.pop()
    expect(getAllThemes()).toHaveLength(3)
  })
})
