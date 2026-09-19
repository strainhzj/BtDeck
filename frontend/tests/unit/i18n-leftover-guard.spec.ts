/**
 * 双语遗留审计门禁 + 遗留补译行为契约（2026-09-19 清扫批）。
 *
 * 背景：P1～P5 分批交付后，部分「已声明完成」的桌面面仍残留未译的**用户可见中文**
 * （壳层侧栏按钮、PWA 更新提示、主机能力面板、下载器控制台操作反馈、共享错误提取器、
 * 高级搜索请求构造校验、user store 抛出文案）——分批验收时未覆盖，属静默漏译。
 *
 * 本 spec 提供两类保护：
 * A. 审计门禁：对「已声明完成」的桌面面做机器扫描，**非注释/非 console 行**出现中文即红
 *    （白名单仅 6 条，逐条注明理由）。新增漏译会在此直接暴露，不再依赖人工发现。
 *    注：P6 计划内的文件（传统视图、孤儿文件、任务、Tracker 管理域、下载器各设置页签、
 *    全局替换弹窗、设置页 MCP/MoviePilot 页签、移动端页面）不在扫描集内——它们按计划
 *    尚未翻译，不属漏译。
 * B. 行为契约：锁定本批补译的共享层（错误提取、请求校验、同源校验）中英双语输出。
 */
import { readFileSync, existsSync, readdirSync, statSync } from 'fs'
import { join, resolve } from 'path'
import {
  extractErrorMessage,
  showErrorToast
} from '@/utils/formatters'
import {
  buildAdvancedSearchRequest,
  buildAdvancedSearchRequestFromTemplateGroups,
  assertSameDownloader
} from '@/views/torrents/utils/torrentBatch'
import i18n, { setLocale, translate } from '@/i18n'

// ====================================================================
// A. 审计门禁：已声明完成的桌面面不得残留用户可见中文
// ====================================================================

/** P1～P5 已声明完成的桌面面（P6 计划内文件有意不列入） */
const AUDITED_FILES = [
  'src/layout/components/Navbar/index.vue',
  'src/layout/components/Sidebar/index.vue',
  'src/layout/components/NotificationDrawer/index.vue',
  'src/layout/index.vue',
  'src/views/login/index.vue',
  'src/views/downloader/index.vue',
  'src/views/torrents/index.vue',
  'src/views/dashboard/index.vue',
  'src/views/query-templates/index.vue',
  'src/views/recycle-bin/index.vue',
  'src/views/torrents/components/TorrentAddDialog.vue',
  'src/views/torrents/components/TrackerOperationDialog.vue',
  'src/views/torrents/components/TrackerDetailCard.vue',
  'src/views/torrents/components/BatchOperationDialog.vue',
  'src/components/torrents/QuickDeleteDuplicatesDialog.vue',
  'src/components/torrents/AdvancedMultiSelect.vue',
  'src/components/torrents/AdvancedSearchBuilder.vue',
  'src/components/torrents/ConditionValueInput.vue',
  'src/components/torrents/PageSizeCombobox.vue',
  'src/components/BatchButton/index.vue',
  'src/components/common/RefreshPrompt.vue',
  'src/components/settings/PlatformCapabilityPanel.vue',
  'src/components/CollapsiblePanel.vue',
  'src/utils/formatters.ts',
  'src/utils/request.ts',
  'src/store/modules/user.ts',
  'src/store/modules/app.ts',
  'src/views/torrents/utils/torrentBatch.ts',
  'src/views/torrents/mixins/torrentBatch.ts',
  // P6-1（种子域收尾）新增扫描面
  'src/views/torrents/TraditionalView.vue',
  'src/views/torrents/components/TransferDialog.vue',
  'src/views/torrents/components/BatchTransferDialog.vue',
  'src/views/torrents/components/SetLocationDialog.vue',
  'src/views/torrents/FileManagement.vue',
  'src/views/torrents/components/GlobalReplaceTrackerDialog.vue'
]

/**
 * 白名单：允许出现中文的行（逐条注明理由）。匹配为「文件 + 行内容子串 + 理由」。
 * 任何未列入的命中都会使门禁失败——新增漏译必须走翻译键，而不是往这里加条目。
 */
const ALLOWLIST: Array<{ file: string, contains: string, reason: string }> = [
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: "{ label: '文件', value: 'files' }",
    reason: '内置页签默认 label 常量：展示经 trackerTabLabel 走 tracker.detail.files.tab 键本地化，'
      + '该常量仅在调用方自定义 tabs 时作为回退'
  },
  {
    file: 'src/components/torrents/AdvancedMultiSelect.vue',
    contains: "getLocale() === 'en' ? 'e.g. |,~,##' : '如: |,~,##'",
    reason: '分隔符示例按 locale 常量直出（含 | 与 ~ 字符，走 vue-i18n 会被复数分隔符解析破坏），本身即双语实现'
  },
  {
    file: 'src/utils/request.ts',
    contains: '刷新响应缺少 access_token',
    reason: '令牌刷新编排内部错误：仅在 request 层捕获后登出，不进入任何用户提示（用户可见文案走 errors/会话过期键）'
  },
  {
    file: 'src/views/torrents/utils/torrentBatch.ts',
    contains: "reason?.message ?? '操作失败'",
    reason: 'runBatchAction 的 errors 数组兜底：纯函数收集失败原因供调用方扩展，桌面批量开始/暂停/重检不展示该数组'
  },
  {
    file: 'src/views/torrents/utils/torrentBatch.ts',
    contains: "TRACKER_SUCCESS_VALUES = new Set(['工作中'",
    reason: '后端 Announce/Scrape 状态**数据值**匹配（非 UI 文案），翻译会破坏判定语义'
  },
  {
    file: 'src/views/torrents/utils/torrentBatch.ts',
    contains: "TRACKER_FAIL_VALUES = new Set(['工作失败'",
    reason: '同上：后端状态数据值集合（含 已禁用/超时/已清除），属判定口径而非展示文案'
  }
]

function isAllowlisted(file: string, line: string): boolean {
  return ALLOWLIST.some(entry => entry.file === file && line.includes(entry.contains))
}

/** 提取「非注释、非 console、非样式段」的行；返回违规行（含中文且不在白名单）。 */
function findChineseViolations(file: string): string[] {
  const absolute = resolve(__dirname, '../../', file)
  if (!existsSync(absolute)) return [`MISSING: ${file}`]
  const text = readFileSync(absolute, 'utf-8')
  // <style> 段可能含中文注释与字体名，不属用户可见文案
  const withoutStyles = text.replace(/<style[\s\S]*?<\/style>/g, '')
  const lines = withoutStyles.split('\n')
  const violations: string[] = []
  let inBlockComment = false
  let inHtmlComment = false
  let previousWasConsole = false

  lines.forEach((line, index) => {
    const trimmed = line.trim()
    if (inBlockComment) {
      if (line.includes('*/')) inBlockComment = false
      return
    }
    if (inHtmlComment) {
      if (line.includes('-->')) inHtmlComment = false
      return
    }
    if (trimmed.startsWith('/*')) {
      if (!trimmed.includes('*/')) inBlockComment = true
      return
    }
    if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('<!--')) {
      if (trimmed.startsWith('<!--') && !trimmed.includes('-->')) inHtmlComment = true
      return
    }
    if (/console\.(log|warn|error|info|debug)/.test(line)) {
      previousWasConsole = true
      return
    }
    // 多行 console 调用的后续参数行（格式串等）
    if (previousWasConsole) {
      previousWasConsole = false
      return
    }
    const code = line.replace(/\/\/.*$/, '')
    if (!/[\u4e00-\u9fff]/.test(code)) return
    const entry = `${file}:${index + 1} ${trimmed}`
    if (!isAllowlisted(file, trimmed)) violations.push(entry)
  })

  return violations
}

describe('双语遗留审计门禁（已声明完成的桌面面零漏译）', () => {
  it('扫描集中无未列入白名单的用户可见中文', () => {
    const violations = AUDITED_FILES.flatMap(findChineseViolations)
    expect(violations).toEqual([])
  })

  it('全仓 $t/translate 键在 zh 与 en 均可达（防键名笔误静默空串）', () => {
    // zh 缺键的行为是「返回空串 + warn 不渲染原始键」——静默失效，单测极易漏网：
    //  · P6-1 曾把 requestValidation 子树误嵌进 presets（parity 仍绿而键不可达）；
    //  · Navbar 曾用错前缀 `navbar.*`（实际 navigation.navbar.*）→ 壳层文案整片空串；
    //  · SizeRangeFilter 曾引用 search.sizeRange.unitPlaceholder（实际在 valueInput.*）。
    // 本门禁扫描全仓（不止审计集），键必须同时存在于 zh-CN 与 en；
    // 动态拼接键（`${` 或以 `.` 结尾的前缀）跳过——无法静态枚举。
    const root = resolve(__dirname, '../../src')
    const files: string[] = []
    const walk = (dir: string): void => {
      readdirSync(dir).forEach(name => {
        const p = join(dir, name)
        if (statSync(p).isDirectory()) walk(p)
        else if (/\.(vue|ts)$/.test(p)) files.push(p)
      })
    }
    walk(root)

    const keyPattern = /(?:\$t|translate|translateChoice)\(\s*'([^']+)'/g
    const missing: string[] = []
    const checked = new Set<string>()

    files.forEach(file => {
      const text = readFileSync(file, 'utf-8')
      let match: RegExpExecArray | null
      while ((match = keyPattern.exec(text)) !== null) {
        const key = match[1]
        if (key.includes('${') || key.endsWith('.') || checked.has(key)) continue
        checked.add(key)
        if (!i18n.te(key) || !i18n.te(key, 'en')) {
          missing.push(`${file.replace(root, 'src')} :: ${key}`)
        }
      }
    })

    expect(missing).toEqual([])
    // 防空转：确认确实扫到了键（当前约 1280 个）
    expect(checked.size).toBeGreaterThan(1000)
  })

  it('白名单条目均仍命中（防白名单腐化掩盖新漏译）', () => {
    const stale = ALLOWLIST.filter(entry => {
      const absolute = resolve(__dirname, '../../', entry.file)
      if (!existsSync(absolute)) return true
      return !readFileSync(absolute, 'utf-8').includes(entry.contains)
    })
    expect(stale.map(e => `${e.file} :: ${e.contains}`)).toEqual([])
  })
})

// ====================================================================
// B. 遗留补译行为契约
// ====================================================================

describe('遗留补译 - extractErrorMessage 双语', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：HTTP 状态码/网络/未知兜底走 errors 键（与原内联逐字节一致）', () => {
    setLocale('zh-CN')
    expect(extractErrorMessage({ response: { status: 500 } })).toBe('服务器内部错误')
    expect(extractErrorMessage({ response: { status: 403 } })).toBe('无权限访问')
    expect(extractErrorMessage({ response: { status: 418 } })).toBe('请求失败 (418)')
    expect(extractErrorMessage({ request: {} })).toBe('网络连接失败，请检查网络设置')
    expect(extractErrorMessage(null)).toBe('未知错误')
  })

  it('en：同一输入输出英文（HTTP 表/回退/网络/未知）', () => {
    setLocale('en')
    expect(extractErrorMessage({ response: { status: 500 } })).toBe('Internal server error')
    expect(extractErrorMessage({ response: { status: 418 } })).toBe('Request failed (418)')
    expect(extractErrorMessage({ request: {} })).toBe('Network connection failed. Please check your network settings.')
    expect(extractErrorMessage(null)).toBe('Unknown error')
  })

  it('后端 msg/message 原文透传（契约化路径由 apiErrorMessage 按 reasonCode 本地化）', () => {
    setLocale('en')
    expect(extractErrorMessage({ response: { status: 500, data: { msg: '后端原文' } } })).toBe('后端原文')
    expect(extractErrorMessage({ response: { status: 500, data: { message: 'raw text' } } })).toBe('raw text')
  })
})

describe('遗留补译 - showErrorToast 上下文拼接双语', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh 保持「{context}失败：{message}」原样', () => {
    setLocale('zh-CN')
    expect(showErrorToast(new Error('连接失败'), '默认值', '刷新')).toBe('刷新失败：连接失败')
  })

  it('en 输出「{context} failed: {message}」', () => {
    setLocale('en')
    expect(showErrorToast(new Error('boom'), 'fallback', 'Refresh')).toBe('Refresh failed: boom')
  })

  it('无 context 时原样返回；空消息走 generic 兜底', () => {
    setLocale('zh-CN')
    expect(showErrorToast(new Error('直接消息'))).toBe('直接消息')
    expect(showErrorToast(undefined)).toBe('未知错误')
  })
})

describe('遗留补译 - 高级搜索请求构造校验双语', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh：逐字节保持原内联校验文案', () => {
    setLocale('zh-CN')
    expect(buildAdvancedSearchRequest({}, 'added_date', 20).error).toBe('搜索条件必须是JSON字符串')
    expect(buildAdvancedSearchRequest({ groups: '{bad' }, 'added_date', 20).error).toBe('搜索条件不是有效JSON')
    expect(
      buildAdvancedSearchRequest({ groups: JSON.stringify([{ logic: 'and', conditions: [] }]) }, 'added_date', 20).error
    ).toBe('条件组1至少需要一个条件')
    expect(
      buildAdvancedSearchRequest({
        groups: JSON.stringify([{ logic: 'and', conditions: [{ field: 'name', operator: 'eq' }] }])
      }, 'added_date', 20).error
    ).toBe('条件组1第1项缺少值')
    expect(
      buildAdvancedSearchRequest({
        groups: JSON.stringify([{ logic: 'and', conditions: [{ field: 'name', operator: 'eq', value: 'x' }] },
          { logic: 'and', conditions: [{ field: 'name', operator: 'eq', value: 'y' }] }]),
        between_group_logics: JSON.stringify([])
      }, 'added_date', 20).error
    ).toBe('组间逻辑数量必须等于条件组数量减一')
  })

  it('en：同输入输出英文（含条件组/项编号插值）', () => {
    setLocale('en')
    expect(buildAdvancedSearchRequest({}, 'added_date', 20).error).toBe('search conditions must be a JSON string')
    expect(
      buildAdvancedSearchRequest({ groups: JSON.stringify([{ logic: 'and', conditions: [] }]) }, 'added_date', 20).error
    ).toBe('Condition group 1 needs at least one condition')
    expect(
      buildAdvancedSearchRequest({
        groups: JSON.stringify([{ logic: 'and', conditions: [{ field: 'name', operator: 'eq' }] }])
      }, 'added_date', 20).error
    ).toBe('Item 1 of condition group 1 is missing a value')
  })

  it('模板分支校验双语 + 未知字段插值', () => {
    setLocale('zh-CN')
    const zh = buildAdvancedSearchRequestFromTemplateGroups([
      { id: 'g1', logic: 'and', betweenGroupLogic: undefined, conditions: [] }
    ] as never, 'added_date')
    expect(zh.error).toBe('模板条件组1没有条件')

    setLocale('en')
    const en = buildAdvancedSearchRequestFromTemplateGroups([
      { id: 'g1', logic: 'and', betweenGroupLogic: undefined, conditions: [] }
    ] as never, 'added_date')
    expect(en.error).toBe('Template condition group 1 has no conditions')
  })

  it('成功路径不因翻译改变请求体（T01 参数不变性回归）', () => {
    setLocale('en')
    const params = {
      groups: JSON.stringify([{ logic: 'and', conditions: [{ field: 'name', operator: 'eq', value: 'x' }] }])
    }
    const enRequest = buildAdvancedSearchRequest(params, 'added_date', 20).request
    setLocale('zh-CN')
    const zhRequest = buildAdvancedSearchRequest(params, 'added_date', 20).request
    expect(enRequest).toEqual(zhRequest)
  })
})

describe('遗留补译 - assertSameDownloader 双语', () => {
  afterEach(() => setLocale('zh-CN'))

  it('zh 与原内联一致，en 输出英文（消费方 TraditionalView 直接展示 reason）', () => {
    setLocale('zh-CN')
    expect(assertSameDownloader([{ downloader_id: '' }]).reason).toBe('选中种子缺少下载器信息，请刷新后重试')
    expect(
      assertSameDownloader([{ downloader_id: 'a' }, { downloader_id: 'b' }]).reason
    ).toBe('选中的种子必须属于同一下载器')

    setLocale('en')
    expect(assertSameDownloader([{ downloader_id: '' }]).reason).toBe(translate('torrent.msg.missingDownloader'))
    expect(assertSameDownloader([{ downloader_id: 'a' }, { downloader_id: 'b' }]).reason)
      .not.toMatch(/[\u4e00-\u9fff]/)
    expect(assertSameDownloader([{ downloader_id: 'a' }]).ok).toBe(true)
  })
})

describe('遗留补译 - 源码契约（壳层/控制台/store 走 i18n 键）', () => {
  const read = (file: string): string => readFileSync(resolve(__dirname, '../../', file), 'utf-8')

  it('Sidebar：移动版入口与折叠按钮 aria/文案全部走键', () => {
    const src = read('src/layout/components/Sidebar/index.vue')
    expect(src).toContain("$t('navigation.sidebar.switchToMobile')")
    expect(src).toContain("$t('navigation.sidebar.mobileEntry')")
    expect(src).toContain("$t('navigation.sidebar.expand')")
    expect(src).toContain("$t('navigation.sidebar.collapse')")
    expect(src).not.toContain('aria-label="切换到移动版"')
  })

  it('RefreshPrompt：PWA 三条文案走 common.pwa 键', () => {
    const src = read('src/components/common/RefreshPrompt.vue')
    expect(src).toContain("$t('common.pwa.found')")
    expect(src).toContain("$t('common.pwa.refresh')")
    expect(src).toContain("$t('common.pwa.dismiss')")
  })

  it('PlatformCapabilityPanel：面板文案走 settings.capability 键，服务端 note 原文透传', () => {
    const src = read('src/components/settings/PlatformCapabilityPanel.vue')
    expect(src).toContain("$t('settings.capability.title')")
    expect(src).toContain("$t('settings.capability.levelUnsupported')")
    expect(src).toContain("$t('settings.capability.platformAndroidServer')")
    // 服务端下发的能力 label/note 必须原样透传（E03 语义）
    expect(src).toContain('{{ row.note }}')
    expect(src).toContain('{{ row.label }}')
  })

  it('downloader 控制台：操作反馈走 downloader.msg 键，禁 response.msg 中文兜底', () => {
    const src = read('src/views/downloader/index.vue')
    expect(src).toContain("$t('downloader.msg.testFailed')")
    expect(src).toContain("$t('downloader.msg.syncStarted'")
    expect(src).toContain("$t('downloader.msg.toggleFailedRolledBack')")
    expect(src).toContain("$t('downloader.msg.deleteConfirm'")
    expect(src).not.toContain("|| '测试连接失败'")
    expect(src).not.toContain("Message.error('删除失败')")
  })

  it('user store：Login/GetUserInfo 抛出文案走 auth 键', () => {
    const src = read('src/store/modules/user.ts')
    expect(src).toContain("import { translate } from '@/i18n'")
    expect(src).toContain("translate('auth.noAccessToken')")
    expect(src).toContain("translate('auth.tokenEmpty')")
    expect(src).toContain("translate('auth.getUserInfoFailed')")
    expect(src).toContain("translate('auth.getUserInfoFailedRelogin')")
  })

  it('formatters：错误提取走 errors 键（HTTP 表/网络/未知/上下文）', () => {
    const src = read('src/utils/formatters.ts')
    expect(src).toContain("translate('errors.unknown')")
    expect(src).toContain('errors.http.')
    expect(src).toContain("translate('errors.httpFallback'")
    expect(src).toContain("translate('errors.network.checkSettings')")
    expect(src).toContain("translate('errors.contextFailed'")
    expect(src).not.toContain('网络连接失败，请检查网络设置')
  })
})
