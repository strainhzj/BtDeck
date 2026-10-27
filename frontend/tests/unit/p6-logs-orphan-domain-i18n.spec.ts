/**
 * 桌面双语 P6-4b：审计日志 + 孤儿文件域 i18n 契约（views/logs/audit.vue + views/orphan-files/index.vue）。
 *
 * 覆盖（对齐 p6-tasks-domain / p6-tracker-domain 同类 spec）：
 * A. 行为契约——auditLogs / orphanFiles 语言包 zh 逐字节与 en 插值抽查（危险链路三要素）；
 * B. 码位映射——操作类型 19 项（短/长双形态）与孤儿状态/置信度按稳定码位映射，未知值回退原文（Q02）；
 * C. reasonCode 契约——后端 P6-4b 新键（AUDIT_LOG_* / ORPHAN_*）经 apiResponseMessage 本地化；
 * D. 源码契约——错误展示接契约入口（禁中文 msg 直读）、E01 诊断明细转 console、
 *    后端扫描上下文/错误消息数据原文透传（B03/Q02）不进语言包。
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'

import { createLocalVue, shallowMount } from '@vue/test-utils'
import VueI18n from 'vue-i18n'

import i18n, { apiResponseMessage, setLocale, translate } from '@/i18n'
import AuditLogs from '@/views/logs/audit.vue'

const read = (file: string): string => readFileSync(resolve(__dirname, '../../', file), 'utf-8')

jest.mock('@/api/audit-logs', () => ({
  queryAuditLogs: jest.fn(() => Promise.resolve({ code: '200', msg: 'ok', status: 'success', data: { list: [], total: 0 } })),
  getAuditLogStatistics: jest.fn(() => Promise.resolve({ code: '200', msg: 'ok', status: 'success', data: null })),
  exportAuditLogs: jest.fn(),
  downloadExportFile: jest.fn(),
  archiveAuditLogs: jest.fn()
}))

const localVue = createLocalVue()
localVue.use(VueI18n)
localVue.directive('waves', {})

// ====================================================================
// A. 行为契约：zh 逐字节 / en 插值
// ====================================================================

describe('P6-4b 操作日志页文案', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：页头/筛选/操作栏/统计/表头/弹窗与原内联逐字节一致', () => {
    setLocale('zh-CN')
    expect(translate('auditLogs.title')).toBe('操作日志')
    expect(translate('auditLogs.subtitle')).toBe('检索关键操作记录，核对执行结果并导出留档')
    expect(translate('auditLogs.filter.panelTitle')).toBe('筛选日志')
    expect(translate('auditLogs.filter.panelDescription')).toBe('可组合名称、类型、操作人、结果与时间范围进行查询')
    expect(translate('auditLogs.filter.countTag', { count: 12 })).toBe('共 12 条')
    expect(translate('auditLogs.filter.torrentNamePlaceholder')).toBe('支持模糊搜索')
    expect(translate('auditLogs.filter.allTypes')).toBe('全部类型')
    expect(translate('auditLogs.filter.operatorPlaceholder')).toBe('全部操作人')
    expect(translate('auditLogs.filter.allResults')).toBe('全部结果')
    expect(translate('auditLogs.filter.rangeSeparator')).toBe('至')
    expect(translate('auditLogs.actions.title')).toBe('日志操作')
    expect(translate('auditLogs.actions.exportCsv')).toBe('导出为 CSV')
    expect(translate('auditLogs.actions.archive')).toBe('归档历史日志')
    expect(translate('auditLogs.stats.total')).toBe('总日志数')
    expect(translate('auditLogs.stats.today')).toBe('今日操作')
    expect(translate('auditLogs.col.operationType')).toBe('操作类型')
    expect(translate('auditLogs.col.ip')).toBe('IP地址')
    expect(translate('auditLogs.empty')).toBe('暂无审计日志')
    expect(translate('auditLogs.detailDialog.title')).toBe('审计日志详情')
    expect(translate('auditLogs.detailDialog.oldSection')).toBe('修改前（旧值）')
    expect(translate('auditLogs.detailDialog.requestId')).toBe('请求ID：')
    expect(translate('auditLogs.detailDialog.copyJson')).toBe('复制 JSON')
    expect(translate('auditLogs.archiveDialog.noticeTitle')).toBe('归档说明')
    expect(translate('auditLogs.archiveDialog.fileNameHint')).toBe('仅接受文件名（自动追加 .json 后缀），固定保存到：data/audit_logs_archive/')
    expect(translate('auditLogs.archiveDialog.confirm')).toBe('确认归档')
  })

  it('zh：归档危险语义三要素（对象+不可恢复+确认）逐字节', () => {
    setLocale('zh-CN')
    expect(translate('auditLogs.msg.archiveConfirm')).toBe('归档操作不可恢复，确定要归档审计日志吗？')
    expect(translate('auditLogs.msg.confirmTitle')).toBe('警告')
    expect(translate('auditLogs.msg.ok')).toBe('确定')
    expect(translate('auditLogs.msg.archiveSuccess', { count: 8 })).toBe('归档成功，已归档 8 条日志')
    expect(translate('auditLogs.msg.exporting', { format: 'CSV' })).toBe('正在导出为 CSV...')
  })

  it('en：操作日志域输出英文（插值保参数）', () => {
    setLocale('en')
    expect(translate('auditLogs.title')).toBe('Operation Logs')
    expect(translate('auditLogs.filter.countTag', { count: 12 })).toBe('12 records in total')
    expect(translate('auditLogs.msg.archiveSuccess', { count: 8 })).toBe('Archived 8 logs')
    expect(translate('auditLogs.msg.archiveConfirm')).toBe('Archiving cannot be undone. Archive the audit logs now?')
    expect(translate('auditLogs.msg.exporting', { format: 'CSV' })).toBe('Exporting as CSV...')
  })
})

describe('P6-4b 孤儿文件页文案', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：页头/页签/统计/筛选/工具栏/表头与原内联逐字节一致', () => {
    setLocale('zh-CN')
    expect(translate('orphanFiles.title')).toBe('孤儿文件')
    expect(translate('orphanFiles.subtitle')).toBe('扫描未被种子引用的文件，并在清理前进行安全复核')
    expect(translate('orphanFiles.scanNow')).toBe('立即扫描')
    expect(translate('orphanFiles.tabs.quarantine')).toBe('隔离区')
    expect(translate('orphanFiles.stats.pendingCount')).toBe('待清理文件数')
    expect(translate('orphanFiles.stats.noScan')).toBe('尚无成功扫描')
    expect(translate('orphanFiles.scanState.largeTitle')).toBe('超量扫描提醒')
    expect(translate('orphanFiles.scanState.largeText')).toBe('本次扫描发现的孤儿文件数量较多，请留意下载器路径映射和孤儿判定；此提醒不影响清理。')
    expect(translate('orphanFiles.filter.statusDegradedTip')).toBe('同时选“待清理”与“已忽视/已清理”会扩大为全部未删除文件')
    expect(translate('orphanFiles.filter.locatedTip')).toBe('按扫描时统计的硬链接副本数过滤；副本位置详情由弹窗实时复核')
    expect(translate('orphanFiles.list.selected', { count: 3 })).toBe('已选择 3 项')
    expect(translate('orphanFiles.list.quickCleanup')).toBe('快捷清理（按路径前缀）')
    expect(translate('orphanFiles.list.empty')).toBe('暂无孤儿文件，点击“立即扫描”开始检测')
    expect(translate('orphanFiles.list.col.path')).toBe('文件路径')
    expect(translate('orphanFiles.list.filesCount', { count: 5 })).toBe('5 个文件')
    expect(translate('orphanFiles.list.multipleDownloaders')).toBe('多个')
    expect(translate('orphanFiles.list.totalPrefix')).toBe('共 ')
    expect(translate('orphanFiles.list.totalSuffix')).toBe(' 条')
    expect(translate('orphanFiles.quarantine.subtitle', { days: 7 })).toBe('已清理文件暂存于此（保留期 7 天），可恢复到原位置或立即彻底删除')
    expect(translate('orphanFiles.quarantine.col.path')).toBe('原位置（规范化路径）')
    expect(translate('orphanFiles.quarantine.total', { count: 4 })).toBe('共 4 条')
  })

  it('zh：隔离清理/彻底删除/删除副本危险语义分别表达', () => {
    setLocale('zh-CN')
    expect(translate('orphanFiles.cleanup.confirmTitle')).toBe('确认将以下孤儿文件移入隔离区？在永久删除前可从隔离区恢复。')
    expect(translate('orphanFiles.cleanup.lowText')).toBe('低置信度文件可能仍被种子引用。移入隔离区前请核对路径，避免将用户数据误判为孤儿文件。')
    expect(translate('orphanFiles.msg.purgeConfirm')).toBe('确认彻底删除选中的文件？此操作不可恢复，文件将被永久删除！')
    expect(translate('orphanFiles.msg.restoreConfirm')).toBe('确认恢复选中的文件到原位置？')
    expect(translate('orphanFiles.hardlink.deleteConfirm', { path: '/lib/a.mkv' })).toBe(
      '确认删除硬链接副本？\n/lib/a.mkv\n此操作不可恢复：仅移除该路径链接，数据仍由源文件保留；位于种子目录内的副本会被拒绝删除。'
    )
    expect(translate('orphanFiles.msg.scanConfirm')).toBe('确认立即扫描孤儿文件？扫描可能需要较长时间。')
    expect(translate('orphanFiles.msg.affectCount', { count: 5 })).toBe('将影响 5 个待清理文件')
    expect(translate('orphanFiles.msg.moveToQuarantine')).toBe('\n\n确认将它们移入隔离区（可恢复）？')
  })

  it('zh：快捷操作说明文案按 strong 分片重组后与原内联一致', () => {
    setLocale('zh-CN')
    const composed =
      translate('orphanFiles.quickAction.noticeLead') +
      translate('orphanFiles.quickAction.noticeFileStrong') +
      translate('orphanFiles.quickAction.noticeMid') +
      translate('orphanFiles.quickAction.noticePendingStrong') +
      translate('orphanFiles.quickAction.noticeTail')
    expect(composed).toBe('输入路径前缀（绝对路径开头），将匹配所有文件路径 以此开头的待清理文件（排除已忽视/已清理）。')
    expect(translate('orphanFiles.quickAction.cleanupNote')).toBe('清理会将文件移入隔离区；永久删除前可恢复。')
    expect(translate('orphanFiles.quickAction.prefixPlaceholder')).toBe('例如：D:\\downloads\\待清理目录\\ 或 /data/leak/')
  })

  it('en：孤儿文件域输出英文（危险语义三要素保留）', () => {
    setLocale('en')
    expect(translate('orphanFiles.title')).toBe('Orphan Files')
    expect(translate('orphanFiles.scanNow')).toBe('Scan Now')
    expect(translate('orphanFiles.list.selected', { count: 3 })).toBe('3 selected')
    expect(translate('orphanFiles.msg.purgeConfirm')).toBe('Permanently delete the selected files? This cannot be undone; the files will be deleted forever!')
    expect(translate('orphanFiles.msg.scanConfirm')).toBe('Scan for orphan files now? The scan may take a while.')
    expect(translate('orphanFiles.hardlink.deleteConfirm', { path: '/lib/a.mkv' })).toContain('This cannot be undone')
    expect(translate('orphanFiles.hardlink.deleteConfirm', { path: '/lib/a.mkv' })).toContain('/lib/a.mkv')
    expect(translate('orphanFiles.list.totalPrefix')).toBe('')
    expect(translate('orphanFiles.list.totalSuffix')).toBe(' items in total')
  })

  it('zh/en：状态与置信度按稳定码位映射（标签与筛选选项同源）', () => {
    setLocale('zh-CN')
    expect(translate('orphanFiles.status.pending')).toBe('待清理')
    expect(translate('orphanFiles.status.ignored')).toBe('已忽视')
    expect(translate('orphanFiles.status.deleted')).toBe('已清理')
    expect(translate('orphanFiles.status.mixed')).toBe('混合')
    expect(translate('orphanFiles.confidence.high')).toBe('高置信度')
    expect(translate('orphanFiles.confidenceTag.low')).toBe('低')
    setLocale('en')
    expect(translate('orphanFiles.status.pending')).toBe('Pending cleanup')
    expect(translate('orphanFiles.status.mixed')).toBe('Mixed')
    expect(translate('orphanFiles.confidence.high')).toBe('High confidence')
  })

  it('zh/en：扫描状态三态与失败包装（error_message 原文经 {reason} 槽位透传）', () => {
    setLocale('zh-CN')
    expect(translate('orphanFiles.scanState.queuedDesc')).toBe('扫描任务已进入后台队列；页面仅轮询轻量状态，列表与清理暂不可用。')
    expect(translate('orphanFiles.scanState.failedWithDisplay', { reason: 'IO 错误' })).toBe(
      '失败原因：IO 错误。当前只读展示最近一次成功扫描的剩余结果，重新扫描成功前不可清理。'
    )
    setLocale('en')
    expect(translate('orphanFiles.scanState.failedNoDisplay', { reason: 'IO error' })).toContain('IO error')
    expect(translate('orphanFiles.msg.scanDone', { total: 10, added: 3, known: 7 })).toBe(
      'Scan finished: 10 orphans, 3 new details, 7 reused'
    )
  })
})

// ====================================================================
// B. 码位映射：操作类型 19 项（短/长双形态）+ 未知值回退（Q02）
// ====================================================================

describe('P6-4b 操作类型码位映射', () => {
  afterEach(() => setLocale('zh-CN'))

  function mountAudit() {
    return shallowMount(AuditLogs, {
      localVue,
      i18n,
      stubs: {
        CollapsiblePanel: { template: '<div><slot name="meta" /><slot /></div>' }
      }
    })
  }

  it('zh：19 项操作类型短标签 + 删除四级长标签（含等级语义后缀）', () => {
    setLocale('zh-CN')
    const wrapper = mountAudit()
    const vm = wrapper.vm as InstanceType<typeof AuditLogs> & {
      getOperationTypeName: (t: string) => string
      operationTypeFilterLabel: (opt: { value: string, key: string }) => string
    }
    expect(vm.getOperationTypeName('add')).toBe('新增种子')
    expect(vm.getOperationTypeName('delete_l4')).toBe('等级4删除')
    expect(vm.getOperationTypeName('keyword_rule_update')).toBe('修改关键词规则')
    expect(vm.operationTypeFilterLabel({ value: 'delete_l4', key: 'deleteL4' })).toBe('等级4删除（待删除）')
    expect(vm.operationTypeFilterLabel({ value: 'delete_l1', key: 'deleteL1' })).toBe('等级1删除（完全删除）')
    expect(vm.operationTypeFilterLabel({ value: 'add', key: 'add' })).toBe('新增种子')
    wrapper.destroy()
  })

  it('未知操作类型/结果回退原始值（Q02），已登记结果三态映射', () => {
    setLocale('zh-CN')
    const wrapper = mountAudit()
    const vm = wrapper.vm as InstanceType<typeof AuditLogs> & {
      getOperationTypeName: (t: string) => string
      getResultName: (r: string) => string
    }
    expect(vm.getOperationTypeName('custom_future_op')).toBe('custom_future_op')
    expect(vm.getResultName('success')).toBe('成功')
    expect(vm.getResultName('partial')).toBe('部分成功')
    expect(vm.getResultName('weird')).toBe('weird')
    wrapper.destroy()
  })

  it('en：操作类型/筛选长标签输出英文', () => {
    setLocale('en')
    const wrapper = mountAudit()
    const vm = wrapper.vm as InstanceType<typeof AuditLogs> & {
      getOperationTypeName: (t: string) => string
      operationTypeFilterLabel: (opt: { value: string, key: string }) => string
    }
    expect(vm.getOperationTypeName('add')).toBe('Add torrent')
    expect(vm.getOperationTypeName('delete_l3')).toBe('Level 3 delete')
    expect(vm.operationTypeFilterLabel({ value: 'delete_l3', key: 'deleteL3' })).toBe('Level 3 delete (recycle bin)')
    wrapper.destroy()
  })

  it('筛选下拉选项数组键化：OPERATION_GROUPS 无中文标签字面量', () => {
    const source = read('src/views/logs/audit.vue')
    expect(source.includes("labelKey: 'auditLogs.operationGroup.seed'")).toBe(true)
    expect(source.includes("value: 'delete_l4', key: 'deleteL4'")).toBe(true)
    // 短/长双形态的分离：filterLabel 有 operationTypeFull 分支
    expect(source.includes('OPERATION_FULL_LABEL_KEYS')).toBe(true)
  })
})

// ====================================================================
// C. reasonCode 契约：AUDIT_LOG_* / ORPHAN_* 本地化
// ====================================================================

describe('P6-4b reasonCode 契约入口', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：audit-logs / orphan-files 新键按 errors.byCode 本地化', () => {
    setLocale('zh-CN')
    expect(
      apiResponseMessage({ code: '400', msg: '没有符合条件的数据可导出', data: { reasonCode: 'AUDIT_LOG_EXPORT_EMPTY' } }, '兜底')
    ).toBe('没有符合条件的数据可导出')
    expect(
      apiResponseMessage({ code: '500', msg: '导出失败: Oops', data: { reasonCode: 'AUDIT_LOG_EXPORT_FAILED' } }, '兜底')
    ).toBe('导出失败，请稍后重试')
    expect(
      apiResponseMessage({ code: '400', msg: 'x', data: { reasonCode: 'AUDIT_LOG_PARAM_INVALID' } }, '兜底')
    ).toBe('时间参数格式错误')
    expect(
      apiResponseMessage({ code: '500', msg: 'x', data: { reasonCode: 'ORPHAN_LIST_FAILED' } }, '兜底')
    ).toBe('查询孤儿文件列表失败，请稍后重试')
    expect(
      apiResponseMessage({ code: '404', msg: '扫描任务不存在', data: { reasonCode: 'ORPHAN_SCAN_NOT_FOUND' } }, '兜底')
    ).toBe('扫描任务不存在')
    expect(
      apiResponseMessage({ code: '200', msg: '维护操作互斥', data: { reasonCode: 'ORPHAN_HARDLINK_DELETE_REJECTED' } }, '兜底')
    ).toBe('维护操作互斥或有拦截，本次未执行删除')
  })

  it('en：同批新键输出英文', () => {
    setLocale('en')
    expect(
      apiResponseMessage({ code: '500', msg: 'x', data: { reasonCode: 'AUDIT_LOG_ARCHIVE_FAILED' } }, 'fallback')
    ).toBe('Archive failed, please try again later')
    expect(
      apiResponseMessage({ code: '500', msg: 'x', data: { reasonCode: 'ORPHAN_QUARANTINE_RESTORE_FAILED' } }, 'fallback')
    ).toBe('Restore failed, please try again later')
    expect(
      apiResponseMessage({ code: '500', msg: 'x', data: { reasonCode: 'ORPHAN_SCAN_SUBMIT_FAILED' } }, 'fallback')
    ).toBe('Failed to submit the scan task, please try again later')
  })

  it('未登记 reasonCode 回退 fallback（不透出后端中文 msg）', () => {
    expect(apiResponseMessage({ code: '400', msg: '后端中文原文', data: { reasonCode: 'NOT_A_P6B_CODE' } }, '本地兜底')).toBe('本地兜底')
  })
})

// ====================================================================
// D. 源码契约：错误接线 / E01 诊断转 console / 数据原文透传
// ====================================================================

describe('P6-4b 源码契约', () => {
  it('操作日志页错误展示接 apiResponseMessage/apiErrorMessage（禁中文 msg 直读）', () => {
    const source = read('src/views/logs/audit.vue')
    expect(source.includes("import { apiErrorMessage, apiResponseMessage } from '@/i18n'")).toBe(true)
    expect(source.includes('apiResponseMessage(response,')).toBe(true)
    expect(source.includes("response.msg || '")).toBe(false)
    expect(source.includes("response?.msg || '")).toBe(false)
  })

  it('孤儿文件页错误展示接契约入口（禁中文 msg 直读）', () => {
    const source = read('src/views/orphan-files/index.vue')
    expect(source.includes("import { apiResponseMessage, translate } from '@/i18n'")).toBe(true)
    expect(source.includes('apiResponseMessage(response,')).toBe(true)
    expect(source.includes('apiResponseMessage(resp,')).toBe(true)
    expect(source.includes("response.msg || '")).toBe(false)
    expect(source.includes("res.msg || '")).toBe(false)
    expect(source.includes("resp.msg || '")).toBe(false)
  })

  it('E01：拒绝/部分失败明细只进 console，用户提示用固定键或计数键', () => {
    const source = read('src/views/orphan-files/index.vue')
    expect(source.includes("console.error('隔离区恢复被拒绝:'")).toBe(true)
    expect(source.includes("console.error('删除硬链接副本被拒绝:'")).toBe(true)
    expect(source.includes("console.error('清理预览被拒绝:'")).toBe(true)
    expect(source.includes("console.error('快捷忽视部分失败明细:'")).toBe(true)
    // 旧直读链路不回流
    expect(source.includes('data.failed_list[0]?.reason ||')).toBe(false)
    expect(source.includes('d.failed_list[0]?.reason ||')).toBe(false)
  })

  it('B03/Q02：后端扫描上下文与错误消息原文透传（{reason} 槽位），本地兜底走键', () => {
    const source = read('src/views/orphan-files/index.vue')
    // error_message / cleanup_block_reason 属后端数据，原文展示 + 本地键兜底
    expect(source.includes('latest.error_message ||')).toBe(true)
    expect(source.includes('translate(\'orphanFiles.scanState.unknownError\')')).toBe(true)
    expect(source.includes('this.scanContext.cleanup_block_reason ||')).toBe(true)
    expect(source.includes("translate('orphanFiles.msg.blockReasonDefault')")).toBe(true)
    expect(source.includes("translate('orphanFiles.msg.blockReasonInitial')")).toBe(true)
  })

  it('筛选/状态选项数组键化（码位驱动），语言切换响应式', () => {
    const source = read('src/views/orphan-files/index.vue')
    expect(source.includes("label: translate('orphanFiles.status.pending')")).toBe(true)
    expect(source.includes("label: translate('orphanFiles.confidence.high')")).toBe(true)
    expect(source.includes("label: '待清理'")).toBe(false)
    expect(source.includes("label: '高置信度'")).toBe(false)
  })

  it('任务提交类 200 信息态按 task_id 分支提示（不依赖后端 msg 文案）', () => {
    const source = read('src/views/orphan-files/index.vue')
    expect(source.includes("translate('orphanFiles.msg.purgeAllProcessing')")).toBe(true)
    expect(source.includes("translate('orphanFiles.msg.cleanupAllProcessing')")).toBe(true)
    expect(source.includes("translate('orphanFiles.msg.matchAllProcessing')")).toBe(true)
  })
})
