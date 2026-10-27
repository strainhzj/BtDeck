/**
 * 下载器类型转换工具函数
 *
 * 用于处理后端返回的数字枚举与前端字符串之间的转换
 *
 * rTorrent 接入前置修复（P0-C）：旧实现对非 0 值一律回退 Transmission（或
 * qBittorrent），类型 2（rTorrent）会被静默误判。现改为显式三路映射，
 * 未知值返回 'unknown' 并告警，不再借用其他类型的语义。
 */

/**
 * 下载器类型枚举定义
 */
export const DOWNLOADER_TYPE = {
  QBITTORRENT: 0,
  TRANSMISSION: 1,
  RTORRENT: 2
} as const

/**
 * 下载器类型名称定义
 */
export const DOWNLOADER_TYPE_NAME = {
  QBITTORRENT: 'qbittorrent',
  TRANSMISSION: 'transmission',
  RTORRENT: 'rtorrent'
} as const

/** 下载器类型名称联合类型（与后端 DownloaderTypeEnum.to_name 对齐） */
export type DownloaderTypeName =
  | typeof DOWNLOADER_TYPE_NAME.QBITTORRENT
  | typeof DOWNLOADER_TYPE_NAME.TRANSMISSION
  | typeof DOWNLOADER_TYPE_NAME.RTORRENT

/** 下载器类型数字联合类型 */
export type DownloaderTypeValue =
  | typeof DOWNLOADER_TYPE.QBITTORRENT
  | typeof DOWNLOADER_TYPE.TRANSMISSION
  | typeof DOWNLOADER_TYPE.RTORRENT

/**
 * 将下载器类型数字转换为字符串名称
 *
 * @param type - 下载器类型数字（0=qbittorrent, 1=transmission, 2=rtorrent）
 * @returns 下载器类型字符串；未知值返回 'unknown'（不再回退已知类型）
 *
 * @example
 * downloaderTypeToString(0) // 'qbittorrent'
 * downloaderTypeToString(1) // 'transmission'
 * downloaderTypeToString(2) // 'rtorrent'
 * downloaderTypeToString(3) // 'unknown'（console.warn）
 */
export function downloaderTypeToString(type: number | undefined): DownloaderTypeName | 'unknown' {
  if (type === DOWNLOADER_TYPE.QBITTORRENT) {
    return DOWNLOADER_TYPE_NAME.QBITTORRENT
  }
  if (type === DOWNLOADER_TYPE.TRANSMISSION) {
    return DOWNLOADER_TYPE_NAME.TRANSMISSION
  }
  if (type === DOWNLOADER_TYPE.RTORRENT) {
    return DOWNLOADER_TYPE_NAME.RTORRENT
  }
  console.warn(`[downloaderType] 未知下载器类型数字: ${type}，返回 'unknown'`)
  return 'unknown'
}

/**
 * 将下载器类型名称转换为数字
 *
 * @param name - 下载器类型字符串
 * @returns 下载器类型数字；未知值返回 -1（不再默认 Transmission）
 *
 * @example
 * downloaderStringToType('qbittorrent') // 0
 * downloaderStringToType('transmission') // 1
 * downloaderStringToType('rtorrent') // 2
 * downloaderStringToType('bogus') // -1
 */
export function downloaderStringToType(name: string | undefined): number {
  if (name === DOWNLOADER_TYPE_NAME.QBITTORRENT) {
    return DOWNLOADER_TYPE.QBITTORRENT
  }
  if (name === DOWNLOADER_TYPE_NAME.TRANSMISSION) {
    return DOWNLOADER_TYPE.TRANSMISSION
  }
  if (name === DOWNLOADER_TYPE_NAME.RTORRENT) {
    return DOWNLOADER_TYPE.RTORRENT
  }
  console.warn(`[downloaderType] 未知下载器类型名称: ${name}，返回 -1`)
  return -1
}

/**
 * 获取下载器类型显示标签
 *
 * @param name - 下载器类型字符串
 * @returns 显示标签；未知值返回 'Unknown'
 *
 * @example
 * getDownloaderTypeLabel('qbittorrent') // 'qBittorrent'
 * getDownloaderTypeLabel('transmission') // 'Transmission'
 * getDownloaderTypeLabel('rtorrent') // 'rTorrent'
 */
export function getDownloaderTypeLabel(name: string | undefined): string {
  if (name === DOWNLOADER_TYPE_NAME.QBITTORRENT) {
    return 'qBittorrent'
  }
  if (name === DOWNLOADER_TYPE_NAME.TRANSMISSION) {
    return 'Transmission'
  }
  if (name === DOWNLOADER_TYPE_NAME.RTORRENT) {
    return 'rTorrent'
  }
  console.warn(`[downloaderType] 未知下载器类型名称: ${name}，返回 'Unknown'`)
  return 'Unknown'
}
