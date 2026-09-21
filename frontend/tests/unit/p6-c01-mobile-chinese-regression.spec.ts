/**
 * C01 移动中文回归抽查（P6-5 收口批）。
 *
 * 背景：桌面双语 P1～P6 分批把大量「桌面/移动共享层」（纯函数、store、utils）
 * 从内联中文改为 i18n 键。移动端页面（/m/*）按计划保持中文——其正确性依赖
 * 这些共享层在 zh 默认语言下输出**与原内联中文逐字节一致**（零回归原则）。
 *
 * 本 spec 抽查 P6-5 动过的共享层（本批翻译面）+ P6 各批代表性共享键：
 * - sync-task.ts buildSyncTaskNotice（移动下载器页终态通知）
 * - notification-markdown.ts notificationFailureTarget（移动通知页失败明细）
 * - clipboard.ts copyTextToClipboard（移动任务/日志/孤儿/设置页复制）
 * - error-normalize.ts 兜底（移动页间接经 request 层消费）
 * - traditionalStatusFilter 固定项键（传统视图状态筛选）
 * - downloader store 兜底键 / 主题键（zh 字节冻结）
 */
import { buildSyncTaskNotice } from '@/views/downloader/sync-task'
import { SyncTaskStatusData } from '@/api/downloader'
import { notificationFailureTarget } from '@/utils/notification-markdown'
import { copyTextToClipboard } from '@/utils/clipboard'
import { extractFromDetail, buildBusinessError } from '@/utils/error-normalize'
import { buildTraditionalStatusFilterItems } from '@/views/torrents/utils/traditionalStatusFilter'
import i18n, { setLocale, translate } from '@/i18n'

function makeTask(overrides: Partial<SyncTaskStatusData> = {}): SyncTaskStatusData {
  return {
    task_id: 'sync_001',
    task_type: 'sync',
    downloader_id: 'dl-1',
    downloader_nickname: '主力 QB',
    status: 'running',
    created_at: '2026-09-20T00:00:00',
    started_at: '2026-09-20T00:00:01',
    finished_at: null,
    progress: 0,
    result: null,
    error: null,
    execution_time: null,
    ...overrides
  }
}

describe('C01 移动中文回归抽查：共享层 zh 逐字节 + en 切换', () => {
  afterEach(() => setLocale('zh-CN'))

  describe('sync-task 终态通知（移动/桌面同源）', () => {
    it('zh：四态与原内联模板串逐字节一致（含 detail 后缀）', () => {
      setLocale('zh-CN')
      expect(buildSyncTaskNotice(makeTask({ status: 'cancelled' }), '').message).toBe('主力 QB 同步已取消')
      expect(buildSyncTaskNotice(makeTask({
        status: 'success', result: { status: 'success', outcome: 'partial', message: '1 成功，1 失败' }
      }), '').message).toBe('主力 QB 同步部分完成：1 成功，1 失败')
      expect(buildSyncTaskNotice(makeTask({ status: 'failed', error: 'RPC 不可用' }), '').message)
        .toBe('主力 QB 同步失败：RPC 不可用')
      expect(buildSyncTaskNotice(makeTask({ status: 'success' }), '').message).toBe('主力 QB 同步完成')
    })

    it('en：切英文输出英文（移动页不受影响，桌面英文用户可见）', () => {
      setLocale('en')
      expect(buildSyncTaskNotice(makeTask({ status: 'cancelled' }), '').message).toBe('Sync cancelled for 主力 QB')
      expect(buildSyncTaskNotice(makeTask({
        status: 'failed', error: 'RPC down'
      }), '').message).toBe('Sync failed for 主力 QB: RPC down')
    })

    it('downloader_nickname 缺失时回退调用方名（数据行为不变）', () => {
      setLocale('zh-CN')
      const task = makeTask({ status: 'success', downloader_nickname: undefined })
      expect(buildSyncTaskNotice(task, '实验室节点 A').message).toBe('实验室节点 A 同步完成')
    })
  })

  describe('notification-markdown 失败明细目标名兜底', () => {
    it('zh：字段全缺显示「记录 {id}」/「未知项」（与原内联逐字节一致）', () => {
      setLocale('zh-CN')
      expect(notificationFailureTarget({ id: 5 } as never)).toBe('记录 5')
      expect(notificationFailureTarget({ } as never)).toBe('未知项')
    })

    it('en：切英文；字段存在时数据原文优先（B03）', () => {
      setLocale('en')
      expect(notificationFailureTarget({ id: 5 } as never)).toBe('record 5')
      expect(notificationFailureTarget({ file_name: 'ubuntu.iso' } as never)).toBe('ubuntu.iso')
    })
  })

  describe('clipboard 错误信息', () => {
    it('zh：两种失败文案与原内联逐字节一致', () => {
      setLocale('zh-CN')
      // jsdom 无 execCommand 实现：触发「当前环境不支持」分支
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(document as any).execCommand = undefined
      return expect(copyTextToClipboard('x')).rejects.toThrow('当前环境不支持剪贴板复制')
    })

    it('en：切英文输出英文', () => {
      setLocale('en')
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(document as any).execCommand = undefined
      return expect(copyTextToClipboard('x')).rejects.toThrow('Clipboard copy is not supported in this environment')
    })
  })

  describe('error-normalize 兜底（E01：未识别错误按当前语言兜底）', () => {
    it('zh：参数校验失败 / 请求错误 / 操作失败与原内联逐字节一致', () => {
      setLocale('zh-CN')
      expect(extractFromDetail([{ msg: '' }], 422).message).toBe('参数校验失败')
      expect(extractFromDetail({ code: '500' }, 500).message).toBe('请求错误')
      expect(extractFromDetail('', 500).message).toBe('请求错误')
      expect(buildBusinessError({ code: '500' }, 200).message).toBe('操作失败')
    })

    it('en：切英文输出英文', () => {
      setLocale('en')
      expect(extractFromDetail([{ msg: '' }], 422).message).toBe('Invalid request parameters')
      expect(extractFromDetail('', 500).message).toBe('Request error')
      expect(buildBusinessError({ code: '500' }, 200).message).toBe('Operation failed')
    })
  })

  describe('传统视图状态筛选固定项（P6-5 补译）', () => {
    it('zh：全部/活动中键与原硬编码逐字节一致', () => {
      setLocale('zh-CN')
      const items = buildTraditionalStatusFilterItems(
        [{ icon: 'pause', label: '已暂停', value: 'paused' }],
        { allLabel: translate('torrent.list.filters.all'), activeLabel: translate('torrent.list.filters.activeStatus') }
      )
      expect(items[0].label).toBe('全部')
      expect(items[1].label).toBe('活动中')
    })

    it('en：键切换为 All/Active', () => {
      setLocale('en')
      expect(translate('torrent.list.filters.all')).toBe('All')
      expect(translate('torrent.list.filters.activeStatus')).toBe('Active')
    })
  })

  describe('store 兜底键与主题键 zh 字节冻结', () => {
    it('downloader.store 九条兜底 zh 与原内联逐字节一致', () => {
      setLocale('zh-CN')
      expect(translate('downloader.store.getSettingsFailed')).toBe('获取设置失败')
      expect(translate('downloader.store.updateSettingsFailed')).toBe('更新设置失败')
      expect(translate('downloader.store.getCapabilitiesFailed')).toBe('获取能力信息失败')
      expect(translate('downloader.store.getTemplatesFailed')).toBe('获取模板列表失败')
      expect(translate('downloader.store.getTemplateDetailFailed')).toBe('获取模板详情失败')
      expect(translate('downloader.store.createTemplateFailed')).toBe('创建模板失败')
      expect(translate('downloader.store.updateTemplateFailed')).toBe('更新模板失败')
      expect(translate('downloader.store.deleteTemplateFailed')).toBe('删除模板失败')
      expect(translate('downloader.store.applyTemplateFailed')).toBe('应用模板失败')
    })

    it('主题三套名/描述 zh 与原内联逐字节一致（ThemeSwitcher 展示）', () => {
      setLocale('zh-CN')
      expect(translate('common.theme.names.emerald')).toBe('翡翠绿')
      expect(translate('common.theme.names.orange')).toBe('活力橙')
      expect(translate('common.theme.names.graphite')).toBe('石墨灰')
      expect(translate('common.theme.descriptions.emerald')).toBe('自然流动 + 稳定可靠 + 高效传输')
      expect(translate('common.theme.switchedTo', { name: '翡翠绿' })).toBe('已切换到翡翠绿主题')
    })

    it('404 联系支持占位与演示横幅四条 zh 逐字节一致', () => {
      setLocale('zh-CN')
      expect(translate('common.notFound.supportComing')).toBe('支持功能开发中，敬请期待')
      expect(translate('common.demo.badge')).toBe('演示模式')
      expect(translate('common.demo.notice')).toBe('数据为本地模拟，不产生后端副作用')
      expect(translate('common.demo.reset')).toBe('重置数据')
      expect(translate('common.demo.resetDone')).toBe('演示数据已重置')
    })
  })

  it('语言恢复 zh-CN 后 i18n 单例语言正确（防测试间泄漏）', () => {
    setLocale('zh-CN')
    expect(i18n.locale).toBe('zh-CN')
  })
})
