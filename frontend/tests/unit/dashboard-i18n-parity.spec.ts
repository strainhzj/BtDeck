/**
 * 仪表盘 i18n 契约（仪表盘一期 W5）。
 *
 * - zh/en dashboard 组键结构完全平齐（漏译即红）；
 * - 决策口径钉死：任务 KPI "已启用"（决策 #1，非执行态）、流量文案
 *   "近 24h"（M-2，不用"今日"）、站点显示名=host（M-4，无站点别名）；
 * - i18n-leftover-guard 覆盖的新文件不含硬编码用户可见中文的组件面抽查。
 */
import { dashboard as zh } from '@/i18n/locales/zh-CN/dashboard'
import { dashboard as en } from '@/i18n/locales/en/dashboard'
import { setLocale, translate } from '@/i18n'

/** 递归取叶子键集合（点路径） */
function leafKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null ? leafKeys(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`]
  )
}

afterEach(() => setLocale('zh-CN'))

describe('dashboard zh/en 键平齐', () => {
  it('en 与 zh 叶子键集合完全一致（双向无缺漏）', () => {
    const zhKeys = leafKeys(zh as unknown as Record<string, unknown>).sort()
    const enKeys = leafKeys(en as unknown as Record<string, unknown>).sort()
    expect(enKeys).toEqual(zhKeys)
  })

  it('键数符合一期新增面规模（60+ 键）', () => {
    expect(leafKeys(zh as unknown as Record<string, unknown>).length).toBeGreaterThanOrEqual(60)
  })
})

describe('决策口径文案钉死', () => {
  it('任务 KPI = "已启用"口径（决策 #1），执行态提示明示二期', () => {
    setLocale('zh-CN')
    expect(translate('dashboard.kpi.enabledUnit')).toBe('已启用')
    expect(translate('dashboard.kpi.enabledNote')).toContain('已启用口径')
    expect(translate('dashboard.kpi.enabledNote')).toContain('二期')
  })

  it('流量卡 = "近 24h"口径（M-2），标题不含"今日"', () => {
    setLocale('zh-CN')
    expect(translate('dashboard.widgets.traffic.title')).toBe('近 24h 流量 · 分时')
    expect(translate('dashboard.widgets.traffic.title')).not.toContain('今日')
  })

  it('大屏近 24h 上传 = "近 24h 上传"', () => {
    setLocale('zh-CN')
    expect(translate('dashboard.screen.upload24h')).toBe('近 24h 上传')
    setLocale('en')
    expect(translate('dashboard.screen.upload24h')).toBe('Upload (last 24h)')
  })

  it('站点卡注释口径：host 聚合 + 种子去重（M-4），无站点别名承诺', () => {
    setLocale('zh-CN')
    expect(translate('dashboard.widgets.sites.note')).toContain('host')
    expect(translate('dashboard.widgets.sites.note')).toContain('去重')
  })

  it('编辑提示注明 localStorage 范围与"最后保存者生效"（一期边界）', () => {
    setLocale('zh-CN')
    expect(translate('dashboard.edit.hint')).toContain('本浏览器')
    expect(translate('dashboard.edit.hint')).toContain('最后保存')
    expect(translate('dashboard.edit.hint')).toContain('二期')
  })

  it('en 关键键输出英文（非 zh 回退）', () => {
    setLocale('en')
    expect(translate('dashboard.preset.overview')).toBe('Overview')
    expect(translate('dashboard.widgets.health.title')).toBe('Instance health')
    expect(translate('dashboard.widgets.tasks.enabled')).toBe('Enabled')
  })
})
