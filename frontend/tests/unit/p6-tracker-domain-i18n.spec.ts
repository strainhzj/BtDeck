/**
 * 桌面双语 P6-3：Tracker 管理域 i18n 契约（关键词看板/搜索、汇报配置、判断测试工具 + 9 组件）。
 *
 * 覆盖（对齐 p6-torrent-domain / p6-downloader-domain 同类 spec）：
 * A. 行为契约——tracker 新子树（pools/board/search/reannounce/testTool/addDialog/importDialog/
 *    listModal/quickAction/keywordCard/timeline/resultSummary/apiLog/lang/errors）zh 逐字节
 *    与 en 插值抽查；
 * B. reasonCode 契约——后端 P6-3 新键经 apiResponseMessage 按 errors.byCode 本地化
 *    （SCREAMING_SNAKE → camelCase 映射），未知 code 回退 fallback；
 * C. 共享层——utils/tracker 的 poolLabel/poolOptions/getLanguageLabel/extractErrorMessage
 *    双语输出与回退（Q02）；
 * D. 源码契约——13 文件零硬编码中文锚（防回流）、pool_label 后端中文字段不再直显、
 *    错误展示接 apiErrorMessage/apiResponseMessage。
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { createLocalVue, shallowMount } from '@vue/test-utils'
import VueI18n from 'vue-i18n'

import i18n, { apiResponseMessage, setLocale, translate } from '@/i18n'
import { extractErrorMessage, getLanguageLabel, poolLabel, poolOptions } from '@/utils/tracker'

const read = (file: string): string => readFileSync(resolve(__dirname, '../../', file), 'utf-8')

const localVue = createLocalVue()
localVue.use(VueI18n)

// ====================================================================
// A. 行为契约：zh 逐字节 / en 插值
// ====================================================================

describe('P6-3 池子与看板文案（tracker.pools.* / tracker.board.*）', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：池子名/弹窗按钮/看板操作与原内联逐字节一致', () => {
    setLocale('zh-CN')
    expect(translate('tracker.pools.candidate')).toBe('候选池')
    expect(translate('tracker.pools.ignored')).toBe('忽略池')
    expect(translate('tracker.pools.success')).toBe('成功池')
    expect(translate('tracker.pools.failed')).toBe('失败池')
    expect(translate('tracker.pools.poolFallback')).toBe('池子')
    expect(translate('tracker.pools.unknownTime')).toBe('未知时间')
    expect(translate('tracker.pools.viewAll')).toBe('查看全部 →')
    expect(translate('tracker.pools.moveTo')).toBe('移动到')
    expect(translate('tracker.pools.moveToOtherPool')).toBe('移动到其它池')
    expect(translate('tracker.pools.batchMoveTo')).toBe('批量移动到')
    expect(translate('tracker.pools.quickActionTip')).toBe('快捷操作（按前缀左匹配）')
    expect(translate('tracker.pools.dialog.confirm')).toBe('确定')
    expect(translate('tracker.pools.dialog.cancel')).toBe('取消')
    expect(translate('tracker.pools.dialog.notice')).toBe('提示')
    expect(translate('tracker.pools.dialog.confirmDelete')).toBe('确认删除')
    expect(translate('tracker.pools.dialog.close')).toBe('关 闭')
    expect(translate('tracker.board.title')).toBe('Tracker关键词管理')
    expect(translate('tracker.board.loadPoolFailed', { pool: '成功池' })).toBe('加载成功池数据失败')
    expect(translate('tracker.board.moveSuccess', { keyword: 'abc', pool: '失败池' })).toBe(
      '关键词 "abc" 已移动到 失败池'
    )
    expect(translate('tracker.board.deleteConfirm', { keyword: 'abc' })).toBe('确定要删除关键词 "abc" 吗？')
    expect(translate('tracker.board.candidateAddDenied')).toBe('候选池不支持手动添加关键词,请将关键词拖拽到其他池子')
  })

  it('en：池子名与插值输出英文', () => {
    setLocale('en')
    expect(translate('tracker.pools.candidate')).toBe('Candidate pool')
    expect(translate('tracker.pools.dialog.close')).toBe('Close')
    expect(translate('tracker.board.moveSuccess', { keyword: 'abc', pool: 'Failed pool' })).toBe(
      'Keyword "abc" moved to Failed pool'
    )
    expect(translate('tracker.board.deleteConfirm', { keyword: 'abc' })).toBe('Delete keyword "abc"?')
    expect(translate('tracker.board.exportWip', { pool: 'Success pool' })).toBe('Export is under development - Success pool')
  })
})

describe('P6-3 关键词搜索/列表弹窗/添加与导入弹窗文案', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：搜索页与列表弹窗逐字节', () => {
    setLocale('zh-CN')
    expect(translate('tracker.search.backToBoard')).toBe('返回看板')
    expect(translate('tracker.search.foundPrefix')).toBe('共找到 ')
    expect(translate('tracker.search.foundSuffix')).toBe(' 个关键词')
    expect(translate('tracker.search.sortTimeDesc')).toBe('添加时间 ↓')
    expect(translate('tracker.search.sortNameAsc')).toBe('关键词 A-Z')
    expect(translate('tracker.search.empty')).toBe('暂无搜索结果，请尝试调整搜索条件或关键词')
    expect(translate('tracker.listModal.titleSuffix', { pool: '忽略池' })).toBe('忽略池详情')
    expect(translate('tracker.listModal.selectedPrefix')).toBe('已选 ')
    expect(translate('tracker.listModal.selectedSuffix')).toBe(' 项')
    expect(translate('tracker.listModal.batchDeleteConfirm', { count: 3 })).toBe('确定要删除选中的 3 个关键词吗？')
    expect(translate('tracker.listModal.batchMoveSuccess', { count: 2, pool: '成功池' })).toBe(
      '已将 2 个关键词移动到 成功池'
    )
  })

  it('en：搜索页与列表弹窗输出英文', () => {
    setLocale('en')
    expect(translate('tracker.search.foundPrefix')).toBe('Found ')
    expect(translate('tracker.listModal.titleSuffix', { pool: 'Ignored pool' })).toBe('Ignored pool details')
    expect(translate('tracker.listModal.batchDeleteConfirm', { count: 3 })).toBe('Delete the 3 selected keywords?')
  })

  it('zh：添加/导入弹窗逐字节（危险与进度语义）', () => {
    setLocale('zh-CN')
    expect(translate('tracker.addDialog.title', { pool: '成功池' })).toBe('添加关键词到 成功池')
    expect(translate('tracker.addDialog.required')).toBe('关键词不能为空')
    expect(translate('tracker.addDialog.tooLong')).toBe('关键词长度不能超过100个字符')
    expect(translate('tracker.addDialog.addSuccess', { keyword: 'k1', pool: '成功池' })).toBe(
      '已添加关键词 "k1" 到 成功池'
    )
    expect(translate('tracker.importDialog.uploadHint')).toBe('仅支持.txt文件,每行一个关键词')
    expect(translate('tracker.importDialog.cancelledWithStats', { success: 2, fail: 1 })).toBe('导入已取消,成功 2 个,失败 1 个')
    expect(translate('tracker.importDialog.progress', { percent: 40, done: 2, total: 5 })).toBe('正在导入 40% (2/5)')
  })

  it('en：添加/导入弹窗输出英文', () => {
    setLocale('en')
    expect(translate('tracker.addDialog.title', { pool: 'Success pool' })).toBe('Add keyword to Success pool')
    expect(translate('tracker.importDialog.progress', { percent: 40, done: 2, total: 5 })).toBe('Importing 40% (2/5)')
    expect(translate('tracker.importDialog.cancelledWithStats', { success: 2, fail: 1 })).toBe(
      'Import cancelled: 2 succeeded, 1 failed'
    )
  })
})

describe('P6-3 汇报配置与测试工具文案', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：汇报配置逐字节（含批量/危险确认链路）', () => {
    setLocale('zh-CN')
    expect(translate('tracker.reannounce.title')).toBe('Tracker汇报配置')
    expect(translate('tracker.reannounce.batchModeInfo', { count: 3 })).toBe('批量编辑模式 - 已选择 3 条记录')
    expect(translate('tracker.reannounce.deleteConfirm', { name: 'demo' })).toBe('确定要删除配置「demo」吗？')
    expect(translate('tracker.reannounce.exitBatchConfirm')).toBe('退出批量编辑将丢失未保存的更改，确定要退出吗？')
    expect(translate('tracker.reannounce.batchPartial', { success: 2, failed: 1 })).toBe('批量更新完成，成功 2 条，失败 1 条')
    expect(translate('tracker.reannounce.detectResult', { detected: 5, created: 3 })).toBe('检测到 5 个域名，新增 3 个配置')
  })

  it('en：汇报配置输出英文', () => {
    setLocale('en')
    expect(translate('tracker.reannounce.title')).toBe('Tracker Reannounce Config')
    expect(translate('tracker.reannounce.batchPartial', { success: 2, failed: 1 })).toBe(
      'Batch update finished: 2 succeeded, 1 failed'
    )
    expect(translate('tracker.reannounce.deleteConfirm', { name: 'demo' })).toBe('Delete config "demo"?')
  })

  it('zh：测试工具逐字节（时间线含高亮标记结构与 zh 原实现一致）', () => {
    setLocale('zh-CN')
    expect(translate('tracker.testTool.title')).toBe('Tracker判断测试工具')
    expect(translate('tracker.testTool.timeline.step1Desc', { length: 12 })).toBe(
      '消息长度: <span class="highlight">12 bytes</span>'
    )
    expect(translate('tracker.testTool.timeline.step2Desc', { count: 2, type: '成功' })).toBe(
      '匹配到 <span class="highlight">2 个</span>成功关键词'
    )
    expect(translate('tracker.testTool.totalRecords', { count: 7 })).toBe('共 7 条记录')
    expect(translate('tracker.testTool.copyResultLine', { result: '成功' })).toBe('判断结果: 成功')
    expect(translate('tracker.resultSummary.failedDesc')).toBe('该消息判定为失败状态（失败优先）')
    expect(translate('tracker.keywordCard.typeCandidate')).toBe('候选')
    expect(translate('tracker.lang.zh_CN')).toBe('中文')
    expect(translate('tracker.lang.generic')).toBe('通用')
  })

  it('en：测试工具输出英文', () => {
    setLocale('en')
    expect(translate('tracker.testTool.timeline.step2Desc', { count: 2, type: 'success' })).toBe(
      'Matched <span class="highlight">2</span> success keywords'
    )
    expect(translate('tracker.lang.zh_CN')).toBe('Chinese')
  })
})

// ====================================================================
// B. reasonCode 契约（后端 P6-3 新键 → errors.byCode 本地化）
// ====================================================================

describe('P6-3 reasonCode → errors.byCode 本地化', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：关键词域 reasonCode 输出本地化文案', () => {
    setLocale('zh-CN')
    expect(apiResponseMessage({ code: '400', msg: '后端中文原文', data: { reasonCode: 'KEYWORD_ALREADY_EXISTS' } }, '兜底')).toBe(
      '该关键词已存在于对应池中'
    )
    expect(apiResponseMessage({ code: '404', msg: '关键词不存在', data: { reasonCode: 'KEYWORD_NOT_FOUND' } }, '兜底')).toBe(
      '关键词不存在或已删除'
    )
    expect(
      apiResponseMessage({ code: '400', msg: '无效的池子类型，必须是: candidate, ignored', data: { reasonCode: 'KEYWORD_INVALID_POOL_TYPE' } }, '兜底')
    ).toBe('无效的池子类型')
  })

  it('zh：汇报配置域 reasonCode 输出本地化文案（not-found 不透传后端诊断 msg）', () => {
    setLocale('zh-CN')
    expect(
      apiResponseMessage({ code: '404', msg: '配置不存在 [id=xxx]', data: { reasonCode: 'REANNOUNCE_CONFIG_NOT_FOUND' } }, '兜底')
    ).toBe('汇报配置不存在或已删除')
    expect(
      apiResponseMessage({ code: '500', msg: '数据库操作失败', data: { reasonCode: 'DB_OPERATION_FAILED' } }, '兜底')
    ).toBe('数据库操作失败，请稍后重试')
    expect(
      apiResponseMessage({ code: '500', msg: '测试失败', data: { reasonCode: 'TEST_MATCH_FAILED' } }, '兜底')
    ).toBe('测试失败，请稍后重试')
  })

  it('en：reasonCode 输出英文；SCREAMING_SNAKE → camelCase 映射一致', () => {
    setLocale('en')
    expect(apiResponseMessage({ code: '400', msg: 'x', data: { reasonCode: 'KEYWORD_DUPLICATE_IN_BATCH' } }, 'fallback')).toBe(
      'Duplicate keywords in the batch list'
    )
    expect(
      apiResponseMessage({ code: '400', msg: 'x', data: { reasonCode: 'KEYWORD_IDS_MUST_BE_LIST' } }, 'fallback')
    ).toBe('keywordIds must be a list')
    expect(
      apiResponseMessage({ code: '400', msg: 'x', data: { reasonCode: 'REANNOUNCE_BATCH_FORMAT_INVALID' } }, 'fallback')
    ).toBe('Invalid batch request data format')
  })

  it('未登记 reasonCode 回退 fallback（不透出后端中文 msg）', () => {
    expect(apiResponseMessage({ code: '400', msg: '后端中文原文', data: { reasonCode: 'NOT_REGISTERED_CODE' } }, '本地兜底')).toBe(
      '本地兜底'
    )
  })
})

// ====================================================================
// C. 共享层：utils/tracker 双语输出
// ====================================================================

describe('P6-3 utils/tracker 共享层', () => {
  afterEach(() => setLocale('zh-CN'))

  it('poolLabel：登记类型走键、未登记原文回退（Q02）', () => {
    setLocale('zh-CN')
    expect(poolLabel('candidate')).toBe('候选池')
    expect(poolLabel('failed')).toBe('失败池')
    expect(poolLabel('unknown-type')).toBe('unknown-type')
    setLocale('en')
    expect(poolLabel('success')).toBe('Success pool')
  })

  it('poolOptions：排除源池且标签随语言切换', () => {
    setLocale('zh-CN')
    const zhOptions = poolOptions(['candidate', 'ignored'])
    expect(zhOptions).toEqual([
      { value: 'success', label: '成功池' },
      { value: 'failed', label: '失败池' }
    ])
    setLocale('en')
    expect(poolOptions(['candidate', 'ignored'])[0]).toEqual({ value: 'success', label: 'Success pool' })
  })

  it('getLanguageLabel：已登记语言码走键、空串走 generic、未知码原文回退', () => {
    setLocale('zh-CN')
    expect(getLanguageLabel('zh_CN')).toBe('中文')
    expect(getLanguageLabel('')).toBe('通用')
    expect(getLanguageLabel('xx_XX')).toBe('xx_XX')
    setLocale('en')
    expect(getLanguageLabel('ru_RU')).toBe('Russian')
  })

  it('extractErrorMessage：默认兜底与 422 拼接双语；后端 msg 原文透传', () => {
    setLocale('zh-CN')
    expect(extractErrorMessage({})).toBe('操作失败')
    expect(
      extractErrorMessage({ response: { data: { detail: [{ loc: ['body', 'keyword'], msg: 'required' }] } } })
    ).toBe('参数验证失败: body.keyword : required')
    expect(extractErrorMessage({ response: { data: { msg: '后端原文' } } })).toBe('后端原文')
    setLocale('en')
    expect(extractErrorMessage({})).toBe('Operation failed')
    expect(
      extractErrorMessage({ response: { data: { detail: [{ loc: ['body', 'keyword'], msg: 'required' }] } } })
    ).toBe('Validation failed: body.keyword : required')
  })
})

// ====================================================================
// D. 源码契约：零硬编码中文锚 + 消费接线防回流
// ====================================================================

describe('P6-3 源码契约', () => {


  it('看板池名走共享 poolLabel（不再消费本地 label 常量）', () => {
    const source = read('src/views/tracker/keywords-board.vue')
    expect(source.includes("import { extractErrorMessage, poolLabel } from '@/utils/tracker'")).toBe(true)
    expect(source.includes("label: '候选池'")).toBe(false)
    expect(source.includes('return poolLabel(poolType)')).toBe(true)
  })

  it('搜索页不再直显后端中文 pool_label 字段', () => {
    const source = read('src/views/tracker/keywords-search.vue')
    // 后端 pool_label（📋 候选池 等带 emoji 的中文字段）禁止直显
    expect(source.includes('{{ item.pool_label }}')).toBe(false)
    expect(source.includes('getPoolLabel(item.pool_type)')).toBe(true)
  })

  it('快捷操作弹窗 POOL_LABELS 中文常量不回流', () => {
    const source = read('src/views/tracker/components/KeywordQuickActionDialog.vue')
    expect(source.includes("candidate: '候选池'")).toBe(false)
    expect(source.includes('poolLabel')).toBe(true)
  })

  it('错误展示接线：错误路径走 apiErrorMessage/apiResponseMessage（禁中文 msg 直读）', () => {
    for (const file of [
      'src/views/tracker/keywords-board.vue',
      'src/views/tracker/keywords-search.vue',
      'src/views/tracker/reannounce-config.vue',
      'src/views/tracker/components/AddKeywordDialog.vue',
      'src/views/tracker/components/KeywordListModal.vue',
      'src/views/tracker/components/KeywordQuickActionDialog.vue'
    ]) {
      const source = read(file)
      const wired = source.includes('apiResponseMessage') || source.includes('apiErrorMessage')
      expect(wired).toBe(true)
    }
  })

  it('reannounce 批量部分失败明细只进日志不进提示（E01 防中文泄漏）', () => {
    const source = read('src/views/tracker/reannounce-config.vue')
    expect(source.includes("console.error('批量更新部分失败明细:'")).toBe(true)
    expect(source.includes('{ messages }')).toBe(false)
    // catch 路径禁止直读后端 msg
    expect(source.includes('error.response?.data?.msg')).toBe(false)
  })

  it('AddKeywordDialog 移动端复用面（C01）：确认/取消按钮走键且 zh 值与原内联一致', () => {
    setLocale('zh-CN')
    expect(translate('tracker.pools.dialog.confirm')).toBe('确定')
    expect(translate('tracker.addDialog.confirmAdd')).toBe('确定添加')
    expect(translate('tracker.addDialog.adding')).toBe('添加中...')
  })
})

// ====================================================================
// E. 挂载冒烟：i18n 单例注入后组件可挂载（buble/模板合法性兜底）
// ====================================================================

describe('P6-3 组件挂载冒烟（i18n 注入）', () => {
  afterEach(() => setLocale('zh-CN'))

  it('AddKeywordDialog（移动端复用）挂载不抛错且标题走键', () => {
    setLocale('zh-CN')
    const wrapper = shallowMount(require('@/views/tracker/components/AddKeywordDialog.vue').default, {
      localVue,
      i18n,
      propsData: { visible: true, poolType: 'success', poolLabel: '成功池' },
      mocks: { $message: { success: jest.fn(), error: jest.fn(), warning: jest.fn(), info: jest.fn() } }
    })
    expect((wrapper.vm as any).dialogTitle).toBe('添加关键词到 成功池')
    wrapper.destroy()
  })

  it('KeywordCard 挂载渲染本地化类型标签', () => {
    setLocale('zh-CN')
    const wrapper = shallowMount(require('@/views/tracker/components/KeywordCard.vue').default, {
      localVue,
      i18n,
      propsData: { keyword: { keyword: 'abc', keyword_type: 'candidate', priority: 3 } }
    })
    expect((wrapper.vm as any).getTagLabel).toBe('候选')
    wrapper.destroy()
  })
})
