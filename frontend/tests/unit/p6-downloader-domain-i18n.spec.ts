/**
 * P6-2 下载器域收尾双语回归（设置弹窗页签骨架 + 速度/高级/路径/标签/模板）。
 *
 * 保护面：
 * A. 行为契约：新增 downloader.* 子树在 zh 下逐字节保持原内联文案（零回归），
 *    en 下输出英文（含插值）；键化数据数组（星期/高级字段/映射类型）按当前语言渲染；
 * B. 源码契约：8 个组件全部走 $t/translate，关键位置无中文字面量，
 *    相对时间与确认链路走 i18n 源。
 *
 * 审计门禁（i18n-leftover-guard）已把本批 8 文件纳入扫描集；
 * 本 spec 补「键存在 + zh 值精确 + 键化数据渲染」的正面契约。
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { setLocale, translate } from '@/i18n'
import {
  templateDisplayDescription,
  templateDisplayName
} from '@/views/downloader/template-presets'

const read = (file: string): string => readFileSync(resolve(__dirname, '../../', file), 'utf-8')

afterEach(() => setLocale('zh-CN'))

// ====================================================================
// A. 行为契约
// ====================================================================

describe('P6-2 设置弹窗页签骨架（downloader.tabs）', () => {
  it('zh 逐字节与原内联一致', () => {
    setLocale('zh-CN')
    expect(translate('downloader.tabs.speedTitle')).toBe('速度设置')
    expect(translate('downloader.tabs.speedDesc')).toBe('全局与分时段限速')
    expect(translate('downloader.tabs.speedSectionTitle')).toBe('速率与调度策略')
    expect(translate('downloader.tabs.liveApply')).toBe('实时应用')
    expect(translate('downloader.tabs.advancedLabel')).toBe('高级设置')
    expect(translate('downloader.tabs.pathSectionTitle')).toBe('存储路径拓扑')
    expect(translate('downloader.tabs.bidirectional')).toBe('双向映射')
    expect(translate('downloader.tabs.needBasicTitle')).toBe('请先保存基本信息')
    expect(translate('downloader.tabs.structureSync')).toBe('结构同步')
  })

  it('en 输出英文（页签/空态/段标题）', () => {
    setLocale('en')
    expect(translate('downloader.tabs.speedTitle')).toBe('Speed Settings')
    expect(translate('downloader.tabs.needBasicTitle')).toBe('Save the basic information first')
    expect(translate('downloader.tabs.pathSectionTitle')).toBe('Storage path topology')
    expect(translate('downloader.tabs.structureSync')).not.toMatch(/[\u4e00-\u9fff]/)
  })
})

describe('P6-2 速度设置（downloader.speed）', () => {
  it('zh 逐字节 + 规则名插值', () => {
    setLocale('zh-CN')
    expect(translate('downloader.speed.globalSection')).toBe('全局速度限制')
    expect(translate('downloader.speed.zeroUnlimited')).toBe('设置为 0 表示不限制')
    expect(translate('downloader.speed.scheduleSwitch')).toBe('启用分时段限速')
    expect(translate('downloader.speed.ruleName', { index: 3 })).toBe('规则 3')
    expect(translate('downloader.speed.addRule')).toBe('添加限速规则')
    expect(translate('downloader.speed.weekday.mon')).toBe('周一')
    expect(translate('downloader.speed.weekday.sun')).toBe('周日')
  })

  it('en：规则名与星期本地化', () => {
    setLocale('en')
    expect(translate('downloader.speed.ruleName', { index: 2 })).toBe('Rule 2')
    expect(translate('downloader.speed.weekday.mon')).toBe('Monday')
    expect(translate('downloader.speed.zeroUnlimited')).toContain('0')
  })
})

describe('P6-2 高级设置（downloader.advanced）', () => {
  it('zh 逐字节 + 双下载器互斥提示完整', () => {
    setLocale('zh-CN')
    expect(translate('downloader.advanced.qbSection')).toBe('qBittorrent 专属设置')
    expect(translate('downloader.advanced.trSection')).toBe('Transmission 专属设置')
    expect(translate('downloader.advanced.supported')).toBe('已支持')
    expect(translate('downloader.advanced.notApplicable')).toBe('不适用')
    expect(translate('downloader.advanced.qbUnavailable'))
      .toBe('当前下载器为 Transmission，qBittorrent 专属设置不可用。如需配置 qBittorrent 选项，请切换到 qBittorrent 下载器。')
    expect(translate('downloader.advanced.trUnavailable'))
      .toBe('当前下载器为 qBittorrent，Transmission 专属设置不可用。如需配置 Transmission 选项，请切换到 Transmission 下载器。')
    expect(translate('downloader.advanced.fields.globalMaxConnectionsHint')).toBe('同时连接的最大 Peer 数量')
  })

  it('en：互斥提示不残留中文且指向正确下载器', () => {
    setLocale('en')
    expect(translate('downloader.advanced.qbUnavailable')).toContain('Transmission')
    expect(translate('downloader.advanced.qbUnavailable')).not.toMatch(/[\u4e00-\u9fff]/)
    expect(translate('downloader.advanced.fields.downloadQueueHint')).not.toMatch(/[\u4e00-\u9fff]/)
  })
})

describe('P6-2 路径映射（downloader.pathMapping）', () => {
  it('zh 逐字节（标题/列/空态/提示/预设占位符）', () => {
    setLocale('zh-CN')
    expect(translate('downloader.pathMapping.headerTitle')).toBe('路径映射配置')
    expect(translate('downloader.pathMapping.colInternal')).toBe('内部路径')
    expect(translate('downloader.pathMapping.autoDiscovered')).toBe('系统自动发现')
    expect(translate('downloader.pathMapping.preset.local')).toBe('本地路径')
    expect(translate('downloader.pathMapping.preset.networkExternalPlaceholder'))
      .toBe('建议使用 // 开头，如：//192.168.5.51/pt2/')
    expect(translate('downloader.pathMapping.preset.windowsExternalPlaceholder')).toBe('Windows路径，如: C:\\Downloads\\')
    expect(translate('downloader.pathMapping.msg.rowAutoDiscovered', { index: 2, name: 'm1' }))
      .toBe('第 2 行（m1）为自动发现的路径，外部路径为空。请补充外部路径配置后再保存。')
    expect(translate('downloader.pathMapping.msg.rowExternalRequiredManual', { index: 5 }))
      .toBe('第 5 行：外部路径不能为空（无法根据 path_mapping_rules 自动生成，请手动填写）')
  })

  it('en：安全提示（系统自动发现/行级校验）输出英文', () => {
    setLocale('en')
    expect(translate('downloader.pathMapping.preset.local')).toBe('Local path')
    expect(translate('downloader.pathMapping.msg.rowAutoDiscovered', { index: 2, name: 'm1' })).toContain('Row 2')
    expect(translate('downloader.pathMapping.msg.rowExternalRequiredManual', { index: 5 })).toContain('Row 5')
  })
})

describe('P6-2 路径维护（downloader.pathMaintenance）', () => {
  it('zh 逐字节（危险删除确认/启停/相对时间）', () => {
    setLocale('zh-CN')
    expect(translate('downloader.pathMaintenance.headerTitle')).toBe('下载器路径管理')
    expect(translate('downloader.pathMaintenance.typeDefault')).toBe('默认路径')
    expect(translate('downloader.pathMaintenance.disabledByUser')).toBe('手动禁用')
    expect(translate('downloader.pathMaintenance.msg.deleteConfirm', { path: '/data/x' }))
      .toBe('确认删除路径"/data/x"吗？删除后该路径将被禁用。')
    expect(translate('downloader.pathMaintenance.msg.toggleDisabled')).toBe('已禁用')
    expect(translate('downloader.pathMaintenance.time.minutesAgo', { n: 5 })).toBe('5分钟前')
  })

  it('en：删除确认明示后续影响', () => {
    setLocale('en')
    const msg = translate('downloader.pathMaintenance.msg.deleteConfirm', { path: '/data/x' })
    expect(msg).toContain('/data/x')
    expect(msg.toLowerCase()).toContain('disabled')
  })
})

describe('P6-2 标签/分类管理（downloader.tag）', () => {
  it('zh 逐字节（列表/弹窗/危险批量删除/相对时间）', () => {
    setLocale('zh-CN')
    expect(translate('downloader.tag.needBasicDesc')).toBe('标签/分类管理需要下载器创建后才能使用')
    expect(translate('downloader.tag.typeCategory')).toBe('分类')
    expect(translate('downloader.tag.createdAt', { time: '今天' })).toBe('创建于 今天')
    expect(translate('downloader.tag.batchDeleteWarning')).toBe('此操作不可撤销，删除后将无法恢复')
    expect(translate('downloader.tag.categoryDialogPrefix')).toBe('分类"')
    expect(translate('downloader.tag.categoryDialogSuffix')).toBe('"下还有种子，')
    expect(translate('downloader.tag.msg.deleteConfirm', { name: 't1' })).toBe('确定要删除标签"t1"吗？')
    expect(translate('downloader.tag.time.yesterday')).toBe('昨天')
    expect(translate('downloader.tag.time.weeksAgo', { n: 2 })).toBe('2 周前')
  })

  it('en：批量删除警告与分类转移文案为英文', () => {
    setLocale('en')
    expect(translate('downloader.tag.batchDeleteWarning').toLowerCase()).toContain('cannot be undone')
    expect(translate('downloader.tag.categoryDialogDesc')).toContain('category')
    expect(translate('downloader.tag.time.today')).toBe('Today')
  })
})

describe('P6-2 模板选择（downloader.template）', () => {
  it('zh 逐字节（覆盖警告为危险语义）', () => {
    setLocale('zh-CN')
    expect(translate('downloader.template.title')).toBe('从模板选择配置')
    expect(translate('downloader.template.systemDefault')).toBe('系统默认')
    expect(translate('downloader.template.selectedPrefix')).toBe('已选择:')
    expect(translate('downloader.template.confirmTitle')).toBe('确认直接应用模板')
    expect(translate('downloader.template.overwriteWarning')).toBe('直接应用将覆盖当前下载器配置，是否继续？')
    expect(translate('downloader.template.unknownType')).toBe('通用')
  })

  it('en：覆盖警告明示会覆写配置', () => {
    setLocale('en')
    expect(translate('downloader.template.overwriteWarning').toLowerCase()).toContain('overwrites')
    expect(translate('downloader.template.msg.invalidId')).not.toMatch(/[\u4e00-\u9fff]/)
  })
})

// ====================================================================
// B. 源码契约
// ====================================================================

describe('P6-2 源码契约', () => {
  const FILES = {
    dialog: 'src/views/downloader/components/DownloaderSettingsDialog.vue',
    speed: 'src/views/downloader/components/SpeedSettingsTab.vue',
    advanced: 'src/views/downloader/components/AdvancedSettingsTab.vue',
    pathManagement: 'src/views/downloader/components/PathManagementTab.vue',
    pathMapping: 'src/views/downloader/components/PathMappingTab.vue',
    pathMaintenance: 'src/views/downloader/components/DownloaderPathManagement.vue',
    tag: 'src/views/downloader/components/TagManagementTab.vue',
    template: 'src/views/downloader/components/TemplateSelectionDialog.vue',
    types: 'src/views/downloader/types.ts'
  }

  it('设置弹窗页签骨架全部走键', () => {
    const src = read(FILES.dialog)
    for (const key of [
      'downloader.tabs.speedTitle', 'downloader.tabs.speedSectionTitle', 'downloader.tabs.liveApply',
      'downloader.tabs.advancedLabel', 'downloader.tabs.pathSectionTitle', 'downloader.tabs.bidirectional',
      'downloader.tabs.tagSectionDesc', 'downloader.tabs.structureSync', 'downloader.tabs.needBasicPath'
    ]) {
      expect(src).toContain(`$t('${key}')`)
    }
    expect(src.includes('以紧凑时间规则控制全局带宽和上下行窗口。')).toBe(false)
  })

  it('键化数据数组：星期 labelKey / 高级字段 labelKey+hintKey / 映射类型三键', () => {
    const speed = read(FILES.speed)
    expect(speed.match(/labelKey: 'downloader\.speed\.weekday\./g)?.length).toBe(7)
    expect(speed).toContain('{{ $t(day.labelKey) }}')

    const advanced = read(FILES.advanced)
    expect(advanced.match(/labelKey: 'downloader\.advanced\.fields\./g)?.length).toBe(6)
    expect(advanced.match(/hintKey: 'downloader\.advanced\.fields\./g)?.length).toBe(6)
    expect(advanced).toContain('{{ $t(field.labelKey) }}')
    expect(advanced).toContain('{{ $t(field.hintKey) }}')

    const pathMapping = read(FILES.pathMapping)
    expect(pathMapping.match(/labelKey: 'downloader\.pathMapping\.preset\./g)?.length).toBe(5)
    expect(pathMapping.match(/descriptionKey: 'downloader\.pathMapping\.preset\./g)?.length).toBe(5)
    expect(pathMapping.match(/placeholderKey: 'downloader\.pathMapping\.preset\./g)?.length).toBe(5)

    const types = read(FILES.types)
    expect(types).toContain('labelKey: string')
    expect(types).toContain('descriptionKey: string')
    expect(types).toContain('placeholderKey: string')
  })

  it('路径提示与占位符经 translate 取值（不再硬编码中文提示表）', () => {
    const src = read(FILES.pathMapping)
    expect(src).toContain("import { apiErrorMessage, apiResponseMessage, translate } from '@/i18n'")
    expect(src).toContain('return key ? translate(key) :')
    // 关键旧中文不得回流
    expect(src.includes('下载器内路径，如: /downloads/')).toBe(false)
    expect(src.includes("option?.placeholder || '输入路径'")).toBe(false)
  })

  it('标签页相对时间与确认链路走 i18n（不再自建中文档位）', () => {
    const src = read(FILES.tag)
    expect(src).toContain("import { translate } from '@/i18n'")
    expect(src).toContain("translate('downloader.tag.time.yesterday')")
    expect(src).toContain("translate('downloader.tag.time.monthsAgo'")
    expect(src.includes("return '今天'")).toBe(false)
    expect(src.includes("confirmButtonText: '确定'")).toBe(false)
  })

  it('路径维护页确认链路与相对时间走键', () => {
    const src = read(FILES.pathMaintenance)
    expect(src).toContain("import { translate } from '@/i18n'")
    expect(src).toContain("downloader.pathMaintenance.msg.deleteConfirm")
    expect(src).toContain("translate('downloader.pathMaintenance.time.justNow')")
    expect(src.includes("'删除确认'")).toBe(false)
  })

  it('死代码组件已移除（BasicSettingsTab 零消费方）', () => {
    expect(() => read('src/views/downloader/components/BasicSettingsTab.vue')).toThrow()
  })
})

// ====================================================================
// C. 系统预设展示映射（P6-2：preset_key → 本地化名称/描述，Q02 保留原文）
// ====================================================================

describe('P6-2 内置模板预设展示映射（template-presets）', () => {
  const PRESETS = [
    ['qb_standard', 'qBittorrent标准模板'],
    ['qb_highperf', 'qBittorrent高性能模板'],
    ['tr_standard', 'Transmission标准模板'],
    ['tr_highperf', 'Transmission高性能模板'],
    ['night_unlimited', '夜间不限速模板']
  ] as const

  it('zh：按 preset_key 返回与后端存储值逐字节一致的名称', () => {
    setLocale('zh-CN')
    PRESETS.forEach(([key, zhName]) => {
      expect(templateDisplayName({ preset_key: key, name: 'stale-name' })).toBe(zhName)
      expect(translate(`downloader.template.presets.${key}.name`)).toBe(zhName)
    })
  })

  it('描述同样按 key 展示（zh 与 default_templates.py 数值口径一致）', () => {
    setLocale('zh-CN')
    expect(templateDisplayDescription({ preset_key: 'qb_standard' }))
      .toContain('1MB/s下载')
    expect(templateDisplayDescription({ preset_key: 'night_unlimited' }))
      .toContain('分时段')
  })

  it('en：预设名称/描述本地化，不残留中文', () => {
    setLocale('en')
    expect(templateDisplayName({ preset_key: 'qb_standard' })).toBe('qBittorrent Standard')
    expect(templateDisplayName({ preset_key: 'night_unlimited' })).toBe('Night Unlimited')
    expect(templateDisplayDescription({ preset_key: 'qb_highperf' })).not.toMatch(/[\u4e00-\u9fff]/)
  })

  it('Q02：未登记 key 与用户自定义模板保留存储原文（不猜不覆盖）', () => {
    setLocale('en')
    expect(templateDisplayName({ preset_key: 'unknown_key', name: '我的自定义模板' })).toBe('我的自定义模板')
    expect(templateDisplayName({ name: '用户模板', description: 'desc' })).toBe('用户模板')
    expect(templateDisplayDescription({ name: '用户模板', description: '用户描述' })).toBe('用户描述')
    expect(templateDisplayName(null)).toBe('')
    expect(templateDisplayDescription(null)).toBe('')
  })

  it('兼容 camelCase presetKey 与空白键', () => {
    setLocale('zh-CN')
    expect(templateDisplayName({ presetKey: 'tr_standard' })).toBe('Transmission标准模板')
    expect(templateDisplayName({ preset_key: '   ' , name: 'raw' })).toBe('raw')
  })

  it('源码契约：弹窗四类展示位全部走解析器（预设名/描述/已选/确认框）', () => {
    const src = read('src/views/downloader/components/TemplateSelectionDialog.vue')
    expect(src).toContain('templateDisplayName(template)')
    expect(src).toContain('templateDisplayDescription(template)')
    expect(src).toContain('templateDisplayName(selectedTemplate)')
    expect(src.includes('{{ template.name }}')).toBe(false)
    expect(src.includes('{{ template.description }}')).toBe(false)
  })
})
