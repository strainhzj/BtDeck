/**
 * 双语遗留审计门禁 + 遗留补译行为契约（2026-09-19 清扫批；P6-5 翻转为全桌面负向排除）。
 *
 * 背景：P1～P5 分批交付后，部分「已声明完成」的桌面面仍残留未译的**用户可见中文**
 * （壳层侧栏按钮、PWA 更新提示、主机能力面板、下载器控制台操作反馈、共享错误提取器、
 * 高级搜索请求构造校验、user store 抛出文案）——分批验收时未覆盖，属静默漏译。
 *
 * 本 spec 提供两类保护：
 * A. 审计门禁（P6-5 起为**负向排除**）：扫描全部桌面 src（除下方排除清单），
 *    **非注释/非 console 行**出现中文即红；白名单逐条注明理由。
 *    P6 收口前审计集是正向清单（65 面），新增文件忘登记就漏拦——P6-5 翻转后
 *    新建桌面文件默认入扫描，无需登记。
 *    排除范围（每项附理由）：移动端页面（C01：移动保持中文，另立项）、i18n 语言包
 *    （zh-CN 本体）、vue-element-admin 模板残留（nested/tree，未路由）、demo 模式
 *    （P0 定为另立项未确认）、后端生成契约（*.generated.ts，禁直改）、同目录测试。
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

/**
 * P6-5：负向排除扫描集——扫描全部桌面 src，仅排除下列范围（逐项附理由）。
 * 翻转前为正向 65 面清单（P1～P6 分批登记），新文件漏登记即漏拦。
 */
const EXCLUDED_DIRS: Array<{ dir: string, reason: string }> = [
  { dir: 'src/views/mobile', reason: '移动端 /m/* 保持中文（主计划 C01：不要求移动全英文，另立项）' },
  { dir: 'src/layout/mobile', reason: '移动版壳层（MobileLayout：底 Tab/抽屉菜单），同上属移动范围' },
  { dir: 'src/i18n', reason: '语言包本体（zh-CN 文案即数据）' },
  { dir: 'src/views/nested', reason: 'vue-element-admin 模板残留，未在路由表登记' },
  { dir: 'src/views/tree', reason: '同上：模板残留' },
  { dir: 'src/demo', reason: 'Demo 模式数据/编排（P0 定为另立项未确认范围；壳层横幅已单独双语）' }
]

const EXCLUDED_FILE_PATTERNS: Array<{ pattern: RegExp, reason: string }> = [
  { pattern: /\.generated\.ts$/, reason: '后端生成契约（禁直改；展示层按稳定值双取 label/labelEn）' },
  { pattern: /__tests__\//, reason: '同目录测试（非运行时代码）' },
  // v1.0.7 合入（dev1.0.7）的 MCP/MoviePilot 新功能面：dev1.0.7 双语线仅到 P1，
  // 这些文件整体为中文硬编码，双语化另立项（见 PLANS/merge-dev107-into-dev.md §8）。
  // 注意：settings/index.vue 主体是 dev P6 双语成果，禁整文件排除，仅页签 label 走白名单。
  { pattern: /^src\/api\/(mcp-settings|moviepilot)\.ts$/, reason: 'MCP/MoviePilot API 层：后端契约错误文案，随端点双语化另立项' },
  { pattern: /^src\/views\/settings\/components\/(McpSettingsPanel|MoviePilotPanel)\.vue$/, reason: 'MCP/MoviePilot 设置面板：v1.0.7 新功能面，双语另立项' }
]

/** 收集扫描集：全部桌面 src 下 .vue/.ts，减去排除范围 */
function collectAuditedFiles(): string[] {
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
  return files
    .map(p => p.replace(root, 'src'))
    .filter(file => {
      if (EXCLUDED_DIRS.some(e => file.startsWith(e.dir + '/'))) return false
      if (EXCLUDED_FILE_PATTERNS.some(e => e.pattern.test(file))) return false
      return true
    })
}

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
  },
  {
    file: 'src/utils/tracker.ts',
    contains: "throw new Error('JSON格式不正确')",
    reason: 'parseJSON 内部异常消息：调用方（test.vue 历史加载）捕获后仅进日志，不进入任何用户提示'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "task.taskStatusName === '运行中' || task.taskStatusName === '空闲'",
    reason: '后端 taskStatusName 中文值**数据匹配**（可执行性判定口径，非展示文案）；'
      + '展示已按 taskStatus 稳定码位走 tasks.status.* 键'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "task.taskStatusName === '已暂停'",
    reason: '同上：后端状态名数据匹配（isTaskInterruptible 口径）'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "task.taskStatusName === '失败' || task.taskStatusName === '已完成'",
    reason: '同上：后端状态名数据匹配'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "'等待运行': 'info',",
    reason: '状态名→el-tag 类型映射的**键**为后端中文状态名（数据值匹配），值是颜色非文案；'
      + '展示走 getStatusName 码位键'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "'运行中': 'success',",
    reason: '同上：状态名数据键映射'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "'空闲': 'info',",
    reason: '同上：状态名数据键映射'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "'已暂停': 'warning',",
    reason: '同上：状态名数据键映射'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "'已停止': 'info',",
    reason: '同上：状态名数据键映射'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "'已完成': 'success',",
    reason: '同上：状态名数据键映射'
  },
  {
    file: 'src/views/tasks/index.vue',
    contains: "'失败': 'danger'",
    reason: '同上：状态名数据键映射（map 末项，无尾逗号形态）'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: 'value="基础"',
    reason: '筛选 value 为模板 category 中文数据值（匹配语义），label 已走 tasks.cronEditor.category.* 键'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: 'value="小时"',
    reason: '同上：category 数据值'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: 'value="日常"',
    reason: '同上：category 数据值'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: 'value="工作日"',
    reason: '同上：category 数据值'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: 'value="周末"',
    reason: '同上：category 数据值'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "category: '基础'",
    reason: '内置模板 category 中文数据值（筛选匹配 + CSS 类名 template-category-* + tag 类型映射），'
      + '名称/描述展示已走 templates.* 键（key 身份）'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "category: '小时'",
    reason: '同上：category 数据值'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "category: '日常'",
    reason: '同上：category 数据值'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "category: '工作日'",
    reason: '同上：category 数据值'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "category: '周末'",
    reason: '同上：category 数据值'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "'基础': 'primary'",
    reason: 'category→el-tag 类型映射键（数据值匹配），值是类型非文案'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "'小时': 'success'",
    reason: '同上：category 数据键映射'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "'日常': 'info'",
    reason: '同上：category 数据键映射'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "'工作日': 'warning'",
    reason: '同上：category 数据键映射'
  },
  {
    file: 'src/components/tasks/CronEditor.vue',
    contains: "'周末': 'danger'",
    reason: '同上：category 数据键映射'
  },
  {
    file: 'src/components/tasks/PythonClassSelector.vue',
    contains: "'备份': 'warning'",
    reason: '类目→el-tag 类型映射键（后端历史 category 中文数据值），值是颜色非文案；'
      + '预定义类列表已改由后端 type-config 驱动（描述 Q02 原文透传）'
  },
  {
    file: 'src/components/tasks/PythonClassSelector.vue',
    contains: "'自定义': 'primary'",
    reason: '同上：类目数据键映射（map 末项）'
  },
  {
    file: 'src/components/tasks/PythonClassSelector.vue',
    contains: "'清理': 'info'",
    reason: '同上：类目数据键映射'
  },
  {
    file: 'src/components/tasks/PythonClassSelector.vue',
    contains: "'同步': 'success'",
    reason: '同上：类目数据键映射'
  },
  {
    file: 'src/components/tasks/PythonClassSelector.vue',
    contains: "'监控': 'danger'",
    reason: '同上：类目数据键映射'
  },
  // ============ P6-5 翻转新增：数据身份 / 范围外登记 ============
  {
    file: 'src/router.ts',
    contains: "title: '",
    reason: '路由 meta.title 为 zh 数据身份（P1 titleKey 方案：resolvePageTitle 优先 titleKey，'
      + '桌面 21 处已键化；/m/* 移动路由无 titleKey 属移动范围另立项）。行内 title'
      + ' 不直出用户界面，新桌面路由必须带 titleKey 才有英文（i18n-locale spec 钉行为）'
  },
  {
    file: 'src/constants/status-config.ts',
    contains: '做种中',
    reason: '状态选项 label 为 zh 数据身份：所有展示位均经 localizedStatusOptions/getStatusText 键化（做种中/下载中同串两处）'
  },
  {
    file: 'src/constants/status-config.ts',
    contains: '下载中',
    reason: '同上：状态 label 数据身份（STATUS_OPTIONS 与 statusTextMap 两处）'
  },
  {
    file: 'src/constants/status-config.ts',
    contains: '已暂停',
    reason: '同上：状态 label 数据身份'
  },
  {
    file: 'src/constants/status-config.ts',
    contains: '下载队列',
    reason: '同上：状态 label 数据身份'
  },
  {
    file: 'src/constants/status-config.ts',
    contains: '错误',
    reason: '同上：状态 label/映射数据身份（label 与 statusTextMap 两处）'
  },
  {
    file: 'src/constants/status-config.ts',
    contains: '检查中',
    reason: '同上：状态 label 数据身份'
  },
  {
    file: 'src/constants/status-config.ts',
    contains: '已完成',
    reason: '同上：statusTextMap 数据身份'
  },
  {
    file: 'src/constants/status-config.ts',
    contains: '未知',
    reason: '同上：statusTextMap 未知码兑底（展示走 getStatusText 键）'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '标签'",
    reason: '高级搜索字段 label 为键缺失兑底数据（searchFieldLabel：localized || label，防新增字段漏登键时渲染空）'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: 'Tracker 信息'",
    reason: '同上：字段 label 兑底数据'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '种子名称'",
    reason: '同上：字段 label 兑底数据'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '种子大小'",
    reason: '同上：字段 label 兑底数据'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '保存路径'",
    reason: '同上：字段 label 兑底数据'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '状态'",
    reason: '同上：字段 label 兑底数据'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '下载器'",
    reason: '同上：字段 label 兑底数据（动态候选选项为后端数据 B03）'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '分类'",
    reason: '同上：字段 label 兑底数据（动态候选选项为后端数据 B03）'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '超级做种'",
    reason: '同上：字段 label 兑底数据'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '添加时间'",
    reason: '同上：字段 label 兑底数据'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '完成时间'",
    reason: '同上：字段 label 兑底数据'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '比率'",
    reason: '同上：字段 label 兑底数据（比率/比率限制同串前缀）'
  },
  {
    file: 'src/components/torrents/advancedSearchFields.ts',
    contains: "label: '比率限制'",
    reason: '同上：字段 label 兑底数据'
  },
  {
    file: 'src/components/torrents/advancedSearchState.ts',
    contains: 'name: group.name || `条件组${groupIndex + 1}`',
    reason: 'T01 冻结：回退组名进入 API 载荷（groups[].name 业务参数），与后端预设组名同语义层，'
      + '两语言 groups 保持一致（行内已有注释钉住）'
  },
  // ── v1.0.7 合入（dev1.0.7）的 MCP/MoviePilot 增量：种子详情「媒体库」页签与设置页新页签 label。
  // 属新功能面待双语另立项（PLANS/merge-dev107-into-dev.md P4.3）；行级登记保留文件其余部分的审计覆盖。
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '媒体库',
    reason: 'v1.0.7 媒体库页签：加载/失败/空态/表头「媒体库路径」与页签 label 常量，待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '整理',
    reason: 'v1.0.7 媒体库页签：整理记录计数/整理方式表头/整理失败标记，待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '刷新',
    reason: 'v1.0.7 媒体库页签：手动刷新按钮，待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '更新失败，显示上次数据',
    reason: 'v1.0.7 媒体库页签：降级提示，待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '媒体标题',
    reason: 'v1.0.7 媒体库页签：表头，待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '季 / 集',
    reason: 'v1.0.7 媒体库页签：表头，待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '源文件路径',
    reason: 'v1.0.7 媒体库页签：表头，待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '实例',
    reason: 'v1.0.7 媒体库页签：表头（MoviePilot 实例），待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '未知标题',
    reason: 'v1.0.7 媒体库页签：标题回退，待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '复制',
    reason: 'v1.0.7 媒体库页签：整理方式展示名（copy），待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '移动',
    reason: 'v1.0.7 媒体库页签：整理方式展示名（move），待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '软链接',
    reason: 'v1.0.7 媒体库页签：整理方式展示名（link），待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '硬链接',
    reason: 'v1.0.7 媒体库页签：整理方式展示名（hardlink），待双语另立项'
  },
  {
    file: 'src/views/torrents/components/TrackerDetailCard.vue',
    contains: '未找到 MoviePilot 整理记录',
    reason: 'v1.0.7 媒体库页签：空态说明，待双语另立项'
  },
  {
    file: 'src/views/torrents/mixins/detailTabsData.ts',
    contains: "error: res.msg || '获取媒体库关联失败'",
    reason: 'v1.0.7 媒体库页签：错误兑底文案，待双语另立项'
  },
  {
    file: 'src/views/settings/index.vue',
    contains: 'label="MCP 服务"',
    reason: 'v1.0.7 设置页新页签 label（MCP/MoviePilot 面板已整体排除，此行保留文件其余部分审计）'
  }
]

function isAllowlisted(file: string, line: string): boolean {
  return ALLOWLIST.some(entry => entry.file === file && line.includes(entry.contains))
}

/** 提取「非注释、非 console、非样式段」的行；返回违规行（含中文且不在白名单）。
 *
 * P6-5 增强：①行内 HTML 注释（`</div> <!-- ... -->`）整段剔除；
 * ②行尾开启的块注释（`code /* ...`）不再误报并进入块注释态。
 */
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
    let code = line.replace(/\/\/.*$/, '')
    // 行内 HTML 注释（含跨 `<a <!-- --> b` 的单行形态）整段剔除
    code = code.replace(/<!--[\s\S]*?-->/g, '')
    // 行内自闭块注释剔除；行尾开启的块注释则截断并进入块注释态
    const blockOpen = code.indexOf('/*')
    if (blockOpen >= 0) {
      code = code.slice(0, blockOpen)
      inBlockComment = true
    }
    if (!/[\u4e00-\u9fff]/.test(code)) return
    const entry = `${file}:${index + 1} ${trimmed}`
    if (!isAllowlisted(file, trimmed)) violations.push(entry)
  })

  return violations
}

describe('双语遗留审计门禁（P6-5 起全桌面负向排除，零漏译）', () => {
  it('扫描集（全桌面减排除清单）无未列入白名单的用户可见中文', () => {
    const files = collectAuditedFiles()
    // 防空转：确认扫描集规模合理（当前约 190+ 桌面文件）
    expect(files.length).toBeGreaterThan(150)
    const violations = files.flatMap(findChineseViolations)
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

  it('PlatformCapabilityPanel：组件已按 dev1.0.7 282f494 移除，禁止从历史恢复（合并 PLANS/merge-dev107-into-dev.md 类 B）', () => {
    // 设置页「主机能力」页签与组件在 dev1.0.7 刻意移除（能力矩阵保留 API，仅去 UI 入口）；
    // 若误恢复组件，此处的源码契约（settings.capability 键）已随语言包演进漂移，
    // 必红提醒重新评估，而不是静默放行。
    expect(existsSync(resolve(__dirname, '../../src/components/settings/PlatformCapabilityPanel.vue'))).toBe(false)
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
