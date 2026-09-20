/**
 * 桌面双语 P6-4a：定时任务域 i18n 契约（任务页 + Cron/Monaco/Python 类选择三组件 + api/tasks 共享层）。
 *
 * 覆盖（对齐 p6-tracker-domain 同类 spec）：
 * A. 行为契约——tasks 语言包子树（tabs/list/type/status/outcome/stale/logs/form/syntax/
 *    logDetail/preview/cleanupDialog/msg/dialog/cronEditor/monaco/pythonSelector）zh 逐字节与 en 插值抽查；
 * B. reasonCode 契约——后端 P6-4a 新键（TASKS_*）经 apiResponseMessage 按 errors.byCode 本地化；
 * C. 共享层——api/tasks 的 getTaskOutcomeMeta（六态）与 getStaleTooltipText 双语输出（移动端复用面 C01）；
 * D. 源码契约——模板身份 key 化（'每天' 中文匹配不回流）、预定义类由后端 type-config 驱动（假树不回流）、
 *    错误展示接 apiErrorMessage/apiResponseMessage、分页分片键。
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'

import { createLocalVue, shallowMount } from '@vue/test-utils'
import VueI18n from 'vue-i18n'

import i18n, { apiResponseMessage, setLocale, translate } from '@/i18n'
import { getStaleTooltipText, getTaskOutcomeMeta } from '@/api/tasks'

const read = (file: string): string => readFileSync(resolve(__dirname, '../../', file), 'utf-8')

const localVue = createLocalVue()
localVue.use(VueI18n)

// ====================================================================
// A. 行为契约：zh 逐字节 / en 插值
// ====================================================================

describe('P6-4a 任务页签与列表文案', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：页签/筛选/工具栏/表格列/菜单与原内联逐字节一致', () => {
    setLocale('zh-CN')
    expect(translate('tasks.tabs.management')).toBe('任务管理')
    expect(translate('tasks.tabs.logs')).toBe('任务日志')
    expect(translate('tasks.list.title')).toBe('任务列表')
    expect(translate('tasks.list.filter.selectPlaceholder')).toBe('请选择')
    expect(translate('tasks.list.toolbar.create')).toBe('新增任务')
    expect(translate('tasks.list.col.cron')).toBe('Cron表达式')
    expect(translate('tasks.list.platformDisabled')).toBe('平台禁用')
    expect(translate('tasks.list.dataStale')).toBe('数据陈旧')
    expect(translate('tasks.list.menu.execute')).toBe('立即执行')
    expect(translate('tasks.list.tip.executeDisabled')).toBe('任务已禁用，请先启用')
    expect(translate('tasks.list.pagination.perPageSuffix')).toBe(' 条/页')
  })

  it('en：任务域输出英文', () => {
    setLocale('en')
    expect(translate('tasks.tabs.management')).toBe('Task Management')
    expect(translate('tasks.list.menu.execute')).toBe('Run now')
    expect(translate('tasks.list.pagination.middle')).toBe(', page ')
    expect(translate('tasks.list.pagination.suffix')).toBe('')
  })

  it('zh：任务类型/状态按稳定码位映射（两处兜底措辞不同）', () => {
    setLocale('zh-CN')
    expect(translate('tasks.type.pythonClass')).toBe('python内部类')
    expect(translate('tasks.type.cleanup')).toBe('清理回收站')
    expect(translate('tasks.type.unknownShort')).toBe('未知')
    expect(translate('tasks.type.unknownType')).toBe('未知类型')
    expect(translate('tasks.type.executorFallback')).toBe('执行内容')
    expect(translate('tasks.status.running')).toBe('运行中')
    expect(translate('tasks.status.unknown')).toBe('未知状态')
  })

  it('zh：危险与批量操作语义逐字节（不可恢复明示）', () => {
    setLocale('zh-CN')
    expect(translate('tasks.msg.deleteConfirm')).toBe('确定要删除这个任务吗?')
    expect(translate('tasks.msg.batchDeleteConfirm', { count: 3 })).toBe('确定要删除选中的 3 个任务吗？此操作不可恢复！')
    expect(translate('tasks.msg.taskDisabled', { name: 'sync' })).toBe('任务 "sync" 已禁用，无法启动。请先启用该任务。')
    expect(translate('tasks.msg.switchedLogs', { name: 'sync' })).toBe('已切换到任务"sync"的日志')
    expect(translate('tasks.msg.logTaskFallback', { id: 7 })).toBe('任务 7')
  })

  it('en：危险与批量操作输出英文', () => {
    setLocale('en')
    expect(translate('tasks.msg.batchDeleteConfirm', { count: 3 })).toBe('Delete the 3 selected tasks? This cannot be undone!')
    expect(translate('tasks.msg.taskDisabled', { name: 'sync' })).toBe('Task "sync" is disabled and cannot be started. Enable it first.')
  })
})

describe('P6-4a 日志/表单/弹窗与 Cron 编辑器文案', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：日志统计/筛选/清理弹窗逐字节', () => {
    setLocale('zh-CN')
    expect(translate('tasks.logs.statsTitle')).toBe('日志统计')
    expect(translate('tasks.logs.stat.today')).toBe('今日日志')
    expect(translate('tasks.logs.activeFilter')).toBe('当前任务筛选')
    expect(translate('tasks.logs.filter.rangeSep')).toBe('至')
    expect(translate('tasks.logs.toolbar.cleanup')).toBe('清理过期日志')
    expect(translate('tasks.cleanupDialog.keepDaysHint')).toBe('清理此天数之前的日志')
    expect(translate('tasks.cleanupDialog.confirm')).toBe('确定清理')
  })

  it('zh：任务表单/语法错误/清理配置/高级配置逐字节', () => {
    setLocale('zh-CN')
    expect(translate('tasks.form.cleanup.level3Unsupported')).toBe('当前主机不支持等级3文件操作')
    expect(translate('tasks.form.cleanup.daysDesc')).toBe('清理多少天前的种子（1-365天）')
    expect(translate('tasks.form.cronError', { message: 'bad' })).toBe('Cron表达式错误: bad')
    expect(translate('tasks.form.enabledOffDesc')).toBe('禁用状态：任务不会执行')
    expect(translate('tasks.syntax.lineError', { line: 3, message: 'oops' })).toBe('第3行：oops')
    expect(translate('tasks.syntax.viewAll', { count: 5 })).toBe('查看全部 5 个错误')
    expect(translate('tasks.syntax.detailLine', { line: 3, col: 9 })).toBe('第3行, 第9列:')
  })

  it('zh：Cron 编辑器字段/校验/内置模板逐字节', () => {
    setLocale('zh-CN')
    expect(translate('tasks.cronEditor.field.tooltipDay')).toBe('日 (1-31, L=最后一天)')
    expect(translate('tasks.cronEditor.rules.expressionFiveFields')).toBe('Cron表达式必须包含5个字段：分 时 日 月 周')
    expect(translate('tasks.cronEditor.rules.fieldInvalid', { index: 2, part: 'x' })).toBe('第2个字段格式不正确: x')
    expect(translate('tasks.cronEditor.time.soon')).toBe('即将执行')
    expect(translate('tasks.cronEditor.time.tomorrow', { time: '08:00' })).toBe('明天 08:00')
    expect(translate('tasks.cronEditor.templates.daily.name')).toBe('每天')
    expect(translate('tasks.cronEditor.templates.daily.desc')).toBe('每天0点执行')
    expect(translate('tasks.cronEditor.templates.workdayAm.desc')).toBe('工作日9点和17点执行')
  })

  it('en：Cron 编辑器输出英文', () => {
    setLocale('en')
    expect(translate('tasks.cronEditor.tabs.template')).toBe('Templates')
    expect(translate('tasks.cronEditor.templates.daily.name')).toBe('Daily')
    expect(translate('tasks.cronEditor.time.daysLater', { count: 2 })).toBe('in 2 days')
  })

  it('zh：Python 类选择器与 Monaco 逐字节', () => {
    setLocale('zh-CN')
    expect(translate('tasks.pythonSelector.tabs.preset')).toBe('预定义类')
    expect(translate('tasks.pythonSelector.manual.waitingDesc')).toBe('请点击验证按钮检查类路径')
    expect(translate('tasks.pythonSelector.detail.colRequired')).toBe('必填')
    expect(translate('tasks.pythonSelector.validation.missingParts')).toBe('类路径应包含至少一个模块名和类名')
    expect(translate('tasks.monaco.fallbackTitle')).toBe('编辑器加载失败')
    expect(translate('tasks.monaco.printQuoteHint')).toBe('print语句可能缺少引号')
  })
})

// ====================================================================
// B. reasonCode 契约（TASKS_* → errors.byCode 本地化）
// ====================================================================

describe('P6-4a reasonCode → errors.byCode 本地化', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：任务域 reasonCode 输出本地化文案（不透传后端 msg）', () => {
    setLocale('zh-CN')
    expect(
      apiResponseMessage({ code: '403', msg: '自定义脚本任务已被安全策略禁用；如确需启用，请设置 ...', data: { reasonCode: 'TASKS_CUSTOM_SCRIPTS_DISABLED' } }, '兜底')
    ).toBe('自定义脚本任务已被安全策略禁用，如需启用请联系管理员')
    expect(
      apiResponseMessage({ code: '400', msg: "任务编码 'x' 已存在，请使用其他编码", data: { reasonCode: 'TASKS_TASK_CONFLICT' } }, '兜底')
    ).toBe('任务编码或名称已存在，请修改后重试')
    expect(
      apiResponseMessage({ code: '404', msg: '定时任务不存在', data: { reasonCode: 'TASKS_NOT_FOUND' } }, '兜底')
    ).toBe('定时任务不存在或已删除')
    expect(
      apiResponseMessage({ code: '422', msg: '参数错误: x', data: { reasonCode: 'TASKS_CLEANUP_INVALID_PARAMS' } }, '兜底')
    ).toBe('请求参数有误，请检查后重试')
  })

  it('en：任务域 reasonCode 输出英文；SCREAMING_SNAKE → camelCase 映射一致', () => {
    setLocale('en')
    expect(
      apiResponseMessage({ code: '500', msg: 'x', data: { reasonCode: 'TASKS_LOG_CLEANUP_FAILED' } }, 'fallback')
    ).toBe('Failed to clean up task logs, please try again later')
    expect(
      apiResponseMessage({ code: '500', msg: 'x', data: { reasonCode: 'TASKS_CLEANUP_PREVIEW_FAILED' } }, 'fallback')
    ).toBe('Failed to preview the cleanup, please try again later')
    expect(
      apiResponseMessage({ code: '400', msg: 'x', data: { reasonCode: 'TASKS_EXECUTOR_NOT_ALLOWED' } }, 'fallback')
    ).toBe('The execution class path is outside the allowed scope')
  })

  it('未登记 reasonCode 回退 fallback（不透出后端中文 msg）', () => {
    expect(apiResponseMessage({ code: '400', msg: '后端中文原文', data: { reasonCode: 'NOT_A_TASKS_CODE' } }, '本地兜底')).toBe('本地兜底')
  })
})

// ====================================================================
// C. 共享层：api/tasks 六态与 stale tooltip（桌面/移动复用，C01）
// ====================================================================

describe('P6-4a api/tasks 共享展示层', () => {
  afterEach(() => setLocale('zh-CN'))

  it('getTaskOutcomeMeta：六态 type 稳定 + 文案按语言输出；未知/空值返回 null', () => {
    setLocale('zh-CN')
    expect(getTaskOutcomeMeta('success')).toEqual({ type: 'success', text: '成功' })
    expect(getTaskOutcomeMeta('no_action')).toEqual({ type: 'info', text: '无变化' })
    expect(getTaskOutcomeMeta('cancelled')).toEqual({ type: 'info', text: '已取消' })
    expect(getTaskOutcomeMeta('unknown_value')).toBeNull()
    expect(getTaskOutcomeMeta(null)).toBeNull()
    setLocale('en')
    expect(getTaskOutcomeMeta('partial')).toEqual({ type: 'warning', text: 'Partial success' })
    expect(getTaskOutcomeMeta('skipped')).toEqual({ type: 'info', text: 'Skipped' })
  })

  it('getStaleTooltipText：三种形态双语输出', () => {
    setLocale('zh-CN')
    expect(getStaleTooltipText(null, '2026-09-20 10:00')).toBe('任务自 2026-09-20 10:00 起已有执行尝试，但尚无成功数据更新（数据陈旧）')
    expect(getStaleTooltipText('2026-09-19 08:00', 'x')).toBe('数据陈旧：最后数据更新时间为 2026-09-19 08:00')
    expect(getStaleTooltipText(null, null)).toBe('数据陈旧：最近一次数据更新距今过久')
    setLocale('en')
    expect(getStaleTooltipText('2026-09-19 08:00', 'x')).toBe('Stale data: last data update was at 2026-09-19 08:00')
  })
})

// ====================================================================
// D. 源码契约：身份 key 化 / 后端驱动 / 错误接线
// ====================================================================

describe('P6-4a 源码契约', () => {
  it('CronEditor 内置模板身份与展示 key 化（中文 name 匹配不回流）', () => {
    const source = read('src/components/tasks/CronEditor.vue')
    expect(source.includes("t.key === 'daily'")).toBe(true)
    expect(source.includes("t.name === '每天'")).toBe(false)
    expect(source.includes("name: '每分钟'")).toBe(false)
    expect(source.includes('templateIdentity')).toBe(true)
    // 自定义模板（用户数据）仍原文直出
    expect(source.includes('template.name')).toBe(true)
  })

  it('PythonClassSelector 预定义类由后端 type-config 驱动（假类树不回流）', () => {
    const source = read('src/components/tasks/PythonClassSelector.vue')
    expect(source.includes('getTaskTypeConfig()')).toBe(true)
    expect(source.includes('buildTreeFromClasses')).toBe(true)
    expect(source.includes("label: 'BackupTask'")).toBe(false)
    expect(source.includes('app.tasks.backup.BackupTask')).toBe(false)
  })

  it('getTaskTypeConfig 此前零调用 → 本批由 PythonClassSelector 消费', () => {
    const api = read('src/api/tasks.ts')
    const selector = read('src/components/tasks/PythonClassSelector.vue')
    expect(api.includes('export function getTaskTypeConfig')).toBe(true)
    expect(selector.includes("import { getTaskTypeConfig")).toBe(true)
  })

  it('任务页错误展示接 apiErrorMessage/apiResponseMessage（msg 直读不回流）', () => {
    const source = read('src/views/tasks/index.vue')
    expect(source.includes("from '@/i18n'")).toBe(true)
    expect(source.includes('apiErrorMessage(error')).toBe(true)
    expect(source.includes('apiResponseMessage(res')).toBe(true)
    expect(source.includes('error.response.data.msg ||')).toBe(false)
    expect(source.includes('res.msg ||')).toBe(false)
  })

  it('任务状态展示按稳定码位（taskStatusName 直显不回流）', () => {
    const source = read('src/views/tasks/index.vue')
    expect(source.includes('{{ getStatusName(scope.row) }}')).toBe(true)
    expect(source.includes('{{ scope.row.taskStatusName }}')).toBe(false)
    // 数据匹配口径保留（白名单治理），但展示不再消费后端中文
    expect(source.includes("task.taskStatusName === '运行中'")).toBe(true)
  })

  it('MonacoEditor 死字段（中文标识符/写不读状态）不回流', () => {
    const source = read('src/components/tasks/MonacoEditor.vue')
    expect(source.includes('代码语法正确')).toBe(false)
    expect(source.includes('可以正常执行')).toBe(false)
    expect(source.includes('syntaxStatus')).toBe(false)
    expect(source.includes('executionStatus')).toBe(false)
  })
})

// ====================================================================
// E. 挂载冒烟（i18n 单例注入）
// ====================================================================

describe('P6-4a 组件挂载冒烟', () => {
  it('MonacoEditor 挂载不抛错（降级告警文案走键）', () => {
    const MonacoEditor = require('@/components/tasks/MonacoEditor.vue').default
    const wrapper = shallowMount(MonacoEditor, {
      localVue,
      i18n,
      propsData: { value: 'print(1)', language: 'python' },
      stubs: { 'el-skeleton': true, 'el-alert': true, 'el-input': true }
    })
    expect((wrapper.vm as any).loadError).toBe(false)
    wrapper.destroy()
  })
})
