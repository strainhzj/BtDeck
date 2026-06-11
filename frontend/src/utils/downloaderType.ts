/**
 * 下载器类型转换工具函数
 *
 * 用于处理后端返回的数字枚举与前端字符串之间的转换
 */

/**
 * 下载器类型枚举定义
 */
export const DOWNLOADER_TYPE = {
  QBITTORRENT: 0,
  TRANSMISSION: 1
} as const

/**
 * 下载器类型名称定义
 */
export const DOWNLOADER_TYPE_NAME = {
  QBITTORRENT: 'qbittorrent',
  TRANSMISSION: 'transmission'
} as const

/**
 * 将下载器类型数字转换为字符串名称
 *
 * @param type - 下载器类型数字（0=qbittorrent, 1=transmission）
 * @returns 下载器类型字符串
 *
 * @example
 * downloaderTypeToString(0) // 'qbittorrent'
 * downloaderTypeToString(1) // 'transmission'
 */
export function downloaderTypeToString(type: number | undefined): 'qbittorrent' | 'transmission' {
  if (type === DOWNLOADER_TYPE.QBITTORRENT) {
    return DOWNLOADER_TYPE_NAME.QBITTORRENT
  }
  // 默认返回 transmission（包括 type=1 或 undefined）
  return DOWNLOADER_TYPE_NAME.TRANSMISSION
}

/**
 * 将下载器类型名称转换为数字
 *
 * @param name - 下载器类型字符串
 * @returns 下载器类型数字
 *
 * @example
 * downloaderStringToType('qbittorrent') // 0
 * downloaderStringToType('transmission') // 1
 */
export function downloaderStringToType(name: string | undefined): number {
  if (name === DOWNLOADER_TYPE_NAME.QBITTORRENT) {
    return DOWNLOADER_TYPE.QBITTORRENT
  }
  return DOWNLOADER_TYPE.TRANSMISSION
}

/**
 * 获取下载器类型显示标签
 *
 * @param name - 下载器类型字符串
 * @returns 显示标签
 *
 * @example
 * getDownloaderTypeLabel('qbittorrent') // 'qBittorrent'
 * getDownloaderTypeLabel('transmission') // 'Transmission'
 */
export function getDownloaderTypeLabel(name: string | undefined): string {
  if (name === DOWNLOADER_TYPE_NAME.QBITTORRENT) {
    return 'qBittorrent'
  }
  return 'Transmission'
}
