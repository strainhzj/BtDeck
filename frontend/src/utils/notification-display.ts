/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/**
 * 系统通知事件展示层（双语 P4 / E03）。
 *
 * 契约（PLANS/desktop-bilingual.md §3.3）：通知 title/content 是产生时的中文
 * 自由文本，不入库改写；已知事件按 extra_data.event + 参数在读取/展示时本地化，
 * 未知 event 或无 extra_data 的历史/自由文本通知原文展示（E03 旧内容不改写）。
 *
 * 已登记事件键（后端产生源同步维护）：
 * - torrent_batch_add_completed（torrent_batch_add_service）
 * - orphan_scan_completed（orphan_notification）
 * - version_update（notification_service 运行时检查 / 欢迎脚本种子）
 * - welcome（欢迎脚本种子）
 */

import { NotificationItem } from '@/api/notification'
import { translate } from '@/i18n'
import { formatFileSize } from './formatters'

/** 批量添加完成：title/content 由事件参数本地化 */
function batchAddDisplay(n: NotificationItem): { title: string, content: string } {
  const extra = n.extra_data || {}
  return {
    title: translate('common.notifications.events.batchAdd.title'),
    content: translate('common.notifications.events.batchAdd.content', {
      total: extra.total_count ?? 0,
      success: extra.success_count ?? 0,
      failed: extra.failed_count ?? 0
    })
  }
}

/** 孤儿扫描完成：数量/大小/护栏提示由事件参数本地化 */
function orphanScanDisplay(n: NotificationItem): { title: string, content: string } {
  const extra = n.extra_data || {}
  let content = translate('common.notifications.events.orphanScan.content', {
    count: extra.orphan_count ?? 0,
    size: formatFileSize(extra.orphan_size ?? 0)
  })
  if (extra.orphan_count_warning) {
    content += translate('common.notifications.events.orphanScan.warning')
  }
  return {
    title: translate('common.notifications.events.orphanScan.title'),
    content
  }
}

/** 版本更新：title 参数化本地化；content 为 GitHub Release 原文（不改写） */
function versionUpdateDisplay(n: NotificationItem): { title: string, content: string } {
  const extra = n.extra_data || {}
  return {
    title: translate('common.notifications.events.versionUpdate.title', {
      version: extra.version || ''
    }),
    content: n.content || ''
  }
}

/** 欢迎：title/content 本地化（历史欢迎通知无 event 键，原文展示） */
function welcomeDisplay(): { title: string, content: string } {
  return {
    title: translate('common.notifications.events.welcome.title'),
    content: translate('common.notifications.events.welcome.content')
  }
}

type EventRenderer = (n: NotificationItem) => { title: string, content: string }

/** 事件键 → 本地化渲染器（未登记事件不在表内，走原文兜底） */
const EVENT_RENDERERS: Record<string, EventRenderer> = {
  torrent_batch_add_completed: batchAddDisplay,
  orphan_scan_completed: orphanScanDisplay,
  version_update: versionUpdateDisplay,
  welcome: welcomeDisplay
}

function renderByEvent(n: NotificationItem): { title: string, content: string } | null {
  const event = n.extra_data?.event
  if (!event) return null
  const renderer = EVENT_RENDERERS[event]
  if (!renderer) return null
  return renderer(n)
}

/** 通知标题：已知事件本地化，其余原文（E03） */
export function notificationDisplayTitle(n: NotificationItem): string {
  const rendered = renderByEvent(n)
  return rendered ? rendered.title : n.title
}

/** 通知正文：已知事件按参数模板本地化，其余原文（E03；失败明细由 failed_list 区域单独渲染） */
export function notificationDisplayContent(n: NotificationItem): string {
  const rendered = renderByEvent(n)
  return rendered ? rendered.content : (n.content || '')
}
