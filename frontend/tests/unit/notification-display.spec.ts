/**
 * 双语 P4 / E03：系统通知事件展示层（utils/notification-display）契约。
 *
 * 锁定不变量（PLANS/desktop-bilingual.md §3.3）：
 * - 已知事件（torrent_batch_add_completed / orphan_scan_completed /
 *   version_update / welcome）按 extra_data.event + 参数本地化 title/content；
 * - 未知 event / 无 extra_data 的历史自由文本通知原文展示（E03 旧内容不改写）；
 * - 中英文均成对可用；孤儿护栏提示（orphan_count_warning）语义还原。
 */

import {
  notificationDisplayContent,
  notificationDisplayTitle
} from '@/utils/notification-display'
import i18n, { setLocale } from '@/i18n'
import { NotificationItem } from '@/api/notification'

const originalLocale = i18n.locale

afterAll(() => {
  setLocale(originalLocale as 'zh-CN' | 'en')
})

const makeItem = (overrides: Partial<NotificationItem>): NotificationItem => ({
  id: 1,
  type: 'system',
  title: '原始标题',
  content: '原始正文',
  priority: 'info',
  is_read: false,
  extra_data: null,
  created_at: '2026-09-21T09:00:00',
  read_at: null,
  ...overrides
})

describe('utils/notification-display 事件本地化（zh-CN 基准）', () => {
  beforeEach(() => {
    setLocale('zh-CN')
  })

  it('torrent_batch_add_completed：title 本地化，content 按计数参数插值', () => {
    const n = makeItem({
      title: '批量添加种子完成',
      content: '批量添加种子任务完成：共 3 个，成功 2 个，失败 1 个。',
      extra_data: {
        event: 'torrent_batch_add_completed',
        total_count: 3,
        success_count: 2,
        failed_count: 1
      }
    })
    expect(notificationDisplayTitle(n)).toBe('批量添加种子完成')
    expect(notificationDisplayContent(n)).toBe(
      '批量添加种子任务完成：共 3 个，成功 2 个，失败 1 个。'
    )
  })

  it('orphan_scan_completed：计数与大小插值；orphan_count_warning 追加护栏提示', () => {
    const base = {
      event: 'orphan_scan_completed' as const,
      scan_id: 's1',
      scan_type: 'manual',
      orphan_count: 5,
      orphan_size: 2048
    }
    const normal = makeItem({ extra_data: base })
    expect(notificationDisplayTitle(normal)).toBe('孤儿文件扫描完成')
    expect(notificationDisplayContent(normal)).toBe(
      '本次扫描发现 5 个孤儿文件，共 2.00 KB，请前往孤儿文件管理页面查看。'
    )

    const warned = makeItem({
      extra_data: { ...base, orphan_count_warning: true }
    })
    expect(notificationDisplayContent(warned)).toContain('护栏阈值')
    expect(notificationDisplayContent(warned)).toContain('请前往孤儿文件管理页面核查。')
  })

  it('version_update：title 参数化本地化，content 透传 Release 原文（不改写）', () => {
    const n = makeItem({
      type: 'version_update',
      title: 'BtDeck v1.0.9 版本更新',
      content: '## v1.0.9 release notes body',
      extra_data: { event: 'version_update', version: '1.0.9' }
    })
    expect(notificationDisplayTitle(n)).toBe('BtDeck 1.0.9 版本更新')
    expect(notificationDisplayContent(n)).toBe('## v1.0.9 release notes body')
  })

  it('welcome：title/content 本地化（脚本种子新通知携带 event）', () => {
    const n = makeItem({
      title: '欢迎使用 BtDeck',
      content: '感谢您使用 BtDeck！这是您的第一条系统通知。通知中心会在这里显示版本更新和系统消息。',
      extra_data: { event: 'welcome' }
    })
    expect(notificationDisplayTitle(n)).toBe('欢迎使用 BtDeck')
    expect(notificationDisplayContent(n)).toContain('感谢您使用 BtDeck')
  })

  it('未登记 event / 无 extra_data / 缺参数：原文展示兜底（E03 旧内容不改写）', () => {
    const unknownEvent = makeItem({
      title: '定时任务被安全策略拦截',
      content: '某任务执行被拦截',
      extra_data: { event: 'cron_blocked_by_policy' }
    })
    expect(notificationDisplayTitle(unknownEvent)).toBe('定时任务被安全策略拦截')
    expect(notificationDisplayContent(unknownEvent)).toBe('某任务执行被拦截')

    const noExtra = makeItem({ title: '历史通知', content: '历史自由文本' })
    expect(notificationDisplayTitle(noExtra)).toBe('历史通知')
    expect(notificationDisplayContent(noExtra)).toBe('历史自由文本')
  })
})

describe('utils/notification-display 事件本地化（en）', () => {
  beforeEach(() => {
    setLocale('en')
  })

  it('批量添加 / 孤儿扫描 / 版本更新事件均有英文文案', () => {
    const batchAdd = makeItem({
      extra_data: {
        event: 'torrent_batch_add_completed',
        total_count: 3,
        success_count: 2,
        failed_count: 1
      }
    })
    expect(notificationDisplayTitle(batchAdd)).toBe('Batch torrent add completed')
    expect(notificationDisplayContent(batchAdd)).toBe(
      'Batch add finished: 3 total, 2 succeeded, 1 failed.'
    )

    const orphan = makeItem({
      extra_data: {
        event: 'orphan_scan_completed',
        orphan_count: 4,
        orphan_size: 1024,
        orphan_count_warning: true
      }
    })
    expect(notificationDisplayTitle(orphan)).toBe('Orphan file scan completed')
    expect(notificationDisplayContent(orphan)).toContain('found 4 orphan files')
    expect(notificationDisplayContent(orphan)).toContain('exceeds the guardrail threshold')

    const version = makeItem({
      extra_data: { event: 'version_update', version: '1.0.9' }
    })
    expect(notificationDisplayTitle(version)).toBe('BtDeck 1.0.9 update available')
  })
})
